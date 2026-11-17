## ADDED Requirements

### Requirement: Angle-of-attack inputs for the van Veen model are derived from the wing's motion

The analysis SHALL provide one pure function that turns the wing's geometric pitch `α_p`, stroke rate
`φ̇` and stroke acceleration `φ̈` into the van Veen model's inputs and the directions its forces act
along in the wing body frame. `decompose_wing_force` SHALL use it; no caller SHALL pass a signed pitch
to the model.

Under `R = Rz(φ)·Ry(α_p)` with zero deviation (all `decompose_wing_force` accepts), a point on the
span axis at hinge distance `r` has body-frame velocity `−φ̇·r·(cos α_p, 0, sin α_p)`; the pitch rate
does not enter because `Ry` leaves the span axis fixed. Let `s = sign(φ̇)`, or `sign(φ̈)` at an instant
where `φ̇ = 0` (the way the wing is about to move), and let `u = −s·(cos α_p, 0, sin α_p)`. Then:

- the angle of attack is `atan2(|u_z|, |u_x|)`;
- the stroke speed is `|φ̇|`, and the acceleration along the motion is `s·φ̈`;
- the model's chord force is applied along `−sign(u_x)` and its normal force along `−sign(u_z)`.

Where `u_x` or `u_z` is exactly zero the corresponding direction is `0`, so that force component is
zero: with no motion along an axis there is no direction to assign. Where `φ̇ = φ̈ = 0` every returned
value SHALL be zero and finite. Folding the pitch into `[0, π/2]` this way relies on two symmetries of
the wing: about its chord midline (either edge may lead) and about its own plane (flat, uncambered,
zero thickness; either face may lead). The elliptic plate has both. The function's docstring SHALL
name both, and SHALL say the model has no pitch-rotation term. For the
added-mass component the result equals `ρ·S_cy·φ̈·(C_Fxα_AM·cos α_p, C_Fzα_AM·sin α_p)` in the body
frame — the reaction to the body-frame acceleration, continuous through stroke reversal.

#### Scenario: The model is fed the angle of attack on both half-strokes

- **Given** the production kinematics (`f_star = 1`, `phi_amp_deg = 70`, `pitch_amp_deg = 45`)
- **When** the inputs are derived at mid forward stroke (`t = 0`) and mid return stroke (`t = 0.5`)
- **Then** the angle of attack is 45° at both; the model-total normal coefficient is `3.13·sin 45°` at
  both, with the same sign; and the model-total chord coefficient is `+0.042125` at `t = 0` and
  `−0.042125` at `t = 0.5` (the added-mass and Wagner terms are zero there because `φ̈ = 0`) —
  hand-computed literals, never the CFD series
- **And** over a full wingbeat every angle of attack lies in `[0, π/2]`, every speed is non-negative,
  and, away from mid-stroke and reversal, the acceleration is positive in the first half of each
  half-stroke and negative in the second

#### Scenario: Directions are right in every quadrant, not only on the sinusoidal waveform

- **Given** pitch values `+45°`, `−45°`, `+120°`, `−120°`, each with `φ̇ > 0` and with `φ̇ < 0`
- **When** the inputs are derived
- **Then** the angle of attack and both direction signs equal hand-computed values for all eight cases —
  for example pitch `−45°` with `φ̇ > 0` gives angle of attack 45° and normal direction `−1`, and pitch
  `+120°` with `φ̇ > 0` gives angle of attack 60° and chord direction `−1`
- **And** an implementation that hard-codes the normal direction as `+1`, or that uses `|α_p|` as the
  angle of attack, fails this scenario
- **And** at pitch `+90°` the chord direction is `0`, and at pitch `0` the normal direction is `0`

#### Scenario: The derivation agrees with the canonical rotation

- **Given** `wing_kinematics.rotation_matrix`, the sinusoidal kinematics, and a second trajectory with
  constant pitch `−45°` and `φ = t`
- **When**, at 200 evenly spaced times over one wingbeat excluding those within `0.01` of a stroke
  reversal (where the velocity is roundoff), the body-frame velocity `v` of a span point is computed by
  a central difference of `R(t)` (step `1e-6`) rotated by `R(t)ᵀ`, and `atan2(|v_z|, |v_x|)`, `|v|/r`, `−sign(v_x)` and `−sign(v_z)`
  are formed from it
- **Then** they equal the function's angle of attack, speed, chord direction and normal direction
  (`rtol = 1e-7`, `atol = 1e-8`), so a change of rotation convention fails this scenario

#### Scenario: Stroke reversal and rest are well defined

- **Given** a literal `φ̇ = 0.0` with `φ̈ = +a` and with `φ̈ = −a`, at pitch `0` and at pitch `0.3`
- **When** the inputs and the added-mass chord force are derived
- **Then** the acceleration along the motion is `+|a|`, the chord direction follows `sign(φ̈)`, the
  normal direction is `0` at pitch `0` and follows `sign(φ̈)` at pitch `0.3`, and the
  body-frame added-mass chord force equals `ρ·φ̈·S_cy·C_Fxα_AM·cos α_p`, non-zero and correctly signed
- **And** with `φ̇ = φ̈ = 0` every returned value is zero and finite
- **And** on the production kinematics the body-frame added-mass chord series equals
  `ρ·φ̈·S_cy·C_Fxα_AM·cos α_p / F_ref` at every step, including the steps on each side of a reversal

### Requirement: Grid figures draw single-source, labelled reference lines

The three grid figures SHALL NOT draw a shaded region presented as a van Veen target. They are
`fig_force_timeseries_3grid`, `fig_grid_convergence_3grid` and `fig_grid_convergence`. A model reference in these figures SHALL
be the corrected model peak read from `decompose_wing_force` on the fine-grid CSV when the figure is
rendered, not a typed literal; a T2a target SHALL be read from `VAN_VEEN_CF_TARGETS`, not a typed copy;
and each reference line's label SHALL name its source. In `fig_force_timeseries_3grid` the chord
reference SHALL be drawn at both `+` and `−` the model chord peak, because the chord force changes sign
each half-stroke. The Richardson / GCI span that `fig_grid_convergence_3grid` draws in each panel for
the CFD grids is not affected; the other two figures have no shaded horizontal span.

#### Scenario: Reference lines follow their sources

- **Given** each of the three figure scripts, with `decompose_wing_force` and `VAN_VEEN_CF_TARGETS`
  replaced by sentinel values
- **When** the figure is generated
- **Then** each model reference line sits at the sentinel model peak and each T2a target line at the
  sentinel target, so a typed literal fails
- **And** the shaded horizontal spans (`axhspan` patches, as distinct from bars) are exactly the
  Richardson / GCI span per panel in `fig_grid_convergence_3grid`, and none in the other two figures
- **And** each reference line's label names its source, and the timeseries chord panel has lines at
  both signs of the model chord peak

## RENAMED Requirements

- FROM: `### Requirement: CF_chord PARTIAL resolved — decomposition figure, RESULTS, and roadmap`
- TO: `### Requirement: T4 decomposition figure, RESULTS, and roadmap state what the corrected model supports`

## MODIFIED Requirements

### Requirement: Flapping-wing plausibility gate on ib_force (lab-frame; frame/tier deferred)

The flapping-wing validation SHALL grade an **order-of-magnitude plausibility gate** on the accumulated
immersed-boundary force `ib_force` (`Fx/Fy/Fz`) **alone** — the added-mass term SHALL NOT be required for
the gate to pass (it is reported separately). Over a pinned, documented steady window, the band
`VAN_VEEN_BAND` SHALL be graded as a **lower-bound O(1) sanity floor**: the peak lab-frame magnitudes
`max|CF_x|` and `max|CF_z|` (van Veen convention, no correction factor) SHALL each be **≥ the band floor
`0.5`** — the check that catches an under-produced / mis-normalized coefficient (it flagged the old
peak-tip normalization at `CF_z ~0.22 < 0.5`). The **band ceiling `1.5` SHALL be reported, not gated**: a
per-component peak **above** `1.5` is **expected** under the corrected motion and is **not** a failure,
because the pinned body-frame normal target (~2.4) also exceeds `1.5` (see the committed
`figures/fig_forces.png`, new-convention lab `max|CF_x| = 2.37`). The `VAN_VEEN_BAND` constant `(0.5, 1.5)`
and its not-loosened guard SHALL remain **unchanged** — this is a **grading-role** change (two-sided gate →
lower-bound floor), **not** a loosening. The rotation-invariant resultant `|CF| = sqrt(CF_x² + CF_z²)`
SHALL be reported as the frame-honest companion, and the `CF_z` floor margin (distance above `0.5`) SHALL
be reported. The **faithful per-component van Veen comparison is the body-frame decomposition** (see
"Body-frame (chord/normal) per-component van Veen comparison"), not the lab-frame band; the lab band is a
floor/sanity only. The regenerated `RESULTS.md`/figures SHALL disclose the lab band as an O(1) floor.
**Validation of the wing-normal against van Veen's quasi-steady model is delivered by Tier T4** (the
per-component decomposition — normal **peak magnitude** graded; peak **phase**, curve RMSE and curve
correlations **reported**; see "Per-component decomposition of the CFD force, graded against van Veen's
model"); the **chord** total curve is **reported, not gated**, and is not explained by the model. The lab band remains a floor/sanity only and
SHALL NOT be read as the time-resolved validation.

