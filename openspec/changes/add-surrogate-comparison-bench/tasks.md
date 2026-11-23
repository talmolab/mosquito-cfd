# Tasks

> **Delivered as PR 1 (#188, merged `e1e6105`), PR 1b (larger-MLP entries, #195) and PR 2
> (results). Archive this change only after PR 2 merges.**

**Rules for every task:**

- **TDD.** Every implementation task names the test written **first**, run red, then made green.
- **Mutation testing.** New guards are mutation-tested on saved-bytes copies with
  `PYTHONDONTWRITEBYTECODE=1`, never alongside another test run, and never restored with
  `git checkout`. The kill table goes in the PR body.
- **CPU suite.** It mirrors CI: `uv run --frozen --group viz pytest -m "not gpu"`. Once per PR, also
  run it under WSL2 with the `train` group installed.
- **GPU tier.** The `train` group is Linux-only, so GPU tests run under WSL2 on the A5000 host.
  - Follow the fine README's recipe: `export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/mosquito-cfd-train"`
    (so the Windows `.venv` is left alone), then `uv run --frozen --group train pytest -m gpu`.
  - Paste the output in the PR body; it must show the new GPU tests as passed, not skipped, because
    CI never runs them.
  - GPU test files import `torch` only inside test bodies.
- **Lint.** Run `ruff check` and `ruff format --check` on `src/`, `tests/`, `scripts/` and
  `examples/prelim_sweep*/`, as CI does.
- **Git hygiene.** Check `git branch --show-current` before every git operation (parallel
  worktrees). Stage explicit paths, never a directory or `-A`.
- No pushing, merging, RunAI, cluster or CFD jobs without the user's go-ahead.
- Anything that looks like a bug outside this change becomes an issue draft for the user, not a fix.
- **Shipped-artifact check** (design D6), at the end of every group that commits.
- **Commits.** Each lettered or numbered group below is one commit, except group 9, which runs
  without committing; group 8, which commits in 8.4; and group 8b, which commits in 8b.0, 8b.2 and
  8b.4. Task 11.5 is a separate archive commit. Tests written first (red) are committed with the
  implementation that makes them green, never alone. Commits use a conventional prefix and the
  `Co-Authored-By` trailer. The suite is green locally after each; CI sees only the PR head.

**Prerequisite:** PR #171 (roadmap revision) merges before PR 1 opens (task 8.1). Groups 0–7 may start earlier.

## PR 1 — code (branch `add-surrogate-comparison-bench`)

### 0. Proposal

- [x] 0.1 Consolidate the review rounds into one `review-reconciliation.md`, then remove the
  per-round files:
  - for every round, the review and its reconciliation, concatenated verbatim, so no finding text or
    ID is lost;
  - include every round, the last one too; 0.2 waits until the last round's reconciliation is
    written.
- [x] 0.2 Before committing:
  - rebase the branch on `origin/main`, which is cheap while only the untracked proposal exists;
  - after the rebase, `git status --porcelain` is empty; if line-ending normalisation shows files,
    halt for a decision (for example a separate `git add --renormalize` commit).

  Then commit `proposal.md`, `design.md`, `tasks.md`, `specs/` and `review-reconciliation.md` with
  `docs(openspec): propose add-surrogate-comparison-bench`.

### 1a. Phase-harmonic features

- [x] 1a.1 **Tests first** (`tests/test_force_surrogate_phase_harmonics.py`): one per clause of the
  input-construction scenarios. That includes the exception type per input and `np.int64(3)`.
- [x] 1a.2 Implement `build_features(df, phase_harmonics=1)` and `phase_harmonics_from_features`.
  Mutation-test: `bool` accepted; harmonic column order swapped.
- [x] 1a.3 Shipped-artifact check. Commit:
  `feat(force-surrogate): optional phase harmonics in build_features`.

### 1b. Trainer and CLI plumbing

- [x] 1b.1 **Tests first** (extend `tests/test_force_surrogate_seed_sweep.py` and
  `tests/test_force_surrogate_train_driver.py`):
  - Update the existing `fake_fit` recorders to accept `phase_harmonics`.
  - `run_training(..., phase_harmonics=3)` passes 3 to every seed.
  - The default call passes `phase_harmonics=1`, and its other recorded kwargs equal literals
    captured at `e600581`.
  - Check the `metrics.json` key paths, `seed_sweep` included:
    - reuse the existing `_install_recorder` helper, which also patches `_measure_inference`;
    - spy on `build_metrics`, keeping the returned dict object;
    - patch `build_training_metadata` to raise a sentinel, so the run stops before `import torch`;
    - assert `pytest.raises(Sentinel)`;
    - the full recursive key paths equal a literal captured at `e600581`.
  - `phase_harmonics` 0, `True` or 2.5, with a valid digest and a nonexistent dataset path, raises
    `ValueError`/`TypeError` with a `match=` on the message (not `FileNotFoundError`), and leaves the
    output directory absent.
  - `scripts/train_surrogate.py` parses `--phase-harmonics 3` and defaults to 1.
- [x] 1b.2 Implement the plumbing in `run_training`, `_fit_one_seed` and the CLI. Mutation-test:
  validation moved after the dataset read; the default not passed explicitly.
- [x] 1b.3 Shipped-artifact check. Commit:
  `feat(force-surrogate): thread phase_harmonics through run_training and the CLI`.

### 1c. Per-seed seams

- [x] 1c.1 **Tests first, CPU.** Setup: `build_model`, `train_model` and `predict` replaced by
  recorders (`predict` returns zeros of the right shape); the committed fine dataset after
  `filter_converged_beat`. One test per clause of the spec's seam scenario. Each compares the full
  recorded call: positional arrays by dtype and `.tobytes()`, plus every keyword argument.
  - The invalid-split clause runs in a subprocess with a `sys.meta_path` hook that raises on any
    `torch` import.
  - The face split is built by hand in the test (`surrogate_bench.splits` arrives in 3b).
  - Add a one-line test that the new names are exported from `mosquito_cfd.force_surrogate`.
- [x] 1c.2 **Tests first, CPU**: the `predict_frame` CPU scenario.
- [x] 1c.3 **Tests first, GPU tier** (`tests/test_force_surrogate_train_gpu.py`): the `n_in = 9`
  forward pass, the `predict_frame` GPU scenario, and "The bench path trains like run_training".
- [x] 1c.4 Implement `fit_seed` and `predict_frame`; update the `build_model` docstring; add the
  exports. Mutation-test each clause of the split validation, and the zero-call path.
- [x] 1c.5 Run 1c.3 under WSL2, then confirm `git status --porcelain` is empty. Shipped-artifact check. Commit:
  `feat(force-surrogate): fit_seed and predict_frame seams`.

### 2. Explicit baseline reference

- [x] 2.1 **Tests first** (`tests/test_force_surrogate_phase_baseline.py`): the explicit-list and
  explicit-interpolation scenarios, including unsorted, duplicated, empty and unknown lists.
- [x] 2.2 Implement. Mutation-test: each guard; an explicit list still ANDed with
  `split == "train"`; the list not sorted.
- [x] 2.3 Shipped-artifact check. Commit:
  `feat(force-surrogate): explicit phase-baseline reference configs`.

### 3a. Shared validation carve

- [x] 3a.1 **Test first**: a carve helper over an arbitrary training list returns
  `make_config_splits`'s validation lists for `pool` (seeds 1234–1238), and a literal list
  for one face split. The helper sorts its input. The existing `make_config_splits` tests still pass.
- [x] 3a.2 Extract the helper in `train.py`. Shipped-artifact check. Commit:
  `refactor(force-surrogate): share the validation carve`.

### 3b. Bench package and splits

- [x] 3b.1 **Tests first**: the import scenario (meta-path blocker) and "The scope names all three
  limits". Mutation: a top-level `import torch` is killed.
- [x] 3b.2 **Tests first** (`tests/test_surrogate_bench_splits.py`): the split scenarios, without
  the E4 rank clause (that is in 4a.1).
- [x] 3b.3 Implement `surrogate_bench/__init__.py` (with `BENCH_SEEDS` and `BENCH_SCOPE`) and
  `surrogate_bench/splits.py`. Mutation-test: the disjointness, face-membership, 3-level and pool
  guards.
- [x] 3b.4 Shipped-artifact check. Commit: `feat(surrogate-bench): package skeleton and splits`.

### 4a. Ridge fit

- [x] 4a.1 **Tests first** (`tests/test_surrogate_bench_ridge.py`):
  - the fit scenarios:
    - cap;
    - both known answers (the realistic one predicts at the corpus's non-uniform phases, so it also
      kills the own-phase mutant);
    - standardisation over configurations;
    - intercept;
    - equal weight;
    - ill-conditioning via `solve_ridge`;
    - malformed input;
    - the 2-configuration clause of "Degenerate folds";
  - the E4 split's "17 columns, rank 16" clause;
  - the "never a checkpoint" static check over `ridge.py`, which also finds no `scipy` or `sklearn`
    import;
  - `ridge_fixed` fits exactly `(16, 3, 1e-6)` with `null` selection fields;
  - the rank and singular-value record of the fitted matrix, including `ridge_fixed`'s rank 16 on
    `control:e4_seed0`;
  - Fourier projection exact for a band-limited signal;
  - `n_params = 6·(2H+1)·P`.
- [x] 4a.2 Implement `solve_ridge`, the fit, the rank record and `ridge_fixed` in
  `surrogate_bench/ridge.py`. Mutation-test; each must be killed:
  - penalised intercept;
  - uncapped basis;
  - normal-equations solve;
  - row weighting;
  - kinematics standardised over rows;
  - `λ = α` instead of `α · n`;
  - interpolated instead of own-phase test evaluation;
  - `ridge_fixed` routed through selection.
- [x] 4a.3 Shipped-artifact check. Commit: `feat(surrogate-bench): Fourier x polynomial ridge fit`.

### 4b. Ridge selection and diagnostics

- [x] 4b.1 **Tests first**:
  - the selection scenarios: fold errors (including the relative fragile and non-fragile cases and
    `threshold = 0`); the one-SE rule with its tie-breaks; CV blind to test rows; ranks and fold
    ranks;
  - folds re-standardise and recompute `L_v`, including the other two "Degenerate folds" clauses (a
    setting with one value in a fold; a 0/0 fold error raises);
  - the runner-up gap and the largest fold share are recorded;
  - `SelectionNotRecheckedWarning` and `recheck_split`:
    - a synthetic summary with `selection_fragile: true` refits at the committed point under
      `pytest.warns`;
    - on a non-fragile summary the discrete outputs must match exactly, and a mismatch raises.
- [x] 4b.2 Implement selection and `recheck_split`. Mutation-test; each must be killed:
  - CV including test configurations;
  - SST about the global mean instead of the configuration mean;
  - a mean of per-configuration ratios instead of `ΣSSE/ΣSST`;
  - `ddof = 0`;
  - `se` of the chosen candidate instead of `θ*`;
  - threshold without `se`;
  - margin relative to `score(θ*)` instead of `threshold`;
  - a NaN fold error skipped instead of raised;
  - a reordered tie-break;
  - the warning dropped.
- [x] 4b.3 Shipped-artifact check. Commit: `feat(surrogate-bench): ridge selection and diagnostics`.

### 5. Metrics

- [x] 5.1 **Tests first** (`tests/test_surrogate_bench_metrics.py`): the metric scenarios, plus:
  - `per_seed_skill` uses all of a seed's test rows in dataset order;
  - the target beat, and the baseline built from the target-beat frame;
  - the target-beat guards from "Late-beat boundary": missing beat 0, a partial last beat, and a
    configuration with fewer beats (this group owns the target-beat helper);
  - `peak_t` is taken over all 27 configurations, not the split's training configurations;
  - direct grid evaluation (its scenario);
  - holdout overlap per split and the face metrics without those configurations;
  - the like-for-like view: RMS metrics only, no skill key, and `null` with its reason for pitch 30;
  - the NaN-aware seed range;
  - timing and memory columns excluded from the equality helper.
- [x] 5.2 Implement `surrogate_bench/metrics.py`. Mutation-test; each must be killed:
  - baseline from `pool` instead of the split;
  - the seed-count check off by one;
  - a NaN-unaware range;
  - the two normalisers swapped;
  - grid evaluation by interpolation instead of directly.
- [x] 5.3 Shipped-artifact check. Commit: `feat(surrogate-bench): metrics`.

### 6a. Gate errors and yardsticks

- [x] 6a.1 **Tests first** (`tests/test_surrogate_bench_gate.py`): the gate scenarios for:
  - GCI traceability, grid peaks and rotation;
  - yardstick values;
  - the shared window, including the windowed-normaliser known answer;
  - the `late_beat` yardstick clauses of "Late-beat boundary", including the coarse corpus lacking
    the target beat (the guards are in 5.1);
  - the wrap jump (sawtooth known answer).
- [x] 6a.2 Implement errors and yardsticks in `surrogate_bench/gate.py`, with a comment citing #173
  at the grid-peak rule. Mutation-test; each must be killed:
  - stroke sign, stroke in degrees, a missing `/f*`, a missing pitch lead, `R` for `Rᵀ`;
  - raw-row instead of grid peaks;
  - the `beat1_vs_beat2` peak normaliser taken over the full grid;
  - the window mismatch;
  - `coarse_vs_fine` normalised by the coarse peak or by the configuration peak;
  - a ×100 scaling;
  - wrap-jump extrapolation from rows −2 and −1, extrapolation to `φ_0` instead of `1 + φ_0`, and raw
    swapped with last-but-one.
- [x] 6a.3 Shipped-artifact check. Commit: `feat(surrogate-bench): gate errors and yardsticks`.

### 6b. Gate verdicts

- [x] 6b.1 **Tests first**: the verdict scenarios. These cover the worst seed with NaN propagation,
  fractions, all boundary cases, `no_yardstick`/`not_applicable`, `late_beat` beside the other
  yardsticks, `holdout_informed` marks, the seven provisional reasons with the wrap-jump reason
  computed from the recorded jumps, and no overall key.
- [x] 6b.2 Implement the verdicts. Mutation-test; each must be killed:
  - the worst-seed reduction made NaN-aware;
  - the margin taken from the median seed;
  - NaN handling;
  - 0/0 handling;
  - the margin's minimum over configurations;
  - a hard-coded wrap-jump reason text.
- [x] 6b.3 Shipped-artifact check. Commit: `feat(surrogate-bench): gate verdicts`.

### 7a. Summary figure

- [x] 7a.1 **Test first** (CPU): the summary-figure scenario.
- [x] 7a.2 Implement `surrogate_bench/figure.py`. Shipped-artifact check. Commit:
  `feat(surrogate-bench): summary figure`.

### 7b. Runner

- [x] 7b.1 **Tests first** (`tests/test_surrogate_bench_runner.py`; `fit_seed` and `predict_frame`
  patched at their import site; git state and the memory probe injected through the runner's
  `git_state` and `memory_probe` arguments):
  - the hyperparameters reach `fit_seed`;
  - the interpolation `mlp_h1` call runs first and receives the full target-beat frame and the
    bench's carve lists;
  - MLP skill uses the fit's own `y_pred`; the runner calls `predict_frame` on the 256-phase grid
    and feeds `grid_sse` from it, and times inference around that call;
  - both ridge rows are present on every split;
  - a synthetic 4-beat dataset:
    - every MLP call and the baseline see only `wingbeat == 3`;
    - the gate receives the unfiltered frame;
    - the ridge input has no duplicate (configuration, phase);
  - output files and schemas;
  - `peak_gpu_mem`, through a fake memory probe on CPU:
    - the call order synchronize → reset → base → fit → synchronize → peak − base;
    - `null` for ridge rows and for `--device cpu`;
  - `scope == BENCH_SCOPE`, and the entries' holdout status;
  - each provenance field:
    - `docker_image` equals the supplied digest, and `timestamp` equals the supplied value
      verbatim;
    - dataset sha256;
    - commit, branch and dirty flag;
    - hardware;
    - seeds, device, entries and epochs;
    - `CUBLAS_WORKSPACE_CONFIG`, including `null` when unset (`monkeypatch.delenv`);
    - `library_versions` with `numpy`, and `torch`/`physicsnemo` keys present (`null` when not
      installed);
  - the summary recomputes from `results.parquet`;
  - no checkpoint file is written, and a static scan of the runner's ridge functions (`run_ridge_entries`)
    finds no checkpoint writer or loader.
- [x] 7b.2 Implement `surrogate_bench/runner.py`. Mutation-test: `mlp_h1`/interpolation not run
  first; a filtered frame passed instead of the full one; a multi-beat frame passed; the memory peak
  not reset; the base not subtracted. Shipped-artifact check. Commit:
  `feat(surrogate-bench): runner and artifacts`.

### 7c. Driver

- [x] 7c.1 **Tests first** (`tests/test_surrogate_bench_cli.py`):
  - every flag in the spec is wired;
  - each refusal in the spec (duplicate entries and a coarse dataset missing a configuration
    included) exits non-zero, leaving the output directory absent or its prior contents unchanged;
  - `--allow-dirty` records `dirty: true` (git state injected as in 7b);
  - CPU smoke run, with the meta-path blocker installed by a `-c` wrapper that then calls
    `runpy.run_path` on the driver:
    - `--entries ridge,ridge_fixed --device cpu` on the real fine and coarse datasets, with a fake
      digest, a fixed `--timestamp` and `--allow-dirty`, into a temporary directory;
    - it writes every file, including the figure;
    - the gate block covers the two ridge entries only.
- [x] 7c.2 Implement `scripts/run_surrogate_bench.py`. Mutation-test each refusal and the
  refuse-before-write ordering. Shipped-artifact check. Commit: `feat(surrogate-bench): driver script`.

### 7d. GPU end-to-end

- [x] 7d.1 **Test first** (GPU tier): a synthetic 27-configuration 3 × 3 × 3 frame labelled 21 + 6,
  with a coarse twin, run through the driver with `--epochs 5 --device cuda --allow-dirty`, a
  `sha256:` digest and a fixed `--timestamp`. Assert that:
  - the `mlp_*` entries run 5 seeds per split end to end;
  - `peak_gpu_mem > 0` for every MLP row;
  - the MLP `n_params` matches the PhysicsNeMo model's trainable parameter count.
- [x] 7d.2 Make it pass under WSL2 (no new production code expected; any fix is recorded), then
  confirm `git status --porcelain` is empty.
  Shipped-artifact check. Commit: `test(surrogate-bench): GPU end-to-end`.

### 8. Rebase, documentation and reconciliation for PR 1

- [x] 8.1 Once PR #171 has merged, rebase on `origin/main` (or merge it in; the PR is squash-merged
  either way). Confirm `git status --porcelain` is empty. The docs below are written after this step,
  so `docs/CHANGELOG.md` and `openspec/project.md`, which `main` has changed, cannot conflict.
