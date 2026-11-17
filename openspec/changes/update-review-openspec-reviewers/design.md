# Design: update-review-openspec-reviewers

## Context

`/review-openspec` is a Claude Code project command (a markdown prompt), not Python. Its subagent
spec blocks are fenced code blocks of `key: "value"` lines that the orchestrating model copies into
Agent tool calls. The Agent tool accepts an optional `model` (`sonnet`, `opus`, `haiku`, ...). When
omitted, the subagent inherits the session model unless a default subagent model is configured.

## Decisions

### D1: Explicit `model` on every subagent, including the Opus ones

Every block names its model; none relies on inheritance. Inheritance would silently move the TDD,
CI and Math/Physics reviewers to Sonnet if the session ran on Sonnet or a default subagent model
were configured. An explicit `model` also overrides a deliberate session-wide downgrade; that is
intended. `opus`/`sonnet` are aliases, not pins: they move to the newest model in each family. That
is acceptable for a review step, whose output is not a reproducible artifact.

### D2: Which lenses move to Sonnet

Sonnet for lenses that check a proposal against written rules: spec format (1), documentation/DRY
(4), git commit plan (5). Opus for lenses that must reason about what is missing or how things
fail: TDD gaps (2), CI/build failure modes (3), math/physics (6). The synthesis step catches a
wrong Sonnet finding, not a missing one; the residual risk is a missed finding (see Risks).

### D3: Subagent 6 is conditional, fail-safe toward running

The run condition covers numerics **and** convention documents, scientific claims, figures and
quoted physical or statistical values, because a docs-only convention gap was the root cause of
#108. It deliberately says "quoted physical or statistical value", not "quoted number": issue
numbers and percentages appear in almost every proposal, and a run condition that always fires
would erase the saving. When unclear, Subagent 6 runs. The orchestrator decides before the single
parallel launch (Step 3). A skip is visible twice in the synthesis (Risk line and section 6), so a
wrong skip is visible at the user's approval checkpoint.

Subagent 6's authority for axes, reference point, sign and normalization is
`docs/coordinate-convention.md` (sourced to van Veen et al. 2022, JFM 936 A3), not the paper
directly; the paper has known traps (its figure 1f reads opposite to §2.2). Disagreements between
proposal, page and paper are flagged, not resolved by the reviewer.

### D4: Structural test with bounded sections

The anchors themselves are listed in the spec scenarios (the living contract after archive). The
test holds them as module-level constants. This section describes only how they are located.

`tests/test_review_openspec_command.py` reads the skill from
`Path(__file__).resolve().parents[1] / ".claude" / "commands" / "review-openspec.md"` with
`encoding="utf-8"` (Windows' default cp1252 decodes the em dashes into wrong characters without
raising). A missing file raises `AssertionError` naming the path.

Helpers (all headings matched at line start, never by `str.find`):

- `_subagent_sections(text)`: splits on `^### Subagent (\d+):`; each section ends at the next
  `^### Subagent`, a `^---$` line, or a `^## ` heading, so the last subagent never absorbs Step 4.
  Duplicate numbers raise. Consequence for authors: no `---` line inside a subagent section (it
  would truncate the section; that fails red, not silently).
- `_spec_block(n, section)`: the first fenced block; it must contain `subagent_type:`. Lines must
  match `^(\w+): "([^"]*)"$`; each key at most once; a `model` line outside the fence is ignored.
- `_prompt_template(section)`: the `> ` lines with the marker stripped; a line that is exactly `>`
  becomes a blank line, so paragraphs inside the quote stay separate.
- `_labelled_block(text, label)`: from a line that starts with the bold label (e.g.
  `**Run condition:**`; matched at line start, so a label inside a `> ` quote never counts as a
  launch-rule paragraph) to the next blank line (`line.strip() == ""`) or the next line that starts
  with a bold label (`^\*\*[^*]+:\*\*`); the label's own line does not end the block. So adjacent
  labelled paragraphs never merge, and a list item `- **Units:** ...` (starts with `- `) does not
  end a list. Applied to the section (outside the quote) for the three launch-rule paragraphs, and
  to `_prompt_template` output for `**Failure classes:**`.
- `_intro(text)`: start of file to `^## Step 1`.
- `_step3_preamble(text)`: `^## Step 3` up to the first `^### Subagent`.
- `_step4(text)`: `^## Step 4` up to `^## Step 5`. The fenced template's `## Verdict` and
  `## Summary` lines do not end it.

Matching: case-insensitive, whitespace collapsed, word-bounded (`(?<!\w)anchor(?!\w)`), so `sign`
does not match `design` and `force` does not match `enforce`. Stem anchors (marked "(stem)" in the
spec) match as a word prefix (`(?<!\w)anchor`): `normaliz`, `reference point` (the spec prose says
"reference points"), and the forbidden `inherit` (so "inherits"/"inheriting" are caught).
Run-condition items are pinned as multi-word phrases (`force, moment and coefficient computation`,
`timestep and grid settings`) because the paragraph's own example list ("force coefficient, R²,
timestep, grid size, seed count") would otherwise satisfy single-word anchors for deleted items. Every content failure raises `AssertionError` naming
the subagent or anchor (convention of `tests/_readme_guards.py`), never
`KeyError`/`IndexError`/`AttributeError`.

The failure-class anchors are searched only inside the `**Failure classes:**` list, because the
authority sentence the spec also requires mentions reference point, sign and normalization; a
whole-template search would let a deleted checklist item go unnoticed.

### D5: TDD red phase

The 5-line Sonnet edit applied before this proposal is discarded (task 1.1) and re-typed in the
green phase, so the red phase runs against `main`'s file. The test is committed red, separately,
and never pushed without the green commit (repo precedent: "Red until the next commit").

## Risks

- A Sonnet reviewer misses something Opus would have caught. Mitigated by D2's split; revisit after
  a few reviews (#157 waits on that evidence).
- The orchestrator ignores the `model` field or the launch rules. The text test cannot check this.
  Task 3.2's smoke run checks the launch path and the `model` parameters once; the skip path and
  the convention-document path are checked only by reading the skill text (one smoke run was
  chosen to limit cost).
- The run-condition anchors pin 13 phrases, so rewording the run condition means updating the test.
  Accepted: the run condition is the contract this change exists to add.
