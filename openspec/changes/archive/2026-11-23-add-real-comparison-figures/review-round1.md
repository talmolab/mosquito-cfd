# OpenSpec Review: add-real-comparison-figures (round 1, 2026-11-18)

## Verdict: BLOCKED

Reviewers: 1 sonnet, 2 opus, 3 skipped, 4 sonnet, 5 sonnet, 6 opus. All ran on the requested model.

## Summary

The core statistics are sound. The math reviewer reproduced most of them bitwise on the committed
data:

- the cycle-mean R² identity;
- σ's independence of the seed;
- the baseline rebuild;
- `range == min/max(runs)`;
- `CF_y` being the only disjoint target.

The blocking findings are about testability and process, not the science:

- a scenario that cannot be written with real-helper fixtures;
- committed-artifact checks that cannot fail for the stated reason;
- path portability tested only for backslashes;
- no guard against a corrupt R² > 1;
- a clean-tree precondition that cannot hold;
- a coarse-README guard that cannot count ratios on today's README;
- edits inside a guarded README section.

## Findings (IDs used by `reconciliation-round1.md`)

Reviewer prefixes: **S** spec quality, **T** TDD, **D** docs, **G** git, **M** math/physics.

### BLOCKING

| ID | Finding (short) |
|---|---|
| T-B1 | "Per-seed values differ from every value in config_resolved, per_target, phase_baseline_skill" is unsatisfiable: `runs[0]` equals those blocks by construction |
| T-B2 | Committed-artifact checks fail on absent files, not staleness; the staleness test can pass vacuously |
| T-B3 | Path portability tested only for backslashes; an absolute `C:/...` passes; `as_posix` test does not work on Linux |
| T-B4 | No guard against `config_mean_r2 > 1`; NaN becomes `null` via `_json_safe`, indistinguishable from the sentinel |
| G-B1 | "`git status --porcelain` is empty" before rendering cannot hold: the change dir is untracked and the task ticks modify a tracked file |
| D-B1 / S-I1 | The coarse quasi-steady guard cannot count "exactly two `~x.x×`": bold `~**1.3×**`, the historical `~2.3×`, and multipliers in the next bullet |
| D-B2 | Edits inside the fine README's guarded "Coarse vs fine" section trip `_BANNED`, `resolution` and the one-heading check |
| D-B3 | The fine README's `docker_image` paragraph does not cover the new sidecars' two digests |

### IMPORTANT

| ID | Finding (short) |
|---|---|
| S-I2 | Refusal rules (`wingbeat < 1`, config sets, beat counts, non-finite, `reference_configs`, missing file, no partial output) have no scenario |
| S-I3 / M-S5 | Beat label defined only for N=2; beat count and contiguity undefined; the label ignores the prediction rows |
| S-I4 | `input_files` roles never enumerated |
| S-I5 | Range-vs-runs check scope inconsistent (D2: `skill_ranges`; spec/tasks: any figure) |
| S-I6 | "Every number … read verbatim or checked" overstates; the R² wording regressed from "never re-derived" without note |
| S-I7 / M-S7 / T-I10 | "Recompute every committed sidecar" cannot hold for `run_metadata` fields |
| S-I8 | Caption phrases in proposal/design/tasks are absent from the spec; banned-word check vague |
| S-I9 | `## Why` too long |
| T-I1 | Fixture should assemble metrics exactly as `run_training` (incl. `build_metrics`); task 2.2 circular; schema parity; hand known answers; byte-distinct corpora; null by construction |
| T-I2 | In-axes notes untestable after `plt.close`; record notes and captions in the sidecar |
| T-I3 | Missing tests: schema columns; all 8 missing files; ±inf; JSON NaN; zero rows; one config; R²=1; R²=−1e6; partial null seeds; non-primary null; seed count / primary seed; bin-edge convention; waveform RMS; σ ddof; seeds-panel values; primary ε; swapped predictions; beat label from predictions |
| T-I4 | "Before any read" spy weak; parametrize over all builders |
| T-I5 / M-I1 | `rel=1e-12, abs=0` ill-conditioned for `1 − x` quantities near 0 and for ε near R²→1; use complement / absolute forms |
| T-I6 | Near-threshold mutants survive; "etc." in the mutant list |
| T-I7 | TDD ordering: 3.2, 3.9, 3.11 tests come after implementation |
| T-I8 / G-I | Planned-red commit is red for the wrong reason and blocks the clean render |
| T-I9 / G-I2 | Nothing ties a committed figure to the renderer code; `git.dirty` ignores untracked files; re-render rule |
| T-I11 | Committed recomputation must not just rerun the builder; independent anchors in the test |
| T-I12 | "Tracked by git" and "fixtures dir absent" untested |
| M-I2 | Null-R² path contradicts the cross-checks; null is all-or-none (σ≈0); refuse partial null |
| M-I3 | `error_histograms` undefined for null skill / RMSE₀≈0 |
| M-I4 | Single-seed histogram without seed context; seed 1234 is the worst seed for several targets |
| M-I5 | "Both grids' cycle means are equally tight" unsupported (CF_y σ/waveform 1/42 vs 1/26) |
| M-I6 | Worst-case tests (R² −6.70, −4.70; ε > σ) missing |
| M-I7 | `density=True` normalises by in-range count |
| M frames | Labels must say lab-frame components on the wing, moments about the hinge; never chord/drag/normal |
| G-I1 | Task 4.3 / 7.9 / 6.1 commits too large; commit plan |
| G-I4 | Corpus regeneration ordering (note: the reviewer took PR #171 for the regeneration; #171 is the roadmap docs PR — the regeneration is a future change) |
| G-I lab | Slides citing an unpushed commit; renderer fixes after slides are built |
| G-I F3a | Merge-conflict plan is a hope, not a plan |
| D-I4 | New sidecar fields documented nowhere a reader looks; `git.commit` is the parent of the figure commit |
| D-I5 | Regeneration recipe in 3+ places |
| D-I6 | project.md: "Four thin argparse CLI drivers"; the parenthetical; clean deletion |
| D-I7 | CHANGELOG: history kept; single Added bullet + Changed line |
| D-I8 | Fine README `figures/` row contradicts the new subfolder |
| D-I9 | "Records predate `library_versions`" said twice |
| D-I10 | Task 0.2 `rg` scope |
| S-S4 | Impact omits docs files |
| S force-surrogate | "record the seeds … all under `library_versions`" misreads; not-installed behaviour |

### SUGGESTIONS (disposition in the reconciliation)

S-S1 (bin edges at ±3), S-S2 (R² > 1, σ = 0), S-S3 (null skill range drawn), S-S5 (split
requirements), S-S6 (change id), S-S7 (tasks commit points, "etc."), S-S8 (grammar); T-S1 (CI lint
paths), T-S2 (warnings as errors), T-S3 (exit code 2, every flag), T-S4 (partial write), T-S5
(banned scope), T-S6 (IB-free regex, "above 1"), T-S7 (rg hit list), T-S8 (numpy cycle means),
T-S9 (second-clone cmp); M-S1 (finer bins), M-S2 (autocorrelation in caption), M-S3 (per-seed RMSE in
scales panel), M-S4 (cross-corpus `val_configs`), M-S6 (`_BANNED` scope), M-S8 (QS attribution); D-11
(DRY proposal/design/spec), D-12 (shared rule literal), D-13 (`CF_c ≈ v` prose guard), D-14/15
(wording), D-F (succinctness).