- [x] 8.2 Write the PR 1 docs:
  - `openspec/project.md`:
    - the package tree;
    - a short bench subsection describing the code: the entries, the driver flags (noting that
      `--allow-dirty` is bench-specific) and the dependency groups (`train` under WSL2 on Windows
      for MLP entries, `viz` for the figure);
    - the `mlp_h1` regression's host and library preconditions, marked "test lands in PR 2";
    - it does not describe `bench/`, `surrogate_h3/` or `figures_h3/` as committed.
  - `docs/CHANGELOG.md`: an entry for the code only, at the top of the file.
- [x] 8.3 Reconcile proposal, spec and tasks against the implementation (new-feature step 9). Record
  any deviation in a "Why N instead of M?" section.
- [x] 8.4 (PR #188, merged `e1e6105`; ticked in PR 1b, the first branch after the merge.) Commit
  8.2 and 8.3: `docs: surrogate bench in project.md and changelog`. Then run, in
  order:
  1. `openspec validate add-surrogate-comparison-bench --strict`;
  2. the full local suite, natively and under WSL2, then `git status --porcelain` is empty;
  3. ruff;
  4. the shipped-artifact check.

  The commits replayed by the rebase are not individually re-tested.

  Run `/pre-merge-check`, which re-runs the checks just before merge. PR 1 is opened only with the
  user's go-ahead, with a conventional title ("Add the surrogate comparison bench (F3a), PR 1 of 2").
  Its description, and the session handoff memory, state:
  **"PR 1 of 2: do not archive the OpenSpec change until PR 2 merges."**

## PR 1b — larger-MLP entries (#195; branch `add-bench-larger-mlp-entries`)

Opened after PR 1 merged, merged before PR 2's runs (group 9). The rules at the top apply. The
change is not archived after this PR. Each task's box is ticked in the commit that completes it;
8b.0's and 8b.5's are ticked in the 8b.4 commit.

### 8b. Larger-MLP entries and per-entry hyperparameters in the metadata

- [ ] 8b.0 Append review round 7 and its reconciliation to `review-reconciliation.md`. Run
  `openspec validate add-surrogate-comparison-bench --strict`. Commit the amendment (`proposal.md`,
  `design.md`, `tasks.md` with 8.4 ticked, the bench spec delta, `review-reconciliation.md`):
  `docs(openspec): amend add-surrogate-comparison-bench with larger-MLP entries (#195)`.
- [ ] 8b.1 **Tests first** (red). No commit of its own: they are committed with 8b.2.
  - Test helpers in `tests/test_surrogate_bench_runner.py`. The recorder never learns entry names.
    - Calls are assigned to entries by position: they arrive in run order, 14 splits × 5 seeds per
      MLP entry, so call `k` belongs to the `k // 70`-th chosen MLP entry.
    - A `SizedRecorder` whose prediction offset also depends on `hidden` and `num_layers`, and whose
      fake model's parameter count depends on them, so every entry's rows and `n_params` differ.
  - New tests, one per clause of the spec scenarios:
    - "The larger MLP entries change only width and depth": 5 calls per split and entry; the
      `(hidden, num_layers, phase_harmonics)` tuple per entry, by position; `lr == 1e-3` (the
      literal) and the run's epochs on every call; with `SizedRecorder`, the rows labelled with each
      MLP entry carry that entry's offset and `n_params`; the `mlp_h1` and `mlp_h3` rows (every
      column except `fit_seconds`, `inference_seconds_per_row` and `peak_gpu_mem`) and their
      `per_seed_skill` equal those of an `entries=("mlp_h1", "mlp_h3")` run.
    - "Entries run in a fixed order and read the shipped defaults": for a fixed shuffle of all six,
      `summary["entries"] == meta["entries"] == list(dict.fromkeys(results["entry"]))` == the
      literal six names in run order; the first call is `(64, 3, 1)` on `interpolation` at the
      first seed.
    - "The metadata records each MLP entry's architecture": the full run, the `mlp_h1,ridge_fixed`
      run and the ridge-only run, each compared with what the recorder received by position; for
      the ridge-only run, `"mlp_hyperparameters" in meta and meta["mlp_hyperparameters"] == {}`.
    - The holdout reasons of the two larger entries contain `E4`, and `mlp_w256d5_h3`'s contains
      `harmonic`.
  - Existing tests in that file, changed by name:
    - `test_the_shipped_hyperparameters_reach_fit_seed`: `14 * 4 * 5` calls; `(64, 3)` for the
      shipped-size entries and `(256, 5)` for the larger ones, by position.
    - `test_mlp_h1_on_interpolation_runs_first_on_the_full_target_beat_frame`: also asserts the
      first call's `(hidden, num_layers) == (64, 3)`, since `mlp_w256d5` also has one harmonic.
    - `test_the_summary_per_seed_skill_is_the_fits_own_skill`: picks its fit by position, not by
      `phase_harmonics == 3`, and repeats the check for `mlp_w256d5_h3` with `SizedRecorder`.
    - `test_scope_holdout_status_and_gate`: the literal set of six entries, and five of them
      `holdout_informed: true`.
    - `test_results_schema`: `n_params` per entry, with the sized fake model.
  - `tests/test_surrogate_bench_import.py`: the recipe test pins `runner.MLP_ENTRIES` to a literal
    (`mlp_h1` 64, 3, 1e-3, 1; `mlp_h3` 64, 3, 1e-3, 3; `mlp_w256d5` 256, 5, 1e-3, 1;
    `mlp_w256d5_h3` 256, 5, 1e-3, 3); compares the `mlp_h1` and `mlp_h3` rows' `hidden`,
    `num_layers` and `lr`, and every `lr`, with `run_training`'s signature defaults; and asserts
    `set(MLP_ENTRIES) | {"ridge", "ridge_fixed"} == set(ENTRIES)`. That the table reads the
    trainer's named constants, not equal literals, is checked in review only.
  - `tests/test_surrogate_bench_cli.py`: the default `--entries` equals the literal six names in
    run order.
  - `tests/test_surrogate_bench_figure.py`: 6 entries and 14 splits, 6 legend labels. The figure
    code does not depend on the entry count, so this is a pin, green from the start.
  - `tests/test_surrogate_bench_gpu.py` (GPU tier, not run in CI but imported by it): rewritten
    against `runner.MLP_ENTRIES`; its import of the removed names fails until 8b.2. It asserts that:
    - each of the four `mlp_*` entries has 14 splits of 5 seeds;
    - `n_params` is 9094, 9350, 266246 and 267270 for `mlp_h1`, `mlp_h3`, `mlp_w256d5` and
      `mlp_w256d5_h3`, and equals the trainable parameters of the PhysicsNeMo model built at that
      entry's width, depth and feature count;
    - `mlp_hyperparameters` in the written metadata equals the table;
    - `peak_gpu_mem > 0` on every MLP row, the `mlp_w256d5` median on `interpolation` exceeds
      `mlp_h1`'s, and the first `mlp_w256d5` interpolation fit's peak is no larger than that
      entry's other interpolation fits (the warm-up check at the new layer shapes).
