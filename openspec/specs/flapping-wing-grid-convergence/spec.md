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
They SHALL be verified against **known analytic** answers on synthetic fields (T3a, cluster-free); the yt
plotfile→field extraction and the actual "LEV present at medium, weak/absent at coarse" call are **deferred
to T3b** (no committed new-convention plotfile exists in-repo).

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

### Requirement: Medium-run provenance and reproducibility (forward contract for T3b)

The future **T3b** operator medium run's provenance SHALL be captured via the existing
`capture_run_metadata` (Docker image digest, IAMReX commit `f93dc794`, inputs hash of
`inputs.3d.convergence_medium`, git SHA, hardware, timing) under the **same `:fp64` pin** (grid refinement
needs no new solver features), and the T3b RESULTS convergence numbers SHALL be recomputable from committed
data via the T2b reproducibility-guard pattern. This is a **forward contract** on that future run — T3a
itself introduces no sim run, Docker change, or pin change. T3a's grader and LEV math SHALL be unit-tested
cluster-free against the committed coarse run + synthetic fixtures (no cluster).

#### Scenario: Same pin, provenance via the existing helper (T3b)

- **Given** the T3b medium run (operator-run A40)
- **When** its provenance is recorded
- **Then** it uses `capture_run_metadata` with the `:fp64 @ f93dc794` image (no new pin), captures the
  `inputs.3d.convergence_medium` hash, and the reported convergence numbers recompute from the committed
  coarse + medium CSVs — while T3a itself introduces no sim run, Docker, or pin change

