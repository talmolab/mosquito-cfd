"""Cluster-free known-answer tests for the periodic-duct control-volume drag core.

These exercise the pure-numpy core (`mosquito_cfd.benchmarks.stress_integral`) with hand-built
analytic fields whose drag has a closed form — no yt, no plotfile, no Z: drive. They are the CI
oracle that gates the H1/H2 verdict (add-sphere-stress-cd). The plotfile-backed tests at the
bottom are `requires_plotfile`-marked and run locally against the Z: data.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.benchmarks.stress_integral import (
    cd_from_drag,
    extract_eulerian_box,
    periodic_duct_drag,
    sphere_cv_drag_cd,
)

# --- pure-numpy core: periodic-duct momentum balance -----------------------------------------


def test_momentum_flux_uniform_planes():
    # Inlet uniform U, outlet uniformly slowed to c*U, no pressure gradient.
    # Drag = rho * (U^2 - (cU)^2) * A_plane.
    rho, u_inf, c, n = 1.3, 1.0, 0.8, 16  # rho != 1 deliberately
    dy = dz = 0.1
    cell_area = dy * dz
    u_in = np.full((n, n), u_inf)
    u_out = np.full((n, n), c * u_inf)
    gradpx = np.zeros((1, n, n))
    drag = periodic_duct_drag(
        u_in, u_out, gradpx, rho=rho, cell_area=cell_area, cell_thickness=dy
    )
    expected = rho * (u_inf**2 - (c * u_inf) ** 2) * (n * n) * cell_area
    np.testing.assert_allclose(drag, expected, rtol=1e-12)


def test_momentum_flux_varying_outlet_profile():
    # Outlet has a spatially-varying deficit; check the area sum of u^2 is integrated correctly.
    rho, u_inf, n = 1.0, 1.0, 24
    dy = dz = 0.25
    yy, zz = np.meshgrid(np.arange(n) * dy, np.arange(n) * dz, indexing="ij")
    u_in = np.full((n, n), u_inf)
    u_out = u_inf - 0.3 * np.exp(-((yy - 3) ** 2 + (zz - 3) ** 2))
    gradpx = np.zeros((1, n, n))
    drag = periodic_duct_drag(
        u_in, u_out, gradpx, rho=rho, cell_area=dy * dz, cell_thickness=dy
    )
    expected = rho * (np.sum(u_in**2) - np.sum(u_out**2)) * dy * dz
    np.testing.assert_allclose(drag, expected, rtol=1e-12)
    assert drag > 0.0  # a slowed outlet (wake) is positive drag


def test_pressure_gradient_constant():
    # Identical planes (no momentum change) + constant dp/dx = G over a volume of nz cells.
    # Drag = - integral dp/dx dV = - G * V.
    rho, n, nz = 1.0, 12, 5
    dy = dz = dxs = 0.2
    u = np.full((n, n), 1.0)
    grad = 0.7
    gradpx = np.full((nz, n, n), grad)
    drag = periodic_duct_drag(
        u, u, gradpx, rho=rho, cell_area=dy * dz, cell_thickness=dxs
    )
    volume = nz * dxs * (n * dy) * (n * dz)
    np.testing.assert_allclose(drag, -grad * volume, rtol=1e-12)


def test_null_field_zero_drag():
    n = 8
    u = np.full((n, n), 1.0)
    gradpx = np.zeros((3, n, n))
    drag = periodic_duct_drag(
        u, u, gradpx, rho=1.0, cell_area=0.1 * 0.1, cell_thickness=0.1
    )
    assert abs(drag) <= 1e-12


def test_nan_in_field_raises():
    n = 6
    u = np.full((n, n), 1.0)
    u_bad = u.copy()
    u_bad[0, 0] = np.nan
    gradpx = np.zeros((1, n, n))
    with pytest.raises(ValueError, match="non-finite"):
        periodic_duct_drag(
            u, u_bad, gradpx, rho=1.0, cell_area=0.01, cell_thickness=0.1
        )


def test_cd_from_drag_known_answer():
    # Fx = 0.5 * rho * U^2 * (pi D^2 / 4) for these params -> Cd should be exactly 1.0.
    rho, u_inf, diameter = 1.0, 1.0, 1.0
    fx = 0.5 * rho * u_inf**2 * (np.pi * diameter**2 / 4.0)
    np.testing.assert_allclose(
        cd_from_drag(fx, rho=rho, u_inf=u_inf, diameter=diameter), 1.0, rtol=1e-12
    )


def test_cd_from_drag_matches_definition():
    rho, u_inf, diameter, fx = 2.0, 3.0, 1.5, 7.0
    area = np.pi * diameter**2 / 4.0
    expected = fx / (0.5 * rho * u_inf**2 * area)
    np.testing.assert_allclose(
        cd_from_drag(fx, rho=rho, u_inf=u_inf, diameter=diameter), expected, rtol=1e-12
    )


# --- yt adapter + literature validation (require a plotfile under $MOSQUITO_CFD_PLOTFILE_ROOT) -

# Literature isolated-sphere drag (Johnson & Patel 1999). The committed run is a transversely
# periodic array (pitch 10 D, 5 D upstream), so its true Cd carries an estimated +3-6% confinement
# offset (design Decision 5b). Neither grid is fully converged; they approach the confined target
# from above (coarse ~1.31 > medium ~1.18), so the principled check is on the Richardson
# extrapolation, which lands in the confinement-corrected band.
LITERATURE_CD = 1.087
H2_EXCLUSION = 0.9  # the broken marker value is ~0.45; the field carries ~1.1-1.3
CONFINED_BAND = (
    1.03,
    1.22,
)  # literature to literature + confinement + a convergence margin


def _sphere_plt(grid: str) -> str:
    root = os.environ.get("MOSQUITO_CFD_PLOTFILE_ROOT", "")
    sub = {"coarse": "flow_past_sphere_coarse", "medium": "flow_past_sphere_10k"}[grid]
    return str(Path(root) / sub / "plt10000")


@pytest.mark.requires_plotfile
def test_adapter_single_level_exact_fp64():
    box = extract_eulerian_box(
        _sphere_plt("medium"), lo=(6.5, 0.0, 0.0), hi=(8.0, 10.0, 10.0)
    )
    for key in ("u", "v", "w", "gradpx", "gradpy", "gradpz"):
        assert isinstance(box[key], np.ndarray)  # bare numpy, not unyt_array
        assert box[key].dtype == np.float64
    assert box["x"].ndim == box["y"].ndim == box["z"].ndim == 1
    np.testing.assert_allclose(np.diff(box["x"]), box["dx"][0], rtol=1e-9)


@pytest.mark.requires_plotfile
def test_adapter_pads_for_face_derivatives():
    lo, hi = (7.0, 4.0, 4.0), (7.5, 6.0, 6.0)
    base = extract_eulerian_box(_sphere_plt("medium"), lo=lo, hi=hi, halo=0)
    padded = extract_eulerian_box(_sphere_plt("medium"), lo=lo, hi=hi, halo=2)
    for axis in range(3):
        assert padded["u"].shape[axis] == base["u"].shape[axis] + 4


@pytest.mark.requires_plotfile
def test_sphere_cv_drag_classifies_h1():
    # The decisive H1/H2 experiment: the periodic-duct CV drag on the committed plotfiles.
    coarse = sphere_cv_drag_cd(_sphere_plt("coarse"), x_inlet=2.0, x_outlet=8.0)["cd"]
    medium = sphere_cv_drag_cd(_sphere_plt("medium"), x_inlet=2.0, x_outlet=8.0)["cd"]

    # (1) H2 (the broken ~0.45 marker value) is decisively excluded on both grids.
    assert coarse > H2_EXCLUSION and medium > H2_EXCLUSION, (coarse, medium)
    # (2) Refinement moves Cd toward literature (converges from above).
    assert medium < coarse, (
        f"not converging toward literature: coarse={coarse}, medium={medium}"
    )
    # (3) Richardson extrapolation (r=2, assumed order p=2) lands in the confinement-corrected
    #     band around the isolated literature value -> H1 (extraction bug), with an H1' offset.
    extrapolated = medium - (coarse - medium) / (2.0**2 - 1.0)
    assert CONFINED_BAND[0] <= extrapolated <= CONFINED_BAND[1], (
        f"extrapolated Cd={extrapolated:.3f} outside confinement-corrected band {CONFINED_BAND}"
    )
