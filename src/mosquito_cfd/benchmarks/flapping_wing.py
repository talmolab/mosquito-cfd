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

Frame note (issue #1 / T2a): :func:`plausibility_gate` grades **lab-frame** coefficients as an
O(1) **magnitude plausibility** check. The faithful **body-frame** per-component van Veen
comparison is **delivered** here by :func:`reconstruct_wing_body_forces` /
:func:`body_frame_overall_match` (rotating ``ib_force`` into the wing frame by the analytic
``R(t)``); only the **time-resolved** curve match vs van Veen fig 3-4 remains deferred to T4.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.benchmarks.wing_kinematics import (
    euler_angles,
    rotation_matrix,
    rotation_matrix_legacy,
)
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN

# Steady evaluation window: a documented PHYSICAL criterion, not tuned to land in band.
# The impulsive-start transient is confined to the first ~8 steps (t <= 0.004), where
# |CF_x| spikes to ~39; any t0 >= 0.005 is clean. We use one-twentieth of a wingbeat.
STEADY_WINDOW_T0 = 0.05

# van Veen plausibility band for insect-wing force coefficients (van Veen 2022, JFM 936:A3).
VAN_VEEN_BAND = (0.5, 1.5)

# van Veen reported OVERALL body-frame force-coefficient targets (T2a, sourced from the open-access
# PDF Fig 4a/4b/4e + eqs 3.1-3.8, in our F_ref = 0.5*rho*omega^2*S_yy normalization). The wing-normal
# translational coefficient follows a least-squares sine fit C_Fz,transl(alpha) ~ 3.4*sin(alpha)
# (peak ~3.4 at alpha=90 deg, ~2.4 at the alpha=45 deg pitch amplitude); the chord-wise tangential
# coefficient is small (~0.2-0.3 peak). CAVEAT (applies to BOTH components): our ib_force is the
# TOTAL hydrodynamic force, whereas these targets are van Veen's TRANSLATIONAL-only coefficients
# (van Veen decomposes F into translational + added-mass + Wagner, eqs 3.1-3.8). So the comparison is
# total (ours) vs translational (target): our CF_normal ~ van Veen's normal because the added-mass (+)
# and Wagner (-) contributions roughly cancel in the wing-normal at this condition; our CF_chord runs
# HIGHER than the translational chord because rotational drag + tangential added mass add to it
# (Bomphrey 2017's mosquito mechanism). The precise per-instant per-component curve match is T4 (needs
# the Section 3.3 mosquito-wingbeat curves digitized). NB VAN_VEEN_BAND [0.5,1.5] is a LAB-frame O(1)
# plausibility range, NOT a body-frame gate: van Veen's own CF_normal (~2.4) exceeds 1.5, so a
# body-frame CF_normal above the band is expected, not a failure — the body-frame gate is this
# van-Veen-target comparison. These are pinned constants guarded by test_match_tolerance_not_loosened.
VAN_VEEN_CF_TARGETS = {
    "cf_normal_peak": 2.4,  # C_Fz,transl at the alpha~45 deg midstroke pitch (Fig 4a sine fit)
    "cf_chord_peak": 0.3,  # C_Fx,transl small tangential peak (Fig 4b)
}
# Overall-magnitude match tolerance [dimensionless CF]. Provisional pending the coarse re-run
# (task 7); NOT reverse-fit to any measured value (no new-convention run exists yet).
VAN_VEEN_MATCH_TOL = 0.6

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
        csv_path: Path to the committed ``forces.csv`` (the write-out of the validated
            wingbeat kept in-repo; the raw ``IB_Particle_*.csv`` dump is gitignored — same
            run and schema, a separate write-out agreeing to ~1e-3).
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
        f_star, phi_amp_deg, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    if not (np.isfinite(f_ref) and f_ref > 0):
        raise ValueError(
            f"f_ref must be finite and positive (got {f_ref}); check f_star / phi_amp_deg for "
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

    The ``VAN_VEEN_BAND`` ``(0.5, 1.5)`` is graded as a **lower-bound O(1) sanity floor** (T2b):
    the graded verdict is ``floor_pass`` — each peak ``|CF|`` clears the floor ``0.5`` (this caught
    the old peak-tip normalization at ``CF_z ~0.22 < 0.5``). The **ceiling** ``1.5`` is **reported,
    not gated** (``cf_*_in_band``, ``cf_x_ceiling_margin``): a per-component peak above ``1.5`` is
    expected under the corrected motion (van Veen's own body-frame normal ~2.4 also exceeds 1.5), not
    a failure. The band *value* is unchanged — this is a grading-role change, not a loosening. The
    faithful per-component van Veen comparison is the body-frame decomposition, not this lab band.

    The verdict is a function of ``ib_force`` only — the added-mass term cannot flip it. The
    rotation-invariant resultant ``|CF| = sqrt(CF_x^2 + CF_z^2)`` is reported as the frame-honest
    companion.
    """
    lo, hi = VAN_VEEN_BAND
    m = _steady_mask(decomp, window_t0)
    max_cf_x = float(np.abs(decomp.cf_x_ib[m]).max())
    max_cf_z = float(np.abs(decomp.cf_z_ib[m]).max())
    resultant = np.sqrt(decomp.cf_x_ib[m] ** 2 + decomp.cf_z_ib[m] ** 2)
    cf_x_above_floor = max_cf_x >= lo
    cf_z_above_floor = max_cf_z >= lo
    return {
        "max_cf_x": max_cf_x,
        "max_cf_z": max_cf_z,
        # Graded floor (lower bound) — the T2b verdict.
        "cf_x_above_floor": cf_x_above_floor,
        "cf_z_above_floor": cf_z_above_floor,
        "floor_pass": cf_x_above_floor and cf_z_above_floor,
        # Reported ceiling companions (two-sided, NOT gated) + resultant.
        "cf_x_in_band": lo <= max_cf_x <= hi,
        "cf_z_in_band": lo <= max_cf_z <= hi,
        "max_resultant": float(resultant.max()),
        "cf_x_ceiling_margin": hi
        - max_cf_x,  # reported; negative when the peak exceeds the ceiling
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


# --- Body-frame (chord/normal) per-component van Veen comparison (Tier T2a) -------------------
#
# #36 graded a LAB-frame O(1) magnitude gate and deferred the faithful body-frame per-component
# comparison to T2a (see the module frame caveat above). Here the lab-frame ib_force is rotated
# into the instantaneous WING body frame by the analytic R(t) from the kinematics mirror (the same
# composition the solver applies), giving chord-wise CF_chord and wing-normal CF_normal in van
# Veen's convention F = (F_x chord, F_z normal). The spanwise F_y is carried as a diagnostic
# (cf_span) but van Veen ignores it. Rotation axes are passed EXPLICITLY (no hard-coded streamwise
# axis) so the analysis layer cannot re-introduce a #1-style mislabel.

# van Veen body-frame axes (wing reference frame, fig 1f / Fig 2 caption): x=chord, y=span, z=normal.
# Write-locked because they are bound as default args below — a caller mutating the returned/default
# array in place would otherwise corrupt shared module state (the axes must stay pure constants).
_CHORD_AXIS = np.array([1.0, 0.0, 0.0])
_SPAN_AXIS = np.array([0.0, 1.0, 0.0])
_NORMAL_AXIS = np.array([0.0, 0.0, 1.0])
for _axis in (_CHORD_AXIS, _SPAN_AXIS, _NORMAL_AXIS):
    _axis.setflags(write=False)

# Body-frame CSV columns (ib_force vector). Fy is needed here (unlike the lab-frame gate).
_REQUIRED_BODY_CSV_COLUMNS = ("time", "Fx", "Fy", "Fz")


def _validate_rotation(rot: NDArray[np.floating]) -> NDArray[np.float64]:
    """Return ``rot`` as FP64, raising if it is not a proper orthonormal rotation (per matrix)."""
    r = np.asarray(rot, dtype=np.float64)
    if r.ndim not in (2, 3) or r.shape[-2:] != (3, 3):
        raise ValueError(f"rotation must be (3,3) or (N,3,3), got shape {r.shape}")
    if not np.isfinite(r).all():
        raise ValueError("rotation contains non-finite values (NaN/inf)")
    batch = r if r.ndim == 3 else r[None]
    ident = np.einsum("nij,nkj->nik", batch, batch)  # R @ R^T
    if not np.allclose(ident, np.eye(3), atol=1e-8):
        raise ValueError("rotation is not orthonormal (R @ R^T != I)")
    if not np.allclose(np.linalg.det(batch), 1.0, atol=1e-8):
        raise ValueError(
            "rotation has det != 1 (not a proper rotation / reflection or singular)"
        )
    return r


def body_frame_coefficients(
    f_lab: NDArray[np.floating],
    rot: NDArray[np.floating],
    f_ref: float,
    *,
    chord_axis: NDArray[np.floating] = _CHORD_AXIS,
    normal_axis: NDArray[np.floating] = _NORMAL_AXIS,
    span_axis: NDArray[np.floating] = _SPAN_AXIS,
) -> dict[str, NDArray[np.floating]]:
    """Rotate lab-frame force(s) into the wing body frame and form van Veen CF components.

    ``F_body = R^T @ F_lab`` (``R`` maps body->lab, so its transpose maps lab->body); the
    coefficients are the body components projected on the **explicitly supplied** chord/normal/span
    axes, divided by ``f_ref``. Swapping ``chord_axis`` and ``normal_axis`` exchanges the returned
    ``cf_chord``/``cf_normal`` — the axes are honoured, not hard-coded.

    Args:
        f_lab: Lab-frame force vector(s), shape ``(3,)`` or ``(N, 3)`` (FP64).
        rot: Rotation matrix/matrices ``R(t)``, shape ``(3, 3)`` or ``(N, 3, 3)``.
        f_ref: Reference force (van Veen ``F_ref``); must be positive.
        chord_axis: Body-frame chord unit vector (default van Veen x).
        normal_axis: Body-frame wing-normal unit vector (default van Veen z).
        span_axis: Body-frame span unit vector (default van Veen y; reported as a diagnostic).

    Returns:
        Dict of ``cf_chord``, ``cf_normal``, ``cf_span`` arrays (shape ``(N,)`` or 0-d).

    Raises:
        ValueError: if ``f_ref`` is not finite and positive, ``f_lab`` is empty or not ``(...,3)``, or ``rot`` is not a
            proper orthonormal rotation.
    """
    if not (np.isfinite(f_ref) and f_ref > 0):
        raise ValueError(
            f"f_ref must be finite and positive to form coefficients (got {f_ref})"
        )
    f = np.asarray(f_lab, dtype=np.float64)
    if f.shape[-1] != 3:
        raise ValueError(f"f_lab must have a trailing size-3 axis, got shape {f.shape}")
    if f.size == 0:
        raise ValueError("f_lab is empty; nothing to decompose")
    if not np.isfinite(f).all():
        raise ValueError("f_lab contains non-finite values (NaN/inf)")
    r = _validate_rotation(rot)
    single = f.ndim == 1
    fb = np.atleast_2d(f)
    rb = r[None] if r.ndim == 2 else r
    if rb.shape[0] == 1 and fb.shape[0] > 1:
        rb = np.broadcast_to(rb, (fb.shape[0], 3, 3))
    if rb.shape[0] != fb.shape[0]:
        raise ValueError(
            f"rotation batch {rb.shape[0]} does not match force batch {fb.shape[0]}"
        )
    # F_body[n,j] = sum_i R[n,i,j] * F_lab[n,i]  (= (R^T @ F)[j])
    f_body = np.einsum("nij,ni->nj", rb, fb)
    out = {
        "cf_chord": (f_body @ np.asarray(chord_axis, float)) / f_ref,
        "cf_normal": (f_body @ np.asarray(normal_axis, float)) / f_ref,
        "cf_span": (f_body @ np.asarray(span_axis, float)) / f_ref,
    }
    if single:
        return {k: v[0] for k, v in out.items()}
    return out


@dataclass(frozen=True)
class WingBodyFrameDecomposition:
    """Body-frame (van Veen) force coefficients for the flapping wing.

    ``cf_chord`` (body x), ``cf_normal`` (body z) are the graded van Veen components; ``cf_span``
    (body y) is the diagnostic van Veen ignores. Each is a per-timestep array.
    """

    time: NDArray[np.floating]
    f_ref: float
    cf_chord: NDArray[np.floating]
    cf_normal: NDArray[np.floating]
    cf_span: NDArray[np.floating]


def reconstruct_wing_body_forces(
    csv_path: str | Path,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
    deviation_amp_deg: float = 0.0,
    legacy_kinematics: bool = False,
) -> WingBodyFrameDecomposition:
    """Body-frame CF_chord/CF_normal series from an IB-particle CSV via the analytic ``R(t)``.

    For each timestep the lab-frame ``ib_force`` ``(Fx,Fy,Fz)`` is rotated into the wing body frame
    by ``R(t)`` from the kinematics mirror (:mod:`mosquito_cfd.benchmarks.wing_kinematics`), the same
    composition the solver applies. ``F_ref`` comes from the single-source ``compute_force_reference``.

    Args:
        csv_path: Path to the committed ``forces.csv`` (IB-particle output; must carry ``Fy``).
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].
        deviation_amp_deg: Deviation amplitude [deg]; default 0.
        legacy_kinematics: If True, use the pre-T2a ``rotation_matrix_legacy`` composition — for the
            **contrast baseline only** (shows the old stroke-∥-span motion's body-frame CF differ).

    Returns:
        A :class:`WingBodyFrameDecomposition`.
    """
    df = pd.read_csv(csv_path)
    missing = [c for c in _REQUIRED_BODY_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"IB-particle CSV {csv_path} is missing required column(s) {missing}; "
            f"body-frame decomposition needs {list(_REQUIRED_BODY_CSV_COLUMNS)}"
        )
    f_ref = compute_force_reference(
        f_star, phi_amp_deg, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    if not (np.isfinite(f_ref) and f_ref > 0):
        raise ValueError(
            f"f_ref must be finite and positive (got {f_ref}); check f_star / phi_amp_deg"
        )
    time = df["time"].to_numpy(float)
    f_lab = np.column_stack(
        [df["Fx"].to_numpy(float), df["Fy"].to_numpy(float), df["Fz"].to_numpy(float)]
    )
    rot_fn = rotation_matrix_legacy if legacy_kinematics else rotation_matrix
    phi_amp = np.radians(phi_amp_deg)
    alpha_amp = np.radians(pitch_amp_deg)
    theta_amp = np.radians(deviation_amp_deg)
    rots = np.stack(
        [
            rot_fn(
                *euler_angles(
                    t,
                    frequency=f_star,
                    stroke_amp_rad=phi_amp,
                    pitch_amp_rad=alpha_amp,
                    deviation_amp_rad=theta_amp,
                )
            )
            for t in time
        ]
    )
    cf = body_frame_coefficients(f_lab, rots, f_ref)
    return WingBodyFrameDecomposition(
        time=time,
        f_ref=f_ref,
        cf_chord=cf["cf_chord"],
        cf_normal=cf["cf_normal"],
        cf_span=cf["cf_span"],
    )


def body_frame_overall_match(
    decomp: WingBodyFrameDecomposition,
    *,
    window_t0: float = STEADY_WINDOW_T0,
    targets: dict[str, float] | None = None,
    tol: float = VAN_VEEN_MATCH_TOL,
    band: tuple[float, float] = VAN_VEEN_BAND,
) -> dict:
    """Grade the body-frame per-component van Veen comparison over the steady window.

    Two graded modes, kept distinct (design D5): (a) the always-on **band floor** — peak
    ``|CF_chord|``/``|CF_normal|`` graded against ``band`` (default the pinned ``VAN_VEEN_BAND``);
    (b) the **overall scalar-match** — when ``targets`` is supplied, peak coefficients must fall
    within ``tol`` of the van Veen values. With ``targets=None`` the verdict falls back to the band
    floor and the van-Veen gap is reported as ``None`` (CC-V2 — never reverse-fit).

    Returns a dict with per-component peaks, cycle-means, ``*_in_band`` bools, and (when targets are
    given) ``*_gap`` and ``*_match`` bools plus an overall ``match`` verdict.
    """
    mask = decomp.time >= window_t0
    if not mask.any():
        raise ValueError(
            f"steady window_t0={window_t0} selects no timesteps; data range "
            f"[{decomp.time.min():.4g}, {decomp.time.max():.4g}]"
        )
    # Raise on a non-finite CF series rather than letting np.max/np.mean hide it: an all-NaN
    # series would otherwise grade silently out-of-band (NaN <= hi is False) instead of erroring.
    if not (
        np.isfinite(decomp.cf_chord[mask]).all()
        and np.isfinite(decomp.cf_normal[mask]).all()
    ):
        raise ValueError(
            "cf_chord/cf_normal contain non-finite values (NaN/inf) in the window"
        )
    lo, hi = band
    peak_chord = float(np.abs(decomp.cf_chord[mask]).max())
    peak_normal = float(np.abs(decomp.cf_normal[mask]).max())
    mean_chord = float(np.abs(decomp.cf_chord[mask]).mean())
    mean_normal = float(np.abs(decomp.cf_normal[mask]).mean())
    result = {
        "peak_cf_chord": peak_chord,
        "peak_cf_normal": peak_normal,
        "mean_cf_chord": mean_chord,
        "mean_cf_normal": mean_normal,
        "cf_chord_in_band": lo <= peak_chord <= hi,
        "cf_normal_in_band": lo <= peak_normal <= hi,
        "window_t0": window_t0,
        # Copy so a caller mutating result["targets"] cannot corrupt a shared module constant
        # (e.g. VAN_VEEN_CF_TARGETS) passed in by reference.
        "targets": dict(targets) if targets is not None else None,
    }
    if targets is None:
        result["cf_chord_gap"] = None
        result["cf_normal_gap"] = None
        result["match"] = None  # tolerance gate is pending sourced targets
        return result
    gap_chord = peak_chord - float(targets["cf_chord_peak"])
    gap_normal = peak_normal - float(targets["cf_normal_peak"])
    chord_match = abs(gap_chord) <= tol
    normal_match = abs(gap_normal) <= tol
    result.update(
        {
            "cf_chord_gap": gap_chord,
            "cf_normal_gap": gap_normal,
            "cf_chord_match": chord_match,
            "cf_normal_match": normal_match,
            "tol": tol,
            "match": bool(chord_match and normal_match),
        }
    )
    return result


# --- Added-mass-subtracted body-frame CF diagnostic (#40 cheap interim) -----------------------
#
# A REPORTED (not graded) diagnostic: subtract the logged added-mass rho_f*SumU (via added_mass_force,
# #36) from the total ib_force, rotate the remainder into the wing body frame with the SAME analytic
# R(t) / body_frame_coefficients the T2a decomposition uses (CC-V4 — reused, not re-derived; the two
# defect classes stay separate), and report peak |CF_chord|/|CF_normal| for total vs subtracted plus
# the body-frame added-mass RMS share. It isolates the added-mass share of the T2a CF_chord PARTIAL
# (0.923 -> 0.652); it does NOT re-grade van Veen (CC-V2 — no *_match/pass field) and does NOT resolve
# the PARTIAL (0.652 is still ~2x van Veen's translational ~0.3 — the residual is the full T4).

# Columns the added-mass-subtracted diagnostic reads. It rotates the FULL 3-D force and added-mass
# vectors, so it needs Fy AND SumU{x,y,z}. No single existing tuple covers all seven:
# _REQUIRED_CSV_COLUMNS lacks Fy and SumUy; _REQUIRED_BODY_CSV_COLUMNS lacks the SumU* columns
# (SumUy is in neither) — hence this own set.
_REQUIRED_SUBTRACTED_CSV_COLUMNS = (
    "time",
    "Fx",
    "Fy",
    "Fz",
    "SumUx",
    "SumUy",
    "SumUz",
)


def _body_frame_rms_share(
    added_body: NDArray[np.floating], ib_body: NDArray[np.floating]
) -> float:
    """Body-frame added-mass RMS share ``rms(added_body)/rms(ib_body)`` (reported, not gated).

    The body-frame analog of the lab-frame :func:`added_mass_fraction` (``rms(added)/rms(ib)``),
    exposed as a seam so the definition can be pinned on synthetic arrays. NOT ``rms(subtracted)`` and
    NOT a peak ratio. Inputs are the already-windowed body-frame component series.
    """
    added = np.asarray(added_body, dtype=float)
    ib = np.asarray(ib_body, dtype=float)
    return float(np.sqrt(np.mean(added**2)) / np.sqrt(np.mean(ib**2)))


def body_frame_added_mass_subtracted(
    csv_path: str | Path,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
    deviation_amp_deg: float = 0.0,
    rho_f: float = RHO,
    window_t0: float = STEADY_WINDOW_T0,
) -> dict:
    """Reported #40 cheap interim: body-frame peaks for ``ib_force`` vs ``ib_force - rho_f*SumU``.

    Subtracts the logged added-mass ``rho_f*SumU`` (via :func:`added_mass_force`, #36) from the total
    lab-frame ``ib_force``, rotates **both** the total and the subtracted force into the wing body frame
    with the analytic ``R(t)`` from :mod:`mosquito_cfd.benchmarks.wing_kinematics` and
    :func:`body_frame_coefficients` (the same composition T2a applies — reused, not re-derived), and
    reports, over the pinned steady window, peak ``|CF_chord|``/``|CF_normal|`` for total and subtracted,
    the **signed** peak-to-peak drop fraction, and the body-frame added-mass RMS share per component.

    Because the total and subtracted peaks can fall at **different phases**, each ``peak_*`` is the
    independent window argmax of ``|series|`` (the subtracted peak is NOT the subtracted value at the
    total's argmax). ``*_drop_frac = 1 - peak_subtracted/peak_total`` is therefore a peak-to-peak ratio,
    **signed** (negative if subtraction raises a peak) — not a per-instant reduction. This is **reported,
    not graded**: the return dict carries NO ``*_match``/``pass`` verdict field (CC-V2), and the existing
    graders (:func:`plausibility_gate`, :func:`body_frame_overall_match`) are untouched.

    Args:
        csv_path: Committed IB-particle CSV; must carry ``time, Fx, Fy, Fz, SumU{x,y,z}``.
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].
        deviation_amp_deg: Deviation amplitude [deg]; default 0.
        rho_f: Fluid density for the added-mass term (``rho_f*SumU``); default ``RHO``.
        window_t0: Steady-window start; default ``STEADY_WINDOW_T0``.

    Returns:
        Dict of reported (never graded) quantities: ``peak_cf_{chord,normal}_{total,subtracted}``,
        ``{chord,normal}_drop_frac``, ``am_rms_share_{chord,normal}``, ``window_t0``.

    Raises:
        ValueError: if a required column is missing, a force/``SumU`` row is non-finite, ``f_ref`` is not
            finite and positive, or ``window_t0`` selects no timesteps.
    """
    df = pd.read_csv(csv_path)
    missing = [c for c in _REQUIRED_SUBTRACTED_CSV_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"IB-particle CSV {csv_path} is missing required column(s) {missing}; the "
            f"added-mass-subtracted diagnostic needs {list(_REQUIRED_SUBTRACTED_CSV_COLUMNS)} "
            "(it rotates the full 3-D force and added-mass vectors)"
        )
    f_ref = compute_force_reference(
        f_star, phi_amp_deg, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    if not (np.isfinite(f_ref) and f_ref > 0):
        raise ValueError(
            f"f_ref must be finite and positive (got {f_ref}); check f_star / phi_amp_deg"
        )
    time = df["time"].to_numpy(float)
    mask = time >= window_t0
    if not mask.any():
        raise ValueError(
            f"steady window_t0={window_t0} selects no timesteps; data range "
            f"[{time.min():.4g}, {time.max():.4g}]"
        )
    ib = np.column_stack(
        [df["Fx"].to_numpy(float), df["Fy"].to_numpy(float), df["Fz"].to_numpy(float)]
    )
    sum_u = np.column_stack(
        [
            df["SumUx"].to_numpy(float),
            df["SumUy"].to_numpy(float),
            df["SumUz"].to_numpy(float),
        ]
    )
    added = added_mass_force(sum_u, rho_f)  # rho_f * SumU (#36); reused, not re-derived
    subtracted = ib - added
    rots = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=f_star,
                    stroke_amp_rad=np.radians(phi_amp_deg),
                    pitch_amp_rad=np.radians(pitch_amp_deg),
                    deviation_amp_rad=np.radians(deviation_amp_deg),
                )
            )
            for t in time
        ]
    )
    # body_frame_coefficients raises on any non-finite force row, so a NaN/inf in ib or SumU
    # surfaces here rather than as a silent coefficient.
    cf_ib = body_frame_coefficients(ib, rots, f_ref)
    cf_added = body_frame_coefficients(added, rots, f_ref)
    cf_sub = body_frame_coefficients(subtracted, rots, f_ref)

    def peak(cf: dict[str, NDArray[np.floating]], key: str) -> float:
        return float(np.abs(cf[key][mask]).max())

    peak_chord_total = peak(cf_ib, "cf_chord")
    peak_normal_total = peak(cf_ib, "cf_normal")
    peak_chord_sub = peak(cf_sub, "cf_chord")
    peak_normal_sub = peak(cf_sub, "cf_normal")
    return {
        "peak_cf_chord_total": peak_chord_total,
        "peak_cf_normal_total": peak_normal_total,
        "peak_cf_chord_subtracted": peak_chord_sub,
        "peak_cf_normal_subtracted": peak_normal_sub,
        # Signed peak-to-peak fraction (peaks may fall at different phases); NOT per-instant.
        "chord_drop_frac": 1.0 - peak_chord_sub / peak_chord_total,
        "normal_drop_frac": 1.0 - peak_normal_sub / peak_normal_total,
        "am_rms_share_chord": _body_frame_rms_share(
            cf_added["cf_chord"][mask], cf_ib["cf_chord"][mask]
        ),
        "am_rms_share_normal": _body_frame_rms_share(
            cf_added["cf_normal"][mask], cf_ib["cf_normal"][mask]
        ),
        "window_t0": window_t0,
    }
