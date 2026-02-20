## Why

The mosquito-cfd project requires GPU-accelerated CFD simulations on the Salk RunAI cluster (A40 GPUs). Currently:
1. RunAI commands must be manually constructed with complex flag syntax
2. Path mappings between Windows, WSL, and cluster are error-prone
3. No integrated Claude assistance for job submission, monitoring, or troubleshooting

A Claude skill for RunAI cluster access will enable streamlined GPU job workflows directly from the development environment, reducing friction for CFD prototyping and validation runs.

## What Changes

### New Capability: `runai-cluster-skill`

A Claude skill providing RunAI CLI v2 assistance for the Salk GPU cluster:

- **WSL Command Pattern**: All runai commands executed via WSL with KUBECONFIG export
- **Path Mapping Reference**: Windows ↔ WSL ↔ Cluster path translations
- **Workspace Management**: Submit, monitor, describe, logs, delete operations
- **GPU Job Templates**: Pre-configured patterns for IAMReX CFD workloads
- **Troubleshooting Guides**: Common error resolution and cluster diagnostics

### Key Design Principles

1. **WSL-native execution**: RunAI CLI runs in WSL, not Windows PowerShell
2. **KUBECONFIG pattern**: Explicit kubeconfig path for talmo-lab project
3. **Path safety**: MSYS_NO_PATHCONV or WSL paths to prevent Git Bash path mangling
4. **Project-specific defaults**: talmo-lab project, host-path mounts to /hpi/hpi_dev

### Skill Components

| Component | Purpose |
|-----------|---------|
| `.claude/skills/runai/skill.md` | Primary skill documentation with command reference |
| `.claude/skills/runai/examples.md` | Real-world IAMReX job examples |
| `.claude/skills/runai/troubleshooting.md` | Error resolution guide |

## Impact

- New spec: `runai-cluster-skill` (skill structure, command patterns)
- New files: `.claude/skills/runai/` directory with skill documentation
- Related: `cfd-infrastructure` (Docker images used in RunAI jobs)
- Reference: GAPIT3 pipeline RunAI patterns, vaults investigation `2026-02-04-runai-wsl-iamrex`