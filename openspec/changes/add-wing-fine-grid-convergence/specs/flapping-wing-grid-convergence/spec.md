# flapping-wing-grid-convergence — T3c spec delta

## ADDED Requirements

### Requirement: Fine-grid deck changes only the spatial resolution and GPU arena cap

`examples/flapping_wing/inputs.3d.convergence_fine` SHALL be identical to
`examples/flapping_wing/inputs.3d.convergence_medium` **except** for `amr.n_cell`
(`256 128 256` vs the medium `128 64 128`) and the addition of `amrex.the_arena_init_size = 28`
(a proactive GPU-memory cap leaving ~12 GB headroom on the A40's 40 GB GPU; the AMReX default
3/4-GPU arena = 30 GB may be exhausted by 8.4M-cell FP64 state). All other parameters SHALL be
**identical** to the medium deck: `ns.fixed_dt = 5e-4` (temporal error isolated, same as
coarse/medium), `particle_inputs.radius = 1.5` (IB regularization held), `amr.plot_int = 100`
(plotfiles every 100 steps — enables LEV at the same phases), kinematics (f\* = 1.0, φ = 70°,
α = 45°), `stop_time = 1.0`, `max_step = 2000`, domain and BCs unchanged.

**CFL note (Δx = 0.03125):** CFL ≈ 28·5e-4/0.03125 ≈ 0.45 < 0.5 at the peak wingtip speed.
Borderline; a runtime dt reduction to `2.5e-4` is permissible if the run is unstable, but SHALL
NOT be baked into the deck — the deck comment documents this fallback and its consequence
(temporal confounding, recorded as `dt_reduced=true` in the run metadata).

#### Scenario: Fine and medium decks differ only in amr.n_cell and amrex.the_arena_init_size

- **Given** the medium `inputs.3d.convergence_medium` and the fine `inputs.3d.convergence_fine`
  parsed into `{key → value}` maps (comments stripped, whitespace normalized)
- **When** their differing keys are compared
- **Then** the symmetric difference is exactly `{amr.n_cell, amrex.the_arena_init_size}`;
  `amr.n_cell` is `"256 128 256"` in fine and `"128 64 128"` in medium; all other keys —
  domain, BCs, kinematics, ν\*, `fixed_dt` = `5e-4`, `radius` = `1.5`, `amr.plot_int` = `100`,
  `max_step`, `stop_time`, `max_grid_size` — match value-for-value

#### Scenario: Temporal isolation and IB regularization are held across all three grids

- **Given** the coarse `inputs.3d.validation`, medium `inputs.3d.convergence_medium`, and fine
  `inputs.3d.convergence_fine`
- **When** `ns.fixed_dt` and `particle_inputs.radius` are read from each as floats
- **Then** `fixed_dt = 5e-4` in all three (temporal error identical, coarse↔medium↔fine delta is
  spatially isolated) and `radius = 1.5` in all three; the fine deck also carries
  `amrex.the_arena_init_size = 28` (the A40 arena cap, not present in coarse/medium — documented
  as a memory-management parameter, not a physics parameter)

### Requirement: 3-grid convergence grader with observed order and Richardson estimate (report-only)

The analysis SHALL provide a **report-only** 3-grid convergence grader extending the existing
2-grid grader. From the coarse/medium/fine peak body-frame coefficient triple it SHALL compute,
per component (peak `|CF_chord|`, `|CF_normal|`):

- **Observed order** p_obs = log|δ₁₂/δ₂₃| / log(r) where δ₁₂ = cf_medium − cf_coarse and
  δ₂₃ = cf_fine − cf_medium; `NaN` if non-monotone (opposite-sign δ values) or degenerate (δ₂₃
  at or below `_DEGENERATE_CF_FLOOR`)
- **Richardson extrapolant** cf_exact_richardson = cf_fine + δ₂₃ / (r^p_obs − 1); `NaN` when
  observed_order is NaN; **report-only with explicit IB caveat**: the IB regularization sharpens
  with the grid (`dv = h·d_nn²`), so each δ reflects combined spatial + IB-model refinement —
  cf_exact_richardson is an **illustrative** Richardson estimate, not a definitive h→0 limit
- **Fine-grid GCI** gci_fine = Fs·|ε₂₃|/(r^p_obs − 1) where ε₂₃ = δ₂₃/cf_fine; `NaN` when NaN
- **`monotone` flag** = `bool(sign(δ₁₂) == sign(δ₂₃))`; always returned as a bool, never NaN

The 3-grid scalar function `wing_grid_convergence_3grid(cf_coarse, cf_medium, cf_fine, *, r=2.0,
safety_factor=1.25) -> dict` SHALL be **report-only**: return a dict with exactly
`{cf_coarse, cf_medium, cf_fine, observed_order, cf_exact_richardson, gci_fine, r, monotone}` —
**no** `*_pass`/`*_match`/`converged`/`verdict` key. "Not converged" and "non-monotone" are valid,
informative outcomes.

