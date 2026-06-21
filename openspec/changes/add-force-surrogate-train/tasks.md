# Tasks — `add-force-surrogate-train` (PR5)

TDD throughout: each implementation item is preceded by its **Test first** item (red → green →
refactor). CPU-tier tests are cluster-free (numpy/pandas only) and **gate CI**; GPU-tier tests are
`@pytest.mark.gpu`, torch-tier, and run on the A5000. Decisions D1–D8 live in `design.md`. Each
phase ≈ one atomic commit (see the proposal's PR-scoping note).

> **Status (2026-06-19).** CPU library + driver + CPU-tier tests green (225 passed, 6 GPU
> deselected, lint clean, `openspec --strict` valid). **De-risk complete on the A5000:**
> PhysicsNeMo 2.1.1 stands up, `FullyConnected` matches `build_model`, all **6 GPU-tier tests
> PASS on real CUDA**, and the full real-dataset run produced the four artifacts under
> `examples/prelim_sweep/surrogate/` with **held-out-config R²=0.983, RMSE=0.051**. torch pinned to
> the cu126 index (D11) so it runs on driver 552.86; `torchvision` added as a direct dep so the pin
> binds. Remaining: **commit the artifacts** (operator/user), and the merge-time roadmap
> reconciliation (9.3/9.6).

## Phase 0: Packaging, marker, CI

- [x] 0.1 Add the optional `train` dependency-group to `pyproject.toml` — `nvidia-physicsnemo`, `torch`, `wandb` — with the heavy deps **marker-gated**: `"nvidia-physicsnemo ; sys_platform == 'linux'"`, `"torch ; sys_platform == 'linux'"`, `"wandb"`. Not in the default groups (D5).
- [x] 0.2 **Regenerate and commit `uv.lock` in the SAME commit** as 0.1 — ran `uv lock` on the Windows dev host (the marker-gated group resolved; 130 packages) and `uv lock --check` passes; a bare `uv sync --frozen` installs only the default set (verified: torch/physicsnemo/wandb absent).
- [x] 0.3 Register the `gpu` marker in `[tool.pytest.ini_options]`.
- [x] 0.4 Add `tests/conftest.py` autoskip: `@pytest.mark.gpu` tests skip when CUDA is unavailable **or** `physicsnemo` is not importable (import guarded → skip, not collection error). Verified: 6 GPU tests reported *skipped* on this CPU host — *Scenario: GPU tests skip on a CPU-only host*.
- [x] 0.5 **Edited `.github/workflows/ci.yml`** test step → `uv run pytest -v -m "not gpu" || [ $? -eq 5 ]` (marker filter added, exit-5 tolerance preserved) — *Scenario: CI deselects the GPU marker explicitly*.
- [x] 0.6 Added `*.pt`/`*.pth`/`*.ckpt binary` to `.gitattributes`.

## Phase 1: De-risk PhysicsNeMo end-to-end (GPU tier) — DO THIS FIRST (D1)

- [x] 1.1 **Created `src/mosquito_cfd/force_surrogate/train.py`** with the `build_model` lazy-import seam (module imports under CI; torch imported inside). Authored the GPU test (no top-level `import torch`) — *Scenario: Model constructs with the right shape*.
- [x] 1.2 **A5000-validated:** PhysicsNeMo 2.1.1 stands up in WSL2; `FullyConnected(in_features, layer_size, out_features, num_layers)` matches `build_model`. Pinned `torch`+`torchvision` to the linux-gated PyTorch **cu126** index + re-locked (default `+cu130` rejects driver 552.86 = CUDA 12.4; cu126 runs via minor-version compat — `cuda.is_available()` True). Versions/host recorded in the surrogate `run_metadata.json`; README documents `uv sync --group train`. (D11. PhysicsNeMo did **not** block.)
- [x] 1.3 **GPU test PASSED on A5000:** `test_seeded_training_reduces_loss` — *Scenario: Seeded training reduces loss*.

## Phase 2: Input/target construction (CPU tier)

- [x] 2.1 `build_features` returns the five cyclic-phase columns, no `reynolds` — *Scenario: Feature columns are the kinematics knobs plus cyclic phase*.
- [x] 2.2 Cyclic-phase continuity across the 0/1 wrap — *Scenario: Cyclic phase encoding is continuous across the wrap*.
- [x] 2.3 `filter_converged_beat` keeps only `wingbeat ≥ 1` with an explicit count — *Scenario: Only the converged beat is used*.
- [x] 2.4 `Standardizer` fit on training rows only (no leakage) — *Scenario: Standardization is fit on training rows only*.
- [x] 2.5 Target standardize→inverse round-trip — *Scenario: Targets round-trip through standardization*.
- [x] 2.6 Implemented `build_features`, `filter_converged_beat`, `Standardizer` (numpy/pandas only; no torch import — D2). (+ zero-variance scale floor test.)

## Phase 3: Configuration split (CPU tier, CC-4)

- [x] 3.1 Test set == the 6 `holdout` configs, none in train/val — *Scenario: Holdout configs are exactly the dataset holdout label*.
- [x] 3.2 Seeded config-level val carve from sorted unique names; whole-config, disjoint, covers all train — *Scenario: Validation is carved at the configuration level*.
- [x] 3.3 Same-seed reproducible, different-seed leaves test unchanged — *Scenario: Split is seed-reproducible and seed-sensitive*.
- [x] 3.4 Missing `split`, zero `holdout`, empty validation carve each raise `ValueError` — *Scenario: Malformed split raises rather than silently emptying a set*.
- [x] 3.5 Implemented `make_config_splits`.

## Phase 4: Metrics (CPU tier)

- [x] 4.1 `compute_metrics` RMSE/MAE/R² match known values — *Scenario: Metrics math is correct on known arrays*.
- [x] 4.2 Zero-variance target → R² NaN sentinel, finite RMSE/MAE, NaN-aware aggregate — *Scenario: Constant-target R² is a defined sentinel*.
- [x] 4.3 Implemented `compute_metrics` — pure numpy, no scipy/sklearn, zero-variance sentinel.

## Phase 5: Model + training loop (torch tier, builds on Phase 1)

- [x] 5.1 **Subprocess import guard** (`sys.modules['torch']=None`/`['physicsnemo']=None`): the five pure helpers import+run without raising; `'torch' not in sys.modules` — *Scenario: Module imports without the training dependency-group*.
- [x] 5.2 Implemented `train_model`/`predict` (lazy import; seeded; `torch.use_deterministic_algorithms`, D6).
- [x] 5.3 **GPU test PASSED on A5000:** seeded `train_model` twice on the CPU torch device → identical loss trajectories — *Scenario: Seeded training step is deterministic on the CPU torch device*.

## Phase 6: Evaluation, artifacts, provenance, wandb (CPU + torch tiers)

- [x] 6.1 Torch-free helper chain bitwise-reproducible (same seed) — *Scenario: Torch-free CPU helpers are bitwise-reproducible*.
- [x] 6.2 `metrics.json` round-trips with `per_target`/`aggregate`/`per_config`/`inference`/`reproducibility` keys (sentinel R² → `null`) — *Scenario: metrics.json carries per-target, aggregate, per-config, and inference keys*.
- [x] 6.3 Evaluation scores only holdout converged-beat rows — *Scenario: Evaluation uses only holdout configurations*.
- [x] 6.4 Predictions frame schema + holdout-only `config_name` membership + true coeffs match — *Scenario: Predictions parquet schema*.
- [x] 6.5 Provenance records digest/timestamp/seeds; versions `None` on CI tier; mutable tag rejected — *Scenario: Provenance records digest, timestamp, and seeds (CI tier)* + *Mutable image tag rejected*.
- [x] 6.6 `disabled` wandb is a no-op without importing wandb — *Scenario: wandb is disabled by default without importing wandb*.
- [x] 6.7 `online` wandb with the import barred still writes a full `metrics.json` (import+call in one try/except) — *Scenario: wandb online failure does not block metrics.json*.
- [x] 6.8 Force-only guard — `run_training` takes only `dataset_path`, no field/plotfile param — *Scenario: Training consumes only the dataset parquet*.
- [x] 6.9 Implemented `build_predictions_frame`/`build_metrics`/`build_training_metadata`/`log_to_wandb` + the `run_training` orchestrator (digest sourced from the dataset's `run_metadata.json`; versions via `importlib.metadata`; reproducibility block).
- [x] 6.10 **GPU test PASSED on A5000:** provenance records resolved `torch`/`physicsnemo` versions (torch 2.12.1+cu126, physicsnemo 2.1.1) — *Scenario: Resolved library versions recorded on the training host*.

## Phase 7: Driver CLI

- [x] 7.1 Driver parses every flag; `main()` delegates via a monkeypatched `run_training` and never imports torch — torch-free CPU test.
- [x] 7.2 Implemented `scripts/train_surrogate.py`; re-exported the public API from `force_surrogate/__init__.py`.
- [x] 7.3 **GPU test PASSED on A5000:** full `train → predict → metrics.json` round-trip writes all four artifacts — *Scenario: All four artifacts are written*.

## Phase 8: Operator A5000 run → committed artifacts (D8)

- [x] 8.1 **DONE on A5000:** ran `scripts/train_surrogate.py` over the full `dataset.parquet` (12,535 holdout rows, 2000 epochs, seed 1234, `--device cuda`) — held-out-config aggregate R²=0.983, RMSE=0.051; per-target R² 0.97–0.99; inference 0.96 ms/row, 12.2M rows/s. (`--wandb disabled` for the reproducible artifact run; the committed `metrics.json` is the source of truth.)
- [~] 8.2 Artifacts produced under `examples/prelim_sweep/surrogate/` (subdir avoids the dataset `run_metadata.json` collision — D10); **commit pending user go-ahead** as the final commit, gated behind the green CPU state. Headline R²=0.983 for the PR description.

## Phase 9: Docs, validation, gates

- [x] 9.1 `examples/prelim_sweep/README.md` surrogate section — artifacts, `uv sync --group train` + train command, `--wandb` gating, CPU-bitwise/GPU-seeded caveat, `pytest -m gpu` note; references the spec scenarios (no schema re-listing).
- [x] 9.2 `openspec/project.md` `force_surrogate/` one-liner gained `train`.
- [ ] 9.3 **MERGE-TIME:** reconcile `docs/force_surrogate/roadmap.md` row #5 text (drop the PyTorch-fallback / ~Jun-18 wording → "PhysicsNeMo-only, D1") with the status flip via `/cleanup-merged`.
- [x] 9.4 `openspec validate add-force-surrogate-train --strict` — valid.
- [x] 9.5 `ruff check`/`format --check` clean; `pytest -m "not gpu"` green (225 passed, 6 GPU deselected); GPU tier collects-and-skips. **NOTE:** `--cov` works for numpy-only modules (e.g. `geometry`, 72%) but fails when sourcing `force_surrogate.*` (its `__init__` imports pandas → a pre-existing numpy-2.x/pandas/coverage double-import bug; reproduces on the PR1 `normalization` module, so it predates this PR). Filed as [#22](https://github.com/talmolab/mosquito-cfd/issues/22). CI uses plain `pytest` (no `--cov`), so it is unaffected. No `--cov-fail-under` on `train.py` (model/training functions are torch-tier).
- [ ] 9.6 **MERGE-TIME:** roadmap row #5 checkbox flips via `/cleanup-merged`.

## Phase 10: Config-resolved (phase-honest) metrics (post-review enhancement, D13)

- [ ] 10.1 **Test first (CPU):** `config_mean_r2` + `within_config_variance_fraction` match the known-answer arrays (two configs `[1,3]`/`[5,7]`, pred means `2`/`5` → fraction `0.2`, R² `0.875`) — *Scenario: config-resolved quantities match known-answer arrays*.
- [ ] 10.2 **Test first (CPU):** a constant per-config mean (zero between-config variance) yields the NaN sentinel for `config_mean_r2` — *Scenario: A constant per-configuration mean yields the R² sentinel*.
- [ ] 10.3 **Test first (CPU):** `metrics.json` carries a `config_resolved` block keyed by the six targets, each with `config_mean_r2` + `within_config_variance_fraction` — *Scenario: config_resolved block is present per target*.
- [ ] 10.4 Implement the config-resolved helper (pure numpy; cycle-mean per config; `_VARIANCE_EPS` floor) and add the `config_resolved` block to `build_metrics`, reported alongside `aggregate`.
- [ ] 10.5 Re-validate `--strict`; re-run the CPU gate + A5000 GPU tests; refresh `surrogate/metrics.json` (gains `config_resolved`); update README + PR.
