"""Field-based (IB-marker-free) drag extraction for the FlowPastSphere benchmark.

Tier T1b, Stage 1 of the aerodynamics-validation program. The corrected diffused-IB force is
**not** recoverable from the committed plotfile markers (T1a; ``docs/aerodynamics_validation/
t1a-findings.md``). But drag is a physical property of the resolved flow and *is* recoverable
from the persisted Eulerian fields via a control-volume momentum balance.

**Method (periodic-duct control volume).** The committed run is periodic in y and z, so the
naive single-plane wake survey (which assumes the lateral faces sit in undisturbed freestream)
is invalid: with periodic walls and blockage, the bypass flow accelerates above ``U_inf`` across
the whole cross-section (see ``design.md`` "Why two-plane periodic-duct instead of single-plane
wake survey"). But periodicity makes the correct balance *simpler*: take a control volume
spanning the full y-z period between an inlet plane ``x1`` and an outlet plane ``x2``. The lateral
faces carry identical fields on opposite (periodic) sides, so they cancel exactly, leaving

    F_drag = rho * ( integral_{x1} u_x^2 dA - integral_{x2} u_x^2 dA )  -  integral_V dp/dx dV,

with the pressure term written from the persisted ``gradpx`` (the unknown additive pressure
constant cancels because both planes have equal area). The streamwise viscous flux on the two
planes is O(1/Re) of the pressure/momentum terms in smooth flow and is neglected at Stage 1
(the H1/H2 question is a ~2.4x discrimination, not a sub-1% measurement). Physically the pressure
drop across the body is the form drag, which dominates sphere Cd at Re=100.

All numerical functions are pure numpy (FP64), with no plotfile or cluster dependency, so they
are unit-testable against analytic known-answer fields in cluster-free CI. The yt adapter is the
only cluster-touching code (lazy yt import).
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
        fx: Streamwise drag force on the body.
        rho: Fluid density.
        u_inf: Freestream velocity.
        diameter: Body diameter (frontal length scale).

    Returns:
        The dimensionless drag coefficient.
    """
    area = np.pi * diameter**2 / 4.0
    return float(fx / (0.5 * rho * u_inf**2 * area))


def periodic_duct_drag(
    u_inlet: np.ndarray,
    u_outlet: np.ndarray,
    gradpx_volume: np.ndarray,
    *,
    rho: float,
    cell_area: float,
    cell_thickness: float,
) -> float:
    """Streamwise drag from a periodic-duct control-volume momentum balance.

    For a control volume spanning the full periodic y-z cross-section between an inlet plane and
    an outlet plane, the lateral (periodic) faces cancel and

        F_drag = rho * ( sum(u_inlet^2) - sum(u_outlet^2) ) * dA  -  sum(gradpx_volume) * dA * dx.

    The pressure term ``- integral dp/dx dV`` uses the persisted ``gradpx`` directly; the unknown
    additive pressure constant cancels (both planes have equal area).

    Args:
        u_inlet: Streamwise velocity on the inlet plane (2-D array, FP64).
        u_outlet: Streamwise velocity on the outlet plane (same shape).
        gradpx_volume: ``dp/dx`` over the cells between the planes (3-D array, FP64).
        rho: Fluid density.
        cell_area: Area of one plane cell (``dy * dz``).
        cell_thickness: Streamwise cell size ``dx``.

    Returns:
        The streamwise drag force on the body.
    """
    u_inlet = np.asarray(u_inlet, dtype=np.float64)
    u_outlet = np.asarray(u_outlet, dtype=np.float64)
    gradpx_volume = np.asarray(gradpx_volume, dtype=np.float64)
    if u_inlet.shape != u_outlet.shape:
        raise ValueError(
            f"inlet/outlet plane shapes differ: {u_inlet.shape} vs {u_outlet.shape}"
        )
    for name, arr in (
        ("u_inlet", u_inlet),
        ("u_outlet", u_outlet),
        ("gradpx", gradpx_volume),
    ):
        if not np.isfinite(arr).all():
            raise ValueError(
                f"control-volume field {name} contains non-finite values (NaN/inf)"
            )
    momentum_flux = rho * (np.sum(u_inlet**2) - np.sum(u_outlet**2)) * cell_area
    pressure = np.sum(gradpx_volume) * cell_area * cell_thickness
    return float(momentum_flux - pressure)


# --- yt adapter (the only cluster-touching code; yt imported lazily) --------------------------

_REQUIRED_FIELDS = (
    ("boxlib", "x_velocity"),
    ("boxlib", "y_velocity"),
    ("boxlib", "z_velocity"),
    ("boxlib", "gradpx"),
    ("boxlib", "gradpy"),
    ("boxlib", "gradpz"),
)


