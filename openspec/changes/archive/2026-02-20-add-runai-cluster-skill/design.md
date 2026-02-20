## Design: RunAI Cluster Skill

### Architecture Overview

```
User Request (Windows)
        │
        ▼
┌───────────────────┐
│  Claude Skill     │
│  .claude/skills/  │
│  runai/           │
└────────┬──────────┘
         │ generates command
         ▼
┌───────────────────┐
│  WSL Execution    │
│  wsl -e bash -c   │
└────────┬──────────┘
         │ KUBECONFIG export
         ▼
┌───────────────────┐
│  RunAI CLI v2     │
│  ~/.runai/bin/    │
└────────┬──────────┘
         │ API calls
         ▼
┌───────────────────┐
│  Salk RunAI       │
│  Cluster (A40s)   │
└───────────────────┘
```

### Key Design Decisions

#### 1. WSL as Execution Environment

**Decision**: All runai commands execute via WSL, not Windows PowerShell/CMD.

**Rationale**:
- RunAI CLI is installed in WSL at `/home/elizabeth/.runai/bin/runai`
- KUBECONFIG and kubectl work natively in Linux environment
- Avoids Windows path mangling issues (MSYS_NO_PATHCONV not needed)
- Consistent with GAPIT3 pipeline patterns

**Trade-offs**:
- Requires WSL to be installed and configured
- Slightly longer command strings
- fstab mount warnings (harmless)

#### 2. Explicit KUBECONFIG Pattern

**Decision**: Every command includes `export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml`.

**Rationale**:
- Ensures correct cluster/project context
- Avoids confusion with other kubectl configs
- Matches verified working pattern from investigations

**Alternative considered**: Setting KUBECONFIG in WSL shell profile
- Rejected: Less explicit, harder to debug, may conflict with other clusters

#### 3. Skills Directory Structure

**Decision**: Place skill in `.claude/skills/runai/` with multiple files.

```
.claude/
└── skills/
    └── runai/
        ├── skill.md           # Primary reference (always loaded)
        ├── examples.md        # Real-world command examples
        └── troubleshooting.md # Error resolution
```

**Rationale**:
- Follows GAPIT3 pattern of modular skill organization
- Keeps primary skill.md focused and scannable
- Separates reference material from examples

#### 4. Project-Specific Defaults

**Decision**: Hardcode `talmo-lab` as the default project.

**Rationale**:
- This skill is for mosquito-cfd, which uses talmo-lab
- Reduces cognitive load and error potential
- Can be parameterized later if needed

#### 5. Path Mapping Strategy

**Decision**: Document all three path contexts explicitly.

| Context | Base Path | Use Case |
|---------|-----------|----------|
| Windows | `Z:\users\eberrigan\` | File browser, IDE |
| WSL | `/mnt/hpi_dev/users/eberrigan/` | Local scripts |
| Cluster | `/hpi/hpi_dev/users/eberrigan/` | --host-path mounts |

**Rationale**:
- Users work in Windows but submit to Linux cluster
- Drive letter may vary (user-specific mapping)
- Explicit documentation prevents path errors

### Integration Points

#### With cfd-infrastructure

The runai-cluster-skill uses Docker images defined by `cfd-infrastructure`:
- `ghcr.io/talmolab/mosquito-cfd:fp32` for A40 prototyping
- `ghcr.io/talmolab/mosquito-cfd:fp64` for validation

Job templates reference these images and assume their contents (IAMReX binary location, Python utilities).

#### With Future HPC Systems

The skill is specific to RunAI/Kubernetes patterns. For future ALCF Aurora or OLCF Frontier deployments:
- Different job submission systems (PBS, SLURM)
- Different authentication mechanisms
- Separate skills would be needed

### Security Considerations

1. **No credentials in skill files**: KUBECONFIG path references existing file, doesn't contain secrets
2. **No hardcoded tokens**: Authentication via `runai login remote-browser` (browser OAuth)
3. **Read-only by default**: Host-path mounts default to read-only unless `readwrite` specified

### Performance Notes

- WSL startup adds ~1-2s latency to commands
- Long-running jobs (CFD simulations) dwarf this overhead
- For rapid iteration, consider keeping a WSL terminal open