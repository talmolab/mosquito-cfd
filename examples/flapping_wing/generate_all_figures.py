#!/usr/bin/env python3
"""Generate all figures for the flapping wing validation.

Usage:
    uv run python examples/flapping_wing/generate_all_figures.py [--forces-csv PATH]
    uv run python examples/flapping_wing/generate_all_figures.py \\
        --plotfile Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/plt00500

Produces:
    examples/flapping_wing/figures/
        fig_planform.pdf/png       G1: Wing planform marker scatter
        fig_kinematics.pdf/png     K1: Euler angles vs phase
        fig_wing_phases.pdf/png    K2: Wing positions at key phases
        fig_forces.pdf/png         F1: Force time series with kinematics
        fig_velocity.pdf/png       V1: x-velocity field at mid-stroke [requires --plotfile]
"""

import argparse
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

from mosquito_cfd.benchmarks.wing_kinematics import rotation_matrix as _wing_rotation
from mosquito_cfd.force_surrogate import compute_force_reference
from mosquito_cfd.force_surrogate.constants import R_GYRATION
from mosquito_cfd.geometry import generate_planform, read_vertex_file

# ---------------------------------------------------------------------------
# Constants matching inputs.3d.validation (van Veen convention, Tier T2a):
# x = chord, y = span, z = vertical/lift. See docs/coordinate-convention.md.
# ---------------------------------------------------------------------------
F_STAR = 1.0  # dimensionless frequency (1 wingbeat = 1 time unit)
PHI_AMP_DEG = 70.0  # stroke amplitude (degrees)
ALPHA_AMP_DEG = 45.0  # pitch amplitude (degrees)
SPAN = 3.0  # wing span (dimensionless chord lengths)
CHORD = 1.0  # wing chord (reference length)
R_TIP = 3.0  # hinge-to-tip distance (dimensionless)
HINGE = np.array([4.0, 0.5, 4.0])  # hinge (span root, low-y end) — domain units
CENTER = np.array(
    [4.0, 2.0, 4.0]
)  # wing centre (solver adds this to the origin-centred vertex file)

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
    """Van Veen convention R = Rz(phi)*Ry(alpha)*Rx(theta) (degrees in).

    Thin wrapper over the single canonical source
    ``mosquito_cfd.benchmarks.wing_kinematics.rotation_matrix`` (no independent rotation math
    here — the DRY code-source rule; docs/coordinate-convention.md).
    """
    return _wing_rotation(
        np.radians(phi_deg), np.radians(alpha_deg), np.radians(theta_deg)
    )


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
        # The committed wing.vertex is origin-centred (the solver adds the domain centre), so it
        # is already in the local frame — no CENTER subtraction.
        markers = read_vertex_file(str(vertex_file))
    else:
        markers = generate_planform(
            "elliptic", SPAN, CHORD, spacing=0.05, span_axis="y"
        )
    # Local frame (van Veen): x = chord (-0.5..0.5), y = span (-1.5..1.5), z = 0 (flat).

    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(
        markers[:, 1], markers[:, 0], s=1.5, color=BLUE, alpha=0.7, rasterized=True
    )
    ax.set_xlabel("Span y (chord lengths)", fontsize=10)
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
    ax.annotate(
        "",
        xy=(1.5, 0.0),
        xytext=(-1.5, 0.0),
        arrowprops=dict(arrowstyle="<->", color=RED, lw=1.5),
    )
    ax.text(0, -0.65, f"Span = {SPAN:.0f}c", ha="center", color=RED, fontsize=9)
    ax.annotate(
        "",
        xy=(0.0, 0.5),
        xytext=(0.0, -0.5),
        arrowprops=dict(arrowstyle="<->", color=GREEN, lw=1.5),
    )
    ax.text(
        1.6,
        0.0,
        f"Chord = {CHORD:.0f}c",
        ha="left",
        color=GREEN,
        fontsize=9,
        va="center",
    )

    fig.tight_layout()
    out = figures_dir / "fig_planform.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"G1: {out} + .png")


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
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"K1: {out} + .png")


# ---------------------------------------------------------------------------
# K2: Wing positions at key phases
# ---------------------------------------------------------------------------