The existing `wing_grid_convergence_from_body_forces` SHALL gain an optional `fine_csv: str | Path |
None = None` parameter (third positional, before the keyword-only block). When `None` (default):
unchanged 2-grid behavior (backward-compatible — all T3b tests pass unmodified). When provided:
calls `wing_grid_convergence_3grid` per component and returns the 3-grid dict per component.

A new `assert_gradeable_triple(coarse_csv, medium_csv, fine_csv, *, coarse_deck=None, medium_deck=None,
fine_deck=None, stop_time=_STOP_TIME) -> None` SHALL extend the 2-grid gradeability guard to three
CSVs, raising `ValueError` with `"no data rows"` / `"window"` / `"time-grid"` / `"fixed_dt"` for the
same failure modes. It SHALL reuse `assert_gradeable_pair` internally (not re-derive the per-pair
checks).

#### Scenario: 3-grid known-answer with exact quadratic convergence

- **Given** `cf_coarse = 1.0`, `cf_medium = 0.25`, `cf_fine = 0.0625`, `r = 2.0` (a triple with
  exact p = 2: δ₁₂ = −0.75, δ₂₃ = −0.1875, ratio = |δ₁₂/δ₂₃| = 4 = 2², log(4)/log(2) = 2)
- **When** `wing_grid_convergence_3grid` is evaluated
- **Then** `observed_order == pytest.approx(2.0)`, `cf_exact_richardson == pytest.approx(0.0)`
  (the extrapolant correctly identifies the exact limit), `monotone == True`, all returned values
  finite, return dict carries exactly `{cf_coarse, cf_medium, cf_fine, observed_order,
  cf_exact_richardson, gci_fine, r, monotone}` with no verdict field

#### Scenario: Non-monotone refinement returns NaN, not an error

- **Given** a triple where the sequence oscillates (e.g. cf_coarse = 1.0, cf_medium = 0.5,
  cf_fine = 0.8 — went down then up: δ₁₂ < 0, δ₂₃ > 0)
- **When** `wing_grid_convergence_3grid` is evaluated
- **Then** `monotone == False`, `observed_order` is `NaN`, `cf_exact_richardson` is `NaN`,
  `gci_fine` is `NaN` — no `ValueError`, no silent finite garbage; the non-monotone reading is a
  valid, informative outcome that is reported as-is

#### Scenario: Decelerating monotone convergence (p_obs ≤ 0) returns informative observed_order but NaN GCI

- **Given** a monotone triple where |δ₂₃| ≥ |δ₁₂| (convergence is decelerating or flat-rate,
  e.g. cf_coarse = 1.0, cf_medium = 0.9, cf_fine = 0.5: δ₁₂ = −0.1, δ₂₃ = −0.4,
  |δ₁₂/δ₂₃| = 0.25, p_obs = log(0.25)/log(2) = −2.0)
- **When** `wing_grid_convergence_3grid` is evaluated
- **Then** `monotone == True`, `observed_order` is finite (e.g. `−2.0` — negative observed order
  is a valid, informative signal of stalled convergence), `gci_fine` is `NaN` and
  `cf_exact_richardson` is `NaN` (the denominator `r**p_obs − 1 ≤ 0` makes both meaningless);
  no `ValueError` is raised

#### Scenario: Near-zero p_obs (equal deltas) protects the GCI denominator

- **Given** a monotone triple where |δ₁₂| ≈ |δ₂₃| (equal refinement steps, p_obs ≈ 0,
  e.g. cf_coarse = 1.0, cf_medium = 0.75, cf_fine = 0.5: δ₁₂ = δ₂₃ = −0.25, ratio = 1.0)
- **When** `wing_grid_convergence_3grid` is evaluated
- **Then** `monotone == True`, `gci_fine` is `NaN` and `cf_exact_richardson` is `NaN`
  (the `r**p_obs − 1` denominator guard fires — near-zero denominator would produce ±∞);
  no `ValueError`; the zero-order reading is still valid as a scientific observation

#### Scenario: Triple gradeability guard raises on malformed inputs

- **Given** any of: a truncated fine CSV with only header rows, a fine CSV covering only t ≤ 0.5
  (does not cover the steady window), a fine CSV with a halved time step (grid mismatch), or a
  fine deck where `ns.fixed_dt` differs from the medium deck (medium↔fine fixed_dt mismatch)
- **When** `assert_gradeable_triple(coarse_csv, medium_csv, fine_csv, *, coarse_deck, medium_deck,
  fine_deck)` is called
- **Then** it raises `ValueError` with a substring matching the failure mode:
  `"no data rows"`, `"window"`, `"time-grid"`, or `"fixed_dt"` respectively;
  a truncated/mismatched medium CSV also raises (the guard checks both coarse↔medium and
  medium↔fine pairs — internal delegation to `assert_gradeable_pair` is NOT skipped for the
  middle grid)

#### Scenario: 3-grid end-to-end from committed CSVs (report-only, no verdict)

- **Given** the committed coarse `forces_t2a_newconv.csv`, medium `forces_medium.csv`, and fine
  `forces_fine.csv` (the T3c operator run)
