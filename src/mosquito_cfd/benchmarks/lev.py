"""Leading-edge-vortex (LEV) vorticity / Q-criterion pure functions (Tier T3a), analysis-only.

Pure numpy diagnostics for the LEV "resolved/present" oracle: the **vorticity magnitude**
(``||curl u||``) and the **Q-criterion** (``Q = 0.5*(||Omega||^2 - ||S||^2)``, the **half-difference**
convention, where ``Omega``/``S`` are the antisymmetric/symmetric parts of the velocity-gradient
tensor ``grad u``). They are computed from a 3-D velocity field on a uniform grid via ``np.gradient``.

These are **reported, never gated** — no magic-number pass/fail threshold. In T3a they are verified
against known-analytic synthetic fields (solid-body rotation -> ``|omega| = 2*Omega``, ``Q = Omega^2``;
pure shear -> ``|omega| = gamma``, ``Q = 0``). The yt plotfile->field extraction and the actual
"LEV present at medium, weak/absent at coarse" call are **deferred to T3b** (no committed
new-convention plotfile exists in-repo yet).

``spacing`` accepts a **scalar** (isotropic grid) **or** a ``(dx, dy, dz)`` triple passed per-axis to
``np.gradient`` — so the T3b plotfile wiring cannot silently mis-differentiate an anisotropic grid. A
centred gradient needs >= 3 points per axis; fewer raises a clear ``ValueError``, and a non-finite
(NaN/inf) field cell raises rather than spreading silently through the stencil.

**Boundary planes carry lower-order (one-sided) values.** ``np.gradient`` uses a one-sided stencil on
the outermost plane of each axis, so the returned vorticity/Q there is less accurate than the centred
interior; a downstream isosurface threshold (T3b) should be read on the interior, not at the domain
edge (the T3a analytic tests compare only the interior for this reason).

The **half-difference** Q convention (the ``1/2`` factor) is documented here so a downstream Q-isosurface
threshold digitized from a paper that uses the ``||Omega||^2 - ||S||^2`` variant is not applied with a
factor-of-2 mismatch.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

# Minimum points per axis for a centred finite-difference gradient (np.gradient's 2nd-order stencil).
_MIN_POINTS_PER_AXIS = 3


def _spacing_triple(spacing: ArrayLike) -> tuple[float, float, float]:
    """Normalize ``spacing`` to a ``(dx, dy, dz)`` float triple (scalar broadcast to all axes)."""
    arr = np.atleast_1d(np.asarray(spacing, dtype=float))
    # Rank + size first: a 2-D array (e.g. shape (1, 3)) has size 3 but must NOT be read per-axis —
    # `float(arr[0])` on it would leak a raw TypeError instead of the promised clear ValueError.
    if arr.ndim != 1 or arr.size not in (1, 3):
        raise ValueError(
            f"spacing must be a scalar or a length-3 (dx, dy, dz) sequence, got shape {arr.shape}"
        )
    if not np.isfinite(arr).all() or (arr <= 0).any():
        raise ValueError(f"spacing must be finite and positive, got {spacing!r}")
    if arr.size == 1:
        return (float(arr[0]), float(arr[0]), float(arr[0]))
    return (float(arr[0]), float(arr[1]), float(arr[2]))


def _validate_field(
    u: ArrayLike, v: ArrayLike, w: ArrayLike
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(u, v, w)`` as FP64 3-D arrays, raising if they mismatch or any axis has < 3 points."""
    ua = np.asarray(u, dtype=np.float64)
    va = np.asarray(v, dtype=np.float64)
    wa = np.asarray(w, dtype=np.float64)
    if not (ua.shape == va.shape == wa.shape):
        raise ValueError(
            f"u, v, w must share the same shape; got {ua.shape}, {va.shape}, {wa.shape}"
        )
    if ua.ndim != 3:
        raise ValueError(f"u, v, w must be 3-D velocity components; got ndim {ua.ndim}")
    for axis, n in enumerate(ua.shape):
        if n < _MIN_POINTS_PER_AXIS:
            raise ValueError(
                f"a centred gradient needs at least {_MIN_POINTS_PER_AXIS} points per axis; "
                f"axis {axis} has {n}"
            )
    # A non-finite field cell would spread through the centred np.gradient stencil into a silent
    # NaN/inf output; raise loudly instead (matches the sibling flapping_wing graders' no-silent-NaN
    # posture). A diverged CFD field (NaN/inf) should fail the LEV diagnostic, not report garbage.
    if not (np.isfinite(ua).all() and np.isfinite(va).all() and np.isfinite(wa).all()):
        raise ValueError(
            "u, v, w must be finite (no NaN/inf); got a non-finite field cell"
        )
    return ua, va, wa


