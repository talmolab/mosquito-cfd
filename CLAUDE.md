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