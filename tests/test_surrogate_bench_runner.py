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
import os
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


# The six entries in run order, and each MLP entry's (hidden, num_layers, phase_harmonics).
# Literals on purpose: the tests must not read them back from the runner.
ALL_ENTRIES = [
    "mlp_h1",
    "mlp_h3",
    "mlp_w256d5",
    "mlp_w256d5_h3",
    "ridge",
    "ridge_fixed",
]
ARCHITECTURES = {
    "mlp_h1": (64, 3, 1),
    "mlp_h3": (64, 3, 3),
    "mlp_w256d5": (256, 5, 1),
    "mlp_w256d5_h3": (256, 5, 3),
}
MLP_ENTRIES = list(ARCHITECTURES)
N_SPLITS = 14
FITS_PER_ENTRY = N_SPLITS * len(BENCH_SEEDS)
UNTIMED = [
    c
    for c in runner.RESULT_COLUMNS
    if c not in ("fit_seconds", "inference_seconds_per_row", "peak_gpu_mem")
]


class _FakeModel:
    def __init__(self, n_bias=5):
        self.n_bias = n_bias

    def parameters(self):
        return [np.zeros((3, 4)), np.zeros(self.n_bias)]


class Recorder:
    """fit_seed / predict_frame stand-ins that record their calls.

    The recorder is never told an entry's name. Its predictions depend only on the seed and
    the harmonic count, so entries of different size are indistinguishable; see SizedRecorder.
    """

    def __init__(self, log=None):
        self.fits = []
        self.log = log if log is not None else []

    @staticmethod
    def offset(seed, phase_harmonics, hidden, num_layers):
        return 0.001 * (seed - 1230) + 0.01 * phase_harmonics

    @staticmethod
    def n_params(hidden, num_layers):
        return 17

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
        y_pred = y_pred.to_numpy() + self.offset(
            seed, phase_harmonics, hidden, num_layers
        )
        assert y_pred.shape == (n_test, 6)
        model = _FakeModel(n_bias=self.n_params(hidden, num_layers) - 12)
        return SimpleNamespace(split=split, model=model, y_pred=y_pred)

    def predict_frame(self, fit, frame, *, device="cpu"):
        return np.full((len(frame), 6), 0.25)


class SizedRecorder(Recorder):
    """Predictions and the parameter count also depend on width and depth.

    At the shipped size (64, 3) both equal the plain Recorder's, so every entry's rows are
    distinguishable from every other's without changing the shipped-size expectations. The
    depth coefficient is far below the seed's (1e-3), so a mutant that changes depth and seed
    together cannot land on another real offset; the test checks the realised offsets differ.
    """

    @staticmethod
    def offset(seed, phase_harmonics, hidden, num_layers):
        return (
            Recorder.offset(seed, phase_harmonics, hidden, num_layers)
            + 1e-4 * (hidden - 64)
            + 1e-5 * (num_layers - 3)
        )

    @staticmethod
    def n_params(hidden, num_layers):
        return 17 + (hidden - 64) + (num_layers - 3)


def fits_by_entry(rec, chosen_mlp=MLP_ENTRIES):
    """Assign the recorded calls to entries by position in the run order.

    Calls arrive entry by entry, 14 splits × 5 seeds each, so call ``k`` belongs to the
    ``k // 70``-th chosen MLP entry. Grouping by the hyperparameters themselves would be
    circular: it could not see a fit run under the wrong entry's name.
    """
    assert len(rec.fits) == FITS_PER_ENTRY * len(chosen_mlp)
    return {
        entry: rec.fits[k * FITS_PER_ENTRY : (k + 1) * FITS_PER_ENTRY]
        for k, entry in enumerate(chosen_mlp)
    }


def _run(tmp_path, monkeypatch, *, frame=None, coarse=None, name="out", **kwargs):
    rec = kwargs.pop("recorder", None) or SizedRecorder()
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
    """Spec "The larger MLP entries change only width and depth", the call clauses."""
    rec, _, _ = full_run
    assert len(rec.fits) == 14 * 4 * len(BENCH_SEEDS)
    target = metrics.target_beat_frame(synthetic_corpus())
    splits = build_splits(target)
    for entry, fits in fits_by_entry(rec).items():
        assert {(f["hidden"], f["num_layers"], f["phase_harmonics"]) for f in fits} == {
            ARCHITECTURES[entry]
        }, entry
        # The shipped learning rate (a literal, not the runner's table) and the run's epochs.
        assert {(f["lr"], f["epochs"]) for f in fits} == {(1e-3, 7)}, entry
        # 5 calls per split, one per seed, in split order.
        expected = [
            (carve_split(split, seed=seed), seed)
            for split in splits.values()
            for seed in BENCH_SEEDS
        ]
        assert [(f["split"], f["seed"]) for f in fits] == expected, entry


