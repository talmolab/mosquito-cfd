r"""Generate the predicted-vs-CFD force-surrogate evidence figure (Track B PR6).

Thin driver over :mod:`mosquito_cfd.force_surrogate.evidence_figure` (all logic lives in the
tested library). Reads the committed PR5 artifacts (``holdout_predictions.parquet`` +
``metrics.json``) and writes ``evidence_figure.png`` (>=200 dpi), an
``evidence_figure_metrics.json`` sidecar, and a ``run_metadata.json`` provenance file.
Force-only (CC-6): no plotfiles, no cluster, no GPU.

Run from the repository root, e.g.::

    uv run python scripts/make_evidence_figure.py \\
        --predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \\
        --metrics examples/prelim_sweep/surrogate/metrics.json \\
        --out-dir examples/prelim_sweep/figures \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-06-23T00:00:00+00:00
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import generate_evidence_figure


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the evidence figure + sidecar + provenance.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Generate the predicted-vs-CFD force-surrogate evidence figure."
    )
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--metrics", type=Path, required=True)
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
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--dpi", type=int, default=200)
    args = parser.parse_args(argv)

    generate_evidence_figure(
        predictions_path=args.predictions,
        metrics_path=args.metrics,
        out_dir=args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        seeds={"global": args.seed},
        dpi=args.dpi,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
