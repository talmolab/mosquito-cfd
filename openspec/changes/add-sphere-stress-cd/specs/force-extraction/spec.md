# Force Extraction Specification

Field-based hydrodynamic force extraction from CFD plotfiles, independent of immersed-boundary marker
bookkeeping. Serves the `apex-benchmarks` FlowPastSphere acceptance criterion (Cd within ±5% of
literature) and the aerodynamics-validation roadmap (Tier T1b).

## ADDED Requirements

### Requirement: Control-volume drag from Eulerian fields

The benchmarks package SHALL compute the hydrodynamic drag force on a body from gridded Eulerian fields
(velocity components and pressure gradient) via a control-volume momentum balance over an axis-aligned
box enclosing the body, using `F_drag = −∮_{∂CV} [ ρ u(u·n) + p n − μ(∇u+∇uᵀ)·n ] dA` with outward
normals and the leading `−` applied once globally. The computation SHALL be FP64 end-to-end, SHALL NOT
use the immersed-boundary particle force fields, and SHALL return the full `(Fx,Fy,Fz)` force vector plus
a per-face and per-term breakdown of the integral. Each term of the integrand (momentum flux, pressure,
viscous) SHALL be validated independently by a known-answer test, with at least one test using `ρ ≠ 1` so
a `ν`-for-`μ` substitution cannot hide. The convenience identity "drag = streamwise = component x" is
specific to the +x-freestream sphere stage; reuse under a different convention SHALL pass the
streamwise/freestream axis explicitly rather than assuming component 0.

Because the H1/H2 question is a ~2.4× discrimination (not a sub-1% measurement), the decisive computation
SHALL be a **single-plane wake survey** (Stage 1); the full 6-face box and its `<1%` viscous/convergence/
plateau validation (Stage 2) are a confirmation, built only if the wake survey is band-edge ambiguous or
the published-rigor artifact is needed, and SHALL NOT gate the H1/H2 verdict.

#### Scenario: Single-plane wake survey is the decisive drag measure

- **GIVEN** a downstream survey plane in the resolved wake (outside the recirculation bubble) with the
  velocity and the in-plane pressure (reconstructed from `gradp`)
- **WHEN** the wake-survey drag `ρ ∬ u_x(U∞−u_x) dA + ∬ (p∞−p) dA` is evaluated on the plane
- **THEN** it returns the streamwise drag using only that plane's data (no 6-face box required), and this
  is the value classified for H1/H2

#### Scenario: Momentum-flux term matches a divergence-free wake closed form

- **GIVEN** a synthetic **pointwise divergence-free** velocity field (uniform freestream `U∞` plus a
  transverse-compact, x-uniform wake deficit; `v,w` close continuity; the test asserts `‖div u‖ ≈ 0`),
  zero pressure, no viscous contribution, **with the CV side faces placed in the freestream (`u=U∞`)**
- **WHEN** `control_volume_drag` is evaluated over the enclosing box
- **THEN** the returned streamwise force equals the wake-survey drag `ρ ∬_outlet u_x(U∞−u_x) dA`
  (= `ρπσ²A(2U∞−A)` for a Gaussian deficit) within 1% (box ≥5σ transversely, or compared against the
  truncated analytic integral over the actual box)
- **AND** the side faces carry nonzero throughflow at `U∞` that the integral accounts for
- **AND** the result is computed without reading any plotfile or cluster-mounted path

#### Scenario: Pressure term matches a known linear-pressure answer

- **GIVEN** a uniform velocity field (no momentum-flux variation, no viscous term) with a linear pressure
  `p = p0 + G·x`, supplied as the gradient field `∇p = (G,0,0)`
- **WHEN** `control_volume_drag` recovers pressure from `∇p` and evaluates the box integral
- **THEN** the returned streamwise force equals the closed-form pressure drag `−G·L_x·A_x` within 1%
- **AND** the recovered pressure reproduces `p0 + G·x` up to an additive constant

#### Scenario: Viscous term — per-face transpose check

