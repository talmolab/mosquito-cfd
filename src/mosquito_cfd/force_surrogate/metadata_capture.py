"""Automated ``run_metadata_<config>.json`` generation for force-surrogate cluster runs.

Replaces hand-authoring of committed provenance files (OpenSpec change
``automate-run-metadata-capture``, following PR #58's ``add-fine-grid-training-pilot`` review,
which caught a hand-typed ``final_time`` bug and a truncated-SHA bug in all 3 committed pilot
files). Every field in :func:`assemble_run_metadata`'s output is derived from an existing
artifact — nothing is re-typed by a human:

- ``run_id``, ``timestamp``, ``hardware``: passed through from the pod's own already-produced
  ``run_metadata.json`` (written by
  :func:`mosquito_cfd.force_surrogate.run_one_config._write_run_metadata` on every cluster
  attempt via :func:`mosquito_cfd.force_surrogate.sidecar.capture_surrogate_run_metadata`).
- ``git`` (always a full 40-char SHA, via :func:`resolve_git_info`): a caller-supplied
  ``--git-commit`` override, used verbatim when present (for pod images with no ``.git``
  directory at all, issue #66, that predate the baked-image fallback below) -- otherwise the
  pod's own ``git`` block, verbatim (see :func:`extract_git_info`). A pod-produced ``git`` block
  can itself already be a build-time-baked fallback rather than a live ``git`` query (see
  :func:`mosquito_cfd.benchmarks.metadata.get_git_info`); either fallback path (CLI override or
  baked-image) adds a ``source`` key (``"cli-override"`` / ``"docker-image-build-arg"``) absent
  from a normal live-git-derived block, and omits ``branch``/``dirty``/``diff_hash``/
  ``repository`` since none of those are knowable without an actual ``.git`` to inspect.
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
- ``grid`` (``amr.n_cell``), ``fixed_dt`` (``ns.fixed_dt``), ``cfl`` (``ns.cfl``): sourced from
  the generated deck file (not in the manifest).
- ``stability``: derived from ``fixed_dt`` (deck-declared intent) AND the run's *observed*
  timestep behaviour (see ``realized_dt``/``interior_dt_below_nominal`` below) — no separate
  hand-set flag. ``fixed_dt`` alone cannot report a CFL-limited run, since ``ns.cfl`` can reduce
  the realized timestep below the deck's declared value independent of any deck-level fallback.
- ``realized_dt``, ``interior_dt_below_nominal``, ``cycles_completed``, ``reached_stop_time``:
  what the run *did*, as opposed to what it was asked to do. ``realized_dt`` (min/mean/max/
  frac_below_nominal) is parsed from ``run.log``'s full-precision per-step ``DT`` output (see
  :func:`read_dt_series_from_run_log`), not by differencing the force CSV's ``time`` column,
  which is written at six significant figures and can quantize a differenced timestep above the
  ``ns.fixed_dt`` ceiling the solver cannot have taken. ``interior_dt_below_nominal`` excludes
  the run's final step (the solver clamps it to land exactly on ``stop_time``, so a short final
  step is expected and is not evidence of instability) and is never derived from the *median*
  interior dt, which is provably blind to CFL limiting on this project's real corpus.
- ``arena_max_mib``: parsed from the AMReX end-of-run "The Arena" line in ``run.log``.
- ``node``, ``gpu_model``: from the pod file's ``orchestration.node`` and ``hardware.gpus[0]``.
- ``timing.final_time``: the committed force CSV's actual **last row** (never the deck's
  ``stop_time`` — the exact bug this change fixes). ``timing.timesteps`` is the CSV's
  **distinct**-``iStep`` count (``ns.init_iter > 0`` writes extra rows at ``iStep = 0``, so the
  raw row count and the timestep count legitimately differ); the raw row count is used
  internally for the pod-side cross-check below, not exposed as ``timesteps``.
- ``timing.wall_time_s``: computed from a completed Argo workflow's persisted status timestamps
  (:func:`query_argo_workflow_status`), reflecting only the final successful attempt — or a
  caller-supplied ``--wall-time-s`` override if the source workflow has already been
  garbage-collected. In a multi-config fan-out workflow (several configs sharing one Argo
  workflow), the node is selected by the pod's own name (``orchestration.pod``, already recorded
  in the pod file) rather than an unfiltered global maximum across every node in the workflow —
  raising ``ValueError`` if that pod name has no matching node, or the matching node isn't
  itself a valid candidate, rather than silently falling back to the global maximum.
- ``orchestration``: passed through from the pod file (``workflow_uid``/``pod``/``node``/
  ``retry``), plus ``workflow_name`` if supplied.
- ``notes``: optional free-text field for genuinely exceptional commentary; omitted entirely
  (not an empty string) when not supplied.

Trust-one-artifact guards (all required, none silently skipped): the pod's reported ``status``
must be ``"completed"`` (a failed/incomplete run is refused, not silently assembled as if it
succeeded); the pod's ``deck_sha256`` must match a freshly computed hash of the ``--deck`` file
actually supplied (an operator pointing ``--deck`` at a stale/wrong file is caught, not silently
trusted); and the pod-reported row count (``rows``) must be present and must match the
CSV-derived **raw** row count (a missing or disagreeing count raises, never silently skipped or
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
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate.runner import STATUS_COMPLETED
from mosquito_cfd.force_surrogate.sidecar import (
    load_json_clear_error,
    validate_image_digest,
)

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SOURCE_CLI_OVERRIDE = (
    "cli-override"  # mirrors benchmarks.metadata._SOURCE_DOCKER_BUILD_ARG
)
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


def read_final_time_from_csv(csv_path: Path | str) -> tuple[float, int, int]:
    """Read a force CSV's actual last row for ``(final_time, timesteps, raw_row_count)``.

    Never uses the deck's ``stop_time`` — IB-particle CSVs systematically end exactly one ``dt``
    short of it (a pre-existing writer convention, not a divergence signal).

    ``ns.init_iter = N`` causes the solver to write ``1 + N`` rows at ``iStep = 0``, so the raw
    row count and the distinct-timestep count legitimately differ for a field-capture run.
    ``timesteps`` is the distinct-``iStep`` count (what the extractor's dataset row count means
    after deduplication); ``raw_row_count`` is the CSV's total data-row count, which is what the
    pod-side row-count cross-check compares against (see ``assemble_run_metadata``).

    Args:
        csv_path: Path to the committed force CSV (``forces_<config>.csv`` /
            ``IB_Particle_1.csv``).

    Returns:
        A ``(final_time, timesteps, raw_row_count)`` tuple.

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
    raw_row_count = len(rows)
    timesteps = len({row["iStep"] for row in rows})
    return float(rows[-1]["time"]), timesteps, raw_row_count


