# flapping-wing-validation (delta)

## MODIFIED Requirements

### Requirement: Flapping-wing plausibility gate on ib_force (lab-frame; frame/tier deferred)

The flapping-wing validation SHALL grade an **order-of-magnitude plausibility gate** on the
accumulated immersed-boundary force `ib_force` (`Fx/Fy/Fz`) **alone** — the added-mass term SHALL NOT
be required for the gate to pass (it is reported separately; see the added-mass requirement). Over a
pinned, documented steady window, the lab-frame magnitudes `|CF_x|` and `|CF_z|` (van Veen convention)
SHALL each lie within the van Veen literature band `[0.5, 1.5]` **without any correction factor**, and
the **rotation-invariant** in-plane resultant `|CF| = sqrt(CF_x² + CF_z²)` SHALL be reported as the
frame-honest companion quantity. Because the committed lab-frame forces come from a run whose stroke is
`Rz(φ)` about the span axis (issue #1), the per-component gate SHALL be documented as a **magnitude
plausibility check**, NOT a frame-faithful van Veen comparison — the per-component values are lab-frame
and do **not** correspond to van Veen's body-frame chord-wise/normal axes. The faithful **body-frame
per-component** comparison is **delivered by the axis-convention refactor** (see "Body-frame
(chord/normal) per-component van Veen comparison" below); only the **time-resolved** curve match
remains deferred to **T4**. The band SHALL NOT be loosened to make the gate pass.

#### Scenario: ib_force magnitudes fall in band without a fudge

- **Given** the wing `ib_force` (`Fx/Fy/Fz`) re-derived under the van Veen convention over the pinned steady window
- **When** the peak coefficients are taken
- **Then** `max|CF_x|` and `max|CF_z|` each lie in `[0.5, 1.5]` with no correction factor applied (added-mass not required), and the rotation-invariant `|CF| = sqrt(CF_x² + CF_z²)` is reported alongside

#### Scenario: Per-component lab values are flagged, with the body-frame comparison now delivered

- **Given** the regenerated wing `RESULTS.md`/figures
- **When** they are inspected
- **Then** they state the lab-frame gate is an **O(1) magnitude** plausibility check whose `CF_x/CF_z`
  are lab-frame (not van Veen's body-frame chord/normal), **and** they point to the delivered
  **body-frame per-component** van Veen comparison (this change), with only the **time-resolved** curve
  match (peak phase + curve RMSE vs van Veen fig 3–4) still deferred to **T4** — the docs do NOT claim
  time-resolved van Veen validation

#### Scenario: Steady window is pinned by a physical criterion and reproducible

- **Given** the single committed wingbeat of `forces.csv` (the committed copy of the IB-particle output), whose first steps carry an impulsive-start transient
- **When** the headline peak coefficients are evaluated
- **Then** the analysis pins the steady evaluation window by a **documented physical criterion** (e.g. excluding the impulsive-start transient, ≥ a stated fraction of a wingbeat after `t = 0`) expressed as a **named constant** — not chosen post-hoc to land in band — and the reported peaks are reproducible from the committed data for that window
- **And** with the pinned window the `CF_z` floor stays clear of `0.5` on `ib_force` alone (the margin is reported)

## ADDED Requirements

### Requirement: Body-frame (chord/normal) per-component van Veen comparison

The flapping-wing analysis SHALL decompose the lab-frame `ib_force` `(Fx,Fy,Fz)` into the
**instantaneous wing body frame** using the **analytic** rotation `R(t)` from the wing kinematics (the
same composition the solver applies), yielding chord-wise `CF_chord` and wing-normal `CF_normal` series
in van Veen's convention (`F = (F_x chord, F_z normal)`), normalized by the single-source
`compute_force_reference` (`F_ref = ½ρω²S_yy`; no correction factor). The rotation axes/order SHALL be
passed **explicitly** (no hard-coded streamwise axis) so the analysis layer cannot re-introduce a
#1-style mislabel. On the **new-convention re-run**, the analysis SHALL grade an **overall scalar
match** — the **peak** `|CF_chord|` and `|CF_normal|` within a **stated tolerance** of van Veen's
reported overall values (cycle-means SHALL be **reported alongside**, not graded — a coarse
single-wingbeat run has no converged mean) — with the test-pinned `VAN_VEEN_BAND` `[0.5,1.5]` as a
floor that SHALL NOT be loosened. Where van Veen's overall numeric targets are not yet sourced (CC-V2), the graded
criterion SHALL fall back to the band floor and the van-Veen gap SHALL be **reported, not reverse-fit**.
The body-frame decomposition of the **old committed run** SHALL be reported as a **contrast baseline**.

#### Scenario: Lab force rotates into chord/normal by the analytic R(t)

- **Given** a known analytic `R(t)` and a synthetic lab-frame force with a pure chord-directed component
- **When** the body-frame decomposition is computed
- **Then** `CF_chord = (Rᵀ·F)_x / F_ref` and `CF_normal = (Rᵀ·F)_z / F_ref` equal the hand-computed
  values, a pure chord-directed lab force yields `CF_normal ≈ 0` (and vice-versa), and the rotation
  axes/order were supplied explicitly (no hard-coded streamwise axis)

#### Scenario: Band floor is always graded and never loosened (live now)

- **Given** the body-frame `CF_chord`/`CF_normal` series over the pinned steady window
- **When** the floor gate is computed
- **Then** the **peak** `|CF_chord|`, `|CF_normal|` are graded against `[0.5,1.5]` read from
  the pinned `VAN_VEEN_BAND` (cycle-means reported, not graded), and a **widened band flips the verdict
  to fail** (guarded by a not-loosened test) — this gate is CI-gradeable before van Veen's overall
  numbers are sourced

#### Scenario: Overall scalar-match tolerance, gated on sourced targets (pending numbers)

- **Given** the body-frame series and van Veen's reported overall values pinned as the named constant
  `VAN_VEEN_CF_TARGETS` with tolerance `VAN_VEEN_MATCH_TOL`
- **When** the tolerance match is computed
- **Then** the **peak** `|CF_chord|`, `|CF_normal|` must fall within `VAN_VEEN_MATCH_TOL` of the
  targets (cycle-means reported, not graded); the grader is proven on synthetic fixtures to **pass
  within and fail outside** (both
  directions); and when `VAN_VEEN_CF_TARGETS is None` (not yet sourced, CC-V2) the verdict falls back to
  the band floor and the van-Veen gap is **reported, not reverse-fit**. Both `VAN_VEEN_CF_TARGETS` and
  `VAN_VEEN_MATCH_TOL` are named, test-guarded constants (a loosened tolerance fails a not-loosened test)

#### Scenario: Old-run body-frame decomposition reported as contrast

- **Given** the old committed `forces.csv` (stroke-∥-span motion) run through the same body-frame decomposition
- **When** its `CF_chord`/`CF_normal` are reported
- **Then** they appear as a labelled **contrast baseline** demonstrating the old motion's per-component
  values differ from van Veen — evidence the refactor is a motion correction, not a relabel

### Requirement: Stroke motion reproduces van Veen's translational sweep

The change SHALL verify — at the **kinematic** level, cluster-free — that the refactored wing kinematics
produce a **stroke that sweeps the span**: evaluating the new `R(t)` on a span-tip marker, its
horizontal (in-stroke-plane) excursion SHALL trace a `±φ_amp` arc that is **non-zero at the α=0
midstroke**, whereas the old composition (stroke `Rz(φ)` about the span) gives a `sin α` excursion that
is `≈0` at midstroke. This encodes that the refactor is a **motion correction** reproducing van Veen's
translational sweep, not merely an axis relabel.

#### Scenario: New stroke sweeps the span-tip; old one does not

- **Given** the new and old analytic rotation compositions evaluated on a span-tip marker over a wingbeat
- **When** the span-tip's horizontal excursion is measured at the α=0 midstroke
- **Then** the **new** composition gives a non-zero excursion consistent with a `±φ_amp` stroke arc,
  the **old** composition gives `≈0` (a `sin α` excursion), and the test asserts the new stroke sweeps
  the span while the old one does not
