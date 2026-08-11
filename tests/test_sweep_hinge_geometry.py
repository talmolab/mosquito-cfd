"""Geometric-consistency guard for the sweep base decks' wing hinge.

OpenSpec change ``fix-force-surrogate-sweep-hinge``. Unlike the pre-existing byte-identity guards
(``test_committed_sweep_matches_regeneration`` and friends), this guard re-derives "root hinge"
from the geometry file every time -- it does not compare against a second frozen constant. That is
precisely what let the original bug (hinge frozen from a pre-refactor deck, geometry file moved to
a new convention) ship undetected for over a month: byte-identity can never catch a
self-consistently wrong value.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate.geometry_guard import (
    assert_hinge_at_span_root,
    read_deck_value,
)

_LIVE_DECK = Path("examples/flapping_wing/inputs.3d.validation")
_CANONICAL_VERTEX = Path("examples/flapping_wing/wing.vertex")
_COARSE_BASE = Path("examples/prelim_sweep/base_inputs.3d.validation")
_FINE_BASE = Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")


def test_hinge_at_span_root_for_correct_deck():
    """Calibration baseline: the guard passes against today's already-correct live deck."""
    assert_hinge_at_span_root(_LIVE_DECK.read_text(), _CANONICAL_VERTEX)


def test_hinge_at_span_root_rejects_midspan_pivot():
    """Zero span-arm (hinge == wing centre) -- half of the real bug's exact shape -- is rejected."""
    deck = """
particle_inputs.x = 4.0
particle_inputs.y = 2.0
particle_inputs.z = 4.0
particle_inputs.hinge_x = 4.0
particle_inputs.hinge_y = 2.0
particle_inputs.hinge_z = 4.0
"""
    with pytest.raises(AssertionError, match="span"):
        assert_hinge_at_span_root(deck, _CANONICAL_VERTEX)


def test_hinge_at_span_root_rejects_spurious_offset():
    """Correct span arm but a spurious non-span-axis offset -- the other half of the real bug."""
    deck = """
particle_inputs.x = 4.0
particle_inputs.y = 2.0
particle_inputs.z = 4.0
particle_inputs.hinge_x = 4.0
particle_inputs.hinge_y = 0.5
particle_inputs.hinge_z = 2.5
"""
    with pytest.raises(AssertionError, match="hinge_z"):
        assert_hinge_at_span_root(deck, _CANONICAL_VERTEX)


def test_hinge_at_span_root_handles_empty_vertex_file(tmp_path):
    empty_vertex = tmp_path / "empty.vertex"
    empty_vertex.write_text("0\n", encoding="utf-8")
    deck = """
particle_inputs.x = 4.0
particle_inputs.y = 2.0
particle_inputs.z = 4.0
particle_inputs.hinge_x = 4.0
particle_inputs.hinge_y = 0.5
particle_inputs.hinge_z = 4.0
"""
    with pytest.raises(ValueError, match="empty.vertex"):
        assert_hinge_at_span_root(deck, empty_vertex)


def test_hinge_at_span_root_rejects_invalid_span_axis():
    """An invalid span_axis raises a clear ValueError, not a bare KeyError."""
    with pytest.raises(ValueError, match="span_axis"):
        assert_hinge_at_span_root(
            _LIVE_DECK.read_text(), _CANONICAL_VERTEX, span_axis="w"
        )


def test_read_deck_value_uses_last_occurrence_when_key_duplicated():
    """A key assigned twice resolves to the LAST value (ParmParse override semantics)."""
    deck = """
particle_inputs.hinge_y = 2.0
particle_inputs.hinge_y = 0.5
"""
    assert read_deck_value(deck, "particle_inputs.hinge_y") == pytest.approx(0.5)


@pytest.mark.xfail(
    reason=(
        "Expected to fail until PR 2 of fix-force-surrogate-sweep-hinge lands "
        "(Phase 1: the base decks' hinge_y/hinge_z fix). This test proves the guard genuinely "
        "detects the real bug -- see openspec/changes/fix-force-surrogate-sweep-hinge/tasks.md."
    ),
    strict=True,
)
def test_hinge_at_span_root_for_coarse_and_fine_base_decks():
    """The real regression check: both sweep base decks against the real canonical geometry."""
    assert_hinge_at_span_root(_COARSE_BASE.read_text(), _CANONICAL_VERTEX)
    assert_hinge_at_span_root(_FINE_BASE.read_text(), _CANONICAL_VERTEX)
