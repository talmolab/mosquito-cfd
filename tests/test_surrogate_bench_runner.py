"""The bench runner (add-surrogate-comparison-bench, 7b; CPU tier, torch-free).

fit_seed and predict_frame are replaced at the runner's import site by recorders, and a small
synthetic 27-configuration corpus stands in for the fine one. Covers the runner clauses of
"Bench model entries and metrics", "Summary carries scope and provenance", "Late-beat boundary"
(the 4-beat entries), "The reference is never a checkpoint" (the runner path) and the runner's
refusals.
"""

from __future__ import annotations

import inspect
import itertools
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS
from mosquito_cfd.surrogate_bench import BENCH_SCOPE, BENCH_SEEDS, metrics, runner
from mosquito_cfd.surrogate_bench.splits import build_splits, carve_split

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TIMESTAMP = "2026-11-22T12:00:00Z"
GIT = {
    "commit": "c" * 40,
    "branch": "add-surrogate-comparison-bench-results",
    "dirty": False,
}
HARDWARE = {"hostname": "test-host", "gpus": [], "gpu_count": 0}
HOLDOUTS = {
    "s35_f085_p45",
    "s45_f085_p60",
    "s45_f100_p60",
    "s45_f115_p60",
    "s55_f085_p45",
    "s55_f115_p45",
}
FILES = {
    "results.parquet",
    "splits.json",
    "summary.json",
    "bench_summary.png",
    "run_metadata.json",
}


def synthetic_corpus(n_beats=2, n_phase=128, scale=1.0):
    """27 configurations on the 3 × 3 × 3 grid, labelled 21 train + 6 holdout."""
    rows = []
    phase = np.arange(n_phase) / n_phase
    for s, f, p in itertools.product((35, 45, 55), (0.85, 1.0, 1.15), (30, 45, 60)):
        name = f"s{s}_f{round(f * 100):03d}_p{p}"
        for beat in range(n_beats):
            frame = pd.DataFrame(
                {
                    "config_name": name,
                    "time": (beat + phase) / f,
                    "phase": phase,
                    "wingbeat": beat,
                    "split": "holdout" if name in HOLDOUTS else "train",
                    "stroke_amp_deg": float(s),
                    "frequency_fstar": float(f),
                    "pitch_amp_deg": float(p),
                }
            )
            for j, t in enumerate(TARGET_COLUMNS):
                frame[t] = scale * (
                    (1 + 0.01 * s + j) * np.sin(2 * np.pi * phase + 0.1 * j)
                    + 0.2 * f * np.cos(4 * np.pi * phase)
                    + 0.005 * p
                    + 0.01 * beat
                )
            rows.append(frame)
    return pd.concat(rows, ignore_index=True)


class _FakeModel:
    def parameters(self):
        return [np.zeros((3, 4)), np.zeros(5)]


class Recorder:
    """fit_seed / predict_frame stand-ins that record their calls."""

    def __init__(self, log=None):
        self.fits = []
        self.log = log if log is not None else []

    def fit_seed(
        self,
        df,
        split,
        *,
        seed,
        phase_harmonics,
        epochs,
        hidden,
        num_layers,
        lr,
        device,
    ):
        self.log.append("fit")
        self.fits.append(
            dict(
                frame=df,
                split=split,
                seed=seed,
                phase_harmonics=phase_harmonics,
                epochs=epochs,
                hidden=hidden,
                num_layers=num_layers,
                lr=lr,
                device=device,
            )
        )
        n_test = int(df["config_name"].isin(split.test_configs).sum())
        y_pred = df.loc[df["config_name"].isin(split.test_configs), TARGET_COLUMNS]
        y_pred = y_pred.to_numpy() + 0.001 * (seed - 1230) + 0.01 * phase_harmonics
        assert y_pred.shape == (n_test, 6)
        return SimpleNamespace(split=split, model=_FakeModel(), y_pred=y_pred)

    def predict_frame(self, fit, frame, *, device="cpu"):
        return np.full((len(frame), 6), 0.25)


