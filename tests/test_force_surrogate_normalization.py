"""Tests for force_surrogate.normalization (TDD red phase)."""

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
    R_TIP,
    RHO,
    SPAN,
    VALIDATED_F_STAR,
    VALIDATED_PHI_AMP_DEG,
    VALIDATED_PITCH_AMP_DEG,
)


def test_validated_constants_reproduce_reference_point():
    """The committed baseline constants reproduce the documented validated F_ref."""
    assert (VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, VALIDATED_PITCH_AMP_DEG) == (
        1.0,
        70.0,
        45.0,
    )
    ref = compute_force_reference(
        VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_TIP, SPAN, CHORD, rho=RHO
    )
    assert ref.f_ref == pytest.approx(624.79, rel=1e-3)


def test_compute_force_reference_matches_validated():
    """Reference normalization reproduces the documented validated values."""
    ref = compute_force_reference(
        f_star=1.0, phi_amp_deg=70.0, r_tip=3.0, span=3.0, chord=1.0, rho=1.0
    )
    assert ref.u_tip_max == pytest.approx(23.029, rel=1e-3)
    assert ref.q_tip == pytest.approx(265.17, rel=1e-3)
    assert ref.area == pytest.approx(2.3562, rel=1e-3)
    assert ref.f_ref == pytest.approx(624.79, rel=1e-3)


def test_compute_force_reference_parameterized():
    """F_ref is a pure function of inputs, not hardcoded."""
    base = compute_force_reference(1.0, 70.0, 3.0, 3.0, 1.0)
    smaller = compute_force_reference(1.0, 35.0, 3.0, 3.0, 1.0)
    assert smaller.u_tip_max < base.u_tip_max
    assert smaller.f_ref < base.f_ref
    doubled = compute_force_reference(2.0, 70.0, 3.0, 3.0, 1.0)
    assert doubled.u_tip_max == pytest.approx(2 * base.u_tip_max, rel=1e-12)


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
    """M_ref = q_tip*area*chord reproduces the validated value (rtol=1e-3).

    Spec scenario: Moment reference at the validated point.
    """
    ref = compute_moment_reference(
        f_star=1.0, phi_amp_deg=70.0, r_tip=3.0, span=3.0, chord=1.0, rho=1.0
    )
    assert ref.m_ref == pytest.approx(624.79, rel=1e-3)
    assert ref.length == 1.0


def test_compute_moment_reference_scales_with_chord_and_reuses_force_ref():
    """m_ref scales as chord**2 and equals f_ref*chord (single-source reuse).

    Spec scenario: Moment reference scales with the chord length scale and reuses
    the force reference. Note chord enters m_ref TWICE -- once via area
    (S = pi/4*span*chord) and once via the explicit length scale L = chord -- so
    m_ref scales quadratically with chord. The robust single-source check is the
    equality m_ref == compute_force_reference(same args).f_ref * chord at a NON-unit
    chord (trivially true at chord=1.0): a divergent re-implementation of q_tip/area
    inside compute_moment_reference would break it (CC-3).
    """
    one = compute_moment_reference(1.0, 70.0, 3.0, 3.0, 1.0)
    two = compute_moment_reference(1.0, 70.0, 3.0, 3.0, 2.0)
    # chord enters via area AND via L -> quadratic, so 2x chord -> 4x m_ref.
    assert two.m_ref == pytest.approx(4.0 * one.m_ref, rel=1e-12)
    force_ref = compute_force_reference(1.0, 70.0, 3.0, 3.0, 2.0)
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
