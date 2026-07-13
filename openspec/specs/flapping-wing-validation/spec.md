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

The flapping-wing validation SHALL grade an **order-of-magnitude plausibility gate** on the accumulated
immersed-boundary force `ib_force` (`Fx/Fy/Fz`) **alone** — the added-mass term SHALL NOT be required for
the gate to pass (it is reported separately). Over a pinned, documented steady window, the band
`VAN_VEEN_BAND` SHALL be graded as a **lower-bound O(1) sanity floor**: the peak lab-frame magnitudes
`max|CF_x|` and `max|CF_z|` (van Veen convention, no correction factor) SHALL each be **≥ the band floor
`0.5`** — the check that catches an under-produced / mis-normalized coefficient (it flagged the old
peak-tip normalization at `CF_z ~0.22 < 0.5`). The **band ceiling `1.5` SHALL be reported, not gated**: a
per-component peak **above** `1.5` is **expected** under the corrected motion and is **not** a failure,
because van Veen's own body-frame normal coefficient (~2.4) also exceeds `1.5` (see the committed
`figures/fig_forces.png`, new-convention lab `max|CF_x| = 2.37`). The `VAN_VEEN_BAND` constant `(0.5, 1.5)`
and its not-loosened guard SHALL remain **unchanged** — this is a **grading-role** change (two-sided gate →
lower-bound floor), **not** a loosening. The rotation-invariant resultant `|CF| = sqrt(CF_x² + CF_z²)`
SHALL be reported as the frame-honest companion, and the `CF_z` floor margin (distance above `0.5`) SHALL
be reported. The **faithful per-component van Veen comparison is the body-frame decomposition** (see
"Body-frame (chord/normal) per-component van Veen comparison"), not the lab-frame band; the lab band is a
floor/sanity only. The regenerated `RESULTS.md`/figures SHALL disclose the lab band as an O(1) floor.
**Validation of the wing-normal against van Veen's quasi-steady model is delivered by Tier T4** (the
per-component decomposition — normal **peak magnitude** graded; peak **phase** and curve RMSE **reported**;
see "Per-component decomposition of the CFD force, graded against van Veen's model"); the **chord** total
curve is grid-limited and is **reported, not gated** (#50). The lab band remains a floor/sanity only and
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
  consequence of the corrected motion (consistent with van Veen's body-frame normal ~2.4 also exceeding
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
  quasi-steady model in **peak magnitude**; peak phase + RMSE reported; chord explained and grid-limited,
  #50), and do **not** present the lab band itself as the time-resolved validation

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
`[0.5,1.5]` as a floor that SHALL NOT be loosened. The **normal** peak matches van Veen's reported overall
normal (`~2.4`) within `VAN_VEEN_MATCH_TOL` (`cf_normal_match = True`). The **chord**'s prior scalar-match
against van Veen's *translational-only* `~0.3` (`cf_chord_match = False`, the T2a **PARTIAL**) is
**superseded by the Tier T4 decomposition**: the total chord is an apples-to-oranges comparison to a
translational-only number, and T4 shows the total should be compared to van Veen's `transl + AM + Wagner`
(see "Per-component decomposition of the CFD force, graded against van Veen's model"). The coarse peak
`CF_chord ≈ 0.92` remains reproducible and its `cf_chord_match = False` scalar result is unchanged; only its
**interpretation** is resolved (#40), with the residual **grid** sensitivity tracked by **#50**. The
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

#### Scenario: Normal scalar-match graded; chord PARTIAL superseded by the T4 decomposition

- **Given** the body-frame series and van Veen's reported overall values pinned as the named constant
  `VAN_VEEN_CF_TARGETS` with tolerance `VAN_VEEN_MATCH_TOL`
- **When** the tolerance match is computed
- **Then** peak `|CF_normal|` falls within `VAN_VEEN_MATCH_TOL` of the normal target (`cf_normal_match =
  True`); the grader is proven on synthetic fixtures to **pass within and fail outside** (both directions);
  and the **chord** `cf_chord_match = False` (peak `≈0.92` vs the translational-only `~0.3`) is **not**
  re-graded here — it is **superseded** by the T4 decomposition, which compares the total chord to
  `transl + AM + Wagner` and reports the translational-only `0.3` as the wrong (apples-to-oranges) target.
  `VAN_VEEN_CF_TARGETS` and `VAN_VEEN_MATCH_TOL` remain named, test-guarded constants (a loosened tolerance
  fails a not-loosened test)

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

### Requirement: RESULTS.md headline numbers reproducible from committed CSVs (issue #3 re-validation)

Every **headline number** in `examples/flapping_wing/RESULTS.md` SHALL be **recomputable** from the
committed force CSVs over the stated steady window, via the single-source `compute_force_reference` /
`compute_force_coefficients`, the body-frame decomposition, the `added_mass_fraction` RMS helper, the
added-mass-subtracted body-frame interim diagnostic (`body_frame_added_mass_subtracted`, #40), **and the
Tier T4 per-component decomposition (`decompose_wing_force`)** — with **no** value transcribed that the
committed data cannot regenerate. The new-convention headline numbers SHALL recompute from
`forces_t2a_newconv.csv` (`F_ref = 200.27`, `t ≥ 0.05`); the contrast-baseline numbers from `forces.csv`.
The recomputation SHALL respect each number's **definition**: coefficient ranges/peaks via
`compute_force_coefficients`; the phase-table `Fz` are **raw forces** read at the named `time` rows (not
coefficients); the added-mass fractions are the **RMS** `added_mass_fraction` values (stroke ~37 % / lift
~29 %); the added-mass-subtracted interim numbers are the total→subtracted body-frame peaks, their % drops,
and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %); **the T4 decomposition numbers are
the per-component + total model coefficients, the graded normal peak magnitude (≈2.48 vs CFD ≈2.61), the
reported normal peak-phase gap (~0.058 cycle) and curve RMSE, and the known-answer translational-chord peak
(≈0.42)**. The enumeration of checked numbers SHALL be **asserted complete** — a
RESULTS.md headline number absent from the enumeration fails the test; **the interim subsection's and the
T4 subsection's distinct numbers SHALL be enumerated / asserted-complete in their own guards** (separate
from the two existing headline tables, so their extra-precision totals do not collide). To keep that
separation load-bearing, the interim and T4 subsections SHALL each use a **distinct `### ` header** whose
text does **not** contain the substrings `lab-frame magnitudes` or `Body-frame per-component van Veen
comparison` (the two the existing `test_headline_tables_enumeration_complete` scans by exact-set-equality),
and SHALL **not add or alter any numeric cell inside those two enumerated tables**; a test SHALL confirm the
existing enumeration guard still passes unchanged. A test SHALL assert this reproducibility **before** any
RESULTS.md edit, and SHALL stand as the **durable regression guard** that closes issue #3 (whose original
`+0.431` defect is superseded by the T2a regeneration — T2b/T4 re-validate the **current** document).

#### Scenario: Lab-frame ranges recompute from the committed new-convention CSV

- **Given** `forces_t2a_newconv.csv` and the van Veen `F_ref = 200.27` from `compute_force_reference`
- **When** the lab-frame coefficients are computed over `t ≥ 0.05`
- **Then** `CF_x` range ≈ `[−2.35, +2.37]`, `CF_z` range ≈ `[−1.46, +0.03]`, `max|CF_x| ≈ 2.37`, and
  `max|CF_z| ≈ 1.46` — each matching the RESULTS.md headline as pinned literals to the documented precision

#### Scenario: Body-frame peaks recompute and are interpreted by the T4 decomposition

- **Given** the same committed CSV and the analytic `R(t)` from the wing kinematics
- **When** `body_frame_overall_match` is evaluated against `VAN_VEEN_CF_TARGETS` / `VAN_VEEN_MATCH_TOL`
- **Then** peak `CF_normal ≈ 2.61` (`cf_normal_match = True`) and peak `CF_chord ≈ 0.92`
  (`cf_chord_match = False`) recompute unchanged from committed data — and the **T4 decomposition now
  interprets** them: the total-chord ≈0.92 is compared to van Veen's `transl + AM + Wagner` (not the
  translational-only ≈0.3), so the coarse numbers are unchanged while their **interpretation** is
  **resolved** (#40); the remaining chord grid sensitivity is tracked by **#50**

#### Scenario: Interim added-mass-subtracted numbers recompute and are asserted present

- **Given** `forces_t2a_newconv.csv` and the `body_frame_added_mass_subtracted` diagnostic over `t ≥ 0.05`
- **When** the interim subsection's numbers are recomputed
- **Then** total→subtracted peaks (`0.923 → 0.652` chord, `2.606 → 2.285` normal), the % drops (≈ −29 % /
  −12 %), and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %) recompute from the committed
  CSV and appear in `RESULTS.md` as pinned literals; the total peaks additionally equal
  `body_frame_overall_match`'s `peak_cf_chord`/`peak_cf_normal` (the "same peaks" cross-check); the interim
  subsection's distinct numbers are **asserted complete** (a new interim number absent from the enumeration
  fails); the doc's "same peaks" note and the body-frame-vs-lab-frame disambiguation sentence are asserted
  present; and the guard runs **before** the doc edit while the existing
  `test_headline_tables_enumeration_complete` still passes unchanged

