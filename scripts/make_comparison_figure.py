r"""Generate the coarse-vs-fine holdout force-comparison figure (add-visualization-tooling).

Thin driver over
:func:`mosquito_cfd.force_surrogate.comparison_figure.build_coarse_vs_fine_comparison` (all logic
lives in the tested library).

Run from the repository root, e.g.::

    uv run python scripts/make_comparison_figure.py \\
        --coarse-predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \\
        --fine-predictions examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet \\
        --out-dir docs/visualization \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-08-12T00:00:00+00:00
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.comparison_figure import (
    DEFAULT_COEFFICIENT,
    build_coarse_vs_fine_comparison,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Render the coarse-vs-fine holdout force-comparison figure.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Render the coarse-vs-fine holdout force-comparison figure."
    )
    parser.add_argument("--coarse-predictions", type=Path, required=True)
    parser.add_argument("--fine-predictions", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned sha256: image digest (mutable tags rejected).",
    )
    parser.add_argument(
        "--timestamp",
        required=True,
        help="Caller-supplied ISO-8601 timestamp (reproducible provenance).",
    )
    parser.add_argument(
        "--coefficient",
        default=DEFAULT_COEFFICIENT,
        help=f"Force-coefficient column prefix to plot. Default: {DEFAULT_COEFFICIENT}.",
    )
    args = parser.parse_args(argv)

    build_coarse_vs_fine_comparison(
        coarse_predictions_path=args.coarse_predictions,
        fine_predictions_path=args.fine_predictions,
        out_dir=args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        coefficient=args.coefficient,
    )
    print(f"Rendered coarse-vs-fine comparison figure -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
