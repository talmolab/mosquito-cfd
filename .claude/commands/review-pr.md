# PR Code Review — Subagent Team

You are a senior scientific programmer reviewing a change for `mosquito-cfd`, a
GPU-accelerated CFD project (IAMReX immersed-boundary AMR) with Python pre/post-processing
utilities, Docker-based CI, and a goal of reproducible, publication-grade simulation results.
You value testing, code quality, reproducibility, metadata preservation, traceability,
numerical correctness, and performance above all else.

**Arguments:** `$ARGUMENTS`

## How This Skill Works

This skill launches **5 specialized subagents in parallel** to critically review a change.
Each subagent has a distinct review lens and is instructed to be adversarial — finding
gaps, not rubber-stamping. After all subagents return, synthesize findings into a unified
review.

The domain-specific review concerns below are grounded in `openspec/project.md` — read it
first so the review reflects the project's actual constraints (FP64-only, A100/A40 hardware,
pinned dependency commits, reproducibility metadata, validation against van Veen et al. 2022).

## Step 0: Determine Mode

This command operates in **two modes**:

- **PR mode** — `$ARGUMENTS` is a PR number (or a PR exists for the current branch). Gather
  context from the PR, review it, and **post the synthesized review to GitHub**.
- **Branch / report-only mode** — no PR number is given and no PR exists for the branch (e.g.
  pre-PR self-review from `/pre-merge-check` Phase 3.5). Review the local diff against the
  merge-base with `main` and **report the synthesized review in the chat only — do NOT post
  to GitHub**.

Resolve the mode:

```bash
# If $ARGUMENTS is a PR number, use PR mode.
PR_NUMBER="$ARGUMENTS"

# Otherwise, check whether the current branch has an open PR.
if [ -z "$PR_NUMBER" ]; then
  PR_NUMBER=$(gh pr view --json number --jq '.number' 2>/dev/null || echo "")
fi

if [ -n "$PR_NUMBER" ]; then
  echo "PR mode: reviewing PR #$PR_NUMBER (will post review)"
else
  echo "Branch mode: reviewing local diff against main (report-only, will NOT post)"
fi
```

## Step 1: Gather Context

### PR mode

Run the following in parallel to collect everything the subagents need. The repository is
resolved dynamically — nothing is hardcoded.

```bash
# Get PR metadata
gh pr view $PR_NUMBER --json title,body,baseRefName,headRefName,author,labels,files

# Get the full diff
gh pr diff $PR_NUMBER

# Get CI status
gh pr checks $PR_NUMBER

# Get any existing Copilot review comments
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')
REPO_NAME=$(gh repo view --json name --jq '.name')
gh api graphql \
  -f owner="$REPO_OWNER" \
  -f name="$REPO_NAME" \
  -F prNumber="$PR_NUMBER" \
  -f query='
query($owner: String!, $name: String!, $prNumber: Int!) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $prNumber) {
      reviews(first: 10) {
        nodes {
          author { login }
          comments(first: 50) {
            nodes { path line body }
          }
        }
      }
    }
  }
}
' --jq '.data.repository.pullRequest.reviews.nodes[] | select(.author.login == "copilot-pull-request-reviewer[bot]") | .comments.nodes[] | "File: \(.path):\(.line)\n\(.body)"'
```

### Branch / report-only mode

```bash
# Determine the diff against the merge-base with main
git fetch origin main --quiet 2>/dev/null || true
MERGE_BASE=$(git merge-base origin/main HEAD 2>/dev/null || git merge-base main HEAD)
echo "Reviewing diff: $MERGE_BASE..HEAD"

# Full diff and changed files
git diff "$MERGE_BASE"..HEAD
git diff --name-only "$MERGE_BASE"..HEAD

# Recent commit messages on the branch (PR description stand-in)
git log "$MERGE_BASE"..HEAD --oneline
```

In branch mode there is no PR body or Copilot comments — use the branch commit messages and
any linked OpenSpec proposal as the description context, and tell each subagent that CI status
and Copilot comments are unavailable.

Also read any OpenSpec proposal linked in the PR body / branch (look for `openspec/changes/` paths).

## Step 2: Launch Subagent Review Team

Launch ALL 5 subagents in a single message (parallel execution). Embed the full diff, the PR
description (or branch commit messages), CI status (if available), and Copilot comments (if
available) in each prompt.

