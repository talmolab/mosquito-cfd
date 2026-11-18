# Design: fix the van Veen quasi-steady model and re-grade T4

## Context

`decompose_wing_force` (T4) builds van Veen's translational + added-mass + Wagner model on our
kinematics and grades its normal peak magnitude against the CFD body-frame force. Since #109 the CFD
series is the IB force on the wing (`ib_w = −ib_force`, applied only through
`force_surrogate.force_on_wing`). This change corrects the model side of that comparison, and the
figures, docs and specs that quote it.

Paper: van Veen, van Leeuwen, van Oudheusden & Muijres (2022), JFM 936 A3, doi:10.1017/jfm.2022.31
(open access). It was read from a local PDF copy for this proposal, and one reviewer re-verified
every row below against the PDF independently.

## Evidence from the paper

| Claim | Where | What the paper says | Status |
|---|---|---|---|
| `S_yy` | eq 1.2 (A3-6) | `S_yy = ∫₀ᴿ c(y)·y² dy` | printed |
| `S_cy` | eq 1.8 (A3-7) | `S_cy = ∫₀ᴿ c(y)²·y dy` | printed |
| `S_cy` for an ellipse | eq 2.11 (A3-14); fig 2e | Eq 2.11 as printed omits a factor and evaluates to `(π/8)·c²R² = 3.53` for our wing. Fig 2e plots values that match `c²R²/3` (3.0 for our wing). | eq 2.11 is misprinted; value from eq 1.8 and fig 2e |
| Coefficients | §3.1.2 (A3-24); §4 eqs 4.1–4.6 | 3.13 (3.10, 3.15); 0.96 (0.95, 0.97); −1.02 (−1.06, −0.98); A, B, C = 8.5e-5 (6.8e-5, 10.2e-5), −1.2e-2 (−1.4e-2, −1.0e-2), 0.41 (0.37, 0.44); 0.104 (0.101, 0.107) | printed; equal to the pinned constants and CIs |
| Second polynomial set | §4.4 eq 4.7 (A3-41) | 1.0e-4 (0.7e-4, 1.3e-4), −1.4e-2 (−1.6e-2, −1.1e-2), 0.43 (0.37, 0.48) | printed; differs from §3.1.2 |
| Eq 3.12 unit | §3.1.1, §3.1.2, fig 4b | No unit is printed. Above 36° the tangential-to-normal ratio is −0.01 ± 0.01 (n = 6); the coefficients "tend to decrease in magnitude with angle of attack"; fig 4b's curve falls from about 0.4 to about 0. Degrees gives 0.31 at 9° and 0.019 at 90°. Radians gives 0.41 → 0.39 and a ratio of +0.14. | not printed; confirmed as degrees by the published dataset (below) |
| `α` is an angle of attack | §2.4 (A3-14) | "Because in the simulations there is no difference between the pitch angle and the angle of attack, we will always refer to this angle as the angle of attack" | printed |
| No reversal in the simulations | §1.2, §2.5 | "wings that perform only a stroke motion, without wing-pitch movements"; "The angle of attack was kept constant throughout each simulation"; α = 9°–90° in 9° steps | printed |
| Inputs for a flapping wing | fig 1c–e | Stroke rate plotted non-negative; acceleration positive early and negative late in each half-stroke. The angle of attack is about 45° at mid-stroke on both strokes, but **leaves `[0°, 90°]` near reversal** (the mosquito curve dips to about −25° and rises to about 105°). | partly supports our convention |
| Sign through a stroke | §1.2; §3.3; fig 13e,g | Added mass is "positive during the acceleration phase … negative during the [deceleration]". In the paper's wing frame `F_z` alternates sign by half-stroke (fig 13e,g), because its wing keeps the same leading edge and flips through vertical. | printed; our frame mirrors it (D4) |
| Wagner for deceleration | eq 3.15 / 4.1 | `sign(ω̇)·√|ω̇|` | printed |
| No pitch-rotation term | §2.8 (A3-20) | "we did not include a (wing-pitch-rate-related) rotational-lift mechanisms in our model" | printed |

**Not available.** §2.8 points to supplementary material S1.1 for "more details about the quasi-steady
application of the new model". How the paper handled angles outside 0°–90° is there. The journal
page offers one supplementary file, the dataset below, and no S1.1 text. #156 asks the
authors for it.

## Evidence from the published dataset

