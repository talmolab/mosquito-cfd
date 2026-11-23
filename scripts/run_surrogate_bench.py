r"""Run the surrogate comparison bench (F3a) on the fine force corpus.

Thin driver over :func:`mosquito_cfd.surrogate_bench.runner.run_bench`. Every refusal (a dirty tree
without ``--allow-dirty``, a non-empty ``--out-dir``, an unknown or repeated entry, ``--epochs``
below 1, an unpinned image reference, a coarse corpus missing a configuration) exits non-zero
before anything is written. ``--allow-dirty`` is specific to this driver.

The MLP entries need the ``train`` group (Linux only; under WSL2 on the Windows A5000 host). A
ridge-only run, ``--entries ridge,ridge_fixed``, needs no torch::

    uv run --frozen --group viz python scripts/run_surrogate_bench.py \
        --dataset examples/prelim_sweep_fine/dataset.parquet \
        --coarse-dataset examples/prelim_sweep/dataset.parquet \
        --out-dir <scratch dir outside the repository> \
        --docker-digest <fine corpus digest> --timestamp <ISO-8601>
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

from mosquito_cfd.benchmarks.metadata import get_git_info, get_hardware_info
from mosquito_cfd.surrogate_bench.runner import ENTRIES, run_bench


def build_parser() -> argparse.ArgumentParser:
    """The argument parser (separate so it is unit-testable)."""
    p = argparse.ArgumentParser(description="Run the surrogate comparison bench (F3a).")
    p.add_argument("--dataset", required=True, help="Fine dataset.parquet.")
    p.add_argument("--coarse-dataset", required=True, help="Coarse dataset.parquet.")
    p.add_argument(
        "--out-dir", required=True, help="Output directory (absent or empty)."
    )
    p.add_argument(
        "--docker-digest",
        required=True,
        help="The fine corpus's pinned image reference (<repo>@sha256:<64 hex>).",
    )
    p.add_argument(
        "--timestamp", required=True, help="Caller-supplied ISO-8601 timestamp."
    )
    p.add_argument("--device", default="cpu", help="'cpu' or 'cuda'.")
    p.add_argument(
        "--entries",
        default=None,
        help=f"Comma-separated entries (default all: {','.join(ENTRIES)}).",
    )
    p.add_argument("--epochs", type=int, default=2000, help="MLP epochs (tests only).")
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Run on a dirty tree and record dirty: true.",
    )
    return p


def parse_entries(value: str | None) -> list[str]:
    """``None`` means every entry; otherwise the comma-separated names, in order."""
    if value is None:
        return list(ENTRIES)
    return [e.strip() for e in value.split(",") if e.strip()]


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the bench; returns a process exit code."""
    args = build_parser().parse_args(argv)
    git = get_git_info()
    if "dirty" not in git:
        git = {**git, "dirty": True}  # an unknown state is never treated as clean
    try:
        dataset = Path(args.dataset)
        data = dataset.read_bytes()
        frame = pd.read_parquet(dataset)
        coarse = pd.read_parquet(args.coarse_dataset)
        result = run_bench(
            frame=frame,
            coarse_frame=coarse,
            out_dir=args.out_dir,
            docker_image_digest=args.docker_digest,
            timestamp=args.timestamp,
            dataset_sha256=hashlib.sha256(data).hexdigest(),
            git_state=git,
            hardware=get_hardware_info(),
            device=args.device,
            entries=parse_entries(args.entries),
            epochs=args.epochs,
            allow_dirty=args.allow_dirty,
        )
    except ValueError as exc:
        print(f"run_surrogate_bench: {exc}", file=sys.stderr)
        return 2
    print(
        f"Wrote {', '.join(str(result[k]) for k in ('results', 'summary', 'figure'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
