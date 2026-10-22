# coordinate-convention Specification

## Purpose
TBD - created by archiving change refactor-wing-axis-convention. Update Purpose after archive.
## Requirements
### Requirement: Project-wide axis convention matches van Veen 2022, documented atomically

The project SHALL adopt a single wing coordinate convention matching **van Veen et al. (2022, *JFM*
936:A3, §1.2 / eq 1.1–1.2 / fig 1f)**: **x = chord-wise, y = spanwise, z = wing-normal (vertical /
lift)**; stroke angle `φ` about the world vertical (z); angle of attack `α` about the spanwise (y)
axis; deviation `θ` out of the stroke plane. Forces are reported in the **wing (body) frame** as
`F = (F_x chord-wise, F_z wing-normal)` (spanwise ignored), normalized by `F_ref = ½ρω²S_yy` with
`S_yy = ∫₀ᴿ c(y)y²dy`. This convention SHALL be stated in a `docs/coordinate-convention.md` page with a
labeled diagram and verbatim citations (van Veen fig 1f + eq 1.1–1.2; Bomphrey 2017 fig 1a). The
convention document, the `WingKinematics.H` docstring, and the `examples/flapping_wing/RESULTS.md`
frame-description SHALL land in the **same change** as the geometry/solver re-orientation — **no interim
commit may carry new-convention geometry with old-convention documentation**.

#### Scenario: Convention page states the van-Veen-faithful axes and normalization

- **Given** `docs/coordinate-convention.md`
- **When** it is read
- **Then** it states x=chord-wise, y=spanwise, z=wing-normal/vertical, `φ` stroke about z, `α` pitch
  about the span (y), `θ` deviation; the body-frame decomposition `F=(F_x chord, F_z normal)`; and
  `F_ref=½ρω²S_yy`, `S_yy=∫c(y)y²dy` — each cited to van Veen 2022 (fig 1f / eq 1.1–1.2) and Bomphrey
  2017 fig 1a

#### Scenario: Spanwise force component is intentionally dropped, not silently lost

- **Given** the body-frame decomposition following van Veen (who "ignores spanwise" forces, so
  `F = (F_x chord, F_z normal)`)
- **When** the chord/normal coefficients are formed
- **Then** the spanwise component `F_y` is documented as **intentionally dropped** (optionally reported
  as a diagnostic), so its absence reads as a deliberate convention choice, not a bug

#### Scenario: Docs and figures co-land with the geometry change (atomicity — a pre-merge gate)

- **Given** the change's commit(s)
- **When** any commit introduces the new-convention `wing.vertex` / `inputs.3d.validation`
- **Then** that same commit (group) also carries `docs/coordinate-convention.md`, the updated
  `RESULTS.md` frame-description, **and the regenerated figures** (which hard-code the old span=z
  convention and are embedded in RESULTS — figures are docs) — no commit leaves new-convention geometry
  described by old-convention docs or figures
- **And** because this is a git-history property no unit test can assert, it SHALL be verified as a
  **pre-merge checklist gate**, not a `pytest` (the corresponding `WingKinematics.H` docstring lives in
  the separate fork and co-lands via the fork PR + pin bump)

### Requirement: Wing geometry, kinematics, and deck are expressed in the new convention

The flapping-wing geometry and kinematics SHALL be re-oriented to the new convention: `wing.vertex`
span along **y** (chord in x, wing flat in the x–y body plane), regenerated via `generate-wing-planform`
with a new **span-axis parameter** (the generator currently hard-codes span along z and cannot emit
span-along-y; the default SHALL preserve the current span-z behaviour), not hand-edited; `WingKinematics.H` composing rotation so **pitch `α` is about the span** and
**stroke `Rz(φ)` is about the lab vertical z, perpendicular to the span**; and
`inputs.3d.validation` using **infinite-span periodic** boundaries — pressure-outflow in x (chord) and z
(vertical/lift), **periodic in y (span)** — with the domain widened in z and the hinge coordinates
updated for the span-along-y geometry.

#### Scenario: Regenerated geometry has span along y

- **Given** the regenerated `examples/flapping_wing/wing.vertex`
- **When** its marker extents are measured
- **Then** the span (largest extent) runs along **y**, the chord runs along x, and the wing is flat in
  the x–y body plane (consistent with the hinge/root), matching the documented convention

#### Scenario: Deck uses infinite-span periodic boundaries

- **Given** the rewritten `examples/flapping_wing/inputs.3d.validation` (the committed deck is *already*
  periodic in y with a z wall and x outflow — the change is z-wall→outflow, not "z-wall→periodic")
- **When** its geometry/BC keys are inspected
- **Then** `geometry.is_periodic` is periodic in **y** only (retained, now coinciding with the span),
  `ns.lo_bc`/`ns.hi_bc` are pressure-outflow in x and **z** (z changed from wall → outflow), the domain
  is widened in z for lift clearance, and the hinge coordinates place the span along y — so the span-tip
  is no longer adjacent to a wall

