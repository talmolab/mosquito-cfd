#!/usr/bin/env python3
"""Generate figures for the heaving ellipsoid validation.

Usage:
    uv run python examples/heaving_ellipsoid/generate_figures.py
    uv run python examples/heaving_ellipsoid/generate_figures.py \\
        --plotfile Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00500

Produces:
    examples/heaving_ellipsoid/figures/
        fig_geometry.pdf/png    G1: Elliptic cross-sections with semi-axes
        fig_forces.pdf/png      F1: Cd and CL vs time
        fig_validation.pdf/png  V1: x-velocity field (t=5.0) + force history [requires --plotfile]
"""

import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
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
# V1: Validation composite — x-velocity field + force history (requires plotfile)
# ---------------------------------------------------------------------------

def plot_validation(figures_dir: Path, plotfile: Path, forces_csv: Path):
    """V1: 2-panel composite matching proposal Figure 2.

    Panel (a): x-velocity z-slice from plotfile via matplotlib FRB (t=5.0).
    Panel (b): Drag and y-force time history from forces.csv.

    Technique adapted from:
        C:\\vaults\\physics surrogate models\\ellipsoid-validation-figure\\
        generate_ellipsoid_figure.py
    """
    import yt
    import pandas as pd
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

    # Body centroid from IB particle positions
    ad = ds.all_data()
    x_body = float(np.mean(np.array(ad['all', 'particle_position_x'])))
    y_body = float(np.mean(np.array(ad['all', 'particle_position_y'])))
    print(f"  Body center (domain): ({x_body:.2f}, {y_body:.2f})"
          f"  -> display: ({x_body - cx:.2f}, {y_body - cy:.2f})")

    # Load force history
    df = pd.read_csv(forces_csv)
    t_f = df["time"].values
    F_drag = -df["Fx"].values   # drag on body > 0
    F_lift = -df["Fy"].values   # y-force on body (resists heave)
    QUASI_STEADY_TIME = 7.0

    # --- Layout ---
    fig = plt.figure(figsize=(14, 5))
    gs = gridspec.GridSpec(
        2, 2, figure=fig,
        width_ratios=[1.7, 1.0],
        height_ratios=[1, 1],
        left=0.06, right=0.97,
        top=0.91, bottom=0.10,
        wspace=0.42, hspace=0.08,
    )
    ax_vel  = fig.add_subplot(gs[:, 0])
    ax_drag = fig.add_subplot(gs[0, 1])
    ax_lift = fig.add_subplot(gs[1, 1], sharex=ax_drag)

    # --- Panel (a): velocity field ---
    extent = [xl - cx, xr - cx, yl - cy, yr - cy]
    im = ax_vel.imshow(
        u,
        origin='lower',
        extent=extent,
        cmap='RdYlBu_r',
        aspect='equal',
        interpolation='bilinear',
    )
    cbar = plt.colorbar(im, ax=ax_vel, label='$u$ (dimensionless)', fraction=0.03, pad=0.04)
    cbar.ax.tick_params(labelsize=9)
    ax_vel.set_xlabel('$x$ (dimensionless)', fontsize=11)
    ax_vel.set_ylabel('$y$ (dimensionless)', fontsize=11)
    ax_vel.plot(x_body - cx, y_body - cy,
                'w+', markersize=14, markeredgewidth=2,
                label=f'body ({x_body:.1f}, {y_body:.1f})')
    ax_vel.legend(fontsize=8, loc='lower right', framealpha=0.7)
    ax_vel.set_title(f'(a) x-velocity field  ($t = {time:.1f}$)', fontsize=11, pad=6)

    # --- Panel (b): force history ---
    kw = dict(linewidth=2, markersize=5)
    qs_kw = dict(color='gray', linestyle='--', linewidth=1, alpha=0.7)
    ax_drag.plot(t_f, F_drag, color=BLUE, marker='o', label='Drag $-F_x$', **kw)
    ax_drag.axvline(QUASI_STEADY_TIME, **qs_kw)
    ax_drag.set_ylabel('Drag force (dimensionless)', fontsize=10)
    ax_drag.legend(fontsize=9, loc='lower right')
    ax_drag.grid(True, alpha=0.3)
    ax_drag.set_ylim(bottom=0)
    ax_drag.tick_params(labelbottom=False)
    ax_drag.set_title('(b) Force time history  ($t = 0$–$10$)', fontsize=11, pad=6)

    ax_lift.plot(t_f, F_lift, color=RED, marker='s', label='y-force $-F_y$', **kw)
    ax_lift.axvline(QUASI_STEADY_TIME,
                    label=f'quasi-steady ($t = {QUASI_STEADY_TIME:.0f}$)', **qs_kw)
    ax_lift.set_xlabel('Time (dimensionless)', fontsize=11)
    ax_lift.set_ylabel('y-force (dimensionless)', fontsize=10)
    ax_lift.legend(fontsize=9, loc='upper right')
    ax_lift.grid(True, alpha=0.3)

    out = figures_dir / "fig_validation.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"V1: {out} + .png")


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
    parser.add_argument(
        "--plotfile",
        type=Path,
        default=None,
        help=(
            "Path to AMReX plotfile for velocity field visualization (V1). "
            "Example: Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00500"
        ),
    )
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to: {args.output_dir}")

    plot_geometry(args.output_dir)
    plot_forces(args.output_dir, args.forces_csv)

    if args.plotfile is not None:
        plot_validation(args.output_dir, args.plotfile, args.forces_csv)
    else:
        print("V1: skipped (pass --plotfile to generate velocity field figure)")

    print("\nAll figures generated.")


if __name__ == "__main__":
    main()
