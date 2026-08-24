r"""Generate a normalized ``run_metadata_<config>.json`` from existing run artifacts.

Thin argparse wrapper over :mod:`mosquito_cfd.force_surrogate.metadata_capture` (all logic lives
in the tested library — see that module's docstring for the full schema and field provenance).
Nothing is hand-typed: every field is read from the pod's own already-produced
``run_metadata.json``, the committed force CSV, ``run.log``, the sweep manifest, and the deck, or
computed from a completed Argo workflow's status.

**Operator-run only — never invoke this from CI.** CI's runner has no ``argo``/cluster access,
matching every other cluster-facing script in this repo.

Must be run before the source Argo workflow is garbage-collected (no ``ttlStrategy`` is
configured on this repo's templates today, so this is a plausible-but-unconfirmed risk, not an
observed failure), or with ``--wall-time-s`` supplied manually if that window has passed.

The full 27-config fine-grid corpus follow-on should use this tool for all ~27 new metadata
files rather than hand-authoring them (the exact pattern that produced PR #58's
``final_time``/truncated-SHA bugs in all 3 pilot files).

Run from the repository root, e.g.::

    uv run python scripts/generate_run_metadata.py \\
        --pod-metadata runs/s01_f100_p45/run_metadata.json \\
        --csv runs/s01_f100_p45/IB_Particle_1.csv \\
        --run-log runs/s01_f100_p45/run.log \\
        --manifest examples/prelim_sweep_fine/sweep_manifest.json \\
        --deck examples/prelim_sweep_fine/inputs/inputs.3d.s01_f100_p45 \\
        --config-name s01_f100_p45 \\
        --tier fine-grid-corpus-full \\
        --workflow-name force-surrogate-full-abc12 \\
        --output examples/prelim_sweep_fine/run_metadata_s01_f100_p45.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import metadata_capture


def main(argv: Sequence[str] | None = None) -> int:
    """Assemble and write one config's normalized ``run_metadata_<config>.json``.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (always ``0`` on success; argparse exits non-zero on bad args).
    """
    parser = argparse.ArgumentParser(
        description="Generate a normalized run_metadata_<config>.json from existing artifacts."
    )
    parser.add_argument("--pod-metadata", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--config-name", required=True)
    parser.add_argument(
        "--tier",
        required=True,
        help="Label for which corpus/tier produced this run (e.g. fine-grid-corpus-full).",
    )
    parser.add_argument(
        "--workflow-name",
        default=None,
        help="Argo workflow name, for the wall-time status query and orchestration.workflow_name.",
    )
    parser.add_argument(
        "--wall-time-s",
        type=float,
        default=None,
        help=(
            "Manual wall_time_s override, bypassing the Argo query entirely "
            "(use if the source workflow has already been garbage-collected)."
        ),
    )
    parser.add_argument("--notes", default=None, help="Optional free-text commentary.")
    parser.add_argument(
        "--git-commit",
        default=None,
        help=(
            "Manual git.commit override (a full 40-character SHA), bypassing the pod's own "
            "git block entirely (use if the pod image has no .git directory at all, e.g. "
            "issue #66, and predates the baked MOSQUITO_CFD_COMMIT build-arg fallback)."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    metadata = metadata_capture.assemble_run_metadata(
        pod_metadata_path=args.pod_metadata,
        csv_path=args.csv,
        run_log_path=args.run_log,
        manifest_path=args.manifest,
        deck_path=args.deck,
        config_name=args.config_name,
        tier=args.tier,
        workflow_name=args.workflow_name,
        wall_time_s=args.wall_time_s,
        argo_status_query=metadata_capture.query_argo_workflow_status,
        notes=args.notes,
        git_commit=args.git_commit,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(f"Wrote {args.output.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
