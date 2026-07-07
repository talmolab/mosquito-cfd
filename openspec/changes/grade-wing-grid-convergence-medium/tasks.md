# Tasks — grade the medium-grid flapping-wing convergence + wire LEV (T3b)

TDD throughout: each implementation task names the test written **first** and the behavior it verifies
**before** the code exists. `uv` for all Python. Branch: `add-wing-grid-convergence-t3b` (off `main`).
Report-only — no pass/fail, no tolerance, no verdict key, no Richardson `cf_exact` (carried from T3a,
not weakened). Reuse, no re-derivation. Test paths are repo-root-relative `Path(...)` — never a
hard-coded `Z:\...` or drive letter (plotfiles are reached only via `MOSQUITO_CFD_PLOTFILE_ROOT`).

> **Operator-run gate → two sessions.** This session (**Session A**) delivers the reviewed + approved
> proposal and commits **only** the OpenSpec change dir (§9.1). Everything that needs run data — the
> committed CSVs, the fixture, the real numbers, the tests that read them — lands in a later
> **Session B** (`/openspec:apply`) **after** the operator A40 run per
> [`docs/aerodynamics_validation/t3b-handoff.md`](../../../docs/aerodynamics_validation/t3b-handoff.md).
> Tasks are tagged **[Session B: needs-run]** (needs the committed medium CSV / a plotfile on Z:) or
> **[Session B: cluster-free]** (buildable without run data, but sequenced into Session B so the fixture
> spike outcome is known before `Closes #33`). All §1–§8 tasks are Session B.

## 0. Pre-flight (operator, before committing data) — [Session B: needs-run]

- [x] 0.1 Run the medium sim per the handoff **delta**: deck `inputs.3d.convergence_medium`, same
  `:fp64 @ f93dc794`, same `mpirun … amr3d.gnu.MPI.CUDA.ex`; capture `run_metadata_t3b.json` via
  `capture_run_metadata(inputs_file=inputs.3d.convergence_medium, output_dir=<run>, docker_image=<:fp64
  digest>, timing=…, extra={"iamrex_commit": "f93dc794…", "tier": "T3b", "image_digest": "<sha256>",
  "fixed_dt": 5e-4, "max_step": 2000, "dt_reduced": false, "plotfile_dir": "t3b-medium"})`. If a run-time
  `dt` reduction was needed for stability, set `"fixed_dt"` to the reduced value, `"max_step"` to the raised
  value, and `"dt_reduced": true` — **named fields, not prose** — and reduce dt only to a value that **keeps
  a plotfile landing exactly on `t = 0.5`** on both grids (raise `amr.plot_int` proportionally if needed), so
  the LEV same-phase guard can pair the grids; **not** baked into the deck.
- [x] 0.2 **ENABLE PLOTFILE OUTPUT (run-plan gap — the committed-forces run command forces
  `amr.plot_int=-1`).** The medium deck sets `amr.plot_int = 100`, but the RESULTS "Run Commands" the handoff
  points to end with `amr.plot_int=-1 amr.check_int=-1` (CLI overrides the deck) → **zero plotfiles**. You
  MUST **drop the `amr.plot_int=-1` override** so plotfiles are written, and **confirm the `t ≈ 0.5`
  plotfile exists** (`plt01000` at the held dt, or the plt nearest `current_time ≈ 0.5`) under the medium run
  dir **before tearing down the ~hours-long job** — otherwise the LEV half of T3b has no field. Write the
  medium plotfiles into a dir named per `run_metadata_t3b.json["plotfile_dir"]` (default `t3b-medium`) so the
  `requires_plotfile` LEV test (§3) can find it (coarse side is the existing `t2a-newconv4`).
- [x] 0.3 **Sanity before grading** — confirm `forces_medium.csv` and the committed `forces_t2a_newconv.csv`
  are **non-empty**, both reach `max(time) ≈ stop_time = 1.0`, share the **same time grid** (matching
  **unique-`iStep`** sets + sample times — deduplicated, since the coarse CSV has 3 `init_iter=2` duplicate
  `t=0` rows), and that `forces_medium.csv` is **not byte-identical** to the coarse CSV and came from the
  **medium** run dir (the 29-col schema alone cannot tell coarse from medium). Enforced by the §2 helper.

## 1. Commit medium data + provenance (schema + plausibility + inputs-hash pinned) — [Session B: needs-run]

