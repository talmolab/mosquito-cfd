"""Cluster-free tests for the axis-general, rotation-equivariant CV force extractor.

Tier T2a (refactor-wing-axis-convention). These pin the invariance instrument: the field-based
force extractor is coordinate-covariant, so ``F(Q.field) == Q.F(field)`` (CC-V4 orientation/labeling
only), it honours an explicit streamwise axis (no hard-coded ``+x``), and it reduces to the existing
``periodic_duct_drag`` on the x-axis. Pure numpy — no yt, no plotfile, no cluster.
"""

from __future__ import annotations

import numpy as np
import pytest

from mosquito_cfd.benchmarks.stress_integral import (
    cv_force_vector,
    periodic_duct_drag,
    sphere_cv_drag_cd,
)


def _rng():
    # Deterministic without Math.random-style nondeterminism.
    return np.random.default_rng(20260701)


def test_axis_x_reduces_to_periodic_duct_drag():
    """axis=+x: Fx equals periodic_duct_drag; cross-stream Fy,Fz ~ 0 for a pure-x field."""
    rho, u_inf, c, n = 1.3, 1.0, 0.8, 8  # rho != 1 deliberately
    dy = dz = 0.1
    cell_area, ds = dy * dz, dy
    # Pure-x velocity field: only u_x nonzero on each plane.
    u_in = np.zeros((n * n, 3))
    u_in[:, 0] = u_inf
    u_out = np.zeros((n * n, 3))
    u_out[:, 0] = c * u_inf
    gradp = np.zeros((n * n, 3))
    gradp[:, 0] = 0.5  # constant streamwise pressure gradient
    f = cv_force_vector(
        u_in,
        u_out,
        gradp,
        streamwise_axis=np.array([1.0, 0.0, 0.0]),
        rho=rho,
        cell_area=cell_area,
        cell_thickness=ds,
    )
    drag_x = periodic_duct_drag(
        u_in[:, 0].reshape(n, n),
        u_out[:, 0].reshape(n, n),
        gradp[:, 0].reshape(1, n, n),
        rho=rho,
        cell_area=cell_area,
        cell_thickness=ds,
    )
    assert f[0] == pytest.approx(drag_x, rel=1e-12)
    assert f[1] == pytest.approx(0.0, abs=1e-12)
    assert f[2] == pytest.approx(0.0, abs=1e-12)


def test_sphere_entry_point_docstring_documents_its_keys():
    """Backward-compat pin: the sphere entry point still documents its four public return keys.

    ``sphere_cv_drag_cd`` is not modified by T2a — the new axis-general vector is a *separate*
    primitive. This guards that a future edit to the shared module does not silently drop the
    documented keys (behaviour is covered by ``test_sphere_cv_drag_wiring_known_answer``).
    """
    doc = sphere_cv_drag_cd.__doc__ or ""
    for key in ("cd", "drag", "x_inlet", "x_outlet"):
        assert key in doc


def test_non_x_streamwise_axis_matches_manual():
    """axis=+y: Fy equals a hand-rolled momentum balance along y; the analysis never assumes +x."""
    rho, n = 1.0, 6
    da, ds = 0.04, 0.2
    rng = _rng()
    # Velocity along y on the two planes (plus small cross components), gradp along y.
    u_in = rng.normal(size=(n * n, 3))
    u_out = rng.normal(size=(n * n, 3))
    gradp = rng.normal(size=(n * n, 3))
    s = np.array([0.0, 1.0, 0.0])
    f = cv_force_vector(
        u_in, u_out, gradp, streamwise_axis=s, rho=rho, cell_area=da, cell_thickness=ds
    )
    # Manual: F_j = rho*(sum u_j*(u.y) - sum u'_j*(u'.y))*dA - sum gradp_j*dA*ds.
    flux_in = (u_in * (u_in @ s)[:, None]).sum(axis=0)
    flux_out = (u_out * (u_out @ s)[:, None]).sum(axis=0)
    manual = rho * (flux_in - flux_out) * da - gradp.sum(axis=0) * da * ds
    np.testing.assert_allclose(f, manual, rtol=1e-12, atol=1e-12)
    # And the y-component is the "drag" along the supplied axis.
    assert f[1] == pytest.approx(manual[1], rel=1e-12)


def test_rotation_equivariance_off_diagonal_Q():
    """F(Q.field) == Q.F(field) for an off-diagonal Q, with all three force components non-zero."""
    rho, n = 1.0, 5
    da, ds = 0.03, 0.15
    rng = _rng()
    u_in = rng.normal(size=(n * n, 3))
    u_out = rng.normal(size=(n * n, 3))
    gradp = rng.normal(size=(n * n, 3))
    s = np.array([1.0, 0.0, 0.0])
    f = cv_force_vector(
        u_in, u_out, gradp, streamwise_axis=s, rho=rho, cell_area=da, cell_thickness=ds
    )
    # All three components genuinely non-zero, so a dropped/swapped component is detectable.
    assert np.all(np.abs(f) > 1e-6)
    # Off-diagonal proper rotation (x,y,z) -> (y,-x,z).
    q = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    f_rot = cv_force_vector(
        u_in @ q.T,
        u_out @ q.T,
        gradp @ q.T,
        streamwise_axis=q @ s,
        rho=rho,
        cell_area=da,
        cell_thickness=ds,
    )
    np.testing.assert_allclose(f_rot, q @ f, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize(
    "bad_axis",
    [
        np.array([0.0, 0.0, 0.0]),  # zero
        np.array([2.0, 0.0, 0.0]),  # non-unit
        np.array([1.0, 0.0]),  # not a 3-vector
        np.array([np.inf, 0.0, 0.0]),  # non-finite
    ],
)
def test_rejects_bad_streamwise_axis(bad_axis):
    """A zero / non-unit / non-3-vector / non-finite streamwise axis raises, not silently wrong."""
    u = np.ones((4, 3))
    gp = np.zeros((4, 3))
    with pytest.raises(ValueError):
        cv_force_vector(
            u,
            u,
            gp,
            streamwise_axis=bad_axis,
            rho=1.0,
            cell_area=1.0,
            cell_thickness=1.0,
        )


def test_rejects_nonfinite_field():
    """A NaN/inf in a CV field raises rather than returning a silent NaN force."""
    u = np.ones((4, 3))
    bad = np.ones((4, 3))
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        cv_force_vector(
            u,
            bad,
            np.zeros((4, 3)),
            streamwise_axis=np.array([1.0, 0.0, 0.0]),
            rho=1.0,
            cell_area=1.0,
            cell_thickness=1.0,
        )
