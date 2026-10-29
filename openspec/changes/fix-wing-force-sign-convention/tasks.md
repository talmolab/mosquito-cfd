# Tasks

**Rules for every task:**

- Every implementation task names the test written **first** and the behaviour it pins.
- Every new guard is mutation-tested on saved-bytes copies; never restore with `git checkout`.
- Kills count only after a green baseline, and each PR body records its kill table.
- Test paths are anchored at `Path(__file__)`.
- A strict xfail carries `raises=` with a dedicated exception.
- The local suite mirrors CI: `uv run --frozen --group viz pytest -m "not gpu"`.
- Run `ruff check` and `ruff format --check` on `src/`, `tests/`, `scripts/` **and**
  `examples/flapping_wing/`. CI's ruff paths miss `examples/flapping_wing/`.
- **Never push a red head** (design D9).
- Each PR's re-derived blast-radius list goes in its PR body, not in this file.

Order: **PR1 → PR2a → PR2b → PR3**. Each PR is opened off `main` after its predecessor merges.

## 0. Blast radius (derived by running the suite, not by reading)

0. [ ] **Before each PR**, re-derive its list by running the CPU suite on a simulated post-change export
   of its base. Build the sim as a git repo (`git init` plus commit) with its own `src` first on
   `PYTHONPATH`. Diff the result against the list below. **Any test outside the PR's list that needs
   editing halts the change.**

   These lists were measured on `a2e8f64` exports:
   - simA = the D5 algebra;
   - simB = extractor negation plus negated parquets;
   - simC = simB plus banners, the provenance key and the `sweep_provenance` edit.

   "edit-driven" marks a test that breaks when a planned edit lands.

   - **PR1:** no existing test changes. New tests, plus additions to `tests/_readme_guards.py`.
   - **PR2a:**
     - `tests/test_flapping_wing_validation.py:166` `test_decomposition_is_six_dof_momentum_balance`
     - `tests/test_results_reproducibility.py`:
       - `:107` `test_lab_frame_ranges_recompute`
       - `:149` `test_phase_table_raw_fz_recompute` (extended to `CF_z (lab)`)
       - `:213` `test_added_mass_subtracted_interim_recomputes`
       - `:248` `test_interim_framing_is_honest_and_disambiguated` (edit-driven)
       - the enumeration guards and `_INTERIM_TABLE_VERIFIED` `:66` (edit-driven)
     - `tests/test_wing_body_frame.py`:
       - `:404` `test_added_mass_subtracted_linearity_and_reuse` (redesign)
       - `:443` `test_subtracted_equals_manual_reuse_pipeline`
       - `:494` `test_added_mass_subtracted_reproduces_interim`
       - `:605` (the degenerate test, split per denominator)
       - `:664` `test_peak_migration_and_signed_drop`
     - `tests/test_flapping_wing_validation_figures.py:52` (edit-driven: label `"CFD total (ib_force)"`)
     - Watch list:
       - `tests/test_new_convention_deck_and_docs.py:19` (`visualize.py` reduced);
       - `tests/test_no_false_diffused_ib_claim.py::test_roadmap_t4_row_flipped_and_reframed` (the
         `roadmap.md:97` edit).
   - **PR2b** (simB/simC, 17 failures, plus edit-driven):
     - `tests/test_committed_surrogate_provenance.py`:
       - `:118` holdout targets (D6 branch)
       - `:141` metadata names the dataset (D6 pinned sha)
       - `:190` seed-variation record (D6 pinned sha)
       - `:294` phase-baseline skill (D6 `−dataset`)
     - `tests/test_force_surrogate_dataset.py`:
       - `:189` `test_coefficients_use_single_source_per_config_normalization`
       - `:870` `test_shift_applied_with_a_non_committed_offset`
       - `:903` `test_committed_geometry_shift_is_spanwise_and_leaves_cf_my_invariant`
       - `:924` `test_offset_is_derived_per_configuration`
     - `tests/test_force_surrogate_scale_invariance.py`:
       - `:87` `test_committed_corpus_cf_is_van_veen_consistent`. Its frozen-sha lines `:116-122` stay
         byte-identical.
       - `:223` hinge reconcile, both corpora
       - `:282` IB-part arm, both corpora
       - `:343` provenance, extended with the new key
       - `:412` staleness banner, generalized to both corpora and anchored at `Path(__file__)`
     - `tests/test_verify_moment_reextraction.py:231` zero-offset control
     - `tests/test_force_surrogate_sweep.py:1015` (edit-driven: `re_extraction` stage)
   - **PR3** (edit-driven):
     - `tests/test_committed_surrogate_provenance.py:190-250` (seed-record keys, README 5-seed table)
     - `tests/test_force_surrogate_sweep.py:1015` (`retrain` stage)
     - `tests/test_force_surrogate_evidence_figure.py` (README and caption literals)
     - The D6 tests revert to their unconditional branch with no edit.
   - **Stay green, cited as gates:**
     - frozen raw shas, `test_force_surrogate_scale_invariance.py:116-122, :145-161`
     - `test_corpus_guards.py` (peaks 4.015 / 2.880 unchanged)
     - `test_force_surrogate_evidence_figure.py:1214-1261, :1500-1525`
     - the grid-convergence tests and `test_flapping_band_floor.py`