def _run(tmp_path, monkeypatch, *, frame=None, coarse=None, name="out", **kwargs):
    rec = kwargs.pop("recorder", None) or Recorder()
    monkeypatch.setattr(runner, "fit_seed", rec.fit_seed)
    monkeypatch.setattr(runner, "predict_frame", rec.predict_frame)
    frame = synthetic_corpus() if frame is None else frame
    coarse = synthetic_corpus(scale=1.1) if coarse is None else coarse
    out = tmp_path / name
    params = dict(
        frame=frame,
        coarse_frame=coarse,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TIMESTAMP,
        dataset_sha256="d" * 64,
        git_state=GIT,
        hardware=HARDWARE,
        epochs=7,
    )
    params.update(kwargs)
    result = runner.run_bench(**params)
    return rec, out, result


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    try:
        yield _run(tmp_path_factory.mktemp("bench"), mp)
    finally:
        mp.undo()


# --- Hyperparameters, order, frames ----------------------------------------------------------


def test_the_shipped_hyperparameters_reach_fit_seed(full_run):
    rec, _, _ = full_run
    assert len(rec.fits) == 14 * 2 * len(BENCH_SEEDS)
    assert {(f["hidden"], f["num_layers"], f["lr"], f["epochs"]) for f in rec.fits} == {
        (64, 3, 1e-3, 7)
    }
    assert {f["phase_harmonics"] for f in rec.fits} == {1, 3}
    assert sorted({f["seed"] for f in rec.fits}) == list(BENCH_SEEDS)


def test_mlp_h1_on_interpolation_runs_first_on_the_full_target_beat_frame(full_run):
    rec, _, _ = full_run
    frame = synthetic_corpus()
    target = metrics.target_beat_frame(frame)
    first = rec.fits[0]
    assert first["phase_harmonics"] == 1 and first["seed"] == BENCH_SEEDS[0]
    assert np.array_equal(
        first["frame"]["config_name"].to_numpy(), target["config_name"].to_numpy()
    )
    assert np.array_equal(
        first["frame"]["phase"].to_numpy(), target["phase"].to_numpy()
    )
    interp = build_splits(target)["interpolation"]
    assert first["split"] == carve_split(interp, seed=BENCH_SEEDS[0])


def test_mlp_skill_uses_the_fits_own_predictions(full_run):
    _, out, _ = full_run
    results = pd.read_parquet(out / "results.parquet")
    row = results[
        (results["entry"] == "mlp_h1")
        & (results["split"] == "interpolation")
        & (results["seed"] == 1234)
        & (results["target"] == "CF_x")
        & (results["config_name"] == "s35_f085_p45")
    ].iloc[0]
    offset = 0.001 * (1234 - 1230) + 0.01
    assert row["sse"] == pytest.approx(row["n_rows"] * offset**2, rel=1e-9)


def test_both_ridge_entries_run_on_every_split(full_run):
    _, out, _ = full_run
    results = pd.read_parquet(out / "results.parquet")
    for entry in ("ridge", "ridge_fixed"):
        assert set(results.loc[results["entry"] == entry, "split"]) == set(
            build_splits(metrics.target_beat_frame(synthetic_corpus()))
        )
        assert set(results.loc[results["entry"] == entry, "seed"]) == {0}


# --- Artifacts, scope, provenance -----------------------------------------------------------


def test_exactly_the_five_artifacts_are_written(full_run):
    _, out, _ = full_run
    assert {p.name for p in out.iterdir()} == FILES


def test_results_schema(full_run):
    _, out, _ = full_run
    results = pd.read_parquet(out / "results.parquet")
    assert set(runner.RESULT_COLUMNS) <= set(results.columns)
    assert results["peak_gpu_mem"].isna().all()  # CPU run and ridge rows: null
    mlp = results[results["entry"].str.startswith("mlp_")]
    assert (mlp["n_params"] == 17).all()


def test_the_summary_recomputes_from_results(full_run):
    _, out, _ = full_run
    results = pd.read_parquet(out / "results.parquet")
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    recomputed = metrics.pooled(results)
    stored = pd.DataFrame(summary["pooled"])
    merged = recomputed.merge(stored, on=["entry", "split", "seed", "target"])
    assert len(merged) == len(recomputed) == len(stored)
    for col in (
        "skill",
        "rmse_frac_component_peak",
        "baseline_rmse_frac_component_peak",
    ):
        np.testing.assert_allclose(merged[f"{col}_x"], merged[f"{col}_y"], rtol=1e-12)


