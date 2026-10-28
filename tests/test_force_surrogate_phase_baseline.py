"""CPU-tier tests for the phase-only baseline and skill (change replace-config-r2-with-baseline-skill).

Torch-free: these run on the CPU-only CI runner. Each test cites the ``force-surrogate`` spec
scenario it verifies ("Phase-only baseline skill in metrics.json").
"""

import json

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import (
    CONVERGED_MIN_WINGBEAT,
    TARGET_COLUMNS,
    build_metrics,
    build_phase_only_baseline,
    compute_baseline_skill,
    write_json,
)


def _beat(config, phase, values, *, split="train", wingbeat=1):
    """Rows for one beat of one config, a single ``CF_x`` target."""
    phase = np.asarray(phase, dtype=float)
    return pd.DataFrame(
        {
            "config_name": config,
            "split": split,
            "wingbeat": wingbeat,
            "phase": phase,
            "CF_x": np.broadcast_to(np.asarray(values, dtype=float), phase.shape),
        }
    )


def _frame(*beats):
    return pd.concat(beats, ignore_index=True)


# --- Scenario: equal-weight interpolants, including wrap and row order --------------------


def test_baseline_is_the_unweighted_mean_of_per_config_interpolants():
    """Equal weight per config, not per row; shuffled rows give the same answer."""
    pa = np.arange(4) / 4
    pb = np.arange(12) / 12  # 3x the rows of config a
    df = _frame(
        _beat("a", pa, np.sin(2 * np.pi * pa)),
        _beat("b", pb, 2.0 + np.cos(2 * np.pi * pb)),
    )
    q = np.array([0.0, 0.25, 0.5, 0.75])  # on both grids -> interpolation is exact
    expected = 0.5 * (np.sin(2 * np.pi * q) + 2.0 + np.cos(2 * np.pi * q))

    pred, _ = build_phase_only_baseline(df, q, ["CF_x"])
    np.testing.assert_allclose(pred[:, 0], expected, rtol=0, atol=1e-12)
    row_weighted = (np.sin(2 * np.pi * q) + 3 * (2.0 + np.cos(2 * np.pi * q))) / 4
    assert not np.allclose(pred[:, 0], row_weighted)

    shuffled = df.sample(frac=1.0, random_state=7).reset_index(drop=True)
    pred_shuffled, _ = build_phase_only_baseline(shuffled, q, ["CF_x"])
    assert np.array_equal(pred, pred_shuffled)


def test_baseline_wraps_periodically_past_the_last_sample():
    """A query between the last sample (0.95) and 1.0 interpolates toward phase 0."""
    df = _frame(_beat("a", [0.0, 0.5, 0.95], [1.0, 3.0, 5.0]))
    pred, _ = build_phase_only_baseline(df, np.array([0.975]), ["CF_x"])
    # Halfway from (0.95, 5.0) to (1.0 == phase 0, 1.0) -> 3.0; a clamped interp gives 5.0.
    assert pred[0, 0] == pytest.approx(3.0, abs=1e-12)


# --- Scenario: holdout never enters ---------------------------------------------------


def test_holdout_rows_never_enter_the_baseline():
    """Holdout targets at 1e6 leave the baseline bitwise unchanged; reference = train configs."""
    p = np.arange(4) / 4
    train = [_beat(c, p, v) for c, v in (("t1", 1.0), ("t0", 2.0), ("t2", 4.0))]
    holdout = _beat("h0", p, 7.0, split="holdout")
    q = np.array([0.1, 0.6])

    pred, definition = build_phase_only_baseline(_frame(*train, holdout), q, ["CF_x"])
    loud = _frame(*train, _beat("h0", p, 1.0e6, split="holdout"))
    pred_loud, _ = build_phase_only_baseline(loud, q, ["CF_x"])

    assert np.array_equal(pred, pred_loud)
    np.testing.assert_allclose(pred[:, 0], 7.0 / 3.0, rtol=0, atol=1e-12)
    # Every split == "train" config, including any a seed would carve for validation.
    assert definition["reference_configs"] == ["t0", "t1", "t2"]


def test_definition_records_how_the_baseline_was_built():
    """The definition block names the kind, split, weighting and converged-beat threshold."""
    df = _frame(_beat("a", [0.0, 0.5], [1.0, 2.0]))
    _, definition = build_phase_only_baseline(df, np.array([0.0]), ["CF_x"])
    assert definition == {
        "kind": "phase_only_periodic_interpolation",
        "reference_split": "train",
        "reference_configs": ["a"],
        "weighting": "equal_per_config_then_beat",
        "converged_min_wingbeat": CONVERGED_MIN_WINGBEAT,
    }


