"""CPU-tier tests for the trainer's seed sweep (change replace-config-r2-with-baseline-skill).

Torch-free: the per-seed fit is replaced through the ``_fit_one_seed`` / ``_measure_inference``
seam (design D4), so order and atomicity are checked on the CPU-only CI runner. Each test cites
the ``force-surrogate`` spec scenario it verifies ("Multi-seed sweep reported by the trainer").
"""

import json
import math
import sys

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import train
from mosquito_cfd.force_surrogate.train import (
    FEATURE_COLUMNS,
    TARGET_COLUMNS,
    build_metrics,
    build_seed_run,
    build_training_metadata,
    make_config_splits,
    run_training,
    summarize_seed_sweep,
)

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "c" * 64
TIMESTAMP = "2026-10-26T12:00:00Z"
ARTIFACTS = (
    "metrics.json",
    "holdout_predictions.parquet",
    "surrogate.pt",
    "run_metadata.json",
)


def _run(seed, skill, r2=0.99, rmse=0.1, cmr2=0.5):
    stats = {"skill": skill, "r2": r2, "rmse": rmse, "config_mean_r2": cmr2}
    return {
        "seed": seed,
        "val_configs": [f"v{seed}"],
        "per_target": {c: dict(stats) for c in ("CF_x", "CF_z")},
    }


# --- Scenario: Seed-sweep summary is computed from the per-seed runs ---------------------


def test_summary_lists_the_primary_first_and_ranges_over_all_seeds():
    """Range is min/max over every seed including the primary; seeds list the primary first."""
    runs = [_run(1236, 0.97), _run(1234, 0.99), _run(1235, 0.95)]
    out = summarize_seed_sweep(runs, primary_seed=1234)
    assert out["primary_seed"] == 1234
    assert out["seeds"] == [1234, 1236, 1235]
    assert [r["seed"] for r in out["runs"]] == [1234, 1236, 1235]
    assert out["range"]["CF_x"]["skill"] == {"min": 0.95, "max": 0.99}
    assert out["range"]["CF_z"]["rmse"] == {"min": 0.1, "max": 0.1}


def test_summary_skips_nulls_and_nulls_an_all_null_statistic():
    """A null statistic is skipped; an all-null one has a null range (NaN or JSON None)."""
    runs = [_run(1, float("nan"), cmr2=None), _run(2, 0.9, cmr2=float("nan"))]
    out = summarize_seed_sweep(runs, primary_seed=1)
    assert out["range"]["CF_x"]["skill"] == {"min": 0.9, "max": 0.9}
    assert out["range"]["CF_x"]["config_mean_r2"] is None


def test_summary_of_one_seed_has_min_equal_max():
    """A single-seed sweep has min == max."""
    out = summarize_seed_sweep([_run(7, -0.25)], primary_seed=7)
    assert out["seeds"] == [7]
    assert out["range"]["CF_x"]["skill"] == {"min": -0.25, "max": -0.25}


def test_summary_rejects_runs_without_the_primary_or_with_a_repeat():
    """The primary must be present exactly once and no seed may repeat."""
    with pytest.raises(ValueError, match="primary seed"):
        summarize_seed_sweep([_run(1, 0.9)], primary_seed=2)
    with pytest.raises(ValueError, match="repeated"):
        summarize_seed_sweep([_run(1, 0.9), _run(1, 0.8)], primary_seed=1)