def test_scope_holdout_status_and_gate(full_run):
    _, out, _ = full_run
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["scope"] == BENCH_SCOPE
    status = summary["holdout_status"]
    assert status["mlp_h1"]["holdout_informed"] == "unverified"
    for entry in ("mlp_h3", "ridge_fixed", "ridge"):
        assert status[entry]["holdout_informed"] is True
    assert "weakly" in status["ridge"]["holdout_reason"]
    gate = summary["gate"]
    assert gate["provisional"] is True and len(gate["reasons"]) == 7
    assert set(gate["entries"]) == {"mlp_h1", "mlp_h3", "ridge", "ridge_fixed"}
    for entry in gate["entries"]:
        assert (
            gate["entries"][entry]["holdout_informed"]
            == status[entry]["holdout_informed"]
        )
    assert summary["holdout_overlap"]["interpolation"] == 6
    assert "face:pitch_amp_deg=30" in summary["like_for_like"]


def test_provenance_fields(tmp_path, monkeypatch):
    monkeypatch.delenv("CUBLAS_WORKSPACE_CONFIG", raising=False)
    _, out, _ = _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["docker_image"] == DIGEST
    assert meta["timestamp"] == TIMESTAMP
    assert meta["inputs"]["dataset_sha256"] == "d" * 64
    assert meta["git"] == GIT
    assert meta["hardware"] == HARDWARE
    assert meta["seeds"] == list(BENCH_SEEDS)
    assert (
        meta["device"] == "cpu"
        and meta["entries"] == ["ridge_fixed"]
        and meta["epochs"] == 7
    )
    assert meta["cublas_workspace_config"] is None
    versions = meta["library_versions"]
    assert versions["numpy"] == np.__version__
    assert "torch" in versions and "physicsnemo" in versions


# --- Memory probe ------------------------------------------------------------------------------


class FakeCuda:
    def __init__(self, log):
        self.log = log
        self.allocated = [100, 160]

    def synchronize(self, *a):
        self.log.append("synchronize")

    def reset_peak_memory_stats(self, *a):
        self.log.append("reset")

    def memory_allocated(self, *a):
        self.log.append("base")
        return 100

    def max_memory_allocated(self, *a):
        self.log.append("peak")
        return 1100


def test_the_memory_probe_brackets_each_fit(tmp_path, monkeypatch):
    log = []
    rec = Recorder(log=log)
    _, out, _ = _run(
        tmp_path,
        monkeypatch,
        recorder=rec,
        entries=("mlp_h1", "ridge_fixed"),
        device="cuda",
        memory_probe=FakeCuda(log),
    )
    assert log[:6] == ["synchronize", "reset", "base", "fit", "synchronize", "peak"]
    results = pd.read_parquet(out / "results.parquet")
    assert (results.loc[results["entry"] == "mlp_h1", "peak_gpu_mem"] == 1000).all()
    assert results.loc[results["entry"] == "ridge_fixed", "peak_gpu_mem"].isna().all()


# --- A diverged seed ---------------------------------------------------------------------------


class DivergedSeed(Recorder):
    """Seed 1236 predicts NaN on the grid and at the test rows; every other seed is finite."""

    BAD = 1236

    def fit_seed(self, df, split, *, seed, **kwargs):
        fit = super().fit_seed(df, split, seed=seed, **kwargs)
        if seed == self.BAD:
            fit.y_pred = np.full_like(fit.y_pred, np.nan)
        fit.seed = seed
        return fit

    def predict_frame(self, fit, frame, *, device="cpu"):
        value = np.nan if fit.seed == self.BAD else 0.25
        return np.full((len(frame), 6), value)


def test_a_diverged_seed_gives_outside_null_verdicts_not_a_crash(tmp_path, monkeypatch):
    """Spec "Gate boundaries": four finite seeds plus one NaN seed give outside, null margin."""
    _, out, _ = _run(
        tmp_path, monkeypatch, recorder=DivergedSeed(), entries=("mlp_h1",)
    )
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    comps = summary["gate"]["entries"]["mlp_h1"]["components"]
    judged = 0
    for comp, verdicts in comps.items():
        for name, v in verdicts.items():
            if "yardstick" not in v:
                continue
            judged += 1
            assert v["verdict"] == "outside" and v["margin"] is None, (comp, name)
            assert "NaN" in v["reason"], (comp, name)
    assert judged > 0
    # The seed ranges skip the NaN seed; the per-seed record keeps it as null.
    skills = summary["per_seed_skill"]["mlp_h1"]["interpolation"]
    assert all(v is None for v in skills[str(DivergedSeed.BAD)].values())
    assert all(
        v is not None for s, d in skills.items() if s != "1236" for v in d.values()
    )


# --- Four beats ------------------------------------------------------------------------------