def plot_k2_wing_phases(figures_dir: Path, vertex_file: Path | None = None):
    """K2: Wing marker positions projected to xz-plane at 4 key phases."""
    if vertex_file and vertex_file.exists():
        # Origin-centred file -> domain frame by adding the wing centre (the solver does this).
        ref_markers = read_vertex_file(str(vertex_file)) + CENTER
    else:
        ref_markers = (
            generate_planform("elliptic", SPAN, CHORD, spacing=0.05, span_axis="y")
            + CENTER
        )

    # 4 key phases: t=0, T/4, T/2, 3T/4
    phases = [(0.0, "t=0"), (0.25, "t=T/4"), (0.5, "t=T/2"), (0.75, "t=3T/4")]

    fig, axes = plt.subplots(1, 4, figsize=(12, 3.5), sharey=True)

    colors = [BLUE, ORANGE, GREEN, RED]
    for ax, (t_val, label), color in zip(axes, phases, colors):
        phi_deg, alpha_deg = euler_angles(t_val)
        R = rotation_matrix(phi_deg, alpha_deg)
        markers = transform_markers(ref_markers, HINGE, R)

        # Project to the x-y stroke plane (van Veen: stroke sweeps the span-tip in x-y)
        ax.scatter(
            markers[:, 0], markers[:, 1], s=1.0, color=color, alpha=0.7, rasterized=True
        )
        ax.scatter(*HINGE[[0, 1]], s=50, color="black", zorder=5, marker="^")
        ax.set_title(
            f"{label}\nphi={phi_deg:.0f}deg, alpha={alpha_deg:.0f}deg",
            fontsize=8,
            color=color,
        )
        ax.set_xlabel("x (chord / streamwise)", fontsize=9)
        ax.set_xlim(0.5, 7.5)
        ax.set_ylim(-0.5, 4.5)
        ax.set_aspect("equal")
        ax.grid(True, alpha=0.3)

    axes[0].set_ylabel("y (span)", fontsize=9)
    axes[0].text(HINGE[0], HINGE[1] - 0.3, "Hinge", ha="center", fontsize=7)

    fig.suptitle(
        "Wing Marker Positions at Key Phases (x-y stroke plane, van Veen convention)\n"
        "Triangle = wing hinge (root); the stroke sweeps the span-tip through x-y",
        fontsize=10,
    )
    fig.tight_layout()
    out = figures_dir / "fig_wing_phases.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"K2: {out} + .png")


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

    # Reference: van Veen F_ref = 0.5*rho*omega^2*S_yy at the radius of gyration
    # (single source — mosquito_cfd.force_surrogate).
    ref = compute_force_reference(F_STAR, PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, rho=1.0)
    u_ref, q_ref, S, F_ref = ref.u_ref, ref.q_ref, ref.area, ref.f_ref
    print(
        f"  u_ref = {u_ref:.2f}, q_ref = {q_ref:.2f}, S = {S:.4f}, F_ref = {F_ref:.2f}"
    )

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
    ax2.plot(
        t_s, CF_x, color=BLUE, lw=1.5, alpha=0.8, label="CF_x (chord / streamwise)"
    )
    ax2.plot(t_s, CF_y, color=GREEN, lw=1.5, alpha=0.8, ls="--", label="CF_y (span)")
    ax2.axhline(0, color="gray", lw=0.5, ls="--", alpha=0.5)
    ax2.set_ylabel("CF (lab frame)", fontsize=9)
    ax2.legend(fontsize=8, loc="upper right")
    plt.setp(ax2.get_xticklabels(), visible=False)

    # Panel 3: CF_z (lift / span-axis force)
    ax3.plot(t_s, CF_z, color=RED, lw=1.5, label="CF_z (vertical / lift)")
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
    note = f"Forces normalized by q_ref x S = {F_ref:.1f} (van Veen: q_ref = 0.5 rho u_ref^2, u_ref = {u_ref:.1f} at radius of gyration)"
    fig.text(0.5, -0.01, note, ha="center", fontsize=7, color="gray")

    out = figures_dir / "fig_forces.pdf"
    fig.savefig(out, bbox_inches="tight", dpi=150)
    fig.savefig(out.with_suffix(".png"), bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"F1: {out} + .png")

    # Print summary stats
    print(f"  CF_z range (t>0.1): [{CF_z.min():.3f}, {CF_z.max():.3f}]")
    print(
        f"  mean CF_z = {CF_z.mean():.4f}, rms CF_z = {np.sqrt((CF_z**2).mean()):.4f}"
    )
    print(f"  max |CF_x| = {np.abs(CF_x).max():.4f}")


# ---------------------------------------------------------------------------
# V1: x-velocity field at mid-stroke (requires --plotfile)
# ---------------------------------------------------------------------------


