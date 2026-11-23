"""Provisional hover gate: errors and yardsticks (spec requirement "Provisional hover gate").

Errors and yardsticks are fractions and share one normaliser per comparison: the corpus-wide
component peak ``peak_t`` for lab components, and the configuration's own CFD peak for the
body-frame normal and chord peaks. Peaks are always taken on the 256-phase grid, never on raw CSV
rows, because the last row of every f* = 0.85 configuration is anomalous (#173).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.benchmarks.flapping_wing import body_frame_coefficients
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix
from mosquito_cfd.surrogate_bench.ridge import N_GRID, PHASE_GRID, resample_beat

# T3c GCI_fine, the computed values behind RESULTS.md's 3.7 % and 27.6 %.
GCI_FINE = {"normal_peak": 0.03692, "chord_peak": 0.2758}
# T3c computed observed orders; the lab components borrow the normal order.
OBSERVED_ORDER = {"normal_peak": 1.3773, "chord_peak": 1.3655}
REFINEMENT_RATIO = 4
PEAKS = ("normal_peak", "chord_peak")
LAB_FORCE = ("CF_x", "CF_y", "CF_z")
# The startup-beat comparison's window starts at phase 0.05: the first grid point at or after it.
WINDOW_PHASE = 0.05
WINDOW_START = math.ceil(WINDOW_PHASE * N_GRID)
LATE_BEAT_MIN_BEATS = 4
UNAVAILABLE_LATE = "fewer than 4 beats"
SCALED_LABEL = (
    "order borrowed from T3c (one configuration, grid and timestep refined together); "
    "safety factor Fs = 1.25 not applied; the two corpora were built with different "
    "container digests"
)
_GCI_TABLES = {
    "normal_peak": "**CF_normal (z, lift)**",
    "chord_peak": "**CF_chord (x, tangential)**",
}
_GCI_ROW = re.compile(r"^\|\s*GCI_fine\s*\|\s*([0-9.]+)\s*%\s*\|", re.MULTILINE)


def parse_gci_from_results(text: str) -> dict[str, float]:
    """The ``GCI_fine`` percentages of the T3c CF_normal and CF_chord tables in RESULTS.md.

    Raises:
        ValueError: If a table heading or its ``GCI_fine`` row is missing, naming the table.
    """
    out = {}
    for comp, heading in _GCI_TABLES.items():
        start = text.find(heading)
        match = _GCI_ROW.search(text, start) if start >= 0 else None
        if match is None:
            raise ValueError(f"no GCI_fine row found under the T3c table {heading}")
        out[comp] = float(match.group(1))
    return out


# --- Body-frame rotation ------------------------------------------------------------------


def body_frame_series(
    phase: NDArray[np.floating],
    lab: NDArray[np.floating],
    *,
    stroke: float,
    fstar: float,
    pitch: float,
) -> dict[str, NDArray[np.floating]]:
    """Rotate lab ``CF_x, CF_y, CF_z`` into the wing frame at each phase.

    Phase → time is ``t = phase / f*``; degrees → radians; ``f_ref = 1`` because the inputs are
    already coefficients.

    Returns:
        ``{"normal", "chord", "span"}`` arrays.
    """
    phase = np.asarray(phase, dtype=float)
    rot = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    p / fstar,
                    frequency=fstar,
                    stroke_amp_rad=np.deg2rad(stroke),
                    pitch_amp_rad=np.deg2rad(pitch),
                )
            )
            for p in phase
        ]
    )
    out = body_frame_coefficients(np.asarray(lab, dtype=float), rot, 1.0)
    return {
        "normal": np.atleast_1d(out["cf_normal"]),
        "chord": np.atleast_1d(out["cf_chord"]),
        "span": np.atleast_1d(out["cf_span"]),
    }


def lab_grid(rows: pd.DataFrame) -> NDArray[np.floating]:
    """One configuration's lab ``CF_x, CF_y, CF_z`` on the phase grid, ``(256, 3)``."""
    return resample_beat(
        rows["phase"].to_numpy(dtype=float), rows[list(LAB_FORCE)].to_numpy(dtype=float)
    )


def _window(values: NDArray[np.floating], windowed: bool) -> NDArray[np.floating]:
    return values[WINDOW_START:] if windowed else values