- [x] 1.1 **Test first (schema pin + physical plausibility):** in `tests/test_wing_body_frame.py` (beside
  `test_newconv_csv_matches_ib_particle_contract`), add `test_medium_csv_matches_ib_particle_contract` —
  assert `list(pd.read_csv(forces_medium.csv).columns)` equals the pinned 29-column `_IB_PARTICLE_29_COLS`
  in exact order; assert `df["time"].max() == pytest.approx(1.0, abs=1e-3)` and `len(df) > 1900` (a
  truncated/diverged run that wrote only a few finite rows must fail here, not silently feed the grader);
  assert `reconstruct_wing_body_forces(forces_medium.csv, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)`
  yields finite `cf_chord`/`cf_normal` of equal length. Fails: file missing.
- [x] 1.2 **Test first (provenance pins the medium deck):** add
  `test_run_metadata_t3b_inputs_hash_matches_medium_deck` — load `run_metadata_t3b.json`, compute
  `sha256(examples/flapping_wing/inputs.3d.convergence_medium)`, assert it equals
  `metadata["inputs"]["hash"]`; assert `metadata["iamrex_commit"].startswith("f93dc794")`,
  `metadata["tier"] == "T3b"`, and `metadata` carries a `docker_image`/`image_digest` + a `fixed_dt` field.
  Fails: file missing.
- [x] 1.3 **Commit** `examples/flapping_wing/forces_medium.csv` + `examples/flapping_wing/run_metadata_t3b.json`
  beside the coarse pair. 1.1 + 1.2 pass.

## 2. Grade convergence (apply the merged grader — report-only) + the pre-grade guard — [Session B: needs-run]

- [x] 2.1 **Test first (the pre-grade guard, unit-level):** in `tests/test_wing_convergence_medium.py`, add
  `test_assert_gradeable_pair_guards` on a new helper `assert_gradeable_pair(coarse_csv, medium_csv)`:
  (a) a header-only CSV → `ValueError(match="no data rows")`; (b) a medium CSV truncated to `max(time)=0.5`
  → `ValueError(match="window")`; (c) a **dt-halved** medium CSV (twice as many unique `iStep` values, same
  endpoint `1.0`) → `ValueError(match="time-grid")` (the dt-reduction silent-failure catch); (d) the
  committed coarse-vs-coarse pair passes **despite the 3 duplicate `t=0` rows** (`init_iter=2` writes
  `iStep=0` thrice — the coarse CSV is 2002 rows, not 2000). The `match=` substrings are exactly
  `"no data rows"`, `"window"`, `"time-grid"` (the step-count-mismatch branch MUST emit `"time-grid"`).
  Fails: helper missing.
- [x] 2.2 **Implement** `assert_gradeable_pair` — compare on the **deduplicated, monotone** time array / the
  **set of unique `iStep` values** (NOT raw equal-row-count + `np.allclose`, which the `init_iter=2`
  triple-zero-row artifact would false-reject): non-empty + `max(time)≈1.0` within a few `dt` + equal
  unique-`iStep` count + matching unique sample times. The authoritative dt-equality check reads
  **`ns.fixed_dt` from the hash-pinned decks** (`inputs.3d.validation` vs `inputs.3d.convergence_medium`) —
  **NOT** from `run_metadata_t2a.json`, which carries **no `fixed_dt` field** (a `KeyError` trap); a run-time
  reduction is cross-checked against `run_metadata_t3b.json["fixed_dt"]` when present. Self-describing errors.
  2.1 passes.
- [x] 2.3 **Test first (real coarse↔medium report):** add `test_medium_convergence_reports_from_committed_csvs`
  — call `assert_gradeable_pair(forces_t2a_newconv.csv, forces_medium.csv)` then
  `wing_grid_convergence_from_body_forces(forces_t2a_newconv.csv, forces_medium.csv, f_star=1.0,
  phi_amp_deg=70.0, pitch_amp_deg=45.0)`. Assert the return is exactly `{"cf_chord": {...}, "cf_normal":
  {...}}`, each sub-dict carrying **only** `{cf_coarse, cf_medium, relative_change, gci_p1, gci_p2, r}` and
  **no** `*_pass`/`*_match`/`converged`/`in_band`/`cf_exact` key; assert `r == 2.0` and `gci_p1 ==
  pytest.approx(3 * gci_p2)` (r=2 is fixed by the 2×2×2 deck pair — both orders load-bearing); assert all
  values finite. Fails: no numbers yet.
