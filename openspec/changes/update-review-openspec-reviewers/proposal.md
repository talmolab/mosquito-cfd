# Change: Right-size `/review-openspec` reviewer models and add a math/physics reviewer

## Why

`/review-openspec` subagents were 11% of total usage in the user's `/usage` report of 2026-11-17 because all five
run on Opus, even the rule-checklist lenses. None of its lenses checks physics or conventions, the
class behind the project's costliest bugs (#108, #109, #92, the F_ref normalization fixed in
`standardize-force-normalization`, and the single-seed R² comparison behind #127).

## What Changes

- Each subagent spec block in `.claude/commands/review-openspec.md` declares an explicit `model`:
  `"sonnet"` for Subagent 1 (Spec Quality), 4 (Documentation) and 5 (Git Workflow); `"opus"` for
  Subagent 2 (TDD & Testing), 3 (CI/CD & Build) and the new Subagent 6.
- Step 3 instructs the orchestrator to pass each `model` field to the Agent tool exactly as given,
  and to decide whether Subagent 6 runs before the single parallel launch.
- New **Subagent 6: Math, Physics & Numerical Correctness**, launched under the run condition in the
  `review-openspec-skill` spec (numerics, convention documents, or scientific claims touched), or
  when that is unclear. A skip is reported in the synthesized review.
- Step 4: physics/convention/units errors become a BLOCKING category; the template gains a
  `Numerical/physical correctness risk` line (with an `N/A (Subagent 6 skipped: <reason>)` value)
  and a `### 6. Math & Physics` section.
- The intro sentence ("This skill launches **5 specialized subagents in parallel**") and Step 3's
  "Launch ALL 5 subagents" are reworded for the optional sixth.
- Subagent 2 and 3 prompts quote CI's real test command (`uv run pytest -v -m "not gpu"`) instead
  of `pytest -v`.
- New CI-enforced structural test `tests/test_review_openspec_command.py`.

Not breaking: the skill's input (`$ARGUMENTS` change-id) and output structure are unchanged apart
from the added Subagent 6 sections.

## Impact

- Affected specs: `review-openspec-skill` (new capability; precedent `runai-cluster-skill`)
- Affected code:
  - `.claude/commands/review-openspec.md` (modified)
  - `tests/test_review_openspec_command.py` (new)
- Not affected: solver, Docker images, `src/`, CI workflow files, run metadata. The two roadmaps
  (`docs/force_surrogate/roadmap.md`, `docs/field_surrogate/roadmap.md`) and
  `.claude/commands/new-feature.md` name `/review-openspec` without a subagent count or model.
- No `docs/CHANGELOG.md` entry: dev-tooling-only change (precedent `6a79e0a`, `5d5f1ad`).
- Follow-ups (out of scope):
  - #157: the same model split for `.claude/commands/review-pr.md`, and reconciling Subagent 6's
    checklist with `/review-pr` Subagent 3 (Scientific Rigor) so the project keeps one physics
    checklist. Physics review exists today only at PR time, after the design is fixed; Subagent 6
    adds it at proposal time.
  - #158: `docker.yml` rebuilds images on docs/test-only merges (pre-existing).
