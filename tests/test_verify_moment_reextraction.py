"""Tests for scripts/verify_moment_reextraction.py (fix-moment-reference-hinge task 26).

The script is the operator-run gate for re-extracting a committed corpus about the hinge. These
tests pin its comparison logic on small synthetic frames (each check must fail on the defect it
exists to catch), and pin against the real repository that it reads its baseline from git and
cannot pass vacuously when the corpus has not been regenerated.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import compute_moment_reference
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN
from mosquito_cfd.force_surrogate.dataset import DATASET_COLUMNS

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "verify_moment_reextraction.py"
OFFSET = np.array([0.0, 1.5, 0.0])
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "7" * 64


def _load():
    spec = importlib.util.spec_from_file_location("verify_moment_reextraction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their module via sys.modules, so register before executing.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _baseline() -> pd.DataFrame:
    """Two configs x 4 rows, CF_m* about the particle origin (the pre-change convention)."""
    rng = np.random.default_rng(0)
    rows = []
    for name, stroke, freq, split in (
        ("s35_f085_p30", 35.0, 0.85, "train"),
        ("s55_f115_p60", 55.0, 1.15, "holdout"),
    ):
        m_ref = compute_moment_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).m_ref
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
                    "CF_x": f[0] / m_ref, "CF_y": f[1] / m_ref, "CF_z": f[2] / m_ref,
                    "CF_mx": m[0] / m_ref, "CF_my": m[1] / m_ref, "CF_mz": m[2] / m_ref,
                }
            )  # fmt: skip
    df = pd.DataFrame(rows)[DATASET_COLUMNS]
    df["config_name"] = df["config_name"].astype("str")
    df["split"] = df["split"].astype("str")
    return df


def _corrected(df: pd.DataFrame, d=OFFSET) -> pd.DataFrame:
    out = df.copy()
    for name, sub in df.groupby("config_name"):
        (stroke,) = sub["stroke_amp_deg"].unique()
        (freq,) = sub["frequency_fstar"].unique()
        m_ref = compute_moment_reference(
            freq, stroke, R_GYRATION, SPAN, CHORD, RHO
        ).m_ref
        idx = sub.index
        out.loc[idx, "CF_mx"] = (
            sub["Mx"] + (d[1] * sub["Fz"] - d[2] * sub["Fy"])
        ) / m_ref
        out.loc[idx, "CF_my"] = (
            sub["My"] + (d[2] * sub["Fx"] - d[0] * sub["Fz"])
        ) / m_ref
        out.loc[idx, "CF_mz"] = (
            sub["Mz"] + (d[0] * sub["Fy"] - d[1] * sub["Fx"])
        ) / m_ref
    return out


def _offsets(df):
    return {name: OFFSET for name in df["config_name"].unique()}


def _failed(checks) -> list[str]:
    return [c.name for c in checks if not c.ok]


def test_correct_reextraction_passes_every_frame_check():
    base = _baseline()
    checks = _load().compare_frames(base, _corrected(base), _offsets(base))
    assert checks and _failed(checks) == []


@pytest.mark.parametrize(
    ("mutate", "expected_failure"),
    [
        (lambda df: df.assign(CF_x=df["CF_x"] * 1.0000001), "unchanged columns"),
        (lambda df: df.assign(Mx=df["Mx"] + 1e-9), "unchanged columns"),
        (lambda df: df.assign(split=df["split"][::-1].to_numpy()), "unchanged columns"),
        (lambda df: df.iloc[:-1], "rows per config"),
        (lambda df: df.drop(columns=["CF_mz"]), "schema"),
    ],
    ids=[
        "CF_x-moved",
        "raw-Mx-moved",
        "split-swapped",
        "row-dropped",
        "column-dropped",
    ],
)
def test_each_frame_check_fails_on_its_defect(mutate, expected_failure):
    base = _baseline()
    checks = _load().compare_frames(base, mutate(_corrected(base)), _offsets(base))
    assert expected_failure in _failed(checks)


def test_unshifted_frame_fails_the_changed_and_algebraic_checks():
    """Comparing the old corpus to itself -- the vacuous case -- must not pass."""
    base = _baseline()
    failed = _failed(_load().compare_frames(base, base.copy(), _offsets(base)))
    assert "CF_mx/CF_mz changed in every config" in failed
    assert "algebraic control (design D11)" in failed


def test_sign_flipped_shift_fails_the_algebraic_control():
    base = _baseline()
    flipped = _corrected(base, d=-OFFSET)
    failed = _failed(_load().compare_frames(base, flipped, _offsets(base)))
    assert failed == ["algebraic control (design D11)"]


def _metadata(offsets, *, docker=DIGEST, dropped=(), sha_names=None):
    return {
        "docker_image": docker,
        "dropped_configs": list(dropped),
        "moment_reference": {
            "point": "wing_hinge",
            "configs": {n: {"offset": list(d)} for n, d in offsets.items()},
        },
        "extraction_inputs": {
            "input_dir": "Z:/runs",
            "csv_sha256": {n: "0" * 64 for n in (sha_names or offsets)},
        },
    }


def test_metadata_checks_pass_for_a_faithful_record():
    offsets = {"a": OFFSET, "b": OFFSET}
    checks = _load().compare_metadata(
        {"docker_image": DIGEST}, _metadata(offsets), offsets
    )
    assert checks and _failed(checks) == []


@pytest.mark.parametrize(
    ("new", "expected_failure"),
    [
        (
            _metadata({"a": OFFSET, "b": OFFSET}, docker=DIGEST.replace("7", "8")),
            "docker_image preserved",
        ),
        (_metadata({"a": OFFSET, "b": OFFSET}, dropped=["b"]), "no dropped configs"),
        (_metadata({"a": OFFSET, "b": -OFFSET}), "recorded offsets match the decks"),
        (
            _metadata({"a": OFFSET, "b": OFFSET}, sha_names=["a"]),
            "every consumed CSV hashed",
        ),
    ],
    ids=["digest-changed", "dropped", "negated-offset", "missing-csv-hash"],
)
def test_each_metadata_check_fails_on_its_defect(new, expected_failure):
    offsets = {"a": OFFSET, "b": OFFSET}
    checks = _load().compare_metadata({"docker_image": DIGEST}, new, offsets)
    assert expected_failure in _failed(checks)


def test_deck_offsets_come_from_the_committed_decks():
    offsets = _load().deck_offsets(REPO / "examples" / "prelim_sweep")
    assert len(offsets) == 27
    for d in offsets.values():
        assert d.tolist() == [0.0, 1.5, 0.0]


def test_gate_comparing_a_committed_corpus_to_itself_fails_and_names_its_baseline(
    capsys,
):
    """With the working tree equal to the baseline, the gate compares a corpus to itself.
    It must FAIL (CF_mx did not change), whatever the corpus's convention, and print the
    baseline blob SHA git reports -- the proof of which side it compared against. (After
    merge, re-verifying needs --baseline-ref set to the pre-change commit.)"""
    corpus = "examples/prelim_sweep"
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", corpus],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    if status.strip():
        pytest.skip(f"{corpus} has local changes; this test needs it equal to HEAD")
    blob = subprocess.run(
        ["git", "rev-parse", f"HEAD:{corpus}/dataset.parquet"],
        cwd=REPO, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip

    rc = _load().main(["--corpus", str(REPO / corpus)])
    out = capsys.readouterr().out
    assert rc == 1
    assert blob in out
    assert "VERDICT: FAIL" in out
    assert "FAIL  CF_mx/CF_mz changed in every config" in out


def test_zero_offset_control_reproduces_a_pre_change_parquet(tmp_path):
    """With the shift forced to zero, the rewired extractor must reproduce, value for value
    across all 22 columns, a parquet written with particle-origin moments."""
    fixture = REPO / "tests" / "fixtures" / "synthetic_ib_particle.csv"
    deck = tmp_path / "inputs" / "deck"
    deck.parent.mkdir()
    deck.write_text(
        "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_y = 0.5\n"
        "particle_inputs.hinge_z = 4.0\n",
        encoding="utf-8",
    )
    cfg = {
        "index": 0, "name": "c", "stroke_amp_deg": 45.0, "frequency_fstar": 1.0,
        "pitch_amp_deg": 45.0, "reynolds": 60.0, "split": "train", "input_file": "inputs/deck",
    }  # fmt: skip
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(json.dumps({"configs": [cfg]}), encoding="utf-8")
    run = tmp_path / "runs" / "c"
    run.mkdir(parents=True)
    run.joinpath("IB_Particle_1.csv").write_bytes(fixture.read_bytes())

    raw = pd.read_csv(fixture)
    m_ref = compute_moment_reference(1.0, 45.0, R_GYRATION, SPAN, CHORD, RHO).m_ref
    module = _load()
    frame, provenance = module.build_with_zero_offset(
        manifest, tmp_path / "runs", "IB_Particle_1.csv"
    )
    assert (
        provenance["c"]["csv_sha256"]
        == hashlib.sha256(fixture.read_bytes()).hexdigest()
    )
    np.testing.assert_array_equal(frame["CF_mx"], raw["Mx"].to_numpy(float) / m_ref)
    np.testing.assert_array_equal(frame["CF_mz"], raw["Mz"].to_numpy(float) / m_ref)

    # The shift is restored afterwards (the patch is scoped, not left behind).
    from mosquito_cfd.force_surrogate import build_dataset

    shifted, _, _ = build_dataset(manifest, {"c": run / "IB_Particle_1.csv"})
    assert not np.allclose(shifted["CF_mx"], frame["CF_mx"])

    # And the frame comparison it feeds is exact across every column.
    checks = module.compare_zero_offset(frame, frame.copy())
    assert _failed(checks) == []
    checks = module.compare_zero_offset(
        frame, frame.assign(CF_mx=frame["CF_mx"] + 1e-15)
    )
    assert _failed(checks) == ["zero-offset control (design D11)"]


def test_a_single_unshifted_config_fails():
    """One config left particle-referenced must not hide among correctly shifted ones."""
    base = _baseline()
    new = _corrected(base)
    one = new["config_name"] == "s55_f115_p60"
    new.loc[one, ["CF_mx", "CF_my", "CF_mz"]] = base.loc[
        one, ["CF_mx", "CF_my", "CF_mz"]
    ]
    failed = _failed(_load().compare_frames(base, new, _offsets(base)))
    assert "CF_mx/CF_mz changed in every config" in failed
    assert "algebraic control (design D11)" in failed


def _git_in(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_end_to_end_compares_the_working_tree_against_the_committed_baseline(
    tmp_path, capsys
):
    """In a throwaway repo: commit a particle-referenced corpus, regenerate it about the hinge
    in the working tree, and the gate PASSES against the committed baseline. A gate that read
    the working tree as its baseline would compare the regenerated file to itself and fail the
    "changed" check -- this is the only test that distinguishes the two."""
    repo = tmp_path / "repo"
    corpus = repo / "corpus"
    (corpus / "inputs").mkdir(parents=True)
    base = _baseline()
    configs = []
    for i, name in enumerate(base["config_name"].unique()):
        deck = f"inputs/inputs.3d.{name}"
        (corpus / deck).write_text(
            "particle_inputs.x = 4.0\nparticle_inputs.y = 2.0\nparticle_inputs.z = 4.0\n"
            "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_y = 0.5\n"
            "particle_inputs.hinge_z = 4.0\n",
            encoding="utf-8",
        )
        sub = base[base["config_name"] == name].iloc[0]
        configs.append(
            {
                "index": i, "name": name, "input_file": deck,
                "stroke_amp_deg": sub["stroke_amp_deg"],
                "frequency_fstar": sub["frequency_fstar"],
                "pitch_amp_deg": 30.0, "reynolds": 42.0, "split": sub["split"],
            }
        )  # fmt: skip
    (corpus / "sweep_manifest.json").write_text(
        json.dumps({"configs": configs}), encoding="utf-8"
    )
    base.to_parquet(corpus / "dataset.parquet", index=False)
    (corpus / "run_metadata.json").write_text(
        json.dumps({"docker_image": DIGEST, "dropped_configs": []}), encoding="utf-8"
    )
    _git_in(repo, "init", "-q")
    _git_in(repo, "add", ".")
    _git_in(
        repo,
        "-c", "user.name=t", "-c", "user.email=t@t",
        "-c", "commit.gpgsign=false", "-c", "core.hooksPath=",
        "commit", "-q", "-m", "base",
    )  # fmt: skip

    # Regenerate in the working tree, as extract_forces.py would.
    _corrected(pd.read_parquet(corpus / "dataset.parquet")).to_parquet(
        corpus / "dataset.parquet", index=False
    )
    (corpus / "run_metadata.json").write_text(
        json.dumps(_metadata(_offsets(base))), encoding="utf-8"
    )

    rc = _load().main(["--corpus", str(corpus)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "VERDICT: PASS" in out
    assert "PASS  algebraic control (design D11)  -- bitwise equal" in out


def test_cf_mz_alone_unshifted_or_wrong_fails():
    """CF_mz is checked in its own right, not only alongside CF_mx: one config with CF_mx
    shifted but CF_mz left particle-referenced, and one with only CF_mz sign-flipped."""
    base = _baseline()
    module = _load()

    stale_mz = _corrected(base)
    one = stale_mz["config_name"] == "s55_f115_p60"
    stale_mz.loc[one, "CF_mz"] = base.loc[one, "CF_mz"]
    failed = _failed(module.compare_frames(base, stale_mz, _offsets(base)))
    assert "CF_mx/CF_mz changed in every config" in failed

    flipped_mz = _corrected(base)
    flipped_mz["CF_mz"] = _corrected(base, d=-OFFSET)["CF_mz"]
    failed = _failed(module.compare_frames(base, flipped_mz, _offsets(base)))
    assert failed == ["algebraic control (design D11)"]


def test_a_non_spanwise_offset_is_refused_rather_than_misjudged():
    """The gate's unchanged-column set assumes d_x = d_z = 0 (only then is CF_my exactly
    invariant). Any other offset must fail clearly, not report a misleading column diff."""
    base = _baseline()
    d = np.array([0.5, 1.5, 0.0])
    new = _corrected(base, d=d)
    failed = _failed(_load().compare_frames(base, new, {n: d for n in _offsets(base)}))
    assert failed == ["offsets are spanwise (d_x = d_z = 0)"]


def test_git_failure_is_reported_with_its_message(tmp_path):
    """A missing ref or path exits with git's own message, not a bare CalledProcessError."""
    with pytest.raises(SystemExit, match="no-such-ref"):
        _load().main(
            [
                "--corpus",
                str(REPO / "examples" / "prelim_sweep"),
                "--baseline-ref",
                "no-such-ref",
            ]
        )


def test_recorded_csv_hashes_are_rechecked_against_the_raw_csvs():
    """With --zero-offset-control the gate re-reads every CSV, so it can confirm the recorded
    csv_sha256 values are the bytes actually on disk, not just that a hash key exists."""
    module = _load()
    good = {"a": {"csv_sha256": "1" * 64}, "b": {"csv_sha256": "2" * 64}}
    meta = {"extraction_inputs": {"csv_sha256": {"a": "1" * 64, "b": "2" * 64}}}
    assert _failed(module.compare_csv_hashes(meta, good)) == []
    meta["extraction_inputs"]["csv_sha256"]["b"] = "3" * 64
    assert _failed(module.compare_csv_hashes(meta, good)) == [
        "recorded CSV hashes match the raw CSVs"
    ]
