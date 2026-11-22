"""Bench metrics (spec requirement "Bench model entries and metrics", design D4).

All errors are fractions (0.05 means 5 %). Per (entry, split, seed, target, test configuration)
the bench stores the sums every pooled value is recomputed from. Skill is the #127 definition
(:func:`~mosquito_cfd.force_surrogate.train.compute_baseline_skill`) against a phase-only baseline
built from the split's own training configurations; skill is never compared across splits.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from mosquito_cfd.force_surrogate.train import (
    build_phase_only_baseline,
    compute_baseline_skill,
)
from mosquito_cfd.surrogate_bench.ridge import N_GRID, PHASE_GRID, config_grids
from mosquito_cfd.surrogate_bench.splits import SETTINGS, BenchSplit

MIN_SEEDS = 5
LEARNED_ENTRY_PREFIX = "mlp_"
# Excluded from every equality test: wall-clock and memory depend on the host and its load.
TIMING_COLUMNS = ("fit_seconds", "inference_seconds_per_row", "peak_gpu_mem")
SPAN_LOW, SPAN_HIGH = 0.01, 0.99
NO_HOLDOUT_REASON = "no labelled holdouts on this face"
_GROUP = ["entry", "split", "seed", "target"]


# --- Target beat -----------------------------------------------------------------------------


def target_beat(df: pd.DataFrame) -> int:
    """The largest ``wingbeat`` present for every configuration.

    Raises:
        ValueError: If the beats common to every configuration are not ``0..N−1``, or a
            configuration's target beat does not span the cycle (first phase ≥ 0.01 or last
            ≤ 0.99).
    """
    per_config = df.groupby("config_name")["wingbeat"].apply(lambda b: set(b.unique()))
    common = set.intersection(*per_config.tolist())
    if common != set(range(len(common))) or not common:
        raise ValueError(
            f"the wingbeats common to every configuration must be 0..N-1, got {sorted(common)}"
        )
    beat = max(common)
    rows = df[df["wingbeat"] == beat]
    span = rows.groupby("config_name")["phase"].agg(["min", "max"])
    partial = sorted(
        span.index[(span["min"] >= SPAN_LOW) | (span["max"] <= SPAN_HIGH)].astype(str)
    )
    if partial:
        raise ValueError(
            f"wingbeat {beat} does not span the cycle for configuration(s) {partial}"
        )
    return int(beat)


def target_beat_frame(df: pd.DataFrame) -> pd.DataFrame:
    """The rows of :func:`target_beat`, in dataset order (index preserved)."""
    return df[df["wingbeat"] == target_beat(df)]


# --- Normalisers and the CFD on the grid ------------------------------------------------------


def grid_truth(
    target_frame: pd.DataFrame, targets: Sequence[str]
) -> dict[str, NDArray[np.floating]]:
    """Each configuration's CFD beat periodically interpolated onto the phase grid."""
    names, _, grids = config_grids(target_frame, targets)
    return dict(zip(names, grids, strict=True))


def component_peaks(
    target_frame: pd.DataFrame, targets: Sequence[str]
) -> dict[str, float]:
    """``peak_t``: each target's ``max|CFD|`` over every configuration's grid beat."""
    _, _, grids = config_grids(target_frame, targets)
    return {t: float(np.abs(grids[:, :, j]).max()) for j, t in enumerate(targets)}


@dataclass
class SplitBaseline:
    """The phase-only baseline of one split's training configurations."""

    target_frame: pd.DataFrame
    train_configs: list[str]
    targets: list[str]
    definition: dict[str, Any]

    def at(self, phases: NDArray[np.floating]) -> NDArray[np.floating]:
        """Baseline predictions at the given phases, ``(n, T)``."""
        pred, _ = build_phase_only_baseline(
            self.target_frame,
            np.asarray(phases, dtype=float),
            self.targets,
            reference_configs=self.train_configs,
        )
        return pred


def split_baseline(
    target_frame: pd.DataFrame, train_configs: Sequence[str], targets: Sequence[str]
) -> SplitBaseline:
    """The baseline built from exactly ``train_configs`` (``reference_split: "explicit"``)."""
    configs = [str(c) for c in train_configs]
    _, definition = build_phase_only_baseline(
        target_frame, PHASE_GRID[:1], list(targets), reference_configs=configs
    )
    return SplitBaseline(target_frame, configs, list(targets), definition)


def _grid_frame(target_frame: pd.DataFrame, configs: Sequence[str]) -> pd.DataFrame:
    """``N_GRID`` rows per configuration with its settings and ``phase = k/N_GRID``."""
    settings = target_frame.groupby("config_name")[list(SETTINGS)].first()
    parts = []
    for name in configs:
        part = pd.DataFrame({"config_name": name, "phase": PHASE_GRID})
        for s in SETTINGS:
            part[s] = float(settings.loc[name, s])
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


