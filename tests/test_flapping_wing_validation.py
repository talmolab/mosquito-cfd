"""Flapping-wing plausibility-gate tests (van Veen 2022), cluster-free, analysis-only.

The gate is graded on ib_force ALONE (it already clears the band); added-mass and the 6-DOF
force are reported separately with the formula locked to the IAMReX WriteIBForceAndMoment
source (NOT tuned to make the gate pass). See openspec/changes/standardize-force-normalization
(Task E; capability flapping-wing-validation).
"""

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    VAN_VEEN_BAND,
    added_mass_force,
    added_mass_fraction,
    plausibility_gate,
    reconstruct_wing_forces,
)

# forces.csv is the committed write-out of the validated wingbeat (IB_Particle_*.csv is the
# gitignored raw dump; see .gitignore). Same run + 29-col schema incl. SumU*, but a separate
# write-out (de-duplicated leading rows; forces agree with the raw dump to ~1e-3 relative) —
# the gate is robust to that (margins ~0.1 dwarf the ~6e-4 delta).
_CSV = "examples/flapping_wing/forces.csv"
_KIN = dict(f_star=1.0, phi_amp_deg=70.0)  # validated point


def _decomp():
    return reconstruct_wing_forces(_CSV, **_KIN)


# --- E.1a: added-mass formula locked to the IAMReX source, not the band ---


def test_added_mass_force_is_rho_times_sumu_column():
    """added_mass = rho_f * SumU (the SumU column is already (sum_u_new-sum_u_old)/dt).

    Scenario: Added-mass formula is locked to the IAMReX source, not the band. The SumU
    column in WriteIBForceAndMoment (DiffusedIB.cpp:~1261) is already a rate, so the
    added-mass force is simply rho_f * SumU on a known row — no extra d/dt, no tuning.
    """
    np.testing.assert_allclose(
        added_mass_force(np.array([4356.75, 1.0, -2.0]), rho_f=1.0),
        np.array([4356.75, 1.0, -2.0]),
    )
    np.testing.assert_allclose(
        added_mass_force(np.array([10.0]), rho_f=2.0), np.array([20.0])
    )
    # on a known committed row: added-mass force = rho_f * SumUx (rho_f = 1)
    df = pd.read_csv(_CSV)
    row = df.iloc[100]
    assert added_mass_force(np.array([row["SumUx"]]), rho_f=1.0)[0] == pytest.approx(
        row["SumUx"]
    )


# --- E.1b: gate on ib_force ALONE, in band, no fudge; verdict independent of added-mass ---


def test_van_veen_band_is_not_loosened():
    """The literature band is pinned to [0.5,1.5] — it SHALL NOT be widened to pass.

    Scenario: ib_force magnitudes fall in band without a fudge (the band itself is fixed).
    Guards against quietly widening VAN_VEEN_BAND to admit a future out-of-band config.
    """
    assert VAN_VEEN_BAND == (0.5, 1.5)


def test_ib_force_gate_in_band_without_fudge():
    """max|CF_x|, max|CF_z| (ib_force, van Veen) lie in [0.5,1.5] with no correction factor.

    Scenario: ib_force magnitudes fall in band without a fudge.
    """
    gate = plausibility_gate(_decomp())
    lo, hi = VAN_VEEN_BAND
    assert lo <= gate["max_cf_x"] <= hi
    assert lo <= gate["max_cf_z"] <= hi
    assert gate["cf_x_in_band"] and gate["cf_z_in_band"]
    # rotation-invariant resultant reported as the frame-honest companion
    assert gate["max_resultant"] > 0


def test_gate_verdict_independent_of_added_mass():
    """The gate is a function of ib_force alone — added-mass cannot flip it.

    Scenario: Added-mass does not decide the gate. Zeroing the added-mass/hydro fields leaves
    the gate verdict identical (it only reads cf_*_ib).
    """
    d = _decomp()
    from dataclasses import replace

    d_no_am = replace(
        d,
        cf_x_added=np.zeros_like(d.cf_x_added),
        cf_z_added=np.zeros_like(d.cf_z_added),
        cf_x_hydro=np.zeros_like(d.cf_x_hydro),
        cf_z_hydro=np.zeros_like(d.cf_z_hydro),
    )
    assert plausibility_gate(d) == plausibility_gate(d_no_am)


# --- E.2: steady window pinned by a physical criterion; margins on BOTH band edges ---


