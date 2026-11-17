# Tasks

TDD throughout: each test is written first and seen to fail for the stated reason before the code
changes. Run `uv run --frozen pytest -m "not gpu"` from Git Bash. Mutation tests use saved-bytes
copies (`PYTHONDONTWRITEBYTECODE=1`, restore with `write_bytes`, never `git checkout`), and
`git diff --stat` must be empty after each round. Tick a box in the commit that does the work.

## 0. Before any code (after user approval)

- [x] 0.1 Reopen #40 with a comment: why (the 0.43 that closed it came from the transcription
      errors; the corrected model chord is 0.107 against 0.411) and the dataset lead (the paper's
      steady tangential coefficient varies about fourfold with stroke rate; compare Reynolds
      numbers). File three follow-up issues and record their numbers here:
      (a) source or replace `VAN_VEEN_CF_TARGETS` (2.4, 0.3), say which force terms they stand
      for, and re-grade T2a;
      (b) compute `S_yy`, `S_cy`, `S_WE` and `F_ref` from the wing geometry file on one planform
      basis, so a new planform is followed automatically; the issue states that every number and
      equation in it must be re-checked as part of the work;
      (c) ask the authors the nine questions (S1.1 text and figures S1–S2; inputs from a measured
      wingbeat; angles outside 0°–90°; signs on the return stroke; eq 3.12 unit and which
      coefficient set fig 13 used; eq 2.11; the CFD density; fig 13 as numbers; permission to
      redistribute the two dataset files).
      Done 2026-11-17: #40 reopened; (a) is #154, (b) is #155, (c) is #156; #115 commented.
      Note the "α=0 midstroke" spec error (live `flapping-wing-validation` spec, "Stroke motion
      reproduces…") on #115.
- [x] 0.2 `openspec validate fix-van-veen-model-regrade-t4 --strict`; record commit 1 (the proposal).

## 1. Model, T4 and `RESULTS.md`, one commit (`fix(t4)`)

`RESULTS.md` moves with the model because the tests that pin the T4 numbers read it. Tests 1.1–1.6
are written before the implementation in 1.7. The pinned numbers are the ones listed in 1.5; four
independent calculations (the author's and three reviewers') agree on them to the precision shown.

### 1.1 Area moments (`tests/test_van_veen_model.py`)

- [x] `s_cy == approx(3.0, rel=1e-12)`, differs from `s_yy`, equals an independent fine quadrature of
      `∫c²·y dy` on the analytic ellipse to 1e-6. Fails today (`s_cy == s_yy`).
- [x] Closed form with `r_tip = 4` gives 5.0; `r_tip < span/2` raises `ValueError`.
- [x] Marker `S_cy` quadrature: committed `wing.vertex` pinned at 2.7033 (`abs = 5e-3`, 30 bins), below
      3.0 by less than 15 %; on a synthetic ellipse outline of ≥ 2e5 markers in `tmp_path`, error below
      5 % at 30 bins, below 1.5 % at 120 bins, and smaller at 120 than at 30; too-fine `nbins` raises.
      Fails today (no such function).
- [x] Planform-mismatch guard: with a synthetic outline in `tmp_path` whose marker `S_cy` is more
      than 15 % from the closed form (a rectangle of the same span and chord, and the committed
      wing scaled by 0.8 in chord), `compute_wing_area_moments` raises `ValueError` naming both
      values; the committed wing scaled by 0.95 in chord also raises (a near-threshold case, about
      −19 %, measured in the test); the committed `wing.vertex` and a synthetic nominal ellipse do
      not raise. Fails today (no guard). Order of checks: zero area, missing file, too-fine
      binning, then this guard; `test_area_moments_guard_too_fine_binning` (200 bins) and the
      `span=0.0` and missing-file tests must still see their own errors.
- [x] Rewrite `test_area_moments_hinge_origin` (drop `s_cy == s_yy`).

### 1.2 Eq 3.12 and the input domain (`tests/test_van_veen_model.py`)

- [x] Coefficient 0.41 / 0.042125 / 0.0185 at 0° / 45° / 90°; ratio to `3.13·sin α` below 0.03 at
      45°–90° in 9° steps; value at 9° more than five times the value at 45°. Fails today (radians).
- [x] Domain: `α = −π/4`, `α = nextafter(π/2, 4)`, an array with one bad element, and `ω < 0` (scalar
      and one array element; translational and Wagner only) raise `ValueError` naming the input, in
      each component and in `total_force`. `α = 0`, `−0.0`, `π/2` and `ω = 0` are accepted; a
      non-finite input still raises the non-finite error. Fails today.
- [x] Rewrite `test_components_match_hand_computed` (90°),
      `test_force_direction_reverses_each_half_stroke` (replaced by the domain test) and
      `test_total_is_sum_and_boundary` (in-domain inputs).

### 1.3 Input function (new tests)

- [x] Both half-strokes: at `t = 0` and `t = 0.5`, angle of attack 45°; model-total normal coefficient
      `3.13·sin 45°` at both; model-total chord coefficient `+0.042125` at `t = 0`, `−0.042125` at
      `t = 0.5`. Over a wingbeat: angle of attack in `[0, π/2]`, speed ≥ 0, acceleration positive then
      negative within each half-stroke (excluding a neighbourhood of mid-stroke and reversal).
- [x] Quadrant table, eight hand-computed rows of (angle of attack, chord direction, normal direction):

      | Pitch | `φ̇ > 0` | `φ̇ < 0` |
      |---|---|---|
      | +45° | 45°, +1, +1 | 45°, −1, −1 |
      | −45° | 45°, +1, −1 | 45°, −1, +1 |
      | +120° | 60°, −1, +1 | 60°, +1, −1 |
      | −120° | 60°, −1, −1 | 60°, +1, +1 |

      Plus the zero cases: chord direction 0 at pitch +90°; normal direction 0 at pitch 0.
- [x] Agreement with the canonical rotation: at 200 evenly spaced times over one wingbeat, excluding
      those within 0.01 of a reversal, form `atan2(|v_z|, |v_x|)`, `|v|/r`, `−sign(v_x)`, `−sign(v_z)`
      from a central difference of `wing_kinematics.rotation_matrix` (h = 1e-6) and assert they equal
      the function's outputs (`rtol = 1e-7`, `atol = 1e-8`). Repeat on a constant-pitch `−45°`,
      `φ = t` trajectory.
- [x] Reversal and rest: literal `φ̇ = 0.0`, `φ̈ = ±a`, pitch 0 and 0.3 → acceleration `+|a|`, chord
      direction `sign(φ̈)`, normal direction 0 at pitch 0, added-mass chord
      `ρ·φ̈·S_cy·0.104·cos α_p`. `φ̇ = φ̈ = 0` → zeros, finite.
- [x] Added-mass chord series on the production kinematics equals
      `ρ·φ̈·S_cy·0.104·cos α_p / F_ref` at every step (a regression guard: today's series already has
      this form, so it fails first only on the `S_cy` value).

### 1.3b Published dataset (`tests/test_van_veen_dataset.py`, new; design D14)

- [x] Add `tests/fixtures/van_veen_2022/{fruitfly.mat,wing_geometry_DB.mat,README.md}`; a test
      asserts each file's SHA-256 equals the value in the README; `git ls-files` lists all three.
      The loader casts every column to `float64`.
- [x] Moment definitions, through the new pure `(c, y)` integrator: for each of the 14 wings the
      integrals of `c²·y` and `√(max(c³y³, 0))` equal the stored `Scy` and `Swe` (`rel = 2e-3`;
      the mosquito profile has three rows with a negative radicand); for the 12 ellipses `Scy` is
      within 1 % of `c²R²/3`. `compute_wing_area_moments().s_cy / (5π/64·chord·span³)` is within
      1 % of the 3 mm ellipse's stored `Scy/Syy`. Fails today (no integrator; ratio 1.03 against
      0.45).