- **GIVEN** a divergence-free field `u = (b·y, c·x, 0)` with zero pressure and `ρ ≠ 1` (a single linear
  shear `u_x=S·y` is insufficient: its net box viscous force is zero and its transpose partner
  `∂v/∂x = 0`, so `∇uᵀ` would go untested)
- **WHEN** `control_volume_drag` evaluates the full-tensor viscous term `μ(∇u+∇uᵀ)·n`
- **THEN** the per-face viscous contributions equal their closed-form values (the `+y`-face streamwise
  traction `μ(b+c)·A` is wrong if the transpose term `c` is dropped), using `μ = ρν` (not `ν`)

#### Scenario: Viscous term — nonzero net (Poiseuille)

- **GIVEN** a plane-Poiseuille field `u_x = U0 + (g/2μ) y(H−y)` with zero pressure and `ρ ≠ 1`
- **WHEN** `control_volume_drag` evaluates the viscous term over the box
- **THEN** the net streamwise viscous force equals the closed form `−g·H·L_x·L_z` within 1% (a nonzero
  net, which no linear field can provide)

#### Scenario: Convergence order is first-to-second order

- **GIVEN** a smooth combined analytic field (divergence-free velocity + linear pressure) with a known
  total drag
- **WHEN** the grid is refined and the error is measured at several resolutions
- **THEN** the fitted convergence order (slope of `log‖error‖` vs `log dx`) is between 1 and 2, ruling out
  a constant-offset false pass

#### Scenario: Reported Cd is taken from a CV-size plateau

- **GIVEN** the control-volume drag computed over a sweep of box face offsets on the analytic field
- **WHEN** the drag is examined as a function of CV size
- **THEN** the values form a plateau (spread `< 1%` across adjacent CV sizes) from which the reported value
  is taken; absence of a plateau on real data is recorded as evidence toward the H2 hypothesis

#### Scenario: Null field yields zero drag

- **GIVEN** a uniform divergence-free flow with zero pressure gradient and no body
- **WHEN** `control_volume_drag` is evaluated over any axis-aligned box
- **THEN** the returned force is zero within `1e-12 · ρ U∞² D²`

#### Scenario: Pressure-constant invariance

- **GIVEN** an Eulerian field and a pressure recovered from `∇p` up to an additive constant
- **WHEN** `control_volume_drag` is evaluated twice with pressures differing by an arbitrary constant
- **THEN** the two drag results are identical to within round-off (compared with `assert_allclose`, not
  `==`), confirming the closed-surface pressure term is invariant to the unknown reference constant

#### Scenario: NaN within the control volume raises

- **GIVEN** an Eulerian field containing a NaN cell inside the control-volume region
- **WHEN** `control_volume_drag` is evaluated
- **THEN** a clear error is raised rather than a silent NaN drag/Cd being returned

### Requirement: Plotfile Eulerian-box adapter

The package SHALL provide a yt-based adapter that reads the velocity components and pressure-gradient
fields over a specified axis-aligned region of an AMReX plotfile into FP64 numpy arrays suitable for the
control-volume core, isolating all plotfile/cluster I/O from the numerical core. It SHALL read the fields
by their `('boxlib', <name>)` tuple identifiers and assert all required fields are present.

#### Scenario: Single-level covering grid is exact and FP64

- **GIVEN** a FlowPastSphere plotfile with `amr.max_level = 0`
- **WHEN** the adapter reads a control-volume region via a level-0 covering grid using the
  `('boxlib', <name>)` field tuples
- **THEN** the returned arrays reproduce the stored cell-centered field values without interpolation
- **AND** the adapter asserts the dataset's maximum AMR level is 0 before returning
- **AND** the returned arrays are explicitly unwrapped from `YTArray` to bare numpy (`.to_ndarray()`), cast
  to and asserted as `float64` (yt may return `float32`), and the run is confirmed to be an fp64 build
- **AND** all six required fields (`x/y/z_velocity`, `gradpx/y/z`) are asserted present, failing loud on
  a name drift

#### Scenario: Read extent is padded for face-normal derivatives

- **GIVEN** a control-volume region whose viscous term needs `∂u/∂n` on the boundary faces
- **WHEN** the adapter reads the region
- **THEN** the read box is padded by at least one cell beyond the integration faces (≥2 for a centered
  second-order difference), and returns the real cell-center coordinates so the core forms face-straddling
  differences without a one-sided or out-of-range stencil

