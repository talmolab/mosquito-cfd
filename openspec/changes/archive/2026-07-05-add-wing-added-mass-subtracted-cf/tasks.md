# Tasks — added-mass-subtracted body-frame CF diagnostic (#40 cheap interim)

TDD throughout: each implementation task names the test written **first** and the behavior it verifies
**before** the code exists. `uv` for all Python. New tests live in `tests/test_wing_body_frame.py` (unit /
guards) and `tests/test_results_reproducibility.py` (doc guard); they reuse the existing module-level path
constants (`_NEWCONV_CSV` / `_NEWCONV`) rather than fresh hard-coded paths (cross-platform). Branch:
`add-wing-added-mass-subtracted-cf` (off `main`).

## 1. Diagnostic core (subtract → rotate → report)

- [x] 1.1 **Test first (unit / synthetic — linearity + pure-chord cancel):** in
    `tests/test_wing_body_frame.py`, add `test_added_mass_subtracted_linearity_and_reuse`. On a synthetic
    force + `SumU` array and a known `R(t)`, assert subtract-`added_mass_force(SumU)`-in-lab-then-rotate
    equals rotate-then-subtract (D2 linearity), and that a **pure-chord** added-mass exactly cancels a
    pure-chord `ib` in `CF_chord` (peak_subtracted ≈ 0) while leaving `CF_normal` untouched. Fails: function
    missing.
- [x] 1.2 **Test first (reuse is real, not re-derived — T-3):** add
    `test_subtracted_equals_manual_reuse_pipeline`. On `forces_t2a_newconv.csv`, independently build
    `am = added_mass_force(SumU_xyz)`, rotate `ib` and `am` with the same `R(t)`
    (`euler_angles`→`rotation_matrix`) via `body_frame_coefficients`, form `CF_chord/CF_normal` of
    `(ib − am)`, and assert the diagnostic's `peak_cf_*_subtracted` equal this manual pipeline to `abs=1e-9`
    — so a divergent re-derivation fails (CC-V4). Fails: function missing.
