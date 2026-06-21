# Design — `add-force-surrogate-train` (PR5)

Architectural decisions for the Track B kinematics(+phase) → force-coefficient surrogate trainer.
Grounded in [docs/force_surrogate/roadmap.md](../../../docs/force_surrogate/roadmap.md) row #5,
GitHub issue [#21](https://github.com/talmolab/mosquito-cfd/issues/21), and the cross-cutting
concerns CC-1 (provenance), CC-2 (cluster-free fixtures), CC-3 (single-source normalization),
CC-4 (held-out **config** evaluation), CC-5 (units), CC-6 (force-only scope).

## Context

The committed dataset (`examples/prelim_sweep/dataset.parquet`) has 109,656 rows over 27 configs,
21 train / 6 holdout configs (config-level `split`), `wingbeat ∈ {0, 1}`, `phase ∈ [0, 1)`, and the
six already-normalized coefficients `CF_x/CF_y/CF_z/CF_mx/CF_my/CF_mz`. PR5 learns the map
kinematics(+phase) → those six coefficients and emits predictions + `metrics.json` for PR6.

---

## D1 — PhysicsNeMo-first, no PyTorch fallback

**Decision.** Ship **only** the PhysicsNeMo regressor. The roadmap row lists "PhysicsNeMo-primary,
PyTorch DeepONet/MLP fallback (hard fallback checkpoint ~Jun 18)"; this change **drops the
fallback** on the user's explicit instruction.

**Why.** Track B's *purpose* is evidence that the NVIDIA PhysicsNeMo stack runs the local pipeline
end-to-end. A second PyTorch model would dilute that evidence and double the maintenance surface for
a proof-of-pipeline. The fallback existed to de-risk schedule; we de-risk by **ordering** instead:
the first implementation task (a GPU test) stands up PhysicsNeMo in the chosen env and trains a
trivial end-to-end model *before* the full pipeline is built, so an environment problem surfaces
with days of slack before the ~Jun-24 cutoff. **Track B never gates submission** — if PhysicsNeMo
hard-blocks, the figure is cut and the proposal stands on the existing sphere/ellipsoid/flapping
benchmarks (roadmap "Hard cutoff").

**Seam, not fallback.** `build_model(n_in, n_out, *, seed)` is a thin factory so the training loop
never names a concrete class inline. This is good design (testable, swappable) — it is **not** a
re-introduced PyTorch model. Only the PhysicsNeMo implementation ships.

**Why the spec does not pin a PhysicsNeMo class name.** The exact PhysicsNeMo MLP API cannot be
verified offline in this Windows session; pinning a class the de-risk task might find renamed would
be dishonest. The spec therefore constrains **behavior** (constructs an `n_in → n_out` regressor, a
seeded loop drives loss down, a forward pass returns the 6-wide output), and the de-risk task
records the actual class/version in `run_metadata.json`.

## D2 — Lazy torch import + two-tier tests (CPU gates CI, GPU gates the local run)

**Decision.** The pure data/feature/split/standardizer/metrics helpers import **no** torch; the model
and training functions import `torch`/`physicsnemo` **lazily inside themselves**. Tests split into a
**CPU tier** (cluster-free, gates CI) and a **GPU tier** behind a registered `@pytest.mark.gpu`
marker that **auto-skips** when `torch.cuda.is_available()` is false or `physicsnemo` is not
importable. CI additionally runs `-m "not gpu"`.

**Why.** CI runs on a CPU-only GitHub runner **without** the heavy `train` group. A top-level
`import torch` in `train.py` would make the module un-importable there, breaking even the pure-helper
tests. Lazy import keeps `from ...train import build_features, make_config_splits, compute_metrics`
working with zero ML deps. The GPU tier is the operator's real-path check on the A5000
(`uv run pytest -m gpu`). This mirrors the runner's "injected-executor mocked test path" precedent —
the orchestration/logic is unit-tested cluster-free; the heavy backend is exercised separately.

**What each tier covers.**
- *CPU (CI gate):* cyclic-phase features; train-only standardization (no leakage); `wingbeat ≥ 1`
  filter; config-level split disjointness + seed-reproducibility + the 6 holdout configs; metrics
  math on known arrays; `metrics.json` / predictions-frame schema; `run_metadata` digest guard;
  units-sidecar read. All numpy/pandas, deterministic, bitwise.
- *GPU (operator gate):* PhysicsNeMo constructs; forward pass returns the 6-wide shape; a seeded tiny
  train loop **reduces loss**; a full train→predict→`metrics.json` round-trip writes all four
  artifacts.

## D3 — Inputs: three kinematic knobs + cyclic phase; no Reynolds

**Decision.** Features `= [stroke_amp_deg, frequency_fstar, pitch_amp_deg, sin(2π·phase),
cos(2π·phase)]`.

**Why cyclic phase.** `phase ∈ [0, 1)` wraps; a raw scalar feature imposes a spurious discontinuity
at the 0/1 boundary (phase 0.999 and 0.001 are adjacent in the cycle but maximally far as scalars).
`(sin, cos)(2π·phase)` is the standard continuous encoding and makes the boundary continuous.

**Why no Reynolds.** Under the resolved CC-7 policy (ν\* held fixed at 0.115), `Re = Re(φ, f*)` is a
deterministic function of two of the swept knobs (`sweep_manifest.json` `reynolds_policy =
nu_star_fixed`). Feeding it as an input adds **no independent information** and would couple the
feature space to a derived quantity. The inputs stay the pure, independent kinematic knobs + phase.
(The dataset still *carries* `reynolds` for traceability; PR5 simply does not use it as a feature.)

**Standardization.** Features are standardized (mean/std) on **train rows only**; the fitted stats
transform val and holdout. Fitting on the full dataset would leak holdout statistics into training —
a subtle CC-4 violation. The fitted stats are recorded in `metrics.json` reproducibility block.

## D4 — Targets: all six coefficients, standardized on train

**Decision.** Predict `CF_x, CF_y, CF_z, CF_mx, CF_my, CF_mz` (multi-output). Targets are
standardized on **train rows only** and predictions inverse-transformed before metrics/predictions.

**Why all six.** Cheap (one extra-wide output head), zero information loss, and it keeps PR6 free to
designate the single headline `CF_m` pitch axis once the figure makes the physically correct axis
unambiguous — PR4 D2 deliberately deferred that pick to PR6. `CF_y` and the off-axis moments may be
near-zero by symmetry; reporting them per-target makes that visible rather than hiding it.

**Why standardize targets.** The six coefficients differ in magnitude; an unscaled multi-output MSE
would weight the largest-magnitude target most and under-fit the rest. Standardizing equalizes the
loss contribution; metrics are computed on the **inverse-transformed** (physical-coefficient) values
so RMSE/MAE are reported in coefficient units, comparable to PR6's figure.

## D5 — `uv` packaging; runtime env is an operator deployment detail

**Decision.** `nvidia-physicsnemo`, CUDA `torch`, and `wandb` live in an **optional `train`
dependency-group** in `pyproject.toml`, installed only via `uv sync --group train`. The training
code is identical across **WSL2 (default)**, the **PhysicsNeMo container**, and a **native Linux
workstation** — the env is chosen at deploy time, not in code.

**The lock MUST be regenerated and committed — but mind *which* command catches a stale lock.** uv
records every `[dependency-groups]` entry's specifiers in the lock's `[package.metadata.requires-dev]`,
so adding the `train` group makes `pyproject.toml` and `uv.lock` diverge. The command that **catches**
that divergence is **`uv lock --check`** (exit 1), *not* `uv sync --frozen`: `--frozen` means "install
from the lock as-is without re-validating it" and exits 0 even against a stale lock (the PR4 archive
documented exactly this — a same-machine `uv sync --frozen` right after editing is "false confidence";
PR4 gated on `uv lock --check`). So a stale lock does **not** by itself break CI's `uv sync --frozen`
test step or the two Dockerfiles' bare `uv sync --frozen` — those install the unchanged default set
and stay green. Re-locking is still **mandatory**, for three real reasons: (1) `uv lock --check`
consistency (run in task 0.2 and the pre-merge gate); (2) the operator's `uv sync --group train` on
the A5000 needs the group *in* the lock to resolve; (3) any future `uv lock` / `--locked` run would
otherwise diverge. The earlier draft mis-attributed the break to `uv sync --frozen`; the *action*
(re-lock + commit in the same commit, gated on `uv lock --check`) is unchanged and correct.
(Contrast PR4's **runtime** pyarrow dep: that one *did* affect `uv sync --frozen`, because `--frozen`
installs exactly the lock's runtime set, so a missing runtime dep means a missing install. An
opt-in *group* is never installed by the default sync, so its absence from a stale lock has no
runtime effect on CI/Docker — only `uv lock --check` and `uv sync --group train` care.)

