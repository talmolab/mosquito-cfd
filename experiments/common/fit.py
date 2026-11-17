"""Thin wrapper over the repo's Track B trainer for arbitrary config splits and features.

Call order mirrors ``mosquito_cfd.force_surrogate.train._fit_one_seed``: standardizers are fit on
training rows only, validation rows drive best-checkpoint selection, test rows are only predicted.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.train import (
    TARGET_COLUMNS,
    Standardizer,
    build_features,
    build_model,
    build_phase_only_baseline,
    compute_baseline_skill,
    predict,
    train_model,
)

FeatureFn = Callable[[pd.DataFrame], tuple[np.ndarray, list[str]]]


@dataclass
class FitResult:
    preds: np.ndarray  # (n_test_rows, 6), physical units, in df row order of the test rows
    test_index: np.ndarray  # df index labels of those rows
    val_configs: list[str]
    seconds: float
    n_params: int
    final_train_loss: float


def fit_predict(
    df: pd.DataFrame,
    train_configs: Sequence[str],
    val_configs: Sequence[str],
    test_configs: Sequence[str],
    *,
    seed: int,
    feature_fn: FeatureFn | None = None,
    width: int = 64,
    depth: int = 3,
    epochs: int = 2000,
    lr: float = 1e-3,
    device: str = "cuda",
    row_stride: int = 1,
) -> FitResult:
    """Train one seeded MLP on ``train_configs`` and predict ``test_configs``.

    ``df`` must already be restricted to the beats to use. ``val_configs=[]`` trains for the fixed
    epoch count and keeps the final weights. ``row_stride`` thins the training rows only.
    """
    sets = [set(train_configs), set(val_configs), set(test_configs)]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
        raise ValueError("train, validation and test configs must be disjoint")
    cfg = df["config_name"].to_numpy()
    train_mask = np.isin(cfg, list(train_configs))
    if row_stride > 1:
        keep = np.zeros(len(df), dtype=bool)
        keep[np.flatnonzero(train_mask)[::row_stride]] = True
        train_mask = keep
    val_mask = np.isin(cfg, list(val_configs))
    test_mask = np.isin(cfg, list(test_configs))

    x_all, names = (feature_fn or build_features)(df)
    fstd = Standardizer().fit(x_all[train_mask])
    xz = fstd.transform(x_all)
    y_all = df[TARGET_COLUMNS].to_numpy(dtype=float)
    tstd = Standardizer().fit(y_all[train_mask])
    yz = tstd.transform(y_all)

    t0 = time.perf_counter()
    model = build_model(len(names), len(TARGET_COLUMNS), seed=seed, hidden=width, num_layers=depth)
    has_val = bool(val_mask.any())
    history = train_model(
        model,
        xz[train_mask],
        yz[train_mask],
        epochs=epochs,
        seed=seed,
        lr=lr,
        device=device,
        x_val=xz[val_mask] if has_val else None,
        y_val=yz[val_mask] if has_val else None,
    )
    preds = tstd.inverse_transform(predict(model, xz[test_mask], device=device))
    return FitResult(
        preds=preds,
        test_index=df.index.to_numpy()[test_mask],
        val_configs=sorted(val_configs),
        seconds=time.perf_counter() - t0,
        n_params=int(sum(p.numel() for p in model.parameters())),
        final_train_loss=float(history[-1]),
    )


def baseline_predictions(df: pd.DataFrame, baseline_configs: Sequence[str], query_phase: np.ndarray) -> np.ndarray:
    """Phase-only baseline (mean waveform of ``baseline_configs``) at ``query_phase``."""
    ref = df[df["config_name"].isin(list(baseline_configs))].copy()
    ref["split"] = "train"
    out, _ = build_phase_only_baseline(ref, query_phase)
    return out


def skill(
    df: pd.DataFrame, baseline_configs: Sequence[str], test_configs: Sequence[str], preds: np.ndarray
) -> dict[str, dict[str, float]]:
    """Per-target skill and RMSE on ``test_configs`` against a baseline built from ``baseline_configs`` only."""
    if set(baseline_configs) & set(test_configs):
        raise ValueError("baseline configs overlap the test configs")
    test = df[df["config_name"].isin(list(test_configs))]
    y = test[TARGET_COLUMNS].to_numpy(dtype=float)
    base = baseline_predictions(df, baseline_configs, test["phase"].to_numpy(dtype=float))
    out = compute_baseline_skill(y, preds, base, list(TARGET_COLUMNS))
    for j, name in enumerate(TARGET_COLUMNS):
        out[name]["rmse"] = float(np.sqrt(np.mean((y[:, j] - preds[:, j]) ** 2)))
    return out
