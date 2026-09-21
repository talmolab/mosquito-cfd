"""Tests for mosquito_cfd.field_surrogate.corpus (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mosquito_cfd.field_surrogate.corpus import FieldCorpus

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lev_boxlib_plt"

_KINEMATICS = {
    "stroke_amp_deg": 35.0,
    "frequency_fstar": 0.85,
    "pitch_amp_deg": 30.0,
    "reynolds": 42.5537291206389,
    "split": "train",
}


def _manifest(names: list[str]) -> dict:
    return {
        "schema_version": 1,
        "configs": [
            {
                "name": name,
                "index": i,
                "input_file": f"inputs/inputs.3d.{name}",
                **_KINEMATICS,
            }
            for i, name in enumerate(names)
        ],
    }


def _corpus(tmp_path: Path, names=("s35_f085_p30",), steps=(100,)) -> Path:
    root = tmp_path / "corpus"
    (root / "runs").mkdir(parents=True)
    (root / "sweep_manifest.json").write_text(json.dumps(_manifest(list(names))))
    for name in names:
        for step in steps:
            shutil.copytree(FIXTURE, root / "runs" / name / f"plt{step:05d}")
    return root


def test_resolves_a_snapshot_by_config_and_step(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))

    assert corpus.config_ids() == ["s35_f085_p30"]
    assert corpus.steps("s35_f085_p30") == [100]

    params = corpus.global_params("s35_f085_p30")
    assert params["stroke_amp_deg"] == 35.0
    assert params["frequency_fstar"] == 0.85
    assert params["pitch_amp_deg"] == 30.0

    snap = corpus.snapshot("s35_f085_p30", step=100)
    assert snap.time == pytest.approx(0.5)
    assert snap.arrays["u"].shape == (6, 6, 6)


def test_steps_come_from_disk_not_from_plot_int(tmp_path):
    # A run can be truncated -- 15 of 27 configs were at ns.cfl = 0.3 -- so the deck's plot_int
    # is not evidence about which plotfiles exist.
    root = _corpus(tmp_path, names=("a", "b"), steps=(100, 200))
    shutil.rmtree(root / "runs" / "b" / "plt00200")

    corpus = FieldCorpus(root)
    assert corpus.steps("a") == [100, 200]
    assert corpus.steps("b") == [100]


def test_steps_ignore_non_plotfile_entries_and_are_deterministic(tmp_path):
    root = _corpus(tmp_path, steps=(100, 1000))
    run = root / "runs" / "s35_f085_p30"
    (run / "plt00200").write_text("a file, not a directory")
    (run / "plt00300.old").mkdir()
    (run / "pltXXXXX").mkdir()

    corpus = FieldCorpus(root)
    assert corpus.steps("s35_f085_p30") == [100, 1000]
    assert corpus.steps("s35_f085_p30") == corpus.steps("s35_f085_p30")


def test_missing_config_is_self_describing(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))
    with pytest.raises(ValueError, match="nope") as excinfo:
        corpus.snapshot("nope", step=100)
    assert "s35_f085_p30" in str(excinfo.value)


def test_missing_step_is_self_describing(tmp_path):
    corpus = FieldCorpus(_corpus(tmp_path))
    with pytest.raises(ValueError) as excinfo:
        corpus.snapshot("s35_f085_p30", step=999)
    message = str(excinfo.value)
    assert "999" in message
    assert "plt00999" in message or "s35_f085_p30" in message


def test_missing_root_is_self_describing(tmp_path):
    with pytest.raises(ValueError, match="does_not_exist"):
        FieldCorpus(tmp_path / "does_not_exist")


def test_malformed_manifest_surfaces_the_guarded_error(tmp_path):
    root = _corpus(tmp_path)
    (root / "sweep_manifest.json").write_text(json.dumps({"not_configs": []}))
    corpus = FieldCorpus(root)
    with pytest.raises(ValueError, match="configs"):
        corpus.config_ids()
