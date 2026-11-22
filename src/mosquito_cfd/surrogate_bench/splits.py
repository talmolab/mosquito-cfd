"""Named splits of the fine force corpus (spec requirement "Bench splits").

Every split is built from the dataset's configuration kinematics and ``split`` labels, never from a
hand-typed list:

- ``interpolation``: train the 21 ``split == "train"`` configurations (``pool``), test the 6
  labelled holdouts;
- ``face:<setting>=<value>``: test the 9 configurations on one face of the 3 × 3 × 3 grid, train
  the other 18;
- ``control:<k>``, ``k = 0..5``: 18 configurations of ``pool`` drawn with
  ``default_rng(k).choice``, tested on the holdouts;
- ``control:e4_seed0``: the exploration's E4 subset, ``default_rng(0).permutation(pool)[:18]``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.train import SplitAssignment, carve_validation

SETTINGS: tuple[str, ...] = ("stroke_amp_deg", "frequency_fstar", "pitch_amp_deg")
N_POOL = 21
N_HOLDOUT = 6
N_CONTROL_TRAIN = 18
N_CONTROLS = 6
N_VAL_CONFIGS = 3


@dataclass(frozen=True)
class BenchSplit:
    """One named split: sorted training and test configuration names."""

    name: str
    train: tuple[str, ...]
    test: tuple[str, ...]


def _config_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per configuration with its settings and label; raise on inconsistent rows."""
    columns = ["split", *SETTINGS]
    per_config = df.groupby("config_name")[columns].nunique()
    mixed = sorted(per_config.index[(per_config > 1).any(axis=1)].astype(str))
    if mixed:
        raise ValueError(f"configuration(s) with mixed kinematics or labels: {mixed}")
    table = df.groupby("config_name")[columns].first()
    table.index = table.index.astype(str)
    return table.sort_index()


def _face_label(value: float) -> str:
    return f"{value:g}"


def build_splits(df: pd.DataFrame) -> dict[str, BenchSplit]:
    """Build the 14 named splits, in order.

    Args:
        df: The fine dataset (or any frame with ``config_name``, ``split`` and the three
            settings).

    Returns:
        ``{name: BenchSplit}`` for ``interpolation``, the six faces (stroke 35/55, f* 0.85/1.15,
        pitch 30/60), ``control:0..5`` and ``control:e4_seed0``.

    Raises:
        ValueError: If a setting does not have exactly 3 distinct values, the labelled pool is
            not 21 train + 6 holdout, or a configuration's rows disagree on its settings.
    """
    table = _config_table(df)
    for setting in SETTINGS:
        n_levels = table[setting].nunique()
        if n_levels != 3:
            raise ValueError(
                f"setting {setting!r} has {n_levels} distinct value(s); the bench needs "
                "exactly 3 (a missing outer value would silently make the middle a face)"
            )
    pool = sorted(table.index[table["split"] == "train"])
    holdouts = sorted(table.index[table["split"] == "holdout"])
    if len(pool) != N_POOL or len(holdouts) != N_HOLDOUT:
        raise ValueError(
            f"the labelled pool must be {N_POOL} train + {N_HOLDOUT} holdout configurations; "
            f"found {len(pool)} + {len(holdouts)}"
        )
    everything = list(table.index)
    splits: dict[str, BenchSplit] = {
        "interpolation": BenchSplit("interpolation", tuple(pool), tuple(holdouts))
    }
    for setting in SETTINGS:
        values = sorted(table[setting].unique())
        for value in (values[0], values[-1]):
            name = f"face:{setting}={_face_label(value)}"
            test = sorted(table.index[table[setting] == value])
            train = sorted(set(everything) - set(test))
            splits[name] = BenchSplit(name, tuple(train), tuple(test))
    for k in range(N_CONTROLS):
        drawn = np.random.default_rng(k).choice(
            pool, size=N_CONTROL_TRAIN, replace=False
        )
        name = f"control:{k}"
        splits[name] = BenchSplit(
            name, tuple(sorted(str(c) for c in drawn)), tuple(holdouts)
        )
    e4 = np.random.default_rng(0).permutation(pool)[:N_CONTROL_TRAIN]
    splits["control:e4_seed0"] = BenchSplit(
        "control:e4_seed0", tuple(sorted(str(c) for c in e4)), tuple(holdouts)
    )
    # Every split is disjoint and non-empty by construction (tested on the output).
    return splits


def carve_split(
    split: BenchSplit, *, seed: int, n_val_configs: int = N_VAL_CONFIGS
) -> SplitAssignment:
    """Carve validation configurations from a split's training list (the shipped algorithm).

    Args:
        split: A bench split.
        seed: The carve seed (the model seed).
        n_val_configs: Validation configurations to carve.

    Returns:
        A :class:`SplitAssignment` whose test list is the split's.
    """
    train, val = carve_validation(split.train, seed=seed, n_val_configs=n_val_configs)
    return SplitAssignment(
        train_configs=train, val_configs=val, test_configs=list(split.test)
    )
