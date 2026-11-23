"""Bench metrics (add-surrogate-comparison-bench, 5; CPU tier).

Scenarios of the requirement "Bench model entries and metrics": "Skill baseline follows the split",
"The two normalisations differ by the ratio of peaks", "Pooled values recompute from the stored
sums", "Learned entries are never reported from one seed", "The model is evaluated directly at
the grid phases", "Holdout-informed entries are flagged" (overlap, faces without holdouts, the
like-for-like view), plus the target-beat guards of "Late-beat boundary".
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import compute_baseline_skill
from mosquito_cfd.surrogate_bench import metrics
from mosquito_cfd.surrogate_bench.ridge import N_GRID, PHASE_GRID
from mosquito_cfd.surrogate_bench.splits import BenchSplit, build_splits

REPO = Path(__file__).resolve().parents[1]
FINE_DATASET = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
TARGETS = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]


@pytest.fixture(scope="module")
def fine():
    return pd.read_parquet(FINE_DATASET)


@pytest.fixture(scope="module")
def target_frame(fine):
    return metrics.target_beat_frame(fine)


# --- Target beat ------------------------------------------------------------------------------


def _beats_frame(beats_per_config, last_phase=0.995, missing=()):
    rows = []
    for name, beats in beats_per_config.items():
        for b in beats:
            if (name, b) in missing:
                continue
            phase = np.linspace(0.0, last_phase, 20)
            rows.append(
                pd.DataFrame({"config_name": name, "wingbeat": b, "phase": phase})
            )
    return pd.concat(rows, ignore_index=True)


def test_the_fine_corpus_target_beat_is_the_converged_beat(fine, target_frame):
    from mosquito_cfd.force_surrogate.train import filter_converged_beat

    assert metrics.target_beat(fine) == 1
    expected = filter_converged_beat(fine)
    assert target_frame.index.equals(expected.index)


def test_the_target_beat_is_the_largest_common_beat():
    frame = _beats_frame({"a": [0, 1, 2, 3], "b": [0, 1, 2]})
    assert metrics.target_beat(frame) == 2


def test_missing_beat_zero_is_rejected():
    frame = _beats_frame({"a": [1, 2, 3], "b": [1, 2, 3]})
    with pytest.raises(ValueError, match="0..N"):
        metrics.target_beat(frame)


def test_a_one_beat_corpus_is_rejected():
    """beat1_vs_beat2 and the converged-beat target both need at least 2 common beats."""
    frame = _beats_frame({"a": [0, 1], "b": [0]})
    with pytest.raises(ValueError, match="at least 2"):
        metrics.target_beat(frame)


def test_a_partial_last_beat_is_rejected():
    frame = _beats_frame({"a": [0, 1], "b": [0, 1]})
    short = (
        frame["wingbeat"].eq(1) & frame["config_name"].eq("b") & frame["phase"].gt(0.5)
    )
    with pytest.raises(ValueError, match="span"):
        metrics.target_beat(frame[~short])


# --- Normalisers ------------------------------------------------------------------------------


def test_component_peaks_cover_every_configuration(target_frame):
    peaks = metrics.component_peaks(target_frame, TARGETS)
    truth = metrics.grid_truth(target_frame, TARGETS)
    for j, t in enumerate(TARGETS):
        assert peaks[t] == max(float(np.abs(g[:, j]).max()) for g in truth.values())
    assert len(truth) == 27


def _two_config_frame():
    phase = np.arange(32) / 32
    rows = []
    for name, amp, s in (("A", 0.1, 35.0), ("B", 1.0, 45.0)):
        rows.append(
            pd.DataFrame(
                {
                    "config_name": name,
                    "wingbeat": 1,
                    "phase": phase,
                    "stroke_amp_deg": s,
                    "frequency_fstar": 1.0,
                    "pitch_amp_deg": 45.0,
                    "CF_x": amp * np.sin(2 * np.pi * phase),
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _score(frame, test, y_pred, predict_grid, baseline, targets=("CF_x",)):
    truth = metrics.grid_truth(frame, list(targets))
    peaks = metrics.component_peaks(frame, list(targets))
    return metrics.score_split_seed(
        entry="m",
        split="s",
        seed=1,
        target_frame=frame,
        test_configs=test,
        y_pred=y_pred,
        predict_grid=predict_grid,
        baseline=baseline,
        truth=truth,
        peaks=peaks,
        targets=list(targets),
        extra={"fit_seconds": 1.0},
    )


def _const_grid(value):
    return lambda grid: np.full((len(grid), 1), value)


def test_the_two_normalisations_differ_by_the_ratio_of_peaks():
    frame = _two_config_frame()
    test_rows = frame[frame["config_name"] == "A"]
    baseline = metrics.split_baseline(frame, ["B"], ["CF_x"])
    rows = _score(
        frame, ["A"], np.zeros((len(test_rows), 1)), _const_grid(0.0), baseline
    )
    a = rows.iloc[0]
    assert a["rmse_frac_config_peak"] / a["rmse_frac_component_peak"] == pytest.approx(
        10.0, rel=1e-12
    )


# --- Baseline per split, per-seed skill, direct grid evaluation ----------------------------


def test_the_skill_baseline_follows_the_split(target_frame):
    face = build_splits(target_frame)["face:stroke_amp_deg=55"]
    baseline = metrics.split_baseline(target_frame, face.train, TARGETS)
    assert baseline.definition["reference_configs"] == list(face.train)
    assert baseline.definition["reference_split"] == "explicit"


def test_per_seed_skill_uses_all_test_rows_in_dataset_order(target_frame):
    split = build_splits(target_frame)["interpolation"]
    baseline = metrics.split_baseline(target_frame, split.train, TARGETS)
    test = target_frame[target_frame["config_name"].isin(split.test)]
    rng = np.random.default_rng(0)
    y_pred = test[TARGETS].to_numpy() + 0.01 * rng.normal(size=(len(test), 6))
    got = metrics.per_seed_skill(target_frame, split.test, y_pred, baseline, TARGETS)
    y_base = baseline.at(test["phase"].to_numpy())
    expected = compute_baseline_skill(test[TARGETS].to_numpy(), y_pred, y_base, TARGETS)
    assert got == {t: expected[t]["skill"] for t in TARGETS}


def test_the_model_is_evaluated_directly_at_the_grid_phases():
    frame = _two_config_frame()
    test_rows = frame[frame["config_name"] == "A"]
    baseline = metrics.split_baseline(frame, ["B"], ["CF_x"])

    def high_frequency(grid):  # zero at every test row (k/32), non-zero between them
        return np.sin(2 * np.pi * 64 * grid["phase"].to_numpy())[:, None]

    rows = _score(
        frame,
        ["A"],
        np.zeros((len(test_rows), 1)),
        high_frequency,
        baseline,
    )
    # The CFD on the grid is the samples periodically (linearly) interpolated, by definition.
    samples = np.arange(32) / 32
    truth = np.interp(
        PHASE_GRID, samples, 0.1 * np.sin(2 * np.pi * samples), period=1.0
    )
    direct = np.sin(2 * np.pi * 64 * PHASE_GRID)
    assert rows.iloc[0]["grid_sse"] == pytest.approx(
        ((truth - direct) ** 2).sum(), rel=1e-12
    )
    assert rows.iloc[0]["n_grid"] == N_GRID


# --- Pooled values, seed ranges, equality helper -------------------------------------------


def _results(seeds=(1, 2, 3, 4, 5), entry="mlp_h1"):
    rng = np.random.default_rng(1)
    rows = []
    for seed in seeds:
        for config in ("c1", "c2"):
            rows.append(
                {
                    "entry": entry,
                    "split": "s",
                    "seed": seed,
                    "target": "CF_x",
                    "config_name": config,
                    "n_rows": 10,
                    "sse": float(rng.uniform(0.1, 1)),
                    "sse_baseline": float(rng.uniform(2, 3)),
                    "n_grid": N_GRID,
                    "grid_sse": float(rng.uniform(0.1, 1)),
                    "baseline_grid_sse": float(rng.uniform(2, 3)),
                    "peak_t": 2.0,
                    "fit_seconds": float(rng.uniform()),
                }
            )
    return pd.DataFrame(rows)


def test_pooled_values_recompute_from_the_stored_sums():
    res = _results()
    pooled = metrics.pooled(res)
    one = res[res["seed"] == 3]
    row = pooled[(pooled["seed"] == 3)].iloc[0]
    assert row["skill"] == pytest.approx(
        1 - one["sse"].sum() / one["sse_baseline"].sum(), rel=1e-12
    )
    assert row["rmse_frac_component_peak"] == pytest.approx(
        np.sqrt(one["grid_sse"].sum() / one["n_grid"].sum()) / 2.0, rel=1e-12
    )
    assert row["baseline_rmse_frac_component_peak"] == pytest.approx(
        np.sqrt(one["baseline_grid_sse"].sum() / one["n_grid"].sum()) / 2.0, rel=1e-12
    )


def test_learned_entries_need_five_seeds():
    with pytest.raises(ValueError, match="5 seeds"):
        metrics.seed_ranges(metrics.pooled(_results(seeds=(1, 2, 3, 4))))
    out = metrics.seed_ranges(metrics.pooled(_results()))
    assert set(out.columns) >= {"skill_min", "skill_max"}


def test_a_single_fit_entry_is_allowed_one_seed():
    out = metrics.seed_ranges(metrics.pooled(_results(seeds=(0,), entry="ridge")))
    assert len(out) == 1


@pytest.mark.parametrize("which", ["one_config", "both_configs"])
def test_a_nan_seed_pools_to_nan_never_to_a_perfect_score(which):
    """A diverged seed's NaN sse/grid_sse must not sum to 0 (skill 1.0, RMSE 0.0)."""
    res = _results()
    bad = res["seed"] == 3
    if which == "one_config":
        bad &= res["config_name"] == "c1"
    res.loc[bad, ["sse", "grid_sse"]] = np.nan
    pooled = metrics.pooled(res)
    row = pooled[pooled["seed"] == 3].iloc[0]
    assert np.isnan(row["skill"]) and np.isnan(row["rmse_frac_component_peak"])
    ranges = metrics.seed_ranges(pooled).iloc[0]
    assert ranges["skill_n_finite_seeds"] == 4
    assert ranges["rmse_frac_component_peak_n_finite_seeds"] == 4
    assert ranges["skill_max"] < 1.0 and ranges["rmse_frac_component_peak_min"] > 0.0


