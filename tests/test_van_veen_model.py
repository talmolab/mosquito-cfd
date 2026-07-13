"""Tests for the van Veen (2022) quasi-steady force model (Tier T4, TDD).

Pure known-answer / guard tests for ``benchmarks.van_veen_model``: the three body-frame
components (translational + added-mass + Wagner), the pinned coefficients + not-loosened guard,
the half-stroke sign reversal (pinned analytically, never to the CFD series), closure + boundary
+ non-finite guards, the hinge-origin area-moments (S_yy = R_GYRATION**2*area, S_cy == S_yy, the
new S_WE marker quadrature), and the erratum provenance literal. See
openspec/changes/decompose-wing-force-per-component.
"""

import numpy as np
import pytest

from mosquito_cfd.benchmarks import van_veen_model as vv
from mosquito_cfd.force_surrogate.constants import RHO


def _omega_ref(f_star: float = 1.0, phi_amp_deg: float = 70.0) -> float:
    """Peak stroke angular velocity omega_ref = 2*pi*f_star*phi_amp_rad."""
    return 2.0 * np.pi * f_star * np.radians(phi_amp_deg)


def test_components_match_hand_computed():
    """Scenario: components equal hand-computed values at a reference state (alpha=pi/2, wd=0)."""
    m = vv.compute_wing_area_moments()
    omega = _omega_ref()
    fx_t, fz_t = vv.translational_force(np.pi / 2, omega, s_yy=m.s_yy)
    # F_z_transl = 0.5*rho*omega**2*S_yy * 3.13*sin(pi/2)
    assert fz_t == pytest.approx(0.5 * RHO * omega**2 * m.s_yy * 3.13)
    A, B, C = vv.TRANSL_TANGENTIAL_POLY
    assert fx_t == pytest.approx(
        0.5 * RHO * omega**2 * m.s_yy * (A * (np.pi / 2) ** 2 + B * (np.pi / 2) + C)
    )
    # AM and Wagner both vanish at omega_dot = 0.
    _, fz_am = vv.added_mass_force_component(np.pi / 2, 0.0, s_cy=m.s_cy)
    _, fz_we = vv.wagner_force(np.pi / 2, omega, 0.0, s_we=m.s_we)
    assert fz_am == pytest.approx(0.0)
    assert fz_we == pytest.approx(0.0)


def test_wagner_sign_for_decelerating_wing():
    """Scenario: Wagner sign generalization is finite and oppositely signed for omega_dot < 0."""
    m = vv.compute_wing_area_moments()
    omega, alpha = _omega_ref(), np.radians(45.0)
    _, fz_accel = vv.wagner_force(alpha, omega, +4.0e6, s_we=m.s_we)
    _, fz_decel = vv.wagner_force(alpha, omega, -4.0e6, s_we=m.s_we)
    assert np.isfinite(fz_accel) and np.isfinite(fz_decel)  # no sqrt of a negative
    assert np.sign(fz_accel) == -np.sign(fz_decel)  # sign(omega_dot) flips it
    assert fz_accel != 0.0


def test_force_direction_reverses_each_half_stroke():
    """Scenario: normal force direction reverses each half-stroke, pinned analytically (not CFD).

    At mid-upstroke (alpha = +45 deg) vs mid-downstroke (alpha = -45 deg) the translational normal
    sign equals sign(sin(alpha)) and reverses between the two half-strokes. Hand-computed, never
    against the CFD series (which would be reverse-fitting).
    """
    m = vv.compute_wing_area_moments()
    omega = _omega_ref()
    _, fz_up = vv.translational_force(+np.radians(45.0), omega, s_yy=m.s_yy)
    _, fz_down = vv.translational_force(-np.radians(45.0), omega, s_yy=m.s_yy)
    assert np.sign(fz_up) == np.sign(np.sin(+np.radians(45.0))) == 1.0
    assert np.sign(fz_down) == np.sign(np.sin(-np.radians(45.0))) == -1.0
    assert np.sign(fz_up) == -np.sign(fz_down)  # reverses between half-strokes


def test_coefficients_pinned():
    """Scenario: coefficients are pinned constants with a not-loosened guard (CC-V2)."""
    assert vv.C_FZA_TRANSL == 3.13
    assert vv.TRANSL_TANGENTIAL_POLY == (8.5e-5, -1.2e-2, 0.41)
    assert vv.C_FZA_AM == 0.96
    assert vv.C_FXA_AM == 0.104
    assert vv.C_FZA_WE == -1.02
    assert vv.C_FZA_TRANSL_CI == (3.10, 3.15)
    # The guard passes on the pinned values...
    vv.assert_coefficients_not_loosened()
    # ...and fails if a coefficient is widened (monkeypatch a loosened value).
    original = vv.C_FZA_WE
    try:
        vv.C_FZA_WE = -0.5  # loosened
        with pytest.raises(AssertionError):
            vv.assert_coefficients_not_loosened()
    finally:
        vv.C_FZA_WE = original


