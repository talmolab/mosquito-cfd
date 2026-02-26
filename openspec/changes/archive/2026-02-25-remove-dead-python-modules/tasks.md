# Tasks

## Remove dead modules

1. [x] Delete `src/mosquito_cfd/generate_wing_markers.py`
2. [x] Delete `src/mosquito_cfd/run_metadata.py`
3. [x] Remove `run-metadata` and `generate-markers` entry points from `pyproject.toml`
4. [x] Remove `run-metadata` reference from `docker/entrypoint.sh`
5. [x] Run `uv sync` to update the lock file after entry point removal

## Update documentation

6. [x] Update `openspec/project.md` directory structure to show `geometry/` and `benchmarks/` instead of the two deleted files
7. [x] Update `openspec/project.md` "Current State" checklist (marker generation and metadata capture are done via the new modules)
8. [x] Update `openspec/project.md` CLI section to reference `generate-wing-planform` and remove `run-metadata` / `generate-markers` examples

## Validate

9. [x] `uv run ruff check .` — 16 pre-existing errors, none from this change
10. [x] `uv run pytest` — 10/10 passed
11. [x] No remaining imports of the deleted modules in `src/`