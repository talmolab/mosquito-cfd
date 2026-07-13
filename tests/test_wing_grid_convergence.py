"""Cluster-free tests for the report-only wing grid-convergence grader (Tier T3a).

Covers the 2-grid order-band GCI known-answer (both orders p=1..2 load-bearing), the report-only
contract (no ``*_pass``/``*_match``/``converged`` verdict, no ``cf_exact`` Richardson extrapolant, no
loosenable tolerance constant), the degenerate/sign-flip guards, and the end-to-end reuse of the T2a
body-frame stack (``reconstruct_wing_body_forces`` + ``body_frame_overall_match``). Pure numpy/pandas.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.flapping_wing import (
    _DEGENERATE_CF_FLOOR,
    STEADY_WINDOW_T0,
    reconstruct_wing_body_forces,
)
from mosquito_cfd.benchmarks.wing_convergence import (
    wing_grid_convergence,
    wing_grid_convergence_3grid,
    wing_grid_convergence_from_body_forces,
)

_NEWCONV_CSV = Path("examples/flapping_wing/forces_t2a_newconv.csv")
_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0, "pitch_amp_deg": 45.0}

_EXPECTED_KEYS = {"cf_coarse", "cf_medium", "relative_change", "gci_p1", "gci_p2", "r"}
_FORBIDDEN_KEYS = (
    "verdict",
    "converged",
    "in_band",
    "pass",
    "cf_pass",
    "cf_match",
    "match",
    "cf_exact",
    "richardson",
    "assumed_p",
    "observed_p",
)


def test_wing_grid_convergence_known_answer():
    """The 2-grid order-band GCI reproduces the hand-computed values; both orders are load-bearing.

    coarse 0.92 / medium 0.80 (r=2, Fs=1.25): relative_change = (0.80-0.92)/0.80 = -0.15,
    gci_p1 = 1.25*0.15/(2^1-1) = 0.1875, gci_p2 = 1.25*0.15/(2^2-1) = 0.0625. p=1 is 3x p=2, so a
    hard-coded /3 (single p=2) would fail gci_p1 and a hard-coded /1 would fail gci_p2.
    """
    out = wing_grid_convergence(0.92, 0.80, r=2.0, safety_factor=1.25)

    rel = (0.80 - 0.92) / 0.80  # bit-identical to the implementation's expression
    assert out["relative_change"] == rel
    assert out["relative_change"] == pytest.approx(-0.15)
    assert out["gci_p1"] == pytest.approx(1.25 * abs(rel) / (2**1 - 1))
    assert out["gci_p2"] == pytest.approx(1.25 * abs(rel) / (2**2 - 1))
    assert out["gci_p1"] == pytest.approx(0.1875)
    assert out["gci_p2"] == pytest.approx(0.0625)
    # Both orders are genuinely computed (p=1 uncertainty is exactly 3x p=2 at r=2).
    assert out["gci_p1"] == pytest.approx(3.0 * out["gci_p2"])
    assert out["cf_coarse"] == 0.92
    assert out["cf_medium"] == 0.80
    assert out["r"] == 2.0


def test_wing_grid_convergence_is_report_only():
    """The return dict is exactly the reported quantities — no verdict, no Richardson extrapolant."""
    out = wing_grid_convergence(0.92, 0.80)
    assert set(out) == _EXPECTED_KEYS
    for forbidden in _FORBIDDEN_KEYS:
        assert forbidden not in out
    # No module-level loosenable convergence tolerance constant to relax (report-only, CC-V2).
    import mosquito_cfd.benchmarks.wing_convergence as wc

    for attr in dir(wc):
        upper = attr.upper()
        assert not (("TOL" in upper or "THRESHOLD" in upper) and "CONVERG" in upper), (
            f"report-only grader must define no convergence tolerance constant; found {attr}"
        )


def test_wing_grid_convergence_guards():
    """A near-zero cf_medium raises ValueError (not ZeroDivisionError/nan); a sign flip stays finite."""
    # Denominator below the degeneracy floor -> clear ValueError, never a silent nan/inf/garbage.
    tiny = _DEGENERATE_CF_FLOOR / 10.0
    with pytest.raises(ValueError, match=r"cf_medium|degenerate"):
        wing_grid_convergence(0.5, tiny)
    # The floor is INCLUSIVE (`<=`): a denominator exactly AT the floor still gives a ~1/floor
    # huge-finite ratio, the exact "silent garbage" the spec forbids, so it must raise too.
    with pytest.raises(ValueError, match=r"cf_medium|degenerate"):
        wing_grid_convergence(0.5, _DEGENERATE_CF_FLOOR)
    with pytest.raises(ValueError, match=r"cf_medium|degenerate"):
        wing_grid_convergence(
            0.5, -_DEGENERATE_CF_FLOOR
        )  # negative side of the floor too

    # Opposite-sign pair (a coefficient that flips under refinement): honestly "not converged",
    # returns finite report values with |relative_change| > 1 and a large finite GCI band — no error.
    out = wing_grid_convergence(0.5, -0.4)
    assert np.isfinite(out["relative_change"])
    assert abs(out["relative_change"]) > 1.0
    assert np.isfinite(out["gci_p1"]) and np.isfinite(out["gci_p2"])
    assert out["gci_p1"] > out["gci_p2"] > 0.0


def test_wing_grid_convergence_rejects_nonfinite_and_bad_ratio():
    """Non-finite inputs, r <= 1, and a negative safety_factor raise (defensive, never silent).

    A NaN ``cf_medium`` must be caught by the finite guard, not slip past ``abs(nan) < floor`` (False)
    into a silent NaN ``relative_change``.
    """
    with pytest.raises(ValueError, match="finite"):
        wing_grid_convergence(np.nan, 0.8)
    with pytest.raises(ValueError, match="finite"):
        wing_grid_convergence(0.9, np.inf)  # non-finite denominator, not just huge
    with pytest.raises(ValueError, match="r must be"):
        wing_grid_convergence(0.92, 0.8, r=1.0)  # r^p - 1 would be 0
    with pytest.raises(ValueError, match="safety_factor"):
        wing_grid_convergence(0.92, 0.8, safety_factor=-0.1)


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_convergence_from_csvs_reuses_body_frame(tmp_path):
    """End-to-end: per-component convergence reconstructs peaks via the reused T2a body-frame stack.

    (a) Self-convergence: same CSV as coarse and medium -> bit-identical peaks -> relative_change == 0
        and gci_p1 == gci_p2 == 0 (exact, not approx).
    (b) Scaled medium: a CSV with only Fx/Fy/Fz scaled by k=0.85 (all other columns preserved) scales
        each body-frame peak by exactly k -> relative_change == (k-1)/k = -0.17647 (NOT k-1), because
        the normalization is by cf_medium = k*cf_coarse.
    """
    # (a) self-convergence
    self_conv = wing_grid_convergence_from_body_forces(
        _NEWCONV_CSV, _NEWCONV_CSV, window_t0=STEADY_WINDOW_T0, **_KIN
    )
    for comp in ("cf_chord", "cf_normal"):
        assert self_conv[comp]["relative_change"] == 0.0
        assert self_conv[comp]["gci_p1"] == 0.0
        assert self_conv[comp]["gci_p2"] == 0.0

    # Sanity: the reconstructed coarse peaks equal the T2a body-frame grader's peaks (reuse, not
    # re-derivation) — the committed run's known CF_chord ~0.92, CF_normal ~2.61.
    assert self_conv["cf_chord"]["cf_coarse"] == pytest.approx(0.923, abs=0.02)
    assert self_conv["cf_normal"]["cf_coarse"] == pytest.approx(2.606, abs=0.02)

    # (b) scaled medium — scale ONLY Fx/Fy/Fz by k, preserve every one of the 29 columns.
    k = 0.85
    df = pd.read_csv(_NEWCONV_CSV)
    n_cols_before = df.shape[1]
    for col in ("Fx", "Fy", "Fz"):
        df[col] = df[col] * k
    scaled = tmp_path / "forces_scaled.csv"
    df.to_csv(scaled, index=False)
    assert pd.read_csv(scaled).shape[1] == n_cols_before == 29  # all columns preserved

    out = wing_grid_convergence_from_body_forces(
        _NEWCONV_CSV, scaled, window_t0=STEADY_WINDOW_T0, **_KIN
    )
    for comp in ("cf_chord", "cf_normal"):
        # cf_medium = k * cf_coarse -> relative_change = (k-1)/k, NOT (k-1).
        assert out[comp]["cf_medium"] == pytest.approx(
            k * out[comp]["cf_coarse"], rel=1e-9
        )
        assert out[comp]["relative_change"] == pytest.approx((k - 1) / k)
        assert out[comp]["relative_change"] == pytest.approx(-0.17647, abs=1e-4)
        assert out[comp]["relative_change"] != pytest.approx(k - 1)  # not -0.15


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_convergence_from_csvs_is_report_only():
    """The per-component end-to-end result carries only the report-only grader dict per component."""
    out = wing_grid_convergence_from_body_forces(
        _NEWCONV_CSV, _NEWCONV_CSV, window_t0=STEADY_WINDOW_T0, **_KIN
    )
    assert set(out) == {"cf_chord", "cf_normal"}
    for comp in ("cf_chord", "cf_normal"):
        assert set(out[comp]) == _EXPECTED_KEYS
        for forbidden in _FORBIDDEN_KEYS:
            assert forbidden not in out[comp]


@pytest.mark.skipif(
    not _NEWCONV_CSV.exists(), reason="new-convention forces CSV not present"
)
def test_from_body_forces_actually_reuses_reconstruct(tmp_path):
    """The helper's coarse peaks equal an independent reconstruct_wing_body_forces call (reuse proof)."""
    decomp = reconstruct_wing_body_forces(_NEWCONV_CSV, **_KIN)
    mask = decomp.time >= STEADY_WINDOW_T0
    peak_chord = float(np.abs(decomp.cf_chord[mask]).max())
    peak_normal = float(np.abs(decomp.cf_normal[mask]).max())
    out = wing_grid_convergence_from_body_forces(
        _NEWCONV_CSV, _NEWCONV_CSV, window_t0=STEADY_WINDOW_T0, **_KIN
    )
    assert out["cf_chord"]["cf_coarse"] == pytest.approx(peak_chord, abs=1e-9)
    assert out["cf_normal"]["cf_coarse"] == pytest.approx(peak_normal, abs=1e-9)