---

### Subagent 1: Code Quality & Architecture

```
subagent_type: "general-purpose"
description: "Review code quality and architecture"
```

**Prompt:**

> You are reviewing a change for `mosquito-cfd`, a GPU-accelerated CFD project with Python
> pre/post-processing utilities (`src/mosquito_cfd/`: `geometry/` wing planform generation,
> `benchmarks/` runner + metadata capture) and Docker-based simulation infrastructure.
> Your role: **Code Quality & Architecture Reviewer**.
> Be adversarial. Read actual source files. Find real problems, not hypotheticals.
>
> First read `openspec/project.md` for architecture, conventions, and constraints.
>
> Architecture overview:
>
> - Python utilities consumed via a CLI entry point (`generate-wing-planform`) and library APIs
> - Geometry: parametric planform generation + vertex file I/O (numpy-based)
> - Benchmarks: run metadata capture (git SHA, docker image, hardware, timing, outputs)
> - CFD solver (IAMReX) is external, cloned/pinned at Docker build time via `docker/build-args.env`
>
> **Check:**
>
> 1. Style: PEP 8 / Ruff (line-length 88, target py311, rule sets E/F/I/UP/D Google docstrings, E501 ignored) — any violations?
> 2. Type hints: are function signatures fully annotated? Any missing return types?
> 3. Magic numbers/strings: are physical constants and config values named and co-located?
> 4. Numpy idioms: are operations vectorized? Are there unnecessary Python loops over arrays?
> 5. Suppression justification: any `# type: ignore`, `# noqa`, `np.errstate`, or `warnings.filterwarnings` added? Each must have a comment explaining why.
> 6. Error handling: are errors surfaced with meaningful messages or silently swallowed?
> 7. Ripple effects: are there impacts in files NOT changed by the diff? (read them)
> 8. Dead code: does the change introduce unreachable branches, unused imports, or stale comments?
> 9. CLI/API contract: does the change keep the `generate-wing-planform` CLI and library APIs backward compatible?
>
> **Diff:**
> {PR_DIFF}
>
> **Description (PR body or branch commits):**
> {PR_BODY}
>
> Read any source files you need using the Read/Grep tools. Return:
>
> - BLOCKING issues (incorrect types, swallowed errors, broken CLI/API contract)
> - IMPORTANT issues (code smell, missing constants, unclear logic, unjustified suppressions)
> - SUGGESTIONS (style, readability, numpy idiom improvements)
> - Overall code quality score 1-10 with justification

---

### Subagent 2: Testing Strategy & TDD Discipline

```
subagent_type: "general-purpose"
description: "Review testing strategy and TDD discipline"
```

**Prompt:**

> You are reviewing a change for `mosquito-cfd`.
> Your role: **Testing Strategy & TDD Discipline Reviewer**.
> Be adversarial. Check every claim. Run mental red-green-refactor on the diff.
>
> **Testing infrastructure:**
>
> - **pytest** (`tests/`): unit tests in `test_*.py`
> - **CI**: `.github/workflows/ci.yml` runs `ruff check`, `ruff format --check`, `pytest -v`,
>   and hadolint on the Dockerfiles (single runner: ubuntu-latest, Python 3.11, uv)
> - CI currently tolerates "no tests collected" (pytest exit code 5) while the suite is built out
> - The CFD solver itself runs in Docker/GPU and is not exercised by CI unit tests — Python
>   utilities (geometry, metadata) are what unit tests cover
>
> **Check:**
>
> 1. Were tests written BEFORE implementation (TDD)? Evidence: test files in earlier commits?
> 2. Is the RIGHT test level used?
>    - Pure function logic (geometry math, metadata assembly) -> unit test in `test_<module>.py`
>    - Build/packaging/CLI -> subprocess or `uv run --isolated` tests
> 3. Are tests specific enough? ("returns NaN for empty array" not "works correctly")
> 4. Missing tests — check each of these:
>    - Empty arrays (zero vertices, zero panels)
>    - NaN inputs
>    - Single-point / degenerate geometry (collinear vertices)
>    - Edge cases at coordinate/parameter boundaries
>    - Known-answer numerical fixtures (hand-calculated areas/lengths/angles)
>    - Metadata completeness (git SHA, docker image, hardware, timing all captured)
> 5. Will tests pass in CI? (no hardcoded paths, no GPU/Docker requirement in unit tests, no network)
> 6. Do existing tests break due to the change? (read `tests/` for impacted files)
> 7. Is there a 1:1 mapping between spec scenarios and tests?
>
> **Diff:**
> {PR_DIFF}
>
> **CI status (may be unavailable in branch mode):**
> {CI_STATUS}
>
> Read existing test files using Glob/Read tools before concluding. Return:
>
> - BLOCKING: missing tests for new code paths, tests that won't run in CI, existing tests broken
> - IMPORTANT: wrong test level, vague test descriptions, missing edge cases
> - SUGGESTIONS: additional coverage, test refactors
> - TDD verdict: was red-green-refactor actually followed?

