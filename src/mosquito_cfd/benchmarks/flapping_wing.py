"""Flapping-wing plausibility-gate analysis (van Veen 2022), analysis-only.

Reconstructs force coefficients from the committed IB-particle CSV under the van Veen
convention (``F_ref = 0.5*rho*omega**2*S_yy`` via the single-source helper). The
**plausibility gate is graded on ``ib_force`` alone**; the added-mass term and the full
6-DOF momentum-balance force are reported **separately**, with their formula locked to the
IAMReX ``WriteIBForceAndMoment`` definition (not tuned to make the gate pass).

IAMReX force semantics (``IAMReX-fork/Source/DiffusedIB.cpp``):
  - ``Fx/Fy/Fz`` columns are ``kernel.ib_force`` (the accumulated immersed-boundary force).
  - ``SumU{x,y,z}`` columns are written as ``(sum_u_new - sum_u_old)/dt`` (line ~1261) — i.e.
    **already a rate**, NOT a raw momentum sum, so no further ``d/dt`` is applied here.
  - The 6-DOF momentum balance (line ~1078) makes the net hydrodynamic force
    ``F_hydro = rho_f * (SumU - ib_force)``. The added-mass contribution is ``rho_f * SumU``.

Frame caveat (issue #1 / T2a): these are **lab-frame** coefficients. van Veen's band is a
body-frame per-component statement; the gate here is an O(1) **magnitude plausibility** check.
The faithful body-frame per-component comparison and the time-resolved curve match are deferred
to T2a (#1) and T4.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN

# Steady evaluation window: a documented PHYSICAL criterion, not tuned to land in band.
# The impulsive-start transient is confined to the first ~8 steps (t <= 0.004), where
# |CF_x| spikes to ~39; any t0 >= 0.005 is clean. We use one-twentieth of a wingbeat.
STEADY_WINDOW_T0 = 0.05

# van Veen plausibility band for insect-wing force coefficients (van Veen 2022, JFM 936:A3).
VAN_VEEN_BAND = (0.5, 1.5)

# IB-particle CSV columns this analysis reads (subset of the 29-col IAMReX schema).
_REQUIRED_CSV_COLUMNS = ("time", "Fx", "Fz", "SumUx", "SumUz")


def _steady_mask(decomp: WingForceDecomposition, window_t0: float) -> NDArray[np.bool_]:
    """Boolean mask for the steady window, raising if it selects no timesteps."""
    mask = decomp.time >= window_t0
    if not mask.any():
        raise ValueError(
            f"steady window_t0={window_t0} selects no timesteps; the data time range is "
            f"[{decomp.time.min():.4g}, {decomp.time.max():.4g}]"
        )
    return mask


def added_mass_force(
    sum_u: NDArray[np.floating], rho_f: float = RHO
) -> NDArray[np.floating]:
    """Added-mass force from the ``SumU`` column = ``rho_f * SumU``.

    The ``SumU`` column is already ``(sum_u_new - sum_u_old)/dt`` (IAMReX
    ``WriteIBForceAndMoment``), so the added-mass force is simply ``rho_f * SumU``. This
    expression is locked to the solver source, NOT chosen to make the gate pass.
    """
    return rho_f * np.asarray(sum_u, dtype=float)


@dataclass(frozen=True)
class WingForceDecomposition:
    """Lab-frame van Veen force coefficients for the flapping wing, decomposed.

    Each ``cf_*`` is a per-timestep array. ``ib`` is the gated quantity; ``added_mass``
    (``rho_f*SumU``) and ``f_hydro`` (``rho_f*(SumU - ib_force)``, the 6-DOF momentum
    balance) are reported, not gated.
    """

    time: NDArray[np.floating]
    f_ref: float
    cf_x_ib: NDArray[np.floating]
    cf_z_ib: NDArray[np.floating]
    cf_x_added: NDArray[np.floating]
    cf_z_added: NDArray[np.floating]
    cf_x_hydro: NDArray[np.floating]
    cf_z_hydro: NDArray[np.floating]


def reconstruct_wing_forces(
    csv_path: str | Path,
    *,
    f_star: float,
    phi_amp_deg: float,
    rho_f: float = RHO,
) -> WingForceDecomposition:
    """Reconstruct lab-frame van Veen CF series from an IB-particle CSV (no correction factor).

    Args:
        csv_path: Path to the committed ``IB_Particle_*.csv``.
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        rho_f: Fluid density (``euler_fluid_rho``; 1.0 dimensionless here).

    Returns:
        A :class:`WingForceDecomposition` with ib / added-mass / 6-DOF hydrodynamic CF series.
    """
    df = pd.read_csv(csv_path)
    missing = [c for c in _REQUIRED_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"IB-particle CSV {csv_path} is missing required column(s) {missing}; "
            f"expected the IAMReX schema columns {list(_REQUIRED_CSV_COLUMNS)}"
        )
    f_ref = compute_force_reference(
        f_star, phi_amp_deg, R_GYRATION, SPAN, CHORD, RHO
    ).f_ref
    if f_ref <= 0:
        raise ValueError(
            f"f_ref must be positive (got {f_ref}); check f_star / phi_amp_deg for "
            "degenerate kinematics (e.g. f_star=0 or phi_amp_deg=0)."
        )
    ib_x, ib_z = df["Fx"].to_numpy(float), df["Fz"].to_numpy(float)
    am_x = added_mass_force(df["SumUx"].to_numpy(float), rho_f)
    am_z = added_mass_force(df["SumUz"].to_numpy(float), rho_f)
    # 6-DOF momentum balance: F_hydro = rho_f*(SumU - ib_force) = added_mass - rho_f*ib_force.
    fh_x = am_x - rho_f * ib_x
    fh_z = am_z - rho_f * ib_z
    return WingForceDecomposition(
        time=df["time"].to_numpy(float),
        f_ref=f_ref,
        cf_x_ib=ib_x / f_ref,
        cf_z_ib=ib_z / f_ref,
        cf_x_added=am_x / f_ref,
        cf_z_added=am_z / f_ref,
        cf_x_hydro=fh_x / f_ref,
        cf_z_hydro=fh_z / f_ref,
    )


def plausibility_gate(
    decomp: WingForceDecomposition, window_t0: float = STEADY_WINDOW_T0
) -> dict:
    """Grade the O(1) magnitude plausibility gate on ``ib_force`` ALONE over the steady window.

    The verdict is a function of ``ib_force`` only — the added-mass term cannot flip it. The
    rotation-invariant resultant ``|CF| = sqrt(CF_x^2 + CF_z^2)`` is reported as the
    frame-honest companion.
    """
    lo, hi = VAN_VEEN_BAND
    m = _steady_mask(decomp, window_t0)
    max_cf_x = float(np.abs(decomp.cf_x_ib[m]).max())
    max_cf_z = float(np.abs(decomp.cf_z_ib[m]).max())
    resultant = np.sqrt(decomp.cf_x_ib[m] ** 2 + decomp.cf_z_ib[m] ** 2)
    return {
        "max_cf_x": max_cf_x,
        "max_cf_z": max_cf_z,
        "cf_x_in_band": lo <= max_cf_x <= hi,
        "cf_z_in_band": lo <= max_cf_z <= hi,
        "max_resultant": float(resultant.max()),
        "cf_x_ceiling_margin": hi - max_cf_x,  # tighter edge near the transient cutoff
        "cf_z_floor_margin": max_cf_z - lo,
        "window_t0": window_t0,
    }


def added_mass_fraction(
    decomp: WingForceDecomposition, window_t0: float = STEADY_WINDOW_T0
) -> dict:
    """RMS fraction of the added-mass term relative to ``ib_force`` over the steady window."""
    m = _steady_mask(decomp, window_t0)

    def frac(added, ib):
        return float(np.sqrt(np.mean(added[m] ** 2)) / np.sqrt(np.mean(ib[m] ** 2)))

    return {
        "stroke": frac(decomp.cf_x_added, decomp.cf_x_ib),
        "lift": frac(decomp.cf_z_added, decomp.cf_z_ib),
    }
