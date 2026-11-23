"""Shared validation carve (add-surrogate-comparison-bench, 3a; CPU tier).

The bench carves validation configurations from an arbitrary training list with the same
algorithm make_config_splits uses (spec scenario "Interpolation validation carve matches the
shipped trainer").
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import carve_validation, make_config_splits

FINE_DATASET = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "prelim_sweep_fine"
    / "dataset.parquet"
)


@pytest.fixture(scope="module")
def configs() -> pd.DataFrame:
    df = pd.read_parquet(
        FINE_DATASET, columns=["config_name", "split", "stroke_amp_deg"]
    )
    return df.drop_duplicates("config_name").set_index("config_name")


@pytest.mark.parametrize("seed", [1234, 1235, 1236, 1237, 1238])
def test_carve_over_the_pool_is_make_config_splits(configs, seed):
    pool = list(configs.index[configs["split"] == "train"])
    df = configs.reset_index()
    shipped = make_config_splits(df, seed=seed, n_val_configs=3)
    train, val = carve_validation(pool, seed=seed, n_val_configs=3)
    assert val == shipped.val_configs
    assert train == shipped.train_configs


def test_carve_of_a_face_split_is_pinned(configs):
    """The stroke-55 face's 18 training configurations, seed 1234 (literal from numpy)."""
    pool = list(configs.index[configs["stroke_amp_deg"] != 55.0])
    train, val = carve_validation(pool, seed=1234, n_val_configs=3)
    assert val == ["s45_f115_p30", "s45_f115_p45", "s45_f115_p60"]
    assert sorted(train + val) == sorted(pool) and len(train) == 15


def test_carve_sorts_its_input(configs):
    pool = list(configs.index[configs["split"] == "train"])
    assert carve_validation(list(reversed(pool)), seed=7, n_val_configs=3) == (
        carve_validation(sorted(pool), seed=7, n_val_configs=3)
    )


@pytest.mark.parametrize("n_val", [0, 3])
def test_carve_rejects_an_impossible_count(n_val):
    with pytest.raises(ValueError, match="n_val_configs"):
        carve_validation(["a", "b", "c"], seed=0, n_val_configs=n_val)


def test_the_carve_sorts_raw_names_as_make_config_splits_did_before():
    """Integer names sort numerically (as on main), not as strings; the names come back raw."""
    import numpy as np

    pool = [23, 7, 8, 9, 24, 26, 100, 5]
    train, val = carve_validation(pool, seed=1234, n_val_configs=3)
    ordered = sorted(pool)
    idx = np.random.default_rng(1234).choice(len(ordered), size=3, replace=False)
    assert val == sorted(ordered[i] for i in idx)
    assert all(isinstance(v, int) for v in val + train)


def test_a_pool_with_repeated_names_is_rejected():
    with pytest.raises(ValueError, match="repeat"):
        carve_validation(["a", "b", "b", "c", "d"], seed=1, n_val_configs=2)
