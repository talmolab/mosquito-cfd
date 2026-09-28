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


def test_missing_step_message_does_not_claim_a_fixed_digit_width(tmp_path):
    # Review correction. The message hardcoded `plt{step:05d}` as "looked for", but the actual
    # matching regex (_PLT_PATTERN, shared with steps()) accepts any digit width and compares by
    # parsed integer -- so once a plotfile directory uses non-5-digit padding, the message names
    # a literal filename the code never actually searches for.
    root = _corpus(tmp_path, steps=(100,))
    run = root / "runs" / "s35_f085_p30"
    (run / "plt00100").rename(run / "plt100")

    corpus = FieldCorpus(root)
    with pytest.raises(ValueError) as excinfo:
        corpus.plotfile("s35_f085_p30", step=999)
    message = str(excinfo.value)
    assert "plt00999" not in message
    assert "999" in message


def test_missing_root_is_self_describing(tmp_path):
    with pytest.raises(ValueError, match="does_not_exist"):
        FieldCorpus(tmp_path / "does_not_exist")


def test_malformed_manifest_surfaces_the_guarded_error(tmp_path):
    root = _corpus(tmp_path)
    (root / "sweep_manifest.json").write_text(json.dumps({"not_configs": []}))
    corpus = FieldCorpus(root)
    with pytest.raises(ValueError, match="configs"):
        corpus.config_ids()


# --- review corrections (tasks 52-53) ---------------------------------------------------------


def test_global_params_returns_exactly_the_kinematic_keys(tmp_path):
    # Task 52. `return dict(config)` survived the original suite, leaking reynolds, split,
    # input_file and index into what a caller hands to to_domino_volume as global_params_values.
    # Key names are literal here, NOT imported from the module under test.
    params = FieldCorpus(_corpus(tmp_path)).global_params("s35_f085_p30")
    assert set(params) == {"stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"}


def test_global_params_raises_on_a_missing_kinematic_key(tmp_path):
    # Review flagged `{k: config[k] for k in GLOBAL_PARAM_KEYS if k in config}` as a silent
    # partial-dict risk: a caller building global_params_values from a shortened dict against a
    # global_params_reference table that happens to also be short by one would misalign
    # positionally with no error anywhere in to_domino_volume. Verified NOT independently
    # reachable through the public API: GLOBAL_PARAM_KEYS is a subset of
    # force_surrogate.dataset._REQUIRED_CONFIG_KEYS, which _configs() already enforces via
    # load_manifest_configs -> _validate_configs for every config, before global_params() ever
    # runs -- so this test exercises that upstream guard end-to-end, not a corpus.py-specific
    # fix. global_params() is still hardened below (unconditional key access instead of a silent
    # `if k in config`) so a future change to that upstream guarantee fails loudly.
    root = _corpus(tmp_path)
    manifest_path = root / "sweep_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["configs"][0]["pitch_amp_deg"]
    manifest_path.write_text(json.dumps(manifest))

    corpus = FieldCorpus(root)
    with pytest.raises(ValueError, match="pitch_amp_deg"):
        corpus.global_params("s35_f085_p30")


def test_manifest_is_parsed_from_disk_only_once_per_instance(tmp_path, monkeypatch):
    # Review correction. _configs() re-parsed sweep_manifest.json from disk on every call, with
    # no caching -- config_ids(), _config() (hence run_dir/global_params/plotfile/snapshot) all
    # go through it. The module docstring says the real corpus root lives on cluster NFS, so this
    # becomes a real per-call cost once F3 builds a DataLoader on top of it.
    import mosquito_cfd.force_surrogate.dataset as fs_dataset

    root = _corpus(tmp_path)
    calls = []
    real = fs_dataset.load_manifest_configs

    def _counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(fs_dataset, "load_manifest_configs", _counting)
    corpus = FieldCorpus(root)
    corpus.config_ids()
    corpus.global_params("s35_f085_p30")
    corpus.steps("s35_f085_p30")
    assert len(calls) == 1, f"expected exactly one manifest parse, got {len(calls)}"


def test_steps_sort_numerically_not_lexically(tmp_path, monkeypatch):
    # Task 53. The regex permits any digit width, and plt10 sorts BEFORE plt2 lexically, so with
    # uniform 5-digit padding lexical and numeric order coincide and a dropped sorted() goes
    # unnoticed.
    #
    # The adverse directory order is FORCED rather than assumed. Relying on the filesystem makes
    # the test's teeth platform-dependent: NTFS happens to yield lexical order (which exposes the
    # mutant), but CI is ubuntu-latest, where ext4 readdir is hash-ordered -- if that order came
    # out ascending, `return found` would survive. Pinning the order makes the check
    # deterministic everywhere.
    root = _corpus(tmp_path, steps=(2, 10, 100))
    run = root / "runs" / "s35_f085_p30"
    for padded, bare in ((2, "plt2"), (10, "plt10")):
        (run / f"plt{padded:05d}").rename(run / bare)

    real_iterdir = Path.iterdir

    def reverse_numeric_iterdir(self):
        # Order by the STEP NUMBER descending, so the raw listing is [100, 10, 2] -- unambiguously
        # the wrong answer. Ordering by name descending would yield plt2, plt10, plt00100, i.e.
        # [2, 10, 100], which is accidentally correct and lets the mutant survive (this test's
        # first version made exactly that mistake).
        def step_of(q):
            digits = q.name[3:]
            return int(digits) if q.name.startswith("plt") and digits.isdigit() else -1

        return iter(sorted(real_iterdir(self), key=step_of, reverse=True))

    monkeypatch.setattr(Path, "iterdir", reverse_numeric_iterdir)
    assert FieldCorpus(root).steps("s35_f085_p30") == [2, 10, 100]