**Cross-platform lock via environment markers.** CUDA `torch` and `nvidia-physicsnemo` are
effectively Linux-only; a universal `uv.lock` (the lock targets win32/darwin/linux) cannot resolve
them on the Windows dev host. The fix is **marker-gating** the heavy deps so non-Linux marker
environments have nothing to resolve:

```toml
[dependency-groups]
train = [
    "nvidia-physicsnemo ; sys_platform == 'linux'",
    "torch ; sys_platform == 'linux'",
    "wandb",
]
```

`uv lock` then succeeds on Windows (the torch/physicsnemo nodes resolve only under the linux marker;
win32/darwin get nothing) **and** `uv lock --check`/`--frozen` stay green everywhere. If the default
PyPI `torch` wheel does not carry the needed CUDA build, the de-risk task (task 1) adds a pinned
PyTorch index (`[[tool.uv.index]]` + `[tool.uv.sources]`, `explicit = true`) under the same linux
gate. The **resolved** `torch`/`physicsnemo` versions are still captured in `run_metadata.json` for
provenance. The earlier draft's "document the install command instead of forcing a broken lock" was
self-contradictory — a group present in `pyproject.toml` but absent from the lock fails `--frozen`;
marker-gating is what actually keeps the lock both consistent and resolvable.

**Provenance.** `run_metadata.json`'s hardware capture records the actual host/GPU, so whichever of
the three envs runs the training is always traceable (CC-1).

