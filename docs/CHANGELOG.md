# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Cluster-free wing-phase hinge-geometry diagnostic (`scripts/make_wing_phase_diagnostic.py`, `src/mosquito_cfd/force_surrogate/wing_phase_diagnostic.py`) — plots the wing marker cloud at four phases of a wingbeat with the hinge marked, sharing its metrics with the `test_sweep_hinge_geometry.py` regression guard; `examples/prelim_sweep/figures/README.md` documents both figure families (#71)
- `src/mosquito_cfd/visualization/wing_render.py` (shared wing marker/outline transform helpers, built on the canonical `benchmarks.wing_kinematics` rotation code) and `src/mosquito_cfd/force_surrogate/comparison_figure.py` (`build_coarse_vs_fine_comparison`, `build_config_mean_collapse_diagnostic`); new optional `viz` dependency group (`scipy`, `scikit-image`, `imageio-ffmpeg`), installed in CI (#73)
- `src/mosquito_cfd/visualization/flow_video.py` (generalized CFD-field video builder: `wake-slice` | `combined-3d` | `lev-3d` | `zvelocity-3d`) and `kinematics_video.py` (cluster-free kinematics preview); four thin CLI drivers under `scripts/` — `make_flow_video.py`, `make_kinematics_video.py`, `make_comparison_figure.py`, `make_config_mean_collapse_diagnostic.py` (#74)
- Committed synthetic-fixture-derived reference figures `tests/fixtures/comparison_figure/coarse_vs_fine_comparison.png` and `diagnostic_config_mean_collapse.png` (with a `README.md` disclosing they are rendered unit-test fixtures, not real corpus data or curated documentation, plus regeneration inputs/commands); `openspec/project.md` "Visualization Tooling" section and a Dependencies-list fix noting the `train`/`viz` optional groups (#75)
- Full 27-config fine-256³ force-surrogate corpus scaffolding: `generate_full_corpus.py` (thin driver over the unmodified `generate_sweep()`, default 27-config Aedes grid, `n_holdout=6`) plus the generated `examples/prelim_sweep_fine/` decks + manifest, committed cluster-free (no live cluster run in this PR) (#61)
- `submit_workflow.sh full --parallelism N`: overrides the fan-out sweep's concurrency via an anchored, self-verifying `sed` patch to a temp copy — never edits the committed `force-surrogate-sweep.yaml`; omitting the flag is a true no-op (#61)
- T3c fine-grid (256×128×256) convergence run: `forces_fine.csv` (4000 steps, 1 wingbeat, RTX A5000) and `run_metadata_t3c.json` with deck hash pin, image digest, timing, and `dt_reduced=true` flag (#52)
- 3-grid Richardson analysis: CF_normal monotone (p_obs=1.38, Richardson=2.162, GCI_fine=3.7%); CF_chord monotone (p_obs=1.37, Richardson=0.321, GCI_fine=27.6%) — documented in `examples/flapping_wing/RESULTS.md` (#52)
- Reproducibility guard test `test_3grid_convergence_recomputes_from_committed_csvs` with tight `abs=1e-4` tolerances pinned to committed CSV values (#52)
- Local Docker GPU run documentation (RTX A5000, arena cap, CFL fallback pattern) in `openspec/project.md` (#52)
- Python (uv) and cluster path mapping conventions consolidated in `openspec/project.md` (#52)
- 3-grid convergence tooling (`assert_gradeable_pair`, `assert_gradeable_triple`, `wing_grid_convergence_from_body_forces`) and fine-grid deck `inputs.3d.convergence_fine` (#52)
- T3c local run script `t3c_run_local.sh` for reproducible A5000 re-runs with D6 dt/step overrides (#52)

### Changed
- `CLAUDE.md` stripped to OpenSpec managed block only — all operational docs (Python/uv commands, RunAI pattern, cluster path mappings) moved to `openspec/project.md` (#52)
- `benchmarks/METHODS.md` fine-grid column corrected: dt=2.5×10⁻⁴ (D6 fallback), 4000 steps; prose updated to document temporal confound in Richardson analysis (#52)
- `docs/aerodynamics_validation/roadmap.md`: T3c flipped ⬜ → ✅ with results summary (#52)
- T4 per-component force-decomposition (`make_force_decomposition_figure.py`, `fig_force_decomposition`) now compares the van Veen quasi-steady model against the fine 256³ grid (`forces_fine.csv`, T3c) instead of the coarse 64³ grid: CF_normal 2.23 vs model 2.48 (rel gap ~11%, still within the 16% tolerance); CF_chord 0.41 vs model 0.43 (close agreement, down from the coarse-grid 0.92). `decompose_wing_force` is no longer called with `medium_csv` here — pairing the finest grid as the 2-grid GCI function's "coarse" role inverted the convergence-direction semantics; RESULTS.md's T4 section and Validation Status row now cite the T3c 3-grid Richardson/GCI numbers instead

### Fixed
- `get_git_info()` (`src/mosquito_cfd/benchmarks/metadata.py`) now resolves Windows-created git worktrees read via WSL — previously it silently dropped git provenance (`git.commit`, `git.branch`, `git.dirty`, etc.), reporting the same "not a git repository" error used for a genuinely missing repo. Adds a reactive retry: on the first failure, if `.git` is a worktree pointer file naming a Windows drive-letter gitdir (e.g. `C:/...`), translate it to its WSL mount equivalent (`/mnt/c/...`) and retry once with `GIT_DIR`/`GIT_WORK_TREE` set; the non-worktree path is unchanged (#77)
- Wing-hinge geometry defect in `examples/prelim_sweep/`'s and `examples/prelim_sweep_fine_pilot/`'s base decks: `particle_inputs.hinge_y`/`hinge_z` collapsed the wing's root hinge to a midspan pivot plus a spurious offset, a regression from the 2026-07-02 axis-convention refactor; corrected to the true root hinge, matching `examples/flapping_wing/inputs.3d.validation`. Regenerated `examples/prelim_sweep/`'s decks + `dataset.parquet`/`surrogate/*`/`figures/*` end-to-end and `examples/prelim_sweep_fine/`'s decks (CFD re-run deferred) (#71)
- `evidence_figure.py::build_caption`'s negative-config-resolved-R² "tell" hardcoded that `CF_y` is always the off-panel axis showing it and that `CF_mx`/`CF_mz` always carry no between-config signal — both became false once the corrected-geometry corpus flipped the ranking (on-panel `CF_x` negative instead, `CF_mx` now the strongest moment). Now computed from `metrics.json` at call time across all six targets, naming the worst (most negative) offender rather than the first found (#71)
- A stale/incorrect `wing.vertex` on the coarse corpus's cluster NFS share, running the pre-T2a axis convention (issue #62); automated NFS provisioning added to `submit_workflow.sh` going forward (#71)
- `.gitattributes`' `inputs.3d.*` LF-normalization pattern broadened to `*inputs.3d.*` so it also covers `base_inputs.3d.*` files — a Windows checkout was silently baking a platform-dependent sha256 into committed `sweep_provenance.json` files (#61)
- `inputs.3d.convergence_fine` reproducibility banner added — warns that re-running the deck as committed will not reproduce `forces_fine.csv` (D6 runtime override required) (#52)
- `test_wing_convergence_fine.py`: strengthened `image_digest` assertion to verify `sha256:` prefix (was vacuous key-presence check); added `cf_normal.monotone=True` and `cf_chord.monotone=True` structural assertions (#52)
- `test_t4_decomposition_numbers_reproduce` and `test_fig_force_decomposition_regenerates` updated to assert against the fine-grid numbers, replacing the stale coarse-grid pins
