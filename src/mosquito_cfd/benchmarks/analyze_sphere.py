"""Analysis utilities for FlowPastSphere benchmark case.

Extracts drag coefficient and validates against literature for Re=100 flow.
Reference: Johnson & Patel (1999), Cd = 1.087 at Re = 100.
"""

import warnings
from pathlib import Path
from typing import Any

import numpy as np

# Physical parameters for standard FlowPastSphere case
SPHERE_DIAMETER = 1.0  # dimensionless
FREESTREAM_VELOCITY = 1.0  # dimensionless
DENSITY = 1.0  # dimensionless
KINEMATIC_VISCOSITY = 0.01  # gives Re = 100
SPHERE_CENTER = (5.0, 5.0, 5.0)  # standard position

# Literature values
LITERATURE_CD = 1.087  # Johnson & Patel (1999)
LITERATURE_CD_RANGE = (1.087, 1.10)  # Range from various sources
ACCEPTANCE_TOLERANCE = 0.05  # 5% acceptance

# T2b confinement-corrected literature grade (H1'). The committed sphere run is a transversely
# periodic ARRAY (pitch 10 D, 5 D upstream), so its Cd carries an estimated +3-6% confinement offset
# above the isolated value; dividing it out yields the isolated-equivalent bracket graded against
# LITERATURE_CD. These are pinned and NOT loosened to make a grade pass (CC-V2).
SPHERE_CONFINEMENT_OFFSET_BAND = (0.03, 0.06)  # (+3%, +6%) transverse-array confinement
SPHERE_LITERATURE_TOL = ACCEPTANCE_TOLERANCE  # +/-5% of LITERATURE_CD


def load_plotfile(plotfile_path: str | Path) -> Any:
    """Load an AMReX plot file using yt.

    Args:
        plotfile_path: Path to plot file directory (e.g., plt00100).

    Returns:
        yt dataset object.
    """
    import yt

    yt.set_log_level("error")
    return yt.load(str(plotfile_path))


def extract_particle_forces(ds: Any) -> dict[str, np.ndarray]:
    """Extract particle (immersed boundary) force data from plot file.

    In IAMReX, particle real components typically contain:
    - comp0-2: Position offset or velocity correction
    - comp3-5: Force components (fx, fy, fz) on fluid

    Args:
        ds: yt dataset from load_plotfile.

    Returns:
        Dictionary with keys 'fx', 'fy', 'fz' (force arrays),
        'x', 'y', 'z' (positions), and 'n_particles'.
    """
    ad = ds.all_data()

    # Get particle positions
    x = np.array(ad["all", "particle_position_x"])
    y = np.array(ad["all", "particle_position_y"])
    z = np.array(ad["all", "particle_position_z"])

    # Force components (comp3, comp4, comp5 based on IAMReX convention)
    fx = np.array(ad["all", "particle_real_comp3"])
    fy = np.array(ad["all", "particle_real_comp4"])
    fz = np.array(ad["all", "particle_real_comp5"])

    return {
        "x": x,
        "y": y,
        "z": z,
        "fx": fx,
        "fy": fy,
        "fz": fz,
        "n_particles": len(x),
    }


def compute_drag_coefficient(
    fx_sum: float,
    rho: float = DENSITY,
    U: float = FREESTREAM_VELOCITY,
    D: float = SPHERE_DIAMETER,
) -> float:
    """Compute drag coefficient from force.

    The IB method computes force on the fluid by the body. The force on the
    body (drag) is the negative of this by Newton's third law.

    Args:
        fx_sum: Sum of x-component forces on fluid from all IB markers.
        rho: Fluid density.
        U: Freestream velocity.
        D: Sphere diameter.

    Returns:
        Drag coefficient Cd.
    """
    # Force on body = -force on fluid
    F_drag = -fx_sum

    # Frontal area of sphere
    A = np.pi * (D / 2) ** 2

    # Cd = F / (0.5 * rho * U^2 * A)
    Cd = F_drag / (0.5 * rho * U**2 * A)

    return Cd