- [x] Model against data at density 1, error `sqrt(Σ(model − data)² / Σ data²)` over all 1,089
      rows: below 0.03 for `Fz`, below 0.25 for `−Fx`. Fails today on `Fx` (radians).
- [x] Free fit: a least-squares fit of the three normal terms lands inside `C_FZA_TRANSL_CI`,
      `C_FZA_AM_CI` and `C_FZA_WE_CI`.
- [x] Every dataset row is inside the model's input domain (no `ValueError`).
- [x] Mutants for 1.9: radians; `Syy` for `Scy`; Wagner dropped; Wagner sign flipped; tangential
      added-mass sign flipped; 3.13 → 3.31. Each must fail a named test here.

### 1.4 `decompose_wing_force` (`tests/test_wing_force_decomposition.py`)

- [x] Keys: `normal_curve_corr`, `chord_curve_corr` present; `set(result) == _EXPECTED_DECOMP_KEYS`;
      the `*_pass` keys are exactly `{normal_mag_pass, closure_pass}`.
- [x] Correlation semantics: scaling the CFD by −1 negates both correlations exactly; by 2 leaves them
      unchanged. The correlation helper called directly with a constant series raises `ValueError`
      (standard deviation below `_DEGENERATE_CF_FLOOR`).
- [x] Rewrite `_model_normal_series` on the production input function; add `assert swe_rel > 0` to
      `test_tolerances_derive_from_sourced_quantities`.
