r"""Verification gate for re-extracting a committed corpus about the wing hinge (#108).

Operator-run after ``scripts/extract_forces.py`` has regenerated a corpus's ``dataset.parquet``
and ``run_metadata.json`` in the working tree, and BEFORE they are committed. It compares the
regenerated files against the committed baseline, which it reads with ``git show <ref>:<path>``
into a temporary file -- never the working-tree copy, since comparing the re-extracted file to
itself would pass every check vacuously -- and prints the baseline's commit and blob SHAs so the
pasted output proves which side it compared against.

Checks (OpenSpec change ``fix-moment-reference-hinge``, tasks 30 / 30a / 30b):

- schema and dtypes identical; rows per config identical;
- every column except ``CF_mx``/``CF_mz`` value-identical to the baseline, including the raw
  ``Fx..Mz``, ``CF_x/CF_y/CF_z``, ``CF_my``, ``config_name`` and ``split``;
- ``CF_mx``/``CF_mz`` changed in every config;
- the algebraic control (design D11): ``CF_m*`` re-derived from the OLD parquet's raw columns and
  the offset from the committed deck are value-identical to the regenerated ones;
- metadata: ``dropped_configs == []``, the CFD ``docker_image`` unchanged, the recorded
  per-config offsets equal the deck-derived ones, and every consumed CSV hashed.

Row counts cannot tell the two corpora apart (both have identical per-config ``max_step`` maps),
so the printed raw-force digests -- and the CI tripwires that pin them -- are what catch a
swapped ``--input-dir``.

``--zero-offset-control`` additionally runs the rewired extractor over the raw CSVs with the
shift forced to zero and requires the result to equal the baseline across all 22 columns
(design D11): it separates "the rewired pipeline changed something" from "the shift did".

Run from anywhere inside the repository, e.g.::

    uv run python scripts/verify_moment_reextraction.py --corpus examples/prelim_sweep_fine \
        --zero-offset-control --input-dir Z:/.../runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from mosquito_cfd.force_surrogate import compute_moment_reference, load_manifest_configs
from mosquito_cfd.force_surrogate import dataset as dataset_module
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN
from mosquito_cfd.force_surrogate.dataset import DATASET_COLUMNS
from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value

_CHANGED = ("CF_mx", "CF_mz")
_RAW = ["Fx", "Fy", "Fz", "Mx", "My", "Mz"]


@dataclass(frozen=True)
class Check:
    """One gate check's outcome."""

    name: str
    ok: bool
    detail: str = ""


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, check=True
    ).stdout


def _repo_root(path: Path) -> Path:
    return Path(_git(path, "rev-parse", "--show-toplevel").decode().strip())


def git_show_to_temp(
    repo: Path, ref: str, rel_path: str, tmpdir: Path
) -> tuple[str, Path]:
    """Write ``<ref>:<rel_path>`` to a temp file; return its blob SHA and local path."""
    spec = f"{ref}:{rel_path}"
    blob = _git(repo, "rev-parse", spec).decode().strip()
    out = tmpdir / Path(rel_path).name
    out.write_bytes(_git(repo, "show", spec))
    return blob, out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_force_digest(df: pd.DataFrame) -> str:
    """The same digest the CI tripwires pin (``_FROZEN_*RAW_FORCE_SHA``)."""
    return hashlib.sha256(
        pd.util.hash_pandas_object(df[_RAW], index=False).values.tobytes()
    ).hexdigest()


def deck_offsets(corpus: Path) -> dict[str, np.ndarray]:
    """Per-config ``particle_inputs.{x,y,z} - particle_inputs.hinge_{x,y,z}`` from the decks.

    Read from the committed decks, not from the ``run_metadata.json`` the extraction wrote --
    otherwise a sign-flipped extractor and its own record would reconcile.
    """
    offsets = {}
    for config in load_manifest_configs(corpus / "sweep_manifest.json"):
        text = (corpus / config["input_file"]).read_text(encoding="utf-8")
        particle = np.array(
            [read_deck_value(text, f"particle_inputs.{a}") for a in "xyz"]
        )
        hinge = np.array(
            [read_deck_value(text, f"particle_inputs.hinge_{a}") for a in "xyz"]
        )
        offsets[config["name"]] = particle - hinge
    return offsets