0a. [ ] Record: **a `_FROZEN_*RAW_FORCE_SHA` trip during PR2b is a HALT, not a re-pin.**

---

# PR1 — evidence and groundwork (no binaries; "advances #109")

1. [ ] Commit the approved change directory: `chore(openspec): add approved proposal …`.

## 1. Canonical angular velocity

2. [ ] **Test first:** `angular_velocity` equals the skew part of `Ṙ Rᵀ` from a central finite
   difference of `rotation_matrix`.
   - Tolerances: `h=1e-6`, `rtol=1e-6`, `atol=1e-9·max|Ω|`.
   - Check ≥ 20 times, with nonzero stroke, pitch and deviation amplitudes.
   - Known answers with `deviation_amp=0`: `t=0` gives `(0, 0, φ_amp·2πf)`, and the stroke term is zero
     at the quarter beat.
3. [ ] Implement `wing_kinematics.angular_velocity`. Mutants that must fail test 2: `α̇` sign flipped,
   `Rz(φ)` dropped on the pitch axis, deviation term dropped, `RᵀṘ` used.

## 2. Physics guards (`tests/test_ib_force_sign_convention.py`)

4. [ ] **Test first, raw work (never xfail).** Over 57 runs:
   - `W ≥ 0` at every row, and `W(t) − W₀ ≥ 0` after `W₀` (the first row with `t ≥ STEADY_WINDOW_T0`).
   - Non-vacuity: exactly 57 runs, ≥ 2 late rows each; a NaN, zero-row or too-short run fails.
   - Keep-last dedup.
   - **Deck mapping by sha256** against `run_metadata_t2a/t3b/t3c.json` `inputs.hash`, with the hinge
     literal `(4.0, 0.5, 4.0)`. `X,Y,Z` is a sanity check only (design D3).
5. [ ] **Test first, raw consistency (never xfail):** `corr(Mz, −Fx) > 0` and `corr(Mx, Fz) > 0` on the
   unshifted columns, per run.
6. [ ] **Test first, coefficient side.** Over 54 configs:
   - `W_wing ≤ 0` (rows and late increment) and `corr(CF_mz, −CF_x) > 0`.
   - The sign predicates raise `CoefficientsOnFluid(AssertionError)`; the non-vacuity checks are plain
     asserts.
   - Mark `xfail(strict=True, raises=CoefficientsOnFluid, reason="#109: the committed corpus coefficients carry the solver's on-fluid sign until re-extraction")`.
7. [ ] Run every row of the design D3 mutation table on saved-bytes copies, including "one config
   dropped under the xfail → FAIL". Record the measured counts. A row that differs from the design is a
   finding to reconcile.

## 3. Helper and docstrings

8. [ ] **Test first:** `force_on_wing(a, b, c) == (−a, −b, −c)`. Dtype and shape are kept;
   `−0.0`/NaN/inf propagate; empty in gives empty out; a scalar works. Also
   `IB_FORCE_ACTS_ON == "fluid"`.
9. [ ] Implement `force_on_wing` and `IB_FORCE_ACTS_ON` in `normalization.py`. No caller yet. The
   docstring links the section.
10. [ ] **Test first:** the `ForceCoefficients` / `MomentCoefficients` docstrings, and the
    `compute_force_coefficients` docstring (`normalization.py:356`):
    - say the container is sign-agnostic;
    - link `docs/coordinate-convention.md#force-and-moment-sign`;
    - describe `cf_z`/`fz` as "lab vertical (z)", not "span-normal";
    - carry **no** interim status (design D4).

    Then edit them. `normalization.py` is frozen from PR2b's task 37, so this is the only chance.

## 4. Canonical section, guards, #19, docstring fix

