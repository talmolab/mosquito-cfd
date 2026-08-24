# Review Reconciliation — fix-git-provenance-wsl-worktree-v2

Multiple `/review-openspec` rounds were run against this proposal before user approval, per
`/new-feature`'s required review gate — one round table below per round actually run. This file
is the durable record of what each round found and how it was reconciled, so the citations in
`design.md` point at a real artifact rather than an unrecorded conversation. (This sentence
previously hardcoded a round count and went stale when a new round was added — the same class of
bug as finding #13/#17 below. Count the round-tables in this file directly rather than trusting
prose that states a total.)

**Archival note**: this file documents the review *process*, not the change's technical
rationale (that's `design.md`'s job). Per the documentation reviewer's round-3 recommendation, it
should be squashed into the PR description at merge time and deleted before this change is
archived via `/openspec:archive` — it is not meant to become a permanent fixture of the archived
spec tree.

## Round 1

| # | Severity | Reviewer | Finding | Fix | Location |
|---|---|---|---|---|---|
| 1 | BLOCKING | Spec Quality | The real production call sites (`metadata.py:185`, `sweep.py:326`) call `get_git_info()` with **no argument**; the drafted design/tests only covered an explicit `repo_path`, leaving the actual trigger for issue #77 undesigned/untested. | Added `repo_dir = repo_path if repo_path is not None else Path.cwd()` resolution. | `design.md` Decision 5; `specs/run-metadata/spec.md` scenario "no repo_path given resolves against the current working directory"; `tasks.md` 3.6 (test), 3.7 (implementation) |
| 2 | BLOCKING | Documentation | `tasks.md` had no task to add a `docs/CHANGELOG.md` entry, this repo's established convention for bugfix changes. | Added a CHANGELOG task. | `tasks.md` 4.5 |
| 3 | IMPORTANT | Spec Quality | `design.md` cited a nonexistent "clarifying-questions record" file three times, backing four design decisions with an unverifiable claim. | Reworded to cite the actual scoping questions inline (which question, which answer) instead of a file reference. | `design.md` Decisions 1, 2, 4 |
| 4 | IMPORTANT | TDD + Spec Quality (both) | No test covered a `.git` pointer file's realistic trailing `\n`, or a mixed forward/backslash gitdir line. | Added two tests. | `tasks.md` 1.6, 1.7 |
| 5 | IMPORTANT | TDD | The POSIX-pointer-rejected scenario was only exercised at the helper level (`_translate_windows_worktree_gitdir`/`_worktree_retry_env`), never through `get_git_info()` itself. | Added an end-to-end test. | `tasks.md` 3.3 |
| 6 | IMPORTANT | TDD | Verification section covered `pytest` only, no `ruff check`/`ruff format --check`, leaving a gap vs. what CI actually enforces. | Added an explicit lint/format verification step. | `tasks.md` 4.3 |
| 7 | IMPORTANT | TDD | A refactor extracting the subprocess body into a helper could silently move `subprocess.run` to a different module-qualified name, breaking `tests/test_metadata_capture.py`'s existing monkeypatch target. | Called out explicitly in the implementation task. | `tasks.md` 3.7 |
| 8 | IMPORTANT | CI/CD | `proposal.md`'s Impact section claimed "not baked into any image," which is false — `get_git_info()` IS compiled into `:fp64`/`:python` and IS executed pod-side, though the new retry path is unreachable there (pod images never `COPY` `.git`). | Corrected the Impact section to state both facts precisely. | `proposal.md` Impact |
| 9 | IMPORTANT | Git Workflow | The manual WSL verification step (then 4.3) needed to read as a hard merge gate, not an optional nicety, since CI cannot exercise the real bug. | Reworded with explicit "SHALL NOT merge without this confirmation recorded" language. | `tasks.md` 4.4 |

Suggestions not applied (judged non-blocking): the `-v2` change-ID suffix, an optional
`openspec/project.md` pointer note, a permission-denied-`.git`-file test, and a minor scenario-wording
nit on which subprocess calls receive the retried env.

## Round 2 (verification pass)

All nine Round 1 fixes were independently re-verified as VERIFIED-FIXED by a second wave of the
same five reviewer lenses, reading the actual current file contents rather than trusting the
Round 1 claims. `openspec validate fix-git-provenance-wsl-worktree-v2 --strict` passed.

Three new findings surfaced during Round 2 itself (this table was originally published with only
finding #10 — the omission of #11/#12 below was itself caught and corrected in Round 3; see that
section):

