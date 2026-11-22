"""Live-spec claim guard (change ``fix-stale-spec-claims``, issues #115 and #170).

The force-surrogate and flapping-wing-validation specs once froze corpus results into their
requirements, and the numbers went stale as the corpora were rebuilt (#115). This module checks
each spec's *effective* text (the live spec with every active change's delta applied):

- the retired claims stay out (a tripwire, with a stale example and corrective text per pattern);
- every number in the guarded requirements is registered as recomputed, fixture or declared.

The helpers are in ``_spec_claims``. This first part unit-tests them on synthetic inputs.
"""

from __future__ import annotations

from pathlib import Path

import _spec_claims as sc
import pytest

# --------------------------------------------------------------------------------------------
# requirement_blocks
# --------------------------------------------------------------------------------------------

_LIVE = """# cap Specification

## Purpose

Text.

## Requirements

### Requirement: Alpha

Alpha body with 1.5.

#### Scenario: a

- **Given** x

### Requirement: Beta

Beta body.

#### Scenario: b

- **Given** y

### Requirement: Gamma

Gamma body.

#### Scenario: c

- **Given** z
"""


def test_requirement_blocks_splits_on_requirement_headings():
    blocks = sc.requirement_blocks(_LIVE)
    assert list(blocks) == ["Alpha", "Beta", "Gamma"]
    assert blocks["Alpha"].startswith("### Requirement: Alpha")
    assert "Alpha body with 1.5." in blocks["Alpha"]
    assert "Beta" not in blocks["Alpha"]
    assert blocks["Gamma"].rstrip().endswith("- **Given** z")


def test_requirement_blocks_is_crlf_safe():
    blocks = sc.requirement_blocks(_LIVE.replace("\n", "\r\n"))
    assert list(blocks) == ["Alpha", "Beta", "Gamma"]
    assert "\r" not in "".join(blocks)


def test_an_unknown_section_ends_a_block_and_is_not_applied():
    delta = (
        "## ADDED Requirements\n\n### Requirement: New\n\nNew body.\n\n#### Scenario: n\n\n"
        "- **Given** q\n\n## Cross-References\n\n- [Other](../other/spec.md)\n"
    )
    sections = sc.delta_sections(delta)
    assert list(sections["ADDED"]) == ["New"]
    assert "Cross-References" not in sections["ADDED"]["New"]
    assert "Other" not in sections["ADDED"]["New"]


# --------------------------------------------------------------------------------------------
# effective_spec / effective_text / effective_block
# --------------------------------------------------------------------------------------------


def _tree(
    tmp_path: Path, changes: dict[str, str], live: str = _LIVE
) -> tuple[Path, Path]:
    specs = tmp_path / "specs"
    (specs / "cap").mkdir(parents=True)
    (specs / "cap" / "spec.md").write_text(live, encoding="utf-8")
    changes_dir = tmp_path / "changes"
    changes_dir.mkdir()
    for change, delta in changes.items():
        d = changes_dir / change / "specs" / "cap"
        d.mkdir(parents=True)
        (d / "spec.md").write_text(delta, encoding="utf-8")
    return specs, changes_dir


def _block(name: str, body: str) -> str:
    return f"### Requirement: {name}\n\n{body}\n\n#### Scenario: s\n\n- **Given** g\n"


def test_delta_replaces_drops_and_appends(tmp_path):
    delta = (
        "## MODIFIED Requirements\n\n" + _block("Alpha", "Alpha NEW body.") + "\n"
        "## REMOVED Requirements\n\n" + _block("Beta", "gone") + "\n"
        "## ADDED Requirements\n\n" + _block("Delta", "Delta body.")
    )
    specs, changes = _tree(tmp_path, {"chg": delta})
    eff = sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)
    assert list(eff) == ["Alpha", "Gamma", "Delta"]
    assert eff["Alpha"] == [("chg", _block("Alpha", "Alpha NEW body.").rstrip("\n"))]
    assert eff["Gamma"][0][0] == "live"
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "Alpha NEW body." in text and "Alpha body with 1.5." not in text
    assert "Beta body." not in text and "Delta body." in text


def test_archive_non_directories_and_other_capabilities_are_ignored(tmp_path):
    specs, changes = _tree(tmp_path, {})
    archived = changes / "archive" / "2026-01-01-old" / "specs" / "cap"
    archived.mkdir(parents=True)
    (archived / "spec.md").write_text(
        "## MODIFIED Requirements\n\n" + _block("Alpha", "ARCHIVED"), encoding="utf-8"
    )
    other = changes / "elsewhere" / "specs" / "other-cap"
    other.mkdir(parents=True)
    (other / "spec.md").write_text(
        "## MODIFIED Requirements\n\n" + _block("Alpha", "OTHER CAP"), encoding="utf-8"
    )
    (changes / "README.md").write_text("not a change", encoding="utf-8")
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "ARCHIVED" not in text and "OTHER CAP" not in text
    assert "Alpha body with 1.5." in text


