"""Heaving-ellipsoid validation graders (Tier T2b).

The heaving ellipsoid (Re=100) is graded on **self-consistency** (not a literature Cd point) plus an
**added-mass-fraction sanity** — it is a symmetric constant-velocity translating body (heave in +y),
so its *steady* added mass is ~0 and its added-mass fraction is expected *below* van Veen's flapping
wing 15%/31% ballpark. All graders are cluster-free on any IB-particle CSV (a synthetic fixture or the
committed re-run ``forces_t2b_ib.csv``); the added-mass term reuses the wing's ``added_mass_force``
(``rho_f*SumU``, the ``WriteIBForceAndMoment`` definition), locking the formula to the solver source.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.benchmarks.flapping_wing import RHO, added_mass_force

# Steady window: the ellipsoid reaches quasi-steady state by t=7 (METHODS.md Case 2).
STEADY_WINDOW_T0 = 7.0
# Self-consistency threshold: forces change < 1% in the steady window (max consecutive-sample rel change).
SELF_CONSISTENCY_TOL = 0.01
# The committed forces.csv is sampled at dt=1.0 — too coarse to resolve a per-step steadiness gate;
# a series whose median steady-window spacing exceeds this declines rather than being mis-graded.
MAX_SAMPLE_DT = 0.1
# van Veen (2022) flapping-WING added-mass fractions, carried as a REPORTED order-of-magnitude sanity
# ballpark (NOT a graded match — CC-V2). Source: the aerodynamics-validation roadmap oracle row for the
# heaving ellipsoid, which cites van Veen 2022. The ellipsoid's constant-velocity steady share is
# expected at/below these accelerating-wing values.
VAN_VEEN_ADDED_MASS_BALLPARK = {"lift": 0.15, "drag": 0.31}

_REQUIRED_FORCE_COLUMNS = ("time", "Fx", "Fy")
_REQUIRED_SUMU_COLUMNS = ("time", "Fx", "Fy", "SumUx", "SumUy")


def _as_df(data: pd.DataFrame | str | Path) -> pd.DataFrame:
    return data if isinstance(data, pd.DataFrame) else pd.read_csv(data)


def _require(df: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [c for c in columns if c not in df.columns]
    if missing:
        raise ValueError(
            f"ellipsoid IB CSV is missing required column(s) {missing}; expected {list(columns)}"
        )


def _max_consecutive_rel_change(x: np.ndarray) -> float:
    """Max |x[i+1]-x[i]| / |x[i]| over consecutive samples (denominator guarded).

    Returns ``inf`` (fails safe) if no consecutive pair has a finite relative change (e.g. an
    all-near-zero series), avoiding a spurious ``All-NaN slice`` warning.
    """
    prev, nxt = x[:-1], x[1:]
    denom = np.where(np.abs(prev) > 1e-12, np.abs(prev), np.nan)
    rel = np.abs(nxt - prev) / denom
    return float(np.nanmax(rel)) if np.any(np.isfinite(rel)) else float("inf")


def ellipsoid_self_consistency(
    data: pd.DataFrame | str | Path,
    *,
    window_t0: float = STEADY_WINDOW_T0,
    tol: float = SELF_CONSISTENCY_TOL,
) -> dict:
    """Grade steady-window self-consistency of the drag (Fx) and heave-lift (Fy) forces.

    Grades the **drag `Fx`** and **heave-direction lift `Fy`** channels (the heave is prescribed in
    +y); the spanwise `Fz` (~0 by symmetry) is not graded, to avoid a degenerate 0/0. Measured as the
    **maximum consecutive-sample relative change** over ``t >= window_t0``; ``converged`` is
    ``max change < tol``. A series sampled too coarsely to resolve a per-step change (median steady
    spacing ``> MAX_SAMPLE_DT``, e.g. the committed 1.0-unit ``forces.csv``) **declines with a clear
    error** — a single deterministic branch — rather than being mis-graded.

    Raises:
        ValueError: too few steady-window samples; degenerate/too-coarse sampling; or non-finite
            steady-window forces (an all-NaN series must not silently grade ``converged=False``).
    """
    df = _as_df(data)
    _require(df, _REQUIRED_FORCE_COLUMNS)
    t = df["time"].to_numpy(float)
    m = t >= window_t0
    t_w = t[m]
    if t_w.size < 3:
        raise ValueError(
            f"self-consistency declines: only {t_w.size} sample(s) in the steady window "
            f"t >= {window_t0}; need >= 3 to resolve a consecutive-sample change"
        )
    median_dt = float(np.median(np.diff(t_w)))
    if not np.isfinite(median_dt) or median_dt <= 0:
        raise ValueError(
            "self-consistency declines: non-increasing/degenerate steady-window timestamps "
            f"(median dt = {median_dt:g}); time must be strictly increasing"
        )
    if median_dt > MAX_SAMPLE_DT:
        raise ValueError(
            f"self-consistency declines: steady-window sampling is too coarse "
            f"(median dt = {median_dt:g} > {MAX_SAMPLE_DT}); cannot resolve per-step steadiness — "
            "grade a finer re-run series, not the coarse committed forces.csv"
        )
    drag_w = df["Fx"].to_numpy(float)[m]
    lift_w = df["Fy"].to_numpy(float)[m]
    if not (np.all(np.isfinite(drag_w)) and np.all(np.isfinite(lift_w))):
        raise ValueError(
            "self-consistency declines: steady-window Fx/Fy contain non-finite values — "
            "cannot grade convergence on NaN/inf forces (this would silently read as not-converged)"
        )
    drag = _max_consecutive_rel_change(drag_w)
    lift = _max_consecutive_rel_change(lift_w)
    return {
        "max_rel_change_drag": drag,
        "max_rel_change_lift": lift,
        "converged": drag < tol and lift < tol,
        "window_t0": window_t0,
        "tol": tol,
        "n_samples": int(t_w.size),
    }


def ellipsoid_added_mass_fraction(
    data: pd.DataFrame | str | Path,
    *,
    rho_f: float = RHO,
    window_t0: float = STEADY_WINDOW_T0,
) -> dict:
    """Report the added-mass fraction (``rho_f*SumU`` relative to ib_force) for drag and lift.

    The **steady-window** fraction is the physically-meaningful quantity: for a constant-velocity heave
    it is ~0 (near-zero steady added mass), well **bounded** below 1, and **decays** from the impulsive
    start. The **per-timestep** ``frac_*`` arrays carry ``NaN`` at an ib-force zero-crossing (where the
    ratio is undefined — NOT a fabricated 0), so a real heave-lift ``Fy`` crossing zero legitimately
    yields NaN there; means are taken with ``nanmean``. The van Veen 15%/31% ballpark is a REPORTED
    order-of-magnitude sanity, **not** matched (CC-V2), and is returned as a COPY so callers cannot
    mutate the module constant.

    Returns per-timestep ``frac_drag``/``frac_lift`` arrays (NaN at zero-crossings), ``decays_*``
    booleans (early-window mean > steady-window mean), the ``early_frac_*``/``steady_frac_*`` nanmeans,
    and a copy of the ballpark.

    Raises:
        ValueError: no samples, or no steady-window (``t >= window_t0``) samples to characterize.
    """
    df = _as_df(data)
    _require(df, _REQUIRED_SUMU_COLUMNS)
    t = df["time"].to_numpy(float)
    steady = t >= window_t0
    early = t < window_t0
    if t.size == 0 or not steady.any():
        raise ValueError(
            f"added-mass fraction: no samples in the steady window t >= {window_t0} "
            f"(data time range covers {t.size} sample(s)); cannot characterize the fraction"
        )
    am_x = added_mass_force(df["SumUx"].to_numpy(float), rho_f)
    am_y = added_mass_force(df["SumUy"].to_numpy(float), rho_f)

    def frac(added: np.ndarray, ib: np.ndarray) -> np.ndarray:
        # NaN (kept, not fabricated 0) where ib passes through zero — the ratio is undefined there.
        denom = np.where(np.abs(ib) > 1e-12, np.abs(ib), np.nan)
        return np.abs(added) / denom

    frac_drag = frac(am_x, df["Fx"].to_numpy(float))
    frac_lift = frac(am_y, df["Fy"].to_numpy(float))

    def _nanmean(a: np.ndarray, mask: np.ndarray) -> float:
        sel = a[mask]
        return float(np.nanmean(sel)) if np.any(np.isfinite(sel)) else float("nan")

    early_drag, steady_drag = _nanmean(frac_drag, early), _nanmean(frac_drag, steady)
    early_lift, steady_lift = _nanmean(frac_lift, early), _nanmean(frac_lift, steady)
    return {
        "frac_drag": frac_drag,
        "frac_lift": frac_lift,
        "early_frac_drag": early_drag,
        "steady_frac_drag": steady_drag,
        "early_frac_lift": early_lift,
        "steady_frac_lift": steady_lift,
        "decays_drag": steady_drag < early_drag,
        "decays_lift": steady_lift < early_lift,
        "van_veen_ballpark": dict(VAN_VEEN_ADDED_MASS_BALLPARK),
    }