| # | Severity | Reviewer | Finding | Fix | Location |
|---|---|---|---|---|---|
| 10 | IMPORTANT | Spec Quality | The Round 1 edit fixing finding #3 introduced two *new* dangling citations of the same defect class — "see the reconciliation record in this change's review history" (design.md) and "see the reconciliation table presented to the user" (design.md) — neither pointing at any committed artifact. | Created this file (`review-reconciliation.md`) as the actual durable artifact, and repointed both citations at it. | `design.md` Decision 5, Open Questions; this file |
| 11 | IMPORTANT | TDD | Task 3.6 (`test_get_git_info_resolves_cwd_when_no_repo_path_given`) didn't say `subprocess.run` must be mocked; an unmocked retry against a fabricated `/mnt/c/...` path would not resolve on a Linux CI runner, risking a flaky/broken test. | Reworded to explicitly require the same mock-first-fails/retry-succeeds pattern as test 3.4. | `tasks.md` 3.6 |
| 12 | SUGGESTION | TDD | Task 4.3 claimed to "match CI's lint job exactly," which was false — CI's lint job also covers `scripts/`, `examples/prelim_sweep/`, `examples/prelim_sweep_fine_pilot/`, `examples/prelim_sweep_fine/`, none of which this change touches. | Reworded to state precisely what the local check does and doesn't confirm. | `tasks.md` 4.3 |