def plot_velocity_field(figures_dir: Path, plotfile: Path):
    """V1: x-velocity field z-slice at mid-stroke (t=0.25, phi=70°).

    Technique adapted from:
        C:\\vaults\\physics surrogate models\\ellipsoid-validation-figure\\
        generate_ellipsoid_figure.py
    """
    import yt

    yt.set_log_level("error")

    print(f"  Loading plotfile: {plotfile}")
    ds = yt.load(str(plotfile))
    time = float(ds.current_time)
    phi_deg, alpha_deg = euler_angles(time)
    print(f"  Time: {time:.3f}, phi={phi_deg:.1f}deg, alpha={alpha_deg:.1f}deg")

    xl = float(ds.domain_left_edge[0])
    xr = float(ds.domain_right_edge[0])
    yl = float(ds.domain_left_edge[1])
    yr = float(ds.domain_right_edge[1])
    nx = int(ds.domain_dimensions[0])
    ny = int(ds.domain_dimensions[1])
    cx = float(ds.domain_center[0])
    cy = float(ds.domain_center[1])

    # Fixed-resolution buffer: full x-y plane at z = domain center (wing / stroke plane)
    # Upsample 4x for smooth visualization of coarse grid
    frb_nx = nx * 4
    frb_ny = ny * 4
    slc = ds.slice("z", ds.domain_center[2])
    frb = slc.to_frb(
        ds.domain_width[0],
        (frb_nx, frb_ny),
        height=ds.domain_width[1],
    )
    u = np.array(frb["x_velocity"])
    # FRB shape: either (frb_nx, frb_ny) or (frb_ny, frb_nx) — imshow wants rows=y, cols=x
    if u.shape == (frb_nx, frb_ny):
        u = u.T
    print(f"  Velocity range: [{u.min():.3f}, {u.max():.3f}]")
    if abs(u.max()) > 50:
        raise ValueError(
            f"Velocity values outside expected dimensionless range: [{u.min():.1f}, {u.max():.1f}]\n"
            "yt may have applied a CGS unit conversion."
        )
    velocity_available = abs(u).max() > 1e-6

    # Wing centroid from IB particle positions
    ad = ds.all_data()
    x_wing = float(np.mean(np.array(ad["all", "particle_position_x"])))
    y_wing = float(np.mean(np.array(ad["all", "particle_position_y"])))
    print(
        f"  Wing centroid (domain): ({x_wing:.2f}, {y_wing:.2f})"
        f"  -> display: ({x_wing - cx:.2f}, {y_wing - cy:.2f})"
    )

    if not velocity_available:
        print(
            "  WARNING: x_velocity is all zeros -- falling back to tracer field (wing position)."
        )
        tracer = np.array(frb["tracer"])
        if tracer.shape == (frb_nx, frb_ny):
            tracer = tracer.T
        field_data = tracer
        cmap = "Blues"
        cbar_label = "tracer (wing material indicator)"
        title_note = "tracer field (velocity not in plotfile)"
    else:
        field_data = u
        cmap = "RdYlBu_r"
        cbar_label = "$u$ (dimensionless)"
        title_note = f"x-velocity field ($t = {time:.3f}$, $\\phi = {phi_deg:.0f}°$)"

    fig, ax = plt.subplots(figsize=(8, 5))
    extent = [xl - cx, xr - cx, yl - cy, yr - cy]
    im = ax.imshow(
        field_data,
        origin="lower",
        extent=extent,
        cmap=cmap,
        aspect="equal",
        interpolation="bilinear",
    )
    cbar = plt.colorbar(im, ax=ax, label=cbar_label, fraction=0.04, pad=0.04)
    cbar.ax.tick_params(labelsize=9)

    ax.plot(
        x_wing - cx,
        y_wing - cy,
        "r+",
        markersize=14,
        markeredgewidth=2,
        label=f"wing centroid ({x_wing:.1f}, {y_wing:.1f})",
    )
    ax.legend(fontsize=8, loc="lower right", framealpha=0.7)

    ax.set_xlabel("$x$ (dimensionless)", fontsize=11)
    ax.set_ylabel("$y$ (dimensionless)", fontsize=11)
    ax.set_title(
        f"Flapping Wing — {title_note}\n"
        f"top-down z-slice at z={float(ds.domain_center[2]):.1f} "
        f"(wing / stroke plane; x=chord, y=span)",
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
    parser = argparse.ArgumentParser(description="Generate all flapping wing figures")
    parser.add_argument(
        "--forces-csv",
        type=Path,
        default=Path(__file__).parent / "forces_t2a_newconv.csv",
        help="Path to the force CSV (default: the validated T2a new-convention run)",
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
    parser.add_argument(
        "--plotfile",
        type=Path,
        default=None,
        help=(
            "Path to AMReX plotfile for velocity field visualization (V1). "
            "Example: Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/plt00500"
        ),
    )
    args = parser.parse_args()

    figures_dir = args.output_dir
    figures_dir.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to: {figures_dir}")

    plot_g1_planform(figures_dir, args.vertex_file)
    plot_k1_kinematics(figures_dir)
    plot_k2_wing_phases(figures_dir, args.vertex_file)
    plot_f1_forces(figures_dir, args.forces_csv)

    if args.plotfile is not None:
        plot_velocity_field(figures_dir, args.plotfile)
    else:
        print("V1: skipped (pass --plotfile to generate velocity field figure)")

    print("\nAll figures generated.")


if __name__ == "__main__":
    main()
