## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Project-wide axis convention matches van Veen 2022, documented atomically

The project SHALL adopt a single wing coordinate convention matching **van Veen et al. (2022, *JFM*
936:A3, §1.2 / eq 1.1–1.2 / fig 1f)**: **x = chord-wise, y = spanwise, z = wing-normal (vertical /
lift)**; stroke angle `φ` about the world vertical (z); pitch `α` about the spanwise (y)
axis (van Veen's angle of attack while the wing moves in the positive stroke direction); deviation `θ` out of the stroke plane. Forces are reported in the **wing (body) frame** as
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