def _m_ref(sub: pd.DataFrame) -> float:
    (stroke,) = sub["stroke_amp_deg"].unique()
    (freq,) = sub["frequency_fstar"].unique()
    return compute_moment_reference(freq, stroke, R_GYRATION, SPAN, CHORD, RHO).m_ref


def _frames_equal(a: pd.DataFrame, b: pd.DataFrame) -> tuple[bool, str]:
    try:
        pd.testing.assert_frame_equal(
            a.reset_index(drop=True), b.reset_index(drop=True), check_exact=True
        )
    except AssertionError as exc:
        return False, str(exc).splitlines()[0] if str(exc) else "frames differ"
    return True, ""


def compare_frames(
    baseline: pd.DataFrame, new: pd.DataFrame, offsets: Mapping[str, np.ndarray]
) -> list[Check]:
    """Frame-level checks of a hinge re-extraction against its pre-change baseline."""
    checks = []
    schema_ok = list(new.columns) == DATASET_COLUMNS == list(baseline.columns)
    dtypes_ok = schema_ok and new.dtypes.to_dict() == baseline.dtypes.to_dict()
    checks.append(
        Check(
            "schema",
            schema_ok and dtypes_ok,
            "" if schema_ok and dtypes_ok else f"columns {list(new.columns)}",
        )
    )
    if not schema_ok:
        return checks

    base_counts = baseline["config_name"].value_counts().sort_index()
    new_counts = new["config_name"].value_counts().sort_index()
    counts_ok = base_counts.to_dict() == new_counts.to_dict()
    checks.append(
        Check(
            "rows per config",
            counts_ok,
            f"{len(new_counts)} configs, {len(new)} rows"
            + ("" if counts_ok else f"; baseline {base_counts.to_dict()}"),
        )
    )
    if not counts_ok:
        return checks

    unchanged = [c for c in DATASET_COLUMNS if c not in _CHANGED]
    ok, detail = _frames_equal(baseline[unchanged], new[unchanged])
    checks.append(Check("unchanged columns", ok, detail or f"{len(unchanged)} columns"))

    moved = []
    for name, sub in new.groupby("config_name"):
        old = baseline.loc[sub.index]
        if any(np.allclose(sub[c], old[c], rtol=1e-9, atol=1e-12) for c in _CHANGED):
            moved.append(name)
    checks.append(
        Check(
            "CF_mx/CF_mz changed in every config",
            not moved,
            f"unchanged in {moved}" if moved else "",
        )
    )

    # Design D11: re-derive the target from the OLD parquet's raw columns and the deck offset,
    # in the same arithmetic order as the extractor, and demand exact equality.
    mismatched = []
    for name, sub in baseline.groupby("config_name"):
        d = offsets[name]
        m_ref = _m_ref(sub)
        want = {
            "CF_mx": (sub["Mx"] + (d[1] * sub["Fz"] - d[2] * sub["Fy"])) / m_ref,
            "CF_my": (sub["My"] + (d[2] * sub["Fx"] - d[0] * sub["Fz"])) / m_ref,
            "CF_mz": (sub["Mz"] + (d[0] * sub["Fy"] - d[1] * sub["Fx"])) / m_ref,
        }
        got = new.loc[sub.index]
        for col, values in want.items():
            if not np.array_equal(got[col].to_numpy(), values.to_numpy()):
                diff = np.max(np.abs(got[col].to_numpy() - values.to_numpy()))
                mismatched.append(f"{name}:{col} (max |diff| {diff:.3g})")
    checks.append(
        Check(
            "algebraic control (design D11)",
            not mismatched,
            "; ".join(mismatched[:6]) if mismatched else "bitwise equal",
        )
    )
    return checks


def compare_metadata(
    baseline: Mapping, new: Mapping, offsets: Mapping[str, np.ndarray]
) -> list[Check]:
    """Provenance checks of a regenerated corpus run_metadata.json."""
    names = set(offsets)
    recorded = (new.get("moment_reference") or {}).get("configs") or {}
    bad_offsets = sorted(
        n
        for n in names
        if n not in recorded
        or list(recorded[n].get("offset") or []) != list(offsets[n])
    )
    hashed = set((new.get("extraction_inputs") or {}).get("csv_sha256") or {})
    return [
        Check(
            "no dropped configs",
            new.get("dropped_configs") == [],
            f"dropped_configs={new.get('dropped_configs')!r}",
        ),
        Check(
            "docker_image preserved",
            new.get("docker_image") == baseline.get("docker_image")
            and bool(baseline.get("docker_image")),
            f"{new.get('docker_image')}",
        ),
        Check(
            "recorded offsets match the decks",
            not bad_offsets,
            f"mismatch in {bad_offsets}" if bad_offsets else f"{len(names)} configs",
        ),
        Check(
            "every consumed CSV hashed",
            hashed == names,
            f"{len(hashed)}/{len(names)}"
            + (f"; missing {sorted(names - hashed)}" if hashed != names else ""),
        ),
    ]