- [x] `test_translational_chord_known_answer`: window peak 0.0573 (`abs = 1e-4`) against an independent
      dense-grid maximum of `(φ̇/ω_ref)²·poly(|α|)`.
- [x] Planform-basis robustness: fine-grid gap 0.0185 with the marker `S_cy` and 0.0207 with the
      nominal-ellipse `S_WE` (`abs = 5e-4`), `normal_mag_pass` true under each.
- [x] Update the stale docstring numbers in this file ("~2.476", "toward the ~0.43 model",
      "2.48 -> 4.95").

### 1.5 T4 pins (`tests/test_results_reproducibility.py`)

- [x] `test_t4_decomposition_numbers_reproduce`, all at `abs = 5e-4`: fine model normal peak 2.2663,
      gap 0.0174, phase gap 0.0277, RMSE 0.163, normal / chord correlation 0.978 / 0.970, model chord
      peak 0.1070, translational-chord peak 0.0573; coarse gap 0.1303 and medium gap 0.0285. CFD-side
      literals (2.23, 0.41, 2.606, 0.923) do not change. Assert the CFD normal peak phase precedes
      the model's (the "CFD leads" statement).
- [x] Literal-in-doc checks scoped to the T4 subsection and matched as whole numbers
      (`(?<![\d.])lit(?!\d)`), for every number the subsection states: the two normal peaks, the gap,
      the phase gap, the RMSE, both correlations, the two chord peaks, the translational-chord peak,
      and the coarse and medium gaps. `_T4_TABLE_VERIFIED` updated to the new table cells.

### 1.6 `RESULTS.md` guards (`tests/test_results_reproducibility.py`), then the document

- [x] Grep `tests/` for every phrase to be changed in `RESULTS.md` and for the forbidden-pattern
      guards new wording could trip (`×2.4`, `2.64`); list which guard each edit touches (design D8).
- [x] Test first: the stale-claim guard, parametrized by document, with `RESULTS.md` as its first
      case (design D13 has the normalization, the sentence rule, the patterns and the anchors).
      Fails today. A separate test feeds it the seven negated sentences round 3 listed (must pass)
      and the fourteen affirmative ones (must fail); both lists are in `review-reconciliation.md`,
      R3-9 and R3-10. Run the new patterns against the current seven documents and read every hit
      before rewriting anything.
- [x] Test first: the new status-row assertion; the interim-section assertions (must not say
      resolved; keeps "~3×", "~2×", "0.3", "#40", "#135"); `test_t4_resolution_attributed_to_t4_not_the_interim`
      inverted; the #133 strings and the two `.index()` slices removed from
      `test_results_vocabulary_states_the_sign_and_the_open_question` (its `ib_w` vocabulary
      assertions stay; its assertions on the roadmap, the figures README and the CHANGELOG move to
      the commits that edit those files, see 2.6 and 3.2); `test_every_chord_resolution_claim_cites_133`
      loses its `RESULTS.md` case. Assert the T4 subsection states each limit the spec lists and that
      the T2a note is present and names its follow-up issue.
