# Decompose the flapping-wing force into van Veen's per-component model (Tier T4)

## Why

Tier T2a (PR #38) grades our **total** immersed-boundary force `ib_force` against van Veen's
**translational-only** coefficient — apples-to-oranges in the chord direction. The normal matches
(peak `CF_normal ≈ 2.61` vs van Veen `~2.4`), but the chord runs ~3× high (peak `CF_chord ≈ 0.92` vs
van Veen's translational `~0.3`). The T2a `RESULTS.md` states the chord excess is "rotational drag +
tangential added mass" **as if settled, without decomposing it** — the open `#40` PARTIAL.

Two partial answers already landed and are **reused, not redone**:
- **Added-mass interim (PR #45):** subtracting the logged added-mass (`ρ_f·SumU`) drops body-frame
  `CF_chord` `0.923 → 0.652` (added mass is 84 % of the chord RMS) — **isolates** the added-mass share
  but does **not** resolve the PARTIAL (`0.652` is still ~2× `0.3`).
- **Grid convergence (T3b, PR #48/#49):** coarse→medium peak `CF_chord` drops 66.5 % (`0.923 → 0.554`)
  toward `~0.3`, but is **not grid-converged** (GCI 0.28–0.83); the 256³ verdict is deferred (**#50**).
  The **normal is grid-settled** (−11.7 %). So part of the chord excess is grid, part may be the
  decomposition — T4 tests the **decomposition** side.

T4 resolves the PARTIAL by building **van Veen's own quasi-steady force model** — translational +
added-mass + Wagner — from its published coefficients, applying it to **our** measured wing kinematics,
and comparing the **model total** (and components) to our CFD `ib_force` time-resolved. Because both sides
share the same kinematics and `F_ref`, the graded claim is that our CFD wing force is **consistent with /
validated against van Veen's quasi-steady model at matched kinematics** — a plausibility result against the
literature-standard model, **not** an independent validation of the per-component split (the CFD gives only
the total; see design §"What T4 can and cannot claim"). It is **graded** by design, with tolerances
**pinned up front from sourced quantities** (van Veen's fitted-coefficient 95 % CIs ⊕ the measured
coarse↔medium grid spread ⊕ the `S_WE` geometric uncertainty), **not** reverse-fit to pass — and the
**sourcing itself is tested** (CC-V2).

**No new simulations.** Analysis-only, cluster-free — reuses the committed T2a/T3b force CSVs.

### Why van Veen's {translational, added-mass, Wagner} instead of #40's {translational, rotational, added-mass}?

Issue #40's task text says "translational + **rotational** + added-mass" and attributes the chord excess
to "rotational drag (Bomphrey 2017)." Reading the reference paper end-to-end
(van Veen, van Leeuwen, van Oudheusden & Muijres 2022, *J. Fluid Mech.* **936**, A3, DOI
10.1017/jfm.2022.31, CC BY) shows its model (eq 2.7) is

`F_total = F_transl + F_AM + F_WE`  —  translational + added-mass + **Wagner**.

The **"rotational" in the paper's title means rotational _stroke acceleration_** (the `ω̇`-dependent
added-mass and Wagner terms), **not** pitch-rotational lift. Van Veen's model contains **no** Sane–
Dickinson rotational-circulation term and **no** Bomphrey rotational-drag term; the chord/tangential force
in van Veen is translational-viscous + tangential added-mass (Wagner-tangential = 0). Using van Veen's
**actual** three components is therefore *more* faithful to #40's own instruction to "compare each
component to van Veen's corresponding curve," and it is what resolves the apples-to-oranges: our
**total** chord must be compared to `transl + AM + Wagner`, and van Veen's **translational** chord alone
is indeed `~0.3`. Bomphrey's rotational-drag mechanism is retained only as **narrative** context. This
refinement was confirmed with the operator before scoping.

## What Changes

- **New pure model module** `src/mosquito_cfd/benchmarks/van_veen_model.py` implementing van Veen's three
  components as functions of `(α, ω, ω̇)` plus the wing area-moments `S_yy`, `S_cy`, `S_WE`, with the
  fitted coefficients pinned as **named, test-guarded constants** carrying their 95 % CIs (a loosened
  coefficient fails a not-loosened guard, CC-V2). **Both** added-mass components use the chord-based `S_cy`
  (the paper's fitted revised model, not the analytic thickness-based `S_τy`; recorded in a comment).
- **One shared `compute_wing_area_moments`** with a **pinned hinge-origin integration convention** (y from
  the stroke axis, `S_yy = r_gyr²·area ≈ 6.797`), emitting `S_yy`, `S_cy` (= `S_yy`), and the **new**
  `S_WE = ∫√(c³y³)dy`; the existing inline `S_yy = r_gyr²·area` sites are refactored to call it (one moment
  code path, CC-V4). `S_WE` is a fixed geometric constant cross-checked against an independent quadrature —
  not a tunable knob.
- **Stroke-rate kinematics helper** `stroke_rate(time, …)` returning `(ω, ω̇) = (φ̇, φ̈)` as the analytic
  derivatives of the existing `wing_kinematics.euler_angles` stroke `φ(t)` (single-source; the model is
  applied to the *same* kinematics the solver runs).
- **Graded per-component decomposition** `decompose_wing_force(csv_path, …)` in `benchmarks/flapping_wing.py`:
  builds the model per-component + total in the wing body frame, normalizes by the single-source
  `compute_force_reference` (`F_ref = ½ρω_ref²S_yy = 200.27`, the *same* reference as our CFD `CF`),
  aligns to the CFD time grid from `reconstruct_wing_body_forces`, and grades / reports the comparison.
- **Graded oracle (one pinned tolerance, sourced + tested — see `design.md` §D5–D6):**
  - **(G1) Normal peak MAGNITUDE** — the **relative** peak gap `|model−cfd|/cfd` (model ≈2.48 vs CFD ≈2.61,
    i.e. ≈0.05) within `T4_NORMAL_MAG_TOL` (a relative/fractional tolerance, units-consistent with the grid
    GCI — see design §D6). The primary graded lever: `S_WE`-**insensitive** (the `S_WE` uncertainty moves
    the normal peak by only ~0.001 — marker and analytic `S_WE` agree to ~0.1%) and grid-settled.
  - **(G3) Decomposition closure** — `model_total ≡ transl + AM + Wagner` to floating tolerance.
- **Reported (not gated):**
  - **Normal peak PHASE** — the CFD peak **leads** the QS model by ~0.058 cycle: the expected
    quasi-steady-vs-unsteady phase discrepancy (QS omits wake-memory), **triply confounded** by grid
    non-convergence + the single-wingbeat transient. A tight gate would require reverse-fitting the
    confounded gap, so it is **reported with its confounds**, not gated (a one-line reconciliation-log note
    records this scoped, evidence-based decision — not a loosened tolerance).
  - **Normal curve RMSE** — inflated by the phase offset; reported.
  - **(G2) Translational-chord self-consistency** — the model's translational-tangential peak is the
    **known-answer** value from the pinned polynomial at our α (≈ **0.42**), reported as **O(0.4) ≪ the CFD
    total 0.92** — the #40 apples-to-oranges resolution. **Not** graded against `0.30` (that both fails
    numerically — the polynomial gives ~0.42 — and is circular); `VAN_VEEN_CF_TARGETS` is **not** reused as
    a chord gate. Van Veen's reported `~0.3` (a Fig-4b eyeball at his operating point) is noted as the same
    order.
  - **(R1) Chord total curve** (model vs CFD) with the **coarse↔medium grid GCI band** — *not* gated
    because the CFD chord is grid-unconverged (→ #50); reports that the CFD chord **converges toward the
    model** (0.92 coarse → 0.554 medium → model ≈0.43).
  - **(R2)** per-component chord/normal shares.
- **Cluster-free figure** `fig_force_decomposition` replotting van Veen's model components + total vs our
  CFD total (chord & normal) over the steady window, at our operating point, from the committed CSVs.
- **Docs (full de-stale sweep — every stale location, per review):** `RESULTS.md` — replace the CF_chord
  "hypothesis (#40)" / PARTIAL language with the **verified-against-van-Veen's-model** decomposition (normal
  consistent; chord explained + grid-limited, #50); **keep** the T3b "Grid convergence" section and the
  added-mass-subtracted interim intact; **keep** the correct "Fig 4" translational-target cites while
  relabelling the "Fig 3–4" time-resolved cites to Fig 13; add the new figure to the Output Files table.
  `roadmap.md` — flip the T4 row (line 97) to ✅ with the PR ref, update the Sequencing line, **and** correct
  the oracle table (line 74: "Fig 3–4" → Fig 13 **and** "digitized curve" → "van Veen's *model* replotted,
  no digitization"). `docs/coordinate-convention.md` (line 84), the `flapping_wing.py` module docstring +
  the `VAN_VEEN_CF_TARGETS` comment (drop "rotational drag"/"digitized"/"deferred to T4"/"Fig 3–4"), and
  `figures/README.md` (line 32 caveat + a new `fig_force_decomposition` row) are all de-staled. **No new
  oracle-relaxation entry** — T4 is graded by design.
- **Repair two existing tests inverted by the RESULTS.md edit:**
  `test_flapping_wing_validation.py::test_results_doc_delivers_body_frame_and_defers_t4` (T4 no longer
  *deferred*) and `test_results_reproducibility.py::test_interim_framing_is_honest_and_disambiguated` (the
  `| … | PARTIAL |` row assertion) — both hard-assert the pre-T4 doc state and must be updated with the doc.
- **Erratum check:** a task verifies the pinned coefficients against **JFM 956 E1 (2023)** (an erratum
  the search characterises as "publisher-introduced" — most likely the malformed data-availability DOI,
  not the fitted coefficients) before they are trusted.

## Non-goals

- ❌ **No new simulations / no cluster.** T4 reuses the committed `forces_t2a_newconv.csv` (coarse) and
  `forces_medium.csv` (medium 128³). The fine-grid 256³ verdict stays deferred (**#50**).
- ❌ **No tight pass/fail on the chord total curve.** The CFD chord is grid-unconverged (T3b), so the
  chord total-vs-CFD is **reported with the grid GCI band**, not gated — gating it would be reverse-fitting
  to a grid-limited number. The chord's *graded* claim is the translational-chord identity (G2).
- ❌ **No Bomphrey rotational-drag / Sane–Dickinson rotational-circulation model.** Van Veen's model has
  neither; adding one would compare our force to a model van Veen does not use.
- ❌ **No digitization / no external data download.** Van Veen's model is fully specified by text
  coefficients (eqs 3.9–3.15); we replot *its model* at our operating point. Van Veen's own published
  mosquito curves (Fig 13, measured *low-amplitude* Anopheles kinematics ≠ our analytic φ=70° stroke) are
  **not** overlaid — a different-kinematics overlay would not be an apples-to-apples comparison.
- ❌ **No change to the existing graders.** `plausibility_gate` and `body_frame_overall_match` stay
  unchanged; the coarse-run peaks (`CF_chord ≈ 0.92`, `CF_normal ≈ 2.61`) remain reproducible — T4
  **explains** them, it does not restate or re-derive them.

## Impact

- **Specs:** `flapping-wing-validation` — **ADD** the model / area-moments / decomposition-grader /
  erratum-provenance / PARTIAL-resolution requirements; **MODIFY** the four requirements whose text asserts
  "deferred to T4" / "#40 remains open" / the "PARTIAL" verdict (plausibility gate, **body-frame
  per-component comparison**, RESULTS reproducibility, added-mass-subtracted diagnostic) so the spec stays
  consistent after the resolution — restoring their load-bearing guard clauses verbatim, editing only the
  status-changed sentences.
- **Code:** new `benchmarks/van_veen_model.py` (+ `compute_wing_area_moments`, incl. `S_WE`); new functions
  in `benchmarks/flapping_wing.py` (`decompose_wing_force`) and `benchmarks/wing_kinematics.py`
  (`stroke_rate`); refactor the inline `S_yy = r_gyr²·area` sites (`generate_validation_figures.py`,
  `test_force_surrogate_normalization.py`) to call the shared moment function; reuses
  `reconstruct_wing_body_forces` / `body_frame_coefficients` / `added_mass_force` / `compute_force_reference`
  / `euler_angles` / `wing_grid_convergence_from_body_forces` (CC-V4 — no re-derivation).
- **Tests:** new `tests/test_van_veen_model.py` (known-answer + CI-guarded constants + sign-convention +
  `S_WE` independent quadrature + erratum literal) and `tests/test_wing_force_decomposition.py` (grader
  pass/fail on synthetic fixtures both directions + tolerance-sourcing test + exact-key-set + end-to-end on
  the committed coarse CSV); repair the two inverted existing tests; add a roadmap-status guard.
- **Docs / figures:** `RESULTS.md`, `roadmap.md` (lines 74 + 97 + Sequencing), `docs/coordinate-convention.md`,
  the `flapping_wing.py` docstring/comment, `examples/flapping_wing/figures/` (+ regenerated
  `fig_force_decomposition`), `figures/README.md`.
- **Reproducibility:** cluster-free; every headline number recomputes from the committed CSVs; FP64;
  `:fp64 @ f93dc794` pin unchanged; `uv` for all Python.
- **Issues:** resolves **#40** (closes on merge). **#50** (T3c fine-grid, deferred) is referenced
  **keyword-free** as the complementary open line.
