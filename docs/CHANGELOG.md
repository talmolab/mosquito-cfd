# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- T3c fine-grid (256×128×256) convergence run: `forces_fine.csv` (4000 steps, 1 wingbeat, RTX A5000) and `run_metadata_t3c.json` with deck hash pin, image digest, timing, and `dt_reduced=true` flag (#52)
- 3-grid Richardson analysis: CF_normal monotone (p_obs=1.38, Richardson=2.16, GCI_fine=3.7%); CF_chord non-monotone — documented in `examples/flapping_wing/RESULTS.md` (#52)
- Reproducibility guard test `test_3grid_convergence_recomputes_from_committed_csvs` with tight `abs=1e-4` tolerances pinned to committed CSV values (#52)
- Local Docker GPU run documentation (RTX A5000, arena cap, CFL fallback pattern) in `openspec/project.md` (#52)
- Python (uv) and cluster path mapping conventions consolidated in `openspec/project.md` (#52)
- 3-grid convergence tooling (`assert_gradeable_pair`, `assert_gradeable_triple`, `wing_grid_convergence_from_body_forces`) and fine-grid deck `inputs.3d.convergence_fine` (#52)
- T3c local run script `t3c_run_local.sh` for reproducible A5000 re-runs with D6 dt/step overrides (#52)

### Changed
- `CLAUDE.md` stripped to OpenSpec managed block only — all operational docs (Python/uv commands, RunAI pattern, cluster path mappings) moved to `openspec/project.md` (#52)
- `benchmarks/METHODS.md` fine-grid column corrected: dt=2.5×10⁻⁴ (D6 fallback), 4000 steps; prose updated to document temporal confound in Richardson analysis (#52)
- `docs/aerodynamics_validation/roadmap.md`: T3c flipped ⬜ → ✅ with results summary (#52)

### Fixed
- `inputs.3d.convergence_fine` reproducibility banner added — warns that re-running the deck as committed will not reproduce `forces_fine.csv` (D6 runtime override required) (#52)
- `test_wing_convergence_fine.py`: fixed vacuous `image_digest` assertion; added `cf_normal.monotone=True` and `cf_chord.monotone=False` structural assertions (#52)