- [x] Rewrite the `RESULTS.md` T4 subsection, status rows and every other T4 statement; apply the
      deletions in design D9; add the T2a note and relabel "van Veen's translational ~0.3 / ~2.4" as
      "the T2a target" (design D10). Keep the T3b section, the interim subsection, the header
      "T4 per-component decomposition — validated against van Veen's quasi-steady model", the sign
      anchor, and the CFD-only literals guarded elsewhere ("3.7 %", "27.6 %", "0.554", "2.162",
      "0.321"). Fix the reference's author list. Every number is recomputed by a test.

### 1.7 Implement

- [x] Closed-form `S_cy`; a pure `(c, y)` integrator; one shared marker-quadrature helper that bins
      the markers, calls the integrator and returns `(S_cy, S_WE)` from a single call (the name the
      tolerance test patches must be the one `compute_wing_area_moments` calls, and that test's
      patch returns the pair); the planform-mismatch guard; `np.degrees` in
      `translational_force`; domain validation; the input function; `decompose_wing_force` changes.
- [x] Docstrings and comments in `van_veen_model.py` (lines 14–17, 43, 121, 199–202, 224, 237):
      degrees evidence, the §4.4 set, the eq 2.11 misprint, the input contract, the estimator's bias,
      the two symmetries and the no-pitch-rotation limit; drop "directly comparable … no rotation
      needed".
- [x] Comments in `flapping_wing.py`: the T4 header (828–844), the tolerance comment (86–97), the
      `VAN_VEEN_CF_TARGETS` comment's T4 and "roughly cancel" claims (62–77, values untouched),
      lines 1039 and 1064. The stale-claim guard gets `flapping_wing.py`'s comments as a case.

### 1.8 HALT checks, after 1.7 and before the commit is recorded

- [x] `normal_mag_pass` true on fine and coarse.
- [x] `test_tolerances_derive_from_sourced_quantities`: both relations hold.
- [x] `plausibility_gate` and `body_frame_overall_match` verdicts unchanged.
- [x] `chord_converges_toward_model` unchanged in `test_closure_reported_and_guards` and
      `test_medium_csv_must_not_pair_a_finer_csv_path`.
- [x] `test_t4_cfd_series_signs_only_through_force_on_wing` and the density-cancellation test pass.

Any failure here: stop and ask the user. Nothing is committed.

### 1.9 Mutation tests (each mutant must fail a named test)

- [x] Model: `S_cy` reverted to `s_yy`; closed form without `r_tip`; `np.degrees` dropped; each domain
      check removed; a domain check written with `.all()`.
- [x] Marker quadrature: integrand `c·y²`; hinge offset dropped; `nbins` guard removed.
- [x] Input function: signed pitch fed through; normal direction hard-coded `+1`; angle of attack
      `|α_p|`; chord direction dropped; `s·φ̈` replaced by `φ̈`; direction from `φ̇` alone at reversal;
      Wagner alone fed raw `φ̈`.
- [x] `decompose_wing_force`: directions applied to the components but not to the total.
- [x] `RESULTS.md` guard: each forbidden form restored in plain, bold and line-wrapped variants; each
      anchor removed; a negated sentence ("does not resolve", "not explained by") must still pass.

## 2. Figures and their README (`fix(figures)`)

- [ ] 2.1 Test first: the T4 figure has no text containing "#133" or "pending"; its `model total`
      normal line equals `series["model_normal"]` and is positive throughout phase bands `[0.4, 0.6]`
      and `[0.9, 1.0)` (today it is −2.2 near phase 0.5). Replaces
      `test_t4_normal_panel_names_the_model_sign_issue`.
- [ ] 2.2 Test first, for each of the three grid figures (captured through the `plt.close`
      monkeypatch the timeseries test already uses): with `decompose_wing_force` and
      `VAN_VEEN_CF_TARGETS` monkeypatched to sentinels, each model line sits at the sentinel peak and
      each T2a line at the sentinel target; the `axhspan` patches are exactly the Richardson / GCI
      span per panel in `fig_grid_convergence_3grid` and none in the other two; each label names its
      source and is shown in the legend; the timeseries chord panel has lines at both signs.
      Red-first reason: the timeseries and 3-grid figures fail on the spans; `fig_grid_convergence`
      fails on the sentinel and the label. Replaces `test_3grid_normal_band_is_positive_only`.