def extract_eulerian_box(
    plotfile_path: str,
    *,
    lo: tuple[float, float, float],
    hi: tuple[float, float, float],
    halo: int = 0,
) -> dict[str, np.ndarray]:
    """Read velocity + pressure-gradient over an axis-aligned region of an AMReX plotfile.

    Isolates all yt / plotfile / cluster I/O from the numpy core. Reads the full level-0 covering
    grid (exact for the single-level sphere runs; ~0.2 GB for 4.2M cells, and free of yt's
    ghost-cell boundary check on interior sub-regions) and slices the requested region in memory,
    padded by ``halo`` cells on each side. Fields are read by their ``('boxlib', name)`` tuple
    identifiers; all are asserted present. Arrays are unwrapped from yt's ``unyt_array`` to bare
    ``float64`` numpy (yt may return ``float32`` for an fp32 build — the assert doubles as the
    fp64-build check). Code units throughout (no conversion).

    Args:
        plotfile_path: Path to the plotfile directory (e.g. ``.../plt10000``).
        lo: Physical lower corner ``(x, y, z)`` (``-inf`` allowed for "full extent").
        hi: Physical upper corner ``(x, y, z)`` (``+inf`` allowed for "full extent").
        halo: Extra cells sliced on every side beyond the requested region.

    Returns:
        Dict with FP64 arrays ``u, v, w, gradpx, gradpy, gradpz`` (indexed ``[ix, iy, iz]``),
        cell-center coordinate arrays ``x, y, z``, and ``dx`` (per-axis spacing).
    """
    import yt

    yt.set_log_level("error")
    ds = yt.load(str(plotfile_path))
    if ds.index.max_level != 0:
        raise ValueError(
            f"extract_eulerian_box requires a single-level plotfile; "
            f"max_level={ds.index.max_level}"
        )
    present = set(ds.field_list)
    missing = [f for f in _REQUIRED_FIELDS if f not in present]
    if missing:
        raise ValueError(f"plotfile is missing required fields {missing}")

    dle = np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64)
    dre = np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64)
    ddims = np.asarray(ds.domain_dimensions, dtype=np.int64)
    dx = (dre - dle) / ddims

    # Clamp to the domain (accepts +/-inf for "full extent" along an axis).
    lo_c = np.clip(np.asarray(lo, dtype=np.float64), dle, dre)
    hi_c = np.clip(np.asarray(hi, dtype=np.float64), dle, dre)
    i_lo = np.floor((lo_c - dle) / dx).astype(np.int64) - halo
    i_hi = np.ceil((hi_c - dle) / dx).astype(np.int64) + halo
    i_lo = np.maximum(i_lo, 0)
    i_hi = np.minimum(np.maximum(i_hi, i_lo + 1), ddims)  # >=1 cell/axis, within domain

    cg = ds.covering_grid(
        level=0, left_edge=ds.domain_left_edge, dims=tuple(int(d) for d in ddims)
    )
    sl = tuple(slice(int(a), int(b)) for a, b in zip(i_lo, i_hi))
    names = ("u", "v", "w", "gradpx", "gradpy", "gradpz")
    out: dict[str, np.ndarray] = {}
    for key, field in zip(names, _REQUIRED_FIELDS):
        raw = cg[field].to_ndarray()
        if raw.dtype != np.float64:  # check BEFORE casting, so an fp32 build is caught
            raise ValueError(f"field {field} is {raw.dtype}, not float64 (fp32 build?)")
        out[key] = np.asarray(raw, dtype=np.float64)[sl]
    out["x"] = (dle[0] + (np.arange(ddims[0]) + 0.5) * dx[0])[sl[0]]
    out["y"] = (dle[1] + (np.arange(ddims[1]) + 0.5) * dx[1])[sl[1]]
    out["z"] = (dle[2] + (np.arange(ddims[2]) + 0.5) * dx[2])[sl[2]]
    out["dx"] = dx
    return out


def sphere_cv_drag_cd(
    plotfile_path: str,
    *,
    x_inlet: float,
    x_outlet: float,
    rho: float = 1.0,
    u_inf: float = 1.0,
    diameter: float = 1.0,
) -> dict[str, float]:
    """Periodic-duct control-volume drag coefficient for the FlowPastSphere benchmark.

    Reads the inlet and outlet y-z planes and the ``gradpx`` volume between them and evaluates
    :func:`periodic_duct_drag`. The planes span the full periodic cross-section.

    Args:
        plotfile_path: Path to the plotfile directory.
        x_inlet: Streamwise location of the upstream (inlet) plane.
        x_outlet: Streamwise location of the downstream (outlet) plane.
        rho: Fluid density.
        u_inf: Freestream velocity.
        diameter: Sphere diameter.

    Raises:
        ValueError: if ``x_inlet >= x_outlet`` (the inlet must be upstream of the outlet, else
            the momentum term would be sign-flipped), or if the two locations resolve to the
            same grid cell (a degenerate zero-thickness control volume).

    Returns:
        Dict with ``cd``, ``drag``, ``x_inlet``, ``x_outlet`` (actual cell-center positions).
    """
    if x_inlet >= x_outlet:
        raise ValueError(
            f"x_inlet ({x_inlet}) must be strictly upstream of x_outlet ({x_outlet})"
        )
    box = extract_eulerian_box(
        plotfile_path,
        lo=(x_inlet, -np.inf, -np.inf),
        hi=(x_outlet, np.inf, np.inf),
    )
    xc = box["x"]
    i_in = int(np.argmin(np.abs(xc - x_inlet)))
    i_out = int(np.argmin(np.abs(xc - x_outlet)))
    if i_in == i_out:
        raise ValueError(
            f"inlet and outlet resolve to the same cell (x={xc[i_in]:.4f}); "
            f"choose more separated planes"
        )
    dy, dz, dxs = float(box["dx"][1]), float(box["dx"][2]), float(box["dx"][0])
    drag = periodic_duct_drag(
        box["u"][i_in, :, :],
        box["u"][i_out, :, :],
        box["gradpx"][i_in:i_out, :, :],
        rho=rho,
        cell_area=dy * dz,
        cell_thickness=dxs,
    )
    return {
        "cd": cd_from_drag(drag, rho=rho, u_inf=u_inf, diameter=diameter),
        "drag": drag,
        "x_inlet": float(xc[i_in]),
        "x_outlet": float(xc[i_out]),
    }


