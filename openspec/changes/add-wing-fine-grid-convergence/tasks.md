# Tasks — add fine-grid (256³) flapping-wing convergence (T3c)

TDD throughout: each implementation task names the **test written first** and the behavior it verifies
**before** the code exists. `uv` for all Python. Branch: `add-wing-fine-grid-convergence-t3c` (off
`main`). Report-only — no pass/fail, no tolerance constant, no verdict key. Reuse committed
coarse/medium CSVs; no re-derivation of body-frame or F_ref logic. Test paths are repo-root-relative
`Path(...)` — never a hard-coded `Z:\…` or drive letter.

> **Operator-run gate → two sessions.** This session (**Session A**) delivers the reviewed + approved
> proposal (§9), the fine-grid deck (§0), and all TDD cluster-free code (§1). Everything that needs
> the fine-grid run data lands in a later **Session B** (`/openspec:apply`) after the operator A40 run.
> Tasks are tagged **[Session A]** (cluster-free, this session) or **[Session B: needs-run]**.

---

## 0. Fine-grid input deck — [Session A]

- [x] 0.1 **Create** `examples/flapping_wing/inputs.3d.convergence_fine` as an **exact copy** of
  `inputs.3d.convergence_medium` with two changes: `amr.n_cell = 256 128 256` and
  `amrex.the_arena_init_size = 28` added (the arena cap — see design D5). Update the header comment to
  identify this as the T3c fine deck and document the CFL check (Δx=0.03125, CFL≈0.45, dt=5e-4held).
  All other parameters — `ns.fixed_dt`, `particle_inputs.radius`, kinematics, BCs, domain, `amr.plot_int=100`
  — are **identical** to medium.
- [x] 0.2 **Test first (deck invariance):** extend `tests/test_convergence_deck.py` (the existing file
  that guards the coarse↔medium pair) with `test_fine_deck_matches_medium_except_n_cell_and_arena`.
  Parse both decks into `{key: value}` maps (comments stripped, whitespace normalized); assert the
  symmetric difference is exactly `{amr.n_cell, amrex.the_arena_init_size}`; assert `amr.n_cell` is
  `"256 128 256"` in fine and `"128 64 128"` in medium; assert `ns.fixed_dt` is `5e-4` in both,
  `particle_inputs.radius` is `1.5` in both, `amr.plot_int` is `100` in both.
  Fails: deck missing or extra field changed.
- [x] 0.3 **Test first (3-deck temporal isolation):** in `tests/test_convergence_deck.py` add
  `test_all_three_decks_share_fixed_dt_and_radius`. Parse coarse (`inputs.3d.validation`), medium
  (`inputs.3d.convergence_medium`), and fine (`inputs.3d.convergence_fine`); assert `ns.fixed_dt ==
  5e-4` and `particle_inputs.radius == 1.5` in all three. Directly covers the "Temporal isolation
  and IB regularization held across all three grids" spec scenario. Fails: deck missing or dt/radius
  changed.
- [x] 0.4 **Verify:** `uv run pytest tests/test_convergence_deck.py -k "fine_deck or three_decks" -v`.

---

## 1. 3-grid convergence functions + guards (TDD, cluster-free) — [Session A]

### 1.1 New scalar function `wing_grid_convergence_3grid`

- [x] 1.1.1 **Test first (known-answer, monotone):** in `tests/test_wing_grid_convergence.py` add
  `test_wing_grid_convergence_3grid_known_answer`. Use a synthetic triple with exact p=2 convergence
  (e.g. `cf_coarse=1.0, cf_medium=0.25, cf_fine=0.0625` at `r=2`: δ₁₂=−0.75, δ₂₃=−0.1875,
  ratio=4=2², p_obs=2.0 exactly; `cf_exact = 0.0625 + (−0.1875)/(4−1) = 0.0625 − 0.0625 = 0.0`).
  Assert `observed_order == pytest.approx(2.0)`, `cf_exact_richardson == pytest.approx(0.0)`,
  `monotone == True`, all values finite, no `*_pass`/`converged`/`verdict` key. Fails: function missing.
- [x] 1.1.2 **Test first (self-convergence):** add `test_wing_grid_convergence_3grid_self_convergence`.
  Feed the same value for all three grids (e.g. `cf=0.5` on all). Assert `monotone=True`,
  `observed_order=NaN` (δ₂₃=0, degenerate), `cf_exact_richardson=NaN`, `gci_fine=NaN`. The
  self-convergent triple should not raise.
