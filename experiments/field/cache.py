"""Local cache of near-wing velocity patches and a downsampled whole-domain field.

One ``<root>/<config>/<step:05d>.npz`` per snapshot, written under a temporary name and renamed, so
an interrupted run never leaves a file that ``index`` or ``load`` would pick up.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import REPO
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix

CACHE_ROOT = REPO / "experiments" / "_cache"
PATCH_LO = (1.0, 0.0, 2.5)
PATCH_HI = (7.0, 4.0, 5.5)
DOWNSAMPLE = 4
_NPZ = re.compile(r"(\d{5})\.npz")


def axis_slice(centers: np.ndarray, lo: float, hi: float) -> slice:
    """Index range of the cell centres lying in ``[lo, hi)``."""
    idx = np.flatnonzero((centers >= lo) & (centers < hi))
    return slice(int(idx[0]), int(idx[-1]) + 1)


def block_mean(a: np.ndarray, k: int) -> np.ndarray:
    """Average ``a`` over non-overlapping ``k**3`` blocks (shape must divide by ``k``)."""
    nx, ny, nz = a.shape
    return a.reshape(nx // k, k, ny // k, k, nz // k, k).mean(axis=(1, 3, 5))


def phase_and_beat(time: float, frequency: float) -> tuple[float, int]:
    """Phase in [0, 1) and whole-beat index of a simulation time (rounded at 1e-9 cycles)."""
    cycles = round(time * frequency, 9)
    beat = int(np.floor(cycles))
    return round(cycles - beat, 9), beat


def build_arrays(snap, frequency: float, *, lo=PATCH_LO, hi=PATCH_HI) -> dict[str, np.ndarray]:
    """Cache payload from a full-domain ``FieldSnapshot`` (fields u, v, w, gradpx, gradpy, gradpz)."""
    sx, sy, sz = (axis_slice(c, a, b) for c, a, b in zip((snap.x, snap.y, snap.z), lo, hi))
    a = snap.arrays
    phase, beat = phase_and_beat(float(snap.time), frequency)
    return {
        "patch_u": np.stack([a[f][sx, sy, sz] for f in ("u", "v", "w")], axis=-1).astype(np.float32),
        "full4_u": np.stack([block_mean(a[f], DOWNSAMPLE) for f in ("u", "v", "w")], axis=-1).astype(np.float32),
        "full4_gradp": np.stack(
            [block_mean(a[f], DOWNSAMPLE) for f in ("gradpx", "gradpy", "gradpz")], axis=-1
        ).astype(np.float32),
        "patch_x": snap.x[sx], "patch_y": snap.y[sy], "patch_z": snap.z[sz],
        "time": np.float64(snap.time), "phase": np.float64(phase), "wingbeat": np.int64(beat),
    }


def _path(root: Path, config: str, step: int) -> Path:
    return Path(root) / config / f"{step:05d}.npz"


def is_cached(root: Path, config: str, step: int) -> bool:
    return _path(root, config, step).is_file()


def write_atomic(root: Path, config: str, step: int, arrays: dict) -> Path:
    final = _path(root, config, step)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(f"{step:05d}.tmp.npz")
    np.savez(tmp, **arrays)
    os.replace(tmp, final)
    return final


def load(root: Path, config: str, step: int, keys: tuple[str, ...] | None = None) -> dict[str, np.ndarray]:
    with np.load(_path(root, config, step)) as z:
        return {k: z[k] for k in (keys or z.files)}


def index(root: Path) -> pd.DataFrame:
    """One row per cached snapshot: config, step, time, phase, wingbeat, path."""
    rows = []
    for cfg_dir in sorted(p for p in Path(root).iterdir() if p.is_dir()):
        for f in sorted(cfg_dir.iterdir()):
            m = _NPZ.fullmatch(f.name)
            if not m:
                continue
            with np.load(f) as z:
                meta = {k: z[k] for k in ("time", "phase", "wingbeat") if k in z.files}
            rows.append({"config": cfg_dir.name, "step": int(m.group(1)), "time": float(meta.get("time", np.nan)),
                         "phase": float(meta.get("phase", np.nan)), "wingbeat": int(meta.get("wingbeat", -1)), "path": str(f)})
    return pd.DataFrame(rows, columns=["config", "step", "time", "phase", "wingbeat", "path"])


def wing_markers(
    time: float, *, body: np.ndarray, center, hinge, frequency: float, stroke_amp_deg: float, pitch_amp_deg: float
) -> np.ndarray:
    """Lab-frame marker positions: ``x = h + R(t) (X_file + center - h)`` with the repo's kinematics."""
    phi, alpha, theta = euler_angles(
        time, frequency=frequency, stroke_amp_rad=np.deg2rad(stroke_amp_deg), pitch_amp_rad=np.deg2rad(pitch_amp_deg)
    )
    h = np.asarray(hinge, dtype=float)
    return h + (np.asarray(body, dtype=float) + np.asarray(center, dtype=float) - h) @ rotation_matrix(phi, alpha, theta).T


def read_vertex_file(path: Path) -> np.ndarray:
    return np.loadtxt(path, skiprows=1)
