# Tasks — refactor-wing-axis-convention (Tier T2a)

TDD throughout: each implementation item names the test written **first** and the behavior it pins.
Cluster-free items are CI-gradeable; `requires_plotfile` / re-run items auto-skip without
`MOSQUITO_CFD_PLOTFILE_ROOT` and are graded on the operator A40 re-run. Run Python via `uv`.

**Cross-repo note (review B1/git):** `IAMReX-fork/Source/WingKinematics.H` is in the **separate**
`talmolab/IAMReX` repo, linked to this repo only by the pinned `IAMREX_COMMIT`. It is NOT a
mosquito-cfd file and is handled by a **fork PR + pin bump** (task 6), NOT the atomic mosquito-cfd
commit group (task 5). **Ordering:** 0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (task 2's kinematics mirror is
the single `R(t)` source consumed by task 3 — mirror before body-frame).

## 0. Source the van Veen oracle (CC-V2 gate — do first)

- [x] 0.1 Extracted van Veen's fitted `C_F` values from the open-access PDF (Fig 4a/4b/4e + eqs 3.1–3.8,
      in our `F_ref=½ρω²S_yy` normalization): wing-**normal** `C_Fz,transl(α) ≈ 3.4·sin(α)` (peak ≈3.4 at
      90°, ≈2.4 at 45°); chord-wise **tangential** `C_Fx,transl` small (~0.2–0.3 peak). Recorded in
      design D5 + memo with provenance and the **transl-vs-total** caveat (our `ib_force` is total;
      van Veen's `C_Fz`=transl+AM+WE → precise per-component = T4). `VAN_VEEN_CF_TARGETS` /
      `VAN_VEEN_MATCH_TOL` to be encoded as named constants in task 3.6.
- [x] 0.2 Confirmed verbatim (PDF §1.2/§2.4/Fig 1f/Fig 2 caption): x=chord→trailing edge, y=span→tip,
      z=wing-normal; `F=(F_x,F_z)`; `F_ref=½ρω²S_yy`, `S_yy=∫c(y)y²dy`; Euler `R = Rz(stroke,z)·Ry(pitch,y)`
      (van Veen `γ`/`φ` = our `φ`/`α`). Feeds `docs/coordinate-convention.md` (task 5.3).

## 1. Invariance guard — axis-general, rotation-equivariant extractor (cluster-free)

- [x] 1.1 **Test first:** `test_stress_integral_axis_general` — the generalized CV core, given a
      synthetic box and an explicit streamwise axis, returns the full `(Fx,Fy,Fz)` vector; with axis=+x
      it reproduces `sphere_cv_drag_cd`'s drag to round-off **and** the sphere entry point's return
      dict keys are unchanged (`cd, drag, x_inlet, x_outlet`) — backward-compat pin.
- [x] 1.2 Implement the explicit-axis generalization in `stress_integral.py` (return full vector; keep
      the sphere entry point's x-default and existing keys). Make 1.1 pass.
- [x] 1.3 **Test first:** `test_extractor_non_x_axis_matches_manual` — the generalized core with
      streamwise axis `+y` (and `+z`) equals a hand-rolled momentum balance across planes normal to
      that axis (spec: "A non-x streamwise axis is honored").
- [x] 1.4 **Test first:** `test_extractor_rotation_equivariance` — for a synthetic field whose force
      vector has **all three components non-zero** and an **off-diagonal** rotation `Q`
      (e.g. `(x,y,z)→(y,−x,z)`), `F(Q·field) == Q·F(field)` to round-off, and both sides use the SAME
      extractor on the SAME field (one rotated) — assert it does NOT compare across geometries.
- [x] 1.5 **Test first:** `test_axis_general_extractor_rejects_bad_axis` — a non-unit / zero /
      non-3-vector streamwise axis raises a clear error (new explicit-axis attack surface), matching the
      existing "Non-finite field raises" robustness bar.
- [x] 1.6 Implement the axis plumbing 1.3–1.5 require; make them pass. No re-run (invariance instrument).

## 2. Kinematics mirror + stroke-motion verification (cluster-free)

- [x] 2.1 **Test first:** `test_python_mirror_matches_design_composition` — pin the Python `R(φ,α,θ)`
      mirror to hand-computed reference matrices at ≥3 `(φ,α,θ)` triples **including one with θ≠0** to
      lock the ORDER `R = Rz(φ)·Ry(α)·Rx(θ?)` (new composition). Golden values come from the **target
      composition defined in design D2** — the mirror is the analytic **source of truth**, NOT transcribed
      from `WingKinematics.H` (which does not exist until task 6; task 6 must conform the C++ to *this*).
      Comment that any rotation-order change MUST update this test. (Drift guard — review round 2 TDD.)
- [x] 2.2 Implement the Python kinematics mirror (single source for the analytic `R(t)`, imported by
      task 3 AND the figure scripts in task 5). Make 2.1 pass.
- [x] 2.5 **Test first:** `test_no_duplicate_rotation_matrix` — source-scan asserts `generate_all_
      figures.py` and `visualize.py` contain **no** local `def rotation_matrix` and import the task-2.2
      mirror (the DRY code-source scenario; parallels the existing doc-content string tests). Removing the
      duplicate is done in task 5.4; this test locks it.
- [x] 2.3 **Test first:** `test_stroke_sweeps_span_tip` — evaluating the **new** `R(t)` on a span-tip
      marker, its horizontal (x–y) excursion traces a ±70° arc and is **non-zero at the α=0 midstroke**;
      the **old** composition gives `r·sin α` (≈0 at midstroke). Encodes the motion fix.
- [x] 2.4 Any helper the motion test needs; make 2.3 pass.

## 3. Body-frame per-component decomposition (cluster-free math, force oracle on re-run)

- [x] 3.1 **Test first:** `test_body_frame_decomposition_known_R` — with a known analytic `R(t)` and a
      synthetic lab force, `CF_chord = (Rᵀ·F)_x/F_ref`, `CF_normal = (Rᵀ·F)_z/F_ref` equal the
      hand-computed values; a pure chord-directed lab force yields `CF_normal≈0` (and vice-versa);
      **supplying the chord/normal axes swapped exchanges `CF_chord`↔`CF_normal`** (proves the explicit
      axes are honored, not cosmetic); rotation axes/order passed explicitly.
- [x] 3.2 **Test first:** `test_body_frame_decomposition_empty_series_and_bad_R` — empty force series
      and a singular / non-orthonormal `R` (det≠1) raise a clear error, matching the module's existing
      `f_ref<=0` / empty-window / NaN robustness bar.
- [x] 3.3 Implement `reconstruct_wing_body_forces` in `benchmarks/flapping_wing.py` using the task-2.2
      mirror `R(t)`, reusing `compute_force_reference` / `R_GYRATION` / `VAN_VEEN_BAND`. Update the
      module docstring (currently "lab-frame … deferred to T2a") to reflect the delivered body frame.
      Make 3.1–3.2 pass.
- [x] 3.4 **Test first:** `test_body_frame_overall_scalar_match` — on a synthetic fixture with
      **injected** targets+tolerance, the verdict PASSES when within and **FAILS when outside** (both
      directions); with targets `None` it falls back to the band floor and reports the gap without
      failing (`test_overall_match_falls_back_to_band_floor_when_targets_absent`).
- [x] 3.5 **Test first:** `test_body_frame_grader_rejects_loosened_band` and
      `test_match_tolerance_not_loosened` — a widened band flips the verdict to fail; `VAN_VEEN_BAND`
      and `VAN_VEEN_MATCH_TOL` are pinned constants (mirrors `test_van_veen_band_is_not_loosened`).
- [x] 3.6 Implement the overall-scalar-match grader; make 3.4–3.5 pass.
- [x] 3.7 **Test first:** `test_old_run_body_frame_contrast_differs` — the committed
      `examples/flapping_wing/forces.csv` run through the decomposition with the **old** `R(t)`
      composition yields `CF_chord`/`CF_normal` materially different from the new-motion expectation
      (the contrast is real, not a copy). Implement the contrast baseline reporting.
- [x] 3.8 **Test first:** `test_body_frame_reports_dropped_spanwise` — the decomposition either exposes a
      `cf_span` diagnostic field OR documents `F_y` as intentionally dropped per van Veen; assert the
      chosen mechanism is present so the spanwise force reads as a deliberate convention choice, not a
      bug (the coordinate-convention "spanwise F_y dropped" scenario — currently untested).

## 4. Geometry generator + regenerated wing.vertex (cluster-free)

- [x] 4.1 **Test first:** `test_generate_planform_span_axis` — `generate_planform` / the
      `generate-wing-planform` CLI accept a **span-axis** parameter and, for `axis="y"`, emit markers
      with span along y, chord along x, flat in x–y. (Generator currently hard-codes span along z —
      review docs B2; `src/mosquito_cfd/geometry/*` is added to Impact.)
- [x] 4.2 Add the span-axis parameter to `geometry/parametric_planform.py` + `geometry/cli.py`
      (default preserves current span-z behavior — backward compatible). Make 4.1 pass.
- [x] 4.3 **Test first:** `test_wing_vertex_span_along_y` — the regenerated `wing.vertex` has
      `ptp(y) > ptp(x)`, `ptp(z) ≈ 0` (flat in x–y) within tolerance, span ≈ `SPAN=3.0`, chord ≈
      `CHORD=1.0` from `constants.py`.
- [x] 4.4 **Test first:** `test_regenerated_vertex_preserves_marker_set` — the regenerated vertex has
      **908 markers** and, up to the intended axis permutation (x↔x, old-z→new-y, chord-flat), its sorted
      marker set matches the committed vertex to tolerance (set-equality, NOT byte-identity — float
      formatting differs). Then regenerate `examples/flapping_wing/wing.vertex` via
      `generate-wing-planform --axis y` invoked with the **span/chord/spacing that reproduce the committed
      908-marker set** (re-oriented only, so the run stays a re-orientation, not a silent geometry change).
      Not hand-edited. Make 4.3–4.4 pass.
- [x] 4.5 **Test first:** `test_radius_of_gyration_matches_regenerated_vertex` — `R_GYRATION` still
      equals the value **traced from the regenerated `wing.vertex`** to tolerance (span column is now y).
      **Also update the EXISTING `test_radius_of_gyration_traced_from_wing_vertex`**
      (`tests/test_force_surrogate_normalization.py:40`) which hard-codes the span as the z column
      (`verts[:,2]`) — repoint it to the **y** column and fix its `# cols` comment, else it mis-traces
      the flat axis as span and breaks. If the trace shifts, update `R_GYRATION` in `constants.py` AND
      note the `F_ref` implication. (Coupling — review round 2 TDD BLOCKING.)

## 5. Solver-adjacent deck + convention + docs + figures (ATOMIC — one commit group)

Everything in this group co-lands: **no commit leaves new-convention geometry described by
old-convention docs *or figures*** (D8; review docs B1/I4).

- [x] 5.1 **Test first:** `test_deck_infinite_span_periodic` — parse `inputs.3d.validation`:
      `geometry.is_periodic = 0 1 0` (periodic on the **span** axis y, retained), `ns.lo_bc/hi_bc`
      pressure-outflow(2) in x and **z** (the z **wall→outflow** change; y periodic), z domain widened,
      hinge on the span-along-y geometry. (Corrected framing — the deck is ALREADY periodic-y/wall-z;
      the real change is z-wall→outflow + z-widen + hinge, NOT "z wall→periodic" — review docs B3/CI I2.)
- [x] 5.2 Rewrite `examples/flapping_wing/inputs.3d.validation` accordingly (diff against the ACTUAL
      committed deck, not the roadmap's stale "z-wall" description). **Also set `ns.init_iter = 2`** (the
      committed deck has `init_iter = 0`, the [[flapping-wing-velocity-v2-fixed]] zero-velocity bug) and
      keep `amr.plot_int` enabled so the re-run persists non-zero velocity plotfiles for visualization
      (D13). Make 5.1 pass.
- [x] 5.3 **Test first:** `test_coordinate_convention_doc_states_axes` — `docs/coordinate-convention.md`
      contains the required axis/normalization strings (parallel to the existing RESULTS.md content
      test). Write `docs/coordinate-convention.md` (labeled diagram; verbatim van Veen fig 1f + eq
      1.1–1.2 and Bomphrey 2017 fig 1a citations). This is the **canonical narrative source**; the
      `WingKinematics.H` docstring, `RESULTS.md`, and the memo cross-reference it (DRY — review docs I5).
- [ ] 5.4 Parametrize the figure code off the convention/mirror and **regenerate all figures**
      (`generate_all_figures.py`: `HINGE`, the `rotation_matrix` duplicate → import task-2.2 mirror,
      "Span z"/"xz projection" labels; `visualize.py` hinge slice; `generate_validation_figures.py`
      `fig_v2_second_moment` span column, and the `fig_v5`/frame captions that say "deferred to T2a").
      (Figures are docs embedded in RESULTS — review docs B1.)
- [x] 5.5 **Test first / update:** `test_results_doc_discloses_frame_and_tier_caveat` updated to assert
      RESULTS now says the body-frame comparison is **delivered** (not deferred; only T4 curve-match
      deferred). Update `examples/flapping_wing/RESULTS.md`: the convention/frame prose AND every
      old-convention block — Wing Geometry ("Span runs in z" **plus the hinge coords `(4.0,2.0,2.5)`,
      "stroke plane horizontal (xy)", and the `r_mid` line**), Kinematics ("R=Rz·Ry·Rx"), BC table
      ("z Wall"), and mark the **old-run numeric tables** (Force-at-key-phases, plausibility-gate,
      van-Veen-comparison, added-mass) as **pending the task-7 re-run** rather than leaving stale
      authoritative numbers (review docs I4). The **IAMReX-fork SHA header** (`RESULTS.md:6`, `@
      7ece065d`) is repointed to `X` in task 7.3 when the re-run lands (else RESULTS documents the old
      solver — an atomicity leak; review round 2 docs).

## 6. Fork solver change + reproducible pin bump (cross-repo — review B1/B2/git)

**PR sequencing (round 2 git/CI — avoid red-Xing `main`):** open the mosquito-cfd PR (PR-B, tasks 0–5,8)
with the pin at the **old** `7ece065d` — it is CI-green and reviewable in parallel with the fork PR
(PR-A). Only **after PR-A merges → `X` exists on `talmolab/IAMReX`** push the pin-bump commit onto PR-B's
branch. Rationale: `docker.yml` `build-fp64` has **no `continue-on-error`** and `Dockerfile.fp64:74-77`
does `git checkout ${IAMREX_COMMIT}`, so a pin bumped to `X` before `X` is pushed **hard-fails the build
and red-Xs `main`**. Task 5 (geometry/deck/docs/figures) and the pin bump (6.2/6.3) are the **same PR-B**.

- [x] 6.1 In `talmolab/IAMReX` (`c:\repos\IAMReX-fork`, branch `feature/arbitrary-geometry`): refactor
      `Source/WingKinematics.H` — `Rx(α)`→`Ry(α)`, span-along-y reference, stroke `Rz(φ)` ⊥ span;
      update the docstring to cite van Veen 2022 fig 1f / Bomphrey 2017 fig 1a and cross-reference
      `docs/coordinate-convention.md`. Open a **fork PR (PR-A)**, merge, record the new commit SHA `X`.
- [x] 6.1a **Test first (fork checkout):** `test_wingkinematics_header_matches_design_composition` —
      evaluate the refactored `WingKinematics.H` at golden `(φ,α,θ)` triples and assert it equals the
      design-D2 composition the Python mirror (2.1) pins — making the C++↔mirror drift guard
      **bidirectional** (2.1 guards Python; this guards the C++). Human cross-check at the fork PR (no
      cross-repo CI).
- [ ] 6.2 In mosquito-cfd (on PR-B, only after `X` exists): bump `IAMREX_COMMIT` to `X` in **both**
      `docker/build-args.env` (line 9 + the `# Last updated` comment) **and** `docker/Dockerfile.fp64`
      (ARG line 17) — they MUST match (MEMORY.md footgun). `Dockerfile.fp32` (a different `ruohai0925`
      pin) is **left untouched** — safe because `docker.yml` `build-fp32` is `continue-on-error: true`
      ("BLOCKED - upstream bug"), so its stale pin cannot block `main`. Follow the canonical workflow
      `openspec/runai-dev-workflow.md:130-141`.
- [x] 6.3 **Test first:** `test_iamrex_pin_consistent` — parse both files with
      `^\s*(?:ARG\s+)?IAMREX_COMMIT\s*=\s*([0-9a-f]{40})` (strip `ARG `, tolerate comments/whitespace,
      assert a **full 40-hex** SHA — not a truncated `7ece065d`) and assert `build-args.env` == the
      `Dockerfile.fp64` ARG default (CI-gradeable pin-drift guard).
- [ ] 6.4 Merge PR-B so `docker.yml` builds & publishes the new `:fp64`; **capture the digest from the
      job-summary block** (`docker.yml:135-142`, a `$GITHUB_STEP_SUMMARY` render — not a workflow artifact).

## 7. Cluster re-run (post-submission, operator/A40, unattended)

- [x] 7.1 Submit one **coarse** new-convention validation wingbeat on the A40 with
      `--image-pull-policy Always` (so the pinned-SHA `:fp64` from 6.4 is used, not a stale cache).
      **Enable plot output and save plotfiles to a NEW run directory under
      `MOSQUITO_CFD_PLOTFILE_ROOT` = `Z:\users\eberrigan\mosquito-cfd-benchmarks`** (a dedicated
      new-convention subdir + distinct `amr.plot_file` prefix) — the deck carries `ns.init_iter = 2`
      from 5.2 so velocity is non-zero. **Non-destructive (D13): do NOT overwrite** the committed
      old-convention `examples/flapping_wing/plt_v2_*` (the preserved contrast baseline) or any existing
      Z: run.
- [x] 7.2 Capture `run_metadata.json`: the **GHA-published `:fp64` digest** read from the `docker.yml`
      job-summary block (6.4; not a local image id), and the **pinned `IAMREX_COMMIT=X`** threaded via
      `capture_run_metadata`'s **existing** `extra=` param (`extra={"iamrex_commit": X}` — metadata.py
      already has this param; no code change), inputs hash, caller-supplied timestamp (CC-V3). A
      `get_git_info(fork)` clean-at-`X` check is a **secondary** sanity gate, NOT a hard validity gate
      (the image's real provenance is the pinned SHA + digest; GHA clones fresh). Track-B corpus untouched.
- [x] 7.3 Grade the D5 body-frame overall-scalar-match on the re-run (`requires_plotfile`/re-run test);
      **regenerate the new-convention velocity figure** (`fig_velocity`) from a new-run plotfile on the
      Z: drive; and **replace** the stale old-run numeric tables in RESULTS with `CF_chord`/`CF_normal`
      cycle-mean + peak vs van Veen, and **repoint the `RESULTS.md:6` IAMReX-fork SHA header to `X`**. If
      the re-run slips, leave those tables/figure marked "pending" and merge the cluster-free deliverables
      (the PIN must still be consistent at merge — the force number may trail).

## 8. Validation, roadmap, reconcile

- [x] 8.1 `uv run pytest` + `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/` +
      `uv run ruff format --check src/ tests/ scripts/ examples/prelim_sweep/` (same four paths as CI —
      a bare `ruff format --check` formats the whole tree and can diverge) green; `requires_plotfile`/
      re-run tests report **skipped** (not error) with the plotfile root unset.
- [x] 8.2 **Rewrite** (not merely tick) the **T2a** oracle in `docs/aerodynamics_validation/roadmap.md`:
      the row L88 + the "Oracle grounding" table L66 + the CC-V4 L120 "forces are already axis-invariant"
      claim — replace sim-to-sim "invariance" with the D1 analysis-layer rotation-equivariance guard +
      body-frame van Veen gate + stroke-motion finding (review docs I7). Note production `inputs.3d.
      production` stays old-convention (deferred to T3) — add an out-of-scope banner (review docs I6).
- [x] 8.3 `openspec validate refactor-wing-axis-convention --strict` passes.
- [ ] 8.4 Reconcile implementation against this proposal/spec before commit (new-feature step 9); record
      any `### Why N instead of M?` deviation; two linked PRs (fork-first), cross-referenced by SHA `X`.
