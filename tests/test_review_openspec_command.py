"""Structural guard for the ``/review-openspec`` command (OpenSpec change
``update-review-openspec-reviewers``, capability ``review-openspec-skill``).

``.claude/commands/review-openspec.md`` is a prompt, not code, so nothing else notices when a
subagent's ``model`` line, the conditional subagents' launch rules, or the synthesis template drift.
This test pins the text contract from the spec. It cannot check what the orchestrating model does
at runtime (that is the manual smoke run in the change's tasks.md).

Every anchor is searched only inside its own bounded section (design D4), matched
case-insensitively, whitespace-collapsed and on word boundaries, so text elsewhere in the file can
never stand in for a deleted anchor. Content failures raise ``AssertionError`` naming the subagent
or anchor, never ``KeyError``/``IndexError``/``AttributeError`` (convention of
``tests/_readme_guards.py``).
"""

from __future__ import annotations

import re
import sys
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

INTRO_REQUIRED = (
    "up to 6 specialized subagents",
    "Subagents 1, 2, 4 and 5 always run",
)
INTRO_FORBIDDEN = ("launches **5 specialized subagents in parallel**",)

STEP1_REQUIRED = ("openspec/changes/archive/", "stop and show")
STEP2_REQUIRED = (
    "{DESIGN_MD}",
    "(no design.md in this change)",
    "{CURRENT_SPECS}",
    "(new capability)",
)

STEP3_PASS_THROUGH = (
    "Pass each subagent's `model` field to the Agent tool exactly as given; do not omit it.",
    "If the Agent tool rejects a model value",
    "closest available model",
    "never drop the field",
)
STEP3_TEAM_SIZE = (
    "Launch ALL applicable subagents",
    "single message",
    "decide whether Subagents 3 and 6 run",
)
STEP3_FORBIDDEN_INHERIT = "inherit"
STEP3_FORBIDDEN_OLD_COUNT = "Launch ALL 5 subagents"

RUN_CONDITION_LABEL = "**Run condition:**"
IF_UNCLEAR_LABEL = "**If unclear:**"
WHEN_SKIPPED_LABEL = "**When skipped:**"
FAILURE_CLASSES_LABEL = "**Failure classes:**"

S3_RUN_CONDITION = (
    "CI workflows",
    "Dockerfiles",
    "build-args.env",
    "dependencies",
    "lockfile",
    "packaging",
)
S3_IF_UNCLEAR = ("launch Subagent 3",)
S3_SKIP_TEXT = "skipped: no CI, Docker, dependency or packaging change"

S6_RUN_CONDITION = (
    "Decide from",
    "mentioning it as background does not count",
    "never count",
    "solver decks",
    "geometry",
    "kinematics",
    "force, moment and coefficient computation",
    "frames",
    "units",
    "timestep and grid settings",
    "surrogate",
    "metrics",
    "extraction and corpus pipelines",
    "parsing, resampling or interpolation of solver output",
    "tolerance, threshold or acceptance gate",
    "convention document",
    "scientific claim",
    "figure",
    "quoted physical or statistical value",
)
S6_IF_UNCLEAR = ("launch Subagent 6",)
S6_SKIP_TEXT = "skipped: no numerics or scientific claims touched"

AUTHORITY_AND_METHOD = (
    "openspec/specs/coordinate-convention/spec.md",
    "openspec/specs/force-surrogate/spec.md",
    "radians(phi_amp_deg)",
    "docs/coordinate-convention.md",
    "narrative only",
    "confirm the code implements",
    "flag, do not resolve",
    "recompute every constant",
    "VERIFIED / CONTRADICTED / UNVERIFIABLE",
    "{DESIGN_MD}",
    "{CURRENT_SPECS}",
)
FAILURE_CLASSES = (
    "sign and frame",
    "no insect-body frame",
    "CF_chord",
    "CF_x..CF_z",
    "flapping-wing lab-frame series",
    "lab-frame components",
    "reference point",
    "normaliz",
    "units",
    "deg vs rad",
    "CFL",
    "realized dt",
    "boundary conditions",
    "time window",
    "worst case",
    "5 seeds",
    "known-answer",
    "like-for-like",
)
# #181: the corpus/surrogate CF_x..CF_z and the flapping-wing lab series are lab-frame, so the
# failure-class list must not say forces in general are wing-frame.
FAILURE_CLASSES_FORBIDDEN = (
    "forces are in the wing frame",
    "forces in the wing frame",
    "By design, forces",
)
# #161 is fixed on the convention page; the authority note must not keep describing it.
AUTHORITY_FORBIDDEN = ("uses ω for two quantities",)