Supplementary database S1 (one 133 KB zip from the article page, downloaded 2026-11-17, SHA-256
`562ba942…0f5a5b`) holds 15 MATLAB files: `wing_geometry_DB.mat` (chord profile and stored `Syy`,
`Scy`, `Swe` for 14 wings) and one file per wing with the angle of attack (degrees), stroke rate,
stroke acceleration and end-of-simulation forces. It was read after review rounds 1 and 2. A round-3 reviewer recomputed every row with an independent
script; the values below are the ones both calculations give, with the density taken as 1.

| Claim | What the dataset shows |
|---|---|
| `S_cy = ∫c²·y dy` | Stored `Scy` equals that integral of the stored `c(y)` to four digits for all 14 wings. For the 12 ellipses it is 0.994–1.001 of `c²R²/3` and 0.84–0.85 of eq 2.11 as printed. |
| Our planform's value | The 3 mm ellipse has `Scy/Syy = 0.450`; the nominal closed forms give `3.0/6.627 = 0.453`. |
| `S_WE` | Stored `Swe` equals `∫√(c³y³) dy` of the stored `c(y)` to four digits. The mosquito profile starts at `y = −2.2e-5`, so three of its rows have a negative radicand, which is clipped at 0. |
| Eq 3.12 is in degrees | A least-squares refit on all 1,089 fruit-fly rows gives (7.6e-5, −1.14e-2, 0.410) in degrees, each inside its §3.1.2 interval, and 0.094 for the tangential added-mass coefficient (printed 0.104; 0.101–0.107, so below its interval). In radians the same fit is (0.25, −0.66, 0.41). A refit on the 43 steady rows alone gives (1.04e-4, −1.46e-2, 0.464), which is close to the §4.4 set and has its constant outside the §3.1.2 interval. Degrees is settled; which printed set is better is not. |
| Normal coefficients | A free fit of the three normal terms gives density × (3.147, 0.966, −1.054) against the printed (3.13, 0.96, −1.02). With the density taken as 1, each lies inside its printed interval (3.147 is 0.003 below the upper edge of 3.10–3.15). With `Syy` in the added-mass term the fitted coefficient is 0.547. The paper's density is not in the text available to this project; 1 is the value under which all three fits land in their intervals. |
| Input domain | Angle of attack 9°–90°, stroke rate 250–1750 rad/s (never ≤ 0), acceleration −4.5e6 to +4.5e6 rad/s². |
| Tangential sign | `Fx` is negative in 997 of 1,089 rows, where the printed tangential coefficient is positive: the dataset's x-axis points against the tangential force the model returns. This says nothing about the chord direction in our body frame (D4). |
| Model against data | Error is `sqrt(Σ(model − data)² / Σ data²)` over the fruit-fly rows, with the pinned coefficients, the dataset's moments and density 1. `Fz`: 0.016. `−Fx`: 0.159 with the §3.1.2 set and 0.210 with the §4.4 set (steady rows alone: 0.314 and 0.287). With `Syy` for `Scy` the `Fz` error is 0.37; with the polynomial in radians the `Fx` error is 1.49. Rows at 27° or less carry 80 % of `ΣFx²`, so the tangential figure says little about higher angles. |

The dataset does not address the reversing-wing recipe: every row is a single stroke at a constant
angle of attack. Its steady tangential coefficient also varies about fourfold with stroke rate (at
9°, 1.2 at 250 rad/s and 0.29 at 1750 rad/s); eq 3.12 is one fit across those. This is recorded on
the open chord issue as a lead and is not stated as a cause in any doc.

**Which coefficient set.** The paper is inconsistent. §4.4's comparison with Sane & Dickinson ("5 %
lower") implies 0.41, the §3.1.2 set. The §3.1.1 ratio is reproduced slightly better by the §4.4 set.
This change keeps §3.1.2's (they are the fit eq 3.12 belongs to, and already pinned). The choice
affects only the chord outputs, not the graded normal, and the docs say so. The published dataset
does not settle it either: the §3.1.2 set fits the accelerated rows better and the §4.4 set fits
the steady rows better (table below). Docs refer to "the §4.4 set" without quoting its digits,
because its constant is one of the superseded numbers the stale-claim guard rejects (D13).

## Decisions

### D1. `S_cy` is the closed form of eq 1.8 for the nominal ellipse

