# coordinate-convention Specification

## Purpose
TBD - created by archiving change refactor-wing-axis-convention. Update Purpose after archive.
## Requirements
### Requirement: Project-wide axis convention matches van Veen 2022, documented atomically

The project SHALL adopt a single wing coordinate convention matching **van Veen et al. (2022, *JFM*
936:A3, §1.2 / eq 1.1–1.2 / fig 1f)**: **x = chord-wise, y = spanwise, z = wing-normal (vertical /
lift)**; stroke angle `φ` about the world vertical (z); pitch `α` about the spanwise (y)
axis (van Veen's angle of attack while the wing moves in the positive stroke direction); deviation `θ` out of the stroke plane.

Wing force coefficients are reported in two frames, and every statement of a frame SHALL name the
quantity it describes:

- the flapping-wing benchmark's `CF_chord`/`CF_normal`, and the diagnostics built from the same
  rotation (`cf_span`, the added-mass-subtracted diagnostic, the T4 decomposition), are **wing
  (body) frame** components, `F = (F_x chord-wise, F_z wing-normal)` (spanwise ignored), rotated by
  `R(t)ᵀ`;
- the force-surrogate corpus and surrogate `CF_x..CF_z`, the flapping-wing lab-frame series
  `cf_x_ib`/`cf_z_ib` from `reconstruct_wing_forces` (the `plausibility_gate` input), and the
  `CF_x..CF_z` that `fig_forces` plots, are **lab-frame components of the IB force on the wing**, not
  rotated.

Both are normalized by `F_ref = ½·ρ·ω_peak²·S_yy` with `S_yy = ∫₀ᴿ c(y)y²dy`, computed per
configuration. `ω_peak` is the peak stroke rate defined by
[Force Surrogate](../force-surrogate/spec.md) ("Single-source force normalization"; code:
`compute_force_reference`). It is not the flap angular frequency `ω = 2πf` of the kinematic
waveforms, so no `F_ref` expression on the page SHALL use a bare `ω`.

This convention SHALL be stated in a `docs/coordinate-convention.md` page with a
labeled diagram and verbatim citations (van Veen fig 1f + eq 1.1–1.2; Bomphrey 2017 fig 1a). The
convention document, the `WingKinematics.H` docstring, and the `examples/flapping_wing/RESULTS.md`
frame-description SHALL land in the **same change** as the geometry/solver re-orientation — **no interim
commit may carry new-convention geometry with old-convention documentation**.

#### Scenario: Convention page states the van-Veen-faithful axes and normalization

- **Given** `docs/coordinate-convention.md`
- **When** it is read
- **Then** it states x=chord-wise, y=spanwise, z=wing-normal/vertical, `φ` stroke about z, `α` pitch
  about the span (y), `θ` deviation; the body-frame decomposition `F=(F_x chord, F_z normal)`,
  named as the flapping-wing benchmark's `CF_chord`/`CF_normal`; and `F_ref = ½·ρ·ω_peak²·S_yy`,
  `S_yy=∫c(y)y²dy` — each cited to van Veen 2022 (fig 1f / eq 1.1–1.2) and Bomphrey
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

#### Scenario: Each reported force quantity is named with its frame

- **Given** the `## Forces` and `## Moments` sections of `docs/coordinate-convention.md`, read with
  markdown emphasis, backticks and blockquote markers removed and whitespace collapsed
- **When** a guard test reads them
- **Then** `## Forces` has one sentence holding `CF_chord`/`CF_normal` and `wing body frame` but not
  `lab-frame`, one holding the corpus and surrogate `CF_x..CF_z` and
  `lab-frame components of the IB force` but not `wing body frame`, and one holding `plausibility_gate`
  or `fig_forces` together with `lab-frame components` but not `wing body frame`, and it keeps
  `intentionally dropped`
- **And** the page contains none of `forces are reported in the wing body frame`,
  `Unlike the forces above` and `body-frame forces`
- **And** no sentence on the page that holds `CF_x..CF_z`, or the word `force`/`forces`, also holds
  `wing body frame`, `wing frame`, `wing-frame`, `body frame` or `body-frame`, unless it names
  `CF_chord`; a test asserts this check fails on pages that add a reworded wing-frame claim beside
  the correct sentences
- **And** `## Moments` has one sentence holding both `lab-frame components about the hinge` and
  `CF_x..CF_z`
- **And** these checks are functions of the text, and a test feeds them the committed fixture
  `tests/fixtures/convention_page/pre_181_161.md` (a frozen copy of the pre-change `## Forces` and
  `## Moments` sections) and asserts that each check except `intentionally dropped` fails on it
- **And** on both committed corpora (`_CORPUS_PARQUETS`) each of `CF_x`, `CF_y`, `CF_z` equals `−F/F_ref`
  of the same raw lab-frame column with the per-configuration `F_ref`, and `flapping_series_on_wing()`
  holds; a test asserts the corpus check fails on a temporary copy whose coefficients are rotated
  about the lab z-axis

#### Scenario: F_ref is written with ω_peak, tied to the code and to the kinematics

- **Given** `docs/coordinate-convention.md`, with HTML comments removed
- **When** a guard test reads it
- **Then** every `F_ref` expression (`F_ref =`, `:=` or `≡`, with `F_ref` optionally in backticks),
  read to the first `,`, `;`, backtick or line end (or, when nothing follows the `=` before that
  point, the next code span), that contains `ω` contains `ω_peak²` (or
  `ω_peak^2`) and no `ω` not followed by `_peak`; one that contains `S_yy` but no `ω` fails; and at
  least two expressions contain `ω_peak²`
- **And** the page contains `ω_peak = 2π·f_star·radians(phi_amp_deg)` and `` `ω = 2πf` ``, names
  `compute_force_reference`, says `F_ref` is computed per configuration, and links
  `openspec/specs/force-surrogate/spec.md` through a link target that resolves to that file
- **And** on the page with emphasis and backticks removed, every quoted `ω_peak ≈ x` and
  `F_ref ≈ y` (`≈`, `~` or `=` followed by a number that does not continue into a formula; at least
  one of each with `≈`, at least two decimals) equals, at the precision printed, `2π·VALIDATED_F_STAR·radians(VALIDATED_PHI_AMP_DEG)` and
  `compute_force_reference(VALIDATED_F_STAR, VALIDATED_PHI_AMP_DEG, R_GYRATION, SPAN, CHORD, RHO).f_ref`;
  a test feeds the value check pages quoting `134.17` (plain, with `F_ref` in backticks, in bold,
  and with `=`) and asserts each fails
- **And** `2π·f_star·radians(phi_amp_deg)` and `compute_force_reference(...).u_ref / R_GYRATION` each
  equal the maximum of `|wing_kinematics.stroke_rate|` over a grid on one wingbeat offset by half a
  step (relative tolerance `1e-6`) at the validated point and at `f_star = 1.15`,
  `phi_amp_deg = 55`, so the name "peak stroke rate" and the code are checked against the kinematics
- **And** the kinematics table keeps `φ_amp·sin(ωt)` and `α_amp·cos(ωt)`

#### Scenario: No bare ω in F_ref in the documents that restate the normalization

- **Given** `docs/coordinate-convention.md`, `examples/flapping_wing/RESULTS.md`,
  `examples/flapping_wing/figures/README.md`, and every requirement block of the effective
  specification (the live spec with every active change's delta applied) of this capability and of
  [Flapping Wing Validation](../flapping-wing-validation/spec.md)
- **When** a guard test searches each of them, flattened, for `ω` or `\omega` squared (`²`, `^2`,
  `^{2}`, `**2` or `<sup>2</sup>`, optionally after a closing parenthesis) followed by `S_yy` (or
  `S_{yy}`) within 24 characters of the same clause (no `.`, `;`, `,` or line break between)
- **Then** there is no match outside the flapping-wing-validation requirement "Van Veen quasi-steady
  force model, pinned and guarded", where `ω` is the model's instantaneous stroke speed
- **And** the guard fails with a message naming that requirement if it is missing from the effective
  specification or no longer contains such a match, so the exemption cannot outlive its reason
- **And** the `RESULTS.md` normalization paragraph and `Force reference F_ref` row and the
  `figures/README.md` `fig_forces` row contain `ω_peak²`, and the `RESULTS.md` `Reference speed u_ref` row
  contains `radians(phi_amp)`
- **And** a test asserts the scan finds a formula wrapped across a line break

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

### Requirement: The canonical convention page states the force and moment sign

`docs/coordinate-convention.md` SHALL carry exactly one `## Force and moment sign` section (anchor
`#force-and-moment-sign`), a sibling of `## Forces` and `## Moments`. It SHALL state:

- that IAMReX's `ib_force` / `ib_moment` (the IB-particle CSV's `Fx..Mz`) are the force and moment the
  wing exerts on the fluid;
- that every derived wing coefficient is the IB force or moment **on the wing**, their negation by
  Newton's third law. This covers the lab-frame `CF_x..CF_z`, the moment coefficients `CF_mx..CF_mz`
  about the hinge, the flapping-wing lab-frame series, the body-frame `CF_chord`/`CF_normal`, and the
  T4 CFD series;
- that no corpus coefficient includes the internal-fluid term `ρ_f·SumU`. The solver's free-body 6-DOF
  balance would add that term, but the solver never evaluates the balance for the prescribed-motion
  wing. For the zero-thickness wing the term is fluid momentum within about one grid cell of the sheet,
  so it depends on the grid, and its physical status is an open follow-up question;
- that the sphere and heaving-ellipsoid paths already report the force on the body;
- the name of the physics regression test that pins the convention.

It SHALL link the page's existing raw-vs-derived paragraph rather than repeat it. The section SHALL be
the only place that carries the **work-inequality evidence**, identified by any spelling of
"work from rest" (case and hyphens ignored) or `M_hinge · Ω` (either dot operator, any
spacing). The search set is every `*.md` under `docs/`, `examples/` and the repository root,
plus every `.py` file under `src/` (docstrings and comments). Exempt from the search:
`openspec/**`, `tests/**`, `docs/CHANGELOG.md` and the section itself.

A fixed list of documents SHALL link the section. Each link lands in the PR named, and the guard's list
grows in the same commit as the link:

| Document | PR |
|---|---|
| the `ForceCoefficients` / `MomentCoefficients` docstrings | PR1 |
| the `force_on_wing` docstring | PR1 |
| the `flapping_wing.py` module docstring | PR1 |
| `examples/flapping_wing/RESULTS.md` | PR2a |
| `examples/flapping_wing/figures/README.md` | PR2a |
| `docs/aerodynamics_validation/roadmap.md` | PR2a |
| both corpus READMEs | PR2b |
| `docs/force_surrogate/roadmap.md` | PR2b |
| `docs/field_surrogate/roadmap.md` | PR3 |

Docstrings SHALL NOT carry interim status. The section carries every pending phrase. Each phrase is the
exact literal below, occurs at most once, and is governed by a guard:

- **corpus phrase** — `Pending #109: the committed corpus coefficients still carry the solver's on-fluid sign.`
  Absent iff **both** committed corpora's `CF_x`, `CF_y` and `CF_z` are each `allclose` to
  `−F/f_ref` (tied to the data). A raw force component that is all zero fails the guard rather
  than satisfying the condition vacuously.
- **flapping-wing phrase** — `Pending #109: the flapping-wing series still carry the solver's on-fluid sign.`
  Absent iff `reconstruct_wing_forces(forces_t2a_newconv.csv)`'s `cf_x_ib` and `cf_z_ib` are both
  `allclose` to `−F/f_ref`, with the same all-zero rule. This is tied to the **code path**, not
  the data: negating the CSV negates both sides.
- **surrogate phrase** — `Pending #109: the committed surrogates still predict the solver's on-fluid sign; negate their outputs.`
  Present iff both corpus READMEs carry the staleness banner.

#### Scenario: The section exists once and states the convention

- **Given** `docs/coordinate-convention.md`
- **When** its sections are read
- **Then** exactly one `## Force and moment sign` section exists, its slug is `force-and-moment-sign`, it names `ib_force`/`ib_moment` as on the fluid and the coefficients as the IB force on the wing, it notes the internal-fluid term, it lists every covered series (lab-frame `CF_x..CF_z`, `CF_mx..CF_mz`, the flapping-wing lab-frame series, body-frame `CF_chord`/`CF_normal`, the T4 CFD series), it names the oracle test, and it links the raw-vs-derived paragraph. HTML comments are removed before any phrase is counted.

#### Scenario: The listed documents link the section; the evidence lives only there

- **Given** the documents whose link has landed by the current PR, and the search set above
- **When** they are read
- **Then** each listed document contains `coordinate-convention.md#force-and-moment-sign`, and no file in the search set outside the section matches `(?i)work[\s-]+from[\s-]+rest|M_hinge\s*[·⋅]\s*Ω`

#### Scenario: Each pending phrase tracks its condition

- **Given** both committed `dataset.parquet` files, the committed `forces_t2a_newconv.csv`, both corpus READMEs and the canonical section
- **When** the guard evaluates each phrase's condition
- **Then** each pinned literal occurs exactly once if its condition holds and not at all otherwise. So the section can neither claim the on-wing sign for a path before that path carries it, nor keep a pending phrase after it does.
- **And** each direction is exercised by a test:
  - **corpus:** parquet copies with the `CF_*` columns negated, so the test holds whichever sign is committed; one corpus on-wing alone, or a single component re-negated, does not satisfy the condition;
  - **flapping-wing:** `force_on_wing` monkeypatched at the `flapping_wing` use site, identity against negation;
  - **surrogate:** README copies with and without the banner.

### Requirement: The canonical convention page separates geometric pitch from angle of attack

`docs/coordinate-convention.md` SHALL state that the `α` in `R = Rz(φ)·Ry(α)·Rx(θ)` is the wing's
**geometric pitch**, and that it equals van Veen's **angle of attack** only while the wing moves in the
positive stroke direction. Van Veen et al. (2022, §2.4) call the two the same because the wing in their
simulations never reverses. For the project's sinusoidal waveform the pitch changes sign with the stroke
rate, so the angle of attack is `|α|`; the page SHALL say so and SHALL name `decompose_wing_force` as
the place where the angle of attack is derived for the van Veen model. The page's kinematics table
SHALL NOT label the `φ₀·sin(ωt)` / `α₀·cos(ωt)` waveform as van Veen's. The page's citations of van Veen
for the axes, the rotation order, the force normalization and the hinge SHALL remain.

#### Scenario: The page distinguishes pitch from angle of attack

- **Given** `docs/coordinate-convention.md`
- **When** a guard test reads it
- **Then** it contains the phrase `geometric pitch`, the expression `|α|` and the name
  `decompose_wing_force`
- **And** the guard locates the kinematics table by its `| Angle | Rotation axis |` header, asserts it
  was found, and asserts the header has no `van Veen kinematics` column
- **And** the page still cites van Veen for the axes and the normalization
- **And** the guard fails when the `geometric pitch` statement is removed

