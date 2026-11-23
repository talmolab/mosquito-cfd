# Add a surrogate comparison bench (F3a)

> **Delivered as PR 1 (#188, merged `e1e6105`), PR 1b (larger-MLP entries, #195) and PR 2
> (results). Archive this change only after PR 2 merges.**

## Why

F3's goal is now a fair comparison of surrogate families that records where each one breaks
(`docs/field_surrogate/roadmap.md`, "Revision (2026-11-18)", PR #171, a prerequisite). Nothing on
`main` can run that comparison: models can only be scored on the 6 labelled holdouts, the inputs are
fixed at one phase harmonic, there is no non-neural reference model, and the hover gate has no measured
yardstick for this corpus.

## What Changes

- **New package `mosquito_cfd.surrogate_bench`** (torch-free except the MLP entry) and driver
  `scripts/run_surrogate_bench.py`:
  - 14 splits of the fine force corpus: interpolation (the 6 labelled holdouts); 6 grid-face
    extrapolation splits (one face held out, 18 configurations trained); 6 random 18-configuration
    controls scored on the labelled holdouts, to help tell a drop at a face apart from having less
    data (test difficulty still differs; design D2); and the exploration's E4 subset, on which
    its ridge collapsed.
  - Entries: `mlp_h1` (the shipped recipe) and `mlp_h3` (3 phase harmonics), each over seeds
    1234–1238; `mlp_w256d5` and `mlp_w256d5_h3`, the same two at width 256 and depth 5 (#195, the
    amendment below); and a `ridge` reference rebuilt from first principles (design D3). The ridge uses
    per-configuration Fourier coefficients, a polynomial basis capped at what each setting's distinct
    values can identify, an unpenalised intercept and a least-squares solve. `(H, d, α)` is chosen by
    leave-one-configuration-out CV inside each split, on the grid fixed in design D3, by the
    one-standard-error rule. Ranks and fold ranks are recorded. A `ridge_fixed` entry at the
    exploration's chosen point separates the effect of re-selection from that of the corrected
    construction.
  - Metrics:
    - #127 skill against a baseline built from each split's own training configurations;
    - RMS error on a 256-phase grid as a fraction of the configuration's peak and of the
      component's corpus-wide peak, with the phase-only baseline's value beside it;
    - the wrap jump of each configuration's beat, which a periodic model cannot fit;
    - the stored sums needed to recompute every pooled value;
    - fit and inference time, peak GPU memory (`peak_gpu_mem`), and parameter count.
  - Seed spread is reported as min/max ranges.
  - Every entry trains and is scored on one target beat, the last beat common to every
    configuration; on the 2-beat corpus that is the beat the shipped trainer uses (design D4).
  - A **provisional** per-component hover gate on the interpolation split, against each available
    yardstick separately: T3c GCI for the two body-frame peaks (taken on the phase grid),
    coarse-vs-fine (an upper bound, also reported scaled), and beat 1 vs beat 2. A `late_beat`
    yardstick switches on automatically when the corpus has ≥ 4 beats. There is no overall pass/fail,
    and components without a yardstick never pass.
- **`force-surrogate` (MODIFIED):**
  - `build_features(df, phase_harmonics=1)`; the trainer and CLI gain `--phase-harmonics`. At the
    default every input, name, checkpoint and `metrics.json` key is bitwise unchanged.
  - Public seams `fit_seed` (one seed on a caller-supplied split) and `predict_frame`, plus
    `phase_harmonics_from_features`.
  - `build_phase_only_baseline(..., reference_configs=None)`; unchanged without the argument.
  - The "no second model" rule gains an explicit carve-out for bench-only references.
  - The committed-artifact requirements name `surrogate_h3/` and `figures_h3/` as further locations.
    The fine reproducibility-gate requirement is reworded so it stays true once the trainer gains
    these options.
- **`force-surrogate` (ADDED):** a committed `phase_harmonics = 3` surrogate and evidence figure
  beside the shipped one (`surrogate_h3/`, `figures_h3/`), under the same twice-run gate. **Every
  shipped artifact stays byte-unchanged.**
- **BREAKING:** none.

Delivered in three PRs (design D0): code, then the larger-MLP entries (#195), then the results
produced from `main`.

Not in this change: field models (F3b), DoMINO (F3c), commanded-change configurations, a change of the
shipped default, the coarse corpus as a bench target, the regenerated corpus.

## Impact

- Affected specs: `force-surrogate` (6 MODIFIED, 1 ADDED), new `surrogate-comparison-bench`.
- Affected code:
  - `src/mosquito_cfd/force_surrogate/train.py`: `build_features`, `_fit_one_seed`, `run_training`
    and `build_phase_only_baseline`; the validation carve inside `make_config_splits`, extracted into
    the shared helper `carve_validation`; new `fit_seed`, `predict_frame` and `phase_harmonics_from_features`; the
    `build_model` docstring.
  - `src/mosquito_cfd/force_surrogate/__init__.py`: exports.
  - `scripts/train_surrogate.py`.
  - New `src/mosquito_cfd/surrogate_bench/` and `scripts/run_surrogate_bench.py`.
- Tests:
  - new `tests/test_force_surrogate_phase_harmonics.py`, `tests/test_surrogate_bench_*.py` and
    `tests/test_committed_surrogate_h3_provenance.py`;
  - extended `tests/test_force_surrogate_seed_sweep.py` (recorder),
    `tests/test_committed_surrogate_provenance.py` (clean-commit list),
    `tests/test_force_surrogate_phase_baseline.py`, `tests/test_force_surrogate_train_driver.py` and
    `tests/test_force_surrogate_train_gpu.py`.
- Docs:
  - `examples/prelim_sweep_fine/README.md` (bench section, `surrogate_h3/`, `figures_h3/` and
    `bench/` rows, regeneration recipes);
  - `openspec/project.md` (package tree and a bench subsection in PR 1; the subsection updated in PR 2);
  - `docs/CHANGELOG.md` (code in PR 1, artifacts in PR 2);
  - `docs/field_surrogate/roadmap.md` row F3a and `docs/force_surrogate/roadmap.md` (next free row; 17 on `c87e39c`), both in
    PR 2.
- New committed artifacts (PR 2): `examples/prelim_sweep_fine/surrogate_h3/`,
  `examples/prelim_sweep_fine/figures_h3/` and `examples/prelim_sweep_fine/bench/`.
- Compute:
  - 280 MLP fits (14 splits × 4 entries × 5 seeds) under WSL2 on the local A5000, plus two full h3
    trainings. The shipped-size entries take about 9 s a fit (about 21 min for their 140). In E4,
    width 256 at depth 5 took about 29 s a fit (28.6–29.5 s, 2000 epochs, CUDA), so the larger
    entries are estimated at about 70 min for their 140, about 90 min of MLP fitting in all. PR 2's
    run measures it (`fit_seconds`);
  - the two ridge entries take seconds on CPU;
  - two CPU recomputes of the committed results (native Windows and WSL2);
  - no RunAI, cluster or CFD jobs.
- Downstream:
  - #114 (`add-real-comparison-figures`) reads the shipped surrogate, which is unchanged.
  - F3b plugs field entries into this bench.
  - After the corpus is regenerated, the bench is rerun, not rewritten.
- Claim scope: see `BENCH_SCOPE` in the bench spec.

## Amendment: larger-MLP entries (#195, between PR 1 and PR 2)

> Delivered as PR 1b (branch `add-bench-larger-mlp-entries`), after PR 1 merged and before PR 2's
> runs. It is a separate PR because PR 2 runs the bench from a clean commit on `main` before any
> commit on its own branch (design D0), so the runner change must be on `main` first.

**Why.** With only `mlp_h1` and `mlp_h3`, the bench cannot tell whether `mlp_h3` beats `mlp_h1`
because of the phase input or because any extra expressiveness would. In the exploration's E4
ablations a width-256, depth-5 MLP with one harmonic closed the gap at least as well as three
harmonics do at the shipped size: higher on each of the 5 seeds (design Context table and D8).

**What changes.**

- Two bench-only entries, `mlp_w256d5` and `mlp_w256d5_h3`. Their definition, holdout status and
  run order are in the bench spec ("Bench model entries and metrics"); the reasoning and the limits
  of what the resulting 2 × 2 can show are in design D8.
- `run_metadata.json` gains `mlp_hyperparameters`: for each MLP entry that ran, the `hidden`,
  `num_layers`, `lr` and `phase_harmonics` passed to `fit_seed`. Until now an entry's architecture
  was recorded only in the code at the run's commit.

**Impact.**

- Code: `src/mosquito_cfd/surrogate_bench/runner.py`.
- Tests: `tests/test_surrogate_bench_{runner,import,figure,cli,gpu}.py`.
- This change's proposal, design, tasks, bench spec delta and `review-reconciliation.md` (round 7).
- Docs: `openspec/project.md` and `docs/CHANGELOG.md` in PR 1b; the fine README bench section and
  both roadmaps in PR 2, as already planned.
- Compute: PR 2's bench run gains 140 fits, about 70 min (see Impact above).
- No shipped artifact changes. No bench result exists yet, so none is invalidated.

**Not in the amendment.** Other widths or depths: the 2 × 2 does not separate width from depth
(E4's width 256 at depth 3 scored 0.990–0.994 and width 64 at depth 5 0.989–0.995). A learning
rate tuned for the larger network. Any committed standalone larger model.

## Reconciliation with the implementation (PR 1)

### Why a public `carve_validation` instead of a private helper?

The spec said validation is carved "by the same private helper `make_config_splits` uses". The
helper is `force_surrogate.train.carve_validation`, public at module level but not exported from
`force_surrogate/__init__.py`. `surrogate_bench.splits` imports it from another package, and
importing a leading-underscore name across packages would make it part of the bench's contract
anyway, so the name says so. The behaviour is unchanged: `make_config_splits` calls it, and task 3a's
tests pin that it returns `make_config_splits`'s validation lists. The spec now names the helper.

### Why does an unknown git state count as dirty?

The spec defined the refusal only for a dirty tree. `benchmarks.metadata.get_git_info` returns no
`dirty` key when git cannot report one (for example from WSL on a Windows worktree). Treating that
as clean would let an unverifiable tree produce committed results, so the runner (not only the
driver) treats it as dirty: it is refused without `--allow-dirty` and recorded as `dirty: true` with
it. The spec now says so.

### Why does `coarse_vs_fine` bound the fine grid's error instead of the coarse grid's?

The approved spec and design said the coarse-fine difference "bounds the coarse grid's error, not
the fine grid's". The pre-PR review showed the reverse under the asymptotic Richardson model the
gate itself uses ($E_c = r^p E_f$): the difference is $(r^p - 1) E_f \approx 5.6\text{–}5.7\,E_f$
for the T3c orders, an upper bound on the fine grid's error (not an estimate of it), and about
$0.85\,E_c$, an under-estimate of the coarse grid's. The user approved the correction. The second
review round refined it: both corpora run at `dt = 5e-4`, so the difference covers spatial error
only, and `coarse_vs_fine_scaled`'s label now says the pair refines the grid only. Spec, design and
the provisional reason say so; no value or verdict changes, and `upper_bound: true` keeps its label
with the corrected meaning.

### Why selection needs 4 training configurations instead of 3?

The spec said "at least 3 training configurations, so that every fold has at least 2", but a fit
itself needs 3, so a 2-configuration fold could never be fitted. The code always required 3 for a
fit and 4 for selection, which makes every leave-one-out fold a valid fit. The spec now says that.
The bench's smallest training set is 18, so no result depends on it.

### Why a per-target like-for-like view with `control:e4_seed0` apart?

The spec scenario fixed the view's metrics but not its grouping. The first implementation took one
min/max over all six targets, every seed and all seven controls, so a face's range was the spread
between components (CF_y beside CF_z on the real corpus) and could not show a face failing on one
component. The view is now per entry and per target, with the six random controls together and the
rank-deficient `control:e4_seed0` on its own. The scenario says so.

### Changes from the pre-PR review (2026-11-22)

A five-reviewer self-review of the branch before PR 1 was opened found one blocking bug and a set of
important issues; the user chose to fix them in PR 1. Each fix has a test that a mutant was run
against. Beyond the three sections above:

- **A diverged MLP seed no longer crashes the bench.** Non-finite grid predictions became an
  exception in the body-frame rotation after every fit had run; they now reach the gate as NaN
  errors (`outside`, null margin), as the "Gate boundaries" scenario requires.
- **Refusals moved up front.** A corpus with fewer than 2 common beats, a configuration labelled
  neither train nor holdout or with a missing setting, no or empty entries, a non-integer epochs, an
  empty timestamp, an unknown device and an output path that is a file are refused; every check
  that depends only on the data runs before the first fit.
- **The summary documents 0/0** as "no error and no yardstick" (`reason_notes`), which the spec
  required and nothing did.
- **Provenance.** `run_metadata.json` records both dataset files, the coarse corpus's sha256 and
  recorded image, and how `--docker-digest` was checked; a digest other than the one the fine
  corpus's `run_metadata.json` records is refused. The driver hashes exactly the bytes it parses.
- **The five artifacts are written atomically**, so a late failure leaves no partial bench.
- **`seed_ranges` counts finite seeds**, so a NaN seed that leaves a range is visible.
- **Performance.** Each split's baseline and grid frame are built once and shared by every seed and
  entry (532 baseline builds per run became 42); the grid prediction's shape and order are checked.
- **GPU memory.** A CUDA run warms up cuBLAS/cuBLASLt before the first probed fit; measured on the
  A5000, the first fit's `peak_gpu_mem` was 13.0 MB against 4.47 MB for every other fit without it,
  and all five are 4.47 MB with it.
- **Code.** The bench reads the shipped recipe (hidden, layers, lr, epochs, validation count) from
  named `train.py` defaults, pinned by a test to `run_training`'s signature; `_SeedFit` became the
  exported `SeedFit`; `carve_validation` sorts names as given, as `make_config_splits` always did,
  and refuses repeats.

A second five-reviewer round on these fixes (fixes have introduced bugs here before) found:

- **Blocking, introduced by the diverged-seed fix:** pandas `sum()` skips NaN, so a NaN seed pooled
  to skill 1.0 and RMSE 0.0. Pooled sums now propagate NaN, and the like-for-like ranges count
  finite values as the seed ranges do.
- **The atomic write deleted a finished run on any failure**, and a move that failed partway left
  some files in `--out-dir`. The staging directory is now kept and named in the error, moves are
  rolled back, `--out-dir` is resolved (so `.` works), and an `--out-dir` under a file or an
  unwritable directory is refused up front.
- **`cuda:<n>` was accepted** although the memory probe reads the default device; `--device` is now
  `cpu` or `cuda`.
- **The driver now reads corpus records strictly** (an unreadable fine record is refused, naming
  it), records them truthfully (no borrowed coarse image, the reason when there is none), records
  dataset paths relative to the repository, and reads git state from the script's repository.
- **The warm-up and D7.** The warm-up now runs before `mlp_h1` / `interpolation`, which D7 requires
  to be fitted first. Verified on the A5000 under WSL2: that fit's per-target skills are bitwise
  equal with and without the warm-up, and to the shipped `metrics.json`. design.md D7 records it.
- Smaller items: the windowed peaks survive a non-finite value before the window; text settings, a
  bare-string `entries` and mixed carve name types get clear errors; and tests pin the cache key,
  the grid check, one grid build per split and selection's minimum of 4.

The ridge-only results on the real corpora are bitwise identical before and after the fixes
(`results.parquet`, timing columns excluded); only new summary keys and the reworded reasons differ.

One finding concerns code outside this change and is drafted as an issue for the user:
`benchmarks.metadata.get_git_info` computes `dirty` from `git diff HEAD`, so untracked files count
as clean.

### Other implementation notes (no behaviour change)

- `--out-dir` and `--docker-digest` are required flags, as in `extract_forces.py` and
  `make_comparison_figure.py`. A missing digest was already a refusal.