# --- Scenario: beats averaged, startup excluded ----------------------------------------


def test_converged_beats_are_averaged_within_a_config_and_startup_is_excluded():
    """Two converged beats count once against a one-beat config; the startup beat is ignored."""
    df = _frame(
        _beat("a", [0.0, 0.5], 100.0, wingbeat=0),  # startup transient
        _beat("a", [0.0, 0.5], 1.0, wingbeat=1),
        _beat(
            "a", [0.25, 0.75], 3.0, wingbeat=2
        ),  # offset phases: pooling would not collide
        _beat("b", [0.0, 0.5], 8.0, wingbeat=1),
    )
    q = np.array([0.0, 0.3, 0.9])
    pred, _ = build_phase_only_baseline(df, q, ["CF_x"])
    # config a -> mean(1, 3) = 2; config b -> 8; equal weight -> 5. Beat-weighted would be 4.
    np.testing.assert_allclose(pred[:, 0], 5.0, rtol=0, atol=1e-12)


# --- Scenario: malformed reference or query rejected ------------------------------------


@pytest.mark.parametrize(
    ("df", "query", "match"),
    [
        (
            _frame(_beat("h", [0.0, 0.5], 1.0, split="holdout")),
            [0.1],
            "no reference",
        ),
        (_frame(_beat("a", [0.2], 1.0)), [0.1], "fewer than 2"),
        (_frame(_beat("a", [0.2, 0.2, 0.6], 1.0)), [0.1], "duplicate phase"),
        (_frame(_beat("a", [0.2, 0.6, 0.2], 1.0)), [0.1], "duplicate phase"),
        (_frame(_beat("a", [0.0, 0.5], [1.0, np.nan])), [0.1], "non-finite reference"),
        (_frame(_beat("a", [0.0, 1.0], 1.0)), [0.1], r"reference phase.*\[0, 1\)"),
        (_frame(_beat("a", [-0.1, 0.5], 1.0)), [0.1], r"reference phase.*\[0, 1\)"),
        (_frame(_beat("a", [0.0, 0.5], 1.0)), [np.nan], r"query phase.*\[0, 1\)"),
        (_frame(_beat("a", [0.0, 0.5], 1.0)), [1.0], r"query phase.*\[0, 1\)"),
        (_frame(_beat("a", [0.0, 0.5], 1.0)), [-0.01], r"query phase.*\[0, 1\)"),
    ],
    ids=[
        "no-reference-config",
        "beat-with-one-row",
        "duplicate-phase",
        "duplicate-phase-not-adjacent",
        "non-finite-value",
        "reference-phase-1.0",
        "reference-phase-negative",
        "query-nan",
        "query-1.0",
        "query-negative",
    ],
)
def test_malformed_reference_or_query_is_rejected(df, query, match):
    """Each malformed input raises ValueError naming the problem."""
    with pytest.raises(ValueError, match=match):
        build_phase_only_baseline(df, np.array(query), ["CF_x"])


def test_baseline_is_bitwise_reproducible():
    """Built twice from the same input -> bitwise identical."""
    p = np.arange(7) / 7
    df = _frame(
        _beat("a", p, np.sin(2 * np.pi * p)), _beat("b", p, np.cos(2 * np.pi * p))
    )
    q = np.linspace(0.0, 0.99, 31)
    first, d1 = build_phase_only_baseline(df, q, ["CF_x"])
    second, d2 = build_phase_only_baseline(df, q, ["CF_x"])
    assert np.array_equal(first, second)
    assert d1 == d2


# --- Scenario: skill known answers, sentinel and degenerate input -----------------------

_T = np.array([[1.0], [-2.0], [3.0], [0.5]])
_B = np.array(
    [[0.0], [-1.0], [2.0], [1.5]]
)  # baseline residuals: 1, -1, 1, -1 -> SSE 4


def test_skill_known_answers():
    """Perfect -> 1; equal to the phase-only baseline -> 0; twice its SSE -> -1 (unclipped)."""
    assert compute_baseline_skill(_T, _T, _B, ["CF_x"])["CF_x"]["skill"] == 1.0
    assert compute_baseline_skill(_T, _B, _B, ["CF_x"])["CF_x"]["skill"] == 0.0
    twice = _T + np.sqrt(2.0) * (_B - _T)  # SSE 8
    skill = compute_baseline_skill(_T, twice, _B, ["CF_x"])["CF_x"]["skill"]
    assert skill == pytest.approx(-1.0, abs=1e-12)


