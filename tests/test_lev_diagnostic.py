"""Cluster-free tests for the LEV vorticity / Q-criterion pure functions (Tier T3a).

Verifies the curl and Q math against synthetic fields with KNOWN ANALYTIC answers (solid-body
rotation -> |omega| = 2*Omega, Q = Omega^2; pure shear -> |omega| = gamma, Q = 0), plus the reported
(not gated) posture, per-axis anisotropic spacing, and the >=3-points-per-axis guard. Pure numpy; no
plotfile / cluster (the yt field extraction + the "LEV present at medium" call are T3b).
"""

from __future__ import annotations

import numpy as np
import pytest

from mosquito_cfd.benchmarks.lev import q_criterion, vorticity_magnitude


def _coords(nx, ny, nz, dx, dy, dz):
    """(X, Y, Z) meshgrids with ij indexing so X[i,j,k]=i*dx, etc."""
    x = np.arange(nx) * dx
    y = np.arange(ny) * dy
    z = np.arange(nz) * dz
    return np.meshgrid(x, y, z, indexing="ij")


def _interior(a):
    return a[1:-1, 1:-1, 1:-1]


def test_vorticity_and_q_on_solid_body_rotation():
    """Solid-body rotation (-Omega*y, Omega*x, 0) -> |omega| = 2*Omega, Q = Omega^2; shear -> gamma, 0."""
    omega = 1.3
    dx = 0.1
    X, Y, Z = _coords(6, 6, 6, dx, dx, dx)
    u = -omega * Y
    v = omega * X
    w = np.zeros_like(X)

    vort = vorticity_magnitude(u, v, w, dx)
    q = q_criterion(u, v, w, dx)
    assert np.allclose(_interior(vort), 2.0 * omega, atol=1e-10)
    assert np.allclose(_interior(q), omega**2, atol=1e-10)

    # Pure shear (gamma*y, 0, 0): |omega| = gamma, Q = 0 (rotation and strain cancel).
    gamma = 0.7
    us = gamma * Y
    vs = np.zeros_like(X)
    ws = np.zeros_like(X)
    vort_s = vorticity_magnitude(us, vs, ws, dx)
    q_s = q_criterion(us, vs, ws, dx)
    assert np.allclose(_interior(vort_s), gamma, atol=1e-10)
    assert np.allclose(_interior(q_s), 0.0, atol=1e-10)


def test_lev_edge_cases():
    """Uniform field -> 0/0; anisotropic spacing honored (scalar != triple); <3 points raises."""
    dx = 0.1

    # (a) Uniform (zero-gradient) field -> |omega| = 0, Q = 0, returned as reported arrays.
    uniform = np.full((5, 5, 5), 3.14)
    vort0 = vorticity_magnitude(uniform, uniform, uniform, dx)
    q0 = q_criterion(uniform, uniform, uniform, dx)
    assert isinstance(vort0, np.ndarray) and isinstance(q0, np.ndarray)
    assert np.allclose(vort0, 0.0, atol=1e-12)
    assert np.allclose(q0, 0.0, atol=1e-12)

    # (b) Anisotropic grid (dy != dx) with a cross-axis gradient du/dy on the mis-spaced axis.
    # Solid-body rotation (-Omega*y, Omega*x, 0): the (dx,dy,dz) triple recovers the analytic 2*Omega,
    # while a scalar dx mis-differentiates du/dy by dy/dx -> Omega*(1 + dy/dx) != 2*Omega (genuinely
    # different, not a tautology).
    omega = 1.3
    dy = 0.25  # deliberately != dx
    X, Y, Z = _coords(6, 6, 6, dx, dy, dx)
    u = -omega * Y
    v = omega * X
    w = np.zeros_like(X)

    vort_triple = vorticity_magnitude(u, v, w, (dx, dy, dx))
    vort_scalar = vorticity_magnitude(u, v, w, dx)
    assert np.allclose(_interior(vort_triple), 2.0 * omega, atol=1e-10)
    # Scalar spacing on the anisotropic grid is WRONG by the cross-axis factor.
    wrong = omega * (1.0 + dy / dx)  # = Omega*(1 + 2.5) = 4.55
    assert np.allclose(_interior(vort_scalar), wrong, atol=1e-10)
    assert not np.allclose(_interior(vort_scalar), 2.0 * omega, atol=1e-6)

    # (c) Fewer than 3 points on any axis raises (a centred gradient needs >= 3 points); exactly 3 ok.
    Xs, Ys, Zs = _coords(2, 4, 4, dx, dx, dx)  # 2 points on axis 0
    two = -omega * Ys
    with pytest.raises(ValueError, match="at least 3"):
        vorticity_magnitude(two, omega * Xs, np.zeros_like(Xs), dx)
    with pytest.raises(ValueError, match="at least 3"):
        q_criterion(two, omega * Xs, np.zeros_like(Xs), dx)

    X3, Y3, Z3 = _coords(3, 3, 3, dx, dx, dx)  # exactly 3 on every axis -> OK
    ok = vorticity_magnitude(-omega * Y3, omega * X3, np.zeros_like(X3), dx)
    assert ok.shape == (3, 3, 3)
    assert np.isfinite(ok).all()


