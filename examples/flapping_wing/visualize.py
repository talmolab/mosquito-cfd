#!/usr/bin/env python3
"""Visualize flapping wing simulation output using yt.

Usage:
    # Velocity slices
    uv run python examples/flapping_wing/visualize.py velocity \\
        Z:/users/eberrigan/mosquito-cfd/runs/flapping_wing/plt00100

    # Force time series with kinematics overlay
    uv run python examples/flapping_wing/visualize.py forces \\
        Z:/users/eberrigan/mosquito-cfd/runs/flapping_wing/plt00* \\
        --output-dir results/

    # Vorticity visualization
    uv run python examples/flapping_wing/visualize.py vorticity \\
        Z:/users/eberrigan/mosquito-cfd/runs/flapping_wing/plt00100
"""

import argparse
from pathlib import Path
import numpy as np


# Kinematics parameters (match inputs file)
# f* = 1.0 means 1 wingbeat per dimensionless time unit
FREQUENCY = 1.0  # dimensionless (1 wingbeat = 1 time unit)
STROKE_AMP = 70.0  # degrees
PITCH_AMP = 45.0  # degrees


def compute_kinematics(time: float) -> tuple[float, float, float]:
    """Compute wing angles at given time.

    Returns:
        phi: stroke angle (degrees)
        alpha: pitch angle (degrees)
        omega_phi: stroke angular velocity (deg/s)
    """
    omega = 2 * np.pi * FREQUENCY
    phi = STROKE_AMP * np.sin(omega * time)
    alpha = PITCH_AMP * np.cos(omega * time)
    omega_phi = STROKE_AMP * omega * np.cos(omega * time) * 180 / np.pi
    return phi, alpha, omega_phi


def visualize_velocity(plotfile: str, output_dir: Path | None = None):
    """Generate velocity field slices with wing kinematics overlay."""
    import yt
    yt.set_log_level("error")

    ds = yt.load(plotfile)
    output_dir = output_dir or Path(".")
    time = float(ds.current_time)

    # Compute current kinematics
    phi, alpha, omega_phi = compute_kinematics(time)

    # Extract particle positions to find wing
    ad = ds.all_data()
    x_pos = float(np.mean(ad['all', 'particle_position_x']))
    y_pos = float(np.mean(ad['all', 'particle_position_y']))
    z_pos = float(np.mean(ad['all', 'particle_position_z']))

    print(f"Loaded: {plotfile}")
    print(f"  Time: {time:.3f}")
    print(f"  Kinematics: phi={phi:.1f} deg, alpha={alpha:.1f} deg")
    print(f"  Wing centroid: ({x_pos:.2f}, {y_pos:.2f}, {z_pos:.2f})")

    for field in ['x_velocity', 'y_velocity', 'z_velocity']:
        # Slice through wing hinge (z=2.5)
        slc = yt.SlicePlot(ds, 'z', field, center=[4.0, 2.0, 2.5])
        slc.set_log(field, False)

        # Add title with simulation info
        field_label = field.replace('_', ' ').title()
        title = (
            f"Flapping Wing | t={time:.2f} | "
            f"phi={phi:.0f} deg | {field_label}"
        )
        slc.annotate_title(title)

        # Mark wing position
        slc.annotate_marker([x_pos, y_pos, z_pos], marker='+', color='white', s=150)

        # Descriptive filename
        output_name = f"flapping_wing_t{time:.2f}_{field}.png"
        output_path = output_dir / output_name
        slc.save(str(output_path))
        print(f"Saved: {output_path}")


def visualize_vorticity(plotfile: str, output_dir: Path | None = None):
    """Generate vorticity visualization at wing plane."""
    import yt
    yt.set_log_level("error")

    ds = yt.load(plotfile)
    output_dir = output_dir or Path(".")
    time = float(ds.current_time)

    phi, alpha, _ = compute_kinematics(time)

    print(f"Loaded: {plotfile}")
    print(f"  Time: {time:.3f}")
    print(f"  Kinematics: phi={phi:.1f} deg, alpha={alpha:.1f} deg")

    # Create vorticity magnitude from velocity gradients
    # yt can compute vorticity automatically
    slc = yt.SlicePlot(ds, 'z', 'vorticity_magnitude', center=[4.0, 2.0, 4.0])

    title = f"Flapping Wing Vorticity | t={time:.2f} | phi={phi:.0f} deg"
    slc.annotate_title(title)

    # Add velocity vectors
    slc.annotate_quiver('x_velocity', 'y_velocity', factor=16)

    output_name = f"flapping_wing_t{time:.2f}_vorticity.png"
    output_path = output_dir / output_name
    slc.save(str(output_path))
    print(f"Saved: {output_path}")


def extract_forces(plotfile: str) -> dict:
    """Extract force components from plotfile particles."""
    import yt
    yt.set_log_level("error")

    ds = yt.load(plotfile)
    ad = ds.all_data()
    time = float(ds.current_time)

    # Force components stored in particle_real_comp3/4/5
    fx = float(np.array(ad['all', 'particle_real_comp3']).sum())
    fy = float(np.array(ad['all', 'particle_real_comp4']).sum())
    fz = float(np.array(ad['all', 'particle_real_comp5']).sum())

    # Compute kinematics at this time
    phi, alpha, omega_phi = compute_kinematics(time)

    return {
        "time": time,
        "fx": fx,
        "fy": fy,
        "fz": fz,
        "phi": phi,
        "alpha": alpha,
        "omega_phi": omega_phi,
    }


