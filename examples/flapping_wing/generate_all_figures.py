#!/usr/bin/env python3
"""Generate all figures for the flapping wing validation.

Usage:
    uv run python examples/flapping_wing/generate_all_figures.py [--forces-csv PATH]

Produces:
    examples/flapping_wing/figures/
        fig_planform.pdf       G1: Wing planform marker scatter
        fig_kinematics.pdf     K1: Euler angles vs phase
        fig_wing_phases.pdf    K2: Wing positions at key phases
        fig_forces.pdf         F1: Force time series with kinematics
"""

import argparse
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from mosquito_cfd.geometry import generate_planform, read_vertex_file

# ---------------------------------------------------------------------------
# Constants matching inputs.3d.validation
# ---------------------------------------------------------------------------
F_STAR = 1.0        # dimensionless frequency (1 wingbeat = 1 time unit)
PHI_AMP_DEG = 70.0  # stroke amplitude (degrees)
ALPHA_AMP_DEG = 45.0  # pitch amplitude (degrees)
SPAN = 3.0          # wing span (dimensionless chord lengths)
CHORD = 1.0         # wing chord (reference length)
R_TIP = 3.0         # hinge-to-tip distance (dimensionless)
HINGE = np.array([4.0, 2.0, 2.5])  # hinge position (domain units)
CENTER = np.array([4.0, 2.0, 4.0])  # wing center (domain units)

# IBM colorblind-safe palette (from plot_config.py)
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
PURPLE = "#CC79A7"


def euler_angles(time, f=F_STAR, phi_amp=PHI_AMP_DEG, alpha_amp=ALPHA_AMP_DEG):
    """Compute Euler angles (deg) at given time."""
    omega = 2.0 * np.pi * f
    phi = phi_amp * np.sin(omega * time)
    alpha = alpha_amp * np.cos(omega * time)
    return phi, alpha


def rotation_matrix(phi_deg, alpha_deg, theta_deg=0.0):
    """ZYX Euler rotation matrix R = Rz(phi) * Ry(theta) * Rx(alpha)."""
    phi = np.radians(phi_deg)
    alpha = np.radians(alpha_deg)
    theta = np.radians(theta_deg)
    cp, sp = np.cos(phi), np.sin(phi)
    ca, sa = np.cos(alpha), np.sin(alpha)
    ct, st = np.cos(theta), np.sin(theta)
    return np.array([
        [cp*ct, cp*st*sa - sp*ca, cp*st*ca + sp*sa],
        [sp*ct, sp*st*sa + cp*ca, sp*st*ca - cp*sa],
        [-st,   ct*sa,            ct*ca],
    ])


def transform_markers(ref_pos, hinge, R):
    """Apply rotation R about hinge to reference positions."""
    d = ref_pos - hinge
    return hinge + (R @ d.T).T


# ---------------------------------------------------------------------------
# G1: Wing planform
# ---------------------------------------------------------------------------

def plot_g1_planform(figures_dir: Path, vertex_file: Path | None = None):
    """G1: Wing planform marker scatter in local frame."""
    if vertex_file and vertex_file.exists():
        markers = read_vertex_file(str(vertex_file))
        # Convert from domain frame to local frame (subtract center)
        markers = markers - CENTER
    else:
        markers = generate_planform("elliptic", SPAN, CHORD, spacing=0.05) - np.array([0., 0., 0.])
    # markers are in local frame: x = chord (-0.5 to 0.5), z = span (-1.5 to 1.5)

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(markers[:, 2], markers[:, 0], s=1.5, color=BLUE, alpha=0.7, rasterized=True)
    ax.set_xlabel("Span z (chord lengths)", fontsize=10)
    ax.set_ylabel("Chord x (chord lengths)", fontsize=10)
    ax.set_aspect("equal")
    ax.set_title(
        f"Wing Planform: elliptic, {SPAN:.0f}c span x {CHORD:.0f}c chord\n"
        f"({len(markers)} Lagrangian markers, 50 mm spacing)",
        fontsize=9,
    )
    ax.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    ax.axvline(0, color="gray", lw=0.5, ls="--", alpha=0.5)

    # Annotate span and chord
    ax.annotate("", xy=(1.5, 0.0), xytext=(-1.5, 0.0),
                arrowprops=dict(arrowstyle="<->", color=RED, lw=1.5))
    ax.text(0, -0.65, f"Span = {SPAN:.0f}c", ha="center", color=RED, fontsize=9)
    ax.annotate("", xy=(0.0, 0.5), xytext=(0.0, -0.5),
                arrowprops=dict(arrowstyle="<->", color=GREEN, lw=1.5))
    ax.text(1.6, 0.0, f"Chord = {CHORD:.0f}c", ha="left", color=GREEN, fontsize=9, va="center")

    fig.tight_layout()
    out = figures_dir / "fig_planform.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"G1: {out}")


