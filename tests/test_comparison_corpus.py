"""Tests of the synthetic corpus helper itself (add-real-comparison-figures, task 2.2).

The helper builds ``metrics.json`` with the real ``train`` helpers, so a builder test could pass
because helper and builder agree by construction. These tests anchor it independently: the key tree
matches the committed file, a hand-built corpus gives literal known answers, and the coarse and fine
corpora differ in every file.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from _comparison_corpus import (
    COARSE_DIR,
    FINE_DIR,
    CorpusSpec,
    write_repo,
)

from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS

REPO = Path(__file__).resolve().parents[1]
FILES = (
    "dataset.parquet",
    "surrogate/holdout_predictions.parquet",
    "surrogate/metrics.json",
    "surrogate/run_metadata.json",
)


def _key_tree(node, path=()):
    """The set of key paths; ``per_config`` keys collapse to one wildcard."""
    out = set()
    if isinstance(node, dict):
        for key, value in node.items():
            k = "*" if path[-1:] == ("per_config",) else key
            out.add((*path, k))
            if path[-1:] not in (("inference",), ("reproducibility",)):
                out |= _key_tree(value, (*path, k))
    elif isinstance(node, list) and node and isinstance(node[0], dict):
        for item in node:
            out |= _key_tree(item, (*path, "[]"))
    return out


def test_fixture_metrics_key_tree_matches_the_committed_file(tmp_path):
    written = write_repo(tmp_path)
    committed = json.loads(
        (REPO / COARSE_DIR / "surrogate" / "metrics.json").read_text(encoding="utf-8")
    )
    fixture = json.loads(
        (tmp_path / COARSE_DIR / "surrogate" / "metrics.json").read_text(
            encoding="utf-8"
        )
    )
    assert _key_tree(fixture) == _key_tree(committed)
    assert set(fixture["inference"]) == set(committed["inference"])
    assert set(fixture["reproducibility"]) == set(committed["reproducibility"])
    assert written["coarse"]["metrics"]["seed_sweep"]["seeds"] == [
        1234,
        1235,
        1236,
        1237,
        1238,
    ]


def _known_answer_truth(split, index, phase, beat):
    """CF_x: training ramps (index+1)·phase; holdout = mean training ramp + 1. CF_y: holdout
    constant [0,0,0,0,0,6] per configuration. Other targets: a harmless waveform."""
    n_train = 3
    cols = np.zeros((phase.shape[0], len(TARGET_COLUMNS)))
    mean_slope = sum(range(1, n_train + 1)) / n_train
    if split == "train":
        cols[:, 0] = (index + 1) * phase
        cols[:, 1] = phase
    else:
        cols[:, 0] = mean_slope * phase + 1.0
        cols[:, 1] = 6.0 if index == 5 else 0.0
    for j in range(2, len(TARGET_COLUMNS)):
        cols[:, j] = np.sin(2 * np.pi * phase) * (1 + index + j)
    return cols


def _known_answer_error(seed_index, holdout_index, phase):
    err = np.zeros((phase.shape[0], len(TARGET_COLUMNS)))
    err[:, 0] = np.where(np.arange(phase.shape[0]) % 2 == 0, 0.1, -0.1)
    err[:, 1:] = 0.01 * (seed_index + 1)
    return err


def test_hand_built_corpus_gives_literal_known_answers(tmp_path):
    spec = CorpusSpec(
        n_train=3,
        rows_per_beat=2,
        truth=_known_answer_truth,
        error=_known_answer_error,
    )
    written = write_repo(tmp_path, coarse=spec)["coarse"]
    skill = written["metrics"]["phase_baseline_skill"]["per_target"]["CF_x"]
    assert math.isclose(skill["phase_baseline_rmse"], 1.0, rel_tol=1e-12, abs_tol=0)
    assert math.isclose(skill["skill"], 0.99, rel_tol=1e-12, abs_tol=0)
    pred = pd.read_parquet(
        tmp_path / COARSE_DIR / "surrogate" / "holdout_predictions.parquet"
    )
    means = pred.groupby("config_name")["CF_y_true"].mean().to_numpy()
    assert means.tolist() == [0.0, 0.0, 0.0, 0.0, 0.0, 6.0]
    assert math.isclose(float(np.std(means)), math.sqrt(5.0), rel_tol=1e-12, abs_tol=0)


def test_coarse_and_fine_fixtures_differ_in_every_file(tmp_path):
    write_repo(tmp_path)
    for name in FILES:
        a = (tmp_path / COARSE_DIR / name).read_bytes()
        b = (tmp_path / FINE_DIR / name).read_bytes()
        assert a != b, name
    assert (tmp_path / FINE_DIR / "run_metadata.json").is_file()


def test_edit_runs_keeps_range_consistent(tmp_path):
    def edit(runs):
        runs[2]["per_target"]["CF_x"]["config_mean_r2"] = -50.0

    written = write_repo(tmp_path, coarse=CorpusSpec(edit_runs=edit))["coarse"]
    sweep = written["metrics"]["seed_sweep"]
    values = [r["per_target"]["CF_x"]["config_mean_r2"] for r in sweep["runs"]]
    assert values[2] == -50.0  # the edit landed
    assert sweep["range"]["CF_x"]["config_mean_r2"] == {
        "min": -50.0,
        "max": max(values),
    }


def test_edit_dataset_runs_before_hashing(tmp_path):
    import hashlib

    def edit(df):
        return df.assign(CF_z=df["CF_z"] + 0.5)

    written = write_repo(tmp_path, coarse=CorpusSpec(edit_dataset=edit))["coarse"]
    recorded = json.loads(
        (tmp_path / COARSE_DIR / "surrogate" / "run_metadata.json").read_text(
            encoding="utf-8"
        )
    )
    actual = hashlib.sha256(
        (tmp_path / COARSE_DIR / "dataset.parquet").read_bytes()
    ).hexdigest()
    assert recorded["inputs"]["hash"] == actual == written["sha"]
