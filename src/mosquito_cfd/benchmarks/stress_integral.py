"""Field-based (IB-marker-free) drag extraction for the FlowPastSphere benchmark.

Tier T1b, Stage 1 of the aerodynamics-validation program. The corrected diffused-IB force is
**not** recoverable from the committed plotfile markers (T1a; ``docs/aerodynamics_validation/
t1a-findings.md``). But drag is a physical property of the resolved flow and *is* recoverable
from the persisted Eulerian fields via a control-volume momentum balance.

Stage 1 is a **single-plane wake survey**: place the control-volume side faces in the freestream
so the box collapses to one downstream plane, where

    F_drag = rho * integral u_x (U_inf - u_x) dA + integral (p_inf - p) dA.

Physically: the sphere leaves a momentum (velocity) deficit and a pressure deficit in its wake;
that lost momentum is the drag (Newton's third law). Because the H1/H2 question is a ~2.4x
discrimination (1.087 vs 0.45), the single plane is decisive; the full 6-face box is a Stage-2
confirmation built only if the survey lands band-edge ambiguous (design Decision 1).

All functions are pure numpy (FP64), with no plotfile or cluster dependency, so they are
unit-testable against analytic known-answer fields in cluster-free CI.
"""

from __future__ import annotations

import numpy as np


def cd_from_drag(
    fx: float,
    *,
    rho: float,
    u_inf: float,
    diameter: float,
) -> float:
    """Drag coefficient from a streamwise drag force.

    ``Cd = Fx / (0.5 * rho * U_inf^2 * A)`` with frontal area ``A = pi * D^2 / 4``.

    Args:
        fx: Streamwise drag force on the body (same units as ``rho * U^2 * D^2``).
        rho: Fluid density.
        u_inf: Freestream velocity.
        diameter: Body diameter (frontal length scale).

    Returns:
        The dimensionless drag coefficient.
    """
    area = np.pi * diameter**2 / 4.0
    return float(fx / (0.5 * rho * u_inf**2 * area))


def wake_survey_drag(
    u_streamwise: np.ndarray,
    pressure: np.ndarray,
    *,
    rho: float,
    u_inf: float,
    p_inf: float,
    cell_area: float,
) -> float:
    """Streamwise drag from a single downstream wake plane (momentum + pressure deficit).

    Evaluates ``D = rho * sum[ u (U_inf - u) ] * dA + sum[ p_inf - p ] * dA`` over the plane
    (midpoint rule on cell-centered data). Valid when the plane's outer edge lies in the
    freestream and the flow is steady (the unsteady term is handled separately by the caller's
    steadiness gate). The pressure enters only as the deficit ``p_inf - p``, so it is invariant
    to the unknown additive constant in a pressure reconstructed from ``grad p``.

    Args:
        u_streamwise: Streamwise velocity ``u_x`` on the plane (2-D array, FP64).
        pressure: Static pressure on the plane (2-D array, same shape).
        rho: Fluid density.
        u_inf: Freestream streamwise velocity.
        p_inf: Freestream static pressure (the plane's freestream-edge value).
        cell_area: Area of one plane cell (``dy * dz``); uniform over the plane.

    Returns:
        The streamwise drag force on the body.
    """
    u_streamwise = np.asarray(u_streamwise, dtype=np.float64)
    pressure = np.asarray(pressure, dtype=np.float64)
    if not np.isfinite(u_streamwise).all() or not np.isfinite(pressure).all():
        raise ValueError("wake-survey plane contains non-finite values (NaN/inf)")
    momentum = rho * np.sum(u_streamwise * (u_inf - u_streamwise)) * cell_area
    pressure_term = np.sum(p_inf - pressure) * cell_area
    return float(momentum + pressure_term)


def recover_pressure_in_plane(
    gradp_y: np.ndarray,
    gradp_z: np.ndarray,
    *,
    dy: float,
    dz: float,
) -> np.ndarray:
    """Reconstruct in-plane pressure (up to an additive constant) from its gradient.

    The plotfiles persist ``grad p`` (verified true, unscaled ``grad p``; IAMReX
    ``Projection.cpp:305``), not ``p``. On a y-z plane, integrate the gradient along a fixed
    path from the ``(0, 0)`` reference cell: ``grad p_y`` down the first column, then ``grad p_z``
    along each row (trapezoid rule). The unknown reference constant cancels in the wake-survey
    pressure deficit ``p_inf - p``.

    Args:
        gradp_y: ``d p / d y`` on the plane (2-D array, FP64), indexed ``[iy, iz]``.
        gradp_z: ``d p / d z`` on the plane (same shape).
        dy: Cell spacing along y.
        dz: Cell spacing along z.

    Returns:
        Pressure on the plane, up to an additive constant (``p[0, 0] == 0``).
    """
    gradp_y = np.asarray(gradp_y, dtype=np.float64)
    gradp_z = np.asarray(gradp_z, dtype=np.float64)
    # Column y-integral at z = z[0], broadcast across columns: p[iy, :] = trapz gradp_y[:, 0] dy.
    p_col = _cumulative_trapezoid(gradp_y[:, 0], dy)  # shape (ny,)
    # Row z-integrals from each row's start: p[iy, iz] += trapz of gradp_z[iy, :] dz.
    p_row = _cumulative_trapezoid(gradp_z, dz, axis=1)  # shape (ny, nz)
    return p_col[:, None] + p_row


def _cumulative_trapezoid(
    values: np.ndarray, spacing: float, *, axis: int = 0
) -> np.ndarray:
    """Cumulative trapezoidal integral along ``axis``, starting at 0 (same shape as input)."""
    values = np.asarray(values, dtype=np.float64)
    avg = 0.5 * (
        np.take(values, range(1, values.shape[axis]), axis=axis)
        + np.take(values, range(0, values.shape[axis] - 1), axis=axis)
    )
    increments = avg * spacing
    cumulative = np.cumsum(increments, axis=axis)
    zero_shape = list(values.shape)
    zero_shape[axis] = 1
    return np.concatenate([np.zeros(zero_shape), cumulative], axis=axis)
