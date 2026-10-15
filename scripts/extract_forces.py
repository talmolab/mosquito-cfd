r"""Extract the tidy force-coefficient dataset from a sweep's IB-particle CSVs.

Thin driver over :mod:`mosquito_cfd.force_surrogate.dataset` (all logic lives in the tested
library). It resolves each config's IB-particle CSV from a configurable ``--input-dir`` +
filename template (default ``<input-dir>/<config name>/IB_Particle_1.csv`` — IAMReX's actual
per-run output name), builds the dataset, and writes the parquet, the ``dataset.units.json``
sidecar, and a ``run_metadata.json`` provenance file (including the moment reference point and
the sha256 of every consumed CSV). Force-only (CC-6): the inputs are the IB-particle CSVs plus
each config's deck (named by the manifest's ``input_file``, read for its declared hinge); no
plotfiles.

Each deck is reconciled against the ``deck_sha256`` its CFD run recorded. By default that is
``run_metadata_<name>.json`` beside the manifest (the fine corpus's committed per-config files);
``--run-metadata-name run_metadata.json`` instead reads ``<input-dir>/<name>/run_metadata.json``,
the file each run wrote beside its CSV. Giving the flag makes verification mandatory: every
extracted config must be anchored, or nothing is written.

Outputs are written in full to temporaries beside their targets, and nothing is moved into place
until every write succeeded, so a failure while writing changes nothing. Three renames cannot be
atomic: the units sidecar and provenance are moved first and the dataset parquet **last**, so a
failure while moving never leaves a new parquet beside stale provenance. It is reported with the
outputs already replaced named and the temporaries not yet moved kept.

Run from the repository root, e.g.::

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
import os
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import (
    build_dataset,
    build_run_metadata,
    load_manifest_configs,
    moment_reference_provenance,
    write_dataset,
)


def _temporary(target: Path) -> Path:
    """A temporary beside ``target`` (same directory, so the final move is a rename)."""
    return target.with_name(f".{target.name}.tmp")


def _remove_quietly(path: Path) -> None:
    """Best-effort cleanup that never masks the error being handled."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _check_run_metadata_name(name: str) -> None:
    """``--run-metadata-name`` must be a bare file name inside each run directory."""
    if (
        name in ("", ".", "..")
        or Path(name).name != name
        or "/" in name
        or "\\" in name
    ):
        raise ValueError(
            f"--run-metadata-name must be a bare file name inside each run directory "
            f"(<input-dir>/<config>/<name>), got {name!r}"
        )


def _check_outputs(outputs: Sequence[Path]) -> None:
    """Reject directory targets and duplicate paths before anything is written.

    Either would otherwise surface only while moving outputs into place, after an earlier
    output had replaced its predecessor (a duplicate silently loses one output).
    """
    directories = [str(p) for p in outputs if p.is_dir()]
    if directories:
        raise ValueError(f"output path(s) {directories} are directories, not files")
    if len({p.resolve() for p in outputs}) != len(outputs):
        raise ValueError(
            f"--out, --units and --metadata must not share the same path: "
            f"{[str(p) for p in outputs]}"
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
    parser.add_argument(
        "--run-metadata-name",
        default=None,
        help=(
            "Reconcile each deck against <input-dir>/<name>/<this file>'s deck_sha256 (the "
            "metadata each CFD run wrote beside its CSV), and require every extracted "
            "config to be anchored. Default: run_metadata_<name>.json beside the manifest, "
            "where present."
        ),
    )
    args = parser.parse_args(argv)
    # Order matters: the parquet is moved into place last (see the module docstring).
    outputs = (args.units, args.metadata, args.out)
    _check_outputs(outputs)
    if args.run_metadata_name is not None:
        _check_run_metadata_name(args.run_metadata_name)

    # Validated read (clear ValueError on a malformed manifest, not a bare KeyError) so the
    # CLI path benefits from the same guards as build_dataset.
    configs = load_manifest_configs(args.manifest)
    csv_paths = {
        config["name"]: args.input_dir / config["name"] / args.csv_name
        for config in configs
    }

    run_metadata_paths = (
        None
        if args.run_metadata_name is None
        else {
            config["name"]: args.input_dir / config["name"] / args.run_metadata_name
            for config in configs
        }
    )
    df, dropped, provenance = build_dataset(
        args.manifest,
        csv_paths,
        allow_missing=args.allow_missing,
        run_metadata_paths=run_metadata_paths,
    )
    if run_metadata_paths is not None:
        # The flag is an explicit opt-in to verification, so it fails closed: a missing
        # file, a file without deck_sha256, or a misspelled name is an error, not a silent
        # "unverified". Configs dropped under --allow-missing consumed nothing.
        unanchored = sorted(
            name
            for name, record in provenance.items()
            if record["deck_sha256_verified_against"] is None
        )
        if unanchored:
            raise ValueError(
                f"config(s) {unanchored} are not anchored: no deck_sha256 found in "
                f"<input-dir>/<config>/{args.run_metadata_name} (--run-metadata-name "
                "makes verification mandatory)"
            )
    # The moment frame and the consumed inputs come from what build_dataset applied and
    # read, not re-derived here, so the record cannot drift from the parquet. Captured
    # BEFORE writing anything, so the git state describes the tree extraction ran from
    # rather than one its own output already dirtied.
    metadata = build_run_metadata(
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        dropped_configs=dropped,
        inputs_file=args.manifest,
        extra=moment_reference_provenance(
            provenance, input_dir=args.input_dir, csv_name=args.csv_name
        ),
    )
    # Write every output in full to a temporary first: a failure here changes nothing.
    temporaries = {target: _temporary(target) for target in outputs}
    try:
        write_dataset(df, temporaries[args.out], temporaries[args.units])
        args.metadata.parent.mkdir(parents=True, exist_ok=True)
        with open(
            temporaries[args.metadata], "w", encoding="utf-8", newline=""
        ) as handle:
            json.dump(metadata, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except BaseException:
        for temporary in temporaries.values():
            _remove_quietly(temporary)
        raise
    # Then move them into place, parquet last. Three renames cannot be atomic; a failure
    # here is reported with what was already replaced, and the rest are kept as-is.
    replaced: list[Path] = []
    for target, temporary in temporaries.items():
        try:
            os.replace(temporary, target)
        except OSError as exc:
            pending = ", ".join(
                str(t) for t in list(temporaries.values())[len(replaced) :]
            )
            done = ", ".join(str(p) for p in replaced) or "none"
            raise RuntimeError(
                f"moving outputs into place failed at {target}: {exc}. Outputs already "
                f"replaced: {done}. The dataset parquet is moved last, so it is "
                f"unchanged. Temporaries not yet moved (kept): {pending}"
            ) from exc
        replaced.append(target)

    print(
        f"Wrote {len(df)} rows to {args.out.as_posix()} (dropped={dropped or 'none'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
