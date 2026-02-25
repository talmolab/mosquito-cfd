"""CLI for wing planform generation.

Usage:
    uv run generate-wing-planform --shape elliptic --span 3.0e-3 --chord 1.0e-3 \
        --spacing 50e-6 --output wing.vertex
"""

import argparse

from mosquito_cfd.geometry.parametric_planform import generate_planform
from mosquito_cfd.geometry.vertex_io import write_vertex_file


def main() -> None:
    """Generate wing planform markers and write to .vertex file."""
    parser = argparse.ArgumentParser(
        description="Generate Lagrangian markers for wing planforms",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--shape",
        type=str,
        choices=["rectangular", "elliptic"],
        default="elliptic",
        help="Planform shape",
    )
    parser.add_argument(
        "--span",
        type=float,
        default=3.0e-3,
        help="Wing span in meters",
    )
    parser.add_argument(
        "--chord",
        type=float,
        default=1.0e-3,
        help="Wing chord in meters (max chord for elliptic)",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=50e-6,
        help="Marker spacing in meters",
    )
    parser.add_argument(
        "--center",
        type=float,
        nargs=3,
        default=[0.0, 0.0, 0.0],
        metavar=("X", "Y", "Z"),
        help="Center position in meters",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default="wing.vertex",
        help="Output file path",
    )

    args = parser.parse_args()

    markers = generate_planform(
        shape=args.shape,
        span=args.span,
        chord=args.chord,
        spacing=args.spacing,
        center=tuple(args.center),
    )

    write_vertex_file(markers, args.output)

    print(f"Shape: {args.shape}")
    print(f"Span: {args.span * 1e3:.2f} mm, Chord: {args.chord * 1e3:.2f} mm")
    print(f"Spacing: {args.spacing * 1e6:.1f} µm")
    print(f"Generated {len(markers)} markers")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()