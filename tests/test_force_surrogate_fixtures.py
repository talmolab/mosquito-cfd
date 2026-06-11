"""Tests that committed fixtures are usable cluster-free (TDD red phase)."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate import compute_force_coefficients
from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# The real IAMReX IB-particle CSV schema (29 columns, exact order) — single source of
# truth is the dataset module's exported constant (consumed by the extractor too).
REAL_SCHEMA = IB_PARTICLE_COLUMNS


def test_synthetic_fixture_loads():
    """Fixture parses name-based, matches the real schema, gives exact coefficients."""
    df = pd.read_csv(FIXTURES / "synthetic_ib_particle.csv")
    assert list(df.columns) == REAL_SCHEMA
    cc = compute_force_coefficients(
        df["Fx"].to_numpy(), df["Fy"].to_numpy(), df["Fz"].to_numpy(), 100.0
    )
    # full columns normalized by the round F_ref=100.0 -> exact decimals
    np.testing.assert_allclose(cc.cf_x, [0.0, 0.5, -0.3, 0.75, -1.0])
    np.testing.assert_allclose(cc.cf_y, [0.0, -0.25, 0.2, 0.0, 0.5])
    np.testing.assert_allclose(cc.cf_z, [0.0, 0.1, -0.4, -0.15, 0.25])


def test_micro_sweep_fixture_parses():
    """The 2-config micro-sweep parses with the documented keys."""
    data = json.loads((FIXTURES / "micro_sweep.json").read_text(encoding="utf-8"))
    assert len(data) == 2
    for cfg in data:
        assert {"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"} <= set(cfg)
