# force-extraction Specification

## Purpose
TBD - created by archiving change add-sphere-stress-cd. Update Purpose after archive.
## Requirements
### Requirement: Periodic-duct control-volume drag from Eulerian fields

The benchmarks package SHALL compute the streamwise drag force on a body from gridded Eulerian fields via
a control-volume momentum balance over a box spanning the full periodic cross-section between an inlet
plane and an outlet plane, using `F_drag = rho * ( sum(u_inlet^2) - sum(u_outlet^2) ) * dA - sum(gradpx) *
dA * dx` (the lateral periodic faces cancel exactly; the streamwise viscous flux is O(1/Re) and neglected
at Stage 1). The computation SHALL be FP64, SHALL NOT use the immersed-boundary particle force fields, and
SHALL use the persisted `gradpx` directly so the unknown additive pressure constant cancels (equal plane
areas). At least one known-answer test SHALL use `rho != 1` so a `nu`-for-`mu`/`rho` confusion cannot hide.

#### Scenario: Momentum-flux term matches a known answer

- **GIVEN** an inlet plane at uniform `U` and an outlet plane uniformly slowed to `c*U` (or a known
  spatially-varying profile), with zero pressure gradient
- **WHEN** the periodic-duct drag is evaluated
- **THEN** the returned force equals `rho * (sum(u_inlet^2) - sum(u_outlet^2)) * dA` to round-off, is
  positive for a slowed (wake) outlet, and is computed without reading any plotfile or cluster path

#### Scenario: Pressure-gradient term matches a known answer

- **GIVEN** identical inlet and outlet planes (no momentum change) and a constant `dp/dx = G` over a
  volume `V` between them
- **WHEN** the periodic-duct drag is evaluated
- **THEN** the returned force equals `-G * V` to round-off (the form-drag term), confirming the pressure
  contribution uses `gradpx` directly with no reconstruction

#### Scenario: Null field yields zero drag

- **GIVEN** identical uniform inlet/outlet planes and zero pressure gradient
- **WHEN** the periodic-duct drag is evaluated
- **THEN** the returned force is zero to within floating-point round-off

#### Scenario: Non-finite field raises

- **GIVEN** an inlet/outlet plane or pressure-gradient volume containing a NaN/inf value
- **WHEN** the periodic-duct drag is evaluated
- **THEN** a clear error is raised rather than a silent NaN drag/Cd being returned

#### Scenario: Degenerate or misordered planes raise

- **GIVEN** a sphere CV drag request with `x_inlet >= x_outlet`, or two locations that resolve to the
  same grid cell
- **WHEN** the control-volume drag is requested
- **THEN** a clear error is raised (rather than a sign-flipped or zero-thickness silent-wrong-answer)

#### Scenario: Steadiness gate is measured, not assumed

- **GIVEN** two consecutive plotfiles (`plt09900`, `plt10000`) and a control volume
- **WHEN** the unsteady momentum term `rho * d/dt integral_CV u_x dV` is computed and divided by the drag
- **THEN** the fraction SHALL be below 5% for the steady balance (hence the H1/H2 verdict) to stand; on
  the committed data it is ~0, confirming the steady-state assumption rather than assuming it

### Requirement: Plotfile Eulerian-box adapter

The package SHALL provide a yt-based adapter that reads the velocity components and pressure-gradient
fields over a specified axis-aligned region of an AMReX plotfile into FP64 numpy arrays, isolating all
plotfile/cluster I/O from the numerical core. It SHALL read fields by their `('boxlib', <name>)` tuple
identifiers and assert all required fields are present.

#### Scenario: Single-level covering grid is exact and FP64

- **GIVEN** a FlowPastSphere plotfile with `amr.max_level = 0`
- **WHEN** the adapter reads a control-volume region (via the full level-0 covering grid, sliced in memory)
- **THEN** it returns the stored cell-centered values without interpolation, asserts `max_level == 0`,
  unwraps `YTArray` to bare numpy and asserts `float64` (the fp32-build guard), asserts all six required
  fields present, and returns the real cell-center coordinate arrays

#### Scenario: Read extent is padded by the requested halo

- **GIVEN** a region request with a halo of `h` cells
- **WHEN** the adapter reads an interior region
- **THEN** each axis of the returned arrays is larger than the unpadded request by `2*h` cells, so a
  caller can form face-straddling differences without a one-sided or out-of-range stencil

### Requirement: Field-based sphere Cd entry point

`extract_sphere_cd` SHALL support a `method="cv"` option that returns the periodic-duct control-volume
drag coefficient as the reported Cd, while retaining the legacy IB-marker sum as a clearly labelled
diagnostic field (never the reported number). The return value SHALL remain backward compatible (existing
keys preserved; new keys added).

#### Scenario: CV method reports the field-based Cd

