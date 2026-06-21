## ADDED Requirements

### Requirement: Held-out-configuration train/validation/test split

The force-surrogate trainer SHALL evaluate on **held-out configurations**, not held-out timesteps
within a run (CC-4). The 6 configurations labelled `split == "holdout"` in the dataset (carried
verbatim from `sweep_manifest.json`) SHALL be the **test** set and SHALL NOT be used for training or
model selection. A **configuration-level validation** set SHALL be carved from the 21 training
configurations by a seeded selection for early-stopping / model selection. The three configuration
sets (train, validation, test) SHALL be mutually disjoint, and the assignment SHALL be reproducible
from the seed. (This is the **model-side** split that *consumes* the `split` label; it is distinct
from the sweep-generation requirement *Held-out configuration split is seeded, non-corner, and
label-only*, which *assigns* that label at sweep-generation time.) A dataset missing the `split`
column, with no `holdout` configurations, or whose seeded validation carve would be empty SHALL
raise a clear `ValueError` rather than silently producing an empty test or validation set.

#### Scenario: Holdout configs are exactly the dataset holdout label

- **Given** the committed dataset whose 6 `split == "holdout"` configurations are `s35_f085_p45, s45_f085_p60, s45_f100_p60, s45_f115_p60, s55_f085_p45, s55_f115_p45`
- **When** `make_config_splits` is called
- **Then** the **test** configuration set equals exactly those 6 names, taken from the `split` column (never re-derived), and no holdout configuration appears in the train or validation sets

#### Scenario: Validation is carved at the configuration level from the training configs

- **Given** the 21 `split == "train"` configurations
- **When** `make_config_splits` is called with a fixed seed
- **Then** a non-empty validation set of **whole configurations** is selected from those 21 (every row of a validation configuration is a validation row — no configuration is split across train and validation), the train and validation configuration sets are disjoint and together cover all 21 training configurations, and neither contains any holdout configuration

#### Scenario: Split is seed-reproducible and seed-sensitive

- **Given** the same dataset
- **When** `make_config_splits` is called twice with the same seed, then once with a different seed
- **Then** the two same-seed calls produce identical train/validation/test configuration sets, and the different-seed call leaves the **test** set unchanged (it is always the 6 holdout configs) while it MAY change which training configs are held for validation — proving the holdout set is fixed by the label and only the validation carve is seeded
- **And** the seeded validation carve selects configurations from the **sorted** unique config-name list (`sorted(unique(config_name))`) before sampling, so the selection is reproducible across pandas versions (not dependent on groupby/unique row order)

#### Scenario: Malformed split raises rather than silently emptying a set

- **Given** a dataset that is missing the `split` column, has zero `split == "holdout"` configurations, or is so small that the seeded validation carve would select zero configurations
- **When** `make_config_splits` is called
- **Then** it raises a clear `ValueError` naming the problem (no `split` column / no holdout configs / empty validation carve) rather than returning an empty test or validation set that would silently train on a malformed corpus

### Requirement: Surrogate input and target construction

