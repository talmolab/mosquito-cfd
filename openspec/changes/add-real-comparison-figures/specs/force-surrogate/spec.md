## MODIFIED Requirements

### Requirement: Training reproducibility and provenance

The training run SHALL be seeded (python/numpy/torch) with `torch.use_deterministic_algorithms`
enabled, and SHALL emit a `run_metadata.json` via `capture_surrogate_run_metadata` requiring a pinned
container **digest** and a **caller-supplied** timestamp (CC-1). The metadata SHALL record the seeds
(at top level) and, under `library_versions`, the resolved `python`, `numpy`, `pandas` and `pyarrow`
versions on every host and — on the training host where the `train` group is installed — the
resolved `torch`/`physicsnemo` versions. The `python` version SHALL be `platform.python_version()`;
each package version SHALL be read from installed-package metadata without importing the package,
and SHALL be `null` when the package is not installed. Surrogate records committed before these
fields existed SHALL NOT be rewritten. Bitwise reproducibility SHALL be claimed only for the CPU path;
the GPU run SHALL be documented as seeded-but-not-bitwise. `wandb` logging SHALL default to
**disabled** (a no-op, without importing `wandb`) and SHALL be opt-in to online; an online wandb
failure SHALL NOT block or truncate the committed `metrics.json`.

#### Scenario: Provenance records digest, timestamp, and seeds (CI tier, no train group)

- **Given** a container image digest containing `sha256:`, a caller-supplied ISO-8601 timestamp, and the run seeds
- **When** the training provenance is captured **without** the `train` group installed
- **Then** the metadata records the git commit, the supplied digest under `docker_image`, the `timestamp` equal to the supplied value verbatim, and the seeds (the `torch`/`physicsnemo` version fields are absent/`null`, not asserted on this tier)

#### Scenario: The Python data stack is recorded on every host (CI tier)

- **Given** the CI environment, without the `train` group
- **When** the training provenance is captured
- **Then** `library_versions` records `python` equal to `platform.python_version()` and `numpy`, `pandas` and `pyarrow` equal to `importlib.metadata.version` of each, all non-null strings, and `seeds` remains a top-level key

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

#### Scenario: An uninstalled package is recorded as null

- **Given** `importlib.metadata.version` raising `PackageNotFoundError` for `pyarrow`
- **When** the training provenance is captured
- **Then** `library_versions.pyarrow` is `null` and the other keys are unaffected

## ADDED Requirements

### Requirement: The coarse README's quasi-steady paragraph reports both grids' ratios

The coarse README's quasi-steady bullet SHALL state the coarse and fine RMS ratios of the model.
The bullet is the text in `examples/prelim_sweep/README.md` from the first line containing
`The Sane–Dickinson` (matched after whitespace collapse) to the line before the next top-level
`- **` bullet. If the start phrase is absent the guard SHALL raise `AssertionError`. It SHALL state the ratios of the uncalibrated Sane–Dickinson model to the
CFD lift as exactly two tokens of the form `~<x.x>×`, with no markup between `~` and the number,
coarse first, each equal to that corpus's `figures/evidence_figure_metrics.json`
`quasi_steady_reference.overshoot_factor` at 1 dp. Any other multiplier in that bullet SHALL NOT use
the `~<number>×` form. After its whitespace runs are collapsed to one space, the bullet SHALL contain
the phrase `stays above 1 on the fine grid`. It SHALL NOT describe either grid as free of
immersed-boundary bias. A CI test SHALL check this against the two committed sidecars.

#### Scenario: Both ratios are the committed sidecars

- **Given** the committed coarse and fine `evidence_figure_metrics.json` and the coarse README
- **When** the README tests run
- **Then** the quasi-steady bullet holds exactly two `~x.x×` tokens, equal to the coarse and fine `overshoot_factor` at 1 dp in that order, contains `stays above 1 on the fine grid`, and matches no `(?i)\b(ib|immersed[- ]boundary)[- ]bias[- ]?free` pattern

#### Scenario: The guard rejects each defect

- **Given** copies of the bullet with, one at a time: one ratio's digit changed, the two ratios swapped, a third `~2.3×` token, `~**1.3×**` markup, the phrase removed, "IB-bias-free" added, and the start phrase removed
- **When** the guard runs on each copy
- **Then** each fails with an `AssertionError` (never an `IndexError` or `ValueError`) whose message names the defect