def test_seed_ranges_are_nan_aware():
    pooled = metrics.pooled(_results())
    pooled.loc[pooled["seed"] == 2, "skill"] = np.nan
    row = metrics.seed_ranges(pooled).iloc[0]
    finite = pooled["skill"].dropna()
    assert row["skill_min"] == finite.min() and row["skill_max"] == finite.max()
    # A seed that drops out of a range is counted, never silently lost.
    assert row["n_seeds"] == 5 and row["skill_n_finite_seeds"] == 4
    assert row["rmse_frac_component_peak_n_finite_seeds"] == 5


def test_timing_and_memory_columns_are_excluded_from_equality():
    a = _results()
    b = a.assign(fit_seconds=a["fit_seconds"] + 1, peak_gpu_mem=7)
    assert metrics.comparable(a).equals(metrics.comparable(b))
    assert not metrics.comparable(a).equals(
        metrics.comparable(a.assign(sse=a["sse"] * 2))
    )


# --- Holdout overlap, faces without holdouts, the like-for-like view -----------------------


HOLDOUTS = [
    "s35_f085_p45",
    "s45_f085_p60",
    "s45_f100_p60",
    "s45_f115_p60",
    "s55_f085_p45",
    "s55_f115_p45",
]


def test_holdout_overlap_per_split(target_frame):
    splits = build_splits(target_frame)
    overlap = metrics.holdout_overlap(splits, HOLDOUTS)
    assert overlap["interpolation"] == 6
    assert all(overlap[f"control:{k}"] == 6 for k in range(6))
    assert overlap["control:e4_seed0"] == 6
    assert [
        overlap[f"face:{s}"]
        for s in (
            "stroke_amp_deg=35",
            "stroke_amp_deg=55",
            "frequency_fstar=0.85",
            "frequency_fstar=1.15",
            "pitch_amp_deg=30",
            "pitch_amp_deg=60",
        )
    ] == [1, 2, 3, 2, 0, 3]


