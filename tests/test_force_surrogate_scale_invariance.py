"""Scale-invariance guard for the van Veen re-normalization (CPU-only, cluster-free).

Re-deriving the corpus coefficients under a different per-config convention multiplies
BOTH the CFD target and the surrogate prediction by the same constant
``k = f_ref_old / f_ref_new``. R^2 is invariant under that common rescale (RMSE/MAE
scale by ``k``), so the held-out skill is unchanged and no retrain is needed. This pins
that property on the committed ``holdout_predictions.parquet`` (proves Track-B re-deriva-
tion is safe). See openspec/changes/standardize-force-normalization (Task B / scenario
"R^2 is invariant under re-normalization").
"""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import (
    compute_force_coefficients,
    compute_force_reference,
)
from mosquito_cfd.force_surrogate.constants import (
    CHORD,
    R_GYRATION,
    R_TIP,
    RHO,
    SPAN,
)
from mosquito_cfd.force_surrogate.train import _r2

_PRED = Path("examples/prelim_sweep/surrogate/holdout_predictions.parquet")

# Convention factor k = f_ref_old / f_ref_new = (R_TIP / R_GYRATION)^2 ~= 3.119.
# Both references come from the single-source helper (old = tip arm, new = gyration arm).
_F_REF_OLD = compute_force_reference(1.0, 70.0, R_TIP, SPAN, CHORD, RHO).f_ref
_F_REF_NEW = compute_force_reference(1.0, 70.0, R_GYRATION, SPAN, CHORD, RHO).f_ref
_K = _F_REF_OLD / _F_REF_NEW


def test_convention_factor_is_geometry_ratio():
    """k = f_ref_old/f_ref_new equals (R_TIP/R_GYRATION)^2 ~= 3.119."""
    assert _K == pytest.approx((R_TIP / R_GYRATION) ** 2, rel=1e-12)
    assert _K == pytest.approx(3.119, rel=1e-3)


@pytest.mark.parametrize("coef", ["CF_x", "CF_z"])
def test_r2_invariant_under_renormalization(coef):
    """Scaling true and pred by the same k leaves R^2 unchanged; RMSE scales by k."""
    df = pd.read_parquet(_PRED)
    y = df[f"{coef}_true"].to_numpy(dtype=float)
    yhat = df[f"{coef}_pred"].to_numpy(dtype=float)

    r2_before = _r2(y, yhat)
    r2_after = _r2(y * _K, yhat * _K)
    assert r2_after == pytest.approx(r2_before, abs=1e-9)

    rmse_before = float(np.sqrt(np.mean((y - yhat) ** 2)))
    rmse_after = float(np.sqrt(np.mean((y * _K - yhat * _K) ** 2)))
    assert rmse_after == pytest.approx(_K * rmse_before, rel=1e-9)


@pytest.mark.parametrize("coef", ["CF_x", "CF_z"])
def test_unscaled_r2_matches_committed_metrics(coef):
    """The committed predictions reproduce metrics.json R^2 (the baseline being preserved)."""
    import json

    df = pd.read_parquet(_PRED)
    metrics = json.loads(
        (Path("examples/prelim_sweep/surrogate/metrics.json")).read_text()
    )
    y = df[f"{coef}_true"].to_numpy(dtype=float)
    yhat = df[f"{coef}_pred"].to_numpy(dtype=float)
    assert _r2(y, yhat) == pytest.approx(metrics["per_target"][coef]["r2"], abs=1e-9)


def test_committed_corpus_cf_is_van_veen_consistent():
    """The re-derived dataset.parquet CF_* equal raw force / per-config van Veen f_ref.

    Scenario: Raw corpus stays frozen; only derived coefficients move. This is the durable
    invariant after the Task-B re-derivation: every CF column is the van Veen
    normalization of the (unchanged) raw force column, so CF and raw forces are mutually
    consistent under the new convention.
    """
    from mosquito_cfd.force_surrogate import compute_moment_reference

    df = pd.read_parquet("examples/prelim_sweep/dataset.parquet")
    # check a sample of distinct configs (one per (stroke, freq) is enough)
    seen = set()
    for _, row in df.iterrows():
        key = (row["stroke_amp_deg"], row["frequency_fstar"])
        if key in seen:
            continue
        seen.add(key)
        f_ref = compute_force_reference(
            row["frequency_fstar"], row["stroke_amp_deg"], R_GYRATION, SPAN, CHORD, RHO
        ).f_ref
        m_ref = compute_moment_reference(
            row["frequency_fstar"], row["stroke_amp_deg"], R_GYRATION, SPAN, CHORD, RHO
        ).m_ref
        assert row["CF_x"] == pytest.approx(row["Fx"] / f_ref, rel=1e-9)
        assert row["CF_z"] == pytest.approx(row["Fz"] / f_ref, rel=1e-9)
        assert row["CF_my"] == pytest.approx(row["My"] / m_ref, rel=1e-9)
        if len(seen) >= 5:
            break
    assert len(seen) >= 5


def test_degenerate_renormalization_is_rejected():
    """A zero new reference (k undefined) or a missing column is rejected, not inf/NaN.

    Scenario: Degenerate re-normalization is rejected. Re-normalizing by ``f_ref_new = 0``
    is rejected by the single-source coefficient helper (parity with non-positive f_ref);
    a missing predicted/target column raises KeyError rather than silently skipping.
    """
    with pytest.raises(ValueError):
        compute_force_coefficients(1.0, 2.0, 3.0, 0.0)  # f_ref_new = 0 -> k undefined
    df = pd.read_parquet(_PRED)
    with pytest.raises(KeyError):
        _ = df["CF_q_true"]  # absent target column
