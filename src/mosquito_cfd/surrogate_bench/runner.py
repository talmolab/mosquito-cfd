"""Run the comparison bench and write its artifacts.

Spec requirements "Bench model entries and metrics" and "Bench artifacts, provenance and claim
scope". Every refusal (dirty tree, non-empty output directory, unknown or duplicated entry, ``epochs`` below
1, a mutable image reference, a coarse corpus missing a configuration) happens before anything is
written. ``mlp_h1`` on ``interpolation`` is fitted first in the process (design D7).
"""

from __future__ import annotations

import importlib.metadata
import os
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.sidecar import validate_image_digest
from mosquito_cfd.force_surrogate.train import (
    TARGET_COLUMNS,
    fit_seed,
    predict_frame,
    write_json,
)
from mosquito_cfd.surrogate_bench import BENCH_SCOPE, BENCH_SEEDS, gate, metrics
from mosquito_cfd.surrogate_bench.figure import write_summary_figure
from mosquito_cfd.surrogate_bench.ridge import (
    N_GRID,
    config_grids,
    fit_ridge_fixed,
    select_ridge,
)
from mosquito_cfd.surrogate_bench.splits import (
    SETTINGS,
    BenchSplit,
    build_splits,
    carve_split,
)

ENTRIES: tuple[str, ...] = ("mlp_h1", "mlp_h3", "ridge", "ridge_fixed")
MLP_HARMONICS = {"mlp_h1": 1, "mlp_h3": 3}
MLP_HYPERPARAMETERS = {"hidden": 64, "num_layers": 3, "lr": 1e-3}
TARGETS = list(TARGET_COLUMNS)
HOLDOUT_STATUS = {
    "mlp_h1": {
        "holdout_informed": "unverified",
        "holdout_reason": "the shipped recipe; the provenance of its hyperparameters is not "
        "recorded here",
    },
    "mlp_h3": {
        "holdout_informed": True,
        "holdout_reason": "its harmonic count was chosen after holdout scores had been seen",
    },
    "ridge_fixed": {
        "holdout_informed": True,
        "holdout_reason": "its point was chosen by CV on the 21 pool configurations, on a grid "
        "widened after holdout scores had been seen",
    },
    "ridge": {
        "holdout_informed": True,
        "holdout_reason": "weakly: its grid contains values added after holdout scores had "
        "been seen, and the one-standard-error rule was adopted after design review had seen "
        "holdout skills of ridge variants",
    },
}
RESULT_COLUMNS = (
    "entry",
    "split",
    "seed",
    "target",
    "config_name",
    "n_rows",
    "sse",
    "sse_baseline",
    "skill",
    "n_grid",
    "grid_sse",
    "baseline_grid_sse",
    "peak_t",
    "rmse_frac_config_peak",
    "rmse_frac_component_peak",
    "baseline_rmse_frac_component_peak",
    "fit_seconds",
    "inference_seconds_per_row",
    "n_params",
    "peak_gpu_mem",
)


def _validate(
    *,
    out_dir: Path,
    entries: Sequence[str],
    epochs: int,
    docker_image_digest: str,
    git_state: Mapping[str, Any],
    allow_dirty: bool,
) -> list[str]:
    if git_state.get("dirty") and not allow_dirty:
        raise ValueError("the working tree is dirty; commit first or pass allow_dirty")
    names = [str(e) for e in entries]
    unknown = sorted(set(names) - set(ENTRIES))
    if unknown:
        raise ValueError(f"unknown entries {unknown}; known: {list(ENTRIES)}")
    repeated = sorted({e for e in names if names.count(e) > 1})
    if repeated:
        raise ValueError(f"entries repeat {repeated}")
    if int(epochs) < 1:
        raise ValueError(f"epochs must be at least 1, got {epochs}")
    validate_image_digest(docker_image_digest)
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"output directory {out_dir} is not empty")
    # mlp_h1 first, so its interpolation fits run first in the process.
    return [e for e in ENTRIES if e in names]


