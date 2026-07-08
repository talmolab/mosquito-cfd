# Design — grade-wing-grid-convergence-medium (T3b)

T3b is an **application + wiring** change: the numerical core (grader GCI math, LEV vorticity/Q,
body-frame decomposition, force reference, the yt Eulerian-box adapter, `capture_run_metadata`) all
exist and are tested. The design decisions are about *reuse boundaries*, the one genuinely-open
question (the LEV plotfile→field wiring + its CI coverage), the silent-failure guards, and the honest
interpretation framing. Sections D1–D8 incorporate the `/review-openspec` findings (5 reviewers).

## D1 — Reuse `extract_eulerian_box` for the LEV plotfile→(u,v,w) wiring (no new reader)

**Decision.** The LEV wiring reuses the existing
`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box`, not a new velocity-only reader.

**Why.** Empirically verified against a real new-convention coarse plotfile
(`Z:/…/t2a-newconv4/plt00500`, `t = 0.25`):

- `ds.index.max_level == 0` (single level) ✓ — `extract_eulerian_box` asserts this.
- `field_list` contains all six required tuples `('boxlib', {x,y,z}_velocity)` **and**
  `('boxlib', gradp{x,y,z})` ✓ — the wing solver writes `gradp` just like the sphere runs, so the
  adapter's `_REQUIRED_FIELDS` assertion passes.
