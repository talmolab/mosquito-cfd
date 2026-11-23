## ADDED Requirements

### Requirement: Bench splits

The bench (`mosquito_cfd.surrogate_bench`) SHALL evaluate every model on the same named splits of the
fine force corpus (`examples/prelim_sweep_fine/dataset.parquet`), built by a pure function from the
dataset's configuration kinematics, never from a hand-typed list. Let `pool` be the sorted list of the
configurations labelled `split == "train"`; the builder SHALL require 21 of them and 6 labelled
`split == "holdout"`, and every configuration to carry one of those two labels and no missing
setting, else raise `ValueError`. A label or setting that is missing on some rows of a
configuration counts as mixed.

- `interpolation`: test = the 6 configurations labelled `split == "holdout"`; train = `pool`.
- `face:<setting>=<value>` for each of the 6 faces of the 3 × 3 × 3 grid (`stroke_amp_deg` 35 and
  55, `frequency_fstar` 0.85 and 1.15, `pitch_amp_deg` 30 and 60), named e.g.
  `face:stroke_amp_deg=35`: test = the 9 configurations on that face; train = the other 18 (which MAY
  include labelled holdout configurations).
- `control:<k>` for `k = 0..5`: train = `sorted(numpy.random.default_rng(k).choice(pool, size=18,
  replace=False))`; test = the 6 labelled holdout configurations.
- `control:e4_seed0`: train = `sorted(numpy.random.default_rng(0).permutation(pool)[:18])`, the
  exploration's E4 subset; test = the 6 labelled holdout configurations.

Each of the three settings SHALL have exactly 3 distinct values in the dataset, else the builder SHALL
raise `ValueError` naming the setting (so a missing outer value never silently promotes the middle
value to a face). Within each split, a learned model's validation configurations SHALL be carved from
that split's training configurations only, with 3 validation configurations, by the same helper
`make_config_splits` uses (`force_surrogate.train.carve_validation`), so that for the `interpolation` split it returns exactly
`make_config_splits(df, seed, n_val_configs=3)`'s validation configurations. Train, validation and
test SHALL be non-empty, pairwise disjoint and SHALL cover only configurations present in the
dataset. The split table (name, train, validation per seed, test) SHALL be written with the results.

#### Scenario: Fourteen splits with the specified membership

- **Given** the fine dataset
- **When** the splits are built
- **Then** there are exactly 14 splits (1 interpolation, 6 faces, 6 controls, `control:e4_seed0`) with the names above; each face split's test set is the 9 configurations sharing that setting value and its train set is the remaining 18; every control's train set is 18 configurations of `pool` and its test set is the 6 labelled holdouts; and the six controls' train lists equal literal lists recorded in the test (so a change in NumPy's `Generator.choice` stream fails loudly)

#### Scenario: The E4 control reproduces the exploration's subset

- **Given** the fine dataset
- **When** `control:e4_seed0` is built
- **Then** its train list equals this literal list: `s35_f085_p30, s35_f100_p30, s35_f100_p45, s35_f100_p60, s35_f115_p30, s35_f115_p45, s35_f115_p60, s45_f085_p30, s45_f100_p30, s45_f100_p45, s45_f115_p30, s45_f115_p45, s55_f085_p30, s55_f100_p30, s55_f100_p45, s55_f100_p60, s55_f115_p30, s55_f115_p60`, and its degree-3 capped polynomial matrix has 17 columns and rank 16

#### Scenario: Interpolation validation carve matches the shipped trainer

- **Given** seeds 1234–1238
- **When** the bench carves validation configurations for the `interpolation` split
- **Then** each seed's validation list equals `make_config_splits(df, seed, n_val_configs=3)`'s

#### Scenario: Splits are disjoint, deterministic and guarded

- **Given** any split and seed
- **When** the split is built twice
- **Then** the lists are identical both times and train/validation/test are pairwise disjoint and non-empty; and a dataset in which any setting has other than 3 distinct values (e.g. no `stroke_amp_deg == 55` rows), or whose labelled pool is not 21 + 6, raises `ValueError` naming the problem

### Requirement: Ridge reference model

The bench SHALL include a Fourier × polynomial ridge regression as a **reference** a learned model
must beat. It SHALL NOT be written as a checkpoint or exposed as a Track B surrogate. It SHALL be pure
numpy (no scipy, no sklearn) and deterministic. It SHALL be defined in two stages:

1. **Per-configuration Fourier coefficients.** Each training configuration's converged beat is
   periodically interpolated (period 1) onto `N = 256` uniform phases `k/256` and projected onto
   `[1, cos 2πhφ, sin 2πhφ]` for `h = 1..H`, giving `2H + 1` coefficients per target. Every
   configuration therefore carries equal weight, whatever its row count.
2. **Polynomial ridge per coefficient.** Kinematics are standardised with the mean and standard
   deviation over the training **configurations** (one value per configuration). The basis is every
   monomial in the three standardised settings with total degree `≤ d` **and** exponent of each
   setting `≤ L_v − 1`, where `L_v` is the number of distinct values of that setting among the
   training configurations. Each coefficient is fitted by minimising
   `Σ_c (a_c − m(z_c)ᵀβ)² + λ Σ_{j ≥ 1} β_j²` (the constant monomial `j = 0` unpenalised),
   `λ = α · n_train_configs`, solved with `numpy.linalg.lstsq` on the augmented system, not the
   normal equations. All coefficients and targets of one `(d, α)` SHALL be solved as one
   multi-right-hand-side system. Ranks SHALL use `numpy.linalg.matrix_rank` with its default
   tolerance. Beside each rank `r` the bench SHALL record, as fractions of the largest singular
   value σ₁: σ_r (the smallest retained), σ_{r+1} (the largest dropped; `null` at full rank) and the
   rank tolerance. σ_r is well conditioned and is compared like any metric. σ_{r+1} is round-off
   when a matrix is rank deficient and is never compared by value: it is only checked to be `null`,
   or below both the rank tolerance and `1e-13`. The tolerance ratio is recorded analytically as
   `max(m, n) · numpy.finfo(float).eps` and compared to `rtol = 1e-12`. The fit SHALL go through one internal function, `solve_ridge(M, A, lam)`, which the
   tests call directly.

