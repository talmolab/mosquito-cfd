"""Tests for force_surrogate.normalization (TDD red phase).

van Veen convention (standardize-force-normalization): F_ref = 0.5*rho*omega^2*S_yy,
parameterized on the radius of gyration r_gyr (= R_GYRATION), NOT the tip arm. The
validated point now reproduces f_ref ~= 200.27 (was 624.79 under the old peak-tip
convention). See openspec/changes/standardize-force-normalization.
"""

import numpy as np
import pytest

from mosquito_cfd.force_surrogate import (
    compute_force_coefficients,
    compute_force_reference,
    compute_moment_coefficient,
    compute_moment_reference,
)
from mosquito_cfd.force_surrogate.constants import (
    CHORD,
    R_GYRATION,
    R_TIP,
    RHO,
    SPAN,
    VALIDATED_F_STAR,
    VALIDATED_PHI_AMP_DEG,
    VALIDATED_PITCH_AMP_DEG,
)

_VERTEX_FILE = "examples/flapping_wing/wing.vertex"  # committed geometry; 908 markers


def test_radius_of_gyration_traced_from_wing_vertex():
    """R_GYRATION is the wing's radius of gyration, traced to the committed markers.

    Spec scenario: Radius of gyration is traced to the committed wing geometry. The
    normalization arm is sqrt(mean(r^2)) (the van Veen S_yy radius), NOT a magic
    constant. NOTE: R_TIP is used *inside* the hinge-offset formula and must survive a
    rename sweep.
    """
    verts = np.loadtxt(_VERTEX_FILE, skiprows=1)  # cols x(chord), y, z
    # Span is the widest-extent axis: T2a re-orients it to y (col 1); the legacy geometry used
    # z (col 2). Detecting it keeps r_gyr orientation-invariant (it depends on the span
    # distribution, not the axis label), so this guard survives the axis-convention refactor.
    span_col = int(np.argmax(np.ptp(verts, axis=0)))
    span = verts[:, span_col]
    r = span + (R_TIP - span.max())  # hinge-distance; tip marker -> R_TIP
    r_gyr = np.sqrt(np.mean(r**2))
    assert r_gyr == pytest.approx(R_GYRATION, rel=1e-3)
    assert R_GYRATION < R_TIP  # load is tip-weighted -> gyration arm < tip arm


def test_validated_constants_reproduce_reference_point():
    """The committed baseline constants reproduce the documented validated F_ref."""
    assert (VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, VALIDATED_PITCH_AMP_DEG) == (
        1.0,
        70.0,
        45.0,
    )
    ref = compute_force_reference(
        VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, rho=RHO
    )
    assert ref.f_ref == pytest.approx(200.27, rel=1e-3)


def test_compute_force_reference_matches_validated():
    """Reference normalization reproduces the documented validated values.

    van Veen eq 1.1: F_ref = 0.5*rho*omega^2*S_yy with S_yy = r_gyr^2 * area.
    """
    ref = compute_force_reference(
        f_star=1.0,
        phi_amp_deg=70.0,
        r_gyr=R_GYRATION,
        span=3.0,
        chord=1.0,
        rho=1.0,
    )
    assert ref.u_ref == pytest.approx(13.04, rel=1e-3)
    assert ref.q_ref == pytest.approx(85.0, rel=1e-3)
    assert ref.area == pytest.approx(2.3562, rel=1e-3)
    assert ref.f_ref == pytest.approx(200.27, rel=1e-3)
    # f_ref == 0.5*rho*omega_peak^2 * S_yy, S_yy = r_gyr^2 * area
    omega_peak = 2.0 * np.pi * 1.0 * np.radians(70.0)
    s_yy = R_GYRATION**2 * ref.area
    assert ref.f_ref == pytest.approx(0.5 * 1.0 * omega_peak**2 * s_yy, rel=1e-9)
    assert s_yy == pytest.approx(6.797, rel=1e-3)


def test_compute_force_reference_parameterized():
    """F_ref is a pure function of inputs, not hardcoded."""
    base = compute_force_reference(1.0, 70.0, R_GYRATION, 3.0, 1.0)
    smaller = compute_force_reference(1.0, 35.0, R_GYRATION, 3.0, 1.0)
    assert smaller.u_ref < base.u_ref
    assert smaller.f_ref < base.f_ref
    doubled = compute_force_reference(2.0, 70.0, R_GYRATION, 3.0, 1.0)
    assert doubled.u_ref == pytest.approx(2 * base.u_ref, rel=1e-12)


def test_compute_force_coefficients_array_and_scalar():
    """Coefficients are F / F_ref element-wise, preserving shape."""
    fx = np.array([50.0, -30.0])
    fy = np.array([0.0, 20.0])
    fz = np.array([10.0, -40.0])
    cc = compute_force_coefficients(fx, fy, fz, 100.0)
    np.testing.assert_allclose(cc.cf_x, [0.5, -0.3])
    np.testing.assert_allclose(cc.cf_y, [0.0, 0.2])
    np.testing.assert_allclose(cc.cf_z, [0.1, -0.4])
    assert cc.cf_x.shape == fx.shape
    scalar = compute_force_coefficients(50.0, 0.0, 10.0, 100.0)
    assert float(scalar.cf_x) == pytest.approx(0.5)