> **Deliberate deletion (not accidental):** the prior requirement motivated the lab-frame caveat via the
> old `Rz(φ)`-about-span stroke (issue #1). That motivation is **obsolete after T2a** corrected the
> motion, and is intentionally dropped from this MODIFIED requirement.

#### Scenario: Peak coefficients clear the O(1) floor without a fudge

- **Given** the wing `ib_force` (`Fx/Fy/Fz`) under the van Veen convention over the pinned steady window
- **When** the peak coefficients are taken
- **Then** `max|CF_x|` and `max|CF_z|` are each **≥ 0.5** (the band floor) with no correction factor
  applied (added-mass not required), and the rotation-invariant `|CF| = sqrt(CF_x² + CF_z²)` is reported
  alongside

#### Scenario: A per-component peak above the ceiling is expected, not a failure

- **Given** the new-convention run whose lab `max|CF_x| = 2.37` exceeds the band ceiling `1.5`
- **When** the plausibility gate is evaluated
- **Then** the gate does **not** fail on the ceiling — the excursion is recorded as an **expected O(1)**
  consequence of the corrected motion (consistent with the pinned body-frame normal target ~2.4 also exceeding
  `1.5`), and the docs state the ceiling is reported, not gated

#### Scenario: The floor still catches an under-produced coefficient (not loosened)

- **Given** a coefficient series whose peak magnitude falls **below** `0.5` (e.g. the old peak-tip
  normalization giving `CF_z ~0.22`)
- **When** the floor gate is evaluated
- **Then** it **fails** — the floor is load-bearing — and `VAN_VEEN_BAND` is still asserted equal to
  `(0.5, 1.5)` by the not-loosened guard (the demotion cannot admit a genuinely too-small coefficient)

#### Scenario: Steady window is pinned by a physical criterion and reproducible

- **Given** the committed IB-particle force series whose first steps carry an impulsive-start transient
- **When** the headline peak coefficients are evaluated
- **Then** the analysis pins the steady window by the documented `STEADY_WINDOW_T0` named constant (not
  chosen post-hoc), and the reported peaks are reproducible from the committed data for that window
- **And** with the pinned window the `CF_z` floor margin above `0.5` is reported (the margin, not just a
  pass/fail bit)

#### Scenario: Docs disclose the lab-frame floor and point to the delivered time-resolved validation

- **Given** the regenerated `RESULTS.md`/figures
- **When** they are inspected
- **Then** they state the lab-frame gate is an **O(1) magnitude floor** whose `CF_x/CF_z` are lab-frame
  (not van Veen's body-frame chord/normal), point to the **delivered** body-frame per-component van Veen
  comparison **and** the **Tier T4 per-component decomposition** (wing-normal validated against van Veen's
  quasi-steady model in **peak magnitude**; peak phase, RMSE and curve correlations reported; chord
  reported beside the model, not explained by it), and do **not** present the lab band itself as the time-resolved validation

### Requirement: Body-frame (chord/normal) per-component van Veen comparison

The flapping-wing analysis SHALL decompose the lab-frame `ib_force` `(Fx,Fy,Fz)` into the
**instantaneous wing body frame** using the **analytic** rotation `R(t)` from the wing kinematics (the
same composition the solver applies), yielding chord-wise `CF_chord` and wing-normal `CF_normal` series
in van Veen's convention (`F = (F_x chord, F_z normal)`), normalized by the single-source
`compute_force_reference` (`F_ref = ½ρω²S_yy`; no correction factor). The rotation axes/order SHALL be
passed **explicitly** (no hard-coded streamwise axis) so the analysis layer cannot re-introduce a
#1-style mislabel. On the **new-convention re-run**, the analysis SHALL grade an **overall scalar
match** — the **peak** `|CF_chord|` and `|CF_normal|` (cycle-means SHALL be **reported alongside**, not
graded — a coarse single-wingbeat run has no converged mean) — with the test-pinned `VAN_VEEN_BAND`
`[0.5,1.5]` as a floor that SHALL NOT be loosened. The **normal** peak is within `VAN_VEEN_MATCH_TOL` of the pinned
normal target (`~2.4`; `cf_normal_match = True`). The **chord**'s scalar-match
against the pinned chord target (`cf_chord_match = False`, the T2a **PARTIAL**) is **not resolved**: the
Tier T4 decomposition compares the total chord with van Veen's `transl + AM + Wagner` model total (see
"Per-component decomposition of the CFD force, graded against van Veen's model") and **reports** the two
peaks without a verdict; it does not explain the PARTIAL. The coarse peak `CF_chord ≈ 0.92` remains
reproducible and its `cf_chord_match = False` scalar result is unchanged. This requirement does not
re-derive the values in `VAN_VEEN_CF_TARGETS`; whether they match the paper's eq 3.9 and eq 3.12 fits
is tracked by a follow-up issue. The
body-frame decomposition of the **old committed run** SHALL be reported as a **contrast baseline**.

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
  to fail** (guarded by a not-loosened test)

#### Scenario: Normal scalar-match graded; chord PARTIAL reported, not resolved

- **Given** the body-frame series and the T2a target values pinned as the named constant
  `VAN_VEEN_CF_TARGETS` with tolerance `VAN_VEEN_MATCH_TOL`
- **When** the tolerance match is computed
- **Then** peak `|CF_normal|` falls within `VAN_VEEN_MATCH_TOL` of the normal target (`cf_normal_match =
  True`); the grader is proven on synthetic fixtures to **pass within and fail outside** (both directions);
  and the **chord** `cf_chord_match = False` (peak `≈0.92` against the pinned chord target) is **not**
  re-graded here and is **not** described as resolved — the T4 decomposition reports the total chord
  against `transl + AM + Wagner` without a verdict.
  `VAN_VEEN_CF_TARGETS` and `VAN_VEEN_MATCH_TOL` remain named, test-guarded constants (a loosened tolerance
  fails a not-loosened test)

#### Scenario: Old-run body-frame decomposition reported as contrast

- **Given** the old committed `forces.csv` (stroke-∥-span motion) run through the same body-frame decomposition
- **When** its `CF_chord`/`CF_normal` are reported
- **Then** they appear as a labelled **contrast baseline** demonstrating the old motion's per-component
  values differ from van Veen — evidence the refactor is a motion correction, not a relabel

### Requirement: RESULTS.md headline numbers reproducible from committed CSVs (issue #3 re-validation)

Every **headline number** in `examples/flapping_wing/RESULTS.md` SHALL be **recomputable** from the
committed force CSVs over the stated steady window, via the single-source `compute_force_reference` /
`compute_force_coefficients`, the body-frame decomposition, the `added_mass_fraction` RMS helper, the
added-mass-subtracted body-frame interim diagnostic (`body_frame_added_mass_subtracted`, #40), **and the
Tier T4 per-component decomposition (`decompose_wing_force`)** — with **no** value transcribed that the
committed data cannot regenerate. The new-convention headline numbers SHALL recompute from
`forces_t2a_newconv.csv` (`F_ref = 200.27`, `t ≥ 0.05`); the contrast-baseline numbers from `forces.csv`.
The recomputation SHALL respect each number's **definition**: coefficient ranges/peaks via
`compute_force_coefficients`; the phase-table `Fz` are **raw forces** read at the named `time` rows (not coefficients) — the
solver's on-fluid `ib_force`, which RESULTS.md SHALL label as such — while the phase table's `CF_z (lab)`
column is the on-wing coefficient `−Fz/F_ref`; the added-mass fractions are the **RMS** `added_mass_fraction` values (stroke ~37 % / lift
~29 %); the added-mass-subtracted interim numbers are the 6-DOF and IB-only (`ib_w`) body-frame peaks, their
signed peak-to-peak fractions,
and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %); **the T4 decomposition numbers are
the model and CFD peak coefficients (normal and chord) on the fine-grid CSV `forces_fine.csv`, the
per-component and total model coefficients and RMS shares wherever `RESULTS.md` states them, the graded
normal relative peak gap, the
reported normal peak-phase gap, the signed curve RMSE and correlations, and the known-answer
translational-chord peak; their values are pinned in the reproducibility test, not in this spec**. The enumeration of checked numbers SHALL be **asserted complete** — a
RESULTS.md headline number absent from the enumeration fails the test; **the interim subsection's and the
T4 subsection's distinct numbers SHALL be enumerated / asserted-complete in their own guards** (separate
from the two existing headline tables, so their extra-precision totals do not collide). To keep that
separation load-bearing, the interim and T4 subsections SHALL each use a **distinct `### ` header** whose
text does **not** contain the substrings `lab-frame magnitudes` or `Body-frame per-component van Veen
comparison` (the two the existing `test_headline_tables_enumeration_complete` scans by exact-set-equality),
and SHALL **not add or alter any numeric cell inside those two enumerated tables** (except the #109 sign
flip of the lab-range cells); a test SHALL confirm the
existing enumeration guard still passes unchanged. A test SHALL assert this reproducibility **before** any
RESULTS.md edit, and SHALL stand as the **durable regression guard** that closes issue #3 (whose original
`+0.431` defect is superseded by the T2a regeneration — T2b/T4 re-validate the **current** document).