#### Scenario: T4 decomposition numbers recompute and are asserted present

- **Given** `forces_t2a_newconv.csv` and `decompose_wing_force` over `t ≥ 0.05`
- **When** the T4 subsection's numbers are recomputed
- **Then** the per-component + total model coefficients, the graded normal peak magnitude (≈2.48 vs CFD
  ≈2.61), the reported normal peak-phase gap (~0.058) and curve RMSE, and the known-answer
  translational-chord peak (≈0.42) recompute from the committed data and appear in `RESULTS.md`
  as pinned literals; the T4 subsection uses a distinct `###` header (not containing the two scanned
  substrings) and adds/alters no cell in the two existing enumerated tables; the T4 subsection's distinct
  numbers are **asserted complete** (a new T4 number absent fails); and the existing headline-table and
  interim enumeration guards still pass unchanged

#### Scenario: Every stated headline value has a committed-data source, by its own definition

- **Given** the RESULTS.md headline numbers — CF ranges/peaks (coefficients), the phase-table `Fz` (raw
  forces at named `time` rows), the body-frame `2.61`/`0.92`, the RMS added-mass fractions (~37 %/~29 %),
  the added-mass-subtracted interim peaks/drops/shares (`0.652`/`2.285`; ~84 %/~13 %), **the T4
  per-component + total coefficients and the translational-chord ≈0.42** — and the contrast-baseline numbers
  (`1.41`/`0.68` from `forces.csv`)
