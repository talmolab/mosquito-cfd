# Review reconciliation: `/review-openspec`

Two rounds. Round 1: five reviewers (spec quality, test plan, physics against the paper,
documentation, git workflow) on the first draft; verdict **NEEDS REVISION**, 11 blocking findings,
none against the physics. Round 2: one reviewer re-checked the revision; verdict **NEEDS REVISION**,
1 blocking finding (the stale-claim guard) and 9 important ones. Both rounds are reconciled below.

Each row gives the reviewer's words, what changed, and where. Locations are stable names, not line
numbers, because the files kept moving: a task id in `tasks.md`, a decision id in `design.md`, a
section of `proposal.md`, or a requirement / scenario title in a spec delta (`F` =
`specs/flapping-wing-validation/spec.md`).

## Round 1: blocking

| # | Reviewer's finding (verbatim) | Resolution | Where |
|---|---|---|---|
| G-B1 | "Commit 2 (`fix(model)`) leaves every `decompose_wing_force` caller raising… Fix: merge commits 2 and 3." | Model and T4 are one commit. | design "Commit plan" item 2; tasks section 1 |
| G-B2 | "Commit 3 is red unless RESULTS.md's T4 numbers move with it… Fix: move the T4 table cells and graded-sentence numbers of RESULTS.md, `_T4_TABLE_VERIFIED`, and the line-363 literals into the model+T4 commit." | All of `RESULTS.md` and its guards move into commit 2 (round 2 showed the table cells alone were not enough). | tasks 1.5, 1.6; design "Commit plan" item 2 |
| G-K1 | "Every commit message lands on main… Gate for 6.4, run over `git log --format=%B origin/main..HEAD`, the PR title and the PR body: `grep -inE '\b(close[sd]?\|fix(e[sd])?\|resolve[sd]?)\b:?\s+(\S+/\S+)?(#\|https://github\.com/\S+/(issues\|pull)/)[0-9]'`. It must return nothing." | That command, over all three. | tasks 5.7 |
| S-B1 / D-B1 | "live-flap:87–95, scenario 'Docs disclose the lab-frame floor…', in the unmodified requirement… requires the docs to say 'chord **explained** and grid-limited, #50'… Add the requirement to MODIFIED and rewrite the Then-clause tail." | The plausibility-gate requirement is MODIFIED; body and scenario say the chord is reported, not explained. | F "Flapping-wing plausibility gate on ib_force…", body and scenario "Docs disclose the lab-frame floor…" |
| D-B2 | "The ~0.3 / ~2.4 sentences left in `RESULTS.md` contradict the corrected T4 text beside them… Put one note under the first T2a table… Rename the attribution, not the numbers: 'van Veen's translational ~0.3' becomes 'the T2a chord target ~0.3'." | Required by the spec; a decision; a task with an assertion. | F "T4 decomposition figure, RESULTS, and roadmap…" (the `VAN_VEEN_CF_TARGETS` sentence); design D10; tasks 1.6 |
| D-B3 | "The scoping rule and D9 disagree about the 'roughly cancel' sentence… State which rule wins. My recommendation is to delete all three." | D9 wins; all three are deleted; the guard forbids the phrase in bold or plain form. | design D9 (first bullet), D13; tasks 1.6, 1.7 |
| T-B1 | "Task 1.2's '3.0 within 2 % on a dense synthetic ellipse' is not achievable… Suggested rewording: 'the marker quadrature converges to the closed form: error under 5 % at 30 bins, under 1.5 % at 120 bins, and decreasing, on an outline of at least 2e5 markers; the dense-limit bias of the max-chord-per-bin estimator is documented.'" | That wording; the docstring states the bias. Round 2 confirmed it is achievable (+4.24 % at 30 bins, +1.20 % at 120). | F scenario "S_cy is the chord-based integral, with a known answer"; tasks 1.1, 1.7 |
| T-B2 | "Task 2.2 cannot fail first and exercises no production code… derive `aoa = atan2(\|v_z\|, \|v_x\|)`, speed `\|v\|/r`, chord direction `−sign(v_x)` and normal direction `−sign(v_z)` from the finite-difference velocity, then assert they equal the production helper's outputs. State h = 1e-6 and rtol = 1e-7, atol = 1e-8." | Exactly so. | F scenario "The derivation agrees with the canonical rotation"; tasks 1.3 |
| T-B3 | "Nothing in the plan can fail on the normal-direction sign or on the 'derive, not fold in sign(ω)' claim… Add a quadrant table test… pitch ∈ {+45°, −45°, +120°, −120°} × `φ̇` ∈ {+, −}… Feed B2's finite-difference check with a non-sinusoidal trajectory (constant pitch −45°, φ = t)… Add both mutants." | Quadrant table (all eight rows written out), second trajectory, both mutants. | F scenario "Directions are right in every quadrant…"; tasks 1.3, 1.9 |
| T-B4 | "The 4.2 stale-claim guard misses the dominant stale forms and is vacuous for two of the edited docs… use a case-insensitive regex per doc… add positive anchors." | Redesigned after round 2; see R2-B1. | design D13 |

