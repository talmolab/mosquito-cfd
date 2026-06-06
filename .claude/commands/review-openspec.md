---
description: Critically review an OpenSpec proposal using a team of specialized subagents before approval
---

# OpenSpec Proposal Review — Subagent Team

You are a senior scientific programmer reviewing an OpenSpec proposal for `mosquito-cfd`,
a GPU-accelerated CFD project (IAMReX immersed-boundary AMR) with Python pre/post-processing
utilities and Docker-based CI. You value testing, code quality, reproducibility, metadata
preservation, traceability, numerical accuracy, correctness, and documentation that is clear,
succinct, and DRY.

This skill launches **5 specialized subagents in parallel** to critically review an OpenSpec proposal.
Each subagent has a distinct review lens and is instructed to be **adversarial** — finding gaps, not rubber-stamping.
After all subagents return, you synthesize their findings into a unified review verdict.

**Arguments:** `$ARGUMENTS` (the change-id to review)

## Step 1: Identify the Proposal

Determine which proposal to review:

- If the user specifies a change ID via `$ARGUMENTS`, use it directly
- Otherwise, run `openspec list` to find active proposals and ask the user which one to review
- Read the proposal's `proposal.md`, `tasks.md`, `design.md` (if exists), and all delta spec files under `specs/`

## Step 2: Gather Context

Before launching subagents, collect essential context that each agent will need:

1. Read the full proposal files (proposal.md, tasks.md, design.md, delta specs)
2. Read the CURRENT specs being modified (from `openspec/specs/`)
3. Read `openspec/AGENTS.md` for OpenSpec conventions
4. Read `openspec/project.md` for project conventions, constraints (FP64-only, A100/A40), and references
5. Note the affected code files listed in the Impact section
6. Note any related GitHub issues mentioned

Embed the full proposal text, current spec text, and file lists into each subagent prompt.

## Step 3: Launch Subagent Review Team

Launch ALL 5 subagents **in a single message** (parallel execution). Each subagent gets the full proposal
text embedded in its prompt. Each agent MUST read the actual files it needs — do not rely on summaries.

---

### Subagent 1: Spec Quality & OpenSpec Best Practices

```
subagent_type: "general-purpose"
description: "Review OpenSpec format quality"
```

**Prompt template:**

