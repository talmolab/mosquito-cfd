"""Cluster-free tests for the body-frame (chord/normal) van Veen comparison (Tier T2a).

Covers the analytic lab->body rotation (explicit axes, no #1-style mislabel), the overall
scalar-match grader (both directions + CC-V2 band-floor fallback), the pinned not-loosened
constants, and the old-vs-new contrast on the committed ``forces.csv``. Pure numpy/pandas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    VAN_VEEN_BAND,
    VAN_VEEN_CF_TARGETS,
    VAN_VEEN_MATCH_TOL,
    WingBodyFrameDecomposition,
    added_mass_force,
    body_frame_added_mass_subtracted,
    body_frame_coefficients,
    body_frame_overall_match,
    reconstruct_wing_body_forces,
)
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN

_FORCES_CSV = Path("examples/flapping_wing/forces.csv")
_F_REF = 200.27


def test_known_R_pure_chord_and_normal_and_axis_swap():
    """A pure chord (then normal) lab force decodes cleanly; swapping axes exchanges the outputs."""
    r = rotation_matrix(0.3, 0.6, 0.9)
    fc, fn = 42.0, 71.0
    # Pure chord-directed lab force = R @ (Fc,0,0); expect cf_chord=Fc/f_ref, cf_normal~0.
    f_lab_chord = r @ np.array([fc, 0.0, 0.0])
    out = body_frame_coefficients(f_lab_chord, r, _F_REF)
    assert out["cf_chord"] == pytest.approx(fc / _F_REF, abs=1e-12)
    assert out["cf_normal"] == pytest.approx(0.0, abs=1e-12)
    assert out["cf_span"] == pytest.approx(0.0, abs=1e-12)
    # Pure normal-directed lab force.
    f_lab_norm = r @ np.array([0.0, 0.0, fn])
    out_n = body_frame_coefficients(f_lab_norm, r, _F_REF)
    assert out_n["cf_normal"] == pytest.approx(fn / _F_REF, abs=1e-12)
    assert out_n["cf_chord"] == pytest.approx(0.0, abs=1e-12)
    # Swapping the chord/normal axes exchanges the results (axes are honoured, not hard-coded).
    swapped = body_frame_coefficients(
        f_lab_chord,
        r,
        _F_REF,
        chord_axis=np.array([0.0, 0.0, 1.0]),
        normal_axis=np.array([1.0, 0.0, 0.0]),
    )
    assert swapped["cf_normal"] == pytest.approx(fc / _F_REF, abs=1e-12)
    assert swapped["cf_chord"] == pytest.approx(0.0, abs=1e-12)


def test_batched_R_matches_per_timestep():
    """A batch of rotations decomposes each force with its own R(t) (incl. nonzero deviation θ)."""
    # Nonzero θ on every element exercises the full 3-angle Rz·Ry·Rx composition, not just Rz·Ry.
    rots = np.stack(
        [rotation_matrix(0.1 * k, 0.2 * k, 0.05 * (k + 1)) for k in range(4)]
    )
    f_lab = np.array([[1.0, 2.0, 3.0]] * 4)
    out = body_frame_coefficients(f_lab, rots, _F_REF)
    for k in range(4):
        single = body_frame_coefficients(f_lab[k], rots[k], _F_REF)
        assert out["cf_chord"][k] == pytest.approx(single["cf_chord"])
        assert out["cf_normal"][k] == pytest.approx(single["cf_normal"])


def test_empty_series_and_bad_rotation_raise():
    r = rotation_matrix(0.2, 0.3, 0.1)
    with pytest.raises(ValueError, match="empty"):
        body_frame_coefficients(np.empty((0, 3)), r, _F_REF)
    with pytest.raises(ValueError, match="positive"):
        body_frame_coefficients(np.array([1.0, 0.0, 0.0]), r, 0.0)
    # Non-orthonormal / det!=1 rotation (2*I) must raise, not emit garbage CFs.
    with pytest.raises(ValueError):
        body_frame_coefficients(np.array([1.0, 0.0, 0.0]), 2.0 * np.eye(3), _F_REF)
    # A reflection (det = -1) must also raise.
    reflect = np.diag([1.0, 1.0, -1.0])
    with pytest.raises(ValueError):
        body_frame_coefficients(np.array([1.0, 0.0, 0.0]), reflect, _F_REF)


def test_nan_or_inf_force_raises_not_silent():
    """A NaN/inf lab force must raise (NaN in -> explicit error), never produce a silent CF.

    Guards the behavioural-correctness contract: a corrupt IB-force row surfaces loudly rather
    than propagating a NaN coefficient into the graded peak/mean (which np.nanmax would hide).
    """
    r = rotation_matrix(0.2, 0.3, 0.1)
    with pytest.raises(ValueError, match="non-finite"):
        body_frame_coefficients(np.array([1.0, np.nan, 0.0]), r, _F_REF)
    with pytest.raises(ValueError, match="non-finite"):
        body_frame_coefficients(np.array([np.inf, 0.0, 0.0]), r, _F_REF)
    # A NaN buried in a batch is caught too (not just a leading scalar).
    batch = np.array([[1.0, 0.0, 0.0], [0.0, np.nan, 0.0]])
    with pytest.raises(ValueError, match="non-finite"):
        body_frame_coefficients(batch, np.stack([r, r]), _F_REF)


_NEWCONV_CSV = Path("examples/flapping_wing/forces_t2a_newconv.csv")
_IB_PARTICLE_29_COLS = (
    "iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,"
    "Fcpx,Fcpy,Fcpz,Tcpx,Tcpy,Tcpz,SumUx,SumUy,SumUz,SumTx,SumTy,SumTz"
).split(",")


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_newconv_csv_matches_ib_particle_contract():
    """forces_t2a_newconv.csv keeps the 29-column IB_Particle schema the decomposition depends on.

    The body-frame decomposition reads Fx/Fy/Fz/time by name; a silent column-order or -name change
    in the solver write-out would break the T2a gate. Pin the exact schema (order + names) and
    confirm the decomposition consumes it end-to-end.
    """
    import pandas as pd

    df = pd.read_csv(_NEWCONV_CSV)
    assert list(df.columns) == _IB_PARTICLE_29_COLS
    assert len(df) > 0  # not an empty write-out
    # The decomposition reads this exact file without a missing-column error.
    decomp = reconstruct_wing_body_forces(
        _NEWCONV_CSV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    assert decomp.cf_chord.shape == decomp.cf_normal.shape == (len(df),)
    assert np.isfinite(decomp.cf_normal).all()


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_committed_run_verdict_is_partial_normal_passes_chord_fails():
    """Lock the HONEST per-component verdict on the committed T2a run: normal passes, chord fails.

    RESULTS.md reports the body-frame comparison as PARTIAL. Pin that to the grader's own output so
    the doc wording cannot drift away from what the code computes: on `forces_t2a_newconv.csv`, graded
    against `VAN_VEEN_CF_TARGETS` (normal 2.4, chord 0.3) at tol 0.6, CF_normal is within tol
    (2.61 → gap ~0.2) but CF_chord is NOT (0.92 → gap ~0.62 > 0.6), so the overall match is False.
    """
    decomp = reconstruct_wing_body_forces(
        _NEWCONV_CSV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    res = body_frame_overall_match(decomp, targets=VAN_VEEN_CF_TARGETS)
    assert res["cf_normal_match"] is True
    assert res["cf_chord_match"] is False  # ~3x target — the honest PARTIAL verdict
    assert res["match"] is False
    assert (
        res["cf_chord_gap"] > VAN_VEEN_MATCH_TOL
    )  # gap exceeds tol, not a rounding artifact


def test_grader_raises_on_all_nan_cf_series():
    """An all-NaN CF series raises (not silently graded out-of-band via NaN comparisons)."""
    t = np.linspace(0.0, 1.0, 50)
    nan_decomp = WingBodyFrameDecomposition(
        time=t,
        f_ref=_F_REF,
        cf_chord=np.full_like(t, np.nan),
        cf_normal=np.cos(2 * np.pi * t),
        cf_span=np.zeros_like(t),
    )
    with pytest.raises(ValueError, match="non-finite"):
        body_frame_overall_match(nan_decomp, targets=None)


def test_nonfinite_f_ref_raises_not_silent():
    """f_ref = NaN/inf must raise (NaN <= 0 is False, so a bare `<= 0` guard would leak it)."""
    r = rotation_matrix(0.2, 0.3, 0.1)
    f = np.array([1.0, 0.0, 0.0])
    for bad in (np.nan, np.inf):
        with pytest.raises(ValueError, match="finite and positive"):
            body_frame_coefficients(f, r, bad)


def test_default_body_axes_are_write_locked():
    """The module-level default axis constants are immutable — a caller cannot corrupt shared state."""
    from mosquito_cfd.benchmarks import flapping_wing as fw

    for axis in (fw._CHORD_AXIS, fw._SPAN_AXIS, fw._NORMAL_AXIS):
        assert axis.flags.writeable is False
        with pytest.raises(ValueError):
            axis[0] = 999.0


def _synthetic_decomp(
    peak_chord: float, peak_normal: float
) -> WingBodyFrameDecomposition:
    t = np.linspace(0.0, 1.0, 200)
    # Steady window t>=0.05; scale sinusoids so the peak |CF| equals the requested values.
    cf_chord = peak_chord * np.sin(2 * np.pi * t)
    cf_normal = peak_normal * np.cos(2 * np.pi * t)
    return WingBodyFrameDecomposition(
        time=t,
        f_ref=_F_REF,
        cf_chord=cf_chord,
        cf_normal=cf_normal,
        cf_span=0.3 * cf_chord,
    )


def test_overall_scalar_match_passes_within_fails_outside():
    """Injected targets: verdict passes when peaks are within tol, fails when outside (both ways)."""
    targets = {"cf_chord_peak": 0.3, "cf_normal_peak": 2.4}
    within = body_frame_overall_match(
        _synthetic_decomp(0.3, 2.4), targets=targets, tol=0.6
    )
    assert within["match"] is True
    assert within["cf_normal_gap"] == pytest.approx(0.0, abs=1e-9)
    # Normal peak far outside tol -> fail.
    outside = body_frame_overall_match(
        _synthetic_decomp(0.3, 5.0), targets=targets, tol=0.6
    )
    assert outside["match"] is False
    assert outside["cf_normal_match"] is False


def test_overall_match_falls_back_to_band_floor_when_targets_absent():
    """CC-V2: with targets=None the tolerance verdict is None (pending) and the floor still grades."""
    res = body_frame_overall_match(_synthetic_decomp(1.0, 1.2), targets=None)
    assert res["match"] is None  # tolerance gate pending sourced targets
    assert res["cf_chord_gap"] is None and res["cf_normal_gap"] is None
    # The band floor is still evaluated (both peaks in [0.5,1.5] here).
    assert res["cf_chord_in_band"] is True
    assert res["cf_normal_in_band"] is True


def test_body_frame_grader_rejects_loosened_band():
    """A loosened band would spuriously pass an out-of-band peak; the pinned band does not."""
    decomp = _synthetic_decomp(0.3, 2.4)  # normal peak 2.4 is ABOVE the [0.5,1.5] band
    pinned = body_frame_overall_match(decomp, targets=None, band=VAN_VEEN_BAND)
    assert pinned["cf_normal_in_band"] is False
    loosened = body_frame_overall_match(decomp, targets=None, band=(0.0, 10.0))
    assert (
        loosened["cf_normal_in_band"] is True
    )  # demonstrates the band is load-bearing


def test_match_constants_are_not_loosened():
    """The band and tolerance are pinned named constants (mirrors test_van_veen_band_is_not_loosened)."""
    assert VAN_VEEN_BAND == (0.5, 1.5)
    assert VAN_VEEN_MATCH_TOL == pytest.approx(0.6)
    assert set(VAN_VEEN_CF_TARGETS) == {"cf_chord_peak", "cf_normal_peak"}


@pytest.mark.skipif(not _FORCES_CSV.exists(), reason="committed forces.csv not present")
def test_old_run_body_frame_contrast_differs():
    """The old (stroke-∥-span) motion's body-frame CF differ materially from the new composition.

    Both decompose the SAME committed lab forces, but with the old vs new R(t): if they agreed the
    refactor would be a mere relabel. They must differ, evidencing a genuine motion change.
    """
    new = reconstruct_wing_body_forces(
        _FORCES_CSV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    old = reconstruct_wing_body_forces(
        _FORCES_CSV,
        f_star=1.0,
        phi_amp_deg=70.0,
        pitch_amp_deg=45.0,
        legacy_kinematics=True,
    )
    # The chord/normal series are materially different (RMS difference is O(1) of the signal).
    rms_diff = float(np.sqrt(np.mean((new.cf_normal - old.cf_normal) ** 2)))
    rms_new = float(np.sqrt(np.mean(new.cf_normal**2)))
    assert rms_diff > 0.1 * rms_new


@pytest.mark.skipif(not _FORCES_CSV.exists(), reason="committed forces.csv not present")
def test_body_frame_reports_dropped_spanwise():
    """The spanwise F_y is exposed as a `cf_span` diagnostic (van Veen ignores it, not a silent loss)."""
    decomp = reconstruct_wing_body_forces(
        _FORCES_CSV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    assert hasattr(decomp, "cf_span")
    assert decomp.cf_span.shape == decomp.cf_chord.shape


# --- Added-mass-subtracted body-frame diagnostic (#40 cheap interim) -------------------------
#
# Reported (not graded) diagnostic: subtract the logged added-mass rho_f*SumU from ib_force, rotate
# the remainder into the wing body frame with the SAME R(t)/body_frame_coefficients as T2a, and report
# peak |CF_chord|/|CF_normal| for total vs subtracted plus the body-frame added-mass RMS shares. These
# tests reuse the module-level path constants and mirror the existing body-frame test conventions.

_SUBTRACTED_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}


def _f_ref(f_star: float = 1.0, phi_amp_deg: float = 70.0) -> float:
    """The single-source van Veen F_ref at the given kinematics (matches the diagnostic)."""
    return compute_force_reference(
        f_star, phi_amp_deg, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref


def _write_body_frame_csv(
    path: Path,
    times: np.ndarray,
    ib_body: np.ndarray,
    am_body: np.ndarray,
    *,
    f_star: float = 1.0,
    phi_amp_deg: float = 70.0,
    pitch_amp_deg: float = 45.0,
) -> Path:
    """Write a synthetic 7-column IB CSV whose per-timestep body-frame ib/added-mass are prescribed.

    For each time ``t`` the lab force is ``R(t) @ ib_body[i]`` and the ``SumU`` row is
    ``R(t) @ am_body[i]`` (so with ``rho_f = 1`` the added-mass ``rho_f*SumU`` decodes back to
    ``am_body`` in the wing frame). This lets a test pin the body-frame subtracted result exactly.
    """
    f_lab, sum_u = [], []
    for i, t in enumerate(times):
        rot = rotation_matrix(
            *euler_angles(
                float(t),
                frequency=f_star,
                stroke_amp_rad=np.radians(phi_amp_deg),
                pitch_amp_rad=np.radians(pitch_amp_deg),
                deviation_amp_rad=0.0,
            )
        )
        f_lab.append(rot @ ib_body[i])
        sum_u.append(
            rot @ am_body[i]
        )  # rho_f = 1 -> SumU == added-mass in the lab frame
    f_lab = np.asarray(f_lab)
    sum_u = np.asarray(sum_u)
    pd.DataFrame(
        {
            "time": times,
            "Fx": f_lab[:, 0],
            "Fy": f_lab[:, 1],
            "Fz": f_lab[:, 2],
            "SumUx": sum_u[:, 0],
            "SumUy": sum_u[:, 1],
            "SumUz": sum_u[:, 2],
        }
    ).to_csv(path, index=False)
    return path


def test_added_mass_subtracted_linearity_and_reuse(tmp_path):
    """Rotation linearity holds, and a pure-chord added-mass cancels the chord while sparing the normal.

    Scenario: Reuses the T2a rotation and #36 added-mass, not a re-derivation (D2 linearity).
    """
    # (A) Linearity of the lab->body rotation: R^T(F - am) == R^T F - R^T am, componentwise.
    rot = rotation_matrix(0.3, 0.6, 0.9)
    f_lab = np.array([12.0, -5.0, 8.0])
    am_lab = np.array([3.0, 2.0, -4.0])
    f_ref = _f_ref()
    both = body_frame_coefficients(f_lab - am_lab, rot, f_ref)
    f_only = body_frame_coefficients(f_lab, rot, f_ref)
    am_only = body_frame_coefficients(am_lab, rot, f_ref)
    for k in ("cf_chord", "cf_normal", "cf_span"):
        assert both[k] == pytest.approx(f_only[k] - am_only[k], abs=1e-12)

    # (B) Through the function: a pure-chord added-mass exactly cancels the chord (subtracted ~ 0)
    # and leaves the normal untouched. ib_body = [c, 0, n]; am_body = [c, 0, 0] -> sub = [0, 0, n].
    times = np.linspace(0.1, 0.9, 60)
    c, n = 150.0, 400.0
    ib_body = np.tile([c, 0.0, n], (times.size, 1))
    am_body = np.tile([c, 0.0, 0.0], (times.size, 1))
    csv = _write_body_frame_csv(tmp_path / "cancel.csv", times, ib_body, am_body)
    out = body_frame_added_mass_subtracted(csv, **_SUBTRACTED_KIN)
    assert out["peak_cf_chord_total"] == pytest.approx(c / f_ref, abs=1e-9)
    assert out["peak_cf_chord_subtracted"] == pytest.approx(0.0, abs=1e-9)
    assert out["peak_cf_normal_subtracted"] == pytest.approx(n / f_ref, abs=1e-9)
    assert out["chord_drop_frac"] == pytest.approx(1.0, abs=1e-9)  # fully cancelled
    assert out["am_rms_share_chord"] == pytest.approx(
        1.0, abs=1e-9
    )  # am chord == ib chord
    assert out["am_rms_share_normal"] == pytest.approx(
        0.0, abs=1e-9
    )  # no am in the normal


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_subtracted_equals_manual_reuse_pipeline():
    """The subtracted peaks equal an independent added_mass_force + body_frame_coefficients pipeline.

    Scenario: Reuses #36 added_mass_force and the T2a rotation, not a re-derivation (CC-V4). A
    divergent re-implementation of the added-mass magnitude or the rotation would fail this identity.
    """
    df = pd.read_csv(_NEWCONV_CSV)
    ib = np.column_stack([df["Fx"], df["Fy"], df["Fz"]]).astype(float)
    sum_u = np.column_stack([df["SumUx"], df["SumUy"], df["SumUz"]]).astype(float)
    time = df["time"].to_numpy(float)
    sub = ib - added_mass_force(sum_u, 1.0)  # reuse #36
    f_ref = _f_ref()
    rots = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=1.0,
                    stroke_amp_rad=np.radians(70.0),
                    pitch_amp_rad=np.radians(45.0),
                    deviation_amp_rad=0.0,
                )
            )
            for t in time
        ]
    )
    cf_sub = body_frame_coefficients(sub, rots, f_ref)
    mask = time >= STEADY_WINDOW_T0
    manual_chord = float(np.abs(cf_sub["cf_chord"][mask]).max())
    manual_normal = float(np.abs(cf_sub["cf_normal"][mask]).max())
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert out["peak_cf_chord_subtracted"] == pytest.approx(manual_chord, abs=1e-9)
    assert out["peak_cf_normal_subtracted"] == pytest.approx(manual_normal, abs=1e-9)


_EXPECTED_SUBTRACTED_KEYS = {
    "peak_cf_chord_total",
    "peak_cf_normal_total",
    "peak_cf_chord_subtracted",
    "peak_cf_normal_subtracted",
    "chord_drop_frac",
    "normal_drop_frac",
    "am_rms_share_chord",
    "am_rms_share_normal",
    "window_t0",
}


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_added_mass_subtracted_reproduces_interim():
    """The #40 interim peaks recompute from the committed CSV: 0.923->0.652, 2.606->2.285.

    Scenario: Added-mass subtracted then rotated reproduces the interim peaks (committed data), and the
    total peaks equal the existing body-frame grader (the "same peaks" identity underwriting the doc).
    """
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert out["peak_cf_chord_total"] == pytest.approx(0.923, abs=0.02)
    assert out["peak_cf_chord_subtracted"] == pytest.approx(0.652, abs=0.02)
    assert out["chord_drop_frac"] == pytest.approx(0.29, abs=0.01)
    assert out["peak_cf_normal_total"] == pytest.approx(2.606, abs=0.02)
    assert out["peak_cf_normal_subtracted"] == pytest.approx(2.285, abs=0.02)
    assert out["normal_drop_frac"] == pytest.approx(0.12, abs=0.01)
    # "Same peaks" identity: the total peaks are the existing grader's peaks to machine precision
    # (both traverse the identical body_frame_coefficients path at identical kinematics/window).
    grader = body_frame_overall_match(
        reconstruct_wing_body_forces(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    )
    assert out["peak_cf_chord_total"] == pytest.approx(
        grader["peak_cf_chord"], abs=1e-9
    )
    assert out["peak_cf_normal_total"] == pytest.approx(
        grader["peak_cf_normal"], abs=1e-9
    )


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_added_mass_body_frame_rms_shares():
    """Body-frame added-mass RMS shares are ~84% chord / ~13% normal, and pinned to the added/ib defn.

    Scenario: Body-frame added-mass RMS shares are reported (rms(added_body)/rms(ib_body), the body-frame
    analog of the lab-frame added_mass_fraction — not a subtracted-ratio, not a peak-ratio).
    """
    from mosquito_cfd.benchmarks.flapping_wing import _body_frame_rms_share

    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert out["am_rms_share_chord"] == pytest.approx(0.84, abs=0.02)
    assert out["am_rms_share_normal"] == pytest.approx(0.13, abs=0.02)
    # Structural definition guard: share(k*ib, ib) == |k|, and NOT rms(ib - added)/rms(ib) = |1 - k|.
    rng = np.linspace(-1.0, 1.0, 101)
    ib = np.cos(3.0 * rng)  # arbitrary nonzero body-frame ib component
    k = 0.84
    added = k * ib
    assert _body_frame_rms_share(added, ib) == pytest.approx(k, abs=1e-9)
    subtracted_ratio = float(
        np.sqrt(np.mean((ib - added) ** 2)) / np.sqrt(np.mean(ib**2))
    )
    assert subtracted_ratio == pytest.approx(abs(1.0 - k), abs=1e-9)
    assert _body_frame_rms_share(added, ib) != pytest.approx(subtracted_ratio)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_diagnostic_is_reported_not_graded():
    """The diagnostic is REPORTED, not graded: no verdict key, and it leaves the graders unchanged.

    Scenario: Reported only — no new van Veen pass/fail; a subtracted value cannot flip any gate (CC-V2).
    """
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    # Exact reported key set — catches ANY later-added key (verdict or not), not just named ones.
    assert set(out) == _EXPECTED_SUBTRACTED_KEYS
    for verdict_key in (
        "match",
        "cf_chord_match",
        "cf_normal_match",
        "pass",
        "floor_pass",
        "in_band",
    ):
        assert verdict_key not in out
    # The existing graders return their unchanged T2a verdicts — the subtracted value cannot re-grade.
    decomp = reconstruct_wing_body_forces(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    body = body_frame_overall_match(decomp, targets=VAN_VEEN_CF_TARGETS)
    assert body["cf_normal_match"] is True
    assert body["cf_chord_match"] is False
    assert body["match"] is False


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
@pytest.mark.parametrize("dropped", ["Fy", "SumUx", "SumUy", "SumUz"])
def test_added_mass_subtracted_missing_column_raises(tmp_path, dropped):
    """Dropping ANY required column (incl. Fy/SumUy, which no single existing tuple covers) raises."""
    df = pd.read_csv(_NEWCONV_CSV).drop(columns=[dropped])
    bad = tmp_path / f"drop_{dropped}.csv"
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="missing required column"):
        body_frame_added_mass_subtracted(bad, **_SUBTRACTED_KIN)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_added_mass_subtracted_nonfinite_and_empty_window_raise(tmp_path):
    """A non-finite force/SumU row raises (never a silent NaN); an empty steady window raises."""
    df = pd.read_csv(_NEWCONV_CSV)
    df.loc[100, "SumUy"] = np.inf
    bad = tmp_path / "nonfinite.csv"
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="non-finite"):
        body_frame_added_mass_subtracted(bad, **_SUBTRACTED_KIN)
    with pytest.raises(ValueError, match="selects no timesteps"):
        body_frame_added_mass_subtracted(
            _NEWCONV_CSV, window_t0=100.0, **_SUBTRACTED_KIN
        )


def test_added_mass_subtracted_degenerate_and_empty_raise(tmp_path):
    """A (near-)zero total-component peak and an empty CSV raise a clear ValueError (never silent garbage).

    Guards the module's no-silent-NaN posture: `drop_frac = 1 - sub/total` would ZeroDivisionError and
    `am_rms_share` would emit a silent nan (exactly zero) or huge finite garbage (roundoff-scale) if a
    total body-frame component is degenerate; both are replaced by a loud, named ValueError against the
    numerical degeneracy floor. (Cannot occur on the committed run — degenerate input only.)
    """
    cols = ["time", "Fx", "Fy", "Fz", "SumUx", "SumUy", "SumUz"]
    times = np.linspace(0.1, 0.9, 40)
    # (a) chord branch: an identically-zero force record -> peak |CF_chord| total == 0 (the exact
    # ZeroDivisionError / 0-0-nan corner) -> clear ValueError.
    zero = {col: np.zeros_like(times) for col in cols}
    zero["time"] = times
    zero_csv = tmp_path / "zero_force.csv"
    pd.DataFrame(zero).to_csv(zero_csv, index=False)
    with pytest.raises(ValueError, match=r"CF_chord.*degenerate"):
        body_frame_added_mass_subtracted(zero_csv, **_SUBTRACTED_KIN)
    # (b) normal branch: a pure-chord wing -> peak |CF_normal| total is roundoff-scale (~1e-13, below
    # the floor) -> clear ValueError. This exercises the guard's second branch, which an exact ==0.0
    # check could never reach (rotation roundoff never yields bit-exact zero for the normal component).
    pure_chord = np.tile([150.0, 0.0, 0.0], (times.size, 1))
    chord_csv = _write_body_frame_csv(
        tmp_path / "pure_chord.csv", times, pure_chord, np.zeros((times.size, 3))
    )
    with pytest.raises(ValueError, match=r"CF_normal.*degenerate"):
        body_frame_added_mass_subtracted(chord_csv, **_SUBTRACTED_KIN)
    # (c) empty (header-only) CSV -> clear "no data rows", not a cryptic numpy reduction error.
    empty = tmp_path / "empty.csv"
    pd.DataFrame({col: [] for col in cols}).to_csv(empty, index=False)
    with pytest.raises(ValueError, match="no data rows"):
        body_frame_added_mass_subtracted(empty, **_SUBTRACTED_KIN)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_window_t0_and_rho_f_plumbing():
    """`window_t0` echoes + changes the window; `rho_f=0` leaves the total unchanged (share 0)."""
    default = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert default["window_t0"] == STEADY_WINDOW_T0
    # A late window (t>=0.9) excludes the chord total peak (~t=0.897), so the reported peak changes.
    later = body_frame_added_mass_subtracted(
        _NEWCONV_CSV, window_t0=0.9, **_SUBTRACTED_KIN
    )
    assert later["window_t0"] == 0.9
    assert later["peak_cf_chord_total"] != pytest.approx(default["peak_cf_chord_total"])
    # rho_f = 0 -> no added mass to subtract: subtracted == total, share == 0 (plumbs rho_f through).
    zero = body_frame_added_mass_subtracted(_NEWCONV_CSV, rho_f=0.0, **_SUBTRACTED_KIN)
    assert zero["peak_cf_chord_subtracted"] == pytest.approx(
        zero["peak_cf_chord_total"], abs=1e-12
    )
    assert zero["am_rms_share_chord"] == pytest.approx(0.0, abs=1e-12)
    assert zero["chord_drop_frac"] == pytest.approx(0.0, abs=1e-12)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_peak_migration_and_signed_drop(tmp_path):
    """Chord total/subtracted peaks fall at DIFFERENT phases; drop_frac is signed (can go negative)."""
    # (a) On the committed run the chord peaks migrate: peak_subtracted is the independent window-max,
    # NOT the subtracted value at the total's argmax.
    df = pd.read_csv(_NEWCONV_CSV)
    ib = np.column_stack([df["Fx"], df["Fy"], df["Fz"]]).astype(float)
    sum_u = np.column_stack([df["SumUx"], df["SumUy"], df["SumUz"]]).astype(float)
    time = df["time"].to_numpy(float)
    sub = ib - added_mass_force(sum_u, 1.0)
    f_ref = _f_ref()
    rots = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=1.0,
                    stroke_amp_rad=np.radians(70.0),
                    pitch_amp_rad=np.radians(45.0),
                    deviation_amp_rad=0.0,
                )
            )
            for t in time
        ]
    )
    m = time >= STEADY_WINDOW_T0
    chord_total = np.abs(body_frame_coefficients(ib, rots, f_ref)["cf_chord"][m])
    chord_sub = np.abs(body_frame_coefficients(sub, rots, f_ref)["cf_chord"][m])
    i_total, i_sub = int(np.argmax(chord_total)), int(np.argmax(chord_sub))
    assert i_total != i_sub  # the two chord peaks are at different timesteps (phases)
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    # The reported subtracted peak is the independent max (~0.652), NOT the value at the total's argmax.
    assert out["peak_cf_chord_subtracted"] == pytest.approx(
        float(chord_sub[i_sub]), abs=1e-9
    )
    assert out["peak_cf_chord_subtracted"] != pytest.approx(
        float(chord_sub[i_total]), abs=1e-3
    )
    # The INSTANTANEOUS added-mass drop AT the total-chord peak is ~47% — the third metric named in
    # the RESULTS.md caveat (distinct from the 84% RMS energy share and the -29% peak-to-peak drop).
    inst_drop_at_total_peak = 1.0 - float(chord_sub[i_total]) / float(
        chord_total[i_total]
    )
    assert inst_drop_at_total_peak == pytest.approx(0.47, abs=0.02)

    # (b) Synthetic case where subtraction RAISES the chord peak (am anti-aligned) -> drop_frac < 0.
    # A nonzero normal keeps peak_cf_normal_total above the degeneracy floor (only chord is exercised).
    times = np.linspace(0.1, 0.9, 40)
    c, n = 150.0, 400.0
    ib_body = np.tile([c, 0.0, n], (times.size, 1))
    am_body = np.tile(
        [-c, 0.0, 0.0], (times.size, 1)
    )  # anti-aligned chord -> sub_chord = 2c
    csv = _write_body_frame_csv(tmp_path / "raise.csv", times, ib_body, am_body)
    raised = body_frame_added_mass_subtracted(csv, **_SUBTRACTED_KIN)
    assert raised["chord_drop_frac"] == pytest.approx(-1.0, abs=1e-9)  # 1 - 2c/c = -1
