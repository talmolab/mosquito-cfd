"""Structural guard for the ``/review-openspec`` command (OpenSpec change
``update-review-openspec-reviewers``, capability ``review-openspec-skill``).

``.claude/commands/review-openspec.md`` is a prompt, not code, so nothing else notices when a
subagent's ``model`` line, Subagent 6's launch rules, or the synthesis template drift. This test
pins the text contract from the spec. It cannot check what the orchestrating model does at runtime
(that is the manual smoke run in the change's tasks.md).

Every anchor is searched only inside its own bounded section (design D4), matched
case-insensitively, whitespace-collapsed and on word boundaries, so text elsewhere in the file can
never stand in for a deleted anchor. Content failures raise ``AssertionError`` naming the subagent
or anchor, never ``KeyError``/``IndexError``/``AttributeError`` (convention of
``tests/_readme_guards.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SKILL = (
    Path(__file__).resolve().parents[1] / ".claude" / "commands" / "review-openspec.md"
)

# --- Anchors (the spec scenarios are the source of truth for every string below) -------------

EXPECTED_MODELS = {
    1: "sonnet",
    2: "opus",
    3: "opus",
    4: "sonnet",
    5: "sonnet",
    6: "opus",
}

# Stem anchors match as a word prefix; every other anchor is word-bounded on both sides.
STEMS = frozenset({"normaliz", "reference point", "inherit"})

INTRO_REQUIRED = ("plus a conditional 6th",)
INTRO_FORBIDDEN = ("launches **5 specialized subagents in parallel**",)

STEP3_PASS_THROUGH = "Pass each subagent's `model` field to the Agent tool exactly as given; do not omit it."
STEP3_REQUIRED = (
    STEP3_PASS_THROUGH,
    "Launch ALL applicable subagents",
    "single message",
    "decide whether Subagent 6 runs",
)
STEP3_FORBIDDEN_INHERIT = "inherit"
STEP3_FORBIDDEN_OLD_COUNT = "Launch ALL 5 subagents"

RUN_CONDITION_LABEL = "**Run condition:**"
IF_UNCLEAR_LABEL = "**If unclear:**"
WHEN_SKIPPED_LABEL = "**When skipped:**"
FAILURE_CLASSES_LABEL = "**Failure classes:**"

RUN_CONDITION = (
    "solver decks",
    "geometry",
    "kinematics",
    "force, moment and coefficient computation",
    "frames",
    "units",
    "timestep and grid settings",
    "surrogate",
    "metrics",
    "convention document",
    "scientific claim",
    "figure",
    "quoted physical or statistical value",
)
IF_UNCLEAR = ("launch Subagent 6",)
SKIP_TEXT = "skipped: no numerics or scientific claims touched"

AUTHORITY_AND_METHOD = (
    "docs/coordinate-convention.md",
    "flag, do not resolve",
    "recompute",
    "VERIFIED / CONTRADICTED / UNVERIFIABLE",
)
FAILURE_CLASSES = (
    "sign and frame",
    "reference point",
    "normaliz",
    "units",
    "CFL",
    "worst case",
    "5 seeds",
    "known-answer",
)

STEP4_REQUIRED = (
    "physics/convention/units errors",
    "Numerical/physical correctness risk: LOW/MEDIUM/HIGH",
    "N/A (Subagent 6 skipped: <reason>)",
    "### 6. Math & Physics",
    SKIP_TEXT,
)

CI_COMMAND = 'uv run pytest -v -m "not gpu"'

# --- Matching ---------------------------------------------------------------------------------


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has(text: str, anchor: str) -> bool:
    """Case-insensitive, whitespace-collapsed, word-bounded (prefix-only for STEMS) match."""
    pattern = r"(?<!\w)" + re.escape(_collapse(anchor))
    if anchor not in STEMS:
        pattern += r"(?!\w)"
    return re.search(pattern, _collapse(text), re.IGNORECASE) is not None


def _require(text: str, anchors: tuple[str, ...], where: str) -> None:
    for anchor in anchors:
        if not _has(text, anchor):
            raise AssertionError(f"{where}: missing anchor {anchor!r}")


def _forbid(text: str, anchor: str, where: str) -> None:
    if _has(text, anchor):
        raise AssertionError(f"{where}: must not contain {anchor!r}")


# --- Section helpers (design D4) --------------------------------------------------------------

_SUBAGENT_HEADING = re.compile(r"^### Subagent (\d+):", re.MULTILINE)
_SECTION_END = re.compile(r"^(?:### Subagent \d+:|---[ \t]*$|## )", re.MULTILINE)
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_SPEC_LINE = re.compile(r'(\w+): "([^"]*)"')
_BOLD_LABEL_LINE = re.compile(r"^\*\*[^*]+:\*\*")


def _read_skill() -> str:
    if not SKILL.is_file():
        raise AssertionError(f"skill file missing: {SKILL}")
    return SKILL.read_text(encoding="utf-8")


def _subagent_sections(text: str) -> list[tuple[int, int, str]]:
    """Return ``(number, heading offset, section text)`` in file order.

    A section ends at the next ``### Subagent N:`` heading, a ``---`` line, or a ``## `` heading,
    so the last subagent never absorbs Step 4.
    """
    sections: list[tuple[int, int, str]] = []
    seen: set[int] = set()
    for match in _SUBAGENT_HEADING.finditer(text):
        number = int(match.group(1))
        if number in seen:
            raise AssertionError(f"Subagent {number}: duplicate section heading")
        seen.add(number)
        end = _SECTION_END.search(text, match.end())
        body = text[match.end() : end.start() if end else len(text)]
        sections.append((number, match.start(), body))
    return sections


def _section(text: str, number: int) -> str:
    for n, _, body in _subagent_sections(text):
        if n == number:
            return body
    raise AssertionError(f"no Subagent {number} section")


def _spec_block(number: int, section: str) -> dict[str, str]:
    fence = _FENCE.search(section)
    if fence is None:
        raise AssertionError(f"Subagent {number}: no fenced spec block")
    body = fence.group(1)
    if "subagent_type:" not in body:
        raise AssertionError(
            f"Subagent {number}: first fenced block is not the spec block"
        )
    fields: dict[str, str] = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        match = _SPEC_LINE.fullmatch(line.strip())
        if match is None:
            raise AssertionError(
                f"Subagent {number}: malformed or unquoted spec line {line.strip()!r}"
            )
        key, value = match.groups()
        if key in fields:
            raise AssertionError(
                f"Subagent {number}: duplicate {key!r} line in spec block"
            )
        fields[key] = value
    return fields


def _model(number: int, section: str) -> str:
    fields = _spec_block(number, section)
    if "model" not in fields:
        raise AssertionError(f"Subagent {number} has no model")
    return fields["model"]


def _prompt_template(section: str) -> str:
    """The ``> `` lines with the marker stripped; a bare ``>`` or any other line becomes blank."""
    lines = []
    for line in section.splitlines():
        if line.startswith("> "):
            lines.append(line[2:])
        else:
            lines.append("")
    return "\n".join(lines)


def _labelled_block(text: str, label: str, where: str) -> str:
    """From a line starting with ``label`` to the next blank line or bold-label line."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if line.startswith(label):
            block = [line[len(label) :]]
            for following in lines[start + 1 :]:
                if not following.strip() or _BOLD_LABEL_LINE.match(following):
                    break
                block.append(following)
            return "\n".join(block)
    raise AssertionError(f"{where}: no {label} block")


