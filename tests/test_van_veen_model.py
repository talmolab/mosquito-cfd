"""Tests for the van Veen (2022) quasi-steady force model (Tier T4, TDD).

Pure known-answer / guard tests for ``benchmarks.van_veen_model``: the three components
(translational + added-mass + Wagner), the pinned coefficients + not-loosened guard, eq 3.12 in
degrees, the input contract (angle of attack in ``[0, pi/2]``, non-negative speed), the function
that derives those inputs from the wing's motion, the area moments (``S_yy = R_GYRATION**2*area``,
``S_cy`` the closed form of ``integral c**2*y dy``, the ``S_WE`` marker quadrature, the planform
guard), and the erratum provenance literal. See openspec/changes/fix-van-veen-model-regrade-t4.
"""

from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.benchmarks import van_veen_model as vv
from mosquito_cfd.benchmarks.wing_kinematics import (
    euler_angles,
    rotation_matrix,
    stroke_rate,
)
from mosquito_cfd.force_surrogate.constants import RHO

_WING = Path("examples/flapping_wing/wing.vertex")


def _omega_ref(f_star: float = 1.0, phi_amp_deg: float = 70.0) -> float:
    """Peak stroke angular velocity omega_ref = 2*pi*f_star*phi_amp_rad."""
    return 2.0 * np.pi * f_star * np.radians(phi_amp_deg)


def _write_vertex(path: Path, xy: np.ndarray) -> Path:
    """Write ``(x chord, y span)`` markers in the wing.vertex layout (count line, then x y z)."""
    verts = np.column_stack([xy, np.zeros(len(xy))])
    np.savetxt(path, verts, header=str(len(verts)), comments="", fmt="%.10e")
    return path


def _ellipse_markers(nx: int, ny: int) -> np.ndarray:
    """Grid markers filling the nominal ellipse (chord 1, span 3, centred like wing.vertex)."""
    x, y = np.meshgrid(np.linspace(-0.5, 0.5, nx), np.linspace(-1.5, 1.5, ny))
    inside = (x / 0.5) ** 2 + (y / 1.5) ** 2 <= 1.0
    return np.column_stack([x[inside], y[inside]])


@pytest.fixture(scope="module")
def dense_ellipse(tmp_path_factory) -> Path:
    """A nominal-ellipse wing file with more than 2e5 markers."""
    xy = _ellipse_markers(301, 901)
    assert len(xy) >= 200_000
    return _write_vertex(tmp_path_factory.mktemp("wing") / "ellipse.vertex", xy)


# --- Components -------------------------------------------------------------------------------


def test_components_match_hand_computed():
    """Scenario: components equal hand-computed values at a reference state (90 deg, wd=0)."""
    m = vv.compute_wing_area_moments()
    omega = _omega_ref()
    fx_t, fz_t = vv.translational_force(np.pi / 2, omega, s_yy=m.s_yy)
    q = 0.5 * RHO * omega**2 * m.s_yy
    assert fz_t == pytest.approx(q * 3.13)
    # Eq 3.12 at 90 degrees: 8.5e-5*8100 - 1.2e-2*90 + 0.41 = 0.0185.
    assert fx_t == pytest.approx(q * 0.0185, rel=1e-9)
    _, fz_am = vv.added_mass_force_component(np.pi / 2, 0.0, s_cy=m.s_cy)
    _, fz_we = vv.wagner_force(np.pi / 2, omega, 0.0, s_we=m.s_we)
    assert fz_am == pytest.approx(0.0)
    assert fz_we == pytest.approx(0.0)


