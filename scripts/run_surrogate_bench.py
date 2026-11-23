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
import io
import sys
from pathlib import Path

import pandas as pd

from mosquito_cfd._json_loader import load_json_clear_error
from mosquito_cfd.benchmarks.metadata import get_git_info, get_hardware_info
from mosquito_cfd.force_surrogate.sidecar import validate_image_digest
from mosquito_cfd.force_surrogate.train import DEFAULT_EPOCHS
from mosquito_cfd.surrogate_bench.runner import ENTRIES, run_bench

REPO = Path(__file__).resolve().parents[1]


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
    p.add_argument(
        "--epochs", type=int, default=DEFAULT_EPOCHS, help="MLP epochs (tests only)."
    )
    p.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Run on a dirty tree and record dirty: true.",
    )
    return p


def parse_entries(value: str | None) -> list[str]:
    """``None`` means every entry; otherwise the comma-separated names, in order.

    Raises:
        ValueError: If any token is empty (``""``, ``",ridge"``, ``"a,,b"``).
    """
    if value is None:
        return list(ENTRIES)
    names = [e.strip() for e in value.split(",")]
    if not all(names):
        raise ValueError(f"--entries has an empty token: {value!r}")
    return names


def _read(path: Path) -> tuple[pd.DataFrame, str]:
    """The dataset and the sha256 of exactly the bytes that were parsed."""
    data = path.read_bytes()
    return pd.read_parquet(io.BytesIO(data)), hashlib.sha256(data).hexdigest()


def _shown(path: Path) -> str:
    """A path as recorded: relative to the repository when inside it, else absolute."""
    path = path.resolve()
    try:
        return path.relative_to(REPO).as_posix()
    except ValueError:
        return path.as_posix()


def _corpus_record(dataset: Path) -> tuple[Path, dict | None]:
    """The ``run_metadata.json`` beside a dataset, parsed, or ``None`` if there is none.

    Raises:
        ValueError: If the file exists but cannot be read as a JSON object (naming it).
    """
    meta = dataset.resolve().parent / "run_metadata.json"
    if not meta.exists():
        return meta, None
    # The project's labelled loader (#175): every content failure is a ValueError naming it.
    return meta, load_json_clear_error(meta, label="corpus run_metadata.json")


def input_provenance(
    dataset: Path, coarse: Path, docker_digest: str
) -> dict[str, object]:
    """Input provenance beyond the fine dataset's sha256.

    The fine corpus's record is binding: ``--docker-digest`` must equal the ``docker_image``
    it records. The coarse corpus's image is informational, so a missing or unreadable coarse
    record is noted, never fatal.

    Raises:
        ValueError: If the fine corpus's ``run_metadata.json`` cannot be read as a JSON object,
            or records a different image than ``--docker-digest``.
    """
    meta, record = _corpus_record(dataset)
    recorded = None if record is None else record.get("docker_image")
    if record is None:
        check = "no run_metadata.json beside the fine dataset"
    elif not isinstance(recorded, str):
        check = f"{_shown(meta)} records no docker_image"
    elif recorded != docker_digest:
        raise ValueError(
            f"--docker-digest {docker_digest} differs from the image the fine corpus records "
            f"in {_shown(meta)}: {recorded}"
        )
    else:
        check = f"matches {_shown(meta)}"

    coarse_meta = coarse.resolve().parent / "run_metadata.json"
    coarse_image = None
    if coarse_meta == meta:
        source = "the coarse dataset shares the fine dataset's run_metadata.json"
    else:
        try:
            _, coarse_record = _corpus_record(coarse)
        except (ValueError, OSError) as exc:  # informational: noted, never fatal
            coarse_record, source = None, str(exc)
        else:
            if coarse_record is None:
                source = "no run_metadata.json beside the coarse dataset"
            elif isinstance(coarse_record.get("docker_image"), str):
                coarse_image = coarse_record["docker_image"]
                source = _shown(coarse_meta)
            else:
                source = f"{_shown(coarse_meta)} records no docker_image"
    return {
        "dataset_file": _shown(dataset),
        "coarse_dataset_file": _shown(coarse),
        "docker_image_check": check,
        "coarse_docker_image": coarse_image,
        "coarse_docker_image_source": source,
    }


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the bench; returns a process exit code."""
    args = build_parser().parse_args(argv)
    git = get_git_info(REPO)  # this repository, whatever the working directory
    if "dirty" not in git:
        git = {**git, "dirty": True}  # an unknown state is never treated as clean
    try:
        # A mutable tag is named as such before the corpus record is compared.
        validate_image_digest(args.docker_digest)
        dataset, coarse_path = Path(args.dataset), Path(args.coarse_dataset)
        extra = input_provenance(dataset, coarse_path, args.docker_digest)
        frame, dataset_sha256 = _read(dataset)
        coarse, coarse_sha256 = _read(coarse_path)
        result = run_bench(
            frame=frame,
            coarse_frame=coarse,
            out_dir=args.out_dir,
            docker_image_digest=args.docker_digest,
            timestamp=args.timestamp,
            dataset_sha256=dataset_sha256,
            git_state=git,
            hardware=get_hardware_info(),
            device=args.device,
            entries=parse_entries(args.entries),
            epochs=args.epochs,
            allow_dirty=args.allow_dirty,
            extra_inputs={**extra, "coarse_dataset_sha256": coarse_sha256},
        )
    except (ValueError, OSError) as exc:
        # OSError: a missing or unreadable dataset, an output path that is a file.
        print(f"run_surrogate_bench: {exc}", file=sys.stderr)
        return 2
    artifacts = ("results", "splits", "summary", "figure", "metadata")
    print("Wrote " + ", ".join(str(result[k]) for k in artifacts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
