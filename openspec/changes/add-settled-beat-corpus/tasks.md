# Tasks: add-settled-beat-corpus

Rules for every task: tests are written first and seen to fail for the right reason before the
code exists. Run tests with `uv run --frozen pytest -m "not gpu"` from Git Bash. Commit messages
say "advances #192" (also "advances #101" / "advances #103" where relevant), never a closing
keyword. **HUMAN GATE** marks a step that needs the user's explicit go-ahead.

## Stage 1 — PR 1: settling metric, pre-registration, long-run decks

### 1. Settling metric (`force_surrogate/settling.py`)

- [ ] 1.1 Tests first (`tests/test_settling.py`), on synthetic beats built in the test:
  - an exactly periodic signal gives step change 0, tail bound 0 and beat 1 settled;
  - a geometric approach `w_b = w_inf + a·r^b·g(phase)` gives step changes, contraction ratio and
    tail bound equal to their closed forms (`rel=1e-9`), and the estimated distance `D + T` is at
    least the true distance to `w_inf` for every beat;
  - a signal whose steps grow gives `contracting = False`, an infinite tail bound and no settled
    beat;
  - a beat with fewer than 95% of its expected rows is excluded and named; the last complete beat
    is the reference;
  - a later beat that fails makes earlier beats not settled (the "every beat from b on" rule);
  - a ratio with a denominator below `1e-4` is dropped; with none left `T = s_B`;
  - the verdict takes the worst target: five targets inside the tolerance and one outside fails;
  - resampling is periodic: a signal sampled on a shifted phase grid gives the same result;
  - bad input (missing column, fewer than 3 complete beats, NaN, zero peak) raises `ValueError`
    naming the config and the column.
- [ ] 1.2 Implement `resample_beats`, `settling_metrics`, `settled_beat`, `training_wingbeat`.
- [ ] 1.3 Pinning test: `SETTLED_TOLERANCE == 0.01`, `N_PHASE == 256`, the 95% completeness rule
  and the `1e-4` noise floor equal the values written in `PREREGISTRATION.md` (parsed from the
  file) and in the spec delta.
- [ ] 1.4 Regression anchor: on the committed 2-beat corpora, `training_wingbeat` is 1 and selects
  exactly the rows `wingbeat >= 1` selects.

### 2. Decision rule

- [ ] 2.1 Tests first: one test per row of the outcome table in `design.md` D3, on hand-built
  per-run results (all settled → max; a 6-beat run unsettled → `extend`; the 8-beat run unsettled
  → `stop`; not contracting → `stop`; `N* > 6` → `needs_cost_approval`; `N* < 5` → used as is).
- [ ] 2.2 Implement `decide_beat_count(run_results)` returning the action, `N*`, and the run,
  beat and target that set it.

### 3. Long-run decks (`examples/settling_check/`)

- [ ] 3.1 Tests first (`tests/test_settling_decks.py`):
  - each generated deck differs from its committed corpus deck in exactly the allowed keys
    (`max_step`, `stop_time`, added `amrex.the_arena_init_size`; coarse twins also
    `amr.plot_int`), compared key by key after parsing;
  - `max_step` / `stop_time` equal `derive_run_duration(f*, n)` for 8, 6 and 6 beats;
  - `ns.cfl`, `ns.fixed_dt`, `ns.init_iter` and the grid are equal to the corpus deck's;
  - the manifest lists both the source deck's and the generated deck's SHA-256;
  - regeneration of the committed decks is byte-identical.
- [ ] 3.2 Implement `generate_decks.py` and commit the six decks and `settling_manifest.json`.

### 4. Controls and report

- [ ] 4.1 Tests first for `compare_force_series` (C1–C3): identical series pass; a `1e-9`-of-peak
  perturbation fails at tolerance `1e-10`; a different time grid fails with a message naming the
  first differing step; the coarse cross-image mode reports and applies the `1e-6` stop
  threshold.
- [ ] 4.2 Tests first for the field statistic `field_change_stats(a, b, u_ref)` on small arrays:
  identical fields → 0; a uniform offset of `0.1·u_ref` → median 0.1 and fraction-above-10%
  boundary behaviour; shape mismatch and non-finite input raise.
- [ ] 4.3 Tests first for `scripts/check_settling.py`: on a synthetic run directory it writes a
  `settling_report.json` that carries the criterion constants, the pre-registration file's
  SHA-256, the git commit, each run's metrics and the decision; a missing control result makes the
  report say `controls_incomplete` and the exit code non-zero.
