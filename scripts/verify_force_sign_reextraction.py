r"""Verification gate for re-extracting a committed corpus with the on-wing sign (#109).

Operator-run after ``scripts/extract_forces.py`` has regenerated a corpus's ``dataset.parquet``
and ``run_metadata.json`` in the working tree. It compares them with the corpus at
``--baseline-ref``, which it reads with ``git show <ref>:<path>`` (never the working-tree copy:
comparing the re-extracted file with itself would be vacuous), and prints the baseline's commit
and blob SHAs so the pasted output proves which side it compared against.

``--baseline-ref`` is required and is the PR branch's merge-base with ``origin/main``, recorded
in the PR body (OpenSpec change ``fix-wing-force-sign-convention``, design D8). Checks:

- **Parquet:** schema and dtypes identical; every non-``CF_*`` column value-identical in the same
  row order (the raw ``Fx..Mz`` included); every ``CF_*`` column exactly the negated baseline,
  with identical NaN positions; and every ``CF_*`` column non-zero somewhere, since ``-0 == 0``
  would let an all-zero column pass the negation check vacuously.
- **Metadata:** ``run_id``, ``timestamp`` and ``git`` may differ; ``hardware`` is reported, not
  compared (a driver update or another host must not halt a correct re-extraction). Exactly one
  key is added, ``force_sign_convention``, equal to this script's own pinned literal (not the
  writer's constant, so a wrong constant cannot pass both). Every other key is identical:
  ``inputs``, ``extraction_inputs`` (every ``csv_sha256`` and the ``input_dir``),
  ``moment_reference``, ``docker_image`` and ``dropped_configs``. ``git.dirty`` is ``false``.
- **Chain:** the baseline parquet's sha256 equals the ``inputs.hash`` of the corpus's surrogate
  at the baseline ref and the pinned pre-change literal, so the parquet negated here is exactly
  the one the stale surrogate was trained on.

Run from anywhere inside the repository (native PowerShell; see tasks.md task 39), e.g.::

    uv run python scripts/verify_force_sign_reextraction.py --corpus examples/prelim_sweep `
        --baseline-ref <merge-base>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate.dataset import DATASET_COLUMNS

CF_COLUMNS = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")
_RAW = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]
SIGN_KEY = "force_sign_convention"
# Keys a re-extraction legitimately rewrites; hardware is reported separately.
_MAY_DIFFER = frozenset({"run_id", "timestamp", "git"})
_REPORTED = frozenset({"hardware"})

# The spec literal ("Force sign convention travels with the corpus"), held here independently
# of the writer's constant.
PINNED_FORCE_SIGN_CONVENTION = {
    "coefficients": "on_wing",
    "raw_columns": "on_fluid",
    "raw_source": "IAMReX kernel.ib_force / kernel.ib_moment",
    "applies_to": ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"],
    "definition": "docs/coordinate-convention.md#force-and-moment-sign",
}

# sha256 of each corpus's pre-change dataset.parquet (design D6), keyed by its repo-relative
# path. Verified equal to the committed surrogate's inputs.hash when this gate was written.
PINNED_PRE_CHANGE_SHA = {
    "examples/prelim_sweep": "01c88ae908b85616f0335583a9ca8e27eb9b660574244981f44333883eb40afa",
    "examples/prelim_sweep_fine": "2092f0fd05a60e706667b22848c46f7ce6608309b2021b02940c606856bd26a9",
}


@dataclass(frozen=True)
class Check:
    """One gate check's outcome."""

    name: str
    ok: bool
    detail: str = ""


def _negation_check_name(column: str) -> str:
    return f"{column} == -baseline (exact, NaN positions identical)"


def compare_frames(baseline: pd.DataFrame, new: pd.DataFrame) -> list[Check]:
    """Frame-level checks: only the sign of the ``CF_*`` columns may change."""
    schema_ok = (
        list(new.columns) == list(baseline.columns) == DATASET_COLUMNS
        and new.dtypes.to_dict() == baseline.dtypes.to_dict()
    )
    checks = [
        Check(
            "schema and dtypes",
            schema_ok,
            ""
            if schema_ok
            else f"columns {list(new.columns)}; dtypes {new.dtypes.to_dict()}",
        )
    ]
    if not schema_ok:
        return checks
    if len(new) != len(baseline):
        checks.append(Check("row count", False, f"{len(new)} vs {len(baseline)}"))
        return checks

    other = [c for c in DATASET_COLUMNS if c not in CF_COLUMNS]
    try:
        pd.testing.assert_frame_equal(
            baseline[other].reset_index(drop=True),
            new[other].reset_index(drop=True),
            check_exact=True,
        )
        checks.append(
            Check("non-CF columns value-identical", True, f"{len(other)} columns")
        )
    except AssertionError as exc:
        first = str(exc).splitlines()[0] if str(exc) else "frames differ"
        checks.append(Check("non-CF columns value-identical", False, first))

    zero = []
    for c in CF_COLUMNS:
        old = baseline[c].to_numpy(dtype=float)
        got = new[c].to_numpy(dtype=float)
        if not np.any(np.isfinite(old) & (old != 0)):
            zero.append(c)
        same_nan = np.array_equal(np.isnan(got), np.isnan(old))
        ok = np.array_equal(got, -old, equal_nan=True)
        if ok:
            detail = f"{len(got)} rows"
        elif not same_nan:
            detail = "NaN positions differ"
        else:
            mismatch = int(np.sum(~((got == -old) | (np.isnan(got) & np.isnan(old)))))
            detail = f"{mismatch} rows differ"
        checks.append(Check(_negation_check_name(c), ok, detail))
    checks.append(
        Check(
            "every CF_* column carries a non-zero finite value",
            not zero,
            f"all zero or non-finite: {zero}" if zero else "",
        )
    )
    return checks