`S_cy = (2/3)·chord²·span·(r_tip − span/2)`: integrate `c(y)² = chord²·(1 − ((y − y_c)/a)²)` times `y`
with `a = span/2`, `y_c = r_tip − span/2`. For span 3, chord 1, `R_TIP = SPAN` it is 3.0.

**The three moments are on three bases, and this change does not unify them.**

| Moment | Basis | Value | Nominal ellipse | Marker quadrature |
|---|---|---|---|---|
| `S_yy` | marker radius of gyration² × nominal area | 6.797 | 6.627 | 6.24 |
| `S_cy` | nominal closed form (this change) | 3.0 | 3.0 | 2.70 |
| `S_WE` | marker quadrature | 3.978 | 4.304 | 3.978 |

- The committed markers are smaller than the nominal wing in both chord (0.947) and span (2.95).
- **Why 3.0 and not 2.70.** 3.0 is the paper's integral on the wing the deck declares, has an exact
  known answer, and is the value #141 reports. 2.70 would match `S_WE`'s basis but not `S_yy`'s.
  Neither choice makes the set consistent.
- **Effect on the grade (fine grid).** Gap 0.0174 with 3.0; 0.0185 with 2.70; 0.021 with a nominal
  `S_WE`. All pass. A test recomputes the gap under each and asserts the verdict holds, so the basis
  cannot be used to tune the grade.
- Unifying the bases changes `F_ref` and with it every coefficient in the corpora. That is a
  follow-up issue. A related caveat for that issue: the CFD coefficients are normalized by 6.797
  although the marker wing's `S_yy` is about 6.24.
- User decision 3 at approval can switch this to 2.70; the spec text and every T4 pin would change
  (the pins in tasks 1.4–1.5 are for 3.0).

**Run-time guard for a changed wing (added at approval).** The closed form is right only for an
ellipse with the nominal span, chord and root position. `compute_wing_area_moments` already reads
the wing file for `S_WE`; it also computes the marker `S_cy` and raises `ValueError` when that
differs from the closed form by more than 15 % (the committed wing differs by 9.9 %). The message
names both values and the wing file. The guard is a tripwire for gross errors only. Round 3 showed
what passes under it: the paper's mosquito planform rescaled to our span (−7.7 %), a same-area
rectangle (−7.5 %), and an ellipse whose root is moved 0.3 outboard (−1.0 %, although `S_yy` and
`F_ref` would then be about 10 % wrong). It cannot be tightened below about 12 % while the
committed wing sits at 9.9 %. It does not make the moments follow the geometry: `S_yy`
and `F_ref` still rest on the pinned ellipse constants. The follow-up issue on one planform basis
covers computing all three moments and `F_ref` from the wing file. Existing callers that pass
non-default `span`, `chord` or `r_tip` with the default wing file were listed by the round-3 reviewer:
none passes `chord`, `r_tip` or another wing file. Order of checks inside the function, which three
existing tests depend on: zero area, then a missing wing file, then too-fine binning, then this
guard (at 66 bins or more the committed wing already reads about 20 % low, and
`test_area_moments_guard_too_fine_binning` expects the too-fine message). The marker helper returns
both integrals from one call, so a test that patches it supplies both.

### D2. Eq 3.12 in degrees; keep §3.1.2's coefficients

`translational_force` evaluates `A·α_deg² + B·α_deg + C` with `α_deg = degrees(α)`. Coefficients and
CIs are unchanged. A code comment records the unit evidence and the §4.4 set. The fit range is
9°–90°; below 9° the polynomial is extrapolated, which for our waveform happens at every reversal,
where `ω² → 0`. The polynomial is slightly negative for roughly 58°–83°.

### D3. The pure model has an explicit input contract

`translational_force`, `added_mass_force_component`, `wagner_force` and `total_force` keep their
signatures. Contract: `α ∈ [0, π/2]`, `ω ≥ 0`, `ω̇` along the motion. Any out-of-range element raises
`ValueError`. `[0, π/2]` is the fitted range extended to zero and is this project's contract; it is
not presented as the paper's convention for a reversing wing. The guard would have caught #133 at
the first call.

### D4. One function derives the model inputs from the wing's motion

Under `R = Rz(φ)·Ry(α_p)` (zero deviation), a point on the span axis `r·ŷ_body` has lab velocity
`φ̇·ẑ × R·r·ŷ`. `Ry` leaves `ŷ` fixed, so the pitch rate does not enter. In the body frame:

    v_body = Rᵀ·v_lab = −φ̇·r·(cos α_p, 0, sin α_p)