- [ ] 4.4 Implement 4.1–4.3 and `scripts/make_settling_figure.py` (step change per beat on a log
  axis, one panel per target, three configurations × two grids, tolerance line; metadata sidecar
  in the project's figure convention). Figure test: the sidecar's numbers equal the report's.
- [ ] 4.5 Write `examples/settling_check/PREREGISTRATION.md` and `README.md` (what will be run,
  the criterion, the outcome table, the controls, the commands).

### 5. Spec, docs, PR 1

- [ ] 5.1 `openspec validate add-settled-beat-corpus --strict`.
- [ ] 5.2 `CHANGELOG.md`; `openspec/project.md` gains a short "Settling check" entry.
- [ ] 5.3 `/review-pr`, focused re-review of each fix commit, `/pre-merge-check` (no Copilot
  review). Merge `main` in, never rebase; `git merge-base --is-ancestor origin/main HEAD` before
  every push. **HUMAN GATE: approval before pushing.**

## Stage 1 — runs on gh-04 (after PR 1 is merged)

- [ ] 6.1 Read-only preparation: check out the PR 1 merge commit on gh-04; verify the image
  digest and its IAMReX label against `docker/build-args.env`; confirm free disk and an idle GPU;
  copy the committed cluster force CSV for `s55_f115_p30` from the share for C1.
- [ ] 6.2 **HUMAN GATE: go-ahead for the controls.** Run C1 (400 steps) and C2 (200 + restart +
  200). Record both results and the measured seconds per step.
- [ ] 6.3 Report C1/C2 and the projected wall time for all six runs. If C1 fails, stop.
- [ ] 6.4 **HUMAN GATE: go-ahead for the long runs.** Run, one at a time: `s45_f100_p30` (8
  beats), `s55_f115_p30` (6), `s45_f100_p45` (6) on the fine grid; then the three coarse twins.
  After each run: extract, run C3 and C4, record. Stop on any failed control.
- [ ] 6.5 If a 6-beat run has no settled beat: **HUMAN GATE** before extending it.
- [ ] 6.6 Copy the raw runs from gh-04 to `Z:\…\examples\settling_check_2026-11\` and verify
  file counts and force-CSV hashes after the copy.

## Stage 2 — PR 2: results, decision, regeneration tooling

### 7. Stage 1 results

- [ ] 7.1 Commit the extracted datasets, run records, `settling_report.json`, the figure and
  `DECISION.md`. Test: `DECISION.md`'s N equals `decide_beat_count` recomputed from the committed
  datasets, and the report's numbers recompute to `rel=1e-12`.
- [ ] 7.2 **HUMAN GATE: the user confirms N** (and the cost, if `N* > 6`). Update `proposal.md`,
  `design.md` and this file with the chosen N; record any deviation from the pre-registration in
  a `### Why … instead of …?` section.

### 8. Generator and drivers

- [ ] 8.1 Tests first: `generate_sweep(frames_per_beat=20, checkpoints_per_beat=1)` writes
  per-config `plot_int` 118 / 100 / 87 and `check_int` 2353 / 2000 / 1739; with both `None` the
  output is byte-identical to today's for both old corpora (the existing byte-identity tests stay
  as they are); non-positive values raise.
- [ ] 8.2 Tests first: both drivers accept `--n-wingbeats`; each refuses, with a message naming
  both values, to write into a directory whose manifest has a different `n_wingbeats`; omitting
  the flag reproduces the committed 2-beat corpora.
- [ ] 8.3 Parametrize the regeneration tests over the corpus registry so each reads `n_wingbeats`
  (and the field-capture settings) from its own manifest.
- [ ] 8.4 Implement 8.1–8.2.

### 9. Supersession writer (#103)

- [ ] 9.1 Tests first: `append_supersession_entry` creates the list when absent, appends without
  touching existing entries or other keys, rejects an entry missing a required field, and is
  idempotent for an identical entry.
- [ ] 9.2 Implement it with a thin CLI; replace the hand edit in the runbook.

### 10. Guards and acceptance gate

- [ ] 10.1 Tests first: the symmetry ratio is computed on the final requested beat; on both
  committed 2-beat corpora every ratio is bit-identical to the current function's; on a synthetic
  6-beat run truncated in its last beat the guard fires, and with the old definition it would not
  (the mutation that motivates the change).
