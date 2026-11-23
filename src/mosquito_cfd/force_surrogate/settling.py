"""Beat-to-beat settling of a flapping-wing run, and the pre-registered beat-count rule.

OpenSpec change ``add-settled-beat-corpus`` (issue #192). The force-surrogate corpora were 2-beat
runs; this module measures how far each wingbeat of a longer run still is from the periodic state,
so the corpus can be regenerated with a beat count whose final beat is settled.

The definitions are pre-registered in ``examples/settling_check/PREREGISTRATION.md`` (the single
narrative home of the rule; the constants below are pinned to its constants block by a test).
In brief, for one run and each of the six coefficients:

- beat ``b`` (1-based) is the rows with ``wingbeat == b - 1``; rows whose step would end past
  ``stop_time`` (the solver's clamped final step) are dropped first;
- ``s_b`` is the RMS, over beat ``b``'s own samples, of beat ``b`` minus beat ``b - 1``
  interpolated (periodic, linear in ``phase``) at those samples, divided by the last beat's peak;
- the tail bound ``T`` extrapolates how far the last beat still is from the periodic state from
  the last three step ratios, widened when the ratios rise, with a noise floor ``nu = 3 J`` set by
  the half-spacing interpolation error ``J`` of the last beat;
- ``E_b = D_b + T`` (``D_b`` is the distance from beat ``b`` to the last beat).

A beat count ``N`` passes when, for every coefficient, the run cut at ``N`` beats has ``T <= 1%``
and the full run has ``E_N <= 1%``. See :func:`evaluate_run` and :func:`decide_beat_count`.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.constants import DT
from mosquito_cfd.force_surrogate.dataset import deduplicate_init_iter_rows
from mosquito_cfd.force_surrogate.metadata_capture import (
    compute_dt_observations,
    read_dt_series_from_run_log,
)

TARGETS: tuple[str, ...] = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")

# Pre-registered constants (pinned to PREREGISTRATION.md's constants block by a test).
SETTLED_TOLERANCE = 0.01
COMPLETE_FRACTION = 0.95
MIN_BEATS = 5
FIRST_RATIO_BEAT = 4
NOISE_FACTOR = 3
MAX_NOISE = 0.0006

# Bound used when every ratio is noise: rho / (1 - rho) at rho = 0.96.
AT_FLOOR_FACTOR = 24.0
# Slack on the clamped-step test (time + dt > stop_time + slack), for float equality at f100.
CLAMP_SLACK = 1e-9
# Beat count above which regeneration needs the user's approval of the cost.
COST_APPROVAL_ABOVE = 6
# Force comparison (controls C1, C3): a value passes within
# max(COMPARE_RELATIVE_TO_COLUMN * max|column|, COMPARE_PRINT_UNITS * print unit).
COMPARE_RELATIVE_TO_COLUMN = 1e-9
COMPARE_PRINT_UNITS = 1.5
# Near-wing field change: the fraction of the box whose change exceeds this, in u_ref.
FIELD_CHANGE_THRESHOLD = 0.1

_REQUIRED = ("time", "phase", "wingbeat", *TARGETS)


@dataclass(frozen=True)
class TailBound:
    """How far the last beat still is from the periodic state, from the last step ratios."""

    tail: float
    rho: float | None
    contracting: bool
    ratio_beats: list[int]
    ratios: list[float]
    skipped: list[int]


@dataclass(frozen=True)
class TargetSettling:
    """Settling of one coefficient of one run (all distances are fractions of ``peak``)."""

    peak: float
    steps: dict[int, float]
    steps_max_abs: dict[int, float]
    distances: dict[int, float]
    distances_max_abs: dict[int, float]
    jitter: float
    noise_floor: float
    tail: float
    rho: float | None
    contracting: bool
    ratios: list[float]
    skipped: list[int]
    estimate: dict[int, float]


@dataclass(frozen=True)
class RunSettling:
    """Settling of one run: the last complete beat ``b_last`` and one entry per target."""

    config_name: str
    b_last: int
    incomplete_beats: list[int]
    targets: dict[str, TargetSettling]
    mean_cf_z: dict[int, float]


@dataclass(frozen=True)
class RunVerdict:
    """The decision rule applied to one run (see :func:`evaluate_run`)."""

    run: str
    n_star: int | None
    contracting: bool
    max_noise: float
    noise_target: str
    passes: dict[int, bool] = field(default_factory=dict)
    binding_beat: int | None = None
    binding_target: str | None = None
    settling: RunSettling | None = None


@dataclass(frozen=True)
class Decision:
    """Outcome of :func:`decide_beat_count`."""

    action: str
    n_star: int | None
    run: str
    beat: int | None
    target: str | None
    reason: str


def drop_clamped_rows(
    frame: pd.DataFrame, *, stop_time: float, dt: float
) -> pd.DataFrame:
    """Drop rows whose step would end past ``stop_time`` (the solver's clamped final step).

    ``max_step = round(stop_time / dt)`` overshoots ``stop_time`` when ``stop_time / dt`` is not
    an integer (``f* = 0.85``), so the solver shortens the final step to land on ``stop_time``
    (``NavierStokesBase.cpp:1168-1169``). That row's forces belong to a short step and show a
    spike; it is not part of the periodic signal.
    """
    keep = frame["time"].to_numpy(dtype=float) + dt <= stop_time + CLAMP_SLACK
    return frame.loc[keep]


def jitter(values: np.ndarray, *, peak: float) -> float:
    """Half-spacing linear-interpolation error bound of a sampled beat, over ``peak``.

    ``rms(v[i-1] - 2 v[i] + v[i+1]) / 8``: for a locally quadratic signal, ``Δ²/8`` is the
    largest error of linear interpolation at half a sample spacing. Interior samples only (no
    wrap: the beat is not yet periodic).
    """
    v = np.asarray(values, dtype=float)
    second = v[:-2] - 2.0 * v[1:-1] + v[2:]
    return float(np.sqrt(np.mean(second**2)) / (8.0 * peak))


def tail_bound(steps: Mapping[int, float], *, b_last: int, nu: float) -> TailBound:
    """Bound the distance from beat ``b_last`` to the periodic state.

    Ratios ``r_b = s_b / s_{b-1}`` are taken for ``b = max(FIRST_RATIO_BEAT, b_last - 2) ..
    b_last``. A ratio is skipped when ``s_{b-1} <= nu`` and ``s_b <= 2 nu`` (noise); when
    ``s_{b-1} <= nu`` but ``s_b > 2 nu`` the run is growing (not contracting).
    ``rho = max r + max(0, r_last - r_first)``; ``rho >= 1`` is not contracting. The tail is
    ``s_B rho / (1 - rho)``, infinite when not contracting, and ``24 max s`` over the ratio beats
    when every ratio was skipped.

    Args:
        steps: Step changes ``s_b`` keyed by beat; must hold ``b - 1`` and ``b`` for every ratio
            beat.
        b_last: The last complete beat ``B``.
        nu: The noise floor.

    Returns:
        A :class:`TailBound`.
    """
    beats = list(range(max(FIRST_RATIO_BEAT, b_last - 2), b_last + 1))
    ratios: list[float] = []
    skipped: list[int] = []
    for b in beats:
        prev, cur = steps[b - 1], steps[b]
        if prev <= nu:
            if cur <= 2.0 * nu:
                skipped.append(b)
                continue
            return TailBound(math.inf, None, False, beats, ratios, skipped)
        ratios.append(cur / prev)
    if not ratios:
        tail = AT_FLOOR_FACTOR * max(steps[b] for b in beats)
        return TailBound(tail, None, True, beats, ratios, skipped)
    rho = max(ratios) + max(0.0, ratios[-1] - ratios[0])
    if rho >= 1.0:
        return TailBound(math.inf, rho, False, beats, ratios, skipped)
    return TailBound(
        steps[b_last] * rho / (1.0 - rho), rho, True, beats, ratios, skipped
    )


def _check_columns(frame: pd.DataFrame, config_name: str) -> None:
    missing = [c for c in _REQUIRED if c not in frame.columns]
    if missing:
        raise ValueError(
            f"settling: config {config_name!r} is missing column(s) {missing}"
        )
    for column in ("time", "phase", *TARGETS):
        values = frame[column].to_numpy(dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError(
                f"settling: config {config_name!r} column {column!r} has a non-finite value"
            )
    labels = frame["wingbeat"].to_numpy(dtype=float)
    if not (np.all(np.isfinite(labels)) and np.all(labels == np.round(labels))):
        raise ValueError(
            f"settling: config {config_name!r} column 'wingbeat' has a non-integer value"
        )


def _split_beats(
    frame: pd.DataFrame, config_name: str, frequency_fstar: float, dt: float
) -> tuple[list[pd.DataFrame], list[int]]:
    """Return the complete beats (1-based order) and the numbers of trailing incomplete beats."""
    expected = 1.0 / (frequency_fstar * dt)
    need = COMPLETE_FRACTION * expected
    ordered = frame.sort_values("time", kind="stable")
    labels = ordered["wingbeat"].to_numpy().astype(np.int64)
    if len(labels) and labels.min() < 0:
        raise ValueError(f"settling: config {config_name!r} has a negative wingbeat")
    n_beats = int(labels.max()) + 1 if len(labels) else 0
    beats: list[pd.DataFrame] = []
    complete: list[bool] = []
    for index in range(n_beats):
        beat = ordered[labels == index]
        phase = beat["phase"].to_numpy(dtype=float)
        if len(phase) > 1 and not np.all(np.diff(phase) > 0):
            raise ValueError(
                f"settling: config {config_name!r} beat {index + 1} has a duplicate or "
                "non-increasing phase"
            )
        beats.append(beat)
        complete.append(len(beat) >= need)
    if complete and not complete[0]:
        raise ValueError(
            f"settling: config {config_name!r} beat 1 is incomplete "
            f"({len(beats[0])} of {expected:.1f} rows)"
        )
    if not complete:
        b_last = 0
    else:
        b_last = max(i + 1 for i, ok in enumerate(complete) if ok)
    for index in range(b_last):
        if not complete[index]:
            raise ValueError(
                f"settling: config {config_name!r} beat {index + 1} is incomplete "
                f"({len(beats[index])} of {expected:.1f} rows) before the last complete "
                f"beat {b_last}"
            )
    incomplete = [i + 1 for i in range(b_last, n_beats)]
    return beats[:b_last], incomplete


def _dist(
    a: pd.DataFrame, c: pd.DataFrame, target: str, peak: float
) -> tuple[float, float]:
    """RMS and max-abs of beat ``a`` minus beat ``c`` interpolated at ``a``'s phases, over peak."""
    phase_c = c["phase"].to_numpy(dtype=float)
    interp = np.interp(
        a["phase"].to_numpy(dtype=float),
        phase_c,
        c[target].to_numpy(dtype=float),
        period=1.0,
    )
    diff = a[target].to_numpy(dtype=float) - interp
    return float(np.sqrt(np.mean(diff**2)) / peak), float(np.max(np.abs(diff)) / peak)


def settling_metrics(
    frame: pd.DataFrame,
    *,
    config_name: str,
    frequency_fstar: float,
    dt: float,
    stop_time: float,
) -> RunSettling:
    """Measure beat-to-beat settling of one run.

    Args:
        frame: One run's rows with ``time``, ``phase``, ``wingbeat`` and the six ``CF_*``
            columns (the extractor's columns, used as given).
        config_name: Configuration name, for error messages.
        frequency_fstar: The run's dimensionless frequency.
        dt: The manifest's timestep ``dt``.
        stop_time: The run's deck ``stop_time``.

    Returns:
        A :class:`RunSettling`.

    Raises:
        ValueError: On a missing column, a non-finite value, a duplicate or non-increasing phase
            within a beat, an incomplete beat before the last complete one, fewer than
            :data:`MIN_BEATS` complete beats, or a zero peak.
    """
    _check_columns(frame, config_name)
    kept = drop_clamped_rows(frame, stop_time=stop_time, dt=dt)
    beats, incomplete = _split_beats(kept, config_name, frequency_fstar, dt)
    b_last = len(beats)
    if b_last < MIN_BEATS:
        raise ValueError(
            f"settling: config {config_name!r} has {b_last} complete beat(s); "
            f"need at least {MIN_BEATS}"
        )
    last = beats[-1]
    results: dict[str, TargetSettling] = {}
    for target in TARGETS:
        peak = float(np.max(np.abs(last[target].to_numpy(dtype=float))))
        if peak == 0.0:
            raise ValueError(
                f"settling: config {config_name!r} {target} has a zero peak"
            )
        steps: dict[int, float] = {}
        steps_max: dict[int, float] = {}
        for b in range(2, b_last + 1):
            steps[b], steps_max[b] = _dist(beats[b - 1], beats[b - 2], target, peak)
        distances: dict[int, float] = {}
        distances_max: dict[int, float] = {}
        for b in range(1, b_last + 1):
            distances[b], distances_max[b] = _dist(beats[b - 1], last, target, peak)
        j = jitter(last[target].to_numpy(dtype=float), peak=peak)
        nu = NOISE_FACTOR * j
        tb = tail_bound(steps, b_last=b_last, nu=nu)
        results[target] = TargetSettling(
            peak=peak,
            steps=steps,
            steps_max_abs=steps_max,
            distances=distances,
            distances_max_abs=distances_max,
            jitter=j,
            noise_floor=nu,
            tail=tb.tail,
            rho=tb.rho,
            contracting=tb.contracting,
            ratios=tb.ratios,
            skipped=tb.skipped,
            estimate={b: d + tb.tail for b, d in distances.items()},
        )
    mean_cf_z = {b: float(beats[b - 1]["CF_z"].mean()) for b in range(1, b_last + 1)}
    return RunSettling(config_name, b_last, incomplete, results, mean_cf_z)


def resample_beats(
    frame: pd.DataFrame, *, n_phase: int = 256
) -> dict[int, dict[str, np.ndarray]]:
    """Resample every beat onto ``k / n_phase`` by periodic linear interpolation in ``phase``.

    For figures and for reproducing the exploration study's published tables only; the settling
    metric itself compares beats at their own sample resolution (a coarse phase grid aliases the
    one-sample force features at stroke reversal).

    Returns:
        ``{beat (1-based): {target: values on the grid}}``.
    """
    grid = np.arange(n_phase) / n_phase
    out: dict[int, dict[str, np.ndarray]] = {}
    for index, beat in frame.groupby("wingbeat"):
        phase = beat["phase"].to_numpy(dtype=float)
        order = np.argsort(phase)
        out[int(index) + 1] = {
            t: np.interp(
                grid, phase[order], beat[t].to_numpy(dtype=float)[order], period=1.0
            )
            for t in TARGETS
        }
    return out


def n_star_from_passes(passes: Mapping[int, bool]) -> int | None:
    """Smallest ``N`` such that ``pass(N')`` holds for every evaluated ``N' >= N``."""
    n_star = None
    for n in sorted(passes, reverse=True):
        if not passes[n]:
            break
        n_star = n
    return n_star


def evaluate_run(
    run: str,
    frame: pd.DataFrame,
    *,
    frequency_fstar: float,
    dt: float,
    stop_time: float,
) -> RunVerdict:
    """Apply pass(N) for every ``MIN_BEATS <= N <= B`` to one run.

    pass(N) holds when, for every target, (a) the run cut at its first ``N`` beats is
    contracting with ``T <= SETTLED_TOLERANCE`` and (b) the full run is contracting with
    ``E_N <= SETTLED_TOLERANCE``.
    """
    name = str(frame["config_name"].iloc[0]) if "config_name" in frame.columns else run
    full = settling_metrics(
        frame,
        config_name=name,
        frequency_fstar=frequency_fstar,
        dt=dt,
        stop_time=stop_time,
    )
    passes: dict[int, bool] = {}
    worst: dict[int, tuple[float, str]] = {}
    for n in range(MIN_BEATS, full.b_last + 1):
        if n == full.b_last:
            trunc = full
        else:
            cut = frame[frame["wingbeat"] < n]
            trunc = settling_metrics(
                cut,
                config_name=name,
                frequency_fstar=frequency_fstar,
                dt=dt,
                stop_time=n / frequency_fstar,
            )
        ok = True
        worst_value, worst_target = -1.0, TARGETS[0]
        for target in TARGETS:
            t_trunc = trunc.targets[target]
            t_full = full.targets[target]
            value = max(t_trunc.tail, t_full.estimate[n])
            ok_target = (
                t_trunc.contracting
                and t_trunc.tail <= SETTLED_TOLERANCE
                and t_full.contracting
                and t_full.estimate[n] <= SETTLED_TOLERANCE
            )
            ok = ok and ok_target
            if value > worst_value:
                worst_value, worst_target = value, target
        passes[n] = ok
        worst[n] = (worst_value, worst_target)
    n_star = n_star_from_passes(passes)
    if n_star is None:
        binding_beat = full.b_last
    elif n_star > MIN_BEATS:
        binding_beat = n_star - 1
    else:
        binding_beat = n_star
    noise_target = max(TARGETS, key=lambda t: full.targets[t].noise_floor)
    return RunVerdict(
        run=run,
        n_star=n_star,
        contracting=all(full.targets[t].contracting for t in TARGETS),
        max_noise=full.targets[noise_target].noise_floor,
        noise_target=noise_target,
        passes=passes,
        binding_beat=binding_beat,
        binding_target=worst[binding_beat][1] if binding_beat in worst else None,
        settling=full,
    )


def decide_beat_count(verdicts: Sequence[RunVerdict]) -> Decision:
    """The pre-registered decision over all settling runs.

    Precedence: ``stop`` (a run with no ``N*``, not contracting, or noise floor above
    :data:`MAX_NOISE`), then ``regenerate_needs_cost_approval`` (``N* > 6``), then
    ``regenerate``. No margin is added to ``N*``.
    """
    if not verdicts:
        raise ValueError("decide_beat_count needs at least one run")
    for v in verdicts:
        if not v.max_noise <= MAX_NOISE:  # NaN stops too
            return Decision(
                "stop",
                None,
                v.run,
                None,
                v.noise_target,
                f"{v.run}: noise floor {v.max_noise:.3g} in {v.noise_target} exceeds "
                f"MAX_NOISE {MAX_NOISE}",
            )
        if not v.contracting:
            return Decision(
                "stop",
                None,
                v.run,
                v.binding_beat,
                v.binding_target,
                f"{v.run}: not contracting on its full length",
            )
        if v.n_star is None:
            return Decision(
                "stop",
                None,
                v.run,
                v.binding_beat,
                v.binding_target,
                f"{v.run}: no settled beat (worst at beat {v.binding_beat}, "
                f"{v.binding_target})",
            )
    slowest = max(verdicts, key=lambda v: v.n_star or 0)
    n_star = slowest.n_star
    action = (
        "regenerate_needs_cost_approval"
        if n_star > COST_APPROVAL_ABOVE
        else "regenerate"
    )
    return Decision(
        action,
        n_star,
        slowest.run,
        slowest.binding_beat,
        slowest.binding_target,
        f"N* = {n_star}, set by {slowest.run} (beat {slowest.binding_beat}, "
        f"{slowest.binding_target}, blocked the count below N*)",
    )


# --------------------------------------------------------------------------- pre-registration

PREREGISTERED_NAMES = (
    "SETTLED_TOLERANCE",
    "COMPLETE_FRACTION",
    "MIN_BEATS",
    "FIRST_RATIO_BEAT",
    "NOISE_FACTOR",
    "MAX_NOISE",
    "AT_FLOOR_FACTOR",
    "CLAMP_SLACK",
    "COST_APPROVAL_ABOVE",
    "COMPARE_RELATIVE_TO_COLUMN",
    "COMPARE_PRINT_UNITS",
    "FIELD_CHANGE_THRESHOLD",
)
_BLOCK_START = "<!-- settling-constants:start -->"
_BLOCK_END = "<!-- settling-constants:end -->"
_ASSIGNMENT = re.compile(r"^\s*([A-Z_]+)\s*=\s*([0-9.eE+-]+)\s*$")
_SPEC_ASSIGNMENT = re.compile(r"`([A-Z_]+) = ([0-9.eE+-]+)`")

SETTLING_PY = "src/mosquito_cfd/force_surrogate/settling.py"
# Files whose bytes every settling run record pins (repository-relative). An edit to any of
# them after the runs started needs a deviations.json entry. settling.py is gated because the
# verdict is recomputed with the current code: changing the analysis after seeing the data is
# a deviation, like changing the criterion.
GATED_FILES = (
    "examples/settling_check/PREREGISTRATION.md",
    "examples/settling_check/generate_decks.py",
    SETTLING_PY,
)
# Records written into the checkout during Stage 1; they do not make it dirty.
RECORDS_PREFIX = "examples/settling_check/records/"


def _preregistered_values() -> dict[str, float]:
    return {name: float(globals()[name]) for name in PREREGISTERED_NAMES}


def read_preregistered_constants(path: Path | str) -> dict[str, float]:
    """Parse the constants block of ``PREREGISTRATION.md``.

    The block sits between ``<!-- settling-constants:start -->`` and
    ``<!-- settling-constants:end -->`` and holds one ``NAME = value`` per line (a code fence
    around it is ignored).

    Raises:
        ValueError: If either anchor is missing or repeated, a line inside the block is not an
            assignment, or a name repeats.
    """
    text = Path(path).read_text(encoding="utf-8")
    if text.count(_BLOCK_START) != 1 or text.count(_BLOCK_END) != 1:
        raise ValueError(
            f"{path}: expected exactly one {_BLOCK_START} and one {_BLOCK_END} "
            "(settling-constants block)"
        )
    body = text.split(_BLOCK_START, 1)[1].split(_BLOCK_END, 1)[0]
    values: dict[str, float] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        match = _ASSIGNMENT.match(stripped)
        if match is None:
            raise ValueError(
                f"{path}: not a NAME = value line in the constants block: {line!r}"
            )
        name, value = match.group(1), float(match.group(2))
        if name in values:
            raise ValueError(f"{path}: {name} appears twice in the constants block")
        values[name] = value
    return values


def constants_mismatches(declared: Mapping[str, float]) -> list[str]:
    """Differences between pre-registered constants and this module's, one message each."""
    current_values = _preregistered_values()
    out = []
    for name in PREREGISTERED_NAMES:
        current = current_values[name]
        if name not in declared:
            out.append(f"{name}: missing from the preregistration")
        elif float(declared[name]) != current:
            out.append(
                f"{name}: preregistered {declared[name]:g}, settling.py {current:g}"
            )
    for name in sorted(set(declared) - set(PREREGISTERED_NAMES)):
        out.append(f"{name}: preregistered but not a settling constant")
    return out


def spec_constants(spec_path: Path | str) -> dict[str, float]:
    """The pre-registered constants as the spec states them (`` `NAME = value` `` pairs).

    Used by the pinning test. A name stated twice with different values raises, so a
    self-contradicting spec cannot pass the pin by its last mention.
    """
    text = Path(spec_path).read_text(encoding="utf-8")
    found: dict[str, float] = {}
    for name, value in _SPEC_ASSIGNMENT.findall(text):
        if name not in PREREGISTERED_NAMES:
            continue
        if name in found and found[name] != float(value):
            raise ValueError(
                f"{spec_path}: {name} is stated as both {found[name]:g} and {float(value):g}"
            )
        found[name] = float(value)
    return found


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_json(path: Path, failures: list[str], label: str) -> object | None:
    """Read JSON, appending a named failure (and returning None) instead of raising."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        failures.append(f"{label}: cannot be read as JSON ({exc})")
        return None


def _deviation_ok(deviations: Sequence[object], file: str, old: str, new: str) -> bool:
    for entry in deviations:
        if (
            isinstance(entry, dict)
            and entry.get("file") == file
            and entry.get("old_sha256") == old
            and entry.get("new_sha256") == new
            and str(entry.get("reason", "")).strip()
            and str(entry.get("pr", "")).strip()
        ):
            return True
    return False


def _manifest_names(manifest: Mapping) -> set[str]:
    return {
        e["name"] for e in [*manifest.get("runs", []), *manifest.get("controls", [])]
    }


def check_precedence(settling_dir: Path | str, *, repo_root: Path | str) -> list[str]:
    """Check that the committed criterion and analysis are the ones the runs started under.

    - Every run record in ``records/`` must carry the SHA-256 of each file in
      :data:`GATED_FILES`, and the committed file must still hash to it, unless a
      ``deviations.json`` entry (``file``, ``old_sha256``, ``new_sha256``, ``reason``, ``pr``)
      accounts for the difference.
    - Once ``DECISION.md`` or ``settling_report.json`` exists, the set of records must equal the
      set of runs and controls the settling manifest declares: none missing, none stray.

    Reads only committed files (no git history), so it works on a shallow CI checkout. Malformed
    JSON is reported as a failure naming the file, never raised.

    Returns:
        Failure messages; empty when the check passes.
    """
    settling_dir = Path(settling_dir)
    repo_root = Path(repo_root)
    failures: list[str] = []
    deviations: list = []
    deviations_path = settling_dir / "deviations.json"
    if deviations_path.exists():
        loaded = _load_json(deviations_path, failures, "deviations.json")
        if isinstance(loaded, list):
            deviations = loaded
        elif loaded is not None:
            failures.append("deviations.json: must be a JSON list of entries")
    records = sorted((settling_dir / "records").glob("*.json"))
    for record_path in records:
        record = _load_json(record_path, failures, record_path.name)
        if record is None:
            continue
        if not isinstance(record, dict) or not isinstance(
            record.get("file_sha256"), dict
        ):
            failures.append(f"{record_path.name}: not a record object with file_sha256")
            continue
        hashes = record["file_sha256"]
        for rel in GATED_FILES:
            recorded = hashes.get(rel)
            if recorded is None:
                failures.append(f"{record_path.name}: no recorded SHA-256 for {rel}")
                continue
            current = _sha256(repo_root / rel)
            if current != recorded and not _deviation_ok(
                deviations, rel, recorded, current
            ):
                failures.append(
                    f"{record_path.name}: {rel} changed since the run "
                    f"(recorded {recorded[:12]}, now {current[:12]}) with no deviations.json "
                    "entry"
                )
    decided = (settling_dir / "DECISION.md").exists() or (
        settling_dir / "settling_report.json"
    ).exists()
    if decided:
        manifest_path = settling_dir / "settling_manifest.json"
        manifest = _load_json(manifest_path, failures, "settling_manifest.json")
        if isinstance(manifest, dict):
            declared = _manifest_names(manifest)
            recorded_names = {p.stem for p in records}
            if not declared:
                failures.append(
                    "a decision or report exists; the manifest declares no runs"
                )
            for name in sorted(declared - recorded_names):
                failures.append(
                    f"a decision or report exists but {name} has no run record"
                )
            for name in sorted(recorded_names - declared):
                failures.append(
                    f"records/{name}.json is not a run or control in the manifest"
                )
    return failures


# --------------------------------------------------------------------------- decks


def deck_key_mismatches(
    source: Mapping[str, str],
    generated: Mapping[str, str],
    declared: set[str] | frozenset[str],
) -> list[str]:
    """Check that ``generated`` differs from ``source`` in exactly the ``declared`` keys.

    Args:
        source: The committed corpus deck, parsed (``metadata_capture.parse_deck``).
        generated: The settling-check deck, parsed.
        declared: Keys the settling manifest declares as changed or added.

    Returns:
        One message per problem: a declared key left unchanged, an undeclared key changed, or an
        undeclared key removed. Empty when the decks differ in exactly ``declared``.
    """
    out: list[str] = []
    for key in sorted(declared):
        if key in source and generated.get(key) == source[key]:
            out.append(f"declared key {key} is not changed or added")
        elif key not in generated:
            out.append(f"declared key {key} is not changed or added")
    for key in sorted(set(source) | set(generated)):
        if key in declared:
            continue
        if key not in generated:
            out.append(f"undeclared key {key} is missing from the generated deck")
        elif key not in source:
            out.append(f"undeclared key {key} is added: {generated[key]!r}")
        elif generated[key] != source[key]:
            out.append(
                f"undeclared key {key} differs: {source[key]!r} -> {generated[key]!r}"
            )
    return out


# --------------------------------------------------------------------------- controls

FORCE_COLUMNS = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")


@dataclass(frozen=True)
class ForceComparison:
    """Outcome of :func:`compare_force_csv`.

    ``n_rows`` is the run CSV's row count after the extractor's de-duplication (``None`` when
    the CSV could not be de-duplicated); ``n_compared`` the number of steps compared.
    """

    passed: bool
    n_compared: int
    failures: list[str]
    n_rows: int | None = None


def print_unit(value):
    """One unit in the 6th significant figure of ``value`` (0 for an exact zero).

    Accepts a scalar or an array; a non-finite value gives NaN, which no tolerance test passes.
    """
    a = np.abs(np.asarray(value, dtype=float))
    out = np.zeros_like(a)
    nonzero = a != 0.0
    # log10 of a NaN/inf is reported as NaN below; silence the warning, not the result.
    with np.errstate(invalid="ignore", divide="ignore"):
        out[nonzero] = 10.0 ** (np.floor(np.log10(a[nonzero])) - 5)
    return float(out) if out.ndim == 0 else out


def compare_force_csv(
    run_csv: Path | str,
    reference: pd.DataFrame,
    *,
    config_name: str,
    dt: float,
    run_stop_time: float,
    reference_stop_time: float,
    declared_steps: int | None,
) -> ForceComparison:
    """Compare a run's raw forces with the committed corpus rows (controls C1 and C3).

    The run's CSV goes through the extractor's de-duplication
    (:func:`.dataset.deduplicate_init_iter_rows`); rows whose step ends past each side's
    ``stop_time`` are dropped; steps ``0 .. n - 1`` must each appear exactly once in both the run
    and the reference, matched by step index ``round(time / dt)``. Every raw ``Fx..Mz`` value
    must then be finite on both sides and agree within
    ``max(COMPARE_RELATIVE_TO_COLUMN * max |column|, COMPARE_PRINT_UNITS * print unit of the
    reference value)``, the column maximum taken over the compared reference rows.

    Args:
        run_csv: The run's ``IB_Particle_1.csv``.
        reference: The configuration's rows of the committed ``dataset.parquet`` (``time`` and
            ``Fx..Mz``).
        config_name: For messages.
        dt: Timestep.
        run_stop_time: The run deck's ``stop_time``.
        reference_stop_time: The reference run's ``stop_time``.
        declared_steps: ``n``: the control deck's ``max_step`` (C1), or ``None`` for every
            reference step left after the reference's clamped final row is dropped (C3).

    Returns:
        A :class:`ForceComparison`; ``failures`` names the first problem of each kind. A
        malformed CSV is a failure, not an exception.
    """
    raw = pd.read_csv(run_csv)
    missing = [c for c in ("iStep", "time", *FORCE_COLUMNS) if c not in raw.columns]
    if missing:
        return ForceComparison(
            False, 0, [f"{config_name}: run CSV lacks column(s) {missing}"]
        )
    missing_ref = [c for c in ("time", *FORCE_COLUMNS) if c not in reference.columns]
    if missing_ref:
        return ForceComparison(
            False, 0, [f"{config_name}: reference lacks column(s) {missing_ref}"]
        )
    try:
        raw = deduplicate_init_iter_rows(raw, name=config_name, csv_path=run_csv)
    except ValueError as exc:
        return ForceComparison(False, 0, [f"duplicate or non-monotonic iStep: {exc}"])
    n_rows = int(len(raw))
    run = drop_clamped_rows(raw, stop_time=run_stop_time, dt=dt)
    ref = drop_clamped_rows(
        reference.sort_values("time", kind="stable"),
        stop_time=reference_stop_time,
        dt=dt,
    )
    if declared_steps is None:
        declared_steps = len(ref)
    failures: list[str] = []
    sides = {}
    for label, frame in (("run", run), ("reference", ref)):
        steps = np.rint(frame["time"].to_numpy(dtype=float) / dt).astype(np.int64)
        keep = steps < declared_steps
        steps = steps[keep]
        if len(np.unique(steps)) != len(steps):
            failures.append(f"{config_name}: {label} has a duplicate step")
        missing_steps = sorted(set(range(declared_steps)) - set(steps.tolist()))
        if missing_steps:
            failures.append(
                f"{config_name}: {label} is missing step {missing_steps[0]} "
                f"({len(missing_steps)} of {declared_steps} missing)"
            )
        sides[label] = frame.loc[keep].assign(_step=steps).set_index("_step")
    if failures or declared_steps == 0:
        return ForceComparison(False, 0, failures or ["no steps to compare"], n_rows)
    run_rows = sides["run"].sort_index()
    ref_rows = sides["reference"].sort_index()
    for column in FORCE_COLUMNS:
        ref_values = ref_rows[column].to_numpy(dtype=float)
        run_values = run_rows[column].to_numpy(dtype=float)
        finite_ref = ref_values[np.isfinite(ref_values)]
        column_max = float(np.max(np.abs(finite_ref))) if finite_ref.size else 0.0
        tolerance = np.maximum(
            COMPARE_RELATIVE_TO_COLUMN * column_max,
            COMPARE_PRINT_UNITS * print_unit(ref_values),
        )
        # `not (|diff| <= tol)` so that a NaN or inf on either side fails, never passes.
        bad = np.flatnonzero(~(np.abs(run_values - ref_values) <= tolerance))
        if len(bad):
            i = bad[0]
            failures.append(
                f"{config_name}: {column} differs at time {ref_rows['time'].iloc[i]:g}: "
                f"run {run_values[i]!r}, reference {ref_values[i]!r}, "
                f"tolerance {tolerance[i]:.3g} ({len(bad)} value(s) out of tolerance)"
            )
    return ForceComparison(not failures, len(ref_rows), failures, n_rows)


def field_change_stats(
    field: np.ndarray, reference: np.ndarray, *, u_ref: float
) -> dict[str, float]:
    """Median, and fraction above :data:`FIELD_CHANGE_THRESHOLD`, of the change in ``u_ref``.

    The change is the vector-difference norm ``|u - u_last| / u_ref`` per cell.

    Args:
        field: Velocity at one frame of beat ``b``, shape ``(..., 3)``.
        reference: Velocity at the matched frame of the last beat, same shape.
        u_ref: The reference wing speed (``compute_force_reference(...).u_ref``).

    Raises:
        ValueError: On mismatched shapes, a last axis other than 3, a non-finite value, or a
            non-positive ``u_ref``.
    """
    a = np.asarray(field, dtype=float)
    b = np.asarray(reference, dtype=float)
    if a.shape != b.shape or a.ndim < 1 or a.shape[-1] != 3:
        raise ValueError(
            f"field shapes {a.shape} and {b.shape} must match and end in 3"
        )
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b))):
        raise ValueError("field contains a non-finite value")
    if not u_ref > 0:
        raise ValueError(f"u_ref must be positive (got {u_ref})")
    change = np.linalg.norm(a - b, axis=-1) / u_ref
    return {
        "median": float(np.median(change)),
        "fraction_above": float(np.mean(change > FIELD_CHANGE_THRESHOLD)),
    }


# --------------------------------------------------------------------------- provenance

UPSTREAM_REF = "origin/main"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
Runner = Callable[..., "subprocess.CompletedProcess"]


def _git(repo_root: Path, *args: str, runner: Runner = subprocess.run):
    return runner(["git", *args], cwd=repo_root, capture_output=True)


def _dirty_lines(porcelain: str) -> list[str]:
    """Porcelain lines that make the checkout dirty; Stage 1 records do not."""
    return [
        line
        for line in porcelain.splitlines()
        if line.strip() and RECORDS_PREFIX not in line
    ]


def git_launch_state(repo_root: Path | str, *, runner: Runner = subprocess.run) -> dict:
    """The checkout's state when a run is launched: HEAD and ``git status --porcelain``.

    Written to ``<run_dir>/launch.json`` just before the container starts, and read back by
    :func:`git_provenance` when the record is written.
    """
    repo_root = Path(repo_root)
    head = _git(repo_root, "rev-parse", "HEAD", runner=runner)
    status = _git(
        repo_root, "status", "--porcelain", "--untracked-files=all", runner=runner
    )
    if head.returncode != 0 or status.returncode != 0:
        raise ValueError(f"settling: {repo_root} is not a usable git checkout")
    return {
        "start_commit": head.stdout.decode().strip(),
        "git_status_porcelain": status.stdout.decode(),
    }


def git_provenance(
    repo_root: Path | str,
    *,
    launch: Mapping,
    upstream_ref: str = UPSTREAM_REF,
    runner: Runner = subprocess.run,
) -> dict:
    """Derive a run's provenance from git, instead of taking the operator's word for it.

    Args:
        repo_root: The checkout the run was launched from.
        launch: The launch state (:func:`git_launch_state`): ``start_commit`` and
            ``git_status_porcelain`` at launch.
        upstream_ref: The ref the start commit must be an ancestor of.
        runner: ``subprocess.run`` (injectable for tests).

    Returns:
        ``start_commit``, ``head_commit``, ``upstream_ref``, ``ancestor_of_upstream``,
        ``dirty_at_launch``, ``dirty_at_record``, ``file_sha256`` (each gated file's SHA-256
        **at the start commit**, from ``git show``) and ``working_tree_matches_commit``.
        :func:`provenance_problems` lists what is wrong with it.
    """
    repo_root = Path(repo_root)
    start = str(launch.get("start_commit", ""))
    head = _git(repo_root, "rev-parse", "HEAD", runner=runner).stdout.decode().strip()
    ancestor = (
        _git(
            repo_root, "merge-base", "--is-ancestor", start, upstream_ref, runner=runner
        ).returncode
        == 0
    )
    status = _git(
        repo_root, "status", "--porcelain", "--untracked-files=all", runner=runner
    )
    hashes: dict[str, str | None] = {}
    matches = True
    for rel in GATED_FILES:
        shown = _git(repo_root, "show", f"{start}:{rel}", runner=runner)
        committed = _sha256_bytes(shown.stdout) if shown.returncode == 0 else None
        hashes[rel] = committed
        path = repo_root / rel
        if committed is None or not path.exists() or _sha256(path) != committed:
            matches = False
    return {
        "start_commit": start,
        "head_commit": head,
        "upstream_ref": upstream_ref,
        "ancestor_of_upstream": ancestor,
        "dirty_at_launch": bool(
            _dirty_lines(str(launch.get("git_status_porcelain", "")))
        ),
        "dirty_at_record": bool(_dirty_lines(status.stdout.decode())),
        "file_sha256": hashes,
        "working_tree_matches_commit": matches,
    }


def provenance_problems(provenance: Mapping) -> list[str]:
    """What is wrong with a run's git provenance (empty when it is clean and on upstream)."""
    problems: list[str] = []
    start = str(provenance.get("start_commit", ""))
    if not _COMMIT_RE.match(start):
        problems.append("provenance.start_commit is not a full 40-hex commit")
    if provenance.get("head_commit") != start:
        problems.append("provenance.head_commit differs: HEAD moved since launch")
    if provenance.get("ancestor_of_upstream") is not True:
        problems.append(
            "provenance.ancestor_of_upstream is false: the start commit is not on "
            f"{provenance.get('upstream_ref', UPSTREAM_REF)}"
        )
    if provenance.get("dirty_at_launch") is not False:
        problems.append("provenance.dirty_at_launch: the checkout was dirty at launch")
    if provenance.get("dirty_at_record") is not False:
        problems.append("provenance.dirty_at_record: the checkout is dirty")
    if provenance.get("working_tree_matches_commit") is not True:
        problems.append(
            "provenance.working_tree_matches_commit is false: a gated file differs from the "
            "start commit"
        )
    hashes = provenance.get("file_sha256")
    for rel in GATED_FILES:
        if not isinstance(hashes, Mapping) or not re.fullmatch(
            r"[0-9a-f]{64}", str(hashes.get(rel, ""))
        ):
            problems.append(f"provenance.file_sha256 lacks {rel}")
    return problems


