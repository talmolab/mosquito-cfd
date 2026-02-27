"""Tests for geometry module."""

import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.geometry import (
    PlanformShape,
    generate_planform,
    read_vertex_file,
    write_vertex_file,
)
from mosquito_cfd.geometry.parametric_planform import estimate_marker_count

# ---------------------------------------------------------------------------
# Python re-implementation of WingKinematics.H (ZYX Euler, van Veen 2022)
# Used to validate the kinematics math independently of the C++ code.
# ---------------------------------------------------------------------------

def _euler_angles(time, freq=600.0, phi_amp=70.0, alpha_amp=45.0,
                  theta_amp=0.0, phase_lead=90.0):
    """Compute (phi, alpha, theta) in radians at given time."""
    omega = 2.0 * math.pi * freq
    phi   = math.radians(phi_amp)   * math.sin(omega * time)
    alpha = math.radians(alpha_amp) * math.cos(omega * time + math.radians(phase_lead) - math.pi / 2)
    # van Veen: phi = phi_amp*sin(wt), alpha = alpha_amp*cos(wt)
    # pitch_phase_lead=90° means alpha = alpha_amp * cos(wt) (cos leads sin by 90°)
    alpha = math.radians(alpha_amp) * math.cos(omega * time)
    theta = math.radians(theta_amp) * math.sin(2.0 * omega * time)
    return phi, alpha, theta


def _rotation_matrix(phi, alpha, theta):
    """R = Rz(phi) * Ry(theta) * Rx(alpha)  [ZYX convention, matches WingKinematics.H]."""
    cp, sp = math.cos(phi),   math.sin(phi)
    ca, sa = math.cos(alpha), math.sin(alpha)
    ct, st = math.cos(theta), math.sin(theta)
    return np.array([
        [cp*ct,  cp*st*sa - sp*ca,  cp*st*ca + sp*sa],
        [sp*ct,  sp*st*sa + cp*ca,  sp*st*ca - cp*sa],
        [-st,    ct*sa,             ct*ca           ],
    ])


class TestGeneratePlanform:
    """Tests for planform generation."""

    def test_rectangular_marker_count(self):
        """Rectangular planform should have span/spacing * chord/spacing markers."""
        markers = generate_planform(
            shape="rectangular",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
        )
        expected = (3.0e-3 / 50e-6) * (1.0e-3 / 50e-6)  # 60 * 20 = 1200
        assert len(markers) == expected

    def test_elliptic_fewer_than_rectangular(self):
        """Elliptic planform should have fewer markers than rectangular."""
        rect = generate_planform(
            shape="rectangular",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
        )
        ellip = generate_planform(
            shape="elliptic",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
        )
        assert len(ellip) < len(rect)
        # Ellipse area ≈ π/4 of rectangle
        ratio = len(ellip) / len(rect)
        assert 0.7 < ratio < 0.85  # Should be close to π/4 ≈ 0.785

    def test_elliptic_shape(self):
        """Elliptic planform markers should fall within ellipse boundary."""
        span = 3.0e-3
        chord = 1.0e-3
        markers = generate_planform(
            shape="elliptic",
            span=span,
            chord=chord,
            spacing=50e-6,
        )
        # Check all markers satisfy ellipse equation: (x/a)^2 + (z/b)^2 <= 1
        a = chord / 2
        b = span / 2
        for m in markers:
            x, y, z = m
            ellipse_val = (x / a) ** 2 + (z / b) ** 2
            assert ellipse_val <= 1.1  # Allow small tolerance for grid discretization

    def test_center_offset(self):
        """Markers should be centered at specified position."""
        center = (0.025, 0.025, 0.025)
        markers = generate_planform(
            shape="rectangular",
            span=1.0e-3,
            chord=1.0e-3,
            spacing=100e-6,
            center=center,
        )
        # Mean position should be close to center
        mean_pos = markers.mean(axis=0)
        np.testing.assert_allclose(mean_pos, center, atol=1e-6)

    def test_markers_in_xz_plane(self):
        """All markers should have the same y-coordinate."""
        markers = generate_planform(
            shape="elliptic",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
            center=(0.0, 0.5, 0.0),
        )
        assert np.all(markers[:, 1] == 0.5)

    def test_shape_enum_and_string(self):
        """Both enum and string shapes should work."""
        m1 = generate_planform(
            shape=PlanformShape.RECTANGULAR,
            span=1e-3,
            chord=1e-3,
            spacing=100e-6,
        )
        m2 = generate_planform(
            shape="rectangular",
            span=1e-3,
            chord=1e-3,
            spacing=100e-6,
        )
        np.testing.assert_array_equal(m1, m2)