- **GIVEN** a sphere plotfile and `method="cv"`
- **WHEN** `extract_sphere_cd` is called
- **THEN** the returned `cd` is the periodic-duct control-volume drag coefficient
- **AND** the legacy marker-sum value is still present under a diagnostic key (e.g. `cd_marker_lastpass`)
  labelled as the last-multidirect-sub-iteration diagnostic, not the result

#### Scenario: Default method preserves the existing contract

- **GIVEN** a caller that invokes `extract_sphere_cd` without specifying a method
- **WHEN** the function returns
- **THEN** all keys returned by the pre-change implementation (`cd`, `fx_sum`, `fy_sum`, `fz_sum`,
  `n_particles`, `time`, `validated`, `error_pct`, `literature_cd`) are still present with their
  established meanings

### Requirement: Literature validation classifies the extraction-vs-field hypothesis

The control-volume sphere Cd SHALL be computed on the committed `plt10000` for both grids and classified
against the literature value (Cd = 1.087, Johnson & Patel 1999): the result decides H1 (force-extraction
bug; the field carries the correct drag), H2 (flow-field deficit; the field also under-produces drag), or
H1' (correct, with the confined-array setup offset). The classification SHALL be recorded as an analysis
artifact (a `requires_plotfile`-marked local test that skips where the plotfile is unavailable), not a CI
gate. The committed run is a transversely-periodic array (pitch 10 D, 5 D upstream), so its true Cd
carries an estimated +3-6% confinement offset above the isolated literature value.

#### Scenario: H2 is decisively excluded

- **GIVEN** the committed sphere `plt10000` for both grids
- **WHEN** the periodic-duct CV Cd is computed
- **THEN** both grids return Cd well above the broken ~0.45 marker value (here ~1.18-1.34), so the
  flow-field-deficit hypothesis H2 is rejected and the ~2.4x deficit is attributed to force extraction (H1)

#### Scenario: Grids converge toward literature (H1/H1')

- **GIVEN** the coarse and medium control-volume Cd
- **WHEN** the pair is examined for grid convergence
- **THEN** refinement reduces Cd toward literature (coarse > medium), and the Richardson extrapolation
  lands in the confinement-corrected band around 1.087 (isolated-equivalent within ~±5%), classifying the
  outcome H1/H1' (extraction bug resolved; residual offset explained by confinement) with no re-run; the
  corrected `extract_sphere_cd(method="cv")` becomes the reported benchmark Cd

#### Scenario: H2 fallback would defer remediation

- **GIVEN** a hypothetical outcome where the CV Cd reproduced the ~0.45 deficit on both grids
- **WHEN** the result is classified
- **THEN** it would be recorded as H2 (flow-field deficit) and the solver fix + re-run documented as
  deferred post-submission, not performed in this change (this branch did not occur — the result is H1/H1')

### Requirement: Robust input validation for the control-volume tools

The control-volume tools SHALL validate their inputs and fail loud rather than emit non-finite or
sign-flipped results. The unsteady-momentum term SHALL reject a non-positive time step, and the
field-based sphere Cd entry point SHALL not require IB-marker fields when run in control-volume mode.

#### Scenario: Non-positive time step raises

- **GIVEN** the unsteady-momentum term with `dt <= 0`
- **WHEN** it is evaluated
- **THEN** a clear error is raised, rather than dividing to `inf`/`nan`

#### Scenario: CV mode tolerates a field-only plotfile

- **GIVEN** a plotfile with no IB-marker particle fields and `extract_sphere_cd(method="cv")`
- **WHEN** the drag coefficient is extracted
- **THEN** the control-volume `cd` is returned, the legacy marker diagnostic `cd_marker_lastpass` is
  `None` (computed best-effort), and no error is raised
- **AND** with `method="marker"` (the default) a missing-particle plotfile still raises, because the
  marker sum *is* that method

### Requirement: Cluster-free verifiability of the plotfile-to-drag wiring

The sphere control-volume drag entry point SHALL compose the Eulerian-field adapter and the numeric
core deterministically, so that — given a known gridded Eulerian box — the resulting drag coefficient
is a known closed-form value. This makes the adapter→core wiring (plane selection, the pressure-gradient
slice, the cell area/thickness weighting, and the Cd conversion) verifiable without cluster data, by
substituting a synthetic box for the plotfile read.

#### Scenario: Known synthetic box yields the closed-form Cd

- **GIVEN** a synthetic Eulerian box (uniform inlet plane, uniformly slowed outlet plane, constant
  pressure gradient) substituted for the plotfile read
- **WHEN** `sphere_cv_drag_cd` is invoked for inlet/outlet planes within that box
- **THEN** the returned `cd` equals the closed-form periodic-duct drag coefficient for that box to
  round-off, confirming the wiring selects the correct planes, slices `gradpx` between them, and applies
  the correct `dy*dz` and `dx` weights — all without reading a plotfile