def test_eq_3_12_is_evaluated_in_degrees():
    """Scenario: eq 3.12 in degrees, checked against the paper's own statements."""
    omega, s_yy = _omega_ref(), 6.797
    q = 0.5 * RHO * omega**2 * s_yy

    def coeff(deg: float) -> tuple[float, float]:
        fx, fz = vv.translational_force(np.radians(deg), omega, s_yy=s_yy)
        return float(fx / q), float(fz / q)

    for deg, want in ((0.0, 0.41), (45.0, 0.042125), (90.0, 0.0185)):
        assert coeff(deg)[0] == pytest.approx(want, rel=1e-9, abs=1e-12)
    # Section 3.1.1: above 36 deg the tangential-to-normal ratio is -0.01 +/- 0.01. In radians it
    # is above 0.12 at every one of these angles.
    for deg in (45, 54, 63, 72, 81, 90):
        cx, cz = coeff(deg)
        assert cz == pytest.approx(3.13 * np.sin(np.radians(deg)))
        assert abs(cx / cz) < 0.03, deg
    # Section 3.1.2: the coefficient decreases with angle of attack.
    assert coeff(9.0)[0] > 5.0 * coeff(45.0)[0]


def test_wagner_sign_for_decelerating_wing():
    """Scenario: Wagner sign generalization is finite and oppositely signed for omega_dot < 0."""
    m = vv.compute_wing_area_moments()
    omega, alpha = _omega_ref(), np.radians(45.0)
    _, fz_accel = vv.wagner_force(alpha, omega, +4.0e6, s_we=m.s_we)
    _, fz_decel = vv.wagner_force(alpha, omega, -4.0e6, s_we=m.s_we)
    assert np.isfinite(fz_accel) and np.isfinite(fz_decel)  # no sqrt of a negative
    assert np.sign(fz_accel) == -np.sign(fz_decel)  # sign(omega_dot) flips it
    assert fz_accel != 0.0


_MOM = dict(s_yy=6.797, s_cy=3.0, s_we=3.978)
_COMPONENTS = {
    "translational": lambda a, w, wd: vv.translational_force(a, w, s_yy=6.797),
    "added_mass": lambda a, w, wd: vv.added_mass_force_component(a, wd, s_cy=3.0),
    "wagner": lambda a, w, wd: vv.wagner_force(a, w, wd, s_we=3.978),
    "total": lambda a, w, wd: vv.total_force(a, w, wd, **_MOM),
}
_BAD_ALPHA = {
    "negative": -np.pi / 4,
    "just_above_90": np.nextafter(np.pi / 2, 4.0),
    "one_bad_element": np.array([0.1, 0.2, -0.3, 0.4]),
    "one_element_above": np.array([0.1, 2.0, 0.3]),
}


@pytest.mark.parametrize("component", list(_COMPONENTS))
@pytest.mark.parametrize("alpha", list(_BAD_ALPHA.values()), ids=list(_BAD_ALPHA))
def test_alpha_outside_the_input_domain_raises(component, alpha):
    """Scenario: an angle of attack outside [0, pi/2] raises, naming alpha (any element)."""
    with pytest.raises(ValueError, match=r"^alpha must be an angle of attack"):
        _COMPONENTS[component](alpha, 3.0, 1.0)


@pytest.mark.parametrize("component", ["translational", "wagner", "total"])
@pytest.mark.parametrize(
    "omega", [-1.0, np.array([1.0, 2.0, -0.5])], ids=["scalar", "one_element"]
)
def test_negative_omega_raises(component, omega):
    """Scenario: a negative stroke speed raises, naming omega (any element)."""
    with pytest.raises(ValueError, match=r"^omega must be a non-negative stroke speed"):
        _COMPONENTS[component](0.5, omega, 1.0)


def test_float32_right_angle_is_named_in_the_error():
    """float32(pi/2) is above the float64 bound; the message shows the excess, not "1.5708"."""
    with pytest.raises(ValueError, match="alpha must be an angle of attack") as err:
        vv.translational_force(np.array([0.1, np.float32(np.pi / 2)]), 3.0, s_yy=6.797)
    assert "1.5707963705062866" in str(err.value)
    assert "float32" in str(err.value)