Minor pre-existing prose polish (Decision 3's CIFS-share bullet and the Risks section's
false-positive bullet) was noted as SUGGESTION-level in Round 2 and left as-is — Round 3
subsequently upgraded the Decision 3 issue to a real rewrite (see finding #14).

## Round 3 (second verification pass)

Verified all of Round 2's claimed fixes (findings #10, #11, #12) against current file content —
all VERIFIED-FIXED. This round's fresh, more skeptical pass — reviewing the reconciliation record
itself, not just the proposal — found:

| # | Severity | Reviewer | Finding | Fix | Location |
|---|---|---|---|---|---|
| 13 | BLOCKING | Spec Quality | This file's own Round 2 table only listed finding #10, silently omitting findings #11 and #12 even though `tasks.md` itself attributed both to "round 2" in its inline notes — the artifact built specifically to be the trustworthy durable review record was itself incomplete, the same failure class Round 2 was convened to catch. | Added findings #11 and #12 to the Round 2 table (this file); corrected the stale finding-count in `design.md`'s Open Questions to match the table's actual row count (re-tallied, not re-typed from memory, after this fix and again after every subsequent addition — see finding #17). | This file; `design.md` Open Questions |
| 14 | IMPORTANT | Spec Quality + TDD (both) | `design.md` Decision 5 states `get_git_info()` always passes `repo_dir` as `cwd=` to the initial git invocation; `specs/run-metadata/spec.md`'s "no repo_path given" scenario instead described the initial invocation as running "with no `cwd` override" — two different subprocess call shapes for the same code path (functionally equivalent only when `repo_dir == Path.cwd()`, but literally contradictory as written). | Reworded the spec scenario to match Decision 5: the initial invocation always passes `cwd=repo_dir`, where `repo_dir` resolves to `Path.cwd()` in the no-argument case — not "no cwd override." | `specs/run-metadata/spec.md` scenario "no repo_path given..." |
| 15 | SUGGESTION → fixed | Spec Quality + TDD + Documentation (three reviewers, independently) | Design.md Decision 3's CIFS-share bullet was genuinely self-contradictory (claims a CIFS-mounted case is "correct," then says the design "does not claim to generalize" to it), not merely a run-on sentence as Round 2 characterized it. | Rewrote the bullet to state plainly: the design is verified only for the WSL `/mnt/<drive>` convention; a CIFS-mounted equivalent is out of scope and untested, not implicitly claimed-correct. | `design.md` Decision 3 |
| 16 | IMPORTANT | Git Workflow | Task 4.4 (the manual WSL merge-gate verification) never said who performs it or whether the implementing agent has WSL access at all — ambiguous ownership risks the PR silently stalling. | Confirmed this session's shell has real WSL access (`wsl --status` succeeds, Ubuntu default distro); reworded task 4.4 to say the implementing agent SHALL attempt this directly (create a real worktree fixture, run `wsl git rev-parse HEAD` against it) before falling back to asking a human, rather than defaulting to human-only. | `tasks.md` 4.4 |

Suggestions from Round 3 not applied as separate fixes: a one-line `review-reconciliation.md`
pointer at the top of `proposal.md` (judged low-value given `design.md` already links it, and
Round 1 already declined a similar broader pointer suggestion), and consolidating tasks
1.2/1.6/1.7 into one `@pytest.mark.parametrize`d test (stylistic, doesn't change coverage — left
as separate named tests since each documents a distinct real-world failure mode PR #76's original
implementation had to handle).

## Round 4 (third verification pass)

Verified all four Round 3 fixes (findings #13-16) against current file content — all
VERIFIED-FIXED, including a full re-tally confirming the finding count/severity breakdown was
arithmetically correct at the time. This round found:

| # | Severity | Reviewer | Finding | Fix | Location |
|---|---|---|---|---|---|
| 17 | IMPORTANT | Spec Quality | Finding #13's own "Fix" column (written mid-edit, before findings #14-16 were added to the same round) said the count was corrected to "fifteen," but the actual total once all of Round 3's findings landed was sixteen — a miniature recurrence of the exact under-counting failure Round 3 itself was convened to catch. | Removed the hardcoded number from finding #13's Fix description (re-tallying a table while still adding rows to it is inherently fragile); this table's row count is now the single source of truth, re-tallied fresh for `design.md`'s summary line after every round rather than incrementally patched. | This file (finding #13 row); `design.md` Open Questions |
| 18 | IMPORTANT | Git Workflow + CI/CD (both, independently) | Task 4.4's worktree-creation instruction (`git worktree add`, no arguments) would likely fail outright in this exact session: bare `git worktree add <path>` defaults to checking out the current branch, and git refuses to check out a branch already checked out in another worktree — this session is already on `fix-git-provenance-wsl-worktree-v2` in this checkout. The task also never instructed cleanup afterward. | Reworded to require `git worktree add <path> --detach` (never contends with the branch already checked out here) at a path outside the tracked repo tree, followed by `git worktree remove <path>` once verification is recorded. | `tasks.md` 4.4 |
| 19 | SUGGESTION | CI/CD | Whether an ad-hoc verification worktree shows up as untracked cruft in `git status` depends on a local, unshared `.git/info/exclude` entry (this repo's committed `.gitignore` has no `.claude/worktrees/`-style rule) — environment-dependent, not guaranteed by the repo itself. Also: `git worktree list` on this repo already shows a real orphaned worktree from the prior (non-merged) PR #76 attempt, un-pruned since 2026-08-21 — a live example of exactly this hygiene gap, though it predates this change and is out of scope to clean up here. | Noted in task 4.4 that the verification worktree's path is not guaranteed to be gitignored on every clone, so the explicit `git worktree remove` step (finding #18) is not optional cosmetic advice. The pre-existing orphaned PR #76 worktree was flagged to the user directly rather than silently removed. | `tasks.md` 4.4 |

Suggestion #19's second half (the pre-existing PR #76 worktree) is **not** part of this change's
scope — it was surfaced as an observation during review, not something this proposal fixes. (It
was subsequently removed by the user via `git worktree remove` + `git worktree prune`, outside
this change's own task list — `git worktree list` now shows only the main worktree.)

## Round 5 (fourth verification pass)

Verified all three Round 4 fixes (findings #17-19) against current file content — all
VERIFIED-FIXED, including an independent from-scratch re-tally of every round-table's rows, which
matched `design.md`'s stated total exactly this time. This round found only cosmetic staleness,
no functional/design/test issues:

| # | Severity | Reviewer | Finding | Fix | Location |
|---|---|---|---|---|---|
| 20 | SUGGESTION | Spec Quality | This file's own opening sentence hardcoded "Three ... rounds" and was never updated when Round 4 was added — the same class of bug as findings #13/#17, just not yet caught because nothing re-read the intro prose specifically. | Reworded to describe the file's structure (one table per round actually run) instead of stating a specific count, so it cannot go stale again regardless of how many further rounds occur. | This file (opening paragraph) |
| 21 | SUGGESTION | Documentation + Git Workflow (both, independently) | Task 4.4's cleanup rationale referenced the orphaned PR #76 worktree in the present tense ("already sitting in..."), which became stale the moment the user manually removed it earlier in this same session. | Reworded to past tense, describing it as a historical incident that motivates the cleanup step, not a currently-existing condition. | `tasks.md` 4.4 |

No BLOCKING or IMPORTANT findings this round. All five reviewer lenses independently recommended
stopping here rather than running a sixth round — the technical design, test coverage, spec
delta, and merge-gate procedure have converged; remaining findings across rounds 4-5 were
progressively narrower (a stale number in review metadata, stale tense in a rationale clause),
not gaps in the actual change being proposed.
