# Review and reconciliation history: add-surrogate-comparison-bench

Six rounds of /review-openspec (2026-11-18), each followed by its reconciliation, concatenated
verbatim. Round 6 had no blocking findings; the user approved the proposal on 2026-11-22.

---

## OpenSpec Review (round 1): add-surrogate-comparison-bench

### Verdict: BLOCKED

Reviewers: 1 sonnet, 2 opus, 3 skipped, 4 sonnet, 5 sonnet, 6 opus. Each reviewer was pointed at the
proposal files and told to read them in full, instead of having the text pasted into its prompt.

### Summary

The conventions hold: frames, units, F_ref normalisation, the on-wing sign, phase ↔ time, the
Fourier-projection claim and every quoted exploration number were recomputed and VERIFIED. The
proposal is blocked on four kinds of problem:

- one gate quantity whose value depends on an unstated sampling choice;
- one claim the bench as specified cannot test;
- test-plan defects: a tolerance that fails a correct implementation, "bitwise" equality across
  machines, untested seams, and a missing task;
- workflow problems: a permanent sha tripwire, provenance ordering, and a dependency on an unmerged
  branch.

### Blocking issues

| ID | Source | Finding (verbatim mechanism) |
|---|---|---|
| B1 | 6 | Body-frame peak `max|C|` sampling is unspecified, and every f* = 0.85 config has an anomalous last row: a 3.3–6.1 % jump. At s55_f085_p45 the normal peak is 2.054 on the raw rows and 1.988 on the 256-grid, a 3.2 % difference, the same size as the 3.7 % yardstick. Fix: "both peaks are computed on the 256-point grid, model evaluated at grid phases and CFD interpolated from lab-frame CF then rotated at the grid phases", plus a scenario pinning ≈1.988. |
| B2 | 6 | "The bench re-tests the claim" is false. `control:0` (`default_rng(0).choice`) is not E4's subset (`default_rng(0).permutation(sorted(pool))[:18]`). None of the 6 controls is rank-deficient, so none reproduces the collapse case. Fix: add `control:e4_seed0` with E4's construction, or drop the wording. |
| B3 | 2 | The cross-machine "bitwise" ridge recompute is infeasible (BLAS/SIMD), and an argmin near-tie can flip the selection. Fix: exact equality on the discrete outputs (H, d, α, P, rank, edge flags); `rtol` ≈ 1e-10 on the continuous ones; record the winner–runner-up CV gap and assert it exceeds the tolerance. Bitwise only within one process. (6 also raised this, as I10.) |
| B4 | 2, 6 | The known-answer tolerance fails a correct implementation: the ridge bias at α = 1e-8 is about 1e-8. Fix: α = 1e-12 with tolerance 1e-8, and synthetic phases on the k/256 grid. Add a separate realistic-sampling test at about 1e-5. |
| B5 | 2 | The spec scenario "CPU tier runs without torch" has no task. Fix: a subprocess test asserting none of {torch, physicsnemo, scipy, sklearn} is in `sys.modules` after `import mosquito_cfd.surrogate_bench`, mutation-tested. |
| B6 | 2 | No task implements `fit_seed` or `predict_frame`. The `_fit_one_seed` default path is never run on CPU, and 7.3 is test-after. Fix: task 1.3b (CPU, with `build_model`/`train_model`/`predict` monkeypatched to recorders) checks that the default path calls `make_config_splits` once and passes byte-identical inputs to today's, with n_in = 5. An explicit split is used verbatim with n_in = 9, and an invalid split raises before any torch import. Task 1.6 implements the seams. 7.3 moves before 7.2. |
| B7 | 1 | The new `phase_harmonics` and bench-carve-out clauses in "PhysicsNeMo force-coefficient regressor" have no scenario. Fix: add scenarios (CLI default 1 and every seed receives H; GPU `build_model(n_in=9)`; no checkpoint is written or loaded for ridge). |
| B8 | 1 | The unmodified "Fine-corpus surrogate … reproducibility gate" says "no functional change (docstrings only)", which this change makes false. "Committed training artifacts" names only `surrogate/`. Fix: MODIFY both (historical wording; `surrogate_h3/` as a second location). |
| B9 | 5, 2 | The sha-pin test (0.1) is a permanent tripwire against the planned regeneration and #114. Its scope also differs between task and spec. Fix: a change-lifetime check that hard-codes {path: sha}, fails on added or deleted files, is run at the end of each task group, and has its result recorded in the PR body. It is not committed as a standing test, and the spec scenario is reworded to "within this change". |
| B10 | 5 | Provenance ordering. Writing artifacts into the repo dirties the tree mid-run. The recorded commit is unreachable after a squash merge, and review fixes make it stale. Fix: outputs go to scratch outside the repo; and either split the PR (artifacts produced from merged main) or add a rule to re-run after every code-affecting fix. |
| B11 | 4, 5 | The proposal's rationale cites the roadmap "Revision (2026-11-18)", which exists only on unmerged `docs-surrogate-comparison-plan` (a90a03f); task 9.2 edits the same table. Fix: merge that branch first as a stated prerequisite; 9.2 only after it. |
| B12 | 4 | The Track B roadmap (`docs/force_surrogate/roadmap.md`, rows 1–15) is missed. Fix: row 16 at archive time. |

### Important issues

- **I1 (6) Ranks.** With the cap, every bench training matrix is full rank (interpolation 17/17,
  faces 14/14, controls 17/17), so the recorded deficit is always 0. The deficits occur in the CV
  folds instead: at d = 3, 6–9 of 18 folds per control are rank 16. Record the minimum fold rank and
  the number of deficient folds per (split, d).
- **I2 (6) Skill across splits.** Skill is not comparable across splits: baseline RMS is 0.11 of peak
  for interpolation and about 0.20 on the pitch faces. Record baseline RMS, and compare splits by
  `rmse_pct_component_peak`.
- **I3 (6) Normalisers.** CF_y is not near zero (per-config peak ≥ 0.40 of the corpus peak), so that
  scenario must be synthetic. Require one normaliser for both sides of every yardstick.
- **I4 (6) GCI provisional reasons are incomplete.** Add: startup beat of a 1-beat run; T3c fine
  dt 2.5e-4 at cfl 0.3 vs the corpus's 5e-4 at cfl 0.6 (temporal error not covered); z boundary
  condition 2 vs 4; stroke 70° outside 35–55°.
- **I5 (6) `coarse_vs_fine`.** It bounds the coarse grid's error, not the fine grid's. Label it an
  upper bound; also report it scaled by 1/(r^p − 1) (r = 4, p ≈ 1.38, about 1/5.8).
- **I6 (6, 1) `late_beat`.** Define it for the peaks as |max|C_N| − max|C_{N−1}|| / max|C_N|. State
  which beat is the target when there are ≥ 4 beats. Use `wingbeat` indices everywhere. Add boundary
  scenarios at 3 and 4 beats. State which wingbeats `beat1_vs_beat2` reads, from the unfiltered frame.
- **I7 (6, 2) Rotation test.** The planned test is circular. Replace it with hand-written known
  answers: phase 0 → cf_normal 1, cf_chord 0; phase 0.25 → cf_normal 1; tolerance 1e-12. This pins
  phase→time and deg→rad.
- **I8 (6) Selection lands on a grid edge.** The CV score falls strictly with H, so the choice lands
  on H = 32 every time, ties never occur and `at_grid_edge` is always true. Pre-register a rule:
  smallest H, then d, within 1 % of the best score.
- **I9 (6) `mlp_h3`.** It was chosen on the labelled holdouts in E4, so its interpolation result is
  optimistic. State this; the face and control results are not affected.
- **I10 (2) Results schema.** `results.parquet` must carry `sse`, `sse_baseline`, `n_rows`,
  `grid_sse` and `n_grid`, so pooled values recompute. Timing is excluded from the equality tests.
- **I11 (2) `mlp_h1` regression check.** Make it a permanent CPU test of committed `results.parquet`
  against committed `surrogate/metrics.json`. Pre-register the criterion (exact) and preconditions
  (library versions). Add: the interpolation baseline with an explicit list of the 21 is
  byte-identical to the no-list call.
- **I12 (2, 5, 1) Evidence-figure output names.** These are required, not "if needed": the script
  writes fixed names. Add a test-first task: default names unchanged; `h3` names correct; shipped
  files untouched.
- **I13 (2, 5) Provenance tests for h3.** Use a separate `tests/test_committed_surrogate_h3_provenance.py`,
  not a reparametrisation; read features from JSON on CPU (the `.pt` only on GPU); add the new
  `run_metadata` files to the clean-commit test; bench digest and dataset sha match the corpus.
- **I14 (2) Gate boundary tests.** error == yardstick → `inside`; one config over → `outside`;
  NaN error never `inside`; yardstick 0; worst error 0 (margin inf, serialisation); GCI parse
  anchored to the T3c `GCI_fine` rows.
- **I15 (2) Ridge mutants and validation.** Add known answers and mutants for: λ = α·n vs α; SST
  about the config mean vs the global mean; ΣSSE/ΣSST vs mean of ratios; own-phase vs interpolated
  evaluation; the tie-break order. Validation: NaN target, phase outside [0,1), fewer than 2 rows,
  duplicate phase, fewer than 2 configs → `ValueError`. The equal-weight scenario uses a 3× denser
  on-grid resample, not duplicated rows.
- **I16 (2) Split guard.** "Each setting has exactly 3 distinct values" (with stroke 55 missing,
  45 would silently become the face). Pin the control draw call.
- **I17 (2) CLI tests.** For `run_surrogate_bench.py`: flags wired, no torch import, mutable digest
  rejected, `--allow-dirty`. Extend the `--phase-harmonics` driver test. `run_training` with
  H = 0 / True / 2.5 raises before any I/O.
- **I18 (2) Runner seam and CI time.** Patch at `_fit_one_seed`/`fit_seed` and assert the
  hyperparameter wiring; inject the git state. Do one multi-right-hand-side solve per
  (split, fold, d, α); the CI recompute must take under 30 s.
- **I19 (1) Default call.** Whether the default call passes `phase_harmonics=1` to the recorder is
  ambiguous. Decide: it is passed; the outputs are unchanged.
- **I20 (1, 4) Impact list.** Add: the `__init__.py` exports, the existing tests that change,
  `project.md` (package tree plus a bench subsection), the `build_model` docstring, `docs/CHANGELOG.md`.
- **I21 (4) Fine README.** Add a scoping sentence for the shipped model; rows for `surrogate_h3/`,
  the h3 figure and `bench/`; the regeneration recipes, cross-referenced; the h3 twice-run result
  recorded durably.
- **I22 (4) DRY.** The scope text is one code constant quoted by the README via test. The GCI values,
  exploration numbers, seeds and shipped-file list each get one home. The proposal's "rank 14–16" is
  wrong (it is 14–17) and should be cut. The exploration SHA (the branch is now at `b99c7b2`) is
  stated once. Reword "one grid layer past" as "to a held-out outer layer".
- **I23 (5) Commit and PR plan.** Split the tasks into atomic commits; reconcile the spec before the
  bench runs; the README lands with the artifacts.

### Suggestions (selected)

- Use the GCI constants from the computed values 0.03692 and 0.2758.
- Record the linear sum next to the quadrature combination.
- Note the ≈ 6,336-row results size.
- Record the wrap-jump floor (1–4 % of peak).
- Add a parameter-count known answer.
- `BREAKING: none` line.
- Trim the proposal's Why.

### Pre-existing finding (issue draft, not a fix)

Every f* = 0.85 config, in both corpora, ends on a last row whose coefficients jump 3–7 % of the
component peak. The likely cause is a truncated final step: stop_time = 2/0.85 is not a multiple of
dt. This is unverified. Draft: `issue-drafts/fstar085-terminal-row-jump.md` (to be written for the
user).

## Reconciliation of review round 1

Every BLOCKING and IMPORTANT finding in `review-round1.md`, with the reviewer's mechanism quoted
verbatim, how the revision addresses it, and where the mechanism now appears. Paths are relative to
this change directory. `S` = `specs/surrogate-comparison-bench/spec.md`; `F` =
`specs/force-surrogate/spec.md`.

Where the revision does something other than the reviewer's literal mechanism, the entry says so
under **Deviation**, with the reason.

### Blocking

**B1.**
- Finding: "Fix: 'both peaks are computed on the 256-point grid, model evaluated at grid phases and
  CFD interpolated from lab-frame CF then rotated at the grid phases', plus a scenario pinning
  ≈1.988."
- Resolution: done as stated. Re-measured independently: 2.0540 on the raw rows and 1.9883 on the
  grid.
