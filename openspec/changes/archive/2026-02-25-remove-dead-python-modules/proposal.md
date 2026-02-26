# Remove Dead Python Modules

## Summary

Delete `generate_wing_markers.py` and `run_metadata.py` from `src/mosquito_cfd/`. Both have been superseded by better implementations and are no longer used.

## Motivation

These two modules were early scaffolding that have since been replaced:

### `generate_wing_markers.py`

- Generates a **rectangular flat-plate grid** of markers, but the actual `wing.vertex` file (908 markers) traces the real Aedes aegypti planform shape from van Veen et al. (2022).
- The `geometry/` package (`parametric_planform.py`, `vertex_io.py`, `cli.py`) already provides the correct wing planform generation via the `generate-wing-planform` CLI entry point.
- Default center `(0.025, 0.025, 0.025)` in meters is wrong for the non-dimensional simulation setup (origin-centered vertex files, translated by IAMReX at runtime).
- Cannot reproduce the committed `wing.vertex` — running it produces a different file.

### `run_metadata.py`

- Superseded by `benchmarks/metadata.py` which provides `capture_run_metadata()` with:
  - Docker image tracking
  - Better git info (branch, dirty status, diff hash, remote URL)
  - Output file listing (plot files, checkpoints)
  - Extensible `extra` dict for arbitrary metadata
- The old module reads `PRECISION`, `CUDA_ARCH`, `USE_MPI` as bare env vars but misses the pinned commit SHAs from `build-args.env` that actually matter for reproducibility.
- Still registered as the `run-metadata` CLI entry point and listed in `docker/entrypoint.sh`, giving the false impression it is the current metadata tool.

## Scope

### Delete

1. `src/mosquito_cfd/generate_wing_markers.py`
2. `src/mosquito_cfd/run_metadata.py`

### Update

3. `pyproject.toml` — remove `run-metadata` and `generate-markers` script entry points
4. `docker/entrypoint.sh` — remove `run-metadata` from help text
5. `openspec/project.md` — update directory structure, "Current State", and CLI sections to reflect the actual tools (`generate-wing-planform`, `benchmarks.metadata`)

## Non-Goals

- No changes to `benchmarks/metadata.py` or `geometry/` — they are already correct.
- No new CLI entry point for benchmarks metadata (it's used as a library, not a standalone CLI).

## Risks

- **Low**: Both modules are dead code with no importers. The `generate-markers` CLI is not called by any script or CI job. The `run-metadata` CLI is listed in entrypoint help text but not invoked by any automation.