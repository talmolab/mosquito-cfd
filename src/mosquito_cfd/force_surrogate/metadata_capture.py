"""Automated ``run_metadata_<config>.json`` generation for force-surrogate cluster runs.

Replaces hand-authoring of committed provenance files (OpenSpec change
``automate-run-metadata-capture``, following PR #58's ``add-fine-grid-training-pilot`` review,
which caught a hand-typed ``final_time`` bug and a truncated-SHA bug in all 3 committed pilot
files). Every field in :func:`assemble_run_metadata`'s output is derived from an existing
artifact — nothing is re-typed by a human:

- ``run_id``, ``timestamp``, ``git`` (full 40-char SHA), ``hardware``: passed through from the
  pod's own already-produced ``run_metadata.json`` (written by
  :func:`mosquito_cfd.force_surrogate.run_one_config._write_run_metadata` on every cluster
  attempt via :func:`mosquito_cfd.force_surrogate.sidecar.capture_surrogate_run_metadata`).
- ``docker_image``: the pod file's validated ``sha256:...`` digest (single field — no separate
  mutable-tag field, unlike the committed t3c/pilot schema's ``docker_image``/``image_digest``
  split).
- ``deck_sha256``: a freshly computed SHA256 of the actual ``--deck`` file supplied, verified to
  match the pod file's recorded ``deck_sha256`` (see the trust-one-artifact guards below) and
  persisted here so deck identity remains auditable after the pod-side (uncommitted) artifacts
  are cleaned up — the old schema's equivalent field was ``inputs.hash``.
- ``config``, ``tier``: the config name and a caller-supplied tier label (e.g.
  ``"fine-grid-corpus-full"`` — a single known constant per invocation, not run-specific data).
- ``kinematics`` (``stroke_amp_deg``/``frequency_fstar``/``pitch_amp_deg``/``reynolds``),
  ``max_step``: sourced from the committed ``sweep_manifest.json``'s per-config entry.
- ``grid`` (``amr.n_cell``), ``fixed_dt`` (``ns.fixed_dt``): sourced from the generated deck file
  (not in the manifest).
- ``stability``: derived solely from ``fixed_dt`` vs. the sweep's nominal ``5e-4`` — no separate
  hand-set ``dt_reduced``-style flag.
- ``arena_max_mib``: parsed from the AMReX end-of-run "The Arena" line in ``run.log``.
- ``node``, ``gpu_model``: from the pod file's ``orchestration.node`` and ``hardware.gpus[0]``.
- ``timing.final_time`` / ``timing.timesteps``: the committed force CSV's actual **last row**
  (never the deck's ``stop_time`` — the exact bug this change fixes).
- ``timing.wall_time_s``: computed from a completed Argo workflow's persisted status timestamps
  (:func:`query_argo_workflow_status`), reflecting only the final successful attempt — or a
  caller-supplied ``--wall-time-s`` override if the source workflow has already been
  garbage-collected.
- ``orchestration``: passed through from the pod file (``workflow_uid``/``pod``/``node``/
  ``retry``), plus ``workflow_name`` if supplied.
- ``notes``: optional free-text field for genuinely exceptional commentary; omitted entirely
  (not an empty string) when not supplied.

Trust-one-artifact guards (all required, none silently skipped): the pod's reported ``status``
must be ``"completed"`` (a failed/incomplete run is refused, not silently assembled as if it
succeeded); the pod's ``deck_sha256`` must match a freshly computed hash of the ``--deck`` file
actually supplied (an operator pointing ``--deck`` at a stale/wrong file is caught, not silently
trusted); and the pod-reported row count (``rows``) must be present and must match the
CSV-derived ``timesteps`` (a missing or disagreeing count raises, never silently skipped or
preferring one value) — all three are exactly the class of "trust the wrong artifact" bug this
change exists to catch.

Non-goals: does not modify ``run_one_config.py``'s pod runtime behavior, does not touch the 3
already-committed ``examples/prelim_sweep_fine_pilot/run_metadata_*.json`` files (see
``openspec/changes/automate-run-metadata-capture/design.md`` D4), and is never invoked from CI
(operator-run only; the Argo status query needs a working ``argo``/cluster session).
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate.runner import STATUS_COMPLETED
from mosquito_cfd.force_surrogate.sidecar import validate_image_digest

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
# Anchored to "[The Arena]" specifically -- a real GPU-build run.log typically also emits
# "[The Device Arena]"/"[The Managed Arena]"/"[The Pinned Arena]" lines, which report different
# (and sometimes larger) figures; matching "Arena" unanchored would silently report the wrong
# arena's peak. "\s+" (not a literal single space) between "The" and "Arena" because AMReX pads
# the tag with extra spaces to column-align it with the longer Device/Managed/Pinned labels.
#
# AMReX's CArena::PrintUsage reports the used figure as a per-MPI-rank "[min ... max]" pair (real
# GPU run.log: "[The         Arena] max space (MB) used      spread across MPI: [7998 ... 7998]")
# -- the "bracket_max" branch captures the SECOND number (the max across ranks), not the first:
# for a genuinely multi-rank run min != max, and grabbing the first number would silently
# under-report the true peak (this repo's runs are single-rank today, so min == max and the
# distinction was invisible until checked against the actual upstream AMReX source). The
# "suffix_num" branch is a fallback for the older "... 7998 MiB" phrasing (no bracket, unit
# suffix directly after the figure) this regex originally targeted, kept for backward
# compatibility with existing fixtures in case some run.log variant ever uses it.
_ARENA_USED_RE = re.compile(
    r"\[The\s+Arena\].*?\bused\b.*?"
    r"(?:\[\s*[\d.]+\s*\.\.\.\s*(?P<bracket_max>\d+(?:\.\d+)?)\s*\]"
    r"|(?P<suffix_num>\d+(?:\.\d+)?)\s*Mi?B)",
    re.IGNORECASE,
)

# The sweep's nominal timestep (matches `sweep_manifest.json`'s top-level "dt" for every config
# that hasn't needed the CFL fallback).
NOMINAL_FIXED_DT = 5e-4


# ---------------------------------------------------------------------------
# Force CSV
# ---------------------------------------------------------------------------


def read_final_time_from_csv(csv_path: Path | str) -> tuple[float, int]:
    """Read a force CSV's actual last row for ``(final_time, timesteps)``.

    Never uses the deck's ``stop_time`` — IB-particle CSVs systematically end exactly one ``dt``
    short of it (a pre-existing writer convention, not a divergence signal).

    Args:
        csv_path: Path to the committed force CSV (``forces_<config>.csv`` /
            ``IB_Particle_1.csv``).

    Returns:
        A ``(final_time, timesteps)`` tuple: the last row's ``time`` value and the total data-row
        count.

    Raises:
        FileNotFoundError: If ``csv_path`` does not exist.
        ValueError: If the CSV has a header but no data rows.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"force CSV not found: {path}")
    with open(path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"force CSV {path} has a header but no data rows")
    return float(rows[-1]["time"]), len(rows)


