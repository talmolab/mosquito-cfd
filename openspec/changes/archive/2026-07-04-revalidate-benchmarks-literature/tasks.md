# Tasks — Re-validate benchmarks against literature oracles (Tier T2b)

TDD throughout: each implementation item is preceded by the **test written first** and the **behavior it
verifies**. Cluster-free tests are CI gates; committed-artifact tests gate on **file existence**
(`skipif(not Path(...).exists())`, loaded **inside** the test body — never at module import, or collection
errors instead of skipping). All Python via `uv`. Branch: `t2b-literature-revalidation` (off `main`).

**Commit discipline (see the Commit Plan at the bottom):** every test-first + doc/impl pair lands in the
**same commit** (or the impl immediately follows) so no pushed/bisected tip is CI-red. `openspec validate
--strict` is run per workstream commit. Each commit ends with the `Co-Authored-By: Claude Opus 4.8 (1M
context)` trailer.

## 1. Sphere — confinement-corrected literature grade (H1′) [force-extraction]

- [x] **1.1 (test first)** `tests/test_sphere_confinement_grade.py::test_richardson_grades_h1prime`
  — asserts the cluster-free grader, given confined Cd `1.131` and offset band `+3–6%`, returns the
  isolated-equivalent bracket by **division** `1.131/(1+[0.03,0.06]) = [1.067, 1.098]` (NOT
  `1.131*(1−offset)`), that it lies within `±5%` of `1.087`, and verdict `H1′`. Verifies **Scenario
  "Richardson-extrapolated Cd grades as H1′ within tolerance"**.
- [x] **1.2 (test first)** `test_tolerance_and_offset_not_loosened` — `±5%`, `+3–6%`, and `1.087` are
  **named constants**; a confined Cd whose isolated bracket falls outside `[1.033, 1.141]` grades **not
  H1′**; widening either constant fails a not-loosened guard. Plus `test_tolerance_edge_is_deterministic`
  — a bracket endpoint exactly at `1.141`/`1.033` is decided one documented way (inclusive/exclusive
  pinned). Verifies **Scenarios "Tolerance and offset band are pinned and not loosened"**,
  **"Tolerance-edge boundary case is decided deterministically"**.
- [x] **1.3 (impl)** Implement `grade_sphere_cd_confinement_corrected(cd_confined, *, offset_band=(0.03,0.06),
  literature_cd=1.087, tol=0.05)` in `src/mosquito_cfd/benchmarks/` (alongside `analyze_sphere.py`),
  returning the **division-form** isolated bracket + `verdict`. Docstring uses the division form verbatim.
  **Compute the bracket via `min/max` over both offset endpoints** — the larger offset yields the *smaller*
  isolated-equivalent, so `offset_band[0]` maps to the bracket *upper* end (`1.098`) and `offset_band[1]` to
  the *lower* (`1.067`); do not hard-code `offset_band[0]→bracket[0]`. **Takes Cd values only — no extractor
  internals touched (CC-V4).** Make 1.1–1.2 green.
- [x] **1.4 (test first, `requires_plotfile`)** `test_cv_regrade_is_traceable` — with
  `MOSQUITO_CFD_PLOTFILE_ROOT` set, asserts the companion calls `extract_sphere_cd(method="cv", x_inlet=2.0,
  x_outlet=8.0)` (**not** the marker default ~0.45) and that its `cd` equals `sphere_cv_drag_cd(...)["cd"]`
  (≈1.18) — **extraction traceability only**. It does **NOT** feed the single medium `1.18` to the H1′ grade
  (`1.18/(1+[0.03,0.06]) = [1.113,1.146]`, upper edge `1.146 > 1.141` → **not H1′**); the H1′ **verdict** is
  graded cluster-free on the **Richardson** value `1.131` (two grids). **Auto-skips** off-cluster. Verifies
  **Scenarios "Companion re-grade verifies CV extraction traceability (verdict stays on Richardson)"** and
  **"Off-cluster run auto-skips"**.
- [x] **1.5 (impl/docs)** Add the H1′ grade to `examples/flow_past_sphere/RESULTS.md` (literature verdict
  row + isolated-equivalent bracket), and **reconcile the pre-existing "≈1.00–1.11" isolated-equivalent
  line** (line ~84) against the new `[1.067, 1.098]` — either explain why the new bracket is tighter (pure
  confinement division vs the old viscous/order-budget bracket) or replace it, so the doc does not carry two
  unexplained brackets. **Cross-reference** the confinement-offset provenance already in the
  `force-extraction` spec rather than restating it (DRY). Note in the doc that the `[1.067,1.098]` bracket's
  source of truth is the grader unit test (task 1.1), since — unlike the flapping headline numbers — no
  doc-reading reproducibility test guards this sphere value.