# ---------------------------------------------------------------------------
# K1: Euler angles vs phase
# ---------------------------------------------------------------------------

def plot_k1_kinematics(figures_dir: Path):
    """K1: phi(t) and alpha(t) over one wingbeat."""
    t = np.linspace(0, 1.0, 1000)
    phi, alpha = euler_angles(t)

    fig, ax1 = plt.subplots(figsize=(6, 3.5))
    ln1 = ax1.plot(t, phi, color=BLUE, lw=2, label="Stroke φ(t)")
    ax1.set_xlabel("Dimensionless time t/T", fontsize=10)
    ax1.set_ylabel("Stroke angle φ (deg)", color=BLUE, fontsize=10)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1.set_ylim(-85, 85)
    ax1.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    ax1.axvline(0.25, color="gray", lw=0.5, ls=":", alpha=0.5)
    ax1.axvline(0.75, color="gray", lw=0.5, ls=":", alpha=0.5)
    ax1.text(0.25, -80, "T/4", ha="center", fontsize=8, color="gray")
    ax1.text(0.75, -80, "3T/4", ha="center", fontsize=8, color="gray")

    ax2 = ax1.twinx()
    ln2 = ax2.plot(t, alpha, color=ORANGE, lw=2, ls="--", label="Pitch α(t)")
    ax2.set_ylabel("Pitch angle α (deg)", color=ORANGE, fontsize=10)
    ax2.tick_params(axis="y", labelcolor=ORANGE)
    ax2.set_ylim(-85, 85)

    lns = ln1 + ln2
    ax1.legend(lns, [l.get_label() for l in lns], loc="upper right", fontsize=9)
    ax1.set_title(
        "Wing Kinematics (van Veen et al. 2022)\n"
        f"f* = {F_STAR:.0f}, phi_amp = {PHI_AMP_DEG:.0f} deg, alpha_amp = {ALPHA_AMP_DEG:.0f} deg",
        fontsize=9,
    )
    fig.tight_layout()
    out = figures_dir / "fig_kinematics.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"K1: {out}")


# ---------------------------------------------------------------------------
# K2: Wing positions at key phases
# ---------------------------------------------------------------------------

def plot_k2_wing_phases(figures_dir: Path, vertex_file: Path | None = None):
    """K2: Wing marker positions projected to xz-plane at 4 key phases."""
    if vertex_file and vertex_file.exists():
        ref_markers = read_vertex_file(str(vertex_file))
    else:
        ref_markers = generate_planform("elliptic", SPAN, CHORD, spacing=0.05) + CENTER

    # 4 key phases: t=0, T/4, T/2, 3T/4
    phases = [(0.0, "t=0"), (0.25, "t=T/4"), (0.5, "t=T/2"), (0.75, "t=3T/4")]

    fig, axes = plt.subplots(1, 4, figsize=(12, 3.5), sharey=True)

    colors = [BLUE, ORANGE, GREEN, RED]
    for ax, (t_val, label), color in zip(axes, phases, colors):
        phi_deg, alpha_deg = euler_angles(t_val)
        R = rotation_matrix(phi_deg, alpha_deg)
        markers = transform_markers(ref_markers, HINGE, R)

        # Project to xz plane (horizontal=x, vertical=z)
        ax.scatter(markers[:, 0], markers[:, 2], s=1.0, color=color, alpha=0.7, rasterized=True)
        ax.scatter(*HINGE[[0, 2]], s=50, color="black", zorder=5, marker="^")
        ax.set_title(
            f"{label}\n"
            f"phi={phi_deg:.0f}deg, alpha={alpha_deg:.0f}deg",
            fontsize=8, color=color,
        )
        ax.set_xlabel("x", fontsize=9)
        ax.set_xlim(2.5, 5.5)
        ax.set_ylim(1.5, 6.5)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("z", fontsize=9)
    axes[0].text(HINGE[0], HINGE[2] - 0.25, "Hinge", ha="center", fontsize=7)

    fig.suptitle(
        "Wing Marker Positions at Key Phases (xz projection)\n"
        "Triangle = wing hinge (root)",
        fontsize=10,
    )
    fig.tight_layout()
    out = figures_dir / "fig_wing_phases.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"K2: {out}")


# ---------------------------------------------------------------------------
# F1: Force time series
# ---------------------------------------------------------------------------