STEP4_REQUIRED = (
    "physics/convention/units errors",
    "a CONTRADICTED value",
    "arithmetic evidence, is BLOCKING",
    "UNVERIFIABLE values",
    "does not rely on are IMPORTANT",
    "documented as deliberate",
    "Reviewers: 1 sonnet, 2 opus, 3 opus|skipped, 4 sonnet, 5 sonnet, 6 opus|skipped",
    "Numerical/physical correctness risk: LOW/MEDIUM/HIGH",
    "N/A (Subagent 6 skipped: <reason>)",
)
# Step 4 template headings that must stand on their own line, each with its own launch/skip record.
STEP4_CONDITIONAL_SECTIONS = {
    "### 3. CI/CD & Build": S3_SKIP_TEXT,
    "### 6. Math & Physics": S6_SKIP_TEXT,
}
LAUNCHED_RECORD = "launched: <"

CI_COMMAND = 'uv run pytest -v -m "not gpu"'

# --- Matching ---------------------------------------------------------------------------------


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has(text: str, anchor: str) -> bool:
    """Case-insensitive, whitespace-collapsed, word-bounded (prefix-only for STEMS) match.

    A boundary is enforced only at an end of the anchor that is a word character, so an anchor
    ending in punctuation (``launched: <``) still matches when a letter follows it.
    """
    collapsed = _collapse(anchor)
    pattern = re.escape(collapsed)
    if re.match(r"\w", collapsed):
        pattern = r"(?<!\w)" + pattern
    if anchor not in STEMS and re.search(r"\w$", collapsed):
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
_LOOSE_SUBAGENT_HEADING = re.compile(r"^#{2,4}\s*Subagent\s+\d+", re.MULTILINE)
_SUBAGENT_TYPE_LINE = re.compile(r"^subagent_type:", re.MULTILINE)
_SECTION_END = re.compile(r"^(?:### Subagent\b|---[ \t]*$|## )", re.MULTILINE)
_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)
_SPEC_LINE = re.compile(r'(\w+): "([^"]*)"')
_BOLD_LABEL_LINE = re.compile(r"^\*\*[^*]+:\*\*")


