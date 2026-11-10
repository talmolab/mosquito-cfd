## ADDED Requirements

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
the lab ranges, the T4 `normal_curve_rmse`, and the added-mass-subtracted `drop_frac`.

The `forces` subcommand of `examples/flapping_wing/visualize.py` SHALL be removed. It summed plotfile
marker increments rather than the accumulated `ib_force`, and labelled `Fy` as lift (pre-T2a axes).

#### Scenario: Lab and body coefficients are on-wing

- **Given** the committed `forces_t2a_newconv.csv`
- **When** `reconstruct_wing_forces` and `reconstruct_wing_body_forces` run
- **Then** `cf_x_ib == −Fx/f_ref` and `cf_z_ib == −Fz/f_ref`, and the body-frame series equal `R(t)ᵀ` applied to `−F`, divided by `f_ref`

#### Scenario: Graded verdicts are unchanged by the sign

- **Given** the committed CSVs
- **When** `plausibility_gate`, `body_frame_overall_match` and `decompose_wing_force` run after this change
- **Then** the existing graded literals in `tests/test_wing_body_frame.py` and the T4 decomposition tests still pass with no edit to those literals. The independent pin is these literals, which predate this change, not a recomputation by the new code.

#### Scenario: The forces subcommand is gone

- **Given** `examples/flapping_wing/visualize.py`
- **When** its argument parser is built
- **Then** its subcommands are exactly `velocity` and `vorticity`

## MODIFIED Requirements

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
so the IB force on the wing is `ρ_f·ib_w`, and `F_ref = ½·ρ_f·ω²·S_yy` SHALL be built with the same
`ρ_f` (`compute_force_reference(..., rho=rho_f)`). The density therefore cancels:
`CF_ib = ρ_f·ib_w/F_ref(ρ_f)`, `CF_added` and `CF_hydro = CF_added + CF_ib` are independent of `ρ_f`, and
so are every ratio (`added_mass_fraction`) and the gate verdict. `ρ_f = 1` in every committed run, so
no committed coefficient changes. A `ρ_f` that is not a finite, positive real number (a
`numbers.Real` other than a boolean) SHALL raise `ValueError` naming `rho_f`, before any file is read;
so SHALL an integer too large to convert to a float, and a value below the smallest normal float
(`np.finfo(float).tiny`), where the cancellation is no longer exact. A `rho_f` large enough that
`F_ref` overflows SHALL raise a `ValueError` that names `rho_f` as a possible cause. The accepted
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
- **And** `ρ_f = 1e308` raises `ValueError` naming `rho_f` in both functions

#### Scenario: Added-mass does not decide the gate