# --------------------------------------------------------------------------- run records

RECORD_SCHEMA_VERSION = 2
REPORT_SCHEMA_VERSION = 1
NEAR_WING_BOX = ((1.0, 0.0, 2.5), (7.0, 4.0, 5.5))
_RUN_TIME_RE = re.compile(r"^Run time\s*=\s*([0-9.eE+-]+)", re.MULTILINE)
_PINNED_IMAGE_RE = re.compile(r"^[^@\s]+@sha256:[0-9a-f]{64}$")


def declared_controls(entry: Mapping) -> list[str]:
    """The controls a settling-manifest entry declares (``C1`` for a control deck)."""
    return ["C1"] if entry.get("kind") == "C1" else list(entry.get("controls", []))


def manifest_entry(settling_dir: Path | str, name: str) -> dict:
    """The settling-manifest entry (run or control) named ``name``.

    Raises:
        ValueError: If no entry, or more than one, has that name.
    """
    manifest = json.loads(
        (Path(settling_dir) / "settling_manifest.json").read_text(encoding="utf-8")
    )
    found = [
        e
        for e in [*manifest.get("runs", []), *manifest.get("controls", [])]
        if e["name"] == name
    ]
    if len(found) != 1:
        raise ValueError(
            f"settling: {name!r} names {len(found)} entries in the settling manifest; "
            "expected exactly one run or control"
        )
    return found[0]


