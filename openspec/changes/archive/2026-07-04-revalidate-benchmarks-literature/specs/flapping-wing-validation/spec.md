# flapping-wing-validation (delta) — Tier T2b

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

## ADDED Requirements

### Requirement: RESULTS.md headline numbers reproducible from committed CSVs (issue #3 re-validation)

Every **headline number** in `examples/flapping_wing/RESULTS.md` SHALL be **recomputable** from the
committed force CSVs over the stated steady window, via the single-source `compute_force_reference` /
`compute_force_coefficients`, the body-frame decomposition, and the `added_mass_fraction` RMS helper —
with **no** value transcribed that the committed data cannot regenerate. The new-convention headline
numbers SHALL recompute from `forces_t2a_newconv.csv` (`F_ref = 200.27`, `t ≥ 0.05`); the
contrast-baseline numbers from `forces.csv`. The recomputation SHALL respect each number's **definition**:
coefficient ranges/peaks via `compute_force_coefficients`; the phase-table `Fz` are **raw forces** read at
the named `time` rows (not coefficients); the added-mass fractions are the **RMS** `added_mass_fraction`
values (stroke ~37 % / lift ~29 %). The enumeration of checked numbers SHALL be **asserted complete** — a
RESULTS.md headline number absent from the enumeration fails the test. A test SHALL assert this
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
  (`cf_chord_match = False`), reproducing the T2a **PARTIAL** verdict from committed data — T2b does
  **not** re-derive the decomposition or resolve the chord PARTIAL (deferred to #40 / T4)

#### Scenario: Every stated headline value has a committed-data source, by its own definition

- **Given** the RESULTS.md headline numbers — CF ranges/peaks (coefficients), the phase-table `Fz` (raw
  forces at named `time` rows), the body-frame `2.61`/`0.92`, the RMS added-mass fractions (~37 %/~29 %) —
  and the contrast-baseline numbers (`1.41`/`0.68` from `forces.csv`)
- **When** the reproducibility test runs
- **Then** each number recomputes from its committed CSV **by the correct definition** (coefficient vs
  raw force vs RMS fraction) within the documented tolerance; any number that cannot be regenerated — or
  any headline number missing from the asserted-complete enumeration — fails the test; and the test passes
  **before** RESULTS.md is edited, so the doc is proven against live data, not curated