#### Scenario: Lab-frame ranges recompute from the committed new-convention CSV

- **Given** `forces_t2a_newconv.csv` and the van Veen `F_ref = 200.27` from `compute_force_reference`
- **When** the lab-frame coefficients are computed over `t ≥ 0.05`
- **Then** the on-wing `CF_x` range ≈ `[−2.37, +2.35]` and `CF_z` range ≈ `[−0.03, +1.46]` (the exact negation of the pre-#109 on-fluid ranges), `max|CF_x| ≈ 2.37`, and
  `max|CF_z| ≈ 1.46` — each matching the RESULTS.md headline as pinned literals to the documented precision

#### Scenario: Body-frame peaks recompute; the chord PARTIAL stays open

- **Given** the same committed CSV and the analytic `R(t)` from the wing kinematics
- **When** `body_frame_overall_match` is evaluated against `VAN_VEEN_CF_TARGETS` / `VAN_VEEN_MATCH_TOL`
- **Then** peak `CF_normal ≈ 2.61` (`cf_normal_match = True`) and peak `CF_chord ≈ 0.92`
  (`cf_chord_match = False`) recompute unchanged from committed data; `RESULTS.md` SHALL NOT describe the
  chord PARTIAL as resolved, closed or explained by the T4 decomposition

#### Scenario: Interim added-mass-subtracted numbers recompute and are asserted present

- **Given** `forces_t2a_newconv.csv` and the `body_frame_added_mass_subtracted` diagnostic over `t ≥ 0.05`
- **When** the interim subsection's numbers are recomputed
- **Then** the 6-DOF and `ib_w` peaks (`0.652` / `0.923` chord, `2.285` / `2.606` normal), the signed
  ratios `drop_frac = 1 − peak_ib/peak_6dof` (≈ −0.42 / −0.14: removing the internal-fluid term raises
  the peaks 42 % / 14 %), and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %) recompute from the committed
  CSV and appear in `RESULTS.md` as pinned literals; the `ib_w` peaks additionally equal `body_frame_overall_match`'s `peak_cf_chord`/`peak_cf_normal` (the "same peaks" cross-check); the interim
  subsection's distinct numbers are **asserted complete** (a new interim number absent from the enumeration
  fails); the doc's "same peaks" note and the body-frame-vs-lab-frame disambiguation sentence are asserted
  present; and the guard runs **before** the doc edit while the existing
  `test_headline_tables_enumeration_complete` still passes unchanged

#### Scenario: T4 decomposition numbers recompute and are asserted present

- **Given** `forces_fine.csv` (the production comparison) and `decompose_wing_force` over `t ≥ 0.05`
- **When** the T4 subsection's numbers are recomputed
- **Then** the model and CFD peak coefficients, the graded normal relative peak gap, the reported normal
  peak-phase gap, the signed curve RMSE and correlations, and the known-answer translational-chord peak
  recompute from the committed data and appear **inside the T4 subsection** of `RESULTS.md` at the
  precision the test pins (a literal is matched as a whole number within that subsection, so a value
  such as `1.7` is not satisfied by `11.7` elsewhere in the document); the gap on the coarse
  (`forces_t2a_newconv.csv`) and medium (`forces_medium.csv`) CSVs, wherever `RESULTS.md` states it,
  recomputes the same way; the T4 subsection uses a distinct `###` header (not containing the two scanned
  substrings) and adds/alters no cell in the two existing enumerated tables; the T4 subsection's distinct
  numbers are **asserted complete** (a new T4 number absent fails); and the existing headline-table and
  interim enumeration guards still pass unchanged

#### Scenario: Every stated headline value has a committed-data source, by its own definition

- **Given** the RESULTS.md headline numbers — CF ranges/peaks (coefficients), the phase-table `Fz` (raw
  forces at named `time` rows), the body-frame `2.61`/`0.92`, the RMS added-mass fractions (~37 %/~29 %),
  the added-mass-subtracted interim 6-DOF/`ib_w` peaks (`0.652`/`0.923`, `2.285`/`2.606`), `drop_frac`
  (≈ −0.42 / −0.14) and shares (~84 %/~13 %), **the T4
  model and CFD peak coefficients and the translational-chord peak** — and the contrast-baseline numbers
  (`1.41`/`0.68` from `forces.csv`)
- **When** the reproducibility test runs
- **Then** each number recomputes from its committed CSV **by the correct definition** (coefficient vs raw
  force vs RMS fraction vs added-mass-subtracted diagnostic vs T4 decomposition) within the documented
  tolerance; any number that cannot be regenerated — or any headline number missing from the
  asserted-complete enumeration — fails the test; and the test passes **before** RESULTS.md is edited, so
  the doc is proven against live data, not curated

#### Scenario: Phase-table coefficients are on-wing while raw forces stay as written

- **Given** `forces_t2a_newconv.csv` and the RESULTS.md phase table
- **When** its rows are recomputed at the named `time` values
- **Then** each `Fz` cell equals the solver's raw `Fz` (labelled as the force on the fluid) and each `CF_z (lab)` cell equals `−Fz/F_ref`, and the table caption gives the formula as `−Fz / F_ref` with a link to `docs/coordinate-convention.md#force-and-moment-sign`

### Requirement: Added-mass-subtracted body-frame CF diagnostic (reported; #40 cheap interim)