@pytest.mark.parametrize("component", list(_COMPONENTS))
def test_domain_edges_are_accepted(component):
    """alpha = 0, -0.0 and pi/2 and omega = 0 are inside the domain; omega = 0 gives no force."""
    for alpha in (0.0, -0.0, np.pi / 2):
        fx, fz = _COMPONENTS[component](alpha, 3.0, 1.0)
        assert np.isfinite(fx) and np.isfinite(fz)
    if component in ("translational", "wagner"):
        fx, fz = _COMPONENTS[component](0.5, 0.0, 1.0)
        assert fx == 0.0 and fz == 0.0


@pytest.mark.parametrize("component", list(_COMPONENTS))
def test_non_finite_input_still_raises_the_non_finite_error(component):
    """A NaN is reported as non-finite, not as out of the domain."""
    with pytest.raises(ValueError, match="non-finite"):
        _COMPONENTS[component](np.nan, 3.0, 1.0)
    with pytest.raises(ValueError, match="non-finite"):
        _COMPONENTS[component](0.5, np.inf, np.inf)


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
    omega = np.abs(_omega_ref() * np.cos(2 * np.pi * t))
    omega_dot = -_omega_ref() * (2 * np.pi) * np.sin(2 * np.pi * t)
    alpha = np.abs(np.radians(45.0) * np.cos(2 * np.pi * t))
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


# --- Inputs derived from the wing's motion ----------------------------------------------------

_STROKE, _PITCH = np.radians(70.0), np.radians(45.0)