def _library_versions() -> dict[str, str | None]:
    out: dict[str, str | None] = {"numpy": np.__version__}
    for dist, key in (("torch", "torch"), ("nvidia-physicsnemo", "physicsnemo")):
        try:
            out[key] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            out[key] = None
    return out


def _n_params(model: Any) -> int:
    return int(sum(np.prod(np.shape(p)) for p in model.parameters()))


class _MemoryProbe:
    """Peak GPU memory of one fit, relative to the allocation when the peak is reset."""

    def __init__(self, cuda: Any | None):
        self.cuda = cuda
        self.base = 0

    def start(self) -> None:
        if self.cuda is None:
            return
        self.cuda.synchronize()
        self.cuda.reset_peak_memory_stats()
        self.base = int(self.cuda.memory_allocated())

    def stop(self) -> int | None:
        if self.cuda is None:
            return None
        self.cuda.synchronize()
        return int(self.cuda.max_memory_allocated()) - self.base


def _default_cuda(device: str) -> Any | None:
    if not str(device).startswith("cuda"):
        return None
    import torch  # lazy: only a CUDA run measures memory

    return torch.cuda


def _ordered_splits(splits: Mapping[str, BenchSplit]) -> list[BenchSplit]:
    return [splits[n] for n in splits]


def _score(
    *,
    entry: str,
    split: BenchSplit,
    seed: int,
    target_frame: pd.DataFrame,
    y_pred: np.ndarray,
    grid_pred: np.ndarray,
    truth: Mapping[str, np.ndarray],
    peaks: Mapping[str, float],
    extra: Mapping[str, Any],
    baseline: metrics.SplitBaseline,
) -> pd.DataFrame:
    return metrics.score_split_seed(
        entry=entry,
        split=split.name,
        seed=seed,
        target_frame=target_frame,
        test_configs=split.test,
        y_pred=y_pred,
        predict_grid=lambda _grid: grid_pred,
        baseline=baseline,
        truth=truth,
        peaks=peaks,
        targets=TARGETS,
        extra=extra,
    )


def run_mlp_entry(
    entry: str,
    split: BenchSplit,
    *,
    target_frame: pd.DataFrame,
    truth: Mapping[str, np.ndarray],
    peaks: Mapping[str, float],
    epochs: int,
    device: str,
    probe: _MemoryProbe,
) -> tuple[list[pd.DataFrame], dict[int, dict[str, float]], dict[int, np.ndarray]]:
    """Fit an MLP entry over the bench seeds on one split and score each seed."""
    configs = sorted(split.test)
    grid = metrics.grid_frame(target_frame, configs)
    baseline = metrics.split_baseline(target_frame, split.train, TARGETS)
    rows, skills, grids = [], {}, {}
    for seed in BENCH_SEEDS:
        assignment = carve_split(split, seed=seed)
        probe.start()
        t0 = time.perf_counter()
        fit = fit_seed(
            target_frame,
            assignment,
            seed=seed,
            phase_harmonics=MLP_HARMONICS[entry],
            epochs=epochs,
            device=device,
            **MLP_HYPERPARAMETERS,
        )
        fit_seconds = time.perf_counter() - t0
        peak_mem = probe.stop()
        t1 = time.perf_counter()
        grid_pred = np.asarray(predict_frame(fit, grid, device=device), dtype=float)
        per_row = (time.perf_counter() - t1) / len(grid)
        extra = {
            "fit_seconds": fit_seconds,
            "inference_seconds_per_row": per_row,
            "n_params": _n_params(fit.model),
            "peak_gpu_mem": peak_mem,
        }
        rows.append(
            _score(
                entry=entry,
                split=split,
                seed=seed,
                target_frame=target_frame,
                y_pred=fit.y_pred,
                grid_pred=grid_pred,
                truth=truth,
                peaks=peaks,
                extra=extra,
                baseline=baseline,
            )
        )
        skills[seed] = metrics.per_seed_skill(
            target_frame, split.test, fit.y_pred, baseline, TARGETS
        )
        grids[seed] = grid_pred
    return rows, skills, grids