Every leave-one-configuration-out fold is a fit in its own right: it re-standardises over, and
recomputes `L_v` from, its own training configurations. A setting with one distinct value in a fold
(`L_v = 1`) contributes no column and is not standardised. The ridge SHALL require at least 3
training configurations, so that every fold has at least 2.

All bench entries, and the phase-only baseline, train and score on one **target beat**, defined as
follows:

- The target beat is the largest `wingbeat` value present for every configuration.
- The `wingbeat` values common to every configuration SHALL be `0..N−1` with `N ≥ 2` (the
  startup beat alone is never the target, and `beat1_vs_beat2` needs two), else `ValueError`.
- Every configuration's target beat SHALL span the cycle (first phase below 0.01, last above 0.99),
  else `ValueError`, so a partial terminal beat is never used.

On the 2-beat corpus the target beat is `wingbeat == 1`: exactly the rows `filter_converged_beat`
keeps, so the MLP's training frame is unchanged. The shipped trainer's filter is not changed by this
change. On a corpus with more beats the target beat is the last one, and the exact `mlp_h1`
regression no longer applies until the shipped surrogate is retrained on that corpus.

`(H, d, α)` SHALL be chosen by leave-one-configuration-out cross-validation **inside each split's
training configurations**, on the pre-registered grid `H ∈ {1, 2, 4, 8, 12, 16, 24, 32}`,
`d ∈ {1, 2, 3}`, `α ∈ {1e-8, 1e-6, 1e-4, 1e-2, 1}`, by the **one-standard-error rule**:

