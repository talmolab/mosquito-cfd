r"""Print the median CFD wall-clock seconds per timestep for a corpus's run metadata.

Thin driver over :func:`mosquito_cfd.force_surrogate.cfd_cost.median_cfd_seconds_per_step`.
Reads only the per-configuration ``run_metadata_<config>.json`` files in ``--metadata-dir`` (the
corpus-level ``run_metadata.json`` does not match the pattern) and prints the median on stdout as
``repr(float)``, which ``float()`` reads back exactly, so it can be passed straight to
``make_evidence_figure.py --cfd-seconds-per-step``. A one-line summary goes to stderr.

Run from the repository root, e.g.::

    uv run --frozen python scripts/cfd_seconds_per_step.py \\
        --metadata-dir examples/prelim_sweep_fine
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.cfd_cost import median_cfd_seconds_per_step


def main(argv: Sequence[str] | None = None) -> int:
    """Print the median per-step CFD seconds for ``--metadata-dir``.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Median CFD wall-clock seconds per timestep from run metadata."
    )
    parser.add_argument("--metadata-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    paths = sorted(args.metadata_dir.glob("run_metadata_*.json"))
    result = median_cfd_seconds_per_step(paths)
    print(
        f"median of {result['n_configs']} configs on {result['gpu_model']} "
        f"(range {result['min']:.3f}-{result['max']:.3f} s/step)",
        file=sys.stderr,
    )
    print(repr(result["seconds_per_step"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
