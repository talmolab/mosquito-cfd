# Docker Images for Mosquito CFD

This directory contains Dockerfiles for building reproducible IAMReX CFD simulation environments.

## Available Images

| Image | Tag | Purpose | Size |
|-------|-----|---------|------|
| `ghcr.io/talmolab/mosquito-cfd:fp32` | `fp32`, `latest-fp32` | A40 GPU prototyping (fast) | ~8-10 GB |
| `ghcr.io/talmolab/mosquito-cfd:fp64` | `fp64`, `latest-fp64` | Validation runs (accurate) | ~8-10 GB |
| `ghcr.io/talmolab/mosquito-cfd:python` | `python`, `latest-python` | Post-processing only | ~1-2 GB |

## Quick Start

```bash
# Pull the FP32 image (recommended for development)
docker pull ghcr.io/talmolab/mosquito-cfd:fp32

# Run with GPU support
docker run --gpus all -it ghcr.io/talmolab/mosquito-cfd:fp32

# Run with mounted workspace
docker run --gpus all -it -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp32
```

## FP32 vs FP64

| Aspect | FP32 | FP64 |
|--------|------|------|
| **A40 Performance** | 37.4 TFLOPS | 0.585 TFLOPS (64x slower) |
| **Use Case** | Development, iteration | Validation, publication |
| **Memory** | Half of FP64 | Full precision |
| **Accuracy** | Sufficient for Re < 300 | Reference standard |

**Recommendation**: Use FP32 for daily development. Run FP64 for final validation to verify accuracy.

## Building Locally

```bash
# Build FP32 image
docker build -f docker/Dockerfile.fp32 -t mosquito-cfd:fp32 .

# Build FP64 image
docker build -f docker/Dockerfile.fp64 -t mosquito-cfd:fp64 .

# Build Python-only image
docker build -f docker/Dockerfile.python -t mosquito-cfd:python .
```

### Build Arguments

Override pinned commits with `--build-arg`:

```bash
docker build -f docker/Dockerfile.fp32 \
  --build-arg IAMREX_COMMIT=abc123 \
  --build-arg AMREX_COMMIT=def456 \
  -t mosquito-cfd:fp32-custom .
```

| Argument | Default | Description |
|----------|---------|-------------|
| `IAMREX_COMMIT` | See `build-args.env` | IAMReX git commit SHA |
| `AMREX_COMMIT` | See `build-args.env` | AMReX git commit SHA |
| `AMREX_HYDRO_COMMIT` | See `build-args.env` | AMReX-Hydro git commit SHA |
| `CUDA_ARCH` | `86` | CUDA compute capability (86 = A40) |

## Running Simulations

```bash
# Interactive shell
docker run --gpus all -it ghcr.io/talmolab/mosquito-cfd:fp32

# Run FlowPastSphere example
docker run --gpus all ghcr.io/talmolab/mosquito-cfd:fp32 \
  bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && mpirun -np 1 ./amr3d.gnu.CUDA.MPI.ex inputs.3d"

# Generate wing markers
docker run -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp32 \
  bash -c "cd /opt/cfd/mosquito-cfd && uv run generate-markers --output /workspace/wing_markers.dat"
```

## GPU Requirements

- **CUDA Compute Capability**: 8.6+ (A40, A100, H100)
- **Minimum Driver Version**: 550.54.14 (for CUDA 12.4)
- **Memory**: 8+ GB GPU RAM recommended

Check your driver version:
```bash
nvidia-smi --query-gpu=driver_version --format=csv,noheader
```

## HPC Portability

These Dockerfiles serve as build recipes for non-Docker HPC environments.

### Native Build (without Docker)

Extract build commands from the Dockerfile:

```bash
# Clone dependencies
git clone https://github.com/ruohai0925/amrex.git
git clone https://github.com/ruohai0925/AMReX-Hydro.git
git clone https://github.com/ruohai0925/IAMReX.git -b development

# Set environment
export AMREX_HOME=$(pwd)/amrex
export AMREX_HYDRO_HOME=$(pwd)/AMReX-Hydro

# Build IAMReX
cd IAMReX/Tutorials/FlowPastSphere
# Edit GNUmakefile with your settings
make -j$(nproc)
```

### Alternative GPU Backends

For non-NVIDIA systems, change the build flags:

| System | Backend | Build Flag |
|--------|---------|------------|
| NVIDIA (A40, A100, H100) | CUDA | `USE_CUDA=TRUE` |
| AMD (MI250, MI300) | HIP | `USE_HIP=TRUE` |
| Intel (Max 1550) | SYCL | `USE_SYCL=TRUE` |

### Apptainer/Singularity Conversion

```bash
# Convert Docker image to Apptainer SIF
apptainer pull mosquito-cfd-fp32.sif docker://ghcr.io/talmolab/mosquito-cfd:fp32

# Run with GPU
apptainer run --nv mosquito-cfd-fp32.sif
```

## Updating Dependencies

1. Get latest commits from upstream:
   ```bash
   gh api repos/ruohai0925/IAMReX/commits/development --jq '.sha'
   gh api repos/ruohai0925/amrex/commits/development --jq '.sha'
   gh api repos/ruohai0925/AMReX-Hydro/commits/main --jq '.sha'
   ```

2. Update `docker/build-args.env` with new SHAs

3. Update ARG defaults in Dockerfiles

4. Rebuild and test before committing

## Troubleshooting

### "CUDA driver version is insufficient"

Your host NVIDIA driver is too old. Update to driver version 550+ for CUDA 12.4.

### "No GPU detected"

Ensure you're using `--gpus all` flag and have nvidia-container-toolkit installed:
```bash
sudo apt-get install nvidia-container-toolkit
sudo systemctl restart docker
```

### Build fails at IAMReX compilation

Check the build log at `/opt/cfd/build.log` inside the container. Common issues:
- Missing CUDA toolkit (should not happen with our base image)
- Incompatible compiler versions
- Out of memory during parallel build (reduce `-j` flag)