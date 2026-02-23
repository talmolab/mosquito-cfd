#!/usr/bin/env python3
"""Visualize FlowPastSphere simulation output using yt."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Visualize FlowPastSphere output")
    parser.add_argument("plotfile", help="Path to plot file (e.g., plt00100)")
    parser.add_argument("--field", default="x_velocity", help="Field to plot")
    parser.add_argument("--axis", default="z", choices=["x", "y", "z"], help="Slice axis")
    parser.add_argument("--output", help="Output image path (default: <plotfile>_<field>.png)")
    args = parser.parse_args()

    import yt

    # Load the dataset
    ds = yt.load(args.plotfile)
    print(f"Loaded: {args.plotfile}")
    print(f"  Time: {ds.current_time}")
    print(f"  Domain: {ds.domain_left_edge} to {ds.domain_right_edge}")

    # Create slice plot
    slc = yt.SlicePlot(ds, args.axis, args.field)
    slc.set_log(args.field, False)  # Linear scale for velocity

    # Add sphere outline (approximate)
    slc.annotate_sphere([5.0, 5.0, 5.0], radius=(0.5, "code_length"), circle_args={"color": "white"})

    # Save
    output = args.output or f"{Path(args.plotfile).name}_{args.field}.png"
    slc.save(output)
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()