"""Parametric wing planform generators.

Generate Lagrangian markers for rectangular and elliptic wing planforms.
Based on van Veen et al. (2022) for insect wing aerodynamics.
"""

from enum import Enum

import numpy as np


class PlanformShape(Enum):
    """Supported wing planform shapes."""

    RECTANGULAR = "rectangular"
    ELLIPTIC = "elliptic"


def generate_planform(
    shape: PlanformShape | str,
    span: float,
    chord: float,
    spacing: float,
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
    span_axis: str = "z",
) -> np.ndarray:
    """Generate Lagrangian markers for a wing planform.

    Parameters
    ----------
    shape : PlanformShape or str
        Planform shape: "rectangular" or "elliptic"
    span : float
        Wing span in meters (along ``span_axis``).
    chord : float
        Wing chord in meters (x-direction). For elliptic, this is the
        maximum chord at the wing root.
    spacing : float
        Marker spacing in meters
    center : tuple
        Center position (x, y, z) in meters. Default is origin.
    span_axis : {"z", "y"}
        Axis the span runs along. ``"z"`` (default) is the legacy orientation
        (span in z, wing flat in x-z). ``"y"`` is the van Veen / Bomphrey
        convention (Tier T2a): span in y, chord in x, wing flat in the x-y
        plane. The chord is always along x; only the span axis moves.

    Returns:
    -------
    markers : np.ndarray
        Array of marker positions with shape (N, 3)
    """
    if isinstance(shape, str):
        shape = PlanformShape(shape.lower())
    if span_axis not in ("y", "z"):
        raise ValueError(f"span_axis must be 'y' or 'z', got {span_axis!r}")

    cx, cy, cz = center
    markers = []

    def _place(chord_off: float, span_off: float) -> list[float]:
        # Chord always along x; span along span_axis; wing flat in the third axis.
        if span_axis == "z":
            return [cx + chord_off, cy, cz + span_off]
        return [cx + chord_off, cy + span_off, cz]  # span_axis == "y"

    if shape == PlanformShape.RECTANGULAR:
        n_span = int(span / spacing)
        n_chord = int(chord / spacing)
        for i in range(n_span):
            span_off = -span / 2 + (i + 0.5) * spacing
            for j in range(n_chord):
                chord_off = -chord / 2 + (j + 0.5) * spacing
                markers.append(_place(chord_off, span_off))

    elif shape == PlanformShape.ELLIPTIC:
        n_span = int(span / spacing)
        for i in range(n_span):
            span_rel = -span / 2 + (i + 0.5) * spacing
            span_norm = 2 * span_rel / span
            local_chord = chord * np.sqrt(max(0, 1 - span_norm**2))
            if local_chord < spacing:
                continue
            n_chord_local = max(1, int(local_chord / spacing))
            for j in range(n_chord_local):
                chord_off = -local_chord / 2 + (j + 0.5) * (local_chord / n_chord_local)
                markers.append(_place(chord_off, span_rel))

    return np.array(markers)


def estimate_marker_count(
    shape: PlanformShape | str,
    span: float,
    chord: float,
    spacing: float,
) -> int:
    """Estimate marker count without generating them."""
    if isinstance(shape, str):
        shape = PlanformShape(shape.lower())

    n_span = int(span / spacing)
    n_chord = int(chord / spacing)

    if shape == PlanformShape.RECTANGULAR:
        return n_span * n_chord
    elif shape == PlanformShape.ELLIPTIC:
        return int(n_span * n_chord * np.pi / 4)
    return 0