### Requirement: Single canonical source per layer, cross-referenced (DRY)

The axis convention SHALL have **one canonical narrative source** — `docs/coordinate-convention.md` —
and one **canonical code source** for the analytic rotation `R(t)` (the Python kinematics mirror).
In-repo locations (the `WingKinematics.H` docstring, `RESULTS.md`, the figure scripts) SHALL
**cross-reference** the canonical sources rather than restate the axis assignments or re-implement the
rotation, so the copies cannot drift. (The out-of-repo memory note is not governed by this repo
requirement.)

#### Scenario: Convention prose is stated once and referenced

- **Given** `RESULTS.md`, the `WingKinematics.H` docstring, and the figure scripts
- **When** they need the axis convention
- **Then** they point to `docs/coordinate-convention.md` rather than restating the x/y/z axis
  assignments, so there is a single narrative source of truth

#### Scenario: The analytic rotation is imported, not re-implemented

- **Given** the body-frame decomposition (`benchmarks/flapping_wing.py`) and the figure scripts
- **When** they need the wing rotation `R(t)`
- **Then** both import the single Python kinematics-mirror function (the old duplicate
  `rotation_matrix` in `generate_all_figures.py` is removed), so there is one code source of `R(t)`
  guarded against C++ drift by the mirror-vs-`WingKinematics.H` golden-value test

### Requirement: The canonical convention page states the moment reference point

The canonical convention page SHALL state the **moment reference point** alongside the axis
assignments it already carries. That page is `docs/coordinate-convention.md`, the single canonical
narrative source for the wing convention, and the statement SHALL live in a `## Moments` section
sibling to the existing `## Forces` section. The omission of such a section is
what allowed the force-surrogate extractor to inherit the immersed-boundary particle's own origin
(the wing's mid-span point) as its moment origin, undetected, while this page already declared a
hinge origin.

The section SHALL state:

- that repository moments are **lab-frame components taken about the wing hinge**;
- that the axes are **not** rotated into the wing frame, so these are not van Veen wing-frame
  moments — that would additionally require rotating by `R(t)ᵀ`, a conversion that is deferred and
  not currently tracked (issue #1, which once covered it, is closed);
- that raw solver-written moment columns are about the solver's own particle origin, while derived
  moment **coefficients** are about the hinge;
- the centre-of-mass alternative appropriate to a future body-in-the-loop model, recorded as a
  deliberate deferral rather than left implicit.

Per the existing DRY requirement, in-repo locations SHALL **cross-reference** this section rather
than restate the reference point's justification or citation, so the copies cannot drift.

The hinge-origin statement SHALL carry a **verbatim** citation from van Veen et al. (2022) on the
same footing as the axis-direction quotation already on the page. Where a claim cannot be sourced
verbatim, it SHALL be narrowed to what the source supports rather than asserted unquoted.

#### Scenario: The canonical page documents the moment reference point

- **Given** `docs/coordinate-convention.md`
- **When** it is read
- **Then** it contains a `## Moments` section naming the wing hinge as the reference point, stating that the axes remain lab axes, and recording the centre-of-mass deferral

#### Scenario: The hinge origin is sourced verbatim

- **Given** the `## Moments` section's citation of van Veen et al. (2022)
- **When** it is checked against the paper
- **Then** the origin claim is supported by a verbatim quotation, as the axis-direction claim already is — and any part not so supported (for example a claim about the *world*-frame origin) is either quoted or removed rather than asserted

#### Scenario: Downstream statements cross-reference rather than restate

- **Given** the force-surrogate module documentation and the corpus READMEs
- **When** they refer to the moment reference point
- **Then** they name it and point at `docs/coordinate-convention.md`, without restating its justification or its van Veen citation

#### Scenario: Documentation does not assert a reference point the pipeline does not yet produce

- **Given** a commit in which the extractor still emits particle-origin moment coefficients — because the parallel-axis shift is delivered in a later increment — and the canonical page and module docstring already describe the hinge reference
- **When** either is read
- **Then** each SHALL carry an explicit pending-status marker naming the increment that applies the shift, so no reader can take the description for the current behaviour of the committed corpora
- **And** the marker SHALL be removed in the increment that wires the shift into extraction, so it cannot outlive the gap it describes

#### Scenario: A claim that rests on inference is labelled as inference

- **Given** a statement on the canonical page that is argued from the source rather than quoted from it — for example the identification of van Veen's world-frame "root" with his wing-frame "hinge"
- **When** it is read
- **Then** it is presented as an inference with its supporting argument, not as an established quotation
- **And** any downstream conclusion drawn from it — such as a lab-to-wing-frame moment conversion being a pure rotation with no parallel-axis shift — is marked conditional on that inference

