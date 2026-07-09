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
    stroke_rate,
)


def test_stroke_rate_matches_analytic_derivatives():
    """stroke_rate returns the analytic (phi_dot, phi_ddot) of phi(t)=phi_amp*sin(2*pi*f*t)."""
    f_star, phi_amp = 1.0, np.radians(70.0)
    w = 2.0 * np.pi * f_star
    omega_ref = phi_amp * w  # peak stroke rate
    for t in (0.0, 0.1, 0.37, 0.5, 0.9):
        omega, omega_dot = stroke_rate(t, frequency=f_star, stroke_amp_rad=phi_amp)
        assert omega == pytest.approx(phi_amp * w * np.cos(w * t))
        assert omega_dot == pytest.approx(-phi_amp * w**2 * np.sin(w * t))
    omega0, omega_dot0 = stroke_rate(0.0, frequency=f_star, stroke_amp_rad=phi_amp)
    assert omega0 == pytest.approx(omega_ref)  # peak rate at midstroke
    assert omega_dot0 == pytest.approx(0.0)
    # Degenerate frequency=0 -> stationary wing, no error.
    assert stroke_rate(0.3, frequency=0.0, stroke_amp_rad=phi_amp) == (0.0, 0.0)


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
    """The NEW motion displaces the span-tip along the stroke arc; the OLD (stroke-∥-span) does not.

    Position check at the stroke EXTREME (φ = +70°, φ̇ = 0, α = 0 — i.e. t = T/4, the turnaround).
    """
    r = 1.5  # span-tip arm
    phi_amp = np.radians(70.0)
    # Stroke extreme (t = T/4): φ = +70°, α = 0.
    phi, alpha = phi_amp, 0.0

    # New convention: span is along y, tip body vector (0, r, 0).
    tip_new = rotation_matrix(phi, alpha, 0.0) @ np.array([0.0, r, 0.0])
    # Horizontal (in-stroke-plane, x) excursion is non-zero: |x| = r*sin(70°).
    assert abs(tip_new[0]) == pytest.approx(r * np.sin(phi_amp), abs=1e-9)
    assert abs(tip_new[0]) > 0.5 * r

    # Old convention: span is along z, tip body vector (0, 0, r); stroke Rz(φ) is about the span.
    tip_old = rotation_matrix_legacy(phi, alpha, 0.0) @ np.array([0.0, 0.0, r])
    # At the stroke extreme the old span-tip has NO horizontal (x,y) excursion — it sits on the axis.
    horizontal_old = np.hypot(tip_old[0], tip_old[1])
    assert horizontal_old == pytest.approx(0.0, abs=1e-9)


def test_new_stroke_span_tip_has_horizontal_velocity_old_does_not():
    """VELOCITY-level: the STROKE sweeps the NEW span-tip through the horizontal plane; the OLD
    (stroke-∥-span) stroke leaves the span-tip stationary.

    Position displacement alone doesn't prove a *translational sweep* — the load-bearing claim is that
    the tip *translates*. We isolate the stroke's effect with a **pure-stroke** motion (pitch α≡0,
    deviation θ≡0, only `φ = φ_amp·sin(2πt)`) and finite-difference the span-tip position at the
    maximum-stroke-rate phase (t = 0, φ = 0, φ̇ = 2π·φ_amp·f_star). Isolating the stroke avoids the
    pitch confound: at the real coupled kinematics α is maximal exactly when φ̇ is, which would tilt the
    old span-tip off its rotation axis and mask the distinction.
    """
    r = 1.5
    f_star = 1.0
    phi_amp = np.radians(70.0)
    dt = 1e-6

    def tip(rot_fn, body_vec, t):
        phi, alpha, theta = euler_angles(
            t,
            frequency=f_star,
            stroke_amp_rad=phi_amp,
            pitch_amp_rad=0.0,  # pure stroke — isolate the stroke's effect on the span-tip
            deviation_amp_rad=0.0,
        )
        return rot_fn(phi, alpha, theta) @ np.asarray(body_vec)

    # Central finite difference of tip position at t=0 (φ=0, φ̇ = 2π·φ_amp·f_star, maximal).
    new_vel = (
        tip(rotation_matrix, [0.0, r, 0.0], dt)
        - tip(rotation_matrix, [0.0, r, 0.0], -dt)
    ) / (2 * dt)
    old_vel = (
        tip(rotation_matrix_legacy, [0.0, 0.0, r], dt)
        - tip(rotation_matrix_legacy, [0.0, 0.0, r], -dt)
    ) / (2 * dt)

    new_horiz_speed = float(np.hypot(new_vel[0], new_vel[1]))
    old_horiz_speed = float(np.hypot(old_vel[0], old_vel[1]))

    # New tip sweeps horizontally at r·φ̇ = r·2π·φ_amp·f_star (cos(0)=1).
    expected = r * 2 * np.pi * phi_amp * f_star
    assert new_horiz_speed == pytest.approx(expected, rel=1e-3)
    # Old span-tip lies ON the stroke (z) axis under pure stroke → Rz(φ) never moves it: ~zero speed.
    assert old_horiz_speed < 1e-6 * expected