def test_seed_run_statistics_equal_the_top_level_metrics():
    """A seed's run entry carries the same numbers build_metrics puts at the top level."""
    rng = np.random.default_rng(4)
    holdout = pd.DataFrame({"config_name": ["h0"] * 5 + ["h1"] * 5 + ["h2"] * 5})
    y_true = rng.standard_normal((15, len(TARGET_COLUMNS)))
    y_pred = y_true + 0.05 * rng.standard_normal(y_true.shape)
    y_base = y_true + 0.3 * rng.standard_normal(y_true.shape)
    metrics = build_metrics(
        y_true,
        y_pred,
        holdout,
        inference={},
        reproducibility={},
        phase_baseline=(y_base, {"kind": "k"}),
    )
    run = build_seed_run(9, ["v1", "v2"], y_true, y_pred, holdout, y_base)
    assert run["seed"] == 9 and run["val_configs"] == ["v1", "v2"]
    for c in TARGET_COLUMNS:
        got = run["per_target"][c]
        assert got == {
            "skill": metrics["phase_baseline_skill"]["per_target"][c]["skill"],
            "r2": metrics["per_target"][c]["r2"],
            "rmse": metrics["per_target"][c]["rmse"],
            "config_mean_r2": metrics["config_resolved"][c]["config_mean_r2"],
        }


# --- Scenario: Duplicate seeds are rejected before anything is read or written ------------


@pytest.mark.parametrize(
    ("sweep", "match"),
    [
        ((1234,), "duplicate seed"),
        ((1235, 1235), "duplicate seed"),
        ((1235, 1236, 1235), "duplicate seed"),
        ((1235, -1), "non-negative"),
    ],
    ids=["primary", "pair", "gap", "negative"],
)
def test_invalid_seeds_raise_before_reading_or_writing(tmp_path, sweep, match):
    """A duplicate or negative seed raises before the dataset is touched."""
    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match=match):
        run_training(
            tmp_path / "does_not_exist.parquet",
            out_dir,
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            seed=1234,
            sweep_seeds=sweep,
        )
    assert not out_dir.exists()


def test_library_default_is_no_sweep():
    """run_training's library default trains the primary seed only."""
    import inspect

    assert inspect.signature(run_training).parameters["sweep_seeds"].default == ()


# --- Scenarios: primary trained first; a failing sweep seed writes nothing ---------------


def _toy_parquet(path):
    """Six train configs + two holdout configs, two beats each, a fittable signal."""
    frames = []
    names = [f"t{i}" for i in range(6)] + ["h0", "h1"]
    for idx, name in enumerate(names):
        for beat in (0, 1):
            phase = np.linspace(0.0, 1.0, 5, endpoint=False)
            frame = pd.DataFrame(
                {
                    "config_name": name,
                    "time": beat + phase,
                    "phase": phase,
                    "wingbeat": beat,
                    "split": "holdout" if name.startswith("h") else "train",
                    "stroke_amp_deg": 35.0 + idx,
                    "frequency_fstar": 1.0,
                    "pitch_amp_deg": 45.0,
                }
            )
            for j, c in enumerate(TARGET_COLUMNS):
                frame[c] = (j + 1) * np.sin(2 * np.pi * phase) + 0.1 * idx
            frames.append(frame)
    pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
    return path


def _install_recorder(monkeypatch, *, fail_on):
    """Replace the per-seed fit with a recorder that raises on seed ``fail_on``."""
    calls = []

    def fake_fit(df, *, seed, n_val_configs, **_):
        calls.append(("fit", seed))
        if seed == fail_on:
            raise RuntimeError(f"recorder: seed {seed} failed")
        split = make_config_splits(df, seed=seed, n_val_configs=n_val_configs)
        n_test = int(np.isin(df["config_name"], split.test_configs).sum())
        return train._SeedFit(
            split=split,
            model=None,
            feature_std=train.Standardizer(),
            target_std=train.Standardizer(),
            feature_names=list(FEATURE_COLUMNS),
            history=[],
            x_test=np.zeros((n_test, len(FEATURE_COLUMNS))),
            y_pred=np.zeros((n_test, len(TARGET_COLUMNS))),
            val_aggregate={},
        )

    def fake_inference(model, x, *, device):
        calls.append(("inference", None))
        return {"latency_ms": 1.0, "throughput_rows_per_s": 1.0, "basis": "fake"}

    monkeypatch.setattr(train, "_fit_one_seed", fake_fit)
    monkeypatch.setattr(train, "_measure_inference", fake_inference)
    return calls


