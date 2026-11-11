"""Tests for scripts/verify_force_sign_reextraction.py (fix-wing-force-sign-convention task 32).

The script is the operator-run gate for re-extracting a committed corpus with the on-wing sign
(design D8). These tests pin each of its checks on small synthetic frames and metadata (every
check must fail on the defect it exists to catch, and a faithful negation must pass), and run it
end to end in throwaway git repositories, so it is shown to read its baseline from git rather
than from the working tree.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.dataset import DATASET_COLUMNS

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_force_sign_reextraction.py"
CF = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "7" * 64
SIGN = {
    "coefficients": "on_wing",
    "raw_columns": "on_fluid",
    "raw_source": "IAMReX kernel.ib_force / kernel.ib_moment",
    "applies_to": ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"],
    "definition": "docs/coordinate-convention.md#force-and-moment-sign",
}


def _load():
    spec = importlib.util.spec_from_file_location(
        "verify_force_sign_reextraction", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their module via sys.modules, so register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _failed(checks) -> list[str]:
    return [c.name for c in checks if not c.ok]


def _baseline() -> pd.DataFrame:
    """Two configs x 4 rows in the pre-change (on-fluid) convention, with one NaN in CF_z."""
    rng = np.random.default_rng(0)
    rows = []
    for name, stroke, freq, split in (
        ("s35_f085_p30", 35.0, 0.85, "train"),
        ("s55_f115_p60", 55.0, 1.15, "holdout"),
    ):
        for i in range(4):
            f = rng.normal(size=3) * 50
            m = rng.normal(size=3) * 20
            rows.append(
                {
                    "config_name": name,
                    "index": 0 if split == "train" else 1,
                    "time": 0.5 * i,
                    "phase": (0.5 * i * freq) % 1,
                    "wingbeat": int(0.5 * i * freq),
                    "stroke_amp_deg": stroke,
                    "frequency_fstar": freq,
                    "pitch_amp_deg": 30.0,
                    "reynolds": 42.0,
                    "split": split,
                    "Fx": f[0], "Fy": f[1], "Fz": f[2],
                    "Mx": m[0], "My": m[1], "Mz": m[2],
                    "CF_x": f[0] / 7, "CF_y": f[1] / 7, "CF_z": f[2] / 7,
                    "CF_mx": m[0] / 3, "CF_my": m[1] / 3, "CF_mz": m[2] / 3,
                }
            )  # fmt: skip
    df = pd.DataFrame(rows)[DATASET_COLUMNS]
    df["config_name"] = df["config_name"].astype("str")
    df["split"] = df["split"].astype("str")
    df.loc[1, "CF_z"] = np.nan
    return df


def _negated(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out[CF] = -out[CF]
    return out


def _base_meta() -> dict:
    return {
        "run_id": "old-run",
        "timestamp": "2026-10-15T21:51:42+00:00",
        "git": {"commit": "a" * 40, "branch": "old", "dirty": False},
        "hardware": {"gpu": "A5000", "driver": "1.0"},
        "docker_image": DIGEST,
        "inputs": {"file": "corpus\\sweep_manifest.json", "hash": "1" * 64},
        "dropped_configs": [],
        "moment_reference": {
            "point": "wing_hinge",
            "configs": {"a": {"offset": [0.0, 1.5, 0.0]}},
        },
        "extraction_inputs": {
            "input_dir": "Z:/runs",
            "csv_name": "IB_Particle_1.csv",
            "csv_sha256": {"a": "2" * 64},
        },
    }


def _new_meta(base: dict | None = None) -> dict:
    new = copy.deepcopy(base or _base_meta())
    new["run_id"] = "new-run"
    new["timestamp"] = "2026-11-11T00:00:00+00:00"
    new["git"] = {"commit": "b" * 40, "branch": "new", "dirty": False}
    new["force_sign_convention"] = copy.deepcopy(SIGN)
    return new


# --- frame checks ---------------------------------------------------------------------------


def test_exact_negation_passes_every_frame_check():
    base = _baseline()
    checks = _load().compare_frames(base, _negated(base))
    assert checks and _failed(checks) == []


def _ulp(df):
    out = df.copy()
    out.loc[0, "CF_x"] = np.nextafter(out.loc[0, "CF_x"], np.inf)
    return out


def _moved_nan(df):
    out = df.copy()
    out.loc[1, "CF_z"] = -df.loc[2, "CF_z"]  # the NaN's slot gets a value...
    out.loc[2, "CF_z"] = np.nan  # ...and the NaN moves one row down
    return out


def _reordered(df):
    return df.iloc[[1, 0, *range(2, len(df))]].reset_index(drop=True)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda df: df.assign(Fx=df["Fx"] + 1e-9), "non-CF columns value-identical"),
        (lambda df: df.assign(Mz=df["Mz"] * 1.0000001), "non-CF columns value-identical"),
        (lambda df: df.assign(phase=df["phase"] + 1e-12), "non-CF columns value-identical"),
        (_reordered, "non-CF columns value-identical"),
        (_ulp, "CF_x == -baseline (exact, NaN positions identical)"),
        (_moved_nan, "CF_z == -baseline (exact, NaN positions identical)"),
        (lambda df: df.drop(columns=["CF_my"]), "schema and dtypes"),
        (lambda df: df.assign(CF_y=-df["CF_y"]), "CF_y == -baseline (exact, NaN positions identical)"),
    ],
    ids=[
        "raw-Fx", "raw-Mz", "non-CF-phase", "row-reorder", "ulp", "moved-nan",
        "missing-CF", "unflipped-CF",
    ],
)  # fmt: skip
def test_each_frame_check_fails_on_its_defect(mutate, expected):
    base = _baseline()
    failed = _failed(_load().compare_frames(base, mutate(_negated(base))))
    assert expected in failed, failed


def test_comparing_the_baseline_with_itself_fails_every_coefficient_check():
    """The vacuous case: a corpus that was not re-extracted is not a negation of itself."""
    base = _baseline()
    failed = _failed(_load().compare_frames(base, base.copy()))
    for c in CF:
        assert f"{c} == -baseline (exact, NaN positions identical)" in failed, c


def test_an_all_zero_coefficient_column_is_refused_rather_than_trivially_negated():
    """``-0 == 0``, so an all-zero column would pass a negation check vacuously."""
    base = _baseline()
    base["CF_y"] = 0.0
    failed = _failed(_load().compare_frames(base, _negated(base)))
    assert "every CF_* column carries a non-zero finite value" in failed


def test_a_changed_dtype_fails_the_schema_check():
    base = _baseline()
    new = _negated(base)
    new["index"] = new["index"].astype("int32")
    assert "schema and dtypes" in _failed(_load().compare_frames(base, new))


def test_reordered_columns_fail_the_schema_check():
    """A dtype map ignores column order, so the column list is compared in its own right."""
    base = _baseline()
    new = _negated(base)[list(reversed(DATASET_COLUMNS))]
    assert "schema and dtypes" in _failed(_load().compare_frames(base, new))


def test_a_dropped_row_fails_the_row_count_check():
    base = _baseline()
    failed = _failed(_load().compare_frames(base, _negated(base).iloc[:-1]))
    assert failed == ["row count"]


# --- metadata checks ------------------------------------------------------------------------


def test_faithful_metadata_passes_and_reports_an_unchanged_hardware_block():
    checks = _load().compare_metadata(_base_meta(), _new_meta())
    assert checks and _failed(checks) == []


def _set(path: list[str], value):
    def mutate(meta):
        node = meta
        for key in path[:-1]:
            node = node[key]
        node[path[-1]] = value
        return meta

    return mutate


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (_set(["extraction_inputs", "csv_sha256", "a"], "3" * 64), "metadata key 'extraction_inputs' unchanged"),
        (_set(["extraction_inputs", "input_dir"], "Z:/other"), "metadata key 'extraction_inputs' unchanged"),
        (_set(["inputs", "hash"], "4" * 64), "metadata key 'inputs' unchanged"),
        (_set(["docker_image"], DIGEST.replace("7", "8")), "metadata key 'docker_image' unchanged"),
        (_set(["moment_reference", "configs", "a", "offset"], [0.0, -1.5, 0.0]), "metadata key 'moment_reference' unchanged"),
        (_set(["dropped_configs"], ["a"]), "metadata key 'dropped_configs' unchanged"),
        (_set(["force_sign_convention", "coefficients"], "on_fluid"), "force_sign_convention is the pinned value"),
        (_set(["git", "dirty"], True), "git.dirty is false"),
    ],
    ids=[
        "csv_sha256", "input_dir", "inputs.hash", "docker_image", "moment_reference-offset",
        "dropped_configs", "wrong-sign-value", "dirty",
    ],
)  # fmt: skip
def test_each_metadata_check_fails_on_its_defect(mutate, expected):
    failed = _failed(_load().compare_metadata(_base_meta(), mutate(_new_meta())))
    assert expected in failed, failed


def test_a_removed_key_fails():
    new = _new_meta()
    del new["dropped_configs"]
    failed = _failed(_load().compare_metadata(_base_meta(), new))
    assert "exactly one key added (force_sign_convention), none removed" in failed


def test_a_second_added_key_fails():
    new = _new_meta()
    new["extra_key"] = 1
    failed = _failed(_load().compare_metadata(_base_meta(), new))
    assert "exactly one key added (force_sign_convention), none removed" in failed


def test_the_sign_key_missing_fails():
    new = _new_meta()
    del new["force_sign_convention"]
    failed = _failed(_load().compare_metadata(_base_meta(), new))
    assert "exactly one key added (force_sign_convention), none removed" in failed
    assert "force_sign_convention is the pinned value" in failed


def test_a_missing_git_block_fails_the_dirty_check():
    new = _new_meta()
    del new["git"]
    assert "git.dirty is false" in _failed(_load().compare_metadata(_base_meta(), new))


def test_a_changed_hardware_block_is_reported_and_passes():
    new = _new_meta()
    new["hardware"] = {"gpu": "A40", "driver": "2.0"}
    checks = _load().compare_metadata(_base_meta(), new)
    assert _failed(checks) == []
    (hardware,) = [c for c in checks if c.name == "hardware (reported, not compared)"]
    assert "A40" in hardware.detail and "differs" in hardware.detail


def test_the_pinned_sign_value_is_the_spec_literal_not_the_writers_constant():
    """The verifier holds its own literal, so a wrong writer constant cannot pass both."""
    assert _load().PINNED_FORCE_SIGN_CONVENTION == SIGN


# --- chain check ----------------------------------------------------------------------------


def test_chain_passes_when_baseline_surrogate_and_pin_agree():
    checks = _load().compare_chain("a" * 64, surrogate_hash="a" * 64, pinned="a" * 64)
    assert checks and _failed(checks) == []


@pytest.mark.parametrize(
    ("surrogate_hash", "pinned"),
    [("b" * 64, "a" * 64), ("a" * 64, "b" * 64), (None, "a" * 64), ("a" * 64, None)],
    ids=["surrogate-mismatch", "pin-mismatch", "no-surrogate-hash", "no-pin"],
)
def test_chain_fails_when_the_baseline_is_not_what_the_surrogate_trained_on(
    surrogate_hash, pinned
):
    failed = _failed(
        _load().compare_chain("a" * 64, surrogate_hash=surrogate_hash, pinned=pinned)
    )
    assert failed == ["baseline parquet is the stale surrogate's training data"]


def test_pins_are_the_d6_literals():
    assert _load().PINNED_PRE_CHANGE_SHA == {
        "examples/prelim_sweep": "01c88ae908b85616f0335583a9ca8e27eb9b660574244981f44333883eb40afa",
        "examples/prelim_sweep_fine": "2092f0fd05a60e706667b22848c46f7ce6608309b2021b02940c606856bd26a9",
    }


# --- end to end in throwaway repos ----------------------------------------------------------


def _git_in(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@t",
            "-c", "commit.gpgsign=false", "-c", "core.hooksPath=", *args,
        ],
        cwd=repo, check=True, capture_output=True,
    )  # fmt: skip


def _throwaway(tmp_path: Path, *, regenerate: bool = True) -> tuple[Path, str]:
    """A repo whose committed corpus is on-fluid and whose working tree holds the faithful
    on-wing re-extraction, as extract_forces.py would leave it. Returns the corpus path and the
    baseline parquet's sha256 (also recorded as the surrogate's ``inputs.hash``)."""
    repo = tmp_path / "repo"
    corpus = repo / "corpus"
    (corpus / "surrogate").mkdir(parents=True)
    base = _baseline()
    base.to_parquet(corpus / "dataset.parquet", index=False)
    sha = hashlib.sha256((corpus / "dataset.parquet").read_bytes()).hexdigest()
    (corpus / "run_metadata.json").write_text(
        json.dumps(_base_meta()), encoding="utf-8"
    )
    (corpus / "surrogate" / "run_metadata.json").write_text(
        json.dumps({"inputs": {"file": "corpus/dataset.parquet", "hash": sha}}),
        encoding="utf-8",
    )
    _git_in(repo, "init", "-q")
    _git_in(repo, "add", ".")
    _git_in(repo, "commit", "-q", "-m", "base")
    if regenerate:
        _negated(base).to_parquet(corpus / "dataset.parquet", index=False)
        (corpus / "run_metadata.json").write_text(
            json.dumps(_new_meta()), encoding="utf-8"
        )
    return corpus, sha


def test_end_to_end_passes_against_the_baseline_read_from_git(tmp_path, capsys):
    corpus, sha = _throwaway(tmp_path)
    module = _load()
    module.PINNED_PRE_CHANGE_SHA = {"corpus": sha}
    rc = module.main(["--corpus", str(corpus), "--baseline-ref", "HEAD"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "VERDICT: PASS" in out
    blob = subprocess.run(
        ["git", "rev-parse", "HEAD:corpus/dataset.parquet"],
        cwd=corpus.parent, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    assert blob in out  # proves which side it compared against


def test_end_to_end_fails_when_the_working_tree_was_not_regenerated(tmp_path, capsys):
    """A gate reading the working tree as its baseline would compare a file with itself."""
    corpus, sha = _throwaway(tmp_path, regenerate=False)
    module = _load()
    module.PINNED_PRE_CHANGE_SHA = {"corpus": sha}
    rc = module.main(["--corpus", str(corpus), "--baseline-ref", "HEAD"])
    out = capsys.readouterr().out
    assert rc == 1 and "VERDICT: FAIL" in out
    assert "FAIL  CF_x == -baseline" in out


def test_end_to_end_fails_for_a_corpus_without_a_pinned_sha(tmp_path, capsys):
    corpus, _ = _throwaway(tmp_path)
    rc = _load().main(["--corpus", str(corpus), "--baseline-ref", "HEAD"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL  baseline parquet is the stale surrogate's training data" in out


def test_baseline_ref_is_required():
    with pytest.raises(SystemExit):
        _load().main(["--corpus", str(REPO / "examples" / "prelim_sweep")])