def test_a_four_beat_corpus_trains_and_scores_on_the_last_beat(tmp_path, monkeypatch):
    seen = []
    real = metrics.split_baseline

    def spy(target_frame, train_configs, targets):
        seen.append(set(target_frame["wingbeat"].unique()))
        return real(target_frame, train_configs, targets)

    monkeypatch.setattr(metrics, "split_baseline", spy)
    rec, out, _ = _run(
        tmp_path,
        monkeypatch,
        frame=synthetic_corpus(n_beats=4),
        coarse=synthetic_corpus(n_beats=2, scale=1.1),
        entries=("mlp_h1", "ridge_fixed"),
    )
    assert {w for f in rec.fits for w in f["frame"]["wingbeat"].unique()} == {3}
    assert seen and all(s == {3} for s in seen)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    comps = summary["gate"]["entries"]["mlp_h1"]["components"]
    assert comps["CF_x"]["beat1_vs_beat2"]["verdict"] in {"inside", "outside"}
    assert comps["CF_x"]["late_beat"]["verdict"] in {"inside", "outside"}
    assert comps["CF_x"]["coarse_vs_fine"] == {
        "verdict": "unavailable",
        "reason": "coarse corpus lacks target beat 3",
    }


# --- The ridge path never touches checkpoints; refusals ---------------------------------------


def test_the_runner_ridge_path_names_no_model_io():
    source = inspect.getsource(runner.run_ridge_entry)
    for name in ("torch", "save(", "load(", "pickle", "load_surrogate"):
        assert name not in source


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        (dict(git_state=dict(GIT, dirty=True)), "dirty"),
        (dict(entries=("mlp_h1", "nope")), "nope"),
        (dict(entries=("ridge", "ridge")), "ridge"),
        (dict(epochs=0), "epochs"),
        (dict(epochs=True), "epochs"),
        (dict(epochs=1.5), "epochs"),
        (dict(entries=()), "no entries"),
        (dict(git_state={"commit": "c" * 40}), "dirty"),
        (dict(git_state=dict(GIT, dirty=None)), "dirty"),
        (dict(timestamp=""), "timestamp"),
        (dict(device="bogus"), "device"),
        (dict(extra_inputs={"dataset_sha256": "e" * 64}), "override"),
        (
            dict(docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest"),
            "digest|pinned|sha256",
        ),
    ],
)
def test_refusals_happen_before_any_write(tmp_path, monkeypatch, kwargs, match):
    with pytest.raises(ValueError, match=match):
        _run(tmp_path, monkeypatch, **kwargs)
    assert not (tmp_path / "out").exists()


def test_a_dirty_tree_is_allowed_with_allow_dirty(tmp_path, monkeypatch):
    _, out, _ = _run(
        tmp_path,
        monkeypatch,
        git_state=dict(GIT, dirty=True),
        allow_dirty=True,
        entries=("ridge_fixed",),
    )
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["git"]["dirty"] is True