# ---------------------------------------------------------------------------
# run.log per-step dt series
# ---------------------------------------------------------------------------

# The nan/inf alternative MUST come first: the numeric alternative `[\d.eE+-]+` also matches a
# lone sign character on its own, so on a signed token like `-nan`/`-inf` a numeric-first
# ordering "succeeds" after consuming only the sign -- `float('-')` then raises a confusing,
# unlabeled ValueError instead of the diverged-run signal ever reaching
# `compute_dt_observations`'s NaN guard (review round 2 on PR #97; glibc printf emits a signed
# NaN payload as `-nan` for a real divergence). Trying nan/inf first lets it claim the whole
# signed token before the numeric alternative gets a chance to grab just the sign.
_STEP_DT_RE = re.compile(
    r"^STEP\s*=\s*\d+\s+TIME\s*=\s*[\d.eE+-]+\s+DT\s*=\s*([+-]?(?:nan|inf(?:inity)?)|[\d.eE+-]+)",
    re.MULTILINE | re.IGNORECASE,
)


def read_dt_series_from_run_log(run_log_path: Path | str) -> list[float]:
    """Parse the per-step ``DT = <value>`` series from ``run.log``, in step order.

    Read at full precision (unlike the force CSV's ``time`` column, which is written at six
    significant figures and can quantize a differenced timestep above the ``ns.fixed_dt``
    ceiling the solver cannot have taken).

    A ``DT = nan``/``DT = inf`` line (a diverged or crashed step) is captured as a real
    non-finite float, not silently dropped -- excluding the line would shift which step is
    treated as the trailing "final clamped step" that :func:`compute_dt_observations` excludes
    by design, and could let a diverged run's own evidence disappear before that function's NaN
    guard ever sees it (review round 1 on PR #97, the "falsely labeled stable" failure class
    reintroduced at the log-parsing layer).

    Args:
        run_log_path: Path to the run's captured ``run.log``.

    Returns:
        The observed ``dt`` values in step order (one entry per ``STEP =`` line matched; a
        ``nan``/``inf`` token parses to the corresponding non-finite ``float``).

    Raises:
        FileNotFoundError: If ``run_log_path`` does not exist.
    """
    path = Path(run_log_path)
    if not path.exists():
        raise FileNotFoundError(f"run.log not found: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    return [float(m) for m in _STEP_DT_RE.findall(text)]


def compute_dt_observations(
    dt_series: Sequence[float], *, fixed_dt: float, epsilon: float = 1e-9
) -> dict[str, Any]:
    """Summarize a run's observed per-step ``dt``, excluding the final (possibly clamped) step.

    The solver clamps its last step to land exactly on ``stop_time``
    (``NavierStokesBase.cpp:1168-1169``), so a short final step is expected on a healthy run and
    is excluded from the comparison rather than being mistaken for CFL limiting.

    The summary deliberately does NOT include a median: it is provably blind to CFL limiting on
    this project's real corpus — even the worst-truncated config kept 59% of its interior steps
    at the nominal ceiling, so its median interior ``dt`` equals nominal despite 40.7% of steps
    being CFL-reduced. ``min`` and ``frac_below_nominal`` are the discriminating statistics.

    Args:
        dt_series: The observed per-step ``dt`` values, in step order (see
            :func:`read_dt_series_from_run_log`).
        fixed_dt: The config's declared ``ns.fixed_dt`` (the comparison threshold — a deck-level
            fallback value, not always the sweep's nominal ``5e-4``).
        epsilon: Tolerance below which a step is not considered reduced (guards against
            floating-point noise, not CFL limiting).

    Returns:
        A dict with ``realized_dt`` (nested ``min``/``mean``/``max``/``frac_below_nominal`` over
        interior steps) and ``interior_dt_below_nominal`` (bool): whether any interior step fell
        below ``fixed_dt``.

    Raises:
        ValueError: If ``dt_series`` has fewer than 2 samples (there is no step left to exclude
            as the clamped final one), or contains a NaN/non-finite value.
    """
    if len(dt_series) < 2:
        raise ValueError(
            f"dt series has {len(dt_series)} sample(s); need at least 2 to exclude the final "
            "clamped step from the comparison"
        )
    interior = np.asarray(dt_series[:-1], dtype=float)
    if not np.all(np.isfinite(interior)):
        raise ValueError(
            "dt series contains a NaN or non-finite value; refusing to compute observations "
            "from a corrupted series"
        )
    below = interior < (fixed_dt - epsilon)
    return {
        "realized_dt": {
            "min": float(interior.min()),
            "mean": float(interior.mean()),
            "max": float(interior.max()),
            "frac_below_nominal": float(below.mean()),
        },
        "interior_dt_below_nominal": bool(below.any()),
    }


def compute_run_completion(
    *, final_time: float, stop_time: float, fixed_dt: float, frequency_fstar: float
) -> dict[str, Any]:
    """Derive ``cycles_completed`` and ``reached_stop_time`` from a run's observed ``final_time``.

    ``reached_stop_time`` tolerates the writer's one-``dt``-short convention (plus the final
    clamped step) rather than requiring exact equality with the deck's ``stop_time``. The
    ``2.0 * fixed_dt`` tolerance is a deliberately loose sanity bound, not a calibrated
    threshold: unlike ``interior_dt_below_nominal`` (the hard, exact gate) and
    ``SYMMETRY_RATIO_TOLERANCE`` (measured against real corpus data, see ``corpus_guards.py``),
    ``reached_stop_time`` is never used to gate the acceptance check -- it is recorded purely as
    a diagnostic (design.md D6), so it does not need, and does not have, an empirically-derived
    value.

    Args:
        final_time: The force CSV's actual last-row ``time`` (see
            :func:`read_final_time_from_csv`).
        stop_time: The config's deck-declared ``stop_time``.
        fixed_dt: The config's declared ``ns.fixed_dt``, used as the tolerance unit.
        frequency_fstar: The config's ``frequency_fstar``.

    Returns:
        A dict with ``cycles_completed`` (``final_time * frequency_fstar``) and
        ``reached_stop_time`` (bool).
    """
    return {
        "cycles_completed": final_time * frequency_fstar,
        "reached_stop_time": (stop_time - final_time) <= 2.0 * fixed_dt,
    }


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
    fixed_dt: float,
    *,
    nominal_fixed_dt: float = NOMINAL_FIXED_DT,
    interior_dt_below_nominal: bool = False,
) -> str:
    """Derive a run's stability verdict from its ``fixed_dt`` and observed timestep behaviour.

    No separate hand-set flag is read for the deck-fallback distinction — that verdict is
    entirely a function of the ``fixed_dt`` this tool already sources mechanically from the
    deck. ``interior_dt_below_nominal`` (see :func:`compute_dt_observations`) is a mechanically
    *observed* signal, not a hand-set one, and is required precisely because ``fixed_dt`` alone
    cannot report a CFL-limited run: ``ns.cfl`` can reduce the realized timestep below the deck's
    declared ``fixed_dt``, independent of the deck's own fallback status.

    Args:
        fixed_dt: The config's actual ``ns.fixed_dt`` (sourced from the deck).
        nominal_fixed_dt: The sweep's standard timestep (default ``5e-4``).
        interior_dt_below_nominal: Whether any interior step fell below ``fixed_dt`` (see
            :func:`compute_dt_observations`).

    Returns:
        ``"stable_at_<nominal>"`` / ``"stable_at_<fixed_dt>_fallback"`` for a run that held its
        declared timestep, or the ``"cfl_limited_at_..."`` counterpart otherwise. The
        ``cfl_limited_*`` values deliberately never share the ``"stable_at_"`` prefix, so a
        naive prefix-matching consumer fails closed rather than silently accepting a CFL-limited
        run as stable.
    """
    if fixed_dt == nominal_fixed_dt:
        suffix = _format_dt(nominal_fixed_dt)
        return (
            f"cfl_limited_at_{suffix}"
            if interior_dt_below_nominal
            else f"stable_at_{suffix}"
        )
    suffix = f"{_format_dt(fixed_dt)}_fallback"
    return (
        f"cfl_limited_at_{suffix}"
        if interior_dt_below_nominal
        else f"stable_at_{suffix}"
    )