def peak_values(
    grid: NDArray[np.floating],
    *,
    stroke: float,
    fstar: float,
    pitch: float,
    windowed: bool = False,
) -> dict[str, float]:
    """``max|C|`` of the body-frame normal and chord over the grid (or the window)."""
    series = body_frame_series(
        PHASE_GRID, grid, stroke=stroke, fstar=fstar, pitch=pitch
    )
    return {
        "normal_peak": float(np.abs(_window(series["normal"], windowed)).max()),
        "chord_peak": float(np.abs(_window(series["chord"], windowed)).max()),
    }


def _lab_columns(grid: NDArray[np.floating], targets: Sequence[str]) -> NDArray:
    return grid[:, [list(targets).index(c) for c in LAB_FORCE]]


def _scale(component: str) -> float:
    order = OBSERVED_ORDER.get(component, OBSERVED_ORDER["normal_peak"])
    return 1.0 / (REFINEMENT_RATIO**order - 1.0)


# --- Model errors ----------------------------------------------------------------------------


def config_errors(
    *,
    model: NDArray[np.floating],
    cfd: NDArray[np.floating],
    settings: Mapping[str, float],
    peaks: Mapping[str, float],
    targets: Sequence[str],
) -> dict[str, dict[str, float]]:
    """A model's error for one configuration, over the full grid and over the window.

    Args:
        model: The model's grid predictions, ``(256, T)``.
        cfd: The CFD target beat on the grid, ``(256, T)``.
        settings: ``stroke``, ``fstar``, ``pitch``.
        peaks: ``peak_t`` per target.
        targets: Target columns.

    Returns:
        ``{component: {"full": e, "window": e}}``: the RMS over ``peak_t`` for lab components,
        and ``|max|Ĉ| − max|C|| / max|C|`` for the two peaks.
    """
    out: dict[str, dict[str, float]] = {}
    # A diverged seed's non-finite value (inf included) becomes NaN, so its verdict takes the
    # spec's NaN path (outside, null margin) instead of a finite margin of 0 or a crash.
    model = np.where(np.isfinite(model), model, np.nan)
    for j, t in enumerate(targets):
        out[t] = {
            "full": float(np.sqrt(np.mean((model[:, j] - cfd[:, j]) ** 2)) / peaks[t]),
            "window": float(
                np.sqrt(np.mean((model[WINDOW_START:, j] - cfd[WINDOW_START:, j]) ** 2))
                / peaks[t]
            ),
        }
    if not np.isfinite(_lab_columns(model, targets)).all():
        for comp in PEAKS:
            out[comp] = {"full": float("nan"), "window": float("nan")}
        return out
    for key, windowed in (("full", False), ("window", True)):
        got = peak_values(_lab_columns(model, targets), **settings, windowed=windowed)
        ref = peak_values(_lab_columns(cfd, targets), **settings, windowed=windowed)
        for comp in PEAKS:
            out.setdefault(comp, {})[key] = abs(got[comp] - ref[comp]) / ref[comp]
    return out


# --- Yardsticks ------------------------------------------------------------------------------


def _relative_peak_change(
    a: Mapping[str, float], b: Mapping[str, float], comp: str
) -> float:
    return abs(a[comp] - b[comp]) / a[comp]


