#!/usr/bin/env python3
"""Generate figures for the heaving ellipsoid validation.

Usage:
    uv run python examples/heaving_ellipsoid/generate_figures.py

Produces:
    examples/heaving_ellipsoid/figures/
        fig_geometry.pdf/png    G1: Elliptic cross-sections with semi-axes
        fig_forces.pdf/png      F1: Cd and CL vs time
"""

import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse

# ---------------------------------------------------------------------------
# Parameters (from inputs.3d.heaving_ellipsoid)
# ---------------------------------------------------------------------------
SEMI_A = 0.5   # chord direction (x)
SEMI_B = 0.02  # thickness (y) — very thin
SEMI_C = 1.5   # span direction (z)

U_INF = 1.0    # freestream velocity
RHO = 1.0      # fluid density
NU = 0.01      # kinematic viscosity (Re = U_inf * 2*a / nu = 100)

# Reference areas
A_FRONTAL = np.pi * SEMI_B * SEMI_C  # flow-normal elliptic area (xz-plane projects to bc)
A_PLANFORM = np.pi * SEMI_A * SEMI_C  # planform area

# Dynamic pressure
Q = 0.5 * RHO * U_INF**2  # = 0.5

# IBM colorblind-safe palette
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"


# ---------------------------------------------------------------------------
# G1: Geometry — elliptic cross-sections
# ---------------------------------------------------------------------------