## Round 1: important

**Physics (reviewer 3)**

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| P-I1 | "eq 2.11 as printed does not give 3.0… should cite eq 1.8 and fig 2e, and record the misprint so nobody later 'corrects' to 3.53." | Cited to eq 1.8 and fig 2e; misprint in the evidence table and a required code comment. | design "Evidence from the paper"; F "Wing area-moments…" (`S_cy` bullet) |
| P-I2 / S-5a / D-A1 | "the three moments use three different planforms, and the consistency claim is not accurate… Either pick one basis or document the mix." | Claim removed. The spec states the mix; a test asserts the verdict under each basis; unifying them is a follow-up issue; the user picks 3.0 or 2.70. | F "Wing area-moments…" (paragraph "The three moments do not share one planform basis") and scenario "The graded verdict does not depend on the planform basis"; design D1; tasks 1.4; proposal "Decisions" 3 |
| P-I2 | "'1.7 %' should not be quoted as a precision." | Stated; the docs must say so. | proposal "Numbers before and after"; F "Wing area-moments…" |
| P-I3 | "`[0, π/2]` is the fit range, not 'the paper's input convention'… The evidence table should add fig 13e,g." | This project's input contract; fig 1c's excursions and fig 13e,g are in the evidence table. | F "Van Veen quasi-steady force model…" (inputs paragraph); design "Evidence", D3 |
| P-I4 | "the new `chord_curve_corr` depends on the coefficient set… Report the chord outputs under both sets, or caveat the correlation in the docs." | Caveat required in `RESULTS.md` and added to the proposal. | F "T4 decomposition figure…" (limits bullet); proposal "Numbers before and after" |
| P-I5 | "the 1.7 % compares peaks at different phases from different mechanisms… Prose should not read the +0.98 correlation or the 1.7 % as confirming the Wagner term." | Required limits; forbidden to present the gap or a correlation as confirming a component. | F "T4 decomposition figure…" |

