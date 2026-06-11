r"""Extract the tidy force-coefficient dataset from a sweep's IB-particle CSVs.

Thin driver over :mod:`mosquito_cfd.force_surrogate.dataset` (all logic lives in the tested
library). It resolves each config's IB-particle CSV from a configurable ``--input-dir`` +
filename template (default ``<input-dir>/<config name>/IB_Particle_1.csv`` — IAMReX's actual
per-run output name), builds the dataset, and writes the parquet, the ``dataset.units.json``
sidecar, and a ``run_metadata.json`` provenance file. Force-only (CC-6): the IB-particle CSV
is the only input; no plotfiles.

Run from the repository root once PR3's real corpus exists, e.g.::

    uv run python scripts/extract_forces.py \\
        --manifest examples/prelim_sweep/sweep_manifest.json \\
        --input-dir <runs-dir> \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-06-30T00:00:00+00:00 \\
        --out examples/prelim_sweep/dataset.parquet \\
        --units examples/prelim_sweep/dataset.units.json \\
        --metadata examples/prelim_sweep/run_metadata.json
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import (
    build_dataset,
    build_run_metadata,
    load_manifest_configs,
    write_dataset,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Build the dataset and write parquet + units sidecar + run metadata.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Extract the force-coefficient dataset from IB-particle CSVs."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--input-dir",
        type=Path,
        required=True,
        help="Directory holding per-config run output (<input-dir>/<name>/<csv-name>).",
    )
    parser.add_argument("--csv-name", default="IB_Particle_1.csv")
    parser.add_argument("--out", type=Path, required=True, help="Output parquet path.")
    parser.add_argument(
        "--units", type=Path, required=True, help="Output dataset.units.json path."
    )
    parser.add_argument(
        "--metadata", type=Path, required=True, help="Output run_metadata.json path."
    )
    parser.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned sha256 container digest of the CFD run image.",
    )
    parser.add_argument(
        "--timestamp", required=True, help="Caller-supplied ISO-8601 timestamp."
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip configs with no IB-particle CSV (recorded in run metadata).",
    )
    args = parser.parse_args(argv)

    # Validated read (clear ValueError on a malformed manifest, not a bare KeyError) so the
    # CLI path benefits from the same guards as build_dataset.
    configs = load_manifest_configs(args.manifest)
    csv_paths = {
        config["name"]: args.input_dir / config["name"] / args.csv_name
        for config in configs
    }

    df, dropped = build_dataset(
        args.manifest, csv_paths, allow_missing=args.allow_missing
    )
    write_dataset(df, args.out, args.units)

    metadata = build_run_metadata(
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        dropped_configs=dropped,
        inputs_file=args.manifest,
    )
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    with open(args.metadata, "w", encoding="utf-8", newline="") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print(
        f"Wrote {len(df)} rows to {args.out.as_posix()} (dropped={dropped or 'none'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
