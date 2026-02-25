#!/usr/bin/env python3
"""Visualize FlowPastSphere simulation output using yt."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Visualize FlowPastSphere output")
    parser.add_argument("plotfile", help="Path to plot file (e.g., plt00100)")
    parser.add_argument("--field", default="x_velocity", help="Field to plot")
    parser.add_argument("--axis", default="z", choices=["x", "y", "z"], help="Slice axis")
    parser.add_argument("--output", help="Output image path")
    parser.add_argument("--output-dir", type=Path, help="Output directory")
    args = parser.parse_args()

    import yt

    # Load the dataset
    ds = yt.load(args.plotfile)
    time = float(ds.current_time)
    print(f"Loaded: {args.plotfile}")
    print(f"  Time: {time}")
    print(f"  Domain: {ds.domain_left_edge} to {ds.domain_right_edge}")

    # Create slice plot
    slc = yt.SlicePlot(ds, args.axis, args.field)
    slc.set_log(args.field, False)  # Linear scale for velocity

    # Add informative title
    field_label = args.field.replace('_', ' ').title()
    state = "Steady State" if time >= 50 else f"t={time:.0f}"
    slc.annotate_title(f"Flow Past Sphere Re=100 | {state} | {field_label}")

    # Add sphere outline
    slc.annotate_sphere([5.0, 5.0, 5.0], radius=(0.5, "code_length"), circle_args={"color": "white"})

    # Descriptive filename
    if args.output:
        output = args.output
    else:
        state_str = "steady" if time >= 50 else f"t{time:.0f}"
        output_name = f"sphere_Re100_{state_str}_{args.field}.png"
        output_dir = args.output_dir or Path(".")
        output = str(output_dir / output_name)

    slc.save(output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()