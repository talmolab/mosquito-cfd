"""Tier T3b — grade the medium-grid convergence on the committed coarse+medium CSVs (report-only).

Covers the pre-grade gradeability guard (``assert_gradeable_pair``) and the end-to-end report-only
convergence on the real committed data. The grader math itself is T3a's (tested in
``test_wing_grid_convergence.py``); T3b only *applies* it and guards the inputs.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.wing_convergence import (
    assert_gradeable_pair,
    assert_gradeable_triple,
    wing_grid_convergence_from_body_forces,
)

_COARSE_CSV = Path("examples/flapping_wing/forces_t2a_newconv.csv")
_MEDIUM_CSV = Path("examples/flapping_wing/forces_medium.csv")
_COARSE_DECK = Path("examples/flapping_wing/inputs.3d.validation")
_MEDIUM_DECK = Path("examples/flapping_wing/inputs.3d.convergence_medium")

_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)
_REPORT_ONLY_KEYS = {
    "cf_coarse",
    "cf_medium",
    "relative_change",
    "gci_p1",
    "gci_p2",
    "r",
}


@pytest.mark.skipif(not _COARSE_CSV.exists(), reason="coarse CSV not present")
def test_assert_gradeable_pair_guards(tmp_path):
    """The pre-grade guard fails loudly on empty / truncated / dt-reduced pairs, passes a valid one."""
    coarse = pd.read_csv(_COARSE_CSV)

    # (a) header-only medium CSV -> "no data rows"
    header_only = tmp_path / "header_only.csv"
    header_only.write_text(",".join(coarse.columns) + "\n")
    with pytest.raises(ValueError, match="no data rows"):
        assert_gradeable_pair(_COARSE_CSV, header_only)

    # (b) medium truncated to t <= 0.5 -> "window"
    truncated = tmp_path / "truncated.csv"
    coarse[coarse["time"] <= 0.5].to_csv(truncated, index=False)
    with pytest.raises(ValueError, match="window"):
        assert_gradeable_pair(_COARSE_CSV, truncated)

    # (c) dt-halved medium (twice as many distinct iStep, same endpoint) -> "time-grid"
    dt_halved = tmp_path / "dt_halved.csv"
    n = 4001
    df = pd.DataFrame({c: np.zeros(n) for c in coarse.columns})
    df["iStep"] = np.arange(n)
    df["time"] = np.arange(n) * 2.5e-4  # reaches 1.0 at step 4000, finer grid
    df.to_csv(dt_halved, index=False)
    with pytest.raises(ValueError, match="time-grid"):
        assert_gradeable_pair(_COARSE_CSV, dt_halved)

    # (d) the committed coarse-vs-coarse pair passes despite the 3 duplicate t=0 init rows
    assert (
        assert_gradeable_pair(
            _COARSE_CSV, _COARSE_CSV, coarse_deck=_COARSE_DECK, medium_deck=_COARSE_DECK
        )
        is None
    )


@pytest.mark.skipif(
    not (_COARSE_CSV.exists() and _MEDIUM_CSV.exists()),
    reason="coarse/medium CSVs not present (T3b run)",
)
def test_medium_convergence_reports_from_committed_csvs():
    """The report-only contract holds on the real coarse<->medium data (no verdict, band load-bearing)."""
    # Guard first (mirrors the RESULTS/reproducibility path), then grade.
    assert_gradeable_pair(
        _COARSE_CSV, _MEDIUM_CSV, coarse_deck=_COARSE_DECK, medium_deck=_MEDIUM_DECK
    )
    out = wing_grid_convergence_from_body_forces(_COARSE_CSV, _MEDIUM_CSV, **_KIN)

    assert set(out) == {"cf_chord", "cf_normal"}
    for comp in ("cf_chord", "cf_normal"):
        v = out[comp]
        # Report-only: EXACTLY the six keys, no verdict/extrapolant.
        assert set(v) == _REPORT_ONLY_KEYS
        assert not any(
            k in v for k in ("converged", "in_band", "cf_exact", "match", "pass")
        )
        assert all(np.isfinite(x) for x in v.values())
        assert v["r"] == 2.0
        # Both orders load-bearing: gci_p1 = 3*gci_p2 at r=2 (a hard-coded /3 would fail the p1 arm).
        assert v["gci_p1"] == pytest.approx(3.0 * v["gci_p2"])

    # The #40 signal: peak CF_chord drops materially under refinement (coarse-grid diffused-IB).
    assert out["cf_chord"]["relative_change"] < 0.0


# ---------------------------------------------------------------------------
# T3c: 3-grid body-forces shape + backward-compat (tasks 1.2.1 and 1.2.2)
# ---------------------------------------------------------------------------

_3GRID_KEYS = {
    "cf_coarse",
    "cf_medium",
    "cf_fine",
    "observed_order",
    "cf_exact_richardson",
    "gci_fine",
    "r",
    "monotone",
}


@pytest.mark.skipif(not _COARSE_CSV.exists(), reason="coarse CSV not present")
def test_wing_grid_convergence_3grid_from_body_forces():
    """The 3-grid body-forces path returns the 3-grid key set per component (task 1.2.1).

    Uses the coarse CSV as all three inputs (coarse = medium = fine = forces_t2a_newconv.csv),
    which produces self-convergence: monotone=True, observed_order=NaN (degenerate δ₂₃=0).
    """
    out = wing_grid_convergence_from_body_forces(
        _COARSE_CSV, _COARSE_CSV, _COARSE_CSV, **_KIN
    )

    assert set(out) == {"cf_chord", "cf_normal"}
    for comp in ("cf_chord", "cf_normal"):
        v = out[comp]
        assert set(v) == _3GRID_KEYS, (
            f"{comp}: expected 3-grid key set, got {sorted(v)}"
        )
        assert v["monotone"] is True
        assert np.isnan(v["observed_order"])  # self-convergence → degenerate
        assert v["r"] == 2.0
        for forbidden in (
            "verdict",
            "converged",
            "pass",
            "relative_change",
            "gci_p1",
            "gci_p2",
        ):
            assert forbidden not in v


@pytest.mark.skipif(not _COARSE_CSV.exists(), reason="coarse CSV not present")
def test_wing_grid_convergence_from_body_forces_unchanged():
    """2-grid path is unchanged when fine_csv=None (explicit) or omitted (task 1.2.2)."""
    # Explicit None
    out_explicit = wing_grid_convergence_from_body_forces(
        _COARSE_CSV, _COARSE_CSV, fine_csv=None, **_KIN
    )
    # Omitted (backward-compat positional call)
    out_omitted = wing_grid_convergence_from_body_forces(
        _COARSE_CSV, _COARSE_CSV, **_KIN
    )

    for out in (out_explicit, out_omitted):
        assert set(out) == {"cf_chord", "cf_normal"}
        for comp in ("cf_chord", "cf_normal"):
            v = out[comp]
            # Must be EXACTLY the 2-grid key set — no 3-grid keys must appear.
            assert set(v) == _REPORT_ONLY_KEYS, (
                f"{comp}: backward-compat 2-grid path must return {sorted(_REPORT_ONLY_KEYS)}, "
                f"got {sorted(v)}"
            )
            for three_grid_key in (
                "observed_order",
                "cf_exact_richardson",
                "gci_fine",
                "monotone",
            ):
                assert three_grid_key not in v


# ---------------------------------------------------------------------------
# T3c: assert_gradeable_triple guard tests (task 1.3.1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _COARSE_CSV.exists(), reason="coarse CSV not present")
def test_assert_gradeable_triple_guards(tmp_path):
    """The 3-grid guard fails loudly on malformed inputs; passes a valid triple (task 1.3.1).

    Uses the committed coarse CSV as a proxy for all three grids (same time grid, same dt).
    Cases:
      (a) header-only fine CSV → "no data rows"
      (b) fine CSV truncated to t<=0.5 → "window"
      (c) fine CSV with dt-halved time grid → "time-grid"
      (d) fine deck has ns.fixed_dt=2.5e-4 (mismatch) → "fixed_dt"
      (e) medium CSV truncated to t=0.5 (valid fine CSV) → "window"
          (composition proof: assert_gradeable_pair(medium, fine) is called, not skipped)
      (f) valid triple (coarse-vs-coarse-vs-coarse) passes without error
    """
    coarse = pd.read_csv(_COARSE_CSV)

    # (a) header-only fine CSV → "no data rows"
    header_only = tmp_path / "header_only.csv"
    header_only.write_text(",".join(coarse.columns) + "\n")
    with pytest.raises(ValueError, match="no data rows"):
        assert_gradeable_triple(_COARSE_CSV, _COARSE_CSV, header_only)

    # (b) fine CSV truncated to t <= 0.5 → "window"
    truncated = tmp_path / "truncated.csv"
    coarse[coarse["time"] <= 0.5].to_csv(truncated, index=False)
    with pytest.raises(ValueError, match="window"):
        assert_gradeable_triple(_COARSE_CSV, _COARSE_CSV, truncated)

    # (c) dt-halved fine CSV (twice as many distinct iStep, same endpoint) → "time-grid"
    dt_halved = tmp_path / "dt_halved.csv"
    n = 4001
    df = pd.DataFrame({c: np.zeros(n) for c in coarse.columns})
    df["iStep"] = np.arange(n)
    df["time"] = np.arange(n) * 2.5e-4  # reaches 1.0 at step 4000
    df.to_csv(dt_halved, index=False)
    with pytest.raises(ValueError, match="time-grid"):
        assert_gradeable_triple(_COARSE_CSV, _COARSE_CSV, dt_halved)

    # (d) fine deck with mismatched dt → "fixed_dt"
    fine_deck_wrong_dt = tmp_path / "fine_deck_wrong_dt.txt"
    fine_deck_wrong_dt.write_text("ns.fixed_dt = 2.5e-4\n")
    with pytest.raises(ValueError, match="fixed_dt"):
        assert_gradeable_triple(
            _COARSE_CSV,
            _COARSE_CSV,
            _COARSE_CSV,
            coarse_deck=_COARSE_DECK,
            medium_deck=_MEDIUM_DECK,
            fine_deck=fine_deck_wrong_dt,
        )

    # (e) medium CSV truncated to t=0.5 (valid fine CSV) → "window"
    # Composition proof: assert_gradeable_pair(medium, fine) checks medium too.
    with pytest.raises(ValueError, match="window"):
        assert_gradeable_triple(_COARSE_CSV, truncated, _COARSE_CSV)

    # (f) valid triple (coarse-vs-coarse-vs-coarse) passes without error.
    assert (
        assert_gradeable_triple(
            _COARSE_CSV,
            _COARSE_CSV,
            _COARSE_CSV,
            coarse_deck=_COARSE_DECK,
            medium_deck=_MEDIUM_DECK,
            fine_deck=_MEDIUM_DECK,  # same dt as medium
        )
        is None
    )