def plot_geometry(figures_dir: Path):
    """G1: Draw elliptic cross-sections in two planes with annotated semi-axes."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8, 4))

    # --- Panel 1: xz-plane (frontal view, looking upstream) ---
    theta = np.linspace(0, 2 * np.pi, 300)
    xz_x = SEMI_A * np.cos(theta)
    xz_z = SEMI_C * np.sin(theta)
    ax1.fill(xz_x, xz_z, color=BLUE, alpha=0.2)
    ax1.plot(xz_x, xz_z, color=BLUE, lw=2)
    ax1.set_aspect("equal")
    ax1.set_xlabel("x (chord, a=0.5)", fontsize=10)
    ax1.set_ylabel("z (span, c=1.5)", fontsize=10)
    ax1.set_title("xz-plane (top view)\nPlanform: π·a·c = {:.3f}".format(A_PLANFORM), fontsize=9)
    # Annotate semi-axes
    ax1.annotate("", xy=(SEMI_A, 0), xytext=(0, 0),
                 arrowprops=dict(arrowstyle="->", color=RED, lw=1.5))
    ax1.text(SEMI_A / 2, 0.1, f"a={SEMI_A}", ha="center", color=RED, fontsize=9)
    ax1.annotate("", xy=(0, SEMI_C), xytext=(0, 0),
                 arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.5))
    ax1.text(0.15, SEMI_C / 2, f"c={SEMI_C}", ha="left", color=GREEN, fontsize=9)
    ax1.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.4)
    ax1.axvline(0, color="gray", lw=0.5, ls="--", alpha=0.4)
    ax1.set_xlim(-1.2, 1.2)
    ax1.set_ylim(-1.8, 1.8)

    # --- Panel 2: xy-plane (side view, looking along span) ---
    xy_x = SEMI_A * np.cos(theta)
    xy_y = SEMI_B * np.sin(theta)
    ax2.fill(xy_x, xy_y, color=ORANGE, alpha=0.3)
    ax2.plot(xy_x, xy_y, color=ORANGE, lw=2)
    ax2.set_aspect("equal")
    ax2.set_xlabel("x (chord, a=0.5)", fontsize=10)
    ax2.set_ylabel("y (thickness, b=0.02)", fontsize=10)
    ax2.set_title(
        "xy-plane (frontal view)\nFrontal: π·b·c = {:.4f}".format(A_FRONTAL), fontsize=9
    )
    ax2.annotate("", xy=(SEMI_A, 0), xytext=(0, 0),
                 arrowprops=dict(arrowstyle="->", color=RED, lw=1.5))
    ax2.text(SEMI_A / 2, 0.005, f"a={SEMI_A}", ha="center", color=RED, fontsize=8)
    ax2.annotate("", xy=(0, SEMI_B), xytext=(0, 0),
                 arrowprops=dict(arrowstyle="->", color=BLUE, lw=1.5))
    ax2.text(-0.05, SEMI_B / 2, f"b={SEMI_B}", ha="right", color=BLUE, fontsize=8)
    ax2.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.4)
    ax2.axvline(0, color="gray", lw=0.5, ls="--", alpha=0.4)
    ax2.set_xlim(-0.7, 0.7)
    ax2.set_ylim(-0.05, 0.05)

    # Freestream arrow on both panels
    for ax, arrow_y, ytext in [(ax1, 1.6, 1.6), (ax2, 0.038, 0.038)]:
        ax.annotate("", xy=(0.8, arrow_y), xytext=(-0.8, arrow_y),
                    arrowprops=dict(arrowstyle="->", color="gray", lw=1.2))
        ax.text(0, arrow_y + 0.005, "U∞", ha="center", color="gray", fontsize=8)

    fig.suptitle(
        "Heaving Ellipsoid Geometry\n"
        f"Semi-axes: a={SEMI_A}, b={SEMI_B}, c={SEMI_C} | Re=100 | V_heave=0.5",
        fontsize=10, fontweight="bold",
    )
    fig.tight_layout()

    out = figures_dir / "fig_geometry.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"G1: {out} + .png")


# ---------------------------------------------------------------------------
# F1: Force time history — Cd and CL
# ---------------------------------------------------------------------------

def plot_forces(figures_dir: Path, forces_csv: Path):
    """F1: Cd and CL vs time from forces.csv."""
    import pandas as pd

    df = pd.read_csv(forces_csv)
    t = df["time"].values
    Fx = df["Fx"].values
    Fy = df["Fy"].values

    # Force on body = -force on fluid (IBM convention)
    F_drag = -Fx  # drag on body (positive = opposing freestream)
    F_lift = -Fy  # lift on body

    # Coefficients referenced to planform area (wing-like reference)
    Cd_planform = F_drag / (Q * A_PLANFORM)
    CL_planform = F_lift / (Q * A_PLANFORM)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True)

    # Panel 1: Cd
    ax1.plot(t, Cd_planform, color=BLUE, lw=2, marker="o", markersize=5, label="Cd (planform ref)")
    ax1.set_ylabel("Drag coefficient Cd", fontsize=10)
    ax1.legend(fontsize=9, loc="upper right")
    ax1.grid(True, alpha=0.3)
    ax1.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    # Annotate steady-state value
    ax1.axhline(Cd_planform[-1], color=BLUE, lw=0.8, ls=":", alpha=0.6)
    ax1.text(t[-1] * 0.05, Cd_planform[-1] + 0.002,
             f"Cd={Cd_planform[-1]:.3f} (t={t[-1]:.0f})", color=BLUE, fontsize=8)

    # Panel 2: CL
    ax2.plot(t, CL_planform, color=RED, lw=2, marker="s", markersize=5,
             label="CL (planform ref)")
    ax2.set_xlabel("Time (dimensionless)", fontsize=10)
    ax2.set_ylabel("Lift coefficient CL", fontsize=10)
    ax2.legend(fontsize=9, loc="upper right")
    ax2.grid(True, alpha=0.3)
    ax2.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    ax2.text(t[-1] * 0.05, CL_planform[-1] + 0.001,
             f"CL={CL_planform[-1]:.3f}", color=RED, fontsize=8)

    fig.suptitle(
        "Heaving Ellipsoid Force History\n"
        f"Re=100 | V_heave=0.5 | Planform ref: A={A_PLANFORM:.3f}",
        fontsize=10, fontweight="bold",
    )
    fig.tight_layout()

    out = figures_dir / "fig_forces.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"F1: {out} + .png")

    # Print summary
    print(f"  Steady-state (t={t[-1]:.0f}): Cd={Cd_planform[-1]:.4f}, CL={CL_planform[-1]:.4f}")
    print(f"  A_planform={A_PLANFORM:.4f}, A_frontal={A_FRONTAL:.4f}, q={Q:.2f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate heaving ellipsoid figures")
    script_dir = Path(__file__).parent
    parser.add_argument(
        "--forces-csv",
        type=Path,
        default=script_dir / "forces.csv",
        help="Path to forces.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=script_dir / "figures",
        help="Output directory for figures",
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to: {args.output_dir}")

    plot_geometry(args.output_dir)
    plot_forces(args.output_dir, args.forces_csv)

    print("\nAll figures generated.")


if __name__ == "__main__":
    main()
