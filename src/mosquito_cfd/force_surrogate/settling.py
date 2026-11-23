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

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TARGETS: tuple[str, ...] = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")

# Pre-registered constants (pinned to PREREGISTRATION.md's constants block by a test).
SETTLED_TOLERANCE = 0.01
COMPLETE_FRACTION = 0.95
MIN_BEATS = 5
FIRST_RATIO_BEAT = 4
NOISE_FACTOR = 3
MAX_NOISE = 0.0006

# Bound used when every ratio is noise: rho / (1 - rho) at rho = 0.96.
_AT_FLOOR_FACTOR = 24.0
# Slack on the clamped-step test (time + dt > stop_time + slack), for float equality at f100.
_CLAMP_SLACK = 1e-9
# Beat count above which regeneration needs the user's approval of the cost.
COST_APPROVAL_ABOVE = 6

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
    keep = frame["time"].to_numpy(dtype=float) + dt <= stop_time + _CLAMP_SLACK
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
        tail = _AT_FLOOR_FACTOR * max(steps[b] for b in beats)
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


def _split_beats(
    frame: pd.DataFrame, config_name: str, frequency_fstar: float, dt: float
) -> tuple[list[pd.DataFrame], list[int]]:
    """Return the complete beats (1-based order) and the numbers of trailing incomplete beats."""
    expected = 1.0 / (frequency_fstar * dt)
    need = COMPLETE_FRACTION * expected
    ordered = frame.sort_values("time", kind="stable")
    labels = ordered["wingbeat"].to_numpy()
    if len(labels) and labels.min() < 0:
        raise ValueError(f"settling: config {config_name!r} has a negative wingbeat")
    n_beats = int(labels.max()) + 1 if len(labels) else 0
    beats: list[pd.DataFrame] = []
    complete: list[bool] = []
    for index in range(n_beats):
        beat = ordered[ordered["wingbeat"] == index]
        phase = beat["phase"].to_numpy(dtype=float)
        if len(phase) > 1 and not np.all(np.diff(phase) > 0):
            raise ValueError(
                f"settling: config {config_name!r} beat {index + 1} has a duplicate or "
                "non-increasing phase"
            )
        beats.append(beat)
        complete.append(len(beat) >= need)
    if not complete or not complete[0]:
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
        if v.max_noise > MAX_NOISE:
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
        n_star,
        slowest.binding_target,
        f"N* = {n_star}, set by {slowest.run} ({slowest.binding_target})",
    )
