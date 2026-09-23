# Wing coordinate convention (van Veen 2022 / Bomphrey 2017)

**This page is the single canonical narrative source for the wing axis convention.** Other locations
(the `WingKinematics.H` docstring, `examples/flapping_wing/RESULTS.md`, the figure scripts, the Python
kinematics mirror) **cross-reference this page** rather than restating the axis assignments, so the
copies cannot drift (Tier T2a; the `coordinate-convention` DRY requirement).

Adopted in Tier **T2a** (`refactor-wing-axis-convention`, issue #1) to match the insect-biomechanics
literature the project validates against — **van Veen et al. (2022)**, *J. Fluid Mech.* **936**, A3
([doi:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31), open access), and **Bomphrey et al.
(2017)** fig 1a, *Nature* **544**, 92.

## Axes (wing reference frame)

Right-handed, origin at the wing hinge. Sourced verbatim from van Veen 2022 §2.4 ("Reference
frames"), which defines the wing reference frame in one sentence — origin and axes together:

> "The aerodynamic forces on the wings are expressed in the wing reference frame, which is a
> right-handed coordinate frame with **the origin at the wing hinge location**, the x-axis parallel
> to the wing surface pointing towards the trailing edge, the y-axis parallel to the surface
> pointing towards the wing tip and the z-axis perpendicular to the wing surface"

The same section places the *world* frame's origin at the wing root: "a right-handed world reference
frame with its origin at the root of the wing".

| Axis | Physical role | van Veen (fig 1f) |
|------|---------------|-------------------|
| **x** | **chord-wise** — in the wing surface, toward the trailing edge | chord |
| **y** | **spanwise** — toward the wing tip (where the wing extends at rest) | span |
| **z** | **wing-normal** — perpendicular to the wing surface (vertical / lift axis at α=0) | normal |

```
        z (wing-normal / lift)
        |
        |      y (span, toward tip)
        |     /
        |    /
        |   /
        |  /
        | /
        +---------------- x (chord, toward trailing edge)
      hinge (root)
```

## Kinematic angles and rotation order

The wing orientation is a ZYX Euler composition (van Veen §2.4: "first rotating around the z_world-axis
… with the stroke angle, and then … around its spanwise axis (y-axis of the wing reference frame) with
a wing-pitch angle"):

```
R(t) = Rz(φ) · Ry(α) · Rx(θ)        (body-frame point → lab frame)
```

| Angle | Rotation axis | Meaning | van Veen kinematics |
|-------|---------------|---------|---------------------|
| **φ** stroke | lab vertical **z** (⊥ span) | horizontal sweep — the span-tip traces a ±φ_amp arc | `φ(t) = φ_amp·sin(ωt)` |
| **α** pitch (angle of attack) | span **y** | wing-pitch about its own span | `α(t) = α_amp·cos(ωt)` (90° lead) |
| **θ** deviation | chord **x** | out-of-stroke-plane, usually 0 | `θ(t) = θ_amp·sin(2ωt)` |

> **Notation note.** van Veen labels the stroke angle `γ` and the pitch angle `φ`; this repository uses
> `φ` (stroke) and `α` (pitch). The *composition* is identical — only the letters differ. Do not
> conflate them.

Because stroke `Rz(φ)` is about the vertical **z** and the span is along **y** (perpendicular to it),
the span-tip sweeps a horizontal arc with the stroke — van Veen's translational sweep. (Before T2a the
span ran along z and the stroke `Rz(φ)` was about that same span axis, so the span-tip barely moved —
issue #1.) The Python mirror of this rotation is
`mosquito_cfd.benchmarks.wing_kinematics.rotation_matrix` (the single code source of `R(t)`).

## Forces

Following van Veen (who "ignore[s] spanwise aerodynamic forces"), aerodynamic forces are reported in the
**wing body frame** decomposed into the **chord-wise** and **wing-normal** components:

```
F = (F_x chord-wise, F_z wing-normal)          spanwise F_y is intentionally dropped
```

Coefficients use the van Veen (2022, eq 1.1) normalization — the stroke rate at the **radius of
gyration** and the spanwise second moment of area:

```
F_ref = ½·ρ·ω²·S_yy,        S_yy = ∫₀ᴿ c(y)·y² dy
```

computed by the single-source `mosquito_cfd.force_surrogate.compute_force_reference` (see also
[`docs/force_surrogate`](force_surrogate/) and the `standardize-force-normalization` change). The
body-frame per-component comparison against van Veen's fitted coefficients is delivered by
`mosquito_cfd.benchmarks.flapping_wing.reconstruct_wing_body_forces` /
`body_frame_overall_match`; the per-component decomposition against van Veen's quasi-steady model
(translational + added-mass + Wagner; Fig 4 polars / the time-resolved mosquito curves are Fig 13) is
delivered by `decompose_wing_force` (Tier T4 — normal peak magnitude graded, phase/RMSE reported).

## Moments

**Reference point: the deck's declared pivot** (`particle_inputs.hinge_{x,y,z}`), i.e. the wing
hinge. Derived moment coefficients `CF_mx/CF_my/CF_mz` are taken about that point.

**Frame: lab, not wing.** Unlike the forces above — which are reported in the wing body frame —
moments are reported as **lab-frame components about the hinge origin**. Only the origin is the
hinge; the axes are not rotated. A wing-frame (body-frame) moment would additionally require
rotating by `R(t)ᵀ`, which this repository deliberately does not do (see issue #1 on the axis
convention). Do not read `CF_my` as a biomechanical pitching moment.

> **The axis table above is the rest-pose-aligned frame.** Lab and wing axes coincide only at
> `φ = α = θ = 0`; under a stroke rotation the wing's instantaneous axes leave the lab axes. So this
> page carries body-frame *forces* and lab-frame *moments* by design, not by oversight.

**Raw vs derived.** The `Mx/My/Mz` columns in `dataset.parquet` are the solver's as-written values,
taken about the immersed-boundary particle's **own origin** (IAMReX forms `(r − kernel.location) × f`
per marker and writes that origin into the CSV's `X,Y,Z` columns). Only the derived `CF_m*`
coefficients are referenced to the hinge, via the parallel-axis shift

```
M_hinge = M_origin + (r_origin − r_hinge) × F
```

applied at extraction by `mosquito_cfd.force_surrogate.shift_moment_reference`. Keeping the raw
columns unshifted preserves the audit trail back to solver output and makes the correction
re-derivable from the committed parquet alone.

**Why the hinge.** For a single-wing prescribed-motion run the hinge moment *is* the actuation
torque. It is also van Veen's frame: §2.4 defines the wing reference frame as "a right-handed
coordinate frame with **the origin at the wing hinge location**", and the world frame as "a
right-handed world reference frame with its **origin at the root of the wing**" — so both of that
paper's frames are rooted at the wing, neither at mid-span. The origin and the axis directions come
from the same sentence, quoted in full under [Axes](#axes-wing-reference-frame) above.

**"Root" and "hinge": whether van Veen means one point or two is unresolved.** §2.4 names the world
frame's origin "the root of the wing" and the wing frame's origin "the wing hinge location" — two
different phrases, in consecutive paragraphs, for two frames' origins. The text does not state
whether they denote the same point, and **figure 1f**, which both sentences cite, is what would
settle it.

Do **not** infer coincidence from the Euler-angle construction in that section. Euler angles
describe *orientation*; an orientation description carries no origin information, so the absence of
a translation term there is a property of the formalism, not evidence about the origins.

In our geometry they are certainly two points: the deck declares `hinge_y = 0.5` while the committed
mesh's blade starts at `y = 0.525` (half-span 1.4750 about the centre at `y = 2.0`), so our pivot
sits 0.025 **inboard** of our own wing surface — physically reasonable for a joint proximal to the
blade it drives. Hence "the deck's declared pivot" below: the wording tracks our geometry, and does
not depend on how van Veen resolves the question.

**Consequence for the issue-#1 body-frame work.** Converting a lab-frame moment into van Veen's wing
frame is a pure rotation by `R(t)ᵀ` **only if** his two frames share an origin. If they do not, the
conversion needs a parallel-axis shift as well — the same class of error this page exists to prevent.
Resolve it from figure 1f before attempting that conversion; nothing in this repository currently
establishes it either way.

**A deferred alternative.** A future body-in-the-loop model — one that integrates the insect's
own dynamics rather than prescribing wing motion — would want moments about the **centre of mass**,
not the hinge. That is a deliberate deferral, recorded so the next reader finds a decision rather
than an inherited default.

**Precision note.** The declared pivot is not exactly the wing's geometric root: `hinge_y = 0.5`
gives an arm of 1.5, while the committed geometry's own half-span is 1.475 (root at `y = 0.525`).
`geometry_guard.assert_hinge_at_span_root` reconciles the two only to `tol = 0.1`. The shift arm is
therefore ~1.7% larger than the geometric root arm — say "the deck's declared pivot", not "the wing
root".

## Simulation deck mapping

`examples/flapping_wing/inputs.3d.validation` places the wing in this convention: **x = chord**
(pressure-outflow, streamwise), **y = span** (periodic — an infinite-span / spanwise model), **z =
vertical/lift** (pressure-outflow), with the domain widened in z for lift clearance and the hinge on the
span-along-y geometry. See that deck and `RESULTS.md` for the concrete values.