def test_compute_force_coefficients_nonpositive_reference_raises():
    """A zero or negative reference is rejected (avoids div-by-zero / sign flip)."""
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, 0.0)
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, -100.0)


def test_compute_force_coefficients_mismatched_shapes_raise():
    """fx/fy/fz of differing shape raise rather than silently misalign."""
    with pytest.raises(ValueError):
        compute_force_coefficients([1.0, 2.0, 3.0], [1.0, 2.0], [1.0], 100.0)


def test_compute_force_coefficients_empty_and_nan():
    """Empty input -> empty output; NaN force -> NaN coefficient (no crash)."""
    empty = compute_force_coefficients(np.array([]), np.array([]), np.array([]), 100.0)
    assert empty.cf_x.shape == (0,)
    assert empty.cf_x.size == 0
    nan_cc = compute_force_coefficients(
        np.array([np.nan, 50.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        100.0,
    )
    assert np.isnan(nan_cc.cf_x[0])
    assert nan_cc.cf_x[1] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Moment normalization (PR4) — spec: "Single-source moment normalization"
# ---------------------------------------------------------------------------


def test_compute_moment_reference_at_validated_point():
    """M_ref = q_ref*area*chord reproduces the validated value (rtol=1e-3).

    Spec scenario: Moment reference at the validated point.
    """
    ref = compute_moment_reference(
        f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=3.0, chord=1.0, rho=1.0
    )
    assert ref.m_ref == pytest.approx(200.27, rel=1e-3)
    assert ref.length == 1.0


def test_compute_moment_reference_scales_with_chord_and_reuses_force_ref():
    """m_ref scales as chord**2 and equals f_ref*chord (single-source reuse).

    Spec scenario: Moment reference scales with the chord length scale and reuses
    the force reference. Note chord enters m_ref TWICE -- once via area
    (S = pi/4*span*chord) and once via the explicit length scale L = chord -- so
    m_ref scales quadratically with chord. The robust single-source check is the
    equality m_ref == compute_force_reference(same args).f_ref * chord at a NON-unit
    chord (trivially true at chord=1.0): a divergent re-implementation of q_ref/area
    inside compute_moment_reference would break it (CC-3).
    """
    one = compute_moment_reference(1.0, 70.0, R_GYRATION, 3.0, 1.0)
    two = compute_moment_reference(1.0, 70.0, R_GYRATION, 3.0, 2.0)
    # chord enters via area AND via L -> quadratic, so 2x chord -> 4x m_ref.
    assert two.m_ref == pytest.approx(4.0 * one.m_ref, rel=1e-12)
    force_ref = compute_force_reference(1.0, 70.0, R_GYRATION, 3.0, 2.0)
    assert two.m_ref == pytest.approx(force_ref.f_ref * 2.0, rel=1e-12)


def test_compute_moment_coefficient_array_and_scalar():
    """Coefficients are M / M_ref element-wise, preserving shape.

    Spec scenario: Moment coefficients. Uses the fixture's round moments under
    M_ref=100 so the decimals are exact.
    """
    mx = np.array([20.0, -40.0])
    my = np.array([-60.0, 10.0])
    mz = np.array([80.0, 30.0])
    cc = compute_moment_coefficient(mx, my, mz, 100.0)
    np.testing.assert_allclose(cc.cf_mx, [0.2, -0.4])
    np.testing.assert_allclose(cc.cf_my, [-0.6, 0.1])
    np.testing.assert_allclose(cc.cf_mz, [0.8, 0.3])
    assert cc.cf_mx.shape == mx.shape
    scalar = compute_moment_coefficient(20.0, -60.0, 80.0, 100.0)
    assert float(scalar.cf_mx) == pytest.approx(0.2)


def test_compute_moment_coefficient_nonpositive_reference_raises():
    """A zero or negative M_ref is rejected.

    Spec scenario: Non-positive moment reference rejected.
    """
    with pytest.raises(ValueError):
        compute_moment_coefficient(1.0, 2.0, 3.0, 0.0)
    with pytest.raises(ValueError):
        compute_moment_coefficient(1.0, 2.0, 3.0, -100.0)


def test_compute_moment_coefficient_mismatched_shapes_raise():
    """mx/my/mz of differing shape raise rather than silently misalign.

    Spec scenario: Mismatched moment shapes rejected.
    """
    with pytest.raises(ValueError):
        compute_moment_coefficient([1.0, 2.0, 3.0], [1.0, 2.0], [1.0], 100.0)


def test_compute_moment_coefficient_empty_and_nan():
    """Empty -> empty; NaN moment -> NaN coefficient (no crash).

    Spec scenario: Empty and NaN moments.
    """
    empty = compute_moment_coefficient(np.array([]), np.array([]), np.array([]), 100.0)
    assert empty.cf_mx.shape == (0,)
    nan_cc = compute_moment_coefficient(
        np.array([np.nan, 20.0]),
        np.array([0.0, 0.0]),
        np.array([0.0, 0.0]),
        100.0,
    )
    assert np.isnan(nan_cc.cf_mx[0])
    assert nan_cc.cf_mx[1] == pytest.approx(0.2)