- [ ] 8b.2 Implement in `surrogate_bench/runner.py`: one `MLP_ENTRIES` table replacing
  `MLP_HARMONICS` and `MLP_HYPERPARAMETERS` (no alias kept); `ENTRIES`; `HOLDOUT_STATUS`;
  `mlp_hyperparameters` in the metadata, built from the same table for the entries that ran.
  Mutation-test, naming the test that kills each mutant in the kill table:
  - the table gives a larger entry the default `hidden`; the default `num_layers`; a different `lr`;
  - the harmonic counts of `mlp_w256d5` and `mlp_w256d5_h3` swapped in the table;
  - `run_mlp_entry` passes the default `hidden` (or `num_layers`) while the table and the metadata
    stay correct;
  - `run_bench` runs one larger entry's fits under the other's name;
  - a larger entry missing from the MLP dispatch, so it falls into the ridge branch;
  - the run order changed: a larger entry before `mlp_h1`; `mlp_w256d5` between `mlp_h1` and
    `mlp_h3`; the larger entries after `ridge`;
  - the metadata block written for every MLP entry, not only those that ran; `null` or absent for
    a ridge-only run; built from a second copy of the values that differs from the table;
  - a larger entry's holdout reason without `E4`; `mlp_w256d5_h3`'s without `harmonic`.

  Shipped-artifact check (design D6: the shipped `surrogate/` and `figures/` bytes are unchanged).
  Commit, with 8b.1's tests: `feat(surrogate-bench): larger-MLP entries (#195)`.