**Spec (reviewer 1)**

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| S-2a | "these still say the normal 'matches van Veen's reported overall normal (`~2.4`)'… 'within `VAN_VEEN_MATCH_TOL` of the pinned normal target (`~2.4`)'." | Rewritten in body and scenario Given. | F "Body-frame (chord/normal) per-component van Veen comparison" |
| S-2b | "'the **per-component** + total model coefficients' was narrowed… Restore 'per-component' or state the narrowing." | "per-component and total model coefficients and RMS shares" restored. | F "RESULTS.md headline numbers reproducible…" |
| S-2c | "a marker `S_yy` quadrature gives `≈6.30`, while :416 says `~6.24`." | Both 6.24 (round 2 measured 6.2415). | F "Wing area-moments…" |
| S-2d | "retains the model-derived literal '~0.001 on the normal peak'." | Removed. | F "Wing area-moments…" |
| S-2e | "dropping 'pinned before the committed-run result' is honest… make it an explicit line in `proposal.md`." | Stated in both. | proposal "What changes" (T4); F "Per-component decomposition…" |
| S-2f / T-I12 | "no spec text backs them any more… Suggested scenario: 'Roadmap T4 row keeps its delivered framing'." | Added; aligned with the existing test in round 2 (R2-I8). | F scenario "Roadmap T4 row keeps its delivered framing" |
| S-3a | "'`F_x` and `F_z` are the forces opposing the wing's…motion' is false for part of the accepted domain." | Reworded in the model requirement; the same phrase removed from the inputs requirement (R2-I5). | F "Van Veen quasi-steady force model…"; F "Angle-of-attack inputs…" |
| S-3b | "'`+0.042125` at one and `−0.042125` at the other' does not say which." | `+` at `t = 0`, `−` at `t = 0.5`, model total. | F scenario "The model is fed the angle of attack on both half-strokes" |
| S-3c | "Define `s` once… and write `s·φ̈`." | Done. | F "Angle-of-attack inputs…" |
| S-3d | "Scope the full statement to `RESULTS.md`, require the other three to 'not contradict it', and add the issue-pointer assertion once Decision 1 is made." | `RESULTS.md` is the single numeric source; the pointer is an anchor of the guard. | F "T4 decomposition figure…"; tasks 0.1; design D13 |
| S-4b / S-4c | "'the **chord** total curve is grid-limited…' Fix it in the same MODIFIED block." / "Reword to 'the pinned normal target'." | Both. | F "Flapping-wing plausibility gate…" |
| S-4d / D-M12 | "`coordinate-convention/spec.md:10`: 'angle of attack `α`…', unqualified… Modify line 10." | MODIFIED. | `specs/coordinate-convention/spec.md` "Project-wide axis convention…" |
| S-5b / D-A4 / D-A5 | "makes passing on the medium and coarse CSVs normative… Add medium and coarse to HALT, or make only fine normative." / "Medium is a new normative pass, added after seeing 2.9 %." | Fine and coarse graded, as in the live spec; medium reported; HALT covers both graded grids. | F scenario "Normal peak MAGNITUDE…"; design D5; proposal "HALT conditions" |
| S-6 | "`φ̇ = 0` and `φ̈ = 0` together… Specify raise or zeros." / "Pearson correlation on a zero-variance series returns NaN." | Zeros; a floor-based raise (R2-I7). | F "Angle-of-attack inputs…"; F "Per-component decomposition…" |
| S-6b | "`added_mass_force_component` takes no `ω`." | Body and task name the two components that take `ω`. | F "Van Veen quasi-steady force model…"; tasks 1.2 |
| S-7 | "three API breaks are listed under 'Public API' but not marked." | Marked **BREAKING**. | proposal "What changes" |