class TestEstimateMarkerCount:
    """Tests for marker count estimation."""

    def test_rectangular_exact(self):
        """Rectangular estimate should be exact."""
        est = estimate_marker_count("rectangular", 3e-3, 1e-3, 50e-6)
        actual = len(generate_planform("rectangular", 3e-3, 1e-3, 50e-6))
        assert est == actual

    def test_elliptic_approximate(self):
        """Elliptic estimate should be close to actual."""
        est = estimate_marker_count("elliptic", 3e-3, 1e-3, 50e-6)
        actual = len(generate_planform("elliptic", 3e-3, 1e-3, 50e-6))
        assert abs(est - actual) / actual < 0.1  # Within 10%


class TestVertexIO:
    """Tests for vertex file I/O."""

    def test_roundtrip(self):
        """Writing and reading should preserve marker positions."""
        markers = generate_planform(
            shape="elliptic",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
        )

        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False) as f:
            filepath = f.name

        try:
            write_vertex_file(markers, filepath)
            loaded = read_vertex_file(filepath)
            np.testing.assert_allclose(markers, loaded, rtol=1e-9)
        finally:
            Path(filepath).unlink()

    def test_file_format(self):
        """Vertex file should have correct format."""
        markers = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False, mode="w") as f:
            filepath = f.name

        try:
            write_vertex_file(markers, filepath)
            with open(filepath) as f:
                lines = f.readlines()

            assert lines[0].strip() == "2"  # Marker count
            assert len(lines) == 3  # Count + 2 markers
        finally:
            Path(filepath).unlink()


class TestVertexFileReader:
    """Validate vertex file format compatibility with C++ VertexFileReader.H (task 2.3.3)."""

    def test_three_marker_file_exact_positions(self):
        """Load a hand-crafted 3-marker file and verify exact positions."""
        content = "3\n1.0 2.0 3.0\n4.0 5.0 6.0\n7.0 8.0 9.0\n"
        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False, mode="w") as f:
            f.write(content)
            filepath = f.name
        try:
            markers = read_vertex_file(filepath)
            assert markers.shape == (3, 3)
            np.testing.assert_allclose(markers[0], [1.0, 2.0, 3.0])
            np.testing.assert_allclose(markers[1], [4.0, 5.0, 6.0])
            np.testing.assert_allclose(markers[2], [7.0, 8.0, 9.0])
        finally:
            Path(filepath).unlink()

    def test_load_wing_vertex_from_generator(self):
        """Load wing.vertex produced by Python generator and verify marker count/shape."""
        markers = generate_planform(
            shape="elliptic",
            span=3.0e-3,
            chord=1.0e-3,
            spacing=50e-6,
            center=(0.015, 0.015, 0.015),
        )
        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False) as f:
            filepath = f.name
        try:
            write_vertex_file(markers, filepath)
            loaded = read_vertex_file(filepath)
            assert loaded.shape[1] == 3
            assert loaded.shape[0] == markers.shape[0]
            # All markers should be in the xz plane (y = center_y = 0.015)
            np.testing.assert_allclose(loaded[:, 1], 0.015, atol=1e-10)
        finally:
            Path(filepath).unlink()

    def test_scientific_notation_precision(self):
        """Vertex file uses scientific notation; round-trip preserves 10-digit precision."""
        markers = np.array([[1.23456789012e-3, 0.0, -9.87654321098e-4]])
        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False) as f:
            filepath = f.name
        try:
            write_vertex_file(markers, filepath)
            loaded = read_vertex_file(filepath)
            np.testing.assert_allclose(loaded, markers, rtol=1e-9)
        finally:
            Path(filepath).unlink()

    def test_marker_count_header(self):
        """First line of vertex file must be the integer marker count (C++ reads this first)."""
        markers = generate_planform("rectangular", 1e-3, 1e-3, 100e-6)
        with tempfile.NamedTemporaryFile(suffix=".vertex", delete=False) as f:
            filepath = f.name
        try:
            write_vertex_file(markers, filepath)
            with open(filepath) as f:
                first_line = f.readline().strip()
            assert int(first_line) == len(markers)
        finally:
            Path(filepath).unlink()