def plot_f1_forces(figures_dir: Path, forces_csv: Path):
    """F1: Force time series with kinematics overlay."""
    import pandas as pd

    df = pd.read_csv(forces_csv)
    t = df["time"].values
    Fx = df["Fx"].values
    Fy = df["Fy"].values
    Fz = df["Fz"].values

    phi, alpha = euler_angles(t)

    # Skip large startup transient
    t_start = 0.05
    mask = t >= t_start
    t_s, Fx_s, Fy_s, Fz_s = t[mask], Fx[mask], Fy[mask], Fz[mask]
    phi_s, alpha_s = phi[mask], alpha[mask]

    # Reference: tip dynamic pressure
    omega = 2 * np.pi * F_STAR
    U_tip_max = omega * np.radians(PHI_AMP_DEG) * R_TIP
    q_tip = 0.5 * 1.0 * U_tip_max**2
    S = np.pi / 4 * SPAN * CHORD
    F_ref = q_tip * S
    print(f"  U_tip_max = {U_tip_max:.2f}, q_tip = {q_tip:.2f}, S = {S:.4f}, F_ref = {F_ref:.2f}")

    CF_x = Fx_s / F_ref
    CF_y = Fy_s / F_ref
    CF_z = Fz_s / F_ref

    fig = plt.figure(figsize=(8, 6))
    gs = gridspec.GridSpec(3, 1, hspace=0.05)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    # Panel 1: kinematics
    ax1.plot(t_s, phi_s, color=BLUE, lw=1.5, label="Stroke phi (deg)")
    ax1_r = ax1.twinx()
    ax1_r.plot(t_s, alpha_s, color=ORANGE, lw=1.5, ls="--", label="Pitch alpha (deg)")
    ax1.set_ylabel("phi (deg)", color=BLUE, fontsize=9)
    ax1_r.set_ylabel("alpha (deg)", color=ORANGE, fontsize=9)
    ax1.tick_params(axis="y", labelcolor=BLUE)
    ax1_r.tick_params(axis="y", labelcolor=ORANGE)
    ax1.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax1_r.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right")
    ax1.set_title(
        f"Flapping Wing Forces — coarse grid 64x32x64, f*={F_STAR:.0f}, Re~100",
        fontsize=9,
    )
    plt.setp(ax1.get_xticklabels(), visible=False)

    # Panel 2: CF_x and CF_y (stroke-plane forces)
    ax2.plot(t_s, CF_x, color=BLUE, lw=1.5, alpha=0.8, label="CF_x (stroke)")
    ax2.plot(t_s, CF_y, color=GREEN, lw=1.5, alpha=0.8, ls="--", label="CF_y (lateral)")
    ax2.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    ax2.set_ylabel("CF (stroke plane)", fontsize=9)
    ax2.legend(fontsize=8, loc="upper right")
    plt.setp(ax2.get_xticklabels(), visible=False)

    # Panel 3: CF_z (lift / span-axis force)
    ax3.plot(t_s, CF_z, color=RED, lw=1.5, label="CF_z (lift / span-normal)")
    ax3.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    # Mark acceptance range
    ax3.axhline(0.5, color=RED, lw=0.8, ls=":", alpha=0.5)
    ax3.axhline(-0.5, color=RED, lw=0.8, ls=":", alpha=0.5)
    ax3.set_ylabel("CF_z (lift)", fontsize=9)
    ax3.set_xlabel("Time t/T", fontsize=9)
    ax3.legend(fontsize=8, loc="upper right")

    # Common x-axis label
    ax3.set_xlabel("Dimensionless time t/T", fontsize=10)

    # Add normalization note
    note = f"Forces normalized by q_tip x S = {F_ref:.1f} (q_tip = 0.5 rho V_tip^2, V_tip = {U_tip_max:.1f})"
    fig.text(0.5, -0.01, note, ha="center", fontsize=7, color="gray")

    out = figures_dir / "fig_forces.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"F1: {out}")

    # Print summary stats
    print(f"  CF_z range (t>0.1): [{CF_z.min():.3f}, {CF_z.max():.3f}]")
    print(f"  mean CF_z = {CF_z.mean():.4f}, rms CF_z = {np.sqrt((CF_z**2).mean()):.4f}")
    print(f"  max |CF_x| = {np.abs(CF_x).max():.4f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate all flapping wing figures")
    parser.add_argument(
        "--forces-csv",
        type=Path,
        default=Path("Z:/users/eberrigan/mosquito-cfd-outputs/flapping_wing_val/IB_Particle_1.csv"),
        help="Path to IB_Particle_1.csv force output",
    )
    parser.add_argument(
        "--vertex-file",
        type=Path,
        default=Path("examples/flapping_wing/wing.vertex"),
        help="Path to wing.vertex file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("examples/flapping_wing/figures"),
    )
    args = parser.parse_args()

    figures_dir = args.output_dir
    figures_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to: {figures_dir}")

    plot_g1_planform(figures_dir, args.vertex_file)
    plot_k1_kinematics(figures_dir)
    plot_k2_wing_phases(figures_dir, args.vertex_file)
    plot_f1_forces(figures_dir, args.forces_csv)

    print("\nAll figures generated.")


if __name__ == "__main__":
    main()