"""Per-step CFD cost from committed per-configuration run metadata.

The evidence figure's speedup denominator is the CFD's wall-clock cost per row, and each dataset
row is one CFD timestep. For the fine corpus that cost is the median, over the committed
``run_metadata_<config>.json`` files, of ``timing.wall_time_s / timing.timesteps`` (change
``add-fine-corpus-surrogate``, design D3). Per step rather than per wingbeat: a wingbeat takes
``1/(f*·dt)`` steps, so per-wingbeat time scales with the kinematics, while the per-step rate does
not (the fine pilot measured 2.00-2.02 s/step across its configs). The median rather than the
mean: per-step time still varies with the node the run landed on, and a mean or maximum would
inflate the speedup.

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


def median_cfd_seconds_per_step(paths: Sequence[Path]) -> dict[str, Any]:
    """Median CFD wall-clock seconds per timestep over per-configuration run metadata files.

    Args:
        paths: ``run_metadata_<config>.json`` files, each carrying ``config``, ``gpu_model``,
            ``timing.wall_time_s`` and ``timing.timesteps``.

    Returns:
        ``{"seconds_per_step", "n_configs", "gpu_model", "min", "max"}``, where the seconds
        are ``statistics.median`` of ``wall_time_s / timesteps`` (for an even count, the mean
        of the middle two) and ``min``/``max`` bound the per-config values.

    Raises:
        ValueError: If no paths are given; a file lacks ``config`` or ``gpu_model``; a
            ``wall_time_s`` is missing, not a number (including ``bool``), non-finite or not
            positive; ``timesteps`` is not a positive integer; a configuration repeats; or the
            files name more than one GPU model. Each message names the offending file.
    """
    if not paths:
        raise ValueError("no run metadata files given")
    per_step: list[float] = []
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
        timing = timing if isinstance(timing, dict) else {}
        wall_s = _positive_number(timing.get("wall_time_s"), "timing.wall_time_s", path)
        steps = timing.get("timesteps")
        if isinstance(steps, bool) or not isinstance(steps, int) or steps <= 0:
            raise ValueError(
                f"{path.name}: timing.timesteps must be a positive integer, got {steps!r}"
            )
        per_step.append(wall_s / steps)
    if len(gpus) != 1:
        raise ValueError(f"run metadata spans more than one GPU model: {sorted(gpus)}")
    return {
        "seconds_per_step": statistics.median(per_step),
        "n_configs": len(per_step),
        "gpu_model": gpus.pop(),
        "min": min(per_step),
        "max": max(per_step),
    }