def visualize_forces(plotfiles: list[str], output_dir: Path | None = None):
    """Generate force time series with kinematics overlay."""
    import matplotlib.pyplot as plt

    output_dir = output_dir or Path(".")

    # Extract forces from all plotfiles
    data = []
    for pf in sorted(plotfiles):
        print(f"Processing: {pf}")
        data.append(extract_forces(pf))

    times = np.array([d["time"] for d in data])
    fx = np.array([d["fx"] for d in data])
    fy = np.array([d["fy"] for d in data])
    phi = np.array([d["phi"] for d in data])
    alpha = np.array([d["alpha"] for d in data])

    # Force on wing = -force on fluid
    F_drag = -fx  # Chord-wise (drag)
    F_lift = -fy  # Normal (lift)

    # Create figure with 3 panels
    fig, axes = plt.subplots(3, 1, figsize=(10, 8), sharex=True)

    # Panel 1: Kinematics
    ax1 = axes[0]
    ln1 = ax1.plot(times, phi, 'b-', linewidth=2, label='Stroke (phi)')
    ax1.set_ylabel('Stroke Angle (deg)', color='blue', fontsize=11)
    ax1.tick_params(axis='y', labelcolor='blue')
    ax1.axhline(0, color='gray', linestyle='--', alpha=0.5)

    ax1_twin = ax1.twinx()
    ln2 = ax1_twin.plot(times, alpha, 'r--', linewidth=2, label='Pitch (alpha)')
    ax1_twin.set_ylabel('Pitch Angle (deg)', color='red', fontsize=11)
    ax1_twin.tick_params(axis='y', labelcolor='red')

    # Combined legend
    lns = ln1 + ln2
    labs = [l.get_label() for l in lns]
    ax1.legend(lns, labs, loc='upper right')
    ax1.set_title('Wing Kinematics', fontsize=12, fontweight='bold')
    ax1.grid(True, alpha=0.3)

    # Panel 2: Drag force
    ax2 = axes[1]
    ax2.plot(times, F_drag, 'b-o', linewidth=2, markersize=4, label='Drag (Fx)')
    ax2.set_ylabel('Drag Force', fontsize=11)
    ax2.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax2.legend(loc='upper right')
    ax2.grid(True, alpha=0.3)

    # Panel 3: Lift force
    ax3 = axes[2]
    ax3.plot(times, F_lift, 'r-s', linewidth=2, markersize=4, label='Lift (Fy)')
    ax3.set_xlabel('Time (dimensionless)', fontsize=11)
    ax3.set_ylabel('Lift Force', fontsize=11)
    ax3.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax3.legend(loc='upper right')
    ax3.grid(True, alpha=0.3)

    # Main title
    fig.suptitle(
        'Flapping Wing Force History with Kinematics\n'
        f'f={FREQUENCY} | phi_amp={STROKE_AMP} deg | alpha_amp={PITCH_AMP} deg',
        fontsize=12, fontweight='bold'
    )
    plt.tight_layout()

    # Save
    output_path = output_dir / 'flapping_wing_force_history.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.savefig(output_dir / 'flapping_wing_force_history.pdf', bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")

    # Also compute and print cycle-averaged forces
    if len(times) > 1:
        period = 1.0 / FREQUENCY
        # Find indices within one complete period
        mask = times <= period
        if mask.sum() > 2:
            mean_lift = np.mean(F_lift[mask])
            mean_drag = np.mean(F_drag[mask])
            print(f"\nCycle-averaged forces (first period):")
            print(f"  Mean lift: {mean_lift:.4f}")
            print(f"  Mean drag: {mean_drag:.4f}")


def main():
    parser = argparse.ArgumentParser(description="Visualize flapping wing output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # velocity subcommand
    vel_parser = subparsers.add_parser("velocity", help="Generate velocity slices")
    vel_parser.add_argument("plotfile", help="Path to plotfile")
    vel_parser.add_argument("--output-dir", type=Path, help="Output directory")

    # vorticity subcommand
    vort_parser = subparsers.add_parser("vorticity", help="Generate vorticity plot")
    vort_parser.add_argument("plotfile", help="Path to plotfile")
    vort_parser.add_argument("--output-dir", type=Path, help="Output directory")

    # forces subcommand
    force_parser = subparsers.add_parser("forces", help="Generate force time series")
    force_parser.add_argument("plotfiles", nargs="+", help="Paths to plotfiles")
    force_parser.add_argument("--output-dir", type=Path, help="Output directory")

    args = parser.parse_args()

    if args.command == "velocity":
        visualize_velocity(args.plotfile, args.output_dir)
    elif args.command == "vorticity":
        visualize_vorticity(args.plotfile, args.output_dir)
    elif args.command == "forces":
        visualize_forces(args.plotfiles, args.output_dir)


if __name__ == "__main__":
    main()
