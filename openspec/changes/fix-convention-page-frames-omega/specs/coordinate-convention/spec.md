## MODIFIED Requirements

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