## 2. Ellipsoid — re-run for SumU, then self-consistency + added-mass sanity [heaving-ellipsoid-validation]

- [x] **2.1 (test first)** `tests/test_heaving_ellipsoid.py::test_added_mass_force_is_rho_times_sumu` —
  on a known row (synthetic fixture, see 2.2), `added_mass_force(ρ_f·SumU)` equals the
  `WriteIBForceAndMoment` value (reuse `flapping_wing.added_mass_force`), formula cited in the docstring.
  Verifies **Scenario "Added-mass formula is locked to the IAMReX source, not tuned"**.
- [x] **2.2 (test first + fixture)** Add a **cluster-free synthetic fixture** `tests/fixtures/ellipsoid_synthetic_ib.csv`
  (or an in-test DataFrame builder, mirroring the `stress_integral` `_synthetic_box` pattern) with `SumU*`
  columns shaped so the added-mass fraction is (a) `0 ≤ f < 1`, (b) largest at `t≈0` and monotonically
  decaying past `t=7`, (c) max consecutive Δ over `t≥7` `< 1%`. Tests `test_added_mass_fraction_bounded_and_decays`
  (bounded + decays, run **cluster-free** on the fixture) and `test_added_mass_vs_van_veen_reported_not_matched`
  (the 15%/31% comparison is reported + **cited to the roadmap oracle row, which cites van Veen 2022**, and
  **no** test asserts a tight match). Verifies **Scenarios "Added-mass fraction is bounded and decays"**,
  **"Van Veen 15%/31% is a reported, cited sanity ballpark, not a graded match"**.
- [x] **2.3 (test first)** Self-consistency grades the **drag `Fx`** and **heave-lift `Fy`** channels (not
  the identically-zero spanwise `Fz`): `test_self_consistency_below_threshold` (fixture: max consecutive Δ
  over `t≥7` `< 1%` passes); `test_self_consistency_fails_above_threshold` (a synthetic series with Δ≈1.5%
  over `t≥7` **fails** — the gate can fail); `test_self_consistency_tol_not_loosened`
  (`SELF_CONSISTENCY_TOL == 0.01` pinned); `test_coarse_series_declines_clearly` (the 11-point `forces.csv`
  **declines with a clear error** — too few samples in the window — a single deterministic branch);
  `test_heave_channel_nonzero` (the graded `Fy` lift channel is non-zero, so the lift-side gate is not a
  degenerate `0/0`). Verifies **Scenarios "Steady-window force change is below the pinned threshold"**,
  **"The gate fails above the threshold"**, **"Coarse committed series is handled deterministically, not
  spoofed"**.
- [x] **2.4 (test first)** `test_run_metadata_records_pinned_provenance` — `capture_surrogate_run_metadata`
  records the `sha256:` digest under `docker_image`, verbatim timestamp, inputs hash, and a **top-level**
  `iamrex_commit` starting with `f93dc794` (via `extra=`); a mutable tag raises `ValueError` (through
  `validate_image_digest`). `test_deck_hash_matches_recorded` — `run_metadata_t2b.json["inputs"]["hash"]
  == hash_file("examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid")` (verifies byte-unchanged; gated
  on the committed metadata file). `test_grader_tests_skip_without_artifact` — the CSV graders **skip** via
  `skipif(not Path(".../forces_t2b_ib.csv").exists())` (committed-file predicate, **not** the
  `requires_plotfile` env marker), loading the CSV **inside** the test. Verifies **Scenarios "Provenance
  records…"**, **"Deck byte-invariance is verified…"**, **"Grader tests skip on the committed-artifact
  predicate…"**.
- [x] **2.5 (impl)** Implement `src/mosquito_cfd/benchmarks/heaving_ellipsoid.py`: self-consistency grader
  (named `STEADY_WINDOW_T0=7`, `SELF_CONSISTENCY_TOL=0.01`), added-mass fraction (reusing `added_mass_force`),
  van-Veen-ballpark reporting. Make 2.1–2.4 green on the synthetic fixture + skips.
