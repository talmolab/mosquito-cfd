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
    """Max |x[i+1]-x[i]| / |x[i]| over consecutive samples (denominator guarded)."""
    prev, nxt = x[:-1], x[1:]
    denom = np.where(np.abs(prev) > 1e-12, np.abs(prev), np.nan)
    rel = np.abs(nxt - prev) / denom
    return float(np.nanmax(rel))


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
        ValueError: too few steady-window samples, or a steady sampling too coarse to resolve the gate.
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
    if median_dt > MAX_SAMPLE_DT:
        raise ValueError(
            f"self-consistency declines: steady-window sampling is too coarse "
            f"(median dt = {median_dt:g} > {MAX_SAMPLE_DT}); cannot resolve per-step steadiness — "
            "grade a finer re-run series, not the coarse committed forces.csv"
        )
    drag = _max_consecutive_rel_change(df["Fx"].to_numpy(float)[m])
    lift = _max_consecutive_rel_change(df["Fy"].to_numpy(float)[m])
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

    The fraction is expected to be **bounded** (0 <= f < 1) and to **decay** after the impulsive start
    (a constant-velocity heave has ~zero *steady* added mass). The result carries the van Veen 15%/31%
    ballpark for a REPORTED order-of-magnitude sanity — it is **not** matched (CC-V2).

    Returns per-timestep ``frac_drag``/``frac_lift`` arrays, ``decays_*`` booleans (early-window mean
    exceeds steady-window mean), the ``early_frac_*``/``steady_frac_*`` means, and the ballpark.
    """
    df = _as_df(data)
    _require(df, _REQUIRED_SUMU_COLUMNS)
    t = df["time"].to_numpy(float)
    am_x = added_mass_force(df["SumUx"].to_numpy(float), rho_f)
    am_y = added_mass_force(df["SumUy"].to_numpy(float), rho_f)

    def frac(added: np.ndarray, ib: np.ndarray) -> np.ndarray:
        denom = np.where(np.abs(ib) > 1e-12, np.abs(ib), np.nan)
        return np.abs(added) / denom

    frac_drag = np.nan_to_num(frac(am_x, df["Fx"].to_numpy(float)))
    frac_lift = np.nan_to_num(frac(am_y, df["Fy"].to_numpy(float)))

    early = t < window_t0
    steady = t >= window_t0
    early_drag = float(np.mean(frac_drag[early])) if early.any() else float("nan")
    steady_drag = float(np.mean(frac_drag[steady])) if steady.any() else float("nan")
    early_lift = float(np.mean(frac_lift[early])) if early.any() else float("nan")
    steady_lift = float(np.mean(frac_lift[steady])) if steady.any() else float("nan")
    return {
        "frac_drag": frac_drag,
        "frac_lift": frac_lift,
        "early_frac_drag": early_drag,
        "steady_frac_drag": steady_drag,
        "early_frac_lift": early_lift,
        "steady_frac_lift": steady_lift,
        "decays_drag": steady_drag < early_drag,
        "decays_lift": steady_lift < early_lift,
        "van_veen_ballpark": VAN_VEEN_ADDED_MASS_BALLPARK,
    }
