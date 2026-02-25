#!/usr/bin/env python3
"""Generate all figures for APEX proposal benchmarks.

This script coordinates figure generation from raw simulation data.
Individual visualize.py scripts in each example directory do the actual work.

Data Paths (set via environment or arguments):
    SPHERE_DATA: Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k/
    ELLIPSOID_DATA: Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/

Usage:
    # Generate all figures
    uv run python benchmarks/results/figures/generate_figures.py --all \
        --sphere-data Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k \
        --ellipsoid-data Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid

    # Generate only velocity plots
    uv run python benchmarks/results/figures/generate_figures.py --velocity \
        --sphere-data Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k

    # Generate only force plots
    uv run python benchmarks/results/figures/generate_figures.py --forces \
        --ellipsoid-data Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def find_plotfiles(data_dir: Path, pattern: str = "plt*") -> list[Path]:
    """Find all plotfiles matching pattern in data directory."""
    plotfiles = sorted(data_dir.glob(pattern))
    # Filter out non-directories (plotfiles are directories)
    return [p for p in plotfiles if p.is_dir()]


def generate_sphere_velocity(data_dir: Path, output_dir: Path) -> list[dict]:
    """Generate FlowPastSphere velocity visualizations. Returns metadata."""
    # Use the final steady-state plotfile
    plotfile = data_dir / "plt10000"
    if not plotfile.exists():
        print(f"Warning: {plotfile} not found, trying plt00100...")
        plotfile = data_dir / "plt00100"

    if not plotfile.exists():
        print(f"Error: No plotfile found in {data_dir}")
        return []

    script = Path(__file__).parent.parent.parent.parent / "examples" / "flow_past_sphere" / "visualize.py"
    generated = []

    for field in ["x_velocity", "y_velocity", "z_velocity"]:
        cmd = [
            sys.executable, str(script),
            str(plotfile),
            "--field", field,
            "--output-dir", str(output_dir)
        ]
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        # Track metadata (script generates descriptive names now)
        generated.append({
            "case": "flow_past_sphere",
            "field": field,
            "source_plotfile": plotfile.name,
            "description": f"Streamwise velocity slice at steady state (Re=100)",
            "reynolds": 100,
            "grid": "256x128x128"
        })

    return generated


def generate_ellipsoid_forces(data_dir: Path, output_dir: Path) -> list[dict]:
    """Generate heaving ellipsoid force time series."""
    plotfiles = find_plotfiles(data_dir, "plt_1k*")
    if not plotfiles:
        plotfiles = find_plotfiles(data_dir, "plt*")

    if not plotfiles:
        print(f"Error: No plotfiles found in {data_dir}")
        return []

    script = Path(__file__).parent.parent.parent.parent / "examples" / "heaving_ellipsoid" / "visualize.py"

    cmd = [
        sys.executable, str(script),
        "forces",
        *[str(p) for p in plotfiles],
        "--output-dir", str(output_dir)
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    return [{
        "case": "heaving_ellipsoid",
        "filename": "ellipsoid_heaving_Re100_force_history.png",
        "description": "Force time history for heaving thin ellipsoid",
        "reynolds": 100,
        "heave_velocity": 0.5,
        "semi_axes": "0.5x0.02x1.5",
        "grid": "256x128x128",
        "time_range": "0-10",
        "source_plotfiles": [p.name for p in plotfiles]
    }]


def generate_ellipsoid_velocity(data_dir: Path, output_dir: Path) -> list[dict]:
    """Generate heaving ellipsoid velocity visualizations.

    Uses t=5 (plt_1k00500) by default - wake is developed but body hasn't
    reached the periodic boundary yet. At t=10, the body is at the boundary
    and wake wraps around, creating confusing visualization.

    Timeline (heave velocity = 0.5, domain y = 0-10):
      t=5:  body at y=7.5, 2.5 units from boundary, wake developed
      t=10: body at y=10, AT boundary, wake wraps around
    """
    # Prefer t=5 (plt_1k00500) - good balance of wake development vs boundary distance
    preferred = ["plt_1k00500", "plt_1k00400", "plt_1k00300"]
    plotfile = None

    for candidate in preferred:
        candidate_path = data_dir / candidate
        if candidate_path.exists():
            plotfile = candidate_path
            break

    if plotfile is None:
        # Fall back to any available plotfile
        plotfiles = find_plotfiles(data_dir, "plt_1k*")
        if not plotfiles:
            plotfiles = find_plotfiles(data_dir, "plt*")
        if plotfiles:
            plotfile = plotfiles[-1]
            print(f"Warning: preferred timesteps not found, using {plotfile.name}")
        else:
            print(f"Error: No plotfiles found in {data_dir}")
            return []

    print(f"Using plotfile: {plotfile.name} (t=5 preferred to avoid periodic boundary artifacts)")

    script = Path(__file__).parent.parent.parent.parent / "examples" / "heaving_ellipsoid" / "visualize.py"

    cmd = [
        sys.executable, str(script),
        "velocity",
        str(plotfile),
        "--output-dir", str(output_dir)
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)

    return [{
        "case": "heaving_ellipsoid",
        "fields": ["x_velocity", "y_velocity", "z_velocity"],
        "source_plotfile": plotfile.name,
        "description": "Velocity field of heaving thin ellipsoid (wing approximation)",
        "reynolds": 100,
        "heave_velocity": 0.5,
        "semi_axes": "0.5x0.02x1.5",
        "grid": "256x128x128",
        "note": "t=5 used: wake developed, body still 2.5 units from periodic boundary"
    }]


def main():
    parser = argparse.ArgumentParser(
        description="Generate APEX proposal figures",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--all", action="store_true", help="Generate all figures")
    parser.add_argument("--velocity", action="store_true", help="Generate velocity visualizations")
    parser.add_argument("--forces", action="store_true", help="Generate force time series")

    parser.add_argument(
        "--sphere-data",
        type=Path,
        default=os.environ.get("SPHERE_DATA"),
        help="Path to FlowPastSphere data directory"
    )
    parser.add_argument(
        "--ellipsoid-data",
        type=Path,
        default=os.environ.get("ELLIPSOID_DATA"),
        help="Path to heaving ellipsoid data directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory for figures"
    )

    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Collect metadata from all generated figures
    manifest = {
        "generated": datetime.now().isoformat(),
        "generator": "generate_figures.py",
        "figures": []
    }

    if args.all or args.velocity:
        if args.sphere_data:
            print("\n=== FlowPastSphere Velocity ===")
            manifest["figures"].extend(generate_sphere_velocity(args.sphere_data, args.output_dir))
        else:
            print("Skipping sphere velocity: --sphere-data not provided")

        if args.ellipsoid_data:
            print("\n=== Heaving Ellipsoid Velocity ===")
            manifest["figures"].extend(generate_ellipsoid_velocity(args.ellipsoid_data, args.output_dir))
        else:
            print("Skipping ellipsoid velocity: --ellipsoid-data not provided")

    if args.all or args.forces:
        if args.ellipsoid_data:
            print("\n=== Heaving Ellipsoid Forces ===")
            manifest["figures"].extend(generate_ellipsoid_forces(args.ellipsoid_data, args.output_dir))
        else:
            print("Skipping ellipsoid forces: --ellipsoid-data not provided")

    # Write manifest with figure metadata
    if manifest["figures"]:
        manifest_path = args.output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        print(f"\nManifest written to: {manifest_path}")

    print(f"Figures saved to: {args.output_dir}")


if __name__ == "__main__":
    main()