@contextmanager
def _shift_forced_to_zero():
    real = dataset_module.shift_moment_reference

    def zero_shift(mx, my, mz, fx, fy, fz, *, offset):
        return real(mx, my, mz, fx, fy, fz, offset=np.zeros(3))

    dataset_module.shift_moment_reference = zero_shift
    try:
        yield
    finally:
        dataset_module.shift_moment_reference = real


def build_with_zero_offset(
    manifest: Path, input_dir: Path, csv_name: str
) -> pd.DataFrame:
    """The rewired extractor over the raw CSVs, with only the shift disabled.

    Deck resolution, the ``X,Y,Z`` read and its guards, the ``iStep`` dedup, column order and
    dtypes all run for real. Round-tripped through parquet so dtypes match a committed file.
    """
    csv_paths = {
        c["name"]: input_dir / c["name"] / csv_name
        for c in load_manifest_configs(manifest)
    }
    with _shift_forced_to_zero():
        frame, dropped, _ = dataset_module.build_dataset(manifest, csv_paths)
    if dropped:
        raise ValueError(f"zero-offset control dropped configs {dropped}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "zero_offset.parquet"
        frame.to_parquet(path, index=False)
        return pd.read_parquet(path)


def compare_zero_offset(baseline: pd.DataFrame, zero: pd.DataFrame) -> list[Check]:
    """The zero-offset extraction must equal the pre-change baseline in every column."""
    ok, detail = _frames_equal(baseline[DATASET_COLUMNS], zero[DATASET_COLUMNS])
    return [
        Check(
            "zero-offset control (design D11)",
            ok,
            detail or f"all {len(DATASET_COLUMNS)} columns value-identical",
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate on one corpus; exit 0 only if every check passes."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--zero-offset-control", action="store_true")
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--csv-name", default="IB_Particle_1.csv")
    args = parser.parse_args(argv)
    if args.zero_offset_control and args.input_dir is None:
        parser.error("--zero-offset-control requires --input-dir")

    corpus = args.corpus.resolve()
    repo = _repo_root(corpus)
    rel = corpus.relative_to(repo).as_posix()
    commit = _git(repo, "rev-parse", args.baseline_ref).decode().strip()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        pq_blob, base_pq = git_show_to_temp(
            repo, commit, f"{rel}/dataset.parquet", tmpdir
        )
        md_blob, base_md = git_show_to_temp(
            repo, commit, f"{rel}/run_metadata.json", tmpdir
        )
        baseline = pd.read_parquet(base_pq)
        baseline_meta = json.loads(base_md.read_text(encoding="utf-8"))

    new_pq, new_md = corpus / "dataset.parquet", corpus / "run_metadata.json"
    new = pd.read_parquet(new_pq)
    new_meta = json.loads(new_md.read_text(encoding="utf-8"))
    offsets = deck_offsets(corpus)

    print(f"corpus:   {rel}")
    print(f"baseline: {args.baseline_ref} = {commit}")
    print(f"  {rel}/dataset.parquet     blob {pq_blob}")
    print(f"  {rel}/run_metadata.json   blob {md_blob}")
    print("regenerated (working tree):")
    print(f"  dataset.parquet     sha256 {_sha256(new_pq)}")
    print(f"  run_metadata.json   sha256 {_sha256(new_md)}")
    print(f"raw Fx..Mz digest: baseline {raw_force_digest(baseline)}")
    print(f"                   new      {raw_force_digest(new)}")
    print(f"deck offsets: {sorted({tuple(d) for d in offsets.values()})}")

    checks = compare_frames(baseline, new, offsets)
    checks += compare_metadata(baseline_meta, new_meta, offsets)
    if args.zero_offset_control:
        zero = build_with_zero_offset(
            corpus / "sweep_manifest.json", args.input_dir, args.csv_name
        )
        checks += compare_zero_offset(baseline, zero)

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