- Where: S:206–212 ("raw CSV rows are never used for a peak"); scenario S:259 "Body-frame peaks use
  the phase grid" (1.988 to 1e-3, not 2.054); design.md D5.

**B2.**
- Finding: "Fix: add `control:e4_seed0` with E4's construction, or drop the wording."
- Resolution: added. The construction was confirmed against `experiments/common/splits.py` and
  `e4_ablations/ridge_cv.py` on the exploration branch (pool = the 21 non-holdout configurations).
  Re-measured: rank 16 of 17, with all 18 folds deficient.
- Where: S:16; scenario S:34 (literal list, rank 16 of 17); design.md D2.

**B3.**
- Finding: "Fix: exact equality on the discrete outputs (H, d, α, P, rank, edge flags); `rtol` ≈ 1e-10
  on the continuous ones; record the winner–runner-up CV gap and assert it exceeds the tolerance.
  Bitwise only within one process."
- Resolution: exact and `rtol = 1e-10` as stated.
- Where: S:334; the gap is recorded as `selection_margin` at S:80 and asserted to exceed 1e-6 at
  S:334; "in one process" at S:122; design.md D7.
- Deviation: under the pre-registered rule from I8, the boundary that can flip is the 1 % threshold,
  not the winner/runner-up pair. So the recorded gap is the closest any candidate came to the
  threshold. It is asserted to exceed 1e-6, which is 10⁴ times the continuous `rtol`.

**B4.**
- Finding: "Fix: α = 1e-12 with tolerance 1e-8, and synthetic phases on the k/256 grid. Add a separate
  realistic-sampling test at about 1e-5."
- Resolution: done as stated.
- Where: S:95–99; S:101–105; tasks.md 4.1.

**B5.**
- Finding: "Fix: a subprocess test asserting none of {torch, physicsnemo, scipy, sklearn} is in
  `sys.modules` after `import mosquito_cfd.surrogate_bench`, mutation-tested."
- Resolution: done as stated.
- Where: S:350; tasks.md 3.1 (with the top-level `import torch` mutant).

**B6.**
- Finding: "Fix: task 1.3b (CPU, with `build_model`/`train_model`/`predict` monkeypatched to recorders)
  checks that the default path calls `make_config_splits` once and passes byte-identical inputs to
  today's, with n_in = 5. An explicit split is used verbatim with n_in = 9, and an invalid split raises
  before any torch import. Task 1.6 implements the seams. 7.3 moves before 7.2."
- Resolution: done.
- Where: task 1.3b; the seams are implemented in 1.4, the renumbered equivalent of "1.6"; F:81–92
  (seam text) and F:121 (scenario).
- Implementation is now test-after nowhere: the GPU end-to-end test is 7.3, which comes before the
  implementation in 7.4.

**B7.**
- Finding: "Fix: add scenarios (CLI default 1 and every seed receives H; GPU `build_model(n_in=9)`; no
  checkpoint is written or loaded for ridge)."
- Resolution: done.
- Where: F:109 "The harmonic count reaches every seed"; F:100 (`n_in=9`); F:133 "The bench reference
  is never a checkpoint".

**B8.**
- Finding: "Fix: MODIFY both (historical wording; `surrogate_h3/` as a second location)."
- Resolution: both are MODIFIED, with their full text.
  - "Committed training artifacts" names `surrogate_h3/` (F:198–201).
  - "Fine-corpus surrogate … reproducibility gate" now reads "was trained by the trainer as it stood
    before `add-surrogate-comparison-bench`" (F:290), and applies the gate to `surrogate_h3/`.
  - "Committed evidence-figure artifacts with provenance" is also MODIFIED, because the h3 figure
    lives in `figures_h3/` (F:222). See I12.

**B9.**
- Finding: "Fix: a change-lifetime check that hard-codes {path: sha}, fails on added or deleted files,
  is run at the end of each task group, and has its result recorded in the PR body. It is not
  committed as a standing test, and the spec scenario is reworded to 'within this change'."
- Resolution: done. The {path: sha} record is the `git ls-tree -r e600581` output, saved as
  `shipped_artifacts.lstree` (tasks.md 0.1). Blob ids catch added, deleted and changed files and are
  immune to CRLF conversion in the Windows working tree.
- Where: the rule is in the tasks.md header; the check closes every task group; scenario F:349
  "Shipped artifacts are byte-unchanged within this change"; design.md:195.

**B10.**
- Finding: "Fix: outputs go to scratch outside the repo; and either split the PR (artifacts produced
  from merged main) or add a rule to re-run after every code-affecting fix."
- Resolution: the PR is split (the user chose two PRs).
- Where: design.md D0 (design.md:28–43); tasks.md 9.1–9.3.
- PR 2's runs happen before any commit on a branch cut from `main`, so the recorded commit is on
  `main` and survives the squash merge. That also satisfies the existing clean-commit test, which
  rejects `branch == "main"`.

**B11.**
- Finding: "Fix: merge that branch first as a stated prerequisite; 9.2 only after it."
- Resolution: pushed as PR #171 (docs-only).
- Where: stated as a prerequisite in proposal.md:6 and tasks.md:21. The F3a roadmap row is updated
  only in PR 2 (tasks.md 11.2).

**B12.**
- Finding: "Fix: row 16 at archive time."
- Resolution: done.
- Where: tasks.md:222 (11.2); proposal.md Impact.

### Important

**I1.**
- Finding: "Record the minimum fold rank and the number of deficient folds per (split, d)."
- Resolution: done. The design's rank paragraph is rewritten from fresh measurements: training
  matrices are full rank; the deficits are in the folds and in E4's subset.
- Where: S:82–83; scenario S:131; design.md D3 "Ranks".

**I2.**
- Finding: "Record baseline RMS, and compare splits by `rmse_pct_component_peak`."
- Resolution: done.
- Where: S:160; S:167 ("Skill SHALL NOT be compared across splits"); design.md:144.

**I3.**
- Finding: "CF_y is not near zero …, so that scenario must be synthetic. Require one normaliser for
  both sides of every yardstick."
- Resolution: done.
- Where: S:182 (synthetic, ratio 10); S:203–206 ("Both sides of every comparison SHALL use the same
  normaliser"); design.md:152.

**I4.**
- Finding: "Add: startup beat of a 1-beat run; T3c fine dt 2.5e-4 at cfl 0.3 vs the corpus's 5e-4 at
  cfl 0.6 (temporal error not covered); z boundary condition 2 vs 4; stroke 70° outside 35–55°."
- Resolution: all four were added. Each was checked against `inputs.3d.convergence_fine` and a corpus
  deck (`stop_time 1.0`, `ns.cfl 0.3`, `lo_bc/hi_bc 2 0 2` vs `2 0 4`, stroke 70).
- Where: S:243–250; design.md D5.

**I5.**
- Finding: "Label it an upper bound; also report it scaled by 1/(r^p − 1) (r = 4, p ≈ 1.38, about
  1/5.8)."
- Resolution: done. The lab components use the normal order; this is labelled as borrowed from T3c.
- Where: S:220–223; tasks.md 6.1.

**I6.**
- Finding: "Define it for the peaks as |max|C_N| − max|C_{N−1}|| / max|C_N|. State which beat is the
  target when there are ≥ 4 beats. Use `wingbeat` indices everywhere. Add boundary scenarios at 3 and
  4 beats. State which wingbeats `beat1_vs_beat2` reads, from the unfiltered frame."
- Resolution: done with 0-based `wingbeat` indices (`N − 1` vs `N − 2`).
- Where: S:224–231; scenario S:289 "Late-beat boundary".

**I7.**
- Finding: "Replace it with hand-written known answers: phase 0 → cf_normal 1, cf_chord 0; phase
  0.25 → cf_normal 1; tolerance 1e-12. This pins phase→time and deg→rad."
- Resolution: done.
- Where: scenario S:265; tasks.md 6.1.

**I8.**
- Finding: "Pre-register a rule: smallest H, then d, within 1 % of the best score."
- Resolution: done, with "1 %" made explicit as relative (`threshold = 1.01 · best`) and α as the
  third key (largest).
- Where: S:76–79; scenario S:125.

**I9.**
- Finding: "State this; the face and control results are not affected."
- Resolution: done.
- Where: design.md table (line 14) and D6; F:346 (README statement).

**I10.**
- Finding: "`results.parquet` must carry `sse`, `sse_baseline`, `n_rows`, `grid_sse` and `n_grid`, so
  pooled values recompute. Timing is excluded from the equality tests."
- Resolution: done.
- Where: S:152–163; scenario "Pooled values recompute from the stored sums".

**I11.**
- Finding: "Make it a permanent CPU test of committed `results.parquet` against committed
  `surrogate/metrics.json`. Pre-register the criterion (exact) and preconditions (library versions).
  Add: the interpolation baseline with an explicit list of the 21 is byte-identical to the no-list
  call."
- Resolution: done.
- Where: S:336 (exact, preconditions asserted first); S:176 (explicit-list baseline); tasks.md 2.1 and
  10.1.
- Deviation: the test reads `summary.json`'s per-seed skill rather than re-pooling `results.parquet`.
  That skill is computed by the same `compute_baseline_skill` call `run_training` makes over all test
  rows, so "exact" is a valid criterion. Re-pooling per-configuration sums would differ in the last
  bit because the summation order differs. The preconditions are the fields the shipped
  `run_metadata.json` actually records (`hardware`, `library_versions.torch/physicsnemo`); it has no
  numpy version.

**I12.**
- Finding: "These are required, not 'if needed': the script writes fixed names. Add a test-first task:
  default names unchanged; `h3` names correct; shipped files untouched."
- Resolution and deviation: the h3 figure is written by the unchanged generator into its own
  directory, `figures_h3/`, with the default names. `scripts/make_evidence_figure.py` already takes
  `--out-dir` (required), and the generator has no dependency on the feature count (checked). No
  name option is added, so there is nothing to test for names. "Shipped files untouched" is covered
  by B9's check.
- Where: F:336; F:222; design.md:190.

**I13.**
- Finding: "Use a separate `tests/test_committed_surrogate_h3_provenance.py`, not a
  reparametrisation; read features from JSON on CPU (the `.pt` only on GPU); add the new
  `run_metadata` files to the clean-commit test; bench digest and dataset sha match the corpus."
- Resolution: done.
- Where: tasks.md:201–207; scenario F:355.

**I14.**
- Finding: "error == yardstick → `inside`; one config over → `outside`; NaN error never `inside`;
  yardstick 0; worst error 0 (margin inf, serialisation); GCI parse anchored to the T3c `GCI_fine`
  rows."
- Resolution: done.
- Where: scenario S:277 "Gate boundaries"; tasks.md:138 (anchored parse).

**I15.**
- Finding: "Add known answers and mutants for: λ = α·n vs α; SST about the config mean vs the global
  mean; ΣSSE/ΣSST vs mean of ratios; own-phase vs interpolated evaluation; the tie-break order.
  Validation: NaN target, phase outside [0,1), fewer than 2 rows, duplicate phase, fewer than 2
  configs → `ValueError`. The equal-weight scenario uses a 3× denser on-grid resample, not
  duplicated rows."
- Resolution: done.
- Where: tasks.md 4.2 (mutant list); S:87–89 and scenario S:137; S:115 (`k/768`).

**I16.**
- Finding: "'Each setting has exactly 3 distinct values' … Pin the control draw call."
- Resolution: done.
- Where: S:19–21; S:50; S:14–15 (the literal call).

**I17.**
- Finding: "For `run_surrogate_bench.py`: flags wired, no torch import, mutable digest rejected,
  `--allow-dirty`. Extend the `--phase-harmonics` driver test. `run_training` with H = 0 / True / 2.5
  raises before any I/O."
- Resolution: done.
- Where: scenario S:324; tasks.md 7.2 and 1.3; scenario F:115.

**I18.**
- Finding: "Patch at `_fit_one_seed`/`fit_seed` and assert the hyperparameter wiring; inject the git
  state. Do one multi-right-hand-side solve per (split, fold, d, α); the CI recompute must take under
  30 s."
- Resolution: done.
- Where: tasks.md:159; S:69–70; S:348.

**I19.**
- Finding: "Decide: it is passed; the outputs are unchanged."
- Resolution: done.
- Where: F:79 ("pass it explicitly (also at the default)"); scenario F:109.

**I20.**
- Finding: "Add: the `__init__.py` exports, the existing tests that change, `project.md` (package tree
  plus a bench subsection), the `build_model` docstring, `docs/CHANGELOG.md`."
- Resolution: done.
- Where: proposal.md:60–78; tasks.md 1.4 and 8.1.