def test_phase_baseline_rmse_and_r2_known_answers():
    """phase_baseline_rmse = sqrt(4/4) = 1; phase_baseline_r2 = 1 - 4/SS_tot."""
    out = compute_baseline_skill(_T, _T, _B, ["CF_x"])["CF_x"]
    ss_tot = float(np.sum((_T - _T.mean()) ** 2))
    assert out["phase_baseline_rmse"] == pytest.approx(1.0, abs=1e-12)
    assert out["phase_baseline_r2"] == pytest.approx(1.0 - 4.0 / ss_tot, abs=1e-12)
    assert set(out) == {"skill", "phase_baseline_rmse", "phase_baseline_r2"}


def test_skill_is_null_when_the_phase_only_baseline_is_exact(tmp_path):
    """Baseline == truth -> skill NaN, serialized as JSON null (no 0/0)."""
    out = compute_baseline_skill(_T, _B, _T, ["CF_x"])
    assert np.isnan(out["CF_x"]["skill"])
    path = tmp_path / "s.json"
    write_json(path, out)
    assert json.loads(path.read_text(encoding="utf-8"))["CF_x"]["skill"] is None


def test_skill_sentinel_is_scale_relative():
    """A small-magnitude target keeps an honest skill; the floor is relative to sum(t**2)."""
    t = 1.0e-6 * np.array([[1.0], [-2.0], [3.0]])
    b = t + 1.0e-8  # SSE_b 3e-16, far above 1e-12 * sum(t**2) = 1.4e-23
    p = t + 0.5e-8  # SSE 0.75e-16 -> skill 0.75
    out = compute_baseline_skill(t, p, b, ["CF_x"])
    assert out["CF_x"]["skill"] == pytest.approx(0.75, abs=1e-9)
    # ...and the sentinel fires once the phase-only baseline error falls below that floor.
    assert np.isnan(
        compute_baseline_skill(t, p, t + 1.0e-20, ["CF_x"])["CF_x"]["skill"]
    )


@pytest.mark.parametrize(
    ("t", "p", "b", "names", "match"),
    [
        (np.zeros((0, 1)), np.zeros((0, 1)), np.zeros((0, 1)), ["CF_x"], "zero-row"),
        (_T, _T[:3], _B, ["CF_x"], "must share shape"),
        (_T, _T, _B[:3], ["CF_x"], "must share shape"),
        (_T, _T, _B, ["CF_x", "CF_z"], "target_names"),
    ],
    ids=["zero-rows", "pred-shape", "baseline-shape", "names-count"],
)
def test_skill_rejects_degenerate_input(t, p, b, names, match):
    """Zero rows or mismatched shapes raise ValueError (parity with compute_metrics)."""
    with pytest.raises(ValueError, match=match):
        compute_baseline_skill(t, p, b, names)


# --- build_metrics writes the phase_baseline_skill block -------------------------------


def _metrics_inputs():
    rng = np.random.default_rng(3)
    n = 8
    holdout = pd.DataFrame({"config_name": ["h0"] * 4 + ["h1"] * 4})
    y_true = rng.standard_normal((n, len(TARGET_COLUMNS)))
    y_pred = y_true + 0.01 * rng.standard_normal(y_true.shape)
    y_base = y_true + 0.1 * rng.standard_normal(y_true.shape)
    return holdout, y_true, y_pred, y_base


def _build(holdout, y_true, y_pred, **kwargs):
    return build_metrics(
        y_true,
        y_pred,
        holdout,
        inference={"latency_ms": 0.5, "throughput_rows_per_s": 2.0e6, "basis": "x"},
        reproducibility={"seeds": {"global": 1234}},
        **kwargs,
    )


def test_build_metrics_writes_the_phase_baseline_skill_block():
    """The block carries the definition and per-target skill for all six targets."""
    holdout, y_true, y_pred, y_base = _metrics_inputs()
    definition = {
        "kind": "phase_only_periodic_interpolation",
        "reference_configs": ["t"],
    }
    metrics = _build(holdout, y_true, y_pred, phase_baseline=(y_base, definition))
    block = metrics["phase_baseline_skill"]
    assert block["phase_baseline"] == definition
    assert block["per_target"] == compute_baseline_skill(
        y_true, y_pred, y_base, list(TARGET_COLUMNS)
    )
    assert set(block["per_target"]) == set(TARGET_COLUMNS)


def test_build_metrics_without_a_phase_baseline_omits_the_block():
    """phase_baseline=None (the default) leaves metrics.json unchanged."""
    holdout, y_true, y_pred, _ = _metrics_inputs()
    metrics = _build(holdout, y_true, y_pred)
    assert set(metrics) == {
        "per_target",
        "aggregate",
        "per_config",
        "config_resolved",
        "inference",
        "reproducibility",
    }