The trainer SHALL build inputs and targets from the dataset without re-deriving any coefficient math
(CC-3 — it consumes the dataset's already-normalized `CF_*` columns). Inputs SHALL be
`[stroke_amp_deg, frequency_fstar, pitch_amp_deg, sin(2π·phase), cos(2π·phase)]` (cyclic phase
encoding; **Reynolds is excluded** because it is a deterministic function of `(φ, f*)` under the
ν\*-fixed policy and carries no independent information). Targets SHALL be the six coefficients
`CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`. The trainer SHALL filter to the **converged beat**
(`wingbeat ≥ 1`) before training and evaluation. Feature and target standardization statistics SHALL
be fit on **training rows only** (no validation/holdout leakage).

#### Scenario: Feature columns are the kinematics knobs plus cyclic phase

- **Given** a dataset slice
- **When** `build_features` is called
- **Then** the returned feature matrix has exactly five columns named `stroke_amp_deg, frequency_fstar, pitch_amp_deg, phase_sin, phase_cos`, where `phase_sin = sin(2π·phase)` and `phase_cos = cos(2π·phase)`, and **no** `reynolds` column is present

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
fallback. Model construction and the training loop SHALL be seeded. The model and training functions
SHALL import `torch`/`physicsnemo` lazily so the surrounding module imports without the optional
`train` dependency-group installed.

#### Scenario: Module imports without the training dependency-group

- **Given** an environment where `torch`/`nvidia-physicsnemo` are **not** installed (the CI runner)
- **When** `mosquito_cfd.force_surrogate.train` is imported and its pure helpers (`build_features`, `filter_converged_beat`, `make_config_splits`, `Standardizer`, `compute_metrics`) are called
- **Then** the import succeeds and the helpers run — no `torch`/`physicsnemo` import is triggered until a model/training function is invoked

#### Scenario: Model constructs with the right shape (GPU tier)

- **Given** the optional `train` group installed and a CUDA device available
- **When** `build_model(n_in=5, n_out=6, seed=...)` is called and a batch of 5-feature inputs is passed through it
- **Then** a PhysicsNeMo model is constructed and the forward pass returns a 6-wide output per input row

#### Scenario: Seeded training reduces loss (GPU/torch tier)

- **Given** the model and a small standardized training batch
- **When** `train_model` runs for a handful of seeded steps
- **Then** the final training loss is strictly less than the initial loss (the loop learns) — the CPU-device determinism of this loop is asserted separately under the reproducibility requirement, not here

### Requirement: Held-out evaluation metrics

The trainer SHALL evaluate the trained model on the **holdout configurations** (converged beat) and
emit a `metrics.json` reporting, for each of the six coefficients, the RMSE, MAE, and R²; an
aggregate across targets; a **per-configuration** breakdown over the 6 holdout configs; and an
inference latency/throughput measurement (for the downstream >1,000× inference-vs-CFD speedup
annotation). Metric computation SHALL be pure **numpy** (no scipy/sklearn — they are not project
dependencies and would break the CPU CI tier) and SHALL operate on inverse-transformed
(physical-coefficient) predictions. For a target with (near-)zero variance, R² SHALL be a documented
sentinel (NaN, serialized as `null`) rather than an unhandled `0/0`, and the `aggregate` block SHALL
be NaN-aware (it skips a sentinel R² rather than propagating it, so one constant target does not
poison the aggregate).

#### Scenario: Metrics math is correct on known arrays

- **Given** target and prediction arrays with an analytically known RMSE, MAE, and R²
- **When** `compute_metrics` is called
- **Then** the returned RMSE, MAE, and R² equal the known values within floating tolerance, for each target independently

#### Scenario: Constant-target R² is a defined sentinel, not an unhandled divide-by-zero

- **Given** a target column whose true values have (near-)zero variance — as `CF_y` and the off-axis moments may be by symmetry (design D4)
- **When** `compute_metrics` is called
- **Then** that target's R² is the documented sentinel (NaN, serialized as `null` in `metrics.json`) rather than an unhandled `0/0`, while its RMSE and MAE remain finite — so `metrics.json` serializes without a crash, and the `aggregate` R² skips the sentinel (NaN-aware) so it is not silently NaN-poisoned

#### Scenario: metrics.json carries per-target, aggregate, per-config, and inference keys

- **Given** a completed evaluation on the holdout configs
- **When** `metrics.json` is written and re-read
- **Then** it contains a `per_target` block keyed by `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` (each with `rmse`, `mae`, `r2`), an `aggregate` block, a `per_config` block keyed by the 6 holdout configuration names, an `inference` block with a `latency_ms` field (single-row forward-pass latency in milliseconds) and a `throughput_rows_per_s` field (batched rows per second) each carrying the timing basis so the downstream >1,000× speedup annotation is auditable, and a `reproducibility` block recording the seeds, the feature list, and the `bitwise` scope key (`"cpu_only"`) — these are CPU-computable, so the CI tier asserts the block's presence even when the model timing is a placeholder

#### Scenario: Evaluation uses only holdout configurations

- **Given** the split assignment
- **When** the holdout metrics are computed
- **Then** every row scored is from a `split == "holdout"` configuration on the converged beat, and no training or validation row contributes to the reported holdout metrics (CC-4)

### Requirement: Config-resolved (phase-honest) evaluation metrics

The surrogate evaluation SHALL additionally report **config-resolved** metrics in `metrics.json`,
because the pointwise aggregate R² is dominated by the within-beat force **waveform** — a smooth
periodic shape shared across all configurations and therefore largely "free" to learn — and on its
own **overstates** the surrogate's skill at the kinematics→force *map* (the genuinely held-out
config-to-config dependence) (CC-4 scientific honesty). The evaluation SHALL carry, per target, a
`config_resolved` block reporting (a) `config_mean_r2` — the R² computed on the per-configuration
**cycle-mean** coefficient (the phase-removed config-to-config skill, the physically-central
cycle-averaged force) — and (b) `within_config_variance_fraction` — the fraction of total holdout
variance that is within-configuration (the waveform), which exposes how much of the aggregate R² is
waveform-driven. These SHALL be pure-numpy, computed on the inverse-transformed predictions grouped
by `config_name`, and reported **alongside** (never instead of) the aggregate.

