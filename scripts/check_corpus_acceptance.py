r"""Run the post-run acceptance gate against a corpus before its dataset.parquet is built.

Thin driver over :func:`mosquito_cfd.force_surrogate.acceptance_gate.run_acceptance_gate` (all
logic lives in the tested library). Run after ``generate_run_metadata.py`` and **before**
``extract_forces.py`` for every config in the corpus -- a truncated (#92) or duplicated-row (#94)
run must never reach a committed ``dataset.parquet``.

Exit code 0 and no output beyond the pass message on success; a nonzero exit and every failure
message, one per line, on failure.

Run from the repository root, e.g.::

    uv run python scripts/check_corpus_acceptance.py \\
        --manifest examples/prelim_sweep_fine/sweep_manifest.json \\
        --provenance examples/prelim_sweep_fine/sweep_provenance.json \\
        --csv-dir /workspace/runs \\
        --csv-name IB_Particle_1.csv \\
        --metadata-dir examples/prelim_sweep_fine
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.acceptance_gate import run_acceptance_gate
from mosquito_cfd.force_surrogate.dataset import load_manifest_configs


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI's argument parser (exposed separately from :func:`main` for testing)."""
    parser = argparse.ArgumentParser(
        description="Gate a corpus against truncation/duplication before its dataset is built."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument(
        "--csv-dir",
        type=Path,
        required=True,
        help="Directory containing <csv-dir>/<config>/<csv-name> per config.",
    )
    parser.add_argument("--csv-name", default="IB_Particle_1.csv")
    parser.add_argument(
        "--metadata-dir",
        type=Path,
        required=True,
        help="Directory containing run_metadata_<config>.json per config.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the acceptance gate and print its verdict.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        0 if the gate passes; 1 if it fails (every failure message printed, one per line).
    """
    args = build_parser().parse_args(argv)

    configs = load_manifest_configs(args.manifest)
    csv_paths = {c["name"]: args.csv_dir / c["name"] / args.csv_name for c in configs}
    run_metadata_paths = {
        c["name"]: args.metadata_dir / f"run_metadata_{c['name']}.json" for c in configs
    }

    result = run_acceptance_gate(
        manifest_path=args.manifest,
        csv_paths=csv_paths,
        run_metadata_paths=run_metadata_paths,
        provenance_path=args.provenance,
    )
    if result.passed:
        print(f"OK: acceptance gate passed for all {len(configs)} configs.")
        return 0
    print(f"FAILED: acceptance gate found {len(result.failures)} issue(s):")
    for failure in result.failures:
        print(f"  - {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