- For candidate `θ` and left-out configuration `c`, the fold error is
  `e_c(θ) = mean_t SSE_{c,t}(θ) / S̄ST_t`, where `SSE_{c,t}` and `SST_{c,t}` are taken on the
  256-phase grid (`SST_{c,t}` about configuration `c`'s own mean) and `S̄ST_t = mean_c SST_{c,t}`.
  The score is `score(θ) = mean_c e_c(θ)` (equal to the mean over targets of `Σ_c SSE / Σ_c SST`),
  and its standard error is `se(θ) = std_c(e_c(θ), ddof=1) / sqrt(n_folds)`.
- Let `θ*` minimise the score, ties broken by the same order as below;
  `threshold = score(θ*) + se(θ*)`. Among candidates with `score ≤ threshold`, choose the smallest
  `H`, then the smallest `d`, then the largest `α`.
- A non-finite fold error SHALL raise `ValueError`, never be skipped.

The bench SHALL record per split:

- the chosen `(H, d, α)` and its score;
- `θ*` with its score, `se` and `at_grid_edge`;
- the relative gap between `θ*`'s score and the runner-up's;
- the largest single fold's share of `Σ_c e_c` for `θ*` and for the chosen candidate;
- `threshold`;
- `selection_margin = min_θ |score(θ) − threshold| / threshold` over all candidates (0 when
  `threshold` is 0);
- `selection_fragile = selection_margin ≤ 1e-6`;
- `at_grid_edge` per chosen value;
- for each `d`, against that `d`'s split-level `P`:
  - the number of polynomial columns `P`;
  - the rank of the training configurations' polynomial matrix, with its singular-value record;
  - the minimum rank over the fold matrices;
  - the number of folds whose rank is below `P`.

Test predictions SHALL evaluate the Fourier series at each test row's own phase.

The ridge SHALL raise `ValueError` for a non-finite target, a phase outside `[0, 1)`, a configuration
with fewer than 2 rows in its beat, a duplicate phase within a configuration's beat, or fewer than 3
training configurations.

#### Scenario: The identifiability cap drops terms a 2- or 3-level setting cannot support

- **Given** training configurations with 3 distinct values of every setting
- **When** the degree-3 basis is built
- **Then** it has 17 columns (no cubic power of any single setting); and with only 2 distinct stroke values (a stroke-face split) every column has stroke exponent ≤ 1 and the basis has 14 columns

#### Scenario: Known-answer recovery on the phase grid

- **Given** synthetic configurations on a 3 × 3 × 3 grid, sampled at phases `k/256`, whose targets are an exact degree-2 polynomial in the settings times `[1, cos 2πφ, sin 4πφ]`
- **When** the ridge model is fitted with `H = 2, d = 2, α = 1e-12` and evaluated on held-out grid configurations
- **Then** the predictions match the truth to `1e-8` relative to the target's scale

#### Scenario: Known-answer recovery at realistic sampling

- **Given** the same truth sampled at the non-uniform phases of a real fine-corpus configuration
- **When** the model is fitted with the same settings
- **Then** the predictions match the truth to `1e-5` relative to the target's scale (the interpolation error of the resample, not a fit error)

#### Scenario: Kinematics are standardised over configurations

- **Given** synthetic configurations with unequal row counts and `α = 1`
- **When** the model is fitted at the fixed point `H = 1, d = 1`, without selection
- **Then** the predictions equal a hand computation that standardises with one value per configuration, and differ from one that standardises over rows

#### Scenario: The intercept is not shrunk

- **Given** targets equal to a constant `10.0` for every configuration and phase
- **When** the model is fitted at the fixed point `H = 1, d = 1, α = 1`, without selection
- **Then** every prediction equals `10.0` to `1e-10` (a penalised intercept would shrink it)

#### Scenario: Equal weight per configuration

- **Given** two configurations with the same truth, one sampled at phases `k/256` and the other at `k/768` (three times denser, containing every `k/256` point)
- **When** the Fourier coefficients are computed
- **Then** the two coefficient vectors are bitwise equal, and each configuration contributes one row to the polynomial fit

#### Scenario: Cross-validation never sees the test configurations

- **Given** a split whose test configurations carry extreme coefficients
- **When** `(H, d, α)` is selected in one process
- **Then** the selection, the scores and the fitted coefficients are bitwise identical to those obtained with the test rows removed from the frame

#### Scenario: Selection follows the one-standard-error rule

- **Given** a synthetic table of fold errors in which `H = 32` has the lowest score, `H = 8` lies within one standard error of it, and every `H ≤ 4` lies outside
- **When** the rule is applied
- **Then** `H = 8` is chosen, `threshold` equals `score(θ*) + se(θ*)` computed by hand, `selection_margin` equals its hand value (and not one computed relative to `score(θ*)`), `at_grid_edge` for the chosen `H` is false and for `θ*`'s `H` is true
- **And** where two candidates within the threshold share `H`, the smaller `d` is chosen, and where they share `H` and `d`, the larger `α`

#### Scenario: Fold errors are computed as specified

- **Given** synthetic fold predictions for three configurations with unequal SST per configuration and target
- **When** `e_c`, `score` and `se` are computed
- **Then** they equal hand values (`ddof = 1`), and `score` equals the mean over targets of `Σ_c SSE / Σ_c SST` to `1e-12`
- **And** a candidate with `|score − threshold| = 1e-7 · threshold` gives `selection_fragile: true`, one at `1e-5 · threshold` gives `false`, and a perfect fit on every fold (`threshold = 0`) gives `selection_margin = 0` and `selection_fragile: true`

#### Scenario: Degenerate folds are handled

- **Given** a training set in which one setting has a single value in some fold, a training set of 2 configurations, and a target that is constant within every configuration (so `S̄ST_t = 0` and the fold error is 0/0)
- **When** the ridge is fitted
- **Then** the first fits without that setting's columns, the second raises `ValueError`, and the third raises `ValueError` rather than selecting around it

#### Scenario: The solve survives ill-conditioning

- **Given** this construction, all drawn from a fixed seed:
  - `M = [1, U diag(s) Vᵀ]` with `n = 27` and `s = numpy.logspace(0, −7, 16)`;
  - `U` from the QR of a column-centred 27 × 16 standard-normal draw (so `1ᵀU = 0`);
  - `V` from the QR of a 16 × 16 draw;
  - `A` a 27 × 3 standard-normal draw;
  - `λ = 1e-12`.
- **When** `solve_ridge(M, A, λ)` and a normal-equations solve of the same system are computed
- **Then**, with the error measured as `max|β − β_cf| / max|β_cf|` against the closed form (intercept `mean(A)`, the rest `V diag(s/(s² + λ)) Uᵀ A`):
  - `solve_ridge` is within `1e-8`;
  - the normal-equations solve is off by at least `1e-7`.

#### Scenario: Ranks and fold ranks are recorded

- **Given** the `control:e4_seed0` and `interpolation` splits
- **When** the ridge entry runs and its per-`d` record for `d = 3` is read
- **Then** `control:e4_seed0` records `P = 17`, rank 16, 18 deficient folds and a dropped σ₁₇/σ₁ below both the rank tolerance and `1e-13`; and `interpolation` records `P = 17`, rank 17, a `null` dropped singular value, minimum fold rank 16 and 1 deficient fold

#### Scenario: Malformed input is rejected

- **Given** a frame with a NaN target, a phase of 1.0 or −0.1, a configuration with one row, a duplicate phase within a beat, or only one training configuration
- **When** the ridge is fitted
- **Then** it raises `ValueError` naming the problem

#### Scenario: The reference is never a checkpoint

- **Given** the `surrogate_bench` package source
- **When** a static check scans `ridge.py` and the runner's ridge path
- **Then** neither references `torch`, a checkpoint writer or the trainer's checkpoint loader, and a bench run writes no checkpoint file

### Requirement: Bench model entries and metrics

The bench SHALL run these entries on every split:

- `mlp_h1` (the shipped MLP recipe, `phase_harmonics = 1`) and `mlp_h3` (`phase_harmonics = 3`),
  each over the seeds `BENCH_SEEDS = (1234, 1235, 1236, 1237, 1238)` with the shipped hyperparameters
  (width 64, depth 3, 2000 epochs, full-batch Adam, best-validation restore);
- `ridge` (one deterministic fit, `(H, d, α)` selected per split as above);
- `ridge_fixed` (one deterministic fit at the exploration's chosen point `H = 16, d = 3, α = 1e-6`,
  pre-registered here, no selection, its selection fields `null`). Against `ridge`, it separates
  the effect of re-selection from that of the corrected construction. The uncorrected leg is the
  exploration's 0.41 on E4's subset, which the bench does not re-run.

Each entry in the gate block and the summary SHALL carry `holdout_informed` (`true` or the string
`"unverified"`) and a `holdout_reason` string. The gate block SHALL also state that no entry is known
to be holdout-clean, so an `inside` verdict is not read as unbiased. The values are:

- `mlp_h1`: `"unverified"`. It is the shipped recipe, and the provenance of its hyperparameters is not
  recorded here.
- `mlp_h3`: `true`. Its harmonic count was chosen after holdout scores had been seen.
- `ridge_fixed`: `true`. Its point was chosen by CV on the 21 pool configurations, on a grid widened
  after holdout scores had been seen.
- `ridge`: `true`, weakly. Its grid contains values added after holdout scores had been seen, and the
  one-standard-error rule was adopted after design review had seen holdout skills of ridge variants,
  although the rule was motivated by the scale of the CV scores.

Holdout-informed entries are optimistic wherever a split's test set contains labelled holdout
configurations: `interpolation`, the controls, and 5 of the 6 faces. The summary SHALL record, per
split, the number of labelled holdouts in its test set, and SHALL also report the face metrics with
those configurations excluded.

The MLP entries SHALL train through `force_surrogate.train.fit_seed` on the full target-beat frame
in dataset order, SHALL score skill on the fit's own test predictions (as `run_training` does), and
SHALL evaluate on the phase grid through `force_surrogate.train.predict_frame`; never through a
re-implementation. The runner SHALL fit `mlp_h1` on `interpolation` first in the process.

All error metrics are **fractions** (0.05 means 5 %). For every entry, split, seed, target and test
configuration `results.parquet` SHALL record:

- `sse`, `sse_baseline` and `n_rows` on the test rows, and
  `skill = 1 − sse / sse_baseline` computed by `compute_baseline_skill` with the baseline built by
  `build_phase_only_baseline(..., reference_configs=<that split's training configurations>)`;
- `grid_sse` and `n_grid` (= 256) on the 256-phase grid, the model evaluated directly at the grid
  phases and the CFD beat periodically interpolated onto them;
- `rmse_frac_config_peak = sqrt(grid_sse / n_grid) / max|CFD_grid|` of that configuration and target;
- `rmse_frac_component_peak = sqrt(grid_sse / n_grid) / peak_t`, where `peak_t` is the target's
  `max|CFD|` over all 27 fine configurations' converged beats on the 256-phase grid;
- `baseline_rmse_frac_component_peak`, the phase-only baseline's value of the same quantity, so splits
  of different difficulty can be compared;
- the fit wall time, the inference time per row (measured around the runner's `predict_frame` call, so no torch import is needed beyond it), `peak_gpu_mem`, and `n_params`.
  - `peak_gpu_mem` is in bytes. For an MLP fit on CUDA it is measured as `synchronize();
    reset_peak_memory_stats(); base = memory_allocated()`, then the fit, then `synchronize();
    peak_gpu_mem = max_memory_allocated() − base`, through the runner's `memory_probe` argument. It is `null`
    for the ridge entries and for `--device cpu`.
  - `n_params` is
    the trainable parameters of the whole MLP, or `6 · (2H + 1) · P` coefficients for the ridge (all
    six targets in both cases).
  - Timing and memory fields SHALL be excluded from every equality test.

`summary.json` SHALL record, per entry, split and seed, the per-target skill computed by
`compute_baseline_skill` over all of that seed's test rows in dataset order (key
`per_seed_skill`), and per entry and split the pooled values recomputed from the `sse`/`grid_sse`
sums. Seed spread SHALL be reported as the NaN-aware min/max range over the 5 seeds, never as a
single run. Skill SHALL NOT be compared across splits; cross-split comparison SHALL use
`rmse_frac_component_peak` next to `baseline_rmse_frac_component_peak`.

#### Scenario: Skill baseline follows the split

- **Given** a face split
- **When** skill is computed for it
- **Then** the baseline's recorded `reference_configs` equal that split's 18 training configurations, not `pool`

#### Scenario: The explicit interpolation baseline is the shipped baseline

- **Given** the fine dataset
- **When** `build_phase_only_baseline` is called with `reference_configs = pool`, with the same list unsorted, and without a list
- **Then** the three baseline curves are bitwise equal (only `reference_split` differs in the definition block)

#### Scenario: The two normalisations differ by the ratio of peaks

- **Given** a synthetic two-configuration frame in which configuration A's peak for one target is one tenth of configuration B's
- **When** the error rows are written for A
- **Then** `rmse_frac_config_peak / rmse_frac_component_peak` equals `peak_t / max|CFD_A|` = 10 to `1e-12`

#### Scenario: Pooled values recompute from the stored sums

- **Given** a results frame
- **When** the summary is rebuilt from it
- **Then** each pooled skill equals `1 − Σ sse / Σ sse_baseline` and each pooled grid RMS equals `sqrt(Σ grid_sse / Σ n_grid)` over that split's test configurations, to `1e-12`

#### Scenario: Learned entries are never reported from one seed

- **Given** an `mlp_*` entry
- **When** the summary is built with 4 completed seeds for any split
- **Then** the bench raises rather than writing a summary for that entry, and with 5 it does not

#### Scenario: The fixed ridge point separates the two causes

- **Given** the `control:e4_seed0` split
- **When** the bench runs
- **Then** both `ridge` (re-selected) and `ridge_fixed` (`H = 16, d = 3, α = 1e-6`) rows are present on every split, `ridge_fixed` performed no selection (its selection fields are `null`), and its recorded rank at `d = 3` on `control:e4_seed0` is 16

#### Scenario: Holdout-informed entries are flagged

- **Given** the 14 splits
- **When** the summary is written
- **Then** each split records its number of labelled holdout test configurations: 6 for `interpolation` and every control, and 1, 2, 3, 2, 0 and 3 for the faces at stroke 35 and 55, f* 0.85 and 1.15, pitch 30 and 60
- **And** each face's metrics are also reported without those configurations
- **And** a like-for-like view reports each face's labelled-holdout configurations beside the controls on the same configurations:
  - it uses `rmse_frac_component_peak` and `baseline_rmse_frac_component_peak` only, with no skill key, because skill is not compared across splits;
  - it is reported per entry and per target, with three ranges of each metric pooled over those configurations: the face model over seeds, the six random controls over controls and seeds, and `control:e4_seed0` over seeds, kept apart because its training subset is rank deficient;
  - for `face:pitch_amp_deg=30`, which has no labelled holdouts, it is `null` with reason `"no labelled holdouts on this face"`
- **And** `holdout_informed` is `"unverified"` for `mlp_h1` and `true` for `mlp_h3`, `ridge_fixed` and `ridge`, each with a `holdout_reason`; `ridge`'s reason says "weakly"

#### Scenario: The model is evaluated directly at the grid phases

- **Given** a synthetic model whose value at a grid phase differs from the linear interpolation of its values at the test rows' phases
- **When** `grid_sse` is computed
- **Then** it uses the model's value at the grid phase

### Requirement: Provisional hover gate

The bench SHALL compute a per-component hover-gate verdict on the `interpolation` split only, for
every entry, comparing the worst seed's error against each available yardstick separately. Errors and
yardsticks are fractions. Both sides of every comparison SHALL use the same normaliser:

- **Lab-frame components** (`CF_x..CF_mz`): error = `rmse_frac_component_peak`; every yardstick is the
  same grid RMS divided by the same `peak_t`.
- **Body-frame normal and chord peaks**: on the 256-phase grid, the model's lab-frame
  `CF_x, CF_y, CF_z` evaluated at the grid phases and the CFD's lab-frame values periodically
  interpolated to the same phases are both rotated into the wing frame at those phases with
  `euler_angles` and `rotation_matrix` (phase → time `t = phase / f*`, degrees → radians) and
  `body_frame_coefficients` (`f_ref = 1`). Error = `|max|Ĉ| − max|C|| / max|C|` for each
  configuration. Raw CSV rows are never used for a peak, because the last row of every f* = 0.85
  configuration is anomalous (#173). Every yardstick for a peak is likewise relative to the
  configuration's own CFD peak.

Yardsticks, each recorded with its source. The constants live in one module, `gate.py`:

- `grid_gci`: T3c `GCI_fine`, CF_normal 0.03692 and CF_chord 0.2758 (the values computed in
  `tests/test_results_reproducibility.py` and reported as 3.7 % and 27.6 % in
  `examples/flapping_wing/RESULTS.md`). Applies to the two body-frame peaks only.
- `coarse_vs_fine`: the same metric with the coarse 64³ corpus (`examples/prelim_sweep/`) in place
  of the model, normalised by the fine corpus's normaliser. It bounds the **coarse** grid's error, so
  it SHALL be labelled `upper_bound: true`. It SHALL also be reported scaled by `1 / (r^p − 1)` with
  `r = 4` and the T3c computed orders (`p = 1.3773` normal, `1.3655` chord, the normal order for the
  lab components) as `coarse_vs_fine_scaled`, labelled with its limits: order borrowed from T3c
  (one configuration, grid and timestep refined together), safety factor `Fs = 1.25` not applied,
  and the two corpora built with different container digests.
  - The coarse corpus SHALL contain every fine configuration, else `ValueError` naming the missing
    configurations.
  - If it lacks the fine target beat (e.g. a regenerated fine corpus with more beats), `coarse_vs_fine`
    is `unavailable` with reason `"coarse corpus lacks target beat <k>"`, and the bench still runs.
- `beat1_vs_beat2`: read from the **unfiltered** frame, it compares `wingbeat == 0` with
  `wingbeat == 1` over the grid points `k/256` with `k ≥ 13` (the `[0.05, 1)` window).
  - For lab components it is the grid RMS of the difference.
  - For peaks it is `|max|C_1| − max|C_0|| / max|C_1|`, with every maximum, the normaliser
    included, taken over the window.
  - The model error is recomputed over the same window for this comparison.
  - The name stays fixed (beats 0 and 1) on longer corpora by design: it measures the startup
    transient.
- `late_beat`: let `N` be the number of `wingbeat` values present for every configuration. When
  `N ≥ 4`, the gate's target beat is `wingbeat == N − 1` and `late_beat` compares it with
  `wingbeat == N − 2` over `[0, 1)`: the grid RMS of the difference for lab components and
  `|max|C_{N−1}| − max|C_{N−2}|| / max|C_{N−1}|` for peaks. When `N < 4` it is recorded as
  `unavailable` with reason `"fewer than 4 beats"`.

The bench SHALL also record, per configuration of the CFD target beat, the **wrap jump**. A
periodic model cannot represent this discontinuity. For lab components (normaliser `peak_t`) and the
body-frame normal and chord values (normaliser the configuration's grid peak), it records four
quantities:

- `|C(first row) − C(last row)|`;
- `|C(first row) − C(last-but-one row)|`;
- a slope-corrected jump, `|C(first row) − C̃|`, where `C̃` linearly extrapolates the last-but-two and
  last-but-one rows to phase `1 + φ_first`;
- the wrap gap `1 + φ_first − φ_last` in units of the beat's median row spacing.

Per (entry, component, yardstick):

- the verdict SHALL be `inside` if the worst-seed error is `≤` the yardstick for every test
  configuration, else `outside`. The worst-seed error is NaN if any seed's error is NaN; this is not
  the NaN-aware reduction used for seed ranges. A NaN error or a NaN yardstick is never `inside`: the
  verdict is `outside`, the margin `null`, and a reason is recorded;
- a yardstick that does not apply to a component is `not_applicable`;
- the margin SHALL be the minimum over test configurations of `yardstick / worst-seed error`:
  - a configuration's term is `"inf"` when its worst error is 0 and the yardstick positive;
  - configurations where both are 0 are left out of the minimum, which is `null` only if every
    configuration is 0/0;
  - any NaN error makes the margin `null` and the verdict `outside`.

A component whose every yardstick is `not_applicable` or `unavailable` SHALL be reported as
`no_yardstick` and never as passing. When `late_beat` is available it is added as a further
yardstick beside the others, for every component. For the two body-frame peaks a combined yardstick
`sqrt(grid_gci² + late_beat²)` is also added, with the linear sum `grid_gci + late_beat` recorded
beside it.

The gate block SHALL carry `provisional: true` with this list of reasons while any verdict rests on a
stand-in yardstick:

- `grid_gci` is from one configuration at 70° stroke, outside the corpus's 35–55°;
- it is a one-beat run, so the startup beat;
- T3c refined grid and timestep together, and its fine run used `dt = 2.5e-4` at `cfl = 0.3`
  while the corpus uses `5e-4` at `0.6`, so the corpus's temporal error is not covered;
- the T3c deck's z boundary condition is 2 where the corpus's is 4;
- `coarse_vs_fine` bounds the coarse grid's error, not the fine grid's;
- `beat1_vs_beat2` includes the startup beat of a 2-beat run that has not settled;
- the converged beat is not periodic. The reason states three values, each computed from the
  recorded values, never fixed text:
  - the largest body-frame normal wrap jump (first row vs last-but-one row) over all configurations,
    and separately over the gated test configurations, each as a percentage beside `grid_gci`;
  - the largest distance in phase between any configuration's normal peak and the wrap.

A component whose margin is `null` because every configuration is 0/0 SHALL carry the reason
`"all configurations 0/0"`.

The gate block SHALL NOT emit a single overall pass/fail.

#### Scenario: GCI constants trace to their sources

- **Given** the yardstick constants in `gate.py`
- **When** the traceability test runs
- **Then** they equal the `gci_fine` values computed by the T3c reproducibility code to `1e-4`, and, rounded to one decimal percent, the 3.7 % and 27.6 % parsed from the `GCI_fine` rows of the T3c CF_normal and CF_chord tables in `RESULTS.md`; a parse failure names the table it could not find

#### Scenario: Body-frame peaks use the phase grid

- **Given** configuration `s55_f085_p45` of the fine dataset
- **When** its CFD body-frame normal peak is computed
- **Then** it equals 1.988 to `1e-3`, not the 2.054 of the raw rows

#### Scenario: Body-frame rotation known answers

- **Given** a configuration with `f* = 0.85`, stroke 55° and pitch 45°, and lab forces written out by hand from the kinematic formulas (not computed through the code under test): at phases 0 and 0.25 the wing's unit normal, and at phase 0.125 the lab unit vectors x̂ and ŷ
- **When** the gate's rotation is applied
- **Then** at phases 0 and 0.25 `cf_normal = 1` and `cf_chord = 0`; at phase 0.125, with `φ = 55°·sin(π/4)` and `α = 45°·cos(π/4)` in radians:
  - for x̂: `cf_normal = cos φ sin α` (0.410381), `cf_chord = cos φ cos α` (0.661366) and `cf_span = −sin φ` (−0.627839);
  - for ŷ: `cf_normal = sin φ sin α` (0.331028) and `cf_chord = sin φ cos α` (0.533481);
- **And** all agree to `1e-12`, so a flipped stroke sign, a stroke in degrees, a missing `/f*`, a missing pitch lead or `R` in place of `Rᵀ` each fails at least one case

#### Scenario: Worst seed decides and margin uses the worst seed

- **Given** five seeds whose errors for one configuration and component are 0.01, 0.02, 0.03, 0.04 and 0.06 against a yardstick of 0.05
- **When** the verdict is computed
- **Then** the verdict is `outside` and the margin is `5/6`

#### Scenario: Errors and yardsticks are fractions

- **Given** a worst-seed body-frame normal peak error of 0.03 against `grid_gci` 0.03692
- **When** the verdict is computed
- **Then** it is `inside` with margin 1.2307 to `1e-4` (an implementation that scales either side by 100 fails)

#### Scenario: Gate boundaries

- **Given** a worst-seed error equal to the yardstick; one configuration over it and the rest under; a NaN error; a yardstick of 0 with a positive error; a worst error of 0 with a positive yardstick; and both 0
- **When** the verdicts are computed
- **Then**:
  - the verdicts are `inside`, `outside`, `outside`, `outside`, `inside` and `inside` respectively;
  - the margin with two configurations is the smaller of theirs;
  - the NaN case's margin is `null`, and four finite seeds plus one NaN seed give `outside` with a `null` margin;
  - a NaN yardstick gives `outside` with a `null` margin and a reason;
  - a component whose every configuration is 0/0 is `inside` with a `null` margin, which the summary documents as "no error and no yardstick", not a failure;
  - the last two margins serialise as `"inf"` and `null`;
  - a 0/0 configuration beside a 0.03-vs-0.05 configuration leaves the margin at 5/3.

#### Scenario: Yardstick values are known answers

- **Given** a synthetic coarse corpus whose `CF_x`, `CF_y`, `CF_z` and `CF_mx` equal the fine corpus's times 1.1, and a synthetic beat 0 that differs from beat 1 by a known sinusoid over the grid points `k/256` with `k ≥ 13` (the `[0.05, 1)` window)
- **When** `coarse_vs_fine`, `coarse_vs_fine_scaled` and `beat1_vs_beat2` are computed
- **Then**:
  - each body-frame peak's `coarse_vs_fine` is exactly 0.1, relative to the configuration's own peak (the rotation is linear);
  - `CF_mx`'s is `0.1 · RMS_grid(fine CF_mx) / peak_t`;
  - the scaled values are those times `1 / (4^1.3773 − 1)` (normal and lab) and `1 / (4^1.3655 − 1)` (chord);
  - `beat1_vs_beat2` equals its hand value;
  - all to `1e-12`, and `coarse_vs_fine` carries `upper_bound: true`

#### Scenario: A component with no yardstick never passes

- **Given** a synthetic case in which every yardstick for one component is `not_applicable` or `unavailable`
- **When** the gate is computed
- **Then** that component is reported as `no_yardstick` with no `inside` verdict; and on the 2-beat corpus `CF_mx`'s `grid_gci` entry is `not_applicable`, its `late_beat` entry is `unavailable` with reason `"fewer than 4 beats"`, and the gate block has `provisional: true` with the listed reasons and no overall pass/fail key

#### Scenario: Late-beat boundary

- **Given** synthetic datasets with 2, 3 and 4 beats per configuration
- **When** the gate is computed
- **Then**:
  - with 2 and 3 beats `late_beat` is `unavailable`;
  - with 4 beats it compares `wingbeat` 3 with 2, and every entry trains and is scored on `wingbeat == 3` only (no duplicate phases reach the ridge);
  - the combined yardstick for the body-frame normal peak equals `sqrt(0.03692² + late_beat²)`, with the linear sum beside it;
  - every lab component gains `late_beat` beside its existing yardsticks;
  - a dataset in which one configuration has fewer beats than the others uses the largest beat common to every configuration;
  - common beats `{1, 2, 3}` (beat 0 missing) raise `ValueError`;
  - a configuration whose last beat ends at phase 0.5 raises `ValueError`;
  - a 2-beat coarse corpus beside a 4-beat fine corpus makes `coarse_vs_fine` `unavailable` with reason `"coarse corpus lacks target beat 3"`, and the rest of the gate is computed.

#### Scenario: Beat yardstick and its error share a window

- **Given** a synthetic frame whose beat 0 differs from beat 1 only in phase `[0, 0.05)`
- **When** `beat1_vs_beat2` and the matching model error are computed
- **Then** the yardstick is 0 and the error is computed over `[0.05, 1)` as well
- **And** given a synthetic beat 1 whose global |C| maximum lies at phase 0.02, outside the window and larger than any value inside it, with beat 0 = 0.9 × beat 1 on the window:
  - the peak `beat1_vs_beat2` is exactly 0.1, because the normaliser is windowed;
  - the matching model error uses the windowed CFD maximum.

#### Scenario: The wrap jump is recorded

- **Given** configuration `s55_f085_p45` of the fine dataset
- **When** its body-frame normal wrap jump is computed
- **Then** it records, against the grid normal peak 1.988, each to `1e-3`:
  - 0.0242 against the last-but-one row;
  - 0.0352 against the last row;
  - 0.0260 slope-corrected;
- **And** it records a gap of 0.941 median spacings, to `1e-3`.
- **And** a synthetic lab sawtooth `C = a·φ` with `a = −3`, uniform spacing `h = 1/50`, `φ_0 = 0.01`, its last row displaced by `δ = 0.37`, and `peak_t = 2` injected, gives:
  - slope-corrected `|a| / peak_t`;
  - raw `|a(φ_L − φ_0) + δ| / peak_t`;
  - last-but-one `|a|(φ_{L−1} − φ_0) / peak_t`;
  - gap `(1 + φ_0 − φ_L) / h`;
  - all to `1e-12`.
- **And** the non-periodic provisional reason reports the largest last-but-one normal jump over all configurations (0.046 on the fine corpus) and over the gated test configurations, each as a percentage, and the largest peak-to-wrap phase distance. A synthetic change to the recorded jumps changes the reason, so a mutant that hard-codes the text is killed.

### Requirement: Bench artifacts, provenance and claim scope

`scripts/run_surrogate_bench.py` SHALL take these flags:

- `--dataset` (required);
- `--coarse-dataset` (required);
- `--out-dir`;
- `--docker-digest`, named as in the repository's other drivers;
- `--timestamp`;
- `--device` (default `cpu`);
- `--entries` (default all; `ridge,ridge_fixed` gives a CPU-only run; duplicate tokens are
  refused);
- `--epochs` (default 2000; for tests);
- `--allow-dirty`.

It SHALL write into `--out-dir`:

- `results.parquet` (one row per entry, split, seed, target and test configuration);
- `splits.json`;
- `summary.json` (per entry and split: pooled metrics with seed ranges, `per_seed_skill`, the ridge
  selection and rank records, the wrap jumps, the gate block);
- `bench_summary.png` (skill by entry and split, seed range as error bars);
- `run_metadata.json`, captured with a pinned container **digest** and a caller-supplied timestamp. It
  records the dataset sha256, the git commit, branch and dirty flag, the hardware block, the seeds,
  the device, the entries and epochs, the `CUBLAS_WORKSPACE_CONFIG` environment value (or `null`),
  and a `library_versions` block (`numpy`, plus `torch` and `physicsnemo` when installed) in the same
  shape the trainer's `run_metadata.json` uses.

`summary.json` SHALL carry a `scope` field whose value is the module constant `BENCH_SCOPE`. It states
three limits:

- interpolation inside, and extrapolation to a held-out outer layer of, a 3 × 3 × 3 grid of
  configurations;
- second-beat data from 2-beat runs that has not settled;
- generic sinusoidal validation kinematics, not van Veen's and not a mosquito's (#142).

The fine README SHALL quote `BENCH_SCOPE` verbatim. The run SHALL refuse a dirty tree unless
`--allow-dirty` is passed, in which case the metadata records `dirty: true`. A tree whose git state
carries no dirty flag SHALL count as dirty. It SHALL also refuse:

- a mutable image tag;
- a missing `--timestamp`;
- a non-empty `--out-dir`;
- an unknown, duplicated or empty `--entries` token, or no entries;
- `--epochs` that is not an integer of at least 1;
- an empty `--timestamp`, or a `--device` other than `cpu`, `cuda` or `cuda:<n>`;
- an `--out-dir` that exists and is not a directory.

All refusals SHALL happen before any file is written. Every check that depends only on the data
(splits, target beat, yardsticks, wrap jumps) SHALL run before the first fit, so a bad corpus is
refused before any GPU time is spent. The committed copy SHALL live in `examples/prelim_sweep_fine/bench/` and
SHALL be produced from a clean tree whose commit is on `main`.

#### Scenario: Summary carries scope and provenance

- **Given** a completed bench run
- **When** `summary.json` and `run_metadata.json` are read
- **Then** `scope` equals `BENCH_SCOPE`, the dataset sha256 equals the committed `dataset.parquet`'s, the digest contains `sha256:`, and the timestamp equals the supplied value

#### Scenario: The scope names all three limits

- **Given** `BENCH_SCOPE`
- **When** the scope test runs
- **Then** it contains "3 × 3 × 3", "held-out outer layer", "2-beat", "has not settled" and "#142"

#### Scenario: The README quotes the scope

- **Given** the committed fine README
- **When** the README test runs
- **Then** it contains `BENCH_SCOPE` verbatim

#### Scenario: The summary figure shows every entry and split

- **Given** a synthetic summary with 4 entries and 14 splits
- **When** `bench_summary.png` is written
- **Then** the file exists and the figure has one point with a seed-range error bar per (entry, split)

#### Scenario: The driver rejects unsafe invocations

- **Given** a mutable image tag, a dirty tree without `--allow-dirty`, a missing `--timestamp`, a non-empty `--out-dir`, an unknown or duplicated `--entries` token, `--epochs 0`, or a coarse dataset missing a fine configuration
- **When** `scripts/run_surrogate_bench.py` is invoked
- **Then** it exits non-zero, and the output directory is absent or its prior contents (names and bytes) are unchanged
- **And** with `--allow-dirty` on a dirty tree it runs and records `dirty: true`

#### Scenario: Committed bench results are consistent with their inputs

- **Given** the committed `examples/prelim_sweep_fine/bench/`
- **When** the CPU-tier consistency test runs
- **Then** every summary number recomputes from `results.parquet` to `1e-12`, and the split lists recompute from the dataset.
- **And** the ridge rows recompute on CPU from the dataset as follows:
  - the committed `selection_fragile` equals the recomputed `selection_margin ≤ 1e-6`;
  - for a split with `selection_fragile: false`, every discrete output (`H`, `d`, `α`, `P`, ranks, fold counts, `at_grid_edge`) is exactly equal;
  - for a split with `selection_fragile: true`, the recompute helper `surrogate_bench.ridge.recheck_split` refits at the committed `(H, d, α)` and raises `SelectionNotRecheckedWarning` (defined in `surrogate_bench/ridge.py`);
  - in both cases every score, threshold, `sse`, `grid_sse`, metric and retained σ_r/σ₁ equals the committed value to `rtol = 1e-8`;
  - `selection_margin`, the runner-up gap and any metric near zero also allow `atol = 1e-9`;
  - each dropped σ_{r+1}/σ₁ is `null` on both sides, or below the rank tolerance and `1e-13` on both sides;
  - rank tolerances agree to `rtol = 1e-12`.

#### Scenario: The interpolation MLP rows reproduce the shipped surrogate

- **Given** the committed `bench/summary.json` and `surrogate/metrics.json`
- **When** the CPU-tier regression test runs
- **Then** it first asserts the preconditions recorded in both `run_metadata.json` files: the same `hardware.hostname`, GPU model and driver version, and the same `library_versions.torch` and `library_versions.physicsnemo`
- **And** for each seed in `BENCH_SEEDS` and each target, `per_seed_skill` of `mlp_h1` / `interpolation` equals `seed_sweep.runs[*].per_target[*].skill` exactly

### Requirement: Two-tier bench tests

The bench SHALL test all logic other than MLP training (splits, ridge, metrics, gate, summaries, CLI
wiring, artifact consistency) on the CPU tier without torch, using small synthetic frames and
monkeypatched MLP seams. MLP-entry tests SHALL be marked `gpu`, import `torch` only inside test
bodies, and be skipped where the `train` group or CUDA is absent, following the repository's existing
two-tier convention. On Windows hosts the GPU tier runs under WSL2, as the shipped surrogate's
training did. The CPU recompute of a full committed bench SHALL fit in the CI job's normal runtime.
The test SHALL record its duration with `record_property` and fail only above 120 s.

#### Scenario: Importing the bench pulls in no heavy dependency

- **Given** a fresh interpreter (`sys.executable`) with a `sys.meta_path` hook that raises on any import of `torch`, `physicsnemo`, `scipy` or `sklearn`
- **When** `import mosquito_cfd.surrogate_bench` runs in that subprocess
- **Then** the subprocess exits 0, so the check is meaningful whether or not those packages are installed

#### Scenario: The committed recompute stays fast

- **Given** the committed bench
- **When** the CPU recompute test runs
- **Then** its duration is recorded with `record_property`, and the test fails only above 120 s