- **When** the reproducibility test runs
- **Then** each number recomputes from its committed CSV **by the correct definition** (coefficient vs raw
  force vs RMS fraction vs added-mass-subtracted diagnostic vs T4 decomposition) within the documented
  tolerance; any number that cannot be regenerated — or any headline number missing from the
  asserted-complete enumeration — fails the test; and the test passes **before** RESULTS.md is edited, so
  the doc is proven against live data, not curated

### Requirement: Added-mass-subtracted body-frame CF diagnostic (reported; #40 cheap interim)

The flapping-wing analysis SHALL provide a **reported** diagnostic that subtracts the logged added-mass
force (`ρ_f·SumU`, via the existing `added_mass_force`, #36) from the total `ib_force`, rotates the
remainder into the instantaneous wing body frame with the **same** analytic `R(t)` and
`body_frame_coefficients` the T2a body-frame decomposition uses (CC-V4 — the rotation and the added-mass
magnitude are **reused, not re-derived**), and reports, over the pinned steady window
(`STEADY_WINDOW_T0`), the peak `|CF_chord|`/`|CF_normal|` for **both** the total and the
added-mass-subtracted force (each peak the **independent** window argmax of its `|series|`, since on this
data the chord total and subtracted peaks fall at different phases), their **signed peak-to-peak** drop
fraction (`drop_frac = 1 − peak_subtracted/peak_total` — negative if subtraction raises a peak, not unsigned
in general), and the **body-frame added-mass RMS share** per component (`rms(CF_added,body)/rms(CF_ib,body)` — the
body-frame analog of the lab-frame `added_mass_fraction`). Because it rotates the **full 3-D** force and
added-mass vectors, the diagnostic SHALL read `time, Fx, Fy, Fz, SumUx, SumUy, SumUz`;
no single existing required-column set covers all seven (`_REQUIRED_CSV_COLUMNS` lacks `Fy` and `SumUy`;
`_REQUIRED_BODY_CSV_COLUMNS` lacks the `SumU*` columns; `SumUy` is in **neither**), so the diagnostic SHALL
define its **own** required-column set including them and raise if **any** one is missing. The diagnostic SHALL be **cluster-free** (the committed
`forces_t2a_newconv.csv`, 29-col with `SumU{x,y,z}`; CC-V3) and normalized by the single-source
`compute_force_reference` (`F_ref = ½ρω²S_yy`; no correction factor).

The diagnostic SHALL be **reported, not graded**: it SHALL NOT introduce any new pass/fail against van
Veen for the subtracted value (CC-V2). Its return value SHALL expose **no** `*_match`/`pass`/`floor`/
`in_band` verdict field, and the existing graders — `plausibility_gate` (lab `ib_force`) and
`body_frame_overall_match` (body `ib_force` vs `VAN_VEEN_CF_TARGETS` at `VAN_VEEN_MATCH_TOL`, floor
`VAN_VEEN_BAND`) — SHALL remain **unchanged**; a subtracted value cannot re-grade van Veen.

The analysis and docs SHALL frame the drop as **isolating the added-mass share**, NOT as (by itself)
resolving the `CF_chord` PARTIAL: the added-mass-subtracted `CF_chord ≈ 0.652` remains ~2× van Veen's
translational ~0.3. That residual is **resolved by the Tier T4 per-component decomposition** (van Veen's
`transl + AM + Wagner`; see "Per-component decomposition of the CFD force, graded against van Veen's
model"), which **closes #40**; the chord's remaining **grid** sensitivity is tracked by **#50**. Where
`RESULTS.md` reports the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %), it SHALL
**explicitly disambiguate** them from the already-reported **lab-frame** added-mass RMS fractions (stroke
~37 % / lift ~29 %, from `added_mass_fraction`): they are a **different frame *and* axis pairing** (lab
stroke/lift are `rms(cf_added)/rms(cf_ib)` in `x`/`z`; body chord/normal are the same ratio *after* rotation
by `R(t)`), and **neither supersedes the other**. Malformed input (missing any of the required columns —
including `Fy`/`SumUy` — a non-finite row, or an empty steady window) SHALL raise `ValueError`, mirroring
the existing decomposition guards (never a silent NaN coefficient).

#### Scenario: Added-mass subtracted then rotated reproduces the interim peaks (committed data)

- **Given** `forces_t2a_newconv.csv` (29-col, with `SumUx/SumUy/SumUz`), `ρ_f = RHO = 1.0`, the analytic
  `R(t)` from the wing kinematics, and `F_ref` from `compute_force_reference`
- **When** the diagnostic subtracts `ρ_f·SumU` from `ib_force` and rotates the remainder into the wing body
  frame over `t ≥ 0.05`
- **Then** peak `|CF_chord|` drops `0.923 → 0.652` (≈ −29 %) and peak `|CF_normal|` drops `2.606 → 2.285`
  (≈ −12 %), reproduced from the committed CSV; the totals `0.923`/`2.606` are the **same peaks** as the
  body-frame comparison's `0.92`/`2.61` shown to an extra significant figure (a test SHALL assert the total
  peaks equal `body_frame_overall_match`'s `peak_cf_chord`/`peak_cf_normal` so the two precisions cannot
  drift), and `RESULTS.md` SHALL carry that "same peaks" note so the dual precision is not read as two
  different results

