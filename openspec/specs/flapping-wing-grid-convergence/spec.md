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

The analysis SHALL provide a **report-only** grid-convergence grader for the flapping wing: from a
coarse+medium pair of peak body-frame coefficients it SHALL compute, per component (peak `|CF_chord|`,
`|CF_normal|`), the coarse→medium **relative change** `(cf_medium − cf_coarse)/cf_medium` (normalized by
`cf_medium`, matching the reused sphere `epsilon`) and a **Grid Convergence Index reported as an
order-dependent band** — `gci_p1` (order p = 1) and `gci_p2` (order p = 2) using the sphere's GCI formula
`Fs·|relative_change|/(r^p − 1)`. An **observed** order is not computable from two grids, and **diffused-IB
force extraction is expected to be lower than the interior scheme's formal 2nd order near the boundary** (the
tangential `CF_chord` especially), so a single assumed p = 2 would **understate** the discretization
uncertainty; the `p = 1..2` band brackets the reported order range. It SHALL NOT emit a Richardson
grid-independent estimate (`cf_exact`): because part of the coarse↔medium delta is an **IB-regularization
model change, not a discretization error** (see the deck requirement's caveat), a Richardson extrapolation
to the h→0 force is not defensible here and would re-introduce the exact "we know the converged value"
over-claim the report-only framing exists to avoid; the GCI band already conveys the discretization
uncertainty. Correspondingly, **`gci_p1` is the reported band edge, NOT a rigorous upper bound**: if the
near-boundary order is sub-1 (plausible for the shear-dominated `CF_chord`), the true GCI **exceeds**
`gci_p1`. The grader SHALL **reuse** `reconstruct_wing_body_forces` / `body_frame_overall_match` for the
peaks and `compute_force_reference` for `F_ref` (no re-derivation of the body-frame decomposition or the GCI
formula). It SHALL be **report-only**: the return value SHALL carry **no** `*_pass`/`*_match`/`converged`/
`in_band` verdict field and SHALL define **no** loosenable pass/fail tolerance constant; a "not converged at
coarse" result is a valid, informative outcome (feeds #40). A degenerate near-zero `cf_medium` (the
denominator) SHALL raise a clear `ValueError` (reusing the module's `_DEGENERATE_CF_FLOOR`), never a
`ZeroDivisionError` or a silent huge-finite garbage ratio.

#### Scenario: 2-grid order-band GCI reproduces the hand-computed values

- **Given** `cf_coarse = 0.92`, `cf_medium = 0.80`, `r = 2`, `safety_factor = 1.25`
- **When** `wing_grid_convergence` is evaluated
- **Then** `relative_change = (0.80 − 0.92)/0.80 = −0.15` and the GCI **band** is `gci_p1 = 1.25·0.15/(2¹ − 1)
  = 0.1875` and `gci_p2 = 1.25·0.15/(2² − 1) = 0.0625` (p = 1 is 3× the p = 2 uncertainty, and the reported
  band edge — not a rigorous bound) — the same GCI formula the sphere uses, evaluated across the reported
  order band (order unobservable from 2 grids; the sphere's pressure-dominated Cd precedent is **not**
  transferable to the tangential wing CF). **No** `cf_exact` grid-independent estimate is returned

#### Scenario: Reported, not graded (no pass/fail, no tolerance, no extrapolant)

- **Given** the grader's return value
- **When** it is inspected
- **Then** it contains exactly `{cf_coarse, cf_medium, relative_change, gci_p1, gci_p2, r}` and **no**
  `*_pass`/`*_match`/`converged`/`in_band` key **and no `cf_exact`/Richardson-extrapolant key**, and the
  module defines no convergence tolerance constant to loosen — the GCI band is reported as the
  discretization-uncertainty range, not a gate and not an estimate of the grid-converged value

#### Scenario: Degenerate and sign-flip inputs are handled honestly

- **Given** a near-zero `cf_medium` (below `_DEGENERATE_CF_FLOOR`), and separately a coarse/medium pair of
  **opposite sign** (a coefficient that flips under refinement)
- **When** `wing_grid_convergence` is evaluated
- **Then** the near-zero `cf_medium` raises a clear `ValueError` (not `ZeroDivisionError`, not a silent
  `nan`/huge-finite garbage), while the opposite-sign pair returns **finite** report values (a
  `|relative_change| > 1` and a large GCI band) — honestly "not converged," never an error, consistent with
  the report-only philosophy

#### Scenario: End-to-end from CSVs reuses the body-frame stack

- **Given** a coarse and a medium IB-particle CSV
- **When** `wing_grid_convergence_from_body_forces` computes per-component convergence
- **Then** it reconstructs the peak `CF_chord`/`CF_normal` from **both** CSVs via
  `reconstruct_wing_body_forces` + `body_frame_overall_match` (reused, not re-derived) and returns
  `wing_grid_convergence` per component; feeding the **same** CSV as coarse and medium yields
  `relative_change = 0` and `gci_p1 = gci_p2 = 0` (self-convergence sanity), and a CSV whose `Fx/Fy/Fz` are
  scaled by `k` (all other columns preserved) scales each body-frame peak by exactly `k`, yielding
  `relative_change = (k − 1)/k` (**not** `k − 1`, because the normalization is by `cf_medium = k·cf_coarse`)

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

