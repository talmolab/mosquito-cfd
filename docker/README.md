# Docker Images for Mosquito CFD

This directory contains Dockerfiles for building reproducible IAMReX CFD simulation environments.

## Available Images

| Image | Tag | Purpose | Size |
|-------|-----|---------|------|
| `ghcr.io/talmolab/mosquito-cfd:fp64` | `fp64`, `latest-fp64` | CFD simulation (the only supported precision) | ~8-10 GB |
| `ghcr.io/talmolab/mosquito-cfd:python` | `python`, `latest-python` | Post-processing only | ~1-2 GB |

## Quick Start

```bash
# Pull the FP64 image
docker pull ghcr.io/talmolab/mosquito-cfd:fp64

# Run with GPU support
docker run --gpus all -it ghcr.io/talmolab/mosquito-cfd:fp64

# Run with mounted workspace
docker run --gpus all -it -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp64
```

## Why FP64 only

An earlier FP32 image existed for fast A40 prototyping (37.4 vs. 0.585 TFLOPS), but it is
**descoped as obsolete**, not merely blocked:

- It's blocked by an unresolved [upstream IAMReX compilation bug](https://github.com/ruohai0925/IAMReX/issues/59)
- The "fast prototyping" motivation no longer holds: every validated benchmark (sphere, ellipsoid,
  flapping wing) and the Track B force corpus already run in FP64, and a coarse-grid FP64 wingbeat
  completes in ~2.4 min on an A40 — the speedup isn't needed
- FP32 raises pressure-projection accuracy concerns for CFD that produces *training data*; FP64 is
  the defensible choice end-to-end

The `Dockerfile.fp32` recipe is retained in the repo for history/potential future revival, and can
still be built manually (`docker build -f docker/Dockerfile.fp32 ...` or via the `docker.yml`
workflow's manual `workflow_dispatch` trigger), but it is **not** built automatically on push and
**not** published to `ghcr.io`. If FP32 is ever revived, it should be a new, scoped change.

## Building Locally

```bash
# Build FP64 image
docker build -f docker/Dockerfile.fp64 -t mosquito-cfd:fp64 .

# Build Python-only image
docker build -f docker/Dockerfile.python -t mosquito-cfd:python .

# Build the descoped FP32 image manually (history/future-revival only; not CI-built or published)
docker build -f docker/Dockerfile.fp32 -t mosquito-cfd:fp32 .
```

### Build Arguments

Override pinned commits with `--build-arg`:

```bash
docker build -f docker/Dockerfile.fp64 \
  --build-arg IAMREX_COMMIT=abc123 \
  --build-arg AMREX_COMMIT=def456 \
  -t mosquito-cfd:fp64-custom .
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
docker run --gpus all -it ghcr.io/talmolab/mosquito-cfd:fp64

# Run FlowPastSphere example (10 timesteps)
docker run --gpus all ghcr.io/talmolab/mosquito-cfd:fp64 \
  bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=10"

# Generate wing markers
docker run -v $(pwd):/workspace ghcr.io/talmolab/mosquito-cfd:fp64 \
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
apptainer pull mosquito-cfd-fp64.sif docker://ghcr.io/talmolab/mosquito-cfd:fp64

# Run with GPU
apptainer run --nv mosquito-cfd-fp64.sif
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

### "fatal: reference is not a tree" during Docker build

**Symptom**: CI build fails with:
```
fatal: reference is not a tree: 5261817c53116695be2a9d29ff95dce1a6a39f9d
```

**Cause**: The `ruohai0925/amrex` fork periodically rebases against upstream AMReX, which rewrites git history and invalidates previously pinned commit SHAs. Docker layer caching may hide this issue until the cache is invalidated.

**Solution**:
1. Get the current HEAD of the development branch:
   ```bash
   git ls-remote https://github.com/ruohai0925/amrex.git refs/heads/development
   ```

2. Update `docker/build-args.env` with the new SHA:
   ```bash
   AMREX_COMMIT=<new-sha>
   ```

3. Update the `ARG AMREX_COMMIT` in both Dockerfiles

4. Verify locally before pushing:
   ```bash
   git clone https://github.com/ruohai0925/amrex.git /tmp/amrex-test
   cd /tmp/amrex-test && git checkout <new-sha>
   ```

**Prevention**: This will happen again whenever `ruohai0925/amrex` rebases. Consider:
- Using official AMReX releases (`AMReX-Codes/amrex` tags like `26.02`) if IAMReX compatibility allows
- Documenting the expected rebase frequency
- Setting up alerts when CI fails with this specific error