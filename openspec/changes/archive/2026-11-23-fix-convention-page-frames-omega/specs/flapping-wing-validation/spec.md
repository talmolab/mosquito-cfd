## MODIFIED Requirements

### Requirement: Van Veen-faithful force-coefficient convention, no correction factor

The flapping-wing analysis SHALL report force coefficients in the **van Veen (2022) convention**
(`F_ref = ½ρ·ω_peak²·S_yy`, with `ω_peak` the peak stroke rate defined in
[Force Surrogate](../force-surrogate/spec.md), "Single-source force normalization") obtained
through the single-source `compute_force_reference` helper (CC-3),
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

### Requirement: Added-mass decomposition reported separately (not graded by the gate)

The wing analysis SHALL report the immersed-boundary **added-mass** term (derived from the `SumU*`
columns of the IB-particle output) as a **separate decomposition** alongside `ib_force`, NOT folded
into the coefficient the plausibility gate grades. The `SumU*`→force relationship SHALL be taken from
the IAMReX `WriteIBForceAndMoment` definition (resolved from the solver source before any combination),
documented in the analysis with the exact column algebra, and a test SHALL assert the added-mass
expression matches that definition on a known row of the committed `forces.csv` (kept IB-particle output) — locking the
formula to the **source**, not to the band. The analysis MAY additionally report the net 6-DOF
hydrodynamic coefficient `F_hydro = ρ_f·(SumU − ib_force)` (the solver's momentum balance, with
`ib_force` the solver's on-fluid column) — written with the on-wing IB force `ib_w = −ib_force` as
`F_hydro = ρ_f·(SumU + ib_w)` — clearly labelled, but the gate verdict SHALL rest on `ib_force` alone.
IAMReX's `ib_force` is per unit fluid density (`DiffusedIB.cpp` multiplies it by `euler_fluid_rho`),
so the IB force on the wing is `ρ_f·ib_w`, and `F_ref = ½·ρ_f·ω_peak²·S_yy` SHALL be built with the same
`ρ_f` (`compute_force_reference(..., rho=rho_f)`). The density therefore cancels:
`CF_ib = ρ_f·ib_w/F_ref(ρ_f)`, `CF_added` and `CF_hydro = CF_added + CF_ib` are independent of `ρ_f`, and
so are every ratio (`added_mass_fraction`) and the gate verdict. `ρ_f = 1` in every committed run, so
no committed coefficient changes. A `ρ_f` that is not a finite, positive real number (a
`numbers.Real` other than a boolean) SHALL raise `ValueError` naming `rho_f`, before any file is read;
so SHALL an integer too large to convert to a float, and a value below the smallest normal float
(`np.finfo(float).tiny`), where the cancellation is no longer exact. A `rho_f` large enough that
`F_ref`, or any force or coefficient computed from finite input, overflows SHALL raise a `ValueError`
that names `rho_f` as a possible cause, never return an `inf`/NaN coefficient. The accepted
value is converted to a Python `float`, so every coefficient is `float64`.

#### Scenario: Added-mass formula is locked to the IAMReX source, not the band

- **Given** the committed 29-column `forces.csv` (with `Fx/Fy/Fz` and `SumU{x,y,z}`) and the documented `WriteIBForceAndMoment` definition
- **When** the added-mass term is computed
- **Then** it equals the documented expression (whether an already-force-like accumulation or a momentum sum requiring `d/dt`, as resolved from the solver source) evaluated on a known row, with the formula citation in the test docstring — and the test does **not** select the expression that makes the gate pass

#### Scenario: Decomposition is the 6-DOF momentum balance, self-consistent

- **Given** the `ib_force`, added-mass (`ρ_f·SumU`), and net hydrodynamic coefficients
- **When** they are computed over the pinned steady window
- **Then** the net hydrodynamic force is the **6-DOF momentum balance** `F_hydro = ρ_f·(SumU − ib_force)` per `WriteIBForceAndMoment` (i.e., with `F_ref` built at the same `ρ_f` and `CF_ib` the **on-wing** IB coefficient `−ρ_f·ib_force/F_ref`, `CF_hydro = CF_added + CF_ib` within floating tolerance, and the raw-column identity `CF_hydro·F_ref = ρ_f·(SumU − ib_force)` checked as well — **not** a sum of `CF_added` with the on-fluid `ib_force`), and the added-mass contribution is reported as a fraction of `ib_force` with the fraction bounded `0 < fraction < 1` and its actual value snapshotted (not hard-coded to "~15%/~33%"; the committed contrast-baseline `forces.csv` gives ~10% stroke / ~40% lift)

> **Why 6-DOF balance, not `ib + added` (implementation deviation):** the proposal's scenario assumed `combined = ib_only + added_mass_only`. Reading the IAMReX source (`DiffusedIB.cpp`) showed the `SumU` columns are already `(sum_u_new − sum_u_old)/dt` and the particle equation of motion combines them as `ρ_f·(SumU − ib_force)`. The gate is unaffected (it is graded on `ib_force` alone); only the *reported* decomposition formula changed to match the solver. `fix-wing-force-sign-convention` (#109) later established that `ib_force` is the force on the fluid and moved the analysis to on-wing coefficients, where the same balance reads `F_hydro = ρ_f·(SumU + ib_w)`.

#### Scenario: The density cancels, so no coefficient or verdict depends on it

- **Given** a committed force CSV
- **When** `reconstruct_wing_forces` and `body_frame_added_mass_subtracted` run at `ρ_f = 0.5`, `2` and
  `1.3`, and at `ρ_f = 1`
- **Then** `f_ref` is `ρ_f` times its `ρ_f = 1` value, while `CF_ib`, `CF_added`, `CF_hydro`, every
  reported peak, `added_mass_fraction`, `*_drop_frac` and `am_rms_share_*` equal their `ρ_f = 1`
  values (exactly at the powers of two, to `1e-12` relative at `1.3`)
- **And** `plausibility_gate` gives the same verdict and the same peaks at every one of those densities
- **And** a `ρ_f` of `Fraction(1, 2)`, `np.float32(2)` or an arbitrary-precision real such as
  `sympy.Float("1.3", 50)` gives the same `float64` coefficients as the equal `float`, bitwise
- **And** a `ρ_f` of `0`, a negative value, NaN, infinity, a boolean, `None`, a string, `10**400`,
  `Decimal("1")` (not a `numbers.Real`), a 0-d array, or a subnormal such as `1e-320` raises
  `ValueError` naming `rho_f` in both functions, also when the CSV path does not exist
- **And** `ρ_f = 5e305` (where `F_ref` is finite but the forces overflow) and `ρ_f = 1e308` (where
  `F_ref` itself overflows) raise `ValueError` naming `rho_f` in both functions

#### Scenario: Added-mass does not decide the gate

- **Given** the plausibility-gate verdict
- **When** it is computed
- **Then** it is a function of `ib_force` alone and is unchanged whether or not the added-mass term is included — an unverified or out-of-band added-mass term cannot flip the gate

### Requirement: Body-frame (chord/normal) per-component van Veen comparison

The flapping-wing analysis SHALL decompose the lab-frame `ib_force` `(Fx,Fy,Fz)` into the
**instantaneous wing body frame** using the **analytic** rotation `R(t)` from the wing kinematics (the
same composition the solver applies), yielding chord-wise `CF_chord` and wing-normal `CF_normal` series
in van Veen's convention (`F = (F_x chord, F_z normal)`), normalized by the single-source
`compute_force_reference` (`F_ref = ½ρω_peak²S_yy`; no correction factor). The rotation axes/order SHALL be
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
`compute_force_reference` (`F_ref = ½ρω_peak²S_yy`; no correction factor).

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
