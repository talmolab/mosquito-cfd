"""Cluster-free known-answer tests for the Stage-1 wake-survey drag core.

These exercise the pure-numpy core (`mosquito_cfd.benchmarks.stress_integral`) with hand-built
analytic fields whose drag has a closed form — no yt, no plotfile, no Z: drive. They are the CI
oracle that gates the H1/H2 verdict (add-sphere-stress-cd, design Decision 4, Stage-1 group).
"""

from __future__ import annotations

import numpy as np

from mosquito_cfd.benchmarks.stress_integral import (
    cd_from_drag,
    recover_pressure_in_plane,
    wake_survey_drag,
)


def _yz_plane(half_width: float, n: int) -> tuple[np.ndarray, np.ndarray, float]:
    """A square y-z plane on [-half_width, half_width]^2 with n cells per side.

    Returns cell-center meshes (yy, zz) and the cell area dA. Cell-centered so the midpoint
    rule applies and no cell straddles the singular origin.
    """
    edges = np.linspace(-half_width, half_width, n + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    d = centers[1] - centers[0]
    yy, zz = np.meshgrid(centers, centers, indexing="ij")
    return yy, zz, d * d


def test_momentum_term_divergence_free_closed_form():
    # Gaussian streamwise wake deficit u = U - A exp(-r^2/2 sigma^2); pressure matched (p=p_inf).
    # Closed form: D = rho * pi * sigma^2 * A * (2U - A)  (box >= 5 sigma so the tail < 0.1%).
    rho, u_inf, amp, sigma = 1.0, 1.0, 0.5, 1.0
    yy, zz, dA = _yz_plane(half_width=6.0, n=240)  # 6 sigma half-width
    r2 = yy**2 + zz**2
    u = u_inf - amp * np.exp(-r2 / (2.0 * sigma**2))
    p = np.zeros_like(u)  # matched pressure: p == p_inf

    drag = wake_survey_drag(u, p, rho=rho, u_inf=u_inf, p_inf=0.0, cell_area=dA)

    expected = rho * np.pi * sigma**2 * amp * (2.0 * u_inf - amp)
    assert abs(drag - expected) / abs(expected) < 0.01


def test_pressure_deficit_term_closed_form():
    # Uniform velocity (no momentum deficit) + Gaussian pressure deficit p = p_inf - dP exp(-r^2/2s^2).
    # Closed form: D = integral (p_inf - p) dA = dP * 2 pi sigma^2.
    rho, u_inf, dP, sigma = (
        1.3,
        1.0,
        0.4,
        1.0,
    )  # rho != 1 deliberately (must not enter pressure term)
    yy, zz, dA = _yz_plane(half_width=6.0, n=240)
    r2 = yy**2 + zz**2
    u = np.full_like(yy, u_inf)
    p_inf = 0.0
    p = p_inf - dP * np.exp(-r2 / (2.0 * sigma**2))

    drag = wake_survey_drag(u, p, rho=rho, u_inf=u_inf, p_inf=p_inf, cell_area=dA)

    expected = dP * 2.0 * np.pi * sigma**2
    assert abs(drag - expected) / abs(expected) < 0.01


def test_null_field_zero_drag():
    rho, u_inf, diameter = 1.0, 1.0, 1.0
    yy, _, dA = _yz_plane(half_width=5.0, n=64)
    u = np.full_like(yy, u_inf)
    p = np.zeros_like(yy)
    drag = wake_survey_drag(u, p, rho=rho, u_inf=u_inf, p_inf=0.0, cell_area=dA)
    assert abs(drag) <= 1e-12 * rho * u_inf**2 * diameter**2


def test_pressure_constant_invariance():
    # Drag uses (p_inf - p), so adding the same constant to both must not change the result.
    rho, u_inf, sigma = 1.0, 1.0, 1.0
    yy, zz, dA = _yz_plane(half_width=6.0, n=120)
    r2 = yy**2 + zz**2
    u = u_inf - 0.5 * np.exp(-r2 / (2.0 * sigma**2))
    p = -0.3 * np.exp(-r2 / (2.0 * sigma**2))
    c = 12345.6
    d0 = wake_survey_drag(u, p, rho=rho, u_inf=u_inf, p_inf=0.0, cell_area=dA)
    d1 = wake_survey_drag(u, p + c, rho=rho, u_inf=u_inf, p_inf=c, cell_area=dA)
    np.testing.assert_allclose(d0, d1, rtol=0.0, atol=1e-9)


def test_sign_convention_deficit_is_positive_drag():
    # A wake (u < U_inf) means the fluid lost streamwise momentum -> positive drag on the body.
    rho, u_inf, sigma = 1.0, 1.0, 1.0
    yy, zz, dA = _yz_plane(half_width=6.0, n=120)
    r2 = yy**2 + zz**2
    u = u_inf - 0.5 * np.exp(-r2 / (2.0 * sigma**2))
    p = np.zeros_like(u)
    drag = wake_survey_drag(u, p, rho=rho, u_inf=u_inf, p_inf=0.0, cell_area=dA)
    assert drag > 0.0


def test_cd_from_drag_known_answer():
    # Fx = 0.5 * rho * U^2 * (pi D^2 / 4) for these params -> Cd should be exactly 1.0.
    rho, u_inf, diameter = 1.0, 1.0, 1.0
    fx = 0.5 * rho * u_inf**2 * (np.pi * diameter**2 / 4.0)
    cd = cd_from_drag(fx, rho=rho, u_inf=u_inf, diameter=diameter)
    np.testing.assert_allclose(cd, 1.0, rtol=1e-12)


def test_cd_from_drag_matches_definition():
    rho, u_inf, diameter, fx = 2.0, 3.0, 1.5, 7.0
    area = np.pi * diameter**2 / 4.0
    expected = fx / (0.5 * rho * u_inf**2 * area)
    np.testing.assert_allclose(
        cd_from_drag(fx, rho=rho, u_inf=u_inf, diameter=diameter), expected, rtol=1e-12
    )


def test_recover_pressure_in_plane_reproduces_known_field():
    # Build a smooth p(y,z), differentiate to get its in-plane gradient, and confirm the
    # reconstruction reproduces p up to an additive constant.
    yy, zz, _ = _yz_plane(half_width=4.0, n=160)
    centers = yy[:, 0]
    dy = dz = centers[1] - centers[0]
    p_true = np.sin(0.5 * yy) * np.cos(0.4 * zz) + 0.1 * yy
    gpy, gpz = np.gradient(p_true, dy, dz, edge_order=2)

    p_rec = recover_pressure_in_plane(gpy, gpz, dy=dy, dz=dz)

    # Equal up to an additive constant -> compare after removing the mean.
    np.testing.assert_allclose(p_rec - p_rec.mean(), p_true - p_true.mean(), atol=5e-3)
