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
    sphere_cv_steadiness_fraction,
    unsteady_momentum_force,
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
    gradpx = np.zeros((1, n, n))
    # NaN in a velocity plane.
    u_nan = u.copy()
    u_nan[0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        periodic_duct_drag(
            u, u_nan, gradpx, rho=1.0, cell_area=0.01, cell_thickness=0.1
        )
    # inf in a velocity plane.
    u_inf = u.copy()
    u_inf[1, 1] = np.inf
    with pytest.raises(ValueError, match="non-finite"):
        periodic_duct_drag(
            u, u_inf, gradpx, rho=1.0, cell_area=0.01, cell_thickness=0.1
        )
    # NaN in the gradpx volume (the pressure path).
    gradpx_nan = gradpx.copy()
    gradpx_nan[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="non-finite"):
        periodic_duct_drag(
            u, u, gradpx_nan, rho=1.0, cell_area=0.01, cell_thickness=0.1
        )


def test_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shapes differ"):
        periodic_duct_drag(
            np.ones((8, 8)),
            np.ones((4, 8)),
            np.zeros((1, 8, 8)),
            rho=1.0,
            cell_area=0.01,
            cell_thickness=0.1,
        )


def test_unsteady_momentum_force_known_answer():
    # rho * (sum(u_new) - sum(u_old)) * dV / dt.
    rho, dV, dt, n = 1.3, 0.001, 0.5, 10
    u_old = np.full((3, n, n), 1.0)
    u_new = u_old + 0.2
    f = unsteady_momentum_force(u_old, u_new, rho=rho, cell_volume=dV, dt=dt)
    expected = rho * (0.2 * 3 * n * n) * dV / dt
    np.testing.assert_allclose(f, expected, rtol=1e-12)
    # A steady field (old == new) gives zero.
    assert unsteady_momentum_force(u_old, u_old, rho=rho, cell_volume=dV, dt=dt) == 0.0


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


def _sphere_plt(grid: str, step: int = 10000) -> str:
    root = os.environ.get("MOSQUITO_CFD_PLOTFILE_ROOT", "")
    sub = {"coarse": "flow_past_sphere_coarse", "medium": "flow_past_sphere_10k"}[grid]
    return str(Path(root) / sub / f"plt{step:05d}")


def test_sphere_cv_drag_rejects_swapped_planes():
    # Guard raises BEFORE any plotfile I/O, so this is cluster-free.
    with pytest.raises(ValueError, match="upstream"):
        sphere_cv_drag_cd("no/such/plotfile", x_inlet=8.0, x_outlet=2.0)
    with pytest.raises(ValueError, match="upstream"):
        sphere_cv_drag_cd("no/such/plotfile", x_inlet=5.0, x_outlet=5.0)


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


@pytest.mark.requires_plotfile
def test_sphere_cv_steadiness_gate():
    # Design Decision 6: the verdict stands only if the unsteady momentum term is << the drag.
    # plt09900 -> plt10000 is 100 steps at fixed_dt=0.01 -> dt=1.0.
    s = sphere_cv_steadiness_fraction(
        _sphere_plt("medium", step=9900),
        _sphere_plt("medium", step=10000),
        x_inlet=2.0,
        x_outlet=8.0,
        dt=1.0,
    )
    assert s["fraction"] < 0.05, (
        f"unsteady term is {s['fraction']:.1%} of drag — steady-state assumption fails; verdict void"
    )


@pytest.mark.requires_plotfile
def test_extract_sphere_cd_default_preserves_contract():
    from mosquito_cfd.benchmarks.analyze_sphere import extract_sphere_cd

    r = extract_sphere_cd(_sphere_plt("medium"))  # default method="marker"
    for key in (
        "cd",
        "fx_sum",
        "fy_sum",
        "fz_sum",
        "n_particles",
        "time",
        "validated",
        "error_pct",
        "literature_cd",
    ):
        assert key in r, f"missing back-compat key {key}"
    # Legacy marker path reproduces the known ~0.448 under-reported value.
    assert 0.4 < r["cd"] < 0.5


@pytest.mark.requires_plotfile
def test_extract_sphere_cd_cv_method_reports_field_cd():
    from mosquito_cfd.benchmarks.analyze_sphere import extract_sphere_cd

    plt = _sphere_plt("medium")
    r = extract_sphere_cd(plt, method="cv", x_inlet=2.0, x_outlet=8.0)
    # cd must EQUAL the periodic-duct CV value (not merely be "large").
    expected = sphere_cv_drag_cd(plt, x_inlet=2.0, x_outlet=8.0)["cd"]
    assert r["cd"] == pytest.approx(expected)
    assert r["cd"] > 0.9  # the field-based CV value (~1.18), not the marker ~0.448
    assert (
        0.4 < r["cd_marker_lastpass"] < 0.5
    )  # marker diagnostic still present, relabelled


# --- cluster-free wiring + robustness (harden-force-extraction) -------------------------------


def _synthetic_box(*, nx, ny, nz, dx, U, c, G, i_in, i_out):
    """A synthetic Eulerian box (the dict `extract_eulerian_box` returns) with a known drag.

    Uniform inlet velocity U everywhere except the outlet plane (slowed to c*U). `gradpx` ramps
    along x as ``G*(ix+1)`` (NON-uniform on purpose, so the pressure-slice test pins plane
    *identity*, not merely slice width). Lets a known-answer test drive sphere_cv_drag_cd with no
    plotfile.
    """
    shape = (nx, ny, nz)
    u = np.full(shape, U, dtype=np.float64)
    u[i_out, :, :] = c * U  # only the outlet plane is slowed
    gradpx = (G * (np.arange(nx) + 1.0))[:, None, None] * np.ones(shape)
    box = {
        "u": u,
        "v": np.zeros(shape),
        "w": np.zeros(shape),
        "gradpx": gradpx.astype(np.float64),
        "gradpy": np.zeros(shape),
        "gradpz": np.zeros(shape),
        "x": (np.arange(nx) + 0.5) * dx[0],
        "y": (np.arange(ny) + 0.5) * dx[1],
        "z": (np.arange(nz) + 0.5) * dx[2],
        "dx": np.asarray(dx, dtype=np.float64),
    }
    return box, i_in, i_out


def _expected_cv_cd(box, i_in, i_out):
    """Independently compute the closed-form CV Cd from the synthetic box fields.

    Computes the periodic-duct integral straight from the arrays (so it is independent of the
    `sphere_cv_drag_cd` wiring under test): drag = rho(Σu_in² − Σu_out²)dA − Σgradpx[in:out] dV.
    """
    dy, dz, dxs = float(box["dx"][1]), float(box["dx"][2]), float(box["dx"][0])
    momentum = (np.sum(box["u"][i_in] ** 2) - np.sum(box["u"][i_out] ** 2)) * dy * dz
    pressure = np.sum(box["gradpx"][i_in:i_out]) * dy * dz * dxs
    return cd_from_drag(momentum - pressure, rho=1.0, u_inf=1.0, diameter=1.0)


def test_sphere_cv_drag_wiring_known_answer(monkeypatch):
    import mosquito_cfd.benchmarks.stress_integral as si

    nx, ny, nz = 10, 4, 3
    dx = (0.2, 0.5, 0.25)
    U, c, G = 1.0, 0.8, 0.3
    i_in, i_out = 1, 6
    box, i_in, i_out = _synthetic_box(
        nx=nx, ny=ny, nz=nz, dx=dx, U=U, c=c, G=G, i_in=i_in, i_out=i_out
    )
    monkeypatch.setattr(si, "extract_eulerian_box", lambda *a, **k: box)

    x_inlet = float(box["x"][i_in])
    x_outlet = float(box["x"][i_out])
    r = si.sphere_cv_drag_cd("dummy", x_inlet=x_inlet, x_outlet=x_outlet)

    assert r["cd"] == pytest.approx(_expected_cv_cd(box, i_in, i_out))
    assert r["x_inlet"] == pytest.approx(x_inlet)
    assert r["x_outlet"] == pytest.approx(x_outlet)


def test_unsteady_dt_nonpositive_raises():
    u = np.ones((2, 2, 2))
    for bad_dt in (0.0, -1.0):
        with pytest.raises(ValueError, match="dt"):
            unsteady_momentum_force(u, u * 1.1, rho=1.0, cell_volume=1e-3, dt=bad_dt)


def test_unsteady_shape_mismatch_raises():
    with pytest.raises(ValueError, match="shapes? differ"):
        unsteady_momentum_force(
            np.ones((2, 2, 2)), np.ones((2, 2, 3)), rho=1.0, cell_volume=1e-3, dt=1.0
        )


def test_unsteady_nonfinite_raises():
    u = np.ones((2, 2, 2))
    for bad_value in (np.nan, np.inf):
        bad = u.copy()
        bad[0, 0, 0] = bad_value
        with pytest.raises(ValueError, match="non-finite"):
            unsteady_momentum_force(u, bad, rho=1.0, cell_volume=1e-3, dt=1.0)


def test_cv_method_without_particles(monkeypatch):
    # CV mode must tolerate a field-only plotfile (no IB particles).
    import mosquito_cfd.benchmarks.analyze_sphere as az
    import mosquito_cfd.benchmarks.stress_integral as si

    box, i_in, i_out = _synthetic_box(
        nx=10, ny=4, nz=3, dx=(0.2, 0.5, 0.25), U=1.0, c=0.8, G=0.3, i_in=1, i_out=6
    )

    class _DS:
        current_time = 100.0

    monkeypatch.setattr(az, "load_plotfile", lambda p: _DS())
    monkeypatch.setattr(
        az,
        "extract_particle_forces",
        lambda ds: (_ for _ in ()).throw(KeyError("no particle_real_comp3")),
    )
    monkeypatch.setattr(si, "extract_eulerian_box", lambda *a, **k: box)

    with pytest.warns(UserWarning, match="marker diagnostic unavailable"):
        r = az.extract_sphere_cd(
            "dummy",
            method="cv",
            x_inlet=float(box["x"][i_in]),
            x_outlet=float(box["x"][i_out]),
        )
    # cd must EQUAL the field-based CV value, not merely be positive.
    assert r["cd"] == pytest.approx(_expected_cv_cd(box, i_in, i_out))
    assert r["cd_marker_lastpass"] is None  # best-effort diagnostic degraded cleanly
    assert r["n_particles"] == 0 and r["fx_sum"] is None


def test_marker_method_requires_particles(monkeypatch):
    import mosquito_cfd.benchmarks.analyze_sphere as az

    class _DS:
        current_time = 100.0

    monkeypatch.setattr(az, "load_plotfile", lambda p: _DS())
    monkeypatch.setattr(
        az,
        "extract_particle_forces",
        lambda ds: (_ for _ in ()).throw(KeyError("no particle_real_comp3")),
    )
    with pytest.raises(KeyError):
        az.extract_sphere_cd(
            "dummy"
        )  # default method="marker" still requires particles


def test_steadiness_fraction_zero_drag_is_inf(monkeypatch):
    # A null/uniform box has zero CV drag; the gate must report inf, not raise ZeroDivisionError.
    import mosquito_cfd.benchmarks.stress_integral as si

    box, i_in, i_out = _synthetic_box(
        nx=10, ny=4, nz=3, dx=(0.2, 0.5, 0.25), U=1.0, c=1.0, G=0.0, i_in=1, i_out=6
    )
    monkeypatch.setattr(si, "extract_eulerian_box", lambda *a, **k: box)
    s = si.sphere_cv_steadiness_fraction(
        "old",
        "new",
        x_inlet=float(box["x"][i_in]),
        x_outlet=float(box["x"][i_out]),
        dt=1.0,
    )
    assert s["drag"] == pytest.approx(0.0)
    assert s["fraction"] == float("inf")


# --- T3b: committed synthetic boxlib plotfile fixture (closes the #33 yt-read CI gap) ----------

_LEV_FIXTURE = Path("tests/fixtures/lev_boxlib_plt")
_FULL = (-np.inf, -np.inf, -np.inf), (np.inf, np.inf, np.inf)


def test_synthetic_fixture_reads_through_eulerian_box():
    """The committed synthetic boxlib plotfile exercises the extract_eulerian_box yt read in CI.

    Before #33 the adapter's actual yt read (covering_grid, ('boxlib', ...) field tuples, FP64 unwrap,
    max_level == 0) was covered ONLY by requires_plotfile tests that auto-skip in CI. This committed
    fixture closes that gap cluster-free — a regression in the yt-reading layer now fails in CI.
    """
    box = extract_eulerian_box(str(_LEV_FIXTURE), lo=_FULL[0], hi=_FULL[1])
    for key in ("u", "v", "w", "gradpx", "gradpy", "gradpz"):
        assert isinstance(box[key], np.ndarray)  # bare numpy, not unyt_array
        assert box[key].dtype == np.float64  # FP64 (the fp32-build catch is exercised)
        assert box[key].ndim == 3  # [ix, iy, iz]
    np.testing.assert_allclose(box["dx"], [1.0, 1.0, 1.0])
    for a in ("x", "y", "z"):
        assert box[a].ndim == 1
    assert box["current_time"] == pytest.approx(0.5)


def test_fixture_is_regenerable(tmp_path):
    """The committed fixture matches a fresh generator run — auditable + regenerable, not an opaque blob."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_make_lev_fixture", "tests/fixtures/make_lev_boxlib_fixture.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    regenerated = mod.write_fixture(tmp_path / "lev_boxlib_plt")

    committed = extract_eulerian_box(str(_LEV_FIXTURE), lo=_FULL[0], hi=_FULL[1])
    fresh = extract_eulerian_box(str(regenerated), lo=_FULL[0], hi=_FULL[1])
    for key in ("u", "v", "w", "gradpx", "gradpy", "gradpz"):
        np.testing.assert_array_equal(committed[key], fresh[key])
