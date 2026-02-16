#!/usr/bin/env python3
"""
Generate Lagrangian markers for a mosquito wing.

Based on van Veen et al. (2022) Aedes aegypti wing geometry.

Usage:
    uv run python -m mosquito_cfd.generate_wing_markers --spacing 0.05 --output wing_markers.dat
"""

import argparse

import numpy as np


def generate_flat_plate_markers(
    span_mm: float = 3.0,
    chord_mm: float = 1.0,
    spacing_mm: float = 0.05,
    center: tuple[float, float, float] = (0.025, 0.025, 0.025),
) -> np.ndarray:
    """
    Generate markers for a thin flat plate wing approximation.

    Args:
        span_mm: Wing span in mm
        chord_mm: Wing chord in mm
        spacing_mm: Marker spacing in mm
        center: Domain center (x, y, z) in meters

    Returns:
        numpy array of marker positions (N x 3) in meters
    """
    # Convert to meters
    span = span_mm * 1e-3
    chord = chord_mm * 1e-3
    spacing = spacing_mm * 1e-3

    cx, cy, cz = center

    n_span = int(span / spacing)
    n_chord = int(chord / spacing)

    markers = []
    for i in range(n_span):
        for j in range(n_chord):
            x = cx - chord / 2 + (j + 0.5) * spacing
            y = cy  # Wing in x-z plane
            z = cz - span / 2 + (i + 0.5) * spacing
            markers.append([x, y, z])

    return np.array(markers)


def write_markers(markers: np.ndarray, output_path: str) -> None:
    """Write markers to IAMReX format file."""
    with open(output_path, "w") as f:
        f.write(f"{len(markers)}\n")
        for m in markers:
            f.write(f"{m[0]:.8e} {m[1]:.8e} {m[2]:.8e}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate wing markers")
    parser.add_argument("--span", type=float, default=3.0, help="Wing span in mm")
    parser.add_argument("--chord", type=float, default=1.0, help="Wing chord in mm")
    parser.add_argument("--spacing", type=float, default=0.05, help="Marker spacing in mm")
    parser.add_argument("--output", "-o", default="wing_markers.dat", help="Output file")

    args = parser.parse_args()

    markers = generate_flat_plate_markers(
        span_mm=args.span,
        chord_mm=args.chord,
        spacing_mm=args.spacing,
    )

    write_markers(markers, args.output)

    n_span = int(args.span / args.spacing)
    n_chord = int(args.chord / args.spacing)

    print(f"Generated {len(markers)} markers ({n_span} x {n_chord})")
    print(f"Wing span: {args.span:.1f} mm, chord: {args.chord:.1f} mm")
    print(f"Marker spacing: {args.spacing:.3f} mm")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