> You are reviewing an OpenSpec proposal for `mosquito-cfd`, a GPU CFD project.
> Your role: **Spec Quality & OpenSpec Best Practices Reviewer**.
>
> IMPORTANT: Be critical. Find problems. Do NOT rubber-stamp.
>
> First, read `openspec/AGENTS.md` to understand the full OpenSpec format rules.
> Then read the proposal files and current specs being modified.
>
> **Format rules to check:**
>
> - Delta sections MUST use: `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`
> - Requirements use `### Requirement: Name` (3 hashtags)
> - Scenarios use `#### Scenario: Name` (4 hashtags)
> - Every requirement MUST have at least one scenario
> - Scenarios MUST use **WHEN**/**THEN** format with bold markers
> - MODIFIED requirements MUST include the FULL existing text (partial deltas lose detail at archive)
> - Requirements use SHALL/MUST for normative language
>
> **Proposal rules:**
>
> - `proposal.md` must have: ## Why, ## What Changes, ## Impact
> - ## Why should be 1-2 sentences explaining the problem/opportunity
> - ## Impact must list: affected specs AND affected code files
> - BREAKING changes must be marked with **BREAKING**
> - Change ID must be verb-led kebab-case
>
> **Tasks rules:**
>
> - Must follow TDD order: tests FIRST, then implementation, then verification
> - Tasks must be small, verifiable work items (suitable for atomic commits)
> - Each task must have a checkbox `- [ ]`
> - Task groups should map to logical commit boundaries
>
> **Check for:**
>
> 1. Are any scenarios vague or untestable? (e.g., "should work correctly")
> 2. Are WHEN/THEN conditions specific enough to write a test from?
> 3. Do MODIFIED requirements include the FULL original text or just fragments?
> 4. Are there requirements without scenarios?
> 5. Are there missing edge case scenarios? (error paths, boundary values, empty states)
> 6. Does the Impact section list ALL affected specs and code files?
> 7. Could any requirements be split into smaller, more focused requirements?
> 8. Is the change ID appropriate (verb-led, descriptive)?
> 9. Run `openspec validate {CHANGE_ID} --strict` and report the result
>
> **Proposal to review:**
> {PROPOSAL_MD}
>
> **Tasks:**
> {TASKS_MD}
>
> **Delta specs:**
> {DELTA_SPECS}
>
> **Current specs being modified:**
> {CURRENT_SPECS}
>
> Return a structured review with:
> - PASS/FAIL verdict for each check
> - Specific issues found with suggested rewrites
> - Overall quality score (1-10) with justification

---

### Subagent 2: TDD & Testing Strategy

```
subagent_type: "general-purpose"
description: "Review TDD and testing plan"
```

**Prompt template:**

> You are reviewing an OpenSpec proposal's testing strategy for `mosquito-cfd`.
> Your role: **TDD & Testing Strategy Reviewer**.
>
> IMPORTANT: Be critical. The test plan must be concrete, complete, and CI-feasible.
>
> **Project testing infrastructure** (read `.github/workflows/ci.yml` and `openspec/project.md`):
>
> - **Framework**: pytest (dev dependency)
> - **CI**: single runner (ubuntu-latest), Python 3.11 via uv; jobs = lint (ruff check + ruff format),
>   test (`pytest -v`), dockerfile-lint (hadolint on `docker/Dockerfile.*`)
> - CI tolerates "no tests collected" (pytest exit code 5) while the suite is built out
> - The CFD solver runs in Docker/GPU and is NOT exercised by CI unit tests; Python utilities
>   (geometry generation, run-metadata capture) are what unit tests cover
> - **Code quality**: Ruff (line-length 88, py311, rule sets E/F/I/UP/D Google docstrings, E501 ignored). Black (line-length 88) is also configured; CI currently enforces only ruff.
>
> **Review the tasks.md for:**
>
> 1. **TDD ordering**: Are tests written BEFORE implementation?
>    - Write failing test → Implement feature → Verify test passes
>    - NOT: Implement feature → Write tests after
> 2. **Test specificity**: Is each test specific enough to implement? Not vague like "verify it works"
> 3. **Correct test framework**: Are the right tools used?
>    - Pure function logic (geometry math, metadata assembly) → pytest unit tests
>    - Build artifacts (wheel contents, metadata) → `uv build` + wheel install tests
>    - CLI entry points (`generate-wing-planform`) → subprocess or `uv run --isolated` tests
>    - Docker / solver behavior → what CAN be tested locally vs. only on a GPU host?
> 4. **Missing tests**:
>    - Error paths and validation failures
>    - Backward compatibility (old vertex files, missing config fields)
>    - Numerical edge cases (empty/degenerate geometry, NaN/inf, known-answer fixtures)
>    - Reproducibility metadata completeness (git SHA, docker image, hardware, timing)
> 5. **CI feasibility**: Will these tests run in CI?
>    - Do any tests require a GPU, Docker, network, or external services? (CI has no GPU)
>    - Are tests cross-platform safe? (path separators, line endings)
> 6. **Scenario-to-test mapping**: Do delta spec scenarios map 1:1 to tests in tasks.md?
>    - Every scenario SHOULD have a corresponding test; flag any scenarios without tests
> 7. **Verification section completeness**: Does tasks.md include:
>    - `uv build` (packaging validation) where relevant
>    - `uv run pytest` (tests)
>    - `uv run ruff check src/` (linting)
>    - `uv run ruff format --check src/` (formatting)
>    - hadolint on any changed Dockerfile
>    - CLI entry point smoke test where relevant
>
> **Tasks to review:**
> {TASKS_MD}
>
> **Delta specs (scenarios to match against tests):**
> {DELTA_SPECS}
>
> **Proposal summary:**
> {PROPOSAL_MD}
>
> Report:
> - Missing tests (with concrete descriptions of what to add)
> - TDD ordering violations (where implementation comes before tests)
> - Scenarios without corresponding tests (gap analysis)
> - Verification checklist gaps
> - Suggested additional test tasks with exact wording

---

### Subagent 3: CI/CD & Build Infrastructure

```
subagent_type: "general-purpose"
description: "Review CI/CD and build changes"
```

**Prompt template:**

> You are reviewing an OpenSpec proposal for `mosquito-cfd`.
> Your role: **CI/CD & Build Infrastructure Reviewer**.
>
> IMPORTANT: Be critical. Read the ACTUAL workflow and Docker files. Find real problems.
>
> **Current infrastructure** (read the actual files):
>
> - `.github/workflows/ci.yml` — lint (ruff check + ruff format) + test (`pytest -v`) + dockerfile-lint (hadolint)
> - `.github/workflows/docker.yml` — build & publish images to `ghcr.io/talmolab/mosquito-cfd` on push to main/tags
> - `docker/Dockerfile.fp64` (primary), `Dockerfile.fp32` (deprecated), `Dockerfile.python` (post-processing)
> - `docker/build-args.env` — pinned external dependency commits (amrex, AMReX-Hydro, IAMReX)
> - **Build backend**: `uv_build`; **Package manager**: uv with `uv.lock`; `uv sync --frozen` in CI
> - Base image `nvidia/cuda:12.4.1-devel-ubuntu22.04`; FP64-only; A100/A40
>
> **Review the proposal for:**
>
> 1. **Workflow changes**: Are proposed CI/docker.yml changes correct and complete?
>    - Will `uv sync --frozen` still hold (lockfile in sync)?
>    - Are image tags consistent with the convention (`{precision}`, `latest-{precision}`, `{precision}-{sha}`)?
>    - Are there race conditions or failure modes not addressed?
> 2. **Dockerfile changes**: Will they still pass hadolint (`failure-threshold: error`)?
>    - Are external dependency commits still pinned in `docker/build-args.env`? No `latest`/branch drift.
>    - Is FP64 preserved? No accidental FP32 build path resurrected.
>    - Are layers cache-efficient and apt installs cleaned up?
> 3. **GitHub Actions versions**: Are action versions reasonable (`actions/checkout`, `astral-sh/setup-uv`, `hadolint/hadolint-action`)?
> 4. **GHCR publishing**: Is the registry push configured correctly (permissions, auth, tags)?
> 5. **Reproducibility**: Does the change keep builds reproducible (pinned commits, lockfile)?
> 6. **Failure handling**: What happens when each step fails? Is the failure surfaced clearly?
> 7. **Migration risk**: Will these changes break an in-flight build if triggered before merge?
>
> Read these files:
> - `.github/workflows/ci.yml`
> - `.github/workflows/docker.yml`
> - `docker/Dockerfile.fp64`, `docker/build-args.env`
> - `pyproject.toml`
>
> **Proposal to review:**
> {PROPOSAL_MD}
>
> **Tasks:**
> {TASKS_MD}
>
> Report:
> - Incorrect assumptions about CI/Docker behavior
> - Missing failure handling
> - Reproducibility risks (unpinned deps, stale lockfile, FP32 regressions)
> - Compatibility issues
> - Suggested workflow/Dockerfile improvements with concrete YAML/Dockerfile snippets

---

### Subagent 4: Documentation Quality (Clear, Succinct, DRY)

```
subagent_type: "general-purpose"
description: "Review documentation impact"
```

**Prompt template:**

> You are reviewing an OpenSpec proposal for `mosquito-cfd`.
> Your role: **Documentation Quality Reviewer** — you enforce clear, succinct, DRY documentation.
>
> IMPORTANT: Be critical. Read the ACTUAL documentation files. Find real inconsistencies.
>
> **Documentation files to read and check** (read the ones that exist):
>
> - `README.md` — project readme (check badges, install/run instructions, version references)
> - `openspec/project.md` — project conventions, constraints, references (check Python version, deps, hardware, CLI examples)
> - `docker/` docs and any `CHANGELOG`/`docs/` if present
> - `.claude/commands/prepare-release.md` — release command (check accuracy after proposed changes)
>
> **Review for:**
>
> 1. **Completeness**: Does the proposal identify ALL documentation that needs updating?
>    - Python version appears in: README, `openspec/project.md`, `.python-version`, pyproject.toml
>    - CLI usage appears in: README, `openspec/project.md`
>    - Docker tags / registry appear in: README, `openspec/project.md`, workflows
> 2. **DRY violations**: Where is the same information stated in multiple places?
>    - Should any docs be consolidated or cross-referenced instead of duplicated?
>    - Are version numbers, Python versions, hardware specs, or dependency lists repeated?
> 3. **Accuracy after changes**: Will the proposed changes introduce NEW inconsistencies?
>    - If the CLI changes, do README/project.md examples still match?
>    - If Docker tags/registry change, do docs referencing them go stale?
>    - If pyproject.toml metadata changes, are docs referencing the old metadata stale?
> 4. **Succinctness**: Are any docs verbose, redundant, or describing features that don't exist?
> 5. **Reproducibility docs**: If run-metadata fields change, are they documented?
>
> **Proposal to review:**
> {PROPOSAL_MD}
>
> **Tasks:**
> {TASKS_MD}
>
> Report:
> - Documentation files the proposal MISSED (needs updating but not listed)
> - DRY violations that should be addressed
> - Inaccuracies that will be introduced by the proposed changes
> - Suggested fixes with concrete rewrites

---

### Subagent 5: Git Workflow & Commit Strategy

```
subagent_type: "general-purpose"
description: "Review git workflow plan"
```

**Prompt template:**

> You are reviewing an OpenSpec proposal for `mosquito-cfd`.
> Your role: **Git Workflow & Commit Strategy Reviewer**.
>
> IMPORTANT: Be critical. Commits should be small, focused, and CI-safe.
>
> **Project git conventions** (check `git log --oneline -20` for commit message style):
>
> - Commit messages use conventional prefixes: `chore:`, `fix:`, `feat:`, `docs:`
> - PRs merged to main; CI runs on PRs (lint, test, dockerfile-lint)
> - Branch naming: feature branches off main
> - OpenSpec changes are archived after merge
> - AI-assisted commits include a `Co-Authored-By` trailer
>
> **Review the tasks.md for commit strategy:**
>
> 1. **Atomic commits**: Can each task group be committed independently with CI staying green?
>    - Bad: one giant commit touching pyproject.toml + Dockerfile + workflows + src + docs
>    - Good: separate commits for code, Docker, CI, docs
> 2. **Commit ordering**: Are there dependencies between tasks?
>    - Must lockfile updates precede `uv sync --frozen` in CI changes?
>    - Must `build-args.env` pin precede a Dockerfile change that uses it?
> 3. **CI safety**: Will CI stay green between commits?
>    - If a Dockerfile changes but `build-args.env` isn't pinned yet, will dockerfile-lint / build fail?
>    - What's the safe ordering to keep lint/test/dockerfile-lint green at every step?
> 4. **Suggested commit plan**: Propose a sequence of small commits with:
>    - Clear conventional commit messages
>    - Files affected per commit
>    - CI state after each commit (green/yellow/red)
>    - Dependencies noted
> 5. **PR strategy**: Single PR or multiple? If single, is it reviewable (not too large)?
> 6. **Risk mitigation**: What if a workflow/Docker change breaks the build? Rollback plan?
>
> **Tasks to review:**
> {TASKS_MD}
>
> **Proposal summary:**
> {PROPOSAL_MD}
>
> **Recent commit style** (run `git log --oneline -20`):
> Check the repo for actual commit message conventions.
>
> Report:
> - Tasks that are too large for a single commit
> - Ordering dependencies the proposal missed
> - CI breakage risks at each step
> - Concrete commit plan with messages and file lists
> - PR strategy recommendation

---

## Step 4: Synthesize Review

After ALL subagents return, synthesize their findings:

1. **Deduplicate**: Merge overlapping findings from multiple reviewers
2. **Prioritize**: Categorize issues as:
   - **BLOCKING** — Must fix before approval (spec errors, missing tests, reproducibility risks, CI breakage)
   - **IMPORTANT** — Should fix before implementation (missing edge cases, unclear scenarios, doc gaps)
   - **SUGGESTION** — Nice to have (style improvements, additional context)
3. **Create a unified review** with this structure:

```markdown
# OpenSpec Review: {change-id}

## Verdict: APPROVED / NEEDS REVISION / BLOCKED

## Summary
[2-3 sentence overall assessment]

## Blocking Issues
[Issues that MUST be resolved before approval]

## Important Issues
[Issues that SHOULD be resolved before implementation]

## Suggestions
[Optional improvements]

## Proposed Commit Plan
1. `type: message` — [files affected, CI state after]
2. `type: message` — [files affected, CI state after]
...

## TDD Plan
For each testable change:
1. Test to write first → expected failure → implementation to pass it

## Risk Assessment
- CI breakage risk: LOW/MEDIUM/HIGH — [explanation]
- Reproducibility risk: LOW/MEDIUM/HIGH — [explanation]
- Documentation drift risk: LOW/MEDIUM/HIGH — [explanation]

## Review Details by Agent
### 1. Spec Quality
### 2. TDD & Testing
### 3. CI/CD & Build
### 4. Documentation
### 5. Git Workflow
```

## Step 5: Present and Iterate

Present the synthesized review and ask:

1. Do you want to address blocking issues now (update proposal, tasks, and specs)?
2. Do you want to approve with important issues noted as additional tasks?
3. Do you want to revise the proposal first?

If revising, update `proposal.md`, `tasks.md`, and delta specs based on the agreed-upon changes.
Run `openspec validate {change-id} --strict` after any updates.