- [ ] 8b.3 **GPU tier.** Run `tests/test_surrogate_bench_gpu.py` under WSL2 on the A5000
  (`--epochs 5`, synthetic frame; a test, not a bench run). Paste the output in the PR body, with
  `fit_seconds` per entry. No commit unless a fix is needed, which is then recorded.
- [ ] 8b.4 Docs, then reconcile:
  - `openspec/project.md` bench subsection: six entries (the two new bullets say what the 2 × 2 is
    for and point to the spec for the definitions), and that `run_metadata.json` records
    `mlp_hyperparameters`;
  - `docs/CHANGELOG.md`: an entry labelled "F3a PR 1b";
  - the comment above the table in `runner.py`;
  - roadmap rows are PR 2's (11.3) and are not touched here;
  - reconcile proposal, spec and tasks against the implementation (new-feature step 9).

  Commit: `docs: larger-MLP bench entries in project.md and changelog`.
- [ ] 8b.5 Then, in order:
  1. `openspec validate add-surrogate-comparison-bench --strict`;
  2. the CPU suite natively (`uv run --frozen --group viz pytest -m "not gpu"`) and under WSL2
     with the `train` group, then `git status --porcelain` is empty;
  3. the GPU tier under WSL2 (8b.3);
  4. `ruff check` and `ruff format --check` on the paths CI uses;
  5. the shipped-artifact check;
  6. the mutation kill table is in the PR body.

  Run `/pre-merge-check`. The PR is opened only with the user's go-ahead, titled "Add larger-MLP
  entries to the surrogate comparison bench (F3a), PR 1b". Its description says "Advances #195"
  (never a closing keyword, which closes the issue even when negated; PR 2 closes it, once the
  2 × 2 has results) and, in bold, "do not archive the OpenSpec change until PR 2 merges". After
  the merge, `/cleanup-merged` deletes the branch and skips its archive step.