**Tests (reviewer 2)**

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| T-I1 | "Carried-over tolerances cannot kill the mutants… Pin at `abs=5e-4`." | All T4 pins at `abs = 5e-4`. | tasks 1.5 |
| T-I2 | "Pin them before 2.6 from an independent calculation." | Pins are written before the implementation task. | tasks section 1 intro, 1.5 → 1.7 |
| T-I3 | "Spec scenarios require pins that no task writes." | Coarse, medium, RMSE and both correlations pinned. | tasks 1.5 |
| T-I4 | "Pin 0.0573 against an independent dense-grid maximum at `abs=1e-4`, and keep 0.042125 for the instantaneous check." | Done. | tasks 1.4, 1.3; F scenario "Translational-chord is a known-answer…" |
| T-I5 | "Scope literal checks to the T4 section and use `(?<![\d.])lit(?!\d)`." | Done. | tasks 1.5; F scenario "T4 decomposition numbers recompute…" |
| T-I6 | "Task 2.3, clause 1 (continuity)… Say so in the task. The metric needs defining." | Replaced by equality with the closed form at every step; the task says it is a regression guard. | tasks 1.3 (last item); F scenario "Stroke reversal and rest are well defined" |
| T-I7 | "call the helper with literal `φ̇ = 0.0`, `φ̈ = ±a`, pitch 0 and pitch 0.3… Add `φ̇ = φ̈ = 0`." | Exactly those inputs. | tasks 1.3; same scenario |
| T-I8 | "Add an array with one bad element… NaN ordering…, `−0.0` accepted, and `np.nextafter(np.pi/2, 4)` rejected." | All present; a `.all()` mutant. | tasks 1.2, 1.9; F scenario "An input outside the model's input domain raises" |
| T-I9 | "Add `assert swe_rel > 0`." | Added; the patched name must be the one called. | tasks 1.4, 1.7; F scenario "The magnitude tolerance derives…" |
| T-I10 | "'Not a typed literal' is only failable by sentinel… Assert the exact set of expected span extents." | Sentinel test; exact spans per figure; red-first reason per figure; mutants. | tasks 2.2, 2.5; F "Grid figures draw single-source, labelled reference lines" |
| T-I11 / G-I2 | "Existing tests affected but not enumerated in tasks.md." / "two guards have vacuity traps." | Each is in D8 and in the task that edits its document. | design D8; tasks 1.6, 2.6, 3.2 |
| T-I13 / D-M1 | "Stale source comment outside every guard. `flapping_wing.py:66-77`." | Edited, and a guard case. | tasks 1.7 |
| T-I14 | "`_scaled_csv(−1)` flips both correlations exactly… Assert the `*_pass` key set literally equals `{normal_mag_pass, closure_pass}`." | Done. | tasks 1.4 |
| T-I15 | "Mutants missing from 1.8 and 2.10." | All named mutants listed. | tasks 1.9 |

**Documentation (reviewer 4)**

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| D-M2 / D-M3 | "Both percentages are relative to the old 0.43." / "Re-base it on the grid evidence." | Both re-based; both are guard cases that fail today. | tasks 3.2, 3.3 |
| D-M4 | "roadmap.md:249-260 (reconciliation log)… Add a dated addendum or list it as a dated record." | Dated addendum; the log is excluded from the guard by its header (R2-I3). | tasks 3.3; design D13 "Scope" |
| D-M5 – D-M7 | "'Explains / explained by' claims that no listed phrase catches." | Caught after normalization (R2-B1). | design D13 |
| D-M8 – D-M10 | "The conclusion reverses"; "Already false"; "The extrapolant 0.321 is three times the corrected model total." | In the known deletions. | design D9 |
| D-M11 | "Narrow the scenario to the CFD-side literals." | MODIFIED. | F "Flapping-wing coefficients report the IB force on the wing", scenario "Graded verdicts are unchanged by the sign" |
| D-M13 / D-M14 | "`inputs.3d.validation`… List it as deliberately untouched." / "`inputs.3d.production`… Relabel or list as out of scope." | Validation deck untouched, with the reason; production deck relabelled. | proposal "Out of scope"; tasks 4.3 |
| D-M15 | "#40 is CLOSED on GitHub… Tie decision 1 to this line and its test." | Decision 1 recommends reopening #40 and names the pinned sentence. | proposal "Decisions" 1; design D8 (last row) |
| D-M16 | "File before section 4." | Task 0.1. | tasks 0.1 |
| D-1x | "Only two have bands." | Corrected everywhere. | proposal "What changes"; design D7; tasks 2.2 |
| D-2 | "`proposal.md` never states 0.057." | Stated. | proposal "Numbers before and after" |
| D-A3 | "The proposal overstates the unit evidence… Reword." | A section separates printed from inferred. | proposal "What the paper supports, and what is inferred" |
| D-A6 / D-A7 | "Preliminary numbers omit two headline values." / reconcile with "peaks near 0.18". | Both in the table and its notes. | proposal "Numbers before and after" |
| D-A8 / D-4 | "The `arbitrary-geometry` delta makes unsupported paper claims… Suggested body." | The suggested body. | `specs/arbitrary-geometry/spec.md` |
| D-4b | "Suggest a guard, or an explicit keep-list." | Both. | tasks 4.2, 4.3; design D12 |
| D-5 | "Make the `RESULTS.md` T4 section the single numeric source." | A requirement. | F "T4 decomposition figure…" |
| D-6 | "Lines 46, 60 and 77 are all unreleased… Amend minimally; do not leave as-is… A test pins line 46." | Lines 46 and 60 corrected outright, with the pin removed (R2-I2); line 77 states no superseded result. | design D11; tasks 3.4 |

