"""Analysis utilities for FlowPastSphere benchmark case.

Extracts drag coefficient and validates against literature for Re=100 flow.
Reference: Johnson & Patel (1999), Cd = 1.087 at Re = 100.
"""

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


def extract_sphere_cd(plotfile_path: str | Path) -> dict[str, Any]:
    """Extract drag coefficient from FlowPastSphere plot file.

    This is the main entry point for Cd extraction.

    Args:
        plotfile_path: Path to plot file directory.

    Returns:
        Dictionary containing:
        - cd: Computed drag coefficient
        - fx_sum, fy_sum, fz_sum: Force sums
        - n_particles: Number of IB markers
        - time: Simulation time
        - validated: Whether Cd is within acceptance range
        - error_pct: Percent error from literature value
    """
    ds = load_plotfile(plotfile_path)
    particles = extract_particle_forces(ds)

    fx_sum = float(particles["fx"].sum())
    fy_sum = float(particles["fy"].sum())
    fz_sum = float(particles["fz"].sum())

    cd = compute_drag_coefficient(fx_sum)

    # Validation
    error_pct = abs(cd - LITERATURE_CD) / LITERATURE_CD * 100
    validated = error_pct <= ACCEPTANCE_TOLERANCE * 100

    return {
        "cd": cd,
        "fx_sum": fx_sum,
        "fy_sum": fy_sum,
        "fz_sum": fz_sum,
        "n_particles": particles["n_particles"],
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
    epsilon_medium = (cd_medium - cd_coarse) / cd_medium if abs(cd_medium) > 1e-12 else 0

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
            "error_pct": abs(gci_results["cd_exact"] - LITERATURE_CD) / LITERATURE_CD * 100,
            "passed": abs(gci_results["cd_exact"] - LITERATURE_CD) / LITERATURE_CD <= ACCEPTANCE_TOLERANCE,
            "gci_acceptable": gci_results["gci_fine"] < 0.02,  # 2% threshold
        },
    }

    return report