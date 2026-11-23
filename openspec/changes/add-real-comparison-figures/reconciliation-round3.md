# Reconciliation of review round 3

**Verdict: NEEDS REVISION.** One blocker (spec B1) is fixed. Each lens reported:

| Lens | Verdict |
|---|---|
| Git | No blocker |
| TDD | Approve with changes |
| Docs | Approve |
| Math | Approve with one fix |
| Spec | NEEDS REVISION (B1) |

Every round-2 item was re-verified by its own reviewer: resolved, apart from the partials closed
below. Every MODIFIED block was diffed against its live requirement, and nothing unintended was
dropped.

**Abbreviations.**

- Reviewer prefixes: S = spec quality, T = TDD, D = docs, G = git, M = math.
- **viz** = `specs/visualization-tooling/spec.md`, **fs** = `specs/force-surrogate/spec.md`.
- **Req** = requirement, **Sc** = scenario.

## BLOCKING

**S-B1.** "Task 9.7 commits a red test … the anchor test fails at 9.7 … Rewrite: delete the anchor bullet from 9.2 and add it to 10.1 or 10.2 … Add it in the same commit as the README edits."

- **Fix:** the anchor bullet is deleted from 9.2. New task 10.1b ("Test first … committed with the README edits that make it pass") also checks that the three PNG links resolve (D-S7).
- **Where:** tasks 9.2, 10.1b.

## IMPORTANT

**S-I1, T-S2, M-S6.** "`edit_runs` cannot reach `phase_baseline_skill` … applied to `runs[0]` via `edit_runs` and to `phase_baseline_skill` via `edit_metrics`."

- **Fix:** adopted.
- **Where:** tasks 5.1 (thresholds); viz Sc "a recorded skill that does not reproduce is refused".

**S-I2.** "State the write order in design D5 … 'with the second `os.replace` patched to raise, exactly the first file exists, no temporary file remains, and no figure is open'."

- **Fix:** adopted. The write order is PNG, metrics, run_metadata.
- **Where:** design D5, Writing; tasks 3.2.

**G-I1.** "State in the Rendering rule that the scratch directories are outside the repo."

- **Fix:** adopted.
- **Where:** tasks Working rules (Rendering); viz Req "Committed comparison figures…" (Re-rendering); design D7.

**G-I2.** "outstanding ticks are committed as a tick-only `chore(openspec)` commit before the 11.3 fix commit."

- **Fix:** adopted.
- **Where:** tasks Working rules (Task ticks).

**G-I3.** "say 'no edits to tracked files other than the 9.5 code fix between 8.4 and 9.6'."

- **Fix:** adopted.
- **Where:** tasks Working rules (Task ticks).

**M-I1.** "'The coarse ratio is down from 2.3 before the corrected hinge geometry (#71) …' is contradicted by the history … Fix: delete the sentence … Add to 10.5: 'any historical value in the new prose is checked against `git show <commit>:…`'."

- **Fix:** the sentence is replaced with "The ratio has changed with each corpus correction (#36, #71); its history is in the git log of `figures/evidence_figure_metrics.json`." The 10.5 check is added.
- The current README's "down from ~2.3×" is itself wrong: the committed values were 2.27 at #25, 0.73 at #36 and 1.34 from #71 on. The rewrite removes it.
- **Where:** design D9 (the first span, and "Why this wording"); tasks 10.5.

**T-I1.** "Add a third hook … `edit_dataset(df)` edits the dataset frame **before** it is hashed …"

- **Fix:** adopted.
- **Where:** tasks 2.1; viz defect list ("both built before the dataset is hashed").

**T-I2.** "Add to viz:206: `phase_baseline.converged_min_wingbeat` set to `0` (via `edit_metrics`); Add to the section-3 mutants in 7.4: 'Drop the `converged_min_wingbeat` equality.'"

- **Fix:** adopted.
- **Where:** viz defect list; tasks 7.4.

**D-I1.** "design D7 contradicts the spec and tasks about scratch directories … Rewrite D7."

- **Fix:** adopted.
- **Where:** design D7 ("Every render, the first included, goes to a scratch directory outside the repository").

## SUGGESTIONS

**Adopted:**

- **S-S2:** stub builders named in 3.3.
- **S-S3, M-S4:** the same dyadic constant in every configuration (viz Sc, tasks 2.1).
- **S-S4:** subject in "Re-rendering".
- **S-S5:** the ε²/σ² check applies when R² is non-null.
- **S-S1, D-S5:** `tests/test_comparison_guards.py` added to the proposal's Impact.
- **M-S1:** the causal claim is conditional in both READMEs ("would be expected to add lift, so they are unlikely to explain it"). No test keys on the fine sentence (checked with `grep`).
- **M-S2, T-S3:** the `0.5 ± 1` fixture keeps the skill finite and is used for the diagnostic only.
- **M-S3:** out-of-range text is `outside ±3: <below> / <above>`.
- **M-S5:** the `1e-10` threshold bound is stated for both signs.
- **T-S1:** the null-skill defect is placed before `summarize_seed_sweep`.
- **T-S4:** the `1 − 1e-6` fixture plus its mutant.
- **T-S5:** beat-label and forbidden-pattern checks in 5.1 and 6.1. "Block not swapped" moved out of Caption.
- **D-S1:** proposal reflow.
- **D-S2:** the literal recipe in design D9.
- **D-S3:** which `Regenerating` heading.
- **D-S4 (partial):** design D9 cites the fs guard instead of restating it.
- **D-S8:** project.md phrase pinned by `test_kinematics_attribution`.
- **D-S9:** training-record pointer in D9.
- **D-S10:** "recomputed in review rounds 1–3" replaces the scratchpad citation.
- **D-N7 remainder:** the slice start is matched after whitespace collapse, and a missing start phrase raises `AssertionError` (fs Req and Sc).

**Declined:**

- **D-S4 (rest), trimming D3/D7 tolerance restatements to citations:** design already defers to the spec on conflict.
- **D-S6:** moot, since the `2.3` sentence is removed.
- **G-S1/S2/S3:** S1 and S3 are covered by the Working rules and 9.6. S2 is adopted in 9.2.
