# Mosquito Swarm CFD

GPU-accelerated CFD simulations of mosquito flight aerodynamics using [IAMReX](https://github.com/ruohai0925/IAMReX) (Immersed-boundary Adaptive Mesh Refinement).

## Purpose

Prototype simulations for the APEX supercomputing proposal, validating against [van Veen et al. (2022)](https://doi.org/10.1017/jfm.2022.31) mosquito wing aerodynamics.

## Quick Start

### Prerequisites

- CUDA 12.x with A40 or newer GPU
- MPI (OpenMPI recommended)
- GNU compilers (g++, gfortran)

### Clone Dependencies

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
├── docker/           # Containerized builds
├── inputs/           # Input file templates
├── scripts/          # Utility scripts (marker generation, metadata)
├── validation/       # Reference data and comparison scripts
└── docs/             # Extended documentation
```

## Hardware Notes

The NVIDIA A40 has strong FP32 (37.4 TFLOPS) but weak FP64 (0.585 TFLOPS). We use `PRECISION=FLOAT` for development and validate accuracy against FP64 spot-checks.

## References

- van Veen et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." *Journal of Fluid Mechanics*, 936, A3. [DOI](https://doi.org/10.1017/jfm.2022.31)
- [IAMReX GitHub](https://github.com/ruohai0925/IAMReX)
- [AMReX Documentation](https://amrex-codes.github.io/amrex/)

## License

TBD