- [ ] 10.2 Tests first: the gate fails when any configuration's final-beat tail bound exceeds the
  tolerance, names the configuration and target, and writes `cluster_run.settling` (per-config
  values and result) into `sweep_provenance.json`; a corpus with fewer than 3 complete beats gets
  `settling: not_applicable` with the reason, so the 2-beat corpora still pass.
- [ ] 10.3 Register the two new corpora in `CORPUS_REGISTRY` behind their existence (the
  directories arrive in PR 3) with a test that an unregistered-but-present corpus directory fails.
- [ ] 10.4 Implement 10.1–10.3.

### 11. Storage manifest

- [ ] 11.1 Tests first: on a fake run tree the manifest lists per-config byte size, plotfile and
  checkpoint steps, and the two hashes; a missing plotfile step, an unexpected extra step and a
  missing run directory are each reported against the sweep manifest's expected steps.
- [ ] 11.2 Implement `write_storage_manifest` / `check_storage_manifest` and a script driver.

### 12. Cluster sizing (#101)

- [ ] 12.1 Tests first (extend `test_submit_workflow_active_deadline.py`,
  `test_submit_workflow_smoke_guards.py`, `test_argo_workflows.py`): the deadline equals the
  step-based formula for a toy manifest (3 configs × 3600 steps, fine grid, parallelism 1 →
  50400 s); a grid with no measured rate fails with a clear message unless the two environment
  variables or an explicit deadline are given; the smoke `max-step` comes from the manifest; the
  retry budget covers `limit + 1` attempts of the manifest's longest configuration.
- [ ] 12.2 Implement in `submit_workflow.sh` and the workflow files; `argo lint` in the existing
  lint step. If `backoff.maxDuration` cannot take a parameter, apply the static fallback and
  record why in `design.md`.
- [ ] 12.3 Update `.claude/commands/submit-cluster-sweep.md`, `cluster/argo/README.md` and the
  spec text: step-based numbers, the new corpus directories, the settling check in the post-run
  gate, the storage manifest, the supersession CLI, and the stale 24 h figures.

### 13. Generate the new corpus decks

- [ ] 13.1 Generate `examples/settled_sweep` and `examples/settled_sweep_fine` with the confirmed
  N; commit decks, manifests and provenance (with a supersession entry naming the 2-beat corpus).
  Tests: byte-identical regeneration; the deck guards; the CFL and `prescribed_vel` / `num_steps`
  lints that apply to the old decks apply to these.
- [ ] 13.2 `/review-pr`, re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before
  pushing.**

## Stage 2 — cluster runs (after PR 2 is merged)

- [ ] 14.1 `/submit-cluster-sweep` step 0–1 for each corpus: digest, wing-phase diagnostic,
  quota, provisioning of the new workspace directories on the share, free space on `Z:`.
- [ ] 14.2 **HUMAN GATE: smoke runs** (full-length `s55_f115_p30` on each grid). Record seconds
  per step; set the coarse rate; CC-F1; one-config gate including the settling check.
- [ ] 14.3 **HUMAN GATE: full sweeps** (coarse first; it is cheap and exercises the pipeline).
  Mid-sweep check after 2–3 configurations.
- [ ] 14.4 Post-run: acceptance gate with the settling check on all 27 configurations per corpus,
  per-config run metadata, storage manifest. Any failure: stop and report.

## Stage 2 — PR 3: the corpora

- [ ] 15.1 Extract both datasets; commit parquet, units, run metadata, updated provenance
  (`cluster_run` including `settling`), storage manifests, and a README per corpus (what it is,
  how it differs from the 2-beat corpus, where the raw runs live, how to regenerate).
- [ ] 15.2 Tests: all corpus guards on both new corpora; the measured healthy symmetry maximum is
  recorded and is below 0.012 (if not: stop, do not re-tune); live-spec-claim guards for every
  number the spec or READMEs quote.
- [ ] 15.3 Add a "superseded by" note to both 2-beat corpus READMEs (text only; their data and
  tests are untouched).
- [ ] 15.4 File the downstream issues from `design.md` D10 that do not exist yet, and the
  resume-on-retry follow-up if C2 passed. Tick #197.
- [ ] 15.5 Reconcile `proposal.md`, `design.md` and the specs with what was built. `/review-pr`,
  re-review of fix commits, `/pre-merge-check`. **HUMAN GATE before pushing.**
- [ ] 15.6 After merge: archive the change with the openspec CLI.
