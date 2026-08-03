# flapping-wing-grid-convergence Specification

## Purpose
TBD - created by archiving change add-wing-grid-convergence. Update Purpose after archive.
## Requirements
### Requirement: Medium-grid deck changes only the spatial resolution

The medium-grid flapping deck `examples/flapping_wing/inputs.3d.convergence_medium` SHALL be identical to
the canonical coarse deck `examples/flapping_wing/inputs.3d.validation` **except** for `amr.n_cell`
(`128 64 128` vs the coarse `64 32 64`) — same domain (`8 4 8`), boundary conditions (`ns.lo_bc`/`ns.hi_bc
= 2 0 2`, y-periodic span), kinematics (f\* = 1.0, φ = 70°, α = 45°, deviation 0), viscosity (ν\* = 0.115),
`wing.vertex` + `particle_inputs` (including `particle_inputs.radius = 1.5`), `ns.init_iter = 2`,
**`ns.fixed_dt = 5e-4` held fixed**, and `amr.max_grid_size = 32` held. Holding dt fixed makes the temporal
discretization error **identical** in both runs, so the coarse↔medium difference is isolated from temporal
error.

**Caveat (grid-tied immersed boundary).** The difference is **not** purely a spatial *discretization*
convergence: the diffused-IB regularization is grid-tied — the marker volume `dv = h·d_nn²` and the
regularization kernel support scale with the grid spacing `h` — so refining the grid **also sharpens the IB
regularization model**. The coarse↔medium coefficient change therefore reflects **combined spatial
discretization + IB-regularization refinement** (with the fixed dimensionless `particle_inputs.radius = 1.5`
held constant against the changing `h`). This is inherent to grid-tied diffused IB and is a further reason
the study is **report-only** (Richardson does not model the IB-regularization change). `inputs.3d.validation`
is the confirmed baseline (its sha256 equals the `inputs.hash` in `run_metadata_t2a.json`); the old-BC
`inputs.3d.validation_v2` (`2 0 4`, z-wall) and the already-128³ **different-operating-point**
`inputs.3d.production` (f\* = 0.1, ν\* = 0.01, 3 wingbeats) SHALL NOT be used as the baseline.

#### Scenario: Medium and coarse decks differ only in amr.n_cell

- **Given** the coarse `inputs.3d.validation` and the medium `inputs.3d.convergence_medium` parsed into
  `key → value` maps (comments stripped; each value's internal whitespace normalized so `"2  2 2"` and
  `"2 2 2"` compare equal — robust to reformatting)
- **When** their differing keys are compared
- **Then** the symmetric difference is exactly `{amr.n_cell}` (medium `128 64 128`, coarse `64 32 64`); all
  other keys — domain, BCs, kinematics, ν\*, `fixed_dt`, `max_grid_size`, `particle_inputs.radius`,
  init_iter — match value-for-value

#### Scenario: dt and the IB regularization length are held fixed

- **Given** the two decks
- **When** `ns.fixed_dt` and `particle_inputs.radius` are read from each and parsed as floats
- **Then** `float(fixed_dt)` is `5e-4` in both (temporal error identical) and `float(radius)` is `1.5` in
  both (the dimensionless regularization length is held against the changing `h`); the deck header
  documents that only Δx changes, so the comparison isolates **spatial + IB-regularization refinement** from
  temporal error (a run-time dt reduction, if the medium run is unstable, is an operator fallback recorded
  in T3b, not baked into this deck)

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

### Requirement: LEV vorticity / Q-criterion diagnostic (reported, not gated)

The analysis SHALL provide **pure** functions computing the **vorticity magnitude** (`‖∇×u‖`) and the
**Q-criterion** (`Q = ½(‖Ω‖² − ‖S‖²)`, the half-difference convention, where Ω/S are the antisymmetric/
symmetric parts of ∇**u**) from a 3-D velocity field on a uniform grid, for the leading-edge-vortex (LEV)
"resolved/present" diagnostic. They SHALL accept **per-axis grid spacing** (`dx` as a scalar for an
isotropic grid **or** a `(dx, dy, dz)` triple), passing per-axis spacing to the gradient so an anisotropic
grid is not silently mis-differentiated. These SHALL be **reported**, never a magic-number pass/fail gate.
They SHALL be verified against **known analytic** answers on synthetic fields (cluster-free).

