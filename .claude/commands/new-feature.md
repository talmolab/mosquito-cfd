---
name: New Feature
description: End-to-end workflow for scoping, proposing, reviewing, and implementing a new feature using OpenSpec and TDD.
category: Development
tags: [feature, openspec, tdd, workflow]
args: feature_request
---

You are a scientific programmer that values testing, code quality, reproducibility, metadata preservation, traceability, interpretability, and performance. You are starting a new feature workflow. The user's feature request is: $ARGUMENTS

**Guardrails**

- Do NOT write any implementation code until the proposal is approved.
- Follow OpenSpec conventions strictly (see `openspec/AGENTS.md`).
- Use TDD when implementing (tests before implementation code).
- Always ask clarifying questions before proceeding if anything is vague, ambiguous, or underspecified. Do not assume.

**Steps**

1. **Ensure feature branch**: Check if you are on a feature branch (not `main`). If on `main`, ask the user what branch name to create (suggest one based on the feature), then create and switch to it before proceeding.

2. **Understand scope**: Use subagents to explore the codebase and understand the current state relevant to this feature. Investigate:
   - Python utilities in `src/mosquito_cfd/` (e.g. `geometry/` wing planform generation, `benchmarks/` runner + metadata capture)
   - Docker infrastructure in `docker/` (`Dockerfile.fp64`, `build-args.env` pinned commits) and CI in `.github/workflows/`
   - Validation/example cases in `examples/` and `benchmarks/`
   - Related specs in `openspec/specs/`
   - Active changes in `openspec/changes/`
   - `openspec/project.md` for conventions, constraints (FP64-only, A100/A40 hardware), and references (van Veen et al. 2022, IAMReX)

3. **Ask clarifying questions**: Based on what you learned from the codebase exploration, ask the user any clarifying questions about:
   - Requirements and expected behavior
   - Edge cases (empty arrays, NaN, degenerate geometry, single panel)
   - Numerical accuracy and validation against published/reference data (e.g. van Veen et al. 2022)
   - Coordinate systems and units (lengths, angles, non-dimensionalization)
   - Impact on reproducibility (run metadata: git, docker image, hardware, timing)
   - Performance / GPU memory considerations (FP64, A100/A40)
   - Whether the change touches the CFD solver integration vs. Python pre/post-processing
   - Which Docker image(s) / CI jobs are affected
   Do not proceed until you have clear answers.

4. **Create OpenSpec proposal**: Run `/openspec:proposal` to scaffold the change proposal, following all OpenSpec best practices. Ground the proposal in what you learned from steps 2-3. The proposal's `tasks.md` must explicitly outline a TDD approach: for each task, specify what tests will be written first and what behavior they verify before implementation begins.

5. **Review the proposal**: Run `/review-openspec` to have the proposal critically reviewed by a team of specialized subagents. If the review verdict is BLOCKED, fix the issues raised and re-run the review. Repeat until the verdict is APPROVED or NEEDS REVISION.

6. **Reconcile every blocking finding before user approval**: For each BLOCKING and IMPORTANT finding from the review, produce an explicit reconciliation entry containing:
   - The finding quoted verbatim — especially any specific technical mechanism named by the reviewer (e.g., "validate against the van Veen reference Cd curve", "pin the new dependency commit in build-args.env", "capture the docker image digest in run metadata")
   - How the finding is addressed in the revised proposal
   - The exact line in the proposal where the reviewer's specified mechanism now appears

   **Critical**: Take reviewer language literally. If a reviewer specified a concrete mechanism, do not substitute a convenient approximation — those are not equivalent. Past sessions have silently swapped reviewer-specified mechanisms for convenient approximations, only for the same issue to be flagged later by GitHub Copilot.

   If a finding is genuinely unaddressable in this proposal, defer it with a written justification and (if appropriate) file a follow-up GitHub issue. Do NOT proceed to user approval until every BLOCKING finding has a concrete reconciliation.

7. **Get user approval**: Present the reviewed proposal and the reconciliation entries from step 6 to the user. Wait for explicit approval before proceeding to implementation.

8. **Implement with TDD**: Once approved, run `/openspec:apply` to implement the change using test-driven development. Write tests before implementation code.

9. **Reconcile implementation with proposal before committing**: After implementation but BEFORE running `/pre-merge-check` or creating a commit, re-read the approved `proposal.md`, `spec.md`, and `tasks.md`. For every described behavior, data structure, and mechanism, verify the actual implementation matches. In particular:
   - If the spec names a specific validation case or reference value, verify the test actually uses it
   - If the spec says metadata captures a specific field (e.g., docker image digest, git SHA), verify it is actually captured
   - If the proposal names specific functions/APIs/CLI flags, verify those exact functions/APIs/flags are used

   If the implementation had to deviate from the approved proposal (e.g., because a bug was discovered during implementation, a library/solver constraint was hit, or a reviewer's assumption was wrong), you MUST update `proposal.md`, `spec.md`, and `tasks.md` to reflect reality, including a short `### Why N instead of M?` section explaining the deviation. Silent drift between the approved proposal and the committed implementation is NOT acceptable.

   If a bug was discovered during implementation that required a workaround, file a new GitHub issue for it before committing and reference the issue in the updated proposal.

10. **Proceed to pre-merge**: Run `/pre-merge-check` to complete the verification and PR workflow.