def _split_results(entries=("mlp_h1",)):
    rows = []
    for entry in entries:
        for split, configs in (
            ("face:p=60", ["h1", "x1", "x2"]),
            ("face:p=30", ["y1", "y2"]),
            ("control:0", ["h1", "h2"]),
            ("control:1", ["h1", "h2"]),
        ):
            for seed in (1, 2, 3, 4, 5):
                for c in configs:
                    rows.append(
                        {
                            "entry": entry,
                            "split": split,
                            "seed": seed,
                            "target": "CF_x",
                            "config_name": c,
                            "n_rows": 4,
                            "sse": 1.0,
                            "sse_baseline": 4.0,
                            "n_grid": N_GRID,
                            "grid_sse": float(seed) * (2.0 if c == "h1" else 1.0),
                            "baseline_grid_sse": 9.0,
                            "peak_t": 3.0,
                        }
                    )
    return pd.DataFrame(rows)


SYNTH_SPLITS = {
    "face:p=60": BenchSplit("face:p=60", ("a",), ("h1", "x1", "x2")),
    "face:p=30": BenchSplit("face:p=30", ("a",), ("y1", "y2")),
    "control:0": BenchSplit("control:0", ("a",), ("h1", "h2")),
    "control:1": BenchSplit("control:1", ("a",), ("h1", "h2")),
}