# ---------------------------------------------------------------------------
# 3-grid convergence tests (T3c, tasks 1.1.1 – 1.1.5)
# ---------------------------------------------------------------------------

_3GRID_EXPECTED_KEYS = {
    "cf_coarse",
    "cf_medium",
    "cf_fine",
    "observed_order",
    "cf_exact_richardson",
    "gci_fine",
    "r",
    "monotone",
}
_3GRID_FORBIDDEN_KEYS = (
    "verdict",
    "converged",
    "in_band",
    "pass",
    "cf_pass",
    "cf_match",
    "match",
    "relative_change",
    "gci_p1",
    "gci_p2",
)


def test_wing_grid_convergence_3grid_known_answer():
    """Exact p=2 synthetic triple reproduces the hand-computed order and Richardson extrapolant.

    cf_coarse=1.0, cf_medium=0.25, cf_fine=0.0625 with r=2:
      δ₁₂ = 0.25 - 1.0 = -0.75, δ₂₃ = 0.0625 - 0.25 = -0.1875
      |δ₁₂/δ₂₃| = 4 = 2², p_obs = log(4)/log(2) = 2.0 exactly
      cf_exact = 0.0625 + (-0.1875)/(2²-1) = 0.0625 - 0.0625 = 0.0
    """
    out = wing_grid_convergence_3grid(1.0, 0.25, 0.0625, r=2.0)

    assert out["observed_order"] == pytest.approx(2.0)
    assert out["cf_exact_richardson"] == pytest.approx(0.0)
    assert out["monotone"] is True
    assert np.isfinite(out["gci_fine"])
    assert out["gci_fine"] > 0.0
    assert out["r"] == 2.0
    assert out["cf_coarse"] == pytest.approx(1.0)
    assert out["cf_medium"] == pytest.approx(0.25)
    assert out["cf_fine"] == pytest.approx(0.0625)
    # No verdict/pass keys.
    for forbidden in _3GRID_FORBIDDEN_KEYS:
        assert forbidden not in out