def extract_sphere_cd(
    plotfile_path: str | Path,
    *,
    method: str = "marker",
    x_inlet: float = 2.0,
    x_outlet: float = 8.0,
) -> dict[str, Any]:
    """Extract drag coefficient from a FlowPastSphere plot file.

    Two extraction methods are available:

    - ``method="marker"`` (default, legacy): the raw sum of the IB marker forces
      (``particle_real_comp3``). T1a proved this is **wrong** — the plotfile persists only the
      last multidirect sub-iteration's force, so the marker sum under-reports the drag by ~2.6x
      (``docs/aerodynamics_validation/t1a-findings.md``). Kept for back-compatibility and as a
      diagnostic.
    - ``method="cv"``: the principled field-based drag from a periodic-duct control-volume
      momentum balance over the persisted Eulerian fields (T1b; :mod:`stress_integral`). This is
      the corrected benchmark Cd.

    Args:
        plotfile_path: Path to plot file directory.
        method: ``"marker"`` (legacy raw-sum diagnostic) or ``"cv"`` (field-based control volume).
        x_inlet: Inlet plane location for the ``"cv"`` method.
        x_outlet: Outlet plane location for the ``"cv"`` method.

    Returns:
        Dictionary containing (back-compatible across methods):
        - cd: Computed drag coefficient (the field-based value for ``"cv"``).
        - fx_sum, fy_sum, fz_sum: IB marker force sums.
        - cd_marker_lastpass: the legacy marker-sum Cd, labelled a diagnostic (last
          multidirect sub-iteration only — never the result). ``None`` when ``method="cv"`` is
          run on a field-only plotfile with no particle data (``fx/fy/fz_sum`` are then ``None``
          and ``n_particles`` is 0).
        - n_particles: Number of IB markers.
        - time: Simulation time.
        - validated: Whether Cd is within acceptance range.
        - error_pct: Percent error from literature value.
        - literature_cd: The literature reference value.
    """
    if method not in ("marker", "cv"):
        raise ValueError(f"unknown method {method!r}; expected 'marker' or 'cv'")

    ds = load_plotfile(plotfile_path)

    # IB-marker diagnostic: REQUIRED for method="marker" (it *is* that method), but only
    # best-effort for method="cv" — a field-only plotfile has no particle fields, yet the
    # control-volume method does not need them. On the cv path a missing-particle read degrades
    # to cd_marker_lastpass=None rather than crashing before the principled CV path runs.
    try:
        particles = extract_particle_forces(ds)
        fx_sum: float | None = float(particles["fx"].sum())
        fy_sum: float | None = float(particles["fy"].sum())
        fz_sum: float | None = float(particles["fz"].sum())
        cd_marker: float | None = compute_drag_coefficient(fx_sum)
        n_particles = particles["n_particles"]
    except Exception as exc:
        if method == "marker":
            raise
        # cv path only: degrade the marker diagnostic rather than fail, but WARN so a real bug
        # in the particle path is visible rather than silently swallowed (not just "no particles").
        warnings.warn(
            f"IB-marker diagnostic unavailable ({exc!r}); cd_marker_lastpass=None. "
            "The control-volume cd is unaffected.",
            stacklevel=2,
        )
        fx_sum = fy_sum = fz_sum = cd_marker = None
        n_particles = 0

    if method == "cv":
        from mosquito_cfd.benchmarks.stress_integral import sphere_cv_drag_cd

        cd = sphere_cv_drag_cd(str(plotfile_path), x_inlet=x_inlet, x_outlet=x_outlet)[
            "cd"
        ]
    else:  # method == "marker"
        cd = cd_marker

    error_pct = abs(cd - LITERATURE_CD) / LITERATURE_CD * 100
    validated = error_pct <= ACCEPTANCE_TOLERANCE * 100

    return {
        "cd": cd,
        "fx_sum": fx_sum,
        "fy_sum": fy_sum,
        "fz_sum": fz_sum,
        "cd_marker_lastpass": cd_marker,
        "n_particles": n_particles,
        "time": float(ds.current_time),
        "validated": validated,
        "error_pct": error_pct,
        "literature_cd": LITERATURE_CD,
    }