def _reference_rows(repo_root: Path, entry: Mapping) -> tuple[pd.DataFrame, float]:
    """The committed corpus rows and stop time of ``entry``'s configuration."""
    corpus = repo_root / Path(entry["source_deck"]).parent.parent
    sweep = json.loads((corpus / "sweep_manifest.json").read_text(encoding="utf-8"))
    config = next((c for c in sweep["configs"] if c["name"] == entry["config"]), None)
    if config is None:
        raise ValueError(
            f"settling: {entry['config']!r} is not in {corpus / 'sweep_manifest.json'}"
        )
    data = pd.read_parquet(
        corpus / "dataset.parquet", filters=[("config_name", "==", entry["config"])]
    )
    return data, float(config["stop_time"])


def _wall_time(run_log: Path) -> float:
    found = _RUN_TIME_RE.findall(run_log.read_text(encoding="utf-8", errors="replace"))
    if len(found) != 1:
        raise ValueError(
            f"settling: expected one run-time line in {run_log}, found {len(found)} "
            "(a restarted run is not a valid settling run)"
        )
    return float(found[0])


def _required_file(run_dir: Path, name: str) -> Path:
    path = run_dir / name
    if not path.is_file():
        raise ValueError(f"settling: {name} is missing from {run_dir}")
    return path