class TestWingKinematics:
    """Validate van Veen (2022) kinematics math (task 3.2.3).

    Tests the Python re-implementation of WingKinematics.H to verify the
    expected angular relationships before running the C++ code.
    """

    def test_at_t0_phi_zero(self):
        """At t=0, stroke angle φ = 0 (sin(0) = 0)."""
        phi, alpha, theta = _euler_angles(0.0)
        assert phi == pytest.approx(0.0, abs=1e-12)

    def test_at_t0_alpha_max(self):
        """At t=0, pitch angle α = α_amp (cos(0) = 1 → maximum pitch)."""
        phi, alpha, theta = _euler_angles(0.0, alpha_amp=45.0)
        assert alpha == pytest.approx(math.radians(45.0), rel=1e-9)

    def test_at_quarter_period_phi_max(self):
        """At t=T/4, stroke angle φ = +φ_amp (sin reaches maximum)."""
        freq = 600.0
        T = 1.0 / freq
        phi, alpha, theta = _euler_angles(T / 4, freq=freq, phi_amp=70.0)
        assert phi == pytest.approx(math.radians(70.0), rel=1e-9)

    def test_at_quarter_period_alpha_zero(self):
        """At t=T/4, pitch angle α = 0 (cos(π/2) = 0 → wing at zero pitch at max stroke)."""
        freq = 600.0
        T = 1.0 / freq
        phi, alpha, theta = _euler_angles(T / 4, freq=freq, alpha_amp=45.0)
        assert alpha == pytest.approx(0.0, abs=1e-9)

    def test_pitch_leads_stroke_by_90_degrees(self):
        """Pitch leads stroke by 90°: α peaks at t=0, φ peaks at t=T/4."""
        freq = 600.0
        T = 1.0 / freq
        n = 1000
        times = np.linspace(0, T, n, endpoint=False)
        phis   = [_euler_angles(t, freq=freq)[0] for t in times]
        alphas = [_euler_angles(t, freq=freq)[1] for t in times]
        phi_peak_idx   = int(np.argmax(np.abs(phis)))
        alpha_peak_idx = int(np.argmax(np.abs(alphas)))
        # α peaks near t=0, φ peaks near t=T/4 → phase difference ≈ n/4
        phase_diff = abs(phi_peak_idx - alpha_peak_idx)
        # Allow ±5% tolerance on n/4
        assert abs(phase_diff - n // 4) < n * 0.05

    def test_rotation_matrix_is_orthogonal(self):
        """Rotation matrix R must satisfy R^T @ R = I (orthogonality)."""
        freq = 600.0
        T = 1.0 / freq
        for t in [0.0, T / 8, T / 4, T / 2, 3 * T / 4]:
            phi, alpha, theta = _euler_angles(t, freq=freq)
            R = _rotation_matrix(phi, alpha, theta)
            np.testing.assert_allclose(R.T @ R, np.eye(3), atol=1e-12)

    def test_at_t0_reference_positions_unchanged_when_phi_zero_theta_zero(self):
        """At t=0 with phi=0, theta=0, only Rx(alpha) is applied.

        A point on the z-axis (x=0, y=0, z=r) relative to hinge rotates by α only.
        """
        phi, alpha, theta = _euler_angles(0.0)  # phi=0, theta=0, alpha=45°
        assert phi == pytest.approx(0.0, abs=1e-12)
        assert theta == pytest.approx(0.0, abs=1e-12)
        R = _rotation_matrix(phi, alpha, theta)
        # Point on z-axis: (0, 0, r) should rotate to (0, -r*sin(α), r*cos(α))
        r = 1.0
        pt = np.array([0.0, 0.0, r])
        rotated = R @ pt
        np.testing.assert_allclose(rotated[0], 0.0, atol=1e-12)
        np.testing.assert_allclose(rotated[1], -r * math.sin(alpha), atol=1e-12)
        np.testing.assert_allclose(rotated[2],  r * math.cos(alpha), atol=1e-12)