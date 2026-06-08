## Why

The Track B force-surrogate program ([docs/force_surrogate/roadmap.md](../../../docs/force_surrogate/roadmap.md), row #1) needs a tested, reproducible foundation before any sweep/dataset/training work. Today:

- The force-coefficient normalization math (`F_ref = q_tip · S`) lives **inline** in `examples/flapping_wing/generate_all_figures.py` — not importable, not unit-tested, and at risk of silent divergence if re-derived in the extractor (PR4) and figure (PR6).
- There is **no committed fixture** that lets force-related tests run without the RunAI cluster or AMReX plotfiles, so downstream PRs would each need live infrastructure to test.
- There is no units/provenance convention for the surrogate data.

PR1 establishes a single source of truth for the normalization math, a dimensionless units-sidecar convention, a reproducible provenance wrapper, module constants, and cluster-free fixtures — so PR2–PR6 build on tested primitives.

## What Changes

### New capability: `force-surrogate`

- **New subpackage `src/mosquito_cfd/force_surrogate/`:**
  - **Normalization math** (`normalization.py`): `compute_force_reference(f_star, phi_amp_deg, r_tip, span, chord, rho=1.0)` → `U_tip_max, q_tip, S, F_ref`; `compute_force_coefficients(Fx, Fy, Fz, F_ref)` → `CF_x, CF_y, CF_z`. Pure, parameterized, no I/O. **The single source of `F_ref`** (CC-3), regression-locked to the documented validated values.
  - **Constants** (`constants.py`): validated baseline geometry/physical values (`SPAN=3.0`, `CHORD=1.0`, `R_TIP=3.0`, `RHO=1.0`) and the validated reference point (φ=70°, pitch=45°, f\*=1.0), each with a unit comment. (Sweep-grid levels are deferred to PR2.)
  - **Sidecar + provenance** (`sidecar.py`): **reuse** `mosquito_cfd.benchmarks.metadata.capture_run_metadata` (import in place; no change to that module) via a thin wrapper that ensures the **docker image digest** is recorded (CC-1); plus new `write_units_sidecar` / `read_units_sidecar` emitting/parsing a `units.json` against a documented **dimensionless units vocabulary** (CC-5).
  - `__init__.py` re-exports + `__all__`.
- **Committed cluster-free test fixtures** under `tests/fixtures/` (CC-2): a tiny synthetic IB-particle force CSV with analytically known forces (columns `iStep,time,Fx,Fy,Fz,Mx,My,Mz,X,Y,Z`) + a 2-config micro-sweep descriptor — so every downstream PR's force tests run with **no RunAI / GPU / plotfiles**.

### Units convention (dimensionless)

The validated flapping-wing pipeline is **dimensionless** (domain 0–8, f\*=1.0, IAMReX dimensionless forces) — it has no physical scaling yet. `project.md` does **not** state a units convention, so this change establishes one for surrogate data. The `units.json` vocabulary is dimensionless: `CF_x/CF_y/CF_z → "dimensionless"`, raw `Fx/Fy/Fz → "dimensionless"` (IAMReX), `stroke_amp/pitch_amp → "deg"`, `frequency → "dimensionless (f*)"`, `time → "dimensionless"`. A physical SI mapping, if ever needed, is a downstream concern (see `design.md` D3).

## Impact

- **New spec:** `force-surrogate` (normalization, dimensionless units sidecar, run provenance).
- **New code:** `src/mosquito_cfd/force_surrogate/`, `tests/test_force_surrogate_*`, `tests/fixtures/`.
- **Refactored (delivers CC-3):** `examples/flapping_wing/generate_all_figures.py` — its inline `F_ref` block now imports `compute_force_reference`, so the new module is the *only* place `F_ref` is computed (no silent-divergence window).
- **Reuses + 1-line cross-platform fix:** `src/mosquito_cfd/benchmarks/metadata.py` — `capture_run_metadata`/`get_git_info` reused as-is, plus `encoding="utf-8", errors="replace"` added to its `subprocess.run` calls (a pre-existing Windows cp1252 decode bug the reuse surfaced; see design.md "Why benchmarks/metadata.py changed").
- **Roadmap:** delivers `docs/force_surrogate/roadmap.md` row #1.
- **No** CFD-solver, Docker, or CI changes. Force-only; out of scope: cluster runs, plotfile/velocity-field reading, the forces→parquet extractor (PR4), training (PR5), figure (PR6), RL.