### Requirement: Field-based sphere Cd entry point

`extract_sphere_cd` SHALL support a `method="surface_stress"` option that returns the control-volume
drag coefficient as the reported Cd, while retaining the legacy IB-marker sum as a clearly labelled
diagnostic field (never the reported number). The return value SHALL remain backward compatible
(existing keys preserved; new keys added).

#### Scenario: Surface-stress method reports the field-based Cd

- **GIVEN** a sphere plotfile and `method="surface_stress"`
- **WHEN** `extract_sphere_cd` is called
- **THEN** the returned `cd` is the control-volume drag coefficient
- **AND** the legacy marker-sum value is still present under a diagnostic key (e.g.
  `cd_marker_lastpass`) labelled as the last-multidirect-sub-iteration diagnostic, not the result

#### Scenario: Default method preserves the existing contract

- **GIVEN** a caller that invokes `extract_sphere_cd` without specifying a method
- **WHEN** the function returns
- **THEN** all keys returned by the pre-change implementation (`cd`, `fx_sum`, `fy_sum`, `fz_sum`,
  `n_particles`, `time`, `validated`, `error_pct`, `literature_cd`) are still present with their
  established meanings

### Requirement: Literature validation classifies the extraction-vs-field hypothesis

The control-volume sphere Cd SHALL be computed on the committed `plt10000` for both the coarse and medium
grids and **classified** against the literature value (Cd = 1.087, Johnson & Patel 1999): within ±5% →
H1, reproducing the ≈0.45 deficit → H2. The classification SHALL be **recorded as an analysis artifact**,
not asserted as a CI gate. The validation is a `requires_plotfile`-marked, locally-run step that **skips
where the plotfile is unavailable** (CI is cluster-free), and on the H2 path the test SHALL be
`xfail`/relaxed so it is never a permanent local red. The verdict SHALL be **void unless the steadiness
gate passes** (see below).

#### Scenario: Steadiness gate must pass for the verdict to stand

- **GIVEN** the committed `plt09900` and `plt10000` for a grid
- **WHEN** the unsteady term `ρ(∫_CV u dV|_{10000} − ∫_CV u dV|_{09900})/dt` is computed
- **THEN** it SHALL be less than 5% of the computed |drag| for the H1/H2 verdict to be valid; otherwise
  the steady-state assumption fails and the verdict is recorded as **void**

#### Scenario: H1 — corrected Cd recovered with no re-run

- **GIVEN** the steadiness gate passes and the control-volume Cd is computed on both grids
- **WHEN** the Cd is classified against 1.087
- **THEN** if both grids fall within ±5% of 1.087, the result is recorded as **H1** (force-extraction
  bug resolved; analysis-only) and `extract_sphere_cd(method="surface_stress")` becomes the reported
  benchmark Cd

#### Scenario: H1′ — correct but setup-offset (confined periodic array)

- **GIVEN** the run is a transversely-periodic array (sphere at pitch 10 D, 5 D upstream), not an isolated
  sphere, with an estimated `+3%…+6%` confinement/blockage offset above the isolated literature value
- **WHEN** the field Cd lands in ~1.09–1.15 and its isolated-equivalent (dividing out `1+kβ`) is within
  ±5% of 1.087
- **THEN** the result is classified **H1′** (extraction and field both correct; the residual is the
  documented setup offset, not solver deficiency), the offset is recorded in `t1a-findings §8`/`RESULTS`,
  and the upper H1-acceptance edge is the β-justified ~+8% (the lower edge and H2 gate are unchanged)

#### Scenario: H2 — deficit is in the flow field, remediation deferred

- **GIVEN** the steadiness gate passes and the control-volume Cd is computed on both grids
- **WHEN** the Cd is classified against 1.087
- **THEN** if the result reproduces the ≈0.45 deficit (well outside ±5%), the result is recorded as
  **H2** (flow-field deficit), the literature test is `xfail`/relaxed, and the solver fix + re-run is
  documented as deferred post-submission, not performed in this change
