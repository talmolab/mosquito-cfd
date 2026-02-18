## ADDED Requirements

### Requirement: Reproducible Docker Images

The cfd-infrastructure SHALL provide Docker images with all dependencies required to build and run IAMReX CFD simulations.

#### Scenario: FP32 image availability
- **WHEN** a user pulls `ghcr.io/<owner>/mosquito-cfd:fp32`
- **THEN** the image contains a working IAMReX build compiled with PRECISION=FLOAT, USE_CUDA=TRUE, and CUDA_ARCH=86

#### Scenario: FP64 image availability
- **WHEN** a user pulls `ghcr.io/<owner>/mosquito-cfd:fp64`
- **THEN** the image contains a working IAMReX build compiled with PRECISION=DOUBLE, USE_CUDA=TRUE, and CUDA_ARCH=86

#### Scenario: Python utilities image
- **WHEN** a user pulls `ghcr.io/<owner>/mosquito-cfd:python`
- **THEN** the image contains the mosquito-cfd Python package with all analysis dependencies (yt, matplotlib, numpy)

#### Scenario: Image metadata
- **WHEN** a Docker image is inspected
- **THEN** labels include: AMReX commit SHA, IAMReX commit SHA, CUDA version, precision mode, and build date

### Requirement: Pinned Dependency Versions

The cfd-infrastructure SHALL use explicit, pinned versions for all build dependencies to ensure reproducibility.

#### Scenario: AMReX commit pinning
- **WHEN** a Docker image is built
- **THEN** the AMReX source is cloned at a specific commit SHA defined in build arguments

#### Scenario: Dependency documentation
- **WHEN** dependency commits are updated
- **THEN** a `docker/build-args.env` file documents all pinned SHAs with their corresponding release/date

#### Scenario: Python lockfile
- **WHEN** Python dependencies are installed in a container
- **THEN** the `uv.lock` file is used to ensure exact package versions

### Requirement: CUDA Build Configuration

The cfd-infrastructure SHALL configure CUDA builds optimized for A40 GPUs with documented portability notes.

#### Scenario: A40 architecture targeting
- **WHEN** IAMReX is compiled in the Docker image
- **THEN** CUDA_ARCH=86 is set for Ampere GA102 (A40) architecture

#### Scenario: CUDA version compatibility
- **WHEN** the Docker image is run on a host system
- **THEN** the minimum required NVIDIA driver version is documented in image labels and README

#### Scenario: MPI support
- **WHEN** IAMReX is compiled
- **THEN** USE_MPI=TRUE is set and OpenMPI is available for multi-GPU runs

### Requirement: GitHub Actions CI Pipeline

The cfd-infrastructure SHALL provide automated CI workflows for code quality and Docker builds.

#### Scenario: Python linting on PR
- **WHEN** a pull request is opened or updated
- **THEN** GitHub Actions runs ruff to lint Python code and reports failures

#### Scenario: Python testing on PR
- **WHEN** a pull request is opened or updated
- **THEN** GitHub Actions runs pytest and reports test results

#### Scenario: Dockerfile validation
- **WHEN** a pull request modifies files in `docker/`
- **THEN** GitHub Actions validates Dockerfile syntax

### Requirement: Automated Docker Image Publishing

The cfd-infrastructure SHALL automatically build and publish Docker images on releases and main branch updates.

#### Scenario: Image build on main push
- **WHEN** code is pushed to the main branch
- **THEN** GitHub Actions builds FP32, FP64, and Python images

#### Scenario: Image publication to ghcr.io
- **WHEN** Docker images are built successfully
- **THEN** images are pushed to GitHub Container Registry with appropriate tags

#### Scenario: Version tagging
- **WHEN** a git tag matching `v*` is pushed
- **THEN** Docker images are tagged with the semver version in addition to `latest-{precision}`

#### Scenario: Build caching
- **WHEN** Docker images are built in CI
- **THEN** layer caching is used to minimize rebuild time

### Requirement: HPC Portability Documentation

The cfd-infrastructure SHALL document how to adapt Docker builds for non-Docker HPC environments.

#### Scenario: Native build instructions
- **WHEN** a user needs to build on an HPC system without Docker
- **THEN** documentation provides equivalent build commands derived from the Dockerfile

#### Scenario: Backend portability notes
- **WHEN** a user needs to target AMD (HIP) or Intel (SYCL) GPUs
- **THEN** documentation explains which build flags to change (USE_HIP, USE_SYCL)

#### Scenario: Apptainer conversion
- **WHEN** a user needs to run on HPC systems using Apptainer/Singularity
- **THEN** documentation provides conversion commands from Docker images

### Requirement: uv Python Package Management

The cfd-infrastructure SHALL use uv for all Python dependency management inside containers.

#### Scenario: uv installation in image
- **WHEN** a Docker image with Python is built
- **THEN** uv is installed and used for dependency resolution

#### Scenario: Lockfile-based installation
- **WHEN** Python dependencies are installed in a container
- **THEN** `uv sync` uses the committed `uv.lock` for reproducible installations

#### Scenario: Development environment parity
- **WHEN** a developer sets up a local environment
- **THEN** the same uv commands work locally and in containers