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
import warnings
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
# The pre-registered selection grid and fragility bound (design D3).
GRID_H: tuple[int, ...] = (1, 2, 4, 8, 12, 16, 24, 32)
GRID_D: tuple[int, ...] = (1, 2, 3)
GRID_ALPHA: tuple[float, ...] = (1e-8, 1e-6, 1e-4, 1e-2, 1.0)
FRAGILE_MARGIN = 1e-6


class SelectionNotRecheckedWarning(UserWarning):
    """A fragile split was refitted at its committed point instead of being re-selected."""


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


def config_grids(
    frame: pd.DataFrame, target_names: Sequence[str]
) -> tuple[list[str], NDArray[np.floating], NDArray[np.floating]]:
    """Each configuration's beat on :data:`PHASE_GRID`, one entry per configuration.

    Args:
        frame: Target-beat rows with ``config_name``, the settings, ``phase`` and targets.
        target_names: Target columns.

    Returns:
        ``(names, settings, grids)``: sorted configuration names, their ``(n_c, 3)`` settings,
        and ``(n_c, N_GRID, T)`` resampled values.

    Raises:
        ValueError: On a malformed beat (see :func:`resample_beat`) or settings that vary
            within a configuration.
    """
    names, settings, grids = [], [], []
    for name, rows in frame.groupby("config_name", sort=True):
        kin = rows[list(SETTINGS)].to_numpy(dtype=float)
        if np.any(kin != kin[0]):
            raise ValueError(f"configuration {name!r} has varying settings")
        grids.append(
            resample_beat(
                rows["phase"].to_numpy(dtype=float),
                rows[list(target_names)].to_numpy(dtype=float),
                label=f"configuration {name!r}",
            )
        )
        names.append(str(name))
        settings.append(kin[0])
    return names, np.array(settings, dtype=float), np.array(grids)


def config_coefficients(
    frame: pd.DataFrame, target_names: Sequence[str], n_harmonics: int
) -> tuple[list[str], NDArray[np.floating], NDArray[np.floating]]:
    """One coefficient set per configuration, whatever its row count.

    Returns:
        ``(names, settings, coefficients)`` with coefficients ``(n_c, 2H + 1, T)``.
    """
    names, settings, grids = config_grids(frame, target_names)
    coeffs = np.array([fourier_coefficients(g, n_harmonics) for g in grids])
    return names, settings, coeffs


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


# --- Selection: leave-one-configuration-out CV and the one-standard-error rule -----------


def _order_key(candidate: tuple[int, int, float]) -> tuple[int, int, float]:
    """Simplest first: smallest ``H``, then smallest ``d``, then largest ``α``."""
    h, d, alpha = candidate
    return (h, d, -alpha)


def _grid_edge(candidate: tuple[int, int, float]) -> dict[str, bool]:
    h, d, alpha = candidate
    return {
        "H": h in (GRID_H[0], GRID_H[-1]),
        "d": d in (GRID_D[0], GRID_D[-1]),
        "alpha": alpha in (GRID_ALPHA[0], GRID_ALPHA[-1]),
    }


def grid_sst(grids: NDArray[np.floating]) -> NDArray[np.floating]:
    """Each configuration's grid SST about its own mean, ``(n_c, T)``."""
    grids = np.asarray(grids, dtype=float)
    return ((grids - grids.mean(axis=1, keepdims=True)) ** 2).sum(axis=1)


