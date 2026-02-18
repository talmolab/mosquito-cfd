# Mosquito Swarm CFD

## Overview

GPU-accelerated CFD simulations of mosquito flight aerodynamics using IAMReX (Immersed-boundary Adaptive Mesh Refinement). This project provides prototype simulations for the APEX supercomputing proposal, validating against van Veen et al. (2022) mosquito wing aerodynamics.

## Goals

1. **Simulation Accuracy**: Validate CFD results against published experimental data from van Veen et al. (2022) for Aedes aegypti mosquito wing aerodynamics
2. **GPU Performance**: Leverage NVIDIA A40 GPUs with FP32 precision for development speed while maintaining accuracy
3. **Reproducibility**: Capture comprehensive metadata for all simulation runs to ensure scientific reproducibility
4. **Scalability**: Design for eventual deployment on APEX supercomputer for large-scale mosquito swarm simulations

## Architecture

### Core Components

- **IAMReX Integration**: External CFD solver using immersed-boundary methods with adaptive mesh refinement
- **Wing Marker Generation**: Python tooling to generate Lagrangian markers for mosquito wing geometry
- **Run Metadata Capture**: Utilities for recording simulation provenance (git commit, hardware, timing, input hashes)

### Technology Stack

- **CFD Solver**: IAMReX (C++/CUDA with AMReX framework)
- **Preprocessing**: Python 3.11+ with NumPy for marker generation
- **Build System**: GNU Make with CUDA 12.x
- **Runtime**: MPI for distributed execution, CUDA for GPU acceleration

## Constraints

- **Hardware**: NVIDIA A40 or newer GPU required (CUDA compute capability 8.6+)
- **Precision**: FP32 for development (A40 has 64:1 FP32:FP64 ratio), FP64 for validation spot-checks
- **Dependencies**: Requires external clones of amrex, AMReX-Hydro, and IAMReX repositories

## Current State

- Wing marker generation implemented for flat plate approximation
- Run metadata capture implemented with git, GPU, and timing information
- IAMReX build and run documented but external to this repository

## References

- van Veen, W.G., et al. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations." Journal of Fluid Mechanics, 936, A3. https://doi.org/10.1017/jfm.2022.31
- IAMReX: https://github.com/ruohai0925/IAMReX
- AMReX: https://amrex-codes.github.io/amrex/