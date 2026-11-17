## ADDED Requirements

### Requirement: Explicit Subagent Model Assignment

`.claude/commands/review-openspec.md` SHALL define exactly Subagents 1-6, in that order, all before
`## Step 4`. Each subagent's spec block SHALL declare an explicit, quoted `model` field: Subagent 1
(Spec Quality), Subagent 4 (Documentation) and Subagent 5 (Git Workflow) SHALL use
`model: "sonnet"`; Subagent 2 (TDD & Testing), Subagent 3 (CI/CD & Build) and Subagent 6 (Math,
Physics & Numerical Correctness) SHALL use `model: "opus"`. No subagent SHALL rely on inheriting
the session model.

#### Scenario: Rule-checklist reviewers use Sonnet

- **WHEN** the spec blocks of Subagents 1, 4 and 5 are read
- **THEN** each contains exactly one line `model: "sonnet"`

#### Scenario: Judgment-heavy reviewers use Opus

- **WHEN** the spec blocks of Subagents 2, 3 and 6 are read
- **THEN** each contains exactly one line `model: "opus"`

#### Scenario: Subagent set drifts

- **WHEN** a subagent section is missing, duplicated, out of order, placed after `## Step 4`, or a
  seventh is added, or a spec block has no `model` line, an unquoted model, or two `model` lines
- **THEN** the structural test fails with an `AssertionError` naming the subagent

### Requirement: Model Pass-Through Instruction

Step 3 of `/review-openspec` SHALL instruct the orchestrator to pass each subagent's `model` field
to the Agent tool exactly as given, and SHALL NOT describe any subagent as inheriting the main
model. Only the presence of the instruction is machine-checked; the orchestrator's compliance is
checked by the manual smoke run.

#### Scenario: Step 3 states the pass-through rule

- **WHEN** Step 3's text before the first `### Subagent` heading is read
- **THEN** it contains ``Pass each subagent's `model` field to the Agent tool exactly as given; do not omit it.``
- **AND** it does not contain `inherit` (stem; also matches inherits, inherited, inheriting)

### Requirement: Subagent 6 Launch Rules Are Stated

The Subagent 6 section SHALL contain, outside its `> ` prompt template, three labelled paragraphs,
each starting with its bold label:

- `**Run condition:**` lists solver decks, geometry, kinematics, force, moment and coefficient
  computation, frames, units, timestep and grid settings, surrogate training and evaluation
  metrics, and any convention document, scientific claim, figure, or quoted physical or statistical
  value (force coefficient, R², timestep, grid size, seed count).
- `**If unclear:**` says to launch Subagent 6.
- `**When skipped:**` gives the exact text `skipped: no numerics or scientific claims touched`.

The intro SHALL describe the team as five subagents plus a conditional sixth. Step 3 SHALL say to
launch all applicable subagents in a single message after deciding whether Subagent 6 runs, and
SHALL NOT say `Launch ALL 5 subagents`.

#### Scenario: Launch rules are present in their labelled paragraphs

- **WHEN** the Subagent 6 section is read
- **THEN** the `**Run condition:**` paragraph contains `solver decks`, `geometry`, `kinematics`,
  `force, moment and coefficient computation`, `frames`, `units`, `timestep and grid settings`,
  `surrogate`, `metrics`, `convention document`, `scientific claim`, `figure` and
  `quoted physical or statistical value` (multi-word phrases, so the example list after
  `quoted physical or statistical value` cannot stand in for a deleted item)
- **AND** the `**If unclear:**` paragraph contains `launch Subagent 6`
- **AND** the `**When skipped:**` paragraph contains `skipped: no numerics or scientific claims touched`
- **AND** deleting any one paragraph fails the test even when the same words remain elsewhere in
  the file, including in an adjacent labelled paragraph

#### Scenario: Team size wording is updated

- **WHEN** the intro (text before `## Step 1`) and Step 3 are read
- **THEN** the intro contains `plus a conditional 6th` and not
  `launches **5 specialized subagents in parallel**`
- **AND** Step 3 contains `Launch ALL applicable subagents`, `single message` and
  `decide whether Subagent 6 runs`, and not `Launch ALL 5 subagents`

### Requirement: Orchestrator Applies Launch Rules

When running `/review-openspec`, the orchestrator SHALL launch Subagent 6 in the same parallel
batch as Subagents 1-5 when the run condition holds or is unclear, and SHALL otherwise skip it and
report the skip. This is runtime behaviour of the orchestrating model and is not machine-verifiable.
The physics-change scenario is checked once by the manual smoke run (task 3.2); the other two
scenarios are checked only by inspecting the skill text.

#### Scenario: Physics change launches Subagent 6

- **WHEN** `/review-openspec` reviews a change to how a force coefficient's sign or normalization is
  defined
- **THEN** Subagent 6 is launched in the same message as Subagents 1-5, each with its declared
  `model`