def run_ridge_entries(
    entry: str,
    split: BenchSplit,
    *,
    target_frame: pd.DataFrame,
    truth: Mapping[str, np.ndarray],
    peaks: Mapping[str, float],
) -> tuple[pd.DataFrame, dict[str, Any], np.ndarray]:
    """Fit ``ridge`` (selected) or ``ridge_fixed`` on one split and score it (pure numpy)."""
    train = target_frame[target_frame["config_name"].isin(split.train)]
    test = target_frame[target_frame["config_name"].isin(split.test)]
    t0 = time.perf_counter()
    if entry == "ridge":
        model = select_ridge(target_frame, TARGETS, split.train)
    else:
        model = fit_ridge_fixed(train, TARGETS)
    fit_seconds = time.perf_counter() - t0
    grid = metrics.grid_frame(target_frame, sorted(split.test))
    t1 = time.perf_counter()
    grid_pred = model.predict(grid)
    per_row = (time.perf_counter() - t1) / len(grid)
    extra = {
        "fit_seconds": fit_seconds,
        "inference_seconds_per_row": per_row,
        "n_params": model.n_params,
        "peak_gpu_mem": None,
    }
    rows = _score(
        entry=entry,
        split=split,
        seed=0,
        target_frame=target_frame,
        y_pred=model.predict(test),
        grid_pred=grid_pred,
        truth=truth,
        peaks=peaks,
        extra=extra,
        baseline=metrics.split_baseline(target_frame, split.train, TARGETS),
    )
    record = {
        "point": [model.n_harmonics, model.degree, model.alpha],
        "rank": model.rank,
        "n_params": model.n_params,
        "selection": model.selection,
    }
    return rows, record, grid_pred


def _settings(target_frame: pd.DataFrame, config: str) -> dict[str, float]:
    row = target_frame[target_frame["config_name"] == config].iloc[0]
    return {
        "stroke": float(row["stroke_amp_deg"]),
        "fstar": float(row["frequency_fstar"]),
        "pitch": float(row["pitch_amp_deg"]),
    }


def _beat_grids(
    frame: pd.DataFrame, config: str, n_beats: int
) -> dict[int, np.ndarray]:
    rows = frame[frame["config_name"] == config]
    out = {}
    for beat in range(n_beats):
        _, _, grids = config_grids(rows[rows["wingbeat"] == beat], TARGETS)
        out[beat] = grids[0]
    return out


def _coarse_grids(
    coarse: pd.DataFrame, configs: Sequence[str], beat: int
) -> tuple[dict[str, np.ndarray] | None, str]:
    missing = sorted(set(configs) - set(coarse["config_name"].astype(str).unique()))
    if missing:
        raise ValueError(f"the coarse corpus is missing configuration(s) {missing}")
    rows = coarse[coarse["wingbeat"] == beat]
    present = set(rows["config_name"].astype(str).unique())
    if not set(configs) <= present:
        return None, f"coarse corpus lacks target beat {beat}"
    names, _, grids = config_grids(rows[rows["config_name"].isin(configs)], TARGETS)
    return dict(zip(names, grids, strict=True)), ""


def _figure_rows(pooled: pd.DataFrame) -> pd.DataFrame:
    per_seed = pooled.groupby(["entry", "split", "seed"], sort=False)["skill"].mean()
    rows = []
    for (entry, split), values in per_seed.groupby(
        level=["entry", "split"], sort=False
    ):
        v = values.to_numpy(dtype=float)
        rows.append(
            {
                "entry": entry,
                "split": split,
                "skill_min": float(np.nanmin(v)),
                "skill_max": float(np.nanmax(v)),
                "skill_median": float(np.nanmedian(v)),
            }
        )
    return pd.DataFrame(rows)


