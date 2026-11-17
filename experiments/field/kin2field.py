"""Predict a flow field from wing kinematics and phase alone, through POD coefficients.

``fit_predict`` is the E4 ridge model (Fourier harmonics in phase x polynomials in the three
kinematic inputs) with POD coefficients as targets. Because the modes are orthonormal, the error of
the decoded field follows from the coefficients and each snapshot's energy (``field_error_sq``), so
the experiment needs only Gram matrices. ``nearest_snapshot_error_sq`` is the no-model baseline:
reuse the training snapshot nearest in kinematics and phase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from experiments.common.features import KINEMATIC
from experiments.common.ridge import _design


def _standardiser(train: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    k = train[list(KINEMATIC)].to_numpy(dtype=float)
    return k.mean(axis=0), np.where(k.std(axis=0) > 0, k.std(axis=0), 1.0)


def fit_predict(
    train: pd.DataFrame, y_train: np.ndarray, test: pd.DataFrame, *, harmonics: int, degree: int, alpha: float
) -> np.ndarray:
    """Ridge fit of ``y_train`` (n_train, n_targets) on the rows of ``train``; prediction for ``test``."""
    mean, scale = _standardiser(train)
    a = _design(train, mean, scale, harmonics, degree)
    coef = np.linalg.solve(a.T @ a + alpha * len(train) * np.eye(a.shape[1]), a.T @ np.asarray(y_train, dtype=float))
    return _design(test, mean, scale, harmonics, degree) @ coef


def field_error_sq(z_true: np.ndarray, z_pred: np.ndarray, centred_sq: np.ndarray) -> np.ndarray:
    """``||decode(z_pred) - x||^2`` per snapshot.

    ``z_true`` are the snapshot's own first-r POD coefficients and ``centred_sq`` is
    ``||x - training mean||^2``: the error is the coefficient error plus what r modes cannot hold.
    """
    return ((z_pred - z_true) ** 2).sum(axis=1) + centred_sq - (z_true**2).sum(axis=1)


def nearest_snapshot_error_sq(
    index: pd.DataFrame, g: np.ndarray, train: np.ndarray, test: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Error of standing in, for each test row, the training row of the nearest config at the nearest phase.

    ``g`` is the Gram matrix of all rows. Nearest config is by standardised kinematics; nearest phase
    is circular. Returns the squared field differences and the chosen training row numbers.
    """
    mean, scale = _standardiser(index.iloc[train])
    k = (index[list(KINEMATIC)].to_numpy(dtype=float) - mean) / scale
    cfg, phase = index["config"].to_numpy(), index["phase"].to_numpy(dtype=float)
    cfg_rows = {c: train[cfg[train] == c] for c in np.unique(cfg[train])}
    cfg_k = {c: k[rows[0]] for c, rows in cfg_rows.items()}
    pick = np.empty(len(test), dtype=int)
    for n, i in enumerate(test):
        rows = cfg_rows[min(cfg_k, key=lambda c: float(np.sum((cfg_k[c] - k[i]) ** 2)))]
        d = np.abs(phase[rows] - phase[i])
        pick[n] = rows[np.argmin(np.minimum(d, 1.0 - d))]
    return g[test, test] - 2.0 * g[test, pick] + g[pick, pick], pick
