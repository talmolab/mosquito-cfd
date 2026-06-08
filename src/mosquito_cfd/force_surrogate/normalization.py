"""Single source of aerodynamic force normalization for the force surrogate.

Pure, parameterized force-coefficient math (no I/O). This module is the *only* place the
reference force ``F_ref = q_tip * area`` is computed; the flapping-wing figure script and
the (future) dataset extractor import these helpers rather than re-deriving the formula
inline (roadmap cross-cutting concern CC-3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True)
class ForceReference:
    """Reference quantities for non-dimensionalizing aerodynamic forces.

    Attributes:
        u_tip_max: Maximum wing-tip speed [dimensionless].
        q_tip: Tip dynamic pressure ``0.5 * rho * u_tip_max**2`` [dimensionless].
        area: Elliptic wing planform area [dimensionless].
        f_ref: Reference force ``q_tip * area`` used to form coefficients [dimensionless].
    """

    u_tip_max: float
    q_tip: float
    area: float
    f_ref: float


@dataclass(frozen=True, eq=False)
class ForceCoefficients:
    """Aerodynamic force coefficients (force / ``F_ref``), dimensionless.

    ``eq`` is disabled so instances are never compared with ``==`` (which would do an
    ambiguous element-wise array comparison). Assert on individual fields instead.

    Attributes:
        cf_x: Stroke-axis force coefficient.
        cf_y: Lateral force coefficient.
        cf_z: Lift / span-normal force coefficient.
    """

    cf_x: NDArray[np.floating]
    cf_y: NDArray[np.floating]
    cf_z: NDArray[np.floating]


def compute_force_reference(
    f_star: float,
    phi_amp_deg: float,
    r_tip: float,
    span: float,
    chord: float,
    rho: float = 1.0,
) -> ForceReference:
    """Compute the reference normalization for flapping-wing forces.

    Formulas (dimensionless)::

        u_tip_max = 2*pi*f_star * radians(phi_amp_deg) * r_tip
        q_tip     = 0.5 * rho * u_tip_max**2
        area      = pi/4 * span * chord        # elliptic planform
        f_ref     = q_tip * area

    Args:
        f_star: Dimensionless flap frequency (wingbeats per time unit).
        phi_amp_deg: Stroke amplitude [deg].
        r_tip: Hinge-to-tip distance [dimensionless].
        span: Wing span [dimensionless].
        chord: Wing chord [dimensionless].
        rho: Fluid density [dimensionless].

    Returns:
        A :class:`ForceReference` with ``u_tip_max``, ``q_tip``, ``area``, ``f_ref``.
    """
    omega = 2.0 * np.pi * f_star
    u_tip_max = omega * np.radians(phi_amp_deg) * r_tip
    q_tip = 0.5 * rho * u_tip_max**2
    area = np.pi / 4.0 * span * chord
    return ForceReference(
        u_tip_max=float(u_tip_max),
        q_tip=float(q_tip),
        area=float(area),
        f_ref=float(q_tip * area),
    )


def compute_force_coefficients(
    fx: ArrayLike,
    fy: ArrayLike,
    fz: ArrayLike,
    f_ref: float,
) -> ForceCoefficients:
    """Normalize force components into dimensionless coefficients.

    Args:
        fx: Stroke-axis force(s) [dimensionless]. Scalar or array-like.
        fy: Lateral force(s).
        fz: Lift / span-normal force(s).
        f_ref: Reference force from :func:`compute_force_reference`. Must be nonzero.

    Returns:
        A :class:`ForceCoefficients` with ``cf_* = F* / f_ref``, preserving the input
        shape. NaN force inputs propagate to NaN coefficients; an empty input yields an
        empty output.

    Raises:
        ValueError: If ``f_ref == 0`` (degenerate kinematics), to avoid inf/NaN output.
    """
    if f_ref == 0:
        raise ValueError(
            "f_ref must be nonzero to form force coefficients (got 0 — check "
            "f_star / phi_amp_deg for degenerate kinematics)."
        )
    return ForceCoefficients(
        cf_x=np.asarray(fx, dtype=float) / f_ref,
        cf_y=np.asarray(fy, dtype=float) / f_ref,
        cf_z=np.asarray(fz, dtype=float) / f_ref,
    )
