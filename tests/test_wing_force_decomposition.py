"""Tests for the Tier T4 per-component van Veen force decomposition (TDD).

Grades ``decompose_wing_force`` against the committed CFD ``ib_force``: the normal peak MAGNITUDE
(relative ``T4_NORMAL_MAG_TOL``) and the decomposition closure are GATED; the normal peak-phase gap,
the curve RMSE, the G2 translational-chord known-answer, and the grid-unconverged chord total are
REPORTED (no verdict). The magnitude tolerance is pinned + recomputed from its sourced inputs
(CC-V2). See openspec/changes/decompose-wing-force-per-component.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks import van_veen_model as vv
from mosquito_cfd.benchmarks.flapping_wing import (
    _EXPECTED_DECOMP_KEYS,
    T4_NORMAL_MAG_TOL,
    _assert_t4_mag_tol_not_loosened,
    decompose_wing_force,
)
from mosquito_cfd.benchmarks.wing_convergence import (
    wing_grid_convergence_from_body_forces,
)
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, stroke_rate
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN

_COARSE = "examples/flapping_wing/forces_t2a_newconv.csv"
_MEDIUM = "examples/flapping_wing/forces_medium.csv"
_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)


def _swe_analytic_ellipse() -> float:
    """Independent analytic elliptic-planform S_WE quadrature (a different integrator than the
    module's marker binning) — used to book the (tiny) S_WE uncertainty in the sourcing floor."""
    verts = np.loadtxt("examples/flapping_wing/wing.vertex", skiprows=1)
    x = verts[:, 0]
    sc = verts[:, int(np.argmax(np.ptp(verts, axis=0)))]
    y = sc + (3.0 - sc.max())
    yc, a = 0.5 * (y.min() + y.max()), 0.5 * (y.max() - y.min())
    yy = np.linspace(y.min(), y.max(), 20000)
    cc = np.ptp(x) * np.sqrt(np.clip(1 - ((yy - yc) / a) ** 2, 0.0, None))
    return float(np.trapezoid(np.sqrt(cc**3 * yy**3), yy))


def _scaled_csv(tmp_path: Path, factor: float) -> Path:
    """Committed coarse CSV with only Fx/Fy/Fz scaled by ``factor`` (scales the CFD peaks by it)."""
    df = pd.read_csv(_COARSE)
    for c in ("Fx", "Fy", "Fz"):
        df[c] = df[c] * factor
    out = tmp_path / f"scaled_{factor}.csv"
    df.to_csv(out, index=False)
    return out


def _model_normal_series() -> np.ndarray:
    """van Veen model total-normal CF series on our kinematics over the steady window (helper)."""
    df = pd.read_csv(_COARSE)
    t = df["time"].to_numpy(float)
    t = t[t >= 0.05]
    stroke_rad, pitch_rad = np.radians(70.0), np.radians(45.0)
    alpha = np.array(
        [
            euler_angles(
                x, frequency=1.0, stroke_amp_rad=stroke_rad, pitch_amp_rad=pitch_rad
            )[1]
            for x in t
        ]
    )
    omega = np.array(
        [stroke_rate(x, frequency=1.0, stroke_amp_rad=stroke_rad)[0] for x in t]
    )
    omega_dot = np.array(
        [stroke_rate(x, frequency=1.0, stroke_amp_rad=stroke_rad)[1] for x in t]
    )
    mom = vv.compute_wing_area_moments()
    f_ref = compute_force_reference(
        1.0, 70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    _, tz = vv.translational_force(alpha, omega, s_yy=mom.s_yy, rho=RHO)
    _, az = vv.added_mass_force_component(alpha, omega_dot, s_cy=mom.s_cy, rho=RHO)
    _, wz = vv.wagner_force(alpha, omega, omega_dot, s_we=mom.s_we, rho=RHO)
    return (tz + az + wz) / f_ref


# --- Section 4: tolerance constants (pinned + sourced) -----------------------------------------


def test_tolerances_pinned():
    """Only T4_NORMAL_MAG_TOL is graded; no phase/RMSE pass-fail constant exists; guard is loud."""
    assert T4_NORMAL_MAG_TOL == 0.16
    import mosquito_cfd.benchmarks.flapping_wing as fw

    # Phase and RMSE are reported, not gated: no pinned pass/fail constant may exist for them.
    assert not hasattr(fw, "T4_PEAK_PHASE_TOL")
    assert not hasattr(fw, "T4_NORMAL_RMSE_TOL")
    _assert_t4_mag_tol_not_loosened()  # passes on the pinned value
    original = fw.T4_NORMAL_MAG_TOL
    try:
        fw.T4_NORMAL_MAG_TOL = 0.5  # loosened
        with pytest.raises(AssertionError):
            fw._assert_t4_mag_tol_not_loosened()
    finally:
        fw.T4_NORMAL_MAG_TOL = original


def test_tolerances_derive_from_sourced_quantities():
    """T4_NORMAL_MAG_TOL is >= its sourced floor and only a small margin above it (not reverse-fit).

    Floor (relative) = quadrature of the normal grid GCI (recomputed from the committed pair), the
    normal coefficient-CI band (recomputed by perturbing the model coefficients to their CI edges),
    and the S_WE geometric-uncertainty term (recomputed from the marker-vs-analytic S_WE delta). Also
    asserts the chord GCI band is read from the helper, not a re-typed literal.
    """
    # (a) normal grid GCI term, recomputed from the committed pair via the reused helper.
    gci = wing_grid_convergence_from_body_forces(_COARSE, _MEDIUM, **_KIN)
    grid_rel = gci["cf_normal"]["gci_p1"]

    # (b) coefficient-CI band: perturb each normal coefficient to its far CI edge, recompute the
    # model normal peak, and combine the relative deviations in quadrature (a real recompute).
    base_peak = float(np.abs(_model_normal_series()).max())
    import mosquito_cfd.benchmarks.van_veen_model as vvmod

    def _peak_with(attr: str, value) -> float:
        original = getattr(vvmod, attr)
        try:
            setattr(vvmod, attr, value)
            return float(np.abs(_model_normal_series()).max())
        finally:
            setattr(vvmod, attr, original)

    # CI edges read from the pinned tuples (not hardcoded literals) — DRY + drift-proof.
    dev_transl = (
        abs(_peak_with("C_FZA_TRANSL", vvmod.C_FZA_TRANSL_CI[1]) - base_peak)
        / base_peak
    )
    dev_am = abs(_peak_with("C_FZA_AM", vvmod.C_FZA_AM_CI[1]) - base_peak) / base_peak
    dev_we = abs(_peak_with("C_FZA_WE", vvmod.C_FZA_WE_CI[0]) - base_peak) / base_peak
    coeff_rel = float(np.sqrt(dev_transl**2 + dev_am**2 + dev_we**2))

    # (c) S_WE geometric-uncertainty term: recompute the model normal peak with S_WE set to an
    # INDEPENDENT analytic elliptic quadrature (a different integrator) and take the relative
    # deviation. Marker and analytic S_WE agree to ~0.1%, so this term is tiny (~0.001) — the
    # budget is grid-dominated (see below), NOT S_WE-driven.
    swe_analytic = _swe_analytic_ellipse()
    original_swe_fn = vvmod._s_we_marker_quadrature
    try:
        vvmod._s_we_marker_quadrature = lambda *a, **k: swe_analytic
        swe_rel = (
            abs(float(np.abs(_model_normal_series()).max()) - base_peak) / base_peak
        )
    finally:
        vvmod._s_we_marker_quadrature = original_swe_fn

    floor = float(np.sqrt(grid_rel**2 + coeff_rel**2 + swe_rel**2))
    assert (
        floor <= T4_NORMAL_MAG_TOL <= floor + 0.03
    )  # >= sourced floor, only a small margin above (tasks §4.3)
    # The floor is grid-GCI-DOMINATED (>90%): the coeff-CI and S_WE terms are negligible, so the
    # magnitude tolerance rests on the measured grid uncertainty, not a tuned coefficient/geometry.
    assert grid_rel > 0.9 * floor

    # Chord GCI band is READ from the helper (not a re-typed literal).
    r = decompose_wing_force(_COARSE, medium_csv=_MEDIUM, **_KIN)
    assert r["chord_gci_band"] == (gci["cf_chord"]["gci_p2"], gci["cf_chord"]["gci_p1"])


# --- Section 5: graded decomposition -----------------------------------------------------------


def test_normal_magnitude_graded_phase_reported(tmp_path):
    """G1 magnitude passes within / fails outside T4_NORMAL_MAG_TOL (both directions); phase + RMSE
    are reported numbers with no pass/fail field."""
    model_peak = float(
        np.abs(_model_normal_series()).max()
    )  # ~2.476, fixed by our kinematics
    # Inside the relative tol: CFD peak set to model_peak/(1 +/- 0.10) -> |gap|_rel = 0.10 < 0.16.
    for gap in (+0.10, -0.10):
        target = model_peak / (1.0 + gap)
        r = decompose_wing_force(_scaled_csv(tmp_path, target / 2.6060), **_KIN)
        assert r["normal_mag_pass"] is True
        assert r["normal_mag_gap_rel"] == pytest.approx(abs(gap), rel=0.02)
    # Outside the relative tol: |gap|_rel = 0.25 > 0.16, BOTH directions.
    for gap in (+0.25, -0.25):
        target = model_peak / (1.0 + gap)
        r = decompose_wing_force(_scaled_csv(tmp_path, target / 2.6060), **_KIN)
        assert r["normal_mag_pass"] is False
    # Phase + RMSE are reported (no *_pass field for them).
    r = decompose_wing_force(_COARSE, **_KIN)
    assert "normal_peak_phase_gap" in r and "normal_curve_rmse" in r
    assert not any(
        k.startswith(("normal_peak_phase", "normal_curve")) and k.endswith("_pass")
        for k in r
    )


def test_translational_chord_known_answer():
    """G2: the model translational-chord peak is the known-answer (~0.42), NOT graded against 0.30."""
    r = decompose_wing_force(_COARSE, **_KIN)
    assert r["transl_chord_peak"] == pytest.approx(0.42, abs=0.01)
    assert r["transl_chord_peak"] < r["chord_peak_cfd"]  # O(0.4) << the CFD total ~0.92
    # No chord *_match/*_pass verdict, and VAN_VEEN_CF_TARGETS is not used as a chord gate.
    assert not any("chord" in k and k.endswith(("_pass", "_match")) for k in r)


def test_closure_reported_and_guards(tmp_path):
    """G3 closure exact; chord band from the helper + convergence direction; exact key set; the
    exact required column set is enforced (missing any of time/Fx/Fy/Fz raises)."""
    r = decompose_wing_force(_COARSE, medium_csv=_MEDIUM, **_KIN)
    assert r["closure_pass"] is True and r["closure_max_resid"] <= 1e-9
    assert r["chord_gci_band"] is not None and len(r["chord_gci_band"]) == 2
    assert (
        r["chord_converges_toward_model"] is True
    )  # medium chord closer to model than coarse
    # Exact enumerated key set — a later-added chord/phase gate would fail this.
    assert set(r) == _EXPECTED_DECOMP_KEYS
    # Required column set enforced: dropping any of time/Fx/Fy/Fz raises (not silently satisfied by
    # a narrower reconstruct set).
    for col in ("time", "Fx", "Fy", "Fz"):
        df = pd.read_csv(_COARSE).drop(columns=[col])
        bad = tmp_path / f"missing_{col}.csv"
        df.to_csv(bad, index=False)
        with pytest.raises(ValueError):
            decompose_wing_force(bad, **_KIN)


def test_degenerate_zero_cfd_force_raises(tmp_path):
    """An all-zero CFD force series raises the module's named ValueError, not a bare ZeroDivision."""
    df = pd.read_csv(_COARSE)
    for c in ("Fx", "Fy", "Fz"):
        df[c] = 0.0
    bad = tmp_path / "zero_force.csv"
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="degeneracy floor"):
        decompose_wing_force(bad, **_KIN)


def test_decompose_reproduces_coarse_peaks():
    """End-to-end: the CFD side reproduces the T2a coarse peaks (0.92 / 2.61), not re-derived."""
    r = decompose_wing_force(_COARSE, **_KIN)
    assert r["chord_peak_cfd"] == pytest.approx(0.923, rel=1e-2)
    assert r["normal_peak_cfd"] == pytest.approx(2.606, rel=1e-2)
    # Model per-component + total returned on the same time grid for the figure.
    assert r["series"]["model_normal"].shape == r["series"]["cfd_normal"].shape