# --- Scoring one fitted model on one split ----------------------------------------------------


def score_split_seed(
    *,
    entry: str,
    split: str,
    seed: int,
    target_frame: pd.DataFrame,
    test_configs: Sequence[str],
    y_pred: NDArray[np.floating],
    predict_grid: Callable[[pd.DataFrame], NDArray[np.floating]],
    baseline: SplitBaseline,
    truth: Mapping[str, NDArray[np.floating]],
    peaks: Mapping[str, float],
    targets: Sequence[str],
    extra: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """One result row per (target, test configuration).

    Args:
        entry: Entry name.
        split: Split name.
        seed: Seed (0 for a single-fit entry).
        target_frame: Target-beat rows of every configuration, in dataset order.
        test_configs: The split's test configurations.
        y_pred: Predictions at the test rows, in dataset order, ``(n, T)``.
        predict_grid: Evaluates the model directly at the rows of a frame (the grid phases).
        baseline: The split's phase-only baseline.
        truth: :func:`grid_truth`.
        peaks: :func:`component_peaks`.
        targets: Target columns.
        extra: Columns copied into every row (timing, memory, parameter count).

    Returns:
        The result rows.
    """
    targets = list(targets)
    is_test = target_frame["config_name"].isin(list(test_configs)).to_numpy()
    test = target_frame[is_test]
    y_pred = np.asarray(y_pred, dtype=float)
    if y_pred.shape != (len(test), len(targets)):
        raise ValueError(
            f"y_pred has shape {y_pred.shape}, expected {(len(test), len(targets))}"
        )
    configs = sorted(str(c) for c in test["config_name"].unique())
    grid_pred = np.asarray(
        predict_grid(_grid_frame(target_frame, configs)), dtype=float
    )
    base_grid = baseline.at(PHASE_GRID)
    y_base = baseline.at(test["phase"].to_numpy(dtype=float))
    y_true = test[targets].to_numpy(dtype=float)
    names = test["config_name"].astype(str).to_numpy()
    rows = []
    for k, config in enumerate(configs):
        mine = names == config
        skills = compute_baseline_skill(
            y_true[mine], y_pred[mine], y_base[mine], targets
        )
        model_grid = grid_pred[k * N_GRID : (k + 1) * N_GRID]
        for j, t in enumerate(targets):
            cfd = truth[config][:, j]
            grid_sse = float(((cfd - model_grid[:, j]) ** 2).sum())
            baseline_grid_sse = float(((cfd - base_grid[:, j]) ** 2).sum())
            rms = np.sqrt(grid_sse / N_GRID)
            row = {
                "entry": entry,
                "split": split,
                "seed": int(seed),
                "target": t,
                "config_name": config,
                "n_rows": int(mine.sum()),
                "sse": float(((y_true[mine, j] - y_pred[mine, j]) ** 2).sum()),
                "sse_baseline": float(((y_true[mine, j] - y_base[mine, j]) ** 2).sum()),
                "skill": skills[t]["skill"],
                "n_grid": N_GRID,
                "grid_sse": grid_sse,
                "baseline_grid_sse": baseline_grid_sse,
                "peak_t": float(peaks[t]),
                "rmse_frac_config_peak": float(rms / np.abs(cfd).max()),
                "rmse_frac_component_peak": float(rms / peaks[t]),
                "baseline_rmse_frac_component_peak": float(
                    np.sqrt(baseline_grid_sse / N_GRID) / peaks[t]
                ),
            }
            row.update(extra or {})
            rows.append(row)
    return pd.DataFrame(rows)


def per_seed_skill(
    target_frame: pd.DataFrame,
    test_configs: Sequence[str],
    y_pred: NDArray[np.floating],
    baseline: SplitBaseline,
    targets: Sequence[str],
) -> dict[str, float]:
    """Skill over all of a seed's test rows in dataset order (the call ``run_training`` makes)."""
    test = target_frame[target_frame["config_name"].isin(list(test_configs))]
    y_base = baseline.at(test["phase"].to_numpy(dtype=float))
    out = compute_baseline_skill(
        test[list(targets)].to_numpy(dtype=float), y_pred, y_base, list(targets)
    )
    return {t: out[t]["skill"] for t in targets}


# --- Summaries --------------------------------------------------------------------------------


def _pool(group: pd.DataFrame) -> pd.Series:
    sse_b = group["sse_baseline"].sum()
    n_grid = group["n_grid"].sum()
    peak = group["peak_t"].iloc[0]
    return pd.Series(
        {
            "skill": 1.0 - group["sse"].sum() / sse_b if sse_b > 0 else np.nan,
            "rmse_frac_component_peak": np.sqrt(group["grid_sse"].sum() / n_grid)
            / peak,
            "baseline_rmse_frac_component_peak": np.sqrt(
                group["baseline_grid_sse"].sum() / n_grid
            )
            / peak,
        }
    )


def pooled(results: pd.DataFrame, by: Sequence[str] = _GROUP) -> pd.DataFrame:
    """Pooled-over-test-configurations values, recomputed from the stored sums."""
    return (
        results.groupby(list(by), sort=True)[
            ["sse", "sse_baseline", "n_grid", "grid_sse", "baseline_grid_sse", "peak_t"]
        ]
        .apply(_pool)
        .reset_index()
    )


_RANGE_COLUMNS = (
    "skill",
    "rmse_frac_component_peak",
    "baseline_rmse_frac_component_peak",
)


def seed_ranges(pooled_results: pd.DataFrame) -> pd.DataFrame:
    """NaN-aware min/max over seeds per (entry, split, target).

    Raises:
        ValueError: If a learned (``mlp_*``) entry has fewer than 5 seeds for any split.
    """
    rows = []
    for (entry, split, target), group in pooled_results.groupby(
        ["entry", "split", "target"], sort=True
    ):
        n_seeds = group["seed"].nunique()
        if str(entry).startswith(LEARNED_ENTRY_PREFIX) and n_seeds < MIN_SEEDS:
            raise ValueError(
                f"{entry} on {split} has {n_seeds} seed(s); learned entries need "
                f"{MIN_SEEDS} seeds"
            )
        row: dict[str, Any] = {
            "entry": entry,
            "split": split,
            "target": target,
            "n_seeds": int(n_seeds),
        }
        for col in _RANGE_COLUMNS:
            values = group[col].to_numpy(dtype=float)
            finite = values[np.isfinite(values)]
            row[f"{col}_min"] = float(finite.min()) if finite.size else np.nan
            row[f"{col}_max"] = float(finite.max()) if finite.size else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def comparable(results: pd.DataFrame) -> pd.DataFrame:
    """The results without the timing and memory columns (for equality checks)."""
    return results.drop(columns=[c for c in TIMING_COLUMNS if c in results.columns])


def holdout_overlap(
    splits: Mapping[str, BenchSplit], holdouts: Sequence[str]
) -> dict[str, int]:
    """Number of labelled holdout configurations in each split's test set."""
    held = set(holdouts)
    return {name: len(set(s.test) & held) for name, s in splits.items()}


def faces_without_holdouts(
    results: pd.DataFrame, splits: Mapping[str, BenchSplit], holdouts: Sequence[str]
) -> pd.DataFrame:
    """Pooled face metrics with the labelled holdouts left out of each face's test set."""
    faces = [n for n in splits if n.startswith("face:")]
    keep = results["split"].isin(faces) & ~results["config_name"].isin(list(holdouts))
    return pooled(results[keep])


def _range(values: Sequence[float]) -> dict[str, float]:
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    return {
        "min": float(finite.min()) if finite.size else np.nan,
        "max": float(finite.max()) if finite.size else np.nan,
    }


def like_for_like(
    results: pd.DataFrame, splits: Mapping[str, BenchSplit], holdouts: Sequence[str]
) -> dict[str, Any]:
    """Each face model beside the controls on the face's labelled-holdout configurations.

    RMS metrics only (skill is not compared across splits). A face with no labelled holdouts
    is ``null`` with a reason.
    """
    held = set(holdouts)
    controls = [n for n in splits if n.startswith("control:")]
    view: dict[str, Any] = {}
    for name, split in splits.items():
        if not name.startswith("face:"):
            continue
        configs = sorted(set(split.test) & held)
        if not configs:
            view[name] = {"value": None, "reason": NO_HOLDOUT_REASON}
            continue
        on = results["config_name"].isin(configs)
        per_entry: dict[str, Any] = {}
        for entry, rows in results[on].groupby("entry", sort=True):
            face = pooled(rows[rows["split"] == name])
            ctrl = pooled(rows[rows["split"].isin(controls)])
            per_entry[str(entry)] = {
                "configs": configs,
                "face": {
                    c: _range(face[c])
                    for c in (
                        "rmse_frac_component_peak",
                        "baseline_rmse_frac_component_peak",
                    )
                },
                "controls": {
                    c: _range(ctrl[c])
                    for c in (
                        "rmse_frac_component_peak",
                        "baseline_rmse_frac_component_peak",
                    )
                },
            }
        view[name] = per_entry
    return view