# ---------------------------------------------------------------------------
# run.log
# ---------------------------------------------------------------------------


def parse_arena_max_mib(run_log_path: Path | str) -> int | None:
    """Parse the AMReX end-of-run "The Arena" max-used figure from ``run.log``.

    Args:
        run_log_path: Path to the run's captured ``run.log``.

    Returns:
        The max-used figure in MiB, or ``None`` if no Arena line is present (some ``run.log``
        variants may not include it).

    Raises:
        FileNotFoundError: If ``run_log_path`` does not exist.
    """
    path = Path(run_log_path)
    if not path.exists():
        raise FileNotFoundError(f"run.log not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = [
        float(m.group("bracket_max") or m.group("suffix_num"))
        for m in _ARENA_USED_RE.finditer(text)
    ]
    if not matches:
        return None
    return int(max(matches))


def _format_dt(value: float) -> str:
    """Format a timestep value as a compact string (``5e-4``, ``2.5e-4``)."""
    mantissa, _, exponent = f"{value:e}".partition("e")
    mantissa = mantissa.rstrip("0").rstrip(".")
    return f"{mantissa}e{int(exponent)}"


def derive_stability(
    fixed_dt: float, *, nominal_fixed_dt: float = NOMINAL_FIXED_DT
) -> str:
    """Derive a run's stability verdict solely from its ``fixed_dt``.

    No separate hand-set ``dt_reduced``-style flag is read — the fallback verdict is entirely a
    function of the ``fixed_dt`` this tool already sources mechanically from the deck.

    Args:
        fixed_dt: The config's actual ``ns.fixed_dt`` (sourced from the deck).
        nominal_fixed_dt: The sweep's standard timestep (default ``5e-4``).

    Returns:
        ``"stable_at_<nominal>"`` if ``fixed_dt`` matches the nominal value, else
        ``"stable_at_<fixed_dt>_fallback"``.
    """
    if fixed_dt == nominal_fixed_dt:
        return f"stable_at_{_format_dt(nominal_fixed_dt)}"
    return f"stable_at_{_format_dt(fixed_dt)}_fallback"


