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
floor/sanity only. The regenerated `RESULTS.md`/figures SHALL disclose the lab band as an O(1) floor and
SHALL **NOT** claim **time-resolved** van Veen validation — only the time-resolved curve match (peak
phase + curve RMSE vs van Veen fig 3–4) remains deferred to **T4**; the body-frame per-component
comparison is already **delivered** (T2a).

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

#### Scenario: Docs disclose the lab-frame floor and do not overclaim time-resolved validation

- **Given** the regenerated `RESULTS.md`/figures
- **When** they are inspected
- **Then** they state the lab-frame gate is an **O(1) magnitude floor** whose `CF_x/CF_z` are lab-frame
  (not van Veen's body-frame chord/normal), point to the **delivered** body-frame per-component van Veen
  comparison, and do **NOT** claim time-resolved van Veen validation — only the **time-resolved** curve
  match (peak phase + curve RMSE vs van Veen fig 3–4) is stated as deferred to **T4**

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
match** — the **peak** `|CF_chord|` and `|CF_normal|` within a **stated tolerance** of van Veen's
reported overall values (cycle-means SHALL be **reported alongside**, not graded — a coarse
single-wingbeat run has no converged mean) — with the test-pinned `VAN_VEEN_BAND` `[0.5,1.5]` as a
floor that SHALL NOT be loosened. Where van Veen's overall numeric targets are not yet sourced (CC-V2), the graded
criterion SHALL fall back to the band floor and the van-Veen gap SHALL be **reported, not reverse-fit**.
The body-frame decomposition of the **old committed run** SHALL be reported as a **contrast baseline**.

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
  to fail** (guarded by a not-loosened test) — this gate is CI-gradeable before van Veen's overall
  numbers are sourced

#### Scenario: Overall scalar-match tolerance, gated on sourced targets (pending numbers)

- **Given** the body-frame series and van Veen's reported overall values pinned as the named constant
  `VAN_VEEN_CF_TARGETS` with tolerance `VAN_VEEN_MATCH_TOL`
- **When** the tolerance match is computed
- **Then** the **peak** `|CF_chord|`, `|CF_normal|` must fall within `VAN_VEEN_MATCH_TOL` of the
  targets (cycle-means reported, not graded); the grader is proven on synthetic fixtures to **pass
  within and fail outside** (both
  directions); and when `VAN_VEEN_CF_TARGETS is None` (not yet sourced, CC-V2) the verdict falls back to
  the band floor and the van-Veen gap is **reported, not reverse-fit**. Both `VAN_VEEN_CF_TARGETS` and
  `VAN_VEEN_MATCH_TOL` are named, test-guarded constants (a loosened tolerance fails a not-loosened test)

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
`compute_force_coefficients`, the body-frame decomposition, the `added_mass_fraction` RMS helper, **and the
added-mass-subtracted body-frame interim diagnostic (`body_frame_added_mass_subtracted`, #40)** — with
**no** value transcribed that the committed data cannot regenerate. The new-convention headline numbers
SHALL recompute from `forces_t2a_newconv.csv` (`F_ref = 200.27`, `t ≥ 0.05`); the contrast-baseline numbers
from `forces.csv`. The recomputation SHALL respect each number's **definition**: coefficient ranges/peaks
via `compute_force_coefficients`; the phase-table `Fz` are **raw forces** read at the named `time` rows (not
coefficients); the added-mass fractions are the **RMS** `added_mass_fraction` values (stroke ~37 % / lift
~29 %); **the added-mass-subtracted interim numbers are the total→subtracted body-frame peaks, their %
drops, and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %)**. The enumeration of checked
numbers SHALL be **asserted complete** — a RESULTS.md headline number absent from the enumeration fails the
test; **the interim subsection's distinct numbers SHALL be enumerated / asserted-complete in their own
guard** (a separate guard from the two existing headline tables, so the interim table's three-sig-fig totals
`0.923`/`2.606` do not collide with the body-frame table's `0.92`/`2.61`). To keep that separation
load-bearing, the interim subsection SHALL use a **distinct `### ` header** whose text does **not** contain
the substrings `lab-frame magnitudes` or `Body-frame per-component van Veen comparison` (the two the
existing `test_headline_tables_enumeration_complete` scans by exact-set-equality), and SHALL **not add or
alter any numeric cell inside those two enumerated tables** — otherwise that pre-existing guard fails; a
test SHALL confirm the existing enumeration guard still passes unchanged. A test SHALL assert this
reproducibility **before** any RESULTS.md edit, and SHALL stand as the **durable regression guard** that
closes issue #3 (whose original `+0.431` defect is superseded by the T2a regeneration — T2b re-validates
the **current** document).

#### Scenario: Lab-frame ranges recompute from the committed new-convention CSV

- **Given** `forces_t2a_newconv.csv` and the van Veen `F_ref = 200.27` from `compute_force_reference`
- **When** the lab-frame coefficients are computed over `t ≥ 0.05`
- **Then** `CF_x` range ≈ `[−2.35, +2.37]`, `CF_z` range ≈ `[−1.46, +0.03]`, `max|CF_x| ≈ 2.37`, and
  `max|CF_z| ≈ 1.46` — each matching the RESULTS.md headline as pinned literals to the documented precision

#### Scenario: Body-frame peaks recompute and reproduce the PARTIAL verdict

- **Given** the same committed CSV and the analytic `R(t)` from the wing kinematics
- **When** `body_frame_overall_match` is evaluated against `VAN_VEEN_CF_TARGETS` / `VAN_VEEN_MATCH_TOL`
- **Then** peak `CF_normal ≈ 2.61` (`cf_normal_match = True`) and peak `CF_chord ≈ 0.92`
  (`cf_chord_match = False`), reproducing the T2a **PARTIAL** verdict from committed data — this change does
  **not** re-derive the decomposition or resolve the chord PARTIAL (deferred to #40 / T4)

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

#### Scenario: Every stated headline value has a committed-data source, by its own definition

- **Given** the RESULTS.md headline numbers — CF ranges/peaks (coefficients), the phase-table `Fz` (raw
  forces at named `time` rows), the body-frame `2.61`/`0.92`, the RMS added-mass fractions (~37 %/~29 %),
  **the added-mass-subtracted interim peaks/drops/shares (`0.652`/`2.285`; ~84 %/~13 %)** — and the
  contrast-baseline numbers (`1.41`/`0.68` from `forces.csv`)
- **When** the reproducibility test runs
- **Then** each number recomputes from its committed CSV **by the correct definition** (coefficient vs raw
  force vs RMS fraction vs added-mass-subtracted diagnostic) within the documented tolerance; any number
  that cannot be regenerated — or any headline number missing from the asserted-complete enumeration —
  fails the test; and the test passes **before** RESULTS.md is edited, so the doc is proven against live
  data, not curated

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

The analysis and docs SHALL frame the drop as **isolating the added-mass share**, NOT as resolving the
`CF_chord` PARTIAL: the added-mass-subtracted `CF_chord ≈ 0.652` remains ~2× van Veen's translational
~0.3, and that residual (rotational drag + coarse grid + total-vs-translational) is explicitly deferred to
**T4**; #40 remains open (only its *cheap-interim* checkbox is ticked). Where `RESULTS.md` reports the
body-frame added-mass RMS shares (chord ~84 % / normal ~13 %), it SHALL **explicitly disambiguate** them
from the already-reported **lab-frame** added-mass RMS fractions (stroke ~37 % / lift ~29 %, from
`added_mass_fraction`): they are a **different frame *and* axis pairing** (lab stroke/lift are
`rms(cf_added)/rms(cf_ib)` in `x`/`z`; body chord/normal are the same ratio *after* rotation by `R(t)`),
and **neither supersedes the other**. Malformed input (missing any of the required columns — including
`Fy`/`SumUy` — a non-finite row, or an empty steady window) SHALL raise `ValueError`, mirroring the
existing decomposition guards (never a silent NaN coefficient).

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

#### Scenario: Honest framing — isolates the share, does not resolve the PARTIAL

- **Given** the added-mass-subtracted `CF_chord ≈ 0.652`
- **When** `RESULTS.md` reports the interim
- **Then** it states the drop **isolates the added-mass share** (84 % of the chord RMS), **not** that it
  resolves the PARTIAL — `0.652` is still ~2× van Veen's translational ~0.3 — and the residual (rotational
  drag + coarse grid + total-vs-translational) is explicitly deferred to **T4**; #40 remains open
- **And** the doc SHALL carry a **metric-type caveat** for the chord: the 84 % is an RMS *energy* share
  over the window, whereas the −29 % is a **peak-to-peak ratio of two window maxima at *different* phases**
  (not a per-instant subtraction) — so "84 % of RMS" is NOT presented as the cause of "the peak dropped
  29 %" (they are different metrics on different supports)
- **And** a reproducibility test SHALL assert the load-bearing framing **wording** is present (an
  `isolat…` phrase, a "does not resolve"/"not … resolve" phrase, the `~2×` / `0.3` residual, the
  peak-to-peak/different-phase caveat, `T4`, and `#40`) — not merely the numbers — and that the
  `RESULTS.md` Validation-Status row still reads **PARTIAL** and references `#40` (the interim SHALL NOT
  weaken that verdict row)

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

