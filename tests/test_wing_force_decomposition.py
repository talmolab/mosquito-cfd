"""Tests for the Tier T4 per-component van Veen force decomposition (TDD).

Grades ``decompose_wing_force`` against the committed CFD ``ib_w``: the normal peak MAGNITUDE
(relative ``T4_NORMAL_MAG_TOL``) and the decomposition closure are GATED; the normal peak-phase gap,
the curve RMSE, the signed curve correlations, the G2 translational-chord window peak, and the
grid-unconverged chord total are REPORTED (no verdict). The magnitude tolerance is pinned +
recomputed from its sourced inputs (CC-V2). See openspec/changes/decompose-wing-force-per-component
and openspec/changes/fix-van-veen-model-regrade-t4.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _density_helpers import BAD_DENSITIES, OVERFLOW_DENSITIES, PreciseReal

from mosquito_cfd.benchmarks import van_veen_model as vv
from mosquito_cfd.benchmarks.flapping_wing import (
    _EXPECTED_DECOMP_KEYS,
    T4_NORMAL_MAG_TOL,
    _assert_t4_mag_tol_not_loosened,
    _curve_corr,
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
_FINE = "examples/flapping_wing/forces_fine.csv"
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
    """van Veen model total-normal CF series on our kinematics over the steady window (helper).

    Built on the production input function ``vv.model_inputs``, like ``decompose_wing_force``.
    """
    df = pd.read_csv(_COARSE)
    t = df["time"].to_numpy(float)
    t = t[t >= 0.05]
    stroke_rad, pitch_rad = np.radians(70.0), np.radians(45.0)
    pitch = np.array(
        [
            euler_angles(
                x, frequency=1.0, stroke_amp_rad=stroke_rad, pitch_amp_rad=pitch_rad
            )[1]
            for x in t
        ]
    )
    rates = np.array(
        [stroke_rate(x, frequency=1.0, stroke_amp_rad=stroke_rad) for x in t]
    )
    inp = vv.model_inputs(pitch, rates[:, 0], rates[:, 1])
    mom = vv.compute_wing_area_moments()
    f_ref = compute_force_reference(
        1.0, 70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    _, tz = vv.translational_force(inp.alpha, inp.omega, s_yy=mom.s_yy, rho=RHO)
    _, az = vv.added_mass_force_component(
        inp.alpha, inp.omega_dot, s_cy=mom.s_cy, rho=RHO
    )
    _, wz = vv.wagner_force(inp.alpha, inp.omega, inp.omega_dot, s_we=mom.s_we, rho=RHO)
    return (tz + az + wz) * inp.normal_dir / f_ref


def _swe_nominal_ellipse() -> float:
    """S_WE of the NOMINAL ellipse (span 3, chord 1, root at the hinge), fine quadrature."""
    y = np.linspace(0.0, 3.0, 200_001)
    c = np.sqrt(np.clip(1.0 - ((y - 1.5) / 1.5) ** 2, 0.0, None))
    return float(np.trapezoid(np.sqrt(c**3 * y**3), y))


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
    # deviation. Marker and analytic S_WE agree to ~0.1%, so this term is tiny — the
    # budget is grid-dominated (see below), NOT S_WE-driven. The patched helper returns the pair
    # (marker S_cy, analytic S_WE): compute_wing_area_moments checks the first against the closed
    # form, so it must stay the real marker value.
    swe_analytic = _swe_analytic_ellipse()
    scy_marker = vvmod.s_cy_marker_quadrature()
    original_fn = vvmod._marker_moment_quadrature
    try:
        vvmod._marker_moment_quadrature = lambda *a, **k: (scy_marker, swe_analytic)
        assert vvmod.compute_wing_area_moments().s_we == swe_analytic
        swe_rel = (
            abs(float(np.abs(_model_normal_series()).max()) - base_peak) / base_peak
        )
    finally:
        vvmod._marker_moment_quadrature = original_fn
    assert swe_rel > 0  # the substituted quadrature took effect

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
    model_peak = float(np.abs(_model_normal_series()).max())  # fixed by our kinematics
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


@pytest.mark.parametrize("csv", [_FINE, _COARSE])
def test_translational_chord_known_answer(csv):
    """G2: the translational-chord window peak equals an independent dense-grid maximum.

    The expression is ``(phi_dot/omega_ref)**2 * (A*a**2 + B*a + C)`` with ``a`` the angle of
    attack in degrees. Its window peak falls away from mid-stroke (where it is 0.042125), because
    the polynomial rises as the angle of attack drops. Reported, NOT graded against the T2a 0.30.
    """
    r = decompose_wing_force(csv, **_KIN)
    t_end = float(pd.read_csv(csv)["time"].max())
    t = np.linspace(0.05, t_end, 2_000_001)
    a_deg = np.abs(45.0 * np.cos(2 * np.pi * t))
    dense = (
        np.cos(2 * np.pi * t) ** 2 * (8.5e-5 * a_deg**2 - 1.2e-2 * a_deg + 0.41)
    ).max()
    assert r["transl_chord_peak"] == pytest.approx(dense, abs=1e-4)
    assert r["transl_chord_peak"] == pytest.approx(0.0573, abs=1e-4)
    assert r["transl_chord_peak"] > 0.042125 + 0.01  # not the mid-stroke value
    assert r["transl_chord_peak"] < r["chord_peak_cfd"]
    # No chord *_match/*_pass verdict, and VAN_VEEN_CF_TARGETS is not used as a chord gate.
    assert not any("chord" in k and k.endswith(("_pass", "_match")) for k in r)


def test_curve_correlations_are_reported_and_signed(tmp_path):
    """The signed normal and chord correlations are plain numbers with no verdict key."""
    base = decompose_wing_force(_COARSE, **_KIN)
    for key in ("normal_curve_corr", "chord_curve_corr"):
        assert isinstance(base[key], float) and -1.0 <= base[key] <= 1.0
    assert {k for k in base if k.endswith("_pass")} == {
        "normal_mag_pass",
        "closure_pass",
    }
    assert not any(k.endswith("_match") for k in base)
    # Negating the CFD negates both correlations exactly; doubling it leaves them unchanged.
    negated = decompose_wing_force(_scaled_csv(tmp_path, -1.0), **_KIN)
    doubled = decompose_wing_force(_scaled_csv(tmp_path, 2.0), **_KIN)
    for key in ("normal_curve_corr", "chord_curve_corr"):
        assert negated[key] == pytest.approx(-base[key], rel=1e-9)
        assert doubled[key] == pytest.approx(base[key], rel=1e-9)
    # The model normal keeps one sign over the wingbeat, as the CFD normal does.
    assert base["normal_curve_corr"] > 0.9


def test_curve_corr_of_a_constant_series_raises():
    """A constant series has no correlation: a named error, never NaN."""
    ramp = np.linspace(0.0, 1.0, 50)
    with pytest.raises(ValueError, match="curve correlation is undefined"):
        _curve_corr(np.full(50, 2.0), ramp)
    with pytest.raises(ValueError, match="curve correlation is undefined"):
        _curve_corr(ramp, np.zeros(50))
    assert _curve_corr(ramp, 3.0 * ramp + 1.0) == pytest.approx(1.0)
    assert _curve_corr(ramp, -ramp) == pytest.approx(-1.0)


def test_graded_verdict_does_not_depend_on_the_planform_basis(monkeypatch):
    """The fine-grid normal gap passes under each alternative moment basis (pinned).

    ``S_cy`` is the nominal closed form and ``S_WE`` a marker quadrature. Swapping either for the
    other basis must not flip the grade, so the basis cannot be used to tune it.
    """
    real = vv.compute_wing_area_moments()
    base = decompose_wing_force(_FINE, **_KIN)
    assert base["normal_mag_gap_rel"] == pytest.approx(0.0174, abs=5e-4)
    assert base["normal_mag_pass"] is True

    def gap_with(**swap) -> dict:
        moments = vv.WingAreaMoments(
            s_yy=real.s_yy,
            s_cy=swap.get("s_cy", real.s_cy),
            s_we=swap.get("s_we", real.s_we),
        )
        monkeypatch.setattr(vv, "compute_wing_area_moments", lambda *a, **k: moments)
        return decompose_wing_force(_FINE, **_KIN)

    marker_scy = gap_with(s_cy=vv.s_cy_marker_quadrature())
    assert marker_scy["normal_mag_gap_rel"] == pytest.approx(0.0185, abs=5e-4)
    assert marker_scy["normal_mag_pass"] is True
    nominal_swe = gap_with(s_we=_swe_nominal_ellipse())
    assert nominal_swe["normal_mag_gap_rel"] == pytest.approx(0.0207, abs=5e-4)
    assert nominal_swe["normal_mag_pass"] is True


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


def test_medium_csv_omitted_gives_no_chord_band():
    """Without ``medium_csv``, ``chord_gci_band``/``chord_converges_toward_model`` default to None
    (no 2-grid report) — the safe default, used in production (T3c/#52) when ``csv_path`` is the
    finest grid available and has no genuinely coarser CSV to pair against."""
    r = decompose_wing_force(_FINE, **_KIN)
    assert r["chord_gci_band"] is None
    assert r["chord_converges_toward_model"] is None


def test_medium_csv_must_not_pair_a_finer_csv_path():
    """Regression pin (T3c fine-grid repoint, #52): pairing a FINER ``csv_path`` against a coarser
    ``medium_csv`` inverts ``wing_grid_convergence``'s coarse/medium role labeling (it treats
    ``csv_path`` as "coarse" unconditionally) and silently flips ``chord_converges_toward_model``
    to the WRONG answer.

    The CFD chord peak falls under refinement (RESULTS.md, T3c): 0.923 coarse -> 0.554 medium ->
    0.411 fine, each step nearer the model's chord peak, which is lower still. But passing the FINE
    grid as ``csv_path`` (forced into the "coarse" role) against the MEDIUM grid as ``medium_csv``
    inverts the role labels and reports the opposite direction.
    This is exactly why ``make_force_decomposition_figure.py`` and
    ``test_t4_decomposition_numbers_reproduce`` deliberately omit ``medium_csv`` now that the
    production comparison uses the fine grid -- see ``decompose_wing_force``'s ``medium_csv``
    docstring caveat. If this assertion ever starts failing, it's a live signal that behavior
    changed; do not "fix" it by asserting True here -- fix the caller instead.
    """
    r = decompose_wing_force(_FINE, medium_csv=_MEDIUM, **_KIN)
    assert (
        r["chord_converges_toward_model"] is False
    )  # the WRONG answer -- pinned as a warning


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


def _assert_same_t4(got, want, *, exact: bool, path: str = "") -> None:
    """Every number, verdict and series in two ``decompose_wing_force`` results agrees."""
    if isinstance(want, dict):
        assert got.keys() == want.keys(), path
        for key in want:
            _assert_same_t4(got[key], want[key], exact=exact, path=f"{path}.{key}")
    elif isinstance(want, (tuple, list)):
        assert len(got) == len(want), path
        for i, (g, w) in enumerate(zip(got, want, strict=True)):
            _assert_same_t4(g, w, exact=exact, path=f"{path}[{i}]")
    elif isinstance(want, (bool, np.bool_)) or want is None or isinstance(want, str):
        assert got == want, path
    elif exact:
        np.testing.assert_array_equal(got, want, err_msg=path)
    else:
        np.testing.assert_allclose(got, want, rtol=1e-12, atol=1e-15, err_msg=path)


@pytest.mark.parametrize("rho", [0.5, 2.0, 1.3, PreciseReal(1.3)], ids=repr)
def test_model_density_cancels_so_no_t4_number_or_verdict_depends_on_it(rho):
    """The model is normalized by ``F_ref`` built at the model's own ``rho``.

    Scenario: The model's density cancels, so no T4 number or verdict depends on it (review
    round 4 of #136). Before the fix the model was divided by the CFD's ``F_ref`` at ``RHO``:
    ``rho = 2`` doubled the model normal peak (against the CFD's 2.23) and flipped
    ``normal_mag_pass``. The powers of two are exact in floating point; 1.3 is not.
    """
    want = decompose_wing_force(_FINE, **_KIN)
    got = decompose_wing_force(_FINE, rho=rho, **_KIN)
    if isinstance(rho, PreciseReal):
        # A higher-precision real is converted to float first, so it matches float(rho) bitwise.
        want = decompose_wing_force(_FINE, rho=float(rho), **_KIN)
        _assert_same_t4(got, want, exact=True)
    else:
        _assert_same_t4(got, want, exact=rho in (0.5, 2.0))


@pytest.mark.parametrize("bad", list(BAD_DENSITIES.values()), ids=list(BAD_DENSITIES))
@pytest.mark.parametrize("csv", [_FINE, "no/such/forces.csv"])
def test_model_density_that_is_not_a_finite_positive_real_raises_before_reading(
    bad, csv
):
    """A bad ``rho`` is a named parameter error, raised before the CSV is opened (round 4)."""
    with pytest.raises(
        ValueError, match=r"^rho must be a finite, positive real number"
    ):
        decompose_wing_force(csv, rho=bad, **_KIN)


# The overflow is the point of these cases; numpy warns on it (and on the inf + -inf after).
@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")
@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")
@pytest.mark.parametrize("rho", OVERFLOW_DENSITIES, ids=repr)
def test_model_density_so_large_that_it_overflows_names_rho(rho):
    """An overflowing ``rho`` is a named error, never an ``inf``/NaN T4 number (round 5).

    At ``5e305`` the model's ``F_ref`` is finite but its forces overflow: round 5 found
    ``normal_peak_model = inf`` and ``normal_mag_pass = False`` returned with no error.
    """
    with pytest.raises(ValueError, match=r"\brho=.*overflow"):
        decompose_wing_force(_FINE, rho=rho, **_KIN)