## D6 — Reproducibility: seeds everywhere, bitwise scoped to CPU

**Decision.** Set explicit seeds (python/numpy/torch) and `torch.use_deterministic_algorithms(True)`.
Claim **bitwise** reproducibility only for the **CPU test path** (CI-verified); the GPU run is
**seeded but not guaranteed bitwise** (cuDNN/TF32 nondeterminism).

**Why scope it.** CC-1 says "rerun → identical given the same seed." That holds bitwise on CPU and is
what the CI tests assert. On the A5000, TF32 matmuls and some cuDNN kernels are nondeterministic even
with deterministic mode (or force a slow fallback). Claiming bitwise GPU reproducibility would be an
overclaim; we state the honest scope in `metrics.json`'s `reproducibility.bitwise = "cpu_only"` and
document it in the README. Seeds + recorded versions still make the GPU run *reproducible in
distribution* and auditable.

**Two determinism tiers (resolving a CI contradiction the review caught).** The bitwise claim splits
across the test tiers because a "seeded CPU training step" *is torch code* and torch is **not** in
CI:
- **CI tier (torch-free):** the seeded `build_features → Standardizer → make_config_splits →
  compute_metrics` chain run twice is bitwise-identical — numpy/pandas only, so it runs on the
  CPU-only CI runner without the `train` group. This is the CI-gating determinism check.
- **Torch tier (`@pytest.mark.gpu`, runnable on the CPU torch device):** a seeded `train_model` step
  run twice produces identical loss trajectories. This needs torch, so it is in the GPU/torch tier
  and deselected in CI. The original single "CPU path is bitwise" scenario folded a torch training
  step into the CI tier, which would have `ImportError`-failed CI — the spec now separates the two.

## D7 — wandb gating: online for operator runs, disabled in CI

**Decision.** `wandb` logs the operator's A5000 runs (`--wandb online`); it defaults to **`disabled`**
in CI and automated reruns. `metrics.json` is the committed source of truth.

**Why.** GitHub runners have no wandb login; a default-online run would hang or fail on auth, and the
committed `metrics.json` must never depend on a network call. `disabled` makes wandb a no-op so the
exact same code path runs in CI and locally. The operator opts into the live dashboard explicitly.

## D8 — Committed artifacts produced by the operator's A5000 run

**Decision.** Commit `metrics.json`, the holdout-predictions parquet, the model checkpoint, and
`run_metadata.json`, all produced by the seeded A5000 run (not a fixture).

**Why commit real artifacts (contrast PR4 D10).** PR4 deliberately did *not* commit a fixture-derived
`dataset.parquet` because it would manufacture false CFD provenance. Here the inputs are the **real**
committed dataset and the artifacts are produced by a **real** GPU training run with a genuine
`:fp64` digest in `run_metadata.json` — so committing them is honest and gives PR6 versioned inputs.
The CI tests still generate all artifacts into `tmp_path` and never touch the committed copies.

**Why commit the checkpoint.** It is small (a few-layer MLP) and lets PR6 / future work reproduce
inference without retraining. It is a non-bitwise GPU binary (D6), so it is provenance-stamped, not
claimed bitwise.

---

## Spec delta summary

The `force-surrogate` capability gains eight requirements:

1. **Held-out-configuration train/validation/test split** (CC-4) — 6 holdout configs = test; seeded
   config-level val from the 21 train configs; disjoint.
2. **Surrogate input and target construction** — cyclic phase, no Reynolds, `wingbeat ≥ 1` filter,
   train-only standardization of features and the six targets.
3. **PhysicsNeMo force-coefficient regressor** — PhysicsNeMo-only, seeded, six outputs, loss
   decreases (GPU tier).
4. **Held-out evaluation metrics** — `metrics.json` per-target/aggregate/per-config + inference
   timing.
5. **Training reproducibility and provenance** — seeds + deterministic flags + `run_metadata`
   digest; CPU bitwise / GPU seeded; wandb gated.
6. **Committed training artifacts** — the four artifacts, real-run provenance.
7. **Two-tier cluster-free / GPU-gated tests** — CPU gates CI; `@pytest.mark.gpu` auto-skips.
8. **Force-only training scope guard** (CC-6) — consumes `dataset.parquet` only; no fields, no
   DoMINO/RL.