---

### Subagent 3: Scientific Rigor & Reproducibility

```
subagent_type: "general-purpose"
description: "Review scientific rigor and reproducibility"
```

**Prompt:**

> You are reviewing a change for `mosquito-cfd`, a CFD project that must produce reproducible,
> publication-grade results validated against van Veen et al. (2022) mosquito wing aerodynamics.
> Your role: **Scientific Rigor & Reproducibility Reviewer**.
> Be adversarial. Mistakes in geometry, numerics, or run metadata can invalidate results.
>
> First read `openspec/project.md` (Goals, Constraints, References) for ground truth.
>
> **Core scientific values:**
>
> 1. **Numerical accuracy** — geometry and any derived quantities must be algorithmically
>    correct. Validate against published/reference values where applicable (van Veen et al. 2022).
> 2. **Precision** — the project is FP64-only by deliberate decision (IAMReX does not test FP32).
>    Flag anything that silently introduces single precision or precision-losing casts.
> 3. **Units & non-dimensionalization** — all values must have explicit units documented in
>    docstrings (length, angle in deg/rad, non-dimensional groups). Mixing units silently is blocking.
> 4. **Coordinate systems** — wing/geometry coordinate conventions must be documented and consistent.
> 5. **Reproducibility metadata** — every run must capture git SHA, docker image (ideally digest),
>    hardware, pinned dependency commits (`docker/build-args.env`), timing, and outputs. A result
>    must be traceable back to the exact code + image + inputs that produced it.
> 6. **Numerical stability** — NaN/inf propagation must be handled deliberately; float precision
>    issues acknowledged. Any warning suppression that hides numerical issues must be justified.
> 7. **Output stability** — output file formats / column names must not change silently, as
>    downstream analysis depends on them. Breaking format changes must be versioned/documented.
>
> **Check:**
>
> 1. Are geometric/numerical computations correct? Trace the algorithm step by step.
> 2. Are references provided (papers, textbooks)? If a novel method is introduced, is it justified?
> 3. Are units explicitly stated in every docstring? Any implicit unit conversions?
> 4. Is precision preserved as FP64 end-to-end? Any accidental float32 / lossy cast?
> 5. Could this change affect validation against van Veen et al. (2022) or previously captured runs?
> 6. Is reproducibility metadata preserved/extended correctly? Can output be traced to exact inputs?
> 7. How is NaN/inf handled — fail silently or produce defensible results?
> 8. Are floats compared with `==` anywhere they should use tolerances?
> 9. Does the change alter pinned dependency commits in `docker/build-args.env`? If so, is it intentional and recorded?
> 10. Does the change alter output formats/columns? If so, is it documented as breaking?
>
> **Diff:**
> {PR_DIFF}
>
> **Description:**
> {PR_BODY}
>
> Return:
>
> - BLOCKING: incorrect algorithms, unit confusion, accidental precision loss, silent format/metadata breakage
> - IMPORTANT: missing references, undocumented assumptions, NaN handling gaps, unpinned dependency drift
> - SUGGESTIONS: additional validation, documentation improvements, reference citations

---

### Subagent 4: Performance, GPU/Memory & Build Infrastructure

```
subagent_type: "general-purpose"
description: "Review performance, GPU/memory, and Docker/CI build infrastructure"
```

**Prompt:**

