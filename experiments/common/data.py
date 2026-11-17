"""Dataset loading and phase resampling shared by the experiments."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
TARGETS = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")
CORPUS_DIR = {"coarse": REPO / "examples" / "prelim_sweep", "fine": REPO / "examples" / "prelim_sweep_fine"}


def dataset_path(grid: Literal["coarse", "fine"]) -> Path:
    return CORPUS_DIR[grid] / "dataset.parquet"


def load_dataset(grid: Literal["coarse", "fine"]) -> pd.DataFrame:
    """The committed force dataset for one grid (all beats, all configs)."""
    return pd.read_parquet(dataset_path(grid))


@lru_cache(maxsize=1)
def holdout_configs() -> tuple[str, ...]:
    """The six held-out configs, from the fine manifest (coarse must agree)."""
    out = []
    for grid in ("fine", "coarse"):
        manifest = json.loads((CORPUS_DIR[grid] / "sweep_manifest.json").read_text())
        out.append(tuple(sorted(manifest["holdout"]["config_names"])))
    if out[0] != out[1]:
        raise ValueError(f"coarse and fine manifests disagree on holdout: {out}")
    return out[0]


def phase_grid(n_phase: int = 256) -> np.ndarray:
    return np.arange(n_phase) / n_phase


def waveforms(
    df: pd.DataFrame, *, wingbeat: int = 1, n_phase: int = 256, columns: tuple[str, ...] = TARGETS
) -> dict[str, np.ndarray]:
    """Each config's one-beat waveform on a common phase grid.

    Periodic linear interpolation onto ``arange(n_phase) / n_phase``, so configs with different
    rows per beat (and the two grids) can be compared point by point.
    """
    grid = phase_grid(n_phase)
    out: dict[str, np.ndarray] = {}
    beat = df[df["wingbeat"] == wingbeat]
    for name, rows in beat.groupby("config_name", sort=True):
        rows = rows.sort_values("phase")
        phase = rows["phase"].to_numpy(dtype=float)
        if np.any(np.diff(phase) == 0.0):
            raise ValueError(f"config {name!r} wingbeat {wingbeat} has a duplicate phase")
        vals = rows[list(columns)].to_numpy(dtype=float)
        out[str(name)] = np.column_stack(
            [np.interp(grid, phase, vals[:, j], period=1.0) for j in range(vals.shape[1])]
        )
    return out