def fold_error_matrix(
    sse: NDArray[np.floating], sst: NDArray[np.floating]
) -> NDArray[np.floating]:
    """Fold errors ``e_c(θ) = mean_t SSE_{c,t}(θ) / S̄ST_t``, ``S̄ST_t = mean_c SST_{c,t}``.

    Args:
        sse: ``(n_candidates, n_folds, T)`` grid SSE of each left-out configuration.
        sst: ``(n_folds, T)`` grid SST of each configuration about its own mean.

    Returns:
        ``(n_candidates, n_folds)``. Their mean over folds equals the mean over targets of
        ``Σ_c SSE / Σ_c SST``.

    Raises:
        ValueError: If any fold error is non-finite (e.g. a target constant within every
            configuration, so ``S̄ST_t = 0``).
    """
    sbar = np.asarray(sst, dtype=float).mean(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        errors = (np.asarray(sse, dtype=float) / sbar).mean(axis=2)
    if not np.all(np.isfinite(errors)):
        raise ValueError(
            "non-finite fold error: a target's reference variance is zero (0/0); "
            "selection does not skip such folds"
        )
    return errors


def apply_one_se_rule(
    candidates: Sequence[tuple[int, int, float]], errors: NDArray[np.floating]
) -> dict[str, Any]:
    """Select by the one-standard-error rule from a fold-error table.

    ``θ*`` minimises the score (ties broken simplest first); ``threshold = score(θ*) +
    se(θ*)``; the simplest candidate with ``score ≤ threshold`` is chosen.

    Args:
        candidates: ``(H, d, α)`` tuples.
        errors: ``(n_candidates, n_folds)`` fold errors.

    Returns:
        The selection record (chosen point, θ*, threshold, margin, fragility, edges, the
        runner-up gap and the largest fold shares).
    """
    cands = [(int(h), int(d), float(a)) for h, d, a in candidates]
    errors = np.asarray(errors, dtype=float)
    n_folds = errors.shape[1]
    scores = errors.mean(axis=1)
    se = errors.std(axis=1, ddof=1) / np.sqrt(n_folds)
    order = sorted(range(len(cands)), key=lambda i: (scores[i], _order_key(cands[i])))
    star = order[0]
    threshold = float(scores[star] + se[star])
    within = [i for i in range(len(cands)) if scores[i] <= threshold]
    chosen = min(within, key=lambda i: _order_key(cands[i]))
    if threshold == 0.0:
        margin = 0.0
    else:
        margin = float(np.min(np.abs(scores - threshold)) / threshold)
    runner_up = order[1] if len(order) > 1 else star
    best = float(scores[star])
    gap = float((scores[runner_up] - best) / best) if best > 0 else 0.0

    def share(i: int) -> float:
        total = float(errors[i].sum())
        return float(errors[i].max() / total) if total > 0 else 0.0

    return {
        "chosen": cands[chosen],
        "chosen_score": float(scores[chosen]),
        "theta_star": cands[star],
        "star_score": best,
        "star_se": float(se[star]),
        "star_at_grid_edge": _grid_edge(cands[star]),
        "runner_up_gap": gap,
        "fold_share_star": share(star),
        "fold_share_chosen": share(chosen),
        "threshold": threshold,
        "selection_margin": margin,
        "selection_fragile": bool(margin <= FRAGILE_MARGIN),
        "at_grid_edge": _grid_edge(cands[chosen]),
    }


def select_ridge(
    frame: pd.DataFrame,
    target_names: Sequence[str],
    train_configs: Sequence[str],
) -> RidgeModel:
    """Choose ``(H, d, α)`` by leave-one-configuration-out CV inside the training configurations.

    Only rows of ``train_configs`` are read, so the test configurations never influence the
    selection. Each fold re-standardises over, and recomputes ``L_v`` from, its own training
    configurations. One multi-right-hand-side solve per fold, ``d`` and ``α`` serves every
    ``H`` and target, because the coefficients of a smaller ``H`` are a prefix.

    Args:
        frame: Target-beat rows (other configurations are ignored).
        target_names: Target columns.
        train_configs: The split's training configurations.

    Returns:
        The ridge fitted at the chosen point, with ``selection`` holding the record of
        :func:`apply_one_se_rule` plus ``ranks`` per ``d``.

    Raises:
        ValueError: On too few training configurations, a malformed beat, or a non-finite
            fold error.
    """
    wanted = {str(c) for c in train_configs}
    train = frame[frame["config_name"].astype(str).isin(wanted)]
    names, settings, grids = config_grids(train, target_names)
    n = len(names)
    if n < MIN_TRAIN_CONFIGS + 1:
        raise ValueError(
            f"selection needs at least {MIN_TRAIN_CONFIGS + 1} training configurations "
            f"(each fold at least {MIN_TRAIN_CONFIGS}), got {n}"
        )
    h_max = GRID_H[-1]
    coeffs = np.array([fourier_coefficients(g, h_max) for g in grids])
    sst = grid_sst(grids)
    bases = {h: fourier_basis(PHASE_GRID, h) for h in GRID_H}
    candidates = list(itertools.product(GRID_H, GRID_D, GRID_ALPHA))
    index = {c: i for i, c in enumerate(candidates)}
    n_targets = grids.shape[2]
    sse = np.zeros((len(candidates), n, n_targets))
    fold_ranks: dict[int, list[int]] = {d: [] for d in GRID_D}
    for c in range(n):
        keep = np.arange(n) != c
        a = coeffs[keep].reshape(n - 1, -1)
        for d in GRID_D:
            mean, std, levels = _standardise(settings[keep])
            exponents = monomial_exponents(levels, d)
            m = polynomial_matrix((settings[keep] - mean) / std, exponents)
            fold_ranks[d].append(int(np.linalg.matrix_rank(m)))
            row = polynomial_matrix(((settings[c] - mean) / std)[None, :], exponents)
            for alpha in GRID_ALPHA:
                beta = solve_ridge(m, a, alpha * (n - 1))
                pred = (row @ beta).reshape(2 * h_max + 1, n_targets)
                for h in GRID_H:
                    fitted = bases[h] @ pred[: 2 * h + 1]
                    sse[index[(h, d, alpha)], c] = ((grids[c] - fitted) ** 2).sum(
                        axis=0
                    )
    selection = apply_one_se_rule(candidates, fold_error_matrix(sse, sst))
    ranks = {}
    for d in GRID_D:
        mean, std, levels = _standardise(settings)
        m = polynomial_matrix((settings - mean) / std, monomial_exponents(levels, d))
        record = rank_record(m)
        record["min_fold_rank"] = int(min(fold_ranks[d]))
        record["n_deficient_folds"] = int(sum(r < record["P"] for r in fold_ranks[d]))
        ranks[d] = record
    selection["ranks"] = ranks
    h, d, alpha = selection["chosen"]
    model = fit_ridge(train, target_names, n_harmonics=h, degree=d, alpha=alpha)
    model.selection = selection
    return model


_DISCRETE_RANK_KEYS = ("P", "rank", "min_fold_rank", "n_deficient_folds")


def _as_point(value: Sequence[Any]) -> tuple[int, int, float]:
    h, d, alpha = value
    return (int(h), int(d), float(alpha))


def recheck_split(
    frame: pd.DataFrame,
    target_names: Sequence[str],
    train_configs: Sequence[str],
    committed: dict[str, Any],
    *,
    name: str,
) -> RidgeModel:
    """Recompute a committed ridge selection.

    A non-fragile split is re-selected and every discrete output must match exactly. A
    fragile one is refitted at its committed point, with a
    :class:`SelectionNotRecheckedWarning`, because a different BLAS could flip a near-tie.

    Args:
        frame: Target-beat rows.
        target_names: Target columns.
        train_configs: The split's training configurations.
        committed: The committed selection record (JSON-loaded or in memory).
        name: The split's name, for messages.

    Returns:
        The recomputed model.

    Raises:
        ValueError: If a discrete output of a non-fragile split differs.
    """
    if committed["selection_fragile"]:
        warnings.warn(
            f"split {name}: selection is fragile; refitted at the committed point, "
            "selection not re-checked",
            SelectionNotRecheckedWarning,
            stacklevel=2,
        )
        h, d, alpha = _as_point(committed["chosen"])
        wanted = {str(c) for c in train_configs}
        train = frame[frame["config_name"].astype(str).isin(wanted)]
        return fit_ridge(train, target_names, n_harmonics=h, degree=d, alpha=alpha)
    model = select_ridge(frame, target_names, train_configs)
    got = model.selection
    for key in ("chosen", "theta_star"):
        if _as_point(committed[key]) != got[key]:
            raise ValueError(f"split {name}: {key} {committed[key]} != {got[key]}")
    for key in ("at_grid_edge", "star_at_grid_edge", "selection_fragile"):
        if committed[key] != got[key]:
            raise ValueError(f"split {name}: {key} {committed[key]} != {got[key]}")
    for d, record in got["ranks"].items():
        old = committed["ranks"].get(d, committed["ranks"].get(str(d)))
        for key in _DISCRETE_RANK_KEYS:
            if old[key] != record[key]:
                raise ValueError(
                    f"split {name}: ranks[{d}].{key} {old[key]} != {record[key]}"
                )
    return model
