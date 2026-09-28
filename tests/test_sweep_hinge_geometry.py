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
    wing_half_span,
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


def test_read_deck_value_rejects_non_finite_value():
    """A NaN/inf value must be rejected here, not silently defeat a downstream tolerance check.

    A tolerance comparison against NaN (``abs(nan - x) >= tol``) is always False in Python, so an
    un-rejected NaN would silently bypass assert_hinge_at_span_root's AssertionError entirely --
    exactly the "self-consistently wrong value slips through" failure mode this guard exists to
    catch, just via a different mechanism than the original bug.
    """
    deck = "particle_inputs.hinge_y = nan\n"
    with pytest.raises(ValueError, match="non-finite"):
        read_deck_value(deck, "particle_inputs.hinge_y")


def test_hinge_at_span_root_rejects_nan_hinge_value():
    """assert_hinge_at_span_root itself must not silently pass on a NaN hinge value."""
    deck = """
particle_inputs.x = 4.0
particle_inputs.y = 2.0
particle_inputs.z = 4.0
particle_inputs.hinge_x = 4.0
particle_inputs.hinge_y = nan
particle_inputs.hinge_z = 4.0
"""
    with pytest.raises(ValueError, match="non-finite"):
        assert_hinge_at_span_root(deck, _CANONICAL_VERTEX)


def test_hinge_at_span_root_rejects_deck_missing_a_required_key():
    """A deck missing one of the 6 required particle_inputs.* keys raises a clear ValueError."""
    deck = """
particle_inputs.x = 4.0
particle_inputs.y = 2.0
particle_inputs.z = 4.0
particle_inputs.hinge_x = 4.0
particle_inputs.hinge_y = 0.5
"""
    with pytest.raises(ValueError, match="particle_inputs.hinge_z"):
        assert_hinge_at_span_root(deck, _CANONICAL_VERTEX)


def test_wing_half_span_uses_max_minus_min_not_max_alone(tmp_path):
    """The half-span formula must be robust to a non-origin-centered vertex file.

    Regression: an earlier version used markers.max() alone, which only equals the true half-span
    because the committed wing.vertex happens to be exactly symmetric about 0 (an artifact of
    generate-wing-planform's span/spacing dividing evenly) -- not a guaranteed property of every
    vertex file. This fixture is deliberately NOT symmetric (span y in [1.0, 4.0], half-span 1.5)
    so markers.max() alone (4.0) and (max-min)/2 (1.5) give different, distinguishable answers.
    """
    asymmetric_vertex = tmp_path / "asymmetric.vertex"
    asymmetric_vertex.write_text(
        "3\n0.0 1.0 0.0\n0.0 2.5 0.0\n0.0 4.0 0.0\n", encoding="utf-8"
    )
    assert wing_half_span(asymmetric_vertex, span_axis="y") == pytest.approx(1.5)


def test_hinge_at_span_root_for_coarse_and_fine_base_decks():
    """The real regression check: both sweep base decks against the real canonical geometry."""
    assert_hinge_at_span_root(_COARSE_BASE.read_text(), _CANONICAL_VERTEX)
    assert_hinge_at_span_root(_FINE_BASE.read_text(), _CANONICAL_VERTEX)


# Every per-config deck of the two extracted corpora. The base-deck check above covers two
# templates (one of them the pilot's), but extraction reads each per-config deck's hinge as the
# moment reference point (fix-moment-reference-hinge), so all 54 are numerically load-bearing.
_CORPUS_DECKS = sorted(
    deck
    for corpus in ("prelim_sweep", "prelim_sweep_fine")
    for deck in (Path("examples") / corpus / "inputs").glob("inputs.3d.*")
)

# The fine-grid pilot's per-config decks are the committed record of what the pilot actually
# ran: the pre-fix-force-surrogate-sweep-hinge midspan pivot (hinge_y = 2.0, hinge_z = 2.5).
# Only its base deck was corrected afterwards; its report flags the defect (see
# test_fine_pilot_deck.py). Correcting these files would falsify that record, and no dataset is
# extracted from the pilot, so they are pinned as the known defect rather than guarded.
_PILOT_DECKS = sorted(
    Path("examples/prelim_sweep_fine_pilot/inputs").glob("inputs.3d.*")
)


def test_per_config_deck_globs_are_not_vacuous():
    """27 coarse + 27 fine, and 3 pilot. An empty glob would parametrize to nothing."""
    assert len(_CORPUS_DECKS) == 54, [p.as_posix() for p in _CORPUS_DECKS]
    assert len(_PILOT_DECKS) == 3, [p.as_posix() for p in _PILOT_DECKS]


@pytest.mark.parametrize("deck", _CORPUS_DECKS, ids=lambda p: p.as_posix())
def test_hinge_at_span_root_for_every_corpus_deck(deck):
    assert_hinge_at_span_root(deck.read_text(encoding="utf-8"), _CANONICAL_VERTEX)


@pytest.mark.parametrize("deck", _PILOT_DECKS, ids=lambda p: p.as_posix())
def test_pilot_decks_record_the_historical_midspan_pivot(deck):
    """If this ever fails, the pilot decks were edited: either restore the historical record or
    move them under the corpus guard deliberately -- never let them pass silently."""
    text = deck.read_text(encoding="utf-8")
    assert read_deck_value(text, "particle_inputs.hinge_y") == 2.0
    assert read_deck_value(text, "particle_inputs.hinge_z") == 2.5
    with pytest.raises(AssertionError, match="midspan"):
        assert_hinge_at_span_root(text, _CANONICAL_VERTEX)