11. [ ] **Test first**, in `tests/test_coordinate_convention_sign.py` using helpers in
    `tests/_readme_guards.py`:
    - There is exactly one `## Force and moment sign` section, with slug `force-and-moment-sign`.
    - It names `ib_force`/`ib_moment` on the fluid and the coefficients as the IB force on the wing.
    - It notes the internal-fluid term, gives the sphere/ellipsoid note, names the oracle test, and
      links the raw-vs-derived paragraph.
    - The **evidence scan**: the tokens `work from rest`, `work-from-rest` and `M_hinge · Ω` appear
      nowhere in the search set except the section. The search set and exemptions are as in the CC
      requirement. This negative check shares a test with the positive one.
    - The **link list** test for PR1's entries: the two coefficient docstrings, `force_on_wing`, and
      `flapping_wing.py`.
12. [ ] **Test first — pending phrases track their conditions.** Each phrase is its exact pinned
    literal (CC requirement), and occurs once iff its condition holds, else not at all (design D4).
    Test both directions:
    - **corpus:** a saved-bytes parquet copy with only `CF_*` negated;
    - **flapping-wing:** `force_on_wing` monkeypatched at the `flapping_wing` use site (identity vs
      negation). A negated CSV cannot test this condition;
    - **surrogate:** README copies with and without the banner, on both corpora.
13. [ ] Write the section in the present tense, with the corpus and flapping-wing phrases. There is no
    banner yet, so no surrogate phrase.
14. [ ] **Test first, then fix:** `flapping_wing.py`'s module docstring no longer calls `ib_force` "the
    TOTAL hydrodynamic force" (`:58-62`), and it links the section.
