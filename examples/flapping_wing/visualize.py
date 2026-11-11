#!/usr/bin/env python3
"""Visualize flapping wing simulation output using yt.

Usage:
    # Velocity slices
    uv run python examples/flapping_wing/visualize.py velocity \\
        Z:/users/eberrigan/mosquito-cfd/runs/flapping_wing/plt00100

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

    args = parser.parse_args()

    if args.command == "velocity":
        visualize_velocity(args.plotfile, args.output_dir)
    elif args.command == "vorticity":
        visualize_vorticity(args.plotfile, args.output_dir)


if __name__ == "__main__":
    main()