## PR 2 — results (branch `add-surrogate-comparison-bench-results`)

### 9. Runs (with the user's go-ahead; before any commit on the branch; no commit)

- [ ] 9.1 Set up the branch and check the host. Precondition: PR 1b is merged, so the runner at
  `M` has six entries; if not, halt.
  - `git fetch`; from the Windows main checkout, `git worktree add` a worktree on the new branch
    `add-surrogate-comparison-bench-results` at `origin/main` (commit `M`, recorded in the PR body);
    the h3 figure (9.3) is generated there;
  - for the WSL2 runs, use a WSL-native clone from GitHub (`origin`), never a worktree created from
    WSL, which would corrupt the Windows checkout's `.git/worktrees`. In it:
    - `git fetch` and check out `M` on the same named branch;
    - `git status --porcelain` is empty, since `--allow-dirty` would fail the clean-commit test;
    - record the clone path in the PR body;
  - `git rev-parse HEAD` is `M` in both trees, and both are clean;
  - under WSL2, confirm that the host, driver, `torch` and `physicsnemo` match the shipped
    `surrogate/run_metadata.json`;
  - check the A5000 is idle.
- [ ] 9.2 Run the full bench under WSL2 (README "Regenerating" step 1 environment) into a scratch
  directory outside the repository (`--device cuda`, the fine corpus's digest; all six entries,
  280 MLP fits = 14 splits × 4 entries × 5 seeds, about 90 min). Check that:
  - the `mlp_h1` / `interpolation` per-seed skills equal the shipped `metrics.json` exactly. If
    they do not, halt (Risk 1);
  - the `mlp_w256d5` / `interpolation` per-seed mean skill over targets matches E4's
    `width256_depth5` arm (design D8's table) to within 1e-3, since it repeats E4's data, seeds
    and carve. If it does not, investigate before reporting the 2 × 2.
- [ ] 9.3 Run the h3 trainings and the gate:
  - check the A5000 is idle;
  - train `surrogate_h3/` twice under WSL2 (runs A and B) into scratch directories, with no fetch,
    pull or rebase in between;
  - apply the twice-run gate with a small comparison script, including that A and B record the same
    `M`, and put the script's source in the PR body;
  - generate the h3 evidence figure from run A natively on Windows with the `viz` group, as for the
    shipped figure, into a scratch `figures_h3/`.

### 10. Commit the results

- [ ] 10.1 **Tests first** (red, files absent):
  - `tests/test_committed_surrogate_h3_provenance.py`:
    - features from JSON on CPU, `.pt` on GPU;
    - dataset reconciliation;
    - seeds, epochs and the validation carve;
    - `phase_baseline_skill` recompute;
    - `seed_sweep` consistency;
    - every `config_name` in the predictions is a holdout;
    - the figure's hashes and `grid == "fine"`.
  - `tests/test_surrogate_bench_committed.py`:
    - the consistency, regression and fast-recompute scenarios;
    - the bench dataset sha256 and digest equal the corpus's;
    - it locates the outputs by `SURROGATE_BENCH_DIR`, defaulting to `examples/prelim_sweep_fine/bench/`;
    - the committed `run_metadata.json` has `entries` equal to the six names in run order and
      `mlp_hyperparameters` equal to `runner.MLP_ENTRIES`.
  - Negative tests in the `test_guards_reject_each_defect` style:
    - a 1-ulp skill change;
    - a different `hardware.driver_version` (an `mlp_h1` regression precondition);
    - a changed `H`;
    - a committed `selection_fragile: true` on a split whose recomputed margin exceeds `1e-6`;
    - an `sse` or score perturbed by about 1e-6 relative;
    - a summary value perturbed by about 1e-10 relative;
    - a dropped σ above the rank tolerance;
    - an edited split list.
  - The bench, `surrogate_h3/` and `figures_h3/` `run_metadata.json` files added to the clean-commit
    parametrisation in
    `tests/test_committed_surrogate_provenance.py`.
- [ ] 10.2 Before 10.3, run the recompute test against the scratch outputs natively on Windows and
  under WSL2. Record, for each check, the largest `|Δ| / (atol + rtol·|ref|)` under the spec's rule.
  If any exceeds 1, halt for a decision; do not loosen. Record the recompute's duration against
  the spec's 120 s limit; the larger entries double the MLP rows.
- [ ] 10.3 Copy `bench/`, `surrogate_h3/` and `figures_h3/` in; tests green. Shipped-artifact check.
  Commit: `feat(force-surrogate): committed bench results and phase-harmonics surrogate`.

### 11. Documentation for PR 2

- [ ] 11.1 **Tests first** (red): the README-equals-`summary.json` test, which also covers every
  number in the README's 2 × 2 paragraph (against `seed_ranges` and `per_seed_skill`), and the
  spec's "The README quotes the scope" scenario.
- [ ] 11.2 `examples/prelim_sweep_fine/README.md`:
  - the shipped-model sentence the `h3` requirement specifies;
  - the `surrogate/` row and the sentence saying the surrogate was retrained "with no functional
    change" updated: the trainer now has `--phase-harmonics`, defaulting to the shipped behaviour;
  - rows for `surrogate_h3/`, `figures_h3/` and `bench/`;
  - the `bench/` row notes:
    - `run_metadata.json`'s `mlp_hyperparameters` records `hidden`, `num_layers`, `lr` and
      `phase_harmonics` for each MLP entry;
    - the `mlp_h1` regression compares host, driver, `torch` and `physicsnemo` only;
    - the numpy version and `CUBLAS_WORKSPACE_CONFIG` are unrecorded for the shipped run and for
      `surrogate_h3/`;
  - a bench section:
    - what each split tests;
    - the size-by-harmonics 2 × 2 (`mlp_h1`, `mlp_h3`, `mlp_w256d5`, `mlp_w256d5_h3`), written
      under design D8's limits (#195):
      - seed ranges, and the 5 paired per-seed differences for any "beats" statement;
      - the comparison read from the face metrics without holdouts, since both the larger size and
        the three harmonics were selected on the holdouts;
      - a drop from `interpolation` to a face compared on `rmse_frac_component_peak`, not skill;
      - the larger entries use the shipped learning rate untuned, and the 2 × 2 does not separate
        width from depth;
    - the holdout overlap;
    - the results table, generated from `summary.json`;
    - the provisional gate;
    - `BENCH_SCOPE` quoted verbatim;
    - a link to #173;
  - the h3 twice-run result;
  - new recipes for the bench and the h3 model:
    - under WSL2, with the `mlp_h1`-first and host preconditions;
    - cross-referencing the existing "Regenerating" steps rather than repeating them.

  Also update the `openspec/project.md` bench subsection: drop the "test lands in PR 2" marker and
  point to `bench/`, `surrogate_h3/` and `figures_h3/`. Tests green.
- [ ] 11.3 Roadmaps and changelog (re-read the merged roadmap first, since #171 may have changed):
  - `docs/field_surrogate/roadmap.md`:
    - row F3a → ✅:
      - "provisional per-component, per-yardstick gate; no overall verdict";
      - its entry list gains `ridge_fixed`, `mlp_w256d5` and `mlp_w256d5_h3`; its splits gain grid-face extrapolation and the
        random-18 and E4 controls;
      - all three PR links;
      - a pointer to the fine README's bench section;
    - Revision item 3's entry list gains `ridge_fixed` and the two larger MLPs;
    - Revision item 3 and open question 4 keep their exploration numbers as history (E1, E0, E0b and
      E4). Only the forward-looking "re-measured by F3a" and "retested by F3a" phrases become
      pointers to that section. The open-question pointer says F3a records stand-in yardsticks; the
      corpus's own CFD uncertainty is still to be measured after regeneration;
    - item 2's second sentence ("so a drop at a face is not mistaken for a drop from less data")
      becomes "reported beside random 18-configuration controls scored on the holdouts, and a
      like-for-like view; see the fine README bench section for what that does and does not
      separate";
    - item 2's E4 sentence reads "at the exploration's fixed hyperparameters the ridge fell to 0.41
      on one of five random 18-config subsets; F3a separates the subset effect from the
      hyperparameter effect (`ridge_fixed` vs the re-selected ridge)";
    - the "What no result here may claim" paragraph points to `BENCH_SCOPE` in the fine README and
      keeps its closing sentence on commanded changes.
  - `docs/force_surrogate/roadmap.md`, the next free row (17 on today's `main`):
    `add-surrogate-comparison-bench`, "comparison bench (interpolation, grid-face extrapolation,
    random and E4 controls), a ridge reference and an optional phase-harmonics surrogate beside the
    shipped one; values live in the fine README", with all three PR links.
  - `docs/CHANGELOG.md` entry for the committed artifacts.
  - No bench results in the roadmaps or the changelog.
- [ ] 11.4 Before merging:
  - the pre-merge diff of design D0 is empty, or the user's re-run decision is recorded;
  - reconcile;
  - `openspec validate --strict`;
  - the full suite;
  - the shipped-artifact check.

  In the same commit, replace the delivery banner at the top of `proposal.md` and `tasks.md` with
  "PR 2 merged: archive this change".

  Commit: `docs: bench results, h3 surrogate and roadmap rows`. Run `/pre-merge-check`. PR 2 is opened
  only with the user's go-ahead. Its description says "Closes #195".
- [ ] 11.5 After PR 2 merges: archive the change in a separate `chore(openspec): archive` commit.