def test_primary_seed_is_trained_and_timed_before_any_sweep_seed(tmp_path, monkeypatch):
    """Recorded order: primary fit, its inference timing, then sweep seeds as given."""
    calls = _install_recorder(
        monkeypatch, fail_on=1236
    )  # last seed: no torch.save reached
    with pytest.raises(RuntimeError, match="seed 1236 failed"):
        run_training(
            _toy_parquet(tmp_path / "ds.parquet"),
            tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            seed=1234,
            n_val_configs=2,
            sweep_seeds=(1238, 1235, 1236),
        )
    assert calls == [
        ("fit", 1234),
        ("inference", None),
        ("fit", 1238),
        ("fit", 1235),
        ("fit", 1236),
    ]


def test_a_failing_sweep_seed_writes_nothing(tmp_path, monkeypatch):
    """A seed failing after the primary propagates and leaves none of the four artifacts."""
    # Unload torch for this test only (it may already be loaded on a GPU host, e.g. by
    # conftest's CUDA probe), so the assertion below proves run_training did not import it.
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    _install_recorder(monkeypatch, fail_on=1236)
    out_dir = tmp_path / "out"
    with pytest.raises(RuntimeError, match="seed 1236 failed"):
        run_training(
            _toy_parquet(tmp_path / "ds.parquet"),
            out_dir,
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            seed=1234,
            n_val_configs=2,
            sweep_seeds=(1236, 1237),
        )
    assert not any((out_dir / name).exists() for name in ARTIFACTS)
    assert "torch" not in sys.modules or sys.modules["torch"] is None


# --- run_metadata seeds record the sweep ----------------------------------------------


def test_training_metadata_records_the_sweep_seeds():
    """build_training_metadata round-trips a seeds block that carries the sweep list."""
    meta = build_training_metadata(
        docker_image_digest=DIGEST,
        timestamp=TIMESTAMP,
        seeds={"global": 1234, "sweep": [1235, 1236]},
        feature_names=list(FEATURE_COLUMNS),
    )
    assert json.loads(json.dumps(meta))["seeds"] == {
        "global": 1234,
        "sweep": [1235, 1236],
    }


def test_summary_round_trips_through_json_with_nulls(tmp_path):
    """NaN statistics serialize as null in metrics.json."""
    out = summarize_seed_sweep([_run(1, float("nan"))], primary_seed=1)
    path = tmp_path / "m.json"
    train.write_json(path, out)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["runs"][0]["per_target"]["CF_x"]["skill"] is None
    assert loaded["range"]["CF_x"]["skill"] is None
    assert not math.isnan(loaded["range"]["CF_x"]["r2"]["min"])


def test_converged_filter_is_what_the_recorder_sees(tmp_path, monkeypatch):
    """The per-seed fit receives the converged-beat frame (startup rows already dropped)."""
    seen = []

    def fake_fit(df, **_):
        seen.append(int(df["wingbeat"].min()))
        raise RuntimeError("stop")

    monkeypatch.setattr(train, "_fit_one_seed", fake_fit)
    with pytest.raises(RuntimeError, match="stop"):
        run_training(
            _toy_parquet(tmp_path / "ds.parquet"),
            tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            n_val_configs=2,
        )
    assert seen == [1]


def test_a_malformed_phase_only_baseline_fails_before_any_seed_trains(
    tmp_path, monkeypatch
):
    """The baseline only reads the dataset, so a malformed one raises before training."""
    calls = _install_recorder(monkeypatch, fail_on=None)
    path = _toy_parquet(tmp_path / "ds.parquet")
    df = pd.read_parquet(path)
    # Duplicate a phase inside one train config's converged beat.
    beat = df.index[(df["config_name"] == "t0") & (df["wingbeat"] == 1)]
    df.loc[beat[1], "phase"] = df.loc[beat[0], "phase"]
    df.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="duplicate phase"):
        run_training(
            path,
            tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            n_val_configs=2,
        )
    assert calls == []
