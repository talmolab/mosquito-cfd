# Review reconciliation: round 1

**Verdict:** NEEDS REVISION.

**Reviewers:**
- Subagent 1 (spec quality): sonnet.
- Subagent 2 (tests): opus.
- Subagent 3 (CI and Docker): skipped. There is no CI, Docker, dependency or packaging change.
- Subagent 4 (docs): sonnet.
- Subagent 5 (git workflow): sonnet.
- Subagent 6 (math and physics): opus. Launched because the change edits a convention document.

**Inputs:** the reviewers were given file paths, not the full text pasted into their prompts, and
were told to read each file in full.

Each entry quotes the finding, says how it is addressed, and gives the line in the revised proposal
where the reviewer's mechanism now appears.

## BLOCKING

**B1** (S2 #1). Finding:

> "Task 1.1 can pass while the main wrong sentence stays. Line 88 says 'aerodynamic forces are
> reported in the **wing body frame**'. It is not forbidden … A text that swaps the frames … passes.
> Fix: Strip markdown emphasis and backticks, then collapse whitespace. Forbid
> `forces are reported in the wing body frame`. Forbid the emphasis-free forms `body-frame forces` and
> `forces above` … Require each frame phrase in the same sentence or bullet as its quantity."

How it is addressed:
- The text is normalized: emphasis, backticks and `>` are stripped and whitespace is collapsed.
- Three phrases are forbidden: `forces are reported in the wing body frame`,
  `Unlike the forces above` and `body-frame forces`.
- Each family must appear in one sentence with its frame.
- A one-off mutant swaps the frames.

Where:
- The coordinate-convention delta, scenario "Each reported force quantity is named with its frame",
  Given / Then / first And.
- tasks.md 1.2, the "Text checks" bullets.
- tasks.md 1.6, "swap the frames of `CF_chord` and `CF_x..CF_z`".

One deviation: I forbid `Unlike the forces above` rather than the bare `forces above`. Correct prose
can say "the forces above" with no frame claim attached. The full sentence is the defect.

**B2** (S2 #2). Finding:

> "Task 1.2's 'each line containing `F_ref =`' can pass vacuously … Fix: use `F_ref\s*=` on the
> flattened text, and assert at least 2 matches on the page."

How it is addressed: the check is now `F_ref\s*=` on the flattened page, with at least two matches.
Each match must contain `ω_peak²` and no `ω(?!_peak)`.

Where:
- The delta scenario "F_ref is written with ω_peak, tied to the code and to the kinematics", Then.
- tasks.md 1.3, the "`F_ref` expressions" bullet.
- tasks.md 1.6, the mutant `F_ref=½·ρ·ω²·S_yy` with no spaces.

**B3** (S2 #3 and #5). Findings:

> "Task 1.3's regex only catches one spelling … misses `⋅` (U+22C5), `ω^2`, `ω**2` … The exemption
> cannot be implemented with `effective_text` as worded … Fix: iterate `effective_spec(cap)` and skip
> the block by name. Separately assert `effective_block(FWV, …)` still matches."

How it is addressed:
- The pattern is now `ω(?:²|\^2|\*\*2)\s*[·⋅]?\s*S_yy`.
- The spec check iterates `_spec_claims.effective_spec` and skips the exempt block by name.
- A missing or non-matching exempt block fails with the requirement's name. A synthetic negative
  control covers that.

Where:
- The delta scenario "No bare ω in F_ref …", When and first And.
- tasks.md 1.4, the "Pattern", "Search set" and "Exemption" bullets.
- design.md D3.

The `ω(?!_peak)` check inside `F_ref` spans (S2's "stronger check") is in B2.

**B4** (S6 I1). Finding:

> "The new requirement says the project reports 'two force quantities', which leaves out the
> flapping-wing lab-frame series. This repeats #181's error one level down … Correction: name a third
> quantity … Guard: extend scenario 1.1 to call the existing
> `test_coordinate_convention_sign.flapping_series_on_wing()` … Prompt: add the same item to the
> Subagent 6 failure-class wording."

How it is addressed:
- The delta body now reads "every other force coefficient — the force-surrogate corpus and surrogate
  `CF_x..CF_z`, and the flapping-wing lab-frame series (the `plausibility_gate` input and the
  `fig_forces` series) — is **lab-frame components of the IB force on the wing**".
- The scenario requires a sentence naming the flapping-wing lab-frame series as lab-frame, and that
  `flapping_series_on_wing()` holds.
- The review-openspec-skill delta adds "the flapping-wing lab-frame series", and adds
  `flapping-wing lab-frame series` as a failure-class anchor.

Where:
- The coordinate-convention delta body (the bullet list) and scenario "Each reported force quantity
  is named with its frame", Then and last And.
- tasks.md 1.2, the "Data" bullet.
- tasks.md 1.5.
- design.md D1 table.

## IMPORTANT

**I1** (S4 DRY). Finding:

> "The coordinate-convention delta body … states the formula `ω_peak = 2π·f_star·radians(phi_amp_deg)`
> in full and then says force-surrogate 'owns' it. That is a second normative definition."

How it is addressed: the delta now only names `ω_peak` and refers to Force Surrogate ("Single-source
force normalization"; code: `compute_force_reference`). The formula appears only on the narrative
page, which is checked against the code.

Where: the coordinate-convention delta body, "`ω_peak` is the peak stroke rate defined by [Force
Surrogate]…". design.md D2.

**I2** (S1 #1, S2 #6, S4 §4). Findings:

> "`And the guard fails on the page as it stood before this change` is a historical, red-run claim.
> It is untestable as a standing scenario."

S2 adds: "write each check as a pure function of text, and add a permanent test that feeds it a
frozen copy of today's Forces/Moments text under `tests/fixtures/`."

How it is addressed: the historical bullet is replaced by a frozen fixture,
`tests/fixtures/convention_page/pre_181_161.md`. Each text check is asserted to fail on it every CI
run.

Where:
- The delta scenario "Each reported force quantity is named with its frame", the fourth And.
- tasks.md 1.1 and the "Fixture" bullet of 1.2.
- design.md D1.

**I3** (S2 #4, S6 table). Finding:

> "Task 1.3's 'Red: about ten hits' is wrong on this branch … Fix: record the red run as 5 doc hits.
> Show the spec half red once with `effective_text(cap, changes_dir=<empty tmp dir>)` (live only: 6
> hits)."

How it is addressed: the expected red is now five doc hits, plus a recorded spec-half run with
`changes_dir` set to an empty `tmp_path`, which gives 6 hits.

Where: tasks.md 1.4, "Expected red". design.md D3, "Spec half of the red run".

**I4** (S2 #7, S6 M5). Findings:

> "Replace the task 1.4 one-off mutants with permanent in-suite negative controls … copy a parquet to
> `tmp_path`, mix components … Exemption: feed a synthetic block … Quoted values: feed text with
> `F_ref ≈ 134.17`."

S6 adds: "Add a mutant that replaces CF_x..CF_z by the R(t)ᵀ-rotated −F/F_ref."

How it is addressed: three permanent negative controls.
- A corpus copy with `(CF_x, CF_y)` rotated 30° about lab z.
- A synthetic exempt block without a match.
- A synthetic page quoting `F_ref ≈ 134.17`.

One-off mutants remain only for what these do not cover (tasks.md 1.6).

Deviation from S6 M5: the control rotates by a fixed angle about lab z rather than by each
configuration's `R(t)ᵀ`. Either one mixes components, and `_on_wing` rejects any mixing at
`rtol = 1e-9`. The fixed-angle control needs no kinematics per configuration in a test. S2's wording
("rotate `CF_x`/`CF_y` by a fixed angle") is the mechanism used.

Where: the delta scenarios (last And of S1, third And of S2, second And of S3). tasks.md 1.2–1.4,
the "Negative control" bullets.

**I5** (S2 missing tests 1–5). Findings:

> "RESULTS.md :160 `u_ref` row → `radians(phi_amp)`: no guard … The page statement 'the waveform ω is
> 2πf' is not pinned to a literal … The force-surrogate spec link is checked only as a substring …
> How the quoted values are parsed is not specified … The spanwise-drop sentence is unguarded."

How it is addressed:
- Positive row checks on RESULTS.md (paragraph, `F_ref` row, `u_ref` `radians(phi_amp)`) and on
  figures/README.
- The literal `` `ω = 2πf` ``.
- The link target must resolve to an existing file.
- Quoted values are parsed with `≈` regexes: at least one of each, at least two decimals, checked
  with `format_like`, and every match is checked.
- `intentionally dropped` is kept.

Where:
- Delta scenario S3, last And; scenario S2, second and third And; scenario S1, Then.
- tasks.md 1.3, 1.4 and 1.2.

**I6** (S2 #6–7 for review-openspec). Findings:

> "Add `narrative only` to `AUTHORITY_AND_METHOD` … forbid `uses ω for two quantities` across the whole
> Subagent 6 template … `forces are in the wing frame` misses … 'forces in the wing frame' …
> Consider also forbidding `By design, forces`."

How it is addressed: all four are adopted. They are in the review-openspec-skill delta:
- the "Authority and method are stated" scenario, `narrative only` plus an AND line;
- the "Failure-class list …" scenario, the final AND.

Where: tasks.md 1.5.

**I7** (S4, S6 I2, S2). Finding: "`RESULTS.md:181` labels the lab-frame row 'CF_x range (chord /
streamwise)' … Lab x equals chord only at rest pose." Also `generate_all_figures.py:311,313` and
`docs/force_surrogate/roadmap.md:226`.

How it is addressed:
- RESULTS.md 181–182 is fixed here, because the file is already in scope.
- The figure legends are pinned by a test and need a re-render, and the roadmap sentence needs a
  lab-frame convergence check. Both are filed as **#203**.

Where: proposal.md, "What Changes", the RESULTS.md bullets; "Out of scope". tasks.md 2.3.

**I8** (S6 M4). Finding:

> "Guard 1.2 recomputes ω_peak and F_ref from the same constants and function the page cites. That is
> internal consistency only … Proposed task wording: 'Assert that
> `2π·VALIDATED_F_STAR·radians(VALIDATED_PHI_AMP_DEG)` equals `max|wing_kinematics.stroke_rate(t, …)|`
> over a dense t-grid on one wingbeat (rel 1e-6), at the validated point and at the corpus corner
> (f*=1.15, 55°)'."

How it is addressed: adopted as worded.

Where: delta scenario S2, fourth And. tasks.md 1.3, the "Known answer" bullet.

**I9** (S6 M3). Finding: "The page should say F_ref is computed per configuration."

How it is addressed: it is required on the page (`computed per configuration`) and in the delta body.

Where: delta body ("computed per configuration") and scenario S2. tasks.md 1.3.

**I10** (S1 #1, Moments). Finding: "No Then asserts anything about Moments … Suggested addition:
`## Moments states the moments are lab-frame components about the hinge`."

How it is addressed: `## Moments` must contain `lab-frame components about the hinge`.

Where: scenario S1, second And. tasks.md 1.2.

**I11** (S1 D4). Finding: "design.md D4 says 'Task 1.4 confirms this …'. Task 1.4 is the mutation
checks."

How it is addressed: D4 now points to task 2.5.

**I12** (S1, S5). Findings: "There are no explicit commit boundaries … the proposal's commit rule ('no
commit carries a red test') is not stated."

S5 adds: "Do NOT commit red tests, and do not use xfail."

How it is addressed: design.md D6 sets the commit plan and the no-red, no-xfail rule. tasks.md opens
with that rule and points to D6.

**I13** (S1 #6). Finding: "`mutation-results.md` … Specify the location."

How it is addressed: the path is given in tasks.md and in proposal.md Impact.

**I14** (S1 #3). Finding: the existing scenario's Then is edited, but the proposal says only the named
substitutions change.

How it is addressed: proposal.md "What Changes" and design.md D5 now name the edit to the existing
scenario.

## SUGGESTIONS adopted

- **S6 M1 (attribution):** the page frames `ω_peak` as this project's constant evaluation of eq 1.1's
  stroke rate (proposal.md, design.md D2).
- **S6 M2 / S4 (units wording):** the page and RESULTS.md place the speed `ω_peak·r_gyr` at the radius
  of gyration, not the rate (proposal.md). The pinned phrase "van Veen (2022, eq 1.1) normalization"
  is kept.
- **S6 M6 / S4:** the page's phrase "shares the prefix" with `LAB_FRAME_PHRASE`, and is not described
  as matching it (proposal.md, design.md D1).
- **S6 M7:** the prompt says derived `CF_m*` are about the hinge and raw `Mx..Mz` are about the particle
  origin (proposal.md).
- **S4 (authority note):** the exact text "narrative only and has been wrong before (#108, #181)".
- **S4 (CHANGELOG):** the entry goes under `### Fixed`, keeps #141 out, and names #202 and #203.
- **S2 (verification):** ruff is run on CI's exact scope, and more test files are named for the full
  run (tasks.md 2.5–2.6).
- **S1 #7:** re-wrapped the long line in the flapping-wing-validation R1 block.

## Not adopted, with reasons

- **S1 #7 (split into ADDED requirements):** the new scenarios guard the requirement's own statements:
  frame per quantity, and `F_ref` with `ω_peak`. A new requirement would restate them, which is the
  DRY problem in I1. They stay as scenarios.
- **S4 (drop `F_ref ≈ 200.27` from the page):** the page is where a reader of the convention looks for
  the reference value, and the guard recomputes the value, so it cannot go stale. Kept.
- **S4 (move scenario S3 to flapping-wing-validation):** coordinate-convention owns the normalization
  convention, so its guard covers every place that restates it. Splitting it would leave two guards
  with one pattern. Kept.
- **S1 (`ω_ref` at flapping-wing-validation line 710):** it is defined as the peak stroke rate, so it
  is correct. Renaming it is in #202 (comment added).
- **S4 (`docs/force_surrogate/roadmap.md:94`):** added to #202.
- **S6 pre-existing items** (S_yy from the marker-derived r_gyr versus the nominal ellipse, a 2.6%
  difference; `plausibility_gate` dropping lab `Fy`): these are not defects of this change. They are
  recorded here for the user to decide whether to file.

## Round 1b: verification of the revision

A verification reviewer (opus) checked the revision against the entries above. It confirmed the
following:
- B1–B4 and I1–I14 each sit at the cited location, with the reviewer's literal mechanism.
- No original requirement text is lost in any MODIFIED block.
- The known answer holds exactly. `max|stroke_rate|` equals `2π·f·radians(φ)`, relative error 0.0, at
  (1.0, 70°) and at (1.15, 55°).
- A 30° rotation of `(CF_x, CF_y)` makes `_parquet_on_wing` return False on both corpora.
- With the exempt block skipped, the live specs have 6 spec-half bare-ω hits, and the specs with the
  deltas applied have 0.

It found four problems, fixed below. Each entry quotes the finding, then gives the fix.

**P1 (blocking).** Finding:

> "Two text checks already pass on today's page, so 'each check fails on the fixture' cannot hold …
> Fix: `## Moments` has one sentence holding both `lab-frame components about the hinge` and
> `CF_x..CF_z` … asserts that each check except `intentionally dropped` fails on it."

Fix: adopted verbatim. Where:
- coordinate-convention delta, scenario "Each reported force quantity is named with its frame",
  second and third And;
- tasks.md 1.2, the Moments check, the "Fixture" bullet and "Expected red";
- design.md D1.

**P2 (blocking, new error introduced by round 1).** Finding:

> "'every other force coefficient … is lab-frame components of the IB force on the wing' is false"

Its counterexamples were `cf_span`, the body-frame added-mass-subtracted `cf_added`/`cf_6dof`, the T4
components, and the lab-frame `cf_*_added`/`cf_*_hydro`, which are not the IB force.

Fix: adopted. The delta body now lists the body-frame family explicitly: "`CF_chord`/`CF_normal`, and
the diagnostics built from the same rotation (`cf_span`, the added-mass-subtracted diagnostic, the T4
decomposition)". It names the lab-frame IB series explicitly as "corpus and surrogate `CF_x..CF_z`"
and "`cf_x_ib`/`cf_z_ib`". "Every other" is gone. The review-openspec-skill delta now says "the
flapping-wing body-frame family (`CF_chord`/`CF_normal` and the diagnostics built on them) is
wing-frame". The design D1 table now has six rows, including "lab, not the IB force", and its family
count is corrected. Where:
- coordinate-convention delta body, the two frame bullets;
- review-openspec-skill delta, the requirement body;
- design.md D1;
- proposal.md, Why table and What Changes.

**P3.** Finding: "D5 miscounts the review-openspec anchors … four."

Fix: design.md D5 now says "four anchors".

**P4.** Finding:

> "The same-sentence rule does not catch a frame swap … Fix: add … the sentence holding
> `CF_chord`/`CF_normal` does not contain `lab-frame`, and the sentence holding `CF_x..CF_z` does not
> contain `wing body frame`. For the flapping-wing sentence, require `plausibility_gate` or
> `fig_forces` together with `lab-frame components`."

Fix: adopted verbatim. Where:
- coordinate-convention delta, scenario "Each reported force quantity is named with its frame", Then;
- tasks.md 1.2;
- design.md D1.

**M1.** Fix: design.md D4 now cites the measured count, `test_live_spec_claims.py`: 155 passed.

**M2.** Fix: the `F_ref` span runs "up to and including the first following `S_yy`" (delta scenario
"F_ref is written with ω_peak …", Then; tasks.md 1.3).

**M3.** Fixes:
- Strip only paired `_…_` emphasis at word boundaries.
- Split sentences on `. ` or bullets, never on the `..` inside `CF_x..CF_z` (design.md D1, tasks.md 1.2).
- The page will use the unhyphenated `wing body frame`. The proposal's What Changes, which
  describes the page wording, says `wing body frame`. Its Why (line 8) still says
  "wing-body-frame" as a compound adjective in prose. No guard reads that line.

**M4.** Correction to I3: S2 named `effective_text(…, changes_dir=<empty>)`. With that call the
exempt block is included, which gives 8 hits. The 6 hits come from iterating `effective_spec` and
skipping the block, which is the mechanism tasks.md 1.4 uses. This is a disclosed refinement of S2's
mechanism, not a substitute for it.

## PR review, round 1 (`/review-pr`, branch mode, 2026-11-23)

Reviewers: code quality (opus), testing (opus), scientific rigor (opus), performance/build
(sonnet), behavioural correctness (opus). Verdict: REQUEST_CHANGES (one blocking finding).

**R1 (BLOCKING, scientific rigor; also IMPORTANT from behavioural).** "The page states 'Van Veen's
strokes run at a constant rate, so eq 1.1 needs no qualifier there.' … the paper's database has 43
steady, 477 accelerating, 46 decelerating simulations … eq 1.1's ω is van Veen's instantaneous
stroke rate, not a constant."
- Verified against `tests/fixtures/van_veen_2022/README.md` and `van_veen_model.py`.
- Fixed: the page now says van Veen's simulations include accelerating and decelerating strokes,
  that the repository's model scales with the instantaneous `|φ̇|`, and that this project's `F_ref`
  uses one constant `ω_peak` per configuration. design.md D2 ("Attribution", plus a
  `### Why not …` note) and proposal.md What Changes match.

**R2 (IMPORTANT, behavioural + science S2).** "`fig_forces` … does not call
`reconstruct_wing_forces`, and it plots `CF_y`."
- Fixed: the page, the coordinate-convention delta body, proposal table and design D1 now attribute
  `cf_x_ib`/`cf_z_ib` to `reconstruct_wing_forces` (the `plausibility_gate` input) and the
  `fig_forces` `CF_x..CF_z` to `generate_all_figures.py`'s inline `force_on_wing`.

**R3 (IMPORTANT, code quality 1 + testing 3).** "All six FRAME_CHECKS return True on a page that
… adds 'Forces are given in the wing body frame.'"
- Fixed: new `no_contradicting_frame_sentence` (a sentence with `CF_x..CF_z` or "force(s)" plus a
  wing-frame phrase must name `CF_chord`), in `FRAME_CHECKS`, red on the frozen fixture, with three
  permanent negative controls (`test_contradicting_frame_sentence_is_rejected`).
  `flapping_lab_sentence` gains `must_not` `wing body frame`. Delta scenario updated.

**R4 (IMPORTANT, code quality 2 + testing 2).** "`F_ref ≈ **134.17**` … returns `[]`."
- Fixed: `quoted_value_failures` reads `normalize(page)` and accepts `≈`, `~`, `=`; the negative
  control now covers plain, backticked, bold and `=` spellings.

**R5 (IMPORTANT, code quality 3 + behavioural S1).** "`f_ref_expression_failures` reads past the
end of the expression" and misses `` `F_ref` = `` / `:=`.
- Fixed: `f_ref_expressions` reads each `F_ref =`/`:=`/`≡` (backticked or not) to its clause end;
  `S_yy` without `ω_peak` fails; `ω_peak^2` is accepted. Parametrized negative controls added, plus
  `test_f_ref_expression_ends_at_its_clause`.

**R6 (IMPORTANT, testing 1 + code quality S4).** "`ω² × S_yy`, `\omega^2 S_yy`, … a wrapped line
also escapes."
- Fixed: wider `BARE_OMEGA`, docs scanned flattened (`bare_omega_hits_in`), spelling and
  wrapped-line tests. design D3 has a `### Why the wider pattern?` note; delta scenario updated.
  The widened pattern finds the same 5 live-spec blocks as before and none in the effective specs.

**R7 (IMPORTANT, testing 4).** "`By design, force coefficients are wing-frame.` survives."
- Fixed: `check_failure_class_frames` in `tests/test_review_openspec_command.py` (one sentence ties
  `CF_x..CF_z` to lab-frame; no "force"/`CF_x..CF_z` sentence in the wing frame without
  `CF_chord`), with negative controls; red on the 246f0a0 prompt. review-openspec-skill delta gains
  one AND line.

Suggestions adopted: known-answer test also checks `compute_force_reference(...).u_ref /
R_GYRATION` and samples a half-step-offset grid (testing S5); link check strips comments (testing
S6); sentence splitter protects `e.g.`/`i.e.` (code quality S1); `cf_*_added`/`cf_*_hydro` and the
frame of each 6-DOF series named (science S1); RESULTS link to `#forces` guarded (behavioural S6);
named `_FIXTURE_SOURCE_SHA` / `_ROTATION_DEG`, one `_COMMENT` regex, fuller assertion messages;
CHANGELOG moments wording (science S3, behavioural S5); long lines rewrapped.

Not adopted:
- Moving `_parquet_on_wing` etc. into a `tests/_frame_guards.py` helper: precedent exists for
  importing from another test module (`test_flapping_wing_sign_use_sites.py`), and the move would
  touch an out-of-scope test file.
- A data check of the `fig_forces` code path: its legends are #203; a source-text check would be
  weak. The page's frame claim for it was verified by reading `generate_all_figures.py:261-284`.
- Exact-heading matching in `_section`: a second `## Forces…` heading fails loudly already.