#### Scenario: config_resolved block is present per target

- **Given** a completed holdout evaluation
- **When** `metrics.json` is written and re-read
- **Then** it contains a `config_resolved` block keyed by `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz`, each carrying a `config_mean_r2` and a `within_config_variance_fraction` — distinct from, and reported in addition to, the pointwise `per_target`/`aggregate` blocks

#### Scenario: config-resolved quantities match known-answer arrays

- **Given** two configurations whose true coefficients are `[1, 3]` (mean 2) and `[5, 7]` (mean 6), with predicted per-configuration cycle-means of `2` and `5`
- **When** the config-resolved metrics are computed
- **Then** `within_config_variance_fraction == 0.2` (within-config SS 4 / total SS 20) and `config_mean_r2 == 0.875` (`1 - 1/8`) — exact known answers, confirming the phase/config decomposition is correct and not a re-label of the inflated aggregate

#### Scenario: A constant per-configuration mean yields the R² sentinel, not garbage

- **Given** holdout configurations whose per-configuration cycle-means are (near-)identical (zero between-config variance)
- **When** `config_mean_r2` is computed
- **Then** it is the documented NaN sentinel (serialized as `null`) rather than an unhandled `0/0`, consistent with the pointwise R² sentinel (`_VARIANCE_EPS` floor)

### Requirement: Training reproducibility and provenance

The training run SHALL be seeded (python/numpy/torch) with `torch.use_deterministic_algorithms`
enabled, and SHALL emit a `run_metadata.json` via `capture_surrogate_run_metadata` requiring a pinned
container **digest** and a **caller-supplied** timestamp (CC-1). The metadata SHALL record the seeds,
and — on the training host where the `train` group is installed — the resolved `torch`/`physicsnemo`
versions. Bitwise reproducibility SHALL be claimed only for the CPU path; the GPU run SHALL be
documented as seeded-but-not-bitwise. `wandb` logging SHALL default to **disabled** (a no-op,
without importing `wandb`) and SHALL be opt-in to online; an online wandb failure SHALL NOT block or
truncate the committed `metrics.json`.

#### Scenario: Provenance records digest, timestamp, and seeds (CI tier, no train group)

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and the run seeds
- **When** the training provenance is captured **without** the `train` group installed
- **Then** the metadata records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, and the seeds (the `torch`/`physicsnemo` version fields are absent/`null`, not asserted on this tier)

#### Scenario: Resolved library versions recorded on the training host (torch tier)