def test_face_metrics_without_holdouts():
    out = metrics.faces_without_holdouts(_split_results(), SYNTH_SPLITS, ["h1", "h2"])
    row = out[(out["split"] == "face:p=60") & (out["seed"] == 2)].iloc[0]
    assert row["rmse_frac_component_peak"] == pytest.approx(
        np.sqrt((2.0 + 2.0) / (2 * N_GRID)) / 3.0, rel=1e-12
    )
    assert set(out["split"]) == {"face:p=60", "face:p=30"}


def _l4l_results():
    """Two targets, distinct per-control scales, and an E4 control kept apart from the rest."""
    scale = {
        "face:p=60": 1.0,
        "control:0": 0.5,
        "control:1": 0.7,
        "control:e4_seed0": 9.0,
    }
    target_scale = {"CF_x": 1.0, "CF_z": 100.0}
    rows = []
    for split, configs in (
        ("face:p=60", ["h1", "x1"]),
        ("face:p=30", ["y1"]),
        ("control:0", ["h1", "h2"]),
        ("control:1", ["h1", "h2"]),
        ("control:e4_seed0", ["h1", "h2"]),
    ):
        for seed in (1, 2, 3, 4, 5):
            for target, ts in target_scale.items():
                for c in configs:
                    # h2 (not on the face) is huge, so including it would show.
                    other = 1e6 if c == "h2" else 1.0
                    rows.append(
                        {
                            "entry": "mlp_h1",
                            "split": split,
                            "seed": seed,
                            "target": target,
                            "config_name": c,
                            "n_rows": 4,
                            "sse": 1.0,
                            "sse_baseline": 4.0,
                            "n_grid": N_GRID,
                            "grid_sse": seed * ts * scale.get(split, 1.0) * other,
                            "baseline_grid_sse": 9.0 * ts,
                            "peak_t": 3.0,
                        }
                    )
    return pd.DataFrame(rows)


L4L_SPLITS = {
    "face:p=60": BenchSplit("face:p=60", ("a",), ("h1", "x1")),
    "face:p=30": BenchSplit("face:p=30", ("a",), ("y1",)),
    "control:0": BenchSplit("control:0", ("a",), ("h1", "h2")),
    "control:1": BenchSplit("control:1", ("a",), ("h1", "h2")),
    "control:e4_seed0": BenchSplit("control:e4_seed0", ("a",), ("h1", "h2")),
}


def _rms(grid_sse):
    return np.sqrt(grid_sse / N_GRID) / 3.0


def test_the_like_for_like_view_reports_rms_only_and_nulls_a_face_without_holdouts():
    view = metrics.like_for_like(_l4l_results(), L4L_SPLITS, ["h1", "h2"])
    assert view["face:p=30"] == {
        "value": None,
        "reason": "no labelled holdouts on this face",
    }
    entry = view["face:p=60"]["mlp_h1"]
    assert entry["configs"] == ["h1"]
    assert set(entry["targets"]) == {"CF_x", "CF_z"}
    seeds = np.arange(1, 6)
    for t, ts in (("CF_x", 1.0), ("CF_z", 100.0)):
        sides = entry["targets"][t]
        assert set(sides) == {"face", "controls", "control:e4_seed0"}
        for side in sides.values():
            assert set(side) == {
                "rmse_frac_component_peak",
                "baseline_rmse_frac_component_peak",
            }
        # Face: the range over seeds of this target only, on h1 only.
        assert sides["face"]["rmse_frac_component_peak"] == {
            "min": pytest.approx(_rms(1 * ts)),
            "max": pytest.approx(_rms(5 * ts)),
            "n_finite": 5,
        }
        # Controls: the random controls (here 0 and 1) x seeds, on h1 only; E4 apart.
        ctrl = [_rms(s * ts * k) for s in seeds for k in (0.5, 0.7)]
        assert sides["controls"]["rmse_frac_component_peak"] == {
            "min": pytest.approx(min(ctrl)),
            "max": pytest.approx(max(ctrl)),
            "n_finite": 10,
        }
        assert sides["control:e4_seed0"]["rmse_frac_component_peak"] == {
            "min": pytest.approx(_rms(1 * ts * 9.0)),
            "max": pytest.approx(_rms(5 * ts * 9.0)),
            "n_finite": 5,
        }
        assert sides["face"]["baseline_rmse_frac_component_peak"] == {
            "min": pytest.approx(_rms(9.0 * ts)),
            "max": pytest.approx(_rms(9.0 * ts)),
            "n_finite": 5,
        }


