# Add a surrogate comparison bench (F3a)

> **PR 1 of 2 — archive this change only after PR 2 merges.**

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
    1234–1238, and a `ridge` reference rebuilt from first principles (design D3). The ridge uses
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

Delivered in two PRs (design D0): code first, then the results produced from `main`.

Not in this change: field models (F3b), DoMINO (F3c), commanded-change configurations, a change of the
shipped default, the coarse corpus as a bench target, the regenerated corpus.

## Impact

- Affected specs: `force-surrogate` (6 MODIFIED, 1 ADDED), new `surrogate-comparison-bench`.
- Affected code:
  - `src/mosquito_cfd/force_surrogate/train.py`: `build_features`, `_fit_one_seed`, `run_training`
    and `build_phase_only_baseline`; the validation carve inside `make_config_splits`, extracted into
    a shared helper; new `fit_seed`, `predict_frame` and `phase_harmonics_from_features`; the
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
  - 140 MLP fits (14 splits × 2 entries × 5 seeds, about 9 s each, about 21 min) under WSL2 on the
    local A5000, plus two full h3 trainings;
  - the two ridge entries take seconds on CPU;
  - two CPU recomputes of the committed results (native Windows and WSL2);
  - no RunAI, cluster or CFD jobs.
- Downstream:
  - #114 (`add-real-comparison-figures`) reads the shipped surrogate, which is unchanged.
  - F3b plugs field entries into this bench.
  - After the corpus is regenerated, the bench is rerun, not rewritten.
- Claim scope: see `BENCH_SCOPE` in the bench spec.
