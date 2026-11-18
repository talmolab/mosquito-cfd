# Tasks: update-review-openspec-reviewers

All work happens in the worktree `C:\repos\mosquito-cfd\.claude\worktrees\update-review-openspec-reviewers`
(branch `update-review-openspec-reviewers`). Follow-ups #157 and #158 are already filed.

## 1. Red phase: tests first, against `main`'s skill file

- [x] 1.1 Discard the pre-applied 5-line edit: in the worktree,
      `git restore .claude/commands/review-openspec.md` (that one path only; never `git restore .`,
      `git checkout -- .`, `git clean` or bare `git stash`). Confirm
      `git diff --quiet -- .claude/commands/review-openspec.md`. It is re-typed in 2.1. (design D5)
- [x] 1.2 Write `tests/test_review_openspec_command.py` with the helpers and matching rules in
      design D4, holding the spec's anchors as module-level constants.
      Parser unit tests (synthetic markdown; each must raise `AssertionError` naming the subagent
      or anchor):
      - `test_last_section_does_not_swallow_step4`, parametrized over (a) a `---` line before
        `## Step 4` and (b) no `---` line: Step 4 holds the skip text, Subagent 6 does not; the
        skip check raises
      - `test_parser_rejects_duplicate_subagent_number`
      - `test_parser_rejects_missing_model`
      - `test_parser_rejects_duplicate_model_key`
      - `test_parser_rejects_unquoted_model`
      - `test_parser_rejects_section_without_fence`
      - `test_parser_requires_spec_block_first` (first fence lacks `subagent_type:`)
      - `test_parser_ignores_model_outside_fence` (prose has `model: "opus"`, block has none; raises)
      - `test_labelled_block_ends_at_blank_line`
      - `test_labelled_paragraphs_do_not_merge` (three adjacent labels with no blank lines; an
        anchor present only in the next paragraph is not found)
      - `test_prompt_template_keeps_quoted_paragraphs_apart` (a bare `>` line ends a labelled list)
      - `test_anchor_matches_on_word_boundary` (`sign` inside `design`, `force` inside `enforce`
        are not found; `normaliz` matches `normalization`) [An anchor inside a longer word does not
        count]
      Skill-content tests (scenario in brackets):
      - `test_subagent_models_exact`: `{1: "sonnet", 2: "opus", 3: "opus", 4: "sonnet", 5: "sonnet",
        6: "opus"}`, in order, all before `## Step 4` [Rule-checklist reviewers use Sonnet;
        Judgment-heavy reviewers use Opus; Subagent set drifts]
      - `test_step3_model_pass_through` and `test_step3_has_no_inherit_wording` [Step 3 states the
        pass-through rule]
      - `test_team_size_wording` (includes "not `Launch ALL 5 subagents`") [Team size wording is
        updated]
      - `test_subagent6_run_condition`, `test_subagent6_if_unclear`, `test_subagent6_when_skipped`
        [Launch rules are present in their labelled paragraphs]
      - `test_subagent6_authority_and_method` [Authority and method are stated]
      - `test_subagent6_failure_classes` [Failure-class list covers each past failure class]
      - `test_step4_covers_subagent6` [Step 4 includes the Subagent 6 outputs]
      - `test_ci_command_in_subagents_2_and_3` [CI command is quoted correctly]
      Not covered by any automated test (runtime behaviour): the three scenarios under
      "Orchestrator Applies Launch Rules" (3.2 covers the first; the other two by text inspection
      only). "Removing an anchor fails the test" is shown by 3.1; "Test does not depend on the
      working directory" by 4.4.
- [x] 1.3 Run `uv run pytest tests/test_review_openspec_command.py -v`. Record per test: parser unit
      tests PASS; `test_subagent_models_exact` FAILS naming a subagent (Subagent 1's missing model
      or the missing Subagent 6); `test_step3_model_pass_through`, `test_team_size_wording` and
      `test_ci_command_in_subagents_2_and_3` FAIL naming their anchor;
      `test_step3_has_no_inherit_wording` PASSES on `main` (expected; 3.1 proves it can fail);
      the Subagent 6 and Step 4 tests FAIL with "no Subagent 6 section" or the missing Step 4 anchor.
      No test may ERROR (KeyError/AttributeError/FileNotFoundError).
