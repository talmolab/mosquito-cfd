"""Cluster-free tests for the Python wing-kinematics mirror (Tier T2a).

Two guards: (1) the mirror's rotation matches the **design-D2 target composition**
``R = Rz(φ)·Ry(α)·Rx(θ)`` at golden angles and is order-locked (the C++ ``WingKinematics.H`` must
conform to this — a matching fork-side test closes the loop); (2) the refactored stroke MOTION
sweeps the span-tip (van Veen's translational sweep), whereas the old stroke-∥-span composition does
not. Pure numpy — no CFD.
"""

from __future__ import annotations

import numpy as np
import pytest

from mosquito_cfd.benchmarks.wing_kinematics import (
    euler_angles,
    rotation_matrix,
    rotation_matrix_legacy,
)


# Independent primitive rotations (hand-written, NOT imported from the module under test).
def _Rz(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


def _Ry(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[c, 0, s], [0, 1.0, 0], [-s, 0, c]])


def _Rx(a):
    c, s = np.cos(a), np.sin(a)
    return np.array([[1.0, 0, 0], [0, c, -s], [0, s, c]])


def test_identity_at_zero():
    np.testing.assert_allclose(rotation_matrix(0.0, 0.0, 0.0), np.eye(3), atol=1e-15)


def test_stroke_is_about_lab_z():
    """φ alone → Rz(φ): stroke rotates about the lab vertical z (golden)."""
    np.testing.assert_allclose(
        rotation_matrix(np.pi / 2, 0.0, 0.0),
        np.array([[0, -1, 0], [1, 0, 0], [0, 0, 1.0]]),
        atol=1e-15,
    )


def test_pitch_is_about_span_y():
    """α alone → Ry(α): pitch rotates about the span y (golden)."""
    np.testing.assert_allclose(
        rotation_matrix(0.0, np.pi / 2, 0.0),
        np.array([[0, 0, 1], [0, 1.0, 0], [-1, 0, 0]]),
        atol=1e-15,
    )


def test_deviation_is_about_chord_x():
    """θ alone → Rx(θ): deviation rotates about the chord x (golden)."""
    np.testing.assert_allclose(
        rotation_matrix(0.0, 0.0, np.pi / 2),
        np.array([[1, 0, 0], [0, 0, -1], [0, 1.0, 0]]),
        atol=1e-15,
    )


def test_order_locked_Rz_Ry_Rx():
    """Generic θ≠0 triple: equals Rz·Ry·Rx and DIFFERS from the wrong order / the legacy order."""
    phi, alpha, theta = 0.3, 0.6, 0.9
    expected = _Rz(phi) @ _Ry(alpha) @ _Rx(theta)
    np.testing.assert_allclose(rotation_matrix(phi, alpha, theta), expected, atol=1e-14)
    # Wrong composition order must NOT accidentally match.
    wrong = _Rz(phi) @ _Rx(alpha) @ _Ry(theta)
    assert not np.allclose(rotation_matrix(phi, alpha, theta), wrong, atol=1e-6)
    # The legacy (pre-T2a) order is genuinely different for this triple.
    assert not np.allclose(
        rotation_matrix(phi, alpha, theta),
        rotation_matrix_legacy(phi, alpha, theta),
        atol=1e-6,
    )


def test_rotation_is_orthonormal():
    r = rotation_matrix(0.3, 0.6, 0.9)
    np.testing.assert_allclose(r @ r.T, np.eye(3), atol=1e-14)
    assert np.linalg.det(r) == pytest.approx(1.0, abs=1e-14)


def test_euler_angles_midstroke_has_zero_pitch():
    """At the quarter-period midstroke, φ is at amplitude and α (∝cos) is 0."""
    f_star = 1.0
    t_mid = 1.0 / (4.0 * f_star)  # ωt = π/2
    phi, alpha, theta = euler_angles(
        t_mid,
        frequency=f_star,
        stroke_amp_rad=np.radians(70.0),
        pitch_amp_rad=np.radians(45.0),
    )
    assert phi == pytest.approx(np.radians(70.0), abs=1e-9)
    assert alpha == pytest.approx(0.0, abs=1e-9)


def _cpp_rotation_matrix(phi, alpha, theta):
    """Exact transcription of ``WingKinematics.H::ComputeRotationMatrix`` (van Veen / T2a).

    KEEP IN LOCK-STEP with ``IAMReX-fork/Source/WingKinematics.H``: this is the fork-conformance
    guard (the C++ is not exercised by CI). Any change to the C++ rotation MUST update this.
    """
    cp, sp = np.cos(phi), np.sin(phi)
    ca, sa = np.cos(alpha), np.sin(alpha)
    ct, st = np.cos(theta), np.sin(theta)
    return np.array(
        [
            [cp * ca, cp * sa * st - sp * ct, cp * sa * ct + sp * st],
            [sp * ca, sp * sa * st + cp * ct, sp * sa * ct - cp * st],
            [-sa, ca * st, ca * ct],
        ]
    )


def test_cpp_wingkinematics_conforms_to_mirror():
    """The C++ ComputeRotationMatrix formula equals the Python mirror (bidirectional drift guard)."""
    rng = np.random.default_rng(1)
    for _ in range(500):
        a = rng.uniform(-np.pi, np.pi, 3)
        np.testing.assert_allclose(
            _cpp_rotation_matrix(*a), rotation_matrix(*a), atol=1e-13
        )


def test_new_stroke_sweeps_span_tip_old_does_not():
    """The NEW motion sweeps the span-tip at the α=0 midstroke; the OLD (stroke-∥-span) does not."""
    r = 1.5  # span-tip arm
    phi_amp = np.radians(70.0)
    # Midstroke: φ = +70°, α = 0.
    phi, alpha = phi_amp, 0.0

    # New convention: span is along y, tip body vector (0, r, 0).
    tip_new = rotation_matrix(phi, alpha, 0.0) @ np.array([0.0, r, 0.0])
    # Horizontal (in-stroke-plane, x) excursion is non-zero: |x| = r*sin(70°).
    assert abs(tip_new[0]) == pytest.approx(r * np.sin(phi_amp), abs=1e-9)
    assert abs(tip_new[0]) > 0.5 * r

    # Old convention: span is along z, tip body vector (0, 0, r); stroke Rz(φ) is about the span.
    tip_old = rotation_matrix_legacy(phi, alpha, 0.0) @ np.array([0.0, 0.0, r])
    # At the α=0 midstroke the old span-tip has NO horizontal (x,y) excursion — it sits on the axis.
    horizontal_old = np.hypot(tip_old[0], tip_old[1])
    assert horizontal_old == pytest.approx(0.0, abs=1e-9)
