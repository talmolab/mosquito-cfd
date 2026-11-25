"""Pre-registration pinning and precedence checks (add-settled-beat-corpus tasks 3.2 and 3.3)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate import settling
from mosquito_cfd.force_surrogate.settling import (
    GATED_FILES,
    check_precedence,
    constants_mismatches,
    read_preregistered_constants,
    spec_constants,
)

REPO = Path(__file__).resolve().parents[1]
PREREG = REPO / "examples" / "settling_check" / "PREREGISTRATION.md"
CHANGE_DELTA = (
    REPO
    / "openspec"
    / "changes"
    / "add-settled-beat-corpus"
    / "specs"
    / "force-surrogate"
    / "spec.md"
)
LIVE_SPEC = REPO / "openspec" / "specs" / "force-surrogate" / "spec.md"


# --------------------------------------------------------------------------- pinning (3.2)


def test_preregistered_constants_equal_the_module():
    declared = read_preregistered_constants(PREREG)
    assert set(declared) == set(settling.PREREGISTERED_NAMES)
    assert len(settling.PREREGISTERED_NAMES) == 12
    assert constants_mismatches(declared) == []


def test_spec_states_the_same_constants():
    # The change's delta while the change is active; the live spec once it is archived.
    source = CHANGE_DELTA if CHANGE_DELTA.exists() else LIVE_SPEC
    assert spec_constants(source) == read_preregistered_constants(PREREG)


def test_missing_anchor_raises(tmp_path):
    bad = tmp_path / "PREREGISTRATION.md"
    bad.write_text(
        PREREG.read_text(encoding="utf-8").replace(
            "<!-- settling-constants:end -->", ""
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="settling-constants"):
        read_preregistered_constants(bad)


def test_mutated_file_fails(tmp_path):
    bad = tmp_path / "PREREGISTRATION.md"
    bad.write_text(
        PREREG.read_text(encoding="utf-8").replace(
            "SETTLED_TOLERANCE = 0.01", "SETTLED_TOLERANCE = 0.02"
        ),
        encoding="utf-8",
    )
    mismatches = constants_mismatches(read_preregistered_constants(bad))
    assert any("SETTLED_TOLERANCE" in m for m in mismatches)


def test_mutated_module_constant_fails(monkeypatch):
    monkeypatch.setattr(settling, "SETTLED_TOLERANCE", 0.02)
    mismatches = constants_mismatches(read_preregistered_constants(PREREG))
    assert mismatches == ["SETTLED_TOLERANCE: preregistered 0.01, settling.py 0.02"]


def test_unparseable_constant_raises(tmp_path):
    bad = tmp_path / "PREREGISTRATION.md"
    bad.write_text(
        PREREG.read_text(encoding="utf-8").replace("MIN_BEATS = 5", "MIN_BEATS five"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="MIN_BEATS"):
        read_preregistered_constants(bad)


# --------------------------------------------------------------------------- precedence (3.3)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(tmp_path: Path, n_runs: int = 2) -> tuple[Path, Path]:
    """A repo-shaped tree with a settling directory and the gated files."""
    root = tmp_path / "repo"
    settling_dir = root / "examples" / "settling_check"
    settling_dir.mkdir(parents=True)
    for rel in GATED_FILES:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"content of {rel}\n", encoding="utf-8")
    manifest = {"runs": [{"name": f"run{i}"} for i in range(n_runs)]}
    (settling_dir / "settling_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return root, settling_dir


def _record(root: Path, settling_dir: Path, name: str) -> None:
    records = settling_dir / "records"
    records.mkdir(exist_ok=True)
    payload = {
        "run": name,
        "file_sha256": {rel: _sha(root / rel) for rel in GATED_FILES},
    }
    (records / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_nothing_to_check_before_any_record_or_decision(tmp_path):
    root, settling_dir = _tree(tmp_path)
    assert check_precedence(settling_dir, repo_root=root) == []


def test_unchanged_files_pass(tmp_path):
    root, settling_dir = _tree(tmp_path)
    for name in ("run0", "run1"):
        _record(root, settling_dir, name)
    (settling_dir / "DECISION.md").write_text("N* = 7\n", encoding="utf-8")
    assert check_precedence(settling_dir, repo_root=root) == []


def test_unrecorded_edit_fails_and_a_matching_deviation_passes(tmp_path):
    root, settling_dir = _tree(tmp_path)
    _record(root, settling_dir, "run0")
    prereg = root / GATED_FILES[0]
    old = _sha(prereg)
    prereg.write_text("edited\n", encoding="utf-8")
    failures = check_precedence(settling_dir, repo_root=root)
    assert failures and GATED_FILES[0] in failures[0]
    deviation = {
        "file": GATED_FILES[0],
        "old_sha256": old,
        "new_sha256": _sha(prereg),
        "reason": "typo",
        "pr": "#999",
    }
    (settling_dir / "deviations.json").write_text(
        json.dumps([deviation]), encoding="utf-8"
    )
    assert check_precedence(settling_dir, repo_root=root) == []


def test_deviation_with_wrong_hash_or_missing_reason_does_not_count(tmp_path):
    root, settling_dir = _tree(tmp_path)
    _record(root, settling_dir, "run0")
    prereg = root / GATED_FILES[0]
    old = _sha(prereg)
    prereg.write_text("edited\n", encoding="utf-8")
    for deviation in (
        {
            "file": GATED_FILES[0],
            "old_sha256": "0" * 64,
            "new_sha256": _sha(prereg),
            "reason": "typo",
            "pr": "#1",
        },
        {
            "file": GATED_FILES[0],
            "old_sha256": old,
            "new_sha256": _sha(prereg),
            "reason": "",
            "pr": "#1",
        },
    ):
        (settling_dir / "deviations.json").write_text(
            json.dumps([deviation]), encoding="utf-8"
        )
        assert check_precedence(settling_dir, repo_root=root)


def test_edited_deck_generator_is_gated_too(tmp_path):
    root, settling_dir = _tree(tmp_path)
    _record(root, settling_dir, "run0")
    (root / GATED_FILES[1]).write_text("edited\n", encoding="utf-8")
    failures = check_precedence(settling_dir, repo_root=root)
    assert failures and GATED_FILES[1] in failures[0]


@pytest.mark.parametrize("artifact", ["DECISION.md", "settling_report.json"])
def test_decision_or_report_without_records_fails(tmp_path, artifact):
    root, settling_dir = _tree(tmp_path)
    (settling_dir / artifact).write_text("{}\n", encoding="utf-8")
    failures = check_precedence(settling_dir, repo_root=root)
    assert len(failures) == 2
    assert all("has no run record" in f for f in failures)
    assert any("run0" in f for f in failures) and any("run1" in f for f in failures)


def test_decision_with_too_few_records_fails(tmp_path):
    root, settling_dir = _tree(tmp_path, n_runs=3)
    _record(root, settling_dir, "run0")
    (settling_dir / "DECISION.md").write_text("N* = 7\n", encoding="utf-8")
    assert check_precedence(settling_dir, repo_root=root)


def test_record_without_hashes_fails(tmp_path):
    root, settling_dir = _tree(tmp_path)
    records = settling_dir / "records"
    records.mkdir()
    (records / "run0.json").write_text(json.dumps({"run": "run0"}), encoding="utf-8")
    assert check_precedence(settling_dir, repo_root=root)


def test_committed_settling_directory_passes():
    assert check_precedence(REPO / "examples" / "settling_check", repo_root=REPO) == []
