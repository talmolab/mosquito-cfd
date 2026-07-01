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

Right-handed, origin at the wing hinge (root). Sourced verbatim from van Veen 2022 §2.4 and the fig 2
caption ("the x-axis parallel to the wing surface pointing towards the trailing edge, the y-axis
parallel to the wing tip, and the z-axis perpendicular to the wing surface"):

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
`body_frame_overall_match`; the time-resolved curve match vs van Veen fig 3–4 is deferred to Tier T4.

## Simulation deck mapping

`examples/flapping_wing/inputs.3d.validation` places the wing in this convention: **x = chord**
(pressure-outflow, streamwise), **y = span** (periodic — an infinite-span / spanwise model), **z =
vertical/lift** (pressure-outflow), with the domain widened in z for lift clearance and the hinge on the
span-along-y geometry. See that deck and `RESULTS.md` for the concrete values.
