## ADDED Requirements

### Requirement: Explicit Subagent Model Assignment

`.claude/commands/review-openspec.md` SHALL define exactly Subagents 1-6, in that order, all before
`## Step 4`, each starting with a heading of the form `### Subagent N: Name`; the file SHALL contain
exactly six `subagent_type:` lines. Each subagent's spec block SHALL declare an explicit, quoted
`model` field: Subagent 1 (Spec Quality), Subagent 4 (Documentation) and Subagent 5 (Git Workflow)
SHALL use `model: "sonnet"`; Subagent 2 (TDD & Testing), Subagent 3 (CI/CD & Build) and Subagent 6
(Math, Physics & Numerical Correctness) SHALL use `model: "opus"`. No subagent SHALL rely on
inheriting the session model.

#### Scenario: Rule-checklist reviewers use Sonnet

- **WHEN** the spec blocks of Subagents 1, 4 and 5 are read
- **THEN** each contains exactly one line `model: "sonnet"`

#### Scenario: Judgment-heavy reviewers use Opus

- **WHEN** the spec blocks of Subagents 2, 3 and 6 are read
- **THEN** each contains exactly one line `model: "opus"`

#### Scenario: Subagent set drifts

- **WHEN** a subagent section is missing, duplicated, out of order, placed after `## Step 4`, or a
  seventh is added (with or without the colon heading form), or a spec block has no `model` line,
  an unquoted model, or two `model` lines
- **THEN** the structural test fails with an `AssertionError` naming the subagent or the count

### Requirement: Model Pass-Through Instruction

Step 3 of `/review-openspec` SHALL instruct the orchestrator to pass each subagent's `model` field
to the Agent tool exactly as given, SHALL say what to do if the Agent tool rejects a model value
(relaunch with the closest available model and record it; never drop the field), and SHALL NOT
describe any subagent as inheriting the main model. Only the presence of the instructions is
machine-checked; the orchestrator's compliance is checked by the manual smoke run.

#### Scenario: Step 3 states the pass-through and fallback rules

- **WHEN** Step 3's text before the first `### Subagent` heading is read
- **THEN** it contains ``Pass each subagent's `model` field to the Agent tool exactly as given; do not omit it.``
  , `If the Agent tool rejects a model value`, `closest available model` and `never drop the field`
- **AND** it does not contain `inherit` (stem; also matches inherits, inherited, inheriting)

### Requirement: Proposal Inputs Are Defined

Step 1 SHALL say what to do when the change id is archived (review it read-only from
`openspec/changes/archive/`) or not found (stop and show `openspec list`). Step 2 SHALL define every
template placeholder, including the value to embed when a change has no `design.md` or modifies no
existing spec.

#### Scenario: Archived and unknown change ids are handled

- **WHEN** Step 1 (from `## Step 1` to `## Step 2`) is read
- **THEN** it contains `openspec/changes/archive/` and `stop and show`

#### Scenario: Placeholders and their fallbacks are defined

- **WHEN** Step 2 (from `## Step 2` to `## Step 3`) is read
- **THEN** it contains `{DESIGN_MD}`, `(no design.md in this change)`, `{CURRENT_SPECS}` and
  `(new capability)`

### Requirement: Conditional Reviewer Launch Rules Are Stated

Subagent 3 and Subagent 6 SHALL each contain, outside their `> ` prompt template, three labelled
paragraphs, each starting with its bold label: `**Run condition:**`, `**If unclear:**` and
`**When skipped:**`. Subagents 1, 2, 4 and 5 SHALL always run.

- Subagent 3's run condition lists CI workflows, Dockerfiles, `build-args.env`, dependencies, the
  lockfile and packaging. If unclear, launch Subagent 3. When skipped, the text starts with
  `skipped: no CI, Docker, dependency or packaging change`.
- Subagent 6's run condition says to decide from the proposal's files, says that mentioning a value
  as background does not count and that issue or PR numbers, file or test counts and tooling or
  usage percentages never count, and lists solver decks,
  geometry, kinematics, force, moment and coefficient computation, frames, units, timestep and grid
  settings, surrogate training and evaluation metrics, force and field extraction and corpus
  pipelines, parsing, resampling or interpolation of solver output, any tolerance, threshold or
  acceptance gate on these quantities, and any convention document, scientific claim, figure, or
  quoted physical or statistical value. If unclear, launch Subagent 6. When skipped, the text starts
  with `skipped: no numerics or scientific claims touched`.

Each `**If unclear:**` paragraph SHALL begin with its launch instruction, so a negated rule cannot
satisfy it. The intro SHALL describe the team as up to 6 subagents. Step 3 SHALL say to decide whether
Subagents 3 and 6 run, then launch all applicable subagents in a single message, and SHALL NOT say
`Launch ALL 5 subagents`.

#### Scenario: Subagent 3 launch rules are present

