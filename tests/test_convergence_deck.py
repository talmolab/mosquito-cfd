"""Deck-invariance guard for the medium-grid flapping deck (Tier T3a).

Cluster-free string/key check: ``inputs.3d.convergence_medium`` must be an exact copy of the
canonical coarse deck ``inputs.3d.validation`` (whose sha256 matches the ``inputs.hash`` in
``run_metadata_t2a.json``) changing **only** ``amr.n_cell`` (64 32 64 -> 128 64 128). Holding
``ns.fixed_dt`` and ``particle_inputs.radius`` fixed keeps the temporal error identical and the
dimensionless IB-regularization length constant, so the coarse<->medium difference is isolated to
spatial + IB-regularization refinement. Nothing here runs the solver.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_COARSE = Path("examples/flapping_wing/inputs.3d.validation")
_MEDIUM = Path("examples/flapping_wing/inputs.3d.convergence_medium")


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