- **When** `assert_gradeable_triple(coarse, medium, fine)` passes and
  `wing_grid_convergence_from_body_forces(coarse, medium, fine_csv=fine, f_star=1.0,
  phi_amp_deg=70.0, pitch_amp_deg=45.0)` is called
- **Then** the return has `{cf_chord: <3-grid dict>, cf_normal: <3-grid dict>}` with each sub-dict
  carrying `{cf_coarse, cf_medium, cf_fine, observed_order, cf_exact_richardson, gci_fine, r,
  monotone}` and **no** verdict key; `r == 2.0`; `monotone` is a `bool`; the float values are
  finite or `NaN` (NaN for observed_order/cf_exact/gci_fine if non-monotone or p_obs ≤ 0).
  Note: the numeric reproducibility assertion (values match RESULTS T3c literals to `abs ≈ 0.02`) is
  a **Session B** guard — see the "Reproducibility guard" scenario below; the Session A contract test
  (`test_fine_3grid_reports_from_committed_csvs`, skipif CSV absent) asserts structure only.

### Requirement: Fine-run provenance and reproducibility (T3c forward contract)

The **T3c** operator fine run's provenance SHALL be captured via the existing `capture_run_metadata`
under the **same `:fp64 @ f93dc794` pin** (no new solver features needed for grid refinement),
producing `examples/flapping_wing/run_metadata_t3c.json` with fields:
- `docker_image`: the `:fp64` image digest (`ghcr.io/talmolab/mosquito-cfd@sha256:…`)
- `iamrex_commit`: `"f93dc794…"` (40-char SHA)
- `inputs.hash`: sha256 of `inputs.3d.convergence_fine`
- `tier`: `"T3c"`, `grid`: `"256 128 256"`
- `fixed_dt`, `max_step`, `dt_reduced` as named extra fields (machine-readable; `dt_reduced=true`
  if the operator reduced dt for stability — the grading triple-guard reads `fixed_dt` from this
  field)

`examples/flapping_wing/forces_fine.csv` SHALL have the 29-column IB-particle schema (identical
column order to `forces_t2a_newconv.csv` / `forces_medium.csv`). Its rows SHALL cover `max(time) ≈
1.0` (within 5 ms) and `len(df) > 1900` (a truncated/diverged run fails the schema pin test, not
the grader). The RESULTS T3c numbers SHALL be recomputable from the three committed CSVs via the
T2b/T3b reproducibility-guard pattern; the fine-grid deck hash SHALL be pinned:
`sha256(inputs.3d.convergence_fine) == run_metadata_t3c.json["inputs"]["hash"]`.

#### Scenario: Fine CSV matches the 29-column IB-particle schema

- **Given** the committed `examples/flapping_wing/forces_fine.csv`
- **When** its columns are read
- **Then** they equal the pinned 29-column IB-particle contract (`iStep,time,X,Y,Z,Vx,…,SumTz`)
  in exact order, `max(time) ≈ 1.0`, and `reconstruct_wing_body_forces` produces a finite
  CF_chord/CF_normal series — a truncated/diverged run that wrote only a few rows fails here,
  not silently inside the grader

#### Scenario: 3-grid convergence numbers recompute from committed CSVs (reproducibility guard)

- **Given** the three committed CSVs (coarse, medium, fine) and the fine deck
- **When** `assert_gradeable_triple` passes and `wing_grid_convergence_from_body_forces(coarse,
  medium, fine_csv=fine, …)` is called
- **Then** the per-component `observed_order`, `cf_exact_richardson`, `gci_fine`, `monotone` match
  the RESULTS T3c headline literals to `abs ≈ 0.02`, and `sha256(inputs.3d.convergence_fine)` equals
  `run_metadata_t3c.json["inputs"]["hash"]` (the fine deck and run metadata are pinned together)

## MODIFIED Requirements

### Requirement: Report-only 2-grid wing grid-convergence grader (order-band GCI)

The function `wing_grid_convergence_from_body_forces` SHALL additionally accept an optional
`fine_csv: str | Path | None = None` parameter (third positional, before the keyword-only block).
When `None` (the default), behavior is **identical** to the T3b/T3a implementation — same 2-grid
return dict, same internal code path, no behavioral change. The `wing_grid_convergence` scalar
function, `assert_gradeable_pair`, and all existing T3b-era scenarios are **unchanged** and continue
to pass as load-bearing requirements of this spec.

#### Scenario: Backward compatibility — 2-grid path unchanged when fine_csv is None

- **Given** `wing_grid_convergence_from_body_forces(coarse_csv, medium_csv, ...)` called without
  `fine_csv` OR with `fine_csv=None` explicitly
- **When** the function returns
- **Then** the return value has exactly the **2-grid key set** `{cf_chord: {cf_coarse, cf_medium,
  relative_change, gci_p1, gci_p2, r}, cf_normal: {…}}` — no 3-grid keys (`observed_order`,
  `cf_exact_richardson`, `gci_fine`, `monotone`) appear; the existing T3b tests
  (`test_medium_convergence_reports_from_committed_csvs` and related) pass unmodified with the same
  assertions they already make