def test_lev_spacing_validation():
    """spacing must be a positive scalar or a length-3 (dx,dy,dz) triple; else a clear ValueError."""
    field = np.zeros((4, 4, 4))
    with pytest.raises(ValueError, match="scalar or a length-3"):
        vorticity_magnitude(field, field, field, (0.1, 0.2))  # length-2 sequence
    with pytest.raises(ValueError, match="scalar or a length-3"):
        # A 2-D (1,3) array has size 3 but must raise a clear ValueError, NOT leak a TypeError
        # from float(arr[0]) in the per-axis branch.
        q_criterion(field, field, field, np.array([[0.1, 0.2, 0.3]]))
    with pytest.raises(ValueError, match="finite and positive"):
        q_criterion(field, field, field, (0.1, -0.2, 0.1))  # non-positive component
    with pytest.raises(ValueError, match="finite and positive"):
        vorticity_magnitude(
            field, field, field, 0.0
        )  # zero spacing -> division blow-up
    # NaN/inf spacing exercises the isfinite clause INDEPENDENTLY: `nan <= 0` is False, so the
    # `(arr <= 0)` clause never catches it — only the `not isfinite` clause does.
    with pytest.raises(ValueError, match="finite and positive"):
        q_criterion(field, field, field, (np.nan, 0.1, 0.1))
    with pytest.raises(ValueError, match="finite and positive"):
        vorticity_magnitude(field, field, field, np.inf)


def test_lev_rejects_nonfinite_field():
    """A NaN/inf field cell raises (never spreads silently through the gradient stencil)."""
    omega = 1.3
    dx = 0.1
    X, Y, Z = _coords(5, 5, 5, dx, dx, dx)
    u = -omega * Y
    v = omega * X
    w = np.zeros_like(X)
    bad = u.copy()
    bad[2, 2, 2] = np.nan
    with pytest.raises(ValueError, match="finite"):
        vorticity_magnitude(bad, v, w, dx)
    inf_w = w.copy()
    inf_w[0, 0, 0] = np.inf
    with pytest.raises(ValueError, match="finite"):
        q_criterion(u, v, inf_w, dx)


def test_lev_rejects_shape_mismatch_and_non_3d():
    """Mismatched component shapes and non-3-D inputs raise (never a silent broadcast)."""
    good = np.zeros((4, 4, 4))
    with pytest.raises(ValueError, match="same shape"):
        vorticity_magnitude(good, np.zeros((4, 4, 3)), good, 0.1)
    with pytest.raises(ValueError, match="3-D"):
        q_criterion(np.zeros((4, 4)), np.zeros((4, 4)), np.zeros((4, 4)), 0.1)
