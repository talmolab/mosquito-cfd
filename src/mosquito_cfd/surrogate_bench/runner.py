"""Run the comparison bench and write its artifacts.

Spec requirements "Bench model entries and metrics" and "Bench artifacts, provenance and claim
scope". Every refusal happens before anything is written, and every check that depends only on
the data (splits, target beat, yardsticks, wrap jumps) runs before the first fit, so a bad corpus
never costs a GPU run. ``mlp_h1`` on ``interpolation`` is fitted first in the process (design
D7).
"""

from __future__ import annotations

import importlib.metadata
import os
import re
import shutil
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.sidecar import validate_image_digest
from mosquito_cfd.force_surrogate.train import (
    DEFAULT_EPOCHS,
    DEFAULT_HIDDEN,
    DEFAULT_LR,
    DEFAULT_NUM_LAYERS,
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
# The shipped recipe, read from the trainer so mlp_h1 cannot drift from it (D7).
MLP_HYPERPARAMETERS = {
    "hidden": DEFAULT_HIDDEN,
    "num_layers": DEFAULT_NUM_LAYERS,
    "lr": DEFAULT_LR,
}
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


_DEVICE = re.compile(r"cpu|cuda(:\d+)?")


def _is_dirty(git_state: Mapping[str, Any]) -> bool:
    """Only an explicit ``dirty: False`` is clean; an unknown state counts as dirty."""
    return git_state.get("dirty") is not False


def _validate(
    *,
    out_dir: Path,
    entries: Sequence[str],
    epochs: int,
    docker_image_digest: str,
    timestamp: str,
    device: str,
    git_state: Mapping[str, Any],
    allow_dirty: bool,
) -> list[str]:
    if _is_dirty(git_state) and not allow_dirty:
        raise ValueError(
            "the working tree is dirty or its state is unknown; commit first or pass "
            "allow_dirty"
        )
    names = [str(e) for e in entries]
    if not names:
        raise ValueError(f"no entries given; known: {list(ENTRIES)}")
    unknown = sorted(set(names) - set(ENTRIES))
    if unknown:
        raise ValueError(f"unknown entries {unknown}; known: {list(ENTRIES)}")
    repeated = sorted({e for e in names if names.count(e) > 1})
    if repeated:
        raise ValueError(f"entries repeat {repeated}")
    if (
        isinstance(epochs, bool)
        or not isinstance(epochs, int | np.integer)
        or epochs < 1
    ):
        raise ValueError(f"epochs must be an integer of at least 1, got {epochs!r}")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError(f"timestamp must be a non-empty string, got {timestamp!r}")
    if not isinstance(device, str) or not _DEVICE.fullmatch(device):
        raise ValueError(f"device must be 'cpu', 'cuda' or 'cuda:<n>', got {device!r}")
    validate_image_digest(docker_image_digest)
    if out_dir.exists() and not out_dir.is_dir():
        raise ValueError(f"output path {out_dir} exists and is not a directory")
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

    def __init__(self, cuda: Any | None) -> None:
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

    # Warm-up: the first GEMMs on a stream allocate cuBLAS/cuBLASLt workspaces through the
    # caching allocator and keep them. Without this, only the first probed fit (mlp_h1 /
    # interpolation / the first seed) would count them in its peak; afterwards they sit in
    # every fit's baseline. A biased Linear's forward and backward take the same paths
    # (addmm through cuBLASLt) as the trainer's layers.
    layer = torch.nn.Linear(8, 8).to(device)
    layer(torch.ones((4, 8), device=device)).sum().backward()
    torch.cuda.synchronize()
    del layer
    return torch.cuda


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
    grid: pd.DataFrame,
) -> pd.DataFrame:
    return metrics.score_split_seed(
        entry=entry,
        split=split.name,
        seed=seed,
        target_frame=target_frame,
        test_configs=split.test,
        y_pred=y_pred,
        predict_grid=lambda _grid: grid_pred,
        grid=grid,
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
    baseline: metrics.SplitBaseline,
    grid: pd.DataFrame,
) -> tuple[list[pd.DataFrame], dict[int, dict[str, float]], dict[int, np.ndarray]]:
    """Fit an MLP entry over the bench seeds on one split and score each seed."""
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
                grid=grid,
            )
        )
        skills[seed] = metrics.per_seed_skill(
            target_frame, split.test, fit.y_pred, baseline, TARGETS
        )
        grids[seed] = grid_pred
    return rows, skills, grids