def _between(text: str, start: str, end: str, where: str) -> str:
    start_match = re.search(start, text, re.MULTILINE)
    if start_match is None:
        raise AssertionError(f"{where}: start heading {start!r} not found")
    end_match = re.compile(end, re.MULTILINE).search(text, start_match.end())
    if end_match is None:
        raise AssertionError(f"{where}: end heading {end!r} not found")
    return text[start_match.end() : end_match.start()]


def _intro(text: str) -> str:
    match = re.search(r"^## Step 1", text, re.MULTILINE)
    if match is None:
        raise AssertionError("intro: '## Step 1' heading not found")
    return text[: match.start()]


def _step3_preamble(text: str) -> str:
    return _between(text, r"^## Step 3", r"^### Subagent", "Step 3")


def _step4(text: str) -> str:
    return _between(text, r"^## Step 4", r"^## Step 5", "Step 4")


# --- Checks (shared by the real-file tests and the synthetic parser tests) -------------------


def check_models(text: str) -> None:
    sections = _subagent_sections(text)
    for number, _, body in sections:
        if number in EXPECTED_MODELS:
            model = _model(number, body)
            if model != EXPECTED_MODELS[number]:
                raise AssertionError(
                    f"Subagent {number}: model {model!r}, expected {EXPECTED_MODELS[number]!r}"
                )
    numbers = [number for number, _, _ in sections]
    if numbers != sorted(EXPECTED_MODELS):
        raise AssertionError(f"expected Subagents 1-6 in order, found {numbers}")
    step4 = re.search(r"^## Step 4", text, re.MULTILINE)
    if step4 is None:
        raise AssertionError("'## Step 4' heading not found")
    for number, offset, _ in sections:
        if offset > step4.start():
            raise AssertionError(f"Subagent {number}: section is after '## Step 4'")