def test_each_mlp_entrys_rows_carry_its_own_fits(full_run):
    """A fit run under another entry's name would file that entry's predictions here.

    Every row of every MLP entry, on every split and seed, carries that entry's own offset.
    """
    _, out, _ = full_run
    results = pd.read_parquet(out / "results.parquet")
    for entry, (hidden, num_layers, harmonics) in ARCHITECTURES.items():
        rows = results[results["entry"] == entry]
        assert len(rows) > 0 and set(rows["split"]) == set(
            build_splits(metrics.target_beat_frame(synthetic_corpus()))
        ), entry
        assert set(rows["seed"]) == set(BENCH_SEEDS), entry
        # Every (split, seed) block is present, not only every split and every seed.
        assert len(rows.groupby(["split", "seed"]).size()) == N_SPLITS * len(
            BENCH_SEEDS
        )
        offset = rows["seed"].map(
            lambda s, h=harmonics, w=hidden, d=num_layers: SizedRecorder.offset(
                s, h, w, d
            )
        )
        np.testing.assert_allclose(
            rows["sse"].to_numpy(),
            (rows["n_rows"] * offset**2).to_numpy(),
            rtol=1e-9,
            err_msg=entry,
        )
        assert set(rows["n_params"]) == {SizedRecorder.n_params(hidden, num_layers)}
    # No two (entry, seed) pairs share an offset, so the check above bites on every row.
    offsets = {
        round(SizedRecorder.offset(s, h, w, d), 12)
        for w, d, h in ARCHITECTURES.values()
        for s in BENCH_SEEDS
    }
    assert len(offsets) == len(ARCHITECTURES) * len(BENCH_SEEDS)
    assert SizedRecorder.n_params(256, 5) != SizedRecorder.n_params(64, 3)


def test_the_shipped_size_rows_do_not_depend_on_the_larger_entries(
    full_run, tmp_path, monkeypatch
):
    _, out, full = full_run
    _, small_out, small = _run(tmp_path, monkeypatch, entries=("mlp_h1", "mlp_h3"))
    with_larger = pd.read_parquet(out / "results.parquet")
    without = pd.read_parquet(small_out / "results.parquet")
    kept = with_larger[with_larger["entry"].isin(["mlp_h1", "mlp_h3"])]
    assert len(kept) == len(without) > 0
    pd.testing.assert_frame_equal(
        kept[UNTIMED].reset_index(drop=True),
        without[UNTIMED].reset_index(drop=True),
        check_exact=True,
    )
    for entry in ("mlp_h1", "mlp_h3"):
        assert (
            full["summary_data"]["per_seed_skill"][entry]
            == small["summary_data"]["per_seed_skill"][entry]
        )


def test_entries_run_in_a_fixed_order_whatever_order_is_given(tmp_path, monkeypatch):
    """Spec "Entries run in a fixed order and read the shipped defaults"."""
    shuffled = (
        "ridge_fixed",
        "mlp_w256d5_h3",
        "mlp_h3",
        "ridge",
        "mlp_w256d5",
        "mlp_h1",
    )
    rec, out, _ = _run(tmp_path, monkeypatch, entries=shuffled)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    results = pd.read_parquet(out / "results.parquet")
    assert summary["entries"] == ALL_ENTRIES
    assert meta["entries"] == ALL_ENTRIES
    # Each entry's rows form one block, in run order (no entry interleaved with another).
    assert [k for k, _ in itertools.groupby(results["entry"])] == ALL_ENTRIES
    for entry, fits in fits_by_entry(rec).items():
        assert {(f["hidden"], f["num_layers"], f["phase_harmonics"]) for f in fits} == {
            ARCHITECTURES[entry]
        }, entry
    # The first fit is mlp_h1 at the shipped size, on interpolation, at the first seed.
    first = rec.fits[0]
    target = metrics.target_beat_frame(synthetic_corpus())
    assert (
        first["hidden"],
        first["num_layers"],
        first["phase_harmonics"],
        first["seed"],
    ) == (64, 3, 1, BENCH_SEEDS[0])
    assert first["split"] == carve_split(
        build_splits(target)["interpolation"], seed=BENCH_SEEDS[0]
    )


