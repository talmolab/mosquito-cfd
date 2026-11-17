"""POD by the method of snapshots, in memory and out of core.

In memory: ``fit`` / ``recon_error`` / ``encode`` / ``decode`` on an ``(n_snap, n_dof)`` array.

Out of core: everything the experiment needs (spectrum, coefficients, reconstruction error on
unseen snapshots) follows from inner products between snapshots, so the big patch never has to be
decomposed directly. ``gram`` accumulates those inner products block by block from memory-mapped
matrices; ``fit_gram`` / ``encode_gram`` / ``recon_error_gram`` work from them.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Pod:
    mean: np.ndarray  # (n_dof,)
    modes: np.ndarray  # (n_modes, n_dof), orthonormal rows
    sing: np.ndarray  # (n_modes,) singular values of the mean-removed snapshot matrix


def _eig_desc(g: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    w, v = np.linalg.eigh(g)
    order = np.argsort(w)[::-1]
    return np.clip(w[order], 0.0, None), v[:, order]


def fit(x: np.ndarray, *, rel_tol: float = 1e-10) -> Pod:
    """POD of ``x`` (rows are snapshots) about its mean; modes with negligible energy are dropped."""
    x = np.asarray(x)
    mean = x.mean(axis=0, dtype=np.float64)
    xc = x.astype(np.float64) - mean
    w, v = _eig_desc(xc @ xc.T)
    keep = w > rel_tol * w[0]
    sing = np.sqrt(w[keep])
    modes = (v[:, keep].T @ xc) / sing[:, None]
    return Pod(mean=mean, modes=modes, sing=sing)


def energy_fraction(p: Pod) -> np.ndarray:
    """Cumulative share of mean-removed energy captured by the first k modes."""
    e = p.sing**2
    return np.cumsum(e) / e.sum()


def encode(p: Pod, x: np.ndarray, r: int) -> np.ndarray:
    return (np.asarray(x, dtype=np.float64) - p.mean) @ p.modes[:r].T


def decode(p: Pod, z: np.ndarray) -> np.ndarray:
    return z @ p.modes[: z.shape[1]] + p.mean


def recon_error(p: Pod, x: np.ndarray, r: int) -> float:
    """Relative error ``||xc - P_r xc|| / ||xc||`` with ``xc = x - training mean`` (Frobenius)."""
    xc = np.asarray(x, dtype=np.float64) - p.mean
    z = xc @ p.modes[:r].T
    total = float(np.sum(xc**2))
    return float(np.sqrt(max(total - float(np.sum(z**2)), 0.0) / total))


# --- out of core -------------------------------------------------------------------------------


def gram(a: np.ndarray, b: np.ndarray | None = None, *, block: int = 250_000) -> np.ndarray:
    """``a @ b.T`` in float64, accumulated over column blocks (``a``/``b`` may be memory-mapped)."""
    b = a if b is None else b
    out = np.zeros((a.shape[0], b.shape[0]))
    for lo in range(0, a.shape[1], block):
        sa = np.asarray(a[:, lo : lo + block], dtype=np.float64)
        sb = sa if b is a else np.asarray(b[:, lo : lo + block], dtype=np.float64)
        out += sa @ sb.T
    return out


@dataclass
class PodGram:
    """POD of a training set known only through its Gram matrix ``g_tt[i, j] = x_i . x_j``."""

    sing: np.ndarray  # (n_modes,)
    vecs: np.ndarray  # (n_train, n_modes) eigenvectors of the centred Gram matrix
    row_mean: np.ndarray  # (n_train,) mean over j of g_tt[i, j]  (= x_i . xbar)
    all_mean: float  # xbar . xbar


def fit_gram(g_tt: np.ndarray, *, rel_tol: float = 1e-10) -> PodGram:
    row_mean = g_tt.mean(axis=1)
    all_mean = float(g_tt.mean())
    gc = g_tt - row_mean[:, None] - row_mean[None, :] + all_mean
    w, v = _eig_desc(gc)
    keep = w > rel_tol * w[0]
    return PodGram(sing=np.sqrt(w[keep]), vecs=v[:, keep], row_mean=row_mean, all_mean=all_mean)


def energy_fraction_gram(p: PodGram) -> np.ndarray:
    e = p.sing**2
    return np.cumsum(e) / e.sum()


def encode_gram(p: PodGram, g_xt: np.ndarray) -> np.ndarray:
    """POD coefficients of snapshots ``x`` given ``g_xt[i, j] = x_i . t_j`` (training snapshots ``t``)."""
    centred = g_xt - g_xt.mean(axis=1, keepdims=True) - p.row_mean[None, :] + p.all_mean
    return centred @ p.vecs / p.sing[None, :]


def centred_sq_norm(p: PodGram, g_xt: np.ndarray, sq_norm: np.ndarray) -> np.ndarray:
    """``||x_i - xbar||^2`` from ``x_i . x_i`` and ``g_xt``."""
    return sq_norm - 2.0 * g_xt.mean(axis=1) + p.all_mean


def recon_error_gram(p: PodGram, g_xt: np.ndarray, sq_norm: np.ndarray, r: int) -> float:
    """Same quantity as :func:`recon_error`, pooled over the snapshots ``x``."""
    z = encode_gram(p, g_xt)[:, :r]
    total = float(centred_sq_norm(p, g_xt, sq_norm).sum())
    return float(np.sqrt(max(total - float(np.sum(z**2)), 0.0) / total))


def modes_from_gram(p: PodGram, train: np.ndarray, r: int, *, block: int = 250_000) -> tuple[np.ndarray, np.ndarray]:
    """First ``r`` spatial modes and the training mean, built block by block from ``train``."""
    n_dof = train.shape[1]
    modes, mean = np.empty((r, n_dof), dtype=np.float32), np.empty(n_dof, dtype=np.float32)
    for lo in range(0, n_dof, block):
        s = np.asarray(train[:, lo : lo + block], dtype=np.float64)
        m = s.mean(axis=0)
        mean[lo : lo + block] = m
        modes[:, lo : lo + block] = (p.vecs[:, :r].T @ (s - m)) / p.sing[:r, None]
    return modes, mean


# --- split hygiene -----------------------------------------------------------------------------


def training_rows(index: pd.DataFrame, holdout: tuple[str, ...]) -> pd.DataFrame:
    """Rows of a cache index that may be used to build a basis."""
    return index[~index["config"].isin(list(holdout))]


def assert_no_holdout(index: pd.DataFrame, holdout: tuple[str, ...]) -> None:
    bad = sorted(set(index["config"]) & set(holdout))
    if bad:
        raise ValueError(f"holdout configs in a training set: {bad}")