- [x] 1.1.2b **Test first (p_obs ≤ 0 — decelerating convergence):** add
  `test_wing_grid_convergence_3grid_negative_order`. Use `cf_coarse=1.0, cf_medium=0.9, cf_fine=0.5`
  (δ₁₂=−0.1, δ₂₃=−0.4, |δ₁₂/δ₂₃|=0.25, p_obs=log(0.25)/log(2)=−2.0 — monotone but decelerating).
  Assert `monotone=True`, `observed_order == pytest.approx(-2.0)` (informative, returned as-is),
  `gci_fine=NaN` (denominator `r**p_obs − 1 < 0`, meaningless GCI), `cf_exact_richardson=NaN`. Never
  a ValueError.
- [x] 1.1.2c **Test first (p_obs ≈ 0 — equal deltas):** add
  `test_wing_grid_convergence_3grid_zero_order`. Use `cf_coarse=1.0, cf_medium=0.75, cf_fine=0.5`
  (δ₁₂=−0.25, δ₂₃=−0.25, ratio=1.0, p_obs=0). Assert `monotone=True`, `observed_order ≈ 0` or NaN,
  `gci_fine=NaN` (denominator near-zero guard fires), `cf_exact_richardson=NaN`. Never a ValueError.
- [x] 1.1.3 **Test first (non-monotone, oscillating):** add
  `test_wing_grid_convergence_3grid_non_monotone`. Use `cf_coarse=1.0, cf_medium=0.5, cf_fine=0.8`
  (went down then up: δ₁₂=−0.5, δ₂₃=+0.3, opposite signs). Assert `monotone=False`,
  `observed_order=NaN`, `cf_exact_richardson=NaN`, `gci_fine=NaN`. Never a ValueError.
- [x] 1.1.4 **Test first (degenerate coarse/medium inputs):** add
  `test_wing_grid_convergence_3grid_degenerate`. Use `cf_fine=0.0` (below `_DEGENERATE_CF_FLOOR` as
  the fine-grid denominator) → `ValueError(match="degenerate")`. Use `cf_coarse=np.nan` → `ValueError`.
  Use `r=1.0` → `ValueError`.
- [x] 1.1.5 **Test first (report-only key set):** add `test_wing_grid_convergence_3grid_key_set`. For
  any valid monotone triple, assert return keys are exactly `{cf_coarse, cf_medium, cf_fine,
  observed_order, cf_exact_richardson, gci_fine, r, monotone}` — no `*_pass`, no `converged`, no
  `verdict` key. Assert `r == 2.0` (the refinement ratio from the deck pair).
- [x] 1.1.6 **Implement** `wing_grid_convergence_3grid(cf_coarse, cf_medium, cf_fine, *, r=2.0,
  safety_factor=1.25) -> dict[str, float | bool]` in `wing_convergence.py`.
  All 1.1.1–1.1.5 + 1.1.2b + 1.1.2c tests pass.

### 1.2 Extend `wing_grid_convergence_from_body_forces` with optional `fine_csv`

- [x] 1.2.1 **Test first (3-grid return shape):** add `test_wing_grid_convergence_3grid_from_body_forces`
  in `tests/test_wing_convergence_medium.py`. Use the committed coarse CSV as all three inputs (coarse =
  medium = fine = `forces_t2a_newconv.csv`). Assert the return dict still has keys `{cf_chord,
  cf_normal}`; each sub-dict has the **3-grid key set** `{cf_coarse, cf_medium, cf_fine,
  observed_order, cf_exact_richardson, gci_fine, r, monotone}`. Assert `monotone=True` for both
  (self-convergence), `observed_order=NaN` (self-convergence degenerate), all other floats finite or
  NaN. Assert no `*_pass`/`converged`/`verdict` key. Fails: parameter not added yet.
- [x] 1.2.2 **Test first (2-grid path unchanged):** add `test_wing_grid_convergence_from_body_forces_unchanged`
  — call with `fine_csv=None` (explicit) and without the param at all; assert the return has the OLD
  2-grid key set `{cf_coarse, cf_medium, relative_change, gci_p1, gci_p2, r}`. Verifies backward-compat.
