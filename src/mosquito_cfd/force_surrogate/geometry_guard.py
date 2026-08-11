"""Geometric-consistency guard: the sweep base deck's hinge vs. the wing's own geometry.

OpenSpec change ``fix-force-surrogate-sweep-hinge``. Deliberately not a byte-identity check —
re-derives "root hinge" from the referenced ``wing.vertex`` marker extent every call, so a hinge
that is self-consistently wrong (frozen from a stale deck against a geometry file that has since
moved to a new axis convention -- exactly what happened) cannot hide behind it the way it hid
behind the pre-existing byte-identity guards for over a month.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from mosquito_cfd.geometry.vertex_io import read_vertex_file

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}

# Non-span axes must match the wing centre exactly (no spurious offset was ever intentional);
# 1e-9 only absorbs float round-trip noise through the deck's text representation.
_EXACT_OFFSET_TOL = 1e-9


def axis_index(span_axis: str) -> int:
    """Resolve an axis label to its column index, validating it first.

    Args:
        span_axis: One of ``"x"``, ``"y"``, ``"z"``.

    Returns:
        The corresponding column index (0, 1, or 2).

    Raises:
        ValueError: If ``span_axis`` is not one of ``"x"``, ``"y"``, ``"z"``.
    """
    if span_axis not in _AXIS_INDEX:
        raise ValueError(
            f"span_axis must be one of {sorted(_AXIS_INDEX)!r}, got {span_axis!r}"
        )
    return _AXIS_INDEX[span_axis]


def read_deck_value(text: str, key: str) -> float:
    """Read a ``key = value`` pair from an IAMReX inputs deck's text.

    If ``key`` is assigned more than once (legal in ParmParse-style decks, where a later
    assignment overrides an earlier one), the LAST occurrence wins -- matching runtime behavior,
    not the first accidental/stale line.

    Args:
        text: The deck's full text.
        key: The full key name to match (e.g. ``"particle_inputs.hinge_y"``).

    Returns:
        The key's value, parsed as a float.

    Raises:
        ValueError: If ``key`` is not found in ``text``, or its value is not finite (NaN/inf) --
            a tolerance comparison against NaN is always ``False``, so an un-rejected NaN would
            silently defeat every downstream guard built on this function (`assert_hinge_at_span_root`
            included) rather than raising the `AssertionError` it exists to raise.
    """
    matches = re.findall(
        rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*(?:#.*)?$", text, re.MULTILINE
    )
    if not matches:
        raise ValueError(f"key {key!r} not found in the deck")
    value = float(matches[-1].strip())
    if not math.isfinite(value):
        raise ValueError(f"key {key!r} has a non-finite value: {value}")
    return value


def wing_half_span(vertex_path: str | Path, span_axis: str = "y") -> float:
    """Re-derive the wing's own half-span from its marker extent.

    Uses ``(max - min) / 2`` rather than ``max()`` alone: the committed ``wing.vertex`` happens to
    be exactly symmetric about 0 along the span axis (an artifact of ``generate-wing-planform``'s
    span/spacing dividing evenly), but that symmetry isn't a guaranteed invariant of every vertex
    file this could be pointed at -- ``max()`` alone would silently drift from the true half-span
    for an off-center marker set.

    Args:
        vertex_path: Path to the ``.vertex`` marker file (origin-centred, as the solver loads it).
        span_axis: Which axis ("x", "y", or "z") is the wing's span. Defaults to "y" (the current
            van Veen convention).

    Returns:
        Half-span length, in the geometry's own length units.

    Raises:
        ValueError: If ``span_axis`` is invalid, or ``vertex_path`` contains zero markers.
    """
    idx = axis_index(span_axis)
    markers = read_vertex_file(str(vertex_path))
    if markers.shape[0] == 0:
        raise ValueError(
            f"{vertex_path} contains zero markers -- cannot derive a span extent"
        )
    axis_values = markers[:, idx]
    return float(axis_values.max() - axis_values.min()) / 2.0


def assert_hinge_at_span_root(
    deck_text: str,
    vertex_path: str | Path,
    *,
    span_axis: str = "y",
    tol: float = 0.1,
) -> None:
    """Assert the deck's hinge sits at the wing's own root, derived from ``vertex_path``.

    Along ``span_axis``, the hinge-to-centre arm must equal the geometry's own half-span (from its
    marker extent) within ``tol``. Along the two non-span axes, the hinge must exactly equal the
    wing centre (``particle_inputs.{x,y,z}``) -- no spurious offset.

    Args:
        deck_text: The IAMReX inputs deck text (``particle_inputs.{x,y,z}`` and
            ``particle_inputs.hinge_{x,y,z}`` are read from it).
        vertex_path: Path to the ``.vertex`` marker file the deck's geometry resolves to. Passed
            explicitly rather than parsed from ``deck_text``'s ``geometry_file`` key -- this
            function is a pure geometry check with no filesystem-path-resolution responsibility;
            the caller supplies the deck's actual declared geometry file.
        span_axis: Which axis ("x", "y", or "z") is the wing's span. Defaults to "y" (the current
            van Veen convention).
        tol: Tolerance (in the geometry's own length units) for the span-axis arm comparison.
            Default 0.1 is ~7% of the wing's ~1.475 half-span -- well above float/deck round-trip
            noise, but over 14x tighter than the real bug's ~1.475 arm error (a midspan pivot has
            zero arm, so the error against the expected ~1.475 arm is ~1.475 itself; see design.md
            D1), so it cannot miss the failure mode this guard exists to catch.

    Raises:
        ValueError: If ``span_axis`` is invalid, ``vertex_path`` contains zero markers, or
            ``deck_text`` is missing (or has a non-finite value for) any required
            ``particle_inputs.{x,y,z}``/``particle_inputs.hinge_{x,y,z}`` key.
        AssertionError: If the span-axis arm doesn't match the geometry's half-span within
            ``tol``, or a non-span axis has a spurious offset from the wing centre.
    """
    half_span = wing_half_span(vertex_path, span_axis)

    center = {a: read_deck_value(deck_text, f"particle_inputs.{a}") for a in "xyz"}
    hinge = {a: read_deck_value(deck_text, f"particle_inputs.hinge_{a}") for a in "xyz"}

    arm = center[span_axis] - hinge[span_axis]
    if abs(abs(arm) - half_span) >= tol:
        raise AssertionError(
            f"hinge_{span_axis} arm {arm} is not within {tol} of the wing's own half-span "
            f"{half_span} (hinge sits near midspan, not the root)"
        )

    for axis in "xyz":
        if axis == span_axis:
            continue
        offset = hinge[axis] - center[axis]
        if abs(offset) >= _EXACT_OFFSET_TOL:
            raise AssertionError(
                f"hinge_{axis} ({hinge[axis]}) has a spurious offset ({offset}) from the wing "
                f"centre ({center[axis]})"
            )
