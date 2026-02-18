## Context

The mosquito-cfd project needs reproducible IAMReX builds with CUDA support for GPU-accelerated CFD simulations. Builds must work on:
- Local development (A40 workstations)
- Salk RunAI cluster (A40 GPUs)
- Future HPC systems (ALCF Aurora with SYCL, OLCF Frontier with HIP)

### Stakeholders
- Researchers: Need consistent, reproducible simulation environments
- CI/CD systems: Automated testing and image publication
- HPC admins: Reference build instructions for native HPC builds

### Constraints
- A40 GPU: CUDA_ARCH=86 (Ampere GA102), weak FP64 (0.585 TFLOPS), strong FP32 (37.4 TFLOPS)
- IAMReX: No official CUDA Docker image exists; AMReX's official container is CPU-only
- HPC systems: Typically don't use Docker; Dockerfile serves as reproducible build documentation

## Goals / Non-Goals

### Goals
1. Provide reproducible Docker images for FP32 and FP64 IAMReX builds
2. Automate Python linting/testing and Docker builds via GitHub Actions
3. Document all build configurations for HPC portability
4. Use uv for Python dependency management (fast, lockfile-based)

### Non-Goals
- SYCL or HIP builds (deferred to HPC allocation phase)
- Apptainer/Singularity conversion (manual user responsibility)
- GPU CI testing (requires self-hosted runners with GPUs)

## Decisions

### Decision 1: Base Image - `nvidia/cuda:12.4.1-devel-ubuntu22.04`

**What**: Use NVIDIA's official CUDA 12.4 development image on Ubuntu 22.04.

**Why**:
- CUDA 12.4 is current stable with good A40/H100 support
- `-devel` variant includes nvcc compiler needed for building
- Ubuntu 22.04 LTS provides stable base with modern gfortran/g++

**Alternatives considered**:
- CUDA 11.8: More conservative but older toolchain
- CUDA 12.6: Latest but may have driver compatibility issues
- Rocky Linux base: Less familiar, no clear benefit

### Decision 2: Separate Images for FP32 and FP64

**What**: Two distinct Dockerfiles producing `mosquito-cfd:fp32` and `mosquito-cfd:fp64`.

**Why**:
- Clarity: Precision is a compile-time decision in AMReX (PRECISION=FLOAT vs DOUBLE)
- No ambiguity about which binary you're running
- Smaller images (no dual binaries)
- Matches the prototyping strategy: FP32 for speed, FP64 for validation

**Alternatives considered**:
- Single image with both: Larger, confusing which binary to use
- Runtime precision selection: Not possible with AMReX architecture

### Decision 3: Clone Dependencies at Build Time with Pinned Commits

**What**: Dockerfile uses `ARG` for commit SHAs; clones repos during build.

```dockerfile
ARG AMREX_COMMIT=abc123
RUN git clone https://github.com/ruohai0925/amrex && \
    cd amrex && git checkout ${AMREX_COMMIT}
```

**Why**:
- Reproducibility: Exact commits documented in Dockerfile/CI
- No submodule complexity in main repo
- Easy to update: Change ARG, rebuild
- Build-time clone ensures fresh source

**Alternatives considered**:
- Git submodules: Adds workflow complexity, harder to update
- Release tarballs: IAMReX doesn't have formal releases

### Decision 4: GitHub Container Registry (ghcr.io)

**What**: Publish images to `ghcr.io/<owner>/mosquito-cfd`.

**Why**:
- Free for public repos
- Integrated with GitHub Actions (no extra credentials)
- Supports multi-platform manifests if needed later

**Alternatives considered**:
- Docker Hub: Rate limits, requires separate credentials
- Both registries: More maintenance overhead

### Decision 5: uv for Python Package Management

**What**: Use uv instead of pip/conda inside Docker and for local development.

**Why**:
- 10-100x faster than pip
- Lockfile (`uv.lock`) ensures reproducible installs
- Already configured in mosquito-cfd repo
- Single tool for venv creation and package install

**Alternatives considered**:
- pip + requirements.txt: Slower, no lockfile by default
- conda: Heavier, mixing with CUDA base images is complex

### Decision 6: Multi-Stage Dockerfile for Python-Only Image

**What**: Provide a lightweight `Dockerfile.python` for post-processing.

**Why**:
- Python utilities (yt, matplotlib) don't need CUDA compiler
- Smaller image for analysis workflows
- Can run on CPU-only systems

**Structure**:
```
Dockerfile.fp32  → ghcr.io/*/mosquito-cfd:fp32     (~8-10 GB)
Dockerfile.fp64  → ghcr.io/*/mosquito-cfd:fp64     (~8-10 GB)
Dockerfile.python → ghcr.io/*/mosquito-cfd:python  (~1-2 GB)
```

### Decision 7: CI Workflow Structure

**What**: Two separate GitHub Actions workflows.

1. **ci.yml** (on PR/push):
   - Lint Python with ruff
   - Run pytest
   - Optionally build Docker images (no push) to verify Dockerfile syntax

2. **docker.yml** (on push to main, tags):
   - Build FP32, FP64, and Python images
   - Push to ghcr.io
   - Tag with `latest-fp32`, `latest-fp64`, `latest-python`, and git SHA

**Why**: Separation allows fast PR feedback (lint/test) while limiting expensive Docker builds to merged code.

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CUDA version mismatch with host driver | Low | High | Document minimum driver version; test on target systems |
| IAMReX upstream changes break build | Medium | Medium | Pin commits; update deliberately with testing |
| Large image size (~10GB) | Certain | Low | Acceptable for HPC; provide Python-only image for analysis |
| GitHub Actions runner timeout | Low | Medium | Cache Docker layers; parallelize builds |
| Windows Docker compatibility | Low | Low | Primary use is Linux; document WSL2 requirements |

## Migration Plan

N/A - new infrastructure, no existing containers to migrate.

### Rollout Sequence
1. Merge Dockerfiles to mosquito-cfd repo
2. Enable GitHub Actions CI
3. Manually verify images build and run on A40
4. Tag v0.1.0 release to trigger image publication
5. Update add-iamrex-cfd-prototype tasks to use container images

## Open Questions

1. **GPU CI testing**: Should we set up a self-hosted runner with GPU for integration tests? (Deferred - manual validation sufficient initially)
2. **Image versioning**: Should images track mosquito-cfd releases, AMReX commits, or independent scheme? (Proposed: mosquito-cfd semver with AMReX commit in labels)
3. **Apptainer conversion**: Should CI auto-generate .sif files? (Deferred - users can convert manually for HPC)