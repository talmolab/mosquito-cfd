## 1. Repository Setup

- [x] 1.1 Create `docker/` directory in mosquito-cfd repo
- [x] 1.2 Create `.github/workflows/` directory for GitHub Actions
- [x] 1.3 Add `.dockerignore` to exclude unnecessary files from build context
- [ ] 1.4 Update `.gitignore` for any Docker-related artifacts

## 2. Docker Base Configuration

- [x] 2.1 Document current IAMReX dependency commits (amrex, AMReX-Hydro, IAMReX)
- [x] 2.2 Create `docker/build-args.env` with pinned commit SHAs
- [ ] 2.3 Test base image `nvidia/cuda:12.4.1-devel-ubuntu22.04` builds locally

## 3. FP32 Dockerfile (Primary Prototyping Image)

- [x] 3.1 Create `docker/Dockerfile.fp32` with:
  - [x] 3.1.1 CUDA 12.4 base image
  - [x] 3.1.2 System dependencies (g++, gfortran, openmpi, cmake)
  - [x] 3.1.3 ARGs for IAMReX/AMReX/AMReX-Hydro commit SHAs
  - [x] 3.1.4 Clone and build AMReX with PRECISION=FLOAT, USE_CUDA=TRUE, CUDA_ARCH=86
  - [x] 3.1.5 Clone and build AMReX-Hydro
  - [x] 3.1.6 Clone and build IAMReX FlowPastSphere tutorial
  - [x] 3.1.7 Install uv and Python dependencies from pyproject.toml
  - [x] 3.1.8 Add labels (version, commit SHAs, precision, cuda_arch)
- [ ] 3.2 Build and test FP32 image locally
- [ ] 3.3 Verify FlowPastSphere runs on A40 GPU inside container
- [ ] 3.4 Document image size and build time

## 4. FP64 Dockerfile (Validation Image)

- [x] 4.1 Create `docker/Dockerfile.fp64` (copy FP32, change PRECISION=DOUBLE)
- [ ] 4.2 Build and test FP64 image locally
- [ ] 4.3 Verify FP64 FlowPastSphere runs (expect ~10-20x slower than FP32 on A40)
- [ ] 4.4 Compare timing between FP32 and FP64 containers

## 5. Python-Only Dockerfile (Analysis Image)

- [x] 5.1 Create `docker/Dockerfile.python` with:
  - [x] 5.1.1 Lightweight base (debian:bookworm-slim)
  - [x] 5.1.2 uv installation
  - [x] 5.1.3 mosquito-cfd Python package installation
  - [x] 5.1.4 yt, matplotlib, numpy for post-processing
- [ ] 5.2 Build and test Python image locally
- [ ] 5.3 Verify `generate-markers` and `run-metadata` CLI commands work

## 6. GitHub Actions CI Workflow

- [x] 6.1 Create `.github/workflows/ci.yml` with:
  - [x] 6.1.1 Trigger on pull_request and push to main
  - [x] 6.1.2 Lint Python with ruff
  - [x] 6.1.3 Run pytest (currently no tests, but infrastructure ready)
  - [x] 6.1.4 Verify Dockerfiles are syntactically valid (hadolint)
- [ ] 6.2 Test CI workflow on a feature branch PR
- [x] 6.3 Add status badge to README.md

## 7. GitHub Actions Docker Workflow

- [x] 7.1 Create `.github/workflows/docker.yml` with:
  - [x] 7.1.1 Trigger on push to main and version tags (v*)
  - [x] 7.1.2 Login to ghcr.io using GITHUB_TOKEN
  - [x] 7.1.3 Build FP32 image with cache
  - [x] 7.1.4 Build FP64 image with cache
  - [x] 7.1.5 Build Python image with cache
  - [x] 7.1.6 Push with tags: `latest-{fp32,fp64,python}`, git SHA
  - [x] 7.1.7 workflow_dispatch with inputs (images, push, tag_suffix, no_cache)
- [x] 7.2 Test workflow by pushing to main
- [x] 7.3 Verify images appear in GitHub Container Registry
- [ ] 7.4 Test pulling and running published images

## 8. Documentation

- [x] 8.1 Update README.md with:
  - [x] 8.1.1 Quick start for pulling pre-built images
  - [x] 8.1.2 Building images locally
  - [x] 8.1.3 Running simulations in container
  - [x] 8.1.4 GPU requirements and driver compatibility
- [x] 8.2 Create `docker/README.md` with:
  - [x] 8.2.1 Detailed build argument documentation
  - [x] 8.2.2 Instructions for updating dependency commits
  - [x] 8.2.3 HPC portability notes (SYCL/HIP native builds)
  - [x] 8.2.4 Apptainer/Singularity conversion instructions
- [x] 8.3 Add CUDA/driver compatibility matrix

## 9. Integration with cfd-pipeline

- [ ] 9.1 Update `add-iamrex-cfd-prototype` tasks.md to reference container images
- [ ] 9.2 Create RunAI job template using ghcr.io images
- [ ] 9.3 Verify metadata capture works inside container
- [ ] 9.4 Test full Stage 0 (build validation) workflow using container

## 10. Validation and Release

- [ ] 10.1 Manual GPU test on Salk A40 cluster via RunAI
- [ ] 10.2 Compare container vs native build performance (should be equivalent)
- [ ] 10.3 Tag v0.1.0 release to trigger initial image publication
- [ ] 10.4 Verify reproducibility: rebuild from Dockerfile, compare checksums