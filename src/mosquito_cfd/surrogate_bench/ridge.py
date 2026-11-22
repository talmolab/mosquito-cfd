"""Fourier × polynomial ridge reference (spec requirement "Ridge reference model", design D3).

Two stages, so every configuration carries equal weight:

1. Each training configuration's beat is periodically interpolated onto ``N_GRID`` uniform phases
   and projected onto ``[1, cos 2πhφ, sin 2πhφ]``, ``h = 1..H`` (exact on that grid for
   ``H < N_GRID / 2``).
2. Each coefficient is a ridge regression on monomials of the configurations' standardised
   settings, capped at what each setting's distinct values can identify, with an unpenalised
   intercept, ``λ = α · n_train_configs``, solved by least squares on the augmented system.

Pure numpy; never written as a checkpoint.
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.surrogate_bench.splits import SETTINGS

N_GRID = 256
PHASE_GRID = np.arange(N_GRID) / N_GRID
MIN_TRAIN_CONFIGS = 3
# The exploration's chosen point, pre-registered for the fixed-point entry (design D3).
RIDGE_FIXED_POINT = {"n_harmonics": 16, "degree": 3, "alpha": 1e-6}


# --- Stage 1: per-configuration Fourier coefficients ----------------------------------------


def _check_beat(
    phase: NDArray[np.floating], values: NDArray[np.floating], label: str
) -> None:
    if phase.shape[0] < 2:
        raise ValueError(f"{label} has fewer than 2 rows; cannot interpolate")
    if not np.all(np.isfinite(phase)) or np.any(phase < 0.0) or np.any(phase >= 1.0):
        raise ValueError(f"{label} has a phase outside [0, 1)")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} has a non-finite target value")


def resample_beat(
    phase: NDArray[np.floating], values: NDArray[np.floating], label: str = "beat"
) -> NDArray[np.floating]:
    """Periodically interpolate one beat onto :data:`PHASE_GRID`.

    Args:
        phase: ``(n,)`` phases in ``[0, 1)``, any order.
        values: ``(n, T)`` target values.
        label: Name used in error messages.

    Returns:
        ``(N_GRID, T)`` values on the grid.

    Raises:
        ValueError: On fewer than 2 rows, a phase outside ``[0, 1)``, a non-finite value or a
            duplicate phase.
    """
    phase = np.asarray(phase, dtype=float)
    values = np.asarray(values, dtype=float)
    _check_beat(phase, values, label)
    order = np.argsort(phase, kind="stable")
    phase, values = phase[order], values[order]
    if np.any(np.diff(phase) == 0.0):
        raise ValueError(f"{label} has a duplicate phase")
    return np.column_stack(
        [
            np.interp(PHASE_GRID, phase, values[:, j], period=1.0)
            for j in range(values.shape[1])
        ]
    )


def fourier_basis(
    phase: NDArray[np.floating], n_harmonics: int
) -> NDArray[np.floating]:
    """``[1, cos 2π·1φ, sin 2π·1φ, …, cos 2πHφ, sin 2πHφ]`` at each phase, ``(n, 2H + 1)``."""
    phase = np.asarray(phase, dtype=float)
    columns = [np.ones_like(phase)]
    for h in range(1, n_harmonics + 1):
        columns += [np.cos(2.0 * np.pi * h * phase), np.sin(2.0 * np.pi * h * phase)]
    return np.column_stack(columns)


def fourier_coefficients(
    grid_values: NDArray[np.floating], n_harmonics: int
) -> NDArray[np.floating]:
    """Orthogonal projection of grid samples onto :func:`fourier_basis`, ``(2H + 1, T)``.

    Exact for a signal band-limited to ``H < N_GRID / 2``. The coefficients for a smaller ``H``
    are the leading rows of those for a larger one.
    """
    if not 1 <= n_harmonics < N_GRID // 2:
        raise ValueError(
            f"n_harmonics must be in 1..{N_GRID // 2 - 1}, got {n_harmonics}"
        )
    basis = fourier_basis(PHASE_GRID, n_harmonics)
    weights = np.full(basis.shape[1], 2.0 / N_GRID)
    weights[0] = 1.0 / N_GRID
    return (basis * weights).T @ np.asarray(grid_values, dtype=float)


def config_coefficients(
    frame: pd.DataFrame, target_names: Sequence[str], n_harmonics: int
) -> tuple[list[str], NDArray[np.floating], NDArray[np.floating]]:
    """One coefficient set per configuration, whatever its row count.

    Args:
        frame: Target-beat rows with ``config_name``, the settings, ``phase`` and targets.
        target_names: Target columns.
        n_harmonics: Harmonics ``H``.

    Returns:
        ``(names, settings, coefficients)``: sorted configuration names, their ``(n_c, 3)``
        settings, and ``(n_c, 2H + 1, T)`` coefficients.

    Raises:
        ValueError: On a malformed beat (see :func:`resample_beat`) or settings that vary
            within a configuration.
    """
    names, settings, coeffs = [], [], []
    for name, rows in frame.groupby("config_name", sort=True):
        kin = rows[list(SETTINGS)].to_numpy(dtype=float)
        if np.any(kin != kin[0]):
            raise ValueError(f"configuration {name!r} has varying settings")
        grid = resample_beat(
            rows["phase"].to_numpy(dtype=float),
            rows[list(target_names)].to_numpy(dtype=float),
            label=f"configuration {name!r}",
        )
        names.append(str(name))
        settings.append(kin[0])
        coeffs.append(fourier_coefficients(grid, n_harmonics))
    return names, np.array(settings, dtype=float), np.array(coeffs)


# --- Stage 2: polynomial ridge -------------------------------------------------------------


def monomial_exponents(levels: Sequence[int], degree: int) -> list[tuple[int, ...]]:
    """Exponent tuples with total degree ``≤ degree`` and each exponent ``≤ L_v − 1``.

    Ordered by total degree, then with the first setting's power descending, so the intercept
    is column 0 and degree 1 reads ``[z_stroke, z_fstar, z_pitch]``.
    """
    ranges = [range(max(int(level), 1)) for level in levels]
    exps = [e for e in itertools.product(*ranges) if sum(e) <= degree]
    return sorted(exps, key=lambda e: (sum(e), tuple(-x for x in e)))


def polynomial_matrix(
    z: NDArray[np.floating], exponents: Sequence[tuple[int, ...]]
) -> NDArray[np.floating]:
    """Monomials of the standardised settings, ``(n, P)``."""
    return np.column_stack([np.prod(z ** np.array(e), axis=1) for e in exponents])


def solve_ridge(
    m: NDArray[np.floating], a: NDArray[np.floating], lam: float
) -> NDArray[np.floating]:
    """Ridge solution with an unpenalised intercept (column 0), by least squares.

    Solves ``[M; √λ·D] β = [A; 0]`` with ``D`` the identity without its intercept row, which
    avoids squaring the condition number as the normal equations do. ``A`` may hold several
    right-hand sides.
    """
    m = np.asarray(m, dtype=float)
    a = np.asarray(a, dtype=float)
    p = m.shape[1]
    penalty = np.sqrt(lam) * np.eye(p)[1:]
    zeros = np.zeros((p - 1,) + a.shape[1:])
    beta, *_ = np.linalg.lstsq(
        np.vstack([m, penalty]), np.concatenate([a, zeros]), rcond=None
    )
    return beta


def rank_record(m: NDArray[np.floating]) -> dict[str, Any]:
    """Rank of a polynomial matrix with its singular values as fractions of σ₁.

    ``tolerance`` is ``numpy.linalg.matrix_rank``'s default as a fraction of σ₁,
    ``max(m, n)·eps``. ``sigma_retained`` is the smallest retained value; ``sigma_dropped`` the
    largest dropped one (``None`` at full rank). The dropped value is round-off when the matrix
    is rank deficient and must never be compared by value.
    """
    m = np.asarray(m, dtype=float)
    sigma = np.linalg.svd(m, compute_uv=False)
    rank = int(np.linalg.matrix_rank(m))
    tolerance = max(m.shape) * np.finfo(float).eps
    return {
        "P": int(m.shape[1]),
        "rank": rank,
        "sigma_retained": float(sigma[rank - 1] / sigma[0]),
        "sigma_dropped": float(sigma[rank] / sigma[0]) if rank < len(sigma) else None,
        "tolerance": float(tolerance),
    }


@dataclass
class RidgeModel:
    """A fitted ridge reference."""

    n_harmonics: int
    degree: int
    alpha: float
    target_names: list[str]
    config_names: list[str]
    mean: NDArray[np.floating]
    std: NDArray[np.floating]
    exponents: list[tuple[int, ...]]
    config_matrix: NDArray[np.floating]
    beta: NDArray[np.floating]
    rank: dict[str, Any]
    selection: dict[str, Any] | None = field(default=None)

    @property
    def n_params(self) -> int:
        """Coefficients over all targets: ``T · (2H + 1) · P``."""
        return int(self.beta.size)

    def _z(self, settings: NDArray[np.floating]) -> NDArray[np.floating]:
        return (settings - self.mean) / self.std

    def predict(self, frame: pd.DataFrame) -> NDArray[np.floating]:
        """Evaluate the Fourier series at each row's own phase, ``(n, T)``."""
        settings = frame[list(SETTINGS)].to_numpy(dtype=float)
        rows = polynomial_matrix(self._z(settings), self.exponents)
        coeff = (rows @ self.beta).reshape(len(frame), 2 * self.n_harmonics + 1, -1)
        basis = fourier_basis(frame["phase"].to_numpy(dtype=float), self.n_harmonics)
        return np.einsum("nk,nkt->nt", basis, coeff)