def check_steady_state(
    plotfile_paths: list[str | Path],
    tolerance: float = 0.01,
) -> dict[str, Any]:
    """Check if simulation has reached steady state.

    Compares Cd from multiple timesteps to detect convergence.

    Args:
        plotfile_paths: List of plot file paths (chronological order).
        tolerance: Relative change threshold for steady state (default 1%).

    Returns:
        Dictionary with:
        - is_steady: Whether steady state is reached
        - cd_values: List of Cd values
        - times: List of simulation times
        - relative_change: Relative change between last two values
    """
    results = []
    for path in plotfile_paths:
        try:
            result = extract_sphere_cd(path)
            results.append(result)
        except Exception as e:
            print(f"Warning: Could not process {path}: {e}")

    if len(results) < 2:
        return {
            "is_steady": False,
            "cd_values": [r["cd"] for r in results],
            "times": [r["time"] for r in results],
            "relative_change": None,
            "message": "Need at least 2 timesteps to check convergence",
        }

    cd_values = [r["cd"] for r in results]
    times = [r["time"] for r in results]

    # Check relative change between last two values
    cd_prev = cd_values[-2]
    cd_last = cd_values[-1]

    if abs(cd_prev) < 1e-10:
        relative_change = float("inf")
    else:
        relative_change = abs(cd_last - cd_prev) / abs(cd_prev)

    is_steady = relative_change < tolerance

    return {
        "is_steady": is_steady,
        "cd_values": cd_values,
        "times": times,
        "relative_change": relative_change,
        "tolerance": tolerance,
    }


def grid_convergence_analysis(
    cd_coarse: float,
    cd_medium: float,
    cd_fine: float,
    r: float = 2.0,
    safety_factor: float = 1.25,
) -> dict[str, float]:
    """Perform Richardson extrapolation and GCI analysis.

    Args:
        cd_coarse: Cd from coarse grid.
        cd_medium: Cd from medium grid.
        cd_fine: Cd from fine grid.
        r: Refinement ratio (default 2).
        safety_factor: GCI safety factor (default 1.25).

    Returns:
        Dictionary with:
        - cd_exact: Richardson-extrapolated value
        - observed_p: Observed order of convergence
        - gci_fine: Grid Convergence Index for fine grid
        - gci_medium: Grid Convergence Index for medium grid
    """
    # Observed order of convergence
    # p = ln[(f_coarse - f_medium) / (f_medium - f_fine)] / ln(r)
    numer = cd_coarse - cd_medium
    denom = cd_medium - cd_fine

    if abs(denom) < 1e-12:
        # Converged or pathological
        observed_p = float("inf")
        cd_exact = cd_fine
    else:
        ratio = numer / denom
        if ratio <= 0:
            # Non-monotonic convergence
            observed_p = float("nan")
            cd_exact = cd_fine
        else:
            observed_p = np.log(ratio) / np.log(r)
            # Richardson extrapolation
            cd_exact = cd_fine + (cd_fine - cd_medium) / (r**observed_p - 1)

    # Grid Convergence Index
    # GCI = Fs * |epsilon| / (r^p - 1)
    epsilon_fine = (cd_fine - cd_medium) / cd_fine if abs(cd_fine) > 1e-12 else 0
    epsilon_medium = (
        (cd_medium - cd_coarse) / cd_medium if abs(cd_medium) > 1e-12 else 0
    )

    if np.isfinite(observed_p) and observed_p > 0:
        gci_fine = safety_factor * abs(epsilon_fine) / (r**observed_p - 1)
        gci_medium = safety_factor * abs(epsilon_medium) / (r**observed_p - 1)
    else:
        gci_fine = abs(epsilon_fine)
        gci_medium = abs(epsilon_medium)

    return {
        "cd_exact": cd_exact,
        "observed_p": observed_p,
        "gci_fine": gci_fine,
        "gci_medium": gci_medium,
        "cd_coarse": cd_coarse,
        "cd_medium": cd_medium,
        "cd_fine": cd_fine,
    }