- `x_velocity` is FP64, shape `(64, 32, 64)`, `min/max ≈ (−10.1, +3.4)` — **non-zero** (the
  new-convention deck's `ns.init_iter = 2` persists the induced field).

`extract_eulerian_box` returns `{u, v, w, gradp*, x, y, z, dx}` with `u,v,w` indexed `[ix, iy, iz]` over
`(x, y, z)` and `dx` a per-axis triple — **exactly** the convention `lev.vorticity_magnitude` /
`q_criterion` document (`[i, j, k]` over `(x, y, z)`, `spacing` = scalar or `(dx, dy, dz)`). So the wiring
is a **direct compose**, honoring the "reuse, no re-derivation" constraint. It also accepts `lo/hi` — the
near-field sub-box D2 requires.

## D2 — The LEV report: mid-stroke phase, a **wing near-field sub-box**, a **resolution-fair** descriptor (not a domain-wide peak, not a directional gate)

Three round-1 findings (sci B2/B3, TDD B1) plus three round-2 findings (sci: phase, box coords, shell
contamination) converge here and **fix the metric design**:

1. **Phase — mid-stroke `t ≈ 0.5` (`plt01000`), selected by physical time, not by name.** The earlier
   choice `t = 0.25` (`plt00500`, only because the existing `fig_velocity` used it) is **stroke reversal**:
   `φ = +70°` max, `φ̇ = 0`, the wing is momentarily **stopped** — the *least* LEV-discriminating phase (the
   attached LEV is unfed; the diagnostic sees a *shed/decaying* vortex, and RESULTS already shows near-zero
   lift there). The analysis therefore uses **mid-stroke `t ≈ 0.5` (max stroke velocity `φ̇`, `plt01000`)**,
   where the LEV is strongest and most present-vs-absent-sensitive. The operator selects the plotfile **by
   physical time** (`ds.current_time ≈ 0.5`), **not** the `plt01000` name — under a run-time `dt` reduction
   with `amr.plot_int = 100`, `plt01000` is a *different* physical time.

2. **Region — near-field sub-box, `lo/hi` REQUIRED, DERIVED from the wing markers (no hard-pinned literal).**
   `extract_eulerian_box` reads the *full* level-0 covering grid; a domain-wide reduction is dominated by
   far-field noise and the immersed-boundary marker shell, so `wing_lev_report(plotfile_path, *, lo, hi)`
   takes a **required** physical near-field box and reduces over its **interior** (`[1:-1,1:-1,1:-1]`). The
   box is **derived from the wing-marker bounding box** (the plotfile's `particle_position_{x,y,z}` fields) at
   the selected `t ≈ 0.5` plotfile **+ a fixed physical margin** (~1 chord in-plane, ~1 in `z`), and the exact
   box is **recorded verbatim in RESULTS**. A hard-pinned literal is **rejected** (round-3 kinematics BLOCKING):
   a literal computed for one phase silently desyncs at another — e.g. a `t = 0.25` box `hi_y = 3.0` **clips
   the mid-stroke wing** (at `t = 0.5` the wing lies straight along the full span, tip at `y ≈ 3.475`; a
   t=0.25-era box excludes ~11% of the span). Deriving from the markers is self-correcting under any phase or
   dt change the design anticipates. An **illustrative** mid-stroke box is `lo = (2.5, 0.0, 3.0)`,
   `hi = (5.5, 4.0, 5.0)` (contains the full mid-stroke wing + near wake; ≥ 14 coarse / ≥ 30 medium interior
   cells/axis) — documented as an *example*, not asserted. A **fixed** box (identical on coarse and medium at
   the same phase) is correct — both grids have the same physical wing at the same phase. The
   `requires_plotfile` test SHALL **assert the marker bbox actually fits inside the requested `lo/hi`** (this
   guard would have caught the t=0.25→0.5 clip automatically). (The earlier "full-domain default acceptable"
   idea is **withdrawn**.)

   **Honest scope of the box (round-2 sci B2, round-3 sci).** The box **trims the far-field** so the reduction
   is *wing-region-defined and reproducible* — but it does **not** fully exclude the IB-regularization shell
   (support ≈ few·`h`), co-located with the wing. So `peak_q`/`peak_vorticity` remain **shell-contaminated**
   (secondary, caveated) and even `q_pos_vol` is not fully shell-free — and the contamination is
   **phase-amplified at mid-stroke** (the fastest wing drives the strongest shell gradients exactly at the
   chosen `t = 0.5`, the cost of moving there for a strong LEV). Therefore also reporting `q_pos_vol` on a box
   **offset ~1 chord downstream** of the wing to isolate the *shed* vorticity from the shell (the t1a-findings
   CV trick of placing the region outside the regularization support) is **required at mid-stroke, not
   optional** — it is the only shell-clean number.

3. **Metric — a resolution-fair primary descriptor (verified).** Pointwise peak `Q ~ (U/Δx)²` **grows under
   refinement for the same physical vortex** (round-2 sci measured +49% resolved / +640% marginal core), so
   `Q_medium > Q_coarse` is expected from resolution alone and is *not* evidence a coarse LEV is absent. The
   primary reported descriptor is the **integrated positive Q over the near-field box**,
   `q_pos_vol = Σ max(Q, 0)·(dx·dy·dz)`, plus the **positive-Q volume fraction** `q_pos_frac` — integrals of
   the resolved field over a fixed physical box, Richardson-convergent and (round-2 sci measured) ~an order
   of magnitude fairer than peak Q, and strictly better than enstrophy `∫‖ω‖²` (which is *more* resolution-
   sensitive and formally divergent for a line vortex). Signed circulation `Γ = ∫ω·dA` is fairer still
   (grid-invariant) but needs the signed vorticity component `lev` does not expose — that is **forbidden new
   derivation**, so `q_pos_vol` is the correct pragmatic choice. **Caveat extends to `q_pos_vol` too**
   (round-2 sci IMPORTANT): it is *not* resolution-invariant — a marginally-resolved coarse core
   under-estimates it (measured +73% coarse→medium), so a coarse→medium `q_pos_vol` **increase is a lower
   bound on LEV growth, not proof of present-vs-absent**. RESULTS states this for both `q_pos_vol` and peak
   Q. All reductions reuse existing `lev` outputs — no new numerical core (`q_pos_vol` is a
   `np.maximum(q,0).sum()·dx·dy·dz` over the box interior).

4. **No directional gate.** `wing_lev_report` returns a plain dict `{peak_vorticity, peak_q, q_pos_vol,
   q_pos_frac, dx, phase_time}` with **no** `*_pass`/`converged`/`present` verdict key. The
   `requires_plotfile` test asserts only that the wiring **ran and produced physical, comparable numbers at
   the same phase**: both grids give finite, positive `peak_vorticity`/`peak_q`/`q_pos_vol`, and the pinned
   `dx` (0.125 coarse / 0.0625 medium) and `phase_time` match. It does **not** assert `Q_medium > Q_coarse`
   (a resolution artifact, not physics). The "present at medium vs weak/absent at coarse" reading lives in
   RESULTS **prose** interpreting the reported `q_pos_vol`/`q_pos_frac` contrast, with the resolution caveat
   above.

**Same-phase guard.** Coarse and medium plotfiles are compared at the same kinematic phase only if both
share `fixed_dt` and output cadence. `wing_lev_report` (and its test) assert their `current_time` agree to
within `0.5·min(dt_coarse, dt_medium)` (the stricter tolerance) before reporting the contrast — the
plotfile analogue of the CSV same-window guard (D5), so a cadence/dt drift fails loudly rather than
comparing mismatched phases.

## D3 — LEV CI coverage: composition (always) + committed boxlib fixture (LAST, de-risked) + fallback

The user chose **"Both"**: a `requires_plotfile` real-data test **and** a committed synthetic fixture for
cluster-free CI wiring coverage. Round-3's red-team showed the committed boxlib fixture is the one genuine
technical risk, so the design **decouples** it from the composition:

- **Composition (always, critical path).** `wing_lev_report` + its cluster-free CI test use an **in-memory
  synthetic box** (monkeypatched `extract_eulerian_box` returning an analytic solid-body-rotation box dict) —
  the PR #30 pattern (`test_sphere_cv_drag_wiring_known_answer`). This proves the reduction math + report-only
  contract in CI **without** the boxlib fixture, so `wing_lev_report`, the real `requires_plotfile` LEV test,
  and the grading/RESULTS deliverables never depend on the fixture spike.
- **Committed boxlib fixture (LAST, closes #33).** A tiny, deterministic, single-level boxlib **plotfile
  directory** under `tests/fixtures/` that `yt.load` opens with `max_level == 0` and a `field_list`
  containing the six required `('boxlib', …)` tuples, exercising the *actual* `extract_eulerian_box` yt-read
  path (the #33 gap). Sequenced **last** (§3.4) so its risk is isolated.

**Fixture format — matched to the REAL wing plotfile (round-3 red-team inspected `t2a-newconv4/plt01000/Level_0/Cell_H`):**
- **Eight** components, not six — the wing Header lists `x_velocity y_velocity z_velocity density tracer
  gradpx gradpy gradpz`; write all eight so the fixture exercises the same Header-parse path #33 covers (of
  which `extract_eulerian_box` reads the six it requires).
- FAB on disk is named **`Cell_D_00000`** (five digits), **not** `Cell_D_0000`.
- Box **≥ 5³** (≥ 3 interior points/axis for `lev`'s centred stencil), velocity = analytic solid-body
  rotation (`−Ω·y, Ω·x, 0`) so `extract_eulerian_box → lev` gives the **known** `‖ω‖ = 2Ω`, `Q = Ω²`.
- **Author a deterministic generator, not an opaque blob** (`tests/fixtures/make_lev_boxlib_fixture.py`)
  writing the FAB with **explicit `<f8`** byte order + a matching FAB descriptor (do not rely on native
  `tobytes()` order); commit generator + fixture + a `test_fixture_is_regenerable`. **Acceptance:** diff the
  generated `Cell_H` against the real one; `max_level == 0`; six required tuples present;
  `extract_eulerian_box(fixture)["u"].dtype == np.float64` (FP64 round-trip, asserted *separately* from the
  known-answer, so the fixture proves the FP64 path rather than tripping the fp32-build guard).
- **`.gitattributes` binary rule FIRST (round-3 red-team).** The repo has `core.autocrlf = true` +
  `* text=auto`, which would CRLF-corrupt the binary `Cell_D` FAB and desync the LF-counted `Cell_H`
  byte-offsets on commit/checkout. Land a binary rule (`tests/fixtures/** -text`, or `…/Cell_D* binary` +
  `…/Cell_H binary`) **in or before** the fixture commit; verify `git check-attr -a` before `git add`.

**Fallback — a HARD tripwire, not "if too costly."** If the fixture does not `yt.load` with the correct
`field_list` within the spike time-box, take the monkeypatch fallback **immediately**: keep **#33 open**,
`git rm` the `force-extraction` spec delta, drop `Closes #33`, re-run `openspec validate --strict` (confirm
the change still validates with only the flapping delta), record `### Why monkeypatch instead of a committed
plotfile?`. Because the fixture is **last and independent**, the fallback never blocks the grading + RESULTS
EPIC closers (the composition is already covered by the in-memory test above).

## D4 — Provenance is captured by the existing helper; `dt`/`max_step` are named fields

`run_metadata_t3b.json` is produced by `capture_run_metadata(inputs_file=inputs.3d.convergence_medium,
output_dir=<run>, docker_image=<:fp64 digest>, timing=…, extra={…})` — mirroring `run_metadata_t2a.json`
(which carries `iamrex_commit`, `image_digest`, `tier`, `convention` as `extra` on top of the helper's
`git`/`hardware`/`inputs.hash`/`timing`). The `inputs.hash` pins the **sha256 of
`inputs.3d.convergence_medium`**, closing the loop with the deck-invariance guard.

Because a run-time `dt` reduction is the one deviation the deck/handoff anticipate (and it is *not* baked
into the deck), `run_metadata_t3b.json`'s `extra` SHALL carry **named** `fixed_dt`, `max_step`,
`dt_reduced` (bool), and `plotfile_dir` fields — not free prose. **The guard reads the authoritative
`fixed_dt` from the hash-pinned DECKS** (`ns.fixed_dt` in `inputs.3d.validation` and
`inputs.3d.convergence_medium`), **not** from `run_metadata_t2a.json` — the coarse metadata carries **no**
`fixed_dt` field (round-3 red-team; reading it would be a `KeyError`). The T3b metadata `fixed_dt` is the
record of an *actual* run-time reduction, cross-checked against the deck value. Any dt reduction SHALL keep
a plotfile landing exactly on `t = 0.5` on both grids (raise `amr.plot_int` proportionally) so the LEV
same-phase guard can pair them. `plotfile_dir` (default `t3b-medium`) names where the medium plotfiles are
written so the `requires_plotfile` LEV test can locate them.

## D5 — Grading pre-flight guard: same **time grid**, not just same endpoint

The handoff warns the grader silently compares each CSV's *independent* window-max peak. The endpoint
check `max(time) ≈ stop_time = 1.0` is **necessary but not sufficient**: a run-time `dt` reduction (with
`max_step` raised to still reach `t = 1.0`) reaches the same endpoint on a **finer time grid** with a
different sample cadence — the window-maxima are then sampled on incongruent grids and a *temporal*-
resolution difference contaminates the *spatial* convergence delta the deck-invariance requirement is
built to isolate. The pre-grade guard `assert_gradeable_pair(coarse_csv, medium_csv)` therefore asserts:

1. both CSVs **non-empty** (row count > 0 — a header-only CSV raises a self-describing `"no data rows"`
   error, not a low-level `ValueError` from the reused reconstruction);
2. both reach the physical window: `max(time)` within a few `dt` of `stop_time = 1.0`;
3. **same time grid**, compared on the **deduplicated, monotone** time array (the committed coarse CSV is
   **2002 rows, not 2000** — `ns.init_iter = 2` writes **3 duplicate `t = 0` rows**, `iStep = 0` thrice;
   round-2 sci). So the guard compares the **set of unique `iStep` values** (and their matching sample
   times), **not** a raw `np.allclose(time)` on the full arrays with an exact row-count equality — otherwise
   a *valid same-dt* medium run whose init writes a different number of leading duplicate-zero rows would be
   falsely rejected. A dt-halved run (unique-`iStep` set differs — twice as many distinct steps) still
   **fails** with a self-describing `"time-grid mismatch"` error; a header-only CSV fails with `"no data
   rows"`. The `match=` substrings the unit test asserts are `"no data rows"`, `"window"`, and `"time-grid"`
   (the row-count/step-count branch must emit `"time-grid"`, not a bare `"row count"`, so §2.1's substring
   matches);
4. `fixed_dt` equality read from the **hash-pinned decks** (`ns.fixed_dt` in `inputs.3d.validation` vs
   `inputs.3d.convergence_medium`), **not** from `run_metadata_t2a.json` (which has no `fixed_dt` — a
   `KeyError` trap; round-3 red-team) — the deck-authoritative dt-reduction check, independent of the row
   artifact, cross-checked against `run_metadata_t3b.json["fixed_dt"]` when present.

This helper is **new code** (test-first, its own unit test) and is reused by both the grading task and the
reproducibility guard.

## D6 — Reproducibility guard covers CSV-derived numbers only; LEV is plotfile-derived; both deck hashes pinned

T3b's convergence numbers (`relative_change`, `gci_p1`, `gci_p2` per component) are recomputed from the
committed coarse + medium **CSVs** and asserted against the RESULTS literals (`abs ≈ 0.02`, the T2b
tolerance; appropriate for the O(0.1–1) dimensionless ratios). The **coarse `cf_coarse` column is the
grader's recomputed value**, not transcribed from `run_metadata_t2a.json` (so a stale JSON cannot drift
the headline). To close the loop on *both* decks of the graded pair, the guard also asserts
`sha256(inputs.3d.validation) == run_metadata_t2a.json["inputs"]["hash"]` (the confirmed coarse baseline)
**and** `sha256(inputs.3d.convergence_medium) == run_metadata_t3b.json["inputs"]["hash"]` (the invariance-
guarded medium). **Honest limit (round-2 sci):** the deck-hash pins prove the *decks are unmodified*; they
do **not** cryptographically link the committed `forces_medium.csv`/plotfiles to that deck (the CSV carries
no deck hash). The CSV↔deck link rests on the schema + `max(time) ≈ 1.0` + `len > 1900` plausibility pins
(§1.1), which are necessary but not a cryptographic guarantee — RESULTS states this honestly (acceptable for
report-only T3b). The **LEV numbers are plotfile-derived** (`plt*/` is gitignored) and therefore **not** in
the CSV-recompute guard; they are covered by the `requires_plotfile` real-data test and the committed
synthetic fixture instead. RESULTS states the LEV numbers as **plotfile-derived** (naming the mid-stroke
`t ≈ 0.5` / `plt01000` phase + the near-field box), not CSV-reproducible — an honest scoping of what the
guard covers.

## D7 — Honest interpretation for #40 (why report-only is not a hedge)

The coarse peak `CF_chord = 0.923` is ~3× van Veen's translational ~0.3. T3b's coarse↔medium
`relative_change` on `CF_chord` **tests the coarse-grid-diffused-IB hypothesis** directly:

- **Drops materially under refinement** → supports "coarse-grid diffused-IB under-resolves the tangential
  boundary layer"; but because the refinement is **combined spatial + IB-regularization** (the grid-tied
  `dv = h·d_nn²` and kernel support), a drop does **not** cleanly isolate discretization from the IB-model
  change — the GCI band quantifies residual discretization uncertainty (`gci_p1` the reported edge, not a
  bound; near-boundary order may be sub-1 for the shear-dominated chord).
- **Barely moves** → consistent with the excess being **model/physical** (rotational drag + tangential
  added mass **add** to the translational chord force, Bomphrey 2017) — **or** with two offsetting
  spatial-vs-IB-regularization effects that a 2-grid study cannot separate. Either reading pushes
  resolution to T4's per-component decomposition / a 3-grid study, not a finer single grid.

Either way the result **feeds #40** and neither is a "pass"/"fail" — which is why a tolerance/verdict
would be scientifically indefensible (2 grids give no observed order; grid-tied diffused IB is not
Richardson-extrapolable). This is the T3a scoping decision, carried unchanged. RESULTS states explicitly
that **#40 remains open regardless of the convergence reading**, so a "drop" is not misread as a
resolution of the PARTIAL.

## D8 — Auto-close discipline (differs from T3a) + the conditional-requirement archive hazard

T3b **completes** Tier T3, so `Closes #46` is **correct and desired**. `Closes #33` is correct **iff** the
D3 fixture spike succeeds; if the fallback is taken, the `force-extraction` spec delta is `git rm`-ed and
`Closes #33` dropped (an explicit task, not a memory test — otherwise the archive would fold a requirement
for a capability never delivered). Write the PR body's `Closes #33` clause **only after** the spike verdict
is known. `#40` **must stay open** (T4 reuses these runs) — referenced keyword-free ("advances #40"), with
**no** closing keyword adjacent to `#40` **even in a negated clause** ([[github-negated-closing-keyword-autocloses]]).

Pre-merge grep over the PR title+body **and every commit** — the **negative** check (no closing keyword may
sit next to `#40`) and a **positive** check (the intended closers ARE present):
```
# NEGATIVE — must print nothing (#40 not closed, even negated; boundary-anchored so #400 doesn't false-hit)
git log main..HEAD --format='%B' | grep -Ei '(clos|fix|resolv)[a-z]*:?[[:space:]]+#?40([^0-9]|$)'
# POSITIVE — the PR body MUST close #46 (and #33 iff the spike succeeded)
grep -Eiq 'clos[a-z]*:?[[:space:]]+#?46' <pr-body>   # required
```
`closes #46` / `closes #33` are the only expected closing directives; a body that *forgot* `Closes #46`
must fail the positive check (else the EPIC silently stays open on merge).

## D9 — Implementation reconciliation (Session B): what deviated from the approved proposal

The medium run completed cleanly on the A40 (762 s, DONE_EXIT=0, `dt_reduced=false`) and the change was
implemented TDD as designed. Three minor, honest deviations from the approved text:

1. **`extract_eulerian_box` gained an additive `current_time` return key.** D1 listed its return as
   `{u,v,w,gradp*,x,y,z,dx}`. `wing_lev_report` needs the plotfile phase for the same-phase guard; rather
   than a second `yt.load`, `extract_eulerian_box` now also returns `current_time = float(ds.current_time)`
   — one additive line, backward-compatible (existing sphere callers ignore it; the 25 sphere adapter tests,
   incl. `requires_plotfile`, still pass). This keeps the composition a **single-reader** and is why the
   in-memory monkeypatch in `test_wing_lev_report_reduction` returns a box dict carrying `current_time`.

2. **The near-field box is the D2 *illustrative* fixed box, recorded in RESULTS + a marker-fits assertion —
   not a per-run marker-derived box.** The `requires_plotfile` test uses `lo=(2.5,0,3)`, `hi=(5.5,4,5)`
   (pre-computed offline to bound the mid-stroke wing) and **asserts the plotfile's `particle_position_*`
   marker bbox fits inside it** — the exact anti-clip guard the marker-derivation was meant to provide, with
   a fixed box being more reproducible (and recorded verbatim in RESULTS). Functionally equivalent to
   "derive lo/hi from the markers + margin"; the fit-assertion would fail a stale/clipping box.

3. **RESULTS phrases the #40 hypothesis without the literal string "diffused-IB".** A pre-existing #32 guard
   (`test_no_false_diffused_ib_claim`) blanket-forbids "diffused-ib" in `examples/flapping_wing/RESULTS.md`
   (to keep a *retired false ~2.4× force-deficit claim* out). T3b's use is the legitimate grid-convergence
   hypothesis, but to respect the guard unchanged, RESULTS says "coarse-grid under-resolution of the
   immersed-boundary tangential boundary layer" instead. The precise term is still used in `benchmarks/METHODS.md`,
   the roadmap, the spec, and this proposal (none of which the guard covers).

**Fixture spike (D3) SUCCEEDED**, so `#33` is closed: the committed `tests/fixtures/lev_boxlib_plt/` (8-field,
`Cell_D_00000`, little-endian `<f8` matching AMReX's actual byte order under the real `(8 7 6 5 4 3 2 1)`
descriptor, `.gitattributes` `-text` binary rule) loads via `yt` and gives the exact `2Ω`/`Ω²` known answer
cluster-free. No fallback taken; the `force-extraction` delta and `Closes #33` stand.

**Headline result:** peak `CF_chord` **0.923 → 0.554 (−66.5 %)** under refinement (`gci` band 0.28–0.83),
`CF_normal` −11.7 %; LEV present on both grids (∫Q⁺ +9 %; peak Q ×3 = resolution artifact). Strong support
for the coarse-grid boundary-layer hypothesis for #40, not grid-converged at medium — #40 advanced, not
resolved.
