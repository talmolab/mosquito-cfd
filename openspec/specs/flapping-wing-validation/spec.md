# flapping-wing-validation Specification

## Purpose
TBD - created by archiving change standardize-force-normalization. Update Purpose after archive.
## Requirements
### Requirement: Van Veen-faithful force-coefficient convention, no correction factor

The flapping-wing analysis SHALL report force coefficients in the **van Veen (2022) convention**
(`F_ref = ½ρ·ω²·S_yy`) obtained through the single-source `compute_force_reference` helper (CC-3),
with the radius of gyration derived from the committed wing geometry. It SHALL NOT apply any post-hoc
correction factor (no "~2.4×"/"~2.64×" multiplier) anywhere in code or documentation; the in-band
result SHALL be achieved by normalization alone, re-derived from committed raw forces (no CFD re-run).

#### Scenario: Convention obtained from the single source, no inline re-derivation

- **Given** the wing analysis / `examples/flapping_wing/generate_all_figures.py`
- **When** it computes the force reference
- **Then** it calls `compute_force_reference` (no inline `F_ref` formula) and reports `f_ref ≈ 200.27` at the validated point

#### Scenario: No correction factor is applied

- **Given** the wing force coefficients and the regenerated `RESULTS.md`/figures
- **When** they are inspected
- **Then** no constant `≈ 2.4` or `≈ 2.64` (nor any other ad-hoc multiplier) multiplies `CF` in code, tests, or docs, and no "diffused-IB force is ~2.4× low" claim remains

### Requirement: Flapping-wing plausibility gate on ib_force (lab-frame; frame/tier deferred)

The flapping-wing validation SHALL grade an **order-of-magnitude plausibility gate** on the
accumulated immersed-boundary force `ib_force` (`Fx/Fy/Fz`) **alone** — the added-mass term SHALL NOT
be required for the gate to pass (it is reported separately; see the added-mass requirement). Over a
pinned, documented steady window, the lab-frame magnitudes `|CF_x|` and `|CF_z|` (van Veen convention)
SHALL each lie within the van Veen literature band `[0.5, 1.5]` **without any correction factor**, and
the **rotation-invariant** in-plane resultant `|CF| = sqrt(CF_x² + CF_z²)` SHALL be reported as the
frame-honest companion quantity. Because the committed forces are **lab-frame** and the repo's axis
convention is non-standard (issue #1, stroke `Rz(φ)` about the span axis; at the α=45° midstroke
lab ≠ body), the per-component gate SHALL be documented as a **magnitude plausibility check**, NOT a
frame-faithful van Veen comparison — the per-component values are lab-frame and do **not** correspond
to van Veen's body-frame chord-wise/normal axes. The faithful body-frame per-component comparison and
the **time-resolved** curve match SHALL be explicitly deferred to **T2a (#1)** and **T4**. The band
SHALL NOT be loosened to make the gate pass.

#### Scenario: ib_force magnitudes fall in band without a fudge

- **Given** the wing `ib_force` (`Fx/Fy/Fz`) re-derived under the van Veen convention over the pinned steady window
- **When** the peak coefficients are taken
- **Then** `max|CF_x|` and `max|CF_z|` each lie in `[0.5, 1.5]` with no correction factor applied (added-mass not required), and the rotation-invariant `|CF| = sqrt(CF_x² + CF_z²)` is reported alongside

#### Scenario: Per-component values are flagged as lab-frame, not van Veen body axes

- **Given** the regenerated wing `RESULTS.md`/figures
- **When** they are inspected
- **Then** they state the gate is a **lab-frame O(1) magnitude** plausibility check, that the lab `CF_x/CF_z` are not van Veen's body-frame chord-wise/normal components, and that faithful body-frame per-component + time-resolved van Veen validation are deferred to T2a (#1) / T4 — the docs do NOT claim frame-faithful or time-resolved van Veen validation

#### Scenario: Steady window is pinned by a physical criterion and reproducible

- **Given** the single committed wingbeat of `forces.csv` (the committed copy of the IB-particle output), whose first steps carry an impulsive-start transient
- **When** the headline peak coefficients are evaluated
- **Then** the analysis pins the steady evaluation window by a **documented physical criterion** (e.g. excluding the impulsive-start transient, ≥ a stated fraction of a wingbeat after `t = 0`) expressed as a **named constant** — not chosen post-hoc to land in band — and the reported peaks are reproducible from the committed data for that window
- **And** with the pinned window the `CF_z` floor stays clear of `0.5` on `ib_force` alone (the margin is reported)

### Requirement: Added-mass decomposition reported separately (not graded by the gate)

The wing analysis SHALL report the immersed-boundary **added-mass** term (derived from the `SumU*`
columns of the IB-particle output) as a **separate decomposition** alongside `ib_force`, NOT folded
into the coefficient the plausibility gate grades. The `SumU*`→force relationship SHALL be taken from
the IAMReX `WriteIBForceAndMoment` definition (resolved from the solver source before any combination),
documented in the analysis with the exact column algebra, and a test SHALL assert the added-mass
expression matches that definition on a known row of the committed `forces.csv` (kept IB-particle output) — locking the
formula to the **source**, not to the band. The analysis MAY additionally report the net 6-DOF
hydrodynamic coefficient `F_hydro = ρ_f·(SumU − ib_force)` (the solver's momentum balance), clearly
labelled, but the gate verdict SHALL rest on `ib_force` alone.

#### Scenario: Added-mass formula is locked to the IAMReX source, not the band

- **Given** the committed 29-column `forces.csv` (with `Fx/Fy/Fz` and `SumU{x,y,z}`) and the documented `WriteIBForceAndMoment` definition
- **When** the added-mass term is computed
- **Then** it equals the documented expression (whether an already-force-like accumulation or a momentum sum requiring `d/dt`, as resolved from the solver source) evaluated on a known row, with the formula citation in the test docstring — and the test does **not** select the expression that makes the gate pass

#### Scenario: Decomposition is the 6-DOF momentum balance, self-consistent

- **Given** the `ib_force`, added-mass (`ρ_f·SumU`), and net hydrodynamic coefficients
- **When** they are computed over the pinned steady window
- **Then** the net hydrodynamic force is the **6-DOF momentum balance** `F_hydro = ρ_f·(SumU − ib_force)` per `WriteIBForceAndMoment` (i.e. `CF_hydro = CF_added − ρ_f·CF_ib`, within floating tolerance — **not** a naive `ib + added` sum), and the added-mass contribution is reported as a fraction of `ib_force` with the fraction bounded `0 < fraction < 1` and its actual value snapshotted (not hard-coded to "~15%/~33%"; the committed corpus gives ~10% stroke / ~40% lift)

> **Why 6-DOF balance, not `ib + added` (implementation deviation):** the proposal's scenario assumed `combined = ib_only + added_mass_only`. Reading the IAMReX source (`DiffusedIB.cpp`) showed the `SumU` columns are already `(sum_u_new − sum_u_old)/dt` and the particle equation of motion combines them as `ρ_f·(SumU − ib_force)`. The gate is unaffected (it is graded on `ib_force` alone); only the *reported* decomposition formula changed to match the solver.

#### Scenario: Added-mass does not decide the gate

- **Given** the plausibility-gate verdict
- **When** it is computed
- **Then** it is a function of `ib_force` alone and is unchanged whether or not the added-mass term is included — an unverified or out-of-band added-mass term cannot flip the gate