15. [ ] **Test first, then fix (#19):** none of `runner.py`, `run_one_config.py` and the argo template
    contains `assum` or `not yet verified` **anywhere** (case-insensitive). Each contains "verified
    against the A40 corpus (PR #18)".
16. [ ] Add the CHANGELOG entry. Run the suite, ruff and `openspec validate --strict`. **Stop for
    approval before pushing.** Open PR1 with "advances #109", mentioning #19 without a keyword; close
    #19 by hand after merge.

---

# PR2a — flapping-wing path (no `Z:`; 8 figure files)

17. [ ] Re-derive task 0's PR2a list, and put it in the PR body.
18. [ ] File the follow-up issue "which CFD force should the van Veen comparison use: the 6-DOF force or
    `ib_w`?" first.
19. [ ] **Test first:**
    - `reconstruct_wing_forces` gives `cf_*_ib == −ib/f_ref` and `cf_hydro == cf_added + ρ_f·cf_ib`.
    - The raw identity `cf_hydro·f_ref == ρ_f·(SumU − ib_force)` holds.
    - Rewrite `test_flapping_wing_validation.py:166`.
20. [ ] **Test first:**
    - `reconstruct_wing_body_forces` rotates `−F`.
    - The existing graded literals in `test_wing_body_frame.py` and the T4 tests stay green with no
      edit to them. This is the independent pin.
21. [ ] **Test first, the identity spy at use sites** (design D1). With the spy in place, across
    `reconstruct_wing_forces`, `reconstruct_wing_body_forces`, `body_frame_added_mass_subtracted`,
    `plot_f1_forces` and `fig_v1_three_convention`:
    - series that *are* the IB force equal the pre-change on-fluid series bitwise;
    - composites equal their formula on the spied output (`cf_hydro`, `peak_cf_*_6dof`);
    - across all calls, the multiset of arrays passed equals the expected set, each once.
22. [ ] **Test first, the relabelled diagnostic:**
    - Keys `peak_cf_*_{6dof,ib}`, and `drop_frac = 1 − ib/6dof`.
    - Values (design D5): chord 0.6517 / 0.9231 / −0.4165; normal 2.2851 / 2.6060 / −0.1404; shares
      0.8392 / 0.1278.
    - 1094 steps between the peaks; −0.394 at the 6-DOF chord peak.
    - The `ib` peaks equal `body_frame_overall_match`'s.
    - **Two-sided degeneracy:** a zero 6-DOF case and a zero `ib_w` case each raise their own
      `ValueError`. Mutants with the floor on only one denominator each fail.
    - Redesign `test_wing_body_frame.py:404` and `:605`. Rewrite `:443`, `:494` and `:664`.
23. [ ] Implement 19–22 through `force_on_wing`, including `plot_f1_forces` and
    `fig_v1_three_convention`. Fix the `flapping_wing.py` comments, docstrings and error messages listed
    in design D5.
24. [ ] **Test first**, in `test_results_reproducibility.py`. Every RESULTS.md edit in design D5 gets a
    pinned assertion:
    - the lab ranges;
    - the phase table: raw `Fz` labelled; `CF_z (lab)` `= −Fz/F_ref`; the caption;
    - the interim header, cells and rise phrasing (no bare "−42 %");
    - the vocabulary sentences ("total" definition, the historical name, the internal-fluid term, not
      van Veen's added mass);
    - `~3×`, 1094 steps, 39 %, the follow-up issue number;
    - `:241` and `:35`;
    - the #133 pointer at `:279`.

    All enumeration guards stay green.
25. [ ] Edit RESULTS.md only after 24 is red against it, then make it green. Update the labels in design
    D5, with `test_flapping_wing_validation_figures.py:52` in the same commit as its label. Add the
    links for RESULTS.md, `figures/README.md` and `docs/aerodynamics_validation/roadmap.md`, and extend
    the link-list test.
26. [ ] **Test first:** the `visualize.py` subparser set is `{velocity, vorticity}` (red now). Then
    remove the `forces` subcommand.
27. [ ] The flapping-wing pending phrase now fails its guard. Remove it from the section in the same
    commit as 23.
28. [ ] Fresh reviewer agent on the figure code, labels and RESULTS.md wording **before rendering**.
29. [ ] **HUMAN CHECKPOINT before committing binaries.**
    - Render only the five functions (design D5), with PDF `CreationDate=None`. Render twice and `cmp`.
    - `git status --porcelain` lists exactly the 8 files, and `validation_figures_summary.json` is
      unchanged.
    - Check the 3-grid band side; add a structural test if it moves.
    - The PR2a figure scope is clean since rendering.
    - Record the generating commit and blob sizes in the PR body.
30. [ ] Add the CHANGELOG entry. Run the suite and ruff. Check one blob per path. **Stop for approval
    before pushing.** Open PR2a with "advances #109".

---

# PR2b — corpus flip and re-extraction (needs `Z:`)

31. [ ] Re-derive task 0's PR2b list and put it in the PR body. Prechecks:
    - `Z:` is mounted.
    - All 27 `IB_Particle_1.csv` per corpus are present under the baseline `input_dir`.
    - All 27 coarse `run_metadata.json` anchors are present.
    - Record the merge-base sha.
32. [ ] **Test first (synthetic, throwaway repos):** the verifier (design D8) passes an exact negation.
    It fails each of the following, one test per case:
    - a changed raw column;
    - a changed non-CF column;
    - a row reorder;
    - an off-by-ULP CF;
    - a moved NaN;
    - a missing CF column;
    - an unflipped CF column;
    - a changed `csv_sha256`, `input_dir`, `inputs.hash`, `docker_image`, `moment_reference` offset or
      `dropped_configs`;
    - a wrong `force_sign_convention`;
    - a removed key;
    - a second added key;
    - `dirty: true`;
    - a baseline parquet whose sha does not match the surrogate's `inputs.hash`.

    A changed `hardware` block is reported and passes.
33. [ ] Implement `scripts/verify_force_sign_reextraction.py`. Mutation-test each check.
34. [ ] **Test first, synthetic extractor:**
    - Rewrite `test_force_surrogate_dataset.py:189, :870, :903, :924` to the negated form, each with a
      non-vacuity clause.
    - Add the identity-spy test for `build_dataset`.
    - Adapt `test_verify_moment_reextraction.py:231` (the control compares against the negated
      baseline).
35. [ ] Call `force_on_wing` in `_extract_config` after the shift. Update `verify_moment_reextraction.py`'s
    control and docstring.
36. [ ] **Test first (synthetic driver only):** `scripts/extract_forces.py` writes `force_sign_convention`
    with the pinned value. Implement it.
37. [ ] **Test first, D6:**
    - Generalize the banner test to both corpora, anchored at `Path(__file__)`.
    - Add banner-conditional branches:
      - `:118`: `−dataset`, not `allclose` to `+`.
      - `:141` and `:190`: the pinned shas `01c88ae9…` and `2092f0fd…`, as full literals.
      - `:294`: compute against `−dataset`.
    - Add a tmp-copy test of the stale branch (a negated parquet plus a banner README).

    These are green now (no banner). Commit the code. **The extraction scope is frozen from this commit**
    (design D9).
38. [ ] Local, red commit:
    - Rewrite `test_force_surrogate_scale_invariance.py:87, :223, :282` to the negated or coefficient
      form, with non-vacuity clauses. `:116-122` stay byte-identical.
    - Extend `:343` to assert `force_sign_convention` on **both committed corpora**, and pin each
      `dataset.units.json` literally.

    Record the failing output.
39. [ ] From the clean tree at task 37's commit, re-extract both corpora into a temp dir. Use the
    **native PowerShell command lines** built verbatim from each baseline `run_metadata.json` (design
    D8); coarse adds `--run-metadata-name run_metadata.json`. Then:
    - Run `verify_force_sign_reextraction.py --baseline-ref <merge-base>` and record the output.
    - The frozen raw shas hold.
    - `git diff --exit-code <merge-base> -- uv.lock` is clean.
40. [ ] **HUMAN CHECKPOINT before committing binaries.** The data commit contains:
    - 2 parquets and 2 `run_metadata.json`;
    - both README banners;
    - the section's surrogate phrase;
    - the `sweep_provenance.json` `re_extraction` stage (with `#108` moved into `history`, the digest
      kept, `pull_request: null`) and the matching `test_force_surrogate_sweep.py:1015` edit.
41. [ ] Commit:
    - drop the xfail on task 6; the corpus phrase now fails its guard, so remove it;
    - add the links in both corpus READMEs and `docs/force_surrogate/roadmap.md`, and extend the
      link-list test;
    - add docs saying the dataset coefficients are the IB force on the wing (corpus README schema notes,
      the force-surrogate roadmap row describing dataset coefficients);
    - add the CHANGELOG entry.
42. [ ] Fresh reviewer on the data and docs commits. Then:
    - `git merge-base --is-ancestor` for both recorded corpus commits.
    - The extraction-scope diff since task 37 is empty.
    - Run the suite and ruff, and check one blob per path.
    - **Stop for approval before pushing** tasks 32–41 together (head at task 41).
    - Open PR2b with "advances #109".
    - In a follow-up commit, set `pull_request` and its test literal together, along with the CHANGELOG
      PR number.

---

# PR3 — retrain and regenerate (closes #109)

43. [ ] Local commit of the pre-registered literals as tests (docstrings name this change and note that
    they may be retired by a later OpenSpec change):
    - the 12 `a2e8f64` skill intervals, plus the overlap test that also asserts
      `inputs.hash == sha256(dataset)` and `inputs.hash != pinned` (red until the retrain);
    - exact `overshoot_factor` and `round(baseline_rmse_cf_z, 4)` (red until the figures).
44. [ ] **Test first, G0**, in `test_force_surrogate_train_gpu.py` (design D7). First verify
    physicsnemo's final-layer options. Run in WSL with the three mutants.
45. [ ] Decide the `seed_variation.json` third dataset key and the README seed-table shape. Edit their
    tests.
46. [ ] Fresh reviewer agent, **before** any render, on:
    - the caption;
    - the evidence-figure title (`evidence_figure.py:682` "span-normal" → "lab vertical");
    - the quasi-steady "poor fit" wording (`evidence_figure.py:8, :644, :672`; coarse README `:416-428`);
    - the README wording.
47. [ ] Commit the code. **Surrogate and figure scopes frozen.** **HUMAN CHECKPOINT before the GPU run.**
48. [ ] In WSL:
    - Check that `git status --porcelain` is empty, `test ! -e .venv/bin`, and `git rev-parse HEAD`
      equals the commit.
    - Train each corpus twice, in separate processes, into scratch dirs outside the repo, passing
      `--git-dir` per command.
    - Evaluate G1–G3. Any failure halts for a decision.
49. [ ] **HUMAN CHECKPOINT before committing binaries.** Surrogate data commit:
    - the surrogates and the coarse `seed_variation.json` extension;
    - the `sweep_provenance.json` `retrain` stage (`pull_request: null`) and its test;
    - **both banners removed**, and the section's surrogate phrase removed (its guard flips);
    - check `git diff --exit-code <merge-base> -- uv.lock`.
50. [ ] Render both evidence figures from the clean tree **after** task 49's commit. Check G4, then
    commit the figures. Then a re-quote commit:
    - README and caption numbers from the new JSON (what n=5 supports);
    - the Stage-2 sentence plus the `docs/field_surrogate/roadmap.md` link (extend the link-list test);
    - the CHANGELOG entry.
51. [ ] Fresh reviewer on the artifacts and docs. Run:
    - the WSL GPU subset (`test_force_surrogate_train{,_gpu}.py`);
    - the CPU suite, ruff and `openspec validate --strict`;
    - `git merge-base --is-ancestor` for the surrogate and figure records;
    - the one-blob check.

    **Stop for approval before pushing** tasks 43–50 together.
52. [ ] Open PR3. Put the hand-written squash message at the top of the PR body and in a PR comment, with
    "Closes #109." on its own line. Then commit the PR number into `sweep_provenance.json` and its test.
    Add the stale T4 literals to #115.
53. [ ] After merge: `/cleanup-merged`, including the OpenSpec archive (a separate `chore(openspec):
    archive …` commit on `main`) and the roadmap update.
