"""Tests for the generator span-axis parameter (Tier T2a).

The generator gains a ``span_axis`` so ``generate-wing-planform`` can emit the van Veen convention
(span along y). The default preserves the legacy span-z behaviour, and span-y is the *same* marker
set with the span axis moved from z to y (a re-orientation, not a geometry change).
"""

from __future__ import annotations

import numpy as np
import pytest

from mosquito_cfd.geometry.parametric_planform import PlanformShape, generate_planform

_SPAN, _CHORD, _SPACING = 3.0, 1.0, 0.05


def test_default_span_axis_is_z_legacy():
    """Omitting span_axis reproduces the legacy span-in-z orientation exactly."""
    m_default = generate_planform("elliptic", _SPAN, _CHORD, _SPACING)
    m_z = generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="z")
    np.testing.assert_array_equal(m_default, m_z)
    # Legacy: span along z, wing flat in x-z (y constant).
    assert np.ptp(m_z[:, 2]) > np.ptp(m_z[:, 0])  # span(z) > chord(x)
    assert np.ptp(m_z[:, 1]) == pytest.approx(0.0)  # flat in y


def test_span_axis_y_is_van_veen_orientation():
    """span_axis='y': span along y, chord along x, wing flat in x-y (z constant)."""
    m = generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="y")
    assert np.ptp(m[:, 1]) > np.ptp(m[:, 0])  # span(y) > chord(x)
    assert np.ptp(m[:, 2]) == pytest.approx(0.0)  # flat in z
    assert np.ptp(m[:, 1]) == pytest.approx(np.ptp(m[:, 0]) * (_SPAN / _CHORD), rel=0.1)


def test_span_y_preserves_marker_set_under_permutation():
    """span-y is the span-z set with y<->z swapped (same shape, re-oriented — not a new geometry)."""
    m_z = generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="z")
    m_y = generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="y")
    assert m_z.shape == m_y.shape  # same marker count
    # Map span-z markers (x, 0, span) to span-y layout (x, span, 0) and compare sorted sets.
    m_z_as_y = m_z[:, [0, 2, 1]]
    sort_z = m_z_as_y[np.lexsort(m_z_as_y.T)]
    sort_y = m_y[np.lexsort(m_y.T)]
    np.testing.assert_allclose(sort_z, sort_y, atol=1e-12)


def test_bad_span_axis_raises():
    with pytest.raises(ValueError, match="span_axis"):
        generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="x")


def test_rectangular_span_axis_y():
    m = generate_planform(
        PlanformShape.RECTANGULAR, _SPAN, _CHORD, _SPACING, span_axis="y"
    )
    assert np.ptp(m[:, 1]) > np.ptp(m[:, 0])
    assert np.ptp(m[:, 2]) == pytest.approx(0.0)