def config_yardsticks(
    *,
    beats: Mapping[int, NDArray[np.floating]],
    coarse: NDArray[np.floating] | None,
    settings: Mapping[str, float],
    peaks: Mapping[str, float],
    targets: Sequence[str],
    coarse_reason: str = "no coarse corpus supplied",
) -> dict[str, dict[str, Any]]:
    """Every yardstick for one configuration.

    Args:
        beats: The CFD on the grid per ``wingbeat`` (``0..N−1``), each ``(256, T)``.
        coarse: The coarse corpus's target beat on the grid, or ``None``.
        settings: ``stroke``, ``fstar``, ``pitch``.
        peaks: ``peak_t`` per target.
        targets: Target columns.
        coarse_reason: Why ``coarse`` is ``None``.

    Returns:
        ``{component: {yardstick: {"value": …} | {"unavailable": reason} |
        {"not_applicable": True}}}``.
    """
    n_beats = len(beats)
    target = max(beats)
    fine = beats[target]
    components = [*targets, *PEAKS]
    out: dict[str, dict[str, Any]] = {c: {} for c in components}

    for comp in components:
        out[comp]["grid_gci"] = (
            {"value": GCI_FINE[comp]} if comp in PEAKS else {"not_applicable": True}
        )

    fine_peaks = peak_values(_lab_columns(fine, targets), **settings)
    if coarse is None:
        for comp in components:
            out[comp]["coarse_vs_fine"] = {"unavailable": coarse_reason}
            out[comp]["coarse_vs_fine_scaled"] = {"unavailable": coarse_reason}
    else:
        coarse_peaks = peak_values(_lab_columns(coarse, targets), **settings)
        for j, t in enumerate(targets):
            value = float(np.sqrt(np.mean((coarse[:, j] - fine[:, j]) ** 2)) / peaks[t])
            out[t]["coarse_vs_fine"] = {"value": value, "upper_bound": True}
        for comp in PEAKS:
            value = _relative_peak_change(fine_peaks, coarse_peaks, comp)
            out[comp]["coarse_vs_fine"] = {"value": value, "upper_bound": True}
        for comp in components:
            out[comp]["coarse_vs_fine_scaled"] = {
                "value": out[comp]["coarse_vs_fine"]["value"] * _scale(comp),
                "label": SCALED_LABEL,
            }

    b0, b1 = beats[0], beats[1]
    for j, t in enumerate(targets):
        diff = b1[WINDOW_START:, j] - b0[WINDOW_START:, j]
        out[t]["beat1_vs_beat2"] = {
            "value": float(np.sqrt(np.mean(diff**2)) / peaks[t])
        }
    p1 = peak_values(_lab_columns(b1, targets), **settings, windowed=True)
    p0 = peak_values(_lab_columns(b0, targets), **settings, windowed=True)
    for comp in PEAKS:
        out[comp]["beat1_vs_beat2"] = {"value": _relative_peak_change(p1, p0, comp)}

    if n_beats < LATE_BEAT_MIN_BEATS:
        for comp in components:
            out[comp]["late_beat"] = {"unavailable": UNAVAILABLE_LATE}
    else:
        last, prev = beats[n_beats - 1], beats[n_beats - 2]
        for j, t in enumerate(targets):
            value = float(np.sqrt(np.mean((last[:, j] - prev[:, j]) ** 2)) / peaks[t])
            out[t]["late_beat"] = {
                "value": value,
                "compares": [n_beats - 1, n_beats - 2],
            }
        pl = peak_values(_lab_columns(last, targets), **settings)
        pp = peak_values(_lab_columns(prev, targets), **settings)
        for comp in PEAKS:
            out[comp]["late_beat"] = {
                "value": _relative_peak_change(pl, pp, comp),
                "compares": [n_beats - 1, n_beats - 2],
            }
    return out


# --- Wrap jump -------------------------------------------------------------------------------


def wrap_jump(
    phase: NDArray[np.floating], values: NDArray[np.floating], normaliser: float
) -> dict[str, float]:
    """The beat's discontinuity at the wrap, as fractions of ``normaliser``.

    Returns:
        ``raw`` (first vs last row), ``last_but_one`` (first vs last-but-one row),
        ``slope_corrected`` (first row vs the last-but-two and last-but-one rows extrapolated to
        ``1 + φ_first``) and ``gap_spacings`` (the wrap gap in median row spacings).
    """
    order = np.argsort(np.asarray(phase, dtype=float), kind="stable")
    p = np.asarray(phase, dtype=float)[order]
    v = np.asarray(values, dtype=float)[order]
    target_phase = 1.0 + p[0]
    slope = (v[-2] - v[-3]) / (p[-2] - p[-3])
    extrapolated = v[-2] + slope * (target_phase - p[-2])
    return {
        "raw": float(abs(v[0] - v[-1]) / normaliser),
        "last_but_one": float(abs(v[0] - v[-2]) / normaliser),
        "slope_corrected": float(abs(v[0] - extrapolated) / normaliser),
        "gap_spacings": float((target_phase - p[-1]) / np.median(np.diff(p))),
    }


def config_wrap_jumps(
    rows: pd.DataFrame,
    *,
    stroke: float,
    fstar: float,
    pitch: float,
    peaks: Mapping[str, float],
    targets: Sequence[str] = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"),
) -> dict[str, dict[str, float]]:
    """Wrap jumps of one configuration's target beat for every target and the two peaks."""
    rows = rows.sort_values("phase", kind="stable")
    phase = rows["phase"].to_numpy(dtype=float)
    out = {
        t: wrap_jump(phase, rows[t].to_numpy(dtype=float), peaks[t]) for t in targets
    }
    settings = dict(stroke=stroke, fstar=fstar, pitch=pitch)
    series = body_frame_series(
        phase, rows[list(LAB_FORCE)].to_numpy(dtype=float), **settings
    )
    grid_peaks = peak_values(lab_grid(rows), **settings)
    out["normal_peak"] = wrap_jump(phase, series["normal"], grid_peaks["normal_peak"])
    out["chord_peak"] = wrap_jump(phase, series["chord"], grid_peaks["chord_peak"])
    return out