**Git workflow (reviewer 5)**

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| G-I1 | "fold the README figure captions into the figures commit." | All of `figures/README.md` moves with the figures (R2-I9). | tasks 2.6 |
| G-O1 | "Run the full re-grade and floor test in the working tree before recording any code commit." | Task 1.8, after implementation and before the commit. | tasks 1.8 |
| G-O2 | "Render to a scratch `--output-dir` and copy back only `fig_kinematics.{png,pdf}`." | Done. | tasks 4.4 |
| G-O3 | "The #142 relabel has no grep-first task." | Task 4.1. | tasks 4.1 |
| G-O4 | "`docs/CHANGELOG.md` is an unlisted conflict hot spot." | In Risks; main is merged in before push. | design "Risks"; tasks 5.8 |
| G-A1 | "Add `metadata={\"CreationDate\": None}`." | To the three `savefig` calls that lack it. | tasks 2.3, 4.4 |

## Round 2

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| R2-B1 (blocking) | "Stale-claim guard… T-B4 is not resolved. Fix the misses: tolerate markup and whitespace… forbid bare superseded numbers… add `full QS model total`, `clos\w+ #40`, `#40 is (closed\|resolved)`, `\+115 ?%`. Fix the false positives: exempt negations (for example a lookbehind for `not `…)… Replace the 'mentions T4' anchor with a per-document anchor… Correct 'Fails today on every document'." | Redesigned: text is normalized (emphasis and code marks removed, whitespace collapsed, lower-cased); the listed patterns are added; a `not ` lookbehind admits the required negations; per-document anchors; whole-number patterns for the superseded values. **Checked by running the patterns on the current files:** every one of the seven documents fails today; all 15 stale forms the reviewer listed are caught (including bold and line-wrapped ones); all 8 sentences the plan must keep or write pass. | design D13; F scenario "Claims the corrected model no longer supports are absent from every doc"; tasks 1.6, 1.9, 2.6, 3.2, 3.5 |
| R2-I1 | "List every literal that commit 2's scoped check requires inside the T4 subsection… and move those edits into commit 2." | All of `RESULTS.md` is in commit 2; the literals are enumerated. | tasks 1.5, 1.6 |
| R2-I2 | "Either write the 'superseded' carve-out into the spec, or correct CHANGELOG:60 outright. Decide line 77." | Corrected outright; no carve-out; line 77 stays. | design D11; F "T4 decomposition figure…"; tasks 3.4 |
| R2-I3 | "Say whether roadmap.md:253's '~0.058 cycle' is edited or the reconciliation log is excluded from the guard." | The log is excluded (located by header, asserted found) and gets a dated addendum. | design D13 "Scope"; F same scenario; tasks 3.2, 3.3 |
| R2-I4 | "State the sample times and exclude a neighbourhood of reversal." | 200 times, excluding those within 0.01 of a reversal. | F scenario "The derivation agrees with the canonical rotation"; tasks 1.3 |
| R2-I5 | "Define the direction at `u_x = 0` and `u_z = 0`; name both symmetries; drop 'so each opposes the wing's motion'." | Direction 0 and zero force component; both symmetries named; phrase dropped. | F "Angle-of-attack inputs…"; design D4 |
| R2-I6 | "'Reverting any one of the model corrections fails the pin' is false for the three gaps… name which pin kills which reversion." | Named: gap pins catch `S_cy`; chord pins catch radians; a signed pitch raises. | F scenario "Normal peak MAGNITUDE…" |
| R2-I7 | "'Zero variance raises' is not reliably testable… Specify a floor." | Standard deviation below `_DEGENERATE_CF_FLOOR`; tested on the helper directly. | F "Per-component decomposition…"; tasks 1.4 |
| R2-I8 | "Align with the test: no affirmative 'digitize van Veen Fig 3–4'; negated forms allowed." | Done. | F scenario "Roadmap T4 row keeps its delivered framing" |
| R2-I9 | "Move the `fig_force_decomposition` caption into the figures commit." | The whole README moves. | tasks 2.6 |
| R2 minor | HALT list missing the fifth check and listed before implementation; "one pin"; provenance wording; S-2b; dropped coverage of `coordinate-convention.md` and the `flapping_wing.py` docstring; figures with no spans; `RESULTS.md:36–38` and `:312`; process-relative wording; caveat on +0.97; the legend filter. | Each fixed. | proposal "HALT conditions"; tasks 1.8, section 1 intro, 2.3; design D1, D9; F (several) |

