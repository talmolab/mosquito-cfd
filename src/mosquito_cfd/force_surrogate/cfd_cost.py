"""Per-wingbeat CFD cost from committed per-configuration run metadata.

The evidence figure's speedup denominator is a CFD wall-clock cost per wingbeat. For the fine
corpus it is the median, over the committed ``run_metadata_<config>.json`` files, of
``timing.wall_time_s / cycles_completed`` (change ``add-fine-corpus-surrogate``, design D3). The
median rather than the mean: per-wingbeat time varies ~2x across configs with the node the run
landed on, not with the kinematics, and a mean or maximum would inflate the speedup.

The figure generator does not read these files (its scope guard allows only the predictions and
``metrics.json``); the value is computed here and passed to it as a scalar.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Sequence
from pathlib import Path
from typing import Any


def _positive_number(value: Any, name: str, path: Path) -> float:
    """Return ``value`` as a float, or raise naming the field and file.

    ``bool`` is rejected explicitly: it is an ``int`` subclass, so ``True`` would otherwise read
    as 1.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path.name}: {name} must be a number, got {value!r}")
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{path.name}: {name} must be finite and > 0, got {value!r}")
    return float(value)


def median_cfd_seconds_per_wingbeat(paths: Sequence[Path]) -> dict[str, Any]:
    """Median CFD wall-clock seconds per wingbeat over per-configuration run metadata files.

    Args:
        paths: ``run_metadata_<config>.json`` files, each carrying ``config``, ``gpu_model``,
            ``cycles_completed`` and ``timing.wall_time_s``.

    Returns:
        ``{"seconds_per_wingbeat", "n_configs", "gpu_model", "min", "max"}``, where the
        seconds are ``statistics.median`` of ``wall_time_s / cycles_completed`` (for an even
        count, the mean of the middle two) and ``min``/``max`` bound the per-config values.

    Raises:
        ValueError: If no paths are given; a file lacks ``config`` or ``gpu_model``; a
            ``wall_time_s`` or ``cycles_completed`` is missing, not a number (including
            ``bool``), non-finite or not positive; a configuration repeats; or the files name
            more than one GPU model. Each message names the offending file.
    """
    if not paths:
        raise ValueError("no run metadata files given")
    per_wingbeat: list[float] = []
    configs: set[str] = set()
    gpus: set[str] = set()
    for path in paths:
        path = Path(path)
        record = json.loads(path.read_text(encoding="utf-8"))
        for key in ("config", "gpu_model"):
            if not isinstance(record.get(key), str):
                raise ValueError(f"{path.name}: missing {key}")
        config = record["config"]
        if config in configs:
            raise ValueError(f"{path.name}: duplicate config {config}")
        configs.add(config)
        gpus.add(record["gpu_model"])
        timing = record.get("timing")
        wall = timing.get("wall_time_s") if isinstance(timing, dict) else None
        wall_s = _positive_number(wall, "timing.wall_time_s", path)
        cycles = _positive_number(
            record.get("cycles_completed"), "cycles_completed", path
        )
        per_wingbeat.append(wall_s / cycles)
    if len(gpus) != 1:
        raise ValueError(f"run metadata spans more than one GPU model: {sorted(gpus)}")
    return {
        "seconds_per_wingbeat": statistics.median(per_wingbeat),
        "n_configs": len(per_wingbeat),
        "gpu_model": gpus.pop(),
        "min": min(per_wingbeat),
        "max": max(per_wingbeat),
    }