def compare_metadata(baseline: Mapping, new: Mapping) -> list[Check]:
    """Provenance checks: one key added, nothing the CFD or the inputs determine changed."""
    added = sorted(set(new) - set(baseline))
    removed = sorted(set(baseline) - set(new))
    checks = [
        Check(
            f"exactly one key added ({SIGN_KEY}), none removed",
            added == [SIGN_KEY] and not removed,
            f"added {added}, removed {removed}",
        ),
        Check(
            f"{SIGN_KEY} is the pinned value",
            new.get(SIGN_KEY) == PINNED_FORCE_SIGN_CONVENTION,
            f"{new.get(SIGN_KEY)!r}",
        ),
    ]
    for key in sorted(set(baseline) - _MAY_DIFFER - _REPORTED):
        if key not in new:
            continue  # reported by the added/removed check
        checks.append(
            Check(f"metadata key {key!r} unchanged", new[key] == baseline[key])
        )
    git = new.get("git")
    checks.append(
        Check(
            "git.dirty is false",
            isinstance(git, Mapping) and git.get("dirty") is False,
            f"git={git!r}",
        )
    )
    old_hw, new_hw = baseline.get("hardware"), new.get("hardware")
    checks.append(
        Check(
            "hardware (reported, not compared)",
            True,
            "unchanged" if old_hw == new_hw else f"differs: {old_hw!r} -> {new_hw!r}",
        )
    )
    return checks


def compare_chain(
    baseline_sha: str, *, surrogate_hash: str | None, pinned: str | None
) -> list[Check]:
    """The negated baseline is exactly the parquet the stale surrogate was trained on."""
    ok = baseline_sha == surrogate_hash == pinned
    return [
        Check(
            "baseline parquet is the stale surrogate's training data",
            ok,
            f"baseline {baseline_sha}; surrogate inputs.hash {surrogate_hash}; "
            f"pinned {pinned}",
        )
    ]


def _git(repo: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, check=True
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"git {' '.join(args)} failed in {repo}: "
            f"{exc.stderr.decode(errors='replace').strip()}"
        ) from exc


def _show(repo: Path, commit: str, rel: str, tmpdir: Path) -> tuple[str, Path]:
    """Write ``<commit>:<rel>`` to a temp file; return its blob SHA and the local path."""
    blob = _git(repo, "rev-parse", f"{commit}:{rel}").decode().strip()
    out = tmpdir / rel.replace("/", "__")
    out.write_bytes(_git(repo, "show", f"{commit}:{rel}"))
    return blob, out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_force_digest(df: pd.DataFrame) -> str:
    """The same digest the CI tripwires pin (``_FROZEN_*RAW_FORCE_SHA``)."""
    return hashlib.sha256(
        pd.util.hash_pandas_object(df[_RAW], index=False).values.tobytes()
    ).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate on one corpus; exit 0 only if every check passes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument(
        "--baseline-ref",
        required=True,
        help="The PR branch's merge-base with origin/main (recorded in the PR body).",
    )
    args = parser.parse_args(argv)

    corpus = args.corpus.resolve()
    repo = Path(_git(corpus, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    rel = corpus.relative_to(repo).as_posix()
    commit = _git(repo, "rev-parse", f"{args.baseline_ref}^{{commit}}").decode().strip()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        pq_blob, base_pq = _show(repo, commit, f"{rel}/dataset.parquet", tmpdir)
        md_blob, base_md = _show(repo, commit, f"{rel}/run_metadata.json", tmpdir)
        sg_blob, base_sg = _show(
            repo, commit, f"{rel}/surrogate/run_metadata.json", tmpdir
        )
        baseline = pd.read_parquet(base_pq)
        baseline_sha = _sha256(base_pq)
        baseline_meta = json.loads(base_md.read_text(encoding="utf-8"))
        surrogate_hash = (
            json.loads(base_sg.read_text(encoding="utf-8")).get("inputs") or {}
        ).get("hash")

    new_pq, new_md = corpus / "dataset.parquet", corpus / "run_metadata.json"
    new = pd.read_parquet(new_pq)
    new_meta = json.loads(new_md.read_text(encoding="utf-8"))

    print(f"corpus:   {rel}")
    print(f"baseline: {args.baseline_ref} = {commit}")
    print(
        f"  {rel}/dataset.parquet               blob {pq_blob}  sha256 {baseline_sha}"
    )
    print(f"  {rel}/run_metadata.json             blob {md_blob}")
    print(f"  {rel}/surrogate/run_metadata.json   blob {sg_blob}")
    print("regenerated (working tree):")
    print(f"  dataset.parquet     sha256 {_sha256(new_pq)}")
    print(f"  run_metadata.json   sha256 {_sha256(new_md)}")
    print(f"raw Fx..Mz digest: baseline {raw_force_digest(baseline)}")
    print(f"                   new      {raw_force_digest(new)}")

    checks = compare_frames(baseline, new)
    checks += compare_metadata(baseline_meta, new_meta)
    checks += compare_chain(
        baseline_sha,
        surrogate_hash=surrogate_hash,
        pinned=PINNED_PRE_CHANGE_SHA.get(rel),
    )

    print()
    for check in checks:
        print(
            f"{'PASS' if check.ok else 'FAIL'}  {check.name}"
            + (f"  -- {check.detail}" if check.detail else "")
        )
    verdict = all(c.ok for c in checks)
    print(f"\nVERDICT: {'PASS' if verdict else 'FAIL'}")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
