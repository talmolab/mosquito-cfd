"""Tests for mosquito_cfd.field_surrogate.domino_adapter (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.field_surrogate.domino_adapter import (
    GEOMETRY_HALF_KEYS,
    VOLUME_HALF_KEYS,
    to_domino_volume,
)
from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "src" / "mosquito_cfd" / "field_surrogate" / "domino_adapter.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lev_boxlib_plt"

GLOBALS_VALUES = (35.0, 0.85, 30.0)
GLOBALS_REFERENCE = (45.0, 1.0, 45.0)


def _snapshot(lo=(1.2, 1.2, 1.2), hi=(4.7, 3.4, 5.6)):
    # Deliberately distinct extents per axis so a transposed grid cannot pass by symmetry.
    return read_field_snapshot(FIXTURE, lo=lo, hi=hi)


def _adapt(snap):
    return to_domino_volume(
        snap,
        global_params_values=GLOBALS_VALUES,
        global_params_reference=GLOBALS_REFERENCE,
    )


def test_emits_exactly_the_volume_half_with_no_batch_dimension():
    snap = _snapshot()
    out = _adapt(snap)

    assert set(out) == set(VOLUME_HALF_KEYS)

    nx, ny, nz = snap.arrays["u"].shape
    n = nx * ny * nz
    f = len(snap.field_names)
    p = len(GLOBALS_VALUES)

    # No leading batch dimension: DoMINO's own datapipe adds one, and a second would be wrong.
    assert out["volume_mesh_centers"].shape == (n, 3)
    assert out["volume_fields"].shape == (n, f)
    assert out["grid"].shape == (nx, ny, nz, 3)
    assert out["global_params_values"].shape == (p, 1)
    assert out["global_params_reference"].shape == (p, 1)


def test_geometry_half_keys_are_absent_not_zero_filled():
    # Zero-filling sdf_nodes would produce a dict that looks trainable and silently is not.
    out = _adapt(_snapshot())
    for key in GEOMETRY_HALF_KEYS:
        assert key not in out, f"{key} must be absent, not present-and-empty"


def test_grid_is_oriented_to_the_snapshot_axes():
    snap = _snapshot()
    out = _adapt(snap)
    nx = snap.x.size

    np.testing.assert_array_equal(
        out["grid"][0, 0, 0], [snap.x[0], snap.y[0], snap.z[0]]
    )
    # [0,0,0] is invariant under an indexing="xy" swap; this corner is what catches it.
    np.testing.assert_array_equal(
        out["grid"][nx - 1, 0, 0], [snap.x[-1], snap.y[0], snap.z[0]]
    )


def test_volume_fields_columns_follow_field_names():
    snap = _snapshot()
    out = _adapt(snap)
    pc = snap.to_point_cloud()
    np.testing.assert_array_equal(out["volume_fields"], pc.values)
    np.testing.assert_array_equal(out["volume_mesh_centers"], pc.coords)


def test_mismatched_global_param_lengths_are_rejected():
    with pytest.raises(ValueError, match="global_params"):
        to_domino_volume(
            _snapshot(),
            global_params_values=(1.0, 2.0),
            global_params_reference=(1.0,),
        )


def test_module_contains_no_torch_or_physicsnemo_import_at_any_scope():
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    banned = {"torch", "physicsnemo"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                f"{a.name}:{node.lineno}"
                for a in node.names
                if a.name.split(".")[0] in banned
            ]
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in banned:
                offenders.append(f"{node.module}:{node.lineno}")
    assert not offenders, f"GPU-only imports found: {offenders}"


_POISONED_IMPORT = """
import sys

sys.modules["torch"] = None
sys.modules["physicsnemo"] = None

import numpy as np

from mosquito_cfd.field_surrogate.domino_adapter import to_domino_volume
from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

snap = read_field_snapshot(r"{fixture}", lo=(-np.inf,) * 3, hi=(np.inf,) * 3)
out = to_domino_volume(
    snap, global_params_values=(1.0,), global_params_reference=(1.0,)
)
assert out["volume_mesh_centers"].shape == (216, 3)
"""


def test_adapter_runs_with_torch_and_physicsnemo_unimportable():
    # A plain "it imports on CI" check cannot fail on a runner where neither package is
    # installed. Poisoning sys.modules makes `import torch` raise, so this also has teeth on the
    # A5000 dev host where --group train IS installed.
    result = subprocess.run(
        [sys.executable, "-c", _POISONED_IMPORT.format(fixture=FIXTURE)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "claim",
    [
        "target",
        "not an encoder input",
        "no pressure field",
        *GEOMETRY_HALF_KEYS,
    ],
)
def test_documentation_states_the_cc4_honesty_claims(claim):
    # Docstrings ONLY -- not the module source. Concatenating the source made the
    # GEOMETRY_HALF_KEYS cases tautological (those names are string literals in the tuple
    # definition), and let the prose be demoted to a # comment that help() never shows:
    # deleting the entire CC-4 prose failed only 3 of 11 parametrizations.
    # Precedent: tests/test_no_false_diffused_ib_claim.py.
    import mosquito_cfd.field_surrogate.domino_adapter as mod

    doc = ((mod.__doc__ or "") + (to_domino_volume.__doc__ or "")).lower()
    assert claim.lower() in doc, f"missing honesty claim: {claim}"


# --- review corrections (task 54) --------------------------------------------------------------

#: Written literally here, NOT imported from the module under test. The original tests read their
#: expectations from the implementation's own constants, making "absences are real" a tautology:
#: a reviewer moved sdf_nodes into VOLUME_HALF_KEYS and emitted it zero-filled, and the suite
#: stayed green while the collected count silently fell by one.
EXPECTED_VOLUME_KEYS = frozenset(
    {
        "volume_mesh_centers",
        "volume_fields",
        "grid",
        "global_params_values",
        "global_params_reference",
    }
)
EXPECTED_ABSENT_KEYS = frozenset(
    {
        "geometry_coordinates",
        "sdf_grid",
        "sdf_nodes",
        "surf_grid",
        "sdf_surf_grid",
        "surface_mesh_centers",
        "surface_normals",
        "surface_areas",
    }
)


def test_module_constants_match_the_specified_key_partition():
    assert frozenset(VOLUME_HALF_KEYS) == EXPECTED_VOLUME_KEYS
    assert frozenset(GEOMETRY_HALF_KEYS) == EXPECTED_ABSENT_KEYS
    assert EXPECTED_VOLUME_KEYS.isdisjoint(EXPECTED_ABSENT_KEYS)


def test_emitted_keys_are_exactly_the_specified_volume_half():
    out = _adapt(_snapshot())
    assert set(out) == EXPECTED_VOLUME_KEYS
    assert EXPECTED_ABSENT_KEYS.isdisjoint(out)
