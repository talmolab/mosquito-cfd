r"""Write one settling run record (OpenSpec change add-settled-beat-corpus, #192).

Thin driver over :func:`mosquito_cfd.force_surrogate.settling.build_run_record`. Run it on the
machine that ran the case, from the clean ``main`` checkout the run was started from, once the run
has finished. It runs the controls the settling manifest declares for that run (C1 for a control
deck; C3 and C4 for a long run), validates the record and writes
``<settling-dir>/records/<name>.json``.

It refuses to overwrite an existing record (records are evidence; a re-run is a new decision for
the user) and refuses to write a record that fails validation, for example from a dirty checkout.

``--field-change`` also measures the near-wing field change from the run's plotfiles (fine long
runs; needs ``yt``).

Usage, from the repository root::

    uv run python scripts/record_settling_run.py --name fine_s35_f085_p30 \
        --run-dir ~/settling_runs/fine_s35_f085_p30 \
        --start-commit "$(git rev-parse HEAD)" \
        --git-dirty "$( [ -z "$(git status --porcelain)" ] && echo false || echo true )" \
        --iamrex-commit f93dc794 --command "$(cat ~/settling_runs/fine_s35_f085_p30/command.txt)" \
        --hardware-json ~/settling_runs/fine_s35_f085_p30/hardware.json --field-change
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, SPAN
from mosquito_cfd.force_surrogate.normalization import compute_force_reference
from mosquito_cfd.force_surrogate.settling import (
    build_run_record,
    field_change_for_run,
    validate_run_record,
)


def _entry(settling_dir: Path, name: str) -> dict:
    manifest = json.loads(
        (settling_dir / "settling_manifest.json").read_text(encoding="utf-8")
    )
    for entry in [*manifest.get("runs", []), *manifest.get("controls", [])]:
        if entry["name"] == name:
            return {**entry, "_frames_per_beat": manifest.get("frames_per_beat", 20)}
    raise SystemExit(
        f"{name!r} is not a run or control in {settling_dir}/settling_manifest.json"
    )


def _field_change(settling_dir: Path, entry: dict, run_dir: Path) -> dict:
    sweep = json.loads(
        (settling_dir / entry["grid"] / "sweep_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    config = next(c for c in sweep["configs"] if c["name"] == entry["config"])
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
        frames_per_beat=int(entry["_frames_per_beat"]),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Write the record; return non-zero without writing if it exists or is invalid."""
    parser = argparse.ArgumentParser(description="Write one settling run record.")
    parser.add_argument("--name", required=True)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--settling-dir", type=Path, default=Path("examples/settling_check")
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--start-commit", required=True)
    parser.add_argument("--git-dirty", required=True, choices=("true", "false"))
    parser.add_argument("--iamrex-commit", required=True)
    parser.add_argument(
        "--command", required=True, help="The exact container command run."
    )
    parser.add_argument("--hardware-json", required=True, type=Path)
    parser.add_argument("--field-change", action="store_true")
    args = parser.parse_args(argv)

    out = args.settling_dir / "records" / f"{args.name}.json"
    if out.exists():
        print(f"refusing to overwrite: {out} exists")
        return 1
    entry = _entry(args.settling_dir, args.name)
    field_change = (
        _field_change(args.settling_dir, entry, args.run_dir)
        if args.field_change
        else None
    )
    record = build_run_record(
        args.run_dir,
        name=args.name,
        settling_dir=args.settling_dir,
        repo_root=args.repo_root,
        start_commit=args.start_commit,
        git_dirty=args.git_dirty == "true",
        iamrex_commit=args.iamrex_commit,
        command=args.command,
        hardware=json.loads(args.hardware_json.read_text(encoding="utf-8")),
        field_change=field_change,
    )
    problems = validate_run_record(record, entry)
    if problems:
        print("record not written:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(record, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    for control, result in record["controls"].items():
        print(f"{control}: {'passed' if result['passed'] else 'FAILED'}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
