"""Shared wing marker/outline transform helpers for the visualization package.

OpenSpec change ``add-visualization-tooling``. :func:`transform_markers` rotates body-frame markers
about the caller's ``hinge`` (never the coordinate origin) using the canonical
:func:`mosquito_cfd.benchmarks.wing_kinematics.rotation_matrix` -- no module under
``visualization/`` reimplements wing rotation (spec requirement). :func:`wing_outline` and
:func:`leading_edge_mask` mirror the wing-planform conventions the vault's original video scripts
established (convex-hull outline, leading edge = ``x >= 0``).

:func:`config_kwargs`/:func:`resolve_kinematics_kwargs` are the PR2 (Phase 2/3) addition: the
config-name-or-explicit-override resolution pattern `design.md` D3 requires of both
``flow_video.py`` and ``kinematics_video.py``. Shared here (rather than duplicated in each) since
both modules need the identical behavior -- this is the one place ``visualization/`` imports from
``force_surrogate`` (``read_deck_value``, ``parse_config_name``), mirroring the same
lookup ``make_wing_phase_diagnostic.py`` already established at the CLI-script layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import ArrayLike, NDArray

from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix
from mosquito_cfd.force_surrogate.evidence_figure import parse_config_name
from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value


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
        ValueError: If ``markers`` is not shape ``(N, 3)``, is empty, or ``hinge``/``markers``/
            ``phi``/``alpha``/``theta`` contain non-finite values.
    """
    markers_arr = np.asarray(markers, dtype=np.float64)
    # Column-shape checked before emptiness, matching wing_outline's "wrong shape is the more
    # fundamental problem" convention -- round-2 review found the two functions disagreed on
    # this ordering for a doubly-wrong input (e.g. a (0, 2) array).
    _require_xyz_columns(markers_arr, "transform_markers")
    if markers_arr.shape[0] == 0:
        raise ValueError("transform_markers: markers array is empty")
    hinge_arr = np.asarray(hinge, dtype=np.float64)
    if not (np.isfinite(markers_arr).all() and np.isfinite(hinge_arr).all()):
        raise ValueError(
            "transform_markers: markers and hinge must be finite (no NaN/inf); "
            f"got hinge={hinge}"
        )
    if not all(np.isfinite(a) for a in (phi, alpha, theta)):
        # Without this, a non-finite angle NaN-poisons the output via rotation_matrix's cos/sin
        # with only a RuntimeWarning (easily swallowed in batch rendering) -- round-3 review found
        # every existing finite check here targeted markers/hinge, never the angles themselves.
        raise ValueError(
            f"transform_markers: phi, alpha, theta must be finite (no NaN/inf); "
            f"got phi={phi}, alpha={alpha}, theta={theta}"
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


_KINEMATICS_KEYS = (
    "center",
    "hinge",
    "stroke_amp_deg",
    "pitch_amp_deg",
    "frequency_fstar",
)


def config_kwargs(config_name: str, corpus_dir: str | Path) -> dict[str, Any]:
    """Read center/hinge/kinematics for ``config_name`` from its own generated deck.

    Mirrors ``make_wing_phase_diagnostic.py``'s ``_sweep_config_kwargs``: reads hinge/centre from
    the config's OWN deck at ``<corpus_dir>/inputs/inputs.3d.<config_name>`` rather than a shared
    base-deck filename (corpora don't consistently have one at the same location).

    Args:
        config_name: Sweep configuration name (e.g. ``"s45_f115_p60"``).
        corpus_dir: Sweep corpus directory (holds ``inputs/inputs.3d.<config_name>``).

    Returns:
        Dict with ``center``, ``hinge`` (each an ``(x, y, z)`` float tuple),
        ``stroke_amp_deg``, ``pitch_amp_deg``, and ``frequency_fstar``.

    Raises:
        ValueError: If the deck is missing a required key or a value is non-finite (from
            :func:`mosquito_cfd.force_surrogate.geometry_guard.read_deck_value`), or
            ``config_name`` doesn't match the expected ``s<NN>_f<NNN>_p<NN>`` pattern (from
            :func:`mosquito_cfd.force_surrogate.evidence_figure.parse_config_name`).
    """
    deck_path = Path(corpus_dir) / "inputs" / f"inputs.3d.{config_name}"
    deck_text = deck_path.read_text(encoding="utf-8")
    center = tuple(read_deck_value(deck_text, f"particle_inputs.{a}") for a in "xyz")
    hinge = tuple(
        read_deck_value(deck_text, f"particle_inputs.hinge_{a}") for a in "xyz"
    )
    params = parse_config_name(config_name)
    return {
        "center": center,
        "hinge": hinge,
        "stroke_amp_deg": params.phi_amp_deg,
        "pitch_amp_deg": params.pitch_amp_deg,
        "frequency_fstar": params.f_star,
    }


def resolve_kinematics_kwargs(
    *,
    config_name: str | None = None,
    corpus_dir: str | Path | None = None,
    center: ArrayLike | None = None,
    hinge: ArrayLike | None = None,
    stroke_amp_deg: float | None = None,
    pitch_amp_deg: float | None = None,
    frequency_fstar: float | None = None,
) -> dict[str, Any]:
    """Resolve center/hinge/kinematics from a named config, explicit overrides, or both.

    Implements `design.md` D3's config-vs-explicit-kwargs split: ``center``/``hinge``/
    ``stroke_amp_deg``/``pitch_amp_deg``/``frequency_fstar`` are read from ``config_name``'s own
    deck (via :func:`config_kwargs`) when given, then any explicitly supplied (non-``None``)
    keyword argument **overrides** that field -- e.g. a caller can resolve a config's kinematics
    from its deck while overriding only ``hinge`` to a corrected value.

    Args:
        config_name: Sweep configuration name, or ``None`` to resolve every field explicitly.
        corpus_dir: Sweep corpus directory; required together with ``config_name``.
        center: Optional override for the wing centre ``(x, y, z)``.
        hinge: Optional override for the hinge position ``(x, y, z)``.
        stroke_amp_deg: Optional override for the stroke amplitude [deg].
        pitch_amp_deg: Optional override for the pitch amplitude [deg].
        frequency_fstar: Optional override for the dimensionless flap frequency.

    Returns:
        Dict with ``center``, ``hinge``, ``stroke_amp_deg``, ``pitch_amp_deg``,
        ``frequency_fstar`` -- every field resolved, config-derived values replaced in place by
        any override supplied.

    Raises:
        ValueError: If exactly one of ``config_name``/``corpus_dir`` is given (they must be
            supplied together or not at all), or if any of the five fields remains unresolved
            after applying overrides (no config given and that field wasn't overridden either).
    """
    if (config_name is None) != (corpus_dir is None):
        raise ValueError(
            "resolve_kinematics_kwargs: config_name and corpus_dir must be supplied together "
            f"or not at all; got config_name={config_name!r}, corpus_dir={corpus_dir!r}"
        )
    resolved: dict[str, Any] = (
        config_kwargs(config_name, corpus_dir) if config_name is not None else {}
    )
    overrides = {
        "center": center,
        "hinge": hinge,
        "stroke_amp_deg": stroke_amp_deg,
        "pitch_amp_deg": pitch_amp_deg,
        "frequency_fstar": frequency_fstar,
    }
    for key, value in overrides.items():
        if value is not None:
            resolved[key] = value
    missing = [k for k in _KINEMATICS_KEYS if k not in resolved]
    if missing:
        raise ValueError(
            f"resolve_kinematics_kwargs: missing required parameter(s) {missing} -- pass "
            "config_name+corpus_dir, or explicit overrides for all of them"
        )
    return resolved
