# Refresh the V3 validation figure and guard the V1–V5 summary against staleness

Advances #124. Takes items 3 and 4 of #137; items 1 and 2 stay open there.

## Why

The committed V3 figure (`examples/flapping_wing/figures/V3_scale_invariance.png`) and the `v3`
block of `validation_figures_summary.json` are stale and mislabelled, and no test compares any
committed V1–V5 output with its source.

- **Stale numbers.** The `v3` block is the R² of the coarse-surrogate predictions committed in
  `c74d69b` (#36). Those predictions have been replaced three times since (`e77643c` #71,
  `de081f3` #126, `e1ee11d` #147); the current R² is in `surrogate/metrics.json`. History and values:
  `design.md`, Context. (#124 says #53 last regenerated V3, but `git log` of both artifacts shows only
  `c74d69b`; #124's "current" pair is the `e77643c` row.)
- **Mislabelled panels, from the first commit.** V3 plots the parquet as "BEFORE" and the parquet × k
  as "AFTER (van Veen)", k = F_ref(R_TIP) / F_ref(R_GYRATION) = (R_TIP / R_GYRATION)² ≈ 3.12. V3 was
  created in the same commit that multiplied every parquet `CF_*` column by exactly k, so from its
  first commit "BEFORE" has shown van Veen coefficients and "AFTER (van Veen)" van Veen × k, which is
  no convention. The figure's claim, that R² does not change under the rescale, holds: R² is
  invariant under any common non-zero scale.
- **No guard.** `tests/test_flapping_wing_validation_figures.py` regenerates into `tmp_path` and
  checks loose literals and ΔR² < 1e-9; it never reads the committed summary or what V3 plots.

## What changes

- **V3 panels** (contract in the spec; rationale in `design.md` D1). Per coefficient, one panel plots
  the committed van Veen coefficients as stored, the other the same coefficients re-expressed on the
  peak-tip reference (stored ÷ k). Titles name the convention and R²; axes name the CFD target
  (lab frame, on the wing) and the surrogate prediction; the suptitle, module and function docstrings
  drop "before/after".
- **BREAKING (summary keys):** the `v3` block's `r2_before` / `r2_after` become `r2_van_veen` /
  `r2_peak_tip`; `delta` stays. Nothing reads the old keys (`design.md` D4).
- **New `v3` fields:** `true_mean`, `true_rms`, `pred_mean`, `pred_rms` of the van Veen arrays per
  coefficient. R² alone cannot see a pure rescale or sign flip of the parquet (the event that caused
  this mislabel); these can (`design.md` D6).
- **Regenerate** V3 and the summary from committed data. A full `main()` run re-renders V1, V2, V4,
  V5 byte-identically on the developer's machine; any change outside V3 and the `v3` block stops the
  change.
- **Summary written with LF** (`Path.write_text(..., newline="\n")`), #137 item 4.
- **Staleness guard (new tests):** the committed summary equals a fresh regeneration, all five
  blocks; the committed `v3` R² equals R² recomputed from the committed parquet and `metrics.json`;
  the comparator is unit-tested, including against the actual stale values; V3's peak-tip panel is
  checked against raw forces on the tip reference (a known answer independent of the generator).
- **Docs:** `examples/flapping_wing/figures/README.md` V3 row; `docs/CHANGELOG.md` [Unreleased].

## What does not change

- The surrogate, the parquet, `metrics.json`, and every other figure.
- R² stays V3's metric: V3 claims invariance under a common rescale, a statement about R² itself, not
  about skill. Baseline-relative skill (#127/#128) is the evidence figure's headline.
- R²'s seed dependence does not apply: the guard checks committed predictions, fixed bytes.
- The `force-surrogate` scale-invariance requirement and its test. They use k in both directions
  (spec `:1888` vs `:1896`); filed as #170.

## Out of scope (follow-ups)

- #137 items 1–2 (per-figure render flag; `CreationDate` in G1/K1/K2 PDFs). Comment on #137.
- #155 (`S_yy` basis). The guard covers `v2.s_yy` and fails if #155 changes it without regenerating.
- #115 (stale numbers in the force-surrogate spec). No V3 number is in any spec.
- #170 (k direction in the force-surrogate spec and test).
- The V3 PNG's pixels have no guard: PNG bytes are not reproducible across platforms. What V3 plots
  is guarded by rendering it in the test; the committed PNG is guarded only by being regenerated in
  the same commit as the summary (`design.md` D5).

## Impact

- Specs: `flapping-wing-validation` (ADDED: three requirements).
- Code: `examples/flapping_wing/generate_validation_figures.py` (`fig_v3_scale_invariance`, module
  docstring, the JSON writer in `main`).
- Artifacts: `examples/flapping_wing/figures/V3_scale_invariance.png`,
  `examples/flapping_wing/figures/validation_figures_summary.json`.
- Docs: `examples/flapping_wing/figures/README.md` (V3 row); `docs/CHANGELOG.md`;
  `docs/force_surrogate/roadmap.md` row 16 after archive (rows go there, as in `80d653a`).
- Tests: `tests/test_flapping_wing_validation_figures.py`. Checked, unchanged:
  `tests/test_flapping_wing_sign_use_sites.py`, `tests/test_new_convention_deck_and_docs.py` (read the
  generator); `tests/test_t4_stale_claims.py`, `tests/test_coordinate_convention_sign.py`,
  `tests/test_kinematics_attribution.py` (read `figures/README.md`).
- No solver, Docker, CI or dependency change. CPU-only, cluster-free, committed data only.
