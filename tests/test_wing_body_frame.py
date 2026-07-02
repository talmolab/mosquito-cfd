"""Cluster-free tests for the body-frame (chord/normal) van Veen comparison (Tier T2a).

Covers the analytic lab->body rotation (explicit axes, no #1-style mislabel), the overall
scalar-match grader (both directions + CC-V2 band-floor fallback), the pinned not-loosened
constants, and the old-vs-new contrast on the committed ``forces.csv``. Pure numpy/pandas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.benchmarks.flapping_wing import (
    VAN_VEEN_BAND,
    VAN_VEEN_CF_TARGETS,
    VAN_VEEN_MATCH_TOL,
    WingBodyFrameDecomposition,
    body_frame_coefficients,
    body_frame_overall_match,
    reconstruct_wing_body_forces,
)
from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix

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
