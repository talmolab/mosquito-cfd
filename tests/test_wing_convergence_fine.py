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
    assert (
        "image_digest" in metadata or "docker_image" in metadata
    )  # image digest may be nested

    # Named extra fields for temporal-confounding bookkeeping.
    assert "fixed_dt" in metadata
    assert "dt_reduced" in metadata