**I21.**
- Finding: "Add a scoping sentence for the shipped model; rows for `surrogate_h3/`, the h3 figure and
  `bench/`; the regeneration recipes, cross-referenced; the h3 twice-run result recorded durably."
- Resolution: done.
- Where: tasks.md:214–221.

**I22.**
- Finding: "The scope text is one code constant quoted by the README via test. The GCI values,
  exploration numbers, seeds and shipped-file list each get one home. The proposal's 'rank 14–16' is
  wrong (it is 14–17) and should be cut. The exploration SHA (the branch is now at `b99c7b2`) is
  stated once. Reword 'one grid layer past' as 'to a held-out outer layer'."
- Resolution: done.
  - Scope: `BENCH_SCOPE` (S:311; tasks.md:218).
  - The homes:
    - exploration numbers and SHA: the design.md table, line 9;
    - GCI values: S:217;
    - shipped-file list: the F:349 scenario and `shipped_artifacts.lstree`.
  - The rank sentence is cut from the proposal.
  - The new wording is at S:312.

**I23.**
- Finding: "Split the tasks into atomic commits; reconcile the spec before the bench runs; the README
  lands with the artifacts."
- Resolution: done.
- Where:
  - one commit per group: tasks.md:18;
  - reconcile before the runs: 8.2, in PR 1;
  - README with the artifacts: 11.1, in PR 2.

### Suggestions taken

- GCI constants from the computed values 0.03692 and 0.2758 (S:217). These are the `gci_fine`
  values asserted in `tests/test_results_reproducibility.py`.
- Linear sum recorded beside the quadrature combination (S:238).
- Results size: 6,732 rows with 14 splits (design.md:156).
- Wrap-jump floor: not taken. The f* = 0.85 last-row jump is now handled by the grid peaks (B1) and
  goes to an issue draft.
- Parameter-count known answer (tasks.md:103).
- `BREAKING: none` (proposal.md:50).
- The proposal's Why is trimmed to two sentences.

### Pre-existing finding

The f* = 0.85 terminal-row jump is drafted for the user as
`issue-drafts/fstar085-terminal-row-jump.md`, not fixed here. The re-measurement narrows the
reviewer's description:

- the jump is 1.9–3.2 % (fine) and 3.9–5.4 % (coarse) of the configuration's component peak, against
  a typical step change under 1 %;
- the last recorded row follows an ordinary 5e-4 step;
- f* = 1.15 also stops short of `stop_time` and shows no jump.

So the "truncated final step" cause is not supported as stated.

---

## OpenSpec Review (round 2): add-surrogate-comparison-bench

### Verdict: BLOCKED (one blocking finding)

Reviewers: 1 sonnet, 2 opus, 3 skipped (no CI, Docker, dependency or packaging change; the bench is
new Python under `src/`, `scripts/` and `tests/`), 4 sonnet, 5 sonnet, 6 opus.

### Summary

All round-1 findings are fixed. Two reviewers independently re-derived every count and rank, the
B1 peaks, the GCI values and orders, the six provisional reasons, and the issue-draft table; all are
VERIFIED. `openspec validate --strict` passes. One test-plan gap blocks: nothing in PR 1 proves that
the bench's `mlp_h1` interpolation fit receives the same bytes as `run_training`. The math reviewer
found four substantive design problems, each reproduced with an independent implementation:

- the 1 % selection rule is effectively argmin;
- the beat is not periodic at its wrap;
- the E4 control mixes two causes;
- the rotation known answers miss stroke.

### Blocking

| ID | Source | Finding (verbatim mechanism) |
|---|---|---|
| B1 | 2 | "Nothing in PR 1 shows the bench's `mlp_h1` / `interpolation` call trains on the same bytes as `run_training`." Add to 1.3b: "`fit_seed(df, make_config_splits(df, seed=s, n_val_configs=3), seed=s, phase_harmonics=1)` passes `build_model`/`train_model`/`predict` arrays byte-identical to `_fit_one_seed(df, seed=s)`, for s = 1234…1238." Add to 7.1: "the runner's interpolation `mlp_h1` call receives the full converged-beat frame (same row order, `np.array_equal` on `config_name` and `phase`) and the bench's carve lists." Add a GPU-tier test before 7.4: "`fit_seed` on the interpolation split and `_fit_one_seed` default, with few epochs on the real dataset and run after an unrelated fit in the same process, give bitwise-equal `y_pred`." |

### Important

**Math and design (6)**

- **M1. Rotation known answers miss the stroke angle.** At phase 0, φ = 0; at 0.25, α = 0 and
  n = e_z. Stroke deg/rad, stroke sign and the `/f*` mutants all survive at f* = 1. Add phase 0.125
  with f* = 0.85, stroke 55°, pitch 45° and lab force x̂: cf_normal = cos φ sin α and cf_chord =
  cos φ cos α, with φ = 55°·sin(π/4) and α = 45°·cos(π/4). This kills every mutant tried.
- **M2. `threshold = 1.01·best` is effectively argmin.**
  - CV NMSE is about 1e-5 to 5e-4, so 1 % is about 3e-6 absolute.
  - The rule picks H 24 or 16 on interpolation and the controls, and **H 32, the grid edge, on all
    six faces**.
  - H = 8 is within about 10 % of the best everywhere.
  - Design's "should be rare" is CONTRADICTED.
  - Pre-register a scale that means something: one standard error over the LOO folds, an absolute
    NMSE band, or 1 % on RMS.
- **M3. The converged beat is not periodic.**
  - The first row vs the last regular row of wingbeat 1 differs by 2–8 % of the lab peak, and by
    1.0–4.6 % of the body-frame normal peak, at every f*.
  - The normal peak sits at phase 0.945–0.984 or exactly 0, which is the splice.
  - A periodic model has an error floor there of the same order as the 3.7 % yardstick.
  - Record `wrap_jump` per configuration and add a provisional reason. Round-1's "wrap-jump floor"
    suggestion was declined on a wrong premise.
- **M4. `control:e4_seed0` confounds "correct ridge" with "re-selected hyperparameters".**
  - The correct ridge at E4's fixed (16, 3, 1e-6) gives holdout skill **0.749**, so it still
    collapses.
  - The CV-selected (24, 2, 1e-4) gives 0.9968.
  - Also record the ridge at the fixed exploration point for this split, or reword the claim.
- **M5. Units.** `rmse_pct_*` and the yardsticks are fractions, but are named and described as %. A
  ×100 implementation passes every listed test. State the unit as a fraction, write the scenarios as
  0.01…0.06 vs 0.05, and add the known answer 0.03 vs 0.03692 → `inside`, margin 1.2307.

**Tests (2)**

- **T1. Ordering and missing tests.**
  - 1.5 is test-after; move it before 1.4.
  - Add a CPU `predict_frame` test.
  - `fit_seed` must reject empty validation, train or test lists. An empty validation list silently
    skips the best-validation restore.
  - With an explicit non-default split, `make_config_splits` must be called 0 times.
- **T2. `rtol = 1e-10` vs BLAS.**
  - A 1-ulp perturbation moved E4 at (32, 3, 1e-8) by 6.4e-10.
  - Use 1e-10 for selected candidates and full-rank solves, and 1e-8 otherwise. Or run the CPU
    recompute on Linux (gh-04) before committing, and pre-register the observed bound.
- **T3. Margin failure path.**
  - Pre-register what happens if `selection_margin ≤ 1e-6`: record `selection_fragile` and skip
    the discrete comparison with a reason.
  - Add a known answer for the margin value, with a mutant that takes the margin from `best`.
- **T4. Mutation lists.**
  - 2.2: the guards; holdout ANDed; unsorted list.
  - 4.2: kinematics standardised over rows.
  - 5.2: baseline from `pool`; the seed count off by one; a NaN-unaware range.
  - 7.4: the driver guards, and the order of refuse-before-write.
  - 1.4: validation after the read; `bool` accepted; column order.
  - 10.1: negative tests for each committed-artifact guard.
- **T5. Gate yardstick values.**
  - Add synthetic known answers for `coarse_vs_fine` (normalised by the fine `peak_t`) and for a
    nonzero `beat1_vs_beat2`.
  - Pin the GCI against the computed `gci_fine` (0.0365 passes the rounded parse).
- **T6. Driver.**
  - Enumerate the flags; define "ridge-only".
  - Add an epochs override for 7.3, and a CPU ridge-only smoke run on the real dataset.
- **T7.** Write the README-equals-JSON and `BENCH_SCOPE` tests first, in 10.1.

**Spec (1)**

- **S1.** Tasks lack a leading `- `, so `openspec list` reports "No tasks". Use `- [ ] N.M`.
- **S2.** The scenario "byte-unchanged within this change" is change-scoped but sits in a permanent
  spec. Keep it in tasks and design only.
- **S3.** `no_yardstick` is defined per component in one place and per yardstick in another.
  - Use `not_applicable` per (component, yardstick).
  - Use `no_yardstick` for a component with zero applicable yardsticks, with a synthetic scenario.
- **S4.** Add a scenario that `BENCH_SCOPE` names all three limits, and require the README to quote
  it.
- **S5.** The "ridge never a checkpoint" scenario needs its static check: `ridge.py` references no
  `torch.save`, `torch.load` or loader.

**Git (5)**

- **G1. Shipped-artifact check.** `git ls-tree e600581` vs HEAD breaks on PR 2, which is cut from a
  later main where #114 may legitimately change `figures/`. Use
  `git diff --exit-code <branch base> HEAD -- <paths>` plus `git status --porcelain`, with base
  `e600581` for PR 1 and M for PR 2. Drop `shipped_artifacts.lstree`.
- **G2. PR 2 procedure.**
  - `git fetch` first, compare against `origin/main`, and record M.
  - No fetch, pull or rebase between runs A and B; assert that A's and B's `git.commit` are equal.
  - Before merge, `git diff M origin/main -- <code paths>` must be empty, or the re-run decision is
    recorded.
  - A mid-PR-2 code fix means: discard the artifacts, recreate the branch from the new main, and
    re-run.
- **G3. Archive timing.** State in 8.4 that `/cleanup-merged` must NOT archive after PR 1.
- **G4. Commit plan.**
  - Split group 1 (features / plumbing / seams) and group 7 (runner / driver / figure).
  - Make the shared-carve refactor in `train.py` its own `refactor(force-surrogate)` commit.
  - The figure needs tests first.
- **G5. CI.**
  - GPU tests import torch inside test bodies, and the local `-m gpu` output goes in the PR body.
  - Ruff also covers `examples/prelim_sweep*/`.
  - Give the 30 s wall-clock assert headroom.

**Docs (4)**

- **D1. PR #171 errors.**
  - Its roadmap says "extrapolation one grid layer past". Reword to "to a held-out outer layer".
  - It attributes the 0.41 collapse to **E3**. E3 is the MLP data-efficiency curve; the ridge is E4.
