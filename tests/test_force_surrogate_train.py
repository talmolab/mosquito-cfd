"""CPU-tier tests for force_surrogate.train (TDD, PR5).

Cluster-free and **torch-free** (roadmap CC-2, design D2): every test here runs on the CPU-only
CI runner with the optional ``train`` dependency-group NOT installed. These tests gate CI. The
GPU/torch tier lives in ``test_force_surrogate_train_gpu.py`` (``@pytest.mark.gpu``, skipped here).

Each test cites the ``force-surrogate`` spec scenario it verifies (change
``add-force-surrogate-train``).
"""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import (
    FEATURE_COLUMNS,
    TARGET_COLUMNS,
    Standardizer,
    build_features,
    build_metrics,
    build_predictions_frame,
    build_training_metadata,
    compute_config_resolved,
    compute_metrics,
    filter_converged_beat,
    filter_converged_beat_report_holdout,
    log_to_wandb,
    make_config_splits,
    run_training,
    write_json,
)

HOLDOUT_CONFIGS = [
    "s35_f085_p45",
    "s45_f085_p60",
    "s45_f100_p60",
    "s45_f115_p60",
    "s55_f085_p45",
    "s55_f115_p45",
]


def _toy_dataset(
    n_train: int = 12,
    n_holdout: int = 6,
    rows_per_config: int = 4,
    *,
    seed: int = 0,
) -> pd.DataFrame:
    """A tiny synthetic dataset frame with the committed schema (no real CFD).

    Two wingbeats (``wingbeat`` 0 = startup, 1 = converged); ``phase`` spans [0, 1); the six
    coefficients are deterministic functions of the kinematics + phase so a model can fit.
    """
    rng = np.random.default_rng(seed)
    frames = []
    train_names = [f"train_{i:02d}" for i in range(n_train)]
    holdout_names = HOLDOUT_CONFIGS[:n_holdout]
    for idx, name in enumerate(train_names + holdout_names):
        split = "train" if name in train_names else "holdout"
        stroke = float(rng.choice([35.0, 45.0, 55.0]))
        fstar = float(rng.choice([0.85, 1.0, 1.15]))
        pitch = float(rng.choice([30.0, 45.0, 60.0]))
        for beat in (0, 1):
            phase = np.linspace(0.0, 1.0, rows_per_config, endpoint=False)
            time = (beat + phase) / fstar
            cf_x = 0.1 * stroke / 45.0 + 0.05 * np.sin(2 * np.pi * phase)
            cf_z = 0.2 * fstar + 0.03 * np.cos(2 * np.pi * phase)
            frames.append(
                pd.DataFrame(
                    {
                        "config_name": name,
                        "index": idx,
                        "time": time,
                        "phase": phase,
                        "wingbeat": beat,
                        "stroke_amp_deg": stroke,
                        "frequency_fstar": fstar,
                        "pitch_amp_deg": pitch,
                        "reynolds": 50.0 + stroke,
                        "split": split,
                        "Fx": cf_x * 100,
                        "Fy": 0.0,
                        "Fz": cf_z * 100,
                        "Mx": 0.0,
                        "My": 0.0,
                        "Mz": cf_x * 10,
                        "CF_x": cf_x,
                        "CF_y": 0.0,  # constant-by-symmetry → zero variance (R² sentinel)
                        "CF_z": cf_z,
                        "CF_mx": 0.0,
                        "CF_my": 0.0,
                        "CF_mz": cf_x * 0.1,
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


# --- Phase 2: input/target construction --------------------------------------------------


def test_build_features_columns_and_no_reynolds():
    """Scenario: Feature columns are the kinematics knobs plus cyclic phase."""
    df = _toy_dataset()
    x, names = build_features(df)
    assert names == [
        "stroke_amp_deg",
        "frequency_fstar",
        "pitch_amp_deg",
        "phase_sin",
        "phase_cos",
    ]
    assert "reynolds" not in names
    assert x.shape == (len(df), 5)
    # phase_sin / phase_cos are sin/cos(2 pi phase)
    np.testing.assert_allclose(x[:, 3], np.sin(2 * np.pi * df["phase"].to_numpy()))
    np.testing.assert_allclose(x[:, 4], np.cos(2 * np.pi * df["phase"].to_numpy()))


def test_cyclic_phase_continuous_across_wrap():
    """Scenario: Cyclic phase encoding is continuous across the wrap."""
    df = pd.DataFrame(
        {
            "phase": [0.999, 0.001],
            "stroke_amp_deg": [45.0, 45.0],
            "frequency_fstar": [1.0, 1.0],
            "pitch_amp_deg": [45.0, 45.0],
        }
    )
    x, _ = build_features(df)
    cyclic_dist = np.hypot(x[0, 3] - x[1, 3], x[0, 4] - x[1, 4])
    raw_dist = abs(0.999 - 0.001)
    assert cyclic_dist < 0.05  # adjacent in the cycle
    assert raw_dist > 0.9  # but maximally far as raw scalars


def test_filter_converged_beat_drops_startup():
    """Scenario: Only the converged beat is used."""
    df = _toy_dataset()
    out = filter_converged_beat(df)
    assert (out["wingbeat"] >= 1).all()
    assert (out["wingbeat"] == 0).sum() == 0
    assert len(out) == int((df["wingbeat"] == 1).sum())


def test_standardizer_fit_on_training_rows_only():
    """Scenario: Standardization is fit on training rows only."""
    df = filter_converged_beat(_toy_dataset())
    x, _ = build_features(df)
    is_train = (df["split"] == "train").to_numpy()
    std = Standardizer().fit(x[is_train])
    # train-fit stats differ from full-dataset stats (no holdout leakage into the fit)
    full = Standardizer().fit(x)
    assert not np.allclose(std.mean_, full.mean_)
    z = std.transform(x[is_train])
    np.testing.assert_allclose(z.mean(axis=0), 0.0, atol=1e-9)
    np.testing.assert_allclose(z.std(axis=0), 1.0, atol=1e-9)


def test_targets_round_trip_through_standardization():
    """Scenario: Targets round-trip through standardization."""
    df = filter_converged_beat(_toy_dataset())
    y = df[TARGET_COLUMNS].to_numpy(dtype=float)
    std = Standardizer().fit(y)
    np.testing.assert_allclose(std.inverse_transform(std.transform(y)), y, atol=1e-9)


def test_standardizer_zero_variance_column_does_not_nan():
    """A constant column (e.g. CF_y) standardizes to 0, not NaN (epsilon-floored scale)."""
    y = np.column_stack([np.linspace(0, 1, 8), np.zeros(8)])
    std = Standardizer().fit(y)
    z = std.transform(y)
    assert np.isfinite(z).all()
    np.testing.assert_allclose(z[:, 1], 0.0)


# --- Phase 3: configuration split --------------------------------------------------------


def test_holdout_configs_are_the_dataset_label():
    """Scenario: Holdout configs are exactly the dataset holdout label."""
    df = _toy_dataset()
    sp = make_config_splits(df, seed=0)
    assert set(sp.test_configs) == set(HOLDOUT_CONFIGS)
    assert not (set(sp.test_configs) & set(sp.train_configs))
    assert not (set(sp.test_configs) & set(sp.val_configs))


def test_validation_carved_at_config_level():
    """Scenario: Validation is carved at the configuration level."""
    df = _toy_dataset()
    sp = make_config_splits(df, seed=0, n_val_configs=3)
    train_pool = set(df.loc[df["split"] == "train", "config_name"].unique())
    assert len(sp.val_configs) == 3
    assert set(sp.val_configs) <= train_pool
    assert not (set(sp.val_configs) & set(sp.train_configs))
    assert set(sp.val_configs) | set(sp.train_configs) == train_pool


def test_split_seed_reproducible_and_seed_sensitive():
    """Scenario: Split is seed-reproducible and seed-sensitive."""
    df = _toy_dataset()
    a = make_config_splits(df, seed=7)
    b = make_config_splits(df, seed=7)
    c = make_config_splits(df, seed=99)
    assert a.train_configs == b.train_configs and a.val_configs == b.val_configs
    assert (
        a.test_configs == c.test_configs == sorted(HOLDOUT_CONFIGS)
    )  # test fixed by label
    # seeded carve selects from the SORTED unique config list (pandas-version stable)
    assert sp_val_is_subset_of_sorted(df, a)


def sp_val_is_subset_of_sorted(df, sp) -> bool:
    pool = sorted(df.loc[df["split"] == "train", "config_name"].unique())
    return set(sp.val_configs) <= set(pool)


def test_malformed_split_raises():
    """Scenario: Malformed split raises rather than silently emptying a set."""
    df = _toy_dataset()
    with pytest.raises(ValueError, match="split"):
        make_config_splits(df.drop(columns=["split"]), seed=0)
    no_holdout = df[df["split"] == "train"].copy()
    with pytest.raises(ValueError, match="holdout"):
        make_config_splits(no_holdout, seed=0)
    with pytest.raises(ValueError, match="valid"):
        make_config_splits(df, seed=0, n_val_configs=0)


# --- Phase 4: metrics --------------------------------------------------------------------


def test_metrics_math_known_arrays():
    """Scenario: Metrics math is correct on known arrays."""
    y_true = np.array([[1.0], [2.0], [3.0], [4.0]])
    y_pred = np.array([[1.0], [2.0], [3.0], [5.0]])  # one residual of 1.0
    m = compute_metrics(y_true, y_pred, ["CF_x"])
    t = m["per_target"]["CF_x"]
    assert t["rmse"] == pytest.approx(0.5)  # sqrt(1/4)
    assert t["mae"] == pytest.approx(0.25)
    ss_tot = np.sum((y_true - y_true.mean()) ** 2)  # 5.0
    assert t["r2"] == pytest.approx(1.0 - 1.0 / ss_tot)


def test_constant_target_r2_is_sentinel():
    """Scenario: Constant-target R² is a defined sentinel, not a divide-by-zero."""
    y_true = np.column_stack([np.array([1.0, 2.0, 3.0, 4.0]), np.zeros(4)])
    y_pred = np.column_stack([np.array([1.0, 2.0, 3.0, 5.0]), np.zeros(4)])
    m = compute_metrics(y_true, y_pred, ["CF_x", "CF_y"])
    assert np.isnan(m["per_target"]["CF_y"]["r2"])  # sentinel
    assert np.isfinite(m["per_target"]["CF_y"]["rmse"])
    assert np.isfinite(m["per_target"]["CF_y"]["mae"])
    # aggregate R² is NaN-aware: it ignores the CF_y sentinel
    assert np.isfinite(m["aggregate"]["r2"])
    assert m["aggregate"]["r2"] == pytest.approx(m["per_target"]["CF_x"]["r2"])


def test_aggregate_rmse_mae_are_nan_aware():
    """A NaN datum in one target nulls that target but not the aggregate RMSE/MAE."""
    y_true = np.column_stack(
        [np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.0, 2.0, 3.0, 4.0])]
    )
    y_pred = y_true.copy()
    y_pred[0, 1] = np.nan  # corrupt one datum in target 2
    m = compute_metrics(y_true, y_pred, ["CF_x", "CF_y"])
    assert np.isnan(m["per_target"]["CF_y"]["rmse"])  # target 2 is NaN
    # aggregate RMSE/MAE skip the NaN target (consistent with R²) — not silently nulled
    assert m["aggregate"]["rmse"] == pytest.approx(m["per_target"]["CF_x"]["rmse"])
    assert m["aggregate"]["mae"] == pytest.approx(m["per_target"]["CF_x"]["mae"])


def test_near_zero_variance_r2_is_sentinel():
    """A near-(not exactly-)zero-variance target yields the NaN R² sentinel, not garbage."""
    base = 5.0
    y_true = np.column_stack(
        [np.array([1.0, 2.0, 3.0, 4.0]), base + np.array([0.0, 1e-13, -1e-13, 0.0])]
    )
    y_pred = y_true + 0.1
    m = compute_metrics(y_true, y_pred, ["CF_x", "CF_y"])
    assert np.isnan(
        m["per_target"]["CF_y"]["r2"]
    )  # tiny variance -> sentinel, not -1e24


def test_compute_metrics_empty_raises():
    """compute_metrics on a zero-row array raises rather than emitting a NaN/warning."""
    with pytest.raises(ValueError, match="zero-row"):
        compute_metrics(np.empty((0, 1)), np.empty((0, 1)), ["CF_x"])


def test_config_resolved_known_answer():
    """Scenario: config-resolved quantities match known-answer arrays."""
    # config A true [1,3] (mean 2), config B true [5,7] (mean 6); pred per-config means 2 and 5
    config_names = np.array(["A", "A", "B", "B"])
    y_true = np.array([[1.0], [3.0], [5.0], [7.0]])
    y_pred = np.array([[2.0], [2.0], [5.0], [5.0]])
    cr = compute_config_resolved(y_true, y_pred, config_names, ["CF_x"])
    # within SS = 4, total SS = 20 -> fraction 0.2
    assert cr["CF_x"]["within_config_variance_fraction"] == pytest.approx(0.2)
    # config-mean R2 = 1 - 1/8 = 0.875 (cm_true [2,6], cm_pred [2,5])
    assert cr["CF_x"]["config_mean_r2"] == pytest.approx(0.875)


def test_config_resolved_constant_means_sentinel():
    """Scenario: A constant per-configuration mean yields the R² sentinel, not garbage."""
    config_names = np.array(["A", "A", "B", "B"])
    y_true = np.array(
        [[1.0], [3.0], [1.0], [3.0]]
    )  # both configs mean 2 -> zero between-var
    y_pred = np.array([[1.5], [2.5], [1.0], [3.0]])
    cr = compute_config_resolved(y_true, y_pred, config_names, ["CF_x"])
    assert np.isnan(cr["CF_x"]["config_mean_r2"])  # sentinel, not 0/0


def test_config_resolved_single_config():
    """A single holdout config has no between-config variance -> R² sentinel, fraction 1.0."""
    config_names = np.array(["A", "A", "A"])
    y_true = np.array([[1.0], [2.0], [3.0]])
    y_pred = np.array([[1.1], [2.1], [2.9]])
    cr = compute_config_resolved(y_true, y_pred, config_names, ["CF_x"])
    assert np.isnan(cr["CF_x"]["config_mean_r2"])
    assert cr["CF_x"]["within_config_variance_fraction"] == pytest.approx(1.0)


def test_config_mean_r2_keeps_honest_negative_for_near_zero_signal():
    """The scale-relative guard does NOT null a tiny-but-real between-config signal (CF_y-like)."""
    # per-config cycle-means -0.02 / 0.01 / 0.04 — a small but genuine between-config spread
    config_names = np.array(["A", "A", "B", "B", "C", "C"])
    y_true = np.array([[-0.03], [-0.01], [0.00], [0.02], [0.03], [0.05]])
    y_pred = y_true + 0.05  # biased -> worse than predicting the mean
    cr = compute_config_resolved(y_true, y_pred, config_names, ["CF_y"])
    r2 = cr["CF_y"]["config_mean_r2"]
    assert np.isfinite(r2) and r2 < 0  # honest negative, not sentinel-nulled


def test_filter_converged_beat_report_holdout_flags_dropped():
    """A holdout config with no converged beat is reported; others survive."""
    df = _toy_dataset()
    victim = "s35_f085_p45"
    df2 = df[~((df["config_name"] == victim) & (df["wingbeat"] == 1))]
    filtered, dropped = filter_converged_beat_report_holdout(df2)
    assert dropped == [victim]
    assert (filtered["wingbeat"] >= 1).all()
    assert victim not in set(
        filtered.loc[filtered["split"] == "holdout", "config_name"]
    )


def test_run_training_raises_clearly_when_all_holdout_startup_only(tmp_path):
    """All holdout configs lacking a converged beat -> clear error (not 'no holdout label')."""
    df = _toy_dataset()
    df = df[
        ~((df["split"] == "holdout") & (df["wingbeat"] == 1))
    ]  # holdout = startup only
    pq = tmp_path / "ds.parquet"
    df.to_parquet(pq, index=False)
    with pytest.raises(ValueError, match="no converged-beat"):
        run_training(
            pq,
            tmp_path / "out",
            docker_image_digest=DIGEST,
            timestamp=TIMESTAMP,
            device="cpu",
        )
    assert (
        "torch" not in sys.modules
    )  # raised before the lazy torch import (CPU-reachable)


def test_metrics_json_has_config_resolved(tmp_path):
    """Scenario: config_resolved block is present per target."""
    holdout, y_true, y_pred = _holdout_arrays()
    metrics = build_metrics(
        y_true,
        y_pred,
        holdout,
        inference=_placeholder_inference(),
        reproducibility=_reproducibility(),
    )
    path = tmp_path / "metrics.json"
    write_json(path, metrics)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert set(loaded["config_resolved"]) == set(TARGET_COLUMNS)
    for block in loaded["config_resolved"].values():
        assert set(block) == {"config_mean_r2", "within_config_variance_fraction"}


def test_standardizer_near_zero_variance_floored():
    """A near-zero-variance column is floored (no astronomically-scaled feature)."""
    y = np.column_stack([np.linspace(0, 1, 8), 5.0 + 1e-14 * np.arange(8)])
    z = Standardizer().fit(y).transform(y)
    assert np.isfinite(z).all()
    assert np.abs(z[:, 1]).max() < 1.0  # not blown up by a tiny std


# --- Phase 5: lazy-import guard ----------------------------------------------------------


def test_pure_helpers_import_without_torch():
    """Scenario: Module imports without the training dependency-group.

    Run in a fresh subprocess with ``torch``/``physicsnemo`` barred (``sys.modules[...] =
    None`` makes any ``import torch`` raise ``ImportError``). The five pure helpers must import
    and run without triggering a torch/physicsnemo import — robust, unlike an in-process
    ``assert 'torch' not in sys.modules`` that the CI suite passes only incidentally.
    """
    code = (
        "import sys\n"
        "sys.modules['torch'] = None\n"
        "sys.modules['physicsnemo'] = None\n"
        "import numpy as np, pandas as pd\n"
        "from mosquito_cfd.force_surrogate.train import ("
        " build_features, filter_converged_beat, make_config_splits, Standardizer,"
        " compute_metrics, FEATURE_COLUMNS, TARGET_COLUMNS)\n"
        "df = pd.DataFrame({'config_name':['a','a','b','b','c','c'],"
        " 'split':['train','train','train','train','holdout','holdout'],"
        " 'wingbeat':[0,1,0,1,0,1],'phase':[0.1,0.2,0.3,0.4,0.5,0.6],"
        " 'stroke_amp_deg':[45.0]*6,'frequency_fstar':[1.0]*6,'pitch_amp_deg':[45.0]*6})\n"
        "x,_ = build_features(df); filter_converged_beat(df)\n"
        "Standardizer().fit(x).transform(x)\n"
        "compute_metrics(np.zeros((2,1)), np.zeros((2,1)), ['CF_x'])\n"
        "assert 'torch' not in sys.modules or sys.modules['torch'] is None\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 0, f"stderr:\n{result.stderr}"
    assert "OK" in result.stdout


# --- Phase 6: evaluation, artifacts, provenance, wandb (CPU tier) -------------------------

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TIMESTAMP = "2026-06-18T12:00:00Z"


def _holdout_arrays():
    """A holdout slice (converged beat) + aligned true/pred coefficient arrays."""
    df = filter_converged_beat(_toy_dataset())
    holdout = df[df["split"] == "holdout"].reset_index(drop=True)
    y_true = holdout[TARGET_COLUMNS].to_numpy(dtype=float)
    rng = np.random.default_rng(0)
    y_pred = y_true + 0.01 * rng.standard_normal(y_true.shape)
    return holdout, y_true, y_pred


def _placeholder_inference():
    return {"latency_ms": 0.5, "throughput_rows_per_s": 2.0e6, "basis": "placeholder"}


def _reproducibility():
    return {
        "seeds": {"global": 1234},
        "features": list(FEATURE_COLUMNS),
        "bitwise": "cpu_only",
    }


def test_predictions_frame_schema_and_membership():
    """Scenario: Predictions parquet schema (+ holdout-only membership)."""
    holdout, y_true, y_pred = _holdout_arrays()
    frame = build_predictions_frame(holdout, y_true, y_pred)
    expected = ["config_name", "time", "phase", "wingbeat"]
    for c in TARGET_COLUMNS:
        expected += [f"{c}_true", f"{c}_pred"]
    assert list(frame.columns) == expected
    assert len(frame) == len(holdout)
    # every config_name is one of the holdout configs (no train/val leak)
    assert set(frame["config_name"]) <= set(HOLDOUT_CONFIGS)
    np.testing.assert_allclose(frame["CF_x_true"], holdout["CF_x"])


def test_metrics_json_keys_round_trip(tmp_path):
    """Scenario: metrics.json carries per-target/aggregate/per-config/inference/reproducibility."""
    holdout, y_true, y_pred = _holdout_arrays()
    metrics = build_metrics(
        y_true,
        y_pred,
        holdout,
        inference=_placeholder_inference(),
        reproducibility=_reproducibility(),
    )
    path = tmp_path / "metrics.json"
    write_json(path, metrics)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert set(loaded["per_target"]) == set(TARGET_COLUMNS)
    for t in loaded["per_target"].values():
        assert set(t) == {"rmse", "mae", "r2"}
    assert "rmse" in loaded["aggregate"]
    assert set(loaded["per_config"]) <= set(HOLDOUT_CONFIGS)
    assert "latency_ms" in loaded["inference"]
    assert "throughput_rows_per_s" in loaded["inference"]
    assert loaded["reproducibility"]["bitwise"] == "cpu_only"
    # the constant CF_y sentinel R² serialized as JSON null
    assert loaded["per_target"]["CF_y"]["r2"] is None


def test_evaluation_uses_only_holdout(tmp_path):
    """Scenario: Evaluation uses only holdout configurations."""
    holdout, y_true, y_pred = _holdout_arrays()
    assert (holdout["split"] == "holdout").all()
    assert (holdout["wingbeat"] >= 1).all()
    metrics = build_metrics(
        y_true,
        y_pred,
        holdout,
        inference=_placeholder_inference(),
        reproducibility=_reproducibility(),
    )
    assert set(metrics["per_config"]) <= set(HOLDOUT_CONFIGS)


def test_provenance_cpu_tier_digest_timestamp_seeds(tmp_path):
    """Scenario: Provenance records digest, timestamp, and seeds (CI tier, no train group)."""
    meta = build_training_metadata(
        docker_image_digest=DIGEST,
        timestamp=TIMESTAMP,
        seeds={"global": 1234},
        feature_names=list(FEATURE_COLUMNS),
    )
    assert meta["docker_image"] == DIGEST
    assert meta["timestamp"] == TIMESTAMP
    assert meta["seeds"] == {"global": 1234}
    assert "git" in meta
    # versions are absent/null on the CI tier (torch/physicsnemo not installed)
    assert meta["library_versions"]["torch"] is None
    assert meta["library_versions"]["physicsnemo"] is None


def test_provenance_rejects_mutable_tag():
    """Scenario: Mutable image tag rejected."""
    with pytest.raises(ValueError):
        build_training_metadata(
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TIMESTAMP,
            seeds={"global": 1},
            feature_names=list(FEATURE_COLUMNS),
        )


def test_torch_free_helpers_bitwise_reproducible():
    """Scenario: Torch-free CPU helpers are bitwise-reproducible (CI tier)."""

    def run():
        df = filter_converged_beat(_toy_dataset(seed=5))
        x, _ = build_features(df)
        z = Standardizer().fit(x).transform(x)
        sp = make_config_splits(df, seed=11)
        m = compute_metrics(
            df[TARGET_COLUMNS].to_numpy(float),
            df[TARGET_COLUMNS].to_numpy(float),
            TARGET_COLUMNS,
        )
        return z, sp, m

    z1, sp1, m1 = run()
    z2, sp2, m2 = run()
    assert np.array_equal(z1, z2)
    assert sp1 == sp2
    # Compare metrics via deterministic JSON (NaN R² sentinels are stable, and NaN != NaN
    # would otherwise break dict equality) — the values are bitwise-identical run to run.
    assert json.dumps(m1) == json.dumps(m2)


def test_wandb_disabled_is_noop_without_import():
    """Scenario: wandb is disabled by default without importing wandb."""
    saved = sys.modules.get("wandb", "absent")
    sys.modules["wandb"] = None  # bar the import: any `import wandb` raises ImportError
    try:
        # disabled mode must not import wandb and must not raise
        log_to_wandb("disabled", project="p", run_config={}, metrics={"a": 1.0})
    finally:
        if saved == "absent":
            sys.modules.pop("wandb", None)
        else:
            sys.modules["wandb"] = saved


def test_wandb_online_failure_does_not_raise():
    """Scenario: wandb online failure does not block metrics.json."""
    saved = sys.modules.get("wandb", "absent")
    sys.modules["wandb"] = (
        None  # online path: import wandb -> ImportError, handled gracefully
    )
    try:
        log_to_wandb(
            "online", project="p", run_config={}, metrics={"a": 1.0}
        )  # no raise
    finally:
        if saved == "absent":
            sys.modules.pop("wandb", None)
        else:
            sys.modules["wandb"] = saved


def test_force_only_guard_no_field_path():
    """Scenario: Training consumes only the dataset parquet."""
    import inspect

    from mosquito_cfd.force_surrogate.train import run_training

    params = set(inspect.signature(run_training).parameters)
    for forbidden in ("plotfile", "field", "fields", "plot_file", "velocity"):
        assert forbidden not in params
    assert "dataset_path" in params