def test_wing_grid_convergence_3grid_self_convergence():
    """Self-convergent triple (same value on all three grids): monotone=True, NaN outputs.

    δ₂₃ = 0 → degenerate denominator → p_obs=NaN, cf_exact=NaN, gci_fine=NaN.
    Must not raise.
    """
    out = wing_grid_convergence_3grid(0.5, 0.5, 0.5)

    assert out["monotone"] is True
    assert np.isnan(out["observed_order"])
    assert np.isnan(out["cf_exact_richardson"])
    assert np.isnan(out["gci_fine"])


def test_wing_grid_convergence_3grid_negative_order():
    """Monotone but decelerating: p_obs < 0 → observed_order returned as-is, GCI/Richardson NaN.

    cf_coarse=1.0, cf_medium=0.9, cf_fine=0.5:
      δ₁₂ = -0.1, δ₂₃ = -0.4, |δ₁₂/δ₂₃| = 0.25
      p_obs = log(0.25)/log(2) = -2.0 — monotone but decelerating.
      r**p_obs - 1 = 2**(-2) - 1 = -0.75 ≤ 0 → denominator guard fires → NaN.
    """
    out = wing_grid_convergence_3grid(1.0, 0.9, 0.5)

    assert out["monotone"] is True
    assert out["observed_order"] == pytest.approx(-2.0)
    assert np.isnan(out["gci_fine"])
    assert np.isnan(out["cf_exact_richardson"])