def build_run_record(
    run_dir: Path | str,
    *,
    name: str,
    settling_dir: Path | str,
    repo_root: Path | str,
    provenance: Mapping,
    iamrex_commit: str,
    hardware: Mapping,
    field_change: Mapping | None = None,
) -> dict:
    """Build one settling run record, running the controls the settling manifest declares.

    Long runs get C3 (their first two beats against the committed corpus rows) and C4 (no
    interior step below the nominal ``dt``); C1 control runs get C1 (the first ``max_step``
    steps against the committed rows). Observed, not copied: the deck in ``run_dir`` is hashed,
    the command is read from ``run_dir/command.txt``, the step count comes from the run's own
    CSV, and the provenance comes from :func:`git_provenance`.

    ``run_dir`` must hold ``IB_Particle_1.csv``, ``run.log``, ``command.txt`` and the deck
    (named as in the settling manifest's ``deck``).

    Raises:
        ValueError: If a required file is missing, the name is not in the manifest, or the log
            has no single run-time line.
    """
    run_dir = Path(run_dir)
    settling_dir = Path(settling_dir)
    repo_root = Path(repo_root)
    entry = manifest_entry(settling_dir, name)
    csv = _required_file(run_dir, "IB_Particle_1.csv")
    run_log = _required_file(run_dir, "run.log")
    command = _required_file(run_dir, "command.txt").read_text(encoding="utf-8").strip()
    deck = _required_file(run_dir, Path(entry["deck"]).name)
    reference, reference_stop = _reference_rows(repo_root, entry)
    is_c1 = entry["kind"] == "C1"
    result = compare_force_csv(
        csv,
        reference,
        config_name=entry["config"],
        dt=DT,
        run_stop_time=float(entry["stop_time"]),
        reference_stop_time=reference_stop,
        declared_steps=int(entry["max_step"]) if is_c1 else None,
    )
    comparison = {
        "passed": result.passed,
        "n_compared": result.n_compared,
        "failures": result.failures,
    }
    controls: dict[str, dict] = {}
    if is_c1:
        controls["C1"] = comparison
    else:
        controls["C3"] = comparison
        observed = compute_dt_observations(
            read_dt_series_from_run_log(run_log), fixed_dt=DT
        )
        controls["C4"] = {
            "passed": not observed["interior_dt_below_nominal"],
            **observed,
        }
    wall = _wall_time(run_log)
    steps = result.n_rows
    record = {
        "schema_version": RECORD_SCHEMA_VERSION,
        "run": name,
        "grid": entry["grid"],
        "config": entry["config"],
        "kind": entry["kind"],
        "provenance": dict(provenance),
        "file_sha256": dict(provenance.get("file_sha256") or {}),
        "image": entry["image"],
        "iamrex_commit": iamrex_commit,
        "command": command,
        "deck_sha256": _sha256(deck),
        "hardware": dict(hardware) if isinstance(hardware, Mapping) else hardware,
        "wall_time_s": wall,
        "steps": steps,
        "seconds_per_step": wall / steps if steps else None,
        "force_csv_sha256": _sha256(csv),
        "run_log_sha256": _sha256(run_log),
        "controls": controls,
    }
    if field_change is not None:
        record["field_change"] = dict(field_change)
    return record