- [x] 2.4 **No grader code changes** — T3a delivered + TDD'd the grader math; T3b only **applies** it. 2.3
  passes once the data is committed. **Record** the per-component `relative_change` + `gci_p1`/`gci_p2` for
  peak `CF_chord`/`CF_normal` (the headline numbers §4 and §5 assert; the coarse column is the grader's
  recomputed value, not the `run_metadata_t2a.json` literal).

## 3. LEV wiring — reuse `extract_eulerian_box`; near-field, resolution-fair, report-only

**Structure (round-3 red-team):** the `wing_lev_report` composition + its CI test use an **in-memory
synthetic box** (monkeypatched `extract_eulerian_box`) so they are on the critical path and independent of
the committed boxlib fixture; the committed boxlib fixture (the #33-specific yt-read coverage) is
**sequenced LAST** with a hard tripwire, so a fixture problem never blocks the graded-run / RESULTS EPIC
closers.

- [x] 3.1 **Test first (composition known-answer + report-only, CI cluster-free, in-memory) — [Session B:
  cluster-free]:** in a new `tests/test_wing_lev.py`, add `test_wing_lev_report_reduction` — **monkeypatch
  `extract_eulerian_box`** to return an analytic solid-body-rotation box dict (`(−Ω·y, Ω·x, 0)`, box **≥ 5³**
  so ≥ 3 interior points/axis, per-axis `dx`, a `phase_time`) — no plotfile, no cluster. Assert the interior
  reproduces `‖ω‖ = 2Ω`, `Q = Ω²` AND the **exact** resolution-fair known-answers
  `q_pos_frac == pytest.approx(1.0)`, `q_pos_vol == pytest.approx(Ω²·N_interior·dx·dy·dz, rel=1e-9)` (the
  exact value pins the `·dx·dy·dz` volume Jacobian a bare `> 0` would miss), and the returned dict carries
  **no** `*_pass`/`converged`/`present` verdict key. (Solid-body rotation is linear, so `np.gradient` is
  exact at edges too — interior and full-box coincide.) Fails: composition missing.
- [x] 3.2 **Implement** `wing_lev_report(plotfile_path, *, lo, hi) -> dict` (thin composition in a new
  `src/mosquito_cfd/benchmarks/wing_lev.py`): call `extract_eulerian_box` (reused) over the **required**
  near-field box, then `vorticity_magnitude`/`q_criterion` with the adapter's per-axis `dx`, reduce over the
  box **interior** to `{peak_vorticity, peak_q, q_pos_vol = Σ max(Q,0)·dx·dy·dz, q_pos_frac, dx,
  phase_time = current_time}`. Report-only, no gate, `lo/hi` required (no full-domain default — dominated by
  far-field + IB-marker shell, per design D2). 3.1 passes.
- [x] 3.3 **Test first (real coarse↔medium, resolution-fair, report-only) — [Session B: needs-run]:** add
  `test_wing_lev_medium_vs_coarse` marked `@pytest.mark.requires_plotfile` — via a `_wing_plt(grid)` helper
  mirroring `test_stress_integral._sphere_plt`, map **coarse → `t2a-newconv4`, medium →
  `run_metadata_t3b.json["plotfile_dir"]` (default `t3b-medium`)** under `MOSQUITO_CFD_PLOTFILE_ROOT`, and
  within each dir **select the plotfile by physical `current_time ≈ 0.5`** (mid-stroke, max stroke velocity —
  the most LEV-discriminating phase; **NOT** `t = 0.25` stroke-reversal; do not hard-code the `plt01000`
  name — a dt reduction moves name↔time). Derive the near-field box **from the plotfile's `particle_position_*`
  wing-marker bounding box + a fixed margin (~1 chord in-plane, ~1 in z)** — `wing_lev_report`'s `lo/hi` are
  required and the **exact derived box is recorded in RESULTS** (do NOT hard-code a literal box: the wing
  position is phase-dependent — at mid-stroke the wing lies straight along the full span, tip at `y ≈ 3.475`,
  so a t=0.25-era literal like `hi_y=3.0` would clip the tip; an example is `lo=(2.5,0,3) hi=(5.5,4,5)`).
  **Assert the marker bbox actually fits inside the requested `lo/hi`** (guards every future phase change).
  Assert both `phase_time` agree to within `0.5·min(dt_coarse, dt_medium)` (same-phase guard), both
  `peak_vorticity`/`peak_q`/`q_pos_vol` are **finite and > 0** (a coherent positive-Q LEV core on both grids),
  and `dx` is `(0.125,…)` coarse / `(0.0625,…)` medium. Also report `q_pos_vol` on a **box offset ~1 chord
  downstream** of the wing to isolate the *shed* vorticity from the IB-regularization shell — **required at
  mid-stroke**, where the fast-moving wing makes the shell contamination of `peak_q`/`peak_vorticity`
  strongest. **Do NOT assert `Q_medium > Q_coarse`** — peak Q (and even `q_pos_vol`) grows with resolution
  for the same vortex (design D2). The present/absent contrast is *reported* (a `q_pos_vol` increase is a
  lower bound on LEV growth), interpreted in RESULTS prose, not gated. Auto-skips in CI (no env var); verify
  it reports **SKIPPED** (not ERROR) with the var unset, and (§7.3) actually **runs** on Z: (a subdir-name
  mismatch would silently skip).
- [x] 3.4 **(LAST, de-risked) Committed synthetic boxlib fixture — the #33 yt-read CI coverage — [Session B:
  cluster-free]:** author a deterministic generator `tests/fixtures/make_lev_boxlib_fixture.py` that writes a
  single-level boxlib plotfile (`Header` + `Level_0/{Cell_H, Cell_D_00000}` — **5-digit** FAB filename, per
  the real `Cell_H`) carrying the **eight fields the wing plotfiles actually write**
  (`x_velocity y_velocity z_velocity density tracer gradpx gradpy gradpz`, so it exercises the same
  Header-parse path #33 covers), velocity = analytic solid-body rotation, box **≥ 5³**, **explicit `<f8`**
  byte order + a matching FAB descriptor (do NOT rely on native `tobytes()` order). **Acceptance:** diff the
  generated `Cell_H` against the real `t2a-newconv4/plt01000/Level_0/Cell_H`; `yt.load` gives `max_level == 0`
  and all six required `('boxlib',…)` tuples; `extract_eulerian_box(fixture)["u"].dtype == np.float64`
  (FP64 round-trip, asserted separately). **FIRST commit a `.gitattributes` binary rule**
  (`tests/fixtures/** -text` or `…/Cell_D* binary` + `…/Cell_H binary`) — `core.autocrlf=true` + `* text=auto`
  would otherwise CRLF-corrupt the binary FAB and desync `Cell_H` byte-offsets; verify with
  `git check-attr -a <fixture files>` before `git add`. Then add `test_fixture_is_regenerable` (regenerate
  into `tmp_path`; committed and regenerated load to identical arrays) and
  `test_synthetic_fixture_reads_through_eulerian_box` (in `tests/test_stress_integral.py`, **unmarked** so it
  runs in CI: asserts the adapter returns bare FP64 `[ix,iy,iz]` arrays + per-axis `dx` — the test that
  literally closes #33). **HARD TRIPWIRE:** if the fixture does not `yt.load` with the correct `field_list`
  within the spike time-box, take the D3 monkeypatch fallback immediately — `git rm` the `force-extraction`
  spec delta, drop `Closes #33`, re-run `openspec validate --strict`, record
  `### Why monkeypatch instead of a committed plotfile?`. Because this task is **last** and independent, the
  fallback never blocks §1–§2/§4/§5 (the EPIC closers).

## 4. RESULTS convergence section + METHODS.md case — [Session B: needs-run]

- [x] 4.1 **Add** a `### Grid convergence (T3b, medium 128³)` subsection to
  `examples/flapping_wing/RESULTS.md` under `## Aerodynamic Forces` (after
  `### Added-mass-subtracted body-frame diagnostic (#40 cheap interim)`, before `### Force at key phases`):
  a per-component table (coarse peak, medium peak, `relative_change`, `gci_p1`/`gci_p2` band) for
  `CF_chord`/`CF_normal`, plus the LEV finding stated as **plotfile-derived** (naming the **mid-stroke
  `t ≈ 0.5` / `plt01000`** phase **and the exact near-field box coordinates used**, not CSV-reproducible)
  reporting `q_pos_vol`/`q_pos_frac`. **Resolution caveat on BOTH descriptors:** a larger medium peak `Q`
  *and* a larger medium `q_pos_vol` are partly expected from resolution alone (a marginally-resolved coarse
  core under-estimates `q_pos_vol`), so a coarse→medium increase is a **lower bound on LEV growth, not proof
  of present-vs-absent**; `peak_q`/`peak_vorticity` also remain IB-shell-contaminated (the box trims the
  far-field but cannot fully exclude the regularization shell — and the contamination is **phase-amplified at
  mid-stroke**, where the fast-moving wing drives the strongest shell gradients, which is why the
  **downstream-offset box** (§3.3) is the shell-clean number). Record the **exact marker-derived box
  coordinates** used. Note the deck-hash pins prove the *decks*, not the CSV↔deck link (which rests on the
  schema/plausibility pins). Frame `#40` honestly: a `CF_chord`
  drop supports coarse-grid-diffused-IB, no movement is consistent with model/physical excess *or* offsetting
  spatial-vs-IB effects a 2-grid study can't separate; **state explicitly that #40 remains open regardless of
  the reading**. State `gci_p1` is a reported band edge, not a rigorous bound, and `r = 2` is fixed by the
  deck pair.
- [x] 4.2 **Add** a `### Case 3: Flapping-wing grid convergence` subsection to `benchmarks/METHODS.md`
  `## Benchmark Cases` (mirroring Cases 1–2) — the T3a-deferred writeup: coarse 64×32×64 vs medium
  128×64×128, held `fixed_dt`/`radius`, report-only 2-grid GCI band + LEV, and a **cross-reference** to
  `examples/flapping_wing/RESULTS.md` for the numbers (do NOT restate them — DRY). T3b changes **no** IAMReX
  pin, so the existing `test_methods_pin_consistent` guard is untouched (prose-only addition).
- [x] 4.3 **Update** the RESULTS Validation-Status / Output-Files rows to list `forces_medium.csv` +
  `run_metadata_t3b.json`, keeping the T2a **PARTIAL** verdict language intact — **#40 stays open; T3b is
  report-only** (deliberately *no* `resolve`/`close` keyword adjacent to `#40` anywhere in-repo, so a
  Session-B author cannot copy such a phrase into a commit/PR body — the phrasing that auto-closed the T4
  issue once before; see [[github-negated-closing-keyword-autocloses]]).

## 5. Reproducibility guard (T2b pattern) — [Session B: needs-run]

- [x] 5.1 **Test first (recompute from committed CSVs + pin both deck hashes):** extend
  `tests/test_results_reproducibility.py` with `test_grid_convergence_recomputes_from_committed_csvs` —
  call `assert_gradeable_pair` then recompute `relative_change`/`gci_p1`/`gci_p2` per component from the
  committed coarse + medium CSVs, assert they match the RESULTS §4 headline **literal strings** (present in
  `RESULTS.md`) to `abs ≈ 0.02`; also assert `sha256(inputs.3d.validation) ==
  run_metadata_t2a.json["inputs"]["hash"]` **and** `sha256(inputs.3d.convergence_medium) ==
  run_metadata_t3b.json["inputs"]["hash"]` (both decks of the graded pair pinned). Do **not** recompute LEV
  numbers (plotfile-derived, not committed). Fails until RESULTS carries the numbers.
- [x] 5.2 Respect the T2b enumeration/magnitude-set guard style — every new headline number in the
  convergence table is recomputed-from-data (or explicitly a reference), so a non-reproducible edit fails
  closed. 5.1 passes.

## 6. Roadmap traceability — [Session B: cluster-free]

- [x] 6.1 **Edit `docs/aerodynamics_validation/roadmap.md` (all four loci in one commit):** flip the **T3b**
  row `⬜ → ✅` (add the T3b PR ref); correct the **stale T3a** row `🟡 → ✅` (T3a merged in PR #47 but was
  left `🟡` at PR-creation time — a status-correction, called out as such); update the **Sequencing** line
  (~99–100) so both T3a and T3b read complete (not "T3a in flight, T3b follows"); add a **one-line** note
  that T3b landed the graded run + RESULTS convergence section. **No** new oracle-relaxation entry (the
  2026-07-05 entry already records graded→reported).

## 7. Verification — [Session B]

- [x] 7.1 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [x] 7.2 `uv run pytest` — full suite green. The `requires_plotfile` LEV test (§3.3) **auto-skips**
  off-cluster; verify with `uv run pytest tests/test_wing_lev.py -v` that it reports **SKIPPED** (not
  ERROR/PASSED) with `MOSQUITO_CFD_PLOTFILE_ROOT` unset. The in-memory composition test (§3.1), the
  fixture/#33 tests (§3.4), and the reproducibility guard (§5.1) run everywhere.
- [x] 7.3 Run once **on the Z: drive** with `MOSQUITO_CFD_PLOTFILE_ROOT` set so §3.3 actually **executes**
  (reports PASS, not SKIPPED) against the real coarse (`t2a-newconv4`) + medium (`t3b-medium`) plotfiles — a
  subdir-name mismatch would silently skip, leaving the LEV real-data path unexercised.
- [x] 7.4 `openspec validate grade-wing-grid-convergence-medium --strict` passes (re-run after any
  fixture-fallback `git rm` of the `force-extraction` delta).

## 8. Commit & PR discipline — [Session B: cluster-free]

- [x] 8.1 **Commit grouping (Session B, atomic + CI-green each; fixture LAST so it never blocks the EPIC
  closers — round-3 red-team):**
  1. `feat(flapping-wing)` — the `wing_lev.py` composition + its **in-memory** cluster-free test (§3.1, §3.2:
     `wing_lev.py`, `test_wing_lev_report_reduction`). No data, no fixture → green everywhere.
  2. `feat(flapping-wing)` — commit `forces_medium.csv` + `run_metadata_t3b.json` **together with** every
     test that reads them (§1.1, §1.2, §2.1–2.4, §3.3 real LEV test). **Invariant:** the CSV and each test
     that reads it land in the *same* commit; no test that reads `forces_medium.csv` precedes the file. §3.3
     (`requires_plotfile`) auto-skips in CI so it never red-lines. → green.
  3. `docs(flapping-wing)` — RESULTS §4 + METHODS §4.2 + roadmap §6 **and** the reproducibility guard §5
     that reads them, **in the same commit**. **Invariant (T3b-specific doc-guard trap):** the guard test
     asserts the RESULTS literals are present, so RESULTS numbers and the guard MUST co-commit — unlike T3a
     (which had no doc-guard test), splitting them red-lines CI. → green.
  4. `test(fixtures)` **(LAST, conditional — closes #33)** — the `.gitattributes` binary rule (first),
     synthetic boxlib fixture + generator + the cluster-free CI tests (§3.4: `test_fixture_is_regenerable`,
     `test_synthetic_fixture_reads_through_eulerian_box`). Independent of 1–3; **omitted entirely if the §3.4
     tripwire fires** (then #33 stays open). → green.
  `ruff format` before each `src/`/`tests/` commit. **Every commit carries `Co-Authored-By: Claude Opus 4.8
  (1M context) <noreply@anthropic.com>`.** (Session A already committed the OpenSpec change dir, §9.1.)
- [x] 8.2 **Auto-close discipline — negative AND positive checks.** The PR body carries `Closes #46` (T3
  EPIC, both halves done) and `Closes #33` (**only if** the §3.4 fixture landed — write that clause only
  after the tripwire verdict is known; if the PR is opened earlier, omit and add on success). Reference `#40`
  **keyword-free** ("advances #40") with **no** closing keyword adjacent to `#40` **even in a negated
  clause** ([[github-negated-closing-keyword-autocloses]]). **Pre-merge grep** over the PR title+body AND
  every commit:
  - NEGATIVE (must print nothing; boundary-anchored so `#400` doesn't false-hit):
    `git log main..HEAD --format='%B' | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]+#?40([^0-9]|$)'`
  - POSITIVE (must match): the PR body closes `#46` (`grep -Eiq 'clos[a-z]*:?[[:space:]]+#?46'`) — else the
    EPIC silently stays open on merge. Confirm `closes #46` / `closes #33` are the **only** closing
    directives.
- [x] 8.3 **Rollback:** the Session-B commits are effect-layered but the docs commit's guard reads the data
  commit's CSV, so **revert the `docs` commit (3) before the `feat` data commit (2)** — a naive
  `git revert <feat>` alone leaves the guard red (it reads the now-removed CSV). Reverting `docs` backs out
  RESULTS/METHODS/roadmap/guard without touching data; the composition commit (1) and the fixture commit (4)
  are independent.
- [x] 8.4 **PR strategy:** single PR, opened in Session B **after** commit 3 (so it is never left
  red/incomplete). The layered commits are individually green and reviewable openspec→fixtures→data→docs.

## 9. Session A (this session) — proposal only — [done on approval]

- [x] 9.1 `chore(openspec)` — commit the entire change dir (`proposal.md`, `design.md`, `tasks.md`, both
  `specs/**/spec.md`), docs-only, CI-green (no code imports it). Suppress the repo's default `(closes #N)`
  PR-title convention for `#40`. *(Committed on approval; the data/fixture/docs work is Session B.)*
