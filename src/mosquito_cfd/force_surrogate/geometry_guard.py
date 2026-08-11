"""Geometric-consistency guard: the sweep base deck's hinge vs. the wing's own geometry.

OpenSpec change ``fix-force-surrogate-sweep-hinge``. Deliberately not a byte-identity check —
re-derives "root hinge" from the referenced ``wing.vertex`` marker extent every call, so a hinge
that is self-consistently wrong (frozen from a stale deck against a geometry file that has since
moved to a new axis convention -- exactly what happened) cannot hide behind it the way it hid
behind the pre-existing byte-identity guards for over a month.
"""

from __future__ import annotations

import re
from pathlib import Path

from mosquito_cfd.geometry.vertex_io import read_vertex_file

_AXIS_INDEX = {"x": 0, "y": 1, "z": 2}


def read_deck_value(text: str, key: str) -> float:
    """Read a single ``key = value`` pair from an IAMReX inputs deck's text.

    Args:
        text: The deck's full text.
        key: The full key name to match (e.g. ``"particle_inputs.hinge_y"``).

    Returns:
        The key's value, parsed as a float.

    Raises:
        ValueError: If ``key`` is not found in ``text``.
    """
    match = re.search(
        rf"^\s*{re.escape(key)}\s*=\s*(.+?)\s*(?:#.*)?$", text, re.MULTILINE
    )
    if match is None:
        raise ValueError(f"key {key!r} not found in the deck")
    return float(match.group(1).strip())


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

    Raises:
        ValueError: If ``vertex_path`` contains zero markers.
        AssertionError: If the span-axis arm doesn't match the geometry's half-span within
            ``tol``, or a non-span axis has a spurious offset from the wing centre.
    """
    markers = read_vertex_file(str(vertex_path))
    if markers.shape[0] == 0:
        raise ValueError(
            f"{vertex_path} contains zero markers -- cannot derive a span extent"
        )

    axis_idx = _AXIS_INDEX[span_axis]
    half_span = float(markers[:, axis_idx].max())

    center = {a: read_deck_value(deck_text, f"particle_inputs.{a}") for a in "xyz"}
    hinge = {a: read_deck_value(deck_text, f"particle_inputs.hinge_{a}") for a in "xyz"}

    arm = center[span_axis] - hinge[span_axis]
    assert abs(abs(arm) - half_span) < tol, (
        f"hinge_{span_axis} arm {arm} is not within {tol} of the wing's own half-span "
        f"{half_span} (hinge sits near midspan, not the root)"
    )

    for axis in "xyz":
        if axis == span_axis:
            continue
        offset = hinge[axis] - center[axis]
        assert abs(offset) < 1e-9, (
            f"hinge_{axis} ({hinge[axis]}) has a spurious offset ({offset}) from the wing "
            f"centre ({center[axis]})"
        )