The yt plotfile→velocity-field extraction and the actual "LEV present at medium, weak/absent at coarse"
call — deferred to T3b in T3a — SHALL now be delivered by **reusing** the existing yt Eulerian-box adapter
`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` (which reads the level-0 covering grid into
FP64 `u, v, w` arrays indexed `[ix, iy, iz]` plus per-axis `dx`), composed with the LEV pure functions
(no new plotfile reader, no re-derivation). A thin composition `wing_lev_report(plotfile_path, *, lo, hi)`
SHALL extract the field over a **required, pinned wing near-field sub-box** (`lo/hi`; a domain-wide
reduction is forbidden — dominated by far-field noise and the grid-tied IB marker shell), evaluate the LEV
functions over the box **interior** (`[1:-1,…]`; boundary planes are one-sided lower-order), and report a
**resolution-fair** primary descriptor — the integrated positive Q over the box
(`q_pos_vol = Σ max(Q, 0)·dx·dy·dz`) and the positive-Q volume fraction `q_pos_frac` — alongside the peak
`‖ω‖` / peak `Q` reported **secondarily with an explicit resolution caveat**. The analysis SHALL be at
**mid-stroke `t ≈ 0.5`** (maximum stroke velocity `φ̇`, `plt01000`) — the most LEV-discriminating phase;
`t = 0.25` (stroke reversal, wing momentarily stopped) is **not** used. The plotfile SHALL be selected **by
physical time** (`current_time ≈ 0.5`), not by the `plt01000` name (a run-time `dt` reduction moves the
name↔time mapping). The near-field box SHALL be **derived from the plotfile's wing-marker bounding box**
(`particle_position_{x,y,z}`) + a fixed physical margin (a hard-pinned literal is forbidden — it is
phase-specific and would clip the mid-stroke wing, whose tip reaches `y ≈ 3.475`; an illustrative box is
`lo = (2.5, 0, 3)`, `hi = (5.5, 4, 5)`), **recorded verbatim in RESULTS**, **fixed** and identical on both
grids at the same phase, and the test SHALL **assert the marker bbox fits inside `lo/hi`**. **Honest scope:**
the box trims the far-field so the reduction is wing-region-defined and reproducible, but it does **not**
fully exclude the IB-regularization shell co-located with the wing (contamination **phase-amplified at
mid-stroke**), so `peak_q`/`peak_vorticity` remain shell-contaminated (secondary) and a **downstream-offset
box** is also reported to isolate shed vorticity; even `q_pos_vol` is **not resolution-invariant** (a
marginally-resolved coarse core under-estimates it) —
so a coarse→medium `q_pos_vol` **increase is a lower bound on LEV growth, not proof of present-vs-absent**;
RESULTS states this for both `q_pos_vol` and peak `Q`. It SHALL return a plain dict carrying **no**
`*_pass`/`converged`/`present` verdict key — the coarse↔medium contrast is **reported** (interpreted in
RESULTS prose), never a thresholded gate or a directional assertion. The two plotfiles SHALL be compared at
the **same phase**, guarded by asserting their `current_time` agree to within `0.5·min(dt_coarse, dt_medium)`.
The wiring SHALL be covered **both** by a `@pytest.mark.requires_plotfile` test against the real coarse ↔
medium plotfiles (auto-skipped in CI when `MOSQUITO_CFD_PLOTFILE_ROOT` is absent) **and** by a **committed
synthetic single-level AMReX/boxlib plotfile fixture** carrying an analytic field, so the
`extract_eulerian_box → lev` yt-read path is exercised cluster-free in CI.

#### Scenario: Solid-body rotation gives the analytic vorticity and Q

- **Given** a uniform grid carrying solid-body rotation `(u, v, w) = (−Ω·y, Ω·x, 0)`
- **When** `vorticity_magnitude` and `q_criterion` are evaluated on the interior
- **Then** `‖∇×u‖ = 2Ω` uniformly and `Q = Ω²` (pure rotation, strain `S = 0`, `Q = ½‖Ω_tensor‖² = ½·2Ω²`),
  matching the analytic values to floating tolerance; a pure-shear field `(γ·y, 0, 0)` gives `|ω| = γ` and
  `Q = 0` (rotation and strain cancel)

