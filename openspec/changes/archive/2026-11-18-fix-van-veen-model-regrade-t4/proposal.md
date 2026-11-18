# Fix the van Veen quasi-steady model and re-grade T4

Advances #141 (model transcription errors), #133 (signed model vs CFD) and the attribution half of
#142 (waveform wrongly credited to van Veen). #135 (which CFD force to compare) stays open; `ib_w`
is kept meanwhile.

## Why

Tier T4 grades our CFD wing force against van Veen et al.'s (2022) quasi-steady model. Three errors
sit between the paper and that comparison: `S_cy` uses the wrong integral (#141), the eq 3.12
tangential polynomial is evaluated in radians (#141), and the model is fed our signed geometric pitch
where it expects an angle of attack (#133). The fixes cannot land separately: in degrees, a pitch of
−45° gives a chord coefficient of 1.12. T4's VALIDATED number, its decomposition curves, the "#40
resolved" chord reading and the "van Veen" references in three grid figures all come from the
uncorrected model.

## What the paper supports, and what is inferred

- **`S_cy = ∫c(y)²·y dy`** is printed (eq 1.8). The code returns `S_yy = 6.797`; the nominal ellipse
  gives 3.0, so every added-mass term is 2.27 times too large.
- **Eq 3.12's unit is not printed, and the paper's dataset settles it.** Refitting the polynomial
  to the fruit-fly rows of the published dataset (supplementary database S1) gives
  (7.6e-5, −1.14e-2, 0.410) in degrees, inside the §3.1.2 intervals; in radians it gives
  (0.25, −0.66, 0.41). The dataset does not say which of the paper's two printed coefficient sets
  is better. The dataset's stored `Scy` also equals `∫c²·y dy` for all 14 wings
  (`design.md`, "Evidence from the published dataset").
- **The input recipe for a reversing wing is inferred** from fig 1c–e and §3.3. The paper's own
  recipe is in the text it cites as supplementary material S1.1, which is not on the journal
  page: the only supplementary file there is the dataset.

## What changes

**Model (`van_veen_model.py`)**
- **BREAKING:** `WingAreaMoments.s_cy` changes from 6.797 to the nominal-ellipse closed form, 3.0. A
  marker quadrature of the same integral is exposed as a reported cross-check, and
  `compute_wing_area_moments` raises when the two differ by more than 15 %. This catches gross
  planform errors only: a mosquito-shaped wing of the same span differs by about 8 % and passes.
- Eq 3.12 is evaluated in degrees.
- **BREAKING:** the component functions take an angle of attack in `[0, π/2]`, a speed `ω ≥ 0` and
  the acceleration along the motion, and raise `ValueError` outside that domain.
- A new pure function derives those inputs, and the body-frame force directions, from the wing's
  pitch, stroke rate and stroke acceleration.
- Two files of the paper's dataset (`fruitfly.mat`, `wing_geometry_DB.mat`; 124 KB together) are
  committed as test fixtures, and the model is tested against the paper's own CFD forces
  (`design.md` D14).

**T4 (`decompose_wing_force`)**
- Feeds the model through that function. The CFD series stays `ib_w`.
- Adds two reported, ungraded outputs: the signed normal and chord curve correlations (breaking only
  for a consumer that checks the exact key set).
- The graded set and `T4_NORMAL_MAG_TOL = 0.16` do not change. The tolerance was pinned before the
  first result; this re-grade applies the same constant after the corrected result is known.

**Re-grade, figures, prose**
- Re-grade T4 on the fine CSV (production) and the coarse CSV, as today; report the medium CSV.
- Re-render `fig_force_decomposition`. In `fig_force_timeseries_3grid` and
  `fig_grid_convergence_3grid`, replace the shaded "van Veen" bands with single-source, labelled
  reference lines; in `fig_grid_convergence`, read its existing reference line from
  `VAN_VEEN_CF_TARGETS` and label its source.
- `RESULTS.md` becomes the single place the T4 numbers are stated. Every other doc gives the verdict
  in words (`tasks.md` 2.6 and section 3). The two unreleased CHANGELOG entries that quote the old
  T4 numbers are corrected.
- One stale-claim guard, with a case per document, replaces the guards that required "#133" beside
  every claim (`design.md` D13). It is a tripwire; the line list in D9 and a repo-wide grep are the
  primary control.
- Delete every claim that T4 resolves, closes or explains the `CF_chord` PARTIAL (#40), and every
  sentence the corrected model reverses (`design.md` D9).
- Add one note to `RESULTS.md` that the T2a targets (2.4, 0.3) are pinned constants under review, and
  call them "T2a targets" where they appear. The T2a grade is not touched.
- Spec deltas: model-derived literals leave the `flapping-wing-validation` spec in favour of values
  pinned in tests (this covers the T4 literals recorded in the #115 comment).

**#142 attribution (last commit, droppable to a follow-up PR)**
- Relabel the `φ₀·sin` / `α₀·cos` waveform as generic sinusoidal validation kinematics in this repo's
  Python docstrings and docs and in two specs. Citations of van Veen for the axes, rotation order,
  normalization, hinge and model stay.

## Numbers before and after

From four independent calculations (the author's scratch script and three reviewers') on the
committed CSVs, `t ≥ 0.05`, `ib_w`, `S_cy = 3.0`. They agree to the precision shown. The tests pin
these values (`tasks.md` 1.5); no doc copies a number from this table.

| Fine grid (production) | Now | Corrected |
|---|---|---|
| Model normal peak (CFD 2.228) | 2.476 | 2.266 |
| Graded relative gap (tolerance 0.16) | 0.112 | 0.017 |
| Normal peak-phase gap [cycle] | 0.055 | 0.028 |
| Signed normal correlation / RMSE | −0.11 / 1.84 | +0.98 / 0.16 |
| Model chord peak (CFD 0.411) | 0.428 | 0.107 |
| Translational-chord window peak | 0.419 | 0.057 |

| Grid | Corrected gap | Role |
|---|---|---|
| fine | 0.017 | graded, production |
| medium | 0.029 | reported |
| coarse T2a | 0.130 (was 0.050) | graded, as today |

- **The gate passes on fine and coarse.** The coarse margin shrinks to 0.03.
- **The gap is not a precision.** With the marker `S_cy` it is 0.0185; with a nominal `S_WE`, 0.021.
  The model and CFD peaks fall at different phases.
- **The chord is not explained by the model.** Model 0.107 vs fine-grid CFD 0.411, with the right
  sign and shape. The chord correlation is +0.97 with the §3.1.2 polynomial coefficients and +0.88
  with the §4.4 set (a reviewer's figure); the graded gap is the same under both. #133's interim
  estimate of 0.18 kept `S_cy = S_yy`.

## HALT conditions (stop and ask the user; no tolerance is retuned)

Checked in the working tree after the implementation and before any code commit is recorded
(`tasks.md` 1.8).

- `normal_mag_pass` is false on the fine or the coarse CSV.
- `test_tolerances_derive_from_sourced_quantities` fails either of its relations
  (`floor ≤ 0.16 ≤ floor + 0.03`; `grid_rel > 0.9·floor`).
- A graded verdict outside T4 changes (`plausibility_gate`, `body_frame_overall_match`).
- `chord_converges_toward_model` changes in either existing test that asserts it.
- `test_t4_cfd_series_signs_only_through_force_on_wing` or the density-cancellation test fails.

## Out of scope

- #142's kinematics change (new CFD); #111 (moments model); #124 (stale V3 figure; after this lands);
  #137, #138, #139.
- The values of `VAN_VEEN_CF_TARGETS` and the T2a grade (#154).
- Putting `S_yy`, `S_cy` and `S_WE` on one planform basis, computed from the wing geometry file so a
  new planform is followed automatically: it changes `F_ref` (#155).
- `src/mosquito_cfd/force_surrogate/comparison_figure.py`, `docs/visualization/` (being created by
  another session), and the #114/#130 items in `openspec/project.md`.
- The IAMReX fork's `WingKinematics.H`, and `examples/flapping_wing/inputs.3d.validation` (its hash is
  pinned to `run_metadata_t2a.json`); both keep their "van Veen kinematics" wording.
- Dated design records (`docs/superpowers/specs/2026-07-28-*.md`,
  `docs/aerodynamics_validation/t3b-handoff.md`).

## Decisions made by the user (2026-11-17)

1. **The open chord question lives in #40, which is reopened.**
2. **Three follow-up issues are filed before any code** (`tasks.md` 0.1): the T2a targets and grade,
   including which force terms the targets stand for; all wing moments and `F_ref` computed from the
   wing file on one basis, with every number and equation re-checked; nine questions for the
   authors.
3. **`S_cy` is 3.0**, with the run-time planform guard.
4. **The PR body closes #141 and #133 and nothing else.** Commits say "advances".
5. **A third, focused review ran** on the edits made after round 2 (`review-reconciliation.md`,
   "Round 3").
6. **The two dataset files are committed** with attribution.

## Impact

- **Specs:** `flapping-wing-validation` (9 modified, one of them also renamed; 2 added),
  `arbitrary-geometry` (2 modified, one of them also renamed), `coordinate-convention` (1 modified,
  1 added).
- **Code:** `benchmarks/van_veen_model.py`, `benchmarks/flapping_wing.py`, docstrings in
  `benchmarks/wing_kinematics.py`; four `make_*` figure scripts; `generate_all_figures.py` (K1 title).
- **Tests:** `test_van_veen_model.py`, `test_wing_force_decomposition.py`,
  `test_results_reproducibility.py`, `test_flapping_wing_validation_figures.py`, and new guards;
  new fixtures under `tests/fixtures/van_veen_2022/`.
  `test_flapping_wing_validation.py`, `test_coordinate_convention_sign.py` and
  `test_no_false_diffused_ib_claim.py` constrain the prose and must keep passing.
- **Docs:** `RESULTS.md`, `figures/README.md`, `docs/aerodynamics_validation/roadmap.md`,
  `examples/prelim_sweep_fine/README.md`, `docs/force_surrogate/roadmap.md`,
  `docs/force_surrogate/fine-grid-pilot-report.md`, `docs/CHANGELOG.md`,
  `docs/coordinate-convention.md`, `benchmarks/METHODS.md`, `openspec/project.md` (line 38 only),
  `examples/flapping_wing/inputs.3d.production` (comments).
- **Committed artifacts:** five figures re-rendered (`.png` + `.pdf`).
  `validation_figures_summary.json` is not touched.
- No Docker image, CI job, lockfile, solver or corpus is affected, and no surrogate is retrained.
