# Fix stale and contradictory claims in the live force-surrogate and flapping-wing-validation specs

Advances #170 and #115.

## Why

Both live specs, where OpenSpec says the truth lives, state things the committed data does not
support. #170: the scale-invariance requirement uses one factor `k` in both directions. #115: result
numbers and claims frozen into requirements went stale as the corpora were rebuilt, and nothing
checks spec text against data.

- **#170.** The force-surrogate requirement "Re-normalization preserves surrogate skill
  (scale-invariance)" defines `k = f_ref_old / f_ref_new` and multiplies by it, which is right
  (`CF = F / f_ref` gives `CF_new = k · CF_old`). It then says "each new column equals the old divided
  by `k`". The sign case writes `CF_old/(−1)`, the same division form. It prints `k ≈ 3.119`; the
  value is 3.11972, which is 3.120 at three decimals.
  `tests/test_force_surrogate_scale_invariance.py` multiplies the committed parquet by `k` and calls
  it `r2_after`. But the parquet has held new-convention coefficients since #36 (`c74d69b`
  multiplied all 12 `CF_*` columns by exactly `k`, verified), so `× k` converts nothing. R² is
  invariant under any common scale, so no assertion is wrong; the wording, the names and the printed
  `k` are. PR #172 fixed the same mislabel in V3, which re-expresses the parquet as `stored / k`.
