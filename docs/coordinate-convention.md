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
      hinge
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

Extraction applies this: `build_dataset` shifts the solver's moments to the deck's pivot before
normalizing, and both committed corpora were re-extracted to match (`fix-moment-reference-hinge`,
issue #108). CI reconciles them against their committed decks
(`tests/test_force_surrogate_scale_invariance.py`). Until that change, this page described a
hinge origin the pipeline did not implement, which is how #108 arose.

**Frame: lab, not wing.** Unlike the forces above — which are reported in the wing body frame —
moments are reported as **lab-frame components about the hinge origin**. Only the origin is the
hinge; the axes are not rotated. A wing-frame (body-frame) moment would additionally require
rotating by `R(t)ᵀ`; that conversion is deferred and not currently tracked (issue #1, which
delivered the axis convention, is closed). Do not read `CF_my` as a biomechanical pitching moment.

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

**"Root" and "hinge" are almost certainly one point in van Veen — an inference, not a quotation.**
§2.4 names the world frame's origin "the root of the wing" and the wing frame's origin "the wing
hinge location". The paper never states that these coincide. The supporting evidence is in **§2.2**,
not §2.4:

> "A single rigid wing with a span of approximately R = 3 mm and a thickness of τ = 18 μm was placed
> with **its root in the centre of a domain** with a size of 5 cm × 5 cm × 5 cm."

A single rigid plate, no body and no articulation, rooted at the domain centre — which §2.4 then
makes the world frame's origin. §2.5 adds that "the wing was not given an additional translational
motion", so the root stays at the domain centre throughout, and the stroke axis therefore passes
through it. The pitch rotation is about the wing's own spanwise axis through its root, so the two
rotation axes intersect at the root. With no joint in the model, that intersection is the only thing
"the wing hinge location" can denote.

That chain is sound but it is **reasoning, not a quoted statement** — figure 1f would settle it
directly, and it does not (see the caution below). Treat the identification as a well-supported
inference and anything downstream of it as conditional.

Two cautions for anyone re-checking this:

- **Figure 1f draws the two triads at different heights.** That is drafting — the world triad is
  offset down `z_world` so it does not collide with the wing triad, with the `z_world` line running
  up to the shared origin. Do not read the separation as a geometric claim.
- **Do not argue it from the Euler-angle construction either.** Euler angles describe *orientation*,
  and an orientation description carries no origin information, so the absence of a translation term
  there proves nothing in either direction.

Our geometry carries a gap van Veen's does not — where his root and hinge coincide, ours are 0.025
apart. See **Precision note** below for the numbers; it is why this page says "the deck's declared
pivot" rather than "the wing root".

**Consequence for any future wing-frame moment conversion (deferred, not currently tracked) —
conditional on the inference above.** *If* his two
frames share an origin, converting a lab-frame moment into van Veen's wing frame is a **pure
rotation** by `R(t)ᵀ`, with no parallel-axis shift on top. Should the identification turn out to be
wrong, that conversion additionally needs a translation, and omitting it would reintroduce exactly
the error class #108 exists to fix — so confirm it against figure 1f before relying on it. Our own
0.025 offset is a separate, smaller matter and is ours to account for either way.

**A deferred alternative.** A future body-in-the-loop model — one that integrates the insect's
own dynamics rather than prescribing wing motion — would want moments about the **centre of mass**,
not the hinge. That is a deliberate deferral, recorded so the next reader finds a decision rather
than an inherited default.

**Precision note.** The declared pivot is not exactly the wing's geometric root: `hinge_y = 0.5`
gives an arm of 1.5, while the committed geometry's own half-span is 1.475 (root at `y = 0.525`).
`geometry_guard.assert_hinge_at_span_root` reconciles the two only to `tol = 0.1`. The shift arm is
therefore ~1.7% larger than the geometric root arm — say "the deck's declared pivot", not "the wing
root".

## Force and moment sign

IAMReX's `ib_force` and `ib_moment` (the `Fx..Mz` columns of `IB_Particle_*.csv`) are the force
and moment the wing exerts **on the fluid**. Each marker's force `(U_wing − u*)/dt · dv` is added to
the fluid's forcing field, and `ib_force` is their sum.

Every derived wing coefficient is the **IB force and moment on the wing**, their negation by Newton's
third law. That covers:
- the lab-frame `CF_x..CF_z`;
- the hinge-referenced moment coefficients `CF_mx..CF_mz`;
- the flapping-wing lab-frame series;
- the body-frame `CF_chord`/`CF_normal`;
- the T4 CFD series.

The wing paths apply the negation only through `mosquito_cfd.force_surrogate.force_on_wing`, and
the raw columns keep the solver's values ([raw vs derived](#moments)). The paths not yet converted
are flagged by the pending notes below.

Pending #109: the committed corpus coefficients still carry the solver's on-fluid sign.

Pending #109: the flapping-wing series still carry the solver's on-fluid sign.

The flapping-wing note covers the lab-frame, body-frame and T4 CFD series alike.

No corpus coefficient includes the internal-fluid term `ρ_f·SumU`. The flapping-wing analysis
reports a 6-DOF series that does include it, separately, as a diagnostic. The solver's free-body
6-DOF balance would add the term, but the solver never evaluates that balance for the
prescribed-motion wing. For this
zero-thickness wing the term is the momentum change of fluid within about one grid cell of the
sheet, so it depends on the grid. Its physical status is an open follow-up question.

The sphere and heaving-ellipsoid analyses already report the force on the body.

**Evidence.** For a rigid wing turning about a fixed hinge, `M_hinge · Ω` is the power the IB
forcing delivers to the fluid. So the cumulative work from rest, `W(t) = ∫ M_hinge · Ω dt`, should
not go negative. This is an empirical check, not a theorem, because the domain has open outflow
boundaries.
- On the solver's moments, `W ≥ 0` at every row of all 57 committed runs: the 54 corpus
  configurations and the T2a, medium and fine validation CSVs.
- Its increment after `t = 0.05` is also non-negative.
- `W` is strictly positive after the first row of every run, so under the opposite sign `W` would go
  negative in every run. The check tells the two signs apart.

`tests/test_ib_force_sign_convention.py` pins this, along with two further checks: the raw force and
moment share one convention, and the coefficients satisfy the mirror inequality.

## Simulation deck mapping

`examples/flapping_wing/inputs.3d.validation` places the wing in this convention: **x = chord**
(pressure-outflow, streamwise), **y = span** (periodic — an infinite-span / spanwise model), **z =
vertical/lift** (pressure-outflow), with the domain widened in z for lift clearance and the hinge on the
span-along-y geometry. See that deck and `RESULTS.md` for the concrete values.
