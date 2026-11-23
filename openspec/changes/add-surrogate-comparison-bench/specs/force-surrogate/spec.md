## MODIFIED Requirements

### Requirement: Surrogate input and target construction

The trainer SHALL build inputs and targets from the dataset without re-deriving any coefficient math
(CC-3 — it consumes the dataset's already-normalized `CF_*` columns). By default inputs SHALL be
`[stroke_amp_deg, frequency_fstar, pitch_amp_deg, sin(2π·phase), cos(2π·phase)]` (cyclic phase
encoding; **Reynolds is excluded** because it is a deterministic function of `(φ, f*)` under the
ν\*-fixed policy and carries no independent information). An optional integer `phase_harmonics = H`
(default `1`, `H ≥ 1`) SHALL append, after those five columns, `sin(2π·h·phase)` and
`cos(2π·h·phase)` for `h = 2..H`, named `phase_sin_h{h}` and `phase_cos_h{h}` in that order, giving
`3 + 2H` columns. At the default the matrix, its column names, the checkpoint's `feature_names` and
every `metrics.json` key SHALL be bitwise identical to the behaviour before this option existed. The
harmonic count SHALL be recoverable from the feature names alone (`phase_harmonics_from_features`),
so a checkpoint needs no new key. Targets SHALL be the six coefficients
`CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`. The trainer SHALL filter to the **converged beat**
(`wingbeat ≥ 1`) before training and evaluation. Feature and target standardization statistics SHALL
be fit on **training rows only** (no validation/holdout leakage).

#### Scenario: Feature columns are the kinematics knobs plus cyclic phase

- **Given** a dataset slice
- **When** `build_features` is called with the default `phase_harmonics`
- **Then** the returned feature matrix has exactly five columns named `stroke_amp_deg, frequency_fstar, pitch_amp_deg, phase_sin, phase_cos`, where `phase_sin = sin(2π·phase)` and `phase_cos = cos(2π·phase)`, and **no** `reynolds` column is present

#### Scenario: Default harmonics are bitwise identical to the pre-option features

- **Given** the committed fine `dataset.parquet` filtered to the converged beat
- **When** `build_features(df)` and `build_features(df, phase_harmonics=1)` are called
- **Then** both matrices are bitwise equal (`np.array_equal` on the raw bytes) to a frozen copy of the pre-change five-column construction `[stroke, f*, pitch, sin(2.0*np.pi*phase), cos(2.0*np.pi*phase)]`, and the names equal `FEATURE_COLUMNS`

#### Scenario: Extra harmonics are appended in a fixed order and recoverable from names

- **Given** rows with known phases
- **When** `build_features(df, phase_harmonics=3)` is called
- **Then** the matrix has 9 columns, the first five equal the default matrix, columns 6–9 are `phase_sin_h2, phase_cos_h2, phase_sin_h3, phase_cos_h3` with values `sin/cos(2π·h·phase)`, and `phase_harmonics_from_features(names)` returns 3 (and 1 for `FEATURE_COLUMNS`)

#### Scenario: Invalid harmonic counts and malformed names are rejected

- **Given** `phase_harmonics` of 0, −1, 2.5, `True` or `"3"`, or a feature-name list with a gap (`phase_sin_h3` without `h2`), a duplicate, or an unknown phase column
- **When** `build_features` or `phase_harmonics_from_features` is called
- **Then** 0 and −1 raise `ValueError`, 2.5, `True` and `"3"` raise `TypeError`, each malformed name list raises `ValueError` naming the problem, and `np.int64(3)` is accepted as 3

#### Scenario: Cyclic phase encoding is continuous across the wrap

- **Given** two rows with `phase = 0.999` and `phase = 0.001` (adjacent in the cycle)
- **When** their `(phase_sin, phase_cos)` features are computed
- **Then** the two feature pairs are numerically close (Euclidean distance small), whereas their raw `phase` scalars differ by ≈ 0.998 — confirming the encoding removes the 0/1 boundary discontinuity

#### Scenario: Only the converged beat is used

- **Given** the dataset with `wingbeat ∈ {0, 1}`
- **When** `filter_converged_beat` is applied
- **Then** every retained row has `wingbeat ≥ 1`, no `wingbeat == 0` (startup-transient) row remains, and the drop is explicit (the count of retained rows equals the count of `wingbeat == 1` rows) — not a silent mask

#### Scenario: Standardization is fit on training rows only

- **Given** train, validation, and holdout row partitions
- **When** the `Standardizer` is fit
- **Then** the feature/target means and standard deviations are computed from the **training rows only**; recomputing them from the full dataset yields different values (proving no validation/holdout rows entered the fit), and transforming the training features yields per-column mean ≈ 0 and std ≈ 1

#### Scenario: Targets round-trip through standardization

- **Given** the six target columns and a `Standardizer` fit on the training targets
- **When** targets are standardized and then inverse-transformed
- **Then** the inverse-transformed values equal the originals within floating tolerance, so metrics computed after inverse-transform are in physical coefficient units

### Requirement: PhysicsNeMo force-coefficient regressor

The trainer SHALL learn the kinematics(+phase) → six-coefficient map with a **PhysicsNeMo** model
(its fully-connected/MLP architecture) and SHALL NOT ship a second (e.g. plain-PyTorch) model as a
fallback. A **bench-only reference model** (the comparison bench's ridge regression, see the
`surrogate-comparison-bench` capability) is not a shipped model: it is never written as a checkpoint,
never loaded by the trainer, and never presented as the Track B surrogate. Model construction and the
training loop SHALL be seeded. The model and training functions SHALL import `torch`/`physicsnemo`
lazily so the surrounding module imports without the optional `train` dependency-group installed.

The trainer SHALL accept `phase_harmonics` (default `1`), validated before any file is read or
written, and pass it explicitly (also at the default) to every per-seed fit, which passes it to
`build_features` and builds the model with `n_in = 3 + 2H`; the CLI SHALL expose it as
`--phase-harmonics` (default `1`). Two public seams SHALL serve callers that need another split:

- `fit_seed(df, split, *, seed, phase_harmonics, ...)` fits one seed on a caller-supplied
  `SplitAssignment`, used verbatim. The per-seed fit with no split calls
  `make_config_splits(df, seed=seed, n_val_configs=...)` exactly once, as before, so the default
  path's inputs, RNG consumption and outputs are unchanged. With an explicit split it SHALL NOT
  call `make_config_splits`. An invalid split (an empty train, validation or test list, overlapping
  lists, or configurations absent from the frame) SHALL raise `ValueError` before any `torch` import;
  an empty validation list is rejected because it would silently skip the best-validation restore.
- `predict_frame(fit, frame)` builds features for arbitrary rows with the fit's own harmonic count
  (from its `feature_names`) and standardisers and returns predictions in coefficient units.

#### Scenario: Module imports without the training dependency-group

- **Given** an environment where `torch`/`nvidia-physicsnemo` are **not** installed (the CI runner)
- **When** `mosquito_cfd.force_surrogate.train` is imported and its pure helpers (`build_features`, `filter_converged_beat`, `make_config_splits`, `Standardizer`, `compute_metrics`) are called
- **Then** the import succeeds and the helpers run — no `torch`/`physicsnemo` import is triggered until a model/training function is invoked

#### Scenario: Model constructs with the right shape (GPU tier)

- **Given** the optional `train` group installed and a CUDA device available
- **When** `build_model(n_in=5, n_out=6, seed=...)` and `build_model(n_in=9, n_out=6, seed=...)` are called and a batch of matching-width inputs is passed through each
- **Then** a PhysicsNeMo model is constructed each time and the forward pass returns a 6-wide output per input row

#### Scenario: Seeded training reduces loss (GPU/torch tier)

- **Given** the model and a small standardized training batch
- **When** `train_model` runs for a handful of seeded steps
- **Then** the final training loss is strictly less than the initial loss (the loop learns) — the CPU-device determinism of this loop is asserted separately under the reproducibility requirement, not here

#### Scenario: The harmonic count reaches every seed

- **Given** `run_training` with `_fit_one_seed` replaced by a recorder (torch-free)
- **When** it is called with `phase_harmonics=3`, and again with no `phase_harmonics`
- **Then** every seed's recorded call carries `phase_harmonics=3` in the first case and `phase_harmonics=1` in the second, the second run's other recorded arguments and `metrics.json` keys equal those of the pre-change trainer, and `scripts/train_surrogate.py` parses `--phase-harmonics 3` to 3 and defaults to 1

#### Scenario: Invalid harmonic counts fail before any I/O

- **Given** `phase_harmonics` of 0, `True` or 2.5
- **When** `run_training` is called with an output directory that does not exist
- **Then** it raises before reading the dataset, and the output directory is still absent

#### Scenario: The per-seed seams are torch-free up to the model

- **Given** `build_model`, `train_model` and `predict` replaced by recorders (CPU tier) and the committed fine dataset after `filter_converged_beat`
- **When** the per-seed fit runs with no split; `fit_seed` runs with `make_config_splits(df, seed=s, n_val_configs=3)` and `phase_harmonics=1`; `fit_seed` runs with a face split and `phase_harmonics=3`; and `fit_seed` runs with an invalid split
- **Then** the first calls `make_config_splits` once and passes `build_model` `n_in = 5` and training inputs byte-identical to a frozen copy of the pre-change construction; the second, for each seed 1234–1238, passes `build_model`, `train_model` and `predict` arrays byte-identical to the first's; the third calls `make_config_splits` zero times, uses the given lists verbatim, fits the standardisers on that split's training rows and passes `n_in = 9`; the fourth raises `ValueError` before any recorder is called and without importing `torch`

#### Scenario: predict_frame builds the fit's own features (CPU tier)

- **Given** a fit object with a 9-name `feature_names` list and known standardisers, and `predict` replaced by a recorder
- **When** `predict_frame` is called on a frame, and on a frame missing a kinematics column
- **Then** the recorder receives the standardised 9-column matrix, the output is the inverse-transformed recorder output, and the second call raises `ValueError` naming the missing column

#### Scenario: predict_frame reproduces the fit's own predictions (GPU tier)

- **Given** fitted `phase_harmonics = 1` and `phase_harmonics = 3` seeds
- **When** `predict_frame` is called on each seed's test rows in one batch
- **Then** its output equals the fit's own test predictions bitwise

#### Scenario: The bench path trains like run_training (GPU tier)

- **Given** the committed fine dataset and a short epoch count
- **When** the default per-seed fit runs first in a fresh subprocess, and, in another process, an unrelated fit, a `predict_frame` call on the 256-phase grid and a timing loop run before `fit_seed` on the interpolation split for the same seed
- **Then** the two fits' test predictions are bitwise equal; a difference halts the change, because it would mean fit order changes results

### Requirement: Phase-only baseline skill in metrics.json

The trainer SHALL report, per target, the surrogate's **skill over a phase-only baseline**,
`skill = 1 − SSE(surrogate) / SSE(phase-only baseline)` over the scored holdout rows, in a top-level
`metrics.json` block `phase_baseline_skill`, because pointwise R² alone is dominated by the wingbeat
waveform that a predictor knowing only the phase already captures (CC-4).

The phase-only baseline SHALL be built from the `split == "train"` configurations only (all of them,
independent of the seed's validation carve; never a holdout row) unless the caller passes an explicit
`reference_configs` list, in which case it SHALL be built from exactly those configurations, the
definition block SHALL record `reference_split: "explicit"`, and every listed configuration SHALL
exist in the frame and appear once (else `ValueError`). With no list the result and definition block SHALL be bitwise
identical to the behaviour before this option existed. Built on the converged beat
(`wingbeat ≥ CONVERGED_MIN_WINGBEAT`): each converged beat, sorted by phase, is periodically
interpolated (`period = 1`) to the query phases; a configuration's curve is the mean of its beats'
curves; the baseline is the **equal-weight** mean of the configuration curves. The block SHALL record
the baseline's definition (`kind`, `reference_split`, `reference_configs`, `weighting`,
`converged_min_wingbeat`) under `phase_baseline` and, per target, `skill`, `phase_baseline_rmse` and
`phase_baseline_r2`. Skill SHALL NOT be clipped; if the baseline's SSE is at or below the
scale-relative `_VARIANCE_EPS · Σ t²` floor, skill SHALL be the NaN sentinel serialized as `null`.
The computation SHALL be pure numpy/pandas (torch-free, CI tier) and SHALL reject malformed input
with `ValueError` rather than emit a NaN.

#### Scenario: Baseline is the equal-weight mean of periodic per-config interpolants

- **Given** two reference configurations sampling known periodic curves at different rates (one with three times the rows of the other), with rows supplied out of phase order
- **When** the baseline is evaluated at query phases including one between a configuration's last sample and phase 1
- **Then** it equals the unweighted mean of the two configurations' periodic linear interpolants at each query phase (known answer), including the wrapped query, so the denser configuration does not dominate and row order does not matter

#### Scenario: Beats are averaged within a configuration and the startup beat is excluded

- **Given** a reference configuration with two converged beats and a startup beat (`wingbeat < CONVERGED_MIN_WINGBEAT`), and a second configuration with one converged beat
- **When** the baseline is built
- **Then** the first configuration contributes the mean of its two converged beats' curves, counted once against the second configuration, and the startup rows have no effect

#### Scenario: Holdout rows never enter the baseline

- **Given** a dataset whose holdout configurations carry extreme coefficients
- **When** the baseline is built
- **Then** it is bitwise identical to the baseline built with the holdout rows removed, and `reference_configs` lists exactly the sorted `split == "train"` configurations

#### Scenario: An explicit reference list overrides the split column

- **Given** a dataset and an explicit `reference_configs` list that includes one `split == "holdout"` configuration and omits two `split == "train"` ones
- **When** the baseline is built with that list
- **Then** it equals the equal-weight mean over exactly the listed configurations, the definition records `reference_split: "explicit"` and the sorted list, the call without a list is unchanged bitwise (compared against a frozen copy of the pre-change output on a toy frame), and a list naming a configuration absent from the frame, naming one twice, or an empty list, raises `ValueError`

#### Scenario: Skill known answers, sentinel and degenerate input

- **Given** true values, a phase-only baseline prediction and a surrogate prediction
- **When** skill is computed
- **Then** a surrogate equal to the truth scores 1, a surrogate equal to the baseline scores 0, a surrogate with twice the baseline's squared error scores −1 (unclipped), a baseline equal to the truth yields the `null` sentinel, and zero rows or mismatched array shapes raise `ValueError`

#### Scenario: Malformed reference or query data is rejected

- **Given** a reference set with no configurations, a beat with fewer than 2 rows, a duplicate phase within a beat, a non-finite value, or a reference or query phase that is non-finite or outside `[0, 1)`
- **When** the baseline is built
- **Then** it raises `ValueError` naming the problem rather than returning an interpolant

### Requirement: Committed training artifacts

The training run SHALL produce four artifacts under the corpus's surrogate directory (`examples/prelim_sweep/surrogate/`,
`examples/prelim_sweep_fine/surrogate/`, or the fine corpus's alternative `examples/prelim_sweep_fine/surrogate_h3/`): a `metrics.json`, a
holdout-**predictions** parquet, a trained **model checkpoint**, and a `run_metadata.json`. The
predictions parquet SHALL carry the holdout identifiers and both true and predicted coefficients so
the downstream figure consumes a versioned prediction file rather than re-running inference.

#### Scenario: Predictions parquet schema

- **Given** a completed holdout evaluation
- **When** the predictions parquet is written and re-read
- **Then** it has columns `config_name, time, phase, wingbeat` plus, for each of the six coefficients, a `CF_*_true` and a `CF_*_pred` column, with one row per scored holdout (config × timestep) on the converged beat
- **And** every `config_name` in the predictions parquet is one of the 6 holdout configuration names (no train/validation row leaks into the predictions file)

#### Scenario: All four artifacts are written

- **Given** a full training driver run into a temporary output directory
- **When** the run completes
- **Then** `metrics.json`, the holdout-predictions parquet, the model checkpoint, and `run_metadata.json` all exist and re-load, and the parquet's true coefficients match the dataset's holdout `CF_*` values for the same (config, timestep) rows

### Requirement: Committed evidence-figure artifacts with provenance

The figure generator SHALL produce three artifacts under the corpus's figures directory (`examples/prelim_sweep/figures/`,
`examples/prelim_sweep_fine/figures/`, or `examples/prelim_sweep_fine/figures_h3/` for the `surrogate_h3/` model): the
`evidence_figure.png`, an `evidence_figure_metrics.json` carrying the per-axis surrogate RMSE, the
quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), the plotted seed
(`primary_seed`) and seed count (`n_seeds`), for **all six** targets the skill over the phase-only
baseline (`skill.<c>` with `committed`, `min`, `max`), the surrogate's pointwise R²
(`pointwise_r2.<c>`) and the phase-only baseline's pointwise R² (`phase_baseline_pointwise_r2.<c>`),
the skill floor (`skill_floor` with its `value` and `targets_below_phase_baseline`), so that every
number the caption prints is recorded, and the speedup-derivation inputs (the batched throughput,
the per-config rows-per-wingbeat, the CFD per-wingbeat cost used (`cfd_seconds_per_wingbeat`), the single-row latency, and both
realized factors with their units); and a `run_metadata.json` emitted via
`capture_surrogate_run_metadata` requiring a pinned container **digest** and a **caller-supplied**
timestamp (CC-1), recording the hash of the consumed inputs (the predictions parquet and
metrics.json) and the seeds read from `metrics.json` `seed_sweep`, plus the grid profile name (`grid`), the CFD
cost per step supplied (`cfd_seconds_per_step`, `null` for a fixed-cost profile) and the CFD
per-wingbeat cost used (`cfd_seconds_per_wingbeat`); a record without those keys (the committed
coarse figure's, which predates them) SHALL be read as `coarse` / 144 s. The `fine` profile requires
a CFD cost per step and has no default; the `coarse` profile's cost is fixed at 144 s per wingbeat
and it takes no per-step cost. Generation with a missing fine per-step cost, a non-finite or
non-positive one, a per-step cost for the coarse profile, or an unknown profile name SHALL raise
`ValueError` before any artifact is written. The caption builder SHALL likewise reject a speedup
whose per-wingbeat cost does not fit its profile (the coarse label over a cost other than 144 s,
or the fine label over 144 s). The sidecar key set SHALL be the same for both profiles. The sidecar SHALL NOT carry
configuration-resolved R², which the figure no longer displays. The JSON sidecars SHALL be written
**LF-newline UTF-8** (as `write_units_sidecar` does) so the committed artifacts do not churn between
Windows authoring and Linux CI.

#### Scenario: All three artifacts write and re-load with the documented content

- **Given** a figure-generation run into a temporary output directory
- **When** the run completes
- **Then** `evidence_figure.png`, `evidence_figure_metrics.json`, and `run_metadata.json` all exist and re-load, and `evidence_figure_metrics.json` carries the per-axis surrogate RMSE, the quasi-steady reference block (`overshoot_factor` + `baseline_rmse_cf_z`), `primary_seed`, `n_seeds`, the six targets' `skill`, `pointwise_r2` and `phase_baseline_pointwise_r2`, the `skill_floor`, and the speedup inputs — equal to what the figure displays and to `metrics.json` — and carries no `config_mean_r2` key

#### Scenario: Every number in the caption is in the sidecar

- **Given** a generated figure
- **When** the caption's plotted seed, seed count, phase-only baseline R² values, skill floor and off-panel `CF_mx`/`CF_mz` skill are compared with `evidence_figure_metrics.json`
- **Then** each equals (within display rounding) the sidecar's recorded value

#### Scenario: Provenance records a pinned digest, caller timestamp and the metrics' seeds

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and a metrics.json with a `seed_sweep` block
- **When** the figure provenance is captured
- **Then** `run_metadata.json` records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, a hash of the consumed predictions parquet + metrics.json, and seeds equal to `{"global": seed_sweep.primary_seed, "sweep": seed_sweep.seeds[1:]}`

#### Scenario: JSON sidecars are written LF-newline UTF-8

- **Given** the figure-generation run on any host (including Windows)
- **When** `evidence_figure_metrics.json` and `run_metadata.json` are written
- **Then** they use LF line endings and UTF-8 encoding (no CRLF), so the committed artifacts are byte-stable across the Windows authoring host and the Linux CI runner

#### Scenario: Mutable image tag is rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** the figure provenance is captured
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording provenance without a pinned image

#### Scenario: A fine figure without a CFD cost writes nothing

- **Given** the `fine` grid profile and no CFD cost per step (or 0, a negative value, NaN or inf), the `coarse` profile given a per-step cost, or an unknown profile name
- **When** figure generation is invoked
- **Then** it raises `ValueError` and the output directory contains no artifact

### Requirement: Fine-corpus surrogate and evidence figure are committed with a reproducibility gate

The fine corpus `examples/prelim_sweep_fine/` SHALL carry a trained force surrogate in
`surrogate/` (`surrogate.pt`, `holdout_predictions.parquet`, `metrics.json`, `run_metadata.json`)
and an evidence figure in `figures/` (`evidence_figure.png`, `evidence_figure_metrics.json`,
`run_metadata.json`), mirroring the coarse corpus's layout. The surrogate was trained by the
trainer as it stood before `add-surrogate-comparison-bench` (that change adds options whose defaults
leave the trainer's output unchanged), with the coarse run's hyperparameters and
seeds (2000 epochs, primary seed 1234, sweep seeds 1235–1238, 3 validation configurations),
differing only in the dataset, the output directory and the container digest, which SHALL be the
fine corpus's own (`examples/prelim_sweep_fine/run_metadata.json` `docker_image`, the image that
produced the data, as for the coarse surrogate). The figure SHALL be generated with the `fine` grid
profile.

Before any fine binary is committed, the full 5-seed training SHALL be run twice from the same
clean, committed tree into two scratch directories outside the repository, and SHALL pass this
gate: `surrogate.pt` and `holdout_predictions.parquet` byte-identical; `metrics.json` equal as
parsed JSON apart from the wall-clock fields of the top-level `inference` block (its `basis` SHALL
also be equal); `run_metadata.json` equal apart from `run_id`; and both records naming the same
40-hex commit with `dirty: false`. A failure SHALL halt the change for a decision; the gate SHALL
NOT be loosened to pass. Passing it is an observed outcome for this run on this host, **not** a
bitwise-reproducibility claim: `reproducibility.bitwise` stays `cpu_only` and the "Training
reproducibility and provenance" requirement is unchanged. The same gate SHALL apply to the fine
corpus's alternative `surrogate_h3/` model.

#### Scenario: The fine surrogate is the committed fine dataset's, trained with the coarse run's settings

- **Given** the committed `examples/prelim_sweep_fine/surrogate/` artifacts, `dataset.parquet` and `run_metadata.json`
- **When** the committed-artifact tests run
- **Then** every holdout `<target>_true` equals the fine dataset on `(config_name, time)` for all six targets, `inputs.hash` is the fine dataset's sha256, the surrogate's `docker_image` equals the fine corpus's, `seed_sweep.seeds == [1234, 1235, 1236, 1237, 1238]`, the recorded epochs are 2000, each run has 3 `val_configs` equal to the split recomputed from the fine dataset, `reproducibility.bitwise == "cpu_only"`, and `phase_baseline_skill` recomputes from the committed predictions and fine dataset

- **And** in the pinned stale-by-sign state of "Committed surrogate artifacts are tied to the dataset they were trained on", only the `<target>_true`, `inputs.hash` and `phase_baseline_skill` clauses above are replaced by that requirement's stale-by-sign clauses; every other clause still holds

#### Scenario: The fine figure is tied to the fine surrogate and regenerates from it

- **Given** the committed fine figure artifacts and the committed fine surrogate outputs
- **When** the committed-artifact tests run
- **Then** the figure's `run_metadata.json` hashes the fine `holdout_predictions.parquet` and `metrics.json` and records `grid == "fine"`, and regenerating the sidecar from the committed fine predictions and metrics with the `fine` profile and the recomputed fine CFD cost reproduces the committed `evidence_figure_metrics.json` (exact for copied values, relative 1e-12 for the two computed quasi-steady RMS values)

#### Scenario: Reruns that differ halt the change

- **Given** two full fine training runs from the same commit whose `surrogate.pt` or `holdout_predictions.parquet` bytes differ, whose `metrics.json` differ outside the `inference` wall-clock fields, whose `run_metadata.json` differ outside `run_id`, or either of which records `dirty: true`
- **When** the gate is evaluated
- **Then** no fine artifact is committed and the change stops for a decision with the user

## ADDED Requirements

### Requirement: Committed phase-harmonics surrogate beside the shipped one

The fine corpus SHALL carry a second trained surrogate with `phase_harmonics = 3` in
`examples/prelim_sweep_fine/surrogate_h3/` (`surrogate.pt`, `holdout_predictions.parquet`,
`metrics.json`, `run_metadata.json`) and its evidence figure, written by the unchanged generator with
the `fine` profile, in `examples/prelim_sweep_fine/figures_h3/` (`evidence_figure.png`,
`evidence_figure_metrics.json`, `run_metadata.json`). It SHALL be trained with the shipped fine
surrogate's settings (epochs, seeds, validation configurations and the fine corpus's container
digest, as that requirement states them), differing only in `phase_harmonics` and the
output paths, and SHALL pass the twice-run gate of "Fine-corpus surrogate and evidence figure are
committed with a reproducibility gate" before it is committed. Both runs SHALL start from a clean
tree whose commit is on `main`. The dataset reconciliation of "Committed surrogate artifacts are tied
to the dataset they were trained on" SHALL apply to `surrogate_h3/` unconditionally (it has no
stale-by-sign state). The fine README SHALL state that the shipped surrogate is the
`phase_harmonics = 1` model and that the `h3` model is an alternative, trained on the same 2-beat
corpus. Its harmonic count was chosen in the exploration after holdout scores had been seen
(holdout-informed), so its result on the labelled holdouts is optimistic.