- **#115.** Every number below was recomputed from committed data, not copied from the issue, whose
  table is out of date. #127/#128 have since removed `CF_y −3.61` and `R²≈0.98`, and PR #168 the T4
  `2.61`/`0.058` claims.

  | Spec | Text | Committed data |
  |---|---|---|
  | FS `:1682` | latency speedup "~310× on the coarse grid" | `examples/prelim_sweep/figures/evidence_figure_metrics.json` `speedup.latency_speedup` = 371.82 |
  | FS `:1721` | parallelism factor "≈12,009×" | `speedup.parallelism_factor` = 7470.44 (coarse), 15462.56 (fine); the toy fixture gives 11,994.4 |
  | FS `:1677` | throughput speedup "equals `latency_speedup × batch_size`" | coarse 371.82 × 12,535 = 4.66e6 vs `throughput_speedup` 2.78e6; fine 6.81e7 vs 8.40e7 (fine's measured parallelism factor exceeds N) |
  | FS `:1637` | the QS model "under-predicts the in-band CFD lift" | `quasi_steady_reference.overshoot_factor` = 1.344 (coarse), 1.407 (fine); `:1594` of the same requirement already says it over-predicts |
  | FS `:1593-1595` | "(≈ 0.7)", "(≈ 1.3, …)", "tracked in #115" | history inside a requirement; the value is the corpus's to report |
  | FS `:1691-1697` | Note: "~310×, N=12,535, ≈12,009×, 3.7×10⁶× are stale" | wrong about N (`speedup.batch_size` = 12535 in both sidecars); 3.7×10⁶× and ≈310× in the scenarios are the synthetic fixture's known answers (`tests/test_force_surrogate_evidence_figure.py:125-126`), which the spec does not say |
  | FS `:2694-2696` | "usable tolerance window of only about 1.3×"; "separates … by roughly two orders of magnitude" | both rest on the truncated fine corpus, no longer committed; the archived D6 limits ~150× to the extreme pair and records 5 of 15 affected configs as indistinguishable; healthy max 0.0091 vs truncated min 0.0150 is ~1.6× |
  | FS `:2694` | normalizing by the peak (implied) removes the pitch-amplitude dependence | it reduces it: maximum normalized ratio p30 0.0056, p60 0.0091 (coarse); 0.0041, 0.0081 (fine), 4 d.p. |
  | FS `:2711`, `:2724`, `:2829` | `3.06e-4`, "83%" in scenario Givens | archived #92 values (s55_f115_p30), used by no committed artifact or test; and #92's CFL truncation had a full step count, so "a truncated config fails the symmetry check" overstates it |
  | FS `:1355-1357` | `config_mean_r2` is "the physically-central" skill | `:1655` calls it unreliable; coarse `seed_sweep.range.CF_x.config_mean_r2` runs −6.70 to 0.65 |
  | FWV `:221-229` | "the α=0 midstroke" | with `φ = φ_amp sin ωt`, `α = α_amp cos ωt`, the pitch is zero at stroke reversal (`t = T/4`); `tests/test_wing_kinematics.py:151` correctly measures reversal |

  The same claims appear in code docstrings: `evidence_figure.py:472` ("equals ``latency_speedup *
  batch_size``"), `train.py:531` ("physically-central"), and the `SYMMETRY_RATIO_TOLERANCE` comment
  in `corpus_guards.py` (pre-#147 signed ranges).

  Every other data-dependent literal in both specs was recomputed and matches (about 65: 25 in
  force-surrogate, 40 in flapping-wing-validation). Line numbers in this change refer to `c87e39c`.

## What Changes

- **#170** (`design.md` D1). `k = f_ref_old / f_ref_new` is kept and stated once with its direction,
  printed `≈ 3.120`.
  - `:1896` now says "multiplied by `k`", and the `k = −1` case says `−CF_old`.
  - The scenario re-expresses the new-convention parquet on the peak-tip reference by dividing by
    `k`, and says this changes the normalization only (not the pre-#36 corpus).
  - The test does the same: `/ _K`, V3 parity, locals renamed, RMSE and MAE `== committed / k`, and
    the `3.120` literal.
- **#115, per item** (`design.md` D2 has the full table). The rule is to delete a corpus result whose
  value is not the point and state the behaviour it illustrated. No corpus result is refreshed into a
  spec.
  - Delete "~310× on the coarse grid", "≈12,009×", "(≈ 0.7)", "(≈ 1.3, …)", the #115 note, "2.9%",
    "1.3×", "two orders of magnitude", `3.06e-4`, both "83%".
  - The QS RMS ratio becomes direction-neutral; `overshoot_factor` is called a historical key name,
    and a scenario is retitled.
  - The parallelism factor is defined as `throughput_speedup ÷ latency_speedup` (= `N · t_single /
    t_batch`), a measured ratio that is never stated as N.
  - The evidence-figure scenarios' 5.17e7, 2000, 12,535, ≈3.72e6 and ≈310× are labelled as
    synthetic fixture values.
  - `config_mean_r2` becomes a diagnostic, never the headline.
  - The gate's symmetry ratio is named as lab-frame `CF_x`, a backstop that reduces but does not
    remove the pitch-amplitude dependence. The two truncation scenarios no longer imply it catches
    every truncation.
  - The stroke-motion requirement names stroke reversal and mid-stroke correctly, names the two
    distances the test measures, and gains a mid-stroke scenario.
- **Guard (new)** (`design.md` D3-D5). Two ADDED requirements.
  - `tests/_spec_claims.py` builds each spec's effective text (live spec plus active deltas). It
    tolerates other sessions' overlapping changes, except on a requirement this guard number-checks.
  - `tests/test_live_spec_claims.py` checks that text:
    - a retired-claim tripwire with a verbatim stale example and must-pass corrective sentences per
      pattern, over both specs and three code files;
    - an enumeration-complete registry over the 10 guarded requirements: every number is
      recomputed, fixture or declared, and is printed exactly as its source formats it;
    - a permanent red against the pre-change text, kept as four fixtures;
    - synthetic must-fail and drift tests.
- **Docstrings and comments** (no behaviour change in `src/`): `compute_speedup`,
  `compute_config_resolved`, and the `SYMMETRY_RATIO_TOLERANCE` comment.
- **Tests** (`design.md` D6):
  - the evidence-figure fixture moves to `tests/_evidence_fixture.py`, with
    `TOY_ROWS_PER_WINGBEAT = 2000`;
  - the parallelism factor is asserted ≠ N;
  - the Euler-angle test is renamed to stroke reversal;
  - a mid-stroke known-answer test is added;
  - a symmetric-but-CFL-limited acceptance-gate test is added, and the CFL message is checked for
    the config name and minimum dt.
- **Docs**: `docs/CHANGELOG.md` [Unreleased].

## What does not change

- No behaviour under `src/`; no committed artifact, figure, corpus or surrogate.
- Requirements not in the deltas. The ~65 matching literals elsewhere stay unguarded; a follow-up
  issue tracks a registry for them.
- "Committed evidence-figure artifacts with provenance". Its "predates them" parenthetical is stale,
  but the in-flight `add-surrogate-comparison-bench` change also modifies that requirement (copying
  the block unchanged), and two MODIFIED deltas on one block race at archive. The parenthetical is a
  follow-up-issue item, with the bench change as the place to fix it if it is still open
  (`design.md` D2).
- Requirement names: a rename is REMOVED + ADDED and breaks cross-references.
- READMEs and RESULTS.md. They state corpus numbers on purpose, and they already state the speedup
  decomposition correctly. They may say the QS model over-predicts; that is true of today's corpora,
  and the spec simply no longer asserts a direction.

## Impact

- Specs:
  - `force-surrogate`: 6 MODIFIED (Config-resolved metrics; Sane–Dickinson reference; Honest
    caption and speedup; Re-normalization scale-invariance; Post-run acceptance gate; Committed
    corpora reconciliation guards) and 2 ADDED.
  - `flapping-wing-validation`: 1 MODIFIED, 1 ADDED.
- Code (docstrings and comments only): `src/mosquito_cfd/force_surrogate/evidence_figure.py`,
  `train.py`, `corpus_guards.py`.
- Tests:
  - new: `tests/_spec_claims.py`, `tests/test_live_spec_claims.py`, `tests/_evidence_fixture.py`,
    `tests/fixtures/spec_claims/stale_force_surrogate.md`,
    `tests/fixtures/spec_claims/stale_flapping_wing_validation.md`,
    `tests/fixtures/spec_claims/stale_code_prose.txt`,
    `tests/fixtures/spec_claims/stale_fwv_pre168.md`;
  - edited: `tests/test_force_surrogate_scale_invariance.py`,
    `tests/test_force_surrogate_evidence_figure.py`, `tests/test_wing_kinematics.py`,
    `tests/test_acceptance_gate.py`.
- Docs: `docs/CHANGELOG.md`; after archive, `docs/force_surrogate/roadmap.md` (next free row).
- Other sessions:
  - A future delta that modifies a guarded requirement must keep its numbers registered, or CI fails
    on that proposal's branch.
  - Two unarchived changes modifying the same guarded requirement fail CI with both change names and
    a "second to merge reconciles" message.
  - In-flight changes checked today (`add-surrogate-comparison-bench`,
    `share-light-corpus-helpers`, `add-real-comparison-figures`) touch no guarded requirement and
    carry no retired phrase.

## Out of scope (noted, not fixed)

- Follow-up issue #176: a registry for the remaining matching literals in both
  specs, plus minor items from the sweep and review:
  - the "predates them" parenthetical at FS `:1773` (fix it in `add-surrogate-comparison-bench` if
    that change is open, otherwise here);
  - FS `:1332`, the `CF_y` near-zero-variance hedge (every committed target's R² is finite);
  - FWV `:608/:614`, "~0.1 %" understating a 0.013 % agreement;
  - FWV `:634`, "≈1.20" (method-dependent);
  - FWV `:550-552`, mutation claims no test exercises;
  - FWV `:547`, 27° dominance, not recomputed;
  - `sane_dickinson_cf_z`'s docstring says `U/U_tip` while the speed is at `r_gyr`;
  - `test_generate_writes_three_artifacts` asserts `overshoot_factor > 1` on toy data;
  - tokens in the registry are sign-blind;
  - the Sane–Dickinson rationale says the model "omits … LEV lift", but the Dickinson–Lehmann–Sane
    (1999) `C_L(α)` fit already includes attached-LEV translational lift.
- #161, #154, #155, #142, #130/#131, #137 items 1–2.
