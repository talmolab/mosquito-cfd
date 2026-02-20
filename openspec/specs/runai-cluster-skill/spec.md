# runai-cluster-skill Specification

## Purpose
TBD - created by archiving change add-runai-cluster-skill. Update Purpose after archive.
## Requirements
### Requirement: WSL Command Execution Pattern

The runai-cluster-skill SHALL execute all RunAI CLI commands via WSL with the correct KUBECONFIG configuration.

#### Scenario: Basic command pattern

- **GIVEN** a user on Windows needs to run a RunAI command
- **WHEN** Claude assists with RunAI operations
- **THEN** commands follow the pattern: `wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && /home/elizabeth/.runai/bin/runai <command>"`

#### Scenario: Command verification

- **WHEN** a RunAI command is constructed
- **THEN** the skill verifies KUBECONFIG path and runai binary path are correct for the user's WSL environment

### Requirement: Path Mapping Reference

The runai-cluster-skill SHALL document path mappings between Windows, WSL, and cluster contexts.

#### Scenario: Path translation table

- **WHEN** a user needs to specify paths for RunAI jobs
- **THEN** the skill provides translations:
  - Windows: `Z:\users\eberrigan\...` (drive letter varies)
  - WSL: `/mnt/hpi_dev/users/eberrigan/...`
  - Cluster: `/hpi/hpi_dev/users/eberrigan/...`

#### Scenario: Host-path mount syntax

- **WHEN** a job requires data mounts
- **THEN** the skill uses cluster paths with format: `--host-path path=/hpi/hpi_dev/...,mount=/data,mount-propagation=HostToContainer,readwrite`

### Requirement: Workspace Management Commands

The runai-cluster-skill SHALL provide templates for all workspace lifecycle operations.

#### Scenario: List workspaces

- **WHEN** a user needs to see running jobs
- **THEN** the skill provides: `runai workspace list -p talmo-lab`

#### Scenario: Submit workspace

- **WHEN** a user needs to submit a GPU job
- **THEN** the skill provides the full `runai workspace submit` command with:
  - `--project talmo-lab`
  - `--image ghcr.io/talmolab/mosquito-cfd:<tag>`
  - `--gpu-devices-request <N>`
  - `--cpu-core-request <N>`
  - `--cpu-memory-request <size>`
  - `--host-path` mounts for data

#### Scenario: View logs

- **WHEN** a user needs to check job progress
- **THEN** the skill provides: `runai workspace logs <name> -p talmo-lab --follow`

#### Scenario: Describe workspace

- **WHEN** a user needs detailed job status
- **THEN** the skill provides: `runai workspace describe <name> -p talmo-lab`

#### Scenario: Delete workspace

- **WHEN** a user needs to clean up a job
- **THEN** the skill provides: `runai workspace delete <name> -p talmo-lab`

### Requirement: GPU Resource Configuration

The runai-cluster-skill SHALL document correct resource request flags for RunAI CLI v2.

#### Scenario: GPU request syntax

- **WHEN** a user specifies GPU requirements
- **THEN** the skill uses v2 flags:
  - `--gpu-devices-request 1` (not deprecated `--gpu 1`)
  - `--gpu-portion-request 0.5` for fractional GPU

#### Scenario: CPU and memory syntax

- **WHEN** a user specifies CPU/memory requirements
- **THEN** the skill uses v2 flags:
  - `--cpu-core-request 12` (not deprecated `--cpu 12`)
  - `--cpu-memory-request 32G` (not deprecated `--memory 32G`)

#### Scenario: A40 optimization recommendations

- **WHEN** a user submits an IAMReX FP32 job
- **THEN** the skill recommends appropriate resources based on cell count and GPU memory (A40 has 46GB VRAM)

### Requirement: IAMReX Job Templates

The runai-cluster-skill SHALL provide pre-configured job templates for common IAMReX workloads.

#### Scenario: Single-GPU CFD job

- **WHEN** a user needs to run a single-GPU CFD simulation
- **THEN** the skill provides a template with:
  - FP32 Docker image
  - 1 A40 GPU
  - Data mounts for inputs/outputs
  - Appropriate CPU/memory for pre/post-processing

#### Scenario: Multi-GPU CFD job

- **WHEN** a user needs a multi-GPU simulation
- **THEN** the skill provides a template with:
  - `--gpu-devices-request 2` or more
  - Large shared memory (`--large-shm`)
  - MPI-aware entrypoint

#### Scenario: Interactive debugging workspace

- **WHEN** a user needs to debug inside the cluster
- **THEN** the skill provides a template with:
  - `--command -- sleep infinity`
  - Instructions for `runai workspace bash` or `runai exec`

### Requirement: Troubleshooting Guide

The runai-cluster-skill SHALL provide troubleshooting guidance for common issues.

#### Scenario: Job stuck in Pending

- **WHEN** a job is stuck in Pending status
- **THEN** the skill suggests checking cluster capacity and resource requests

#### Scenario: Mount failures

- **WHEN** a job fails with mount errors
- **THEN** the skill verifies host-path syntax and path existence on cluster nodes

#### Scenario: Image pull errors

- **WHEN** a job fails to pull the Docker image
- **THEN** the skill verifies image tag exists in ghcr.io and suggests `docker pull` test

#### Scenario: Token expired

- **WHEN** runai commands fail with authentication errors
- **THEN** the skill provides login command: `runai login remote-browser`

### Requirement: CLI v1 to v2 Migration Reference

The runai-cluster-skill SHALL document differences between deprecated v1 and current v2 CLI syntax.

#### Scenario: Command migration table

- **WHEN** a user has legacy v1 commands
- **THEN** the skill provides translations:
  - `runai submit` → `runai workspace submit`
  - `runai list jobs` → `runai workspace list`
  - `runai describe job` → `runai workspace describe`
  - `runai logs` → `runai workspace logs`
  - `runai delete job` → `runai workspace delete`

#### Scenario: Flag migration table

- **WHEN** a user has legacy v1 flags
- **THEN** the skill provides translations:
  - `--cpu 12` → `--cpu-core-request 12`
  - `--memory 32G` → `--cpu-memory-request 32G`
  - `--gpu 1` → `--gpu-devices-request 1`
  - `--host-path /src:/dst:ro` → `--host-path path=/src,mount=/dst,mount-propagation=HostToContainer`

