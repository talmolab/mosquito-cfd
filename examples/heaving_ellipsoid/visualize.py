#!/usr/bin/env python3
"""Visualize Heaving Ellipsoid simulation output using yt.

Usage:
    # Velocity slices
    uv run python examples/heaving_ellipsoid/visualize.py velocity \
        Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k01000

    # Force time series (extracts from multiple plotfiles)
    uv run python examples/heaving_ellipsoid/visualize.py forces \
        Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00000 \
        Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00100 \
        ... (all plotfiles)
"""

import argparse
from pathlib import Path


def visualize_velocity(plotfile: str, output_dir: Path | None = None):
    """Generate velocity field slices with actual body position tracking."""
    import yt
    import numpy as np
    from matplotlib.patches import Ellipse
    yt.set_log_level("error")

    ds = yt.load(plotfile)
    output_dir = output_dir or Path(".")
    time = float(ds.current_time)

    # Extract actual particle positions (body has moved due to heaving!)
    ad = ds.all_data()
    x_pos = float(np.mean(ad['all', 'particle_position_x']))
    y_pos = float(np.mean(ad['all', 'particle_position_y']))
    z_pos = float(np.mean(ad['all', 'particle_position_z']))

    print(f"Loaded: {plotfile}")
    print(f"  Time: {time}")
    print(f"  Body position: ({x_pos:.2f}, {y_pos:.2f}, {z_pos:.2f})")

    # Ellipsoid semi-axes (from inputs file)
    semi_a, semi_b, semi_c = 0.5, 0.02, 1.5  # x, y, z

    for field in ['x_velocity', 'y_velocity', 'z_velocity']:
        slc = yt.SlicePlot(ds, 'z', field)
        slc.set_log(field, False)

        # Add title with simulation info
        field_label = field.replace('_', ' ').title()
        slc.annotate_title(f"Heaving Ellipsoid Re=100 | t={time:.1f} | {field_label}")

        # Mark ACTUAL body position (not initial position!)
        slc.annotate_marker([x_pos, y_pos, z_pos], marker='+', color='white', s=150)

        # Add ellipse showing body cross-section in x-y plane
        # Note: yt uses simulation coordinates, ellipse width/height in data units
        def add_ellipse_annotation(plot):
            ax = plot.axes
            # Draw ellipse at actual position (width=2*a in x, height=2*b in y)
            ellipse = Ellipse(
                xy=(x_pos, y_pos),
                width=2 * semi_a,
                height=2 * semi_b * 50,  # Scale up thickness for visibility
                fill=False, edgecolor='white', linewidth=2
            )
            ax.add_patch(ellipse)

        add_ellipse_annotation(slc.plots[field])

        # Descriptive filename
        output_name = f"ellipsoid_heaving_Re100_t{time:.0f}_{field}.png"
        output_path = output_dir / output_name
        slc.save(str(output_path))
        print(f"Saved: {output_path}")


def extract_forces(plotfile: str) -> dict:
    """Extract force components from plotfile particles."""
    import yt
    import numpy as np
    yt.set_log_level("error")

    ds = yt.load(plotfile)
    ad = ds.all_data()

    fx = float(np.array(ad['all', 'particle_real_comp3']).sum())
    fy = float(np.array(ad['all', 'particle_real_comp4']).sum())
    fz = float(np.array(ad['all', 'particle_real_comp5']).sum())

    return {
        "time": float(ds.current_time),
        "fx": fx,
        "fy": fy,
        "fz": fz,
    }


def visualize_forces(plotfiles: list[str], output_dir: Path | None = None):
    """Generate force time series plot."""
    import matplotlib.pyplot as plt
    import numpy as np

    output_dir = output_dir or Path(".")

    # Extract forces from all plotfiles
    data = []
    for pf in sorted(plotfiles):
        print(f"Processing: {pf}")
        data.append(extract_forces(pf))

    times = np.array([d["time"] for d in data])
    fx = np.array([d["fx"] for d in data])
    fy = np.array([d["fy"] for d in data])

    # Force on body = -force on fluid
    F_drag = -fx
    F_lift = -fy

    # Plot
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True)

    ax1.plot(times, F_drag, 'b-o', linewidth=2, markersize=6, label='Drag (Fx)')
    ax1.set_ylabel('Drag Force (dimensionless)', fontsize=12)
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(times, F_lift, 'r-s', linewidth=2, markersize=6, label='Lift (Fy)')
    ax2.set_xlabel('Time (dimensionless)', fontsize=12)
    ax2.set_ylabel('Lift Force (dimensionless)', fontsize=12)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    # Informative title with simulation parameters
    fig.suptitle(
        'Heaving Ellipsoid Force History\n'
        'Re=100 | V_heave=0.5 | Semi-axes: 0.5×0.02×1.5',
        fontsize=12, fontweight='bold'
    )
    plt.tight_layout()

    # Descriptive filename
    output_path = output_dir / 'ellipsoid_heaving_Re100_force_history.png'
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.savefig(output_dir / 'ellipsoid_heaving_Re100_force_history.pdf', bbox_inches='tight')
    plt.close()
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Visualize Heaving Ellipsoid output")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # velocity subcommand
    vel_parser = subparsers.add_parser("velocity", help="Generate velocity slices")
    vel_parser.add_argument("plotfile", help="Path to plotfile")
    vel_parser.add_argument("--output-dir", type=Path, help="Output directory")

    # forces subcommand
    force_parser = subparsers.add_parser("forces", help="Generate force time series")
    force_parser.add_argument("plotfiles", nargs="+", help="Paths to plotfiles")
    force_parser.add_argument("--output-dir", type=Path, help="Output directory")

    args = parser.parse_args()

    if args.command == "velocity":
        visualize_velocity(args.plotfile, args.output_dir)
    elif args.command == "forces":
        visualize_forces(args.plotfiles, args.output_dir)


if __name__ == "__main__":
    main()