# ---------------------------------------------------------------------------
# Manifest / deck sourcing
# ---------------------------------------------------------------------------


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
    manifest = load_json_clear_error(manifest_path, label="sweep manifest")
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
        "cfl": float(_deck_field("ns.cfl")),
        "stop_time": float(_deck_field("stop_time")),
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
    return load_json_clear_error(path, label="pod-side run_metadata.json")


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


def resolve_git_info(
    pod_metadata: dict[str, Any],
    *,
    git_commit_override: str | None = None,
) -> dict[str, Any]:
    """Resolve the run's git provenance, preferring a manual override over the pod's own value.

    Mirrors :func:`resolve_wall_time_s`: when an override is supplied it is used verbatim (after
    validation) and the pod's git block is never even consulted; only when no override is given
    does this fall through to :func:`extract_git_info`'s existing pod-sourced validation.

    Args:
        pod_metadata: The loaded pod-side ``run_metadata.json``.
        git_commit_override: A manually-supplied commit SHA (``--git-commit``), used verbatim
            (after format validation) when present -- the pod's ``git.commit`` is never
            consulted. Needed for pod images with no ``.git`` directory at all (issue #66) that
            also predate the baked ``MOSQUITO_CFD_COMMIT`` build-arg fallback in
            :func:`mosquito_cfd.benchmarks.metadata.get_git_info`.

    Returns:
        A git-info dict. When overridden: ``{"commit": ..., "source": "cli-override"}`` only --
        branch/dirty/repository are not knowable for a commit supplied out-of-band. Otherwise:
        the pod's own ``git`` sub-dict, as returned by :func:`extract_git_info`.

    Raises:
        ValueError: If ``git_commit_override`` is supplied but is not a full 40-character SHA, or
            (when no override is supplied) if the pod's ``git.commit`` is missing/invalid -- see
            :func:`extract_git_info`.
    """
    if git_commit_override is not None:
        if not _FULL_SHA_RE.match(git_commit_override):
            raise ValueError(
                f"--git-commit override must be a full 40-character SHA; got "
                f"{git_commit_override!r} (length {len(git_commit_override)})"
            )
        return {"commit": git_commit_override, "source": _SOURCE_CLI_OVERRIDE}
    return extract_git_info(pod_metadata)


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