#### Scenario: Reported, not gated; anisotropic spacing honored; degenerate input guarded

- **Given** the LEV functions
- **When** they are evaluated
- **Then** on a uniform (zero-gradient) field they return `|ω| = 0` / `Q = 0` as **reported** arrays with no
  pass/fail verdict; on an anisotropic grid a `(dx, dy, dz)` triple yields the correct per-axis-differentiated
  curl (a scalar `dx` on a truly anisotropic grid would be wrong — hence per-axis spacing is accepted); and a
  field with fewer than 3 points on any axis raises a clear `ValueError` (a centred gradient needs ≥ 3
  points), never a silent degenerate result

#### Scenario: LEV wiring reuses the adapter and reports a resolution-fair coarse↔medium contrast (no directional gate)

- **Given** new-convention coarse (Δx = 0.125) and medium (Δx = 0.0625) wing plotfiles at **mid-stroke
  `t ≈ 0.5`** (selected by physical `current_time`, not the `plt01000` name; single-level, carrying the
  `('boxlib', {x,y,z}_velocity)` + `('boxlib', gradp{x,y,z})` fields, `init_iter = 2` so the velocity is
  non-zero) available under `MOSQUITO_CFD_PLOTFILE_ROOT`, and the **pinned** wing near-field box `lo/hi`
- **When** `wing_lev_report` extracts each field via `extract_eulerian_box` (reused, not re-implemented) over
  the near-field box and evaluates `vorticity_magnitude` / `q_criterion` with the adapter's per-axis `dx`
- **Then** for each grid it returns a report-only dict `{peak_vorticity, peak_q, q_pos_vol, q_pos_frac, dx,
  phase_time}` with **no** verdict key; the test (`@pytest.mark.requires_plotfile`, auto-skipping in CI)
  asserts both plotfiles share the same phase (`phase_time` within `0.5·min(dt_coarse, dt_medium)`), both
  grids give **finite, positive** `peak_vorticity`/`peak_q`/`q_pos_vol` (a coherent LEV core exists on both),
  and the pinned per-axis `dx` matches each grid — it does **not** assert `Q_medium > Q_coarse` (a resolution
  artifact, not physics); the "present at medium vs weak/absent at coarse" reading is reported via the
  `q_pos_vol`/`q_pos_frac` contrast (a `q_pos_vol` increase being a *lower bound* on LEV growth) and
  interpreted in RESULTS, not gated

#### Scenario: Committed synthetic plotfile gives the LEV wiring cluster-free CI coverage

- **Given** a committed tiny single-level AMReX/boxlib plotfile fixture (box ≥ 5³ so ≥ 3 interior points per
  axis) carrying an analytic solid-body-rotation velocity field (`(−Ω·y, Ω·x, 0)`) plus constant `gradp`,
  authored by a committed deterministic generator with explicit `<f8` byte order
- **When** the LEV composition reads it via `extract_eulerian_box` and computes the interior descriptors —
  with **no** `MOSQUITO_CFD_PLOTFILE_ROOT` and **no** cluster access
- **Then** the wiring runs in CI and reproduces the known analytic `‖ω‖ = 2Ω`, `Q = Ω²` to floating tolerance
  **and the exact resolution-fair descriptors** `q_pos_frac = 1` and `q_pos_vol = Ω²·N_interior·dx·dy·dz`
  (the exact value pins the volume Jacobian a bare `> 0` would miss; solid-body rotation is linear so
  `np.gradient` is exact on the interior), the adapter returns **bare FP64** arrays (`dtype == np.float64`,
  asserted separately so the fixture proves the FP64 read path rather than tripping the fp32-build guard),
  the returned report dict carries **no** verdict key, and the fixture is regenerable (generator output
  matches the committed bytes) — proving the `extract_eulerian_box → lev` yt-read path (field-tuple access,
  covering grid, FP64 unwrap, `max_level == 0`) end-to-end without a cluster

### Requirement: Medium-run provenance and reproducibility (forward contract for T3b)

