# Add wing grid-convergence tooling + medium-grid deck (T3a, cluster-free)

## Why

Tier T2a delivered the body-frame van Veen comparison on the **coarse** 64×32×64 run: `CF_normal` 2.61
(PASS) but `CF_chord` 0.92 (PARTIAL, ~3× van Veen's ~0.3, tracked in
[#40](https://github.com/talmolab/mosquito-cfd/issues/40)). One live hypothesis for the chord excess is
**coarse-grid diffused-IB error** (Δx = 0.125 under-resolves the tangential boundary layer). The roadmap's
**Tier T3** tests this by re-running the wing on a **medium** 128×64×128 grid and quantifying how much the
body-frame coefficients move under refinement — the CFD-fidelity gate that also unblocks T4 (#40 reuses the
T3 runs).

T3 needs a **new medium-grid simulation** on the A40 — an hours-long, **operator-run** cluster job that
cannot be executed here. So, exactly as **T2 split into T2a (solver/run) + T2b (grade)**, **T3 splits into
T3a (this change) + T3b (the graded run)**:

- **T3a (this change, cluster-free, mergeable now):** re-author the medium deck, build + TDD the wing
  grid-convergence grader and the LEV vorticity/Q-criterion diagnostic against the committed coarse run and
  synthetic fixtures, and file the T3 tracking issue — so the tooling and deck are **reviewed and validated
  before** spending hours of A40 time.
- **T3b (separate follow-up, after the operator run):** commit `forces_medium.csv` + run metadata, apply
  the grader + LEV to the real medium data, and write the RESULTS convergence section.

The existing `inputs.3d.production` (128³) is **not** a grid-refinement of the coarse run — it is a
**different operating point** (f\* = 0.1, ν\* = 0.01, 3 wingbeats), so it must not be reused; the medium
deck is re-authored to change **only the grid**.

## What Changes

- **New medium-grid deck** `examples/flapping_wing/inputs.3d.convergence_medium`: identical to the
  canonical coarse deck `inputs.3d.validation` (van Veen convention, BCs `2 0 2`, domain 8×4×8, f\* = 1.0,
  φ = 70°, α = 45°, ν\* = 0.115, `wing.vertex`, `init_iter = 2`, **`fixed_dt = 5e-4` held fixed**,
  `amr.max_grid_size = 32` held) except **`amr.n_cell`** (128 64 128 vs 64 32 64). Holding dt fixed makes the
  temporal error identical in both runs, so the coarse↔medium difference is **isolated from temporal error**.
  It is **not** purely a spatial *discretization* convergence, though: the diffused-IB regularization is
  grid-tied (`dv = h·d_nn²` and the kernel support scale with `h`), so refining the grid **also sharpens the
  IB model** — the difference reflects **combined spatial + IB-regularization refinement** (a further reason
  the study is report-only; see design D4). Guarded by a **deck-invariance test** that asserts the two decks
  differ **only** in `amr.n_cell` (and that `fixed_dt`, `particle_inputs.radius` are held). (`inputs.3d.validation`
  is confirmed the canonical coarse deck — its sha256 matches the `inputs.hash` in `run_metadata_t2a.json`.
  `validation_v2` is an old-BC `2 0 4` variant, and `inputs.3d.production` is old-BC `2 0 4` **and** a
  different operating point (f\* = 0.1, ν\* = 0.01, 3 wingbeats) **and** already 128³ — the naive-but-wrong
  medium deck; neither is the baseline.)
- **Wing grid-convergence grader** in `src/mosquito_cfd/benchmarks/wing_convergence.py` — a **report-only**
  2-grid GCI on the peak body-frame `CF_chord` and `CF_normal`: per component it reports the coarse→medium
  **relative change** and the GCI as an **order-dependent band** — `gci_p1`/`gci_p2` at orders p = 1 and 2.
  An observed order needs a 3rd grid, and **diffused-IB force extraction is expected below the formal 2nd
  order near the boundary** (the tangential `CF_chord` especially), so a single assumed p = 2 would
  **understate** the uncertainty; the band brackets the reported order range (the sphere's pressure-dominated
  Cd precedent is **not** transferable). `gci_p1` is the **band edge, not a rigorous upper bound** (sub-1
  order → larger GCI). It emits **no Richardson `cf_exact`** grid-independent estimate — because part of the
  coarse↔medium delta is an IB-regularization model change (not a discretization error), a "grid-converged
  value" is not defensible and would re-introduce the very extrapolation over-claim report-only avoids; the
  GCI band already conveys the uncertainty. **No pass/fail bar, no loosenable tolerance** (per the scoping
  decision) — "not converged at coarse" is a valid, informative outcome for #40. A degenerate near-zero
  `cf_medium` raises a clear `ValueError` (reusing `_DEGENERATE_CF_FLOOR`). Reuses
  `reconstruct_wing_body_forces` / `body_frame_overall_match` / `compute_force_reference` (no re-derivation of
  the body-frame decomposition or the GCI formula).
- **LEV diagnostic (pure functions)** in `src/mosquito_cfd/benchmarks/lev.py`: vorticity-magnitude and
  Q-criterion (½-difference convention) computed from a 3-D velocity field, accepting **per-axis grid
  spacing** (scalar or `(dx,dy,dz)`) so an anisotropic grid is not silently mis-differentiated. TDD'd on
  synthetic fields with **known analytic vorticity** (solid-body rotation → `|ω| = 2Ω`, `Q = Ω²`).
  **Reported** (a present/absent LEV call), **not** a magic-number gate. The yt plotfile→field wiring and
  the actual medium-run LEV call are **deferred to T3b** (no committed new-convention plotfile exists yet).
- **Roadmap T3-row edit + T3 tracking issue.** The T3 row currently states a **graded** oracle ("CF
  converged **within tol**; LEV present"); this change **rewrites that exit-criterion cell** (not merely
  appends a note) to the report-only diagnostic + splits the row into **T3a/T3b**, with a reconciliation-log
  entry recording that **T3's graded oracle is relaxed to a reported diagnostic** (a 2-grid + diffused-IB
  "converged" verdict is not defensible) and the true observed-order (256³/grant) study **deferred**. Files
  the T3 EPIC tracking issue (none exists; the roadmap files them just-in-time).

## Non-goals (explicit)

- **No graded convergence pass/fail.** Convergence is **report-only** (relative change + GCI band); no
  `*_pass`/`*_match` verdict and no tolerance constant to loosen. The GCI is reported as the
  discretization-uncertainty band; a "not converged at coarse" reading is a valid, informative outcome.
- **No LEV gate.** The vorticity/Q diagnostic is reported, never a magic-number threshold.
- **No re-derivation** — reuse the sphere `grid_convergence_analysis` GCI/Richardson math, the T2a
  body-frame stack, `compute_force_reference`, `capture_run_metadata`, and the T2b reproducibility-guard
  pattern.
- **Cluster-free.** No sim is run here; T3a is TDD'd against the committed coarse `forces_t2a_newconv.csv`
  + synthetic fixtures. The medium run + grading real data are **T3b**.
- **Docs deferred to T3b (stated, not missed):** the `benchmarks/METHODS.md` flapping-convergence case
  writeup and the RESULTS.md convergence section are **T3b** (they need the real medium numbers); T3a
  changes **no** IAMReX pin, so METHODS.md needs no pin edit now. `docs/coordinate-convention.md` is
  **unaffected** (no convention change).
- **Out of scope:** the medium sim run itself (T3b); a **fine 256³** grid (owned by the roadmap's *Out of
  scope* section — H100/grant, "unless the coarse/medium pair already satisfies the oracles"); the true
  observed-order (3-grid) convergence *verdict*; and the full T4 curve-match / #40 resolution.

## Impact

- **Specs:** new capability `flapping-wing-grid-convergence` (deck-invariance, report-only grader, LEV
  diagnostic, provenance reuse); cross-references `flapping-wing-validation`.
- **Code:** `src/mosquito_cfd/benchmarks/wing_convergence.py` (grader) + `lev.py` (LEV pure functions),
  reusing the body-frame stack and the sphere GCI formula. `examples/flapping_wing/inputs.3d.convergence_medium`
  (new deck). Analysis-only, `uv`/numpy, no GPU, no solver change, no Docker/CI change; same `:fp64 @
  f93dc794` pin.
- **Tests:** deck-invariance (differ-only-`amr.n_cell`, dt/radius held); grader order-band known-answer +
  report-only + degenerate/sign guards + end-to-end reuse; LEV known-analytic-vorticity + per-axis spacing +
  min-points guard.
- **Docs:** `docs/aerodynamics_validation/roadmap.md` (**T3 row rewritten** to report-only + T3a/T3b split +
  reconciliation-log entry); `docs/aerodynamics_validation/t3b-handoff.md` (new run-plan).
- **Reproducibility:** T3a numbers are unit-tested from the committed coarse run + synthetic fixtures; the
  medium run's provenance (T3b) is `capture_run_metadata` (digest, IAMReX commit, inputs hash, git, hw,
  timing).