def run_bench(
    *,
    frame: pd.DataFrame,
    coarse_frame: pd.DataFrame,
    out_dir: Path | str,
    docker_image_digest: str,
    timestamp: str,
    dataset_sha256: str,
    git_state: Mapping[str, Any],
    hardware: Mapping[str, Any],
    device: str = "cpu",
    entries: Sequence[str] = ENTRIES,
    epochs: int = 2000,
    allow_dirty: bool = False,
    memory_probe: Any | None = None,
) -> dict[str, Any]:
    """Run the bench on the fine corpus and write the five artifacts into ``out_dir``.

    Args:
        frame: The fine dataset, every beat.
        coarse_frame: The coarse dataset, every beat.
        out_dir: Output directory (absent or empty).
        docker_image_digest: The fine corpus's pinned image reference.
        timestamp: Caller-supplied ISO-8601 timestamp.
        dataset_sha256: sha256 of the fine ``dataset.parquet``.
        git_state: ``{commit, branch, dirty}``.
        hardware: The hardware block.
        device: ``"cpu"`` or ``"cuda"``.
        entries: Entries to run.
        epochs: MLP training epochs.
        allow_dirty: Run on a dirty tree, recording ``dirty: true``.
        memory_probe: An object with the ``torch.cuda`` memory API (default ``torch.cuda`` on a
            CUDA device, none on CPU).

    Returns:
        The artifact paths and the summary.

    Raises:
        ValueError: On any refusal, before anything is written.
    """
    out_dir = Path(out_dir)
    chosen = _validate(
        out_dir=out_dir,
        entries=entries,
        epochs=epochs,
        docker_image_digest=docker_image_digest,
        git_state=git_state,
        allow_dirty=allow_dirty,
    )
    beat = metrics.target_beat(frame)
    n_beats = beat + 1
    target_frame = metrics.target_beat_frame(frame)
    splits = build_splits(target_frame)
    interp = splits["interpolation"]
    coarse_by_config, coarse_reason = _coarse_grids(
        coarse_frame, sorted(target_frame["config_name"].astype(str).unique()), beat
    )
    truth = metrics.grid_truth(target_frame, TARGETS)
    peaks = metrics.component_peaks(target_frame, TARGETS)
    cuda = memory_probe if memory_probe is not None else _default_cuda(device)
    probe = _MemoryProbe(cuda)

    results: list[pd.DataFrame] = []
    per_seed_skill: dict[str, dict[str, Any]] = {}
    ridge_records: dict[str, dict[str, Any]] = {}
    gate_grids: dict[str, dict[int, np.ndarray]] = {}
    for entry in chosen:
        per_seed_skill[entry] = {}
        ridge_records[entry] = {}
        for split in _ordered_splits(splits):
            if entry in MLP_HARMONICS:
                rows, skills, grids = run_mlp_entry(
                    entry,
                    split,
                    target_frame=target_frame,
                    truth=truth,
                    peaks=peaks,
                    epochs=epochs,
                    device=device,
                    probe=probe,
                )
                results.extend(rows)
                per_seed_skill[entry][split.name] = {
                    str(s): v for s, v in skills.items()
                }
            else:
                rows, record, grid_pred = run_ridge_entries(
                    entry, split, target_frame=target_frame, truth=truth, peaks=peaks
                )
                results.append(rows)
                ridge_records[entry][split.name] = record
                grids = {0: grid_pred}
            if split.name == interp.name:
                gate_grids[entry] = grids

    table = pd.concat(results, ignore_index=True)
    for col in RESULT_COLUMNS:
        if col not in table.columns:
            table[col] = None
    table["peak_gpu_mem"] = pd.array(table["peak_gpu_mem"], dtype="Int64")
    pooled = metrics.pooled(table)

    test_configs = sorted(interp.test)
    gate_entries: dict[str, Any] = {}
    yardsticks: dict[str, Any] = {}
    for k, config in enumerate(test_configs):
        settings = _settings(target_frame, config)
        coarse = None if coarse_by_config is None else coarse_by_config[config]
        yardsticks[config] = gate.config_yardsticks(
            beats=_beat_grids(frame, config, n_beats),
            coarse=coarse,
            coarse_reason=coarse_reason or "no coarse corpus supplied",
            settings=settings,
            peaks=peaks,
            targets=TARGETS,
        )
        for entry, grids in gate_grids.items():
            per_config = gate_entries.setdefault(entry, {}).setdefault(config, {})
            for seed, grid_pred in grids.items():
                model = grid_pred[k * N_GRID : (k + 1) * N_GRID]
                per_config[seed] = gate.config_errors(
                    model=model,
                    cfd=truth[config],
                    settings=settings,
                    peaks=peaks,
                    targets=TARGETS,
                )
    all_configs = sorted(target_frame["config_name"].astype(str).unique())
    wrap_jumps, distance = {}, {}
    for config in all_configs:
        settings = _settings(target_frame, config)
        rows = target_frame[target_frame["config_name"] == config]
        wrap_jumps[config] = gate.config_wrap_jumps(rows, peaks=peaks, **settings)
        distance[config] = gate.normal_peak_wrap_distance(
            truth[config][:, :3], **settings
        )
    gate_block = gate.gate_block(
        entries=gate_entries,
        yardsticks=yardsticks,
        wrap_jumps=wrap_jumps,
        peak_wrap_distance=distance,
        test_configs=test_configs,
        holdout_status={e: HOLDOUT_STATUS[e] for e in gate_entries},
    )
    holdouts = list(interp.test)
    summary = {
        "scope": BENCH_SCOPE,
        "target_beat": beat,
        "n_beats": n_beats,
        "entries": chosen,
        "seeds": list(BENCH_SEEDS),
        "pooled": pooled.to_dict(orient="records"),
        "seed_ranges": metrics.seed_ranges(pooled).to_dict(orient="records"),
        "per_seed_skill": per_seed_skill,
        "ridge": {e: r for e, r in ridge_records.items() if r},
        "holdout_overlap": metrics.holdout_overlap(splits, holdouts),
        "faces_without_holdouts": metrics.faces_without_holdouts(
            table, splits, holdouts
        ).to_dict(orient="records"),
        "like_for_like": metrics.like_for_like(table, splits, holdouts),
        "holdout_status": {e: HOLDOUT_STATUS[e] for e in chosen},
        "wrap_jumps": wrap_jumps,
        "peak_wrap_distance": distance,
        "gate": gate_block,
    }
    splits_json = {
        name: {
            "train": list(s.train),
            "test": list(s.test),
            "validation": {
                str(seed): carve_split(s, seed=seed).val_configs for seed in BENCH_SEEDS
            },
        }
        for name, s in splits.items()
    }
    metadata = {
        "docker_image": docker_image_digest,
        "timestamp": timestamp,
        "inputs": {"dataset_sha256": dataset_sha256},
        "git": dict(git_state),
        "hardware": dict(hardware),
        "seeds": list(BENCH_SEEDS),
        "device": device,
        "entries": chosen,
        "epochs": int(epochs),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "library_versions": _library_versions(),
        "settings_columns": list(SETTINGS),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "results": out_dir / "results.parquet",
        "splits": out_dir / "splits.json",
        "summary": out_dir / "summary.json",
        "figure": out_dir / "bench_summary.png",
        "metadata": out_dir / "run_metadata.json",
    }
    table.loc[:, list(RESULT_COLUMNS)].to_parquet(paths["results"], index=False)
    write_json(paths["splits"], splits_json)
    write_json(paths["summary"], summary)
    write_summary_figure(_figure_rows(pooled), paths["figure"])
    write_json(paths["metadata"], metadata)
    return {**paths, "summary_data": summary}
