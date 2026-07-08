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

### Requirement: Axis-general control-volume force vector with an explicit freestream axis

The control-volume force core SHALL accept the streamwise/freestream axis **explicitly** and return the
full `(Fx, Fy, Fz)` momentum-flux force vector, rather than assuming the streamwise axis is `+x`. The
existing sphere entry point (`sphere_cv_drag_cd` / `cd_from_drag`) SHALL retain its current `+x`-default
behavior and keys (backward compatible), delegating to the generalized core. This exists so the wing
under the new convention — whose relevant force axis differs from the sphere's, and which has no single
freestream — can be analyzed without re-introducing a #1-style axis mislabel in the analysis layer.

#### Scenario: Explicit axis reproduces the x-only answer

- **GIVEN** a synthetic Eulerian box and the generalized core invoked with streamwise axis `= +x`
- **WHEN** the control-volume force is computed
- **THEN** the returned `Fx` equals the current `sphere_cv_drag_cd` drag for that box to round-off, and
  the full `(Fx,Fy,Fz)` vector is returned (backward-compatible for the sphere entry point)

#### Scenario: A non-x streamwise axis is honored

- **GIVEN** the same synthetic box but the streamwise axis supplied as `+y` (or `+z`)
- **WHEN** the control-volume force is computed
- **THEN** the momentum balance is taken across planes normal to the supplied axis and the returned
  force vector equals a hand-rolled balance across planes normal to that axis — the analysis never
  hard-codes `+x`

#### Scenario: A malformed streamwise axis raises

- **GIVEN** a streamwise axis that is a zero vector, a non-unit vector, or not a 3-vector
- **WHEN** the generalized core is invoked
- **THEN** a clear error is raised (matching the existing "Non-finite field raises" robustness bar),
  rather than a silently mis-projected or NaN force vector

### Requirement: Rotation-equivariance invariance guard (orientation/labeling only)