> **2.6 / 2.7 are DEFERRED to the operator A40 re-run — tracked in [#43](https://github.com/talmolab/mosquito-cfd/issues/43).**
> PR #42 landed the graders + cluster-free numerics; the ellipsoid `SumU` capture + real-data verdicts
> land via #43 (like T2a's #40). The artifact-dependent tests auto-activate when the CSV/metadata land.

- [ ] **2.6 (operator re-run, cluster) — deferred to [#43](https://github.com/talmolab/mosquito-cfd/issues/43)** Run the **byte-unchanged** `inputs.3d.heaving_ellipsoid` on the
  pinned `:fp64` image (IAMReX `f93dc794`) via the RunAI/WSL pattern (CLAUDE.md), 29-col IB output enabled,
  plotfiles to `MOSQUITO_CFD_PLOTFILE_ROOT`. **Grade the fresh CSV locally (task 5.2) BEFORE `git add`** —
  commit `examples/heaving_ellipsoid/{forces_t2b_ib.csv, run_metadata_t2b.json}` (via
  `capture_surrogate_run_metadata`, caller-supplied timestamp; carry the T2a `git.dirty:true` explanatory
  `note`) **only if self-consistency is green**. Commit the 29-col header doc / a `units.json` sidecar so
  the CSV is self-describing. Re-run the now-unskipped 2.1–2.4 against the real artifact.
  **Negative-result fallback:** if the re-run misses Δ<1%, do **NOT** loosen `SELF_CONSISTENCY_TOL` and do
  **NOT** commit the artifact (keeps 2.x skipped, CI green); record the miss as a **negative-result
  verdict** in RESULTS.md + open a follow-up issue; the other three workstreams ship regardless.
- [ ] **2.7 (docs)** Add the self-consistency verdict + added-mass fraction (reported **vs** the van Veen
  15%/31% ballpark, **cited** to the roadmap oracle row / van Veen 2022 — not free-restated) to
  `examples/heaving_ellipsoid/RESULTS.md`. **Leave** the line-91 "~60% discrepancy" note for **CC-V5/#29**
  (out of scope) — add a one-line pointer that **names #29** so the retained line reads as intentional.

## 3. Flapping — band-as-floor + RESULTS #3 re-validation [flapping-wing-validation]

- [x] **3.1 (test first)** `tests/test_flapping_band_floor.py::test_floor_graded_ceiling_reported` — the
  gate grades `max|CF_x|`, `max|CF_z| ≥ 0.5` (floor) and does **not** fail when a peak exceeds `1.5`;
  `test_new_convention_cf_x_above_ceiling_not_failure` on `forces_t2a_newconv.csv` (`max|CF_x| = 2.37`)
  passes the floor gate; the resultant + `cf_z_floor_margin` are reported. Verifies **Scenarios "Peak
  coefficients clear the O(1) floor…"**, **"A per-component peak above the ceiling is expected, not a
  failure"**, and (with the existing `test_steady_window_pinned_and_margins_reported`, which task 3.3 keeps
  green) the **"Steady window is pinned by a physical criterion and reproducible"** scenario incl. its
  `And` margin clause.
- [x] **3.2 (test first)** `test_floor_still_catches_under_produced` — a sub-`0.5` peak (e.g. `CF_z 0.22`)
  **fails** the floor; `test_van_veen_band_is_not_loosened` still asserts `VAN_VEEN_BAND == (0.5, 1.5)`.
  Verifies **Scenario "The floor still catches an under-produced coefficient (not loosened)"**.
- [x] **3.3 (impl)** Modify `plausibility_gate` in `src/mosquito_cfd/benchmarks/flapping_wing.py` to grade
  the **lower-bound floor** (both components `≥ 0.5`) and **report** (not gate) the ceiling. **Preserve the
  existing return-dict keys `cf_x_ceiling_margin`, `cf_z_floor_margin`, `cf_x_in_band`, `cf_z_in_band`** —
  they are load-bearing for the existing `tests/test_flapping_wing_validation.py` at lines **118-119**
  (`*_margin > 0`) **and 71-82** (`test_ib_force_gate_in_band_without_fudge`, which reads
  `cf_x_in_band`/`cf_z_in_band`), both of which stay green on the old-run `forces.csv` (CF_x 1.41 → ceiling
  margin 0.09 > 0, still two-sided in-band). `VAN_VEEN_BAND` value unchanged. Make 3.1–3.2 green; keep both
  existing old-run tests green.
- [x] **3.4 (test first — issue #3)** `tests/test_results_reproducibility.py` — recompute **every**
  RESULTS.md headline number from committed CSVs, each by its correct definition, pinned as concrete
  literals:
  - lab coefficients (`forces_t2a_newconv.csv`, `t≥0.05`, `F_ref=200.27` via `compute_force_reference`):
    `CF_x` range `[−2.35,+2.37]`, `CF_z` range `[−1.46,+0.03]`, `max|CF_x|≈2.37`, `max|CF_z|≈1.46`;
  - body-frame via `body_frame_overall_match`: peak `CF_normal≈2.61` (`cf_normal_match=True`), `CF_chord≈0.92`
    (`cf_chord_match=False`), cycle-means `1.06`/`0.52` — reproducing the **PARTIAL** verdict;
  - phase-table `Fz` as **raw forces** — NOT via `compute_force_coefficients`. The table's `t` column is
    **wingbeat phase** (0…1), while the CSV `time` runs 0…2; the test SHALL map phase→CSV row via the
    documented `phase = (time·f*) mod 1` convention (`f*=1`), reading `phase 0.25/0.50/0.75 → Fz
    −9.9/−290.3/−18.4` and the `argmax|Fz|` peak `≈−292` at phase `≈0.49`;
  - added-mass fractions as the **RMS** `added_mass_fraction` values (stroke ~37 % / lift ~29 %);
  - contrast baseline (`forces.csv`): `1.41`/`0.68`.
  The enumeration is **asserted complete** (a headline number absent from it fails the test). **Runs green
  before any doc edit.** Verifies all three **RESULTS.md-reproducibility scenarios**.
- [x] **3.5 (impl/docs)** After 3.4 is green, clarify in `examples/flapping_wing/RESULTS.md` that `[0.5,1.5]`
  is a lower-bound **floor/sanity** (not the van Veen per-component gate) and the body-frame targets are the
  graded per-component oracle — with the docs NOT claiming time-resolved validation (T4 deferral retained).
  Extend the existing `test_results_doc_delivers_body_frame_and_defers_t4` (or add an assertion) so the
  "floor"/"lower-bound" wording is guarded and "van veen gate" is not claimed of the lab band. **No headline
  number changes** (proven reproducible in 3.4). Then **close issue #3**, noting `test_results_reproducibility.py`
  is the **durable regression guard**.

## 4. METHODS.md pin reconciliation [benchmark-provenance]

- [x] **4.1 (test first)** `tests/test_methods_pin_consistent.py::test_methods_iamrex_pin_matches_build_args`
  — extract a **7-to-40-hex** commit token from the METHODS.md software-stack IAMReX row and the full 40-hex
  from `docker/build-args.env`; assert `build_pin.startswith(methods_pin)` with `len(methods_pin) >= 7`,
  failure message naming both sources. On the **current** doc it extracts `c5f8e2a` and produces a genuine
  **mismatch** assertion failure (not an extraction error) — the valid test-first red. Verifies **Scenario
  "METHODS.md commit is a prefix of the build-args pin"**.
- [x] **4.1b (test first)** `test_methods_has_no_stale_provenance` — `benchmarks/METHODS.md` names
  `talmolab/IAMReX` and `docker/Dockerfile.fp64`, the sphere analysis example **positively contains**
  `method="cv"` (a **positive** assertion — the current bare-default `extract_sphere_cd('…')` carries no
  literal `method="marker"` string, so a "marker absent" negative would be **vacuous** and give no
  regression guard for the fix), and the doc does **NOT** contain `c5f8e2a` or `Dockerfile.iamrex`. The
  upstream FP32 issue link `ruohai0925/IAMReX#59` is explicitly **allowed** (a legitimate upstream-issue
  reference), so the test targets the specific stale strings, not every `ruohai0925`. On the current doc it
  fails (no `method="cv"` in the example; `c5f8e2a`/`Dockerfile.iamrex` present); passes after 4.2. Verifies
  **Scenarios "The repository is the fork, not upstream…"**, **"Stale build/Docker/extraction references
  are corrected…"**.
- [x] **4.2 (impl/docs)** Reconcile `benchmarks/METHODS.md`: line 15 → `talmolab/IAMReX @ f93dc794` (repo
  **and** hash, abbreviation matched by the prefix rule); line 174 `Dockerfile.iamrex` → `docker/Dockerfile.fp64`;
  the sphere analysis example (~line 214) → `extract_sphere_cd(..., method="cv")`; the ellipsoid run-command
  block (~lines 198-203) reconciled to the actual T2b re-run (consistent with `run_metadata_t2b.json`); the
  illustrative `run_metadata.json` block (~lines 220-238) gains an `iamrex_commit` field and no longer labels
  a git commit `sha256`; line 24's upstream `ruohai0925/IAMReX#59` link kept with a one-line note that the
  **fork** is what is built; the line-80 pointer ("computed values and **discrepancy investigation**") →
  reworded to the closed H1′ literature grade; Known-Limitation #1 refreshed so no line contradicts the
  pinned image (a one-line pointer to the sphere H1′ verdict in `flow_past_sphere/RESULTS.md`; the "~60%
  low / 2.64×" substance stays with **CC-V5/#29**). Make 4.1 + 4.1b green.

## 5. Roadmap + validation

- [x] **5.1 (docs, cluster-free — commit C6)** Update `docs/aerodynamics_validation/roadmap.md`: **T2b
  Tiers-table row (line ~94)** → the cluster-free verdicts (sphere H1′, flapping band-as-floor, METHODS pin)
  with the ellipsoid cell marked **"pending operator re-run"** (finalized to its verdict — or a
  negative-result — in commit C7 when the artifact lands), and **fix its exit-criterion text** ("flapping
  CF in band without fudge" → "flapping peak |CF| clears the O(1) floor; body-frame CF_normal PASS /
  CF_chord PARTIAL (#40)"); the
  **oracle-grounding flapping row (line ~73)** and **axis-convention row (line ~71)** → reword "within the
  band / gate" to the **floor** framing so the roadmap does not contradict the RESULTS/spec; the
  **reconciliation-log note (line ~213)**. NB both line ~213 and lines ~190-191 sit inside the **dated
  frozen** "Reconciliation log — adversarial roadmap review (2026-06-24)" section, where `7ece065d` was the
  accurate fork pin *on that date*; rewriting either would falsify the log, so each gets a **parenthetical
  forward-pointer** ("later demoted to a floor in T2b" on 190-191; "the fork pin is now `f93dc794`
  post-T2a, reconciled in T2b" on 213), **not** a hash rewrite. Link this change + #3; note #40 (CF_chord)
  + T3/T4 remain.
- [x] **5.2 (validation)** `uv run ruff check .` + `uv run ruff format --check .`; `uv run pytest`
  (cluster-free tests green; `requires_plotfile`/artifact-gated skips reported); `openspec validate
  revalidate-benchmarks-literature --strict` clean — run **per workstream commit**, not only at the end.
- [x] **5.3 (reconciliation gate)** Before commit, re-read `proposal.md` / `design.md` / the four spec
  deltas and verify the implementation matches (named constants present, CC-V4 separation intact,
  `VAN_VEEN_BAND` value unchanged, `plausibility_gate` keys preserved, provenance fields captured + deck
  hash verified, prefix-match pin test, negative-content guard). If the ellipsoid re-run misses the pinned
  threshold, record a **negative-result verdict** — never loosen `SELF_CONSISTENCY_TOL` (CC-V2). Record any
  deviation with a `### Why N instead of M?` note per the new-feature workflow.

## Commit plan (each tip CI-green; test+doc/impl paired per commit)

1. **C1** `docs(benchmark-provenance): reconcile METHODS.md IAMReX pin + add prefix-match consistency tests` — 4.1, 4.1b, 4.2 (test red-on-current → doc fix, same commit; diff is test + doc + spec, no `src/`). GREEN.
2. **C2** `feat(force-extraction): grade sphere Cd via confinement-corrected H1′` — 1.1–1.5 (1.4 `requires_plotfile` skips in CI). GREEN.
3. **C3** `refactor(flapping-wing-validation): demote [0.5,1.5] band to a floor` — 3.1–3.3 (preserve gate keys). GREEN.
4. **C4** `test(flapping-wing-validation): assert RESULTS.md headlines recompute from committed CSVs (closes #3)` — 3.4, 3.5 (test green before doc edit; the enumeration-complete guard **intentionally fails-closed** on any *future* RESULTS headline edit — that is its value as the durable #3 guard, not a regression). GREEN.
5. **C5** `feat(heaving-ellipsoid-validation): self-consistency + added-mass grader (synthetic-fixture numerics; artifact tests skip)` — 2.1–2.5. GREEN.
6. **C6** `docs(roadmap): tick T2b + fix floor/gate + stale-hash notes` — 5.1 (cluster-free, no dependency on the ellipsoid artifact — lands **before** the operator run so the docs are fully reconciled in the pre-artifact PR batch). GREEN.
7. **C7** `feat(heaving-ellipsoid-validation): commit T2b re-run artifact + grade` — 2.6, 2.7 (operator-gated; committed only if self-consistency green locally). GREEN or negative-result fallback (no artifact commit).

**PR strategy:** single PR (links #3 + the roadmap T2b tier), opened after C1–C6 (all cluster-free/green — the roadmap tick states ellipsoid as "pending operator re-run" until C7 lands); C7 pushed as a follow-up commit once the operator re-run lands. The PR is reviewable and mergeable with the three cluster-free workstreams + docs even if C7 slips (ellipsoid then ships as a negative-result or a follow-up).