The flapping-wing analysis SHALL provide a **reported** diagnostic that compares the **6-DOF
force** `F_6dof = ρ_f·(SumU + ib_w)` with the IB force on the wing `ρ_f·ib_w` (`ib_w = −ib_force`;
`ib_force` is per unit density, so both sides carry `ρ_f`; `F_ref` is built with the same `ρ_f`, so
the diagnostic's peaks and ratios do not depend on it). `F_6dof` is the
solver's free-body momentum balance `ρ_f·(SumU − ib_force)` applied to the wing's columns; the solver
itself never evaluates that balance for the prescribed-motion wing. The difference between the two is
the solver's **internal-fluid momentum term** `ρ_f·SumU` (via the existing `added_mass_force`, #36). For
the zero-thickness vertex-file wing, that term is the momentum change of fluid within about one grid
cell of the sheet, so it depends on the grid. This code calls the term "added mass", but it is **not**
van Veen's added-mass component; which CFD force corresponds to van Veen's model is a follow-up issue. The
requirement's name is historical: `ρ_f·ib_w` is the 6-DOF force minus `ρ_f·SumU`. The diagnostic rotates
both forces into the instantaneous wing body frame with the **same** analytic `R(t)` and
`body_frame_coefficients` the T2a body-frame decomposition uses (CC-V4 — the rotation and the added-mass
magnitude are **reused, not re-derived**), and reports, over the pinned steady window
(`STEADY_WINDOW_T0`), the peak `|CF_chord|`/`|CF_normal|` for **both** the 6-DOF force and `ib_w` (return keys
`peak_cf_{chord,normal}_{6dof,ib}`; each peak the **independent** window argmax of its `|series|`,
since on this data the two chord peaks fall at different phases), their **signed peak-to-peak**
fraction (`drop_frac = 1 − peak_ib/peak_6dof`, the change from removing the internal-fluid term;
negative when removing it raises a peak, as it does here), and the **body-frame added-mass RMS share** per component (`rms(CF_added,body)/rms(CF_ib,body)` — the
body-frame analog of the lab-frame `added_mass_fraction`). Because it rotates the **full 3-D** force and
added-mass vectors, the diagnostic SHALL read `time, Fx, Fy, Fz, SumUx, SumUy, SumUz`;
no single existing required-column set covers all seven (`_REQUIRED_CSV_COLUMNS` lacks `Fy` and `SumUy`;
`_REQUIRED_BODY_CSV_COLUMNS` lacks the `SumU*` columns; `SumUy` is in **neither**), so the diagnostic SHALL
define its **own** required-column set including them and raise if **any** one is missing. The diagnostic SHALL be **cluster-free** (the committed
`forces_t2a_newconv.csv`, 29-col with `SumU{x,y,z}`; CC-V3) and normalized by the single-source
`compute_force_reference` (`F_ref = ½ρω²S_yy`; no correction factor).

The diagnostic SHALL be **reported, not graded**: it SHALL NOT introduce any new pass/fail against van
Veen for the diagnostic's values (CC-V2). Its return value SHALL expose **no** `*_match`/`pass`/`floor`/
`in_band` verdict field, and the existing graders — `plausibility_gate` (lab `ib_force`) and
`body_frame_overall_match` (body `ib_force` vs `VAN_VEEN_CF_TARGETS` at `VAN_VEEN_MATCH_TOL`, floor
`VAN_VEEN_BAND`) — SHALL remain **unchanged**; a diagnostic value cannot re-grade van Veen.

The analysis and docs SHALL frame the comparison as **isolating the internal-fluid term's share**, NOT
as resolving the `CF_chord` PARTIAL: the IB-only `CF_chord ≈ 0.923` remains ~3× the pinned chord
target ~0.3, and the 6-DOF `≈ 0.652` ~2×. Which CFD force the van Veen comparison should use
(`ib_w` or the 6-DOF force) is a follow-up issue, not decided here. The Tier T4 per-component
decomposition (van Veen's `transl + AM + Wagner`; see "Per-component decomposition of the CFD force,
graded against van Veen's model") **does not resolve that residual either**: it reports the model chord
total and the CFD chord side by side, without a verdict. The docs SHALL NOT state that #40 is closed
or resolved by T4. Where
`RESULTS.md` reports the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %), it SHALL
**explicitly disambiguate** them from the already-reported **lab-frame** added-mass RMS fractions (stroke
~37 % / lift ~29 %, from `added_mass_fraction`): they are a **different frame *and* axis pairing** (lab
stroke/lift are `rms(cf_added)/rms(cf_ib)` in `x`/`z`; body chord/normal are the same ratio *after* rotation
by `R(t)`), and **neither supersedes the other**. Malformed input (missing any of the required columns —
including `Fy`/`SumUy` — a non-finite row, or an empty steady window) SHALL raise `ValueError`, mirroring
the existing decomposition guards (never a silent NaN coefficient).

#### Scenario: 6-DOF and IB-only forces rotated into the body frame reproduce the interim peaks (committed data)

- **Given** `forces_t2a_newconv.csv` (29-col, with `SumUx/SumUy/SumUz`), `ρ_f = RHO = 1.0`, the analytic
  `R(t)` from the wing kinematics, and `F_ref` from `compute_force_reference`
- **When** the diagnostic forms `F_6dof = ρ_f·(SumU + ib_w)` and `ρ_f·ib_w`, and rotates both into the wing body frame over `t ≥ 0.05`
- **Then** the 6-DOF peaks are `|CF_chord| ≈ 0.652` and `|CF_normal| ≈ 2.285` and the `ib_w` peaks
  `0.923` and `2.606`, so `chord_drop_frac ≈ −0.42` and `normal_drop_frac ≈ −0.14` (removing the
  internal-fluid term raises both peaks), reproduced from the committed CSV; the `ib_w` peaks
  `0.923`/`2.606` are the **same peaks** as the body-frame comparison's `0.92`/`2.61` shown to an extra
  significant figure, because at `ρ_f = RHO = 1` the `ρ_f·ib_w` series is exactly the graded force (a
  test SHALL assert, at `ρ_f = RHO` and at `ρ_f = 2`, that the `ib_w` peaks equal
  `body_frame_overall_match`'s `peak_cf_chord`/`peak_cf_normal` so the two precisions cannot drift;
  the identity holds at any density because `F_ref` carries the same `ρ_f`), and `RESULTS.md` SHALL carry that "same peaks" note so the dual precision is not read as two
  different results

#### Scenario: Body-frame added-mass RMS shares are reported

- **Given** the body-frame added-mass force (`Rᵀ·ρ_f·SumU`) and the body-frame on-wing IB force `Rᵀ·ρ_f·ib_w` over the
  pinned steady window
- **When** the RMS share is formed as `rms(added-mass component)/rms(ib component)` per body axis (the
  body-frame analog of the lab-frame `added_mass_fraction`, not a peak ratio and not `rms(6dof)`)
- **Then** it reports ≈ **84 %** of the chord RMS and ≈ **13 %** of the normal RMS — quantifying that the internal-fluid term is large relative to `ib_w` in the chord and small in the
  normal; it SHALL NOT be described as van Veen's added mass

#### Scenario: Reuses the T2a rotation and #36 added-mass, not a re-derivation

- **Given** the diagnostic
- **When** it computes the 6-DOF and `ib_w` body-frame coefficients
- **Then** it calls `added_mass_force` (#36) for `ρ_f·SumU` and `body_frame_coefficients` / the
  `wing_kinematics` `R(t)` mirror (T2a) — add-in-lab-then-rotate equals rotate-then-add because the rotation is linear — and it does **not** re-implement the added-mass magnitude or the rotation
  (the magnitude and orientation defect classes stay separate, CC-V4)

#### Scenario: Reported only — no new van Veen pass/fail, existing graders unchanged

- **Given** the diagnostic's return value and the existing `plausibility_gate` /
  `body_frame_overall_match` graders on the committed run
- **When** they are evaluated
- **Then** the diagnostic exposes **no** `*_match`/`pass`/`floor`/`in_band` field (it is reported, not
  graded), and the plausibility-gate floor verdict and the body-frame van-Veen-target verdict
  (`cf_normal_match=True`, `cf_chord_match=False`, `match=False`) — both graded on the on-wing `ib_w` — are
  **unchanged** (CC-V2); no diagnostic value can flip any gate

#### Scenario: Honest framing — isolates the share; the PARTIAL stays open

- **Given** the 6-DOF `CF_chord ≈ 0.652` and the IB-only `CF_chord ≈ 0.923`
- **When** `RESULTS.md` reports the interim
- **Then** it states the comparison **isolates the internal-fluid term's share** (84 % of the chord RMS),
  **not** that the interim resolves the PARTIAL — `0.923` is still ~3× the pinned chord target
  ~0.3 (the 6-DOF `0.652` ~2×) — and it
  states that the Tier T4 decomposition does not resolve the residual either
- **And** the doc SHALL carry a **metric-type caveat** for the chord: the 84 % is an RMS *energy* share
  over the window, whereas `drop_frac ≈ −0.42` (removing the term raises the chord peak 42 %) is a **peak-to-peak ratio
  of two window maxima at *different* phases**
  (not a per-instant subtraction) — so "84 % of RMS" is NOT presented as the cause of "the chord peak rose 42 %" (they are different metrics on different
  supports); the instantaneous ratio at the 6-DOF chord peak (`1 − |ib_w|/|F_6dof|` ≈ −0.39, i.e. `|ib_w|`
  exceeds `|F_6dof|` by 39 % there) is named as a third metric, and the two chord peaks are ~1094
  timesteps apart
- **And** a reproducibility test SHALL assert the load-bearing framing **wording** is present (an
  `isolat…` phrase, a "does not resolve"/"not … resolve" phrase for the interim-by-itself, the `~3×` / `0.3` residual, a statement that `ρ_f·SumU` is the solver's internal-fluid term and not van
  Veen's added mass, a pointer to the follow-up issue on which CFD force van Veen's comparison should use, the peak-to-peak/different-phase caveat) and that the `RESULTS.md` wing Validation-Status row
  states the T4 result as **validated against van Veen's quasi-steady model in normal peak magnitude**,
  with the chord **reported and not explained by the model**; the reproducibility test SHALL fail if the
  interim subsection says the PARTIAL is resolved or that #40 is closed

#### Scenario: Malformed input raises, never a silent coefficient

- **Given** a CSV with **any one** of `Fy`, `SumUx`, `SumUy`, `SumUz` removed (each dropped individually —
  `Fy`/`SumUy` are the cases the two existing required-column sets do **not** cover), or a non-finite
  `ib_force`/`SumU` row, or a `window_t0` selecting no timesteps
- **When** the diagnostic runs
- **Then** it raises `ValueError` (missing-column / non-finite / empty-window), mirroring the existing
  `reconstruct_wing_body_forces` and `body_frame_coefficients` guards — never a silent NaN coefficient

#### Scenario: Docs disambiguate body-frame shares from lab-frame fractions

- **Given** `RESULTS.md` reporting the new body-frame added-mass RMS shares (chord ~84 % / normal ~13 %)
  one section from the existing lab-frame added-mass RMS fractions (stroke ~37 % / lift ~29 %)
- **When** the interim subsection is read
- **Then** it carries an explicit sentence stating the two are a **different frame and axis pairing**
  (neither supersedes the other), and the reproducibility guard asserts that disambiguation phrase is
  present (not merely that all four percentages coexist in the file)

#### Scenario: Either degenerate denominator raises

- **Given** a synthetic CSV whose `ib_w` is nonzero with `ρ_f·SumU = −ib_w` (a zero 6-DOF force), and another whose `ib_w` is zero with nonzero `SumU`
- **When** the diagnostic runs on each
- **Then** the first raises `ValueError` naming the degenerate 6-DOF peak (the `drop_frac` denominator) and the second raises `ValueError` naming the degenerate `ib_w` (the RMS-share denominator), each against `_DEGENERATE_CF_FLOOR`
- **And** a guard on only one of the two denominators fails this scenario

### Requirement: Van Veen quasi-steady force model, pinned and guarded

The analysis SHALL provide a **pure** implementation of van Veen's (2022, JFM 936 A3) quasi-steady
force model — the sum of **three** additive components `F_total = F_transl + F_AM + F_WE`
(translational + added-mass + **Wagner**), each returning a `(chord/x, normal/z)` force from
`(α, ω, ω̇)` and the wing area-moments. There SHALL be **no** rotational-circulation or rotational-drag
term (van Veen's model has none; the paper's "rotational" denotes rotational *stroke acceleration*, i.e.
the `ω̇`-dependent added-mass and Wagner terms). The fitted coefficients SHALL be **named module-level
constants** carrying their published 95 % confidence intervals, and a **not-loosened guard** test SHALL
fail if a coefficient (or its CI) is widened (CC-V2).

The inputs SHALL be: `α`, the **angle of attack**, in radians within `[0, π/2]`; `ω ≥ 0`, the stroke
**speed**; and `ω̇`, the stroke acceleration **along the direction of motion** (positive while the wing
speeds up, negative while it slows). `[0, π/2]` is the range the paper's fits cover (single strokes at
α = 9°–90° with `ω > 0`, §2.5), extended down to `α = 0`. It is **this project's input contract**, not
a statement of how the paper treats a reversing wing: the measured kinematics in the paper's fig 1c
leave that range near stroke reversal, and the recipe the paper applied to them is in supplementary
text (S1.1) that is not published with the article. A component function SHALL raise `ValueError` naming the input
when **any element** of `α` lies outside `[0, π/2]` or, for the components that take `ω` (translational
and Wagner), any element of `ω` is negative: a signed geometric pitch is not a valid input. The
returned `F_x` and `F_z` are signed along the directions that oppose the wing's chord-wise and
wing-normal motion (the fitted tangential coefficient is itself slightly negative for roughly
58°–83°); mapping them onto the wing body axes on both half-strokes is the caller's job (see
"Angle-of-attack inputs for the van Veen model are derived from the wing's motion"). The functional
forms are:

- translational: `F_z = ½ρω²S_yy·C_Fzα_transl·sinα` (`C_Fzα_transl = 3.13`);
  `F_x = ½ρω²S_yy·(A·α_deg²+B·α_deg+C)` with `α_deg` the angle of attack in **degrees**
  (`A=8.5e-5, B=−1.2e-2, C=0.41`, eq 3.12). The paper does not print eq 3.12's unit; degrees is the
  reading that reproduces §3.1.1 (above 36° the tangential-to-normal ratio is −0.01 ± 0.01), §3.1.2
  (the coefficient decreases with angle of attack) and fig 4b. A code comment SHALL record this, and
  SHALL record that §4.4 restates the polynomial with different coefficients (`1.0e-4, −1.4e-2, 0.43`)
  while the pinned values are §3.1.2's
- added-mass: `F_z = ρω̇S_cy·C_Fzα_AM·sinα` (`C_Fzα_AM = 0.96`);
  `F_x = ρω̇S_cy·C_Fxα_AM·cosα` (`C_Fxα_AM = 0.104`) — **both** AM components use the chord-based `S_cy`
  (the paper's *fitted revised* model rebased the tangential AM on `S_cy`/viscous, NOT the analytic
  thickness-based `S_τy`; a code comment SHALL record this so it is not "corrected" back)
- Wagner: `F_z = ½ρω·sign(ω̇)·√|ω̇|·S_WE·C_Fzα_WE·sinα` (`C_Fzα_WE = −1.02`); `F_x = 0`

The added-mass coefficient `0.96` is the paper's **fitted** value (vs the analytic potential-flow
`π/4 ≈ 0.785`); T4 uses the fitted model. The pinned coefficients SHALL be verified against the erratum
**JFM 956 E1 (2023)** before they are trusted, and the verdict recorded as a testable provenance literal
(see "Erratum-verified coefficient provenance").

#### Scenario: Components equal hand-computed values at a reference state

- **Given** the model at `α = π/2`, instantaneous `ω = ω_ref`, `ω̇ = 0`, and the committed geometry moments
- **When** the three components are evaluated
- **Then** `F_z_transl = ½ρω_ref²S_yy·3.13`, `F_z_AM = 0` and `F_z_WE = 0` (both `∝ ω̇ = 0`), and the
  tangential `F_x_transl = ½ρω_ref²S_yy·(A·90²+B·90+C)` — each matching the hand-computed literal to
  floating tolerance

#### Scenario: Eq 3.12 is evaluated in degrees, checked against the paper's own statements

- **Given** the translational component at `ω = ω_ref` and `α` = 0°, 45° and 90° (passed in radians)
- **When** the tangential coefficient `F_x / (½ρω_ref²S_yy)` is evaluated
- **Then** it equals `0.41`, `0.042125` and `0.0185` to floating tolerance
- **And** at each of 45°, 54°, 63°, 72°, 81° and 90° its ratio to the normal coefficient `3.13·sinα` is
  below `0.03` in magnitude (the paper's §3.1.1 ratio above 36° is −0.01 ± 0.01; a radian evaluation
  gives more than 0.12 at every one of those angles and fails)
- **And** the coefficient at 9° is more than five times the coefficient at 45° (§3.1.2: it decreases
  with angle of attack)

#### Scenario: The model reproduces the paper's published fruit-fly normal force

- **Given** the committed `fruitfly.mat` and `wing_geometry_DB.mat` from the paper's supplementary
  database, whose SHA-256 values equal those recorded beside them, with every column cast to
  `float64`
- **When** the model functions are evaluated at every row's angle of attack, stroke rate and stroke
  acceleration with that wing's stored `Syy`, `Scy` and `Swe` and a density of 1
- **Then** no row raises, and the error `sqrt(Σ(model − data)² / Σ data²)` over all rows is below
  `0.03` for the normal force
- **And** a least-squares fit of the three normal terms to the same rows lands inside the pinned
  interval of each normal coefficient
- **And** the same error is below `0.25` for the tangential force, compared as `−Fx` (the dataset's
  x-axis points against the tangential force the model returns); this bound admits both of the
  paper's printed coefficient sets and is dominated by rows at 27° or less, so it guards the unit
  and the signs of the tangential terms, not their behaviour at higher angles
- **And** these bounds are regression bounds set after the results were seen; an added-mass term on
  `Syy` gives a normal error above `0.3`, a 6 % change in the translational normal coefficient
  gives a normal error above `0.03`, and a radian evaluation of eq 3.12 gives a tangential error
  above `1`

#### Scenario: total_force is exactly the sum of components, with boundary + non-finite guards