def grade_sphere_cd_confinement_corrected(
    cd_confined: float,
    *,
    offset_band: tuple[float, float] = SPHERE_CONFINEMENT_OFFSET_BAND,
    literature_cd: float = LITERATURE_CD,
    tol: float = SPHERE_LITERATURE_TOL,
) -> dict[str, Any]:
    """Grade a confined control-volume Cd against literature by removing the confinement offset (H1').

    The committed sphere run is a transversely-periodic array whose Cd sits an estimated
    ``offset_band`` (+3-6%) above the isolated value. The isolated-equivalent bracket is obtained by
    **dividing** the confined Cd by ``(1 + offset)`` — NOT ``cd * (1 - offset)``. Because a larger
    offset yields a *smaller* isolated value, the bracket is taken as ``min``/``max`` over both offset
    endpoints (do not assume ``offset_band[0]`` maps to the lower bracket end). The verdict is **H1'**
    when the whole bracket lies within ``+/- tol`` of ``literature_cd`` (edges **inclusive**).

    This takes Cd *values* only — it does not read plotfiles or touch the extractor internals (CC-V4).
    The H1' verdict is intended for the two-grid Richardson value (1.131); a single grid (e.g. the
    medium CV 1.18) legitimately grades ``not H1'``.

    Args:
        cd_confined: The confined-array control-volume Cd (a single grid or the Richardson value).
        offset_band: ``(lo, hi)`` fractional confinement offsets, ``0 <= lo <= hi``.
        literature_cd: The literature target (Johnson & Patel 1999 = 1.087).
        tol: Fractional tolerance on ``literature_cd`` (0.05 = +/-5%).

    Returns:
        Dict with ``cd_confined``, ``isolated_bracket`` (lo, hi), ``tol_range`` (lo, hi),
        ``literature_cd``, ``within`` (bool), and ``verdict`` ("H1'" | "not H1'").

    Raises:
        ValueError: for a non-positive Cd, a misordered/negative offset band, or a negative tol.
    """
    if not np.isfinite(cd_confined) or cd_confined <= 0:
        raise ValueError(f"cd_confined must be finite and positive, got {cd_confined}")
    if not np.isfinite(literature_cd) or literature_cd <= 0:
        raise ValueError(
            f"literature_cd must be finite and positive, got {literature_cd}"
        )
    lo_off, hi_off = offset_band
    if (
        not (0 <= lo_off <= hi_off)
        or not np.isfinite(lo_off)
        or not np.isfinite(hi_off)
    ):
        raise ValueError(
            f"offset_band must be finite with 0 <= lo <= hi, got {offset_band}"
        )
    if not np.isfinite(tol) or tol < 0:
        raise ValueError(f"tol must be finite and non-negative, got {tol}")

    # Divide out the confinement offset; min/max because a larger offset -> smaller isolated value.
    iso_a = cd_confined / (1 + lo_off)
    iso_b = cd_confined / (1 + hi_off)
    bracket = (min(iso_a, iso_b), max(iso_a, iso_b))

    tol_range = (literature_cd * (1 - tol), literature_cd * (1 + tol))
    within = (
        tol_range[0] <= bracket[0] and bracket[1] <= tol_range[1]
    )  # inclusive edges

    return {
        "cd_confined": cd_confined,
        "isolated_bracket": bracket,
        "tol_range": tol_range,
        "literature_cd": literature_cd,
        "within": within,
        "verdict": "H1'" if within else "not H1'",
    }


def generate_convergence_report(
    plotfiles_coarse: list[str | Path],
    plotfiles_medium: list[str | Path],
    plotfiles_fine: list[str | Path],
    grid_sizes: tuple[int, int, int] = (128, 256, 512),
) -> dict[str, Any]:
    """Generate complete grid convergence report.

    Args:
        plotfiles_coarse: Plot files from coarse grid (last one used).
        plotfiles_medium: Plot files from medium grid.
        plotfiles_fine: Plot files from fine grid.
        grid_sizes: Grid sizes for each resolution.

    Returns:
        Complete report dictionary with all analysis results.
    """
    # Extract Cd from final timestep of each resolution
    cd_coarse = extract_sphere_cd(plotfiles_coarse[-1])["cd"]
    cd_medium = extract_sphere_cd(plotfiles_medium[-1])["cd"]
    cd_fine = extract_sphere_cd(plotfiles_fine[-1])["cd"]

    # Grid convergence analysis
    gci_results = grid_convergence_analysis(cd_coarse, cd_medium, cd_fine)

    # Build report
    report = {
        "resolutions": {
            "coarse": {
                "n_cells": grid_sizes[0],
                "cd": cd_coarse,
            },
            "medium": {
                "n_cells": grid_sizes[1],
                "cd": cd_medium,
            },
            "fine": {
                "n_cells": grid_sizes[2],
                "cd": cd_fine,
            },
        },
        "grid_convergence": gci_results,
        "literature": {
            "cd": LITERATURE_CD,
            "source": "Johnson & Patel (1999)",
        },
        "validation": {
            "error_pct": abs(gci_results["cd_exact"] - LITERATURE_CD)
            / LITERATURE_CD
            * 100,
            "passed": (
                abs(gci_results["cd_exact"] - LITERATURE_CD) / LITERATURE_CD
                <= ACCEPTANCE_TOLERANCE
            ),
            "gci_acceptable": gci_results["gci_fine"] < 0.02,  # 2% threshold
        },
    }

    return report