def test_total_is_sum_and_boundary():
    """Scenario: total_force == transl + AM + Wagner; omega_dot=0 boundary; non-finite raises."""
    m = vv.compute_wing_area_moments()
    t = np.linspace(0.0, 1.0, 101)
    omega = _omega_ref() * np.cos(2 * np.pi * t)
    omega_dot = -_omega_ref() * (2 * np.pi) * np.sin(2 * np.pi * t)
    alpha = np.radians(45.0) * np.cos(2 * np.pi * t)
    tx, tz = vv.translational_force(alpha, omega, s_yy=m.s_yy)
    ax, az = vv.added_mass_force_component(alpha, omega_dot, s_cy=m.s_cy)
    wx, wz = vv.wagner_force(alpha, omega, omega_dot, s_we=m.s_we)
    fx, fz = vv.total_force(
        alpha, omega, omega_dot, s_yy=m.s_yy, s_cy=m.s_cy, s_we=m.s_we
    )
    np.testing.assert_allclose(fx, tx + ax + wx)
    np.testing.assert_allclose(fz, tz + az + wz)
    # omega_dot == 0 exactly: AM and Wagner both zero, no sqrt/divide error.
    ax0, az0 = vv.added_mass_force_component(alpha, 0.0, s_cy=m.s_cy)
    wx0, wz0 = vv.wagner_force(alpha, omega, 0.0, s_we=m.s_we)
    assert np.all(ax0 == 0.0) and np.all(az0 == 0.0)
    assert np.all(wx0 == 0.0) and np.all(wz0 == 0.0)
    # Non-finite input raises (no silent NaN coefficient).
    with pytest.raises(ValueError):
        vv.translational_force(np.nan, omega, s_yy=m.s_yy)
    with pytest.raises(ValueError):
        vv.wagner_force(alpha, omega, np.inf, s_we=m.s_we)


def _swe_analytic_ellipse() -> float:
    """S_WE from an INDEPENDENT analytic elliptic-planform quadrature (different code path).

    Fits an ellipse ``c(y) = c_max*sqrt(1 - ((y-yc)/a)**2)`` to the committed markers' hinge-distance
    span and chord extent, then integrates ``sqrt(c**3 * y**3)`` on a fine 20k-point grid — no
    binning, a genuinely different method from the module's marker quadrature.
    """
    verts = np.loadtxt("examples/flapping_wing/wing.vertex", skiprows=1)
    x = verts[:, 0]
    sc = verts[:, int(np.argmax(np.ptp(verts, axis=0)))]
    y = sc + (3.0 - sc.max())  # R_TIP hinge offset
    yc, a = 0.5 * (y.min() + y.max()), 0.5 * (y.max() - y.min())
    yy = np.linspace(y.min(), y.max(), 20000)
    cc = np.ptp(x) * np.sqrt(np.clip(1 - ((yy - yc) / a) ** 2, 0.0, None))
    return float(np.trapezoid(np.sqrt(cc**3 * yy**3), yy))


def test_area_moments_hinge_origin():
    """Scenario: S_yy hinge-origin (=R_GYRATION**2*area, NOT the marker quadrature); S_cy==S_yy;
    S_WE cross-checked against an INDEPENDENT analytic quadrature; degenerate planform raises."""
    m = vv.compute_wing_area_moments()
    assert m.s_yy == pytest.approx(
        6.797, rel=1e-3
    )  # = R_GYRATION**2 * area, reconciles F_ref
    assert m.s_cy == m.s_yy  # identical integrand
    # S_WE marker quadrature (~3.98), cross-checked against a genuinely INDEPENDENT analytic
    # elliptic quadrature (a different integrator, not a re-binning) — they agree to ~0.1%.
    assert m.s_we == pytest.approx(3.98, rel=1e-2)
    assert m.s_we == pytest.approx(_swe_analytic_ellipse(), rel=0.02)
    # A hinge-origin S_yy quadrature over the markers would give ~6.24 (marker area < elliptic
    # area by ~7%); the spec deliberately does NOT use it for S_yy. Sanity: 6.797 != ~6.24.
    assert abs(m.s_yy - 6.24) > 0.3
    # Degenerate planform raises.
    with pytest.raises(ValueError):
        vv.compute_wing_area_moments(span=0.0)


def test_area_moments_guard_too_fine_binning():
    """A too-fine nbins (bins with <=1 marker) raises rather than silently under-estimating S_WE."""
    # 908 markers: the empty-bin guard first fires around nbins~90 (>5% of bins hold <=1 marker);
    # by nbins=200 (~4.5 markers/bin, ~140 empty bins) the marker-quadrature S_WE would collapse ~3x.
    with pytest.raises(ValueError, match="too fine"):
        vv.compute_wing_area_moments(nbins=200)


def test_area_moments_missing_vertex_file_raises(tmp_path):
    """A missing vertex file raises a clear FileNotFoundError (not a bare loadtxt OSError)."""
    with pytest.raises(FileNotFoundError, match="wing.vertex not found"):
        vv.compute_wing_area_moments(vertex_path=tmp_path / "nope.vertex")


def test_erratum_checked():
    """Scenario: erratum verdict is pinned as a committed artifact (JFM 956 E1, 2023)."""
    assert "956 E1" in vv.ERRATUM_CHECKED
    assert "no coefficient change" in vv.ERRATUM_CHECKED