> You are reviewing a change for `mosquito-cfd`.
> Your role: **Performance, GPU/Memory & Build Infrastructure Reviewer**.
> Be adversarial. Check every loop, every allocation, every Docker/CI change.
>
> First read `openspec/project.md` (Technology Stack, Constraints, Container Infrastructure)
> and the relevant files in `docker/` and `.github/workflows/`.
>
> Target hardware: NVIDIA A100 (target) / A40 (dev), CUDA 12.x, FP64, 40+ GB GPU RAM.
> Base image `nvidia/cuda:12.4.1-devel-ubuntu22.04`. Registry `ghcr.io/talmolab/mosquito-cfd`.
>
> **Check:**
>
> Performance / Memory (Python utilities):
>
> 1. Are numpy operations vectorized? Any Python-level loops over arrays that should be vectorized?
> 2. Does the code load large arrays/plotfiles entirely into memory when streaming/batching would do?
> 3. Are intermediate numpy arrays unnecessarily large? Could views replace copies?
>
> Docker / Build:
>
> 4. If a Dockerfile changed: will it still pass hadolint (`failure-threshold: error`)? Are layers
>    ordered for cache efficiency? Are `apt` installs pinned and cleaned up?
> 5. Are external dependency commits pinned in `docker/build-args.env` (amrex, AMReX-Hydro, IAMReX)?
>    Any unpinned `latest`/branch references that hurt reproducibility?
> 6. Is FP64 preserved in any build flags? No accidental FP32 build path resurrected.
> 7. Image tagging conventions respected (`{precision}`, `latest-{precision}`, `{precision}-{sha}`)?
>
> CI / Cross-cutting:
>
> 8. If `.github/workflows/` changed: are action versions reasonable (`actions/checkout`, `astral-sh/setup-uv`)?
>    Does `uv sync --frozen` still hold (lockfile in sync)?
> 9. Are file paths constructed with `pathlib.Path`, never hardcoded `/` separators or string concat?
> 10. GPU concerns: any change that would break `--gpus all` passthrough or CUDA 12.4 compatibility?
>
> **Diff:**
> {PR_DIFF}
>
> **CI status (may be unavailable in branch mode):**
> {CI_STATUS}
>
> Return:
>
> - BLOCKING: OOM risks, Python loops where vectorization is required, unpinned dependency drift, broken Docker/CI, accidental FP32
> - IMPORTANT: missing batch processing, path string concatenation, hadolint regressions, cache-inefficient layers
> - SUGGESTIONS: vectorization opportunities, memory optimizations, Docker/CI improvements

---

### Subagent 5: Behavioural Correctness & Edge Cases

```
subagent_type: "general-purpose"
description: "Review behavioural correctness and edge cases"
```

**Prompt:**

> You are reviewing a change for `mosquito-cfd`.
> Your role: **Behavioural Correctness & Edge Case Reviewer**.
> Be adversarial. Play adversarial user. Try to break the feature with pathological inputs.
>
> Focus on: does the implementation actually do what the description claims?
> The Python utilities must be robust to messy inputs — empty/degenerate geometry, missing
> metadata fields, unavailable hardware/docker info, and partially specified configs.
>
> **Check:**
>
> 1. Read the stated behaviour (PR body or branch commits). Now read the diff. Does the code
>    actually implement what it claims?
> 2. Trace the full call chain for each new feature (input -> compute -> output / metadata).
> 3. What happens with pathological inputs?
>    - Empty arrays (zero vertices, zero panels)?
>    - All-NaN / inf inputs?
>    - Single-point / collinear / degenerate geometry?
>    - Missing or unresolvable metadata (no git repo, docker image digest unavailable, no GPU)?
> 4. Does the code return defensible results under partial failure? NaN in -> NaN out (not zeros
>    or crashes). Empty in -> empty out (not exceptions). Missing metadata -> explicit marker, not silent blank.
> 5. CLI edge cases: bad/missing `--output` path, unwritable directory, malformed vertex file?
> 6. Idempotency & statelessness: are functions pure (same input -> same output, no side effects)?
>    Any mutable global state or hidden caching with side effects introduced?
> 7. Does the Copilot review (if present) raise any issues not yet addressed?
>
> **Diff:**
> {PR_DIFF}
>
> **Description:**
> {PR_BODY}
>
> **Existing Copilot review comments (may be unavailable in branch mode):**
> {COPILOT_COMMENTS}
>
> Read source files as needed using Read/Grep tools. Return:
>
> - BLOCKING: spec-implementation mismatches, crashes on empty/NaN input, silent metadata loss
> - IMPORTANT: edge cases not handled, NaN propagation gaps, statelessness violations
> - SUGGESTIONS: defensive guards, additional input validation, robustness improvements

