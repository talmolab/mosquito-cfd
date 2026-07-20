"""Tier T3c — fine-grid 256×128×256 schema pin and provenance tests (skipif CSV absent).

These tests gate on the existence of the fine-grid operator run artifacts:
  ``examples/flapping_wing/forces_fine.csv`` and ``examples/flapping_wing/run_metadata_t3c.json``.

They **skip** in Session A / CI (no fine CSV until after the operator A40 run in Session B)
and **run** in Session B once the data is committed alongside the tests (tasks 1.4.1–1.4.2).
Nothing here runs the solver; all checks are pure file-read assertions.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

_FINE_CSV = Path("examples/flapping_wing/forces_fine.csv")
_FINE_META = Path("examples/flapping_wing/run_metadata_t3c.json")
_FINE_DECK = Path("examples/flapping_wing/inputs.3d.convergence_fine")

_IB_PARTICLE_29_COLS = (
    "iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,"
    "Fcpx,Fcpy,Fcpz,Tcpx,Tcpy,Tcpz,SumUx,SumUy,SumUz,SumTx,SumTy,SumTz"
).split(",")


@pytest.mark.skipif(not _FINE_CSV.exists(), reason="fine CSV not present (Session B)")
def test_fine_csv_matches_ib_particle_contract():
    """Fine CSV has the pinned 29-column IB-particle schema, covers stop_time=1.0, is not truncated.

    A truncated or diverged fine run that wrote only a few rows (or stopped short of stop_time = 1.0)
    fails here rather than silently feeding a wrong-but-plausible peak into the convergence grader.
    """
    df = pd.read_csv(_FINE_CSV)
    assert list(df.columns) == _IB_PARTICLE_29_COLS
    assert df["time"].max() == pytest.approx(1.0, abs=1e-3)
    assert len(df) > 1900


@pytest.mark.skipif(
    not (_FINE_META.exists() and _FINE_DECK.exists()),
    reason="run_metadata_t3c.json or fine deck not present (Session B)",
)
def test_run_metadata_t3c_fields():
    """run_metadata_t3c.json carries the required T3c provenance fields.

    Verifies the IAMReX commit prefix, tier/grid identity, fine-deck hash pin, and the named extra
    fields (fixed_dt, dt_reduced) that the grading pipeline and the assert_gradeable_triple guard
    rely on.
    """
    with _FINE_META.open() as f:
        metadata = json.load(f)

    assert metadata["iamrex_commit"].startswith("f93dc794"), (
        f"IAMReX commit must be f93dc794… (same pin as T3a/T3b); got {metadata['iamrex_commit']}"
    )
    assert metadata["tier"] == "T3c"
    assert metadata["grid"] == "256 128 256"

    # Fine deck hash pinned to the committed deck.
    expected_hash = hashlib.sha256(_FINE_DECK.read_bytes()).hexdigest()
    assert metadata["inputs"]["hash"] == expected_hash, (
        "inputs.hash in run_metadata_t3c.json does not match sha256(inputs.3d.convergence_fine); "
        "the fine deck was modified after the run — re-capture metadata or restore the deck"
    )

    # Required provenance fields.
    assert "docker_image" in metadata
    assert "image_digest" in metadata

    # Named extra fields for temporal-confounding bookkeeping.
    assert "fixed_dt" in metadata
    assert "dt_reduced" in metadata


# ---------------------------------------------------------------------------
# §4.3 — 3-grid convergence grading from committed CSVs (Session B)
# ---------------------------------------------------------------------------

_COARSE_CSV = Path("examples/flapping_wing/forces_t2a_newconv.csv")
_MEDIUM_CSV = Path("examples/flapping_wing/forces_medium.csv")
_COARSE_DECK = Path("examples/flapping_wing/inputs.3d.validation")
_MEDIUM_DECK = Path("examples/flapping_wing/inputs.3d.convergence_medium")


@pytest.mark.skipif(
    not (_FINE_CSV.exists() and _FINE_META.exists()),
    reason="fine CSV or run_metadata_t3c.json not present (Session B — run operator job first)",
)
def test_fine_3grid_reports_from_committed_csvs():
    """3-grid convergence grader runs on the committed coarse+medium+fine triple (Session B).

    The coarse+medium 2-grid pair guard (``assert_gradeable_pair``) is always called — those
    two runs share the same dt=5e-4 and the same iStep time grid, so the check passes cleanly.

    The full ``assert_gradeable_triple`` is NOT called here because the fine run used
    ``dt_reduced=True`` (dt=2.5e-4 at runtime, CFL fallback D6): the fine CSV has 4000 unique
    iSteps while the medium has 2000, so ``assert_gradeable_triple`` raises ``"time-grid"`` as
    designed.  That is the expected, documented behavior per the t3c-handoff (not a test failure).

    The grader ``wing_grid_convergence_from_body_forces`` extracts peaks from each CSV
    independently (no common-time-grid requirement) and runs correctly regardless.

    The actual RESULTS headline values are asserted in ``test_results_reproducibility.py``
    (``test_3grid_convergence_recomputes_from_committed_csvs``), which is the durable
    regression guard for RESULTS.md.
    """
    import json
    import math

    from mosquito_cfd.benchmarks.wing_convergence import (
        assert_gradeable_pair,
        assert_gradeable_triple,
        wing_grid_convergence_from_body_forces,
    )

    with _FINE_META.open() as f:
        metadata = json.load(f)
    dt_reduced = metadata.get("dt_reduced", False)

    # Coarse+medium 2-grid pair is always dt-isolated (both dt=5e-4, same iStep sets).
    assert_gradeable_pair(
        _COARSE_CSV,
        _MEDIUM_CSV,
        coarse_deck=_COARSE_DECK,
        medium_deck=_MEDIUM_DECK,
    )

    if dt_reduced:
        # Fine run used a reduced dt at runtime — assert_gradeable_triple raises "time-grid"
        # because the fine CSV has 4000 unique iSteps while medium has 2000. This is the
        # expected D6-fallback behavior documented in t3c-handoff.md; it is NOT a test failure.
        with pytest.raises(ValueError, match="time-grid"):
            assert_gradeable_triple(
                _COARSE_CSV,
                _MEDIUM_CSV,
                _FINE_CSV,
                coarse_deck=_COARSE_DECK,
                medium_deck=_MEDIUM_DECK,
            )
    else:
        assert_gradeable_triple(
            _COARSE_CSV,
            _MEDIUM_CSV,
            _FINE_CSV,
            coarse_deck=_COARSE_DECK,
            medium_deck=_MEDIUM_DECK,
            fine_deck=_FINE_DECK,
        )

    out = wing_grid_convergence_from_body_forces(
        _COARSE_CSV,
        _MEDIUM_CSV,
        _FINE_CSV,
        f_star=1.0,
        phi_amp_deg=70.0,
        pitch_amp_deg=45.0,
    )

    # Monotone state is a structural property that must survive any peak-extraction change.
    assert out["cf_normal"]["monotone"] is True
    assert out["cf_chord"]["monotone"] is False

    # 3-grid path returns the expected key set for each component.
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
    assert set(out["cf_chord"].keys()) == _3GRID_KEYS
    assert set(out["cf_normal"].keys()) == _3GRID_KEYS

    # Fine-grid peaks are finite and positive (run did not diverge or produce degenerate output).
    for comp in ("cf_chord", "cf_normal"):
        cf_fine = out[comp]["cf_fine"]
        assert math.isfinite(cf_fine) and cf_fine > 0, (
            f"{comp} cf_fine={cf_fine!r} is not a finite positive float — "
            "check the fine-grid run for divergence or a degenerate IB force"
        )