def test_wing_grid_convergence_3grid_zero_order():
    """Equal deltas → p_obs ≈ 0 → denominator guard fires → GCI/Richardson NaN.

    cf_coarse=1.0, cf_medium=0.75, cf_fine=0.5:
      δ₁₂ = -0.25, δ₂₃ = -0.25, ratio = 1.0
      p_obs = log(1.0)/log(2) = 0.0 → r**0 - 1 = 0 → near-zero guard → NaN.
    Must not raise.
    """
    out = wing_grid_convergence_3grid(1.0, 0.75, 0.5)

    assert out["monotone"] is True
    assert np.isnan(out["gci_fine"])
    assert np.isnan(out["cf_exact_richardson"])


def test_wing_grid_convergence_3grid_non_monotone():
    """Oscillating triple: went down then up → monotone=False, all NaN, never ValueError.

    cf_coarse=1.0, cf_medium=0.5, cf_fine=0.8:
      δ₁₂ = -0.5 (negative), δ₂₃ = +0.3 (positive) → opposite signs → non-monotone.
    """
    out = wing_grid_convergence_3grid(1.0, 0.5, 0.8)

    assert out["monotone"] is False
    assert np.isnan(out["observed_order"])
    assert np.isnan(out["cf_exact_richardson"])
    assert np.isnan(out["gci_fine"])


def test_wing_grid_convergence_3grid_degenerate():
    """Degenerate inputs raise ValueError, never silent NaN/garbage."""
    # cf_fine at or below the degeneracy floor → ValueError("degenerate")
    from mosquito_cfd.benchmarks.flapping_wing import _DEGENERATE_CF_FLOOR

    with pytest.raises(ValueError, match="degenerate"):
        wing_grid_convergence_3grid(1.0, 0.5, 0.0)

    with pytest.raises(ValueError, match="degenerate"):
        wing_grid_convergence_3grid(1.0, 0.5, _DEGENERATE_CF_FLOOR)

    # Non-finite inputs → ValueError
    with pytest.raises(ValueError, match="finite"):
        wing_grid_convergence_3grid(np.nan, 0.5, 0.25)

    with pytest.raises(ValueError, match="finite"):
        wing_grid_convergence_3grid(1.0, np.inf, 0.25)

    # r <= 1 → ValueError
    with pytest.raises(ValueError, match="r must be"):
        wing_grid_convergence_3grid(1.0, 0.5, 0.25, r=1.0)


def test_wing_grid_convergence_3grid_key_set():
    """Return dict is exactly the report-only key set — no verdict, no 2-grid keys."""
    out = wing_grid_convergence_3grid(1.0, 0.25, 0.0625)

    assert set(out) == _3GRID_EXPECTED_KEYS
    for forbidden in _3GRID_FORBIDDEN_KEYS:
        assert forbidden not in out
    assert out["r"] == 2.0
    assert isinstance(out["monotone"], bool)
