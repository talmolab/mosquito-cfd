"""Tests for the generator span-axis parameter (Tier T2a).

The generator gains a ``span_axis`` so ``generate-wing-planform`` can emit the van Veen convention
(span along y). The default preserves the legacy span-z behaviour, and span-y is the *same* marker
set with the span axis moved from z to y (a re-orientation, not a geometry change).
"""

from __future__ import annotations

from pathlib import Path

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


# --- Guards on the COMMITTED wing.vertex (the headline T2a geometry artifact, tasks 4.3/4.4) ---

_WING_VERTEX = Path("examples/flapping_wing/wing.vertex")


def test_committed_wing_vertex_span_along_y():
    """The committed wing.vertex is span-along-y, chord-x, flat-in-z (origin-centred, 908 markers).

    Guards the headline geometry deliverable directly — the r_gyr trace auto-detects the span axis
    and would NOT catch a silent revert to span-z, so pin the orientation here.
    """
    v = np.loadtxt(_WING_VERTEX, skiprows=1)
    assert v.shape[0] == 908
    assert np.ptp(v[:, 1]) > np.ptp(v[:, 0])  # span(y) > chord(x)
    assert np.ptp(v[:, 2]) == pytest.approx(0.0, abs=1e-9)  # flat in z
    assert np.ptp(v[:, 1]) == pytest.approx(_SPAN, abs=0.1)  # span ~ 3
    assert np.ptp(v[:, 0]) == pytest.approx(_CHORD, abs=0.1)  # chord ~ 1
    # Origin-centred (the solver adds the domain centre): means ~ 0.
    assert abs(v[:, 0].mean()) < 0.05 and abs(v[:, 1].mean()) < 0.05


def test_committed_wing_vertex_matches_generator():
    """The committed wing.vertex is byte-set-equal to `generate-wing-planform --axis y` (regen guard)."""
    v = np.loadtxt(_WING_VERTEX, skiprows=1)
    gen = generate_planform("elliptic", _SPAN, _CHORD, _SPACING, span_axis="y")
    assert gen.shape == v.shape  # same marker count (908)
    sort_v = v[np.lexsort(v.T)]
    sort_g = gen[np.lexsort(gen.T)]
    np.testing.assert_allclose(sort_v, sort_g, atol=1e-9)