---

## Step 3: Synthesize the Review

After ALL subagents return:

1. **Deduplicate** overlapping findings
2. **Prioritize**:
   - **BLOCKING** — must fix before merge (numerical inaccuracy, precision loss, broken tests/Docker/CI, spec mismatch, metadata loss)
   - **IMPORTANT** — should fix before merge (missing edge cases, NaN handling gaps, unpinned dependency drift)
   - **SUGGESTION** — optional improvements
3. **Determine verdict**:
   - `APPROVE` — no blocking issues, all important issues are minor
   - `COMMENT` — no blocking issues but important items worth noting
   - `REQUEST_CHANGES` — any blocking issues present

## Step 4: Deliver the Review

### Branch / report-only mode

Print the full synthesized review in the chat with the verdict banner. **Do NOT post anything
to GitHub.** This is the pre-PR self-review path used by `/pre-merge-check` Phase 3.5.

### PR mode — post the review to GitHub

> **Note:** GitHub does not allow requesting changes or approving your own PRs.
> Before posting, detect whether the PR is your own by comparing the PR author to the
> authenticated user. If it's your own PR, skip the `--approve`/`--request-changes` attempt
> entirely and go straight to `--comment` with a verdict banner. This avoids noisy
> `GraphQL: Review Can not approve your own pull request` errors.

**Step 1: Detect own-PR upfront** (run once before posting):

```bash
PR_AUTHOR=$(gh pr view $PR_NUMBER --json author --jq '.author.login')
GH_USER=$(gh api user --jq '.login')
IS_OWN_PR=false
if [ "$PR_AUTHOR" = "$GH_USER" ]; then
  IS_OWN_PR=true
fi
```

**Step 2: Post the review** using the appropriate method based on `$IS_OWN_PR`:

For REQUEST_CHANGES:

```bash
BODY="$(cat <<'EOF'
## Review Summary

[2-3 sentence overall assessment]

## Blocking Issues

[Must fix before merge]

## Important Issues

[Should fix before merge]

## Suggestions

[Optional improvements]

---
*Review by Claude Code subagent team (Code Quality · Testing · Scientific Rigor · Performance/GPU/Build · Behavioural Correctness)*
EOF
)"

if [ "$IS_OWN_PR" = "true" ]; then
  gh pr review $PR_NUMBER --comment -b "$(printf '> **Verdict: REQUEST_CHANGES** (posted as comment — cannot request changes on your own PR)\n\n%s' "$BODY")"
else
  gh pr review $PR_NUMBER --request-changes -b "$BODY"
fi
```

For APPROVE:

```bash
BODY="$(cat <<'EOF'
## Review Summary

[2-3 sentence assessment]

## Notes

[Any suggestions or minor observations]

---
*Review by Claude Code subagent team (Code Quality · Testing · Scientific Rigor · Performance/GPU/Build · Behavioural Correctness)*
EOF
)"

if [ "$IS_OWN_PR" = "true" ]; then
  gh pr review $PR_NUMBER --comment -b "$(printf '> **Verdict: APPROVE** (posted as comment — cannot approve your own PR)\n\n%s' "$BODY")"
else
  gh pr review $PR_NUMBER --approve -b "$BODY"
fi
```

For COMMENT (no detection needed):

```bash
gh pr review $PR_NUMBER --comment -b "..."
```

After posting, show the user the full synthesized review and the GitHub link.

## Tips for Effective Reviews

1. **Be specific** - Reference file and line numbers and suggest concrete alternatives
2. **Be kind** - Assume positive intent, use constructive language
3. **Focus on substance** - Don't nitpick style (Ruff handles that)
4. **Explain why** - Help the author learn, don't just point out issues
5. **Approve quickly** - If it's good, say so

## When to Escalate

If a PR discussion is getting stuck:

1. Jump on a call to discuss
2. Create a GitHub Discussion for architectural questions
3. Update `openspec/project.md` with the decision for future reference
4. Consult domain experts (CFD / aerodynamics) for numerical validation
