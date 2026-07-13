# Tasks — per-component van Veen force decomposition (T4)

TDD throughout: each implementation task names the test written **first** and the behavior it verifies
**before** the code exists. `uv` for all Python. Branch: `add-wing-force-decomposition-t4` (off `main`).
Cluster-free — everything is tested against the committed CSVs + synthetic fixtures. NO new sims. Pin all
tolerances/coefficients **before** computing the committed-run result (CC-V2). Tests use `encoding="utf-8"`
and the `Agg` matplotlib backend where relevant (cross-platform / CI-safe).

## 1. Van Veen quasi-steady model (pure module)

- [x] 1.1 **Test first (known-answer components):** in `tests/test_van_veen_model.py`, add
  `test_components_match_hand_computed` — at `α = π/2`, `ω = ω_ref`, `ω̇ = 0`, committed moments: assert
  `F_z_transl == ½·RHO·ω_ref²·S_yy·3.13` (sin(π/2)=1), `F_z_AM == 0` and `F_z_WE == 0` (both ∝ ω̇), and
  `F_x_transl == ½·RHO·ω_ref²·S_yy·(A·(π/2)²+B·(π/2)+C)` — to `pytest.approx`. Fails: module missing.
- [x] 1.2 **Test first (Wagner sign generalization):** add `test_wagner_sign_for_decelerating_wing` —
  for `ω̇ < 0`, assert `F_z_WE` uses `sign(ω̇)·√|ω̇|` (finite, no `√` of negative), and is **oppositely
  signed** to the `ω̇ > 0` case of equal `|ω̇|`. Fails: module missing.
- [x] 1.2b **Test first (half-stroke sign pinned analytically — design §D4):** add
  `test_force_direction_reverses_each_half_stroke` — at mid-downstroke and mid-upstroke (opposite `φ̇`,
  opposite `α`), assert the model normal `F_z` sign equals the hand-computed `sign(sinα(t))`/`R(t)`-frame
  expectation and **reverses** between the two half-strokes; asserted against **hand-computed literals**,
  **never** the CFD series. Fails: module missing.
- [x] 1.3 **Test first (coefficients pinned + not-loosened guard):** add `test_coefficients_pinned` —
  assert the named constants equal `3.13, (8.5e-5, −1.2e-2, 0.41), 0.96, 0.104, −1.02` and their 95 % CIs
  equal the pinned tuples; assert `_assert_coefficients_not_loosened()` **raises** if any coefficient or CI
  is widened (CC-V2). Fails: constants missing.
- [x] 1.4 **Implement** `src/mosquito_cfd/benchmarks/van_veen_model.py`: the three body-frame components
  `translational_force(alpha, omega, *, s_yy, rho)`, `added_mass_force_component(alpha, omega_dot, *, s_cy,
  rho)`, `wagner_force(alpha, omega, omega_dot, *, s_we, rho)`, each returning `(F_x, F_z)`; a
  `total_force(...)` summing the three; the pinned coefficient constants + CIs +
  `_assert_coefficients_not_loosened`. A code comment records that **both** AM components use `S_cy` (the
  fitted revised model, not the analytic `S_τy`). Docstring cites eqs 1.1–2.10 / 3.9–3.15 and the DOI.
  1.1–1.3 pass.
