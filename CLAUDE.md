<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Command Conventions

### Python Code (this repo)
Use `uv` for all Python operations:
```bash
uv run python script.py
uv run pytest
uv run ruff check .
```

### RunAI Cluster Operations
Use WSL with the documented pattern:
```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && /home/elizabeth/.runai/bin/runai <command>"
```

### Path Mappings
| Context | Path |
|---------|------|
| Windows | `Z:\users\eberrigan\...` |
| WSL | `/mnt/hpi_dev/users/eberrigan/...` |
| Cluster | `/hpi/hpi_dev/users/eberrigan/...` |

Cluster data mounted on Windows via `Z:` drive is accessible for local Python analysis.

### Local Docker GPU Runs (A5000, skip RunAI queue)

The dev box has an **RTX A5000 (24 GB, sm_86)** with Docker Desktop GPU passthrough.
Use this to run validation/convergence sims without waiting for cluster quota.

**Pattern** (PowerShell — never git-bash, MSYS mangles `/opt/...` paths):
```powershell
docker run --rm --gpus all `
  -v "c:/repos/mosquito-cfd/examples/flapping_wing:/workspace" `
  ghcr.io/talmolab/mosquito-cfd:fp64 `
  bash /workspace/<run_script>.sh 2>&1 | tee examples/flapping_wing/sim-<label>.log
```

**A5000 arena cap**: always pass `amrex.the_arena_init_size=18` (GiB).
AMReX defaults to ¾ × VRAM = 18 GiB on a 24 GB card, but set it explicitly to
prevent the default from changing under a newer AMReX version. A40 (40 GB) uses 28.

**CFL at fine 256³ grid**: the deck `inputs.3d.convergence_fine` sets `ns.fixed_dt=0.0005`
(CFL ≈ 0.45 → unstable). Use `ns.fixed_dt=0.00025` + `max_step=4000` for a stable 1-wingbeat
run. See `examples/flapping_wing/t3c_run_local.sh` for the complete override set.

**Image staleness**: the local fp64 image must be at IAMReX commit `f93dc794` (T2a 3D d_nn fix).
Verify: `docker run --rm ghcr.io/talmolab/mosquito-cfd:fp64 git -C /opt/cfd/IAMReX log --oneline -1`
should show that hash. If it's behind, either pull the latest CI image or rebuild:
```powershell
docker build -f docker/Dockerfile.fp64 -t ghcr.io/talmolab/mosquito-cfd:fp64 .
```