def _positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def validate_run_record(record: Mapping, entry: Mapping) -> list[str]:
    """Problems with a run record against its settling-manifest entry (empty when valid)."""
    problems: list[str] = []
    if record.get("run") != entry.get("name"):
        problems.append(f"run is {record.get('run')!r}, expected {entry.get('name')!r}")
    provenance = record.get("provenance")
    if not isinstance(provenance, Mapping):
        problems.append("provenance is missing")
    else:
        problems.extend(provenance_problems(provenance))
        if record.get("file_sha256") != provenance.get("file_sha256"):
            problems.append("file_sha256 is not the provenance's start-commit hashes")
    image = str(entry.get("image", ""))
    if not _PINNED_IMAGE_RE.match(image) or record.get("image") != image:
        problems.append(
            f"image {record.get('image')!r} is not the manifest's pinned image"
        )
    command = str(record.get("command", ""))
    if not command.strip():
        problems.append("command is empty")
    elif image not in command:
        problems.append("command does not run the manifest's pinned image")
    if record.get("deck_sha256") != entry.get("deck_sha256"):
        problems.append(
            "deck_sha256: the run's deck is not the committed settling deck"
        )
    if not str(record.get("iamrex_commit", "")).strip():
        problems.append("iamrex_commit is empty")
    if not isinstance(record.get("hardware"), Mapping) or not record.get("hardware"):
        problems.append("hardware is empty")
    for key in ("wall_time_s", "seconds_per_step", "steps"):
        if not _positive_number(record.get(key)):
            problems.append(f"{key} is missing or not positive")
    if record.get("steps") != entry.get("max_step"):
        problems.append(
            f"steps is {record.get('steps')}, the deck declares {entry.get('max_step')}: "
            "the run did not run to its end"
        )
    for control in declared_controls(entry):
        result = (record.get("controls") or {}).get(control)
        if not isinstance(result, Mapping) or not isinstance(
            result.get("passed"), bool
        ):
            problems.append(f"control {control} has no recorded result")
    return problems


