"""Small statistics used by the residual analysis."""

from __future__ import annotations

import numpy as np

REVERSALS = (0.25, 0.75)  # stroke angle phi = phi0 sin(2 pi phase) is extremal here


def reversal_share(sq_err: np.ndarray, phase: np.ndarray, *, half_width: float = 0.05) -> float:
    """Share of summed squared error within ``half_width`` (in phase) of a stroke reversal.

    Errors spread evenly over the beat give ``4 * half_width``.
    """
    phase = np.asarray(phase, dtype=float)
    near = np.zeros(phase.shape, dtype=bool)
    for r in REVERSALS:
        d = np.abs(phase - r)
        near |= np.minimum(d, 1.0 - d) <= half_width
    sq_err = np.asarray(sq_err, dtype=float)
    return float(sq_err[near].sum() / sq_err.sum())


def position_class(stroke: float, fstar: float, pitch: float) -> str:
    """Where a config sits in the 3x3x3 sweep: corner, edge, face (centre of a face) or centre."""
    off = sum(not np.isclose(v, mid) for v, mid in ((stroke, 45.0), (fstar, 1.0), (pitch, 45.0)))
    return {3: "corner", 2: "edge", 1: "face", 0: "centre"}[off]