- [x] 1.2.3 **Implement** the `fine_csv: str | Path | None = None` parameter on
  `wing_grid_convergence_from_body_forces`. When `None`: unchanged code path (2-grid). When not `None`:
  compute `_peaks(fine_csv)` and call `wing_grid_convergence_3grid(coarse_X, medium_X, fine_X)` per
  component. Both 1.2.1 and 1.2.2 pass.

### 1.3 `assert_gradeable_triple` guard

- [x] 1.3.1 **Test first:** add `test_assert_gradeable_triple_guards` in
  `tests/test_wing_convergence_medium.py`. Cases (a)–(f) all implemented and passing.
- [x] 1.3.2 **Implement** `assert_gradeable_triple(coarse_csv, medium_csv, fine_csv, *, coarse_deck=None,
  medium_deck=None, fine_deck=None, stop_time=_STOP_TIME) -> None`. Reuses `assert_gradeable_pair`
  internally: call `assert_gradeable_pair(coarse, medium)`, then `assert_gradeable_pair(medium, fine)`.
  Optionally check `_deck_float` for all three decks. Self-describing errors. 1.3.1 passes.

### 1.4 Fine-data schema pin test (Session A, skipif fine CSV absent)

- [x] 1.4.1 **Test first (schema + plausibility):** add `test_fine_csv_matches_ib_particle_contract`
  in a new `tests/test_wing_convergence_fine.py`. Mark `@pytest.mark.skipif(not _FINE_CSV.exists(), ...)`.
  Assert `list(pd.read_csv(forces_fine.csv).columns)` equals the pinned 29-column `_IB_PARTICLE_29_COLS`
  in exact order; `df["time"].max() == pytest.approx(1.0, abs=1e-3)`; `len(df) > 1900`. The test
  **skips** in CI (no fine CSV until Session B) and **runs** in Session B once the data is committed.
- [x] 1.4.2 **Test first (provenance pin):** add `test_run_metadata_t3c_fields` in
  `tests/test_wing_convergence_fine.py`, skipif absent. Load `run_metadata_t3c.json`; assert
  `metadata["iamrex_commit"].startswith("f93dc794")`, `metadata["tier"] == "T3c"`,
  `metadata["grid"] == "256 128 256"`, `metadata["inputs"]["hash"] == sha256(inputs.3d.convergence_fine)`,
  `metadata` carries `docker_image`/`image_digest` + `fixed_dt`/`dt_reduced` fields.

---

## 2. Verification — Session A suite must be green

- [ ] 2.1 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [ ] 2.2 `uv run pytest tests/test_wing_grid_convergence.py tests/test_wing_convergence_medium.py
  tests/test_convergence_deck.py -v` — all Session A tests pass; §1.4 tests report SKIPPED (not ERROR).
- [ ] 2.3 The full suite `uv run pytest` is green (no regressions in existing T3a/T3b/T4 tests).

---

## 3. Session B pre-flight (operator, before committing data) — [Session B: needs-run]

- [ ] 3.1 **Submit the fine-grid run** on the A40: deck `inputs.3d.convergence_fine`, same
  `:fp64 @ f93dc794`, same `mpirun … amr3d.gnu.MPI.CUDA.ex`. Confirm GPU memory is acceptable
  (`nvidia-smi` shows < 36 GB used with `amrex.the_arena_init_size=28`). Estimated ~2 hr. If OOM
  despite the cap, document as a blocker in `run_metadata_t3c.json["oom_blocker"] = true` and stop.
- [ ] 3.2 **If run diverges at dt=5e-4:** reduce `ns.fixed_dt = 2.5e-4` at runtime (NOT a deck
  change), raise `max_step = 4000` (to reach `stop_time=1.0`), confirm plotfiles still land near
  `t = 0.5`. Record `dt_reduced=true` in metadata; flag temporal confounding in RESULTS (see §4.4).
- [ ] 3.3 **Confirm the `t ≈ 0.5` plotfile exists** (e.g. `plt01000` at dt=5e-4 or `plt02000` at
  dt=2.5e-4) under the fine run dir before tearing down the job. Without it, the fine LEV is absent.
- [ ] 3.4 **Sanity before grading:** run `assert_gradeable_triple(forces_t2a_newconv.csv, forces_medium.csv,
  forces_fine.csv)` to confirm the triple passes (non-empty, covers 1.0, same time grid at dt=5e-4;
  if dt was reduced, the guard will raise "time-grid" — see §3.2 above for the dt-reduction branch).

---

## 4. Commit fine data + RESULTS (Session B) — [Session B: needs-run]