- [ ] 2.3 Update the four scripts; remove hard-coded 0.3 / 0.43 / 2.4 / 2.48 / 2.16; fix the
      timeseries legend filter, which drops any label containing "van Veen"; add
      `metadata={"CreationDate": None}` to the two convergence scripts' PDF `savefig`.
- [ ] 2.4 Re-render the four figures; look at each PNG; `git status --short` lists exactly eight
      binaries.
- [ ] 2.5 Mutation tests: a hard-coded band restored; a typed literal at the correct value; the "#133"
      note restored; labels swapped; the negative chord line dropped.
- [ ] 2.6 `figures/README.md` in this commit: grep `tests/` for its pinned phrases first; add it as a
      stale-claim-guard case (fails today); rewrite the T4 paragraph and the four figure rows with the
      verdict in words, keeping the sign anchor; move the README assertion out of
      `test_results_vocabulary_…` and drop the README case of `test_every_chord_resolution_claim_cites_133`.

## 3. Remaining docs (`docs(t4)`)

- [ ] 3.1 Grep `tests/` for every phrase to be changed (including the fine README's
      `_FINE_COMPARATIVE` / `_DENOMINATOR_RATIO` guards).
- [ ] 3.2 Test first: add the remaining stale-claim-guard cases:
      `docs/aerodynamics_validation/roadmap.md` (scanned without its reconciliation log),
      `examples/prelim_sweep_fine/README.md`, `docs/force_surrogate/roadmap.md`,
      `docs/force_surrogate/fine-grid-pilot-report.md`, `docs/CHANGELOG.md`. Each fails today on a
      named pattern (the pilot report on the "+115 %" / "4–5 %" patterns). Move the roadmap and
      CHANGELOG assertions out of `test_results_vocabulary_…`; delete what remains of
      `test_every_chord_resolution_claim_cites_133`. Add the roadmap-row test additions the spec
      scenario names (the dated addendum; `coordinate-convention.md` and the `flapping_wing.py`
      docstring free of "deferred to T4" / "rotational drag").
- [ ] 3.3 Edit the docs, verdict in words and no model number: the roadmap T4 row and lines 101–103,
      174–175 (the phrases `test_roadmap_t4_row_flipped_and_reframed` requires stay); a dated addendum
      to the reconciliation log, which is otherwise left as written;
      `examples/prelim_sweep_fine/README.md:136–137` with a link to the `RESULTS.md` T4 subsection;
      `docs/force_surrogate/roadmap.md:219–221` and `docs/force_surrogate/fine-grid-pilot-report.md:9–13`,
      re-based on the grid evidence using only numbers pinned elsewhere.
- [ ] 3.4 `docs/CHANGELOG.md`: correct the unreleased entries at lines 46 and 60 so they state what
      ships (the pinned phrase "The T4 figure flags the normal" goes, with its assertion); line 77
      has no superseded statement and stays; add one entry for this change, verdict in words.
- [ ] 3.5 Mutation tests for 3.2, as in 1.9's last item, for each document.

## 4. #142 attribution relabel (`docs(kinematics)`, last commit)

- [ ] 4.1 Grep `tests/` for every phrase to be relabelled (`_HEADLINE_TABLES` keys on the header
      "Body-frame per-component van Veen comparison"; `test_new_convention_deck_and_docs` requires
      "van veen" in the convention page).
- [ ] 4.2 Test first: the `coordinate-convention.md` guard (phrases `geometric pitch`, `|α|`,
      `decompose_wing_force`; the kinematics table located by header, asserted found, with no
      `van Veen kinematics` column; van Veen still cited for axes and normalization), plus
      `euler_angles.__doc__`, `benchmarks/METHODS.md` and the K1 title (via `plot_k1_kinematics` into
      `tmp_path`) no longer attributing the waveform. Fails today.
- [ ] 4.3 Relabel the places in design D12. Keep-list: every van Veen citation for the axes, rotation
      order, normalization, `S_yy`, hinge and model. `inputs.3d.production` comments are relabelled
      (no test or metadata file hashes that deck; re-check before editing).