#### Scenario: Body-frame added-mass RMS shares are reported

- **Given** the body-frame added-mass force (`Rᵀ·ρ_f·SumU`) and the body-frame total `ib_force` over the
  pinned steady window
- **When** the RMS share is formed as `rms(added-mass component)/rms(ib component)` per body axis (the
  body-frame analog of the lab-frame `added_mass_fraction`, not a peak ratio and not `rms(subtracted)`)
- **Then** it reports ≈ **84 %** of the chord RMS and ≈ **13 %** of the normal RMS — quantifying that the
  chord PARTIAL is added-mass-dominated while the normal is barely affected (consistent with added-mass +
  Wagner roughly cancelling in the normal)

#### Scenario: Reuses the T2a rotation and #36 added-mass, not a re-derivation

- **Given** the diagnostic
- **When** it computes the subtracted body-frame coefficients
- **Then** it calls `added_mass_force` (#36) for `ρ_f·SumU` and `body_frame_coefficients` / the
  `wing_kinematics` `R(t)` mirror (T2a) — subtract-in-lab-then-rotate equals rotate-then-subtract because
  the rotation is linear — and it does **not** re-implement the added-mass magnitude or the rotation
  (the magnitude and orientation defect classes stay separate, CC-V4)

#### Scenario: Reported only — no new van Veen pass/fail, existing graders unchanged

- **Given** the diagnostic's return value and the existing `plausibility_gate` /
  `body_frame_overall_match` graders on the committed run
- **When** they are evaluated
- **Then** the diagnostic exposes **no** `*_match`/`pass`/`floor`/`in_band` field (it is reported, not
  graded), and the plausibility-gate floor verdict and the body-frame van-Veen-target verdict
  (`cf_normal_match=True`, `cf_chord_match=False`, `match=False`) — both graded on `ib_force` — are
  **unchanged** (CC-V2); the subtracted value cannot flip any gate

#### Scenario: Honest framing — isolates the share; T4 resolves the PARTIAL

- **Given** the added-mass-subtracted `CF_chord ≈ 0.652`
- **When** `RESULTS.md` reports the interim
- **Then** it states the drop **isolates the added-mass share** (84 % of the chord RMS), **not** that the
  interim *by itself* resolves the PARTIAL — `0.652` is still ~2× van Veen's translational ~0.3 — and it
  states the residual is **resolved by the Tier T4 decomposition** (which **closes #40**), with the chord's
  remaining **grid** sensitivity tracked by **#50**
- **And** the doc SHALL carry a **metric-type caveat** for the chord: the 84 % is an RMS *energy* share
  over the window, whereas the −29 % is a **peak-to-peak ratio of two window maxima at *different* phases**
  (not a per-instant subtraction) — so "84 % of RMS" is NOT presented as the cause of "the peak dropped
  29 %" (they are different metrics on different supports)
- **And** a reproducibility test SHALL assert the load-bearing framing **wording** is present (an
  `isolat…` phrase, a "does not resolve"/"not … resolve" phrase for the interim-by-itself, the `~2×` / `0.3`
  residual, the peak-to-peak/different-phase caveat) and that the `RESULTS.md` wing Validation-Status row is
  updated **by T4** (not by the interim) from **PARTIAL** to **validated against van Veen's quasi-steady
  model (normal) / chord-grid-limited** — the interim subsection SHALL NOT itself be the edit that changed
  the verdict row (T4's decomposition is)

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

### Requirement: Van Veen quasi-steady force model, pinned and guarded

The analysis SHALL provide a **pure** implementation of van Veen's (2022, JFM 936 A3) quasi-steady
force model — the sum of **three** additive components `F_total = F_transl + F_AM + F_WE`
(translational + added-mass + **Wagner**), each returning a body-frame `(chord/x, normal/z)` force from
`(α, ω, ω̇)` and the wing area-moments. There SHALL be **no** rotational-circulation or rotational-drag
term (van Veen's model has none; the paper's "rotational" denotes rotational *stroke acceleration*, i.e.
the `ω̇`-dependent added-mass and Wagner terms). The fitted coefficients SHALL be **named module-level
constants** carrying their published 95 % confidence intervals, and a **not-loosened guard** test SHALL
fail if a coefficient (or its CI) is widened (CC-V2). The functional forms are (α in radians):

- translational: `F_z = ½ρω²S_yy·C_Fzα_transl·sinα` (`C_Fzα_transl = 3.13`);
  `F_x = ½ρω²S_yy·(A·α²+B·α+C)` (`A=8.5e-5, B=−1.2e-2, C=0.41`)
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
  tangential `F_x_transl = ½ρω_ref²S_yy·(A·(π/2)²+B·(π/2)+C)` — each matching the hand-computed literal to
  floating tolerance

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

#### Scenario: Force direction reverses each half-stroke, pinned analytically (not to CFD)

- **Given** the model normal component at mid-downstroke and mid-upstroke (opposite `φ̇`, opposite `α`)
- **When** its sign is evaluated
- **Then** it equals the hand-computed `sign(sinα(t))`/`R(t)`-frame expectation and **reverses** between the
  two half-strokes — asserted against **hand-computed literals**, never against the CFD force series (which
  would be reverse-fitting)

### Requirement: Wing area-moments from a single hinge-origin quadrature

The analysis SHALL compute the wing area-moments from **one shared** `compute_wing_area_moments` function
using a **pinned integration convention**: `y` measured from the **stroke rotation (hinge) axis** (van
Veen's convention; the wing root sits at a hinge offset `d ≈ 1.5` from the wing's geometric centre, so
`r_gyr ≈ 1.6985` **about the hinge**). It SHALL emit:
- `S_yy = R_GYRATION²·area ≈ 6.797`, defined via the committed `R_GYRATION` (the *same* single source
  `compute_force_reference` uses for `F_ref`) — **NOT** re-derived as a marker `∫c·y²dy` quadrature (a raw
  chord-integral over the discrete markers gives `≈6.30` because the marker planform area ≠ the analytic
  elliptic area by ~7 %; the spec does **not** claim `S_yy` equals that quadrature);
- `S_cy == S_yy` (van Veen's `S_cy` has the identical integrand as `S_yy`, so it takes the same value);
- the **new** `S_WE = ∫√(c³y³)dy ≈ 3.98` (`y > 0` throughout, so the `√` is real), computed by a
  hinge-origin marker quadrature and **cross-checked against a genuinely independent analytic
  elliptic-planform quadrature** (a different integrator, not a re-binning — they agree to ~0.1 %); this
  independent-quadrature claim applies to `S_WE`, **not** to `S_yy`. A too-fine `nbins` (bins with ≤1
  marker) **raises** rather than silently under-estimating `S_WE`.
The existing inline `S_yy = r_gyr²·area` sites (`generate_validation_figures.py`,
`test_force_surrogate_normalization.py`) SHALL be refactored to call this one function (CC-V4 — a single
moment code path, not two). `S_WE` is a **fixed geometric constant** of the pinned planform, never tuned to
make a grade pass; the marker quadrature and the independent analytic quadrature agree to ~0.1 %, so its
uncertainty feeding the `T4_NORMAL_MAG_TOL` budget is negligible (~0.001 on the normal peak) — the budget is
grid-dominated. (The distinct `S_yy` uses the analytic-elliptic area for `F_ref` consistency; a marker
`∫c·y²dy` quadrature would give ~6.24 — a documented convention, not an uncertainty; `S_yy` is fixed.)

#### Scenario: S_yy reproduces the committed value under the hinge-origin convention

- **Given** the committed wing planform and the hinge-origin convention (y from the stroke axis, not the
  wing centre)
- **When** `compute_wing_area_moments` runs
- **Then** `S_yy ≈ 6.797` (`= R_GYRATION²·area`, reconciling the committed value) and `S_cy == S_yy`; using
  the wing-**centre** origin instead would give the wrong `≈1.20`, so the test pins the hinge origin

#### Scenario: S_WE is an independent quadrature, cross-checked

- **Given** the same planform + convention
- **When** `S_WE = ∫√(c³y³)dy` is computed
- **Then** it matches an **independent** numeric quadrature of the committed planform to tolerance (a
  genuine known-answer, not a re-read of a stored constant), and a degenerate (zero-area) planform raises
  `ValueError`

### Requirement: Per-component decomposition of the CFD force, graded against van Veen's model

The analysis SHALL provide `decompose_wing_force(csv_path, *, f_star, phi_amp_deg, pitch_amp_deg,
window_t0=STEADY_WINDOW_T0, …)` that builds van Veen's per-component + total model on **our** measured wing
kinematics, normalizes each by the single-source `compute_force_reference` (`F_ref = ½ρω_ref²S_yy = 200.27`,
the **same** reference as the CFD `CF`; no correction factor), aligns to the CFD time grid from
`reconstruct_wing_body_forces` (reused, not re-derived, CC-V4), and grades / reports the comparison over
the pinned steady window. It SHALL be **cluster-free** (committed CSVs) and FP64. Because both sides share
the **same** kinematics and `F_ref`, the graded claim is **"consistent with / validated against van Veen's
quasi-steady model at matched kinematics — in peak magnitude"** — a plausibility result against the
literature-standard model, **not** an independent validation of the per-component split (the CFD gives only
the total). The graded oracle SHALL rest on the **grid-settled** normal **peak magnitude** (the robust,
`S_WE`-insensitive lever) and the **decomposition-closure identity**. The normal **peak phase** (measured:
the CFD peak **leads** the QS model by ~0.058 cycle — the expected quasi-steady-vs-unsteady discrepancy,
triply confounded by grid non-convergence + the single-wingbeat transient), the normal **curve RMSE**, the
translational-chord magnitude, and the **grid-unconverged** chord total curve SHALL be **reported, not
gated** (a tight phase gate would require reverse-fitting the confounded ~0.06 gap — CC-V2). The **one**
graded magnitude tolerance SHALL be a **named, test-guarded constant** derived from **sourced** quantities
(van Veen coefficient 95 % CIs ⊕ the measured coarse↔medium grid spread ⊕ the small `S_WE` geometric
uncertainty) and pinned **before** the committed-run result — never reverse-fit (CC-V2); the magnitude
grader SHALL be proven on synthetic fixtures to **pass within and fail outside** `T4_NORMAL_MAG_TOL` (both
directions). The return value SHALL expose **no** chord `*_pass`/`*_match` verdict key, and its key set
SHALL be exact/enumerated (a later-added chord gate fails a guard).

#### Scenario: Normal peak MAGNITUDE is the primary graded lever (S_WE-insensitive)

- **Given** the model-total `CF_normal(t)` and the CFD `CF_normal(t)` over the steady window
- **When** the normal peak-magnitude grade is computed
- **Then** the **relative** peak gap `|model_peak − cfd_peak| / cfd_peak` (model ≈2.48 vs CFD ≈2.61, i.e.
  ≈0.05) is within `T4_NORMAL_MAG_TOL` (a **relative/fractional** tolerance, units-consistent with the
  grid GCI — see design §D6); the term is `S_WE`-**insensitive** (the `S_WE` uncertainty moves the normal
  peak by only ~0.001, marker and analytic `S_WE` agreeing to ~0.1 %); a synthetic series offset in
  magnitude beyond the tolerance **fails** (both directions), and widening `T4_NORMAL_MAG_TOL` flips a
  not-loosened test

#### Scenario: Normal peak phase and curve RMSE are reported, not gated

- **Given** the same normal series
- **When** the peak-phase gap and curve RMSE are computed
- **Then** they are **reported** (no pass/fail tolerance): the peak-phase gap (~0.058 cycle, CFD leading) is
  reported with its confounds (QS-vs-unsteady wake-memory omission + grid non-convergence + single-wingbeat
  transient), and the curve RMSE (inflated by the phase offset) is reported — neither is gated, so neither
  can be reverse-fit

#### Scenario: Translational-chord is a known-answer self-consistency check, NOT an identity to 0.30

- **Given** the model's translational-tangential peak `CF` on our kinematics
- **When** it is reported
- **Then** it equals the value **computed from the pinned polynomial** `(A·α²+B·α+C)` at our α (≈ **0.42**),
  pinned as a **known-answer literal** — and it is reported as **O(0.4) ≪ the CFD total peak ≈0.92**, which
  is the #40 apples-to-oranges resolution; van Veen's *reported* translational chord `~0.3` (a Fig-4b
  eyeball at his mosquito operating point) is noted as the same order, the small difference attributed to
  the operating point — **reported, not graded**. The analysis SHALL NOT assert the peak equals `0.30`
  within a tolerance, and SHALL NOT reuse `VAN_VEEN_CF_TARGETS["cf_chord_peak"]` as a chord gate (that
  would both fail numerically and be circular)

#### Scenario: Decomposition closure is an exact identity (graded)

- **Given** the per-component model series (translational, added-mass, Wagner)
- **When** they are summed
- **Then** the sum equals the reported `model_total` (chord and normal) to floating tolerance

#### Scenario: Chord total curve is reported with the grid band and the convergence direction

- **Given** the model-total `CF_chord(t)` and the CFD `CF_chord(t)` on the coarse **and** medium CSVs
- **When** the chord comparison is reported
- **Then** it is emitted **with** `T4_CHORD_GCI_BAND` (asserted **equal** to the committed T3b chord GCI via
  the reused `wing_grid_convergence_from_body_forces`, not a re-typed literal) and **no** chord
  `*_pass`/`*_match` key, and it reports that the CFD chord **converges toward the model** under refinement
  (coarse `≈0.92` → medium `≈0.554` → model `≈0.43`) — the tight chord verdict is deferred to **#50**

#### Scenario: The magnitude tolerance derives from its sourced inputs (not reverse-fit)

- **Given** the committed T3b normal grid GCI (via the reused convergence helper), the pinned
  coefficient-CI band, and the `S_WE` geometric-uncertainty term **recomputed** from the marker-vs-analytic
  `S_WE` difference propagated through the Wagner share (**not** a typed literal)
- **When** `T4_NORMAL_MAG_TOL` is checked against its §D6 quadrature recomputed from those inputs
- **Then** it is **≥** its derived floor (`√(0.146²+0.006²+0.001²) ≈ 0.147`) and **≤** a small rounding
  margin above it — a tolerance loosened past its sourced budget **fails** — making "pinned from sourced
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

### Requirement: Erratum-verified coefficient provenance

The pinned van Veen coefficients SHALL carry a **testable provenance literal** recording that they were
checked against the erratum **JFM 956 E1 (2023)**. Because the erratum is characterised as a
"publisher-introduced" (production) correction — most likely the malformed Data-availability DOI, not the
fitted coefficients — the check is **blocking-if-unresolved**: if the erratum changes a coefficient, the
pinned constant + CI are updated and the deviation recorded in `design.md` §D9.

#### Scenario: Erratum verdict is pinned as a committed artifact

- **Given** the pinned coefficients and the erratum JFM 956 E1 (2023)
- **When** the provenance is asserted
- **Then** a committed literal (e.g. `ERRATUM_CHECKED = "JFM 956 E1 (2023): no coefficient change"`) records
  the outcome and is asserted in a test — so "verified before trust" is a committed artifact, not only a
  human step; and if the erratum **does** change a coefficient, the pinned constant + CI are updated to
  match and the deviation is recorded in `design.md`

### Requirement: CF_chord PARTIAL resolved — decomposition figure, RESULTS, and roadmap

The change SHALL resolve the `CF_chord` PARTIAL (#40) in the documentation and figures. A **cluster-free**
figure `fig_force_decomposition` SHALL replot, for chord and normal separately, van Veen's model
translational / added-mass / Wagner / total curves against the CFD total over the steady window,
regenerated from the committed CSVs at our operating point. `RESULTS.md` SHALL replace the CF_chord
"hypothesis (#40)" / PARTIAL language with the **verified-against-van-Veen's-model** decomposition — the
**normal** consistent with the model in **peak magnitude** (within the sourced band; the peak **phase** gap
is **reported** with its confounds, not tightly gated) and the **chord** **explained** by van Veen's
translational + tangential-added-mass accounting and **grid-limited** (the tight chord verdict tracked by
**#50**) — while **keeping** the T3b "Grid convergence" section and the added-mass-subtracted interim
intact, and adding the new figure to the Output Files table. Every new headline number SHALL recompute from
the committed CSVs. `roadmap.md` SHALL flip the **T4** row to ✅ with the PR reference, update the Sequencing
line, **rewrite the T4 row body** (line 97: "translational + rotational + added-mass" → "translational +
added-mass + Wagner"; "earns the word *validated*" → "validated against van Veen's quasi-steady model"; and
its "digitize … Fig 3–4"), correct the oracle table (line 74, **both** occurrences of "Fig 3–4" → Fig 13 —
oracle cell and Source column — **and** "digitized curve" → "van Veen's *model* replotted, no
digitization"), and add a **one-line reconciliation-log note** that normal peak-**phase** is
reported-not-gated because it is **triply confounded** (QS-intrinsic + grid non-convergence + single-wingbeat
transient) — an **evidence-based scoping decision, NOT a loosened tolerance** (the magnitude gate stays
sourced; no tolerance is widened to pass). It SHALL also soften the reconciliation-log's bare "validated …
wing curve (T4)" line to "validated against van Veen's QS model". Plus `docs/coordinate-convention.md` and
the `flapping_wing.py` module docstring/`VAN_VEEN_CF_TARGETS` comment (dropping the stale "rotational
drag"/"digitized"/"deferred to T4"/"Fig 3–4" framing). The docs SHALL say "validated **against van Veen's
quasi-steady model**" (consistency at matched kinematics), not a bare "validated".

#### Scenario: Decomposition figure regenerates cluster-free from committed data

- **Given** the committed `forces_t2a_newconv.csv` (and `forces_medium.csv`) and the van Veen model
- **When** `fig_force_decomposition` is generated
- **Then** it shows the model translational / added-mass / Wagner / total vs the CFD total for **both**
  chord and normal over the steady window, written as `.pdf` + `.png` (Agg backend), with **no**
  cluster/plotfile dependency, and a row for it is added to the `RESULTS.md` Output Files table

#### Scenario: RESULTS.md states the verified-against-model decomposition and keeps T3b intact

- **Given** the regenerated `RESULTS.md`
- **When** it is inspected
- **Then** the wing Validation-Status is updated from **PARTIAL (#40)** to **validated against van Veen's
  quasi-steady model (normal consistent; chord explained + grid-limited, #50)**; the decomposition numbers
  recompute from the committed CSVs; the "Grid convergence (T3b)" section and the added-mass-subtracted
  interim subsection remain present and unchanged in substance; the existing correct "Fig 4"
  translational-target cites are **kept** while the "Fig 3–4" time-resolved cites are relabelled to Fig 13;
  and no post-hoc correction factor is introduced

#### Scenario: Roadmap and adjacent docs de-stale the reframe at every location

- **Given** `docs/aerodynamics_validation/roadmap.md`, `docs/coordinate-convention.md`,
  `examples/flapping_wing/figures/README.md`, and the `flapping_wing.py` docstring/comment
- **When** they are read after the change
- **Then** the T4 row (line 97) carries a ✅ + PR reference **and** its body no longer contains
  "translational + rotational + added-mass" or a bare "earns the word validated" (replaced by
  `{transl, AM, Wagner}` and "validated against van Veen's QS model"); the Sequencing line no longer says
  "T4 … is next"; the oracle table (line 74) has **neither** "Fig 3–4" occurrence (oracle cell + Source
  column) nor "digitized curve"; the reconciliation-log bare "validated … wing curve (T4)" is softened; the
  only reconciliation-log addition is the **phase-reported** note (an evidence-based scoping decision, not a
  loosened tolerance); every "deferred to T4"/"fig 3–4" string in `coordinate-convention.md`,
  `figures/README.md`, and the `flapping_wing.py` docstring/comment is corrected to `{transl, AM, Wagner}` /
  Fig 13 / delivered

