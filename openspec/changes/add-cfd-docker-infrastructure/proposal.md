## Why

The mosquito-cfd project requires containerized, reproducible builds of IAMReX with GPU support to:
1. Enable reproducible CFD simulations across local workstations, Salk RunAI cluster, and future HPC systems
2. Automate quality checks (linting, testing) and Docker image publication via CI/CD
3. Support both FP32 (fast A40 prototyping) and FP64 (validation) precision builds in separate, well-documented images

Currently, IAMReX must be manually cloned and built with specific compiler flags. This creates reproducibility risks and makes onboarding new team members or systems error-prone. The existing `add-iamrex-cfd-prototype` proposal identified containerization as an open question—this proposal provides the answer.

## What Changes

### New Capability: `cfd-infrastructure`

Docker and CI/CD infrastructure for reproducible IAMReX builds:

- **Multi-precision Dockerfiles**: Separate images for FP32 and FP64 builds based on `nvidia/cuda:12.4.1-devel-ubuntu22.04`
- **Pinned dependencies**: IAMReX, AMReX-Hydro, and AMReX cloned at specific commit SHAs for reproducibility
- **GitHub Actions CI/CD**:
  - Lint Python code with ruff on PRs
  - Run pytest for Python utilities
  - Build and push Docker images to ghcr.io on main/release
- **uv for Python**: Fast, reproducible Python dependency management inside containers

### Key Design Principles

1. **Reproducibility over convenience**: Pinned commits, explicit versions, documented build args
2. **Precision separation**: FP32 and FP64 as distinct images (not runtime flags) for clarity
3. **HPC portability**: Dockerfile serves as build recipe for non-Docker HPC systems (SYCL/HIP rebuilds)

### Infrastructure Components

| Component | Purpose |
|-----------|---------|
| `docker/Dockerfile.fp32` | FP32 CUDA build (A40 prototyping) |
| `docker/Dockerfile.fp64` | FP64 CUDA build (validation) |
| `docker/Dockerfile.python` | Python utilities only (post-processing) |
| `.github/workflows/ci.yml` | Lint + test on PR |
| `.github/workflows/docker.yml` | Build + push images on main/tag |

## Impact

- New spec: `cfd-infrastructure` (containerization, CI/CD, image registry)
- Affected code: `mosquito-cfd` repo (add docker/, .github/workflows/)
- Related proposal: `add-iamrex-cfd-prototype` in vaults/openspec (answers open question on containerization)
- Related docs: [IAMReX A40 Prototyping Guide](https://gist.github.com/talmo/d06fa93906c763f889043e19c8fd9e00)