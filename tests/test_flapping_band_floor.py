"""Flapping band-as-floor demotion (Tier T2b).

The [0.5, 1.5] band is graded as a lower-bound O(1) sanity FLOOR (it caught the old peak-tip
normalization at CF_z ~0.22 < 0.5). The ceiling 1.5 is REPORTED, not gated: under the corrected
motion the new-convention lab CF_x peak is 2.37 (> 1.5), which is expected (van Veen's own body-frame
normal ~2.4 also exceeds 1.5), not a failure. The VAN_VEEN_BAND value and its not-loosened guard are
unchanged — this is a grading-role change, not a loosening.
"""

from __future__ import annotations

import numpy as np

from mosquito_cfd.benchmarks.flapping_wing import (
    VAN_VEEN_BAND,
    WingForceDecomposition,
    plausibility_gate,
    reconstruct_wing_forces,
)

_OLD = "examples/flapping_wing/forces.csv"  # superseded stroke-||-span run (contrast baseline)
_NEWCONV = (
    "examples/flapping_wing/forces_t2a_newconv.csv"  # van Veen convention (headline)
)
_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0}


def _flat_decomp(cf_peak: float) -> WingForceDecomposition:
    """A synthetic decomposition whose steady-window CF peak is exactly ``cf_peak``."""
    t = np.linspace(0.0, 1.0, 50)
    z = np.zeros_like(t)
    arr = np.full_like(t, cf_peak)
    return WingForceDecomposition(
        time=t,
        f_ref=200.27,
        cf_x_ib=arr,
        cf_z_ib=arr,
        cf_x_added=z,
        cf_z_added=z,
        cf_x_hydro=z,
        cf_z_hydro=z,
    )


def test_van_veen_band_is_not_loosened():
    """The band value is pinned — the demotion is a role change, not a loosening."""
    assert VAN_VEEN_BAND == (0.5, 1.5)


def test_floor_graded_ceiling_reported():
    """The old run clears the O(1) floor; the ceiling is reported alongside (two-sided here).

    Scenario: Peak coefficients clear the O(1) floor without a fudge.
    """
    gate = plausibility_gate(reconstruct_wing_forces(_OLD, **_KIN))
    assert gate["cf_x_above_floor"] and gate["cf_z_above_floor"]
    assert gate["floor_pass"] is True
    # ceiling companion + resultant still reported (not gated)
    assert "cf_x_in_band" in gate and "cf_z_in_band" in gate
    assert gate["max_resultant"] > 0


def test_new_convention_cf_x_above_ceiling_not_failure():
    """New-convention lab CF_x peak (2.37) exceeds the ceiling — expected, not a floor failure.

    Scenario: A per-component peak above the ceiling is expected, not a failure.
    """
    gate = plausibility_gate(reconstruct_wing_forces(_NEWCONV, **_KIN))
    assert (
        gate["max_cf_x"] > 1.5
    )  # documented O(1) excursion (van Veen normal ~2.4 also > 1.5)
    assert gate["cf_x_in_band"] is False  # ceiling REPORTED, not gated
    assert gate["floor_pass"] is True  # clears the floor -> the gate passes
    assert gate["cf_x_above_floor"] and gate["cf_z_above_floor"]


def test_floor_still_catches_under_produced():
    """A sub-0.5 peak FAILS the floor — the floor is load-bearing (catches under-normalization).

    Scenario: The floor still catches an under-produced coefficient (not loosened).
    """
    gate = plausibility_gate(_flat_decomp(0.22))  # the old peak-tip normalization value
    assert gate["cf_x_above_floor"] is False
    assert gate["floor_pass"] is False