def run_ridge_entry(
    entry: str,
    split: BenchSplit,
    *,
    target_frame: pd.DataFrame,
    truth: Mapping[str, np.ndarray],
    peaks: Mapping[str, float],
    baseline: metrics.SplitBaseline,
    grid: pd.DataFrame,
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
        baseline=baseline,
        grid=grid,
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


def _write_atomically(out_dir: Path, write_all: Any) -> None:
    """All five artifacts or none: stage beside ``out_dir``, then move them in.

    A failure while writing (a full disk, a figure error) removes the staging directory and
    leaves ``out_dir`` as it was: absent, or empty. The emptiness check is repeated just before
    the move, since a full run takes hours.
    """
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.", dir=out_dir.parent))
    try:
        write_all(staging)
        if not out_dir.exists():
            staging.rename(out_dir)
            return
        if not out_dir.is_dir() or any(out_dir.iterdir()):
            raise ValueError(f"output directory {out_dir} is no longer empty")
        for item in staging.iterdir():
            os.replace(item, out_dir / item.name)
        staging.rmdir()
    finally:
        if staging.exists():
            shutil.rmtree(staging)


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
    epochs: int = DEFAULT_EPOCHS,
    allow_dirty: bool = False,
    memory_probe: Any | None = None,
    extra_inputs: Mapping[str, Any] | None = None,
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
        extra_inputs: Further input provenance recorded beside ``dataset_sha256`` (the
            driver adds the dataset files, the coarse corpus's sha256 and digest, and how the
            digest was checked). It may not override ``dataset_sha256``.

    Returns:
        The artifact paths and the summary.

    Raises:
        ValueError: On any refusal, before anything is written.
    """
    out_dir = Path(out_dir)
    extra_inputs = dict(extra_inputs or {})
    if "dataset_sha256" in extra_inputs:
        raise ValueError("extra_inputs may not override dataset_sha256")
    chosen = _validate(
        out_dir=out_dir,
        entries=entries,
        epochs=epochs,
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        device=device,
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
    test_configs = sorted(interp.test)
    settings_of = {
        c: _settings(target_frame, c)
        for c in sorted(target_frame["config_name"].astype(str).unique())
    }
    # Data-only: computed before the first fit so a bad corpus fails fast.
    yardsticks = {
        config: gate.config_yardsticks(
            beats=_beat_grids(frame, config, n_beats),
            coarse=None if coarse_by_config is None else coarse_by_config[config],
            coarse_reason=coarse_reason or "no coarse corpus supplied",
            settings=settings_of[config],
            peaks=peaks,
            targets=TARGETS,
        )
        for config in test_configs
    }
    wrap_jumps, distance = {}, {}
    for config, settings in settings_of.items():
        rows = target_frame[target_frame["config_name"] == config]
        wrap_jumps[config] = gate.config_wrap_jumps(rows, peaks=peaks, **settings)
        distance[config] = gate.normal_peak_wrap_distance(
            truth[config][:, :3], **settings
        )
    # The baseline and the grid frame depend only on the split: built once, shared by every
    # seed and entry.
    baselines = {
        name: metrics.split_baseline(target_frame, s.train, TARGETS)
        for name, s in splits.items()
    }
    grid_frames = {
        name: metrics.grid_frame(target_frame, sorted(s.test))
        for name, s in splits.items()
    }
    cuda = memory_probe if memory_probe is not None else _default_cuda(device)
    probe = _MemoryProbe(cuda)

    results: list[pd.DataFrame] = []
    per_seed_skill: dict[str, dict[str, Any]] = {}
    ridge_records: dict[str, dict[str, Any]] = {}
    gate_grids: dict[str, dict[int, np.ndarray]] = {}
    for entry in chosen:
        per_seed_skill[entry] = {}
        ridge_records[entry] = {}
        for split in splits.values():
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
                    baseline=baselines[split.name],
                    grid=grid_frames[split.name],
                )
                results.extend(rows)
                per_seed_skill[entry][split.name] = {
                    str(s): v for s, v in skills.items()
                }
            else:
                rows, record, grid_pred = run_ridge_entry(
                    entry,
                    split,
                    target_frame=target_frame,
                    truth=truth,
                    peaks=peaks,
                    baseline=baselines[split.name],
                    grid=grid_frames[split.name],
                )
                results.append(rows)
                ridge_records[entry][split.name] = record
                grids = {0: grid_pred}
            if split.name == interp.name:
                gate_grids[entry] = grids

    table = pd.concat(results, ignore_index=True)
    missing = [c for c in RESULT_COLUMNS if c not in table.columns]
    if missing:  # an internal invariant: every scorer writes every column
        raise RuntimeError(f"result columns missing from the scored rows: {missing}")
    table["peak_gpu_mem"] = pd.array(table["peak_gpu_mem"], dtype="Int64")
    pooled = metrics.pooled(table)

    gate_entries: dict[str, Any] = {}
    for k, config in enumerate(test_configs):
        settings = settings_of[config]
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
        "inputs": {"dataset_sha256": dataset_sha256, **extra_inputs},
        "git": {**git_state, "dirty": _is_dirty(git_state)},
        "hardware": dict(hardware),
        "seeds": list(BENCH_SEEDS),
        "device": device,
        "entries": chosen,
        "epochs": int(epochs),
        "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"),
        "library_versions": _library_versions(),
        "settings_columns": list(SETTINGS),
    }

    names = {
        "results": "results.parquet",
        "splits": "splits.json",
        "summary": "summary.json",
        "figure": "bench_summary.png",
        "metadata": "run_metadata.json",
    }

    def write_all(directory: Path) -> None:
        table.loc[:, list(RESULT_COLUMNS)].to_parquet(
            directory / names["results"], index=False
        )
        write_json(directory / names["splits"], splits_json)
        write_json(directory / names["summary"], summary)
        write_summary_figure(_figure_rows(pooled), directory / names["figure"])
        write_json(directory / names["metadata"], metadata)

    _write_atomically(out_dir, write_all)
    return {**{k: out_dir / v for k, v in names.items()}, "summary_data": summary}
