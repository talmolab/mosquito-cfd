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
) -> np.ndarray:
    """Generate Lagrangian markers for a wing planform.

    Parameters
    ----------
    shape : PlanformShape or str
        Planform shape: "rectangular" or "elliptic"
    span : float
        Wing span in meters (z-direction)
    chord : float
        Wing chord in meters (x-direction). For elliptic, this is the
        maximum chord at the wing root.
    spacing : float
        Marker spacing in meters
    center : tuple
        Center position (x, y, z) in meters. Default is origin.

    Returns
    -------
    markers : np.ndarray
        Array of marker positions with shape (N, 3)
    """
    if isinstance(shape, str):
        shape = PlanformShape(shape.lower())

    cx, cy, cz = center
    markers = []

    if shape == PlanformShape.RECTANGULAR:
        n_span = int(span / spacing)
        n_chord = int(chord / spacing)
        for i in range(n_span):
            for j in range(n_chord):
                x = cx - chord / 2 + (j + 0.5) * spacing
                y = cy
                z = cz - span / 2 + (i + 0.5) * spacing
                markers.append([x, y, z])

    elif shape == PlanformShape.ELLIPTIC:
        n_span = int(span / spacing)
        for i in range(n_span):
            z_rel = -span / 2 + (i + 0.5) * spacing
            z_norm = 2 * z_rel / span
            local_chord = chord * np.sqrt(max(0, 1 - z_norm**2))
            if local_chord < spacing:
                continue
            n_chord_local = max(1, int(local_chord / spacing))
            for j in range(n_chord_local):
                x = cx - local_chord / 2 + (j + 0.5) * (local_chord / n_chord_local)
                y = cy
                z = cz + z_rel
                markers.append([x, y, z])

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