def _kinematics(t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Production ``(pitch, phi_dot, phi_ddot)`` at times ``t``."""
    pitch = np.array(
        [
            euler_angles(
                x, frequency=1.0, stroke_amp_rad=_STROKE, pitch_amp_rad=_PITCH
            )[1]
            for x in t
        ]
    )
    rates = np.array([stroke_rate(x, frequency=1.0, stroke_amp_rad=_STROKE) for x in t])
    return pitch, rates[:, 0], rates[:, 1]


def _model_total_cf(t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Model-total body-frame ``(CF_chord, CF_normal)`` through the input function."""
    inp = vv.model_inputs(*_kinematics(t))
    fx, fz = vv.total_force(inp.alpha, inp.omega, inp.omega_dot, **_MOM)
    f_ref = 0.5 * RHO * _omega_ref() ** 2 * _MOM["s_yy"]
    return fx * inp.chord_dir / f_ref, fz * inp.normal_dir / f_ref


def test_model_is_fed_the_angle_of_attack_on_both_half_strokes():
    """Scenario: the model is fed the angle of attack on both half-strokes (hand-computed)."""
    t = np.array([0.0, 0.5])
    inp = vv.model_inputs(*_kinematics(t))
    np.testing.assert_allclose(inp.alpha, np.radians(45.0), rtol=1e-12)
    chord, normal = _model_total_cf(t)
    # phi_ddot is 0 at mid-stroke (to roundoff at t = 0.5), so only the translational term is left.
    np.testing.assert_allclose(normal, 3.13 * np.sin(np.radians(45.0)), rtol=1e-6)
    np.testing.assert_allclose(chord, [+0.042125, -0.042125], rtol=1e-6)

    t = np.linspace(0.0, 1.0, 2001)
    pitch, phi_dot, phi_ddot = _kinematics(t)
    inp = vv.model_inputs(pitch, phi_dot, phi_ddot)
    assert inp.alpha.min() >= 0.0 and inp.alpha.max() <= np.pi / 2
    assert inp.omega.min() >= 0.0
    # Each half-stroke runs reversal -> mid-stroke -> reversal: speeding up, then slowing down.
    # Reversals at t = 0.25, 0.75; mid-strokes at 0, 0.5, 1.
    margin = 0.01
    speeding_up = ((t > 0.25 + margin) & (t < 0.5 - margin)) | (
        (t > 0.75 + margin) & (t < 1.0 - margin)
    )
    slowing_down = ((t > margin) & (t < 0.25 - margin)) | (
        (t > 0.5 + margin) & (t < 0.75 - margin)
    )
    assert (inp.omega_dot[speeding_up] > 0).all()
    assert (inp.omega_dot[slowing_down] < 0).all()


# (pitch deg, sign of phi_dot) -> (angle of attack deg, chord direction, normal direction)
_QUADRANTS = [
    (+45.0, +1, 45.0, +1, +1),
    (+45.0, -1, 45.0, -1, -1),
    (-45.0, +1, 45.0, +1, -1),
    (-45.0, -1, 45.0, -1, +1),
    (+120.0, +1, 60.0, -1, +1),
    (+120.0, -1, 60.0, +1, -1),
    (-120.0, +1, 60.0, -1, -1),
    (-120.0, -1, 60.0, +1, +1),
]


@pytest.mark.parametrize("pitch_deg, s, aoa_deg, chord_dir, normal_dir", _QUADRANTS)
def test_directions_are_right_in_every_quadrant(
    pitch_deg, s, aoa_deg, chord_dir, normal_dir
):
    """Scenario: directions are right in every quadrant, not only on the sinusoid."""
    inp = vv.model_inputs(np.radians(pitch_deg), 2.5 * s, 0.7)
    assert np.degrees(inp.alpha) == pytest.approx(aoa_deg, abs=1e-9)
    assert inp.omega == 2.5
    assert inp.omega_dot == pytest.approx(0.7 * s)
    assert (inp.chord_dir, inp.normal_dir) == (chord_dir, normal_dir)


def test_zero_velocity_component_has_no_direction():
    """At pitch +90 deg there is no chord-wise motion; at pitch 0 there is no normal motion."""
    vertical = vv.model_inputs(np.pi / 2, 1.0, 0.0)
    assert vertical.chord_dir == 0.0 and vertical.normal_dir == 1.0
    assert vertical.alpha == pytest.approx(np.pi / 2)
    flat = vv.model_inputs(0.0, 1.0, 0.0)
    assert flat.normal_dir == 0.0 and flat.chord_dir == 1.0
    assert flat.alpha == 0.0
    # Only roundoff is treated as zero: a pitch of 1e-9 rad still has a normal direction.
    small = vv.model_inputs(1e-9, 1.0, 0.0)
    assert small.normal_dir == 1.0 and small.alpha == pytest.approx(1e-9)
    nearly_vertical = vv.model_inputs(np.pi / 2 - 1e-9, 1.0, 0.0)
    assert nearly_vertical.chord_dir == 1.0
    # No direction is ever a negative zero.
    for value in (vertical.chord_dir, flat.normal_dir):
        assert not np.signbit(value)


def _inputs_from_rotation(phi_of_t, pitch_of_t, t: float, h: float = 1e-6):
    """``(alpha, speed, chord_dir, normal_dir)`` of a span point from a central difference of R."""
    tip = np.array([0.0, 1.0, 0.0])

    def lab(time: float) -> np.ndarray:
        return rotation_matrix(phi_of_t(time), pitch_of_t(time)) @ tip

    v_lab = (lab(t + h) - lab(t - h)) / (2.0 * h)
    v = rotation_matrix(phi_of_t(t), pitch_of_t(t)).T @ v_lab
    return (
        np.arctan2(abs(v[2]), abs(v[0])),
        float(np.linalg.norm(v)),
        -np.sign(v[0]),
        -np.sign(v[2]),
    )


def test_derivation_agrees_with_the_canonical_rotation():
    """Scenario: the derivation agrees with ``wing_kinematics.rotation_matrix``."""
    w = 2.0 * np.pi

    def check(phi_of_t, pitch_of_t, phi_dot_of_t, phi_ddot_of_t, times):
        for t in times:
            want = _inputs_from_rotation(phi_of_t, pitch_of_t, t)
            got = vv.model_inputs(pitch_of_t(t), phi_dot_of_t(t), phi_ddot_of_t(t))
            np.testing.assert_allclose(
                [got.alpha, got.omega, got.chord_dir, got.normal_dir],
                want,
                rtol=1e-7,
                atol=1e-8,
                err_msg=f"t={t}",
            )

    times = np.linspace(0.0, 1.0, 200, endpoint=False)
    times = times[(np.abs(times - 0.25) > 0.01) & (np.abs(times - 0.75) > 0.01)]
    assert len(times) > 180
    check(
        lambda t: _STROKE * np.sin(w * t),
        lambda t: _PITCH * np.cos(w * t),
        lambda t: _STROKE * w * np.cos(w * t),
        lambda t: -_STROKE * w**2 * np.sin(w * t),
        times,
    )
    # A second, non-sinusoidal trajectory: constant pitch -45 deg, phi = t.
    check(
        lambda t: t,
        lambda t: -np.pi / 4,
        lambda t: 1.0,
        lambda t: 0.0,
        times,
    )


@pytest.mark.parametrize("pitch", [0.0, 0.3])
@pytest.mark.parametrize("phi_ddot", [+7.0, -7.0])
def test_stroke_reversal_is_well_defined(pitch, phi_ddot):
    """Scenario: at a literal phi_dot = 0 the direction is the way the wing is about to move."""
    inp = vv.model_inputs(pitch, 0.0, phi_ddot)
    assert inp.omega == 0.0
    assert inp.omega_dot == abs(phi_ddot)
    assert inp.chord_dir == np.sign(phi_ddot)
    assert inp.normal_dir == (0.0 if pitch == 0.0 else np.sign(phi_ddot))
    ax, _ = vv.added_mass_force_component(inp.alpha, inp.omega_dot, s_cy=3.0)
    want = RHO * phi_ddot * 3.0 * vv.C_FXA_AM * np.cos(pitch)
    assert ax * inp.chord_dir == pytest.approx(want)
    assert want != 0.0


def test_rest_returns_zeros():
    """With phi_dot = phi_ddot = 0 every output is zero and finite."""
    inp = vv.model_inputs(0.3, 0.0, 0.0)
    for value in (inp.alpha, inp.omega, inp.omega_dot, inp.chord_dir, inp.normal_dir):
        assert value == 0.0 and np.isfinite(value)


def test_added_mass_chord_series_is_the_reaction_to_the_body_frame_acceleration():
    """On the production kinematics the added-mass chord force is rho*phi_ddot*S_cy*0.104*cos."""
    t = np.linspace(0.0, 1.0, 4001)
    pitch, phi_dot, phi_ddot = _kinematics(t)
    inp = vv.model_inputs(pitch, phi_dot, phi_ddot)
    ax, az = vv.added_mass_force_component(inp.alpha, inp.omega_dot, s_cy=3.0)
    np.testing.assert_allclose(
        ax * inp.chord_dir,
        RHO * phi_ddot * 3.0 * vv.C_FXA_AM * np.cos(pitch),
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        az * inp.normal_dir,
        RHO * phi_ddot * 3.0 * vv.C_FZA_AM * np.sin(pitch),
        rtol=1e-12,
        atol=1e-12,
    )


def test_model_inputs_docstring_names_its_assumptions():
    """The docstring names both symmetries and the missing pitch-rotation term."""
    doc = " ".join(vv.model_inputs.__doc__.split())
    assert "chord midline" in doc and "its own plane" in doc
    assert "no pitch-rotation term" in doc


# --- Area moments -----------------------------------------------------------------------------


def _swe_analytic_ellipse() -> float:
    """S_WE from an INDEPENDENT analytic elliptic-planform quadrature (different code path).

    Fits an ellipse ``c(y) = c_max*sqrt(1 - ((y-yc)/a)**2)`` to the committed markers' hinge-distance
    span and chord extent, then integrates ``sqrt(c**3 * y**3)`` on a fine 20k-point grid — no
    binning, a genuinely different method from the module's marker quadrature.
    """
    verts = np.loadtxt(_WING, skiprows=1)
    x = verts[:, 0]
    sc = verts[:, int(np.argmax(np.ptp(verts, axis=0)))]
    y = sc + (3.0 - sc.max())  # R_TIP hinge offset
    yc, a = 0.5 * (y.min() + y.max()), 0.5 * (y.max() - y.min())
    yy = np.linspace(y.min(), y.max(), 20000)
    cc = np.ptp(x) * np.sqrt(np.clip(1 - ((yy - yc) / a) ** 2, 0.0, None))
    return float(np.trapezoid(np.sqrt(cc**3 * yy**3), yy))


def test_area_moments_hinge_origin():
    """Scenario: S_yy hinge-origin (=R_GYRATION**2*area, NOT the marker quadrature); S_WE
    cross-checked against an INDEPENDENT analytic quadrature; degenerate planform raises."""
    m = vv.compute_wing_area_moments()
    assert m.s_yy == pytest.approx(
        6.797, rel=1e-3
    )  # = R_GYRATION**2 * area, reconciles F_ref
    # S_WE marker quadrature (~3.98), cross-checked against a genuinely INDEPENDENT analytic
    # elliptic quadrature (a different integrator, not a re-binning) — they agree to ~0.1%.
    assert m.s_we == pytest.approx(3.98, rel=1e-2)
    assert m.s_we == pytest.approx(_swe_analytic_ellipse(), rel=0.02)
    # A hinge-origin S_yy quadrature over the markers would give ~6.24 (marker area < elliptic
    # area by ~7%); the spec deliberately does NOT use it for S_yy. Sanity: 6.797 != ~6.24.
    assert abs(m.s_yy - 6.24) > 0.3
    # Degenerate planform raises.
    with pytest.raises(ValueError, match="degenerate planform"):
        vv.compute_wing_area_moments(span=0.0)


def test_s_cy_is_the_chord_based_integral_with_a_known_answer():
    """Scenario: S_cy = integral c**2*y dy = 3.0 for the nominal ellipse, not S_yy."""
    m = vv.compute_wing_area_moments()
    assert m.s_cy == pytest.approx(3.0, rel=1e-12)
    assert abs(m.s_cy - m.s_yy) > 3.0
    # Independent fine quadrature of the analytic ellipse (root at the hinge, span 3, chord 1).
    y = np.linspace(0.0, 3.0, 2_000_001)
    c2 = 1.0 - ((y - 1.5) / 1.5) ** 2
    assert m.s_cy == pytest.approx(float(np.trapezoid(c2 * y, y)), abs=1e-6)
    # The same ellipse moved one chord outboard.
    assert vv.s_cy_closed_form(r_tip=4.0) == pytest.approx(5.0, rel=1e-12)
    # The ellipse spans [r_tip - span, r_tip]: it reaches inboard of the hinge when r_tip < span.
    assert vv.s_cy_closed_form(r_tip=3.0) == pytest.approx(3.0, rel=1e-12)
    for bad in (np.nextafter(3.0, 0.0), 2.0, 1.5, 1.4, 0.0, -1.0, np.nan, np.inf):
        with pytest.raises(ValueError, match=r"^r_tip="):
            vv.s_cy_closed_form(r_tip=bad)
        with pytest.raises(ValueError, match=r"^r_tip="):
            vv.compute_wing_area_moments(r_tip=bad)
    # r_tip = span/2 used to reach a division by zero in the planform guard.
    with pytest.raises(ValueError, match=r"^r_tip="):
        vv.compute_wing_area_moments(span=6.0)
    for kwargs in ({"span": -3.0, "chord": -1.0}, {"chord": 0.0}, {"span": np.nan}):
        with pytest.raises(
            ValueError, match="span and chord must be finite and positive"
        ):
            vv.s_cy_closed_form(**kwargs)


def test_s_cy_marker_quadrature_of_the_committed_wing_is_pinned():
    """The marker S_cy is a reported cross-check: 2.70, below the closed form by under 15 %."""
    marker = vv.s_cy_marker_quadrature()
    assert marker == pytest.approx(2.7033, abs=5e-3)
    assert 0.0 < (3.0 - marker) / 3.0 < 0.15


def test_s_cy_marker_quadrature_converges_on_a_dense_ellipse(dense_ellipse):
    """On a dense nominal ellipse the estimator is biased high and improves with more bins."""
    err30 = abs(vv.s_cy_marker_quadrature(dense_ellipse, nbins=30) - 3.0) / 3.0
    err120 = abs(vv.s_cy_marker_quadrature(dense_ellipse, nbins=120) - 3.0) / 3.0
    assert err30 < 0.05
    assert err120 < 0.015
    assert err120 < err30
    doc = " ".join(vv._marker_moment_quadrature.__doc__.split())
    assert "biased high" in doc


def test_s_cy_marker_quadrature_too_fine_binning_raises():
    """A too-fine nbins raises for the S_cy marker quadrature as it does for S_WE."""
    with pytest.raises(ValueError, match="too fine"):
        vv.s_cy_marker_quadrature(nbins=200)


@pytest.mark.parametrize("nbins", [0, 1, 2, 4, -1, -5, 30.0, True, None, "30"])
def test_bad_nbins_is_reported_as_nbins_not_as_a_planform_mismatch(nbins):
    """A bin count that cannot give a quadrature is its own error, in both entry points."""
    for call in (vv.compute_wing_area_moments, vv.s_cy_marker_quadrature):
        with pytest.raises(ValueError, match=r"^nbins must be an integer >= 5"):
            call(nbins=nbins)
    assert vv.s_cy_marker_quadrature(nbins=5) > 0


@pytest.mark.parametrize(
    "r_tip", [np.nan, np.inf, 0.0, -1.0, 0.5, 1.0, 2.45, 2.94, 2.9499]
)
def test_marker_quadrature_rejects_a_bad_r_tip(r_tip):
    """The public cross-check validates r_tip itself.

    The committed markers span 2.95, so any r_tip below that puts markers inboard of the hinge;
    r_tip = 1.0 used to return a negative S_cy.
    """
    with pytest.raises(ValueError, match=r"^r_tip="):
        vv.s_cy_marker_quadrature(r_tip=r_tip)


def test_marker_quadrature_accepts_r_tip_at_the_marker_span():
    """r_tip equal to the markers' own span puts the root marker exactly on the hinge."""
    assert vv.s_cy_marker_quadrature(r_tip=2.95) > 0
    assert vv.s_cy_marker_quadrature(r_tip=4.0) > vv.s_cy_marker_quadrature()


def test_profile_moments_validates_its_profile():
    """``profile_moments`` refuses a profile it would integrate to a wrong number."""
    y = np.linspace(0.0, 3.0, 2001)
    c = np.sqrt(np.clip(1.0 - ((y - 1.5) / 1.5) ** 2, 0.0, None))
    s_cy, s_we = vv.profile_moments(c, y)
    assert s_cy == pytest.approx(3.0, rel=1e-4) and s_we == pytest.approx(
        4.304, rel=1e-3
    )
    rng = np.random.default_rng(0)
    shuffled = rng.permutation(len(y))
    bad = {
        "descending y": (c[::-1], y[::-1]),
        "shuffled y": (c[shuffled], y[shuffled]),
        "NaN chord": (np.where(np.arange(len(c)) == 7, np.nan, c), y),
        "NaN y": (c, np.where(np.arange(len(y)) == 7, np.nan, y)),
        "length mismatch": (c[:-1], y),
        "single point": (c[:1], y[:1]),
        "empty": (c[:0], y[:0]),
        "2-D": (np.stack([c, c]), np.stack([y, y])),
    }
    for name, (cc, yy) in bad.items():
        with pytest.raises(ValueError, match=r"^profile_moments: "):
            vv.profile_moments(cc, yy)
        assert name  # keeps the case name in the traceback locals
    # Repeated stations are allowed (a step in the profile), as is a hair of negative y.
    vv.profile_moments([0.0, 1.0, 1.0, 0.0], [-1e-5, 1.0, 1.0, 2.0])


def test_planform_mismatch_guard(tmp_path, dense_ellipse):
    """A wing file whose marker S_cy is over 15 % from the closed form raises, naming both."""
    x, y = np.meshgrid(np.linspace(-0.5, 0.5, 61), np.linspace(-1.5, 1.5, 181))
    rectangle = _write_vertex(
        tmp_path / "rectangle.vertex", np.column_stack([x.ravel(), y.ravel()])
    )
    committed = np.loadtxt(_WING, skiprows=1)[:, :2]
    cases = {"rectangle": rectangle}
    for scale in (0.8, 0.95):
        cases[f"chord x{scale}"] = _write_vertex(
            tmp_path / f"chord_{scale}.vertex", committed * np.array([scale, 1.0])
        )
    # Bracket the 15 % limit itself: the committed wing sits at -9.9 %, so chord scalings of
    # 0.975 and 0.965 land just inside (-14.3 %) and just outside (-16.1 %).
    inside = _write_vertex(
        tmp_path / "chord_0.975.vertex", committed * np.array([0.975, 1.0])
    )
    assert (vv.s_cy_marker_quadrature(inside) - 3.0) / 3.0 == pytest.approx(
        -0.143, abs=0.004
    )
    vv.compute_wing_area_moments(inside)
    cases["chord x0.965"] = _write_vertex(
        tmp_path / "chord_0.965.vertex", committed * np.array([0.965, 1.0])
    )
    assert (vv.s_cy_marker_quadrature(cases["chord x0.965"]) - 3.0) / 3.0 == (
        pytest.approx(-0.161, abs=0.004)
    )
    # The upper side: the committed markers are 9.9 % low, so a chord 12 % too large still
    # passes (+13.0 %) and one 13 % too large raises (+15.1 %).
    wider = _write_vertex(
        tmp_path / "chord_1.12.vertex", committed * np.array([1.12, 1.0])
    )
    assert (vv.s_cy_marker_quadrature(wider) - 3.0) / 3.0 == pytest.approx(
        0.130, abs=0.004
    )
    vv.compute_wing_area_moments(wider)
    cases["chord x1.13"] = _write_vertex(
        tmp_path / "chord_1.13.vertex", committed * np.array([1.13, 1.0])
    )
    for name, path in cases.items():
        marker = vv.s_cy_marker_quadrature(path)
        assert abs(marker - 3.0) / 3.0 > 0.15, name
        with pytest.raises(ValueError, match="planform mismatch") as err:
            vv.compute_wing_area_moments(path)
        assert f"{marker:.4f}" in str(err.value) and "3.0000" in str(err.value), name
        assert str(path) in str(err.value)
    # The near-threshold case is about -19 %, measured here.
    near = vv.s_cy_marker_quadrature(cases["chord x0.95"])
    assert (near - 3.0) / 3.0 == pytest.approx(-0.187, abs=0.01)
    # The committed wing and a nominal ellipse do not raise.
    committed_moments = vv.compute_wing_area_moments()
    dense_moments = vv.compute_wing_area_moments(dense_ellipse)
    # S_WE comes from the file that was passed, not from the default wing: the dense nominal
    # ellipse gives the nominal-ellipse value (4.30), the committed markers 3.98.
    assert committed_moments.s_we == pytest.approx(3.978, abs=5e-3)
    assert dense_moments.s_we == pytest.approx(4.304, rel=0.05)
    assert dense_moments.s_we > committed_moments.s_we + 0.2
    doc = " ".join(vv.compute_wing_area_moments.__doc__.split())
    assert "gross planform errors only" in doc


def test_area_moments_guard_too_fine_binning():
    """A too-fine nbins (bins with <=1 marker) raises rather than silently under-estimating S_WE.

    It is reported by its own error, before the planform guard (at 66 bins or more the committed
    wing's marker S_cy already reads about 20 % low).
    """
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
