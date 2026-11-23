"""Provisional hover gate: errors and yardsticks (spec requirement "Provisional hover gate").

Errors and yardsticks are fractions and share one normaliser per comparison: the corpus-wide
component peak ``peak_t`` for lab components, and the configuration's own CFD peak for the
body-frame normal and chord peaks. Peaks are always taken on the 256-phase grid, never on raw CSV
rows, because the last row of every f* = 0.85 configuration is anomalous (#173).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.benchmarks.flapping_wing import body_frame_coefficients
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix
from mosquito_cfd.surrogate_bench.ridge import PHASE_GRID, resample_beat

# T3c GCI_fine, the computed values behind RESULTS.md's 3.7 % and 27.6 %.
GCI_FINE = {"normal_peak": 0.03692, "chord_peak": 0.2758}
# T3c computed observed orders; the lab components borrow the normal order.
OBSERVED_ORDER = {"normal_peak": 1.3773, "chord_peak": 1.3655}
REFINEMENT_RATIO = 4
PEAKS = ("normal_peak", "chord_peak")
LAB_FORCE = ("CF_x", "CF_y", "CF_z")
# Grid points k/256 with k >= 13: the [0.05, 1) window of the startup-beat comparison.
WINDOW_START = 13
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
    for j, t in enumerate(targets):
        out[t] = {
            "full": float(np.sqrt(np.mean((model[:, j] - cfd[:, j]) ** 2)) / peaks[t]),
            "window": float(
                np.sqrt(np.mean((model[WINDOW_START:, j] - cfd[WINDOW_START:, j]) ** 2))
                / peaks[t]
            ),
        }
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
