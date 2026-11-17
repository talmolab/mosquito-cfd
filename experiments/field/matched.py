"""Lab-frame POD scored on the fluid a wing-fixed box covers, so the two frames compare like for like.

``box_mask`` marks the lab cells whose centres lie in a box that moves with the wing. Two uses:

* ``masked_gram``: snapshot inner products of the lab field with everything outside the box set to
  zero. POD of that is the lab-frame description of exactly the fluid the wing-frame box holds.
* ``restricted_residuals``: reconstruction error of a POD fitted on the whole lab patch, summed only
  over the cells in the box.

Both work block by block on a memory-mapped ``(n_snap, n_cell * ncomp)`` matrix whose columns are
ordered cell-major (all components of cell 0, then cell 1, ...).
"""

from __future__ import annotations

import numpy as np

from experiments.field.pod import PodGram


def box_mask(x, y, z, rot, hinge, lo, hi, *, period_y: float | None = None) -> np.ndarray:
    """Cells ``(ix, iy, iz)`` whose centre, in wing coordinates ``R^T (p - hinge)``, lies in ``[lo, hi)``.

    With ``period_y`` the y images one period either side are tested too.
    """
    rot, hinge = np.asarray(rot, dtype=float), np.asarray(hinge, dtype=float)
    lo, hi = np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)
    dx = np.asarray(x, dtype=float)[:, None, None] - hinge[0]
    dz = np.asarray(z, dtype=float)[None, None, :] - hinge[2]
    out = np.zeros((len(x), len(y), len(z)), dtype=bool)
    for shift in (0.0,) if period_y is None else (-period_y, 0.0, period_y):
        dy = np.asarray(y, dtype=float)[None, :, None] - hinge[1] + shift
        inside = np.ones(out.shape, dtype=bool)
        for a in range(3):  # xi_a = column a of R dotted with (p - hinge)
            xi = dx * rot[0, a] + dy * rot[1, a] + dz * rot[2, a]
            inside &= (xi >= lo[a]) & (xi < hi[a])
        out |= inside
    return out


def _blocks(n_cell: int, block_cells: int):
    for lo in range(0, n_cell, block_cells):
        yield lo, min(lo + block_cells, n_cell)


def _load(a, masks, lo, hi, ncomp, scale):
    s = np.asarray(a[:, lo * ncomp : hi * ncomp], dtype=np.float64)
    if scale is not None:
        s *= np.asarray(scale, dtype=float)[:, None]
    return s, np.repeat(np.asarray(masks[:, lo:hi], dtype=bool), ncomp, axis=1)


def masked_gram(a, masks, *, scale=None, ncomp: int = 3, block_cells: int = 30_000) -> np.ndarray:
    """``(a * mask) @ (a * mask).T`` with rows of ``a`` multiplied by ``scale``."""
    n_cell = masks.shape[1]
    out = np.zeros((a.shape[0], a.shape[0]))
    for lo, hi in _blocks(n_cell, block_cells):
        s, m = _load(a, masks, lo, hi, ncomp, scale)
        s *= m
        out += s @ s.T
    return out


def restricted_residuals(
    a, masks, train, test, p: PodGram, z_test, ranks, *, scale=None, ncomp: int = 3, block_cells: int = 30_000
) -> dict[str, np.ndarray]:
    """Squared reconstruction residual of the test snapshots, summed over each snapshot's masked cells.

    ``p`` is the POD of the (scaled) training rows of ``a``; ``z_test`` their coefficients for the test
    rows. Returns ``residual`` ``(n_test, n_ranks)``, and ``centred`` / ``total`` ``(n_test,)``: the
    masked sums of ``(x - training mean)^2`` and ``x^2``.
    """
    ranks = tuple(ranks)
    r_max = max(ranks)
    rows = np.concatenate([train, test])
    nt = len(train)
    sc = None if scale is None else np.asarray(scale, dtype=float)[rows]
    out = {"residual": np.zeros((len(test), len(ranks))), "centred": np.zeros(len(test)), "total": np.zeros(len(test))}
    for lo, hi in _blocks(masks.shape[1], block_cells):
        s = np.asarray(a[:, lo * ncomp : hi * ncomp][rows], dtype=np.float64)
        if sc is not None:
            s *= sc[:, None]
        m = np.repeat(np.asarray(masks[test, lo:hi], dtype=bool), ncomp, axis=1)
        mean = s[:nt].mean(axis=0)
        modes = (p.vecs[:, :r_max].T @ (s[:nt] - mean)) / p.sing[:r_max, None]
        out["total"] += (s[nt:] ** 2 * m).sum(axis=1)
        res = s[nt:] - mean
        out["centred"] += (res**2 * m).sum(axis=1)
        done = 0
        for j, r in enumerate(ranks):
            res = res - z_test[:, done:r] @ modes[done:r]
            done = r
            out["residual"][:, j] += (res**2 * m).sum(axis=1)
    return out


class HalfCellSmoothed:
    """A field matrix as it would look after trilinear interpolation half a cell along every axis.

    That is the average over each 2x2x2 group of neighbouring cells: the strongest smoothing a
    trilinear resample at this cell size can apply. It is the control for the wing-frame resample,
    which smooths by some amount between none and this. y wraps; x and z repeat the last layer.

    Supports only ``view[:, lo:hi]`` with ``lo`` and ``hi`` on whole x-layers, which is what the
    block-wise routines in this module and ``pod.gram`` ask for when their block is one layer.
    """

    def __init__(self, a, shape):
        self._a, self._shape = a, tuple(int(s) for s in shape)
        self._layer = int(np.prod(self._shape[1:]))
        self.shape = a.shape

    def __getitem__(self, key) -> np.ndarray:
        rows, cols = key
        if rows != slice(None) or not isinstance(cols, slice) or cols.step not in (None, 1):
            raise ValueError("only view[:, lo:hi] is supported")
        lo, hi = cols.start or 0, min(cols.stop if cols.stop is not None else self.shape[1], self.shape[1])
        if lo % self._layer or hi % self._layer:
            raise ValueError(f"column range must cover whole x-layers of {self._layer} values")
        nx = self._shape[0]
        x0, x1 = lo // self._layer, hi // self._layer
        f = np.asarray(self._a[:, x0 * self._layer : min(x1 + 1, nx) * self._layer], dtype=np.float32)
        f = f.reshape(f.shape[0], -1, *self._shape[1:])
        if x1 == nx:
            f = np.concatenate([f, f[:, -1:]], axis=1)
        f = 0.5 * (f[:, :-1] + f[:, 1:])
        f = 0.5 * (f + np.roll(f, -1, axis=2))
        f = 0.5 * (f + np.concatenate([f[:, :, :, 1:], f[:, :, :, -1:]], axis=3))
        return f.reshape(f.shape[0], -1)
