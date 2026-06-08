"""Tests that committed fixtures are usable cluster-free (TDD red phase)."""

import json
from pathlib import Path

import pandas as pd

from mosquito_cfd.force_surrogate import compute_force_coefficients

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The real IAMReX IB-particle CSV schema (29 columns, exact order).
REAL_SCHEMA = [
    "iStep",
    "time",
    "X",
    "Y",
    "Z",
    "Vx",
    "Vy",
    "Vz",
    "Rx",
    "Ry",
    "Rz",
    "Fx",
    "Fy",
    "Fz",
    "Mx",
    "My",
    "Mz",
    "Fcpx",
    "Fcpy",
    "Fcpz",
    "Tcpx",
    "Tcpy",
    "Tcpz",
    "SumUx",
    "SumUy",
    "SumUz",
    "SumTx",
    "SumTy",
    "SumTz",
]


def test_synthetic_fixture_loads():
    """Fixture parses name-based, matches the real schema, gives exact coefficients."""
    df = pd.read_csv(FIXTURES / "synthetic_ib_particle.csv")
    assert list(df.columns) == REAL_SCHEMA
    cc = compute_force_coefficients(
        df["Fx"].to_numpy(), df["Fy"].to_numpy(), df["Fz"].to_numpy(), 100.0
    )
    # row 1: Fx=50 -> 0.5 ; row 2: Fz=-40 -> -0.4
    assert cc.cf_x[1] == 0.5
    assert cc.cf_z[2] == -0.4


def test_micro_sweep_fixture_parses():
    """The 2-config micro-sweep parses with the documented keys."""
    data = json.loads((FIXTURES / "micro_sweep.json").read_text(encoding="utf-8"))
    assert len(data) == 2
    for cfg in data:
        assert {"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"} <= set(cfg)
