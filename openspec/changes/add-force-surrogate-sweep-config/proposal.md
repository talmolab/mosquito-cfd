## Why

The Track B force-surrogate program ([docs/force_surrogate/roadmap.md](../../../docs/force_surrogate/roadmap.md), row #2) needs a **reproducible corpus of CFD input configurations** before any cluster run (PR3), dataset build (PR4), or training (PR5). Today the repo has exactly one validated flapping-wing input file (`examples/flapping_wing/inputs.3d.validation`) at a single, non-mosquito kinematic point (φ=70°, the generic large-amplitude demo). There is:

- **No sweep generator** — no way to produce the biologically-anchored kinematic grid the surrogate must learn over.
- **No resolution of CC-7** (the open Reynolds-handling decision the roadmap explicitly defers to PR2): changing stroke amplitude / frequency changes U_tip and therefore Re unless ν\* is rescaled per config.
- **No committed, traceable record** of which kinematic configurations the corpus covers, nor a reproducible train/held-out split (CC-4 requires held-out **configs**, not timesteps).

PR2 delivers a tested, cluster-free sweep generator that re-anchors on *Aedes aegypti* kinematics (Bomphrey 2017), resolves CC-7, and emits the committed 27-config corpus + manifest that PR3 runs and PR4/PR6 consume — all built on PR1's published `force-surrogate` foundation.

## What Changes

### Extends capability: `force-surrogate`

- **New module `src/mosquito_cfd/force_surrogate/sweep.py`** (pure, no cluster/GPU/plotfiles):
  - `build_kinematic_grid(...) -> list[dict]` — the Aedes-anchored 3×3×3 grid (stroke φ∈{35,45,55}°, dimensionless frequency f\*∈{0.85,1.0,1.15}, pitch α∈{30,45,60}°) = **27 configs**, each carrying the documented schema `{stroke_amp_deg, frequency_fstar, pitch_amp_deg}` — the **same keys as `tests/fixtures/micro_sweep.json`** so that fixture is the cluster-free test input (CC-2). Levels live in named constants, sourced to Bomphrey 2017.
  - `compute_reynolds(stroke_amp_deg, frequency_fstar, nu_star, r_mid=R_MID) -> float` — `Re = 2π·f*·radians(φ)·r_mid / ν*`, using the **midspan arm `r_mid=1.5`** (the viscous-scaling arm), explicitly **not** `R_TIP=3.0` (the force-normalization arm). Reproduces Re≈100 at the validated φ=70°, f\*=1.0, ν\*=0.115 point.
  - `derive_run_duration(frequency_fstar, n_wingbeats, dt) -> (max_step, stop_time)` — `stop_time = n_wingbeats / f*`, `max_step = round(stop_time / dt)`, `dt` fixed at the validated `5e-4`.
  - `select_holdout(configs, n_holdout, seed) -> list[int]` — deterministic (`numpy.random.default_rng(seed)`) selection of **6** held-out configs drawn only from grid **non-corners** (a corner = all three params at an extreme level; 8 corners ⇒ 19 eligible), so the eventual evidence figure measures **interpolation**, not extrapolation.
  - `render_inputs(base_text, *, stroke_amp_deg, frequency_fstar, pitch_amp_deg, max_step, stop_time, plot_int) -> str` — **exact-key** rewrite of the IAMReX inputs that changes **only** the swept/derived keys and preserves every comment, blank line, ordering, and unrelated key byte-for-byte (full-key match, so the prefix-sibling `kinematics_deviation_amp` is untouched). `amr.plot_int` is forced to **-1** (force-only, CC-6 — no field plotfiles, sidesteps the velocity-field-in-plotfiles bug). Output is **LF-only** with deterministic float formatting so the committed corpus is byte-reproducible on Windows (dev) and Linux (CI) — see `design.md` D6.
  - `generate_sweep(...)` — orchestrator: writes the 27 input files + `sweep_manifest.json` + `sweep_manifest.units.json`, returns the manifest dict.
- **`constants.py`:** add `R_MID = 1.5` (the midspan viscous-scaling arm, with a unit comment cross-referencing the existing `R_TIP=3.0`-vs-`r_mid` note) and the Aedes sweep-grid level constants + `VALIDATED_NU_STAR = 0.115`, `DT = 5e-4`.
- **Thin driver `examples/prelim_sweep/generate_sweep.py`** — calls the library to (re)generate the committed artifacts under `examples/prelim_sweep/`; all logic lives in the tested module.
- **Committed artifacts** under `examples/prelim_sweep/`: `inputs/inputs.3d.s{φ}_f{f*×100}_p{α}` (27 files), `sweep_manifest.json` (deterministic config description), `sweep_manifest.units.json`, `sweep_provenance.json` (git/timestamp/base-hash — kept separate so the manifest stays byte-reproducible; see `design.md` D5), and a `README.md`. A test asserts the inputs + manifest + units are **byte-identical to a fresh regeneration** with the recorded seed (CC-1).

### CC-7 resolved: hold ν\* fixed (Re varies)

All 27 configs keep the validated `ns.vel_visc_coef = 0.115`; **Re ≈ 43–90 varies as a deterministic function of the swept φ, f\***. Rationale (see `design.md` D1): Re is then a single-valued function of the input kinematics (no hidden confounder — the φ,f\*,α→force map stays well-posed); it is biologically faithful (Re co-varies with kinematics in real flight); every input file differs **only** in the swept/derived keys (cleanest provenance and "differs-only" test); and all configs stay on the one validated viscosity rather than 26 unvalidated rescaled values. Per-config Re is recorded in the manifest.

### Provenance (separate sidecar, no docker digest in PR2)

A separate `sweep_provenance.json` records generation provenance — git commit (`get_git_info()["commit"]`), base-inputs **SHA256** (`hash_file`), and a **caller-supplied timestamp** — but **no Docker image digest**: PR2 invokes no container. It is a *separate* file (not embedded in the manifest) because `git_commit` is non-reproducible across checkouts and would otherwise defeat the manifest byte-identity guarantee (see `design.md` D5). The per-run `run_metadata.json` with the pinned container digest (via PR1's `capture_surrogate_run_metadata`) is emitted by PR3, the stage that actually runs the image. The units sidecar reuses PR1's `write_units_sidecar` (vocabulary already covers `deg` / `dimensionless` / `dimensionless (f*)`).

## Impact

- **Spec:** `force-surrogate` capability gains 6 requirements (grid, Reynolds policy, run duration, force-only inputs, held-out split, reproducible manifest+units).
- **New code:** `src/mosquito_cfd/force_surrogate/sweep.py`, `tests/test_force_surrogate_sweep.py`; `constants.py` gains `R_MID` + grid/`DT`/`VALIDATED_NU_STAR` constants and `__init__.py` re-exports the new public API.
- **New artifacts:** `examples/prelim_sweep/` (driver + 27 inputs + manifest + units sidecar + README).
- **`.gitattributes`:** add `examples/**/inputs.3d.* text eol=lf` so the extension-less committed decks are stored LF (byte-reproducibility, D6).
- **CI (`.github/workflows/ci.yml`):** widen the lint job from `src/` to `src/ tests/ examples/prelim_sweep/` so the new driver + test file are CI-lint-enforced (today CI lints `src/` only). **Scoped deliberately:** the rest of `examples/` carries 32 pre-existing ruff violations + 7 unformatted files in unrelated scripts (3 under `flapping_wing/`, 2 under `flow_past_sphere/`, 2 under `heaving_ellipsoid/`); linting all of `examples/` would red CI on out-of-scope debt, so a full `examples/` lint widening + cleanup is a tracked follow-up (task 7.2). `tests/` is already clean. ruff only inspects `.py`, so the 27 input decks and JSON sidecars are ignored. See `design.md` D9.
- **Reuses (no change):** `force_surrogate.sidecar.write_units_sidecar`/`read_units_sidecar`, `benchmarks.metadata.hash_file`/`get_git_info`, and the committed `tests/fixtures/micro_sweep.json` (CC-2).
- **Roadmap:** records the **CC-7 resolution** in `docs/force_surrogate/roadmap.md` (the open "(decide in PR2)" decision text). The row-#2 **status checkbox** flips on merge via `cleanup-merged` (not in this PR).
- **No** CFD-solver, Docker, or CI changes. Force-only; **out of scope** (CC-6): cluster/RunAI runs (PR3), plotfile/velocity-field reading, the forces→parquet extractor (PR4), training (PR5), the evidence figure (PR6), RL, and any docker digest in PR2 metadata.