- **WHEN** the Subagent 3 section is read
- **THEN** its `**Run condition:**` paragraph contains `CI workflows`, `Dockerfiles`,
  `build-args.env`, `dependencies`, `lockfile` and `packaging`
- **AND** its `**If unclear:**` paragraph begins with `launch Subagent 3`
- **AND** its `**When skipped:**` paragraph contains
  `skipped: no CI, Docker, dependency or packaging change`

#### Scenario: Subagent 6 launch rules are present

- **WHEN** the Subagent 6 section is read
- **THEN** its `**Run condition:**` paragraph contains `Decide from`,
  `mentioning it as background does not count`, `never count`,
  `solver decks`, `geometry`, `kinematics`, `force, moment and coefficient computation`, `frames`,
  `units`, `timestep and grid settings`, `surrogate`, `metrics`,
  `extraction and corpus pipelines`, `parsing, resampling or interpolation of solver output`,
  `tolerance, threshold or acceptance gate`, `convention document`, `scientific claim`, `figure`
  and `quoted physical or statistical value`
- **AND** its `**If unclear:**` paragraph begins with `launch Subagent 6`, so
  `do not launch Subagent 6` fails
- **AND** its `**When skipped:**` paragraph contains `skipped: no numerics or scientific claims touched`
- **AND** deleting any one paragraph fails the test even when the same words remain elsewhere in
  the file, including in an adjacent labelled paragraph

#### Scenario: Team size wording is updated

- **WHEN** the intro (text before `## Step 1`) and Step 3 are read
- **THEN** the intro contains `up to 6 specialized subagents` and
  `Subagents 1, 2, 4 and 5 always run`, and not
  `launches **5 specialized subagents in parallel**`
- **AND** Step 3 contains `Launch ALL applicable subagents`, `single message` and
  `decide whether Subagents 3 and 6 run`, and not `Launch ALL 5 subagents`

### Requirement: Orchestrator Applies Launch Rules

When running `/review-openspec`, the orchestrator SHALL launch each conditional subagent in the
same parallel batch as the always-run subagents when its run condition holds or is unclear, and
SHALL otherwise skip it and report the skip. This is runtime behaviour of the orchestrating model
and is not machine-verifiable. The physics-change scenario was run once (task 3.2) on the
pre-revision skill, where Subagent 3 always ran. The conditional Subagent 3 path (launch and skip),
the Subagent 6 skip path, the model-rejection fallback and the reworded Step 3 have never been run;
they are checked only by inspecting the skill text.

#### Scenario: Physics change launches Subagent 6

- **WHEN** `/review-openspec` reviews a change to how a force coefficient's sign or normalization is
  defined
- **THEN** Subagent 6 is launched in the same message as the always-run subagents, each with its
  declared `model`

#### Scenario: Convention-document change launches Subagent 6

- **WHEN** a documentation-only proposal changes a stated sign convention, force-coefficient value,
  or R² claim
- **THEN** Subagent 6 is launched

#### Scenario: Out-of-scope change skips a conditional subagent visibly

- **WHEN** a proposal touches none of Subagent 6's run condition items, or none of Subagent 3's
- **THEN** that subagent is not launched
- **AND** the synthesized review reports the skip with the subagent's skip text and a one-line reason

### Requirement: Math and Physics Review Checklist

Subagent 6's prompt template SHALL name `openspec/specs/coordinate-convention/spec.md` and
`openspec/specs/force-surrogate/spec.md` as the normative authority (including the definition
`ω_peak = 2π·f_star·radians(phi_amp_deg)` for F_ref) and `docs/coordinate-convention.md` as
narrative only; SHALL tell the reviewer to confirm the code implements what those pages say, and to
flag, not resolve, disagreement between the proposal, the pages, the code and the source paper. It
SHALL tell the reviewer to recompute every constant, reference point, sign, timestep or seed count
the proposal relies on from its source and report each as `VERIFIED / CONTRADICTED / UNVERIFIABLE`,
and SHALL receive the current specs being modified. Within the prompt template, a list starting
with `**Failure classes:**` SHALL name: sign and frame conventions (there is no insect-body frame;
forces in the wing frame and moments in the lab frame by design), reference points and
normalization, units (deg vs rad), CFL-limited timestep (the realized dt), domain size and boundary
conditions, time window and sampling, worst case rather than first case validation, variance across
at least 5 seeds, known-answer tests, and like-for-like comparisons.

#### Scenario: Authority and method are stated

- **WHEN** Subagent 6's prompt template (its `> ` lines) is read
- **THEN** it contains `openspec/specs/coordinate-convention/spec.md`,
  `openspec/specs/force-surrogate/spec.md`, `radians(phi_amp_deg)`,
  `docs/coordinate-convention.md`, `confirm the code implements`, `flag, do not resolve`,
  `recompute every constant`, `VERIFIED / CONTRADICTED / UNVERIFIABLE`, `{DESIGN_MD}` and
  `{CURRENT_SPECS}`

