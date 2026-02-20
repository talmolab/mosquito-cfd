## Tasks

### Phase 1: Skill Documentation

- [ ] 1.1 Create `.claude/skills/runai/` directory structure
- [ ] 1.2 Write `skill.md` with WSL command pattern and path mappings
- [ ] 1.3 Document RunAI CLI v2 command reference (workspace submit/list/describe/logs/delete)
- [ ] 1.4 Document resource request flags (gpu-devices-request, cpu-core-request, cpu-memory-request)
- [ ] 1.5 Add v1 to v2 migration table for legacy command translation

### Phase 2: IAMReX Job Templates

- [ ] 2.1 Create single-GPU FP32 CFD job template
- [ ] 2.2 Create single-GPU FP64 validation job template
- [ ] 2.3 Create multi-GPU scaling test template
- [ ] 2.4 Create interactive debugging workspace template
- [ ] 2.5 Document host-path mount patterns for `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/`

### Phase 3: Examples and Troubleshooting

- [ ] 3.1 Write `examples.md` with real-world command sequences
  - List workspaces
  - Submit test job
  - Monitor progress
  - View logs
  - Clean up
- [ ] 3.2 Write `troubleshooting.md` covering:
  - Token expired errors
  - Job stuck in Pending
  - Mount failures
  - Image pull errors
  - Out of memory

### Phase 4: Validation

- [ ] 4.1 Test WSL command pattern with `runai version`
- [ ] 4.2 Test workspace list command
- [ ] 4.3 Submit test GPU job using FP32 image
- [ ] 4.4 Verify logs and describe commands work
- [ ] 4.5 Clean up test workspace
- [ ] 4.6 Document any environment-specific adjustments needed

### Phase 5: Integration

- [ ] 5.1 Add skill reference to CLAUDE.md
- [ ] 5.2 Update cfd-infrastructure tasks.md to reference runai skill for cluster testing
- [ ] 5.3 Archive this change proposal after implementation