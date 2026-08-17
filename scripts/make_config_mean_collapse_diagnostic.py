r"""Generate the config-mean-collapse diagnostic figure (add-visualization-tooling).

Thin driver over
:func:`mosquito_cfd.force_surrogate.comparison_figure.build_config_mean_collapse_diagnostic` (all
logic lives in the tested library). Internal diagnostic confirming whether the *true* per-config
average force has collapsed toward a single point on the fine grid, even though the model's
moment-by-moment waveform fit stays visually accurate.

Run from the repository root, e.g.::

    uv run python scripts/make_config_mean_collapse_diagnostic.py \\
        --coarse-predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \\
        --fine-predictions examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet \\
        --coarse-metrics examples/prelim_sweep/surrogate/metrics.json \\
        --fine-metrics examples/prelim_sweep_fine/surrogate/metrics.json \\
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
    build_config_mean_collapse_diagnostic,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Render the config-mean-collapse diagnostic figure.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Render the config-mean-collapse diagnostic figure."
    )
    parser.add_argument("--coarse-predictions", type=Path, required=True)
    parser.add_argument("--fine-predictions", type=Path, required=True)
    parser.add_argument("--coarse-metrics", type=Path, required=True)
    parser.add_argument("--fine-metrics", type=Path, required=True)
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
        help=f"Force-coefficient column prefix. Default: {DEFAULT_COEFFICIENT}.",
    )
    args = parser.parse_args(argv)

    build_config_mean_collapse_diagnostic(
        coarse_predictions_path=args.coarse_predictions,
        fine_predictions_path=args.fine_predictions,
        coarse_metrics_path=args.coarse_metrics,
        fine_metrics_path=args.fine_metrics,
        out_dir=args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        coefficient=args.coefficient,
    )
    print(f"Rendered config-mean-collapse diagnostic -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
