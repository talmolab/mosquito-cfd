# Tasks

> **PR 1 of 2 — archive this change only after PR 2 merges.**

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
  without committing, and group 8, which commits in 8.4; task 11.5 is a separate archive commit. Commits use a conventional prefix and the `Co-Authored-By` trailer. The suite
  is green locally after each; CI sees only the PR head.

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

- [ ] 7a.1 **Test first** (CPU): the summary-figure scenario.
- [ ] 7a.2 Implement `surrogate_bench/figure.py`. Shipped-artifact check. Commit:
  `feat(surrogate-bench): summary figure`.

### 7b. Runner

- [ ] 7b.1 **Tests first** (`tests/test_surrogate_bench_runner.py`; `fit_seed` and `predict_frame`
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
- [ ] 7b.2 Implement `surrogate_bench/runner.py`. Mutation-test: `mlp_h1`/interpolation not run
  first; a filtered frame passed instead of the full one; a multi-beat frame passed; the memory peak
  not reset; the base not subtracted. Shipped-artifact check. Commit:
  `feat(surrogate-bench): runner and artifacts`.

### 7c. Driver

- [ ] 7c.1 **Tests first** (`tests/test_surrogate_bench_cli.py`):
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
- [ ] 7c.2 Implement `scripts/run_surrogate_bench.py`. Mutation-test each refusal and the
  refuse-before-write ordering. Shipped-artifact check. Commit: `feat(surrogate-bench): driver script`.

### 7d. GPU end-to-end

- [ ] 7d.1 **Test first** (GPU tier): a synthetic 27-configuration 3 × 3 × 3 frame labelled 21 + 6,
  with a coarse twin, run through the driver with `--epochs 5 --device cuda --allow-dirty`, a
  `sha256:` digest and a fixed `--timestamp`. Assert that:
  - the `mlp_*` entries run 5 seeds per split end to end;
  - `peak_gpu_mem > 0` for every MLP row;
  - the MLP `n_params` matches the PhysicsNeMo model's trainable parameter count.
- [ ] 7d.2 Make it pass under WSL2 (no new production code expected; any fix is recorded), then
  confirm `git status --porcelain` is empty.
  Shipped-artifact check. Commit: `test(surrogate-bench): GPU end-to-end`.

### 8. Rebase, documentation and reconciliation for PR 1

- [ ] 8.1 Once PR #171 has merged, rebase on `origin/main` (or merge it in; the PR is squash-merged
  either way). Confirm `git status --porcelain` is empty. The docs below are written after this step,
  so `docs/CHANGELOG.md` and `openspec/project.md`, which `main` has changed, cannot conflict.
- [ ] 8.2 Write the PR 1 docs:
  - `openspec/project.md`:
    - the package tree;
    - a short bench subsection describing the code: the entries, the driver flags (noting that
      `--allow-dirty` is bench-specific) and the dependency groups (`train` under WSL2 on Windows
      for MLP entries, `viz` for the figure);
    - the `mlp_h1` regression's host and library preconditions, marked "test lands in PR 2";
    - it does not describe `bench/`, `surrogate_h3/` or `figures_h3/` as committed.
  - `docs/CHANGELOG.md`: an entry for the code only, at the top of the file.
- [ ] 8.3 Reconcile proposal, spec and tasks against the implementation (new-feature step 9). Record
  any deviation in a "Why N instead of M?" section.
- [ ] 8.4 Commit 8.2 and 8.3: `docs: surrogate bench in project.md and changelog`. Then run, in
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

## PR 2 — results (branch `add-surrogate-comparison-bench-results`)

### 9. Runs (with the user's go-ahead; before any commit on the branch; no commit)

- [ ] 9.1 Set up the branch and check the host:
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
  directory outside the repository (`--device cuda`, the fine corpus's digest). Check that the
  `mlp_h1` / `interpolation` per-seed skills equal the shipped `metrics.json` exactly. If they do not,
  halt (Risk 1).
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
    - it locates the outputs by `SURROGATE_BENCH_DIR`, defaulting to `examples/prelim_sweep_fine/bench/`.
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
  If any exceeds 1, halt for a decision; do not loosen.
- [ ] 10.3 Copy `bench/`, `surrogate_h3/` and `figures_h3/` in; tests green. Shipped-artifact check.
  Commit: `feat(force-surrogate): committed bench results and phase-harmonics surrogate`.

### 11. Documentation for PR 2

- [ ] 11.1 **Tests first** (red): the README-equals-`summary.json` test and the spec's "The README
  quotes the scope" scenario.
- [ ] 11.2 `examples/prelim_sweep_fine/README.md`:
  - the shipped-model sentence the `h3` requirement specifies;
  - the `surrogate/` row and the sentence saying the surrogate was retrained "with no functional
    change" updated: the trainer now has `--phase-harmonics`, defaulting to the shipped behaviour;
  - rows for `surrogate_h3/`, `figures_h3/` and `bench/`;
  - the `bench/` row notes:
    - the `mlp_h1` regression compares host, driver, `torch` and `physicsnemo` only;
    - the numpy version and `CUBLAS_WORKSPACE_CONFIG` are unrecorded for the shipped run and for
      `surrogate_h3/`;
  - a bench section:
    - what each split tests;
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
      - its entry list gains `ridge_fixed`; its splits gain grid-face extrapolation and the
        random-18 and E4 controls;
      - both PR links;
      - a pointer to the fine README's bench section;
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
    shipped one; values live in the fine README", with both PR links.
  - `docs/CHANGELOG.md` entry for the committed artifacts.
  - No bench results in the roadmaps or the changelog.
- [ ] 11.4 Before merging:
  - the pre-merge diff of design D0 is empty, or the user's re-run decision is recorded;
  - reconcile;
  - `openspec validate --strict`;
  - the full suite;
  - the shipped-artifact check.

  In the same commit, replace the "PR 1 of 2" banner in `proposal.md` and `tasks.md` with "PR 2
  merged: archive this change".

  Commit: `docs: bench results, h3 surrogate and roadmap rows`. Run `/pre-merge-check`. PR 2 is opened
  only with the user's go-ahead.
- [ ] 11.5 After PR 2 merges: archive the change in a separate `chore(openspec): archive` commit.