def test_steady_window_pinned_and_margins_reported():
    """The window is a named constant; both band-edge margins are positive (van Veen).

    Scenario: Steady window is pinned by a physical criterion and reproducible. The CF_x
    ceiling (the tighter edge near the impulsive-start cutoff) and the CF_z floor are both
    reported and clear of the band.
    """
    assert (
        STEADY_WINDOW_T0 == 0.05
    )  # documented physical criterion (excludes t<=0.004 start)
    gate = plausibility_gate(_decomp(), window_t0=STEADY_WINDOW_T0)
    assert gate["cf_z_floor_margin"] > 0  # CF_z stays clear of 0.5
    assert gate["cf_x_ceiling_margin"] > 0  # CF_x stays under 1.5 (the tighter edge)
    # reproducible from committed data: the documented validated peaks
    assert gate["max_cf_x"] == pytest.approx(1.41, abs=0.02)
    assert gate["max_cf_z"] == pytest.approx(0.68, abs=0.02)


def test_window_excludes_impulsive_start():
    """Including the impulsive start (t=0) blows |CF_x| out of band — the cut is load-bearing."""
    gate_full = plausibility_gate(_decomp(), window_t0=0.0)
    assert gate_full["max_cf_x"] > 1.5  # transient spike, excluded by the pinned window


# --- Robustness / degenerate-input guards (new analysis functions) ---


def test_empty_steady_window_raises_clear_error():
    """A window past all timesteps reports the data range, not a bare reduction crash."""
    d = _decomp()
    with pytest.raises(ValueError, match="selects no timesteps"):
        plausibility_gate(d, window_t0=1e9)
    with pytest.raises(ValueError, match="selects no timesteps"):
        added_mass_fraction(d, window_t0=1e9)


def test_degenerate_kinematics_rejected():
    """f_star=0 / phi_amp_deg=0 give f_ref=0 — reject, don't return inf/NaN coefficients.

    Parity with compute_force_coefficients (the corpus path already guards this).
    """
    with pytest.raises(ValueError, match="f_ref must be finite and positive"):
        reconstruct_wing_forces(_CSV, f_star=0.0, phi_amp_deg=70.0)
    with pytest.raises(ValueError, match="f_ref must be finite and positive"):
        reconstruct_wing_forces(_CSV, f_star=1.0, phi_amp_deg=0.0)


def test_missing_csv_column_raises_descriptive_error(tmp_path):
    """A CSV missing a required column raises a schema-citing ValueError, not a bare KeyError."""
    df = pd.read_csv(_CSV).drop(columns=["SumUx"])
    bad = tmp_path / "no_sumux.csv"
    df.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="missing required column"):
        reconstruct_wing_forces(bad, **_KIN)


# --- E.3: decomposition is the 6-DOF momentum balance, self-consistent ---


def test_decomposition_is_six_dof_momentum_balance():
    """F_hydro = rho_f*(SumU - ib_force); added-mass is a positive non-trivial fraction.

    Scenario: Decomposition is reported and self-consistent. Per WriteIBForceAndMoment the net
    hydrodynamic force is the 6-DOF balance rho_f*(SumU - ib_force) (NOT a naive ib+added sum).
    """
    d = _decomp()
    # f_hydro == added_mass - rho_f*ib (rho_f = 1): cf_hydro == cf_added - cf_ib
    np.testing.assert_allclose(d.cf_x_hydro, d.cf_x_added - d.cf_x_ib, rtol=1e-9)
    np.testing.assert_allclose(d.cf_z_hydro, d.cf_z_added - d.cf_z_ib, rtol=1e-9)
    frac = added_mass_fraction(d)
    for key in ("stroke", "lift"):
        assert 0.0 < frac[key] < 1.0  # positive, non-trivial, not hard-coded
    # added-mass is a larger fraction of lift than of stroke (reported, not asserted exact)
    assert frac["lift"] > frac["stroke"]


# --- E.5: docs disclose the lab-frame caveat and defer body-frame/time-resolved ---


def test_results_doc_delivers_body_frame_and_defers_t4():
    """RESULTS.md delivers the body-frame per-component van Veen comparison (T2a) and defers T4.

    Scenario (task 5.5): the faithful body-frame CF_chord/CF_normal comparison #36 deferred is now
    DELIVERED here; only the time-resolved curve match (T4) remains deferred. The lab-frame band is
    still disclosed as an O(1) plausibility range, not the body-frame gate.
    """
    from pathlib import Path

    text = Path("examples/flapping_wing/RESULTS.md").read_text(encoding="utf-8")
    low = text.lower()
    # Body frame is DELIVERED, not deferred (the #36 deferral is now closed by T2a).
    assert "body-frame" in low or "body frame" in low
    assert (
        "cf_normal" in low and "cf_chord" in low
    )  # per-component decomposition present
    assert "deliver" in low  # framed as delivered, not deferred
    # Lab-frame magnitudes still disclosed as an O(1) plausibility range (not the gate).
    assert "lab-frame" in low or "lab frame" in low
    assert "plausibility" in low
    # Time-resolved curve match is the remaining deferral (T4).
    assert "t4" in low
    assert "200.27" in text or "200.3" in text  # van Veen F_ref
    assert "2.64" not in text  # no sphere extraction-factor conflation