## Round 3

One focused reviewer (a smaller model, at the user's request) on the edits made after round 2: the
dataset evidence and test, the redesigned stale-claim guard, and the run-time planform guard. It
recomputed every dataset number with its own script. Verdict: needs revision in all three areas; no
finding was labelled blocking. The author re-ran the numbers it disputed before adopting them.

| # | Finding (verbatim) | Resolution | Where |
|---|---|---|---|
| R3-1 | "The mosquito `Swe` integrand is NaN as written… state `integrand = sqrt(max(c³y³, 0))` in tasks and spec." | Done. | design D14 "Moment definitions"; tasks 1.3b; F scenario "S_cy is the chord-based integral…" |
| R3-2 | "dtype traps in `fruitfly.mat`… add 'cast every column to float64 at load' to task 1.3b." | Done. | design D14; tasks 1.3b; F scenario "The model reproduces…" |
| R3-3 | "The spec says the production helpers take a wing's stored `c(y)`; they do not… either factor a pure `(c, y)` integrator that the marker helper also uses and test that, or reword D14." | The integrator is factored out and the marker helper calls it. | design D14; tasks 1.3b, 1.7 |
| R3-4 | "Fitting one density on the steady rows… absorbs any error in 3.13… 3.13 → 3.45 … passes… Asserting each free-fit coefficient inside its printed CI tests the coefficients directly." | Density fixed at 1; the free fit is asserted inside the pinned intervals; what the test cannot detect is listed. At density 1, 3.13 → 3.31 fails (0.050). | design D14; tasks 1.3b |
| R3-5 | "'Reproduces … tangential force' overclaims… 80 % of the `Fx` norm² comes from α ≤ 27°… Define the metric in the spec." | Scenario retitled to the normal force; the tangential bound is described as guarding unit and signs; the metric is defined. | F scenario "The model reproduces the paper's published fruit-fly normal force"; design D14 |
| R3-6 | "The data do not uniformly favour §3.1.2 over §4.4… The `< 0.20` bound sits only 5 % under §4.4's 0.2102… add the table… say the bound pins §3.1.2." | Taken further than suggested: the bound is 0.25 so both printed sets pass, because the test should not choose between them. The steady-row refit and the per-set errors are in the evidence table; "inside its printed interval" is limited to the all-rows fit. | design "Evidence from the published dataset", "Which coefficient set", D14; proposal "What the paper supports" |
| R3-9 | "The `(?<!not )` lookbehind rejects plan-required negations: 'T4 does not fully resolve the CF_chord PARTIAL'; 'remains unresolved by T4'; 'neither resolved by T4 nor explained by the model'; 'never resolves' and 'can't resolve'; 'is not fully explained by the model'; 'T4 does not close #40'; 'PR #51 closed #40 on merge; it was reopened'… use sentence-level negation handling." | Sentence-level negation for claim patterns. The last two are handled by a wording rule instead: docs say "#40 is open" and do not narrate its closure. | design D13 "Sentences", D9 |
| R3-10 | "Stale claims the patterns MISS: 'T4 resolves the T2a PARTIAL'; 'T4 resolved the chord PARTIAL (#40)'; 'the resolution of the CF_chord PARTIAL by T4'; 'T4 settles the chord question'; 'the model accounts for the chord excess'; 'the CFD chord total now sits close to the model'; 'close agreement'; 'CF_chord agrees with the van Veen model'; 'converges to the QS model'; 'the total-chord should never have been compared to the translational-only 0.3'; 'the PARTIAL was an apples-to-oranges comparison'; 'approaching the physical chord target'; '~5 % off the QS-model target' and '115 % off …'; 'the issue #40 is done'." | Patterns added for each family; the live occurrences are added to the D9 deletion list. "CF_chord agrees with the van Veen model" has no pattern ("agrees" is needed for the normal force); it is on the both-polarity test list as a known miss to be caught by the D9 list and the grep. | design D13, D9; tasks 1.6 |
| R3-11 | "The whole-number patterns reject legitimate unrelated numbers… record in D9 and task 1.6 that docs must refer to the §4.4 set without digits… anchor `4\s?[–-]\s?5\s?%`." | Wording rule recorded; pattern anchored; the cost is stated. | design D9, D13, "Which coefficient set" |
| R3-12 | "The roadmap exclusion hides stale T4 text… add a test that the dated addendum names `0.058` as superseded." | The dated subsection gets a superseded line and a test asserts it. | design D13 "Scope"; F scenario "Claims the corrected model…" |
| R3-14 | "The patched `_s_we_marker_quadrature` in `test_tolerances_derive_from_sourced_quantities` will break… have the shared helper return both integrals in one call… the too-fine check [must] fire before the planform guard." | Done; the order of checks is specified. | design D1, D8; tasks 1.1, 1.7 |
| R3-15 | "proposal.md says 'a wing file that is not the nominal ellipse cannot silently keep the ellipse value'. That is false… reword to 'gross planform errors (more than about 15 % in `S_cy`) raise'… Do not tighten the threshold below about 12 %." | Reworded, with the wings that pass under it listed; a near-threshold test case added. | proposal "What changes"; design D1; tasks 1.1; F scenario "S_cy is the chord-based integral…" |
| R3 minor (7, 8, 13) | Density 1.0112 against 1.007 and `Fz` 0.0194 against 0.018; ellipse range 0.9945–1.0006; the dataset says nothing about our chord direction; weak CHANGELOG anchor, un-normalized anchors, em dash, "#133 pending" order, comment extraction unspecified. | Each fixed. The density and `Fz` differences came from the author fitting on all 14 wings' steady rows and the reviewer on the fruit fly's; both are replaced by density 1 (`Fz` 0.016). | design evidence table, D13 |

Not adopted: the reviewer's optional "direct marker-extent checks against `chord` and `span`" (R3-15).
It has the same sensitivity limits and the planform-basis follow-up issue replaces the guard.

These round-3 fixes have been checked by the author only (strict validation; the dataset numbers
re-run at density 1). The new guard patterns are first run against the documents in task 1.6.

## Deferred, with reasons

| Finding | Why deferred |
|---|---|
| Spec reviewer: "Split the #142 relabel into its own change." | The user chose to fold it in as its own commit. It is last and can be dropped to a follow-up PR. |
| Physics reviewer: "Report the chord outputs under both sets." | A second pinned coefficient set is new model surface. The docs carry the caveat; the graded normal does not depend on the set. |
| Physics reviewer: "A per-component ablation is worth reporting." | A new reported output beyond what the user approved; the limits are stated in prose. |
| Physics reviewer: CFD coefficients normalized by 6.797 while the marker `S_yy` is about 6.24. | It changes `F_ref` and every corpus coefficient. Recorded in design D1 for the planform-basis follow-up issue. |
| Spec reviewer: live spec "the α=0 midstroke" (pre-existing error in another requirement). | Unrelated to the model; task 0.1 notes it on #115. |
| Docs reviewer: `openspec/project.md:13` "experimental data … Aedes aegypti". | Tracked by #79. |
| Round 2: "The paper evidence table in design.md was not checked by me." | The round-1 physics reviewer checked every row against the PDF; round 2 had no PDF access. |
