# Mosquito Swarm CFD

[![CI](https://github.com/talmolab/mosquito-cfd/actions/workflows/ci.yml/badge.svg)](https://github.com/talmolab/mosquito-cfd/actions/workflows/ci.yml)
[![Docker](https://github.com/talmolab/mosquito-cfd/actions/workflows/docker.yml/badge.svg)](https://github.com/talmolab/mosquito-cfd/actions/workflows/docker.yml)

GPU-accelerated CFD simulations of mosquito flight aerodynamics using [IAMReX](https://github.com/ruohai0925/IAMReX) (Immersed-boundary Adaptive Mesh Refinement).

## Purpose

Prototype simulations for the APEX supercomputing proposal, validating against [van Veen et al. (2022)](https://doi.org/10.1017/jfm.2022.31) mosquito wing aerodynamics.

## Quick Start

### Using Docker (Recommended)

```bash
# Pull the pre-built FP64 image
docker pull ghcr.io/talmolab/mosquito-cfd:fp64

# Run with GPU support
docker run --gpus all -it -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp64

# Inside container: run FlowPastSphere example
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=10
```

Available images:
- `ghcr.io/talmolab/mosquito-cfd:fp64` - CFD simulation (the only supported precision)
- `ghcr.io/talmolab/mosquito-cfd:python` - Post-processing only

FP32 is **descoped** (not just blocked): the "fast A40 prototyping" motivation no longer holds now
that all validated benchmarks and the Track B force corpus run in FP64, and a coarse-grid FP64
wingbeat already completes in ~2.4 min on an A40. See [docker/README.md](docker/README.md) for
details; the FP32 Dockerfile is retained in history but no longer built or published.

See [docker/README.md](docker/README.md) for full documentation.

### Manual Build

#### Prerequisites

- CUDA 12.x with A40 or newer GPU
- MPI (OpenMPI recommended)
- GNU compilers (g++, gfortran)

#### Clone Dependencies

```bash
cd /path/to/mosquito-cfd
git clone https://github.com/ruohai0925/amrex
git clone https://github.com/ruohai0925/AMReX-Hydro
git clone https://github.com/ruohai0925/IAMReX.git -b development
```

### Build (GPU, FP64)

```bash
cd IAMReX/Tutorials/FlowPastSphere
export AMREX_HOME=/path/to/mosquito-cfd/amrex
export AMREX_HYDRO_HOME=/path/to/mosquito-cfd/AMReX-Hydro

# Edit GNUmakefile:
#   USE_CUDA=TRUE
#   CUDA_ARCH=86  # or your GPU's compute capability
#   PRECISION=DOUBLE

make -j$(nproc)
```

### Run

```bash
mpirun -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=10
```

## Directory Structure

```
mosquito-cfd/
├── src/mosquito_cfd/ # Python utilities (marker generation, metadata, force surrogate)
├── scripts/          # Thin CLI drivers over the library (e.g. run_sweep.py, extract_forces.py)
├── examples/         # Validation cases + force-surrogate sweep corpus
├── cluster/argo/     # Argo Workflows for cluster-side sweep orchestration
├── docker/           # Dockerfiles and build documentation
├── .github/workflows/# CI/CD pipelines
├── openspec/         # Specification-driven development
├── pyproject.toml    # Python project configuration
└── uv.lock           # Dependency lockfile
```

## Hardware Notes

The project uses `PRECISION=DOUBLE` (FP64) throughout, a deliberate choice: FP32 raised pressure-
projection accuracy concerns for CFD that produces training data, and every validated benchmark
(sphere, ellipsoid, flapping wing) plus the Track B force corpus already runs comfortably in FP64
on an A40, so the FP32-for-speed tradeoff was never actually needed.

## References

- van Veen et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." *Journal of Fluid Mechanics*, 936, A3. [DOI](https://doi.org/10.1017/jfm.2022.31)
- [IAMReX GitHub](https://github.com/ruohai0925/IAMReX)
- [AMReX Documentation](https://amrex-codes.github.io/amrex/)

## License

TBD
