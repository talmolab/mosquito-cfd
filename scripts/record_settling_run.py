r"""Record a settling run (OpenSpec change add-settled-beat-corpus, #192).

Two subcommands, run on the machine that runs the case, from the clean ``main`` checkout:

``launch --run-dir DIR``
    Just before the container starts. Refuses (exit 1, nothing written) unless the checkout is
    clean and HEAD is on ``origin/main``, so a run that could never be recorded is not started.
    Otherwise writes ``DIR/launch.json`` with HEAD and ``git status --porcelain``.

``record --name NAME --run-dir DIR``
    After the run. Derives the provenance from git (:func:`settling.git_provenance`: HEAD still
    the launch commit, on ``origin/main``, clean at launch and now, gated files equal to the start
    commit), reads the IAMReX label of the manifest's image with ``docker image inspect``, runs
    the declared controls (:func:`settling.build_run_record`), validates the record, and only
    then, with ``--field-change``, measures the near-wing field change (fine long runs; needs
    ``yt``). Writes ``<settling-dir>/records/<NAME>.json``.

``record`` refuses to overwrite an existing record (records are evidence) and refuses to write
an invalid one; nothing is written on refusal. New, untracked records under
``examples/settling_check/records/`` do not make the checkout dirty.

``DIR`` must live outside the checkout, or under an ignored ``runs/`` folder, and hold
``IB_Particle_1.csv``, ``run.log``, ``command.txt`` (the exact container command),
``hardware.json``, the run's deck (named as in the settling manifest) and ``launch.json``.

Usage, from the repository root::

    uv run python scripts/record_settling_run.py launch --run-dir <DIR>
    # ... run the container, writing command.txt and hardware.json into <DIR> ...
    uv run python scripts/record_settling_run.py record --name fine_s35_f085_p30 \
        --run-dir <DIR> --field-change
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, SPAN
from mosquito_cfd.force_surrogate.normalization import compute_force_reference
from mosquito_cfd.force_surrogate.settling import (
    UPSTREAM_REF,
    _dirty_lines,
    build_run_record,
    field_change_for_run,
    git_launch_state,
    git_provenance,
    manifest_entry,
    provenance_problems,
    validate_run_record,
)

IAMREX_LABEL = "com.mosquito-cfd.iamrex-commit"


def _iamrex_label_from_docker(image: str) -> str:
    """The image's IAMReX commit label, from ``docker image inspect``."""
    try:
        proc = subprocess.run(
            [
                "docker",
                "image",
                "inspect",
                image,
                "--format",
                '{{index .Config.Labels "' + IAMREX_LABEL + '"}}',
            ],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise SystemExit(
            f"record not written: cannot run docker image inspect ({exc})"
        ) from exc
    if proc.returncode != 0 or not proc.stdout.strip():
        raise SystemExit(
            f"record not written: cannot read {IAMREX_LABEL} of {image} with docker "
            f"({proc.stderr.strip()})"
        )
    return proc.stdout.strip()


# Looked up at call time, so tests can stand in for docker without a CLI override.
_iamrex_label = _iamrex_label_from_docker


def _field_change(settling_dir: Path, entry: dict, run_dir: Path) -> dict:
    sweep = json.loads(
        (settling_dir / entry["grid"] / "sweep_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    config = next(c for c in sweep["configs"] if c["name"] == entry["config"])
    manifest = json.loads(
        (settling_dir / "settling_manifest.json").read_text(encoding="utf-8")
    )
    f_star = float(config["frequency_fstar"])
    u_ref = compute_force_reference(
        f_star, float(config["stroke_amp_deg"]), R_GYRATION, SPAN, CHORD
    ).u_ref
    return field_change_for_run(
        run_dir,
        b_last=int(entry["n_wingbeats"]),
        frequency_fstar=f_star,
        dt=float(sweep["dt"]),
        u_ref=u_ref,
        frames_per_beat=int(manifest["frames_per_beat"]),
    )


def _launch(args: argparse.Namespace) -> int:
    out = args.run_dir / "launch.json"
    if out.exists():
        print(f"refusing to overwrite: {out} exists")
        return 1
    state = git_launch_state(args.repo_root)
    dirty = _dirty_lines(state["git_status_porcelain"])
    if dirty:
        print(
            "launch refused: the checkout is dirty (a run from it could not be recorded):"
        )
        for line in dirty[:10]:
            print(f"  {line}")
        return 1
    probe = git_provenance(args.repo_root, launch=state)
    upstream = [
        p for p in provenance_problems(probe) if "upstream" in p or "ancestor" in p
    ]
    if upstream:
        print(f"launch refused: HEAD is not on {UPSTREAM_REF}:")
        for problem in upstream:
            print(f"  {problem}")
        return 1
    args.run_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"launch state: {state['start_commit']} (clean, on {UPSTREAM_REF})")
    return 0


def _record(args: argparse.Namespace) -> int:
    out = args.settling_dir / "records" / f"{args.name}.json"
    if out.exists():
        print(f"refusing to overwrite: {out} exists")
        return 1
    launch_path = args.run_dir / "launch.json"
    if not launch_path.is_file():
        print(
            f"record not written: {launch_path} is missing (run `launch` before the run)"
        )
        return 1
    hardware_path = args.hardware_json or args.run_dir / "hardware.json"
    if not hardware_path.is_file():
        print(f"record not written: {hardware_path} is missing (hardware.json)")
        return 1
    entry = manifest_entry(args.settling_dir, args.name)
    if args.field_change and (entry["kind"] != "long" or entry["grid"] != "fine"):
        print("record not written: --field-change applies to fine long runs only")
        return 1
    provenance = git_provenance(
        args.repo_root, launch=json.loads(launch_path.read_text(encoding="utf-8"))
    )
    record = build_run_record(
        args.run_dir,
        name=args.name,
        settling_dir=args.settling_dir,
        repo_root=args.repo_root,
        provenance=provenance,
        iamrex_commit=_iamrex_label(entry["image"]),
        hardware=json.loads(hardware_path.read_text(encoding="utf-8")),
    )
    problems = validate_run_record(record, entry)
    if problems:
        print("record not written:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    if args.field_change:
        record["field_change"] = _field_change(args.settling_dir, entry, args.run_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    for control, result in record["controls"].items():
        print(f"{control}: {'passed' if result['passed'] else 'FAILED'}")
    print(f"wrote {out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the ``launch`` or ``record`` subcommand."""
    parser = argparse.ArgumentParser(description="Record a settling run.")
    sub = parser.add_subparsers(dest="command", required=True)
    launch = sub.add_parser("launch", help="write launch.json before the run starts")
    launch.add_argument("--run-dir", required=True, type=Path)
    launch.add_argument("--repo-root", type=Path, default=Path("."))
    record = sub.add_parser("record", help="write the run record after the run")
    record.add_argument("--name", required=True)
    record.add_argument("--run-dir", required=True, type=Path)
    record.add_argument(
        "--settling-dir", type=Path, default=Path("examples/settling_check")
    )
    record.add_argument("--repo-root", type=Path, default=Path("."))
    record.add_argument(
        "--hardware-json",
        type=Path,
        default=None,
        help="Default: <run-dir>/hardware.json",
    )
    record.add_argument("--field-change", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "launch":
        return _launch(args)
    return _record(args)


if __name__ == "__main__":
    sys.exit(main())