# --- Verdicts --------------------------------------------------------------------------------

ALL_ZERO_REASON = "all configurations 0/0"
# How the summary documents a reason (spec "Gate boundaries"): 0/0 is not a failure.
REASON_NOTES = {
    ALL_ZERO_REASON: "no error and no yardstick, not a failure: the model and the CFD agree "
    "exactly and the yardstick is zero",
}
HOLDOUT_STATEMENT = (
    "No entry is known to be holdout-clean, so an inside verdict here is not an unbiased "
    "estimate of the error on new configurations."
)
FIXED_REASONS = (
    "grid_gci is from one configuration at 70° stroke, outside the corpus's 35–55°",
    "grid_gci is from a one-beat run, so its peaks are those of the startup beat",
    "T3c refined grid and timestep together, and its fine run used dt = 2.5e-4 at "
    "cfl = 0.3 while the corpus uses 5e-4 at 0.6, so the corpus's temporal error is not "
    "covered",
    "the T3c deck's z boundary condition is 2 where the corpus's is 4",
    "coarse_vs_fine is an upper bound on the fine grid's error, not an estimate of it: "
    "under the asymptotic Richardson model the coarse-fine difference is (r^p - 1) "
    "(about 5.8) times the fine grid's error, and it under-estimates the coarse grid's "
    "error",
    "beat1_vs_beat2 includes the startup beat of a 2-beat run that has not settled",
)
_WINDOWED_YARDSTICKS = ("beat1_vs_beat2",)


def verdict(
    errors: Mapping[str, Sequence[float]], yardsticks: Mapping[str, float]
) -> dict[str, Any]:
    """The verdict of one entry, component and yardstick.

    The worst seed decides; it is NaN if any seed is NaN. ``inside`` needs ``worst ≤
    yardstick`` for every configuration. The margin is the minimum of ``yardstick / worst``:
    ``"inf"`` where the worst error is 0, configurations with both 0 left out (``None`` if all
    are), and ``None`` with ``outside`` on any NaN.

    Args:
        errors: Per configuration, the error of each seed.
        yardsticks: Per configuration, the yardstick value.

    Returns:
        ``{"verdict", "margin"}`` and, where the margin is ``None``, a ``"reason"``.
    """
    worst = {}
    for config, values in errors.items():
        arr = np.asarray(values, dtype=float)
        worst[config] = float("nan") if np.isnan(arr).any() else float(arr.max())
    for config, value in worst.items():
        if np.isnan(value):
            return {
                "verdict": "outside",
                "margin": None,
                "reason": f"a seed's error is NaN for {config}",
            }
        if np.isnan(yardsticks[config]):
            return {
                "verdict": "outside",
                "margin": None,
                "reason": f"the yardstick is NaN for {config}",
            }
    inside = all(worst[c] <= yardsticks[c] for c in worst)
    terms = []
    for config, value in worst.items():
        y = float(yardsticks[config])
        if value == 0.0 and y == 0.0:
            continue
        terms.append(float("inf") if value == 0.0 else y / value)
    result: dict[str, Any] = {"verdict": "inside" if inside else "outside"}
    if not terms:
        result.update(margin=None, reason=ALL_ZERO_REASON)
    else:
        margin = min(terms)
        result["margin"] = "inf" if margin == float("inf") else margin
    return result


def component_verdicts(
    errors: Mapping[str, Mapping[int, Mapping[str, float]]],
    yardsticks: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, Any]:
    """Verdicts of one entry and component against each yardstick separately.

    Args:
        errors: ``{config: {seed: {"full", "window"}}}``.
        yardsticks: ``{config: {yardstick: entry}}``.

    Returns:
        ``{yardstick: verdict}``, or ``{"status": "no_yardstick"}`` when no yardstick applies.
    """
    configs = list(errors)
    names = list(yardsticks[configs[0]])
    out: dict[str, Any] = {}
    for name in names:
        first = yardsticks[configs[0]][name]
        if first.get("not_applicable"):
            out[name] = {"verdict": "not_applicable"}
            continue
        if "unavailable" in first:
            out[name] = {"verdict": "unavailable", "reason": first["unavailable"]}
            continue
        key = "window" if name in _WINDOWED_YARDSTICKS else "full"
        per_config = {
            c: [errors[c][s][key] for s in sorted(errors[c])] for c in configs
        }
        values = {c: float(yardsticks[c][name]["value"]) for c in configs}
        out[name] = {**verdict(per_config, values), "yardstick": values}
    if not any("yardstick" in v for v in out.values()):
        return {"status": "no_yardstick"}
    return out