#### Scenario: Convention-document change launches Subagent 6

- **WHEN** a documentation-only proposal changes a stated sign convention, force-coefficient value,
  or R² claim
- **THEN** Subagent 6 is launched

#### Scenario: Out-of-scope change skips Subagent 6 visibly

- **WHEN** a proposal touches none of the run condition items (for example it changes only
  `.claude/commands/`, `.github/workflows/` or lint configuration, with no solver deck, timestep,
  grid, surrogate, metric, convention document, scientific claim, figure, or quoted physical or
  statistical value)
- **THEN** Subagent 6 is not launched
- **AND** the synthesized review's Risk Assessment line reads `N/A (Subagent 6 skipped: <reason>)`
  and its `### 6. Math & Physics` section reads
  `skipped: no numerics or scientific claims touched` with a one-line reason

### Requirement: Math and Physics Review Checklist

Subagent 6's prompt template SHALL name `docs/coordinate-convention.md` as the authority for axes,
reference point, sign and normalization, and SHALL tell the reviewer to flag, not resolve,
disagreement between the proposal, that page and the source paper. It SHALL tell the reviewer to
recompute every constant, reference point, sign, timestep or seed count the proposal relies on from
its source and report each as `VERIFIED / CONTRADICTED / UNVERIFIABLE`. Within the prompt template,
a list starting with `**Failure classes:**` SHALL name: sign and frame conventions, reference
points and normalization, units, CFL-limited timestep, worst case rather than first case
validation, variance across at least 5 seeds, and known-answer tests.

#### Scenario: Authority and method are stated

- **WHEN** Subagent 6's prompt template (its `> ` lines) is read
- **THEN** it contains `docs/coordinate-convention.md`, `flag, do not resolve`, `recompute` and
  `VERIFIED / CONTRADICTED / UNVERIFIABLE`

#### Scenario: Failure-class list covers each past failure class

- **WHEN** the `**Failure classes:**` list in Subagent 6's prompt template is read
- **THEN** it contains `sign and frame`, `reference point` (stem), `normaliz` (stem), `units`, `CFL`,
  `worst case`, `5 seeds` and `known-answer`
- **AND** deleting any one list item fails the test even though the authority sentence also
  mentions reference point, sign and normalization

### Requirement: Synthesis Covers Subagent 6

The Step 4 synthesis instructions SHALL list physics/convention/units errors as BLOCKING. The Step 4
template SHALL include a `Numerical/physical correctness risk: LOW/MEDIUM/HIGH` line with the
skipped value `N/A (Subagent 6 skipped: <reason>)`, and a `### 6. Math & Physics` section with the
skipped text `skipped: no numerics or scientific claims touched`.

#### Scenario: Step 4 includes the Subagent 6 outputs

- **WHEN** Step 4 (from the line `## Step 4` to the line `## Step 5`) is read
- **THEN** it contains `physics/convention/units errors`,
  `Numerical/physical correctness risk: LOW/MEDIUM/HIGH`, `N/A (Subagent 6 skipped: <reason>)`,
  `### 6. Math & Physics` and `skipped: no numerics or scientific claims touched`

### Requirement: Accurate CI Command in Reviewer Prompts

The prompts of Subagent 2 (TDD & Testing) and Subagent 3 (CI/CD & Build) SHALL quote CI's actual
test command, `uv run pytest -v -m "not gpu"`.

#### Scenario: CI command is quoted correctly

- **WHEN** the Subagent 2 and Subagent 3 sections are read
- **THEN** each contains `uv run pytest -v -m "not gpu"`

### Requirement: CI-Enforced Skill Structure

The text requirements above SHALL be checked by `tests/test_review_openspec_command.py`, which runs
in the existing CI `pytest` job without a GPU, network or Docker and reads the skill as UTF-8 from a
path resolved relative to the test file. Each anchor SHALL be searched only within its section:
a subagent section ends at the next `### Subagent` heading, a `---` line or a `## ` heading; a
labelled paragraph or list ends at the next blank line or the next line that starts with a bold
label (`**Label:**`). Anchors SHALL match case-insensitively, after collapsing whitespace, on word
boundaries; only anchors marked (stem) match as a word prefix.

#### Scenario: Removing an anchor fails the test

- **WHEN** any anchor named in this specification is removed or altered in its section
- **THEN** `uv run pytest tests/test_review_openspec_command.py` fails with an `AssertionError`
  naming the subagent or anchor that is missing or wrong

#### Scenario: An anchor inside a longer word does not count

- **WHEN** the only occurrence of an anchor such as `sign` or `force` is inside a longer word such
  as `design` or `enforce`
- **THEN** the anchor is reported missing

#### Scenario: Test does not depend on the working directory

- **WHEN** the test file is run from the `tests/` directory instead of the repository root
- **THEN** it locates the skill file and gives the same result
