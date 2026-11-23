"""Synthetic coarse/fine corpus pairs for the comparison-figure tests (add-real-comparison-figures).

``write_repo(root, coarse=..., fine=...)`` writes ``root/examples/prelim_sweep{,_fine}/`` with the
four files each figure builder reads (``dataset.parquet``, ``surrogate/holdout_predictions.parquet``,
``surrogate/metrics.json``, ``surrogate/run_metadata.json``) plus the fine corpus-level
``run_metadata.json``. ``metrics.json`` is assembled exactly as ``train.run_training`` assembles it
(converged-beat filter -> ``build_phase_only_baseline`` -> ``build_seed_run`` per seed ->
``build_metrics(..., phase_baseline=)`` -> ``summarize_seed_sweep``), so a builder test exercises
the real schema rather than a hand-written imitation.

Three edit hooks reach the defects the builders must refuse without breaking the guards that run
before them:

- ``edit_dataset(df)`` edits the dataset frame **before** it is hashed and before anything is built
  from it, so the dataset-hash guard still passes;
- ``edit_runs(runs)`` edits the per-seed run dicts **before** ``summarize_seed_sweep``, so ``range``
  stays consistent with the runs;
- ``edit_metrics(metrics)`` edits the assembled ``metrics.json`` payload.

Every configuration has an **even** number of rows per beat, so a ±a alternation within a
configuration averages to exactly zero.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.train import (
    CONVERGED_MIN_WINGBEAT,
    TARGET_COLUMNS,
    build_metrics,
    build_phase_only_baseline,
    build_predictions_frame,
    build_seed_run,
    summarize_seed_sweep,
    write_json,
)

COARSE_DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "c" * 64
FINE_DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "f" * 64
COARSE_DIR = "examples/prelim_sweep"
FINE_DIR = "examples/prelim_sweep_fine"

_REPO = Path(__file__).resolve().parents[1]
_COMMITTED_METRICS = _REPO / COARSE_DIR / "surrogate" / "metrics.json"

# truth(split, index, phase, beat) -> (n, 6); error(seed_index, holdout_index, phase) -> (n, 6)
TruthFn = Callable[[str, int, np.ndarray, int], np.ndarray]
ErrorFn = Callable[[int, int, np.ndarray], np.ndarray]


def _alternation(n: int) -> np.ndarray:
    """``+1, -1, +1, ...`` over ``n`` rows (``n`` even, so the mean is exactly 0)."""
    return np.where(np.arange(n) % 2 == 0, 1.0, -1.0)


def default_truth(salt: float) -> TruthFn:
    """A smooth per-target waveform whose amplitude and mean depend on the configuration."""

    def truth(split: str, index: int, phase: np.ndarray, beat: int) -> np.ndarray:
        c = index + (100 if split == "holdout" else 0)
        amp = 1.0 + 0.07 * (c % 9) + salt
        mean = 0.02 * ((c * 7) % 5) + salt
        cols = [
            amp * (1.0 + 0.1 * j) * np.sin(2 * np.pi * phase + 0.5 * j) + mean * (j + 1)
            for j in range(len(TARGET_COLUMNS))
        ]
        return np.column_stack(cols) + 0.01 * beat

    return truth


def default_error(scales: tuple[float, ...]) -> ErrorFn:
    """Per-seed error: a ±1 per-configuration offset plus a within-configuration alternation."""

    def error(seed_index: int, holdout_index: int, phase: np.ndarray) -> np.ndarray:
        s = scales[seed_index]
        offset = 1.0 if holdout_index % 2 == 0 else -1.0
        alt = _alternation(phase.shape[0])
        cols = [
            s * (0.004 * (j + 1) * offset + 0.03 * alt)
            for j in range(len(TARGET_COLUMNS))
        ]
        return np.column_stack(cols)

    return error


@dataclass
class CorpusSpec:
    """One synthetic corpus. Defaults give a valid corpus every builder accepts."""

    n_beats: int = 2
    n_train: int = 6
    n_holdout: int = 6
    rows_per_beat: int = 8
    seeds: tuple[int, ...] = (1234, 1235, 1236, 1237, 1238)
    error_scales: tuple[float, ...] = (1.0, 1.4, 0.7, 1.2, 0.9)
    salt: float = 0.0
    truth: TruthFn | None = None
    error: ErrorFn | None = None
    digest: str = COARSE_DIGEST
    edit_dataset: Callable[[pd.DataFrame], pd.DataFrame] | None = None
    edit_runs: Callable[[list[dict[str, Any]]], None] | None = None
    edit_metrics: Callable[[dict[str, Any]], None] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def _train_names(spec: CorpusSpec) -> list[str]:
    return [f"t{i:02d}" for i in range(spec.n_train)]


def _holdout_names(spec: CorpusSpec) -> list[str]:
    return [f"h{i:02d}" for i in range(spec.n_holdout)]


def build_dataset(spec: CorpusSpec) -> pd.DataFrame:
    """The dataset frame: every configuration has wingbeats ``0..n_beats-1``."""
    if spec.rows_per_beat % 2:
        raise ValueError("rows_per_beat must be even")
    truth = spec.truth or default_truth(spec.salt)
    phase = np.arange(spec.rows_per_beat) / spec.rows_per_beat
    frames = []
    for split, names in (
        ("train", _train_names(spec)),
        ("holdout", _holdout_names(spec)),
    ):
        for index, name in enumerate(names):
            for beat in range(spec.n_beats):
                values = truth(split, index, phase, beat)
                frame = pd.DataFrame(values, columns=list(TARGET_COLUMNS))
                frame.insert(0, "config_name", name)
                frame.insert(1, "split", split)
                frame.insert(2, "time", beat + phase)
                frame.insert(3, "phase", phase)
                frame.insert(4, "wingbeat", beat)
                frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _val_configs(spec: CorpusSpec, seed_index: int) -> list[str]:
    names = _train_names(spec)
    return [names[(seed_index + k) % len(names)] for k in range(3)]


def build_metrics_payload(
    spec: CorpusSpec, df: pd.DataFrame
) -> tuple[dict[str, Any], pd.DataFrame]:
    """``(metrics, predictions)`` assembled as ``run_training`` assembles them."""
    error = spec.error or default_error(spec.error_scales)
    filtered = df[df["wingbeat"] >= CONVERGED_MIN_WINGBEAT].reset_index(drop=True)
    test_configs = sorted(
        filtered.loc[filtered["split"] == "holdout", "config_name"].unique()
    )
    holdout_df = filtered[filtered["config_name"].isin(test_configs)].reset_index(
        drop=True
    )
    y_true = holdout_df[list(TARGET_COLUMNS)].to_numpy(dtype=float)
    baseline = build_phase_only_baseline(
        filtered, holdout_df["phase"].to_numpy(dtype=float), list(TARGET_COLUMNS)
    )
    holdout_index = {name: i for i, name in enumerate(_holdout_names(spec))}
    preds = []
    for seed_index in range(len(spec.seeds)):
        y_pred = y_true.copy()
        for name, rows in holdout_df.groupby("config_name", sort=False).groups.items():
            idx = np.asarray(rows)
            phase = holdout_df.loc[idx, "phase"].to_numpy(dtype=float)
            y_pred[idx] += error(seed_index, holdout_index.get(name, 0), phase)
        preds.append(y_pred)
    runs = [
        build_seed_run(
            seed, _val_configs(spec, i), y_true, preds[i], holdout_df, baseline[0]
        )
        for i, seed in enumerate(spec.seeds)
    ]
    if spec.edit_runs is not None:
        spec.edit_runs(runs)
    committed = json.loads(_COMMITTED_METRICS.read_text(encoding="utf-8"))
    metrics = build_metrics(
        y_true,
        preds[0],
        holdout_df,
        inference=copy.deepcopy(committed["inference"]),
        reproducibility=copy.deepcopy(committed["reproducibility"]),
        phase_baseline=baseline,
    )
    metrics["seed_sweep"] = summarize_seed_sweep(runs, spec.seeds[0])
    if spec.edit_metrics is not None:
        spec.edit_metrics(metrics)
    return metrics, build_predictions_frame(holdout_df, y_true, preds[0])


def write_corpus(root: Path, corpus_dir: str, spec: CorpusSpec) -> dict[str, Any]:
    """Write one corpus under ``root/corpus_dir``; return the in-memory pieces."""
    base = Path(root) / corpus_dir
    (base / "surrogate").mkdir(parents=True, exist_ok=True)
    df = build_dataset(spec)
    if spec.edit_dataset is not None:
        df = spec.edit_dataset(df)
    dataset_path = base / "dataset.parquet"
    df.to_parquet(dataset_path)
    sha = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
    stored = pd.read_parquet(dataset_path)
    metrics, predictions = build_metrics_payload(spec, stored)
    predictions.to_parquet(base / "surrogate" / "holdout_predictions.parquet")
    write_json(base / "surrogate" / "metrics.json", metrics)
    write_json(
        base / "surrogate" / "run_metadata.json",
        {
            "docker_image": spec.digest,
            "inputs": {"file": f"{corpus_dir}/dataset.parquet", "hash": sha},
            **spec.extra,
        },
    )
    return {
        "dataset": stored,
        "metrics": metrics,
        "predictions": predictions,
        "sha": sha,
    }


def write_repo(
    root: Path, coarse: CorpusSpec | None = None, fine: CorpusSpec | None = None
) -> dict[str, dict[str, Any]]:
    """Write a coarse/fine corpus pair (byte-distinct by default) and the fine corpus record."""
    coarse = coarse or CorpusSpec()
    fine = fine or CorpusSpec(salt=0.013, digest=FINE_DIGEST)
    out = {
        "coarse": write_corpus(root, COARSE_DIR, coarse),
        "fine": write_corpus(root, FINE_DIR, fine),
    }
    write_json(
        Path(root) / FINE_DIR / "run_metadata.json", {"docker_image": fine.digest}
    )
    return out
