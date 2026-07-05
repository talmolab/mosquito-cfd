# flapping-wing-validation (delta)

## ADDED Requirements

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

## MODIFIED Requirements

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