@pytest.mark.parametrize(
    ("delta", "match"),
    [
        ("## MODIFIED Requirements\n\n" + _block("Nope", "x"), "Nope"),
        ("## REMOVED Requirements\n\n" + _block("Nope", "x"), "Nope"),
        ("## ADDED Requirements\n\n" + _block("Alpha", "x"), "Alpha"),
    ],
)
def test_inconsistent_deltas_raise_naming_change_and_requirement(
    tmp_path, delta, match
):
    specs, changes = _tree(tmp_path, {"bad-change": delta})
    with pytest.raises(ValueError, match=match) as err:
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)
    assert "bad-change" in str(err.value)


def test_renamed_section_raises(tmp_path):
    delta = "## RENAMED Requirements\n\n- FROM: `### Requirement: Alpha`\n- TO: `### Requirement: A2`\n"
    specs, changes = _tree(tmp_path, {"chg": delta})
    with pytest.raises(NotImplementedError, match="RENAMED"):
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)


def test_two_changes_adding_one_name_raise(tmp_path):
    add = "## ADDED Requirements\n\n" + _block("Delta", "x")
    specs, changes = _tree(tmp_path, {"one": add, "two": add})
    with pytest.raises(ValueError, match="Delta"):
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)


def test_two_changes_modifying_one_requirement(tmp_path):
    specs, changes = _tree(
        tmp_path,
        {
            "first-change": "## MODIFIED Requirements\n\n" + _block("Alpha", "FIRST"),
            "second-change": "## MODIFIED Requirements\n\n" + _block("Alpha", "SECOND"),
        },
    )
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "FIRST" in text and "SECOND" in text  # a whole-spec scan reads both variants
    with pytest.raises(ValueError) as err:
        sc.effective_block("cap", "Alpha", specs_dir=specs, changes_dir=changes)
    message = str(err.value)
    assert "first-change" in message and "second-change" in message
    assert "second to merge" in message
    # an unshared requirement still builds
    assert "Gamma body." in sc.effective_block(
        "cap", "Gamma", specs_dir=specs, changes_dir=changes
    )


def test_effective_block_of_an_absent_requirement_names_the_registry(tmp_path):
    specs, changes = _tree(tmp_path, {})
    with pytest.raises(KeyError, match="GUARDED"):
        sc.effective_block("cap", "Missing", specs_dir=specs, changes_dir=changes)


def test_default_paths_resolve_from_the_module_at_call_time(tmp_path, monkeypatch):
    specs, changes = _tree(
        tmp_path, {"chg": "## MODIFIED Requirements\n\n" + _block("Alpha", "PATCHED")}
    )
    monkeypatch.setattr(sc, "SPECS_DIR", specs)
    monkeypatch.setattr(sc, "CHANGES_DIR", changes)
    monkeypatch.chdir(tmp_path.parent)
    assert "PATCHED" in sc.effective_text("cap")
    # and the real defaults point at the repository, not the working directory
    monkeypatch.undo()
    repo = Path(__file__).resolve().parents[1]
    assert sc.SPECS_DIR == repo / "openspec" / "specs"
    assert sc.CHANGES_DIR == repo / "openspec" / "changes"


# --------------------------------------------------------------------------------------------
# number_tokens and format_like
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("a 256x128x256 grid", ["256", "128", "256"]),
        ("a 64×32×64 grid", ["64", "32", "64"]),
        ("≈ 3.7×10⁶× faster", ["3.7", "10"]),
        ("within 1e-9", ["1e-9"]),
        ("fell to 3.06e-4", ["3.06e-4"]),
        ("5.17e7 rows", ["5.17e7"]),
        ("N=12,535 rows", ["12,535"]),
        (">1,000× speedup", ["1,000"]),
        ("LF-newline UTF-8 and ISO-8601", ["8", "8601"]),
        ("at t = T/4", ["4"]),
        ("arrays [1, 3] and [5, 7]", ["1", "3", "5", "7"]),
        ("k = −1 case", ["1"]),
        ("k ≈ 3.120.", ["3.120"]),
        ("s45_f115_p60 #115 CC-4 design D6 CC-F1 sha256: R² x ３ y", []),
    ],
)
def test_number_tokens(text, tokens):
    assert sc.number_tokens(text) == tokens


def test_superscript_after_a_digit_is_found():
    found = sc.superscripts_after_digits(
        "3.72×10⁶, ~10³× and 1×10⁻⁹; R² and Σt² are fine"
    )
    assert found == ["0⁶", "0³", "0⁻"]


@pytest.mark.parametrize(
    ("value", "literal", "expected"),
    [
        (3.1197210117, "3.120", "3.120"),
        (3722400.0, "3.72e6", "3.72e6"),
        (5.17e7, "5.17e7", "5.17e7"),
        (3.0607e-4, "3.06e-4", "3.06e-4"),
        (12535, "12,535", "12,535"),
        (310.34, "310", "310"),
        (144.0, "144", "144"),
        (2.5, "2", "2"),  # Python rounds half to even
        (3.1187, "3.119", "3.119"),
    ],
)
def test_format_like(value, literal, expected):
    assert sc.format_like(value, literal) == expected


def test_format_like_detects_a_drift_in_the_last_digit_and_in_the_exponent():
    assert sc.format_like(3.1207, "3.120") == "3.121"
    assert sc.format_like(3.72e7, "3.72e6") == "3.72e7"
