"""Resample a lab-frame velocity field onto a grid that moves with the wing."""

from __future__ import annotations

import numpy as np


def trilinear(field: np.ndarray, origin, spacing: float, pts: np.ndarray, *, periodic_len=(None, None, None)) -> np.ndarray:
    """Trilinear interpolation of ``field[ix, iy, iz, c]`` (cell centres at ``origin + spacing * i``).

    An axis with a ``periodic_len`` wraps; other axes clamp to the outermost cells.
    """
    n = field.shape[:3]
    idx0, frac = [], []
    for a in range(3):
        coord = np.asarray(pts[:, a], dtype=float)
        if periodic_len[a] is not None:
            coord = np.mod(coord - origin[a], periodic_len[a]) + origin[a]
        t = (coord - origin[a]) / spacing
        if periodic_len[a] is None:
            t = np.clip(t, 0.0, n[a] - 1.0)
        i0 = np.floor(t).astype(int)
        frac.append(t - i0)
        idx0.append(i0)
    out = np.zeros((len(pts), field.shape[3]))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = np.ones(len(pts))
                ii = []
                for a, d in enumerate((dx, dy, dz)):
                    w = w * (frac[a] if d else 1.0 - frac[a])
                    i = idx0[a] + d
                    ii.append(np.mod(i, n[a]) if periodic_len[a] is not None else np.minimum(i, n[a] - 1))
                out += w[:, None] * field[ii[0], ii[1], ii[2]]
    return out


def wing_frame_sample(
    field: np.ndarray, origin, spacing: float, rot: np.ndarray, hinge: np.ndarray, xi: np.ndarray, *,
    periodic_len=(None, None, None),
) -> np.ndarray:
    """Velocity at wing-fixed points ``xi`` (lab position ``hinge + R xi``), expressed in wing axes (``R^T u``)."""
    pts = np.asarray(hinge, dtype=float) + np.asarray(xi, dtype=float) @ np.asarray(rot).T
    return trilinear(field, origin, spacing, pts, periodic_len=periodic_len) @ np.asarray(rot)
