"""Config-level splits for experiments that the repo's fixed 3-config carve cannot express."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def carve_validation(
    configs: Sequence[str], *, seed: int, frac: float = 1 / 7, min_val: int = 1
) -> tuple[list[str], list[str]]:
    """Split ``configs`` into (train, validation); validation is ~``frac`` of them, at least ``min_val``."""
    pool = sorted(configs)
    n_val = max(min_val, round(len(pool) * frac))
    if not 1 <= n_val < len(pool):
        raise ValueError(f"cannot carve {n_val} validation configs from {len(pool)}")
    idx = np.random.default_rng(seed).choice(len(pool), size=n_val, replace=False)
    val = sorted(pool[i] for i in idx)
    return sorted(set(pool) - set(val)), val


def nested_subsets(pool: Sequence[str], sizes: Sequence[int], *, seed: int) -> dict[int, list[str]]:
    """Random subsets of ``pool``, one per size, each containing every smaller one."""
    order = np.random.default_rng(seed).permutation(sorted(pool))
    if max(sizes) > len(order):
        raise ValueError(f"largest size {max(sizes)} exceeds pool of {len(order)}")
    return {int(n): sorted(str(c) for c in order[:n]) for n in sizes}