def test_a_non_empty_out_dir_is_refused_and_left_unchanged(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_bytes(b"precious")
    with pytest.raises(ValueError, match="not empty"):
        _run(tmp_path, monkeypatch)
    assert [p.name for p in out.iterdir()] == ["keep.txt"]
    assert (out / "keep.txt").read_bytes() == b"precious"


def test_a_coarse_corpus_missing_a_configuration_is_refused(tmp_path, monkeypatch):
    coarse = synthetic_corpus(scale=1.1)
    coarse = coarse[coarse["config_name"] != "s45_f100_p45"]
    with pytest.raises(ValueError, match="s45_f100_p45"):
        _run(tmp_path, monkeypatch, coarse=coarse)
    assert not (tmp_path / "out").exists()


def test_an_unknown_git_state_with_allow_dirty_is_recorded_dirty(tmp_path, monkeypatch):
    _, out, _ = _run(
        tmp_path,
        monkeypatch,
        git_state={"error": "git not available or not a repository"},
        allow_dirty=True,
        entries=("ridge_fixed",),
    )
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["git"]["dirty"] is True
    assert meta["git"]["error"] == "git not available or not a repository"


def test_a_data_only_failure_is_raised_before_any_fit(tmp_path, monkeypatch):
    """A bad startup-beat value of a gated configuration fails before the first fit."""
    frame = synthetic_corpus()
    bad = frame.index[
        (frame["config_name"] == "s35_f085_p45") & (frame["wingbeat"] == 0)
    ][3]
    frame.loc[bad, "CF_x"] = np.nan
    log = []
    with pytest.raises(ValueError, match="s35_f085_p45"):
        _run(tmp_path, monkeypatch, frame=frame, recorder=Recorder(log=log))
    assert log == []
    assert not (tmp_path / "out").exists()


def test_each_split_baseline_is_built_once_per_phase_array(tmp_path, monkeypatch):
    """One definition build plus the test-row and grid evaluations: 3 per split, not per seed."""
    calls = []
    real = metrics.build_phase_only_baseline

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(metrics, "build_phase_only_baseline", spy)
    _run(tmp_path, monkeypatch, entries=("mlp_h1", "ridge_fixed"))
    assert len(calls) == 3 * 14


# --- Wiring: grid predictions, per-seed skill, splits.json, CUBLAS, ridge_fixed ---------------


class GridRecorder(Recorder):
    """Records every frame predict_frame is given."""

    def __init__(self):
        super().__init__()
        self.frames = []

    def predict_frame(self, fit, frame, *, device="cpu"):
        self.frames.append(frame)
        return super().predict_frame(fit, frame, device=device)


def test_grid_sse_comes_from_predict_frame_on_the_grid(tmp_path, monkeypatch):
    rec = GridRecorder()
    _, out, _ = _run(tmp_path, monkeypatch, recorder=rec, entries=("mlp_h1",))
    target = metrics.target_beat_frame(synthetic_corpus())
    interp = build_splits(target)["interpolation"]
    expected_grid = metrics.grid_frame(target, sorted(interp.test))
    first = rec.frames[0]
    assert list(first["config_name"]) == list(expected_grid["config_name"])
    assert np.array_equal(first["phase"].to_numpy(), expected_grid["phase"].to_numpy())
    results = pd.read_parquet(out / "results.parquet")
    truth = metrics.grid_truth(target, list(TARGET_COLUMNS))
    row = results[
        (results["split"] == "interpolation")
        & (results["seed"] == BENCH_SEEDS[0])
        & (results["target"] == "CF_z")
        & (results["config_name"] == "s45_f100_p60")
    ].iloc[0]
    j = list(TARGET_COLUMNS).index("CF_z")
    expected = float(((truth["s45_f100_p60"][:, j] - 0.25) ** 2).sum())
    assert row["grid_sse"] == pytest.approx(expected, rel=1e-12)


def test_the_summary_per_seed_skill_is_the_fits_own_skill(full_run):
    rec, out, _ = full_run
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    target = metrics.target_beat_frame(synthetic_corpus())
    split = build_splits(target)["face:pitch_amp_deg=60"]
    baseline = metrics.split_baseline(target, split.train, list(TARGET_COLUMNS))
    fit = next(
        f
        for f in rec.fits
        if f["phase_harmonics"] == 3
        and f["seed"] == BENCH_SEEDS[2]
        and f["split"] == carve_split(split, seed=BENCH_SEEDS[2])
    )
    test = fit["frame"]["config_name"].isin(split.test)
    y_pred = fit["frame"].loc[test, TARGET_COLUMNS].to_numpy() + (
        0.001 * (BENCH_SEEDS[2] - 1230) + 0.03
    )
    expected = metrics.per_seed_skill(
        target, split.test, y_pred, baseline, list(TARGET_COLUMNS)
    )
    got = summary["per_seed_skill"]["mlp_h3"]["face:pitch_amp_deg=60"][
        str(BENCH_SEEDS[2])
    ]
    assert got == pytest.approx(expected, rel=1e-12)


def test_splits_json_holds_train_test_and_each_seeds_validation(full_run):
    _, out, _ = full_run
    written = json.loads((out / "splits.json").read_text(encoding="utf-8"))
    splits = build_splits(metrics.target_beat_frame(synthetic_corpus()))
    assert list(written) == list(splits)
    for name, split in splits.items():
        assert written[name]["train"] == list(split.train)
        assert written[name]["test"] == list(split.test)
        assert written[name]["validation"] == {
            str(s): carve_split(split, seed=s).val_configs for s in BENCH_SEEDS
        }


def test_a_set_cublas_workspace_config_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    _, out, _ = _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["cublas_workspace_config"] == ":4096:8"


def test_ridge_fixed_records_no_selection_and_ridge_does(full_run):
    _, out, _ = full_run
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    for name, record in summary["ridge"]["ridge_fixed"].items():
        assert record["selection"] is None, name
        assert record["point"] == [16, 3, 1e-6], name
    for name, record in summary["ridge"]["ridge"].items():
        assert record["selection"]["chosen"] == record["point"], name
