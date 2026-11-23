r"""Render one coarse-vs-fine force-surrogate figure (OpenSpec change add-real-comparison-figures).

Thin driver over :mod:`mosquito_cfd.force_surrogate.comparison_figure`; all logic and every
input guard live in the tested library. Run from the repository root (``root`` is the current
directory, and every recorded input path is relative to it).

Arguments (all required):

- ``--figure``: ``skill_ranges``, ``error_histograms`` or ``cycle_mean_r2_diagnostic``;
- ``--coarse-dir`` / ``--fine-dir``: the corpus directories, each holding ``dataset.parquet`` and
  ``surrogate/{holdout_predictions.parquet,metrics.json,run_metadata.json}``;
- ``--out-dir``: where ``<figure>.png``, ``_metrics.json`` and ``_run_metadata.json`` are written
  (render into a scratch directory outside the repository, then copy the files in, so the recorded
  ``git.dirty`` stays false);
- ``--docker-digest``: a pinned image digest, ``<repo>@sha256:<64hex>`` (by convention the fine
  corpus's CFD digest, ``examples/prelim_sweep_fine/run_metadata.json``);
- ``--timestamp``: a caller-supplied ISO-8601 timestamp.

The regeneration recipe for the committed figures is in ``examples/prelim_sweep_fine/README.md``
("Comparison figures").
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.comparison_figure import (
    FIGURES,
    build_cycle_mean_r2_diagnostic,
    build_error_histograms,
    build_skill_ranges,
)

BUILDERS = {
    "skill_ranges": build_skill_ranges,
    "error_histograms": build_error_histograms,
    "cycle_mean_r2_diagnostic": build_cycle_mean_r2_diagnostic,
}


def main(argv: Sequence[str] | None = None) -> int:
    """Render the named figure.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Render one coarse-vs-fine force-surrogate figure."
    )
    parser.add_argument("--figure", required=True, choices=FIGURES)
    parser.add_argument("--coarse-dir", required=True, type=Path)
    parser.add_argument("--fine-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned image digest, <repo>@sha256:<64hex> (mutable tags rejected).",
    )
    parser.add_argument(
        "--timestamp",
        required=True,
        help="Caller-supplied ISO-8601 timestamp (reproducible provenance).",
    )
    args = parser.parse_args(argv)
    BUILDERS[args.figure](
        root=Path.cwd(),
        coarse_dir=args.coarse_dir,
        fine_dir=args.fine_dir,
        out_dir=args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
    )
    print(f"Rendered {args.figure} -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