def check_step3(text: str) -> None:
    preamble = _step3_preamble(text)
    _require(preamble, STEP3_REQUIRED, "Step 3")
    _forbid(preamble, STEP3_FORBIDDEN_INHERIT, "Step 3")
    _forbid(preamble, STEP3_FORBIDDEN_OLD_COUNT, "Step 3")


def check_intro(text: str) -> None:
    intro = _intro(text)
    _require(intro, INTRO_REQUIRED, "intro")
    for anchor in INTRO_FORBIDDEN:
        _forbid(intro, anchor, "intro")


def check_run_condition(text: str) -> None:
    block = _labelled_block(_section(text, 6), RUN_CONDITION_LABEL, "Subagent 6")
    _require(block, RUN_CONDITION, f"Subagent 6 {RUN_CONDITION_LABEL}")


def check_if_unclear(text: str) -> None:
    block = _labelled_block(_section(text, 6), IF_UNCLEAR_LABEL, "Subagent 6")
    _require(block, IF_UNCLEAR, f"Subagent 6 {IF_UNCLEAR_LABEL}")


def check_when_skipped(text: str) -> None:
    block = _labelled_block(_section(text, 6), WHEN_SKIPPED_LABEL, "Subagent 6")
    _require(block, (SKIP_TEXT,), f"Subagent 6 {WHEN_SKIPPED_LABEL}")


def check_authority_and_method(text: str) -> None:
    template = _prompt_template(_section(text, 6))
    _require(template, AUTHORITY_AND_METHOD, "Subagent 6 prompt template")


def check_failure_classes(text: str) -> None:
    template = _prompt_template(_section(text, 6))
    block = _labelled_block(
        template, FAILURE_CLASSES_LABEL, "Subagent 6 prompt template"
    )
    _require(block, FAILURE_CLASSES, f"Subagent 6 {FAILURE_CLASSES_LABEL}")


def check_step4(text: str) -> None:
    _require(_step4(text), STEP4_REQUIRED, "Step 4")


def check_ci_command(text: str) -> None:
    for number in (2, 3):
        _require(_section(text, number), (CI_COMMAND,), f"Subagent {number}")


# --- Synthetic documents for the parser unit tests --------------------------------------------


def _subagent(number: int, spec: str, body: str = "> Prompt.") -> str:
    return f"### Subagent {number}: Name\n\n```\n{spec}\n```\n\n{body}\n"


def _doc(
    *sections: str, before_step4: str = "---\n\n", step4: str = "Template."
) -> str:
    return (
        "# Title\n\n## Step 1: One\n\n## Step 3: Launch\n\n"
        + "\n".join(sections)
        + f"\n{before_step4}## Step 4: Synthesize\n\n{step4}\n\n## Step 5: Present\n"
    )


_SPEC_OK = 'subagent_type: "general-purpose"\nmodel: "opus"\ndescription: "x"'

# --- Parser unit tests ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "before_step4", ["---\n\n", ""], ids=["rule-before-step4", "no-rule"]
)
def test_last_section_does_not_swallow_step4(before_step4):
    text = _doc(
        _subagent(6, _SPEC_OK, f"{WHEN_SKIPPED_LABEL} nothing here."),
        before_step4=before_step4,
        step4=f"### 6. Math & Physics\n{SKIP_TEXT}",
    )
    with pytest.raises(AssertionError, match="Subagent 6"):
        check_when_skipped(text)


def test_parser_rejects_duplicate_subagent_number():
    text = _doc(_subagent(6, _SPEC_OK), _subagent(6, _SPEC_OK))
    with pytest.raises(AssertionError, match="Subagent 6: duplicate"):
        _subagent_sections(text)


