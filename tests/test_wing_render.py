"""Shared wing marker/outline transform helpers for the visualization package.

OpenSpec change ``add-visualization-tooling``. ``transform_markers`` rotates about the caller's
``hinge`` (never the origin) using the canonical ``benchmarks.wing_kinematics.rotation_matrix`` --
no module under ``visualization/`` may reimplement wing rotation (spec requirement, guarded here by
an AST scan).
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial import ConvexHull

from mosquito_cfd.visualization.wing_render import (
    leading_edge_mask,
    transform_markers,
    wing_outline,
)

# Anchored to the repo root via __file__ (not a cwd-relative "src/..." string) -- a relative
# Path silently rglobs zero files if pytest is ever invoked from outside the repo root, which
# would make these AST-scan tests vacuously pass instead of actually enforcing the spec
# requirements they guard. Mirrors tests/test_no_false_diffused_ib_claim.py's own convention.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_VISUALIZATION_PKG = _REPO_ROOT / "src" / "mosquito_cfd" / "visualization"
_VIZ_GROUP_MODULES = {"scipy", "skimage", "imageio_ffmpeg"}


def test_transform_markers_rotates_about_hinge_not_origin():
    """A 90-degree stroke about a hinge away from the origin matches a hand-computed rotation."""
    marker = np.array([[1.0, 0.0, 0.0]])
    hinge = np.array([2.0, 3.0, 0.0])

    result = transform_markers(marker, hinge, phi=np.pi / 2, alpha=0.0, theta=0.0)

    # Hand-computed: translate to hinge-relative (-1, -3, 0), rotate 90 deg about z
    # ((x, y) -> (-y, x)) giving (3, -1, 0), translate back by +hinge -> (5, 2, 0).
    expected_about_hinge = np.array([[5.0, 2.0, 0.0]])
    np.testing.assert_allclose(result, expected_about_hinge, atol=1e-10)

    # A rotation about the ORIGIN instead would give a different result for this
    # off-origin hinge -- explicitly assert the two differ (catches the bug class this
    # requirement exists to prevent).
    about_origin = np.array([[0.0, 1.0, 0.0]])
    assert not np.allclose(result, about_origin)


def test_transform_markers_applies_the_same_rotation_to_every_marker():
    """N>1 markers each get the identical rotation about the hinge (not just N=1 -- a transpose
    bug could pass a single-row check while breaking on a real (N, 3) array).
    """
    markers = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0], [-2.0, 3.0, 1.0]]
    )
    hinge = np.array([2.0, 3.0, 0.0])
    phi, alpha, theta = 0.7, 0.35, 0.0

    result = transform_markers(markers, hinge, phi=phi, alpha=alpha, theta=theta)

    expected = np.array(
        [
            transform_markers(
                m[np.newaxis, :], hinge, phi=phi, alpha=alpha, theta=theta
            )[0]
            for m in markers
        ]
    )
    np.testing.assert_allclose(result, expected, atol=1e-12)


def test_transform_markers_rejects_zero_marker_input():
    empty = np.zeros((0, 3))
    with pytest.raises(ValueError, match="empty|zero"):
        transform_markers(empty, hinge=(0.0, 0.0, 0.0), phi=0.0, alpha=0.0, theta=0.0)


def test_transform_markers_rejects_non_finite_hinge():
    marker = np.array([[1.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="finite"):
        transform_markers(
            marker, hinge=(float("nan"), 0.0, 0.0), phi=0.0, alpha=0.0, theta=0.0
        )


def test_transform_markers_rejects_wrong_column_count():
    """2-column (x, y) input -- caller forgot z -- is rejected, not silently returned as (N, 2)."""
    markers_2d = np.array([[1.0, 0.0], [0.0, 1.0]])
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        transform_markers(
            markers_2d, hinge=(0.0, 0.0, 0.0), phi=0.0, alpha=0.0, theta=0.0
        )


def test_wing_outline_from_vertex_file():
    """The convex-hull outline matches scipy.spatial.ConvexHull called directly."""
    rng = np.random.default_rng(0)
    xy = rng.uniform(-1.0, 1.0, size=(30, 2))
    markers = np.column_stack([xy, np.zeros(30)])

    outline = wing_outline(markers)

    expected_hull = ConvexHull(xy)
    expected_points = markers[expected_hull.vertices]
    np.testing.assert_allclose(outline, expected_points)


@pytest.mark.parametrize("n_markers", [0, 1, 2])
def test_wing_outline_rejects_too_few_markers(n_markers):
    """<3 markers raises a clear ValueError, not scipy's raw QhullError."""
    with pytest.raises(ValueError, match="at least 3"):
        wing_outline(np.zeros((n_markers, 3)))