def with_combined_yardsticks(
    yardsticks: Mapping[str, Mapping[str, Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    """Add the peaks' quadrature and linear GCI + late-beat yardsticks where late is available."""
    out = {comp: dict(entries) for comp, entries in yardsticks.items()}
    for comp in PEAKS:
        late = out.get(comp, {}).get("late_beat", {})
        if "value" not in late:
            continue
        gci = GCI_FINE[comp]
        out[comp]["grid_gci_late_quadrature"] = {
            "value": float(np.hypot(gci, late["value"]))
        }
        out[comp]["grid_gci_late_linear"] = {"value": float(gci + late["value"])}
    return out


def wrap_reason(
    wrap_jumps: Mapping[str, Mapping[str, Mapping[str, float]]],
    peak_wrap_distance: Mapping[str, float],
    test_configs: Sequence[str],
) -> str:
    """The non-periodic-beat reason, computed from the recorded jumps (never fixed text)."""
    every = [j["normal_peak"]["last_but_one"] for j in wrap_jumps.values()]
    tested = [
        wrap_jumps[c]["normal_peak"]["last_but_one"]
        for c in test_configs
        if c in wrap_jumps
    ]
    return (
        "the converged beat is not periodic: its largest body-frame normal wrap jump "
        f"(first row vs last-but-one row) is {100 * max(every):.1f} % of the normal peak over "
        f"all configurations and {100 * max(tested):.1f} % over the gated test "
        f"configurations, beside grid_gci {100 * GCI_FINE['normal_peak']:.1f} %; every normal "
        f"peak lies within {max(peak_wrap_distance.values()):.3f} of phase of the wrap"
    )


def gate_block(
    *,
    entries: Mapping[
        str, Mapping[str, Mapping[int, Mapping[str, Mapping[str, float]]]]
    ],
    yardsticks: Mapping[str, Mapping[str, Mapping[str, Any]]],
    wrap_jumps: Mapping[str, Mapping[str, Mapping[str, float]]],
    peak_wrap_distance: Mapping[str, float],
    test_configs: Sequence[str],
    holdout_status: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """The provisional per-component hover gate of the interpolation split.

    Args:
        entries: ``{entry: {config: {seed: {component: {"full", "window"}}}}}``.
        yardsticks: ``{config: {component: {yardstick: entry}}}`` from
            :func:`config_yardsticks`.
        wrap_jumps: ``{config: …}`` from :func:`config_wrap_jumps`, every configuration.
        peak_wrap_distance: Per configuration, the phase distance of its normal peak from
            the wrap.
        test_configs: The gated test configurations.
        holdout_status: Per entry, ``holdout_informed`` and ``holdout_reason``.

    Returns:
        The gate block: ``provisional``, ``reasons``, ``holdout_statement``, ``reason_notes``
        (what a verdict reason such as ``"all configurations 0/0"`` means) and the verdicts per
        entry and component. It has no overall pass/fail.
    """
    combined = {c: with_combined_yardsticks(yardsticks[c]) for c in test_configs}
    components = list(combined[test_configs[0]])
    out_entries = {}
    for entry, per_config in entries.items():
        comps = {}
        for comp in components:
            errs = {
                c: {s: per_config[c][s][comp] for s in per_config[c]}
                for c in test_configs
            }
            comps[comp] = component_verdicts(
                errs, {c: combined[c][comp] for c in test_configs}
            )
        out_entries[entry] = {**holdout_status[entry], "components": comps}
    return {
        "provisional": True,
        "reasons": [
            *FIXED_REASONS,
            wrap_reason(wrap_jumps, peak_wrap_distance, test_configs),
        ],
        "holdout_statement": HOLDOUT_STATEMENT,
        "reason_notes": dict(REASON_NOTES),
        "entries": out_entries,
    }


def normal_peak_wrap_distance(
    grid: NDArray[np.floating], *, stroke: float, fstar: float, pitch: float
) -> float:
    """Phase distance from the wrap of a configuration's body-frame normal grid peak."""
    series = body_frame_series(
        PHASE_GRID, grid, stroke=stroke, fstar=fstar, pitch=pitch
    )
    phase = float(PHASE_GRID[int(np.argmax(np.abs(series["normal"])))])
    return min(phase, 1.0 - phase)