def test_parser_rejects_missing_model():
    text = _doc(_subagent(1, 'subagent_type: "general-purpose"\ndescription: "x"'))
    with pytest.raises(AssertionError, match="Subagent 1 has no model"):
        check_models(text)


def test_parser_rejects_duplicate_model_key():
    spec = 'subagent_type: "general-purpose"\nmodel: "sonnet"\nmodel: "opus"'
    with pytest.raises(AssertionError, match="Subagent 1: duplicate 'model'"):
        check_models(_doc(_subagent(1, spec)))


def test_parser_rejects_unquoted_model():
    spec = 'subagent_type: "general-purpose"\nmodel: sonnet'
    with pytest.raises(AssertionError, match="Subagent 1: malformed or unquoted"):
        check_models(_doc(_subagent(1, spec)))


def test_parser_rejects_section_without_fence():
    text = _doc("### Subagent 1: Name\n\nNo spec block.\n")
    with pytest.raises(AssertionError, match="Subagent 1: no fenced spec block"):
        check_models(text)


def test_parser_requires_spec_block_first():
    section = (
        '### Subagent 1: Name\n\n```\nexample: "x"\n```\n\n```\n' + _SPEC_OK + "\n```\n"
    )
    with pytest.raises(AssertionError, match="Subagent 1: first fenced block"):
        check_models(_doc(section))


def test_parser_ignores_model_outside_fence():
    spec = 'subagent_type: "general-purpose"\ndescription: "x"'
    text = _doc(_subagent(1, spec, '> model: "sonnet"'))
    with pytest.raises(AssertionError, match="Subagent 1 has no model"):
        check_models(text)


def test_labelled_block_ends_at_blank_line():
    text = _doc(
        _subagent(6, _SPEC_OK, f"{IF_UNCLEAR_LABEL} decide.\n\nlaunch Subagent 6")
    )
    with pytest.raises(AssertionError, match="launch Subagent 6"):
        check_if_unclear(text)


def test_labelled_paragraphs_do_not_merge():
    body = (
        f"{RUN_CONDITION_LABEL} solver decks.\n"
        f"{IF_UNCLEAR_LABEL} decide.\n"
        f"{WHEN_SKIPPED_LABEL} launch Subagent 6"
    )
    with pytest.raises(AssertionError, match="launch Subagent 6"):
        check_if_unclear(_doc(_subagent(6, _SPEC_OK, body)))


def test_prompt_template_keeps_quoted_paragraphs_apart():
    body = f"> {FAILURE_CLASSES_LABEL}\n>\n> - sign and frame conventions"
    with pytest.raises(AssertionError, match="sign and frame"):
        check_failure_classes(_doc(_subagent(6, _SPEC_OK, body)))


def test_anchor_matches_on_word_boundary():
    assert not _has("read design.md", "sign")
    assert not _has("we enforce it", "force")
    assert _has("check normalization", "normaliz")
    assert _has("reference points and normalization", "reference point")
    assert _has("Subagent 2 inherits the model", "inherit")
    assert _has("a force\n  coefficient", "force coefficient")


# --- Skill-content tests (the real file) ------------------------------------------------------


@pytest.fixture(scope="module")
def skill() -> str:
    return _read_skill()


def test_subagent_models_exact(skill):
    check_models(skill)


def test_step3_model_pass_through(skill):
    _require(_step3_preamble(skill), STEP3_REQUIRED, "Step 3")


def test_step3_has_no_inherit_wording(skill):
    _forbid(_step3_preamble(skill), STEP3_FORBIDDEN_INHERIT, "Step 3")


def test_team_size_wording(skill):
    check_intro(skill)
    _forbid(_step3_preamble(skill), STEP3_FORBIDDEN_OLD_COUNT, "Step 3")


def test_subagent6_run_condition(skill):
    check_run_condition(skill)


def test_subagent6_if_unclear(skill):
    check_if_unclear(skill)


def test_subagent6_when_skipped(skill):
    check_when_skipped(skill)


def test_subagent6_authority_and_method(skill):
    check_authority_and_method(skill)


def test_subagent6_failure_classes(skill):
    check_failure_classes(skill)


def test_step4_covers_subagent6(skill):
    check_step4(skill)


def test_ci_command_in_subagents_2_and_3(skill):
    check_ci_command(skill)