- [x] 1.5 **Test first (pure closure + ω̇=0 boundary + non-finite):** add `test_total_is_sum_and_boundary`
  — `total_force == translational + added_mass + wagner` component-wise (chord & normal) to float tol; at
  `ω̇ = 0` both AM and Wagner return exactly `0` (no `√`/`÷` error); a non-finite `α`/`ω`/`ω̇` **raises**
  (matching the repo's no-silent-NaN posture). Drives the guards in 1.4.

## 2. Stroke-rate kinematics helper (ω, ω̇)

- [x] 2.1 **Test first (analytic derivatives):** in `tests/test_wing_kinematics.py`, add
  `test_stroke_rate_matches_analytic_derivatives` — for `φ(t)=φ_amp·sin(2πf*t)`, assert
  `stroke_rate(t, …) == (φ_amp·2πf*·cos(2πf*t), −φ_amp·(2πf*)²·sin(2πf*t))` at several `t`, `ω(0)==ω_ref`
  (peak rate), `ω̇(0)==0`, and `frequency=0` ⇒ `(0, 0)` (valid, no error). Fails: helper missing.
- [x] 2.2 **Implement** `stroke_rate(time, *, frequency, stroke_amp_rad) -> tuple[float, float]` in
  `benchmarks/wing_kinematics.py` (analytic `φ̇, φ̈`; single-source with `euler_angles`' stroke). 2.1 passes.

## 3. Wing area-moments — one shared hinge-origin quadrature (reconciles review B3)

- [x] 3.1 **Test first (hinge-origin convention + S_cy==S_yy + independent S_WE quadrature):** in
  `tests/test_van_veen_model.py`, add `test_area_moments_hinge_origin` — `compute_wing_area_moments(...)`
  under the **hinge-origin** convention (y from the stroke axis, hinge offset `d≈1.5` from the wing
  centre) returns `S_yy ≈ 6.797` (`= R_GYRATION²·area`, reconciling the committed value; using the wing
  **centre** origin would give the wrong `≈1.20`), `S_cy == S_yy`, and `S_WE = ∫√(c³y³)dy` matching an
  **independent** trapezoidal quadrature of the committed planform to tolerance; a zero-area planform raises
  `ValueError`. Fails: fn missing.
- [x] 3.2 **Implement** one shared `compute_wing_area_moments` (hinge-origin `∫₀^R … dy`) emitting `S_yy`,
  `S_cy` (==`S_yy`), `S_WE`; document the y-origin/limits contract. **Refactor** the inline
  `S_yy = r_gyr²·area` sites (`examples/flapping_wing/generate_validation_figures.py`,
  `tests/test_force_surrogate_normalization.py`) to call it (one moment code path, CC-V4), reconciling the
  literal to `6.797` ("≈6.80"). 3.1 passes and the existing normalization test stays green.

## 4. Tolerance constants (pinned, sourced, guarded, and the sourcing TESTED — reconciles review B2 / CC-V2)

- [x] 4.1 **Test first (not-loosened tolerance):** in `tests/test_wing_force_decomposition.py`, add
  `test_tolerances_pinned` — assert the **single graded** magnitude tolerance `T4_NORMAL_MAG_TOL == 0.16`
  (phase and RMSE are *reported*, so there is **no** `T4_PEAK_PHASE_TOL` / `T4_NORMAL_RMSE_TOL` pass/fail
  constant — assert those names are absent, so no reported diagnostic can grow a silent gate); assert a
  not-loosened guard **raises** if `T4_NORMAL_MAG_TOL` is widened. Docstring/source cite the §D6 derivation.
  Fails: constant missing.
- [x] 4.2 **Implement** the named `T4_NORMAL_MAG_TOL` constant + guard in `benchmarks/flapping_wing.py` with
  the sourced-derivation comment (design §D6). 4.1 passes.
- [x] 4.3 **Test first (the magnitude tolerance derives from sourced inputs, not reverse-fit):** add
  `test_tolerances_derive_from_sourced_quantities` — recompute the §D6 quadrature from its **inputs**: the
  committed T3b normal grid GCI via `wing_grid_convergence_from_body_forces` on the coarse+medium CSVs
  (`gci_p1 ≈ 0.146`), the pinned normal coefficient-CI band from `van_veen_model` (recomputed ≈0.006), and
  the `S_WE` geometric-uncertainty term **recomputed** from the marker-vs-**analytic-ellipse** `S_WE`
  difference (they agree to ~0.1%, so ≈0.001 — **NOT** a typed literal). Assert
  `derived_floor (√(0.146²+0.006²+0.001²) ≈ 0.147) ≤ T4_NORMAL_MAG_TOL ≤ derived_floor + 0.03`, and
  `T4_CHORD_GCI_BAND == (chord gci_p2, chord gci_p1)` read from the reused convergence helper (**not** a
  re-typed literal). A tolerance loosened past its sourced budget **fails**. (This test asserts
  **unconditionally** — no `skipif` on `forces_medium.csv`, which is committed — so the reverse-fit catch
  never silently disappears.) Fails: constant/helper wiring missing.

## 5. Graded per-component decomposition

- [x] 5.1 **Test first (G1 magnitude graded pass-within/fail-outside; phase + RMSE reported):** add
  `test_normal_magnitude_graded_phase_reported` — build a synthetic CFD `CF_normal(t)` = model + a
  controlled offset; assert **G1 peak MAGNITUDE** passes within `T4_NORMAL_MAG_TOL` and **fails** for a
  magnitude offset beyond it (both directions), and widening `T4_NORMAL_MAG_TOL` flips a not-loosened
  companion; assert the **peak-phase gap** and **curve RMSE** are returned as **reported** numbers with **no**
  pass/fail field (a phase/RMSE offset changes the reported value but never a verdict). Fails:
  `decompose_wing_force` missing.
- [x] 5.2 **Test first (G2 known-answer, NOT an identity to 0.30):** add
  `test_translational_chord_known_answer` — assert the model's translational-tangential **peak** equals the
  value computed from the pinned polynomial at our α (`pytest.approx(≈0.42)`), is reported as `O(0.4) ≪
  0.92`, and that the grader does **not** compare it to `VAN_VEEN_CF_TARGETS["cf_chord_peak"]` nor expose a
  chord `*_match`/`*_pass` key for it. Fails: grader missing.
- [x] 5.3 **Test first (G3 closure + R1 band-from-helper + exact key set + malformed):** add
  `test_closure_reported_and_guards` — assert `model_total == transl + AM + Wagner` (chord & normal) to
  float tol; assert the chord report carries `T4_CHORD_GCI_BAND` **read from the convergence helper** and
  reports the coarse→medium→model direction, with **no** chord `*_pass`/`*_match` key; assert
  `set(result) == _EXPECTED_DECOMP_KEYS` (enumerated — a later chord gate fails); assert a missing column /
  non-finite row / empty window raises `ValueError` (the test names the **exact** required column set
  `decompose_wing_force` enforces — dropping each one individually — so the guard isn't accidentally
  satisfied only by `reconstruct_wing_body_forces`'s narrower `time,Fx,Fy,Fz` set). Fails: grader missing.
- [x] 5.4 **Test first (end-to-end on committed coarse CSV):** add
  `test_decompose_reproduces_coarse_peaks` — on `forces_t2a_newconv.csv`, assert the CFD side reproduces
  `peak CF_chord ≈ 0.92` / `CF_normal ≈ 2.61` via reused `reconstruct_wing_body_forces` (not re-derived) and
  returns the per-component + total model on the same time grid. Drives 5.5.
- [x] 5.5 **Implement** `decompose_wing_force(csv_path, *, f_star, phi_amp_deg, pitch_amp_deg,
  window_t0=STEADY_WINDOW_T0, rho=RHO)` in `benchmarks/flapping_wing.py`: reuse
  `reconstruct_wing_body_forces` for the CFD body-frame `CF`; reuse `euler_angles` + `stroke_rate` for
  `(α, ω, ω̇)`; call `van_veen_model` per component; normalize each by `compute_force_reference`; grade
  **G1 (normal peak magnitude) + G3 (closure)**, report the **normal peak-phase gap + curve RMSE**, G2, R1,
  R2; read `T4_CHORD_GCI_BAND` from `wing_grid_convergence_from_body_forces`. Return an enumerated-key dict
  with **no** chord verdict key and **no** phase/RMSE verdict key (reported only). 5.1–5.4 pass.

## 6. Decomposition figure (cluster-free)

- [x] 6.1 **Test first (figure exists + cluster-free):** in `tests/test_flapping_wing_validation_figures.py`,
  add `test_fig_force_decomposition_regenerates` — invoking the generator on the committed CSVs writes
  `fig_force_decomposition.pdf` + `.png` (`Agg` backend) with **no** plotfile/cluster dependency, and the
  plotted line data (`Line2D.get_ydata()`) equals the `decompose_wing_force` arrays via
  `np.testing.assert_allclose` (so the figure cannot plot stale/independent numbers). Fails: generator
  missing.
- [x] 6.2 **Implement** `fig_force_decomposition` in the flapping-wing figure script (chord & normal panels:
  model transl/AM/Wagner/total vs CFD total over the steady window). 6.1 passes.

## 7. RESULTS.md + reproducibility guard + repair inverted tests

- [x] 7.1 **Test first (T4 numbers reproducible + verdict updated) — BEFORE the doc edit:** in
  `tests/test_results_reproducibility.py`, add `test_t4_decomposition_numbers_reproduce` — the T4 subsection's
  per-component + total coefficients, the **graded normal peak magnitude** (≈2.48 vs CFD ≈2.61), the
  **reported** normal peak-phase gap (~0.058) + curve RMSE, and the known-answer translational-chord peak
  (≈0.42) recompute from the committed CSV as pinned literals; the T4 subsection
  uses a **distinct `###` header** not containing the substrings `lab-frame magnitudes` /
  `Body-frame per-component van Veen comparison`, adds/alters **no** cell in the two existing enumerated
  tables, and its numbers are **asserted-complete**; assert the wing Validation-Status row now reads
  **validated against van Veen's quasi-steady model / chord-grid-limited** (not PARTIAL), references **#50**
  and **not** an open **#40**; assert the existing headline-table + interim enumeration guards **still pass
  unchanged**; assert the T3b "Grid convergence" section and the new figure's Output Files row are present.
  Fails until 7.2.
- [x] 7.2 **Edit `RESULTS.md`:** replace the CF_chord "hypothesis (#40)" / PARTIAL language with the
  verified-against-model decomposition (normal consistent in **magnitude**, grid-dominated; peak-**phase**
  gap ~0.058 **reported** with its confounds; chord explained + grid-limited, #50); add the T4 subsection
  with its numbers; update the Validation-Status row; **keep** the correct "Fig 4" translational-target
  cites, relabel the "Fig 3–4" time-resolved cites (lines ~206/399) to Fig 13 **and** soften their (and
  line ~40's) "time-resolved per-component **curve match** (which resolves the split) is T4" wording →
  "time-resolved per-component **magnitude** comparison; phase/curve **reported**" (so RESULTS does not
  overclaim a gated time-resolved curve match after the phase→reported decision — round-3 docs); add the
  `fig_force_decomposition` row to the Output Files table; **keep** the "Grid convergence (T3b)" section and
  the added-mass-subtracted interim's numbers + metric-caveat intact — but update **only** that interim's
  stale *forward-looking* clause ("the residual is the **full T4**; **#40 remains open**") → "the residual
  is **resolved by the T4 decomposition** below (the interim *by itself* does not resolve it; **#40
  closed**)", so §7.3b's "resolved by … T4" phrase has an authorized home and coexists with the retained
  "does not resolve" wording (round-3 git). 7.1 passes.
- [x] 7.3 **Repair the two existing tests inverted by 7.2** (in the same docs commit): update
  `tests/test_flapping_wing_validation.py::test_results_doc_delivers_body_frame_and_defers_t4` (T4 is no
  longer *deferred* — assert the delivered-T4 wording instead of `"t4" in low` as a deferral) and
  `tests/test_results_reproducibility.py::test_interim_framing_is_honest_and_disambiguated` (only the
  `| … | PARTIAL |` Validation-Status assertion → the new validated-against-model/chord-grid-limited row;
  its still-valid `"does not resolve"` / `"t4"` / `"#40"` framing asserts stay). Both hard-assert the
  pre-T4 doc state and will fail on the 7.2 edit.
- [x] 7.3b **Test first (verdict changed BY T4, not by the interim — spec "Honest framing" clause):** in
  `tests/test_results_reproducibility.py`, assert the updated Validation-Status row (validated-against-model
  / chord-grid-limited) references **T4/#50**, **and** that the **interim** (`### Added-mass-subtracted
  body-frame …`) subsection still frames its drop as *isolating the added-mass share* and attributes the
  PARTIAL resolution to the **T4 decomposition** (an `isolat…` phrase + a "resolved by … T4" phrase in that
  subsection) — so the doc cannot be read as the interim itself resolving #40. Lands in commit (3) with
  7.2/7.3.

## 8. Roadmap + adjacent-doc de-stale sweep + status guard

- [x] 8.1 **Edit the docs** (one docs commit with §7): `docs/aerodynamics_validation/roadmap.md` —
  **(a) T4 row (line 97):** add a ✅ marker + PR ref **and rewrite the row body** — "decompose our total
  `ib_force` into **translational + rotational + added-mass**" → "… into **translational + added-mass +
  Wagner**"; "This tier is what **earns the word *validated*** for the wing" → "… what **validates the wing
  against van Veen's quasi-steady model** (consistency at matched kinematics)"; and its "**digitize** van
  Veen Fig 3–4" → the model-replot framing. **(b) Sequencing line (~99–100):** no longer "T4 … is next".
  **(c) Oracle table (line 74):** replace **both** "Fig 3–4" occurrences (the oracle cell **and** the Source
  column) with **Fig 13**, "digitized curve" → "van Veen's *model* replotted at our operating point (no
  digitization)", **and** soften the exit-criterion "**time-resolved** … match … **within tol**" → "peak
  **magnitude** within tol; **phase/RMSE reported**" (so the oracle-target row matches the delivered
  magnitude-only-graded reality — round-3 docs). **(d) Reconciliation log:** soften the bare "reserved *validated* for … the wing curve
  (T4)" line to "validated **against van Veen's QS model**", and add a **one-line note** that normal
  peak-**phase** is reported-not-gated because triply confounded (QS-intrinsic + grid non-convergence +
  single-wingbeat transient) — an evidence-based scoping decision, **NOT** a loosened tolerance (the
  magnitude gate stays sourced). Also de-stale `docs/coordinate-convention.md` (line 84, "deferred to Tier
  T4" + its "fig 3–4" → delivered + Fig 13), the `benchmarks/flapping_wing.py` module docstring (line ~20)
  and the `VAN_VEEN_CF_TARGETS` comment (lines ~56–59: drop "rotational drag"/"digitized"/"Section 3.3 …
  digitized = T4" → van Veen's tangential AM + Wagner; delivered), and `examples/flapping_wing/figures/
  README.md` (line 32 caveat → delivered + Fig 13; add a `fig_force_decomposition` table row). Beyond the
  single **phase-reported** note, **no** oracle-*relaxation* (loosened-tolerance) entry is added — T4's one
  magnitude gate stays sourced.
- [x] 8.2 **Test first (roadmap T4 row flipped + reframe present + no bare-validated leftover):** add a
  roadmap-status guard (new test or extend `tests/test_no_false_diffused_ib_claim.py`) asserting the T4 row
  (line 97) carries ✅ + the PR ref **and** its body no longer contains "translational + rotational +
  added-mass" or a bare "earns the word validated"; the Sequencing line no longer says "T4 … is next"; line
  74 has **no** remaining "Fig 3–4" (both occurrences) or "digitized curve"; the reconciliation-log bare
  "validated … wing curve (T4)" is softened; the `{transl, AM, Wagner}` / Fig 13 reframe strings are
  present; and the only reconciliation-log addition is the phase-reported note (no loosened-tolerance
  relaxation entry). Lands with 8.1 in the docs commit (guards the doc it ships with).

## 9. Erratum coefficient verification + pinned provenance

- [x] 9.1 **Verify** the pinned van Veen coefficients against the erratum **JFM 956 E1 (2023)** (fetch the
  erratum text; characterised as a "publisher-introduced"/production correction — most likely the malformed
  data-availability DOI). Confirm it does **not** change the fitted coefficients; if it **does**, update the
  pinned constant + CI in `van_veen_model.py` and record the deviation in `design.md` §D9. Note the outcome
  in the PR body.
- [x] 9.2 **Test first (pin the erratum outcome as a committed artifact):** add `test_erratum_checked` — a
  committed literal `ERRATUM_CHECKED = "JFM 956 E1 (2023): no coefficient change"` (or the corrected verdict
  from 9.1) is asserted in `tests/test_van_veen_model.py`, so "verified before trust" is a committed
  artifact, not only a human step. Lands with the model in the feat commit.

## 10. Verification

- [x] 10.1 `uv run ruff check .` and `uv run ruff format --check .` clean (note: CI lints
  `src/ tests/ scripts/ examples/prelim_sweep/` — the `examples/flapping_wing` figure script is outside the
  CI ruff path, so `.` here is the broader check that actually covers it).
- [x] 10.2 `uv run pytest` — full suite green (new + existing, incl. the two repaired tests).
- [x] 10.3 `"/c/Users/Elizabeth/AppData/Roaming/npm/openspec" validate decompose-wing-force-per-component
  --strict` passes.

## 11. Commit & PR discipline

- [ ] 11.1 **Commit grouping** (atomic, CI-green each; run `uv run pytest -m 'not gpu'` locally before each
  commit — CI only tests branch HEAD, so per-commit greenness is operator-enforced): (1) `chore(openspec)` —
  the **entire change dir** (`proposal.md`, `design.md`, `tasks.md`, `specs/flapping-wing-validation/spec.md`),
  docs-only, green; (2) `feat(flapping-wing)` — `van_veen_model.py` (+ moments, coeffs, `ERRATUM_CHECKED`) +
  the `stroke_rate` / `compute_wing_area_moments` refactor + `decompose_wing_force` + the figure generator +
  **all** §1–6 + §9.2 tests together (tests import the new code, so they may not precede it), green;
  (3) `docs` — the RESULTS.md + roadmap + adjacent-doc edits + the §7 reproducibility guard + the two
  **repaired** tests (§7.3) + the roadmap-status guard (§8.2), green. `ruff format` before each
  `src/`/`tests/` commit. **Every commit carries the `Co-Authored-By: Claude Opus 4.8 (1M context)
  <noreply@anthropic.com>` trailer.**
- [ ] 11.2 **#40 SHOULD close; #50 must NOT auto-close (G-1):** `Closes #40` is correct/desired (T4 resolves
  the PARTIAL). **#50** (T3c fine-grid, deferred) is the complementary open line — reference it
  **keyword-free** (`advances`/`see #50`), **never** a closing keyword adjacent to `#50`, **including in a
  negated clause** ("does not resolve #50" would still auto-close it; see
  [[github-negated-closing-keyword-autocloses]] — that incident was a PR-**body** phrase). PR title e.g.
  `T4: per-component van Veen force decomposition (Closes #40) (#<PR>)`. **Pre-merge grep over BOTH commits
  AND the PR title+body** (the PR #45 incident was a PR-body phrase `git log` alone would miss), with the
  no-space form covered (`[[:space:]]*`, since GitHub honors `closes#50`) **and a trailing digit boundary**
  `([^0-9]|$)` (so `#50` does not match `#500`/`#5000` — a false alarm — and, symmetrically, the #40 check
  is not spoofed-green by an unrelated `Closes #400`/`#4000` — review git-N1):
  ```
  { git log main..HEAD --format='%B'; gh pr view <PR> --json title,body -q '.title,.body'; } \
    | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]*#?50([^0-9]|$)' && { echo "FAIL: #50 would auto-close"; exit 1; } || true
  ```
  must print **nothing** for #50. **Separately confirm the closing keyword IS present for #40** (else the
  PARTIAL silently stays open):
  ```
  { git log main..HEAD --format='%B'; gh pr view <PR> --json title,body -q '.title,.body'; } \
    | grep -Eiq '(clos|fix|resolv)[a-z]*:?[[:space:]]*#?40([^0-9]|$)' || { echo "FAIL: no closing keyword for #40"; exit 1; }
  ```
- [ ] 11.3 **Rollback note:** the three commits are effect-independent, but the `docs` commit (3) imports the
  new code **and** `benchmarks/flapping_wing.py` is edited in **both** commit (2) (code) and commit (3)
  (docstring/`VAN_VEEN_CF_TARGETS` comment de-stale, disjoint lines), so a real rollback reverts (3)
  **before** (2): `git revert` (3) then (2) backs out the model+grader+figure+tests+docs without disturbing
  the openspec proposal (1).
