"""Single source of aerodynamic force normalization for the force surrogate.

Pure, parameterized force-coefficient math (no I/O). This module is the *only* place the
reference force ``F_ref = 0.5*rho*omega**2*S_yy`` is computed (the van Veen 2022
convention, eq 1.1: the stroke rate at the radius of gyration and the spanwise second
moment of area). The flapping-wing figure script and the dataset extractor import these
helpers rather than re-deriving the formula inline (roadmap cross-cutting concern CC-3).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray


@dataclass(frozen=True)
class ForceReference:
    """Reference quantities for non-dimensionalizing aerodynamic forces.

    van Veen (2022) convention: ``u_ref`` is the speed at the radius of gyration (not the
    wing tip) and ``f_ref = 0.5*rho*omega**2*S_yy`` with ``S_yy = r_gyr**2 * area``.

    Attributes:
        u_ref: Reference speed ``omega * r_gyr`` at the radius of gyration [dimensionless].
        q_ref: Reference dynamic pressure ``0.5 * rho * u_ref**2`` [dimensionless].
        area: Elliptic wing planform area [dimensionless].
        f_ref: Reference force ``q_ref * area`` used to form coefficients [dimensionless].
    """

    u_ref: float
    q_ref: float
    area: float
    f_ref: float


@dataclass(frozen=True)
class MomentReference:
    """Reference quantities for non-dimensionalizing aerodynamic moments.

    The moment reference extends the force reference by a length scale ``L = chord``
    (the standard pitch/aerodynamic-moment normalization): ``m_ref = q_ref * area * chord``.
    ``u_ref``, ``q_ref``, and ``area`` are computed by the *same* formulas as
    :func:`compute_force_reference` (single source — force-surrogate CC-3).

    Attributes:
        u_ref: Reference speed ``omega * r_gyr`` at the radius of gyration [dimensionless].
        q_ref: Reference dynamic pressure ``0.5 * rho * u_ref**2`` [dimensionless].
        area: Elliptic wing planform area [dimensionless].
        length: Moment length scale ``L`` (the chord) [dimensionless].
        m_ref: Reference moment ``q_ref * area * length`` used to form moment coefficients.
    """

    u_ref: float
    q_ref: float
    area: float
    length: float
    m_ref: float


@dataclass(frozen=True, eq=False)
class MomentCoefficients:
    """Aerodynamic moment coefficients (moment / ``M_ref``), dimensionless.

    The three components are **lab-frame** components taken about the **wing hinge**
    (the deck's declared pivot). ``docs/coordinate-convention.md`` is the canonical
    definition of that reference point -- it is named, not justified, here.

    Only the *origin* is the hinge: the axes remain the lab axes as written by IAMReX,
    so these are **not** van Veen wing-frame moments (that would additionally require
    rotating by ``R(t)^T``; GitHub issue #1). The raw ``Mx/My/Mz`` columns carried
    alongside these coefficients are still about the solver's own particle origin.

    A future body-in-the-loop model would want the insect's centre of mass instead;
    that alternative is deliberately deferred, not overlooked.

    The single "pitch moment" axis is deliberately *not* designated here (see the
    force-surrogate roadmap / PR6). ``eq`` is disabled for the same reason as
    :class:`ForceCoefficients`.

    Attributes:
        cf_mx: Moment coefficient about the lab x-axis.
        cf_my: Moment coefficient about the lab y-axis.
        cf_mz: Moment coefficient about the lab z-axis.
    """

    cf_mx: np.floating | NDArray[np.floating]
    cf_my: np.floating | NDArray[np.floating]
    cf_mz: np.floating | NDArray[np.floating]


@dataclass(frozen=True, eq=False)
class ForceCoefficients:
    """Aerodynamic force coefficients (force / ``F_ref``), dimensionless.

    ``eq`` is disabled so the dataclass never does an ambiguous element-wise array
    comparison; equality and hashing therefore fall back to **object identity** by
    design. Compare individual fields (e.g. ``np.testing.assert_allclose``), not whole
    instances. Each field is a numpy array, or a 0-d numpy scalar for scalar inputs.

    Attributes:
        cf_x: Stroke-axis force coefficient.
        cf_y: Lateral force coefficient.
        cf_z: Lift / span-normal force coefficient.
    """

    cf_x: np.floating | NDArray[np.floating]
    cf_y: np.floating | NDArray[np.floating]
    cf_z: np.floating | NDArray[np.floating]


def compute_force_reference(
    f_star: float,
    phi_amp_deg: float,
    r_gyr: float,
    span: float,
    chord: float,
    rho: float = 1.0,
) -> ForceReference:
    """Compute the reference normalization for flapping-wing forces (van Veen 2022).

    Formulas (dimensionless), van Veen eq 1.1 ``F = 0.5*rho*omega**2*S_yy`` with the
    stroke rate at the radius of gyration ``r_gyr`` and ``S_yy = r_gyr**2 * area``::

        u_ref = 2*pi*f_star * radians(phi_amp_deg) * r_gyr   # speed at r_gyr
        q_ref = 0.5 * rho * u_ref**2
        area  = pi/4 * span * chord                          # elliptic planform
        f_ref = q_ref * area = 0.5 * rho * omega**2 * S_yy

    At the validated point (``f_star=1.0, phi_amp_deg=70, r_gyr=R_GYRATION, span=3,
    chord=1``) ``f_ref ≈ 200.27``.

    Args:
        f_star: Dimensionless flap frequency (wingbeats per time unit).
        phi_amp_deg: Stroke amplitude [deg].
        r_gyr: Radius of gyration ``sqrt(S_yy/area)`` [dimensionless] — the van Veen
            normalization arm (``R_GYRATION``), NOT the tip arm.
        span: Wing span [dimensionless].
        chord: Wing chord [dimensionless].
        rho: Fluid density [dimensionless].

    Returns:
        A :class:`ForceReference` with ``u_ref``, ``q_ref``, ``area``, ``f_ref``.
    """
    omega = 2.0 * np.pi * f_star
    u_ref = omega * np.radians(phi_amp_deg) * r_gyr
    q_ref = 0.5 * rho * u_ref**2
    area = np.pi / 4.0 * span * chord
    return ForceReference(
        u_ref=float(u_ref),
        q_ref=float(q_ref),
        area=float(area),
        f_ref=float(q_ref * area),
    )


def compute_moment_reference(
    f_star: float,
    phi_amp_deg: float,
    r_gyr: float,
    span: float,
    chord: float,
    rho: float = 1.0,
) -> MomentReference:
    """Compute the reference normalization for flapping-wing moments (van Veen 2022).

    Extends :func:`compute_force_reference` by the moment length scale ``L = chord``::

        m_ref = q_ref * area * chord

    where ``q_ref`` and ``area`` come from :func:`compute_force_reference` (the single
    source — they are *not* re-derived here; force-surrogate CC-3). At the validated
    point (``f_star=1.0, phi_amp_deg=70, r_gyr=R_GYRATION, span=3, chord=1``)
    ``m_ref ≈ 200.27``, numerically equal to ``f_ref`` only because ``chord == 1.0``.

    Args:
        f_star: Dimensionless flap frequency (wingbeats per time unit).
        phi_amp_deg: Stroke amplitude [deg].
        r_gyr: Radius of gyration (``R_GYRATION``), the van Veen normalization arm.
        span: Wing span [dimensionless].
        chord: Wing chord [dimensionless]; doubles as the moment length scale ``L``.
        rho: Fluid density [dimensionless].

    Returns:
        A :class:`MomentReference` with ``u_ref``, ``q_ref``, ``area``, ``length``
        (the chord), and ``m_ref = q_ref * area * chord``.
    """
    force_ref = compute_force_reference(f_star, phi_amp_deg, r_gyr, span, chord, rho)
    return MomentReference(
        u_ref=force_ref.u_ref,
        q_ref=force_ref.q_ref,
        area=force_ref.area,
        length=float(chord),
        m_ref=float(force_ref.f_ref * chord),
    )


def compute_moment_coefficient(
    mx: ArrayLike,
    my: ArrayLike,
    mz: ArrayLike,
    m_ref: float,
) -> MomentCoefficients:
    """Normalize moment components into dimensionless coefficients.

    Args:
        mx: Moment(s) about the lab x-axis [dimensionless]. Scalar or array-like.
        my: Moment(s) about the lab y-axis.
        mz: Moment(s) about the lab z-axis.
        m_ref: Reference moment from :func:`compute_moment_reference`. Must be nonzero.

    Returns:
        A :class:`MomentCoefficients` with ``cf_m* = M* / m_ref``, preserving the input
        shape. NaN moment inputs propagate to NaN coefficients; an empty input yields an
        empty output.

    Raises:
        ValueError: If ``m_ref <= 0`` (degenerate/non-physical reference), or if
            ``mx``, ``my``, ``mz`` do not share the same shape.
    """
    if m_ref <= 0:
        raise ValueError(
            f"m_ref must be positive to form moment coefficients (got {m_ref}); check "
            "f_star / phi_amp_deg / rho / chord for degenerate or non-physical inputs."
        )
    mx_a = np.asarray(mx, dtype=float)
    my_a = np.asarray(my, dtype=float)
    mz_a = np.asarray(mz, dtype=float)
    if not (mx_a.shape == my_a.shape == mz_a.shape):
        raise ValueError(
            "mx, my, mz must share the same shape; got "
            f"{mx_a.shape}, {my_a.shape}, {mz_a.shape}"
        )
    return MomentCoefficients(
        cf_mx=mx_a / m_ref, cf_my=my_a / m_ref, cf_mz=mz_a / m_ref
    )


def shift_moment_reference(
    mx: ArrayLike,
    my: ArrayLike,
    mz: ArrayLike,
    fx: ArrayLike,
    fy: ArrayLike,
    fz: ArrayLike,
    *,
    offset: ArrayLike,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Move moments to a new reference point via the parallel-axis shift.

    For a moment taken about point ``P``, the moment about a new point ``P'`` is::

        M_P' = M_P + (P - P') x F

    so ``offset`` is the displacement **from the new reference point to the old one**
    (``r_old - r_new``). The identity is exact for a rigid force system, including
    through IAMReX's multidirect sub-iteration accumulation, because the per-marker
    force and moment are the same marker sum and both accumulate in lockstep.

    The full three-component cross product is always evaluated -- no component is
    special-cased and no zero-displacement fast path is taken. That matters: for a
    purely spanwise displacement the y term is ``0.0 * Fx - 0.0 * Fz``, which is
    exactly zero for finite forces but **NaN** for a non-finite one. Short-circuiting
    would make those two cases disagree.

    Note the invariance that follows is a statement about the displacement's
    *components*, not about the span: ``M_y`` is unchanged because ``d_x = d_z = 0``.
    The lab y-axis is the span axis only in the rest pose, so the moment about the
    wing's *instantaneous* span axis is not invariant under a stroke rotation.

    Args:
        mx: Moment(s) about the lab x-axis, taken about the old reference point.
        my: Moment(s) about the lab y-axis.
        mz: Moment(s) about the lab z-axis.
        fx: Total force component along lab x, from the same marker sum as the moments.
        fy: Total force component along lab y.
        fz: Total force component along lab z.
        offset: The three-component displacement ``r_old - r_new``. Must be finite.

    Returns:
        ``(mx, my, mz)`` about the new reference point, preserving the input shape.
        NaN inputs -- and non-finite forces -- propagate rather than being masked.

    Raises:
        ValueError: If ``offset`` is not three finite components, or if the six
            moment/force inputs do not all share the same shape (which would let
            broadcasting silently misalign a force with the wrong moment row).
    """
    d = np.asarray(offset, dtype=float)
    if d.shape != (3,):
        raise ValueError(
            "offset must have exactly three components (the displacement "
            f"r_old - r_new); got shape {d.shape}"
        )
    if not np.all(np.isfinite(d)):
        raise ValueError(
            f"offset must be finite; got {d!r}. A non-finite reference-point "
            "displacement would silently NaN every moment component."
        )

    arrays = [np.asarray(v, dtype=float) for v in (mx, my, mz, fx, fy, fz)]
    shapes = {a.shape for a in arrays}
    if len(shapes) > 1:
        raise ValueError(
            "mx, my, mz, fx, fy, fz must all share the same shape; got "
            f"{[a.shape for a in arrays]}"
        )
    mx_a, my_a, mz_a, fx_a, fy_a, fz_a = arrays

    # Full cross product d x F, evaluated componentwise (see docstring).
    cross_x = d[1] * fz_a - d[2] * fy_a
    cross_y = d[2] * fx_a - d[0] * fz_a
    cross_z = d[0] * fy_a - d[1] * fx_a

    return mx_a + cross_x, my_a + cross_y, mz_a + cross_z


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
        ValueError: If ``f_ref <= 0`` (degenerate/non-physical reference), or if
            ``fx``, ``fy``, ``fz`` do not share the same shape (which would silently
            misalign the coefficient vectors).
    """
    if f_ref <= 0:
        raise ValueError(
            f"f_ref must be positive to form force coefficients (got {f_ref}); check "
            "f_star / phi_amp_deg / rho for degenerate or non-physical inputs."
        )
    fx_a = np.asarray(fx, dtype=float)
    fy_a = np.asarray(fy, dtype=float)
    fz_a = np.asarray(fz, dtype=float)
    if not (fx_a.shape == fy_a.shape == fz_a.shape):
        raise ValueError(
            "fx, fy, fz must share the same shape; got "
            f"{fx_a.shape}, {fy_a.shape}, {fz_a.shape}"
        )
    return ForceCoefficients(cf_x=fx_a / f_ref, cf_y=fy_a / f_ref, cf_z=fz_a / f_ref)
