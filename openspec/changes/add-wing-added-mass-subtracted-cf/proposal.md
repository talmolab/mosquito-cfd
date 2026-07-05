# Add added-mass-subtracted body-frame CF diagnostic (#40 cheap interim, cluster-free)

## Why

Tier T2a graded our **total** `ib_force` body-frame peaks against van Veen's
**translational-only** coefficients and returned **PARTIAL**: `CF_normal` 2.61 vs ~2.4 matches
(`cf_normal_match=True`), but `CF_chord` 0.92 vs ~0.3 does **not** (`cf_chord_match=False`,
gap 0.62 > tol 0.6). `RESULTS.md` states the working hypothesis — rotational drag + tangential
added mass **add** to the chord force (Bomphrey 2017) — but that split is **unverified**: coarse grid
(Δx=0.125), single-wingbeat transient, and total-vs-translational are all unseparated at T2a.

Issue **#40** (Tier T4) tracks the full resolution. Its **first checkbox** is a *cheap, cluster-free*
interim: subtract the **logged** added-mass (`ρ_f·SumU`) from `ib_force` and re-report `CF_chord`. The
data to do this is already committed — `forces_t2a_newconv.csv` carries the 29-column IAMReX schema
with `SumU{x,y,z}` — and the machinery already exists: `added_mass_force` (#36), `body_frame_coefficients`
+ the analytic `R(t)` kinematics mirror (T2a). This change formalizes that one interim as a **reported
diagnostic**, TDD-tested and guarded in the docs.

The finding (reproduced this session from the committed CSV, steady window t ≥ 0.05, ρ_f = RHO = 1.0):

| body-frame peak | total `ib_force` | `ib_force − ρ_f·SumU` | van Veen (transl.) |
|---|---|---|---|
| **CF_chord** | 0.923 | **0.652** (−29 %) | ~0.3 |
| **CF_normal** | 2.606 | **2.285** (−12 %) | ~2.4 |

Body-frame added-mass **RMS share** (a separate, whole-window energy metric): **84 %** of the chord RMS,
**13 %** of the normal RMS.

**Interpretation.** The chord PARTIAL is **added-mass-dominated**: added mass is 84 % of the chord RMS
(energy over the window), and the added-mass-subtracted peak `|CF_chord|` (window-max) is 0.652 vs the
total's 0.923. **These are two different metrics, not one** — the 84 % is an RMS energy share; the −29 %
is a **peak-to-peak ratio of two window maxima that fall at *different* phases** (the total-chord peak is
near a stroke reversal, the subtracted-chord peak mid-stroke), **not** a per-instant subtraction (the
instantaneous added-mass drop *at the total peak* is ~47 %). So "84 % of RMS" does not "cause" the "−29 %
peak" — both independently show added mass dominates the chord, by different measures. The normal is barely
affected (−12 %, share 13 %; its peaks coincide in phase), consistent with the T2a "added-mass + Wagner
roughly cancel in the normal". This **isolates a share**; it does **not** resolve the PARTIAL — even
added-mass-subtracted, `CF_chord ≈ 0.652` is still ~2× van Veen's 0.3 (0.652/0.3 ≈ 2.17). The residual
(rotational drag + coarse grid + total-vs-translational) is the **full T4**, not this interim.

## What Changes

- **New reported diagnostic** `body_frame_added_mass_subtracted` in
  `src/mosquito_cfd/benchmarks/flapping_wing.py`: reads the committed IB-particle CSV, subtracts
  `ρ_f·SumU` (via the existing `added_mass_force`) from the lab-frame `ib_force`, rotates **both** the
  total and the subtracted force into the wing body frame with the **existing** `body_frame_coefficients`
  + analytic `R(t)` (from `wing_kinematics`), and returns, over the pinned steady window: peak
  `|CF_chord|`/`|CF_normal|` for total **and** subtracted, their **signed** peak-to-peak drop fraction
  (`drop_frac = 1 − peak_subtracted/peak_total`), and the **body-frame added-mass RMS share** per
  component. **Reported only — the return value carries no `*_match`/pass field.**
- **`examples/flapping_wing/RESULTS.md`**: a new subsection under the added-mass decomposition reporting
  the interim finding (the table above + RMS shares), with **honest framing** (isolates the share, does
  not resolve the PARTIAL; residual deferred to T4). It MUST (a) carry an explicit sentence
  **disambiguating** the body-frame shares (chord 84 % / normal 13 %) from the existing **lab-frame**
  fractions (stroke 37 % / lift 29 %) — different frame *and* axis pairing, neither superseding the other;
  (b) carry a **"same peaks"** note that the interim totals `0.923`/`2.606` are the body-frame table's
  `0.92`/`2.61` shown to an extra significant figure; (c) keep the Validation-Status row reading **PARTIAL**
  and referencing `#40`; (d) use a **distinct `### ` header** (not containing `lab-frame magnitudes` or
  `Body-frame per-component van Veen comparison`) and **not** touch a numeric cell in those two tables, so
  the existing `test_headline_tables_enumeration_complete` still passes; and (e) carry a **metric-type
  caveat** that the −29 % chord drop is a **peak-to-peak ratio of window maxima at *different* phases** (not
  a per-instant subtraction, and distinct from the 84 % RMS energy share). The `### Body-frame per-component`
  table gains the interim numbers; the unguarded `## Comparison with van Veen` table gets a bare
  **cross-reference** to the interim subsection (no re-transcribed number — it is outside the enumeration
  guard, so a number copy there could drift); the Validation-Status row references the interim (still PARTIAL).
- **Reproducibility guard**: mirroring `tests/test_results_reproducibility.py`, a new test recomputes the
  interim numbers from `forces_t2a_newconv.csv` **and** asserts they appear in `RESULTS.md`, with the
  interim subsection's numbers **enumerated / asserted-complete** (set-equality scan of the subsection),
  the total peaks cross-checked against `body_frame_overall_match`, and the framing/disambiguation/"same
  peaks" wording asserted present — run **before** the doc edit (no unguarded headline number).
- **Issue #40**: check off the *cheap-interim* checkbox with this finding. **Do NOT close #40** — the full
  T4 decomposition + van Veen Fig 3–4 curve match remain. No commit message, PR title, or PR body may use a
  closing keyword (`closes`/`fixes`/`resolves`) next to `#40`; reference it as **`advances #40`** / *#40
  cheap interim* only (repo convention is `(closes #N)` — that must be suppressed here).
- **`docs/aerodynamics_validation/roadmap.md`** (T4 row): a one-line note that the cheap interim is
  delivered (cluster-free), full T4 still open — traceability only.

## Non-goals (explicit)

- **No graded-gate change.** The plausibility gate stays on `ib_force`; `VAN_VEEN_CF_TARGETS`
  (chord 0.3 / normal 2.4, tol 0.6) and `VAN_VEEN_BAND` are **unchanged**. No new pass/fail against van
  Veen for the subtracted value (CC-V2 — the interim isolates a share, it does not re-grade).
- **No re-derivation** of the added-mass magnitude or the rotation — reuse `added_mass_force` (#36) and
  `body_frame_coefficients` + the `R(t)` mirror (T2a). Two defect classes kept separate (CC-V4).
- **Cluster-free.** Committed `forces_t2a_newconv.csv` only; no new sim, no cluster (CC-V3).
- **Not the full T4**: no digitized van Veen Fig 3–4, no time-resolved CF_x(t)/CF_z(t) curve RMSE /
  peak-phase match, no translational+rotational+added-mass decomposition. **Not** T3 (medium grid).
  `VAN_VEEN_BAND` and the match tolerances are **not** loosened. #40 stays **open**.

## Impact

- **Specs:** `flapping-wing-validation` — one ADDED requirement (the reported diagnostic) + one MODIFIED
  requirement (the RESULTS reproducibility guard extends to the interim numbers).
- **Code:** `src/mosquito_cfd/benchmarks/flapping_wing.py` (one new pure function; no change to existing
  graders). Analysis-only, `uv`/numpy/pandas, no GPU, no solver, no Docker/CI change.
- **Tests:** `tests/test_wing_body_frame.py` unit + guard tests (the body-frame test home);
  `tests/test_results_reproducibility.py` doc guard. New tests reuse the existing module-level path
  constants (`_NEWCONV_CSV` / `_NEWCONV`), not fresh hard-coded paths, for cross-platform portability.
- **Docs:** `examples/flapping_wing/RESULTS.md`, `docs/aerodynamics_validation/roadmap.md`.
- **Reproducibility:** every reported number recomputes from a committed CSV (CC-V3); no run metadata,
  Docker image, or hardware is involved (pure post-processing of an existing artifact).
