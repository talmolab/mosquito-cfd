#!/usr/bin/env python3
"""Generate figures for the Flow Past Sphere validation.

Usage:
    uv run python examples/flow_past_sphere/generate_figures.py
    uv run python examples/flow_past_sphere/generate_figures.py \\
        --plotfile Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k/plt10000

Produces:
    examples/flow_past_sphere/figures/
        fig_forces_convergence.pdf/png    F1: Grid convergence — Cd vs time
        fig_velocity.pdf/png              V1: x-velocity field at steady state [requires --plotfile]
"""

import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Physical parameters (from inputs.3d.flow_past_sphere)
# ---------------------------------------------------------------------------
SPHERE_RADIUS = 0.5   # dimensionless (diameter = 1.0)
U_INF = 1.0
RHO = 1.0

# Frontal projected area: A = pi * r^2
A_PROJ = np.pi * SPHERE_RADIUS**2  # = pi * 0.25 ≈ 0.7854

# Dynamic pressure
Q = 0.5 * RHO * U_INF**2  # = 0.5

# Literature reference (Re=100 sphere)
CD_LITERATURE = 1.087  # Johnson & Patel (1999)

# IBM colorblind-safe palette
BLUE = "#0072B2"
RED = "#D55E00"
GREEN = "#009E73"


# ---------------------------------------------------------------------------
# F1: Grid convergence — Cd vs time
# ---------------------------------------------------------------------------

def plot_forces_convergence(figures_dir: Path, forces_coarse: Path, forces_medium: Path):
    """F1: Cd vs time for coarse and medium grids with literature reference."""
    import pandas as pd

    df_c = pd.read_csv(forces_coarse)
    df_m = pd.read_csv(forces_medium)

    # Cd = -Fx / (q * A_proj)
    Cd_coarse = -df_c["Fx"].values / (Q * A_PROJ)
    Cd_medium = -df_m["Fx"].values / (Q * A_PROJ)
    t_coarse = df_c["time"].values
    t_medium = df_m["time"].values

    fig, ax = plt.subplots(figsize=(7, 4.5))

    ax.plot(t_coarse, Cd_coarse, color=BLUE, lw=2, ls="--", marker="o", markersize=4,
            label=f"Coarse 128×64×64 (Cd={Cd_coarse[-1]:.3f})")
    ax.plot(t_medium, Cd_medium, color=RED, lw=2, ls="-", marker="s", markersize=4,
            label=f"Medium 256×128×128 (Cd={Cd_medium[-1]:.3f})")
    ax.axhline(CD_LITERATURE, color=GREEN, lw=2, ls="-.",
               label=f"Literature Cd={CD_LITERATURE} (Johnson & Patel 1999, Re=100)")

    # Annotate discrepancy
    y_c = Cd_coarse[-1]
    y_m = Cd_medium[-1]
    t_ann = t_medium[-1] * 0.6
    ax.annotate(
        f"~{(CD_LITERATURE / y_m - 1) * 100:.0f}% below literature\n(known diffused-IB scaling)",
        xy=(t_ann, (y_m + CD_LITERATURE) / 2),
        fontsize=8, color="gray", ha="center", va="center",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.7),
    )

    ax.set_xlabel("Simulation time (dimensionless)", fontsize=10)
    ax.set_ylabel("Drag coefficient Cd", fontsize=10)
    ax.legend(fontsize=9, loc="center right")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(bottom=0)

    ax.set_title(
        "Flow Past Sphere — Grid Convergence\n"
        f"Re=100 | A_proj=π·r²={A_PROJ:.4f} | q={Q:.1f}",
        fontsize=10, fontweight="bold",
    )
    fig.tight_layout()

    out = figures_dir / "fig_forces_convergence.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"F1: {out} + .png")

    # Summary
    print(f"  Coarse Cd={Cd_coarse[-1]:.4f} ({(1 - Cd_coarse[-1]/CD_LITERATURE)*100:.1f}% below lit)")
    print(f"  Medium Cd={Cd_medium[-1]:.4f} ({(1 - Cd_medium[-1]/CD_LITERATURE)*100:.1f}% below lit)")