def _read_skill() -> str:
    path = SKILL
    if not path.is_file():
        raise AssertionError(f"skill file missing: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise AssertionError(f"skill file is not UTF-8: {path} ({exc})") from None


def _subagent_sections(text: str) -> list[tuple[int, int, str]]:
    """Return ``(number, heading offset, section text)`` in file order.

    A section ends at the next ``### Subagent`` heading, a ``---`` line, or a ``## `` heading,
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
        raise AssertionError(f"Subagent {number}: no closed fenced spec block")
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


def _step1(text: str) -> str:
    return _between(text, r"^## Step 1", r"^## Step 2", "Step 1")


def _step2(text: str) -> str:
    return _between(text, r"^## Step 2", r"^## Step 3", "Step 2")


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
    headings = len(_LOOSE_SUBAGENT_HEADING.findall(text))
    if headings != len(EXPECTED_MODELS):
        raise AssertionError(f"expected 6 subagent headings, found {headings}")
    type_lines = len(_SUBAGENT_TYPE_LINE.findall(text))
    if type_lines != len(EXPECTED_MODELS):
        raise AssertionError(f"expected 6 subagent_type lines, found {type_lines}")
    step4 = re.search(r"^## Step 4", text, re.MULTILINE)
    if step4 is None:
        raise AssertionError("'## Step 4' heading not found")
    for number, offset, _ in sections:
        if offset > step4.start():
            raise AssertionError(f"Subagent {number}: section is after '## Step 4'")


def check_step1(text: str) -> None:
    _require(_step1(text), STEP1_REQUIRED, "Step 1")


def check_step2(text: str) -> None:
    _require(_step2(text), STEP2_REQUIRED, "Step 2")


def check_step3_pass_through(text: str) -> None:
    _require(_step3_preamble(text), STEP3_PASS_THROUGH, "Step 3")


def check_step3_no_inherit(text: str) -> None:
    _forbid(_step3_preamble(text), STEP3_FORBIDDEN_INHERIT, "Step 3")


def check_team_size(text: str) -> None:
    intro = _intro(text)
    _require(intro, INTRO_REQUIRED, "intro")
    for anchor in INTRO_FORBIDDEN:
        _forbid(intro, anchor, "intro")
    preamble = _step3_preamble(text)
    _require(preamble, STEP3_TEAM_SIZE, "Step 3")
    _forbid(preamble, STEP3_FORBIDDEN_OLD_COUNT, "Step 3")


def check_launch_rules(
    text: str,
    number: int,
    run: tuple[str, ...],
    unclear: tuple[str, ...],
    skip: str,
) -> None:
    section = _section(text, number)
    where = f"Subagent {number}"
    for label, anchors in (
        (RUN_CONDITION_LABEL, run),
        (IF_UNCLEAR_LABEL, unclear),
        (WHEN_SKIPPED_LABEL, (skip,)),
    ):
        block = _labelled_block(section, label, where)
        _require(block, anchors, f"{where} {label}")
    # Fail-safe rule: the If-unclear paragraph must *begin* with its instruction, so a negated
    # rule ("do not launch Subagent N") cannot satisfy the anchor.
    unclear_block = _collapse(_labelled_block(section, IF_UNCLEAR_LABEL, where))
    if not unclear_block.lower().startswith(unclear[0].lower()):
        raise AssertionError(
            f"{where} {IF_UNCLEAR_LABEL}: must start with {unclear[0]!r}, found {unclear_block[:40]!r}"
        )


def check_subagent3_launch_rules(text: str) -> None:
    check_launch_rules(text, 3, S3_RUN_CONDITION, S3_IF_UNCLEAR, S3_SKIP_TEXT)


def check_subagent6_launch_rules(text: str) -> None:
    check_launch_rules(text, 6, S6_RUN_CONDITION, S6_IF_UNCLEAR, S6_SKIP_TEXT)


def check_authority_and_method(text: str) -> None:
    template = _prompt_template(_section(text, 6))
    _require(template, AUTHORITY_AND_METHOD, "Subagent 6 prompt template")
    for anchor in AUTHORITY_FORBIDDEN:
        _forbid(template, anchor, "Subagent 6 prompt template")


def check_failure_classes(text: str) -> None:
    template = _prompt_template(_section(text, 6))
    block = _labelled_block(
        template, FAILURE_CLASSES_LABEL, "Subagent 6 prompt template"
    )
    _require(block, FAILURE_CLASSES, f"Subagent 6 {FAILURE_CLASSES_LABEL}")
    for anchor in FAILURE_CLASSES_FORBIDDEN:
        _forbid(block, anchor, f"Subagent 6 {FAILURE_CLASSES_LABEL}")


def check_step4(text: str) -> None:
    step4 = _step4(text)
    _require(step4, STEP4_REQUIRED, "Step 4")
    for heading, skip in STEP4_CONDITIONAL_SECTIONS.items():
        where = f"Step 4 {heading!r}"
        match = re.search(rf"^{re.escape(heading)}[ \t]*$", step4, re.MULTILINE)
        if match is None:
            raise AssertionError(f"{where}: heading missing or not on its own line")
        end = re.compile(r"^### |^```", re.MULTILINE).search(step4, match.end())
        body = step4[match.end() : end.start() if end else len(step4)]
        _require(body, (LAUNCHED_RECORD, skip), where)


def check_ci_command(text: str) -> None:
    for number in (2, 3):
        _require(_section(text, number), (CI_COMMAND,), f"Subagent {number}")


# --- Synthetic documents for the parser unit tests --------------------------------------------


def _spec(number: int) -> str:
    return (
        f'subagent_type: "general-purpose"\nmodel: "{EXPECTED_MODELS[number]}"\n'
        f'description: "x"'
    )


def _subagent(number: int, spec: str | None = None, body: str = "> Prompt.") -> str:
    spec = _spec(number) if spec is None else spec
    return f"### Subagent {number}: Name\n\n```\n{spec}\n```\n\n{body}\n"


def _doc(
    *sections: str, before_step4: str = "---\n\n", step4: str = "Template."
) -> str:
    return (
        "# Title\n\n## Step 1: One\n\n## Step 2: Two\n\n## Step 3: Launch\n\n"
        + "\n".join(sections)
        + f"\n{before_step4}## Step 4: Synthesize\n\n{step4}\n\n## Step 5: Present\n"
    )


def _six(
    *, skip: int | None = None, order: tuple[int, ...] = (1, 2, 3, 4, 5, 6)
) -> list[str]:
    return [_subagent(n) for n in order if n != skip]


_SPEC_OK = _spec(6)

# --- Parser unit tests ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "before_step4", ["---\n\n", ""], ids=["rule-before-step4", "no-rule"]
)
def test_last_section_does_not_swallow_step4(before_step4):
    text = _doc(
        _subagent(6, body="> No labels in this section."),
        before_step4=before_step4,
        step4=f"{WHEN_SKIPPED_LABEL} {S6_SKIP_TEXT}",
    )
    with pytest.raises(
        AssertionError, match=r"Subagent 6: no \*\*When skipped:\*\* block"
    ):
        _labelled_block(_section(text, 6), WHEN_SKIPPED_LABEL, "Subagent 6")


def test_subagent_anchor_not_satisfied_by_next_subagent():
    text = _doc(
        _subagent(2, body="> No command here."), _subagent(3, body=f"> {CI_COMMAND}")
    )
    with pytest.raises(AssertionError, match="Subagent 2: missing anchor"):
        check_ci_command(text)


def test_rule_line_ends_section():
    body = f"> Prompt.\n---\n{WHEN_SKIPPED_LABEL} {S6_SKIP_TEXT}"
    text = _doc(_subagent(6, body=body))
    with pytest.raises(AssertionError, match=r"no \*\*When skipped:\*\* block"):
        _labelled_block(_section(text, 6), WHEN_SKIPPED_LABEL, "Subagent 6")


def test_parser_rejects_duplicate_subagent_number():
    text = _doc(_subagent(6), _subagent(6))
    with pytest.raises(AssertionError, match="Subagent 6: duplicate"):
        _subagent_sections(text)


def test_parser_rejects_out_of_order():
    with pytest.raises(AssertionError, match=r"in order, found \[1, 2, 3, 5, 4, 6\]"):
        check_models(_doc(*_six(order=(1, 2, 3, 5, 4, 6))))


def test_parser_rejects_missing_subagent():
    with pytest.raises(AssertionError, match=r"in order, found \[1, 2, 3, 5, 6\]"):
        check_models(_doc(*_six(skip=4)))


def test_parser_rejects_seventh_subagent():
    seventh = _subagent(7, 'subagent_type: "general-purpose"\nmodel: "haiku"')
    with pytest.raises(AssertionError, match=r"found \[1, 2, 3, 4, 5, 6, 7\]"):
        check_models(_doc(*_six(), seventh))


def test_parser_rejects_colonless_extra_heading():
    extra = '### Subagent 7 - Extra\n\n```\nsubagent_type: "general-purpose"\n```\n'
    with pytest.raises(AssertionError, match="expected 6 subagent headings, found 7"):
        check_models(_doc(*_six(), extra))


def test_parser_rejects_extra_spec_block():
    extra = '#### Extra reviewer\n\n```\nsubagent_type: "general-purpose"\n```\n'
    with pytest.raises(AssertionError, match="expected 6 subagent_type lines, found 7"):
        check_models(_doc(*_six(), extra))


def test_parser_rejects_section_after_step4():
    text = _doc(*_six(skip=6), step4=_subagent(6))
    with pytest.raises(AssertionError, match="Subagent 6: section is after"):
        check_models(text)


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
    with pytest.raises(AssertionError, match="Subagent 1: no closed fenced spec block"):
        check_models(text)


def test_parser_requires_spec_block_first():
    section = (
        '### Subagent 1: Name\n\n```\nexample: "x"\n```\n\n```\n' + _spec(1) + "\n```\n"
    )
    with pytest.raises(AssertionError, match="Subagent 1: first fenced block"):
        check_models(_doc(section))


def test_parser_ignores_model_outside_fence():
    spec = 'subagent_type: "general-purpose"\ndescription: "x"'
    text = _doc(_subagent(1, spec, '> model: "sonnet"'))
    with pytest.raises(AssertionError, match="Subagent 1 has no model"):
        check_models(text)


@pytest.mark.parametrize(
    ("helper", "text", "message"),
    [
        (_intro, "# Title\n\nNo steps.\n", "'## Step 1' heading not found"),
        (_step4, "## Step 4: Synthesize\n\nNo step 5.\n", "end heading"),
        (_step3_preamble, "## Step 3: Launch\n\nNo subagents.\n", "end heading"),
        (_step1, "# Title\n\nNo steps.\n", "start heading"),
    ],
    ids=["no-step1", "no-step5", "no-subagent-after-step3", "between-no-start"],
)
def test_missing_step_heading_is_assertion(helper, text, message):
    with pytest.raises(AssertionError, match=message):
        helper(text)


def test_check_models_requires_step4_heading():
    text = _doc(*_six()).replace("## Step 4", "## Step X")
    with pytest.raises(AssertionError, match="'## Step 4' heading not found"):
        check_models(text)


def test_missing_section_is_assertion():
    with pytest.raises(AssertionError, match="no Subagent 6 section"):
        _section(_doc(*_six(skip=6)), 6)


def test_label_inside_quote_does_not_count():
    text = _doc(_subagent(6, body=f"> {WHEN_SKIPPED_LABEL} {S6_SKIP_TEXT}"))
    with pytest.raises(AssertionError, match=r"no \*\*When skipped:\*\* block"):
        _labelled_block(_section(text, 6), WHEN_SKIPPED_LABEL, "Subagent 6")


@pytest.mark.parametrize(
    "negated", ["do not launch Subagent 6.", "never launch Subagent 6."]
)
def test_negated_if_unclear_rule_fails(negated):
    body = (
        f"{RUN_CONDITION_LABEL} solver decks.\n\n{IF_UNCLEAR_LABEL} {negated}\n\n"
        f"{WHEN_SKIPPED_LABEL} {S6_SKIP_TEXT}"
    )
    text = _doc(_subagent(6, body=body))
    with pytest.raises(AssertionError, match="must start with 'launch Subagent 6'"):
        check_launch_rules(text, 6, ("solver decks",), S6_IF_UNCLEAR, S6_SKIP_TEXT)


def test_step4_heading_must_stand_alone():
    step4 = (
        "\n".join(STEP4_REQUIRED)
        + f"\n```markdown\n#### 3. CI/CD & Build\n[{LAUNCHED_RECORD}x; or: {S3_SKIP_TEXT}]\n"
        f"### 6. Math & Physics\n[{LAUNCHED_RECORD}x; or: {S6_SKIP_TEXT}]\n```"
    )
    with pytest.raises(AssertionError, match="heading missing or not on its own line"):
        check_step4(_doc(step4=step4))


def test_step4_section_requires_its_own_launched_record():
    step4 = (
        "\n".join(STEP4_REQUIRED)
        + f"\n```markdown\n### 3. CI/CD & Build\n[findings; or: {S3_SKIP_TEXT}]\n"
        f"### 6. Math & Physics\n[{LAUNCHED_RECORD}x; or: {S6_SKIP_TEXT}]\n```"
    )
    with pytest.raises(
        AssertionError, match="CI/CD & Build'.*missing anchor 'launched: <'"
    ):
        check_step4(_doc(step4=step4))


def test_missing_skill_file_is_assertion(monkeypatch, tmp_path):
    monkeypatch.setattr(sys.modules[__name__], "SKILL", tmp_path / "missing.md")
    with pytest.raises(AssertionError, match="skill file missing"):
        _read_skill()


def test_undecodable_skill_is_assertion(monkeypatch, tmp_path):
    path = tmp_path / "bad.md"
    path.write_bytes(b"\xff\xfe\xfa not utf-8")
    monkeypatch.setattr(sys.modules[__name__], "SKILL", path)
    with pytest.raises(AssertionError, match="not UTF-8"):
        _read_skill()


def test_labelled_block_ends_at_blank_line():
    text = _doc(_subagent(6, body=f"{IF_UNCLEAR_LABEL} decide.\n\nlaunch Subagent 6"))
    with pytest.raises(AssertionError, match="launch Subagent 6"):
        _require(
            _labelled_block(_section(text, 6), IF_UNCLEAR_LABEL, "Subagent 6"),
            S6_IF_UNCLEAR,
            "Subagent 6",
        )


def test_labelled_paragraphs_do_not_merge():
    body = (
        f"{RUN_CONDITION_LABEL} solver decks.\n"
        f"{IF_UNCLEAR_LABEL} decide.\n"
        f"{WHEN_SKIPPED_LABEL} launch Subagent 6"
    )
    text = _doc(_subagent(6, body=body))
    with pytest.raises(AssertionError, match="launch Subagent 6"):
        _require(
            _labelled_block(_section(text, 6), IF_UNCLEAR_LABEL, "Subagent 6"),
            S6_IF_UNCLEAR,
            "Subagent 6",
        )


def test_prompt_template_keeps_quoted_paragraphs_apart():
    body = f"> {FAILURE_CLASSES_LABEL}\n>\n> - sign and frame conventions"
    with pytest.raises(AssertionError, match="sign and frame"):
        check_failure_classes(_doc(_subagent(6, body=body)))


def test_anchor_matches_on_word_boundary():
    assert not _has("read design.md", "sign")
    assert not _has("we enforce it", "force")
    assert not _has("two signs", "sign")
    assert not _has("forced tool use", "force")
    assert _has("check normalization", "normaliz")
    assert _has("reference points and normalization", "reference point")
    assert _has("Subagent 2 inherits the model", "inherit")
    assert _has("a force\n  coefficient", "force coefficient")
    assert _has("[launched: <matched item>", "launched: <")
    assert not _has("relaunched: <matched item>", "launched: <")


# --- Skill-content tests (the real file) ------------------------------------------------------


@pytest.fixture(scope="module")
def skill() -> str:
    return _read_skill()


def test_subagent_models_exact(skill):
    check_models(skill)


def test_step1_handles_archived_and_unknown_ids(skill):
    check_step1(skill)


def test_step2_defines_placeholders(skill):
    check_step2(skill)


def test_step3_model_pass_through(skill):
    check_step3_pass_through(skill)


def test_step3_has_no_inherit_wording(skill):
    check_step3_no_inherit(skill)


def test_team_size_wording(skill):
    check_team_size(skill)


def test_subagent3_launch_rules(skill):
    check_subagent3_launch_rules(skill)


def test_subagent6_launch_rules(skill):
    check_subagent6_launch_rules(skill)


def test_subagent6_authority_and_method(skill):
    check_authority_and_method(skill)


def test_subagent6_failure_classes(skill):
    check_failure_classes(skill)


def test_step4_covers_conditional_reviewers(skill):
    check_step4(skill)


def test_ci_command_in_subagents_2_and_3(skill):
    check_ci_command(skill)
