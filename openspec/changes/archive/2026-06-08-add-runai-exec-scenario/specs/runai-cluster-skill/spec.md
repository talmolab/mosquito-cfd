## MODIFIED Requirements

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

#### Scenario: Execute command in running workspace

- **WHEN** a user needs to run a command inside a running workspace
- **THEN** the skill uses: `runai workspace exec <name> -p talmo-lab -- <command>`
- **NOTE**: Do NOT use `kubectl exec` — RunAI manages its own auth layer
- **Examples**:
  - List files: `runai workspace exec <name> -p talmo-lab -- ls /workspace/`
  - Run simulation: `runai workspace exec <name> -p talmo-lab -- bash -c 'cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex /workspace/inputs.3d.validation > /workspace/sim.log 2>&1'`
  - Read a file: `runai workspace exec <name> -p talmo-lab -- bash -c 'cat /workspace/sim.log'`
  - Interactive shell: `runai workspace exec <name> -p talmo-lab --stdin --tty -- /bin/bash`