- **Given** the pure model functions
- **When** `total_force` is evaluated and boundary/degenerate inputs are supplied
- **Then** `total_force == translational + added_mass + wagner` component-wise (chord & normal) to float
  tolerance; at `ω̇ = 0` both AM and Wagner return exactly `0` (no `√`/`÷` error); and a non-finite
  `α`/`ω`/`ω̇` raises (matching the repo's no-silent-NaN posture)

#### Scenario: Coefficients are pinned constants with a not-loosened guard

- **Given** the module coefficient constants and their 95 % CIs
- **When** the guard test runs
- **Then** each coefficient equals its pinned value (`3.13`, `A/B/C`, `0.96`, `0.104`, `−1.02`) and its CI
  equals the pinned tuple; a widened coefficient **or** a widened CI **fails** the not-loosened test — the
  model cannot be silently retuned to pass (CC-V2)

#### Scenario: Wagner sign generalization is finite for decelerating wings

- **Given** a decelerating state `ω̇ < 0`
- **When** the Wagner normal component is evaluated
- **Then** it uses `sign(ω̇)·√|ω̇|` (van Veen eq 3.15/4.1), is **finite** (no `√` of a negative), and is
  **oppositely signed** to the accelerating case of equal `|ω̇|` — never `NaN`

#### Scenario: An input outside the model's input domain raises

- **Given** each of the three component functions
- **When** it is called with `α = −π/4`, with `α = nextafter(π/2, 4)`, with an array of valid values
  holding one out-of-range element, or (for the translational and Wagner components) with `ω < 0` as a
  scalar or as one element of an array
- **Then** it raises `ValueError` naming the offending input, and `total_force` raises for the same inputs
- **And** `α = 0`, `α = −0.0`, `α = π/2` and `ω = 0` are accepted, and `ω = 0` returns zero force
- **And** a non-finite `α` or `ω` still raises the non-finite error

### Requirement: Wing area-moments from a single hinge-origin quadrature

The analysis SHALL compute the wing area-moments from **one shared** `compute_wing_area_moments` function
using a **pinned integration convention**: `y` measured from the **stroke rotation (hinge) axis** (van
Veen's convention; the wing root sits at a hinge offset `d ≈ 1.5` from the wing's geometric centre, so
`r_gyr ≈ 1.6985` **about the hinge**). It SHALL emit:
- `S_yy = R_GYRATION²·area ≈ 6.797`, defined via the committed `R_GYRATION` (the *same* single source
  `compute_force_reference` uses for `F_ref`) — **NOT** re-derived as a marker `∫c·y²dy` quadrature (a raw
  chord-integral over the discrete markers gives `≈6.24` at 30 bins because the marker planform area ≠ the analytic
  elliptic area by ~7 %; the spec does **not** claim `S_yy` equals that quadrature);
- `S_cy = ∫c(y)²·y dy` (van Veen eq 1.8), the **chord-based** second moment — a different integral from
  `S_yy = ∫c(y)·y² dy`. It SHALL be the closed form of that integral for the nominal elliptic planform,
  `S_cy = (2/3)·chord²·span·(r_tip − span/2)`, which is `chord²·span²/3 = 3.0` for span 3, chord 1 and
  the root at the hinge. A code comment SHALL record that the paper's eq 2.11, evaluated as printed,
  gives `(π/8)·chord²·span² ≈ 3.53` because its integrand omits a factor, while the paper's fig 2e plots
  values that match `chord²·span²/3`; the closed form here follows eq 1.8 and fig 2e, and SHALL NOT be
  "corrected" to 3.53. A hinge-origin **marker** quadrature of the same integral SHALL be exposed as a
  cross-check; it is lower than the closed form because the marker planform is smaller than the nominal
  one in both chord and span, and it is reported, never fed to the model;
- the **new** `S_WE = ∫√(c³y³)dy ≈ 3.98` (`y > 0` throughout, so the `√` is real), computed by a
  hinge-origin marker quadrature and **cross-checked against a genuinely independent quadrature of an
  ellipse fitted to the marker extents** (a different integrator, not a re-binning — they agree to ~0.1 %); this
  independent-quadrature claim applies to `S_WE`, **not** to `S_yy`. A too-fine `nbins` (bins with ≤1
  marker) **raises** rather than silently under-estimating `S_WE`.
The existing inline `S_yy = r_gyr²·area` sites (`generate_validation_figures.py`,
`test_force_surrogate_normalization.py`) SHALL be refactored to call this one function (CC-V4 — a single
moment code path, not two). `S_WE` is a **fixed geometric constant** of the pinned planform, never tuned to
make a grade pass; the marker quadrature and the independent fitted-ellipse quadrature agree to ~0.1 %, so the
integration error feeding the `T4_NORMAL_MAG_TOL` budget is negligible and the budget is
grid-dominated. (The distinct `S_yy` uses the analytic-elliptic area for `F_ref` consistency; a marker
`∫c·y²dy` quadrature would give ~6.24 — a documented convention, not an uncertainty; `S_yy` is fixed.)

**The three moments do not share one planform basis.** `S_yy` is the marker radius of gyration squared
times the nominal area; `S_cy` is the nominal-ellipse closed form; `S_WE` is a marker quadrature (the
nominal ellipse gives a larger value). The basis SHALL NOT be chosen to make a grade pass: a test
SHALL recompute the fine-grid normal peak gap with the marker `S_cy` in place of the closed form and
with the nominal-ellipse `S_WE` in place of the marker value, and SHALL assert `normal_mag_pass` holds
under each. Wherever the docs quote the graded gap they SHALL state that the moments are on mixed
bases and SHALL NOT present the gap as a precision. Putting all three on one basis changes `F_ref` and
is tracked by a follow-up issue.

#### Scenario: S_yy reproduces the committed value under the hinge-origin convention

- **Given** the committed wing planform and the hinge-origin convention (y from the stroke axis, not the
  wing centre)
- **When** `compute_wing_area_moments` runs
- **Then** `S_yy ≈ 6.797` (`= R_GYRATION²·area`, reconciling the committed value); using
  the wing-**centre** origin instead would give the wrong `≈1.20`, so the test pins the hinge origin

#### Scenario: S_cy is the chord-based integral, with a known answer

- **Given** the nominal elliptic planform (span 3, chord 1, root at the hinge)
- **When** `compute_wing_area_moments` runs
- **Then** `S_cy = 3.0` to floating tolerance, it differs from `S_yy`, and it equals an independent fine
  numeric quadrature of `∫c(y)²·y dy` over the analytic ellipse to `1e-6`
- **And** with `r_tip = 4` (the same ellipse moved one chord outboard) the closed form gives `5.0`, and
  a planform with `r_tip < span/2` raises `ValueError`
- **And** the marker quadrature converges to the closed form on a synthetic ellipse outline of at least
  2e5 markers: its error is below 5 % at 30 bins, below 1.5 % at 120 bins, and smaller at 120 bins than
  at 30 (the estimator takes the widest chord in each bin, so it is biased high at finite bin count;
  the docstring SHALL say so)
- **And** the marker quadrature of the committed `wing.vertex` equals its pinned value, which lies below
  the closed form by less than 15 %
- **And** a too-fine `nbins` raises for the `S_cy` marker quadrature as it does for `S_WE`
- **And** `compute_wing_area_moments` raises `ValueError`, naming both values, when the marker
  quadrature of the wing file it was given differs from the closed form by more than 15 % (a
  rectangular outline of the nominal span and chord raises, and so does the committed wing with
  its chord scaled by 0.95; the committed wing and a nominal ellipse outline do not); the docstring
  SHALL say this catches gross planform errors only, and that a too-fine `nbins`, a missing wing
  file and a zero-area planform are reported by their own errors first
- **And** for each of the 14 wings in the committed `wing_geometry_DB.mat`, the module's own profile
  integrator (the one its marker quadrature calls) gives `∫c(y)²·y dy` and `∫√(max(c³y³, 0)) dy` of
  the stored chord profile equal to the stored `Scy` and `Swe` to `2e-3` relative, and
  the nominal `S_cy` over the nominal `∫c·y² dy` is within 1 % of the stored `Scy/Syy` of the paper's
  3 mm ellipse

#### Scenario: The graded verdict does not depend on the planform basis

- **Given** the fine-grid CSV and the corrected model
- **When** the normal peak gap is recomputed with the marker `S_cy`, and again with the nominal-ellipse
  `S_WE`
- **Then** `normal_mag_pass` holds under each, and the three gaps are pinned in the test

#### Scenario: S_WE is an independent quadrature, cross-checked

- **Given** the same planform + convention
- **When** `S_WE = ∫√(c³y³)dy` is computed
- **Then** it matches an **independent** numeric quadrature of the committed planform to tolerance (a
  genuine known-answer, not a re-read of a stored constant), and a degenerate (zero-area) planform raises
  `ValueError`

### Requirement: Per-component decomposition of the CFD force, graded against van Veen's model

The analysis SHALL provide `decompose_wing_force(csv_path, *, f_star, phi_amp_deg, pitch_amp_deg,
window_t0=STEADY_WINDOW_T0, …)` that builds van Veen's per-component + total model on **our** wing
kinematics, normalizes each by the single-source `compute_force_reference` built at the model's density
`rho` (`F_ref = ½ρω_ref²S_yy`, 200.27 at `ρ = 1`; the same reference formula as the CFD `CF`; no
correction factor), so the model coefficients, like the CFD's, do not depend on the density, aligns to the CFD time grid from
`reconstruct_wing_body_forces` (reused, not re-derived, CC-V4), and grades / reports the comparison over
the pinned steady window. It SHALL be **cluster-free** (committed CSVs) and FP64. The CFD series is the
IB force on the wing, `ib_w`.

The model SHALL be fed van Veen's **angle of attack**, not the signed geometric pitch, through the
shared input derivation (see "Angle-of-attack inputs for the van Veen model are derived from the
wing's motion"); each model component's `F_x` and `F_z` SHALL be multiplied by that derivation's chord
and normal direction signs, for the components and for the total alike, before normalization.

Because both sides share the **same** kinematics and `F_ref`, the graded claim is **"consistent with /
validated against van Veen's quasi-steady model at matched kinematics — in peak magnitude"** — a
plausibility result against the literature-standard model, **not** an independent validation of the
per-component split (the CFD gives only the total). The graded oracle SHALL rest on the normal **peak
magnitude** (the robust, `S_WE`-insensitive lever) and the **decomposition-closure identity**. The normal
**peak phase**, the normal **curve RMSE**, the signed normal and chord **curve correlations**
(`normal_curve_corr`, `chord_curve_corr`), the translational-chord magnitude and the chord total curve
SHALL be **reported, not gated** (CC-V2). The **one** graded magnitude tolerance SHALL be a **named,
test-guarded constant** derived from **sourced** quantities (van Veen coefficient 95 % CIs ⊕ the
measured coarse↔medium grid spread ⊕ the small `S_WE` geometric uncertainty) and never reverse-fit
(CC-V2). The tolerance was pinned before the first committed-run result. A later correction to the
model is graded against the same constant, with its result already known, so the constant SHALL NOT
be changed to accommodate a model result. The magnitude grader SHALL be proven on synthetic
fixtures to **pass within and fail outside** `T4_NORMAL_MAG_TOL` (both directions). The return value
SHALL expose **no** chord, phase, RMSE or correlation `*_pass`/`*_match` verdict key — its `*_pass`
keys are exactly `normal_mag_pass` and `closure_pass` — and its key set SHALL be exact/enumerated (a
later-added gate fails a guard). A correlation over a series whose standard deviation is below
`_DEGENERATE_CF_FLOOR` SHALL raise `ValueError`, never return NaN. A `rho` that is not a finite,
positive, normal real number SHALL raise `ValueError` naming `rho` before any file is read, and a
`rho` large enough that the model's `F_ref` or any model force overflows SHALL raise `ValueError`
naming `rho`, never return an `inf`/NaN number.

#### Scenario: Normal peak MAGNITUDE is the primary graded lever (S_WE-insensitive)

- **Given** the model-total `CF_normal(t)` and the CFD `CF_normal(t)` over the steady window
- **When** the normal peak-magnitude grade is computed
- **Then** the **relative** peak gap `|model_peak − cfd_peak| / cfd_peak` is within `T4_NORMAL_MAG_TOL` (a
  **relative/fractional** tolerance, units-consistent with the grid GCI) on the flagship T3c fine-256³
  CSV (the production comparison) and on the T2a coarse CSV; the gap on the medium CSV is **reported**.
  All three gaps are pinned in the reproducibility test at `abs = 5e-4`. Together with the chord pins
  they fail under the reversion of any one model correction: the gap pins catch a reverted `S_cy`, the
  chord pins catch a radian eq 3.12, and a signed pitch raises. The term is `S_WE`-**insensitive**; a synthetic
  series offset in magnitude beyond the tolerance **fails** (both directions), and widening
  `T4_NORMAL_MAG_TOL` flips a not-loosened test

#### Scenario: Normal peak phase, curve RMSE and curve correlation are reported, not gated

- **Given** the same normal and chord series
- **When** the peak-phase gap, the signed curve RMSE and the signed curve correlation are computed
- **Then** they are **reported** (no pass/fail tolerance): the normal peak-phase gap is reported with its
  confounds (QS-vs-unsteady wake-memory omission + grid non-convergence + single-wingbeat transient),
  and the normal RMSE and the normal and chord Pearson correlations between the signed model and CFD
  series are returned as plain numbers — none is gated, so none can be reverse-fit
- **And** negating the CFD series negates both correlations exactly and doubling it leaves them unchanged
- **And** the correlation helper, called directly with a constant series, raises `ValueError`

#### Scenario: Translational-chord is a known-answer self-consistency check, not a gate

- **Given** the model's translational-tangential peak `CF` on our kinematics
- **When** it is reported
- **Then** it equals the **window peak** of `(φ̇/ω_ref)²·(A·α_deg²+B·α_deg+C)` over the steady window,
  which falls away from mid-stroke because the polynomial rises as the angle of attack drops; it is
  pinned against an independent dense-grid maximum of that expression, and is distinct from the
  mid-stroke value `0.042125` — **reported, not graded**. The analysis SHALL NOT reuse
  `VAN_VEEN_CF_TARGETS["cf_chord_peak"]` as a chord gate

#### Scenario: Decomposition closure is an exact identity (graded)

- **Given** the per-component model series (translational, added-mass, Wagner)
- **When** they are summed
- **Then** the sum equals the reported `model_total` (chord and normal) to floating tolerance

#### Scenario: Chord total curve is reported with the grid band and the convergence direction

- **Given** the model-total `CF_chord(t)` and the CFD `CF_chord(t)` on the coarse **and** medium CSVs
- **When** `medium_csv` is supplied and the chord comparison is reported
- **Then** it is emitted **with** `T4_CHORD_GCI_BAND` (asserted **equal** to the committed T3b chord GCI via
  the reused `wing_grid_convergence_from_body_forces`, not a re-typed literal) and **no** chord
  `*_pass`/`*_match` key, and it reports the direction flag `chord_converges_toward_model` as a plain
  boolean meaning only "the medium CFD peak is closer to the model peak than the coarse CFD peak is".
  The docs SHALL state the model chord peak and the CFD chord peak side by side, naming the grid, and
  SHALL NOT call the chord explained by the model or say it converges to the model

  **Caveat (T3c, fine-grid production usage):** `medium_csv` is **optional** and this 2-grid band is
  **report-only**, exercised directly by the coarse/medium fixture in `test_wing_force_decomposition.py`.
  `medium_csv` MUST NOT be paired with a `csv_path` that is **finer** than it — `wing_grid_convergence`
  treats `csv_path`'s role as "coarse" unconditionally, so pairing a finer grid as `csv_path` against a
  coarser `medium_csv` **inverts** the convergence-direction sign. Once the fine 256³ grid
  (`forces_fine.csv`) became the flagship CFD comparison (T3c), the production caller
  (`make_force_decomposition_figure.py`, `test_t4_decomposition_numbers_reproduce`) stopped passing
  `medium_csv` for exactly this reason — `chord_gci_band`/`chord_converges_toward_model` are `None` in
  that call — and RESULTS.md instead reports the separately-computed T3c 3-grid Richardson/`GCI_fine`
  numbers (`wing_grid_convergence_3grid`) as the authoritative grid-uncertainty figure for the chord.

#### Scenario: The magnitude tolerance derives from its sourced inputs (not reverse-fit)

- **Given** the committed T3b normal grid GCI (via the reused convergence helper), the pinned
  coefficient-CI band, and the `S_WE` geometric-uncertainty term **recomputed** from the marker-vs-analytic
  `S_WE` difference propagated through the Wagner share (**not** a typed literal)
- **When** `T4_NORMAL_MAG_TOL` is checked against its sourced quadrature recomputed from those inputs
- **Then** the recomputed `S_WE` term is non-zero (the test's substituted quadrature took effect), and
  the tolerance is **≥** its derived floor (the quadrature of the three terms, recomputed by the test from
  the model) and **≤** a small rounding margin above it — a tolerance loosened past its sourced budget **fails** — making "pinned from sourced
  quantities, before the result" enforceable rather than aspirational (CC-V2); and `T4_CHORD_GCI_BAND` is
  asserted **equal** to the committed T3b chord GCI from the helper (a reported band, not a typed literal)

#### Scenario: End-to-end on the committed coarse CSV reproduces the known peaks

- **Given** `forces_t2a_newconv.csv` (29-col, with `SumU{x,y,z}`) and the analytic `R(t)`
- **When** `decompose_wing_force` runs
- **Then** the CFD side reproduces the T2a coarse peaks (`CF_chord ≈ 0.92`, `CF_normal ≈ 2.61`) via the
  reused `reconstruct_wing_body_forces` (not re-derived), and the per-component model + total are returned
  on the same time grid, with an exact/enumerated key set (no chord verdict key)

#### Scenario: Malformed input raises, never a silent coefficient

- **Given** a CSV missing a required column, a non-finite `ib_force`/`SumU` row, or a `window_t0` selecting
  no timesteps
- **When** `decompose_wing_force` runs
- **Then** it raises `ValueError` (mirroring the existing decomposition guards) — never a silent `NaN`

#### Scenario: The model's density cancels, so no T4 number or verdict depends on it

- **Given** `forces_fine.csv` and the production kinematics (`f_star = 1`, `phi_amp_deg = 70`,
  `pitch_amp_deg = 45`)
- **When** `decompose_wing_force` runs at `rho = 0.5`, `2` and `1.3`, and at `rho = 1`
- **Then** every returned number, every `*_pass` verdict and every `series` array equals its `rho = 1`
  value (exactly at the powers of two, to `1e-12` relative at `1.3`); a model that did not cancel the
  density would double its normal peak at `rho = 2` and flip `normal_mag_pass`
- **And** a `rho` of `0`, a negative value, NaN, infinity, a boolean, `None`, a string, `10**400`,
  `Decimal("1")`, a 0-d array or a subnormal raises `ValueError` naming `rho`, also when the CSV path
  does not exist
- **And** `rho = 5e305` (the model forces overflow while `F_ref` is finite) and `rho = 1e308` (`F_ref`
  overflows) raise `ValueError` naming `rho`

### Requirement: Flapping-wing coefficients report the IB force on the wing

The flapping-wing analysis SHALL report every coefficient series it derives from the IB-particle CSV
as the IB force **on the wing** (`ib_w = −ib_force`). That covers:

- the lab-frame `cf_*_ib`;
- the body-frame `CF_chord`/`CF_normal`;
- the T4 **CFD** series;
- both series of the added-mass-subtracted diagnostic;
- the figure scripts that compute coefficients directly from the CSV
  (`generate_all_figures.plot_f1_forces`, `generate_validation_figures.fig_v1_three_convention`).

Each is obtained through the force-surrogate's single-source `force_on_wing` helper (see the
force-surrogate requirement "Wing coefficients report the IB force and moment on the wing").

Where other requirements in this capability speak of coefficients "of `ib_force`", or of the CFD
"total" force, they mean `ib_w`. The solver's 6-DOF force `ρ_f·(SumU + ib_w)` is always named "6-DOF".
Raw-force values that `RESULTS.md` quotes SHALL remain the solver's values and SHALL be labelled as
the force on the fluid.

Every magnitude-graded verdict SHALL be unchanged by this convention, because each grades `|·|`:
`plausibility_gate`, `body_frame_overall_match`, the T4 `normal_mag_pass` and `closure_pass`, and the
peak phases. Reported signed quantities SHALL be recomputed from committed data, never hand-edited:
the lab ranges, the T4 `normal_curve_rmse` and curve correlations, and the added-mass-subtracted `drop_frac`.

The `forces` subcommand of `examples/flapping_wing/visualize.py` SHALL be removed. It summed plotfile
marker increments rather than the accumulated `ib_force`, and labelled `Fy` as lift (pre-T2a axes).

#### Scenario: Lab and body coefficients are on-wing

- **Given** the committed `forces_t2a_newconv.csv`
- **When** `reconstruct_wing_forces` and `reconstruct_wing_body_forces` run
- **Then** `cf_x_ib == −Fx/f_ref` and `cf_z_ib == −Fz/f_ref`, and the body-frame series equal `R(t)ᵀ` applied to `−F`, divided by `f_ref`

#### Scenario: Graded verdicts are unchanged by the sign

- **Given** the committed CSVs
- **When** `plausibility_gate`, `body_frame_overall_match` and `decompose_wing_force` run on the on-wing series
- **Then** each graded verdict equals its verdict on the on-fluid series, because each grades a magnitude. The independent pin is the CFD-side literals in `tests/test_wing_body_frame.py` and in the T4 decomposition tests (the CFD peaks), not a recomputation by the code under test.

#### Scenario: The forces subcommand is gone

- **Given** `examples/flapping_wing/visualize.py`
- **When** its argument parser is built
- **Then** its subcommands are exactly `velocity` and `vorticity`

### Requirement: T4 decomposition figure, RESULTS, and roadmap state what the corrected model supports

A **cluster-free** figure `fig_force_decomposition` SHALL plot, for chord and normal separately, van
Veen's model translational / added-mass / Wagner / total curves against the CFD total over the steady
window, regenerated from the committed fine-grid CSV at our operating point, with the model fed the
angle of attack. The figure SHALL NOT carry a note that the model's sign convention is pending a fix.

`examples/flapping_wing/RESULTS.md` is the **single place** where the T4 numbers are stated. Its T4
subsection SHALL state, with every number recomputed from the committed CSVs by a test:

- the **normal** force is **validated against van Veen's quasi-steady model in peak magnitude** (graded:
  the relative gap and the tolerance), a consistency claim at matched kinematics, not a bare "validated";
- the normal peak-phase gap, the signed curve RMSE and the signed curve correlations (**reported**);
- the **chord** (**reported**): the model chord peak and the CFD chord peak side by side, naming the grid;
- the limits of the comparison: the model peak and the CFD peak fall at different phases; the CSVs cover
  the first wingbeat from an impulsive start; the wing moments are on mixed planform bases; the paper
  gives two coefficient sets for eq 3.12 and the chord outputs depend on which is used, while the graded
  normal does not; and the model's input recipe for a reversing wing rests on the paper's fig 1c–e and
  §3.3, the supplementary text S1.1 that describes it not being published with the article.

`RESULTS.md` SHALL NOT state that the `CF_chord` PARTIAL (#40) is resolved, closed or explained by T4,
SHALL NOT say the CFD chord converges to the model, SHALL NOT present the gap or a correlation as
confirming any single model component, and SHALL NOT mark any T4 statement as pending the model fix. It
SHALL point to the open issue that tracks the chord gap. Its sections that compare against
`VAN_VEEN_CF_TARGETS` SHALL call those values the T2a targets, not van Veen's translational
coefficients, and SHALL carry one note, under the first T2a table, that the constants are under review
in a named follow-up issue and are not the paper's eq 3.9 / eq 3.12 values; the T2a verdicts are not
re-graded. `RESULTS.md` SHALL keep the T3b "Grid convergence" section and the added-mass-subtracted
interim subsection, and SHALL list the figure in its Output Files table.

Every other document that mentions the T4 result — `examples/flapping_wing/figures/README.md`,
`docs/aerodynamics_validation/roadmap.md`, `examples/prelim_sweep_fine/README.md`,
`docs/force_surrogate/roadmap.md`, `docs/force_surrogate/fine-grid-pilot-report.md` and
`docs/CHANGELOG.md` — SHALL give the verdict in words, SHALL NOT contradict `RESULTS.md`, and SHALL NOT
quote a T4 model number that the model does not produce. Unreleased CHANGELOG entries that state a
superseded T4 result SHALL be corrected, not annotated. Comments and docstrings in `src/` and `tests/`
are held to the same rule. `docs/coordinate-convention.md` and the `flapping_wing.py` module docstring
SHALL describe the T4 decomposition as delivered (no "deferred to T4", no "rotational drag" framing).
The dated reconciliation log in `docs/aerodynamics_validation/roadmap.md` is a record of past decisions:
it is not rewritten, and it SHALL carry a dated addendum pointing to the current T4 result.

`docs/aerodynamics_validation/roadmap.md`'s T4 row SHALL keep its ✅ and PR references, the
`translational + added-mass + Wagner` wording (never "rotational"), the Fig 13 citation (no instruction
to digitize van Veen's Fig 3–4; a negated mention is allowed), and the reconciliation-log note that the normal peak **phase** is
reported-not-gated as an evidence-based scoping decision, NOT a loosened tolerance.

#### Scenario: Decomposition figure regenerates cluster-free from committed data

- **Given** the committed `forces_fine.csv` and the van Veen model
- **When** `fig_force_decomposition` is generated
- **Then** it shows the model translational / added-mass / Wagner / total vs the CFD total for **both**
  chord and normal over the steady window, written as `.pdf` + `.png` (Agg backend), with **no**
  cluster/plotfile dependency, and `RESULTS.md`'s Output Files table has a row for it
- **And** the plotted model-total normal curve is the `model_normal` series `decompose_wing_force`
  returns, and it is positive throughout the phase bands `[0.4, 0.6]` and `[0.9, 1.0)`
- **And** no text in the figure mentions a pending model-sign issue

#### Scenario: RESULTS.md states the graded normal, the reported chord and the limits, and keeps T3b intact

- **Given** the regenerated `RESULTS.md`
- **When** it is inspected
- **Then** the wing Validation-Status row reads **validated against van Veen's quasi-steady model** for
  the normal peak magnitude and gives the chord as reported, not explained by the model; the
  decomposition numbers recompute from the committed CSVs; the T4 subsection states each limit listed in
  this requirement and names the open chord issue; the T2a note is present and names its follow-up
  issue; the "Grid convergence (T3b)" section and the added-mass-subtracted interim subsection remain
  present; and no post-hoc correction factor is introduced

#### Scenario: Claims the corrected model no longer supports are absent from every doc

- **Given** `RESULTS.md` and the six other documents this requirement names, and the comments and
  docstrings of `src/mosquito_cfd/benchmarks/flapping_wing.py`
- **When** a guard test scans each after removing Markdown emphasis and code marks, collapsing all
  whitespace (so a phrase split across lines or wrapped in bold is still found), lower-casing, and
  splitting into sentences
- **Then** no sentence that lacks a negation states that T4 or the model resolves, settles, explains
  or accounts for the chord PARTIAL or #40, that the chord sits close to or converges to the model,
  that the earlier comparison was "apples-to-oranges", or
  names a "physical chord target" or a "QS-model target"
- **And** no sentence at all contains: a pending-#133 marker in either word order; a statement that
  #40 is closed, resolved or done; "should never have been compared"; "roughly cancel"; "full QS model total"; a "0.3–0.43" chord
  range; the "115 %" and "4–5 %" off-model-target figures; or a superseded model number as a whole
  number (`2.48`, `0.43`, `0.42` not preceded by a minus sign, `0.055`, `0.058`, and "near 0.18")
- **And** negated statements are accepted, because the docs are required to make them: "does not
  resolve", "does not fully resolve", "remains unresolved by", "neither resolved by T4 nor explained
  by the model", "not fully explained by the model"
- **And** the guard cannot pass on an empty or unrelated document: each document is asserted to exist
  and to contain its own anchor (`RESULTS.md`: the T4 subsection header and "#40 is open";
  `figures/README.md`: `fig_force_decomposition`; the aerodynamics roadmap: its T4 row; the
  fine-corpus README: a link to the `RESULTS.md` T4 subsection; the two force-surrogate documents:
  `CF_chord`; the CHANGELOG: its entry for this change)
- **And** the aerodynamics roadmap is scanned without its dated reconciliation log, which is located by
  its header and asserted found; the log's dated T4 phase subsection carries a line marking its
  phase-gap figure superseded, and a test asserts that line
- **And** the guard is proven to fail when each forbidden form, in plain, bold and line-wrapped
  variants, is restored to each document in turn, and when each anchor is removed

#### Scenario: Roadmap T4 row keeps its delivered framing

- **Given** `docs/aerodynamics_validation/roadmap.md`
- **When** the T4 row, the oracle table and the reconciliation log are read
- **Then** the row carries ✅ and its PR references, says `translational + added-mass + Wagner` (never
  "translational + rotational + added-mass"), cites Fig 13, contains no instruction to digitize van
  Veen's Fig 3–4 (negated mentions such as "not a digitized curve" are allowed), and the log keeps the
  phase-reported-not-gated note and carries the dated addendum
- **And** `docs/coordinate-convention.md` and the `flapping_wing.py` module docstring contain no
  "deferred to T4" and no "rotational drag" framing of the decomposition
