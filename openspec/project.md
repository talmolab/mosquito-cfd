# Mosquito Swarm CFD

## Overview

GPU-accelerated CFD simulations of mosquito flight aerodynamics using IAMReX (Immersed-boundary Adaptive Mesh Refinement), validating against van Veen et al. (2022) mosquito wing aerodynamics.

**Grant history**: this project originally targeted the [ALCF APEX supercomputing proposal](https://www.alcf.anl.gov/science/apex-proposal-requirements-and-submissions-instructions) (submitted Feb 27, 2026; **denied**). The target moved to the **NVIDIA Academic Grant Program** (H100, submitted by the June 30, 2026 deadline; decision expected ~Sep 2026) — see `openspec/changes/add-apex-benchmarking/h100_resource_estimate.md`. The rescope is *targets*, not *abandonment*: the underlying validation work (sphere, ellipsoid, flapping wing) is the evidence base for either proposal and continued independent of the grant outcome — see `docs/aerodynamics_validation/roadmap.md` for the current tier-by-tier status.

**Repository**: [talmolab/mosquito-cfd](https://github.com/talmolab/mosquito-cfd)

## Goals

1. **Simulation Accuracy**: Validate CFD results against published experimental data from van Veen et al. (2022) for Aedes aegypti mosquito wing aerodynamics
2. **GPU Performance**: Leverage NVIDIA A100 GPUs with FP64 for high-throughput simulations
3. **Reproducibility**: Capture comprehensive metadata for all simulation runs to ensure scientific reproducibility
4. **Scalability**: Design for eventual deployment on large-scale GPU allocations (H100 grant target) for large-scale mosquito swarm simulations
5. **Grant Readiness**: Develop benchmarks and scaling studies suitable for grant proposal submission (originally ALCF APEX, now the NVIDIA Academic Grant/H100)

## Architecture

### Directory Structure

```
mosquito-cfd/
├── src/mosquito_cfd/         # Python utilities
│   ├── geometry/             # Wing planform generation (parametric + vertex I/O)
│   ├── benchmarks/           # Benchmark runner and metadata capture
│   └── force_surrogate/      # Track B force-surrogate prep (normalization, sweep, dataset, train)
├── scripts/                  # Thin CLI drivers over the tested library (e.g. run_sweep.py, extract_forces.py)
├── docker/                   # Container infrastructure
│   ├── Dockerfile.fp64       # Primary simulation image
│   ├── Dockerfile.fp32       # Deprecated (upstream unsupported)
│   └── Dockerfile.python     # Post-processing only
├── examples/                 # Validation cases
│   ├── flow_past_sphere/     # Classic CFD validation case
│   ├── flapping_wing/        # Validated flapping-wing demo (van Veen kinematics)
│   └── prelim_sweep/         # Force-surrogate kinematic sweep corpus + dataset contract
├── cluster/argo/             # Argo Workflows for cluster-side sweep orchestration (production)
│   ├── workflow-templates/   # Single-config WorkflowTemplate (one A40 pod = one mpirun)
│   ├── workflows/            # Fan-out sweep Workflow over the manifest configs
│   └── scripts/              # submit/monitor wrappers (WSL + KUBECONFIG)
├── .github/workflows/        # CI/CD pipelines
│   ├── ci.yml                # Lint, test, Dockerfile lint
│   └── docker.yml            # Build & publish to ghcr.io
├── openspec/                 # Specification-driven development
└── pyproject.toml            # Python project configuration
```

### Core Components

- **IAMReX Integration**: External CFD solver using immersed-boundary methods with adaptive mesh refinement
- **Wing Geometry**: Parametric planform generation for Aedes aegypti wings via `geometry/` package (`generate-wing-planform` CLI)
- **Benchmarks & Metadata**: Benchmark runner and reproducibility metadata capture via `benchmarks/` package (git, docker image, hardware, timing, outputs)
- **Docker Infrastructure**: Reproducible build environments with pinned dependency versions

## Technology Stack

### CFD Solver
- **IAMReX**: C++/CUDA with AMReX framework
- **External Dependencies** (cloned at build time):
  - [ruohai0925/amrex](https://github.com/ruohai0925/amrex) - Development branch
  - [ruohai0925/AMReX-Hydro](https://github.com/ruohai0925/AMReX-Hydro) - Main branch
  - [ruohai0925/IAMReX](https://github.com/ruohai0925/IAMReX) - Development branch

### Python Environment
- **Python**: 3.11+ (managed via `.python-version`)
- **Package Manager**: [uv](https://github.com/astral-sh/uv) (lockfile: `uv.lock`)
- **Dependencies**:
  - `numpy>=2.4.2` - Array operations, marker generation
  - `matplotlib>=3.10.8` - Visualization
  - `pandas>=3.0.0` - Data analysis
  - `yt>=4.4.2` - AMReX plot file visualization
  - Two optional dependency groups exist beyond the base set above: `train` (documented only in
    `pyproject.toml`'s own comment, no dedicated section here) and `viz` (`scipy`,
    `scikit-image`, `imageio-ffmpeg`; installed in CI — see "Visualization Tooling" below)
- **Dev Dependencies**:
  - `pytest>=9.0.2` - Testing
  - `ruff>=0.15.1` - Linting and formatting

### Build & Runtime
- **Build System**: GNU Make with CUDA 12.x
- **Runtime**: MPI (OpenMPI) + CUDA
- **Base Image**: `nvidia/cuda:12.4.1-devel-ubuntu22.04`

### Container Infrastructure
- **Registry**: `ghcr.io/talmolab/mosquito-cfd`
- **Images**:
  - `:fp64` - Primary image for all simulations and benchmarks
  - `:python` - Post-processing only (~1-2 GB)
  - `:fp32` - Deprecated (upstream does not support)
- **HPC Portability**: Apptainer/Singularity conversion supported

### CI/CD
- **Platform**: GitHub Actions
- **Pipelines**:
  - `ci.yml`: Lint (ruff), test (pytest), Dockerfile lint (hadolint)
  - `docker.yml`: Build & publish images on push to main/tags

## Constraints

### Hardware
- **Development**: NVIDIA A40 (local/Salk cluster), also RTX A5000 (local dev box)
- **Target**: NVIDIA H100 (NVIDIA Academic Grant, decision ~Sep 2026); the original ALCF APEX/A100
  target was denied — see Overview
- **CUDA**: Compute capability 8.0+ (A100) or 8.6+ (A40/H100)
- **Driver**: 550.54.14+ (for CUDA 12.4)
- **Memory**: 40+ GB GPU RAM on A100/H100

### Precision
- **FP64 Only**: All benchmarks and simulations use double precision
- **Rationale**: IAMReX maintainer [does not test single precision](https://github.com/ruohai0925/IAMReX/issues/59); FP64 ensures scientific accuracy
- **Target Hardware**: NVIDIA H100 (grant target); A100 (19.5 TFLOPS FP64) was the original
  ALCF APEX target

### Dependencies
- Requires external clones of amrex, AMReX-Hydro, and IAMReX repositories
- Pinned commits managed in `docker/build-args.env`

## Current State

### Implemented
- [x] Parametric wing planform generation (`geometry/` package)
- [x] Run metadata capture with docker/git/hardware tracking (`benchmarks/metadata`); force-surrogate
  cluster runs additionally get a fully automated `run_metadata_<config>.json` generator
  (`force_surrogate/metadata_capture.py`, `scripts/generate_run_metadata.py`) that derives
  timing/kinematics/orchestration/stability fields from existing artifacts instead of hand-typing
  them (`automate-run-metadata-capture`) — `examples/flapping_wing/run_metadata_{t3c,t3b,t2a}.json`
  and the 3 `examples/prelim_sweep_fine_pilot/run_metadata_*.json` pilot files intentionally remain
  on the older, pre-normalization hand-authored schema (not retrofitted)
- [x] Docker infrastructure with FP64 working builds
- [x] GitHub Actions CI/CD for lint/test/publish
- [x] Flow past sphere validation example (100 timesteps verified on A40)
- [x] **APEX benchmarking substance** (sphere Cd, heaving-ellipsoid self-consistency, flapping-wing
  van Veen validation) - delivered, but under separate, later OpenSpec changes (T1a-T4/T3c, see
  `docs/aerodynamics_validation/roadmap.md`) rather than under `add-apex-benchmarking` itself; that
  change's own proposal/tasks describe the pre-submission Feb 2026 state and are kept as a
  historical record of the (denied) APEX submission - see
  [add-apex-benchmarking](changes/add-apex-benchmarking/proposal.md)
- [x] **Arbitrary geometry support** - external vertex file loading + prescribed kinematics for
  flapping wing validation; archived as `add-arbitrary-geometry` once its foundational scope
  shipped and was extended by the same T2a-T4/T3c lineage
- [x] Full 27-config fine-256³ force-surrogate corpus (decks + manifest only, no CFD output yet) —
  `examples/prelim_sweep_fine/generate_full_corpus.py`, committed via `add-fine-grid-corpus-full`,
  the follow-on to the 3-config `add-fine-grid-training-pilot` (GO recommendation) — reuses
  `generate_sweep()`'s default 27-point grid and `n_holdout=6`, unmodified
- [x] Fixed a wing-hinge geometry defect (root hinge collapsed to a midspan pivot in the
  git-committed base decks) dating to the 2026-07-02 axis-convention refactor; separately found and
  fixed a stale/incorrect `wing.vertex` on the coarse corpus's cluster NFS share (issue #62) that had
  been running the pre-T2a axis convention entirely; regenerated `examples/prelim_sweep/`'s decks +
  `dataset.parquet`/`surrogate/*`/`figures/*` end-to-end and `examples/prelim_sweep_fine/`'s decks
  (CFD re-run deferred); automated NFS provisioning going forward —
  `fix-force-surrogate-sweep-hinge`

### Not Planned
- FP32 builds - upstream IAMReX does not support; using FP64 on A100/H100 instead

### Pending
- [ ] Scaling benchmarks for the NVIDIA Academic Grant (H100) - the current grant target;
  scaling-benchmark scope originally written for APEX still applies, just against H100 hardware
- [ ] Multi-GPU / multi-node validation
- [ ] Submit the full 27-config fine-grid corpus's live cluster run (~2.55 days serial single-A40)
  — scaffolding landed in `add-fine-grid-corpus-full`; the actual submission needs a separate,
  explicit go-ahead (shared lab GPU quota). The two bugs that sank the prior two attempts —
  `activeDeadlineSeconds` not scaling with an overridden `--parallelism` (issue #63, killed
  `force-surrogate-sweep-7wrk7` at 24h with 0/27 done) and `retryStrategy.backoff.maxDuration`
  exhausting after only 3 of 5 configured retries under preemption (issue #64, lost 3 configs
  from `force-surrogate-sweep-vb8t5`) — are fixed in `fix-argo-sweep-timeouts`:
  `submit_workflow.sh full` now has an `--active-deadline-seconds` override with an auto-scale
  fallback, and `maxDuration` is `4h` (covers the full `limit: 5` sequence). A third,
  metadata-only bug (issue #65: `compute_wall_time_s` picked the globally-latest-finishing pod's
  duration for every config in a multi-config fan-out workflow) is fixed in
  `fix-wall-time-pod-selection` — the resubmission is now blocked only on the user's explicit
  go-ahead, not any known bug. **Superseded run:**
  `force-surrogate-sweep-vb8t5` + `force-surrogate-retry-failed-trz9k` already completed once,
  but against the stale wing-hinge geometry (`fix-force-surrogate-sweep-hinge`) — still needs
  re-submission against the corrected decks; see
  `examples/prelim_sweep_fine/sweep_provenance.json`'s `superseded_by` field.
- [ ] Generate the first **real** `docs/visualization/coarse_vs_fine_comparison.png` and
  `docs/visualization/diagnostic_config_mean_collapse.png` once
  `examples/prelim_sweep_fine/surrogate/` exists — no placeholder exists at that path today; the
  synthetic-fixture-derived renders used to validate the figure-building code live instead at
  `tests/fixtures/comparison_figure/` (see its `README.md`), not under `docs/`. Gated on the
  above full-corpus cluster run landing.

## Conventions

### Code Style
- **Python**: Enforce with `ruff` (line-length: 100, target: py311)
- **Rules**: E, F, I (imports), UP (pyupgrade)
- **Formatting**: `ruff format`

### Commit Messages
- Use conventional commits when applicable
- Include `Co-Authored-By` for AI-assisted commits

### Docker
- Pin all dependency commits in `docker/build-args.env`
- Lint Dockerfiles with hadolint (failure-threshold: error)
- Tag format: `{precision}`, `latest-{precision}`, `{precision}-{sha}`

### Python (uv)
Use `uv` for all Python operations:
```bash
uv run python script.py
uv run pytest
uv run ruff check .
uv run generate-wing-planform --output wing.vertex
```

### Cluster Path Mappings
| Context | Path |
|---------|------|
| Windows (Z: drive) | `Z:\users\eberrigan\...` |
| WSL | `/mnt/hpi_dev/users/eberrigan/...` |
| Cluster | `/hpi/hpi_dev/users/eberrigan/...` |

`Z:` = `\\multilab-na.ad.salk.edu\hpi_dev` (mapped network drive, Salk VPN required).
Cluster data mounted on Windows via `Z:` is accessible for local Python analysis.

### Running Simulations

#### Cluster (RunAI / A40)

Use WSL with the documented pattern:
```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && /home/elizabeth/.runai/bin/runai <command>"
```
Run scripts and Argo workflow templates live in `cluster/argo/`.

#### Local Docker (A5000, skip RunAI queue)

The dev box has an **RTX A5000 (24 GB, sm_86)** with Docker Desktop GPU passthrough.
Use this for validation / convergence runs without waiting for cluster quota.

**Always use PowerShell** — git-bash (MSYS) mangles `/opt/...` paths to
`C:/Program Files/Git/opt/...`.

```powershell
docker run --rm --gpus all `
  -v "c:/repos/mosquito-cfd/examples/flapping_wing:/workspace" `
  ghcr.io/talmolab/mosquito-cfd:fp64 `
  bash /workspace/<run_script>.sh 2>&1 | tee examples/flapping_wing/sim-<label>.log
```

**A5000 arena cap** — always pass `amrex.the_arena_init_size=18` (value is in GiB).
AMReX defaults to ¾ × VRAM = 18 GiB on a 24 GB card, but set it explicitly so a
future AMReX version can't silently change the default. A40 (40 GB) uses 28.

**CFL at fine 256³ grid** — `inputs.3d.convergence_fine` sets `ns.fixed_dt=0.0005`
(CFL ≈ 0.45, unstable). Use `ns.fixed_dt=0.00025` + `max_step=4000` for a stable
1-wingbeat run. See `examples/flapping_wing/t3c_run_local.sh` for the full override set.

**Image staleness check** — the local fp64 image must be at IAMReX commit `f93dc794`
(T2a 3D d_nn fix). Verify before a long run:
```powershell
docker run --rm ghcr.io/talmolab/mosquito-cfd:fp64 git -C /opt/cfd/IAMReX log --oneline -1
```
If stale, rebuild: `docker build -f docker/Dockerfile.fp64 -t ghcr.io/talmolab/mosquito-cfd:fp64 .`

#### Quick validation example (Docker)
```bash
# Inside container (bash)
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=100

# Output to mounted workspace
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=100
```

### Visualization Tooling

`src/mosquito_cfd/visualization/` (`wing_render.py` shared marker/outline transform helpers,
`flow_video.py` generalized CFD-field video builder, `kinematics_video.py` cluster-free
kinematics preview) plus `src/mosquito_cfd/force_surrogate/comparison_figure.py`
(coarse-vs-fine holdout comparison, config-mean-collapse diagnostic). All rendering/figure
functions install via the optional `viz` dependency group (`scipy`, `scikit-image`,
`imageio-ffmpeg`) — CI installs it (`uv sync --frozen --group viz`); a local dev-host checkout
needs the same flag to import these modules. Four thin `argparse` CLI drivers live in `scripts/`.

See OpenSpec change `add-visualization-tooling` (`design.md` D3) for the two documented
hinge-caveat cases (as-run vs. corrected-for-display) that `make_flow_video.py`/
`make_kinematics_video.py` accept via `--hinge`/`--center` overrides.

```bash
# One CFD-field video (wake-slice | combined-3d | lev-3d | zvelocity-3d)
uv run python scripts/make_flow_video.py \
    --plotfile-dir Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/t3c-fine \
    --field-mode wake-slice \
    --center 4.0 2.0 4.0 --hinge 4.0 0.5 4.0 \
    --stroke-amp-deg 70.0 --pitch-amp-deg 45.0 --frequency-fstar 1.0 \
    --label t3c-fine \
    --out-dir examples/prelim_sweep_fine/figures \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp 2026-08-12T00:00:00+00:00

# Cluster-free kinematics preview (no plotfile, no CFD run)
uv run python scripts/make_kinematics_video.py \
    --config s45_f115_p60 --corpus-dir examples/prelim_sweep_fine \
    --hinge 4.0 0.5 4.0 \
    --label s45_f115_p60 \
    --out-dir examples/prelim_sweep_fine/figures \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp 2026-08-12T00:00:00+00:00

# Coarse-vs-fine holdout force-comparison figure
uv run python scripts/make_comparison_figure.py \
    --coarse-predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \
    --fine-predictions examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet \
    --out-dir docs/visualization \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp 2026-08-12T00:00:00+00:00

# Config-mean-collapse diagnostic (config_resolved R2 vs. per_target RMSE)
uv run python scripts/make_config_mean_collapse_diagnostic.py \
    --coarse-predictions examples/prelim_sweep/surrogate/holdout_predictions.parquet \
    --fine-predictions examples/prelim_sweep_fine/surrogate/holdout_predictions.parquet \
    --coarse-metrics examples/prelim_sweep/surrogate/metrics.json \
    --fine-metrics examples/prelim_sweep_fine/surrogate/metrics.json \
    --out-dir docs/visualization \
    --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \
    --timestamp 2026-08-12T00:00:00+00:00
```

**Mid-sweep partial-corpus check** (corrected 2026-08-31 — the previous version of this note
recommended a plotfile-based video check that cannot work against this corpus's design intent;
see `.claude/commands/submit-cluster-sweep.md` for the full runbook this note now defers to):
once just a few of the 27-config corpus's cluster runs finish (before the full sweep completes),
check those configs' force output directly — **not** `make_flow_video.py`'s multi-frame
workflow, which needs a time series of AMReX plotfiles this corpus is not designed to produce
(every deck's `amr.plot_int` is forced to `-1` by `generate_sweep()`, force-only by design, per
`openspec/specs/force-surrogate/spec.md` and `cluster/argo/README.md`'s "Force-only (CC-6)"
note). Instead:
1. For each finished config, confirm `runs/<config>/IB_Particle_1.csv` has the expected row
   count (`check_completion`'s own logic, matching `sweep_manifest.json`'s `max_step`) and
   `run_metadata.json`'s `stability` field is `stable_at_5e-4` (not a `_fallback` suffix).
2. Build a partial dataset from just the finished configs and eyeball actual force values:
   `uv run python scripts/extract_forces.py --allow-missing ...` (the `--allow-missing` flag
   exists exactly for this — skips configs with no CSV yet instead of hard-failing), then check
   each config's CF_x/CF_z for NaN/Inf, non-zero magnitude, and oscillation at the config's own
   kinematic frequency.

A wing geometry/kinematics bug (the exact class `fix-force-surrogate-sweep-hinge` fixed) is
cheaper to catch this way on 2-3 finished configs than after burning the remaining GPU-hours on
all 27. Before submitting at all, also cluster-freely check wing geometry itself with
`scripts/make_wing_phase_diagnostic.py` (no cluster run needed) as an even earlier, zero-cost
gate. See `.claude/commands/submit-cluster-sweep.md` for the full submission runbook.

## References

### Scientific
- van Veen, W.G., et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." *Journal of Fluid Mechanics*, 936, A3. [DOI:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31)

### Technical
- [IAMReX GitHub](https://github.com/ruohai0925/IAMReX)
- [AMReX Documentation](https://amrex-codes.github.io/amrex/)
- [ALCF APEX Proposal Requirements](https://www.alcf.anl.gov/science/apex-proposal-requirements-and-submissions-instructions)

### Issue Tracking
- [IAMReX #59: FP32 compilation bug](https://github.com/ruohai0925/IAMReX/issues/59) - maintainer confirms no single precision testing