With `s = sign(φ̇)` (or `sign(φ̈)` where `φ̇ = 0`) and `u = −s·(cos α_p, 0, sin α_p)`:

| Output | Value | For our waveform |
|---|---|---|
| angle of attack | `atan2(|u_z|, |u_x|)` | `|α_p|` |
| speed | `|φ̇|` | |
| acceleration along the motion | `s·φ̈` | positive early in each half-stroke |
| chord direction | `−sign(u_x)` | `s` |
| normal direction | `−sign(u_z)` | `+1` |

`decompose_wing_force` calls the model with the first three and multiplies each component's and the
total's `F_x`, `F_z` by the two directions.

- **Why derive, not fold in `sign(ω)`.** The two agree on this waveform. The derived form holds in
  every quadrant, which measured kinematics (#142 option 3) will need. A quadrant-table test and a
  second, non-sinusoidal trajectory make the difference testable; on the sinusoid alone it is not.
- **Our frame mirrors the paper's.** The paper's wing keeps its leading edge, so its `F_z` alternates
  sign and its `F_x` does not. Our wing pitches through horizontal and the opposite edge leads on the
  return stroke, so our `F_z` keeps its sign and our `F_x` alternates. For a plate symmetric about its
  chord midline the two are mirror images. The CFD agrees: `ib_w` normal is positive on both
  half-strokes and the chord mean is +0.18 forward, −0.17 on return.
- **Added mass.** Through this function the body-frame added-mass force is
  `ρ·S_cy·φ̈·(0.104·cos α_p, 0.96·sin α_p)`: the reaction to the body-frame acceleration, with no sign
  branch and no discontinuity. The existing code already had this sign right; only `S_cy` was wrong.
  A test asserts the series equals this closed form.
- **Reversal and rest.** `stroke_rate` never returns an exact zero on the CSV grids, so the
  `sign(φ̈)` rule is exercised by a direct call with a literal zero. `φ̇ = φ̈ = 0` returns zeros.
- **Zero components.** Where `u_x` or `u_z` is exactly zero its direction is 0 and that force
  component is zero. This drops the small eq 3.12 value at exactly 90° pitch (0.0185), which our
  waveform never reaches.
- **Two symmetries.** The fold relies on the plate being symmetric about its chord midline (either
  edge may lead) and about its own plane (either face may lead).
- **Limits, stated in the docs.** The model has no pitch-rotation term. The velocity formula is for
  points on the span axis; off it, the pitch rate adds a normal velocity the model does not see.

### D5. Two reported outputs are added; nothing new is graded

`_EXPECTED_DECOMP_KEYS` gains `normal_curve_corr` and `chord_curve_corr` (Pearson, signed series,
steady window). No `_pass` key. A zero-variance series raises. #133 asked whether a signed metric
should be graded: not here, because a gate added after seeing it pass is reverse-fit (CC-V2). For
the same reason the medium grid stays reported; fine and coarse are graded as they are today.

### D6. `T4_NORMAL_MAG_TOL` stays 0.16

The constant, its guard and its derivation test are kept. The derivation test recomputes the floor
from the corrected model (reviewers' prediction: grid term 0.146, floor 0.147, both relations hold).
See the HALT list in `proposal.md`.

### D7. Grid figures: reference lines by source

| Figure | Now | After |
|---|---|---|
| `fig_force_timeseries_3grid` | `_VV_BANDS` shaded 2.16–2.48 and 0.30–0.43 | dashed line at the model peak from `decompose_wing_force(fine)`; chord at ± the peak |
| `fig_grid_convergence_3grid` | `_VAN_VEEN` hard-codes (0.3, 0.43) and (2.4, 2.48), shaded | two lines: the model peak (computed) and the T2a target (imported from `VAN_VEEN_CF_TARGETS`) |
| `fig_grid_convergence` | one dashed line at a hard-coded 0.3 / 2.4, labelled "van Veen 2022 ~" | the same line, imported from `VAN_VEEN_CF_TARGETS`, labelled as the T2a target |

Tests use sentinel values for the model peak and the targets, so a typed literal fails, and assert
the exact set of shaded spans, so the legitimate Richardson / GCI spans stay.

### D8. Existing tests that change

| Test | Today | After |
|---|---|---|
| `test_components_match_hand_computed` | eq 3.12 at `π/2` radians | at 90° |
| `test_force_direction_reverses_each_half_stroke` | signed pitch into the model | out-of-domain input raises |
| `test_total_is_sum_and_boundary` | signed pitch | in-domain inputs |
| `test_area_moments_hinge_origin` | `s_cy == s_yy` | `s_cy == 3.0`, `!= s_yy` |
| `_model_normal_series` helper | signed pitch, `s_cy = s_yy` | built on the production input function |
| `test_tolerances_derive_from_sourced_quantities` | patches `_s_we_marker_quadrature` with a lambda returning one number | patches the shared helper to return `(marker S_cy, analytic S_WE)`; a single number would reach the planform guard as `S_cy = 4.304` and raise. Also asserts the patched `S_WE` term is non-zero |
| `test_translational_chord_known_answer` | 0.42 | window peak (0.0573) against a dense-grid maximum |
| `test_t4_decomposition_numbers_reproduce`, `_T4_TABLE_VERIFIED` | 2.48, 0.11, 0.055, 0.42, 0.43; whole-doc literal search | corrected values at `abs = 5e-4`; literals matched whole, inside the T4 subsection |
| `test_t4_normal_panel_names_the_model_sign_issue` | figure text contains "#133" | no pending note; model normal positive in phase bands `[0.4, 0.6]` and `[0.9, 1.0)` |
| `test_3grid_normal_band_is_positive_only` | reads `_VV_BANDS` | replaced by the sentinel reference-line test |
| `test_every_chord_resolution_claim_cites_133` | every "resolved" claim cites #133; `assert claims` | deleted, one document case per commit; replaced by the stale-claim guard (D13) |
| `test_results_vocabulary_states_the_sign_and_the_open_question` | exact "Pending [#133](" strings; two `.index()` slices; pins phrases in the roadmap, the figures README and the CHANGELOG | #133 strings and slices removed; `ib_w` vocabulary assertions kept; each other document's assertion is removed in the commit that edits that document |
| `test_interim_framing_is_honest_and_disambiguated` | exact status row with "pending #133" | new status row; interim must not say resolved |
| `test_t4_resolution_attributed_to_t4_not_the_interim` | requires "resolved by" / "resolves" | inverted: forbids them |
| `test_grid_convergence_recomputes_from_committed_csvs` | requires "#40 remains open" | kept: #40 is reopened (user decision) |

Constraints the rewritten prose must keep satisfying, with no test change:
`test_results_doc_delivers_body_frame_and_t4_decomposition` ("t4 per-component decomposition",
"validated against van veen"); `test_listed_documents_link_the_sign_section` (the sign anchor in
`figures/README.md` and the roadmap sits on rows being rewritten);
`test_roadmap_t4_row_flipped_and_reframed`; `test_no_false_diffused_ib_claim` (no `×2.4`, no `2.64`);
`_readme_guards` on the fine README; the interim's "~3×", "~2×", "0.3", "#40", "#135".

Before any prose is re-quoted, `tests/` is grepped for the old phrase. Every new or rewritten guard is
mutation-tested on saved-bytes copies.

### D9. Prose rule and known deletions

Every number in prose is recomputed from committed data by a test. A sentence the corrected model no
longer supports is deleted. The docs are required to say that T4 does not resolve the chord PARTIAL;
the guard accepts negated forms (D13). Those sentences belong in the docs only: "does not resolve
#40" in a commit message or the PR text would close #40. Known deletions in `RESULTS.md` (lines at
`80d653a`):

- 32–34, 202–203: "added-mass (+) and Wagner (−) … roughly cancel" (both vanish near the peak).
  Also `flapping_wing.py:69–70`. This deletion wins over the "leave T2a sentences" scoping.
- 36–38: "working hypothesis is rotational drag + tangential added mass adding to it" (the model
  has no rotational-drag term, and its chord total is a quarter of the fine-grid CFD chord).
- 305–306: "the CFD peak leads" is kept only because a test asserts it on the corrected model.
- 312: the second #133 pointer.
- 44–45, 523: T4 "explains" the chord.
- 207–214, 546–549: "translational-chord peak of only ~0.42"; "#40 closed".
- 259–260: interim "resolved by … #40 closed".
- 281–289: the whole "Pending #133" note.
- 298–303: "the fine-grid gap (~11 %) now exceeds … GCI_fine = 3.7 %" (the corrected gap is below it).
- 317: "the CFD chord converges toward the model".
- 410–413: "The van Veen target (translational ~2.48) sits between the fine and the extrapolant".
- 426–431, 440–442, 525: the chord extrapolant "sits between … ~0.3 and … ~0.43".
- 92, 538: "(van Veen Eq. 1–2)" for the waveform; "van Veen: mid-stroke | MATCH".

Found by the round-3 reviewer and added to the list:

- `RESULTS.md` 315–316: "the chord total (0.41) now sits very close to the" model; 428: "approaching
  the physical chord target"; 27–31: the "total-vs-translational" framing is re-read against the
  corrected chord.
- Aerodynamics roadmap 97, 102: "resolved the CF_chord PARTIAL", "apples-to-oranges".
- `docs/force_surrogate/roadmap.md` 220 and `fine-grid-pilot-report.md` 10: "off the van Veen
  QS-model target".

Two wording rules follow from the guard (D13). Docs say "#40 is open" and do not narrate that it
was closed and reopened; that history is in the issue. Docs name "the §4.4 set" without its digits.

### D10. T2a sentences stay, relabelled, with one note

The values 2.4 and 0.3 and the T2a verdicts are untouched. Where `RESULTS.md` attributes them to van
Veen's translational coefficients it says "T2a target" instead, and one note under the first T2a
table says they are pinned constants under review, not the paper's eq 3.9 / eq 3.12 values, citing
the follow-up issue. Without this the document would give two values for one quantity.

### D11. Unreleased CHANGELOG entries are corrected

Lines 46 and 60 sit under `[Unreleased]` and would ship describing a state that never shipped. They
are corrected so they state what ships; they are not annotated. The test assertion that pins "The T4
figure flags the normal" in line 46 is removed with the sentence. Line 77 states no superseded result
and stays. One new entry describes this change, verdict in words.

### D13. The stale-claim guard

One parametrized test, one case per document, added in the commit that edits the document. It is a
tripwire, not proof: round 3 found phrasings no pattern list anticipates. The line list in D9 and
the repo-wide grep in task 5.3 remain the primary control.

- **Normalization.** Remove Markdown emphasis and code marks (`*`, `_`, `` ` ``), collapse all
  whitespace including newlines, lower-case. Anchors are normalized the same way (`CF_chord`
  becomes `cfchord`).
- **Blocks, then sentences (changed after the PR review).** The text is first cut into blocks:
  a heading, a list item, a table cell and a paragraph are each their own block. Each block is
  normalized and split after `.`, `;`, `:`, `!` or `?` (optionally followed by a closing
  bracket or quote) and a space. A claim is excused only by a negation that comes **before**
  it in the same sentence:
  `\b(not|never|neither|nor|cannot|no)\b|n['’]t\b|\bun(resolved|explained|settled)`.
  The first version normalized the whole document before splitting; the review measured
  22–57 % of each guarded document inside sentences its negation rule exempted.
- **Claim patterns, rejected in a sentence that is not negated.**
  - `(?<![-\w])resolv\w*|(?<![-\w])resolution\W+of\b` together with `t4|#40|partial` in the
    same sentence ("under-resolves" and "under-resolution" are about the grid and are skipped)
  - `explain\w*|accounts?\W+for|settle[sd]?` together with `chord` in the same sentence
  - `sits\W+(very\W+)?close\W+to\W+the\W+model`, `close\W+agreement`
  - `converges?\W+to(ward)?\W+the\W+(qs\W+)?model`
  - `apples-to-oranges`
  - `physical\W+chord\W+target`, `qs-?model\W+(chord\W+)?target`
- **Patterns rejected in any sentence, negated or not.**
  - `(pending|awaiting).{0,20}#133|#133.{0,20}(pending|awaiting)`
  - `#40\W+(is\W+|remains\W+|was\W+)?(closed|resolved|done)`, `clos\w+\W+#40`
  - `roughly\W+cancel`, `full qs model total`, `near 0\.18`
  - `should\W+never\W+have\W+been\W+compared` (it contains "never", so it cannot be a
    negation-skipped pattern)
  - `0\.3\s*(–|—|-|to)\s*0\.43`, `\+?115\s?%`, `(?<![\d.])4\s?(–|—|-|to)\s?5\s?%`
  - whole-number superseded values: `(?<![\d.])2\.48(?!\d)`, `(?<![\d.])0\.43(?!\d)`,
    `(?<![−\-\d.])0\.42(?!\d)` (so `drop_frac ≈ −0.42` stays), `(?<![\d.])0\.05[58](?!\d)`
- **Known cost of the number patterns.** They reject those digits with any meaning, for example
  "phase 0.43". No document needs such a number today; if one later does, the pattern gets a
  narrow exception with its own mutation test, not a blanket removal.
- **Known cost of sentence negation.** "T4 resolves the chord PARTIAL, not the normal" would pass.
  Accepted: the alternative, a lookbehind, rejected seven required sentences in round 3.
- **Anchors.** Each document must exist and contain its own anchor: `RESULTS.md` the T4 subsection
  header and "#40 is open"; `figures/README.md` `fig_force_decomposition`; the aerodynamics
  roadmap its T4 row; the fine README a link to the `RESULTS.md` T4 subsection; the two
  force-surrogate documents `CF_chord`; the CHANGELOG its new entry, located by "#141".
- **Scope.** The aerodynamics roadmap is scanned without its dated reconciliation log (from the
  header "## Reconciliation log" to the end of the file, asserted found). The log's dated T4
  subsection ("T4 normal peak-PHASE reported, not gated") states the superseded phase gap, so it
  gets one added line marking it superseded by this change, and a test asserts that line is
  present. `flapping_wing.py` is scanned on its `tokenize` COMMENT tokens and its docstrings
  (`ast.get_docstring` on the module and every function).
- **Mutation.** Each forbidden form is restored in plain, bold and line-wrapped variants, and each
  anchor removed, per document. Both polarities are tested: six of the negated sentences round 3
  listed must pass (the seventh, "T4 does not close #40", is rejected by the closing-#40
  pattern under the D9 wording rule), and the fourteen affirmative ones it listed must fail.

The round-2 patterns were run against the current files by the round-3 reviewer: every hit was
stale text. The patterns above are new in round 3 and are first run in task 1.6; they are
re-checked against the rewritten documents in task 5.3.

### D14. The model is tested against the paper's own CFD forces

`fruitfly.mat` (14 KB) and `wing_geometry_DB.mat` (109 KB) are committed unmodified under
`tests/fixtures/van_veen_2022/` with a README giving the source URL, the download date, the SHA-256
of each file and of the zip, the citation, and the licence basis (the article is CC BY 4.0 and its
data-availability statement says the data are openly available at the article DOI; the zip has no
licence file). The user approved committing them. Tests read them with `scipy.io.loadmat` (`scipy`
is in the `viz` group, which CI installs); no `importorskip`, so a missing dependency fails instead
of skipping. Every column is cast to `float64` at load: the file stores `aoa` as uint8, `sr` as
uint16 and `sa` as int32, and `sr**2` overflows in uint16.

- **Density is fixed at 1, not fitted.** A density fitted on the steady rows absorbs any error in
  the 3.13 coefficient (round 3 showed 3.13 → 3.45 passing). The value 1 is an assumption the
  free fit supports; the authors are asked to confirm it.
- **Metric.** `sqrt(Σ(model − data)² / Σ data²)` over all 1,089 rows.
- **Normal force.** Error below 0.03 (observed 0.016). At density 1 a change of 3.13 to 3.31 or to
  2.95 gives 0.050 and fails; dropping the Wagner term gives 0.22; `Syy` for `Scy` gives 0.37.
- **Free fit against the pinned intervals.** A least-squares fit of the three normal terms must
  land inside the module's pinned intervals for 3.13, 0.96 and −1.02. This ties the pinned
  intervals to the data instead of to our typing of them.
- **Tangential force.** Error below 0.25 for `−Fx` (observed 0.159). The bound is set to admit both
  of the paper's printed coefficient sets (the §4.4 set gives 0.210): the test is not meant to
  choose between them. Radians gives 1.49, a flipped sign on either tangential term gives 1.15,
  and dropping the tangential added mass gives 0.57.
- **The bounds are regression bounds, chosen after seeing the results.**
- **Moment definitions.** `van_veen_model.py` gains one pure function that integrates `c²·y` and
  `√(max(c³y³, 0))` over a given `(c, y)` profile. The marker quadrature calls it after binning,
  and the dataset test calls it on each wing's stored profile, so the test exercises production
  code.
- **What these tests cannot detect.**
  - An error of a few per cent in one normal coefficient (the constants themselves are pinned by
    `assert_coefficients_not_loosened`).
  - Tangential behaviour above about 27°: removing the translational tangential term at 54° and
    above moves the error from 0.159 to 0.164.
  - Anything about the input function. The dataset has no reversing wing.

### D12. #142 relabel is the last commit

Labels only: `wing_kinematics.py` docstrings (including "pitch/angle-of-attack"),
`docs/coordinate-convention.md`, `RESULTS.md` (lines 54, 82, 92–95, 535–538), `figures/README.md:20`,
`openspec/project.md:38`, `benchmarks/METHODS.md:126`, `inputs.3d.production` comments (only if no
hash pins that deck), the `generate_all_figures.py` K1 title. A keep-list protects the correct van
Veen citations (axes, rotation order, normalization, `S_yy`, hinge, the model).
`generate_all_figures.py` rewrites four figures, so K1 is rendered to a scratch directory and only
`fig_kinematics.{png,pdf}` is copied back.

## What changed in each modified requirement (reader's guide to the 900-line delta)

| Requirement | Change |
|---|---|
| Plausibility gate | T4 pointer: chord "reported, not explained"; "~2.4" called the pinned target |
| Body-frame comparison | chord PARTIAL "not resolved"; "~2.4"/"~0.3" called pinned targets |
| RESULTS reproducibility | T4 literals removed; production CSV is fine; literals matched inside the T4 subsection |
| Added-mass-subtracted diagnostic | "T4 resolves / closes #40" removed; docs must not say so |
| Van Veen model | input contract and domain guard; eq 3.12 in degrees; two scenarios replaced, one added |
| Area moments | `S_cy` definition; eq 2.11 misprint; mixed-basis statement; two scenarios added |
| Decomposition | fed through the input function; correlations; fine + coarse graded, medium reported; literals removed |
| IB force on the wing | correlations listed; verdict-invariance scenario no longer says "no edit to those literals" |
| Docs requirement (renamed) | RESULTS as single numeric source; limits; T2a note; stale-claim guard; roadmap scenario kept |
| Added: model inputs | D4 |
| Added: grid-figure reference lines | D7 |

## Commit plan

Every commit is green on `uv run --frozen pytest -m "not gpu"` and CI's ruff lines. The HALT checks
run in the working tree before commit 2 is recorded.

1. `chore(openspec): propose fix-van-veen-model-regrade-t4`
2. `fix(t4): van Veen model takes angle-of-attack inputs; S_cy and eq 3.12 corrected`: model, input
   function, `decompose_wing_force`, their tests, the T4 pins, and all of `RESULTS.md` with its
   guards (the tests that pin the T4 numbers read the document, so it cannot lag the model).
3. `fix(figures): single-source reference lines replace the van Veen bands; re-render T4 and grid figures`:
   four scripts, eight binaries, their tests, and `figures/README.md` with its guard case.
4. `docs(t4): state what the corrected model supports; drop the chord-resolution claims`: the
   roadmap, the fine README, the two force-surrogate docs, the CHANGELOG, and their guard cases.
5. `docs(kinematics): label the sinusoidal waveform as generic validation kinematics`

Between commits 2 and 4 the roadmap, the fine README and the CHANGELOG still carry the old T4
numbers; nothing is pushed until all five exist.

Commit bodies say "Advances #N". No commit message, PR title or PR body puts close / fix / resolve
(any inflection) directly before an issue reference; a grep over all three enforces it. Commits are
not rewritten once recorded; fixes go on top; main is merged in, never rebased onto.

## Risks

- **A guard keyed on literal text stops checking.** D8's grep-first rule, positive anchors, mutation tests.
- **Parallel session.** `docs/CHANGELOG.md` `[Unreleased]` is the likely conflict; the entry is its own
  bullet and main is merged in before push. `project.md:38` and `force_surrogate/roadmap.md` edits are
  single lines, made in the last commits.
- **S1.1 could describe a different input recipe.** It is not published; #156 asks the
  authors. The docs name the evidence used.
- **Dataset licence.** The zip has no licence file; the article is CC BY 4.0 and states its data are
  openly available at the article DOI. The user decides at approval whether the two files are
  committed (proposal, decision 5). If not, D14's tests are dropped and the evidence table stays.
- **Re-rendered figures.** Three of the five PDFs embed a creation date; `CreationDate: None` is added
  to those `savefig` calls. Before each commit `git status --short` must list exactly the intended
  binaries.