- [ ] 4.4 Add `CreationDate: None` to K1's PDF `savefig`. Render `generate_all_figures.py` into a
      scratch `--output-dir`; copy back only `fig_kinematics.{png,pdf}`; a test compares the plotted
      line data with the pre-change values so only the title differs.
- [ ] 4.5 Mutation-test 4.2.

## 5. Close-out

- [ ] 5.1 Re-read `proposal.md`, the spec deltas and this file against the implementation; record any
      deviation in a "Why N instead of M?" section before committing it.
- [ ] 5.2 Re-run the full mutant list after the last fix commit; `pytest -rs` shows no new skip.
- [ ] 5.3 Repo-wide grep for `2.48`, `0.43`, `0.42`, `0.055`, `0.058`, `#133`, `resolv` across `src/`,
      `docs/`, `examples/`, test docstrings and the live specs; explain each remaining hit.
- [ ] 5.4 Re-run the five figure scripts at HEAD into a scratch directory and confirm the committed
      PNGs match.
- [ ] 5.5 `uv run --frozen pytest -m "not gpu"` from Git Bash; CI's two ruff commands verbatim, plus
      `ruff check` and `ruff format --check` on `examples/flapping_wing/` and `scripts`;
      `openspec validate fix-van-veen-model-regrade-t4 --strict`.
- [ ] 5.6 `/review-pr`; a focused re-review of every fix commit.
- [ ] 5.7 Closing-keyword gate over `git log --format=%B origin/main..HEAD`, the PR title and the PR
      body: `grep -inE '\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\b:?\s+(\S+/\S+)?(#|https://github\.com/\S+/(issues|pull)/)[0-9]'`
      returns nothing. The prose form "does not resolve #40" is for the docs only; it must not appear
      in a commit message, the PR title or the PR body.
- [ ] 5.7b The PR body, and only the PR body, closes #141 and #133 (user decision). After the gate
      in 5.7, the only closing keywords found are those two. #40, #135 and #142 are named with
      "advances" or not at all.
- [ ] 5.8 `git fetch`; `git merge-base --is-ancestor origin/main HEAD` (merge main in if not, re-run
      the suite); stop for user approval before pushing.
- [ ] 5.9 `/pre-merge-check`. At archive time, diff the live specs against `80d653a` first: a MODIFIED
      block replaces the whole requirement.

## Deviations from the approved plan

### Why six negated sentences instead of seven (task 1.6)?

Round 3 listed "T4 does not close #40" among the negations the guard must accept. The approved
pattern list also rejects `clos\w+\W+#40` in every sentence, and the wording rule in design D9 says
docs do not narrate the closure. The two cannot both hold, so the sentence is on the must-fail
list. Six negated sentences are on the must-pass list, with four more taken from the documents.

### Why is "should never have been compared" rejected in every sentence?

The phrase contains "never", so as a negation-skipped claim pattern it could never fire. It is in
the always-rejected group.

### Why is the "resolves" pattern narrower than approved?

On its first run against the documents the approved `resolv\w*|resolution` matched "coarse-grid
under-resolution was a major contributor to the #40 chord excess", which is a true statement about
the grid. The pattern now skips forms that follow a hyphen or a letter ("under-resolves",
"under-resolution") and takes "resolution" only as "resolution of". Both polarity lists still pass.

### Why does the T4 test check every decimal in the subsection, not only that each literal is present?

Mutation testing: changing one prose copy of the model chord peak to 0.108 survived, because the
right value was still in the table. The test now requires the set of decimals in the T4 subsection
to equal the set of recomputed ones, and the status row's to be a subset.

### Why does `RESULTS.md` not quote the gaps under the alternative planform bases?

They are pinned in `tests/test_wing_force_decomposition.py` (0.0185 and 0.0207). Quoting them would
add two numbers to the document for a statement ("the grade passes under each") that needs none.

### Why is a velocity component below 1e-15 treated as zero in `model_inputs`?

The spec gives chord direction 0 at pitch +90°. In floating point `cos(pi/2)` is 6e-17, not 0, so
without the rounding the direction would be +1 there.

### Where the stale-claim guard lives

In `tests/_stale_claims.py` (the patterns) and `tests/test_t4_stale_claims.py` (the polarity lists
and one case per document), not in `tests/test_results_reproducibility.py`.