def test_mlp_h1_on_interpolation_runs_first_on_the_full_target_beat_frame(full_run):
    rec, _, _ = full_run
    frame = synthetic_corpus()
    target = metrics.target_beat_frame(frame)
    first = rec.fits[0]
    assert first["phase_harmonics"] == 1 and first["seed"] == BENCH_SEEDS[0]
    # mlp_w256d5 also has one harmonic: the first fit must be the shipped size.
    assert (first["hidden"], first["num_layers"]) == (64, 3)
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
    assert set(mlp["entry"]) == set(MLP_ENTRIES)
    for entry, (hidden, num_layers, _) in ARCHITECTURES.items():
        assert set(mlp.loc[mlp["entry"] == entry, "n_params"]) == {
            SizedRecorder.n_params(hidden, num_layers)
        }


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
    assert set(status) == set(ALL_ENTRIES)
    for entry in ("mlp_h3", "mlp_w256d5", "mlp_w256d5_h3", "ridge_fixed", "ridge"):
        assert status[entry]["holdout_informed"] is True
    assert "weakly" in status["ridge"]["holdout_reason"]
    for entry in ("mlp_w256d5", "mlp_w256d5_h3"):
        assert "E4" in status[entry]["holdout_reason"], entry
    assert "harmonic" in status["mlp_w256d5_h3"]["holdout_reason"]
    assert "harmonic" not in status["mlp_w256d5"]["holdout_reason"]
    gate = summary["gate"]
    assert gate["provisional"] is True and len(gate["reasons"]) == 7
    assert set(gate["entries"]) == set(ALL_ENTRIES)
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


def _recorded_hyperparameters(fits):
    values = {
        (f["hidden"], f["num_layers"], f["lr"], f["phase_harmonics"]) for f in fits
    }
    assert len(values) == 1
    hidden, num_layers, lr, harmonics = values.pop()
    return {
        "hidden": hidden,
        "num_layers": num_layers,
        "lr": lr,
        "phase_harmonics": harmonics,
    }


def test_the_metadata_records_each_mlp_entrys_architecture(full_run):
    """Spec "The metadata records each MLP entry's architecture", the full run."""
    rec, out, _ = full_run
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    recorded = meta["mlp_hyperparameters"]
    assert list(recorded) == MLP_ENTRIES
    for entry, fits in fits_by_entry(rec).items():
        assert recorded[entry] == _recorded_hyperparameters(fits), entry
        hidden, num_layers, harmonics = ARCHITECTURES[entry]
        assert recorded[entry] == {
            "hidden": hidden,
            "num_layers": num_layers,
            "lr": 1e-3,
            "phase_harmonics": harmonics,
        }


def test_the_metadata_records_only_the_mlp_entries_that_ran(tmp_path, monkeypatch):
    rec, out, _ = _run(tmp_path, monkeypatch, entries=("mlp_h1", "ridge_fixed"))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["mlp_hyperparameters"] == {
        "mlp_h1": _recorded_hyperparameters(rec.fits)
    }
    assert len(rec.fits) == FITS_PER_ENTRY


def test_a_ridge_only_run_records_an_empty_mlp_hyperparameters(tmp_path, monkeypatch):
    rec, out, _ = _run(tmp_path, monkeypatch, entries=("ridge", "ridge_fixed"))
    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert "mlp_hyperparameters" in meta and meta["mlp_hyperparameters"] == {}
    assert rec.fits == []


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
    # The seed ranges skip the NaN seed and count it out; it never scores as perfect.
    for r in summary["seed_ranges"]:
        if r["entry"] == "mlp_h1":
            assert r["skill_n_finite_seeds"] == 4, r
            assert r["rmse_frac_component_peak_n_finite_seeds"] == 4, r
            assert r["rmse_frac_component_peak_min"] > 0.0, r
    face = summary["like_for_like"]["face:stroke_amp_deg=35"]["mlp_h1"]["targets"][
        "CF_x"
    ]
    assert face["face"]["rmse_frac_component_peak"]["n_finite"] == 4
    # The per-seed record keeps it as null.
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
        (dict(device="cuda:1"), "device"),
        (dict(device="cudax"), "device"),
        (dict(entries="ridge"), "list of entry names"),
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
    seed = BENCH_SEEDS[2]
    seen = set()
    # By position, not by harmonic count: two entries have three harmonics.
    for entry in ("mlp_h3", "mlp_w256d5_h3"):
        hidden, num_layers, harmonics = ARCHITECTURES[entry]
        fit = next(
            f
            for f in fits_by_entry(rec)[entry]
            if f["seed"] == seed and f["split"] == carve_split(split, seed=seed)
        )
        test = fit["frame"]["config_name"].isin(split.test)
        offset = SizedRecorder.offset(seed, harmonics, hidden, num_layers)
        y_pred = fit["frame"].loc[test, TARGET_COLUMNS].to_numpy() + offset
        expected = metrics.per_seed_skill(
            target, split.test, y_pred, baseline, list(TARGET_COLUMNS)
        )
        got = summary["per_seed_skill"][entry]["face:pitch_amp_deg=60"][str(seed)]
        assert got == pytest.approx(expected, rel=1e-12), entry
        seen.add(tuple(sorted(got.items())))
    assert (
        len(seen) == 2
    )  # the two entries' skills differ, so neither stands in for the other


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