- [x] 1.4 Commit the red test (commit 2 below). Do not push.

## 2. Green phase: implement the skill changes

- [x] 2.1 Add `model: "sonnet"` to Subagents 1, 4, 5 and `model: "opus"` to Subagents 2, 3.
- [x] 2.2 Step 3: the pass-through sentence (spec "Step 3 states the pass-through rule"),
      "Launch ALL applicable subagents" wording, "single message", and "decide whether Subagent 6
      runs" before launching; no `inherit`, no `Launch ALL 5 subagents`. (Superseded by 6.2:
      "decide whether Subagents 3 and 6 run", plus the model-rejection fallback.)
- [x] 2.3 Add the Subagent 6 section after Subagent 5: spec block (`model: "opus"`); the three
      labelled paragraphs outside the `> ` prompt template, each a single paragraph separated by a
      blank line; and the prompt template with the authority, flag-do-not-resolve and
      recompute/VERIFIED/CONTRADICTED/UNVERIFIABLE instructions and a `**Failure classes:**` list
      (one class per line). The list items start on the line directly after
      `> **Failure classes:**`, with no bare `>` line before or between them (unlike the file's
      other lists, which would make this list read as empty). No item may start with a bold label
      (`**Units:**`); `- **Units:** ...` is fine. No `---` line inside the section. (Spec requirements "Subagent 6
      Launch Rules Are Stated" and "Math and Physics Review Checklist"; design D3, D4.)
- [x] 2.4 Intro sentence wording; Step 4 BLOCKING definition adds physics/convention/units errors;
      Risk Assessment line with its N/A value; `### 6. Math & Physics` in Review Details with the
      skipped text.
- [x] 2.5 Subagents 2 and 3: replace the quoted test command `pytest -v` with
      `uv run pytest -v -m "not gpu"`.
- [x] 2.6 Run `uv run pytest tests/test_review_openspec_command.py -v`: all pass.

## 3. Verify

- [x] 3.1 Mutation check from a scratchpad script that loops over (description, old, new) triples,
      saves the skill's bytes first, restores from those bytes after each mutant (not
      `git checkout`), and prints PASS/FAIL per mutant. Mutants: each of the six `model` lines
      (remove; change value), `"opus"` → `opus` (unquoted), a `model` line moved into prompt prose,
      the Step 3 pass-through sentence removed, the inherit sentence re-added to Step 3,
      `Launch ALL 5 subagents` re-added to Step 3, each labelled paragraph removed, the blank lines
      between labelled paragraphs removed with `scientific claim` deleted from the run condition,
      the skip text removed from Subagent 6 and kept in Step 4, the skip text removed from Step 4,
      each `**Failure classes:**` list item deleted as a whole line, each authority/method anchor,
      each other Step 4 anchor, each CI-command anchor, each run-condition anchor phrase deleted
      individually (including "force," alone, "and coefficient" alone, and "timestep and grid
      settings"), each Step 3 positive anchor and the intro anchor deleted, `launch Subagent 6`
      replaced with `skip Subagent 6` in the If-unclear paragraph, "Subagent 2 inherits the session
      model." added to Step 3, the whole Subagent 6 section removed, the Subagent 6 heading
      duplicated. Every mutant must fail the test. One control must PASS: the spec's checklist
      prose copied word for word (plural "reference points", "worst case rather than first case"). (`PYTHONDONTWRITEBYTECODE`
      does not apply: only the `.md` is mutated.) Paste the output into the PR description.
- [x] 3.2 Manual smoke run of the launch path (runtime behaviour, not machine-checkable). Expected
      outcome, written down before running: six Agent calls in one assistant message; models
      1 sonnet, 2 opus, 3 opus, 4 sonnet, 5 sonnet, 6 opus; synthesis contains the
      `Numerical/physical correctness risk` line and `### 6. Math & Physics`. Procedure: from this
      worktree, read the new `.claude/commands/review-openspec.md` and execute it with the
      argument `openspec/changes/archive/2026-11-16-fix-wing-force-sign-convention` (an archived
      path, since Step 1's `openspec list` only shows active changes). Then, in the session JSONL
      under `~/.claude/projects/`, extract every `Agent` `tool_use` in the launching assistant
      message with its `model` input, and the `message.model` of each subagent transcript's
      assistant turns. Paste both into the PR description. The skip path and the
      convention-document path are not smoke-run (one run chosen to limit cost).

## 4. Verification commands

- [x] 4.1 `uv run pytest -v -m "not gpu"` (full suite green)
- [x] 4.2 `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`
- [x] 4.3 `uv run ruff format --check` on the same paths
- [x] 4.4 From `tests/`: `uv run pytest test_review_openspec_command.py` (working-directory
      independence)
- [x] 4.5 `openspec validate update-review-openspec-reviewers --strict`
- Not applicable: `uv build`, hadolint and a CLI smoke test (no `src/`, Dockerfile or entry-point
  change).

## 6. Revision after the pre-PR `/review-pr` self-review (do before section 5)

The self-review found 1 BLOCKING and 12 IMPORTANT issues; all are fixed here (proposal
"Deviations"). Follow-ups #161, #162, #163 filed.

Test and scenario names in 1.2 are the original ones; 6.1 renamed and extended them (e.g.
`test_subagent6_launch_rules`, `test_step4_covers_conditional_reviewers`).

- [x] 6.1 Red: extend `tests/test_review_openspec_command.py` with the new spec anchors (Step 1,
      Step 2, Step 3 fallback, Subagent 3 launch rules, the extended Subagent 6 run condition,
      authority and failure classes, Step 4 severity/recording) and the missing parser tests:
      `test_last_section_does_not_swallow_step4` fixed (label only in Step 4),
      `test_subagent_anchor_not_satisfied_by_next_subagent`, `test_parser_rejects_out_of_order`,
      `test_parser_rejects_missing_subagent`, `test_parser_rejects_seventh_subagent`,
      `test_parser_rejects_colonless_extra_heading`, `test_parser_rejects_section_after_step4`,
      `test_rule_line_ends_section`, `test_missing_step_heading_is_assertion`,
      `test_missing_skill_file_is_assertion` (monkeypatched path), `test_undecodable_skill_is_assertion`.
      Use `check_step3` from the tests and split the Step 3 constants (pass-through vs team size).
      Run against the current skill: every new content test fails naming its anchor; parser tests
      pass; nothing errors. Commit red, do not push. Done as `fa6e5ab`: 25 parser tests passed,
      9 content tests failed with AssertionErrors naming their anchor, none errored. `check_step3`
      was split into three used checks (`check_step3_pass_through`, `check_step3_no_inherit`,
      `check_team_size`) rather than kept as one.
- [x] 6.2 Green: edit the skill for every requirement change (authority, frames, CFL realized dt,
      new failure classes, run-condition additions and decision inputs, Subagent 3 launch rules,
      Step 1/2/3 additions, Step 4 severity mapping, `Reviewers:` and `launched:` recording, intro
      and Step 3 wording, the "Then\nLaunch" capitalization). Test file green. Done as `35071c7`;
      the green phase also fixed a matcher bug (a trailing boundary after an anchor that ends in
      punctuation), recorded in design D4.
- [x] 6.3 Extend the 3.1 mutation script to every new anchor and parser branch; every mutant
      killed, control passes, file restored and hash verified. Final run: 115 skill mutants and
      26 test-helper mutants killed by real test failures (a kill by import or collection error
      is not counted), control passing, both files' sha256 verified. Two survivors found and
      covered along the way: `test_parser_rejects_extra_spec_block` and
      `test_step4_section_requires_its_own_launched_record`.
- [x] 6.4 Targeted re-review (TDD on Opus, spec quality on Sonnet) of the revision; findings
      reconciled: the trailing word boundary, the severity verdicts, the If-unclear fail-safe
      wording and the per-section Step 4 records are now pinned; two missing-heading guards, the
      label-in-quote rule and the missing-section branch have tests; spec anchors added for the
      fallback, always-run, background-mention and recompute clauses; stale text corrected.
- [x] 6.5 Re-run 4.1-4.5. Clean run at `d67719e` (nothing else touching the tree): pytest exit 0, 2004 passed, 22 skipped, 16 deselected; ruff clean; openspec valid. An earlier "1 failed" was a false failure from running the in-place mutation script concurrently with the full suite.
- Note on 3.2: the smoke run was on the pre-revision skill (`052cdb3`), where Subagent 3 always ran.
  It does not change any `model` line, so the evidence that each subagent ran on its declared model
  carries over; Step 3's launch wording was reworded, so the carry-over covers only the declared
  models. Not re-run (cost). The conditional Subagent 3 path, the Subagent 6 skip path and the
  model-rejection fallback have never been run.

## 5. PR and post-merge

- [x] 5.1 Push, open the PR, run `/pre-merge-check` (no Copilot step). PR body: summary,
      motivation ("the physics/convention failures in #108, #109 and #92 were outside every
      existing reviewer lens"), red-phase evidence (1.3, 6.1), mutation output (3.1, 6.3), smoke
      run (3.2), self-review findings and fixes (6), verification (4.x), "Follow-up: #157, #158,
      #161, #162, #163", rollback note (`git revert` of the squash commit). Never use closing
      keywords or negated forms of them near an issue number.
- [x] 5.2 After merge, confirm with `gh pr view <N> --json state,mergeCommit`.
- [x] 5.3 From the main checkout: `git worktree remove .claude/worktrees/update-review-openspec-reviewers`.
- [x] 5.4 `git branch -D update-review-openspec-reviewers` (`-D` because squash-merged branches
      are not ancestors of main; only after 5.2), then `git push origin --delete` if GitHub has not
      deleted it, and `git remote prune origin`.
- [x] 5.5 On main: `openspec archive update-review-openspec-reviewers --yes` (no `--skip-specs`;
      this creates `openspec/specs/review-openspec-skill/spec.md`). Replace its "Purpose: TBD"
      placeholder with a real Purpose, then `openspec validate --strict`.
- [x] 5.6 Commit `chore(openspec): archive update-review-openspec-reviewers OpenSpec change`
      ("Related: PR #N"), push.

## Commit plan (CI only evaluates the pushed head)

1. `docs(openspec): propose update-review-openspec-reviewers` (change folder only; green)
2. `test(review-openspec): pin per-subagent models and the Subagent 6 contract` (test file only;
   body "Red until the next commit"; never pushed alone)
3. `feat(review-openspec): per-subagent models and conditional math/physics reviewer` (skill file;
   green)
4. `docs(openspec): tick tasks with red-phase, mutation and smoke-run evidence` (tasks.md; green)

Revision commits (after the pre-PR `/review-pr` self-review):

5. `docs(openspec): revise update-review-openspec-reviewers after pre-PR self-review` (`2a62e5d`)
6. `test(review-openspec): pin the self-review revision and cover every parser branch` (`fa6e5ab`,
   red, not pushed alone)
7. `feat(review-openspec): fix Subagent 6 authority, conditional Subagent 3, inputs and severity
   rules` (`35071c7`, green)
8. `test(review-openspec): cover the subagent_type count check` (`c6b1e75`)
9. `test(review-openspec): pin verdicts, fail-safe wording and remaining parser branches`
   (TDD re-review fixes, with these tasks and spec updates)