def _velocity_gradient(
    u: NDArray[np.float64],
    v: NDArray[np.float64],
    w: NDArray[np.float64],
    spacing: ArrayLike,
) -> tuple[NDArray[np.float64], ...]:
    """Nine components of ``grad u`` (``d{u,v,w}/d{x,y,z}``) via per-axis ``np.gradient``."""
    dx, dy, dz = _spacing_triple(spacing)
    ux, uy, uz = np.gradient(u, dx, dy, dz)
    vx, vy, vz = np.gradient(v, dx, dy, dz)
    wx, wy, wz = np.gradient(w, dx, dy, dz)
    return ux, uy, uz, vx, vy, vz, wx, wy, wz


def vorticity_magnitude(
    u: ArrayLike, v: ArrayLike, w: ArrayLike, spacing: ArrayLike
) -> NDArray[np.float64]:
    """Vorticity magnitude ``||curl u||`` of a 3-D velocity field (reported, not gated).

    ``curl u = (dw/dy - dv/dz, du/dz - dw/dx, dv/dx - du/dy)``. On solid-body rotation
    ``(-Omega*y, Omega*x, 0)`` this is uniformly ``2*Omega``; on pure shear ``(gamma*y, 0, 0)`` it is
    ``gamma``.

    Args:
        u: x-velocity component, a 3-D array indexed ``[i, j, k]`` over ``(x, y, z)``.
        v: y-velocity component (same shape as ``u``).
        w: z-velocity component (same shape as ``u``).
        spacing: Grid spacing — a scalar ``dx`` (isotropic) or a ``(dx, dy, dz)`` triple (per-axis).

    Returns:
        A 3-D array of ``||curl u||`` at every grid point (same shape as ``u``).

    Raises:
        ValueError: if ``u``/``v``/``w`` mismatch in shape, are not 3-D, or any axis has < 3 points;
            or if ``spacing`` is not a positive scalar or ``(dx, dy, dz)`` triple.
    """
    u, v, w = _validate_field(u, v, w)
    ux, uy, uz, vx, vy, vz, wx, wy, wz = _velocity_gradient(u, v, w, spacing)
    omega_x = wy - vz
    omega_y = uz - wx
    omega_z = vx - uy
    return np.sqrt(omega_x**2 + omega_y**2 + omega_z**2)


def q_criterion(
    u: ArrayLike, v: ArrayLike, w: ArrayLike, spacing: ArrayLike
) -> NDArray[np.float64]:
    """Q-criterion ``Q = 0.5*(||Omega||^2 - ||S||^2)`` of a 3-D velocity field (reported, not gated).

    ``S = 0.5*(grad u + grad u^T)`` and ``Omega = 0.5*(grad u - grad u^T)`` are the symmetric/
    antisymmetric parts of the velocity-gradient tensor; ``||.||`` is the Frobenius norm. This is the
    **half-difference** convention (the leading ``1/2`` factor) — documented so a Q-isosurface
    threshold from a paper using the ``||Omega||^2 - ||S||^2`` variant is not applied with a 2x
    mismatch. On solid-body rotation ``Q = Omega^2`` (strain ``S = 0``); on pure shear ``Q = 0``
    (rotation and strain cancel).

    Args:
        u: x-velocity component, a 3-D array indexed ``[i, j, k]`` over ``(x, y, z)``.
        v: y-velocity component (same shape as ``u``).
        w: z-velocity component (same shape as ``u``).
        spacing: Grid spacing — a scalar ``dx`` (isotropic) or a ``(dx, dy, dz)`` triple (per-axis).

    Returns:
        A 3-D array of ``Q`` at every grid point (same shape as ``u``); ``Q > 0`` is rotation-dominated.

    Raises:
        ValueError: if ``u``/``v``/``w`` mismatch in shape, are not 3-D, or any axis has < 3 points;
            or if ``spacing`` is not a positive scalar or ``(dx, dy, dz)`` triple.
    """
    u, v, w = _validate_field(u, v, w)
    ux, uy, uz, vx, vy, vz, wx, wy, wz = _velocity_gradient(u, v, w, spacing)
    # Symmetric strain-rate S (diagonal + off-diagonal); Frobenius norm squared.
    s_xy = 0.5 * (uy + vx)
    s_xz = 0.5 * (uz + wx)
    s_yz = 0.5 * (vz + wy)
    s_norm2 = ux**2 + vy**2 + wz**2 + 2.0 * (s_xy**2 + s_xz**2 + s_yz**2)
    # Antisymmetric spin Omega (zero diagonal); Frobenius norm squared.
    o_xy = 0.5 * (uy - vx)
    o_xz = 0.5 * (uz - wx)
    o_yz = 0.5 * (vz - wy)
    o_norm2 = 2.0 * (o_xy**2 + o_xz**2 + o_yz**2)
    return 0.5 * (o_norm2 - s_norm2)