# ---------------------------------------------------------------------------
# V1: x-velocity field at steady state (requires --plotfile)
# ---------------------------------------------------------------------------

def plot_velocity_field(figures_dir: Path, plotfile: Path):
    """V1: x-velocity field z-slice at steady state (t=100).

    Technique adapted from:
        C:\\vaults\\physics surrogate models\\ellipsoid-validation-figure\\
        generate_ellipsoid_figure.py
    """
    import yt
    import matplotlib.patches as mpatches
    yt.set_log_level("error")

    print(f"  Loading plotfile: {plotfile}")
    ds = yt.load(str(plotfile))
    time = float(ds.current_time)
    print(f"  Time: {time:.2f}")

    xl = float(ds.domain_left_edge[0])
    xr = float(ds.domain_right_edge[0])
    yl = float(ds.domain_left_edge[1])
    yr = float(ds.domain_right_edge[1])
    nx = int(ds.domain_dimensions[0])
    ny = int(ds.domain_dimensions[1])
    cx = float(ds.domain_center[0])
    cy = float(ds.domain_center[1])

    # Fixed-resolution buffer: full x-y plane at z = domain center
    slc = ds.slice('z', ds.domain_center[2])
    frb = slc.to_frb(
        ds.domain_width[0],
        (nx, ny),
        height=ds.domain_width[1],
    )
    u = np.array(frb['x_velocity'])
    # FRB shape: either (nx, ny) or (ny, nx) — imshow wants (ny, nx): rows=y, cols=x
    if u.shape == (nx, ny):
        u = u.T
    print(f"  Velocity range: [{u.min():.3f}, {u.max():.3f}]")
    if abs(u.max()) > 50:
        raise ValueError(
            f"Velocity values outside expected dimensionless range: [{u.min():.1f}, {u.max():.1f}]\n"
            "yt may have applied a CGS unit conversion."
        )

    fig, ax = plt.subplots(figsize=(10, 5))
    extent = [xl - cx, xr - cx, yl - cy, yr - cy]
    im = ax.imshow(
        u,
        origin='lower',
        extent=extent,
        cmap='RdYlBu_r',
        aspect='equal',
        interpolation='bilinear',
    )
    cbar = plt.colorbar(im, ax=ax, label='$u$ (dimensionless)', fraction=0.03, pad=0.04)
    cbar.ax.tick_params(labelsize=9)

    # Sphere outline: sphere at (5, 5) in domain coords → (5 - cx, 5 - cy) in display
    circle = mpatches.Circle(
        (5.0 - cx, 5.0 - cy), SPHERE_RADIUS,
        fill=False, edgecolor='white', linewidth=2,
    )
    ax.add_patch(circle)

    ax.set_xlabel('$x$ (dimensionless)', fontsize=11)
    ax.set_ylabel('$y$ (dimensionless)', fontsize=11)
    ax.set_title(
        f'Flow Past Sphere — x-velocity field  ($t = {time:.1f}$, steady state)\n'
        f'Re=100 | z-slice at z={float(ds.domain_center[2]):.1f}',
        fontsize=11,
    )

    out = figures_dir / "fig_velocity.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"V1: {out} + .png")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate flow past sphere figures")
    script_dir = Path(__file__).parent
    parser.add_argument(
        "--forces-coarse",
        type=Path,
        default=script_dir / "forces_coarse.csv",
        help="Path to forces_coarse.csv",
    )
    parser.add_argument(
        "--forces-medium",
        type=Path,
        default=script_dir / "forces_medium.csv",
        help="Path to forces_medium.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "figures",
        help="Output directory for figures",
    )
    parser.add_argument(
        "--plotfile",
        type=Path,
        default=None,
        help=(
            "Path to AMReX plotfile for velocity field visualization (V1). "
            "Example: Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k/plt10000"
        ),
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to: {args.output_dir}")

    plot_forces_convergence(args.output_dir, args.forces_coarse, args.forces_medium)

    if args.plotfile is not None:
        plot_velocity_field(args.output_dir, args.plotfile)
    else:
        print("V1: skipped (pass --plotfile to generate velocity field figure)")

    print("\nAll figures generated.")


if __name__ == "__main__":
    main()