# --- Atomic write ------------------------------------------------------------------------------


def _staging_dirs(parent):
    return [q for q in parent.iterdir() if q.name.startswith(".out.")]


def _kept_staging(exc_info, parent):
    """A failure keeps the staging directory and names it in the exception's notes."""
    kept = _staging_dirs(parent)
    assert len(kept) == 1
    notes = " ".join(getattr(exc_info.value, "__notes__", []))
    assert kept[0].as_posix() in notes or str(kept[0]) in notes
    return kept[0]


@pytest.mark.parametrize("pre_existing", [False, True])
def test_a_failure_while_writing_leaves_out_dir_as_it_was(
    tmp_path, monkeypatch, pre_existing
):
    """out_dir is untouched; what was written is kept in the named staging directory."""

    def broken(*args, **kwargs):
        raise OSError("disk full while writing the figure")

    monkeypatch.setattr(runner, "write_summary_figure", broken)
    out = tmp_path / "out"
    if pre_existing:
        out.mkdir()
    with pytest.raises(OSError, match="disk full") as exc_info:
        _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    if pre_existing:
        assert out.is_dir() and list(out.iterdir()) == []
    else:
        assert not out.exists()
    kept = _kept_staging(exc_info, tmp_path)
    assert {q.name for q in kept.iterdir()} == {
        "results.parquet",
        "splits.json",
        "summary.json",
    }


def test_a_successful_run_leaves_no_staging_directory(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()  # absent or empty are both allowed
    _, out, _ = _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    assert {q.name for q in out.iterdir()} == FILES
    assert [q.name for q in tmp_path.iterdir()] == ["out"]


def test_an_out_dir_filled_during_the_run_is_refused_and_the_bench_kept(
    tmp_path, monkeypatch
):
    out = tmp_path / "out"
    out.mkdir()
    real = runner.write_summary_figure

    def intruder(rows, path):
        real(rows, path)
        (out / "someone_else.txt").write_bytes(b"theirs")  # written mid-run

    monkeypatch.setattr(runner, "write_summary_figure", intruder)
    with pytest.raises(ValueError, match="no longer empty") as exc_info:
        _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    assert [q.name for q in out.iterdir()] == ["someone_else.txt"]
    kept = _kept_staging(exc_info, tmp_path)
    assert {q.name for q in kept.iterdir()} == FILES  # the finished bench is not lost


def test_a_move_that_fails_partway_is_rolled_back(tmp_path, monkeypatch):
    """All five or none in out_dir, even when the third move fails."""
    out = tmp_path / "out"
    out.mkdir()
    real = runner.os.replace
    calls = []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 3:
            raise PermissionError("locked by another process")
        return real(src, dst)

    monkeypatch.setattr(runner.os, "replace", flaky)
    with pytest.raises(PermissionError) as exc_info:
        _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    assert list(out.iterdir()) == []
    kept = _kept_staging(exc_info, tmp_path)
    assert {q.name for q in kept.iterdir()} == FILES


def test_the_current_directory_works_as_out_dir(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    _run(tmp_path, monkeypatch, entries=("ridge_fixed",), out_dir=".")
    assert {q.name for q in work.iterdir()} == FILES


def test_an_out_dir_under_a_file_is_refused_before_any_fit(tmp_path, monkeypatch):
    blocker = tmp_path / "afile"
    blocker.write_bytes(b"x")
    log = []
    with pytest.raises(ValueError, match="afile"):
        _run(
            tmp_path,
            monkeypatch,
            recorder=Recorder(log=log),
            out_dir=blocker / "sub",
        )
    assert log == []
    assert blocker.read_bytes() == b"x"


@pytest.mark.skipif(os.name != "posix", reason="POSIX directory modes")
def test_a_new_out_dir_gets_the_umask_mode_not_mkdtemps_0700(tmp_path, monkeypatch):
    old = os.umask(0o022)
    try:
        _, out, _ = _run(tmp_path, monkeypatch, entries=("ridge_fixed",))
    finally:
        os.umask(old)
    assert (out.stat().st_mode & 0o777) == 0o755


def test_each_split_grid_frame_is_built_once(tmp_path, monkeypatch):
    calls = []
    real = metrics.grid_frame

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(metrics, "grid_frame", spy)
    _run(tmp_path, monkeypatch, entries=("mlp_h1", "ridge_fixed"))
    assert len(calls) == 14
