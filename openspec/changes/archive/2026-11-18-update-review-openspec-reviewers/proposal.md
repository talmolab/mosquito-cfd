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
  and to decide whether Subagents 3 and 6 run before the single parallel launch.
- New **Subagent 6: Math, Physics & Numerical Correctness**, launched under the run condition in the
  `review-openspec-skill` spec (numerics, extraction pipelines, gates, convention documents, or
  scientific claims touched), or when that is unclear. A skip is reported in the synthesized review.
- **Subagent 3 (CI/CD & Build) becomes conditional**: launched only when CI workflows, Dockerfiles,
  `build-args.env`, dependencies, the lockfile or packaging are touched (or when unclear).
- Step 1 handles archived and unknown change ids; Step 2 defines every template placeholder and its
  fallback; Step 3 says what to do if the Agent tool rejects a model value.
- Step 4 maps Subagent 6's VERIFIED / CONTRADICTED / UNVERIFIABLE verdicts to severities and records
  which model ran each lens and why each conditional subagent ran or was skipped.
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
- Follow-ups found during the pre-PR self-review: #161 (`docs/coordinate-convention.md` uses ω for
  two quantities), #162 (`added_mass_force` label), #163 (analytic sign test).
- Follow-ups (out of scope):
  - #157: the same model split for `.claude/commands/review-pr.md`, and reconciling Subagent 6's
    checklist with `/review-pr` Subagent 3 (Scientific Rigor) so the project keeps one physics
    checklist. Physics review exists today only at PR time, after the design is fixed; Subagent 6
    adds it at proposal time.
  - #158: `docker.yml` rebuilds images on docs/test-only merges (pre-existing).

## Deviations from the first approved version (pre-PR self-review)

The `/review-pr` self-review of the implemented branch found one BLOCKING and twelve IMPORTANT
issues; the user chose to fix all of them in this change and to make Subagent 3 conditional.

### Why the normative specs instead of `docs/coordinate-convention.md` as Subagent 6's authority?

The docs page uses ω for the flap frequency 2πf in its kinematics table and, undefined, for the peak
stroke rate in `F_ref = ½·ρ·ω²·S_yy`. Read literally it gives F_ref = 134.17 instead of 200.27 at the
validated point (a factor φ_amp_rad² ≈ 1.49), so the approved prompt would have produced false
CONTRADICTED verdicts and could miss a real error of the same size. The normative definition
(`ω_peak = 2π·f_star·radians(phi_amp_deg)`) lives in `openspec/specs/force-surrogate/spec.md`. The
page is kept as narrative; its ambiguity is #161.

### Why a conditional Subagent 3 instead of five always-run reviewers?

At current list prices (Sonnet 5.5 is $2/$10 and Opus 5.5 $4/$20 per million input/output tokens,
i.e. half; assuming equal tokens per agent, see design D2) the approved split saved about 30% on
non-physics proposals but only about 10%, or nothing if Subagent 6 reads more than average, on
physics proposals, which are most proposals here. Skipping the CI/build reviewer when no CI, Docker,
dependency or packaging file is touched brings a typical physics review to 2 Opus + 3 Sonnet (about
a 30% saving) without moving any judgment-heavy lens to Sonnet. Test CI-feasibility stays covered by
Subagent 2.