def unsteady_momentum_force(
    u_cv_old: np.ndarray,
    u_cv_new: np.ndarray,
    *,
    rho: float,
    cell_volume: float,
    dt: float,
) -> float:
    """The unsteady x-momentum term ``rho * d/dt integral_CV u_x dV`` (time finite-difference).

    The periodic-duct drag balance assumes steady flow (this term is ~0). At Re=100 the sphere
    wake is steady (below the ~Re 210 shedding onset), but the assumption SHALL be checked, not
    assumed (design Decision 6).

    Args:
        u_cv_old: Streamwise velocity over the control volume at the earlier time (3-D, FP64).
        u_cv_new: Streamwise velocity over the control volume at the later time (same shape).
        rho: Fluid density.
        cell_volume: Volume of one cell (``dx * dy * dz``).
        dt: Time between the two snapshots.

    Returns:
        The unsteady momentum force (same units as a drag force).
    """
    if dt <= 0:
        raise ValueError(f"dt must be positive, got {dt}")
    u_cv_old = np.asarray(u_cv_old, dtype=np.float64)
    u_cv_new = np.asarray(u_cv_new, dtype=np.float64)
    if u_cv_old.shape != u_cv_new.shape:
        raise ValueError(
            f"old/new control-volume shapes differ: {u_cv_old.shape} vs {u_cv_new.shape}"
        )
    if not (np.isfinite(u_cv_old).all() and np.isfinite(u_cv_new).all()):
        raise ValueError("control-volume velocity contains non-finite values (NaN/inf)")
    return float(rho * (np.sum(u_cv_new) - np.sum(u_cv_old)) * cell_volume / dt)


def sphere_cv_steadiness_fraction(
    plotfile_old: str,
    plotfile_new: str,
    *,
    x_inlet: float,
    x_outlet: float,
    dt: float,
    rho: float = 1.0,
) -> dict[str, float]:
    """Steadiness gate: ``|unsteady momentum term| / |CV drag|`` between two plotfiles.

    The periodic-duct drag balance neglects the unsteady term; this quantifies it. The verdict
    stands only if the returned ``fraction`` is small (design Decision 6 uses < 5%).

    Args:
        plotfile_old: Earlier-time plotfile (e.g. ``plt09900``).
        plotfile_new: Later-time plotfile (e.g. ``plt10000``).
        x_inlet: Inlet plane location.
        x_outlet: Outlet plane location.
        dt: Time between the two plotfiles.
        rho: Fluid density.

    Returns:
        Dict with ``unsteady``, ``drag``, ``fraction`` (``|unsteady| / |drag|``).
    """
    box_old = extract_eulerian_box(
        plotfile_old, lo=(x_inlet, -np.inf, -np.inf), hi=(x_outlet, np.inf, np.inf)
    )
    box_new = extract_eulerian_box(
        plotfile_new, lo=(x_inlet, -np.inf, -np.inf), hi=(x_outlet, np.inf, np.inf)
    )
    xc = box_new["x"]
    i_in = int(np.argmin(np.abs(xc - x_inlet)))
    i_out = int(np.argmin(np.abs(xc - x_outlet)))
    cell_volume = float(np.prod(box_new["dx"]))
    unsteady = unsteady_momentum_force(
        box_old["u"][i_in:i_out, :, :],
        box_new["u"][i_in:i_out, :, :],
        rho=rho,
        cell_volume=cell_volume,
        dt=dt,
    )
    drag = sphere_cv_drag_cd(plotfile_new, x_inlet=x_inlet, x_outlet=x_outlet, rho=rho)[
        "drag"
    ]
    # A near-zero CV drag (degenerate planes / null field) is exactly the pathological case the
    # gate should flag, not crash on — return inf rather than dividing by ~0.
    fraction = float("inf") if abs(drag) < 1e-12 else abs(unsteady) / abs(drag)
    return {
        "unsteady": unsteady,
        "drag": drag,
        "fraction": fraction,
    }