def _standardise(settings: NDArray[np.floating]) -> tuple[NDArray, NDArray, list[int]]:
    """Mean and std over configurations; a one-level setting is left unscaled (no column)."""
    levels = [len(np.unique(settings[:, j])) for j in range(settings.shape[1])]
    mean = settings.mean(axis=0)
    std = settings.std(axis=0)
    std = np.where(np.array(levels) > 1, std, 1.0)
    return mean, std, levels


def fit_from_coefficients(
    settings: NDArray[np.floating],
    coeffs: NDArray[np.floating],
    *,
    degree: int,
    alpha: float,
) -> tuple[NDArray, NDArray, list[tuple[int, ...]], NDArray, NDArray]:
    """Stage 2 on precomputed coefficients ``(n_c, K, T)``: returns mean, std, exponents, M, β."""
    if settings.shape[0] < MIN_TRAIN_CONFIGS:
        raise ValueError(
            f"the ridge needs at least {MIN_TRAIN_CONFIGS} training configurations, "
            f"got {settings.shape[0]}"
        )
    mean, std, levels = _standardise(settings)
    exponents = monomial_exponents(levels, degree)
    m = polynomial_matrix((settings - mean) / std, exponents)
    lam = alpha * settings.shape[0]
    beta = solve_ridge(m, coeffs.reshape(settings.shape[0], -1), lam)
    return mean, std, exponents, m, beta