# --------------------------------------------------------------------------- field change


def frame_index(
    step: int, *, dt: float, frequency_fstar: float, frames_per_beat: int
) -> tuple[int, int]:
    """Beat (1-based) and frame (0-based) of a time-triggered plotfile written after ``step``.

    ``amr.plot_per = 1 / (frames_per_beat f*)`` writes at the first step whose end time reaches
    each multiple, so the plotfile's time ``step * dt`` lies within one step of frame ``m``'s
    phase: ``m = round(step * dt * f* * frames_per_beat)``.
    """
    m = round(step * dt * frequency_fstar * frames_per_beat)
    return m // frames_per_beat + 1, m % frames_per_beat


def field_change_for_run(
    run_dir: Path | str,
    *,
    b_last: int,
    frequency_fstar: float,
    dt: float,
    u_ref: float,
    frames_per_beat: int,
    box: tuple[tuple[float, float, float], tuple[float, float, float]] = NEAR_WING_BOX,
    reader: Callable[..., Mapping[str, np.ndarray]] | None = None,
) -> dict:
    """Near-wing field change of beats ``1 .. b_last - 1`` against beat ``b_last``, per frame.

    Returns ``{"beats": {beat: {"median": [...], "fraction_above": [...]}},
    "plotfile_header_sha256": {step: sha}}`` with string keys (JSON-ready). Only each plotfile's
    ``Header`` is hashed.

    Raises:
        ValueError: If a frame of beats ``1 .. b_last`` has no plotfile or two plotfiles.
    """
    from mosquito_cfd.field_surrogate.corpus import scan_plotfiles

    if reader is None:
        from mosquito_cfd.benchmarks.stress_integral import (
            extract_eulerian_box as reader,
        )
    run_dir = Path(run_dir)
    frames: dict[tuple[int, int], tuple[int, Path]] = {}
    for step, path in sorted(scan_plotfiles(run_dir).items()):
        beat, k = frame_index(
            step,
            dt=dt,
            frequency_fstar=frequency_fstar,
            frames_per_beat=frames_per_beat,
        )
        if beat > b_last:
            continue
        if (beat, k) in frames:
            raise ValueError(f"settling: two plotfiles map to beat {beat} frame {k}")
        frames[(beat, k)] = (step, path)
    for beat in range(1, b_last + 1):
        for k in range(frames_per_beat):
            if (beat, k) not in frames:
                raise ValueError(
                    f"settling: no plotfile for beat {beat} frame {k} in {run_dir}"
                )

    def velocity(path: Path) -> np.ndarray:
        data = reader(path, lo=box[0], hi=box[1])
        return np.stack([data["u"], data["v"], data["w"]], axis=-1)

    last = {k: velocity(frames[(b_last, k)][1]) for k in range(frames_per_beat)}
    beats: dict[str, dict[str, list[float]]] = {}
    for beat in range(1, b_last):
        stats = [
            field_change_stats(velocity(frames[(beat, k)][1]), last[k], u_ref=u_ref)
            for k in range(frames_per_beat)
        ]
        beats[str(beat)] = {
            "median": [s["median"] for s in stats],
            "fraction_above": [s["fraction_above"] for s in stats],
        }
    headers = {
        str(step): _sha256(path / "Header") for step, path in sorted(frames.values())
    }
    return {"beats": beats, "plotfile_header_sha256": headers}