#### Scenario: The h3 surrogate is self-describing and tied to the dataset

- **Given** the committed `surrogate_h3/metrics.json`, `run_metadata.json` and `holdout_predictions.parquet`
- **When** the CPU-tier provenance test reads them
- **Then** `phase_harmonics_from_features` of the recorded feature list is 3 with 9 entries, the seeds are 1234–1238, epochs 2000, 3 validation configurations per seed equal to the split recomputed from the dataset, `inputs.hash` equals the committed fine `dataset.parquet`'s sha256, every `<target>_true` equals the dataset, and the record names a clean 40-hex commit on a branch other than `main`
- **And** on the GPU tier the checkpoint's `feature_names` equal the recorded list

#### Scenario: The h3 figure is tied to the h3 surrogate

- **Given** the committed `figures_h3/` artifacts
- **When** the committed-artifact tests run
- **Then** the figure's `run_metadata.json` hashes `surrogate_h3/holdout_predictions.parquet` and `surrogate_h3/metrics.json` and records `grid == "fine"`

#### Scenario: The h3 binaries passed the twice-run gate

- **Given** two full 5-seed `phase_harmonics = 3` trainings from the same clean tree into two scratch directories outside the repository
- **When** their outputs are compared under the gate
- **Then** `surrogate.pt` and `holdout_predictions.parquet` are byte-identical and the JSON files equal apart from the documented wall-clock and `run_id` fields, and the comparison is recorded in the fine README and the PR body