The field-based force extractor SHALL be **rotation-equivariant**: for a rotation `Q` that
rotates/permutes the grid axes, the extracted force satisfies `F(Q·field) = Q·F(field)` to
floating-point round-off. This property SHALL be proven as a **cluster-free** test on synthetic fields
(and, where a plotfile is available, on the committed field rotated in memory) — the pure-rotation
control pair. It is the invariance instrument for the axis-convention change (**CC-V4: orientation and
labeling only**): it validates that the relabel/extraction is correct **without** comparing forces
across two physically different runs (never new-extractor-new-geom vs old-extractor-old-geom), and it
does **not** touch force-magnitude reconstruction (T1b/#36).

#### Scenario: Extractor is equivariant under a grid rotation

- **GIVEN** a synthetic Eulerian field whose force vector has **all three components non-zero** and an
  **off-diagonal** rotation `Q` (e.g. `(x,y,z)→(y,−x,z)`, not a pure axis-relabel that could cancel a
  latent sign error)
- **WHEN** the force is extracted from the field and, separately, from `Q·field` with the axis mapping rotated by `Q`
- **THEN** `F(Q·field)` equals `Q·F(field)` to round-off, confirming the extractor is a correct
  relabeling under rotation (a dropped or swapped component would be detectable)

#### Scenario: The guard does not compare across geometries

- **GIVEN** the invariance test
- **WHEN** it is run
- **THEN** both sides use the **same** extractor on the **same** physical field (one rotated), never a
  different extractor on a different geometry — so the guard measures labeling correctness only, kept
  strictly separate from the magnitude fixes (CC-V4)

### Requirement: Confinement-corrected sphere Cd literature grade (H1′)

The benchmarks package SHALL grade the control-volume sphere Cd against the literature point
**Cd = 1.087** (Johnson & Patel 1999) by correcting for the **transverse-array confinement offset** whose
provenance (pitch 10 D, 5 D upstream; estimated **+3–6%** above the isolated value) is already stated by
the existing "Literature validation classifies the extraction-vs-field hypothesis" requirement — this
requirement **sharpens** that classification into a graded literature verdict and does **not** restate or
re-own the offset provenance. Given a confined control-volume Cd (a single grid or the
Richardson-extrapolated value) and the offset band, the grader SHALL compute the **isolated-equivalent**
Cd bracket by **dividing** the confined Cd by `(1 + offset)` — i.e. `cd_confined / (1 + [0.03, 0.06])` —
and classify the outcome **H1′** (extraction resolved; residual explained by confinement) when that
bracket lies within a **pinned tolerance** of 1.087 (**±5%**, i.e. `[1.033, 1.141]`). The tolerance and the
offset band SHALL be **named constants**, stated up front and **not** loosened or fitted to make the grade
pass (CC-V2). The grader SHALL be **cluster-free** — it takes Cd *values* as inputs and does **not**
re-derive the extractor (CC-V4) — while a `requires_plotfile`-marked companion recomputes the Cd with
`extract_sphere_cd(method="cv")` on the committed `plt10000` where the plotfile root is available.

#### Scenario: Richardson-extrapolated Cd grades as H1′ within tolerance

- **GIVEN** the committed T1b Richardson-extrapolated control-volume Cd `1.131` and the stated
  confinement offset band `+3–6%`
- **WHEN** the confinement-corrected literature grade is computed
- **THEN** the isolated-equivalent bracket is `cd/(1+[0.03,0.06]) = [1.067, 1.098]`, that bracket lies
  within `±5%` of 1.087, and the verdict is **H1′** — computed without reading any plotfile or cluster path

#### Scenario: Tolerance and offset band are pinned and not loosened

- **GIVEN** the literature target `1.087`, the pinned tolerance `±5%`, and the pinned offset band `+3–6%`
  as named constants
- **WHEN** a test inspects them
- **THEN** widening the tolerance or the offset band to admit an out-of-range confined Cd **fails** a
  not-loosened guard test, and a confined Cd whose isolated-equivalent bracket falls outside `[1.033, 1.141]`
  is graded **not H1′** (the grader can fail, not only pass)

#### Scenario: Tolerance-edge boundary case is decided deterministically

- **GIVEN** a confined Cd whose isolated-equivalent bracket lands **exactly at** a tolerance edge (e.g. an
  endpoint equal to `1.141` or `1.033`)
- **WHEN** the grade is computed
- **THEN** the inclusive/exclusive edge behaviour is deterministic and documented (the boundary is decided
  one way, not left to floating-point luck), so "within ±5%" has a single unambiguous meaning

#### Scenario: Companion re-grade verifies CV extraction traceability (verdict stays on Richardson)

- **GIVEN** the committed sphere `plt10000` (medium grid) and `MOSQUITO_CFD_PLOTFILE_ROOT` set
- **WHEN** the `requires_plotfile` companion recomputes the control-volume Cd
- **THEN** it calls `extract_sphere_cd(method="cv", x_inlet=2.0, x_outlet=8.0)` (**not** the default
  `method="marker"`, which returns the known-wrong ~0.45), and the returned `cd` matches
  `sphere_cv_drag_cd(...)["cd"]` (≈1.18) — confirming the extractor reproduces the pinned per-grid CV
  number (traceability; the marker/CV confusion is guarded)
- **AND** the H1′ **verdict** is graded on the **Richardson-extrapolated** value `1.131` (which requires
  **both** grids), **not** on the single medium value: the medium `1.18` alone yields
  `1.18/(1+[0.03,0.06]) = [1.113, 1.146]`, whose upper edge exceeds the tolerance `1.141` and so grades
  **not H1′** — the companion therefore verifies *extraction*, while the *literature verdict* rests on the
  Richardson value from the cluster-free grade (a single grid cannot reproduce a two-grid extrapolation)

#### Scenario: Off-cluster run auto-skips the plotfile companion but still grades the pinned numbers

- **GIVEN** no `MOSQUITO_CFD_PLOTFILE_ROOT` (CI / off-cluster)
- **WHEN** the sphere T2b tests run
- **THEN** the `requires_plotfile` companion **auto-skips**, while the cluster-free H1′ grade on the pinned
  Richardson value 1.131 still runs and passes — the literature verdict is CI-gradeable without cluster data

### Requirement: Committed synthetic plotfile gives the yt Eulerian-box adapter cluster-free CI coverage

The test suite SHALL commit a **tiny synthetic single-level AMReX/boxlib plotfile** under `tests/fixtures/`
carrying the **eight components the real wing plotfiles write** (`x/y/z_velocity`, `density`, `tracer`,
`gradpx/gradpy/gradpz`) — so it exercises the same Header-parse path as a real plotfile — of which
`extract_eulerian_box` reads the six it requires; and a CI test SHALL read it through the yt Eulerian-box
adapter `extract_eulerian_box` so the yt-read path is covered **cluster-free**. `extract_eulerian_box` reads
an AMReX plotfile via `yt.load` + `covering_grid(level=0)` + `('boxlib', <name>)` field-tuple access + FP64
unwrap + `max_level == 0` assertion; prior to this change that actual yt read was exercised **only** by
`requires_plotfile`-marked tests that auto-skip in CI (the real plotfiles live on the cluster Z: drive), so a
regression in the yt-reading layer would not be caught by CI. The fixture SHALL be authored by a committed
deterministic generator (explicit `<f8` byte order; FAB file `Cell_D_00000`) and protected by a
`.gitattributes` **binary** rule (the repo's `core.autocrlf = true` + `* text=auto` would otherwise
CRLF-corrupt the binary FAB), and its velocity field SHALL be analytic (solid-body rotation) so the same
fixture doubles as the LEV wiring's known-answer CI check (`‖ω‖ = 2Ω`, `Q = Ω²`).

#### Scenario: The committed fixture exercises the yt read path in CI

- **Given** the committed synthetic single-level boxlib plotfile fixture and **no** `MOSQUITO_CFD_PLOTFILE_ROOT`
  (CI / off-cluster)
- **When** `extract_eulerian_box` reads it
- **Then** the yt read succeeds cluster-free — `max_level == 0` passes, all six `('boxlib', …)` fields are
  found, and every field array is returned as **bare FP64 numpy** (`dtype == np.float64`, asserted so the
  fixture proves the FP64 read path rather than tripping the adapter's fp32-build guard) indexed
  `[ix, iy, iz]` with the correct per-axis `dx` — so a regression in the field-tuple access, covering-grid
  slice, FP64 unwrap, or level assertion is caught in CI without a cluster (closing the #33 coverage gap)