- **D2.** 11.2 must update the F3a row ("provisional per-component, per-yardstick gate; no overall
  verdict"), Revision item 3 and open question 4, as pointers to the README. Give row 16's wording.
- **D3.**
  - Say which PR's CHANGELOG and project.md entries cover what.
  - PR 1 must not describe `bench/` or `surrogate_h3/` as committed.
  - Document that the `mlp_h1` regression is valid only on talmo-lab-02 with the recorded driver and
    the recorded `torch`/`physicsnemo` versions; gh-04 fails the precondition by design.
  - State the dependency groups.
- **D4. DRY.**
  - Seeds get one home, `BENCH_SEEDS`.
  - GCI constants live in the spec only.
  - The f* = 0.85 story lives in the issue draft only.
  - Cut the design's repeats of the spec numbers.
  - The issue draft must not cite a private memory note.

### Suggestions (selected)

- `n_params`: say whether it is per target or ×6.
- Say whether LOO folds re-standardise and recompute L_v.
- `coarse_vs_fine_scaled` label: add "Fs = 1.25 not applied", "different container digests" and the
  computed orders 1.3773/1.3655.
- Name the denominator of `beat1_vs_beat2`'s peak change.
- Margin with yardstick 0 and error 0 → NaN, not `"inf"`.
- Issue draft: only f* = 0.85 has a row at the last whole-step time, so the shortened-step hypothesis
  is consistent after all. If the row is later dropped, the 1.988 pin becomes 1.9859.
- Pin `CUBLAS_WORKSPACE_CONFIG` as a precondition, and run `mlp_h1`/`interpolation` first in the
  process.
- Exception types per input; accept `np.int64`.
- A small twice-run comparison script.

### Verified (not issues)

These are independently recomputed by reviewers 1, 2 and 6:

- ranks;
- the E4 list;
- the draw calls (`choice` on strings = on indices);
- 17/14 columns;
- the Fourier exactness;
- the equal-weight bitwise property;
- B1 2.054/1.988;
- phase→time;
- `F_body = Rᵀ F`;
- GCI 0.03692/0.2758;
- p 1.3773/1.3655;
- 1/(4^p − 1);
- the deck reasons;
- `CF_y` ≥ 0.40;
- baseline RMS 0.111 vs 0.200;
- 6,732 rows;
- `selection_margin` 2.6e-4–9.6e-3;
- CV runtime about 6 s;
- no leakage (`peak_t` is a shared reporting constant);
- claim scope within limits.

## Reconciliation of review round 2

Every BLOCKING and IMPORTANT finding in `review-round2.md`: how it is addressed and where. Citations
name the file and the scenario or task, not line numbers. `S` = `specs/surrogate-comparison-bench/spec.md`;
`F` = `specs/force-surrogate/spec.md`. The reviewer's mechanism is quoted in `review-round2.md`. A
**Deviation** line explains any place the revision differs from it.

User decisions taken on 2026-11-18:

- **M2:** the one-standard-error rule.
- **D1:** fix PR #171 on its branch and push. Done as `2ec3d2c`.

### Blocking

- **B1. The bench's interpolation fit receives the same bytes as `run_training`.** All three
  mechanisms are adopted:
  - CPU: F scenario "The per-seed seams are torch-free up to the model", second clause, with tasks
    1c.1;
  - runner: S requirement "Bench model entries and metrics" ("full converged-beat frame in dataset
    order", "fit `mlp_h1` on `interpolation` first"), with task 7a.1;
  - GPU: F scenario "The bench path trains like run_training", with task 1c.3.

### Important — math and design

- **M1. Rotation known answers.**
  - Phase 0.125 is added, with `f* = 0.85`, stroke 55°, pitch 45° and lab force x̂. Its values were
    checked against the code before being written in: 0.41038 and 0.66137, equal to the hand
    formulas.
  - Where: S scenario "Body-frame rotation known answers"; task 6.1; design D5 "Rotation".
- **M2. Selection rule.** Replaced by the one-standard-error rule over the leave-one-out folds,
  defined so the score equals the earlier mean of `ΣSSE/ΣSST`.
  - The `threshold`, `selection_margin` and `selection_fragile` definitions follow from it.
  - Design D3 no longer claims edge choices are rare; it says they are recorded.
  - Where: the S requirement "Ridge reference model"; S scenario "Selection follows the
    one-standard-error rule"; design D3 "Selection".
- **M3. Wrap jump.**
  - It is recorded per configuration against the last row and the last-but-one row, for lab
    components and peaks.
  - A seventh provisional reason is added.
  - A known answer was computed for `s55_f085_p45`: 0.0242 and 0.0352.
  - Where: the S requirement "Provisional hover gate"; S scenario "The wrap jump is recorded"; design
    D5.
- **M4. E4 confound.** A `ridge_fixed` entry at the pre-registered point `(16, 3, 1e-6)` runs on
  every split, labelled optimistic where the labelled holdouts are the test set.
  - Where: the S requirement "Bench model entries and metrics"; S scenario "The fixed ridge point
    separates the two causes"; design D3 "`ridge_fixed`".
  - Deviation: it runs on all 14 splits rather than only `control:e4_seed0`. The cost is negligible,
    and it lets every split separate the two causes.
- **M5. Units.** Every metric is stated as a fraction and renamed `rmse_frac_*`. The scenarios use
  0.01–0.06 against 0.05, and the 0.03 vs 0.03692 → margin 1.2307 known answer is added.
  - Where: S scenarios "Worst seed decides and margin uses the worst seed" and "Errors and yardsticks
    are fractions"; mutation "a ×100 scaling" in task 6.2.

### Important — tests

- **T1.**
  - 1c.3 (GPU) and 1c.1–1c.2 (CPU) precede 1c.4.
  - `predict_frame` gets a CPU scenario.
  - `fit_seed` rejects empty lists.
  - An explicit split makes zero `make_config_splits` calls.
  - Where: F, the regressor requirement text and its seam scenarios.
- **T2.** Continuous ridge outputs use `rtol = 1e-8`, and a Linux recompute runs on gh-04 before PR 2
  opens.
  - Where: S scenario "Committed bench results are consistent with their inputs"; design D7; task
    10.2.
  - Both reviewer options are taken.
- **T3.** `selection_fragile` is recorded. A fragile split is refit at its committed choice instead
  of being re-selected. The margin value has a known answer, with the threshold-vs-best mutant.
  - Where: S, the ridge requirement and the consistency scenario; tasks 4.1–4.2.
- **T4.** Every listed mutant is added, in tasks 1a.2, 1b.2, 1c.4, 2.2, 4.2, 5.2, 6.2 and 7b.2, plus
  negative tests in 10.1.
- **T5.** Yardstick known answers are added, and the GCI constants are compared with the computed
  `gci_fine` to 1e-4.
  - Where: S scenarios "Yardstick values are known answers" and "GCI constants trace to their
    sources".
- **T6.** The driver's flags are listed, including `--entries` (which gives a ridge-only CPU run) and
  `--epochs`. The CPU smoke run is task 7b.1.
  - Where: the S requirement "Bench artifacts, provenance and claim scope".
- **T7.** The README tests are written first, in 10.1, before 11.1.

### Important — spec

- **S1.** The tasks use `- [ ] N.M`; `openspec list` now shows 0/51 tasks.
- **S2.** The change-scoped "byte-unchanged" scenario is removed from F; the check lives in the
  tasks header and design D6.
- **S3.** A yardstick that does not apply is `not_applicable`, and `no_yardstick` means a component
  with no applicable yardstick. A synthetic scenario covers it.
  - Where: S scenario "A component with no yardstick never passes".
- **S4.** S scenario "The scope names all three limits and the README quotes it" is added.
- **S5.** The static check is S scenario "The reference is never a checkpoint" and task 4.1. It moved
  from F to S because it concerns the bench's code.

### Important — git

- **G1.** The check now runs `git diff --exit-code <base> -- <paths>` with base `e600581` or `M`;
  `shipped_artifacts.lstree` is dropped.
  - Where: design D6; tasks header.
  - The diff runs against the working tree, so it holds before the commit.
- **G2.**
  - fetch first, compare against `origin/main`, and record `M`;
  - no fetch, pull or rebase between runs A and B, which must record the same `M`;
  - a pre-merge `git diff M origin/main` check;
  - a procedure for a code fix found during PR 2.
  - Where: design D0; tasks 9.1, 9.3 and 11.3.
- **G3.** Task 8.4 says `/cleanup-merged` must not archive after PR 1; task 11.4 archives after PR 2.
- **G4.**
  - Group 1 becomes 1a, 1b and 1c.
  - Group 7 becomes 7a, 7b and 7c, with the figure tested first.
  - The carve refactor is its own commit, 3a.
- **G5.**
  - GPU tests import torch inside test bodies, and their output goes in the PR body.
  - Ruff covers `examples/prelim_sweep*/`.
  - The 30 s assert becomes "report the duration, fail above 120 s".
  - Where: tasks header; S requirement "Two-tier bench tests".

### Important — docs

- **D1.** Fixed on PR #171 (`2ec3d2c`), with the user's go-ahead: E3 → E4, and the claim scope
  reworded to "to a held-out outer layer".
- **D2.** Task 11.2 now has the F3a row text, the Revision item 3 and open question 4 pointers, and
  the row 16 wording.
- **D3.**
  - Each PR's CHANGELOG entry is scoped (tasks 8.1 and 11.2).
  - PR 1's project.md must not describe artifacts as committed (8.1).
  - The `mlp_h1` regression's host and library preconditions are documented (8.1, 11.1, design D7).
  - The dependency groups are stated (8.1).
- **D4.**
  - `BENCH_SEEDS` is the one home for the seeds.
  - The GCI constants live in `gate.py` and the spec; design D5 no longer repeats them.
  - The f* = 0.85 account lives in the issue draft only; design D5 points there.
  - Design D2 and D3 point to the spec for ranks and lists.
  - The issue draft no longer cites a private note.

### Suggestions taken

- `n_params` covers all six targets for both model kinds.
- Folds re-standardise and recompute `L_v`.
- The `coarse_vs_fine_scaled` label carries its limits and uses the computed orders 1.3773 and 1.3655.
- `beat1_vs_beat2`'s peak denominator is beat 1.
- The 0/0 margin serialises as `null`.
- `CUBLAS_WORKSPACE_CONFIG` is recorded, and `mlp_h1`/`interpolation` runs first.
- The exception types per input are pinned, and `np.int64` is accepted.
- The twice-run comparison uses a small script.
- The issue draft is corrected: only f* = 0.85 has a row at the last whole-step time, and the 1.9859
  caveat is noted.

---

## OpenSpec Review (round 3): add-surrogate-comparison-bench

### Verdict: BLOCKED (two blocking findings, both from the math reviewer)

Reviewers: 1 sonnet, 2 opus, 3 skipped (no CI, Docker, dependency or packaging change), 4 sonnet,
5 sonnet, 6 opus.

All round-2 fixes held. Reviewers 2 and 6 independently re-implemented the ridge CV on the training
configurations only, and found:

- **One-SE rule:** it chooses `H = 8, d = 2` on interpolation, E4 and the controls, and `H` 16–24
  with `d = 3` on the faces. `θ*` is at `H = 32` everywhere. The smallest `selection_margin` is
  8.7e-3.
- **E4 subset:** `ridge_fixed` gives about 0.749 holdout skill there and re-selection about 0.997.
  Interpolation at the fixed point gives 0.99914.

Verified: the score identity, the wrap jumps 0.0242 and 0.0352, the 0.125 known answers, the margin
1.2307, and the factors 0.173954 and 0.177331.

### Blocking

| ID | Source | Finding |
|---|---|---|
| B1 | 6 | The phase-0.125 known answer does not kill a stroke-sign mutant: with lab force x̂, `cf_normal` and `cf_chord` are even in φ. Fix: also apply ŷ at 0.125 (`cf_normal = sin φ sin α = 0.331028`, `cf_chord = sin φ cos α = 0.533481`) and assert `cf_span = −sin φ = −0.627839` for x̂. |
| B2 | 6 | The recorded "last retained / first dropped" singular-value ratio is round-off when the matrix is rank deficient (1.08e15–1.55e15 under 1-ulp perturbation), and undefined at full rank. It would fail the `rtol = 1e-8` cross-platform recompute. Fix: record σ_r/σ₁, σ_{r+1}/σ₁ (`null` at full rank) and the rank tolerance; compare them by decade; add a scenario. |

### Important

**Testing (2)**

- **T1.** No test for `ridge_fixed`.
- **T2.** Three mutants survive:
  - SST about the global mean;
  - a mean of per-configuration ratios;
  - the normal equations (they need an ill-conditioned case).

  Add a fold-error known answer and an ill-conditioned solve.
- **T3.** Commit 3b's rank assertion depends on group 4.
- **T4.** The README tests are red at commit 10.3.
- **T5.** 1b's `metrics.json` check cannot run torch-free as written: `run_training` calls
  `torch.save` first.
- **T6.** Degenerate folds (fewer than 3 configurations, a setting with `L_v = 1`), NaN fold errors
  and ties for `θ*` are unspecified.
- **T7.** Fragile handling is not testable:
  - the committed flag needs to be checked against the recomputed one;
  - a named warning is needed;
  - a synthetic fragile case is needed.
- **T8.** The 7b smoke run needs its flags.
- **T9.** 1c.1 must compare every keyword argument, not just the arrays.

**Math and physics (6)**

- **M1. Wrap jump.**
  - Record the gap in row spacings (2.13 at f* = 1.15) and a slope-corrected jump.
  - State which normaliser the design's range uses.
  - "At the splice" should read "within 0.06 of phase (at it in 4 of 27)".
  - Reword the provisional reason.
- **M2.** The `coarse_vs_fine` known answer is ill-defined. Scale `CF_x`, `CF_y` and `CF_z` together;
  each peak's value is then exactly 0.1.
- **M3.**
  - The margin's minimum with `null` or NaN terms is unspecified.
  - "`late_beat` alone" is ambiguous.
- **M4.** With 4 or more beats, the training frame is undefined; the ridge would see duplicate phases.
- **M5.** Wording errors:
  - "chosen on the labelled holdouts" is inaccurate: the point came from CV on the pool, on a grid
    widened after holdout scores were seen;
  - "face results not affected" is false: 5 of 6 faces contain 1–3 holdouts.

**Spec (1)**

- **S1.** The design said `git diff <base> HEAD`, contradicting the tasks.
- **S2.** No scenario pins the tie-break on `d` or `α`; `selection_margin` with a zero threshold is
  unspecified.

**Git (1)**

- **G1.** Same contradiction as S1.
- **G2.** The PR 1 base should be `merge-base origin/main HEAD`.
- **G3.** The no-archive rule should also go in the PR 1 body and the session memory.
- **G4.** The gh-04 step lacks a mechanism.
- **G5.** The CPU smoke run must be ridge-only.
- **G6.** Consolidate the per-round review files into one `review-reconciliation.md`.

**Docs (4)**

- **D1.** The roadmap promises "memory", which the bench does not record.
- **D2.** The roadmap's E4 sentence contradicts the design.
- **D3.** The claim scope has four homes.
- **D4.** The 7,344 formula as written is not a product.
- **D5.** The issue draft is not public-ready:
  - no reproduction;
  - the 0.3 % basis is undefined;
  - no task records the issue number.

**Platform**

The `train` group is `sys_platform == 'linux'`. The A5000 host is Windows, where the shipped
surrogate's training ran under WSL2 (fine README). The GPU tier and the bench therefore run under WSL2.

### Suggestions (selected)

- Explain why `ridge` comes out below `ridge_fixed`: the `H`-first tie-break takes `d = 2`.
- Record `θ*`'s `at_grid_edge`, the runner-up gap and the largest fold share.
- Refuse a non-empty `--out-dir`, unknown entries and `--epochs < 1`.
- Reject duplicate `reference_configs`.
- Write the wrap jump with `|·|`.
- Test the `BENCH_SCOPE` substrings in PR 1.
- Pin the chord order.
- Add a lab wrap-jump known answer.
- Define the `[0.05, 1)` grid points.
- Use neutral wording instead of "Round 2 found".
- Split groups 4 and 6.
- Include `pyproject.toml` and `uv.lock` in the pre-merge diff.
- Add a `bench mlp_h3` vs `surrogate_h3` cross-check.

## Reconciliation of review round 3

`S` = `specs/surrogate-comparison-bench/spec.md`; `F` = `specs/force-surrogate/spec.md`. Findings
are quoted in `review-round3.md`. Where an entry departs from the reviewer's fix, it says so.

### Blocking

- **B1. Stroke sign is now pinned.** The ŷ case at phase 0.125 (0.331028, 0.533481) and
  `cf_span = −0.627839` for x̂ were checked against the code before they were written in.
  - Where: S scenario "Body-frame rotation known answers"; task 6a.1; mutant "stroke sign" in 6a.2;
    design D5.
- **B2. Singular values are recorded as fractions of σ₁.** The record holds σ_r, σ_{r+1} (`null` at
  full rank) and the rank tolerance. They are compared by decade, never by `rtol`.
  - Where: S requirement "Ridge reference model"; S scenarios "Ranks and fold ranks are recorded"
    (σ₁₇/σ₁ < 1e-13; `null` for interpolation) and "Committed bench results are consistent with
    their inputs" (`rtol` only on scores, sums and metrics; singular values within one decade).

### Important

**Testing**

- **T1.** `ridge_fixed` has a test of its point and its `null` selection fields (task 4a.1), a
  routed-through-selection mutant (4a.2), a both-rows-on-every-split check (7a.1) and an extended S
  scenario.
- **T2.** S scenario "Fold errors are computed as specified" and task 4b.1 are added, with the
  global-mean, ratio-mean, `ddof` and `se`-of-the-chosen-candidate mutants in 4b.2. S scenario "The
  solve survives ill-conditioning" and task 4a.1 are added.
- **T3.** The rank assertion moved from 3b.2 to 4b.1.
- **T4.** The README tests moved to 11.1, before 11.2.
- **T5.** Task 1b.1 captures `build_metrics`' return before `torch.save`, and updates the existing
  `fake_fit` recorders.
- **T6.**
  - Ties for `θ*` break by the selection order.
  - A setting with `L_v = 1` in a fold contributes no column.
  - The ridge requires at least 3 training configurations.
  - A non-finite fold error raises.
  - Where: S ridge requirement; S scenario "Degenerate folds are handled"; task 4a.1.
- **T7.** The committed `selection_fragile` must equal the recomputed one. A fragile split emits
  `SelectionNotRecheckedWarning`. There is a synthetic fragile case (S scenario "Fold errors…"; task
  4b.1) and a negative test in 10.1.
- **T8.** The smoke run's flags are spelled out in task 7b.1.
- **T9.** Task 1c.1 compares the full recorded call.
- Also from the testing review:
  - the GPU sequence in 1c.3 mirrors the bench's;
  - 10.2 halts above `1e-8`;
  - duration goes through `record_property`;
  - the pasted GPU output must show the tests passed;
  - exports get a test;
  - 3a pins a face split's carve;
  - the predictions-are-holdouts check covers h3.

**Math and physics**

- **M1.**
  - The wrap jump records raw, last-but-one and slope-corrected values, plus the gap in median
    spacings, with stated normalisers and `|·|`.
  - The provisional reason now reads "4.6 % … within 0.06 of phase".
  - Design D5 gives both normalisers' ranges and "at it in 4 of 27".
  - Where: the S gate requirement and scenario "The wrap jump is recorded", which adds a lab known
    answer.
- **M2.** The yardstick known answer is rewritten as the reviewer proposed: the three force
  components scaled together, so each peak's value is exactly 0.1, and the chord order is pinned.
  - Where: S scenario "Yardstick values are known answers".
- **M3.**
  - In the margin's minimum, 0/0 configurations are left out, and NaN makes it `null` and the
    verdict `outside`.
  - `late_beat` is added beside the other yardsticks.
  - Where: S gate requirement; scenarios "Gate boundaries" and "Late-beat boundary".
- **M4.** Every entry trains and is scored on the target beat `wingbeat == N − 1`. That equals
  `filter_converged_beat` on the 2-beat corpus, and the shipped trainer is unchanged.
  - Where: S ridge requirement; design D4 "Target beat"; scenario "Late-beat boundary".
  - This is a design decision taken here, not by the reviewer, so it is flagged for the user.
- **M5.** "Holdout-informed" replaces "chosen on the labelled holdouts". The face overlap per split
  is recorded, and the faces are also reported without the holdouts.
  - Where: S scenario "Holdout-informed entries are flagged"; design D3, D6 and the table.

**Spec**

- **S1.** The design's check is now the working-tree diff.
- **S2.** The tie-break on `d` and `α` and `θ*`'s edge flag are in S scenario "Selection follows the
  one-standard-error rule".
- Taken as well:
  - the `threshold > 0` case: scores are non-negative, and `θ*` = 0 only for a perfect fit, which the
    fragile flag covers;
  - out-dir, entries and epochs refusals;
  - duplicate `reference_configs`;
  - `BENCH_SCOPE` substrings tested in PR 1 (task 3b.1);
  - the Impact list names the carve helper.

**Git**

- **G1.** Same fix as S1.
- **G2.** The base is `merge-base origin/main HEAD` (tasks header, design D6).
- **G3.** The no-archive rule is in the PR 1 body and the session memory (task 8.4, design D0).
- **G4.** Replaced: the Linux recompute runs under WSL2 on the authoring host, where the GPU work
  already runs. Nothing moves between machines, and scratch outputs are located by
  `SURROGATE_BENCH_DIR` (task 10.2).
- **G5.** The smoke run is ridge-only (task 7b.1).
- **G6.** Task 0.1 consolidates the review files into one `review-reconciliation.md`. The issue
  draft is not committed.
- Also taken:
  - groups 4 and 6 are split;
  - `pyproject.toml` and `uv.lock` are added to the pre-merge diff;
  - the twice-run script's source goes in the PR body;
  - a line-ending dry run is task 0.2.

**Docs**

- **D1.** `peak_gpu_mem` (`torch.cuda.max_memory_allocated`) is added for the MLP entries, so the
  roadmap's "memory" is met (S metrics requirement; task 5.1).
- **D2 and D3.** Task 11.3 rewrites the roadmap's E4 sentence and makes its scope paragraph a pointer
  to `BENCH_SCOPE`. The proposal's scope line is a pointer.
- **D4.** The formula is now 12 × 6 × 102 (design D4).
- **D5.** The issue draft:
  - has a reproduction snippet;
  - gives the 0.3 % basis (0.11 % at `s55_f085_p45`, at most 0.29 %);
  - names the change, with filing instructions in the status line;
  - task 11.4 records the issue number.

### Not taken

**`bench mlp_h3` vs `surrogate_h3` exact cross-check.** It is not taken, for two reasons:

- the bench fits `mlp_h3` later in a process that has already run other fits;
- the exact `mlp_h1` check holds only because that fit runs first.

An exact h3 check would be fragile, and a loose one adds little.

**"Simplest by `n_params`".** Not taken: the `H`-first order is pre-registered in this proposal, and the
bench records `n_params`, so a reader can see where the two orders would differ.

---

## OpenSpec Review (round 4): add-surrogate-comparison-bench

### Verdict: BLOCKED (four blocking findings)

Reviewers: 1 sonnet, 2 opus, 3 skipped (no CI, Docker, dependency or packaging change), 4 sonnet,
5 sonnet, 6 opus.

Round-3 B1 (stroke sign) and most round-3 fixes were verified against code and data. Reviewers 1, 2,
4 and 6 confirmed, independently:

- the rotation values;
- the rank and singular-value values;
- the holdout overlaps;
- the 7,344 rows;
- the target beat equalling `filter_converged_beat` row for row on the 2-beat corpus;
- the issue-draft table.

### Blocking

| ID | Source | Finding |
|---|---|---|
| B1 | 2 | The ill-conditioning scenario cannot pass. With cond ≈ 1e7 and α = 1e-12, the ridge bias dominates, so neither solver recovers the generating coefficients. Fix: compare against the closed-form ridge solution of an SVD-built matrix with an orthogonal intercept column; `lstsq` reaches about 1e-11 and the normal equations about 1e-5. Name the internal solve function. |
| B2 | 2, 6 | The dropped singular value is not stable even to a decade. On E4's matrix, row reordering, transposition and 1-ulp perturbations give 1.65e-18 to 1.3e-16, a spread of 1.8 decades. Fix: compare the retained σ_r/σ₁ with `rtol`; only check the dropped value is `null` or below the rank tolerance and 1e-13; compare the tolerance exactly. |
| B3 | 5 | Row 16 of `docs/force_surrogate/roadmap.md` is already taken on `origin/main` (#172, `c87e39c`). |
| B4 | 5 | Task 0.1 would delete the uncommitted per-round review files, while the reconciliations cite their quotes. |

### Important

**Testing**

- **T1.** The 1b `metrics.json` mechanism misses `seed_sweep`, which is set after `build_metrics`
  returns. Spy on `build_metrics` and stop with a sentinel at `build_training_metadata`.
- **T2.** The fragile case's "within 1e-7" is absolute, which is about 1e-4 relative. Make it
  relative, and pin the boundary with a 1e-5 case.
- **T3.** The target-beat definition is ambiguous. N comes from the beat count, while "last common
  beat" and "converged-beat frame" say otherwise. Specify the baseline's frame. Reject non-contiguous
  beats and partial beats.
- **T4.** The runner's "trains on the target beat only" clause has no task.
- **T5.** 7b's smoke run expects the figure that 7c implements.
- **T6.** The torch-absence checks are vacuous in every environment that runs them. Use a
  `sys.meta_path` blocker.
- **T7.** The GPU command without `UV_PROJECT_ENVIRONMENT` would turn the Windows `.venv` into a
  Linux one.
- **T8.** The WSL2 recompute uses the same BLAS as the run, so it is not a cross-platform check.

**Spec and docs**

- `peak_gpu_mem` is never named or tested.
- `SelectionNotRecheckedWarning` has no home and no test.
- `threshold = 0` is unspecified.
- The design cites the uncommitted issue draft.
- The force-surrogate h3 sentence still says "chosen on the labelled holdouts".
- Task 11.4's `gate.py` edit in PR 2 breaks D0.
- The gh-04 sentence is ambiguous.
- The tolerances are not stated per check.
- PR #171 still cites #133 for the GCI band, and says "reliable only on the full 21".

**Math**

- A NaN seed hidden by a NaN-aware reduction could report `inside`; a NaN yardstick is unspecified.
- The provisional reason's 4.6 % is the last-but-one quantity and is hard-coded.
- The lab wrap known answer cannot kill mutants.
- The gate's `mlp_h3` and `ridge_fixed` verdicts are fully holdout-informed.
- For N ≥ 4:
  - the last-beat choice discards beats;
  - the last beat carries #173;
  - the exact regression no longer applies.

**Git**

- `issue-drafts/` is untracked and at risk.
- The branch must rebase on `origin/main` after #171.
- Under WSL2, `/mnt/c` can show a spurious dirty tree.
- `ridge_fixed`'s rank check sits in 4b.

### Suggestions (selected)

- Add the remaining rotation mutants to 6a.2.
- Add metric and selection mutants.
- Add figure and duration scenarios.
- Measure `peak_gpu_mem` relative to the allocation at reset.
- Note H = 16 as the exploration grid's edge.
- Note the control-versus-face test-difficulty confounder.
- Update README lines 19 and 27.
- Generate the h3 figure natively on Windows.
- Check `grid == "fine"` on the h3 figure, and its predictions schema.

## Reconciliation of review round 4

`S` = `specs/surrogate-comparison-bench/spec.md`; `F` = `specs/force-surrogate/spec.md`. Findings
are quoted in `review-round4.md`.

User decisions taken on 2026-11-18:

- **PR #171:** fixed and pushed (`ec739af`). The `#133` citations now point to T3c in `RESULTS.md`,
  and the ridge sentence now reads "its collapse on one 18-config subset is retested by F3a".
- **Issue draft:** the user had me file it. It is **#173**, and the draft directory is removed.

### Blocking

- **B1.** S scenario "The solve survives ill-conditioning" now compares `solve_ridge(M, A, λ)` with
  the closed-form ridge solution, at `λ = 1e-12`. Checked before writing: `lstsq` reaches
  1.3e-11, the normal equations 4.6e-5. At `λ = 1e-8` both pass, which is why λ is pinned. `solve_ridge`
  is named in the S ridge requirement.
- **B2.** S ridge requirement and S scenario "Committed bench results are consistent with their
  inputs":
  - the retained σ_r/σ₁ is compared with `rtol = 1e-8`;
  - the dropped σ_{r+1}/σ₁ is only checked to be `null`, or below both the rank tolerance and 1e-13;
  - the tolerance is compared exactly;
  - design D7 says why.
- **B3.** Tasks 11.3 and the proposal Impact list now say "the next free row (17 on today's `main`)".
- **B4.** Task 0.1 now concatenates every round's review and reconciliation verbatim into
  `review-reconciliation.md` before removing the per-round files, so nothing is lost and finding IDs
  stay citable.

### Important

**Testing**

- **T1.** Task 1b.1 now spies on `build_metrics` and raises a sentinel from `build_training_metadata`.
- **T2.** S scenario "Fold errors are computed as specified" uses relative 1e-7 (true) and 1e-5
  (false), and covers `threshold = 0`.
- **T3.** The target beat is defined in the S ridge requirement:
  - it is the largest common beat;
  - the common beats must be 0..N−1;
  - the beat must span the cycle;
  - the baseline uses the same frame;
  - "converged-beat frame" now reads "target-beat frame".
  - New S "Late-beat boundary" clauses cover the error cases.
- **T4.** Task 7b.1 adds a synthetic 4-beat runner test.
- **T5.** The figure is now group 7a, before the runner (7b), the driver (7c) and the GPU end-to-end
  test (7d).
- **T6.** S scenario "Importing the bench…" and tasks 1c.1, 3b.1 and 7c.1 use a `sys.meta_path`
  blocker.
- **T7.** The tasks header sets `UV_PROJECT_ENVIRONMENT`, per the fine README.
- **T8.** The recompute runs natively on Windows and under WSL2, and a CI failure halts (task 10.2,
  design D7).

**Spec and docs**

- `peak_gpu_mem` is named and defined in the S metrics requirement, listed in the proposal, and
  tested in 7b.1 and 7d.1.
- `SelectionNotRecheckedWarning` and `recheck_split` live in `ridge.py`, tested in 4b.1 with a
  mutant.
- `threshold = 0` gives `selection_margin = 0` (S ridge requirement).
- Design D5 cites #173, and the S grid-peak text cites #173.
- The F h3 sentence now says holdout-informed.
- #173 goes into `gate.py` in PR 1 (6a.2) and into the README in PR 2 (11.2). PR 2 makes no `src/`
  edit.
- The gh-04 sentence is rewritten (design D7).
- The tolerances are stated per check: 1e-12 for summaries, `rtol = 1e-8` plus `atol = 1e-9` for
  refits (design D7, S consistency scenario).
- Also added:
  - the duplicate `reference_configs` scenario;
  - the figure and duration scenarios;
  - "per-`d` record for `d = 3`";
  - README lines 19 and 27 in 11.2;
  - the h3 figure natively on Windows, with `grid == "fine"`;
  - the predictions-are-holdouts check for h3.

**Math**

- The worst-seed error is NaN if any seed's is. A NaN yardstick gives `outside`, a `null` margin
  and a reason. An all-0/0 component is documented (S gate requirement; scenario "Gate boundaries").
- The wrap-jump provisional reason names the quantity and is computed from the recorded jumps.
- The lab known answer is a sawtooth with three mutants (S scenario "The wrap jump is recorded";
  task 6a.2).
- The gate block marks `holdout_informed: true` for `mlp_h3` and `ridge_fixed`.
- For N ≥ 4, design D4 records the trade-offs (discarded beats, #173 on the last beat, beat N−2 as
  the alternative, the regression valid only on 2 beats) as a decision for the rerun.
- `peak_gpu_mem` is measured relative to the allocation at reset, after `synchronize`.
- Design D2 names the control-versus-face test-difficulty confounder; the proposal softens "told
  apart" to "help tell apart".
- Design D3 notes `H = 16` was the exploration grid's edge.

**Git**

- `issue-drafts/` is gone (filed as #173).
- Task 8.3 rebases on `origin/main` after #171 and re-runs everything.
- Task 9.1 checks `git status` inside WSL2, with a WSL-side worktree as the fallback.
- `ridge_fixed`'s rank is checked in 4a.1.
- Explicit-path staging is in the tasks header.

---

## OpenSpec Review (round 5): add-surrogate-comparison-bench

### Verdict: BLOCKED (one blocking finding, raised by reviewers 2 and 6)

Reviewers: 1 sonnet, 2 opus, 3 skipped (no CI, Docker, dependency or packaging change), 4 sonnet,
5 sonnet, 6 opus. Reviewers 1, 4 and 5 found nothing blocking.

Round-4 fixes were verified against code and data:

- the sentinel order in `train.py`;
- the meta-path blocker;
- the target-beat rule on both corpora;
- the retained singular value and fold ranks under perturbation;
- the wrap-jump sawtooth algebra;
- the rotation values;
- the face overlaps;
- a CPU recompute of about 8 s.

### Blocking

| ID | Source | Finding |
|---|---|---|
| B1 | 2, 6 | The ill-conditioning scenario's "to 1e-8" is unmeasured and its construction unpinned. Coefficients reach about 1e6, so absolute `lstsq` error is up to 1.7e-4. Under a different valid spectrum, `lstsq` reaches 1.9e-8 and the normal equations drop to 6.4e-8. Fix: pin `n = 27`, `s = logspace(0, −7, 16)`, `U` from the QR of a centred draw, `V`, `A` (27 × 3) and a seed; measure `max|β − β_cf| / max|β_cf|`; `solve_ridge` ≤ 1e-8, normal equations ≥ 1e-7. |

### Important

**Math (6)**

- **M1.** "Tolerance compared exactly" does not round-trip. Record `max(m, n)·eps` analytically and
  compare it to `rtol = 1e-12`.
- **M2.** `ridge` is weakly holdout-informed. Its grid contains post-holdout values, and the one-SE
  rule was adopted after design review saw holdout skills. Mark all four entries; `mlp_h1` is
  unverifiable.
- **M3.** Design D2's "face-without-holdouts partly removes test difficulty" is wrong. It removes
  optimism and widens the test-set difference. The like-for-like view is face and controls on the same
  holdout configurations.

**Testing (2)**

- **T1.** The key-set check must cover the nested key paths, with `match=` messages.
- **T2.** Two "Degenerate folds" clauses need group 4b code.
- **T3.** The static scan of the runner's ridge path must sit in 7b and name its functions.
- **T4.** `peak_gpu_mem` code is tested after it is written; there is no CPU-null task.
- **T5.** The provenance fields are not enumerated.
- **T6.** A non-empty `--out-dir` cannot be left "empty or absent"; it should be "unchanged".
- **T7.** No negative tests for the main consistency guards.
- **T8.** No test of direct grid evaluation.
- **T9.** The smoke run's device and blocker mechanism are unspecified.

**Spec (1)**

- **S1.** The prerequisite wording contradicts task 8.3.
- **S2.** The 10.2 halt rule ignores `atol`.
- **S3.** The proposal's row 17 does not match the reconciliation.
- **S4.** The wrap-jump provisional reason has no scenario.
- **S5.** The coarse dataset requirements are unspecified.

**Docs (4)**

- **D1.** The `project.md` "lands in PR 2" marker is never removed.
- **D2.** `--docker-image-digest` should be `--docker-digest`, as in every other script.
- **D3.** Task 11.3 would delete exploration numbers that live only in the roadmap.

**Git (5)**

- **G1.** The rebase in 8.3 runs with docs uncommitted; `CHANGELOG` will conflict. Rebase before
  group 1a.
- **G2.** The WSL-side worktree fallback would corrupt Windows git, and a detached checkout fails the
  clean-commit test. Use a WSL-native clone on a named branch.
- **G3.** The no-archive guard needs an in-repo banner.

### Suggestions taken

- 0/0 reason string.
- `beat1_vs_beat2` window applied to the normaliser too.
- Gap known answer and pinned `δ`.
- `peak_gpu_mem` measured as peak minus the baseline at reset.
- Note the exploration's 0.41 as the uncorrected leg.
- Duplicate `--entries` refused.
- The `beat1_vs_beat2` name kept by design.
- `recheck_split` on a non-fragile summary.
- 7d frame described, and the MLP `n_params` checked.
- Literal seeds in 3a.
- Proposal compute line, banner, seed-spread indent.
- A conventional PR title.

## Reconciliation of review round 5

`S` = `specs/surrogate-comparison-bench/spec.md`. Findings are quoted in `review-round5.md`.

### Blocking

- **B1.** S scenario "The solve survives ill-conditioning" now uses the reviewer's construction and
  measure, word for word:
  - `n = 27`;
  - `s = numpy.logspace(0, −7, 16)`;
  - `U` from the QR of a column-centred draw;
  - `V`;
  - `A` 27 × 3, from a fixed seed;
  - `λ = 1e-12`;
  - error `max|β − β_cf| / max|β_cf|`, with `solve_ridge` ≤ 1e-8 and the normal equations ≥ 1e-7.

### Important

**Math**

- **M1.** The S ridge requirement records the rank tolerance as `max(m, n) · eps`; the consistency
  scenario compares it to `rtol = 1e-12`.
- **M2.** The S requirement "Bench model entries and metrics" now marks every entry with a reason:
  - `mlp_h1` `"unverified"`;
  - `mlp_h3`, `ridge_fixed` and `ridge` `true`, the last weakly.

  S scenario "Holdout-informed entries are flagged" asserts all four. Design D3 explains `ridge`.
- **M3.** The design D2 sentence is corrected. S scenario "Holdout-informed entries are flagged" and
  task 5.1 add the like-for-like view: face and controls on the same holdout configurations.

**Testing**

- **T1.** Task 1b.1 now:
  - checks recursive key paths and `reproducibility.features`;
  - uses `match=`;
  - reuses `_install_recorder`.
- **T2.** Two "Degenerate folds" clauses move to 4b.1; 4a.1 keeps the 2-configuration clause.
- **T3.** 4a.1's static check covers `ridge.py` only. 7b.1 scans the runner's `run_ridge_entries`.
- **T4.** 7b.1 tests the `peak_gpu_mem` call order with a fake memory probe on CPU, including `null`
  for `--device cpu`, with "peak not reset" and "base not subtracted" mutants. The S metrics
  requirement defines the probe.
- **T5.** 7b.1 enumerates every provenance field, including `CUBLAS_WORKSPACE_CONFIG = null` when it
  is unset.
- **T6.** S scenario "The driver rejects unsafe invocations" and 7c.1 now say "absent, or prior
  contents unchanged".
- **T7.** 10.1 adds four negative tests.
- **T8.** New S scenario "The model is evaluated directly at the grid phases", tested in 5.1.
  4a.1 notes that the realistic known answer kills the own-phase mutant.
- **T9.** 7c.1 runs with `--device cpu`, using a `-c` wrapper and `runpy`.

**Spec**

- **S1.** The tasks prerequisite now reads "merges before PR 1 opens (task 8.3); groups 0–8.2 may
  start earlier".
- **S2.** Task 10.2 uses the spec's allclose rule.
- **S3.** The proposal now gives "17 on `c87e39c`".
- **S4.** S scenario "The wrap jump is recorded" pins the computed reason, with a hard-coded-text
  mutant.
- **S5.** The S `coarse_vs_fine` text requires every fine target beat. Both datasets are required
  flags, and the refusal scenario includes a missing configuration.

**Docs**

- **D1.** Task 11.2 updates the `project.md` subsection in PR 2. The proposal's Docs list says so.
- **D2.** `--docker-digest` everywhere.
- **D3.** Task 11.3 keeps the exploration numbers as history and adds `ridge_fixed` and the controls
  to the F3a row.

**Git**

- **G1.** Task 0.2 rebases before any code. The docs commit (8.3) comes before the post-#171 rebase
  (8.4), with the CHANGELOG conflict named.
- **G2.** Task 9.1 uses a WSL-native clone on the named branch.
- **G3.** The banner "PR 1 of 2 — archive this change only after PR 2 merges" is at the top of
  `proposal.md` and `tasks.md`.

---

## OpenSpec Review (round 6): add-surrogate-comparison-bench

### Verdict: NEEDS REVISION (no blocking findings)

Reviewers: 1 sonnet (8.5/10), 2 opus, 3 skipped (no CI, Docker, dependency or packaging change),
4 sonnet, 5 sonnet, 6 opus. **No reviewer found a blocking issue.**

Round-5 fixes verified:

- **Ill-conditioning test.** Reviewers 2 and 6 checked it over 3,000 seed and draw-order cases:
  `lstsq` at most 4.5e-10, the normal equations at least 1.66e-6.
- **Rank tolerance.** `max(m, n)·eps` is exactly numpy's ratio.
- **Holdout statuses** are justified.
- **Wrap-jump values** reproduce.
- **The sentinel mechanism** is writable.
- **Every scenario in both delta specs maps to a task.**
- **The six MODIFIED requirements** carry the full current text.

### Important

| ID | Source | Finding |
|---|---|---|
| I1 | 1 | The holdout-status key is never named. Use `holdout_informed` plus `holdout_reason`. |
| I2 | 1 | The prerequisite cites task 8.3, but the #171 gate is a later step. |
| I3 | 2 | 7b.1 omits `docker_image` and `timestamp` from the provenance checks. |
| I4 | 2 | The target-beat guards are tested in 6a, but implemented with the helper in 5, so they would be test-after. |
| I5 | 2 | The memory-probe test on CPU needs inference timing through an injectable seam, and a named `memory_probe` argument. |
| I6 | 6 | The like-for-like view's metric is unspecified (skill would break the cross-split rule), and pitch 30 has no holdouts. |
| I7 | 6 | Requiring the coarse corpus to hold the fine target beat would block the planned rerun on a ≥ 4-beat corpus. |
| I8 | 6 | No test pins the windowed `beat1_vs_beat2` normaliser. |
| I9 | 4 | Task 11.3 leaves #171's "so a drop at a face is not mistaken for a drop from less data", which over-claims. |
| I10 | 4 | The F3a row calls the controls "entries"; the Q4 and "retested" pointers would read as answered. |
| I11 | 5 | The 8.x docs written before the post-#171 rebase will conflict; `project.md` changed on main too. |
| I12 | 5 | The 0.2 line-ending dry run is vacuous; check `git status` after the rebase. |
| I13 | 5 | 9.1 leaves the Windows-side PR 2 worktree and the WSL clone's source unstated. |
| I14 | 5 | WSL runs on `/mnt/c` may leave stray files; check `git status` afterwards. |

### Suggestions taken

- Pin the sawtooth's `a`, `h`, `φ_0`, `δ` and `peak_t`.
- Fixed `(H, d)` for the intercept and standardisation scenarios.
- "Component" in the 0/0 reason.
- Design D6 lists `ridge`; "no entry is holdout-clean" in the gate block.
- Static scan for `scipy` and `sklearn`.
- `torch` and `physicsnemo` keys present, `null` when absent.
- 7d.1 flags.
- Face split built by hand in 1c.1.
- `peak_t` over 27 configurations asserted.
- The hard-coded-reason and full-grid-normaliser mutants.
- `hardware.driver_version` wording.
- `figures_h3` in the clean-commit list.
- README edits named by content.
- Re-read the merged roadmap in 11.3.
- The banner replaced in PR 2.
- `--allow-dirty` noted as bench-specific.
- The design's "one place" softened.

## Reconciliation of review round 6

`S` = `specs/surrogate-comparison-bench/spec.md`. Findings are in `review-round6.md`.

| ID | Resolution | Where |
|---|---|---|
| I1 | `holdout_informed` (`true` or `"unverified"`) and `holdout_reason`; the gate block also states that no entry is known to be holdout-clean | S "Bench model entries and metrics"; scenario "Holdout-informed entries are flagged" |
| I2 | The prerequisite now reads "merges before PR 1 opens (task 8.1). Groups 0–7 may start earlier." | `tasks.md` header |
| I3 | `docker_image` equals the supplied digest, and `timestamp` the supplied value verbatim | task 7b.1 |
| I4 | 5.1 owns the target-beat helper and its guards; 6a.1 keeps the `late_beat` clauses | tasks 5.1 and 6a.1 |
| I5 | Inference is timed around the runner's `predict_frame` call; the probe is the `memory_probe` argument | S metrics requirement; task 7b.1 |
| I6 | The like-for-like view reports RMS metrics only, with no skill key; for pitch 30 it is `null` with reason `"no labelled holdouts on this face"` | S scenario "Holdout-informed entries are flagged"; task 5.1 |
| I7 | `ValueError` only for a missing configuration; a missing target beat makes `coarse_vs_fine` `unavailable`, and the bench still runs | S `coarse_vs_fine` text; "Late-beat boundary" clause |
| I8 | A windowed-normaliser known answer (maximum at phase 0.02 outside the window, result exactly 0.1) with a full-grid-normaliser mutant | S scenario "Beat yardstick and its error share a window"; tasks 6a.1 and 6a.2 |
| I9 | Task 11.3 rewrites item 2's second sentence | task 11.3 |
| I10 | The F3a row's entries and splits are listed separately. The open-question pointer says F3a records stand-in yardsticks and the CFD uncertainty is still to be measured. "Retested by F3a" becomes a pointer. | task 11.3 |
| I11 | Group 8 is reordered: 8.1 rebase (or merge) after #171, 8.2 docs, 8.3 reconcile, 8.4 commit and checks, so the docs are written on the rebased tree | tasks 8.1–8.4 |
| I12 | 0.2 checks that `git status --porcelain` is empty after the rebase, and halts on normalisation changes | task 0.2 |
| I13 | Windows `git worktree add` from the main checkout on the named branch at `M` (used for the h3 figure). The WSL clone comes from GitHub, on the same named branch. `rev-parse` is `M` in both trees, and both are clean. | task 9.1 |
| I14 | `git status --porcelain` must be empty after every WSL run | tasks 1c.5, 7d.2, 8.4 |

## OpenSpec Review (round 7, the #195 amendment): add-surrogate-comparison-bench

Scope: only the amendment that adds `mlp_w256d5` and `mlp_w256d5_h3` (PR 1b). The rest of the change
was reviewed in rounds 1–6 and merged as PR #188. This round is the synthesis of the five reviewer
reports; the reports themselves were not kept verbatim.

### Verdict: NEEDS REVISION (before the fixes recorded below)

Reviewers: 1 sonnet, 2 opus, 3 skipped, 4 sonnet, 5 sonnet, 6 opus.

### Summary

The amendment was well formed and passed `openspec validate --strict`, and its quoted E4 skills and
fit counts were verified against the exploration's `ablations.parquet`. It relied on one value that
E4's own data contradicts (the fit time of the larger network), planned a commit that would break
test collection, and proposed a test that could not detect a fit filed under the wrong entry.

### Blocking issues

- **B1 (reviewers 2 and 5).** "`tests/test_surrogate_bench_gpu.py:18` does `from
  mosquito_cfd.surrogate_bench.runner import MLP_HARMONICS, MLP_HYPERPARAMETERS`. 8b.2 removes both
  names. pytest imports the module before `-m "not gpu"` deselects anything, so CI and the native
  suite get an `ERROR collecting` (exit 2)." Also: 8b.3's GPU test, written after the
  implementation, "goes green on the first run and is never red". Fix named by the reviewer: "move
  the GPU-test edit into 8b.1 and commit it with 8b.2".
- **B2 (reviewer 2).** "Identifying an entry by its hyperparameter tuple is circular. … Grouping by
  the tuple under test cannot detect a mislabelled fit." Mechanism named: "The test assigns each
  recorded call to an entry by its position: calls arrive in run order, 14 splits × 5 seeds per MLP
  entry, so call `k` belongs to `chosen_mlp[k // 70]`. Separately, a `SizedRecorder` whose prediction
  offset also depends on `hidden` and `num_layers` … checks that the `results.parquet` rows labelled
  `mlp_w256d5` and `mlp_w256d5_h3` carry their own entry's offset."
- **B3 (reviewer 6).** "The fit-time estimate is contradicted by E4's own data. … width256_depth5:
  28.6, 29.5, 28.8, 29.3, 28.6 s, about 3.2 times the shipped size. The 140 new fits therefore take
  about 140 × 29 s ≈ 68 min, not 21 min. Total MLP time is about 90 min, not about 42."
- **B4 (reviewer 5).** "The commit rule at tasks.md:26-28 does not cover 8b": one lettered group
  with several commits, and 8b.1 never says its red tests are committed with 8b.2.
- **B5 (reviewer 4).** The spec says the `mlp_h1`/`mlp_h3` rows are "identical with and without the
  two larger entries", while task 8b.1 says "timing columns excluded"; the rows include
  `fit_seconds`, inference time and `peak_gpu_mem`, "so the spec as written cannot pass".
- **B6 (reviewers 1, 4 and 5).** Task 8b.0 commits "the appended review round in
  `review-reconciliation.md`", which had not been written.

### Important issues

- **I1 (reviewer 1).** The run-order, one-table and trainer-defaults sentences have no scenario.
  Proposed scenario: "Entries run in a fixed order and read the shipped defaults".
- **I2 (reviewers 1 and 2).** The "rows equal with and without the larger entries" test "proves
  nothing with the current Recorder", whose predictions depend only on the seed and the harmonic
  count. It needs the size-dependent recorder.
- **I3 (reviewer 2).** Existing tests that break or go weak, by name:
  `test_the_shipped_hyperparameters_reach_fit_seed`,
  `test_mlp_h1_on_interpolation_runs_first_on_the_full_target_beat_frame` (checks only
  `phase_harmonics == 1`, which `mlp_w256d5` also satisfies),
  `test_the_summary_per_seed_skill_is_the_fits_own_skill`, `test_scope_holdout_status_and_gate`,
  `test_results_schema` (`n_params == 17` for every entry).
- **I4 (reviewer 2).** The run-order test has no observable for the ridge entries; assert
  `summary["entries"] == meta["entries"] == list(dict.fromkeys(results["entry"]))`.
- **I5 (reviewer 2).** Missing mutants: `run_mlp_entry` passing the default `hidden` while table and
  metadata stay correct; a larger entry missing from the MLP dispatch; a ridge-only run writing
  `null`; reasons losing `E4` or the harmonic phrase; state which test kills the `lr` mutant.
- **I6 (reviewer 2).** Tests that compare the code with itself (`parse_entries(None) ==
  list(runner.ENTRIES)`); pin literals.
- **I7 (reviewer 2).** PR 2's tasks 10.1 and 11.1 do not cover `mlp_hyperparameters` or the 2 × 2
  paragraph; 10.2 should record the recompute's duration.
- **I8 (reviewer 6).** Design D8's "E4's ranges … overlap or nearly touch" is false: the shipped
  MLP's range lies below both others; only three harmonics and the larger network overlap, and the
  larger network is higher on all 5 seeds. The proposal's "about as well" understates it.
- **I9 (reviewer 6).** Pairing: the four MLP entries share each seed's validation carve. "Any
  statement that one cell of the 2 × 2 beats another cites the 5 per-seed differences from
  `per_seed_skill`, not only overlapping ranges."
- **I10 (reviewer 6).** Claim scope: width 256 at depth 5 was the best of E4's size arms, chosen on
  the 6 holdouts; `mlp_w256d5` on `interpolation` "is a near re-run of E4 … not new evidence". "The
  size-versus-phase-input question is answered from the face metrics without holdouts." The 2 × 2
  does not separate width from depth, and the interaction is reported descriptively, not tested.
- **I11 (reviewers 2 and 6).** D8 "Order" overclaims: the larger entries run after every `mlp_h1`
  and `mlp_h3` fit and each fit reseeds, so they cannot change those rows; PR 2's `mlp_h1`
  regression "is not a test of this", and nothing on the GPU checks `mlp_h3`.
- **I12 (reviewers 1 and 6).** `n_params` has no spec clause and the GPU task asserts only "larger".
  Known answers: 9094, 9350, 266246, 267270.
- **I13 (reviewer 1).** `--entries` without `mlp_h1` makes "SHALL fit `mlp_h1` … first" vacuous.
- **I14 (reviewers 4 and 5).** The "PR 1 of 2" banners, design D0 and "both PR links" describe two
  PRs; task 11.4 replaces the banner by its old text; PR 1's task 8.4 is still unticked.
- **I15 (reviewer 5).** "'Closes #195' is wrong": the 2 × 2 has results only after PR 2, and a
  negated closing keyword still closes. Use "Advances #195" here and "Closes #195" in PR 2.
- **I16 (reviewer 5).** `/cleanup-merged`'s archive step would archive the change after PR 1b; say
  to skip it. Task 9.1 needs the precondition that PR 1b is merged.
- **I17 (reviewer 4).** Docs: 8b.4 omits the `runner.py` table comment and the "PR 1b" changelog
  label; roadmap Revision item 3's entry list is not in 11.3; the fine README plan never says
  `run_metadata.json` carries `mlp_hyperparameters`.
- **I18 (reviewers 1 and 4).** The Impact statement omits the test files and the change's own files.
  The entry list, holdout reasons and fit count are repeated in places that can drift.

### Suggestions

- S1 (reviewer 6): check `mlp_w256d5` / `interpolation` against E4's per-seed skills in task 9.2.
- S2 (reviewer 2): GPU test asserts the metadata values, a larger `peak_gpu_mem` for the larger
  entry, and the warm-up check at the new layer shapes.
- S3 (reviewer 2): monkeypatch `train.DEFAULT_LR` and reload the runner to check the table reads the
  named constants.
- S4 (reviewer 1): a scenario for a diverged larger fit.
- S5 (reviewer 6): record the best-validation epoch per fit.
- S6 (reviewers 1 and 4): split 8b.5's checks; name the shipped-artifact check; shorten the
  amendment section.

### Risk assessment

- CI breakage: LOW after B1.
- Reproducibility: LOW; the amendment adds provenance (`mlp_hyperparameters`).
- Documentation drift: MEDIUM until PR 2 (roadmap rows and the README are PR 2's).
- Numerical and scientific correctness: LOW for the code; MEDIUM for how the 2 × 2 is read, which
  D8 now scopes.

### Review details by agent

1. Spec quality: validate passed; 7/10; I1, I2, I12, I13, I18, B6.
2. TDD and testing: B1, B2, I2–I7, I11.
3. CI/CD and build: skipped: no CI, Docker, dependency or packaging change (runner and tests only).
4. Documentation: E4 values and counts match #195; B5, B6, I14, I17, I18.
5. Git workflow: B1, B4, B6, I14–I16; keep PR 1b separate from PR 2.
6. Math and statistics (launched: surrogate training entries, seed handling and quoted skills):
   E4 skills VERIFIED, fit counts VERIFIED, 9 s for the larger network CONTRADICTED (B3), holdout
   labels VERIFIED, `n_params` VERIFIED against E4's recorded counts, GPU memory feasible (under
   1 GB); I8–I12, S1.

## Reconciliation of review round 7

`S` = `specs/surrogate-comparison-bench/spec.md`. The E4 values were recomputed from
`ablations.parquet` (`origin/explore-surrogate-experiments`) before being written into the design.

| ID | Resolution | Where |
|---|---|---|
| B1 | `tests/test_surrogate_bench_gpu.py` is rewritten against `runner.MLP_ENTRIES` in 8b.1 and committed with 8b.2; 8b.3 only runs it under WSL2. No alias of the removed names is kept. | tasks 8b.1 (last bullet), 8b.2, 8b.3 |
| B2 | Calls are assigned to entries by position (`k // 70`), and a `SizedRecorder` makes each entry's rows and `n_params` distinguishable; the scenario requires that rows labelled with an entry carry that entry's own predictions. | tasks 8b.1 "Test helpers"; S scenario "The larger MLP entries change only width and depth" |
| B3 | About 29 s a fit, about 70 min for the 140 new fits, about 90 min in all; measured by PR 2. | `proposal.md` Impact, Compute; design Context row; task 9.2 |
| B4 | The commit rule names group 8b's commits (8b.0, 8b.2, 8b.4) and says red tests are committed with the implementation. | `tasks.md` rules; 8b.1 first line |
| B5 | "every column except the timing and `peak_gpu_mem` columns", compared with an `--entries mlp_h1,mlp_h3` run. | S same scenario, last clause; task 8b.1 |
| B6 | This round is appended before the 8b.0 commit, which the task now says. | task 8b.0 |
| I1 | New scenario, with the reviewer's content. | S "Entries run in a fixed order and read the shipped defaults" |
| I2 | The equality test uses `SizedRecorder`. | task 8b.1; S scenario "Given" |
| I3 | Each test is named with its change. | task 8b.1 "Existing tests in that file" |
| I4 | The three-way `entries` equality against the literal order. | task 8b.1; S fixed-order scenario |
| I5 | All added to the mutant list, which must name the killing test; `lr` is compared with the literal `1e-3`. | task 8b.2 |
| I6 | Literal pins for the table, the default `--entries` and the entry set. | task 8b.1 import and CLI bullets |
| I7 | Added. | tasks 10.1, 10.2, 11.1 |
| I8 | D8 states the three ranges, the per-seed values and "higher on each of the 5 seeds"; the Why says "at least as well". | design D8 "What E4 showed"; `proposal.md` amendment Why |
| I9 | D8 "Paired reading"; the README task requires the 5 paired differences. | design D8; task 11.2 |
| I10 | D8 "Where the comparison is unselected" and "What the 2 × 2 cannot show"; the README task repeats the limits. | design D8; `proposal.md` "Not in the amendment"; task 11.2 |
| I11 | D8 "Order" rewritten with the reviewer's argument. | design D8 |
| I12 | Known answers in a GPU-tier scenario and in the GPU test; the CPU tier checks `n_params` per entry with the sized fake model. | S "The parameter counts are the architectures'"; task 8b.1 |
| I13 | The order rule is stated for the chosen entries; `mlp_h1` is first "when `mlp_h1` is among them". | S "Bench model entries and metrics" |
| I14 | New banner in both files; D0 is "Three PRs" with a PR 1b bullet; 11.4 replaces "the delivery banner"; "all three PR links"; 8.4 ticked with its PR. | `proposal.md`, `tasks.md` banners; design D0; tasks 8.4, 11.3, 11.4 |
| I15 | "Advances #195" in PR 1b, "Closes #195" in PR 2. | tasks 8b.5, 11.4 |
| I16 | Skip the archive step; 9.1 precondition. | tasks 8b.5, 9.1 |
| I17 | Added. | tasks 8b.4, 11.2, 11.3 |
| I18 | Impact lists code, tests, the change's files, docs and compute. The proposal and design point to the spec for definitions; the two holdout bullets are merged. | `proposal.md` amendment; design D6 sentence; S holdout list |
| S1 | Adopted, tolerance 1e-3. | task 9.2 |
| S2 | Adopted. | task 8b.1 GPU bullet |
| S3 | Deferred: reloading the runner module in a test risks stale module state in the other bench tests; the literal pin plus the comparison with `run_training`'s defaults is kept, and the named-constant read is checked in review. | task 8b.1 import bullet |
| S4 | Not added: a diverged fit of any `mlp_*` entry already reaches the gate as NaN errors (PR 1's "Gate boundaries" scenario and its test); the new entries take the same path. | — |
| S5 | Deferred: recording the best-validation epoch changes the shared trainer seam, which is outside this amendment. | — |
| S6 | Adopted. | tasks 8b.2, 8b.5; `proposal.md` amendment |

## PR 1b pre-PR self-review (`/review-pr`, branch mode, `e8f9c96`)

Five reviewers (code quality, testing, scientific rigour, performance/GPU/build, behavioural
correctness) on `b6c5ab1..e8f9c96`. Verdict: **COMMENT**, no blocking finding. Important findings
and how each is addressed:

| # | Finding | Resolution | Where |
|---|---|---|---|
| T1 | The shuffled-order test does not assert the clause "the first recorded call is `(64, 3, 1)` on `interpolation` at the first seed"; only the unshuffled run does. | Asserted in the shuffled run too. | `test_entries_run_in_a_fixed_order_whatever_order_is_given` |
| T2 | "Rows labelled with each MLP entry carry that entry's own predictions" is checked on one row per entry. | Checked on every row of every MLP entry (all splits and seeds) against the `SizedRecorder` offset; two partial-mislabel mutants (one seed; one split and seed at the wrong depth) are killed, which the one-row check missed. | `test_each_mlp_entrys_rows_carry_its_own_fits` |
| R1 | D8's "best of its size arms, so untuned does not mean handicapped" is a non sequitur: every E4 arm used lr 1e-3, and w256d5 is the corner (largest point) of the size grid. | Replaced by an explicit confound statement: corner of the grid, not a selected optimum; every reading of the large cells, the interaction included, is conditional on lr and epochs. Same caveat in the README task. | design D8 "Only two arguments differ"; task 11.2 |
| R2 | CHANGELOG and `project.md` say the 2 × 2 lets the two gains "be told apart", which overclaims against D8. | Reworded to "meant to show, descriptively", with the limits named and D8 cited. | `docs/CHANGELOG.md`; `openspec/project.md` bench list |
| R3 | Task 9.2's 1e-3 tolerance is about the smallest E4 paired difference against h3 (0.0011), and E4 ran through its own wrapper, not `fit_seed`. | 9.2 records the largest per-seed `|Δ|` and re-checks the 5 paired signs from the bench's own `per_seed_skill`; statements use the bench's values. D8 says E4 shared `train_model`, not `fit_seed`. | task 9.2; design D8 "Where the comparison is unselected" |

Suggestions adopted: the stale exploration reference and the "one place" rule in design Context;
the seed-range figure (0.002–0.005) and the 5-of-5 sign result (one-sided p = 0.031) in D8; the
README task forbids "beats" for a sign result; `SizedRecorder`'s depth coefficient is far below
the seed's, so a mutant changing depth and seed together cannot hit another real offset (no real
offsets collided before either); the shuffled test also checks that no entry's rows are interleaved; the
runner's D7 comments say "when chosen"; the warm-up comment says the workspace is per handle and
lazy kernel loading lands in the first fit's time; the GPU test's warm-up check is called a
sanity check. Not adopted: a `TypedDict` or `MappingProxyType` for `MLP_ENTRIES` (the import test
pins the literal table and the recorder's keyword-only signature catches a misspelt key); the
probe's `gc.collect()` and timer/sync swap (no reference cycles, every fit ends in a host sync;
identical peaks across seeds); recording `n_val_configs` (recoverable from the commit).
Rejected on the evidence: a reviewer read E4's shipped-size fit as 19.4 s and the compute
estimate as 2× high. That was the first, warm-up fit; E4's baseline median is 9.26 s
(8.76–19.38) and `width256_depth5`'s 28.84 s (28.58–29.48), so "about 70 min" for the 140 larger
fits stands. Task 8b.4's "comment above the table" went in with the 8b.2 commit, not 8b.4's.

Re-review of the fix commit `10ffdf6` (one reviewer, by reproduction): no blocking finding. One
important finding, introduced by the fix: D8 called `width256_depth5` "not a selected optimum",
contradicting D8's own "best of E4's size arms" and the spec's holdout reason. Reworded to "the
largest point tried and the best of E4's size arms, so an edge of the grid, not an interior
optimum". Suggestions adopted: "shipped with" (not "chosen for") the 9k net, since the shipped
hyperparameters' provenance is unrecorded; "its MLP rows" in Context; D8 "Paired reading" aligned
with the sign-result rule; the every-row test also requires all 14 × 5 (split, seed) blocks.
