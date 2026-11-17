"""Non-neural comparator: ridge regression on Fourier harmonics in phase x polynomials in kinematics."""

from __future__ import annotations

from collections.abc import Sequence
from itertools import combinations_with_replacement

import numpy as np
import pandas as pd

from experiments.common.features import KINEMATIC
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS


def _design(df: pd.DataFrame, mean: np.ndarray, scale: np.ndarray, harmonics: int, degree: int) -> np.ndarray:
    k = (df[list(KINEMATIC)].to_numpy(dtype=float) - mean) / scale
    poly = [np.ones(len(df))]
    for d in range(1, degree + 1):
        for combo in combinations_with_replacement(range(k.shape[1]), d):
            poly.append(np.prod(k[:, combo], axis=1))
    poly = np.column_stack(poly)
    phase = df["phase"].to_numpy(dtype=float)
    four = [np.ones(len(df))]
    for h in range(1, harmonics + 1):
        four += [np.sin(2 * np.pi * h * phase), np.cos(2 * np.pi * h * phase)]
    four = np.column_stack(four)
    return (poly[:, :, None] * four[:, None, :]).reshape(len(df), -1)


def n_coefficients(harmonics: int, degree: int, n_kin: int = 3) -> int:
    from math import comb

    return comb(n_kin + degree, degree) * (2 * harmonics + 1) * len(TARGET_COLUMNS)


def fourier_poly_fit_predict(
    df: pd.DataFrame, train_configs: Sequence[str], test_configs: Sequence[str], *,
    harmonics: int = 4, degree: int = 2, alpha: float = 1e-6,
) -> np.ndarray:
    """Fit on ``train_configs`` rows, predict ``test_configs`` rows (in ``df`` row order)."""
    tr = df[df["config_name"].isin(list(train_configs))]
    te = df[df["config_name"].isin(list(test_configs))]
    k = tr[list(KINEMATIC)].to_numpy(dtype=float)
    mean, scale = k.mean(axis=0), np.where(k.std(axis=0) > 0, k.std(axis=0), 1.0)
    a = _design(tr, mean, scale, harmonics, degree)
    y = tr[TARGET_COLUMNS].to_numpy(dtype=float)
    coef = np.linalg.solve(a.T @ a + alpha * len(tr) * np.eye(a.shape[1]), a.T @ y)
    return _design(te, mean, scale, harmonics, degree) @ coef
