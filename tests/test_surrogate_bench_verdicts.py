"""Hover-gate verdicts (add-surrogate-comparison-bench, 6b; CPU tier).

Scenarios of the requirement "Provisional hover gate": "Worst seed decides and margin uses the
worst seed", "Errors and yardsticks are fractions", "Gate boundaries", "A component with no
yardstick never passes", the combined-yardstick clause of "Late-beat boundary", the computed
wrap-jump reason, and the holdout marks of "Holdout-informed entries are flagged".
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from mosquito_cfd.surrogate_bench import gate


def _v(errors, yardsticks):
    return gate.verdict(errors, yardsticks)


# --- Worst seed, fractions, boundaries --------------------------------------------------


def test_the_worst_seed_decides_and_sets_the_margin():
    out = _v({"c": [0.01, 0.02, 0.03, 0.04, 0.06]}, {"c": 0.05})
    assert out["verdict"] == "outside"
    assert out["margin"] == pytest.approx(5 / 6, rel=1e-12)


def test_errors_and_yardsticks_are_fractions():
    out = _v({"c": [0.03] * 5}, {"c": gate.GCI_FINE["normal_peak"]})
    assert out["verdict"] == "inside"
    assert out["margin"] == pytest.approx(1.2307, abs=1e-4)


@pytest.mark.parametrize(
    ("errors", "yardsticks", "verdict", "margin"),
    [
        ({"c": [0.05] * 5}, {"c": 0.05}, "inside", 1.0),
        ({"a": [0.01] * 5, "b": [0.06] * 5}, {"a": 0.05, "b": 0.05}, "outside", 5 / 6),
        ({"c": [0.02] * 5}, {"c": 0.0}, "outside", 0.0),
        ({"c": [0.0] * 5}, {"c": 0.05}, "inside", "inf"),
        ({"a": [0.0] * 5, "b": [0.03] * 5}, {"a": 0.0, "b": 0.05}, "inside", 5 / 3),
        ({"a": [0.01] * 5, "b": [0.02] * 5}, {"a": 0.05, "b": 0.05}, "inside", 2.5),
    ],
)
def test_gate_boundaries(errors, yardsticks, verdict, margin):
    out = _v(errors, yardsticks)
    assert out["verdict"] == verdict
    if margin == "inf":
        assert out["margin"] == "inf"
    else:
        assert out["margin"] == pytest.approx(margin, rel=1e-12)


def test_a_nan_seed_makes_the_verdict_outside_with_a_null_margin():
    out = _v({"c": [0.01, 0.01, 0.01, 0.01, math.nan]}, {"c": 0.05})
    assert out["verdict"] == "outside" and out["margin"] is None and out["reason"]


def test_a_nan_yardstick_is_outside_with_a_reason():
    out = _v({"c": [0.01] * 5}, {"c": math.nan})
    assert out["verdict"] == "outside" and out["margin"] is None and out["reason"]


def test_all_zero_over_zero_is_inside_with_a_null_margin_and_a_reason():
    out = _v({"a": [0.0] * 5, "b": [0.0] * 5}, {"a": 0.0, "b": 0.0})
    assert out["verdict"] == "inside" and out["margin"] is None
    assert out["reason"] == "all configurations 0/0"


# --- The gate block --------------------------------------------------------------------------


def _yardsticks(late=None, comps=("CF_mx", "normal_peak")):
    ys = {}
    for comp in comps:
        ys[comp] = {
            "grid_gci": (
                {"value": gate.GCI_FINE[comp]}
                if comp in gate.PEAKS
                else {"not_applicable": True}
            ),
            "coarse_vs_fine": {"value": 0.2, "upper_bound": True},
            "coarse_vs_fine_scaled": {"value": 0.03},
            "beat1_vs_beat2": {"value": 0.1},
            "late_beat": (
                {"unavailable": gate.UNAVAILABLE_LATE}
                if late is None
                else {"value": late, "compares": [3, 2]}
            ),
        }
    return ys


def _errors(value=0.02):
    return {
        seed: {
            comp: {"full": value, "window": value} for comp in ("CF_mx", "normal_peak")
        }
        for seed in range(5)
    }


def _block(late=None, jumps=None, holdouts=None):
    yardsticks = {"h1": _yardsticks(late), "h2": _yardsticks(late)}
    jumps = jumps or {
        "h1": {"normal_peak": {"last_but_one": 0.03}},
        "t1": {"normal_peak": {"last_but_one": 0.046}},
    }
    return gate.gate_block(
        entries={"mlp_h1": {"h1": _errors(), "h2": _errors()}},
        yardsticks=yardsticks,
        wrap_jumps=jumps,
        peak_wrap_distance={"h1": 0.02, "t1": 0.0547},
        test_configs=["h1", "h2"],
        holdout_status=holdouts
        or {"mlp_h1": {"holdout_informed": "unverified", "holdout_reason": "r"}},
    )


def test_the_two_beat_block_is_provisional_with_seven_reasons_and_no_overall_key():
    block = _block()
    assert block["provisional"] is True and len(block["reasons"]) == 7
    assert not {"pass", "passed", "overall", "verdict"} & set(block)
    cf_mx = block["entries"]["mlp_h1"]["components"]["CF_mx"]
    assert cf_mx["grid_gci"] == {"verdict": "not_applicable"}
    assert cf_mx["late_beat"] == {
        "verdict": "unavailable",
        "reason": gate.UNAVAILABLE_LATE,
    }
    assert cf_mx["beat1_vs_beat2"]["verdict"] == "inside"


def test_the_fixed_reasons_state_their_facts():
    """Each provisional reason carries the fact it rests on (spec "Provisional hover gate")."""
    gci_stroke, one_beat, temporal, bc, coarse, startup = gate.FIXED_REASONS
    assert "70°" in gci_stroke and "35–55°" in gci_stroke
    assert one_beat == (
        "grid_gci is from a one-beat run, so its peaks are those of the startup beat"
    )
    assert "dt = 2.5e-4" in temporal and "cfl = 0.3" in temporal
    assert "5e-4 at 0.6" in temporal
    assert "is 2 where the corpus's is 4" in bc
    # Under the asymptotic Richardson model the coarse-fine difference is (r^p - 1) E_fine:
    # an upper bound on the fine grid's error, and below the coarse grid's own error.
    assert "upper bound on the fine grid's error" in coarse
    assert "under-estimates the coarse grid's error" in coarse
    # Both corpora run at dt = 5e-4, so temporal error cancels from the difference.
    assert "dt = 5e-4" in coarse and "spatial" in coarse
    assert "5.6-5.7" in coarse and "5.8" not in coarse and "conservative" not in coarse
    assert "refines the grid only" in gate.SCALED_LABEL
    assert "startup beat" in startup and "has not settled" in startup


def test_the_block_documents_the_all_zero_reason_as_no_error_and_no_yardstick():
    """Spec "Gate boundaries": the summary documents 0/0 as no error and no yardstick."""
    notes = _block()["reason_notes"]
    assert notes[gate.ALL_ZERO_REASON] == (
        "no error and no yardstick, not a failure: the model and the CFD agree exactly and "
        "the yardstick is zero"
    )


def test_a_component_with_no_applicable_yardstick_never_passes():
    out = gate.component_verdicts(
        {"h1": {s: {"full": 0.0, "window": 0.0} for s in range(5)}},
        {
            "h1": {
                "grid_gci": {"not_applicable": True},
                "late_beat": {"unavailable": gate.UNAVAILABLE_LATE},
            }
        },
    )
    assert out == {"status": "no_yardstick"}


def test_late_beat_adds_the_combined_yardsticks_for_the_peaks():
    block = _block(late=0.02)
    normal = block["entries"]["mlp_h1"]["components"]["normal_peak"]
    assert "late_beat" in normal and "beat1_vs_beat2" in normal
    q = normal["grid_gci_late_quadrature"]
    assert q["yardstick"]["h1"] == pytest.approx(
        np.hypot(gate.GCI_FINE["normal_peak"], 0.02), rel=1e-12
    )
    lin = normal["grid_gci_late_linear"]
    assert lin["yardstick"]["h1"] == pytest.approx(
        gate.GCI_FINE["normal_peak"] + 0.02, rel=1e-12
    )
    assert (
        "grid_gci_late_quadrature"
        not in block["entries"]["mlp_h1"]["components"]["CF_mx"]
    )


def test_the_wrap_reason_is_computed_from_the_recorded_jumps():
    reason = _block()["reasons"][-1]
    assert "4.6 %" in reason and "3.0 %" in reason and "0.055" in reason
    changed = _block(
        jumps={
            "h1": {"normal_peak": {"last_but_one": 0.01}},
            "t1": {"normal_peak": {"last_but_one": 0.02}},
        }
    )["reasons"][-1]
    assert changed != reason and "2.0 %" in changed


def test_holdout_status_and_the_no_clean_entry_statement():
    block = _block(
        holdouts={"mlp_h1": {"holdout_informed": True, "holdout_reason": "weakly"}}
    )
    entry = block["entries"]["mlp_h1"]
    assert entry["holdout_informed"] is True and entry["holdout_reason"] == "weakly"
    assert "holdout-clean" in block["holdout_statement"]