- [x] 1.3 **Implement** `body_frame_added_mass_subtracted(csv_path, *, f_star, phi_amp_deg, pitch_amp_deg,
    deviation_amp_deg=0.0, rho_f=RHO, window_t0=STEADY_WINDOW_T0) -> dict` in
    `src/mosquito_cfd/benchmarks/flapping_wing.py`. Reuse `added_mass_force` (#36), `body_frame_coefficients`,
    and the `wing_kinematics` `R(t)` mirror (CC-V4 — no re-derivation). Define its **own** required-column
    set `time, Fx, Fy, Fz, SumUx, SumUy, SumUz` (no single existing tuple covers all seven —
    `_REQUIRED_CSV_COLUMNS` lacks `Fy` and `SumUy`; `_REQUIRED_BODY_CSV_COLUMNS` lacks the `SumU*` columns;
    `SumUy` is in neither). Compute the peak of each series as the window **argmax of the |series|
    independently** (the subtracted peak is NOT the subtracted value at the total's argmax — on this data the
    chord total/subtracted peaks fall at different phases). Factor the RMS share out as a module-level helper
    `_body_frame_rms_share(added_body_component, ib_body_component)` so the structural guard (2.2) can call it
    directly. Return the reported keys only (`peak_cf_{chord,normal}_{total,subtracted}`,
    `{chord,normal}_drop_frac` with `drop_frac = 1 − peak_subtracted/peak_total`, **signed** — it can be
    negative if subtraction raises a peak, `am_rms_share_{chord,normal}`, `window_t0`) — **no** `*_match`/pass
    field. 1.1 + 1.2 pass.

## 2. Committed-data finding (the headline numbers)

- [x] 2.1 **Test first (committed CSV, pin `pitch_amp_deg=45.0`):** add
    `test_added_mass_subtracted_reproduces_interim` — from `forces_t2a_newconv.csv` (t ≥ 0.05, ρ_f = 1.0)
    assert `peak_cf_chord_total ≈ 0.923 → peak_cf_chord_subtracted ≈ 0.652` (`chord_drop_frac ≈ 0.29`) and
    `peak_cf_normal_total ≈ 2.606 → peak_cf_normal_subtracted ≈ 2.285` (`normal_drop_frac ≈ 0.12`)
    (abs=0.02 / 0.01). **Also (T-4, exact identity):** evaluate the RHS
    `body_frame_overall_match(reconstruct_wing_body_forces(_NEWCONV_CSV, f_star=1.0, phi_amp_deg=70.0,
    pitch_amp_deg=45.0))["peak_cf_chord"]`/`["peak_cf_normal"]` at the **same** kinematics and the diagnostic's
    default `window_t0=STEADY_WINDOW_T0`, and assert `peak_cf_chord_total`/`peak_cf_normal_total` equal them
    to **`abs=1e-9`** (both traverse the identical `body_frame_coefficients` path, so this is a bit-identity —
    `1e-9`, not `5e-4`, so a subtle mask/window mismatch cannot slip under tolerance). This is the "same peaks"
    cross-check underwriting the dual-precision doc note. Passes once 1.3.
- [x] 2.2 **Test first (RMS shares + definition guard — T-5):** add `test_added_mass_body_frame_rms_shares`
    asserting `am_rms_share_chord ≈ 0.84` and `am_rms_share_normal ≈ 0.13` (abs=0.02); **and** a structural
    guard calling the `_body_frame_rms_share(added_body, ib_body)` helper (1.3) directly on synthetic 1-D
    arrays — `added = k*ib` yields `share == k` (abs=1e-9) and is **not** equal to `rms(ib − added)/rms(ib)`
    for that case — pinning the D3 definition (added/ib RMS, not subtracted-ratio, not peak-ratio). (The
    other candidates give chord 60 %/normal 88 % (subtracted-ratio) and chord 99.8 %/normal 12.9 %
    (peak-ratio); only the helper's added/ib RMS gives 84 %/13 %.) Passes once 1.3.

## 3. Reported-only invariant (no new gate — CC-V2)

- [x] 3.1 **Test first:** add `test_diagnostic_is_reported_not_graded` asserting (a) `set(out)` equals the
    exact reported key set (T-7 — catches any later-added key), and in particular contains **no** verdict
    key (`match`, `cf_chord_match`, `cf_normal_match`, `pass`, `floor_pass`, `in_band`); and (b)
    `plausibility_gate` + `body_frame_overall_match(..., targets=VAN_VEEN_CF_TARGETS)` on the committed CSV
    return their **unchanged** T2a verdicts (floor pass; `cf_normal_match=True`, `cf_chord_match=False`,
    `match=False`) — the diagnostic cannot re-grade van Veen. (Complements
    `test_match_constants_are_not_loosened`.) Passes once 1.3.

## 4. Robustness guards (mirror existing decomposition)

- [x] 4.1 **Test first:** add `test_added_mass_subtracted_guards` — parametrized over dropping **each** of
    `Fy`, `SumUx`, `SumUy`, `SumUz` individually (each raises `ValueError` matching `missing required
    column`; `SumUy` is covered by no existing tuple and `SumUx/SumUz` only by the lab one, so the own-set is
    load-bearing), a non-finite `Fx`/`SumU` row raises (`non-finite`), and a `window_t0` past all timesteps
    raises (`selects no timesteps`). Build
    malformed CSVs from `forces_t2a_newconv.csv` via `tmp_path` (mirrors
    `test_missing_csv_column_raises_descriptive_error`). Drives the guard branches + the new required-column
    set in 1.3.
- [x] 4.2 **Test first (`window_t0` + `rho_f` plumbing — T-6 / T-8):** add
    `test_window_t0_and_rho_f_plumbing` — the returned `window_t0` echoes the argument and a non-default
    `window_t0` changes the selected peaks; `rho_f=0` yields `peak_*_subtracted == peak_*_total` and
    `am_rms_share_* == 0` (no added mass to subtract) — confirming `rho_f` flows to `added_mass_force`.
    Passes once 1.3.
- [x] 4.3 **Test first (peak-migration + signed drop_frac — physics edge cases):** add
    `test_peak_migration_and_signed_drop` — (a) on `forces_t2a_newconv.csv`, assert the chord total-peak and
    subtracted-peak occur at **different timesteps** (`argmax|CF_chord_total| != argmax|CF_chord_subtracted|`)
    and that `peak_cf_chord_subtracted` is the independent window-max (≈0.652), NOT the subtracted value at
    the total's argmax (≈0.489) — pinning the "peaks may migrate" semantics; (b) on a synthetic case where
    subtraction **raises** a component's window-peak, assert `drop_frac` is **negative** (it is
    `1 − sub/total`, signed — the docs/return must not call it unsigned). Passes once 1.3.

## 5. RESULTS.md interim finding (guarded before the edit)

- [x] 5.1 **Test first (doc numbers guard):** in `tests/test_results_reproducibility.py`, add
    `test_added_mass_subtracted_interim_recomputes` that (a) recomputes total→subtracted peaks, % drops, and
    the 84 %/13 % RMS shares from `forces_t2a_newconv.csv` via `body_frame_added_mass_subtracted`;
    (b) asserts the interim literals (`0.923`, `0.652`, `2.606`, `2.285`, and load-bearing share phrases
    `chord 84` / `normal 13`) are present in `RESULTS.md`, with the interim subsection's distinct numbers
    **asserted-complete via a set-equality scan** of that subsection (a new interim number absent from the
    enumeration fails); and (c) asserts the existing `test_headline_tables_enumeration_complete` still passes
    (the interim subsection did not perturb the two enumerated tables). Fails until 5.3. Runs **before** the
    doc is edited.
- [x] 5.2 **Test first (honest-framing + disambiguation + same-peaks wording — T-1 / D-2 / D-3 / D-5):** add
    `test_interim_framing_is_honest_and_disambiguated` (mirrors `test_results_doc_delivers_body_frame…`)
    asserting the interim subsection of `RESULTS.md` contains — case-insensitively — an `isolat…` phrase, a
    "does not resolve"/"not … resolve" phrase, the `~2×`/`~2x` + `0.3` residual, `T4`, `#40`; the
    **disambiguation** sentence separating body-frame `84`/`13` from lab-frame `stroke 37`/`lift 29`
    (different frame + axis pairing); the **"same peaks"** note tying `0.923`/`2.606` to `0.92`/`2.61`; the
    **metric-type caveat** that the −29 % chord drop is a **peak-to-peak ratio of window maxima at different
    phases** (not per-instant, distinct from the 84 % RMS share); and that the **Validation-Status row still
    reads `PARTIAL` and references `#40`**. Fails until 5.3.
- [x] 5.3 **Edit `examples/flapping_wing/RESULTS.md`:** add subsection *"Added-mass-subtracted body-frame
    diagnostic (#40 cheap interim)"* (a **distinct `### ` header** — not containing `lab-frame magnitudes` or
    `Body-frame per-component van Veen comparison`; do **not** alter cells in those two tables) under the
    added-mass decomposition — the total→subtracted table (`0.923→0.652`, `2.606→2.285`), the RMS shares
    (chord 84 % / normal 13 %), the **honest framing** (D5: isolates the added-mass share, does **not**
    resolve the PARTIAL; `0.652` still ~2× van Veen's 0.3; residual → T4; #40 open), the **disambiguation**
    sentence (body-frame shares vs lab-frame `added_mass_fraction` — different frame + axis pairing, neither
    supersedes the other), the **"same peaks"** note (totals `0.923`/`2.606` are the body-frame table's
    `0.92`/`2.61` shown to an extra significant figure), and the **metric-type caveat** (the −29 % is a
    peak-to-peak ratio of window maxima falling at **different phases** — the chord total peak near a stroke
    reversal, the subtracted peak mid-stroke — not a per-instant subtraction, and a different metric from the
    84 % RMS energy share). Put every interim **number** ONLY in this new guarded subsection; the two
    enumerated tables (`### lab-frame magnitudes`, `### Body-frame per-component`) get a **bare
    cross-reference** in prose (no decimal cell) so `test_headline_tables_enumeration_complete` stays green
    (adding a number to those tables would break it — the B1 invariant wins over a number copy). The
    unguarded `## Comparison with van Veen` table likewise gets a bare cross-reference; the Validation-Status
    row keeps its `| Body-frame van Veen comparison | PARTIAL |` prefix and references `#40` (a no-number
    pointer to the interim only). 5.1 + 5.2 now pass.

    > **Why cross-references, not table numbers (implementation correction):** the round-1/2 B1 invariant
    > requires the interim subsection not to alter the two enumeration-guarded tables. Adding `0.652`/`2.285`
    > into the `### Body-frame per-component` table would fail `test_headline_tables_enumeration_complete`
    > (exact set-equality) and the new guard's clause (d). So interim numbers live only in the guarded
    > interim subsection; the other tables reference it without a number.

## 6. Traceability

- [x] 6.1 **Edit `docs/aerodynamics_validation/roadmap.md`** (T4 / #40 row): one-line note that the cheap
    interim is **delivered** (cluster-free) — `CF_chord 0.923→0.652`, added mass 84 % of the chord RMS,
    **isolates the added-mass share, does not resolve the PARTIAL** — while the full curve-match +
    per-component decomposition remain. Do not restructure the tier or use a `#40`-closing phrase.
- [x] 6.2 **Check off #40's *cheap-interim* checkbox** with the finding (via `gh issue edit`), at PR time.
    **Do NOT close #40** — full T4 remains. Verify the edit preserves the other checklist items.
    **DONE** post-merge: #40's first checkbox ticked + finding table posted as a comment; other checklist
    items preserved; #40 confirmed OPEN.

## 7. Verification

- [x] 7.1 `uv run ruff check .` and `uv run ruff format --check .` clean (run `ruff format` before **each**
    commit that touches `src/`/`tests/`, not only at the end — CI checks formatting per push).
- [x] 7.2 `uv run pytest` — full suite green (new + existing; the existing reproducibility / not-loosened /
    enumeration guards still pass).
- [x] 7.3 `"/c/Users/Elizabeth/AppData/Roaming/npm/openspec" validate add-wing-added-mass-subtracted-cf
    --strict` passes.

## 8. Commit & PR discipline (CI green at every pushed commit)

- [x] 8.1 **Commit grouping** (3 atomic commits, each CI-green):
    - `chore(openspec): add-wing-added-mass-subtracted-cf proposal (#40 cheap interim)` — the change dir only.
    - `feat(flapping-wing): added-mass-subtracted body-frame CF diagnostic (reported-only; advances #40)` —
      `src/…/flapping_wing.py` + all §1–4 tests (1.1–1.3, 2.x, 3.1, 4.1–4.3) together in
      `tests/test_wing_body_frame.py` (the committed-CSV tests import the new function, so they may not
      precede it).
    - `docs(flapping-wing): RESULTS.md added-mass-subtracted interim + reproducibility guard (advances #40)`
      — the §5 doc-guard tests (5.1/5.2 in `tests/test_results_reproducibility.py`) **and** the RESULTS.md
      edit (5.3) **and** the roadmap note (6.1) in **one** commit (5.1/5.2 are red until 5.3 lands the
      literals — G-2).
- [x] 8.2 **#40 must NOT auto-close (G-1):** no commit message, PR title, or PR body may place a closing
    keyword (`close`/`closes`/`closed`/`fix`/`fixes`/`fixed`/`resolve`/`resolves`/`resolved`) adjacent to
    `#40` — **avoid even the `resolve #40` bigram in a negated sentence** (GitHub's parser matches the
    bigram and ignores the negation). PR title e.g. `T4: added-mass-subtracted body-frame CF (cheap interim,
    advances #40) (#<PR>)`. Each commit carries the `Co-Authored-By` trailer.
    > ⚠ **OUTCOME — the guard FAILED once and was remediated.** The PR body used the phrasing *"does not
    > resolve #40"* (which this task's own earlier example unfortunately suggested), and the merge
    > **auto-closed #40** anyway — GitHub keyed on the `resolve #40` bigram and ignored the "does not". #40
    > was immediately **reopened**, the checkbox ticked, and the PR body corrected. **Lesson:** never place
    > a closing keyword next to `#40` even in a negated clause; phrase it with **no** keyword adjacent, e.g.
    > *"#40 stays open — full T4 (per-component decomposition + Fig 3–4 curve match) remains."*
