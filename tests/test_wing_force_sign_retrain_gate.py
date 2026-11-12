"""Pre-registered retrain gate for fix-wing-force-sign-convention (#109), design D7 G3 and G4.

These literals were committed **before** the GPU retrain, so the gate is fixed before its outcome
is known and survives CI's depth-1 checkout. They are the pre-change (``a2e8f64``) committed
values: each corpus's 5-seed ``seed_sweep.range.<target>.skill`` interval, and the evidence-figure
sidecar's sign-invariant quasi-steady reference.

Retraining on the negated targets equals retraining on the old targets with the output layer's
initial weights and bias negated (G0, ``test_force_surrogate_train_gpu.py``), so the retrained
networks are new draws. G3 therefore asks only that each new 5-seed range intersect the old one,
never that a single seed reproduce. Config-resolved R² is not gated.

A later change that legitimately retrains (#114, #125) MAY retire these tests through its own
OpenSpec proposal; they belong to fix-wing-force-sign-convention.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.evidence_figure import _baseline_reference
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS

REPO = Path(__file__).resolve().parents[1]
COARSE = REPO / "examples" / "prelim_sweep"
FINE = REPO / "examples" / "prelim_sweep_fine"
GRID = {COARSE: "coarse", FINE: "fine"}

# sha256 of each corpus's pre-change (a2e8f64) dataset.parquet, the stale surrogate's inputs.hash.
PRE_CHANGE_DATASET_SHA = {
    COARSE: "01c88ae908b85616f0335583a9ca8e27eb9b660574244981f44333883eb40afa",
    FINE: "2092f0fd05a60e706667b22848c46f7ce6608309b2021b02940c606856bd26a9",
}

# G3: a2e8f64 seed_sweep.range.<target>.skill as (min, max), seeds 1234-1238.
PRE_CHANGE_SKILL_RANGE = {
    COARSE: {
        "CF_x": (0.9878643917804139, 0.9923201760348408),
        "CF_y": (0.9744095516037377, 0.984431230555837),
        "CF_z": (0.9838098377643206, 0.9902290456972815),
        "CF_mx": (0.9731657705986549, 0.9895178464470501),
        "CF_my": (0.9698341418672275, 0.9841863475193975),
        "CF_mz": (0.9832180073641285, 0.9911490791595372),
    },
    FINE: {
        "CF_x": (0.989776816135081, 0.9959668308245451),
        "CF_y": (0.9799977959566399, 0.9937001503623268),
        "CF_z": (0.9770005294841001, 0.9905410344266189),
        "CF_mx": (0.9684980816883039, 0.9925529168914591),
        "CF_my": (0.974752053929043, 0.9864361810445282),
        "CF_mz": (0.9865312487753023, 0.99508971650889),
    },
}

# G4: overshoot_factor is an RMS ratio, so a sign flip leaves it bit-identical. The quasi-steady
# RMSE drops because the quasi-steady lift and the CFD lift now share a sign.
OVERSHOOT_FACTOR = {COARSE: 1.3435407346470738, FINE: 1.4074274138248275}
BASELINE_RMSE_CF_Z_4DP = {COARSE: 0.5175, FINE: 0.4782}


def _corpora():
    return pytest.mark.parametrize(
        "corpus",
        [pytest.param(COARSE, id="coarse"), pytest.param(FINE, id="fine")],
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _meta(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check_trained_on_current_dataset(
    inputs_hash: str, *, current: str, pinned: str
) -> None:
    """The surrogate hashes the committed dataset, and that is not the pre-change one.

    The second clause stops G3 passing vacuously on the stale surrogate, whose ranges are the
    literals themselves.
    """
    assert inputs_hash == current, "the surrogate was not trained on dataset.parquet"
    assert inputs_hash != pinned, "the surrogate is still the pre-change one"


def check_skill_ranges_overlap(
    seed_range: dict, pre_change: dict[str, tuple[float, float]]
) -> None:
    """For every target, the new 5-seed skill range intersects the pre-change one (touching counts)."""
    for target in TARGET_COLUMNS:
        new = seed_range[target]["skill"]
        lo, hi = pre_change[target]
        assert new["min"] <= new["max"], f"{target}: inverted range"
        assert new["min"] <= hi and lo <= new["max"], (
            f"{target}: new skill range [{new['min']}, {new['max']}] is disjoint from the "
            f"pre-change [{lo}, {hi}] (G3: halt for a decision)"
        )


def check_quasi_steady_reference(
    sidecar_qs: dict, recomputed: dict, *, overshoot: float, rmse_4dp: float
) -> None:
    """G4: exact overshoot factor, recomputable RMSE, and the pre-registered 4-dp RMSE."""
    assert sidecar_qs["overshoot_factor"] == overshoot
    assert sidecar_qs["baseline_rmse_cf_z"] == pytest.approx(
        recomputed["baseline_rmse_cf_z"], rel=1e-12
    )
    assert round(sidecar_qs["baseline_rmse_cf_z"], 4) == rmse_4dp


# --- G3 / G4 on the committed artifacts (red until the retrain, then the figures) -----------


@_corpora()
def test_retrained_surrogate_is_trained_on_the_current_dataset(corpus):
    """G3 non-vacuity: inputs.hash == sha256(dataset.parquet) != the pre-change sha."""
    inputs = _meta(corpus / "surrogate" / "run_metadata.json")["inputs"]
    check_trained_on_current_dataset(
        inputs["hash"],
        current=_sha256(corpus / "dataset.parquet"),
        pinned=PRE_CHANGE_DATASET_SHA[corpus],
    )


@_corpora()
def test_retrained_skill_ranges_overlap_the_pre_change_ranges(corpus):
    """G3: each of the six new 5-seed skill ranges intersects its a2e8f64 interval."""
    metrics = _meta(corpus / "surrogate" / "metrics.json")
    check_trained_on_current_dataset(
        _meta(corpus / "surrogate" / "run_metadata.json")["inputs"]["hash"],
        current=_sha256(corpus / "dataset.parquet"),
        pinned=PRE_CHANGE_DATASET_SHA[corpus],
    )
    assert metrics["seed_sweep"]["seeds"] == [1234, 1235, 1236, 1237, 1238]
    check_skill_ranges_overlap(
        metrics["seed_sweep"]["range"], PRE_CHANGE_SKILL_RANGE[corpus]
    )


@_corpora()
def test_regenerated_quasi_steady_reference_is_sign_consistent(corpus):
    """G4: overshoot_factor exact; baseline_rmse_cf_z recomputes (rel 1e-12) and rounds as pinned."""
    sidecar = _meta(corpus / "figures" / "evidence_figure_metrics.json")
    holdout = pd.read_parquet(corpus / "surrogate" / "holdout_predictions.parquet")
    check_quasi_steady_reference(
        sidecar["quasi_steady_reference"],
        _baseline_reference(holdout, grid=GRID[corpus]),
        overshoot=OVERSHOOT_FACTOR[corpus],
        rmse_4dp=BASELINE_RMSE_CF_Z_4DP[corpus],
    )


# --- The checks on synthetic inputs (each must fail on its defect) ---------------------------

_GOOD_RANGE = {
    c: {"skill": {"min": lo, "max": hi}}
    for c, (lo, hi) in PRE_CHANGE_SKILL_RANGE[COARSE].items()
}


def _shifted(target: str, lo: float, hi: float) -> dict:
    out = {c: {"skill": dict(v["skill"])} for c, v in _GOOD_RANGE.items()}
    out[target]["skill"] = {"min": lo, "max": hi}
    return out


def test_overlap_check_accepts_overlapping_and_touching_ranges():
    check_skill_ranges_overlap(_GOOD_RANGE, PRE_CHANGE_SKILL_RANGE[COARSE])
    lo, hi = PRE_CHANGE_SKILL_RANGE[COARSE]["CF_y"]
    check_skill_ranges_overlap(
        _shifted("CF_y", hi, hi + 0.01), PRE_CHANGE_SKILL_RANGE[COARSE]
    )
    check_skill_ranges_overlap(
        _shifted("CF_y", lo - 0.01, lo), PRE_CHANGE_SKILL_RANGE[COARSE]
    )


@pytest.mark.parametrize("side", ["above", "below"])
@pytest.mark.parametrize("target", TARGET_COLUMNS)
def test_overlap_check_rejects_a_disjoint_range(target, side):
    lo, hi = PRE_CHANGE_SKILL_RANGE[COARSE][target]
    eps = 1e-12
    bad = (hi + eps, hi + 0.01) if side == "above" else (lo - 0.01, lo - eps)
    with pytest.raises(AssertionError, match=target):
        check_skill_ranges_overlap(
            _shifted(target, *bad), PRE_CHANGE_SKILL_RANGE[COARSE]
        )


def test_overlap_check_rejects_an_inverted_range():
    """An inverted range lying inside the old interval would pass the intersection alone."""
    lo, hi = PRE_CHANGE_SKILL_RANGE[COARSE]["CF_z"]
    mid = (lo + hi) / 2
    with pytest.raises(AssertionError, match="CF_z"):
        check_skill_ranges_overlap(
            _shifted("CF_z", mid + 0.001, mid - 0.001), PRE_CHANGE_SKILL_RANGE[COARSE]
        )


def test_dataset_identity_check_rejects_stale_and_foreign_hashes():
    cur, pinned = "a" * 64, PRE_CHANGE_DATASET_SHA[COARSE]
    check_trained_on_current_dataset(cur, current=cur, pinned=pinned)
    with pytest.raises(AssertionError, match="pre-change"):
        check_trained_on_current_dataset(pinned, current=pinned, pinned=pinned)
    with pytest.raises(AssertionError, match="not trained"):
        check_trained_on_current_dataset("b" * 64, current=cur, pinned=pinned)


@pytest.mark.parametrize(
    "defect",
    ["overshoot one ulp off", "rmse not recomputable", "rmse rounds differently"],
)
def test_quasi_steady_check_rejects_each_defect(defect):
    good = {
        "overshoot_factor": 1.3435407346470738,
        "baseline_rmse_cf_z": 0.5174799075783006,
    }
    recomputed = {"baseline_rmse_cf_z": 0.5174799075783006}
    kwargs = {"overshoot": 1.3435407346470738, "rmse_4dp": 0.5175}
    check_quasi_steady_reference(good, recomputed, **kwargs)
    bad, rec = dict(good), dict(recomputed)
    if defect == "overshoot one ulp off":
        bad["overshoot_factor"] = 1.3435407346470740
    elif defect == "rmse not recomputable":
        rec["baseline_rmse_cf_z"] = 0.51748
    else:
        bad["baseline_rmse_cf_z"] = rec["baseline_rmse_cf_z"] = 0.51756
    with pytest.raises(AssertionError):
        check_quasi_steady_reference(bad, rec, **kwargs)