# ---------------------------------------------------------------------------
# Manifest / deck sourcing
# ---------------------------------------------------------------------------


def _load_json_clear_error(path: Path, *, label: str) -> dict:
    """Load JSON from ``path``, wrapping a decode failure in a clear, file-identified error."""
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} {path} is not valid JSON: {exc}") from exc


def parse_deck(deck_path: Path | str) -> dict[str, str]:
    """Parse an AMReX inputs deck into a ``key -> value`` map (comments stripped).

    Args:
        deck_path: Path to the generated deck (``inputs.3d.<config>``).

    Returns:
        A mapping of deck keys to their (whitespace-normalized) string values.
    """
    kv: dict[str, str] = {}
    for raw in Path(deck_path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        kv[key] = " ".join(value.split())
    return kv


def source_config_fields(
    *, manifest_path: Path | str, deck_path: Path | str, config_name: str
) -> dict[str, Any]:
    """Source kinematics/grid/fixed_dt/max_step for one config from the manifest and deck.

    Kinematics (``stroke_amp_deg``/``frequency_fstar``/``pitch_amp_deg``/``reynolds``) and
    ``max_step`` come from the committed ``sweep_manifest.json``'s per-config entry; ``grid``
    (``amr.n_cell``) and ``fixed_dt`` (``ns.fixed_dt``) come from the deck file, since the
    manifest does not record either per config.

    Args:
        manifest_path: Path to the committed ``sweep_manifest.json``.
        deck_path: Path to the config's generated deck.
        config_name: The config's name (e.g. ``"s35_f085_p45"``).

    Returns:
        A dict with keys ``kinematics`` (nested dict), ``grid``, ``fixed_dt``, ``max_step``.

    Raises:
        ValueError: If the manifest file is not valid JSON.
        KeyError: If ``config_name`` is not present in the manifest.
    """
    manifest_path = Path(manifest_path)
    manifest = _load_json_clear_error(manifest_path, label="sweep manifest")
    entry = next(
        (c for c in manifest.get("configs", []) if c.get("name") == config_name), None
    )
    if entry is None:
        available = [c.get("name") for c in manifest.get("configs", [])]
        raise KeyError(
            f"config {config_name!r} not found in manifest {manifest_path} "
            f"(available: {available})"
        )
    deck_path = Path(deck_path)
    deck = parse_deck(deck_path)

    def _entry_field(key: str) -> Any:
        if key not in entry:
            raise KeyError(
                f"manifest entry for config {config_name!r} in {manifest_path} is missing "
                f"required field {key!r}"
            )
        return entry[key]

    def _deck_field(key: str) -> str:
        if key not in deck:
            raise KeyError(
                f"deck {deck_path} for config {config_name!r} is missing required key {key!r}"
            )
        return deck[key]

    return {
        "kinematics": {
            "stroke_amp_deg": _entry_field("stroke_amp_deg"),
            "frequency_fstar": _entry_field("frequency_fstar"),
            "pitch_amp_deg": _entry_field("pitch_amp_deg"),
            "reynolds": _entry_field("reynolds"),
        },
        "grid": _deck_field("amr.n_cell"),
        "fixed_dt": float(_deck_field("ns.fixed_dt")),
        "max_step": _entry_field("max_step"),
    }


# ---------------------------------------------------------------------------
# Pod-side run_metadata.json: loading + digest/git validation
# ---------------------------------------------------------------------------


def load_pod_run_metadata(path: Path | str) -> dict[str, Any]:
    """Load the pod's own already-produced ``run_metadata.json``.

    Args:
        path: Path to the pod-side ``run_metadata.json`` (copied down from the NFS run dir).

    Returns:
        The parsed metadata dict.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the file is not valid JSON.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"pod-side run_metadata.json not found: {path}")
    return _load_json_clear_error(path, label="pod-side run_metadata.json")


def extract_docker_image(pod_metadata: dict[str, Any]) -> str:
    """Extract and validate the pod's docker image digest.

    Args:
        pod_metadata: The loaded pod-side ``run_metadata.json``.

    Returns:
        The validated ``sha256:...`` digest.

    Raises:
        ValueError: If the value is not a content-addressable digest.
    """
    return validate_image_digest(pod_metadata.get("docker_image", ""))


def extract_git_info(pod_metadata: dict[str, Any]) -> dict[str, Any]:
    """Extract the pod's ``git`` block, requiring a full 40-character commit SHA.

    Args:
        pod_metadata: The loaded pod-side ``run_metadata.json``.

    Returns:
        The ``git`` sub-dict, unchanged.

    Raises:
        ValueError: If ``git.commit`` is missing or not a full 40-character SHA.
    """
    git = dict(pod_metadata.get("git", {}))
    commit = git.get("commit", "") or ""
    if not _FULL_SHA_RE.match(commit):
        raise ValueError(
            f"git commit must be a full 40-character SHA; got {commit!r} "
            f"(length {len(commit)})"
        )
    return git


# ---------------------------------------------------------------------------
# Argo workflow status
# ---------------------------------------------------------------------------


# Generous but bounded: protects an interactive operator run from hanging indefinitely on a
# half-torn-down/partitioned cluster session (raised in review; this tool has no other timeout
# anywhere since every other input is a local file read).
_ARGO_QUERY_TIMEOUT_S = 30


def query_argo_workflow_status(workflow_name: str) -> dict[str, Any]:
    """Query a completed Argo workflow's persisted status (read-only, works after completion).

    Args:
        workflow_name: The Argo workflow's name (known to the operator from their own
            submission step).

    Returns:
        The parsed ``argo get <workflow-name> -o json`` output.

    Raises:
        RuntimeError: If the ``argo`` CLI is unavailable, the query fails, times out, or the
            output is not valid JSON.
    """
    try:
        completed = subprocess.run(
            ["argo", "get", workflow_name, "-o", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_ARGO_QUERY_TIMEOUT_S,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "`argo` CLI not found; is it installed and on PATH?"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"`argo get {workflow_name} -o json` did not return within "
            f"{_ARGO_QUERY_TIMEOUT_S}s; the cluster session may be unresponsive. Retry, or "
            "supply --wall-time-s manually."
        ) from exc
    if completed.returncode != 0:
        raise RuntimeError(
            f"`argo get {workflow_name} -o json` failed (exit {completed.returncode}): "
            f"{completed.stderr}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"`argo get {workflow_name} -o json` did not return valid JSON: {exc}"
        ) from exc


def _parse_argo_timestamp(value: str) -> datetime:
    """Parse an Argo/Kubernetes ISO-8601 timestamp (``Z``-suffixed) into a ``datetime``."""
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def compute_wall_time_s(status: dict[str, Any]) -> float:
    """Compute wall-clock duration from a completed Argo workflow's node timestamps.

    Reflects only the final **successful** attempt's duration — a failed attempt followed by a
    successful retry contributes nothing to the result. Excludes Argo's own ``"Retry"``-type
    wrapper node: when a step has a ``retryStrategy`` (as
    ``cluster/argo/workflow-templates/force-surrogate-single-config.yaml`` does), Argo emits a
    wrapper node whose ``phase`` also becomes ``"Succeeded"`` but whose ``startedAt`` is the
    *first* (failed) attempt's start — including it would silently inflate the result by the
    failed attempt's duration. Timestamps are parsed to ``datetime`` (not compared as raw
    strings) so mixed sub-second-precision formatting can't misorder attempts.

    Args:
        status: The parsed Argo workflow status (as returned by
            :func:`query_argo_workflow_status`).

    Returns:
        The successful attempt's duration in seconds.

    Raises:
        ValueError: If no non-Retry node has phase ``"Succeeded"`` with both ``startedAt`` and
            ``finishedAt`` timestamps.
    """
    nodes = status.get("status", {}).get("nodes", {})
    candidates = []
    for node in nodes.values():
        if node.get("phase") != "Succeeded" or node.get("type") == "Retry":
            continue
        started_raw, finished_raw = node.get("startedAt"), node.get("finishedAt")
        if not started_raw or not finished_raw:
            continue
        candidates.append(
            (_parse_argo_timestamp(started_raw), _parse_argo_timestamp(finished_raw))
        )
    if not candidates:
        raise ValueError(
            "Argo workflow status has no non-Retry Succeeded node with both startedAt and "
            "finishedAt timestamps; cannot compute wall_time_s"
        )
    started, finished = max(candidates, key=lambda pair: pair[1])
    return (finished - started).total_seconds()


def resolve_wall_time_s(
    *,
    workflow_name: str | None,
    wall_time_s_override: float | None = None,
    argo_status_query: Callable[[str], dict[str, Any]] = query_argo_workflow_status,
) -> float:
    """Resolve ``wall_time_s``, preferring a manual override over an Argo query.

    Args:
        workflow_name: The Argo workflow's name; required unless an override is supplied.
        wall_time_s_override: A manually-supplied wall time (``--wall-time-s``), used verbatim
            when present — the Argo query is never attempted.
        argo_status_query: Injectable query function (tests pass a fake).

    Returns:
        The resolved wall-clock duration in seconds.

    Raises:
        ValueError: If neither ``workflow_name`` nor ``wall_time_s_override`` is supplied.
    """
    if wall_time_s_override is not None:
        return float(wall_time_s_override)
    if not workflow_name:
        raise ValueError("workflow_name is required unless --wall-time-s is supplied")
    return compute_wall_time_s(argo_status_query(workflow_name))


# ---------------------------------------------------------------------------
# Schema assembler
# ---------------------------------------------------------------------------


def assemble_run_metadata(
    *,
    pod_metadata_path: Path | str,
    csv_path: Path | str,
    run_log_path: Path | str,
    manifest_path: Path | str,
    deck_path: Path | str,
    config_name: str,
    tier: str,
    workflow_name: str | None = None,
    wall_time_s: float | None = None,
    argo_status_query: Callable[[str], dict[str, Any]] = query_argo_workflow_status,
    notes: str | None = None,
) -> dict[str, Any]:
    """Assemble a normalized ``run_metadata_<config>.json`` from existing artifacts.

    See the module docstring for the full schema and where each field is sourced from.

    Args:
        pod_metadata_path: Path to the pod's own ``run_metadata.json``.
        csv_path: Path to the committed force CSV.
        run_log_path: Path to the run's ``run.log``.
        manifest_path: Path to the committed ``sweep_manifest.json``.
        deck_path: Path to the config's generated deck.
        config_name: The config's name.
        tier: A caller-supplied label for which corpus/tier produced this run (e.g.
            ``"fine-grid-corpus-full"``).
        workflow_name: The Argo workflow's name (required unless ``wall_time_s`` is supplied).
        wall_time_s: Manual override for ``timing.wall_time_s``, bypassing the Argo query
            entirely (for a workflow already garbage-collected).
        argo_status_query: Injectable Argo status-query function (tests pass a fake).
        notes: Optional free-text commentary; omitted from the output entirely when ``None``.

    Returns:
        The assembled, normalized metadata dict.

    Raises:
        FileNotFoundError: If any input file is missing.
        ValueError: If any input is malformed, the docker digest or git commit fails validation,
            the pod-reported status is not ``"completed"``, the ``--deck`` file's hash doesn't
            match the pod-recorded ``deck_sha256``, or the pod-reported row count is missing or
            disagrees with the CSV-derived timestep count.
        KeyError: If ``config_name`` is not present in the manifest, or the manifest entry/deck
            is missing a required field.
    """
    pod_metadata = load_pod_run_metadata(pod_metadata_path)
    docker_image = extract_docker_image(pod_metadata)
    git_info = extract_git_info(pod_metadata)

    pod_status = pod_metadata.get("status")
    if pod_status != STATUS_COMPLETED:
        raise ValueError(
            f"pod-reported status for config {config_name!r} is {pod_status!r}, not "
            f"{STATUS_COMPLETED!r}; refusing to assemble metadata for a non-completed run"
        )

    deck_path = Path(deck_path)
    pod_deck_sha256 = pod_metadata.get("deck_sha256")
    if not pod_deck_sha256:  # catches both an absent key and an empty/null value
        raise ValueError(
            f"pod-side run_metadata.json for config {config_name!r} has no deck_sha256; "
            "cannot verify the supplied --deck is the one actually executed"
        )
    actual_deck_sha256 = hash_file(deck_path)
    if actual_deck_sha256 != pod_deck_sha256:
        raise ValueError(
            f"--deck {deck_path} (sha256:{actual_deck_sha256}) does not match the pod-recorded "
            f"deck_sha256 ({pod_deck_sha256}) for config {config_name!r}; the supplied deck is "
            "not the one actually executed"
        )

    final_time, timesteps = read_final_time_from_csv(csv_path)
    if "rows" not in pod_metadata:
        raise ValueError(
            f"pod-side run_metadata.json for config {config_name!r} has no 'rows' field; "
            "cannot cross-validate against the CSV-derived timestep count"
        )
    pod_rows = pod_metadata["rows"]
    if int(pod_rows) != timesteps:
        raise ValueError(
            f"pod-reported row count ({pod_rows}) disagrees with the CSV-derived timestep "
            f"count ({timesteps}) for config {config_name!r}"
        )

    arena_max_mib = parse_arena_max_mib(run_log_path)
    config_fields = source_config_fields(
        manifest_path=manifest_path, deck_path=deck_path, config_name=config_name
    )
    stability = derive_stability(config_fields["fixed_dt"])

    orchestration = dict(pod_metadata.get("orchestration", {}))
    if workflow_name is not None:
        orchestration["workflow_name"] = workflow_name

    resolved_wall_time_s = resolve_wall_time_s(
        workflow_name=workflow_name,
        wall_time_s_override=wall_time_s,
        argo_status_query=argo_status_query,
    )

    hardware = pod_metadata.get("hardware", {})
    gpus = hardware.get("gpus") or []
    gpu_model = gpus[0].get("model") if gpus else None

    result: dict[str, Any] = {
        "run_id": pod_metadata.get("run_id"),
        "timestamp": pod_metadata.get("timestamp"),
        "git": git_info,
        "docker_image": docker_image,
        "deck_sha256": actual_deck_sha256,
        "hardware": hardware,
        "config": config_name,
        "tier": tier,
        "kinematics": config_fields["kinematics"],
        "grid": config_fields["grid"],
        "fixed_dt": config_fields["fixed_dt"],
        "max_step": config_fields["max_step"],
        "stability": stability,
        "arena_max_mib": arena_max_mib,
        "node": orchestration.get("node"),
        "gpu_model": gpu_model,
        "timing": {
            "final_time": final_time,
            "timesteps": timesteps,
            "wall_time_s": resolved_wall_time_s,
        },
        "orchestration": orchestration,
    }
    if notes is not None:
        result["notes"] = notes
    return result