# --------------------------------------------------------------------------- report


def _finite_or_none(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return float(value)


def _keyed(values: Mapping[int, float]) -> dict[str, float | None]:
    return {str(k): _finite_or_none(v) for k, v in values.items()}


def _target_json(t: TargetSettling) -> dict:
    return {
        "peak": t.peak,
        "steps": _keyed(t.steps),
        "steps_max_abs": _keyed(t.steps_max_abs),
        "distances": _keyed(t.distances),
        "distances_max_abs": _keyed(t.distances_max_abs),
        "estimate": _keyed(t.estimate),
        "jitter": t.jitter,
        "noise_floor": t.noise_floor,
        "tail": _finite_or_none(t.tail),
        "rho": _finite_or_none(t.rho),
        "contracting": t.contracting,
        "ratios": [_finite_or_none(r) for r in t.ratios],
        "skipped": t.skipped,
    }


def _control_status(
    manifest: Mapping, settling_dir: Path
) -> tuple[dict[str, dict], dict[str, dict], list[str], list[str]]:
    """Per-entry control results, the valid records, and missing / failed messages.

    Every record is checked with :func:`validate_run_record`; an invalid record is a failure,
    and a control counts as passed only when its ``passed`` is the boolean ``True``.
    """
    missing: list[str] = []
    failed: list[str] = []
    controls: dict[str, dict] = {}
    records: dict[str, dict] = {}
    for entry in [*manifest.get("runs", []), *manifest.get("controls", [])]:
        name = entry["name"]
        path = settling_dir / "records" / f"{name}.json"
        if not path.exists():
            missing.append(f"{name}: no run record")
            continue
        record = _load_json(path, failed, f"records/{name}.json")
        if not isinstance(record, dict):
            if record is not None:
                failed.append(f"records/{name}.json: not a JSON object")
            continue
        records[name] = record
        failed.extend(f"{name}: {p}" for p in validate_run_record(record, entry))
        controls[name] = {}
        for control in declared_controls(entry):
            result = (record.get("controls") or {}).get(control)
            if not isinstance(result, Mapping) or "passed" not in result:
                missing.append(f"{name}: no {control} result")
                continue
            passed = result["passed"] is True
            controls[name][control] = {"passed": passed}
            if not passed:
                failed.append(f"{name}: {control} did not pass")
    return controls, records, missing, failed


def _extraction_csv_sha(settling_dir: Path, grid: str, config: str) -> str | None:
    path = settling_dir / grid / "run_metadata.json"
    if not path.exists():
        return None
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        return meta["extraction_inputs"]["csv_sha256"].get(config)
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def build_settling_report(
    settling_dir: Path | str, *, repo_root: Path | str, git_commit: str
) -> dict:
    """Recompute every force-derived settling number and apply the decision rule.

    Reads ``settling_manifest.json``, ``records/<name>.json``, ``<grid>/dataset.parquet`` and
    ``<grid>/run_metadata.json``. ``status`` is, in order of precedence:

    - ``controls_incomplete``: a declared record or control result is missing;
    - ``control_failed``: a record is invalid or a control did not pass;
    - ``precedence_failed``: :func:`check_precedence` reports a problem;
    - ``data_incomplete``: a run has no dataset rows, fewer complete beats than declared, or a
      dataset not extracted from the CSV its record hashes;
    - ``complete``.

    Infinite values are written as ``null`` (a non-contracting target also has
    ``contracting: false``). Field change and mean-lift drift are reported only.
    """
    settling_dir = Path(settling_dir)
    repo_root = Path(repo_root)
    manifest = json.loads(
        (settling_dir / "settling_manifest.json").read_text(encoding="utf-8")
    )
    controls, records, missing, failed = _control_status(manifest, settling_dir)
    runs: dict[str, dict] = {}
    verdicts: list[RunVerdict] = []
    data_missing: list[str] = []
    field_change_missing: list[str] = []
    datasets: dict[str, pd.DataFrame | None] = {}
    for entry in manifest.get("runs", []):
        name, grid = entry["name"], entry["grid"]
        if grid not in datasets:
            path = settling_dir / grid / "dataset.parquet"
            datasets[grid] = pd.read_parquet(path) if path.exists() else None
        data = datasets[grid]
        frame = None if data is None else data[data["config_name"] == entry["config"]]
        if frame is None or frame.empty:
            data_missing.append(f"{name}: no dataset rows")
            continue
        extracted = _extraction_csv_sha(settling_dir, grid, entry["config"])
        recorded = records.get(name, {}).get("force_csv_sha256")
        if recorded is not None and extracted != recorded:
            data_missing.append(
                f"{name}: the dataset was not extracted from the recorded CSV "
                f"(extraction {str(extracted)[:12]}, record {recorded[:12]})"
            )
        f_star = float(frame["frequency_fstar"].iloc[0])
        verdict = evaluate_run(
            name,
            frame,
            frequency_fstar=f_star,
            dt=DT,
            stop_time=float(entry["stop_time"]),
        )
        full = verdict.settling
        if full.b_last != int(entry["n_wingbeats"]):
            data_missing.append(
                f"{name}: {full.b_last} complete beats, the manifest declares "
                f"{entry['n_wingbeats']}"
            )
        verdicts.append(verdict)
        if grid == "fine" and not records.get(name, {}).get("field_change"):
            field_change_missing.append(name)
        means = full.mean_cf_z
        runs[name] = {
            "grid": grid,
            "config": entry["config"],
            "b_last": full.b_last,
            "incomplete_beats": full.incomplete_beats,
            "n_star": verdict.n_star,
            "passes": {str(n): ok for n, ok in verdict.passes.items()},
            "contracting": verdict.contracting,
            "max_noise": verdict.max_noise,
            "noise_target": verdict.noise_target,
            "binding_beat": verdict.binding_beat,
            "binding_target": verdict.binding_target,
            "targets": {t: _target_json(full.targets[t]) for t in TARGETS},
            "mean_cf_z": {str(b): v for b, v in means.items()},
            "mean_cf_z_drift": {
                str(b): means[b] - means[b - 1] for b in sorted(means) if b - 1 in means
            },
            "field_change": records.get(name, {}).get("field_change"),
        }
    precedence = check_precedence(settling_dir, repo_root=repo_root)
    decision = None
    if verdicts and not data_missing:
        d = decide_beat_count(verdicts)
        decision = {
            "action": d.action,
            "n_star": d.n_star,
            "run": d.run,
            "beat": d.beat,
            "target": d.target,
            "reason": d.reason,
        }
    if missing:
        status = "controls_incomplete"
    elif failed:
        status = "control_failed"
    elif precedence:
        status = "precedence_failed"
    elif data_missing:
        status = "data_incomplete"
    else:
        status = "complete"
    current = repo_root / SETTLING_PY
    current_sha = _sha256(current) if current.exists() else None
    recorded_settling = {
        (r.get("file_sha256") or {}).get(SETTLING_PY) for r in records.values()
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": status,
        "missing": missing,
        "failed": failed,
        "precedence": precedence,
        "data_missing": data_missing,
        "field_change_missing": field_change_missing,
        "constants": _preregistered_values(),
        "preregistration_sha256": _sha256(repo_root / GATED_FILES[0]),
        "git_commit": git_commit,
        "settling_py_sha256": current_sha,
        "settling_py_matches_records": bool(records)
        and recorded_settling == {current_sha},
        "controls": controls,
        "runs": runs,
        "decision": decision,
        "field_change_note": "reported only; not part of the decision",
    }