- [ ] 4.1 **Commit** `examples/flapping_wing/forces_fine.csv` + `examples/flapping_wing/run_metadata_t3c.json`
  beside coarse/medium. Both §1.4 tests pass. Commit invariant: CSV and schema test in the same commit.
- [ ] 4.2 **Grade 3-grid convergence:** call `assert_gradeable_triple(coarse, medium, fine)` then
  `wing_grid_convergence_from_body_forces(coarse, medium, fine_csv=fine, f_star=1.0, phi_amp_deg=70.0,
  pitch_amp_deg=45.0)`. Record per-component `observed_order`, `cf_exact_richardson`, `gci_fine`,
  `monotone` for the RESULTS section.
- [ ] 4.3 **Test first (end-to-end real triple):** in `tests/test_wing_convergence_fine.py` add
  `test_fine_3grid_reports_from_committed_csvs` (skipif fine CSV absent). Call `assert_gradeable_triple`
  then `wing_grid_convergence_from_body_forces(coarse, medium, fine_csv=fine, ...)`. Assert return
  has `{cf_chord, cf_normal}` each with the 3-grid key set; `r == 2.0`; all float values finite or NaN;
  no verdict key; `monotone` present as bool. Does NOT assert a specific observed_order (report-only).
- [ ] 4.4 **Add** `### Grid convergence (T3c, fine 256³)` subsection to `examples/flapping_wing/RESULTS.md`
  under `### Grid convergence (T3b, medium 128³)`:
  - A 3-column table: coarse / medium / fine peak CF_chord / CF_normal
  - Observed convergence order p_obs per component (NaN if non-monotone)
  - Richardson estimate cf_exact_richardson with a self-contained IB caveat written directly in RESULTS
    (not a pointer to design.md, which will be archived): "cf_exact_richardson is an illustrative
    Richardson estimate — the diffused-IB regularization sharpens with the grid (dv = h·d_nn²), so
    each delta reflects combined spatial + IB-model refinement; cf_exact_richardson is NOT a
    definitive h→0 limit"
  - GCI at observed order for the fine grid
  - Verdict stated in prose ("converging toward model total ≈ 0.43" / "not yet converged" / "non-monotone
    at fine grid" — whichever applies); **no pass/fail key**
  - If dt was reduced: "Note: fine run used dt=2.5e-4 (instability at 5e-4); temporal confounding
    introduced; coarse/medium 2-grid comparison (same dt) remains temporally isolated"
  - LEV: `wing_lev_report` at `t ≈ 0.5` on the fine grid (if plotfiles available); or "force-only
    run — LEV not available for fine grid" if plot_int=-1 was used

---

## 5. Reproducibility guard (T2b/T3b pattern) — [Session B: needs-run]

- [ ] 5.1 **Test first:** in `tests/test_results_reproducibility.py` add
  `test_3grid_convergence_recomputes_from_committed_csvs` (skipif fine CSV absent). Call
  `assert_gradeable_triple`, then `wing_grid_convergence_from_body_forces(coarse, medium, fine_csv=fine,
  ...)`, assert per-component values match the RESULTS §4.4 headline literals to `abs ≈ 0.02`;
  also assert `sha256(inputs.3d.convergence_fine) == run_metadata_t3c.json["inputs"]["hash"]` (fine
  deck pinned). Fails until RESULTS carries the numbers.
- [ ] 5.2 5.1 passes once RESULTS + data are committed together.

---

## 6. Roadmap + METHODS + handoff doc update

- [x] 6.1 **[Session A]** Add `⬜ **T3c** ([#50](…))` row to `docs/aerodynamics_validation/roadmap.md`
  Tiers table; updated the Sequencing paragraph and the "Out of scope" section to reflect T3c in-flight.
- [x] 6.2 **[Session A]** Create `docs/aerodynamics_validation/t3c-handoff.md` (operator instruction
  doc, same format as `t3b-handoff.md`). Includes: deck path, IAMReX image pin, CFL note (CFL≈0.45,
  borderline), arena cap (amrex.the_arena_init_size=28, ~12 GB headroom), dt-reduction fallback
  procedure (dt=2.5e-4 → dt_reduced=true in metadata → assert_gradeable_triple will raise "time-grid",
  operator must pass metadata dt), and `assert_gradeable_triple` pre-commit check command.
- [ ] 6.3 **[Session B]** Flip `⬜ → ✅` with the PR ref once data + RESULTS are committed.
- [ ] 6.4 **[Session B]** Update `benchmarks/METHODS.md` Case 3 — the deferral sentence
  ("a rigorous verdict needs a 3rd 256³ grid, deferred to H100/grant") becomes false once T3c lands.
  Update to: "T3c (PR #N) ran the fine 256×128×256 grid; see RESULTS.md § Grid convergence (T3c) for
  the 3-grid observed order and Richardson estimate. IB coupling caveat applies — see design D1." Also
  update the Method sentence to mention `wing_grid_convergence_from_body_forces(..., fine_csv=fine)`.
- [ ] 6.5 **[Session B]** Add a forward pointer in RESULTS.md T3b prose section (line ~311): after
  the "What two grids cannot settle" paragraph, append: "See Grid convergence (T3c) below for the
  fine-grid (256³) result."

---

## 7. LEV (fine grid) — [Session B: needs-run, requires_plotfile]

- [ ] 7.1 **Add** `test_wing_lev_fine_vs_medium` in `tests/test_wing_lev.py` marked
  `@pytest.mark.requires_plotfile`. Via the `_wing_plt(grid)` helper, map `fine → run_metadata_t3c.json
  ["plotfile_dir"]` under `MOSQUITO_CFD_PLOTFILE_ROOT`. Select the plotfile by `current_time ≈ 0.5`.
  Assert finite/positive `peak_vorticity`/`peak_q`/`q_pos_vol`; assert `dx ≈ (0.03125, …)` for fine.
  Auto-skips in CI; skips gracefully if fine plotfiles are absent. Do NOT assert `Q_fine > Q_medium`.
  If the fine run used `amr.plot_int = -1`, skip with a note in RESULTS.

---

## 8. Commit & PR discipline — [Session B]

- [ ] 8.1 **Commit grouping (Session B, atomic + CI-green each):**
  1. `feat(flapping-wing): commit fine 256³ run data + end-to-end test (T3c)` —
     `examples/flapping_wing/forces_fine.csv` + `examples/flapping_wing/run_metadata_t3c.json` +
     additions to `tests/test_wing_convergence_fine.py` (§1.4 schema/provenance tests AND
     `test_fine_3grid_reports_from_committed_csvs` §4.3 in the SAME commit — data and its
     contract test are always co-committed). CI: §1.4 tests flip from SKIPPED → PASS. → green.
  2. `docs(flapping-wing): RESULTS T3c + reproducibility guard + roadmap ✅` — RESULTS §4.4 +
     `tests/test_results_reproducibility.py` §5.1 + roadmap §6.2 ✅. The guard test (§5.1)
     reads literals from RESULTS §4.4 — they MUST land in the same commit so CI does not see
     a failing guard between commits. Enforce as a hard constraint, not a parenthetical. → green.
  Every commit carries `Co-Authored-By: <model implementing Session B> <noreply@anthropic.com>`
  (fill with actual implementing model, not hardcoded as Sonnet 4.6).
- [ ] 8.2 **Auto-close discipline.** PR body: `Closes #50`. Reference open issues keyword-free only.
  No accidental closing keywords for any other issue. Pre-merge checks (all mandatory):
  - NEGATIVE commits (must print nothing): `git log main..HEAD --format='%B' | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]+#[0-9]+'` — review the list; any hit is an accidental closing keyword that will auto-close an unintended issue
  - POSITIVE body (must print `Closes #50`): `gh pr view --json body --jq '.body' | grep 'Closes #50'`
  - POSITIVE title check (must print nothing — no closing keywords in title): `gh pr view --json title --jq '.title' | grep -Ei '(clos|fix|resolv)[a-z]*'`
- [ ] 8.3 **Single PR**, opened after commit 2 (so CI is green before review). The layered commits
  are individually green.

---

## 9. Session A — proposal and deck commit (this session, on approval)

- [x] 9.1 **Commit A-1** `chore(openspec): add wing-fine-grid-convergence (T3c)` — committed: OpenSpec
  change dir + roadmap. SHA: 6aae0b2.
- [x] 9.2 **Commit A-2** `feat(flapping-wing): 3-grid convergence tooling + fine deck (T3c, Session A)`
  — committed: fine deck + wing_convergence.py + all cluster-free tests + t3c-handoff.md.
  SHA: 1ff426d. CI-green: 22 pass, 2 skip, no regressions.