def test_wing_outline_rejects_non_finite_markers():
    """NaN/inf markers raise this module's own clear ValueError, not scipy's raw
    'Points cannot contain NaN' -- matches the finite-input convention transform_markers and
    leading_edge_mask already enforce.
    """
    markers = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, float("nan"), 0.0]])
    with pytest.raises(ValueError, match="finite"):
        wing_outline(markers)


def test_wing_outline_rejects_collinear_markers():
    """3+ collinear (chord, span) points can't form a hull -- clear ValueError, not QhullError."""
    collinear = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="degenerate|collinear"):
        wing_outline(collinear)


def test_wing_outline_rejects_wrong_column_count():
    """2-column (x, y) input is rejected outright, not silently returned as an (M, 2) outline."""
    markers_2d = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        wing_outline(markers_2d)


def test_wing_outline_reports_wrong_shape_before_too_few_points():
    """A doubly-wrong input (wrong columns AND too few rows) reports the shape problem first,
    matching the docstring's documented Raises: order -- not the more specific-sounding but
    less fundamental 'need at least 3 markers' message.
    """
    markers_2d_and_too_few = np.array([[0.0, 0.0], [1.0, 0.0]])
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        wing_outline(markers_2d_and_too_few)


def test_wing_outline_preserves_nonzero_z_not_flattened():
    """The hull-vertex markers' own z is returned, not hardcoded to 0 (unlike the vault script
    this replaces -- proves the docstring's claim with markers that actually HAVE nonzero z;
    the sibling flat-z test can't distinguish 'preserved' from 'flattened' since both give the
    same answer when z is already 0 everywhere).
    """
    markers = np.array(
        [
            [0.0, 0.0, 5.0],
            [1.0, 0.0, 6.0],
            [0.0, 1.0, 7.0],
            [1.0, 1.0, 8.0],
            [
                0.5,
                0.5,
                100.0,
            ],  # interior point, not on the hull -- z=100 must not appear
        ]
    )

    outline = wing_outline(markers)

    assert set(outline[:, 2]) == {5.0, 6.0, 7.0, 8.0}
    assert 100.0 not in outline[:, 2]


def test_leading_trailing_edge_split():
    """Markers with x >= 0 are classified leading, matching the vault README convention."""
    markers = np.array(
        [
            [0.5, 0.0, 0.0],  # leading (x >= 0)
            [0.0, 1.0, 0.0],  # leading (x == 0)
            [-0.5, 0.0, 0.0],  # trailing (x < 0)
        ]
    )
    mask = leading_edge_mask(markers)
    np.testing.assert_array_equal(mask, [True, True, False])


def test_leading_edge_mask_rejects_wrong_column_count():
    markers_2d = np.array([[1.0, 0.0], [-1.0, 0.0]])
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        leading_edge_mask(markers_2d)


def test_leading_edge_mask_rejects_non_finite_chord_value():
    """A NaN chord value must raise, not silently misclassify as trailing-edge (NaN >= 0 is
    False, which would otherwise propagate a wrong-but-not-crashing answer).
    """
    markers = np.array([[float("nan"), 0.0, 0.0], [1.0, 0.0, 0.0]])
    with pytest.raises(ValueError, match="finite"):
        leading_edge_mask(markers)


def _visualization_py_files() -> list[Path]:
    files = list(_VISUALIZATION_PKG.rglob("*.py"))
    # A wrong/broken _VISUALIZATION_PKG path would make the two AST-scan tests below vacuously
    # pass (rglob on a nonexistent/empty dir silently yields nothing) instead of actually
    # enforcing the spec requirements they guard -- fail loudly instead.
    assert files, f"expected to find .py files under {_VISUALIZATION_PKG}, found none"
    return files


def test_no_local_rotation_matrix_definition():
    """No module under visualization/ redefines rotation_matrix/euler_angles (spec requirement)."""
    banned_names = {"rotation_matrix", "euler_angles"}
    offending = []
    for path in _visualization_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in banned_names:
                offending.append(f"{path}:{node.name}")
    assert not offending, f"local rotation function(s) found: {offending}"


def test_no_top_level_viz_group_imports():
    """No visualization/ module eagerly imports scipy/skimage/imageio_ffmpeg at module top."""
    offending = []
    for path in _visualization_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:  # only top-level statements, not inside functions
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                if name in _VIZ_GROUP_MODULES:
                    offending.append(f"{path}: top-level import of {name!r}")
    assert not offending, f"eager viz-group import(s) found: {offending}"