# --- The baseline is built once per phase array; the grid is checked -------------------------


def _counting_baseline(monkeypatch):
    calls = []
    real = metrics.build_phase_only_baseline

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(metrics, "build_phase_only_baseline", spy)
    return calls


def test_the_split_baseline_is_built_once_per_phase_array(monkeypatch):
    frame = _two_config_frame()
    calls = _counting_baseline(monkeypatch)
    baseline = metrics.split_baseline(frame, ["B"], ["CF_x"])
    built = len(calls)
    first = baseline.at(PHASE_GRID)
    again = baseline.at(PHASE_GRID.copy())  # equal values, a different array object
    assert len(calls) == built + 1
    assert np.array_equal(first, again)
    other = baseline.at(np.array([0.1, 0.2]))
    assert len(calls) == built + 2 and other.shape == (2, 1)
    # The cached array cannot be changed by a caller.
    with pytest.raises(ValueError):
        first[0, 0] = 99.0
    # The cache returns exactly what a fresh build returns.
    fresh, _ = metrics.build_phase_only_baseline(
        frame, PHASE_GRID, ["CF_x"], reference_configs=["B"]
    )
    assert np.array_equal(first, fresh)


def test_a_grid_prediction_of_the_wrong_length_is_rejected():
    frame = _two_config_frame()
    test_rows = frame[frame["config_name"] == "A"]
    baseline = metrics.split_baseline(frame, ["B"], ["CF_x"])
    with pytest.raises(ValueError, match="grid"):
        _score(
            frame,
            ["A"],
            np.zeros((len(test_rows), 1)),
            lambda grid: np.zeros((len(grid) - 1, 1)),
            baseline,
        )


def test_a_supplied_grid_must_match_the_test_configurations_in_order():
    frame = _two_config_frame()
    both = frame  # A and B are both test configurations here
    baseline = metrics.split_baseline(frame, ["A"], ["CF_x"])
    wrong_order = metrics.grid_frame(frame, ["B", "A"])
    with pytest.raises(ValueError, match="grid"):
        metrics.score_split_seed(
            entry="m",
            split="s",
            seed=1,
            target_frame=frame,
            test_configs=["A", "B"],
            y_pred=np.zeros((len(both), 1)),
            predict_grid=lambda grid: np.zeros((len(grid), 1)),
            grid=wrong_order,
            baseline=baseline,
            truth=metrics.grid_truth(frame, ["CF_x"]),
            peaks=metrics.component_peaks(frame, ["CF_x"]),
            targets=["CF_x"],
        )


def test_the_cache_tells_equal_length_phase_arrays_apart():
    frame = _two_config_frame()
    baseline = metrics.split_baseline(frame, ["B"], ["CF_x"])
    a = baseline.at(np.array([0.1, 0.2]))
    b = baseline.at(np.array([0.3, 0.4]))
    assert not np.array_equal(a, b)


def test_a_supplied_grid_with_the_wrong_phases_is_rejected():
    frame = _two_config_frame()
    baseline = metrics.split_baseline(frame, ["A"], ["CF_x"])
    grid = metrics.grid_frame(frame, ["A", "B"])
    grid["phase"] = grid["phase"].to_numpy()[::-1]  # right configurations, wrong phases
    with pytest.raises(ValueError, match="grid"):
        metrics.score_split_seed(
            entry="m",
            split="s",
            seed=1,
            target_frame=frame,
            test_configs=["A", "B"],
            y_pred=np.zeros((len(frame), 1)),
            predict_grid=lambda g: np.zeros((len(g), 1)),
            grid=grid,
            baseline=baseline,
            truth=metrics.grid_truth(frame, ["CF_x"]),
            peaks=metrics.component_peaks(frame, ["CF_x"]),
            targets=["CF_x"],
        )
