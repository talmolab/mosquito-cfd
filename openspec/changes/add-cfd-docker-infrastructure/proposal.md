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

### Descoped: FP32 image (obsolete)

The FP32 image is **descoped** — not merely blocked. Rationale:

1. **Upstream blocker, unresolved:** IAMReX fails to compile with `PRECISION=FLOAT` + `USE_CUDA=TRUE` (filed as [ruohai0925/IAMReX#59](https://github.com/ruohai0925/IAMReX/issues/59)); no upstream fix.
2. **Motivation no longer holds:** FP32 was intended for *fast A40 prototyping*, but every validated benchmark (sphere, ellipsoid, flapping wing) and the Track B force corpus run in **FP64**, and a coarse-grid FP64 wingbeat already completes in ~2.4 min on an A40 — the prototyping speedup is not needed.
3. **Accuracy:** FP32 raises pressure-projection accuracy concerns for CFD that produces *training data*; FP64 is the defensible choice end-to-end.
4. **Forward target:** the production/grant target (H100) has strong native FP64.

**Supported image set is therefore FP64 (CFD) + Python (analysis).** FP32 work (Dockerfile, CI build, upstream-fix investigation) is retained in history but marked obsolete in `tasks.md`; the `cfd-infrastructure` spec no longer promises an FP32 image. If FP32 is ever revived, it should be a new, scoped change.

## Impact

- New spec: `cfd-infrastructure` (containerization, CI/CD, image registry)
- Affected code: `mosquito-cfd` repo (add docker/, .github/workflows/)
- Related proposal: `add-iamrex-cfd-prototype` in vaults/openspec (answers open question on containerization)
- Related docs: [IAMReX A40 Prototyping Guide](https://gist.github.com/talmo/d06fa93906c763f889043e19c8fd9e00)