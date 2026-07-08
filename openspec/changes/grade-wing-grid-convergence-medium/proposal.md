# Grade the medium-grid flapping-wing convergence + wire LEV (T3b, operator-run)

## Why

Tier **T3a** (PR [#47](https://github.com/talmolab/mosquito-cfd/pull/47), OpenSpec change
`add-wing-grid-convergence`) delivered the **report-only** grid-convergence tooling and the medium-grid
deck, all TDD'd cluster-free against the committed coarse run + synthetic fixtures. It ships a **forward
contract** ([`openspec/specs/flapping-wing-grid-convergence/spec.md`](../../specs/flapping-wing-grid-convergence/spec.md),
requirement *"Medium-run provenance and reproducibility (forward contract for T3b)"*) on the future
operator run, and explicitly **defers** the yt plotfile→velocity-field extraction and the actual "LEV
present at medium, weak/absent at coarse" call to T3b (LEV requirement, "no committed new-convention
plotfile exists in-repo").

**Tier T3b** ([#46](https://github.com/talmolab/mosquito-cfd/issues/46)) is that operator-run graded
follow-up. It runs the medium 128×64×128 sim on the A40 (an hours-long, operator-run job that cannot be
executed here — exactly why T3 split T3a/T3b, mirroring T2a/T2b), commits the run data + provenance,
**applies** the already-merged grader + LEV to the real coarse↔medium data, wires the plotfile→field
extraction the LEV call needs, writes the RESULTS convergence section with a reproducibility guard, and
closes the T3 EPIC. It is grounded in [`docs/aerodynamics_validation/t3b-handoff.md`](../../../docs/aerodynamics_validation/t3b-handoff.md).

This tier tests the **coarse-grid diffused-IB** hypothesis for the `CF_chord` PARTIAL (coarse peak
`CF_chord = 0.923` vs van Veen's ~0.3, tracked in [#40](https://github.com/talmolab/mosquito-cfd/issues/40)):
a drop under refinement supports the coarse-grid-diffused-IB explanation; **no movement** says the excess
is model/physical (rotational drag + tangential added mass), not grid. **Both readings are informative for
#40** — this is why the tier is report-only and "not converged at coarse" is a valid outcome.

**Session note (operator-run gate).** The medium run is **not yet done** (no committed `forces_medium.csv`,
no medium plotfile on Z:), so this session delivers the **reviewed + approved proposal** and commits only
the OpenSpec change dir; `/openspec:apply` runs in a **later session** once the run lands (tasks are tagged
Session A / Session B accordingly — see `tasks.md`). The operator A40 run is kicked off per the handoff. The
new-convention **coarse** plotfiles already exist on Z: (`t2a-newconv4/plt00000..plt02000`), so the coarse
side of the LEV comparison is available now.

## What Changes

- **Commit the medium run data + provenance.** Add `examples/flapping_wing/forces_medium.csv` (the 29-column
  IB-particle write-out, identical schema to the committed coarse `forces_t2a_newconv.csv`) and
  `examples/flapping_wing/run_metadata_t3b.json` captured via the existing
  `mosquito_cfd.benchmarks.metadata.capture_run_metadata` — Docker image **digest**, IAMReX commit
  **`f93dc794`**, **inputs-hash of `inputs.3d.convergence_medium`**, git SHA, hardware, timing, plus **named
  `extra` fields** `fixed_dt`/`max_step`/`dt_reduced` (so a stability dt reduction is a machine-readable
  field the grading guard can enforce on, not prose) — the same helper and `:fp64 @ f93dc794` pin T2a used
  for `run_metadata_t2a.json`. The 29-column schema **and physical plausibility** (`max(time) ≈ 1.0`,
  row-count) are pinned by a test (like `test_wing_body_frame.py::test_newconv_csv_matches_ib_particle_contract`),
  and a second test pins `inputs.hash == sha256(inputs.3d.convergence_medium)`, so a silent column drift or a
  truncated/wrong-deck run fails closed.
- **Grade convergence (report-only) by _applying_ the merged grader.** Call
  `wing_grid_convergence_from_body_forces(forces_t2a_newconv.csv, forces_medium.csv, f_star=1.0,
  phi_amp_deg=70.0, pitch_amp_deg=45.0)` → per-component `relative_change` + `gci_p1`/`gci_p2` for peak
  `CF_chord`/`CF_normal`. **Before grading**, a new `assert_gradeable_pair` helper guards that both CSVs are
  **non-empty**, reach `max(time) ≈ 1.0`, **and share the same time grid** (matching **unique-`iStep`** sets +
  sample times — deduplicated, since the coarse CSV carries 3 `init_iter=2` duplicate `t=0` rows) — the
  endpoint alone is insufficient because a run-time `dt` reduction (with `max_step` raised)
  reaches `t = 1.0` on a *finer* time grid, silently injecting a temporal-resolution difference into the
  spatial delta; the same-time-grid check (and a `dt_coarse == dt_medium` check reading `ns.fixed_dt` from
  the hash-pinned decks — the coarse metadata has none) makes that fail loudly. `gci_p1` is the reported band
  edge, **not** a rigorous upper bound; `r = 2`
  is fixed by the 2×2×2 deck pair. No grader code changes — T3a delivered and TDD'd the math; only the guard
  is new.
- **Wire the LEV plotfile→field extraction (the piece T3a deferred) by _reusing_ `extract_eulerian_box`.**
  The existing `mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` reads the level-0 covering grid
  of an AMReX plotfile into FP64 `u, v, w` arrays indexed `[ix, iy, iz]` plus per-axis `dx` — **exactly** the
  input `lev.vorticity_magnitude` / `lev.q_criterion` expect (spacing accepts the `dx` triple). **Verified**
  that new-convention wing plotfiles carry all six required `('boxlib', …)` fields (`x/y/z_velocity`,
  `gradpx/gradpy/gradpz`), are single-level (`max_level == 0`), FP64, with non-zero velocity (`init_iter = 2`
  persists the induced field). A thin composition `wing_lev_report(plotfile_path, *, lo, hi)` extracts the
  field over a **required near-field sub-box derived from the plotfile's wing-marker bbox + margin**
  (a domain-wide reduction is forbidden — dominated by far-field noise + the grid-tied IB marker shell; a
  hard literal is forbidden too — it clips the mid-stroke wing, tip at `y ≈ 3.475`), and **reports** a
  resolution-fair primary descriptor — integrated positive `Q` over the box (`q_pos_vol = Σ max(Q,0)·dx·dy·dz`)
  + positive-`Q` volume fraction — alongside peak `‖ω‖` / peak `Q` *with an explicit resolution caveat that
  applies to `q_pos_vol` too* (both grow under refinement for the same vortex, so a coarse→medium increase is
  a **lower bound on LEV growth, not proof of present-vs-absent**; `peak_q`/`peak_vorticity` also stay
  IB-shell-contaminated, phase-amplified at mid-stroke → a downstream-offset box is also reported). The
  analysis is at **mid-stroke `t ≈ 0.5` (max stroke velocity — the most LEV-discriminating phase; not the
  `t = 0.25` stroke reversal where the wing is momentarily stopped)**, selected **by physical time** and
  compared at the same phase (`current_time` within `0.5·min(dt_coarse, dt_medium)`). The return dict carries
  **no** verdict key; the "present at medium vs weak/absent at coarse" reading is interpreted in RESULTS prose
  from the reported `q_pos_vol` contrast — never a directional `Q_medium > Q_coarse` gate (design D2). See
  `design.md` D1/D2 for the verified `extract_eulerian_box` reuse facts + the box definition.
- **Test the LEV wiring both ways.** (a) The `wing_lev_report` composition is CI-tested cluster-free via an
  **in-memory** monkeypatched box (critical path — never blocked by the fixture spike), plus a
  `@pytest.mark.requires_plotfile` real coarse ↔ medium comparison at **mid-stroke `t ≈ 0.5`** (auto-skipping
  in CI). (b) A **committed synthetic single-level AMReX/boxlib plotfile fixture** under `tests/fixtures/`
  (the 8 components the real wing plotfiles write; `Cell_D_00000`; a `.gitattributes` binary rule to survive
  `autocrlf`; **sequenced last** with a hard tripwire) exercises the *actual* `extract_eulerian_box` yt-read
  path cluster-free. This committed fixture is exactly issue
  [#33](https://github.com/talmolab/mosquito-cfd/issues/33)'s deliverable — because the CI test exercises the
  real `extract_eulerian_box` yt-read path against the fixture, T3b **closes #33** (the
  "yt read layer not covered in CI" gap). See `design.md` for the fixture-authoring **spike + fallback** (if
  hand-authoring a boxlib plotfile proves too costly, fall back to the PR #30 in-memory monkeypatch pattern,
  keep #33 open, and drop the `Closes #33`).
- **RESULTS convergence section + METHODS case + reproducibility guard.** Add a `### Grid convergence (T3b,
  medium 128³)` subsection to `examples/flapping_wing/RESULTS.md` under `## Aerodynamic Forces` (after the
  added-mass interim, before `### Force at key phases`) reporting per-component `relative_change` + GCI band
  and the LEV finding, with an honest `#40` interpretation that **states #40 remains open regardless of the
  convergence reading** (so a `CF_chord` drop is not misread as resolving the PARTIAL). Add a `### Case 3:
  Flapping-wing grid convergence` subsection to `benchmarks/METHODS.md` `## Benchmark Cases` — the writeup
  T3a **explicitly deferred to T3b** — cross-referencing RESULTS for the numbers (DRY, no restatement; no
  IAMReX pin edit, so the `test_methods_pin_consistent` guard is untouched). Extend
  `tests/test_results_reproducibility.py` (the T2b pattern) to **recompute** `relative_change`,
  `gci_p1`/`gci_p2` from the committed coarse + medium CSVs (via `assert_gradeable_pair` first) and assert
  they match the RESULTS headline literals (`abs ≈ 0.02`), and to pin **both** deck hashes (coarse
  `inputs.3d.validation` vs `run_metadata_t2a.json`; medium vs `run_metadata_t3b.json`). The LEV numbers
  derive from **non-committed plotfiles**, so they are **not** in the CSV-recompute guard — the
  `requires_plotfile` test recomputes them when Z: is present, and the synthetic fixture guards the wiring
  math with a known analytic answer.
- **Roadmap.** Flip the **T3b** row `⬜ → ✅` (add the PR ref) and correct the **stale T3a** row `🟡 → ✅`
  (T3a merged in PR #47 but was left `🟡 in flight` at PR-creation time), and update the Sequencing line so
  both T3a and T3b read complete. No new oracle-relaxation reconciliation entry is needed — the 2026-07-05
  entry already records the graded→reported relaxation; add only a one-line note that T3b landed the graded
  run.

## Non-goals (explicit)

- **No pass/fail, no tolerance, no verdict, no Richardson `cf_exact`.** T3b stays **report-only** (relative
  change + GCI band); "not converged at coarse" is a valid, informative outcome for #40. This carries T3a's
  hard constraint unchanged — the grader/LEV math is not touched.
- **No re-derivation.** Reuse the merged `wing_convergence` / `lev` functions, `reconstruct_wing_body_forces`
  / `body_frame_overall_match` / `compute_force_reference`, **`extract_eulerian_box`**, `capture_run_metadata`,
  the T2b reproducibility-guard pattern, and the existing `requires_plotfile` conftest marker.
- **No solver / Docker / pin change.** Grid refinement needs no solver change; same `:fp64 @ f93dc794`,
  FP64 throughout, `uv` for all Python. The **only** CI additions are the committed synthetic fixture + the
  reproducibility-guard and schema-pin tests.
- **Out of scope:** a fine **256³** grid and the **true observed-order (3-grid) convergence verdict**
  (deferred to H100/grant); the **T4** per-component decomposition / #40 resolution (T4 reuses these runs).

## Impact

- **Specs:** MODIFY `flapping-wing-grid-convergence` — the *LEV* requirement (remove the T3b deferral; add the
  near-field `extract_eulerian_box` wiring, the resolution-fair report-only descriptor, and the
  committed-fixture CI coverage) and the *Medium-run provenance* requirement (forward contract → fulfilled;
  named `dt` fields; same-time-grid + both-deck-hash guards). ADD one requirement to `force-extraction`
  recording that the committed synthetic plotfile gives the yt Eulerian-box adapter cluster-free CI coverage
  (closes #33) — **withdrawn (`git rm`) if the fixture spike falls back** (design D3/D8). No change to the
  deck-invariance or grader-math requirements (T3a delivered those; T3b only applies them).
- **Code:** new `wing_lev_report` composition (thin near-field reduction reusing `extract_eulerian_box` +
  `lev`) and a new `assert_gradeable_pair` pre-grade guard; no new numerical core (the resolution-fair
  `q_pos_vol` is a `np.maximum(Q,0).sum()·dx·dy·dz` reduction over existing `lev` output). Analysis-only,
  `uv`/numpy/yt, no GPU at analysis time, no solver change.
- **Data:** `examples/flapping_wing/forces_medium.csv` + `run_metadata_t3b.json` (committed);
  `tests/fixtures/<synthetic plotfile>` (committed, tiny). Real coarse/medium **plotfiles stay on Z:** (not
  committed; `plt*/` is gitignored).
- **Tests:** 29-col schema + physical-plausibility pin (medium CSV); inputs-hash-pins-medium-deck test;
  `assert_gradeable_pair` unit test (non-empty + same-time-grid + dt guard, its own error substrings); grader
  application report; LEV — the dedicated `#33` adapter-contract CI test on the fixture, the LEV known-answer
  + report-only CI test, the fixture-regenerability test, and the `requires_plotfile` real-data test;
  reproducibility-guard recompute + both-deck-hash pin.
- **Docs:** `examples/flapping_wing/RESULTS.md` (new convergence subsection); `benchmarks/METHODS.md` (new
  Case 3, T3a-deferred); `roadmap.md` (T3a+T3b rows → ✅, Sequencing line, one-line T3b note).
- **Issues:** **Closes #46** (T3 EPIC — both halves now delivered) and **#33** (synthetic-fixture CI
  coverage) **contingent on the fixture spike** — if the spike falls back to the monkeypatch (design D3), the
  `force-extraction` spec delta is `git rm`-ed, `Closes #33` dropped, and `openspec validate --strict`
  re-run. **Advances #40** — #40 **stays open** (T4 reuses these runs); referenced keyword-free with **no**
  closing clause (even negated) adjacent to #40, verified by a boundary-anchored pre-merge grep plus a
  positive `Closes #46` presence check.
