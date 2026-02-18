# Mosquito Swarm CFD

[![CI](https://github.com/talmolab/mosquito-cfd/actions/workflows/ci.yml/badge.svg)](https://github.com/talmolab/mosquito-cfd/actions/workflows/ci.yml)
[![Docker](https://github.com/talmolab/mosquito-cfd/actions/workflows/docker.yml/badge.svg)](https://github.com/talmolab/mosquito-cfd/actions/workflows/docker.yml)

GPU-accelerated CFD simulations of mosquito flight aerodynamics using [IAMReX](https://github.com/ruohai0925/IAMReX) (Immersed-boundary Adaptive Mesh Refinement).

## Purpose

Prototype simulations for the APEX supercomputing proposal, validating against [van Veen et al. (2022)](https://doi.org/10.1017/jfm.2022.31) mosquito wing aerodynamics.

## Quick Start

### Using Docker (Recommended)

```bash
# Pull the pre-built FP32 image
docker pull ghcr.io/talmolab/mosquito-cfd:fp32

# Run with GPU support
docker run --gpus all -it -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp32

# Inside container: run FlowPastSphere example
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun -np 1 ./amr3d.gnu.CUDA.MPI.ex inputs.3d
```

Available images:
- `ghcr.io/talmolab/mosquito-cfd:fp32` - A40 prototyping (fast)
- `ghcr.io/talmolab/mosquito-cfd:fp64` - Validation (accurate)
- `ghcr.io/talmolab/mosquito-cfd:python` - Post-processing only

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

### Build (A40 GPU, FP32)

```bash
cd IAMReX/Tutorials/FlowPastSphere
export AMREX_HOME=/path/to/mosquito-cfd/amrex
export AMREX_HYDRO_HOME=/path/to/mosquito-cfd/AMReX-Hydro

# Edit GNUmakefile:
#   USE_CUDA=TRUE
#   CUDA_ARCH=86
#   PRECISION=FLOAT

make -j$(nproc)
```

### Run

```bash
mpirun -np 1 ./amr3d.gnu.CUDA.MPI.ex inputs.3d
```

## Directory Structure

```
mosquito-cfd/
├── src/mosquito_cfd/ # Python utilities (marker generation, metadata)
├── docker/           # Dockerfiles and build documentation
├── .github/workflows/# CI/CD pipelines
├── openspec/         # Specification-driven development
├── pyproject.toml    # Python project configuration
└── uv.lock           # Dependency lockfile
```

## Hardware Notes

The NVIDIA A40 has strong FP32 (37.4 TFLOPS) but weak FP64 (0.585 TFLOPS). We use `PRECISION=FLOAT` for development and validate accuracy against FP64 spot-checks.

## References

- van Veen et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." *Journal of Fluid Mechanics*, 936, A3. [DOI](https://doi.org/10.1017/jfm.2022.31)
- [IAMReX GitHub](https://github.com/ruohai0925/IAMReX)
- [AMReX Documentation](https://amrex-codes.github.io/amrex/)

## License

TBD
