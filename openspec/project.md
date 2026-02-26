# Mosquito Swarm CFD

## Overview

GPU-accelerated CFD simulations of mosquito flight aerodynamics using IAMReX (Immersed-boundary Adaptive Mesh Refinement). This project provides prototype simulations for the [APEX supercomputing proposal](https://www.alcf.anl.gov/science/apex-proposal-requirements-and-submissions-instructions), validating against van Veen et al. (2022) mosquito wing aerodynamics.

**Repository**: [talmolab/mosquito-cfd](https://github.com/talmolab/mosquito-cfd)

## Goals

1. **Simulation Accuracy**: Validate CFD results against published experimental data from van Veen et al. (2022) for Aedes aegypti mosquito wing aerodynamics
2. **GPU Performance**: Leverage NVIDIA A100 GPUs with FP64 for high-throughput simulations
3. **Reproducibility**: Capture comprehensive metadata for all simulation runs to ensure scientific reproducibility
4. **Scalability**: Design for eventual deployment on APEX supercomputer for large-scale mosquito swarm simulations
5. **Proposal Readiness**: Develop benchmarks and scaling studies suitable for ALCF APEX proposal submission

## Architecture

### Directory Structure

```
mosquito-cfd/
├── src/mosquito_cfd/         # Python utilities
│   ├── geometry/             # Wing planform generation (parametric + vertex I/O)
│   └── benchmarks/           # Benchmark runner and metadata capture
├── docker/                   # Container infrastructure
│   ├── Dockerfile.fp64       # Primary simulation image
│   ├── Dockerfile.fp32       # Deprecated (upstream unsupported)
│   └── Dockerfile.python     # Post-processing only
├── examples/                 # Validation cases
│   └── flow_past_sphere/     # Classic CFD validation case
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
- **Development**: NVIDIA A40 (local/Salk cluster)
- **Target**: NVIDIA A100 (ALCF APEX systems)
- **CUDA**: Compute capability 8.0+ (A100) or 8.6+ (A40)
- **Driver**: 550.54.14+ (for CUDA 12.4)
- **Memory**: 40+ GB GPU RAM on A100

### Precision
- **FP64 Only**: All benchmarks and simulations use double precision
- **Rationale**: IAMReX maintainer [does not test single precision](https://github.com/ruohai0925/IAMReX/issues/59); FP64 ensures scientific accuracy
- **Target Hardware**: NVIDIA A100 (19.5 TFLOPS FP64) on ALCF systems

### Dependencies
- Requires external clones of amrex, AMReX-Hydro, and IAMReX repositories
- Pinned commits managed in `docker/build-args.env`

## Current State

### Implemented
- [x] Parametric wing planform generation (`geometry/` package)
- [x] Run metadata capture with docker/git/hardware tracking (`benchmarks/metadata`)
- [x] Docker infrastructure with FP64 working builds
- [x] GitHub Actions CI/CD for lint/test/publish
- [x] Flow past sphere validation example (100 timesteps verified on A40)

### Not Planned
- FP32 builds - upstream IAMReX does not support; using FP64 on A100 instead

### In Progress
- [ ] **APEX benchmarking** ([add-apex-benchmarking](changes/add-apex-benchmarking/proposal.md)) - FlowPastSphere and heaving ellipsoid validation cases
- [ ] **Arbitrary geometry support** ([add-arbitrary-geometry](changes/add-arbitrary-geometry/proposal.md)) - External vertex file loading + prescribed kinematics for flapping wing validation

### Pending
- [ ] Scaling benchmarks for APEX proposal
- [ ] Multi-GPU / multi-node validation

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

### CLI Tools
```bash
# Generate wing vertex file from parametric planform
uv run generate-wing-planform --output wing.vertex
```

### Running Simulations
```bash
# Using Docker (recommended)
docker run --gpus all -it -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp64
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=100

# Output to mounted workspace
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=100
```

## References

### Scientific
- van Veen, W.G., et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." *Journal of Fluid Mechanics*, 936, A3. [DOI:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31)

### Technical
- [IAMReX GitHub](https://github.com/ruohai0925/IAMReX)
- [AMReX Documentation](https://amrex-codes.github.io/amrex/)
- [ALCF APEX Proposal Requirements](https://www.alcf.anl.gov/science/apex-proposal-requirements-and-submissions-instructions)

### Issue Tracking
- [IAMReX #59: FP32 compilation bug](https://github.com/ruohai0925/IAMReX/issues/59) - maintainer confirms no single precision testing