The **T3b** operator medium run's provenance SHALL be captured via the existing `capture_run_metadata`
(Docker image digest, IAMReX commit `f93dc794`, inputs hash of `inputs.3d.convergence_medium`, git SHA,
hardware, timing) under the **same `:fp64` pin** (grid refinement needs no new solver features), and the
T3b RESULTS convergence numbers SHALL be recomputable from committed data via the T2b reproducibility-guard
pattern. This forward contract is **fulfilled by T3b**: the committed `examples/flapping_wing/forces_medium.csv`
(the 29-column IB-particle write-out, identical schema to the committed coarse `forces_t2a_newconv.csv`) and
`examples/flapping_wing/run_metadata_t3b.json` record the run, and the RESULTS convergence section's
per-component `relative_change` + `gci_p1`/`gci_p2` recompute from the committed coarse + medium CSVs. The
LEV peaks are **plotfile-derived** (the plotfiles are not committed — `plt*/` is gitignored) and are
therefore **not** part of the CSV-recompute guard; they are covered by the `requires_plotfile` real-data
test and the committed synthetic fixture instead. No new sim run, Docker change, or pin change beyond the
medium run itself; if the medium run required a run-time `dt` reduction for stability, that reduction SHALL
be recorded in `run_metadata_t3b.json` as **named `extra` fields** (`fixed_dt`, `max_step`, `dt_reduced`),
not baked into the deck — so the grading pre-flight guard can read `fixed_dt` and refuse to grade a
coarse↔medium pair whose time grids differ. The reproducibility guard SHALL pin **both** decks of the
graded pair: `sha256(inputs.3d.validation)` equals the coarse `run_metadata_t2a.json` inputs hash and
`sha256(inputs.3d.convergence_medium)` equals the medium `run_metadata_t3b.json` inputs hash.

#### Scenario: Same pin, provenance via the existing helper (T3b)

- **Given** the T3b medium run (operator-run A40)
- **When** its provenance is recorded
- **Then** it uses `capture_run_metadata` with the `:fp64 @ f93dc794` image (no new pin), captures the
  `inputs.3d.convergence_medium` inputs hash (matching the deck-invariance guard's deck), git SHA, hardware,
  timing, and the named `extra` fields `fixed_dt`/`max_step`/`dt_reduced` — so any run-time `dt` reduction is
  recorded there as a named field (not in the deck, and readable by the grading guard)

#### Scenario: Committed medium CSV matches the 29-column IB-particle schema

- **Given** the committed `examples/flapping_wing/forces_medium.csv`
- **When** its header is read
- **Then** its columns equal the pinned 29-column IB-particle contract (`iStep,time,X,Y,Z,Vx,…,SumTz`) in
  exact order — identical to `forces_t2a_newconv.csv` — so a silent solver column-order/name drift fails
  closed, and `reconstruct_wing_body_forces` consumes it to a finite `CF_chord`/`CF_normal` series

#### Scenario: Convergence numbers recompute from the committed coarse + medium CSVs

- **Given** the committed coarse `forces_t2a_newconv.csv` and medium `forces_medium.csv`
- **When** the reproducibility guard first calls `assert_gradeable_pair(coarse, medium)` and then recomputes
  `wing_grid_convergence_from_body_forces(coarse, medium, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)`
- **Then** `assert_gradeable_pair` fails loudly (self-describing `ValueError`) if either CSV is empty (`"no
  data rows"`), does not reach `max(time) ≈ 1.0` (`"window"`), or does **not share the same time grid**
  (`"time-grid"`) — compared on the **set of unique `iStep` values** and their matching sample times (the
  committed coarse CSV has 3 duplicate `t = 0` rows from `init_iter = 2`, so a raw row-count/`allclose` check
  would false-reject a valid same-dt run; the unique-`iStep` comparison + the metadata `fixed_dt` equality is
  what catches a dt reduction) — so a wrong-pair, truncated, or dt-reduced write-out cannot be graded
  silently; and, when it passes, the per-component `relative_change`, `gci_p1`, `gci_p2` reproduce the RESULTS
  convergence literals
  to `abs ≈ 0.02` (the T2b tolerance), with `r = 2` fixed by the deck pair and `gci_p1 = 3·gci_p2`; the guard
  also pins `sha256(inputs.3d.validation)` to the coarse metadata hash and `sha256(inputs.3d.convergence_medium)`
  to the medium metadata hash (both decks of the graded pair confirmed)

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

