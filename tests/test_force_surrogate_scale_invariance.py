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


# Pinned SHA256 of the committed raw force/moment columns (Fx..Mz). The Track-B
# re-derivation freezes these — a future regeneration that disturbs the raw CFD forces
# (not just the derived CF) would change this digest and fail the test.
# NOTE: `pd.util.hash_pandas_object` is value-based but pandas-major-version coupled. pandas
# is pinned in uv.lock, so this is stable in CI; if pandas is upgraded and this digest trips
# on unchanged data, re-pin it (it is a corpus tripwire, not phantom data corruption).
_FROZEN_RAW_FORCE_SHA = (
    "d709c6cd458b47f037652a8719deeb68c70c314077bcddb3a26224a9b26de41d"
)


def test_committed_corpus_cf_is_van_veen_consistent():
    """Every distinct config's CF_* equals raw force / per-config van Veen f_ref.

    Scenario: Raw corpus stays frozen; only derived coefficients move. Covers ALL distinct
    (stroke, freq) keys (f_ref ∝ stroke², so a stroke-dependent bug must not slip through),
    using a vectorized per-config check.
    """
    import hashlib

    from mosquito_cfd.force_surrogate import compute_moment_reference

    df = pd.read_parquet("examples/prelim_sweep/dataset.parquet")
    keys = df.drop_duplicates(["stroke_amp_deg", "frequency_fstar"])[
        ["stroke_amp_deg", "frequency_fstar"]
    ]
    assert len(keys) == 9  # the full 3x3 (stroke x freq) grid
    for stroke, freq in keys.itertuples(index=False):
        sub = df[(df["stroke_amp_deg"] == stroke) & (df["frequency_fstar"] == freq)]
        f_ref = compute_force_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).f_ref
        m_ref = compute_moment_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).m_ref
        np.testing.assert_allclose(sub["CF_x"], sub["Fx"] / f_ref, rtol=1e-9)
        np.testing.assert_allclose(sub["CF_z"], sub["Fz"] / f_ref, rtol=1e-9)
        np.testing.assert_allclose(sub["CF_my"], sub["My"] / m_ref, rtol=1e-9)

    # Raw force/moment columns are frozen (only derived CF columns were re-derived).
    raw = df[["Fx", "Fy", "Fz", "Mx", "My", "Mz"]]
    raw_sha = hashlib.sha256(
        pd.util.hash_pandas_object(raw, index=False).values.tobytes()
    ).hexdigest()
    assert raw_sha == _FROZEN_RAW_FORCE_SHA, (
        "raw CFD forces changed — they must stay frozen"
    )


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
