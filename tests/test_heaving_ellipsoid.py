"""Heaving-ellipsoid self-consistency + added-mass-fraction sanity (Tier T2b).

Cluster-free: the numerics are graded on a SYNTHETIC fixture (shaped so the added-mass fraction
decays past t=7 and the steady Delta < 1%), mirroring the stress_integral _synthetic_box pattern.
Tests that read the real committed re-run CSV (forces_t2b_ib.csv) gate on FILE EXISTENCE and load the
CSV INSIDE the test body, so they skip (never error) until the operator re-run lands.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.flapping_wing import added_mass_force
from mosquito_cfd.benchmarks.heaving_ellipsoid import (
    MAX_SAMPLE_DT,
    SELF_CONSISTENCY_TOL,
    STEADY_WINDOW_T0,
    VAN_VEEN_ADDED_MASS_BALLPARK,
    ellipsoid_added_mass_fraction,
    ellipsoid_self_consistency,
)

_T2B_CSV = Path("examples/heaving_ellipsoid/forces_t2b_ib.csv")
_T2B_META = Path("examples/heaving_ellipsoid/run_metadata_t2b.json")
_COARSE = "examples/heaving_ellipsoid/forces.csv"  # committed 1.0-unit series (no SumU)


def _synthetic_ib(*, converged: bool = True) -> pd.DataFrame:
    """Fine-resolution ellipsoid IB series with SumU columns; heave (Fy) non-zero, span (Fz)=0.

    ``converged``: drag/lift settle to <1% consecutive change after t=7; added-mass fraction
    (rho*SumU / ib) is largest near t=0 and decays past t=7. ``converged=False`` adds a ~1.5%
    per-sample wobble in the steady window so the self-consistency gate FAILS.
    """
    t = np.arange(0.0, 10.0 + 1e-9, 0.01)
    # Drag Fx and heave-lift Fy: settle from an impulsive start toward a steady value.
    fx = -0.19 * (1 + 0.10 * np.exp(-t))
    fy = 0.10 * (1 + 0.10 * np.exp(-t))
    if not converged:
        wobble = 0.016 * (np.arange(t.size) % 2)  # ~1.6% two-sample oscillation
        fx = fx * (1 + wobble)
        fy = fy * (1 + wobble)
    # Added mass = rho*SumU; SumU decays fast so the fraction is large at t~0 and ~0 by t>=7.
    sum_ux = -0.10 * np.exp(-0.5 * t)
    sum_uy = 0.05 * np.exp(-0.5 * t)
    z = np.zeros_like(t)
    return pd.DataFrame(
        {
            "time": t,
            "Fx": fx,
            "Fy": fy,
            "Fz": z,
            "SumUx": sum_ux,
            "SumUy": sum_uy,
            "SumUz": z,
        }
    )


# --- 2.1: added-mass formula locked to the IAMReX source (shared with the wing) ---


def test_added_mass_force_is_rho_times_sumu():
    """added_mass = rho_f * SumU on a known fixture row (WriteIBForceAndMoment, shared with the wing)."""
    df = _synthetic_ib()
    row = df.iloc[100]
    assert added_mass_force(np.array([row["SumUx"]]), rho_f=1.0)[0] == pytest.approx(
        row["SumUx"]
    )
    assert added_mass_force(np.array([2.0]), rho_f=2.0)[0] == pytest.approx(4.0)


# --- 2.2: added-mass fraction bounded + decays; van Veen reported, not matched ---


def test_added_mass_fraction_bounded_and_decays():
    """The STEADY-window fraction is bounded 0<=f<1 and decays from the impulsive start.

    The per-timestep frac is NaN at an ib zero-crossing (a real heave-lift Fy crosses zero), so the
    physically-meaningful bounded claim is on the STEADY window (constant-velocity steady share ~0),
    not on every timestep.
    """
    res = ellipsoid_added_mass_fraction(_synthetic_ib())
    # Per-timestep frac: non-negative where finite (NaN at zero-crossings is expected, not a fake 0).
    for key in ("frac_drag", "frac_lift"):
        f = res[key]
        assert np.all(f[np.isfinite(f)] >= 0.0)
    # Steady-window fraction bounded well below 1.
    assert 0.0 <= res["steady_frac_drag"] < 1.0
    assert 0.0 <= res["steady_frac_lift"] < 1.0
    # Decays: early-window mean fraction exceeds the steady-window mean fraction.
    assert res["decays_drag"] is True and res["decays_lift"] is True
    assert res["steady_frac_drag"] < res["early_frac_drag"]


def test_added_mass_vs_van_veen_reported_not_matched():
    """The 15%/31% van Veen ballpark is REPORTED (cited), never asserted as a tight match."""
    res = ellipsoid_added_mass_fraction(_synthetic_ib())
    # The ballpark is a pinned, cited constant carried for reporting.
    assert VAN_VEEN_ADDED_MASS_BALLPARK == {"lift": 0.15, "drag": 0.31}
    assert res["van_veen_ballpark"] == VAN_VEEN_ADDED_MASS_BALLPARK
    # This test does NOT assert the ellipsoid fraction equals the van Veen wing values (CC-V2).


def test_added_mass_ballpark_returned_as_copy():
    """The ballpark is returned as a COPY — mutating it must not corrupt the module constant."""
    res = ellipsoid_added_mass_fraction(_synthetic_ib())
    res["van_veen_ballpark"]["lift"] = 999.0
    assert VAN_VEEN_ADDED_MASS_BALLPARK == {"lift": 0.15, "drag": 0.31}


def test_added_mass_rejects_no_steady_samples():
    """A window past all samples raises rather than returning NaN-laden output."""
    with pytest.raises(ValueError, match="no samples in the steady window"):
        ellipsoid_added_mass_fraction(_synthetic_ib(), window_t0=1e9)


# --- 2.3: self-consistency over the steady window (drag Fx + heave-lift Fy) ---


def test_self_consistency_below_threshold():
    """A fine converged series: max consecutive relative change over t>=7 is < 1%."""
    res = ellipsoid_self_consistency(_synthetic_ib(converged=True))
    assert res["max_rel_change_drag"] < SELF_CONSISTENCY_TOL
    assert res["max_rel_change_lift"] < SELF_CONSISTENCY_TOL
    assert res["converged"] is True
    assert res["window_t0"] == STEADY_WINDOW_T0


def test_self_consistency_fails_above_threshold():
    """A fine series with a ~1.5% steady-window wobble FAILS the 1% gate (the gate can fail)."""
    res = ellipsoid_self_consistency(_synthetic_ib(converged=False))
    assert res["converged"] is False
    assert res["max_rel_change_drag"] > SELF_CONSISTENCY_TOL


def test_self_consistency_tol_not_loosened():
    """The threshold and sampling constants are pinned (not loosened to pass)."""
    assert SELF_CONSISTENCY_TOL == 0.01
    assert MAX_SAMPLE_DT == 0.1


def test_coarse_series_declines_clearly():
    """The committed 1.0-unit forces.csv is too coarsely sampled to resolve the gate -> declines."""
    df = pd.read_csv(_COARSE)
    with pytest.raises(ValueError, match="too coarse"):
        ellipsoid_self_consistency(df)


def test_self_consistency_rejects_nonfinite_forces():
    """All-NaN steady-window forces RAISE, never a silent converged=False."""
    df = _synthetic_ib()
    df.loc[df["time"] >= STEADY_WINDOW_T0, "Fx"] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        ellipsoid_self_consistency(df)


def test_heave_channel_nonzero():
    """The graded heave-lift Fy channel is non-zero, so the lift-side gate is not a degenerate 0/0."""
    df = _synthetic_ib()
    m = df["time"].to_numpy() >= STEADY_WINDOW_T0
    assert np.abs(df["Fy"].to_numpy()[m]).max() > 0.0


# --- 2.4: provenance + skip-on-artifact (real re-run CSV / metadata) ---


def test_run_metadata_records_pinned_provenance():
    """capture_surrogate_run_metadata records the digest, timestamp, inputs hash, and iamrex_commit.

    Cluster-free: exercises the provenance helper the ellipsoid re-run will use (task 2.6), so the
    metadata contract is guarded before the artifact lands. iamrex_commit is a TOP-LEVEL key (extra
    is merged last), and a mutable tag (no sha256:) is rejected.
    """
    from mosquito_cfd.force_surrogate import capture_surrogate_run_metadata

    digest = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
    deck = "examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid"
    meta = capture_surrogate_run_metadata(
        docker_image_digest=digest,
        inputs_file=Path(deck),
        timestamp="2026-07-04T00:00:00+00:00",
        extra={"iamrex_commit": "f93dc794ed9d8b8ae58b3f5719f485ca7d79c8da"},
    )
    assert meta["docker_image"] == digest
    assert meta["timestamp"] == "2026-07-04T00:00:00+00:00"
    assert meta["inputs"]["hash"]  # inputs hash recorded
    assert meta["iamrex_commit"].startswith("f93dc794")  # top-level (extra merged last)
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:fp64",  # mutable tag, no sha256:
            timestamp="2026-07-04T00:00:00+00:00",
        )


@pytest.mark.skipif(
    not _T2B_CSV.exists(), reason="ellipsoid T2b re-run artifact not committed yet"
)
def test_real_run_self_consistency_and_added_mass():
    """On the committed re-run CSV: self-consistency holds and added-mass is bounded (loaded here)."""
    df = pd.read_csv(_T2B_CSV)  # loaded INSIDE the test body (never at module import)
    sc = ellipsoid_self_consistency(df)
    assert sc["converged"] is True
    am = ellipsoid_added_mass_fraction(df)
    # Real heave-lift Fy crosses zero -> per-timestep frac has NaN there; grade the STEADY window,
    # where the constant-velocity added-mass share is ~0 and well below 1.
    assert 0.0 <= am["steady_frac_drag"] < 1.0
    assert 0.0 <= am["steady_frac_lift"] < 1.0


@pytest.mark.skipif(
    not _T2B_META.exists(), reason="ellipsoid T2b run_metadata not committed yet"
)
def test_deck_hash_matches_recorded():
    """The recorded inputs.hash equals hash_file(deck) — 'deck byte-unchanged' is verified, not claimed."""
    import json

    from mosquito_cfd.benchmarks.metadata import hash_file

    meta = json.loads(_T2B_META.read_text(encoding="utf-8"))
    deck = "examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid"
    assert meta["inputs"]["hash"] == hash_file(deck)
    assert meta["iamrex_commit"].startswith("f93dc794")
