# Add fine-grid (256³) flapping-wing convergence — Tier T3c

## Why

Tier **T3b** (PRs [#48](https://github.com/talmolab/mosquito-cfd/pull/48)/[#49](https://github.com/talmolab/mosquito-cfd/pull/49))
ran the medium 128×64×128 grid on the A40, committed `forces_medium.csv` + `run_metadata_t3b.json`,
and reported the coarse↔medium **relative change + 2-grid GCI band (p = 1..2)** for peak body-frame
CF_chord/CF_normal:

- **CF_chord:** 0.923 → 0.554, −66.5 %, GCI band 0.28–0.83 — **not grid-converged** at medium
- **CF_normal:** 2.606 → 2.303, −11.7 %, GCI band 0.04–0.13 — **nearly grid-settled**

Tier **T4** (PR [#51](https://github.com/talmolab/mosquito-cfd/pull/51)) validated the wing against
van Veen's quasi-steady model. That validation shows the CFD chord **converges toward the model**
under refinement (0.92 coarse → 0.554 medium → model total ≈ 0.43), but the 2-grid study cannot
close the analysis:

1. **No observed convergence order.** Three grids are required to compute the rate p at which CF_chord
   approaches the h→0 limit. From two grids, both orders p = 1 and p = 2 are load-bearing — the
   reported GCI band [0.28, 0.83] spans them. Without p, it is impossible to apportion the remaining
   chord gap (~0.55 − 0.43 ≈ 0.12) between "more grid error" and "physical residual."
2. **Van Veen's ~0.3 is underdetermined.** It lies *inside* the GCI band under 1st-order, *outside*
   under 2nd-order. The 3-grid study fixes p from data, resolving the ambiguity.

**Tier T3c** closes GitHub issue [#50](https://github.com/talmolab/mosquito-cfd/issues/50) by running
the fine 256×128×256 grid and completing the Richardson study. It follows the same operator-run
split used by T3a/T3b and T2a/T2b: **Session A** delivers the reviewed + approved proposal, the
fine-grid deck, and the cluster-free TDD code; **Session B** (post-run) commits the data and the
RESULTS section.

## What Changes

### New fine-grid input deck

`examples/flapping_wing/inputs.3d.convergence_fine` — an **exact copy** of
`inputs.3d.convergence_medium` changing **only** two parameters:

- `amr.n_cell = 256 128 256` (2× medium in all directions, 4× coarse)
- `amrex.the_arena_init_size = 28` added (proactive GPU-memory cap, leaving ~12 GB headroom on the
  A40 40 GB GPU; prevents first-run OOM from the AMReX default ¾-GPU arena = 30 GB)

All other parameters are **identical**: `ns.fixed_dt = 5e-4` (temporal error isolated), `particle_inputs.radius = 1.5` (IB model held),
`amr.plot_int = 100` (plotfiles every 100 steps — enables LEV on the fine grid at the same phases as
medium), kinematics (`f_star=1.0, phi_amp_deg=70, pitch_amp_deg=45`), `stop_time=1.0`, `max_step=2000`.

**CFL note (Δx = 0.03125):** CFL ≈ 28·5e-4/0.03125 ≈ 0.45 < 0.5. Borderline but stable in principle.
If the fine run diverges, the operator MAY reduce `ns.fixed_dt` to `2.5e-4` as a runtime fallback
(NOT baked into the deck); if reduced, `dt_reduced = true` is recorded in `run_metadata_t3c.json`
and the temporal confounding is **flagged explicitly in RESULTS** alongside the convergence numbers.

### Operator cluster run (Session B, out-of-session)

A40 (`:fp64 @ f93dc794`, same IAMReX pin as T3a/T3b). Estimated ~2 hr wall time (8× medium cell
count, ~2–3× medium wall time based on AMReX scaling observations). The operator checks GPU memory
before submitting; the deck's `amrex.the_arena_init_size = 28` provides headroom. If the A40 proves
insufficient (memory OOM after the cap, or the job exceeds the queue limit), this is declared a blocker
in RESULTS and #50 is left open with a note: "H100 required."

### Committed run data + provenance (Session B)

`examples/flapping_wing/forces_fine.csv` (29-column IB-particle schema, identical to coarse/medium)
and `examples/flapping_wing/run_metadata_t3c.json` captured via `capture_run_metadata` with the same
fields as `run_metadata_t3b.json` plus `"tier": "T3c"`, `"grid": "256 128 256"`, named extra fields
`fixed_dt`, `max_step`, `dt_reduced`, `plotfile_dir`.

### 3-grid convergence analysis (cluster-free, Session A code + Session B numbers)

**Two new functions in `src/mosquito_cfd/benchmarks/wing_convergence.py`:**

1. **`wing_grid_convergence_3grid(cf_coarse, cf_medium, cf_fine, *, r=2.0, safety_factor=1.25) -> dict`**
   (new scalar-level function). Computes from the three-grid triple:
   - `observed_order` = log|δ₁₂/δ₂₃| / log(r), where δ₁₂ = cf_medium − cf_coarse, δ₂₃ = cf_fine −
     cf_medium; `NaN` if non-monotone (opposite-sign δ₁₂ / δ₂₃) or degenerate (δ₂₃ = 0 below floor)
   - `cf_exact_richardson` = cf_fine + δ₂₃ / (r^p_obs − 1); `NaN` when observed_order is NaN
   - `gci_fine` = safety_factor · |ε₂₃| / (r^p_obs − 1), where ε₂₃ = δ₂₃/cf_fine; `NaN` when NaN
   - `monotone` = `bool(sign(δ₁₂) == sign(δ₂₃))` — always returned, never NaN
   - `cf_coarse`, `cf_medium`, `cf_fine`, `r` — always returned

   **Report-only, IB caveat documented.** `cf_exact_richardson` is an *illustrative* Richardson
   estimate: because the IB regularization sharpens with the grid (dv = h·d_nn²), a portion of each
   delta reflects IB-model change, not purely discretization error — so cf_exact_richardson is **not**
   a definitive h→0 limit; see design D1. No pass/fail verdict, no loosenable tolerance.

2. **`assert_gradeable_triple(coarse_csv, medium_csv, fine_csv, *, coarse_deck=None, medium_deck=None, fine_deck=None, stop_time=_STOP_TIME) -> None`**
   (new gradeability guard extending `assert_gradeable_pair`). Asserts non-empty / covers window / same
   time grid for all three CSVs, plus optionally checks `ns.fixed_dt` consistency across all three
   decks. Raises `ValueError` with `"no data rows"` / `"window"` / `"time-grid"` / `"fixed_dt"`
   substrings.

**Extend existing function (backward-compat):**

`wing_grid_convergence_from_body_forces(coarse_csv, medium_csv, fine_csv=None, *, f_star, phi_amp_deg, pitch_amp_deg, window_t0=STEADY_WINDOW_T0) -> dict`

When `fine_csv is None` (default): unchanged behavior, returns the existing 2-grid dict per component
(`cf_chord: {2-grid keys}`, `cf_normal: {2-grid keys}`). When `fine_csv is not None`: calls
`wing_grid_convergence_3grid` per component, returning the 3-grid dict. The 2-grid path is never
broken; all T3b tests continue to pass.

### LEV on fine plotfiles (Session B)

If `amr.plot_int = 100` produced fine-grid plotfiles (expected under the committed deck), apply
`wing_lev_report` at mid-stroke `t ≈ 0.5` on the fine grid. Report alongside the coarse/medium
`q_pos_vol`/`q_pos_frac` contrast. If the fine run was submitted with `amr.plot_int = -1` (memory
fallback), note "force-only run, LEV not available for fine grid" in RESULTS — consistent with what
T3b documented for the medium run's LEV.

### RESULTS.md — new "Grid convergence (T3c)" subsection (Session B)

Add `### Grid convergence (T3c, fine 256³)` to `examples/flapping_wing/RESULTS.md` under the
existing `### Grid convergence (T3b, medium 128³)` section, with:
- A 3-column table: coarse / medium / fine peak CF, relative changes, observed order p, Richardson
  estimate cf_exact_richardson per component
- A written verdict: "converged" / "not yet converged" / "non-monotone" — **all are valid, informative
  outcomes** (no pass bar, report-only)
- Explicit IB caveat: cf_exact_richardson is an illustrative Richardson estimate; see design D1
- If dt was reduced: flag temporal confounding explicitly
- The T3b "Grid convergence" section is kept intact (not modified); T3c is additive

### Roadmap update (Session A)

`docs/aerodynamics_validation/roadmap.md`:
- Add T3c row to the Tiers table: `⬜ **T3c** (#50)` at proposal time; flip to `✅` with PR ref on
  merge
- Update the Sequencing paragraph (line ~99) to mention T3c + #50

## Non-goals (explicit)

- **No pass/fail, no tolerance constant, no verdict key.** T3c stays **report-only** — the 3-grid
  analysis reports observed order + Richardson estimate with the IB caveat; "not converged" or
  "non-monotone" is a valid, informative result.
- **No new solver / Docker / IAMReX pin change.** Same `:fp64 @ f93dc794`, FP64 throughout, `uv` for
  all Python.
- **No modification to T3b's 2-grid function path or existing tests.** The `fine_csv=None` default
  preserves all existing T3b behavior; all `test_wing_convergence_medium.py` tests pass unmodified.
- **No change to T4's decomposition (`decompose_wing_force`) or van Veen model.** T3c analysis-only.
- **No closing of #40** (already resolved by T4). T3c closes only #50.
- **No additional simulation beyond the one fine-grid run.** The coarse (T2a) and medium (T3b) CSVs
  are reused from committed data.

## Impact

- **Specs:** MODIFY `flapping-wing-grid-convergence` — ADD fine-grid deck invariance requirement; MODIFY
  the report-only grader requirement to add the 3-grid extension path; ADD fine-run provenance and
  reproducibility requirement.
- **Input deck (Session A):** `examples/flapping_wing/inputs.3d.convergence_fine` — guarded by
  deck-invariance test in `tests/test_convergence_deck.py` and 3-deck temporal isolation test.
- **Code:** two new functions (`wing_grid_convergence_3grid`, `assert_gradeable_triple`) + one extended
  parameter (`fine_csv=None` on `wing_grid_convergence_from_body_forces`). Analysis-only, `uv`/numpy,
  no GPU at analysis time.
- **Data (Session B):** `examples/flapping_wing/forces_fine.csv` + `run_metadata_t3c.json`; real
  fine-grid plotfiles stay on Z: (gitignored).
- **Tests (Session A cluster-free):** `tests/test_convergence_deck.py` — deck-invariance and 3-deck
  temporal isolation; `tests/test_wing_grid_convergence.py` — new 3-grid known-answer,
  self-convergence, p_obs≤0, p_obs≈0, non-monotone, degenerate, and key-set tests;
  `tests/test_wing_convergence_medium.py` — `assert_gradeable_triple` guard tests (including
  fixed_dt mismatch and composition proof); `tests/test_wing_convergence_fine.py` (skipif CSV absent).
  Session B adds: `tests/test_results_reproducibility.py` (§5.1 reproducibility guard).
- **Docs (Session A):** `docs/aerodynamics_validation/t3c-handoff.md` (operator run instructions);
  `roadmap.md` (T3c row stub, Sequencing paragraph). Session B adds: `examples/flapping_wing/RESULTS.md`
  (T3c subsection + forward pointer in T3b prose); `benchmarks/METHODS.md` (Case 3 deferral sentence
  updated); `roadmap.md` (T3c row → ✅).
- **Issues:** **Closes #50** on merge. No other issues touched. Pre-merge grep confirms the PR
  title/body/commits carry no unintended closing keywords (see tasks §8).