#### Scenario: Failure-class list covers each past failure class

- **WHEN** the `**Failure classes:**` list in Subagent 6's prompt template is read
- **THEN** it contains `sign and frame`, `no insect-body frame`, `reference point` (stem),
  `normaliz` (stem), `units`, `deg vs rad`, `CFL`, `realized dt`, `boundary conditions`,
  `time window`, `worst case`, `5 seeds`, `known-answer` and `like-for-like`
- **AND** deleting any one list item fails the test even though the authority sentence also
  mentions reference point, sign and normalization

### Requirement: Synthesis Covers Conditional Reviewers

The Step 4 synthesis instructions SHALL list physics/convention/units errors as BLOCKING and SHALL
map Subagent 6's verdicts to severities: a CONTRADICTED value the proposal relies on, with evidence,
is BLOCKING; UNVERIFIABLE values, and disagreements the proposal does not rely on, are IMPORTANT; a
divergence documented as deliberate in the authority pages is not an error. The Step 4 template
SHALL record which model ran each lens and whether each conditional subagent ran (with the reason)
or was skipped (with its skip text), and SHALL include a
`Numerical/physical correctness risk: LOW/MEDIUM/HIGH` line with the skipped value
`N/A (Subagent 6 skipped: <reason>)` and a `### 6. Math & Physics` section.

#### Scenario: Step 4 includes the conditional-reviewer outputs

- **WHEN** Step 4 (from the line `## Step 4` to the line `## Step 5`) is read
- **THEN** it contains `physics/convention/units errors`, `a CONTRADICTED value`,
  `arithmetic evidence, is BLOCKING`, `UNVERIFIABLE values`, `does not rely on are IMPORTANT`,
  `documented as deliberate`,
  `Reviewers: 1 sonnet, 2 opus, 3 opus|skipped, 4 sonnet, 5 sonnet, 6 opus|skipped`,
  `Numerical/physical correctness risk: LOW/MEDIUM/HIGH` and `N/A (Subagent 6 skipped: <reason>)`
- **AND** the lines `### 3. CI/CD & Build` and `### 6. Math & Physics` each stand on their own line,
  and each section contains `launched: <` and its own skip text
  (`skipped: no CI, Docker, dependency or packaging change`,
  `skipped: no numerics or scientific claims touched`)

### Requirement: Accurate CI Command in Reviewer Prompts

The prompts of Subagent 2 (TDD & Testing) and Subagent 3 (CI/CD & Build) SHALL quote CI's actual
test command, `uv run pytest -v -m "not gpu"`.

#### Scenario: CI command is quoted correctly

- **WHEN** the Subagent 2 and Subagent 3 sections are read
- **THEN** each contains `uv run pytest -v -m "not gpu"`

### Requirement: CI-Enforced Skill Structure

The text requirements above SHALL be checked by `tests/test_review_openspec_command.py`, which runs
in the existing CI `pytest` job without a GPU, network or Docker and reads the skill as UTF-8 from a
path resolved relative to the test file; a missing or undecodable file SHALL fail with an
`AssertionError` naming the path. Each anchor SHALL be searched only within its section: a subagent
section ends at the next `### Subagent` heading, a `---` line or a `## ` heading; a labelled
paragraph or list ends at the next blank line or the next line that starts with a bold label
(`**Label:**`). Anchors SHALL match case-insensitively, after collapsing whitespace, on word
boundaries; only anchors marked (stem) match as a word prefix. Every parser branch (section order,
count, placement after `## Step 4`, the `---` terminator, missing headings, missing file) SHALL have
a committed synthetic test (shown by the mutation check in tasks.md, not by a scenario).

#### Scenario: Missing or undecodable skill file

- **WHEN** the skill file is missing or is not valid UTF-8
- **THEN** the test fails with an `AssertionError` naming the path, not a setup error

#### Scenario: Removing an anchor fails the test

- **WHEN** any anchor named in this specification is removed or altered in its section
- **THEN** `uv run pytest tests/test_review_openspec_command.py` fails with an `AssertionError`
  naming the subagent or anchor that is missing or wrong

#### Scenario: Section bounding is tested in CI

- **WHEN** a subagent's anchor appears only in the next subagent's section or only in Step 4
- **THEN** the committed synthetic tests report it missing from its own section

#### Scenario: An anchor inside a longer word does not count

- **WHEN** the only occurrence of an anchor such as `sign` or `force` is inside a longer word such
  as `design` or `enforce`
- **THEN** the anchor is reported missing

#### Scenario: Test does not depend on the working directory

- **WHEN** the test file is run from the `tests/` directory instead of the repository root
- **THEN** it locates the skill file and gives the same result