- **Given** the plausibility-gate verdict
- **When** it is computed
- **Then** it is a function of `ib_force` alone and is unchanged whether or not the added-mass term is included — an unverified or out-of-band added-mass term cannot flip the gate

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
the per-component + total model coefficients, the graded normal peak magnitude (≈2.48 vs CFD ≈2.61), the
reported normal peak-phase gap (~0.058 cycle) and curve RMSE, and the known-answer translational-chord peak
(≈0.42)**. The enumeration of checked numbers SHALL be **asserted complete** — a
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
- **Then** the 6-DOF and `ib_w` peaks (`0.652` / `0.923` chord, `2.285` / `2.606` normal), the signed
  ratios `drop_frac = 1 − peak_ib/peak_6dof` (≈ −0.42 / −0.14: removing the internal-fluid term raises
  the peaks 42 % / 14 %), and the body-frame added-mass RMS shares (chord ~84 % / normal ~13 %) recompute from the committed
  CSV and appear in `RESULTS.md` as pinned literals; the `ib_w` peaks additionally equal `body_frame_overall_match`'s `peak_cf_chord`/`peak_cf_normal` (the "same peaks" cross-check); the interim
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
  the added-mass-subtracted interim 6-DOF/`ib_w` peaks (`0.652`/`0.923`, `2.285`/`2.606`), `drop_frac`
  (≈ −0.42 / −0.14) and shares (~84 %/~13 %), **the T4
  per-component + total coefficients and the translational-chord ≈0.42** — and the contrast-baseline numbers
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
as (by itself) resolving the `CF_chord` PARTIAL: the IB-only `CF_chord ≈ 0.923` remains ~3× van Veen's
translational ~0.3, and the 6-DOF `≈ 0.652` ~2×. Which CFD force the van Veen comparison should use
(`ib_w` or the 6-DOF force) is a follow-up issue, not decided here. T4's resolution of the chord
PARTIAL below holds on the condition that `ib_w` is the right comparand. That residual is **resolved by the Tier T4 per-component decomposition** (van Veen's
`transl + AM + Wagner`; see "Per-component decomposition of the CFD force, graded against van Veen's
model"), which **closes #40**; the chord's remaining **grid** sensitivity is tracked by **#50**. Where
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

#### Scenario: Honest framing — isolates the share; T4 resolves the PARTIAL

- **Given** the 6-DOF `CF_chord ≈ 0.652` and the IB-only `CF_chord ≈ 0.923`
- **When** `RESULTS.md` reports the interim
- **Then** it states the comparison **isolates the internal-fluid term's share** (84 % of the chord RMS),
  **not** that the interim *by itself* resolves the PARTIAL — `0.923` is still ~3× van Veen's translational
  ~0.3 (the 6-DOF `0.652` ~2×) — and it
  states the residual is **resolved by the Tier T4 decomposition** (which **closes #40**), with the chord's
  remaining **grid** sensitivity tracked by **#50**
- **And** the doc SHALL carry a **metric-type caveat** for the chord: the 84 % is an RMS *energy* share
  over the window, whereas `drop_frac ≈ −0.42` (removing the term raises the chord peak 42 %) is a **peak-to-peak ratio
  of two window maxima at *different* phases**
  (not a per-instant subtraction) — so "84 % of RMS" is NOT presented as the cause of "the chord peak rose 42 %" (they are different metrics on different
  supports); the instantaneous ratio at the 6-DOF chord peak (`1 − |ib_w|/|F_6dof|` ≈ −0.39, i.e. `|ib_w|`
  exceeds `|F_6dof|` by 39 % there) is named as a third metric, and the two chord peaks are ~1094
  timesteps apart
- **And** a reproducibility test SHALL assert the load-bearing framing **wording** is present (an
  `isolat…` phrase, a "does not resolve"/"not … resolve" phrase for the interim-by-itself, the `~3×` / `0.3` residual, a statement that `ρ_f·SumU` is the solver's internal-fluid term and not van
  Veen's added mass, a pointer to the follow-up issue on which CFD force van Veen's comparison should use, the peak-to-peak/different-phase caveat) and that the `RESULTS.md` wing Validation-Status row is
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

#### Scenario: Either degenerate denominator raises

- **Given** a synthetic CSV whose `ib_w` is nonzero with `ρ_f·SumU = −ib_w` (a zero 6-DOF force), and another whose `ib_w` is zero with nonzero `SumU`
- **When** the diagnostic runs on each
- **Then** the first raises `ValueError` naming the degenerate 6-DOF peak (the `drop_frac` denominator) and the second raises `ValueError` naming the degenerate `ib_w` (the RMS-share denominator), each against `_DEGENERATE_CF_FLOOR`
- **And** a guard on only one of the two denominators fails this scenario

### Requirement: Per-component decomposition of the CFD force, graded against van Veen's model

The analysis SHALL provide `decompose_wing_force(csv_path, *, f_star, phi_amp_deg, pitch_amp_deg,
window_t0=STEADY_WINDOW_T0, …)` that builds van Veen's per-component + total model on **our** measured wing
kinematics, normalizes each by the single-source `compute_force_reference` built at the model's density
`rho` (`F_ref = ½ρω_ref²S_yy`, 200.27 at `ρ = 1`; the same reference formula as the CFD `CF`; no
correction factor), so the model coefficients, like the CFD's, do not depend on the density, aligns to the CFD time grid from
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
SHALL be exact/enumerated (a later-added chord gate fails a guard). A `rho` that is not a finite,
positive, normal real number SHALL raise `ValueError` naming `rho` before any file is read.

#### Scenario: Normal peak MAGNITUDE is the primary graded lever (S_WE-insensitive)

- **Given** the model-total `CF_normal(t)` and the CFD `CF_normal(t)` over the steady window
- **When** the normal peak-magnitude grade is computed
- **Then** the **relative** peak gap `|model_peak − cfd_peak| / cfd_peak` is within `T4_NORMAL_MAG_TOL` (a
  **relative/fractional** tolerance, units-consistent with the grid GCI — see design §D6); on the T2a
  coarse CSV, model ≈2.48 vs CFD ≈2.61 (gap ≈0.05); on the flagship T3c fine-256³ CSV (the current
  production comparison), model ≈2.48 vs CFD ≈2.23 (gap ≈0.11) — both pass. The term is
  `S_WE`-**insensitive** (the `S_WE` uncertainty moves the normal peak by only ~0.001, marker and analytic
  `S_WE` agreeing to ~0.1 %); a synthetic series offset in magnitude beyond the tolerance **fails** (both
  directions), and widening `T4_NORMAL_MAG_TOL` flips a not-loosened test

#### Scenario: Normal peak phase and curve RMSE are reported, not gated

- **Given** the same normal series
- **When** the peak-phase gap and curve RMSE are computed
- **Then** they are **reported** (no pass/fail tolerance): the peak-phase gap (~0.058 cycle on the T2a
  coarse CSV, ~0.055 cycle on the T3c fine-256³ CSV; CFD leading either way) is reported with its confounds
  (QS-vs-unsteady wake-memory omission + grid non-convergence + single-wingbeat transient), and the curve
  RMSE (inflated by the phase offset) is reported — neither is gated, so neither can be reverse-fit

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
- **When** `medium_csv` is supplied and the chord comparison is reported
- **Then** it is emitted **with** `T4_CHORD_GCI_BAND` (asserted **equal** to the committed T3b chord GCI via
  the reused `wing_grid_convergence_from_body_forces`, not a re-typed literal) and **no** chord
  `*_pass`/`*_match` key, and it reports that the CFD chord **converges toward the model** under refinement
  (coarse `≈0.92` → medium `≈0.554` → model `≈0.43`) — the tight chord verdict is deferred to **#50**

  **Caveat (T3c, fine-grid production usage):** `medium_csv` is **optional** and this 2-grid band is
  **report-only**, exercised directly by the coarse/medium fixture in `test_wing_force_decomposition.py`.
  `medium_csv` MUST NOT be paired with a `csv_path` that is **finer** than it — `wing_grid_convergence`
  treats `csv_path`'s role as "coarse" unconditionally, so pairing a finer grid as `csv_path` against a
  coarser `medium_csv` **inverts** the convergence-direction sign (verified: `chord_converges_toward_model`
  flips to `False`, the wrong answer). Once the fine 256³ grid (`forces_fine.csv`) became the flagship
  CFD comparison (T3c, closing #50), the production caller (`make_force_decomposition_figure.py`,
  `test_t4_decomposition_numbers_reproduce`) stopped passing `medium_csv` for exactly this reason —
  `chord_gci_band`/`chord_converges_toward_model` are `None` in that call — and RESULTS.md instead reports
  the separately-computed T3c 3-grid Richardson/`GCI_fine` numbers (`wing_grid_convergence_3grid`) as the
  authoritative grid-uncertainty figure for the chord (CF_chord fine `≈0.41` vs model `≈0.43`).

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

#### Scenario: The model's density cancels, so no T4 number or verdict depends on it

- **Given** `forces_fine.csv` and the production kinematics (`f_star = 1`, `phi_amp_deg = 70`,
  `pitch_amp_deg = 45`)
- **When** `decompose_wing_force` runs at `rho = 0.5`, `2` and `1.3`, and at `rho = 1`
- **Then** every returned number, every `*_pass` verdict and every `series` array equals its `rho = 1`
  value (exactly at the powers of two, to `1e-12` relative at `1.3`); before this change, `rho = 2`
  doubled the model normal peak (2.48 → 4.95 against the CFD's 2.23) and flipped `normal_mag_pass`
- **And** a `rho` of `0`, NaN, a boolean or a string raises `ValueError` naming `rho`, also when the CSV
  path does not exist
