"""Deck-invariance guard for the medium-grid flapping deck (Tier T3a) and fine-grid deck (Tier T3c).

Cluster-free string/key check: ``inputs.3d.convergence_medium`` must be an exact copy of the
canonical coarse deck ``inputs.3d.validation`` (whose sha256 matches the ``inputs.hash`` in
``run_metadata_t2a.json``) changing **only** ``amr.n_cell`` (64 32 64 -> 128 64 128). Similarly,
``inputs.3d.convergence_fine`` must be an exact copy of the medium deck changing **only**
``amr.n_cell`` (128 64 128 -> 256 128 256) and adding ``amrex.the_arena_init_size = 28``.
Holding ``ns.fixed_dt`` and ``particle_inputs.radius`` fixed across all three decks keeps the
temporal error identical and the dimensionless IB-regularization length constant, so the
coarse<->medium<->fine difference is isolated to spatial + IB-regularization refinement. Nothing
here runs the solver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_COARSE = Path("examples/flapping_wing/inputs.3d.validation")
_MEDIUM = Path("examples/flapping_wing/inputs.3d.convergence_medium")
_FINE = Path("examples/flapping_wing/inputs.3d.convergence_fine")


def _parse_deck(path: Path) -> dict[str, str]:
    """Parse an AMReX inputs deck into a ``key -> value`` map.

    Strips ``#`` comments and normalizes each value's internal whitespace via ``" ".join(v.split())``
    so cosmetic reformatting (e.g. ``"2  2 2"`` vs ``"2 2 2"``) does not false-diff.
    """
    kv: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0]  # strip trailing/whole-line comments
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        kv[key] = " ".join(value.split())  # normalize internal whitespace
    return kv


@pytest.mark.skipif(not _COARSE.exists(), reason="coarse validation deck not present")
def test_medium_deck_changes_only_the_grid():
    """The medium deck differs from the coarse deck ONLY in ``amr.n_cell``; dt/radius held fixed.

    Parses both decks to key->value maps and asserts the symmetric difference of differing keys
    (present-in-one-only OR value-mismatch) is exactly ``{amr.n_cell}`` — so no other physics knob
    (domain, BCs, kinematics, viscosity, max_grid_size, init_iter) drifted. Also asserts
    ``ns.fixed_dt`` and ``particle_inputs.radius`` are float-equal across both decks (string
    ``"0.0005"`` != ``"5e-4"``, so parse as floats).
    """
    coarse = _parse_deck(_COARSE)
    medium = _parse_deck(_MEDIUM)

    all_keys = set(coarse) | set(medium)
    differing = {k for k in all_keys if coarse.get(k) != medium.get(k)}
    assert differing == {"amr.n_cell"}, (
        f"medium deck must change ONLY amr.n_cell; differing keys: {sorted(differing)}"
    )
    assert coarse["amr.n_cell"] == "64 32 64"
    assert medium["amr.n_cell"] == "128 64 128"

    # dt held fixed (temporal error identical) and the IB-regularization length held (against the
    # changing h). Parse as floats because "0.0005" and "5e-4" are unequal strings but equal floats.
    assert float(coarse["ns.fixed_dt"]) == float(medium["ns.fixed_dt"]) == 5e-4
    assert (
        float(coarse["particle_inputs.radius"])
        == float(medium["particle_inputs.radius"])
        == 1.5
    )


@pytest.mark.skipif(not _MEDIUM.exists(), reason="medium convergence deck not present")
def test_fine_deck_matches_medium_except_n_cell_and_arena():
    """The fine deck differs from the medium deck ONLY in ``amr.n_cell`` and ``amrex.the_arena_init_size``.

    Parses both decks to key->value maps and asserts the symmetric difference of differing or
    missing keys is exactly ``{amr.n_cell, amrex.the_arena_init_size}`` — so no other physics
    parameter (domain, BCs, kinematics, viscosity, dt, radius, max_grid_size, init_iter) drifted.
    Also asserts the grid-resolution key holds the expected values and that ``ns.fixed_dt``,
    ``particle_inputs.radius``, and ``amr.plot_int`` are identical between the two decks.
    """
    medium = _parse_deck(_MEDIUM)
    fine = _parse_deck(_FINE)

    all_keys = set(medium) | set(fine)
    # Keys that differ: either value mismatch OR present in one but absent in the other.
    differing = {k for k in all_keys if medium.get(k) != fine.get(k)}
    assert differing == {"amr.n_cell", "amrex.the_arena_init_size"}, (
        f"fine deck must change ONLY amr.n_cell and amrex.the_arena_init_size; "
        f"differing keys: {sorted(differing)}"
    )
    assert medium["amr.n_cell"] == "128 64 128"
    assert fine["amr.n_cell"] == "256 128 256"
    # Arena cap present only in fine deck (not in medium).
    assert "amrex.the_arena_init_size" not in medium
    assert fine["amrex.the_arena_init_size"] == "28"

    # dt and radius held across the medium→fine step (temporal isolation + IB-regularization held).
    assert float(medium["ns.fixed_dt"]) == float(fine["ns.fixed_dt"]) == 5e-4
    assert (
        float(medium["particle_inputs.radius"])
        == float(fine["particle_inputs.radius"])
        == 1.5
    )
    assert int(medium["amr.plot_int"]) == int(fine["amr.plot_int"]) == 100


@pytest.mark.skipif(
    not (_COARSE.exists() and _MEDIUM.exists() and _FINE.exists()),
    reason="coarse, medium, or fine deck not present",
)
def test_all_three_decks_share_fixed_dt_and_radius():
    """All three decks hold ``ns.fixed_dt = 5e-4`` and ``particle_inputs.radius = 1.5``.

    Directly covers the "Temporal isolation and IB regularization held across all three grids"
    spec scenario. A deck-level dt change in any of the three would break the coarse<->medium<->fine
    comparison's temporal-isolation guarantee.
    """
    coarse = _parse_deck(_COARSE)
    medium = _parse_deck(_MEDIUM)
    fine = _parse_deck(_FINE)

    assert float(coarse["ns.fixed_dt"]) == 5e-4, "coarse deck dt changed"
    assert float(medium["ns.fixed_dt"]) == 5e-4, "medium deck dt changed"
    assert float(fine["ns.fixed_dt"]) == 5e-4, "fine deck dt changed"

    assert float(coarse["particle_inputs.radius"]) == 1.5, "coarse deck radius changed"
    assert float(medium["particle_inputs.radius"]) == 1.5, "medium deck radius changed"
    assert float(fine["particle_inputs.radius"]) == 1.5, "fine deck radius changed"
