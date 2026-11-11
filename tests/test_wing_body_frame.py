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


_MEDIUM_CSV = Path("examples/flapping_wing/forces_medium.csv")
_MEDIUM_DECK = Path("examples/flapping_wing/inputs.3d.convergence_medium")
_T3B_META = Path("examples/flapping_wing/run_metadata_t3b.json")


@pytest.mark.skipif(
    not _MEDIUM_CSV.exists(), reason="medium forces CSV not present (T3b run)"
)
def test_medium_csv_matches_ib_particle_contract():
    """forces_medium.csv (T3b) keeps the 29-column schema AND is a plausible full-window run.

    Mirrors the coarse pin, plus a physical-plausibility guard: a truncated or diverged medium run
    that wrote only a few finite rows (or stopped short of stop_time = 1.0) must fail here rather than
    silently feed a wrong-but-plausible peak into the convergence grader.
    """
    df = pd.read_csv(_MEDIUM_CSV)
    assert list(df.columns) == _IB_PARTICLE_29_COLS
    # Physical plausibility: reaches the stop_time window and is not a truncated write-out.
    assert df["time"].max() == pytest.approx(1.0, abs=1e-3)
    assert len(df) > 1900
    # The decomposition consumes it end-to-end to a finite per-component series.
    decomp = reconstruct_wing_body_forces(
        _MEDIUM_CSV, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    assert decomp.cf_chord.shape == decomp.cf_normal.shape == (len(df),)
    assert np.isfinite(decomp.cf_chord).all() and np.isfinite(decomp.cf_normal).all()


@pytest.mark.skipif(
    not (_T3B_META.exists() and _MEDIUM_DECK.exists()),
    reason="T3b run metadata / medium deck not present",
)
def test_run_metadata_t3b_inputs_hash_matches_medium_deck():
    """run_metadata_t3b.json pins the MEDIUM deck (inputs hash) + the :fp64 @ f93dc794 provenance.

    The inputs-hash link is load-bearing: it ties the committed convergence data to the exact
    deck-invariance-guarded medium deck. A silent drift (wrong deck hashed) would make the deck
    guarantee vacuous, so pin it cryptographically here.
    """
    import hashlib
    import json

    meta = json.loads(_T3B_META.read_text())
    deck_sha = hashlib.sha256(_MEDIUM_DECK.read_bytes()).hexdigest()
    assert meta["inputs"]["hash"] == deck_sha
    assert meta["iamrex_commit"].startswith("f93dc794")
    assert meta["tier"] == "T3b"
    # Same :fp64 pin (digest present) and a machine-readable dt record for the grading guard.
    assert "docker_image" in meta and meta.get("image_digest", "").startswith("sha256:")
    assert float(meta["fixed_dt"]) == pytest.approx(5e-4)


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
# Reported (not graded) diagnostic: the 6-DOF free-body force rho_f*SumU + rho_f*ib_w and the IB
# force on the wing rho_f*ib_w, rotated into the wing body frame with the SAME R(t) /
# body_frame_coefficients as T2a; reports both peak |CF_chord|/|CF_normal|, the signed drop
# fractions and the body-frame RMS shares of the internal-fluid term. These tests reuse the
# module-level path constants and mirror the existing body-frame test conventions.

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


def _kin_rotations(time: np.ndarray) -> np.ndarray:
    """``R(t)`` at the diagnostic's kinematics, built independently of the module's loop."""
    return np.stack(
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


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_body_frame_series_rotate_the_ib_force_on_the_wing():
    """``reconstruct_wing_body_forces`` rotates ``−ib_force``, the IB force on the wing (issue #109).

    The graded body-frame peaks use ``|·|`` and are unchanged; the existing literals elsewhere in this
    file stay green with no edit, which is the independent pin.
    """
    df = pd.read_csv(_NEWCONV_CSV)
    time = df["time"].to_numpy(float)
    f_lab = df[["Fx", "Fy", "Fz"]].to_numpy(float)
    expected = body_frame_coefficients(-f_lab, _kin_rotations(time), _f_ref())
    got = reconstruct_wing_body_forces(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    for key in ("cf_chord", "cf_normal", "cf_span"):
        np.testing.assert_allclose(getattr(got, key), expected[key], rtol=0, atol=1e-12)


def test_added_mass_subtracted_linearity_and_reuse(tmp_path):
    """Rotation linearity holds, and a pure-chord added-mass moves only the 6-DOF chord.

    Scenario: Reuses the T2a rotation and #36 added-mass, not a re-derivation (D2 linearity). The CSV's
    ``F`` is the solver's on-fluid ``ib_force``, so the wing's ``ib_w = −F`` and the 6-DOF force is
    ``rho_f·SumU + rho_f·ib_w``.
    """
    # (A) Linearity of the lab->body rotation: R^T(am - F) == R^T am - R^T F, componentwise.
    rot = rotation_matrix(0.3, 0.6, 0.9)
    f_lab = np.array([12.0, -5.0, 8.0])
    am_lab = np.array([3.0, 2.0, -4.0])
    f_ref = _f_ref()
    both = body_frame_coefficients(am_lab - f_lab, rot, f_ref)
    f_only = body_frame_coefficients(f_lab, rot, f_ref)
    am_only = body_frame_coefficients(am_lab, rot, f_ref)
    for k in ("cf_chord", "cf_normal", "cf_span"):
        assert both[k] == pytest.approx(am_only[k] - f_only[k], abs=1e-12)

    # (B) Through the function. CSV body force [c, 0, n] on the fluid -> ib_w = [-c, 0, -n]; a
    # pure-chord added mass [3c, 0, 0] -> 6-DOF = [2c, 0, -n]: the chord doubles, the normal is spared.
    times = np.linspace(0.1, 0.9, 60)
    c, n = 150.0, 400.0
    ib_body = np.tile([c, 0.0, n], (times.size, 1))
    am_body = np.tile([3 * c, 0.0, 0.0], (times.size, 1))
    csv = _write_body_frame_csv(tmp_path / "chord_only.csv", times, ib_body, am_body)
    out = body_frame_added_mass_subtracted(csv, **_SUBTRACTED_KIN)
    assert out["peak_cf_chord_ib"] == pytest.approx(c / f_ref, abs=1e-9)
    assert out["peak_cf_chord_6dof"] == pytest.approx(2 * c / f_ref, abs=1e-9)
    assert out["peak_cf_normal_ib"] == pytest.approx(n / f_ref, abs=1e-9)
    assert out["peak_cf_normal_6dof"] == pytest.approx(n / f_ref, abs=1e-9)
    assert out["chord_drop_frac"] == pytest.approx(0.5, abs=1e-9)  # 1 - c/(2c)
    assert out["normal_drop_frac"] == pytest.approx(0.0, abs=1e-9)
    assert out["am_rms_share_chord"] == pytest.approx(3.0, abs=1e-9)  # rms(3c)/rms(c)
    assert out["am_rms_share_normal"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_subtracted_equals_manual_reuse_pipeline():
    """The 6-DOF and ``ib_w`` peaks equal an independent pipeline from the raw columns.

    Scenario: Reuses #36 added_mass_force and the T2a rotation, not a re-derivation (CC-V4). The 6-DOF
    force is taken straight from the solver's balance, ``rho_f·(SumU − ib_force)``, and ``ib_w`` as
    ``−ib_force``, so a divergent sign, added-mass magnitude or rotation fails this identity.
    """
    df = pd.read_csv(_NEWCONV_CSV)
    ib = np.column_stack([df["Fx"], df["Fy"], df["Fz"]]).astype(float)
    sum_u = np.column_stack([df["SumUx"], df["SumUy"], df["SumUz"]]).astype(float)
    time = df["time"].to_numpy(float)
    six_dof = added_mass_force(sum_u, 1.0) - ib  # rho_f*(SumU - ib_force), rho_f = 1
    rots = _kin_rotations(time)
    mask = time >= STEADY_WINDOW_T0
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    for name, force in (("6dof", six_dof), ("ib", -ib)):
        cf = body_frame_coefficients(force, rots, _f_ref())
        for comp in ("chord", "normal"):
            manual = float(np.abs(cf[f"cf_{comp}"][mask]).max())
            assert out[f"peak_cf_{comp}_{name}"] == pytest.approx(manual, abs=1e-9)


_EXPECTED_SUBTRACTED_KEYS = {
    "peak_cf_chord_6dof",
    "peak_cf_normal_6dof",
    "peak_cf_chord_ib",
    "peak_cf_normal_ib",
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
    """The diagnostic's committed-run values match design D5 to four decimals.

    Scenario: the 6-DOF force (``rho_f·SumU + rho_f·ib_w``) and ``ib_w`` rotated into the body frame
    reproduce the D5 peaks, signed drop fractions and RMS shares, and the ``ib`` peaks equal the
    existing body-frame grader's (the "same peaks" identity underwriting the doc).
    """
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    for key, value in (
        ("peak_cf_chord_6dof", 0.6517),
        ("peak_cf_chord_ib", 0.9231),
        ("chord_drop_frac", -0.4165),
        ("peak_cf_normal_6dof", 2.2851),
        ("peak_cf_normal_ib", 2.6060),
        ("normal_drop_frac", -0.1404),
        ("am_rms_share_chord", 0.8392),
        ("am_rms_share_normal", 0.1278),
    ):
        assert round(out[key], 4) == value, (key, out[key])
    # "Same peaks" identity: the ib peaks are the existing grader's peaks to machine precision
    # (both traverse the identical body_frame_coefficients path at identical kinematics/window).
    # It holds at any density because F_ref carries the same rho_f as the force (review of #136).
    grader = body_frame_overall_match(
        reconstruct_wing_body_forces(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    )
    for rho_f in (RHO, 2.0):
        at = body_frame_added_mass_subtracted(
            _NEWCONV_CSV, rho_f=rho_f, **_SUBTRACTED_KIN
        )
        assert at["peak_cf_chord_ib"] == pytest.approx(
            grader["peak_cf_chord"], abs=1e-9
        )
        assert at["peak_cf_normal_ib"] == pytest.approx(
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
    """A (near-)zero denominator and an empty CSV raise a clear, named ValueError (never garbage).

    Two denominators, each with its own floor: the 6-DOF peak (``drop_frac = 1 − ib/6dof``) and the
    ``ib_w`` peak (``am_rms_share = rms(added)/rms(ib_w)``). A zero or roundoff-scale denominator would
    otherwise give a ZeroDivisionError, a silent nan, or huge finite garbage. (Cannot occur on the
    committed run — degenerate input only.)
    """
    cols = ["time", "Fx", "Fy", "Fz", "SumUx", "SumUy", "SumUz"]
    times = np.linspace(0.1, 0.9, 40)
    body = np.tile([150.0, 0.0, 400.0], (times.size, 1))
    # (a) zero 6-DOF: rho_f·SumU = −rho_f·ib_w, i.e. SumU equals the CSV's on-fluid force, while ib_w
    # is healthy -> only the 6-DOF floor can fire.
    six_dof_zero = _write_body_frame_csv(
        tmp_path / "six_dof_zero.csv", times, body, body
    )
    with pytest.raises(
        ValueError,
        match=r"CF_chord\| of the 6-DOF force .*the chord drop fraction is undefined",
    ):
        body_frame_added_mass_subtracted(six_dof_zero, **_SUBTRACTED_KIN)
    # (b) zero ib_w: no IB force at all, while the added mass keeps the 6-DOF healthy -> only the
    # ib_w floor can fire.
    ib_zero = _write_body_frame_csv(
        tmp_path / "ib_zero.csv", times, np.zeros_like(body), body
    )
    # ib_w is the drop fraction's numerator, so its floor protects only the RMS share.
    with pytest.raises(
        ValueError, match=r"CF_chord\| of ib_w .*the chord RMS share is undefined"
    ) as caught:
        body_frame_added_mass_subtracted(ib_zero, **_SUBTRACTED_KIN)
    assert "drop fraction" not in str(caught.value)
    # (c) normal branch, roundoff-scale: a pure-chord wing -> both normal peaks are ~1e-13, below the
    # floor, which an exact ==0.0 check could never reach.
    pure_chord = np.tile([150.0, 0.0, 0.0], (times.size, 1))
    chord_csv = _write_body_frame_csv(
        tmp_path / "pure_chord.csv", times, pure_chord, np.zeros((times.size, 3))
    )
    with pytest.raises(
        ValueError, match=r"CF_normal\| of the 6-DOF force .*degenerate"
    ):
        body_frame_added_mass_subtracted(chord_csv, **_SUBTRACTED_KIN)
    # (d) normal ib_w alone: a pure-chord IB force with a normal internal-fluid term keeps both
    # chord peaks and the 6-DOF normal healthy -> only the normal ib_w floor can fire.
    normal_am = np.tile([0.0, 0.0, 400.0], (times.size, 1))
    ib_normal_zero = _write_body_frame_csv(
        tmp_path / "ib_normal_zero.csv", times, pure_chord, normal_am
    )
    with pytest.raises(ValueError, match=r"CF_normal\| of ib_w .*degenerate"):
        body_frame_added_mass_subtracted(ib_normal_zero, **_SUBTRACTED_KIN)
    # (c) empty (header-only) CSV -> clear "no data rows", not a cryptic numpy reduction error.
    empty = tmp_path / "empty.csv"
    pd.DataFrame({col: [] for col in cols}).to_csv(empty, index=False)
    with pytest.raises(ValueError, match="no data rows"):
        body_frame_added_mass_subtracted(empty, **_SUBTRACTED_KIN)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_window_t0_and_rho_f_plumbing():
    """`window_t0` echoes + changes the window; `rho_f` cancels, so no reported value moves.

    IAMReX's ``ib_force`` is per unit density (``DiffusedIB.cpp`` multiplies it by
    ``euler_fluid_rho``), so the force on the wing is ``rho_f·ib_w`` and the 6-DOF force
    ``rho_f·SumU + rho_f·ib_w``. ``F_ref`` is built with the same density, so ``rho_f = 2``
    leaves every peak, drop fraction and RMS share unchanged; a density that is not finite and
    positive is rejected as a parameter error (reviews of #136).
    """
    default = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert default["window_t0"] == STEADY_WINDOW_T0
    # A late window (t>=0.9) excludes the chord ib peak (~t=0.897), so the reported peak changes.
    later = body_frame_added_mass_subtracted(
        _NEWCONV_CSV, window_t0=0.9, **_SUBTRACTED_KIN
    )
    assert later["window_t0"] == 0.9
    assert later["peak_cf_chord_ib"] != pytest.approx(default["peak_cf_chord_ib"])
    for rho_f in (0.5, 2.0):
        other = body_frame_added_mass_subtracted(
            _NEWCONV_CSV, rho_f=rho_f, **_SUBTRACTED_KIN
        )
        assert other == default, rho_f  # exact: the powers of two cancel bitwise
    other = body_frame_added_mass_subtracted(_NEWCONV_CSV, rho_f=1.3, **_SUBTRACTED_KIN)
    for key, value in default.items():
        assert other[key] == pytest.approx(value, rel=1e-12, abs=1e-15), key
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(
            ValueError, match=r"rho_f must be a finite, positive real number"
        ):
            body_frame_added_mass_subtracted(_NEWCONV_CSV, rho_f=bad, **_SUBTRACTED_KIN)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_peak_migration_and_signed_drop(tmp_path):
    """The 6-DOF and ``ib_w`` chord peaks fall at different phases; drop_frac is signed."""
    # (a) On the committed run the chord peaks are 1094 steps apart: each reported peak is its own
    # window max, NOT one series' value at the other's argmax.
    df = pd.read_csv(_NEWCONV_CSV)
    ib = np.column_stack([df["Fx"], df["Fy"], df["Fz"]]).astype(float)
    sum_u = np.column_stack([df["SumUx"], df["SumUy"], df["SumUz"]]).astype(float)
    time = df["time"].to_numpy(float)
    rots = _kin_rotations(time)
    m = time >= STEADY_WINDOW_T0
    chord_ib = np.abs(body_frame_coefficients(-ib, rots, _f_ref())["cf_chord"][m])
    six_dof = added_mass_force(sum_u, 1.0) - ib
    chord_6dof = np.abs(body_frame_coefficients(six_dof, rots, _f_ref())["cf_chord"][m])
    i_ib, i_6dof = int(np.argmax(chord_ib)), int(np.argmax(chord_6dof))
    assert abs(i_ib - i_6dof) == 1094
    out = body_frame_added_mass_subtracted(_NEWCONV_CSV, **_SUBTRACTED_KIN)
    assert out["peak_cf_chord_6dof"] == pytest.approx(
        float(chord_6dof[i_6dof]), abs=1e-9
    )
    assert out["peak_cf_chord_6dof"] != pytest.approx(float(chord_6dof[i_ib]), abs=1e-3)
    # The INSTANTANEOUS comparison at the 6-DOF chord peak: |ib_w| exceeds |F_6dof| by 39 % there
    # (1 − |ib_w|/|F_6dof| = −0.394), distinct from the peak-to-peak −0.4165 and the 84 % RMS share.
    inst = 1.0 - float(chord_ib[i_6dof]) / float(chord_6dof[i_6dof])
    assert round(inst, 3) == -0.394

    # (b) Synthetic case where ib_w's chord peak exceeds the 6-DOF one -> drop_frac < 0. CSV body force
    # [c, 0, n] -> ib_w = [-c, 0, -n]; added [c/2, 0, 0] -> 6-DOF = [-c/2, 0, -n].
    times = np.linspace(0.1, 0.9, 40)
    c, n = 150.0, 400.0
    ib_body = np.tile([c, 0.0, n], (times.size, 1))
    am_body = np.tile([c / 2, 0.0, 0.0], (times.size, 1))
    csv = _write_body_frame_csv(tmp_path / "raise.csv", times, ib_body, am_body)
    raised = body_frame_added_mass_subtracted(csv, **_SUBTRACTED_KIN)
    assert raised["chord_drop_frac"] == pytest.approx(-1.0, abs=1e-9)  # 1 - c/(c/2)
