"""Bench splits (add-surrogate-comparison-bench, 3b.2; CPU tier).

Scenarios "Fourteen splits with the specified membership", "The E4 control reproduces the
exploration's subset" (list only; its rank is tested with the ridge), "Interpolation validation
carve matches the shipped trainer" and "Splits are disjoint, deterministic and guarded"
(surrogate-comparison-bench spec, requirement "Bench splits").
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import make_config_splits
from mosquito_cfd.surrogate_bench import BENCH_SEEDS
from mosquito_cfd.surrogate_bench.splits import SETTINGS, build_splits, carve_split

FINE_DATASET = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "prelim_sweep_fine"
    / "dataset.parquet"
)
HOLDOUTS = [
    "s35_f085_p45",
    "s45_f085_p60",
    "s45_f100_p60",
    "s45_f115_p60",
    "s55_f085_p45",
    "s55_f115_p45",
]
# Literal lists from the spec's numpy calls (computed once, so a change in NumPy's
# Generator.choice stream fails loudly).
CONTROLS = {
    0: "s35_f085_p30 s35_f085_p60 s35_f100_p30 s35_f100_p45 s35_f100_p60 s35_f115_p30 "
    "s45_f085_p30 s45_f085_p45 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p30 s55_f115_p60",
    1: "s35_f085_p30 s35_f085_p60 s35_f100_p30 s35_f100_p60 s35_f115_p45 s35_f115_p60 "
    "s45_f085_p30 s45_f085_p45 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f085_p60 s55_f100_p30 s55_f100_p45 s55_f115_p30 s55_f115_p60",
    2: "s35_f085_p30 s35_f085_p60 s35_f100_p30 s35_f100_p45 s35_f100_p60 s35_f115_p30 "
    "s35_f115_p60 s45_f085_p30 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f085_p60 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p30",
    3: "s35_f085_p30 s35_f085_p60 s35_f100_p45 s35_f100_p60 s35_f115_p45 s35_f115_p60 "
    "s45_f085_p30 s45_f085_p45 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f085_p60 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p60",
    4: "s35_f085_p30 s35_f100_p30 s35_f100_p45 s35_f100_p60 s35_f115_p30 s35_f115_p60 "
    "s45_f085_p30 s45_f085_p45 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p30 s55_f115_p60",
    5: "s35_f085_p30 s35_f085_p60 s35_f100_p30 s35_f100_p45 s35_f100_p60 s35_f115_p30 "
    "s35_f115_p45 s45_f085_p30 s45_f085_p45 s45_f100_p30 s45_f100_p45 s45_f115_p30 "
    "s45_f115_p45 s55_f085_p30 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p30",
}
E4_SUBSET = (
    "s35_f085_p30 s35_f100_p30 s35_f100_p45 s35_f100_p60 s35_f115_p30 s35_f115_p45 "
    "s35_f115_p60 s45_f085_p30 s45_f100_p30 s45_f100_p45 s45_f115_p30 s45_f115_p45 "
    "s55_f085_p30 s55_f100_p30 s55_f100_p45 s55_f100_p60 s55_f115_p30 s55_f115_p60"
).split()
FACES = [
    ("stroke_amp_deg", 35.0, "35"),
    ("stroke_amp_deg", 55.0, "55"),
    ("frequency_fstar", 0.85, "0.85"),
    ("frequency_fstar", 1.15, "1.15"),
    ("pitch_amp_deg", 30.0, "30"),
    ("pitch_amp_deg", 60.0, "60"),
]


@pytest.fixture(scope="module")
def fine() -> pd.DataFrame:
    return pd.read_parquet(FINE_DATASET, columns=["config_name", "split", *SETTINGS])


@pytest.fixture(scope="module")
def splits(fine):
    return build_splits(fine)


@pytest.fixture(scope="module")
def configs(fine):
    return fine.drop_duplicates("config_name").set_index("config_name")


def test_fourteen_named_splits(splits):
    expected = [
        "interpolation",
        *(f"face:{s}={label}" for s, _, label in FACES),
        *(f"control:{k}" for k in range(6)),
        "control:e4_seed0",
    ]
    assert list(splits) == expected


def test_interpolation_is_the_labelled_split(splits, configs):
    split = splits["interpolation"]
    assert list(split.test) == HOLDOUTS
    assert list(split.train) == sorted(configs.index[configs["split"] == "train"])


@pytest.mark.parametrize(("setting", "value", "label"), FACES)
def test_each_face_holds_out_exactly_its_nine(splits, configs, setting, value, label):
    split = splits[f"face:{setting}={label}"]
    on_face = sorted(configs.index[configs[setting] == value])
    assert list(split.test) == on_face and len(on_face) == 9
    assert list(split.train) == sorted(set(configs.index) - set(on_face))


@pytest.mark.parametrize("k", range(6))
def test_controls_equal_their_literal_lists(splits, k):
    split = splits[f"control:{k}"]
    assert list(split.train) == CONTROLS[k].split()
    assert list(split.test) == HOLDOUTS


def test_the_e4_control_is_the_exploration_subset(splits):
    split = splits["control:e4_seed0"]
    assert list(split.train) == E4_SUBSET
    assert list(split.test) == HOLDOUTS


def test_splits_are_deterministic_disjoint_and_non_empty(fine, splits):
    again = build_splits(fine)
    assert again == splits
    for split in splits.values():
        assert split.train and split.test
        assert not set(split.train) & set(split.test)


@pytest.mark.parametrize("seed", BENCH_SEEDS)
def test_interpolation_carve_is_the_shipped_carve(fine, splits, seed):
    carved = carve_split(splits["interpolation"], seed=seed)
    shipped = make_config_splits(fine, seed=seed, n_val_configs=3)
    assert carved == shipped


@pytest.mark.parametrize("name", ["face:stroke_amp_deg=55", "control:3"])
def test_carves_are_drawn_from_the_split_training_list(splits, name):
    split = splits[name]
    carved = carve_split(split, seed=1234)
    assert len(carved.val_configs) == 3
    assert set(carved.train_configs) | set(carved.val_configs) == set(split.train)
    assert not set(carved.train_configs) & set(carved.val_configs)
    assert list(carved.test_configs) == list(split.test)


def test_a_setting_without_three_values_is_rejected(fine):
    no_55 = fine[fine["stroke_amp_deg"] != 55.0]
    with pytest.raises(ValueError, match="stroke_amp_deg"):
        build_splits(no_55)
    extra = fine.copy()
    extra.loc[extra["config_name"] == "s45_f100_p45", "pitch_amp_deg"] = 50.0
    with pytest.raises(ValueError, match="pitch_amp_deg"):
        build_splits(extra)


def test_a_pool_other_than_21_plus_6_is_rejected(fine):
    relabelled = fine.copy()
    relabelled.loc[relabelled["config_name"] == "s45_f100_p45", "split"] = "holdout"
    with pytest.raises(ValueError, match="21"):
        build_splits(relabelled)


def test_a_config_with_mixed_kinematics_is_rejected(fine):
    mixed = fine.copy()
    rows = np.flatnonzero(mixed["config_name"].to_numpy() == "s45_f100_p45")
    mixed.iloc[rows[0], mixed.columns.get_loc("stroke_amp_deg")] = 35.0
    with pytest.raises(ValueError, match="s45_f100_p45"):
        build_splits(mixed)
