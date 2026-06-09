"""Tests for force_surrogate.normalization (TDD red phase)."""

import numpy as np
import pytest

from mosquito_cfd.force_surrogate import (
    compute_force_coefficients,
    compute_force_reference,
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


def test_compute_force_coefficients_zero_reference_raises():
    """A zero reference (degenerate kinematics) raises rather than div-by-zero."""
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, 0.0)


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
