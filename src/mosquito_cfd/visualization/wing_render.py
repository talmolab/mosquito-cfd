"""Shared wing marker/outline transform helpers for the visualization package.

OpenSpec change ``add-visualization-tooling``. :func:`transform_markers` rotates body-frame markers
about the caller's ``hinge`` (never the coordinate origin) using the canonical
:func:`mosquito_cfd.benchmarks.wing_kinematics.rotation_matrix` -- no module under
``visualization/`` reimplements wing rotation (spec requirement). :func:`wing_outline` and
:func:`leading_edge_mask` mirror the wing-planform conventions the vault's original video scripts
established (convex-hull outline, leading edge = ``x >= 0``).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix


def _require_xyz_columns(markers_arr: NDArray[np.float64], func_name: str) -> None:
    """Raise a clear ``ValueError`` if ``markers_arr`` isn't shape ``(N, 3)``.

    Without this, a caller who passes 2-column ``(x, y)`` markers (forgetting the ``z`` column)
    gets a silently truncated ``(M, 2)`` return from ``wing_outline``/``transform_markers``
    instead of the ``(*, 3)`` shape every docstring in this module promises -- found by review.
    """
    if markers_arr.ndim != 2 or markers_arr.shape[1] != 3:
        raise ValueError(
            f"{func_name}: markers must be shape (N, 3) (x, y, z), got {markers_arr.shape}"
        )


def transform_markers(
    markers: ArrayLike,
    hinge: ArrayLike,
    phi: float,
    alpha: float,
    theta: float = 0.0,
) -> NDArray[np.float64]:
    """Rotate reference-frame markers about ``hinge`` (not the origin) by ``(phi, alpha, theta)``.

    Args:
        markers: Marker positions, shape ``(N, 3)``, in the same reference frame as ``hinge``.
        hinge: The pivot point ``(x, y, z)`` markers rotate about.
        phi: Stroke angle [rad] (about lab z) -- see
            :func:`mosquito_cfd.benchmarks.wing_kinematics.rotation_matrix`.
        alpha: Pitch angle [rad] (about span y).
        theta: Deviation angle [rad] (about chord x); default 0.

    Returns:
        Transformed marker positions, shape ``(N, 3)``.

    Raises:
        ValueError: If ``markers`` is empty, is not shape ``(N, 3)``, or ``hinge``/``markers``
            contain non-finite values.
    """
    markers_arr = np.asarray(markers, dtype=np.float64)
    if markers_arr.shape[0] == 0:
        raise ValueError("transform_markers: markers array is empty")
    _require_xyz_columns(markers_arr, "transform_markers")
    hinge_arr = np.asarray(hinge, dtype=np.float64)
    if not (np.isfinite(markers_arr).all() and np.isfinite(hinge_arr).all()):
        raise ValueError(
            "transform_markers: markers and hinge must be finite (no NaN/inf); "
            f"got hinge={hinge}"
        )
    r = rotation_matrix(phi, alpha, theta)
    return (r @ (markers_arr - hinge_arr).T).T + hinge_arr


def wing_outline(markers: ArrayLike) -> NDArray[np.float64]:
    """Convex-hull outline of the wing planform in its flat (chord, span) plane.

    Lazily imports ``scipy.spatial.ConvexHull`` (only inside this function, never at module top --
    keeps the module importable without the optional ``viz`` dependency group).

    Args:
        markers: Marker positions, shape ``(N, 3)``, with the planform lying flat in ``(x, y)``.

    Returns:
        Hull-vertex marker positions (their own 3-D coordinates, not flattened to ``z=0``), shape
        ``(M, 3)``, in the order ``scipy.spatial.ConvexHull`` returns.

    Raises:
        ValueError: If ``markers`` is not shape ``(N, 3)``, has fewer than 3 points, contains
            non-finite (NaN/inf) values, or the 2-D (chord, span) projection is degenerate (e.g.
            all collinear) so no convex hull can be constructed.
    """
    markers_arr = np.asarray(markers, dtype=np.float64)
    # Column-shape checked before the point-count check, matching the docstring's Raises: order
    # -- these are orthogonal problems (wrong columns vs. too few rows) and a doubly-wrong input
    # (e.g. a (2, 2) array) should be told about the more fundamental one (wrong shape) first,
    # not "need at least 3 markers" when the real issue is a missing z column.
    _require_xyz_columns(markers_arr, "wing_outline")
    if markers_arr.shape[0] < 3:
        raise ValueError(
            "wing_outline: need at least 3 markers to compute a convex hull, got "
            f"{markers_arr.shape[0]}"
        )
    if not np.isfinite(markers_arr).all():
        # Both siblings (transform_markers, leading_edge_mask) raise this module's own clear
        # message for non-finite input; without this check, scipy's ConvexHull raises its own
        # "Points cannot contain NaN" ValueError instead -- correct exception type, but review
        # found it inconsistent with this module's convention and untested.
        raise ValueError("wing_outline: markers must be finite (no NaN/inf)")
    from scipy.spatial import ConvexHull, QhullError

    try:
        hull = ConvexHull(markers_arr[:, :2])
    except QhullError as exc:
        raise ValueError(
            f"wing_outline: could not compute a convex hull from {markers_arr.shape[0]} "
            f"markers (degenerate/collinear (chord, span) projection?): {exc}"
        ) from exc
    return markers_arr[hull.vertices]


def leading_edge_mask(markers: ArrayLike) -> NDArray[np.bool_]:
    """Classify markers as leading edge (``x >= 0``) vs. trailing edge (``x < 0``).

    Matches the vault README's documented convention (chord axis ``x``, leading edge toward the
    direction of travel).

    Args:
        markers: Marker positions, shape ``(N, 3)``.

    Returns:
        Boolean mask, ``True`` for leading-edge markers.

    Raises:
        ValueError: If ``markers`` is not shape ``(N, 3)`` or contains non-finite chord (``x``)
            values -- ``NaN >= 0`` is silently ``False``, which would otherwise misclassify a bad
            marker as trailing-edge with no error (this module's siblings all reject non-finite
            input explicitly rather than let it propagate a wrong-but-not-crashing answer).
    """
    markers_arr = np.asarray(markers, dtype=np.float64)
    _require_xyz_columns(markers_arr, "leading_edge_mask")
    if not np.isfinite(markers_arr[:, 0]).all():
        raise ValueError(
            "leading_edge_mask: markers' chord (x) column must be finite (no NaN/inf)"
        )
    return markers_arr[:, 0] >= 0