- **Given** the `train` group installed (the A5000/WSL2 training host)
- **When** the training provenance is captured
- **Then** it additionally records the resolved `torch` and `physicsnemo` version strings, so the GPU run's environment is auditable from metadata even though it is not bitwise-reproducible

#### Scenario: Mutable image tag rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** the training provenance is captured
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording provenance without a pinned image

#### Scenario: Torch-free CPU helpers are bitwise-reproducible (CI tier)

- **Given** the torch-free CPU code paths only (feature build, standardization, config split, metrics) — no `torch` import
- **When** they are run twice with the same seed
- **Then** their outputs are bitwise-identical — this is the CI-gating determinism check, runnable without the `train` group

#### Scenario: Seeded training step is deterministic on the CPU torch device (torch tier)

- **Given** the `train` group installed and the model placed on the CPU torch device
- **When** a seeded `train_model` step is run twice with the same seed
- **Then** the two loss trajectories are identical, and `metrics.json` records `reproducibility.bitwise == "cpu_only"` to scope the claim honestly (the CUDA/GPU run is seeded but not asserted bitwise — cuDNN/TF32 nondeterminism)

#### Scenario: wandb is disabled by default without importing wandb

- **Given** the trainer invoked in the default `disabled` mode (the CI/rerun default) with the `wandb` import barred
- **When** training runs
- **Then** the wandb-gating path is a no-op that does **not** import `wandb` (no `ImportError` on a host without it), and the run completes and writes `metrics.json` with no wandb network call

#### Scenario: wandb online failure does not block metrics.json

- **Given** `--wandb online` selected but no reachable/authenticated wandb backend
- **When** training runs
- **Then** `metrics.json` is still written in full from local state (no missing or partial fields) — the committed artifact never depends on the wandb call succeeding

### Requirement: Committed training artifacts

The training run SHALL produce four artifacts under `examples/prelim_sweep/`: a `metrics.json`, a
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

### Requirement: Two-tier cluster-free and GPU-gated tests

The trainer SHALL be tested in two tiers. The **CPU tier** SHALL be cluster-free (CC-2) — no RunAI,
no GPU, no plotfiles, no `train` dependency-group — and SHALL gate CI, covering feature/target
construction, the converged-beat filter, the configuration split, standardization-leakage,
metric math, the artifact schemas, and the provenance digest guard. The **GPU tier** SHALL be marked
with a registered `gpu` pytest marker that **auto-skips** when CUDA is unavailable or `physicsnemo`
is not importable, and CI SHALL additionally deselect it (`-m "not gpu"`), so no GPU-bound test can
block CI.

#### Scenario: GPU tests skip on a CPU-only host

- **Given** a host with no CUDA device or without `physicsnemo` installed (the CI runner)
- **When** the test suite runs
- **Then** every `@pytest.mark.gpu` test is skipped (not failed, not errored), and the CPU-tier tests run and pass

#### Scenario: CI deselects the GPU marker explicitly

- **Given** the CI pytest invocation
- **When** it is configured
- **Then** it passes `-m "not gpu"` so GPU tests are deselected regardless of the runner's hardware, and the `gpu` marker is registered in `[tool.pytest.ini_options]` (no unknown-marker warning)

### Requirement: Force-only training scope guard

The trainer SHALL consume **only** the tidy `dataset.parquet` (kinematics + phase + coefficients) and
SHALL NOT read AMReX plotfiles or velocity/pressure fields, build a DoMINO/latent-dynamics encoder,
or integrate any RL loop (CC-6). It is the instantaneous kinematics(+phase) → force-coefficient
regressor only.

#### Scenario: Training consumes only the dataset parquet

- **Given** the training inputs
- **When** the trainer runs
- **Then** it requires only `examples/prelim_sweep/dataset.parquet` (and its units sidecar) — it neither accepts nor requires a plotfile/field path — and it produces force-coefficient predictions only, with no field reconstruction, no latent-dynamics state, and no RL interaction
