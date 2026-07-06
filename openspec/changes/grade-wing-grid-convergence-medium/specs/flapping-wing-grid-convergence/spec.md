# flapping-wing-grid-convergence — spec delta (T3b)

T3b fulfils the two forward-looking requirements T3a left open: it wires the LEV plotfile→field
extraction (previously deferred) and converts the medium-run provenance forward contract into a
delivered, reproducible result. The deck-invariance requirement and the report-only grader-math
requirement are **unchanged** (T3a delivered them; T3b only *applies* the grader) and are not restated
here.

## MODIFIED Requirements

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