def _is_succeeded_non_retry(node: dict[str, Any]) -> bool:
    """Whether an Argo status node is a Succeeded, non-Retry wall-time candidate.

    The single source of truth for this predicate -- used by the global-max fallback, the
    matched-node validation, and the unmatched-pod-name error's candidate-key listing, so the
    three branches can't silently drift out of sync with each other.
    """
    return node.get("phase") == "Succeeded" and node.get("type") != "Retry"


def compute_wall_time_s(
    status: dict[str, Any], *, pod_name: str | None = None
) -> float:
    """Compute wall-clock duration from a completed Argo workflow's node timestamps.

    Reflects only the final **successful** attempt's duration — a failed attempt followed by a
    successful retry contributes nothing to the result. Excludes Argo's own ``"Retry"``-type
    wrapper node: when a step has a ``retryStrategy`` (as
    ``cluster/argo/workflow-templates/force-surrogate-single-config.yaml`` does), Argo emits a
    wrapper node whose ``phase`` also becomes ``"Succeeded"`` but whose ``startedAt`` is the
    *first* (failed) attempt's start — including it would silently inflate the result by the
    failed attempt's duration. Timestamps are parsed to ``datetime`` (not compared as raw
    strings) so mixed sub-second-precision formatting can't misorder attempts.

    When ``pod_name`` is supplied, the node belonging to that specific pod is selected directly
    (Argo status node dict keys are the pod's own full name) instead of the unfiltered global
    maximum across every node in the workflow -- required for a multi-config fan-out workflow,
    where several configs' pods share one workflow and an unfiltered maximum would return
    whichever pod finished last for every config. When ``pod_name`` is omitted, behavior is
    unchanged: the global maximum across every Succeeded, non-Retry candidate node.

    Args:
        status: The parsed Argo workflow status (as returned by
            :func:`query_argo_workflow_status`).
        pod_name: The specific pod's own name to select, disambiguating a multi-config fan-out
            workflow. When ``None``, the unfiltered global maximum is used (correct for a
            single-config workflow, where there is only one real candidate). An empty string is
            treated as a literal (and virtually certain to be unmatched) pod name, not as
            "omitted" -- only ``None`` falls back to the unfiltered maximum, matching this
            function's no-silent-fallback design (a real pod name is never empty in practice).

    Returns:
        The successful attempt's duration in seconds.

    Raises:
        ValueError: If ``pod_name`` is supplied but no node has that key, or the matched node is
            not itself a valid candidate (not ``"Succeeded"``, is a ``"Retry"`` node, or is
            missing a timestamp). If ``pod_name`` is omitted, raised when no non-Retry node has
            phase ``"Succeeded"`` with both ``startedAt`` and ``finishedAt`` timestamps.
    """
    nodes = status.get("status", {}).get("nodes", {})
    if pod_name is not None:
        node = nodes.get(pod_name)
        if node is None:
            candidate_keys = sorted(
                key
                for key, candidate in nodes.items()
                if _is_succeeded_non_retry(candidate)
                and candidate.get("startedAt")
                and candidate.get("finishedAt")
            )
            raise ValueError(
                f"No node named {pod_name!r} in Argo workflow status; available candidate "
                f"keys (Succeeded, non-Retry, fully-timestamped): {candidate_keys}"
            )
        started_raw, finished_raw = node.get("startedAt"), node.get("finishedAt")
        if not _is_succeeded_non_retry(node):
            # The pass/fail decision itself is gated on the shared predicate (so a future
            # change to it can't silently diverge here); only the differentiated message text
            # below is computed by re-inspecting which specific check failed.
            if node.get("phase") != "Succeeded":
                reason = f"phase is {node.get('phase')!r}, not 'Succeeded'"
            else:
                reason = "node is a 'Retry' wrapper, not the underlying Pod attempt"
        elif not started_raw or not finished_raw:
            reason = "missing startedAt and/or finishedAt"
        else:
            reason = None
        if reason is not None:
            raise ValueError(
                f"Node {pod_name!r} is not a valid candidate for wall_time_s: {reason}"
            )
        started = _parse_argo_timestamp(started_raw)
        finished = _parse_argo_timestamp(finished_raw)
        return (finished - started).total_seconds()

    candidates = []
    for node in nodes.values():
        if not _is_succeeded_non_retry(node):
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
    pod_name: str | None = None,
    argo_status_query: Callable[[str], dict[str, Any]] = query_argo_workflow_status,
) -> float:
    """Resolve ``wall_time_s``, preferring a manual override over an Argo query.

    Args:
        workflow_name: The Argo workflow's name; required unless an override is supplied.
        wall_time_s_override: A manually-supplied wall time (``--wall-time-s``), used verbatim
            when present — the Argo query is never attempted, and ``pod_name`` is ignored.
        pod_name: The specific pod's own name, passed through to :func:`compute_wall_time_s` to
            disambiguate a multi-config fan-out workflow. Ignored when ``wall_time_s_override``
            is supplied.
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
    return compute_wall_time_s(argo_status_query(workflow_name), pod_name=pod_name)


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
    git_commit: str | None = None,
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
        git_commit: Manual override for ``git.commit`` (``--git-commit``), bypassing the pod's
            own ``git`` block entirely -- for pod images with no ``.git`` directory at all
            (issue #66) that predate the baked ``MOSQUITO_CFD_COMMIT`` build-arg fallback.

    Returns:
        The assembled, normalized metadata dict.

    Raises:
        FileNotFoundError: If any input file is missing.
        ValueError: If any input is malformed, the docker digest or git commit fails validation,
            the pod-reported status is not ``"completed"``, the ``--deck`` file's hash doesn't
            match the pod-recorded ``deck_sha256``, the pod-reported row count is missing or
            disagrees with the CSV-derived timestep count, or (in a multi-config fan-out
            workflow) the pod's own ``orchestration.pod`` name has no matching node in the Argo
            workflow status, or the matching node is not itself a valid ``wall_time_s``
            candidate -- see :func:`compute_wall_time_s`.
        KeyError: If ``config_name`` is not present in the manifest, or the manifest entry/deck
            is missing a required field.
    """
    pod_metadata = load_pod_run_metadata(pod_metadata_path)
    docker_image = extract_docker_image(pod_metadata)
    git_info = resolve_git_info(pod_metadata, git_commit_override=git_commit)

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

    final_time, timesteps, raw_row_count = read_final_time_from_csv(csv_path)
    if "rows" not in pod_metadata:
        raise ValueError(
            f"pod-side run_metadata.json for config {config_name!r} has no 'rows' field; "
            "cannot cross-validate against the CSV-derived row count"
        )
    pod_rows = pod_metadata["rows"]
    # Compared against the RAW row count, not the deduplicated `timesteps`: the pod records the
    # raw count, and the two legitimately differ by `init_iter` when initialization rows are
    # present (see read_final_time_from_csv).
    if int(pod_rows) != raw_row_count:
        raise ValueError(
            f"pod-reported row count ({pod_rows}) disagrees with the CSV-derived row count "
            f"({raw_row_count}) for config {config_name!r}"
        )

    arena_max_mib = parse_arena_max_mib(run_log_path)
    config_fields = source_config_fields(
        manifest_path=manifest_path, deck_path=deck_path, config_name=config_name
    )
    dt_series = read_dt_series_from_run_log(run_log_path)
    dt_obs = compute_dt_observations(dt_series, fixed_dt=config_fields["fixed_dt"])
    stability = derive_stability(
        config_fields["fixed_dt"],
        interior_dt_below_nominal=dt_obs["interior_dt_below_nominal"],
    )
    completion = compute_run_completion(
        final_time=final_time,
        stop_time=config_fields["stop_time"],
        fixed_dt=config_fields["fixed_dt"],
        frequency_fstar=config_fields["kinematics"]["frequency_fstar"],
    )

    orchestration = dict(pod_metadata.get("orchestration", {}))
    if workflow_name is not None:
        orchestration["workflow_name"] = workflow_name

    resolved_wall_time_s = resolve_wall_time_s(
        workflow_name=workflow_name,
        wall_time_s_override=wall_time_s,
        pod_name=orchestration.get("pod"),
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
        "cfl": config_fields["cfl"],
        "max_step": config_fields["max_step"],
        "stability": stability,
        "realized_dt": dt_obs["realized_dt"],
        "interior_dt_below_nominal": dt_obs["interior_dt_below_nominal"],
        "cycles_completed": completion["cycles_completed"],
        "reached_stop_time": completion["reached_stop_time"],
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