def fit_ridge(
    frame: pd.DataFrame,
    target_names: Sequence[str],
    *,
    n_harmonics: int,
    degree: int,
    alpha: float,
) -> RidgeModel:
    """Fit the ridge reference at a given ``(H, d, α)``.

    Args:
        frame: Target-beat rows of the training configurations.
        target_names: Target columns.
        n_harmonics: Fourier harmonics ``H``.
        degree: Total polynomial degree ``d``.
        alpha: Ridge strength; ``λ = α · n_train_configs``.

    Returns:
        The fitted :class:`RidgeModel` (``selection`` is ``None``).

    Raises:
        ValueError: On fewer than 3 training configurations or a malformed beat.
    """
    names, settings, coeffs = config_coefficients(frame, target_names, n_harmonics)
    mean, std, exponents, m, beta = fit_from_coefficients(
        settings, coeffs, degree=degree, alpha=alpha
    )
    return RidgeModel(
        n_harmonics=n_harmonics,
        degree=degree,
        alpha=alpha,
        target_names=list(target_names),
        config_names=names,
        mean=mean,
        std=std,
        exponents=exponents,
        config_matrix=m,
        beta=beta,
        rank=rank_record(m),
    )


def fit_ridge_fixed(frame: pd.DataFrame, target_names: Sequence[str]) -> RidgeModel:
    """The ``ridge_fixed`` entry: :data:`RIDGE_FIXED_POINT`, no selection."""
    return fit_ridge(frame, target_names, **RIDGE_FIXED_POINT)
