# Design — refactor-wing-axis-convention (Tier T2a)

## Context

Issue #1 framed the axis change as "orientation/labeling only; forces are axis-invariant." Working the
kinematics by hand (see proposal) shows that is **false for the motion**: the current stroke `Rz(φ)` is
about the span axis, so the span-tip sweeps via `sin α` only. Matching van Veen (stroke ⊥ span) is a
**motion change**, not a rotation of the existing run. The roadmap's stated T2a oracle ("forces
invariant under the documented transform, T1b extractor on both runs") therefore cannot be a
sim-to-sim comparison of the old and new *motions*. The user selected **Decouple** (grading fork) and
**infinite-span periodic** (BC fork), and steered the comparison to **match van Veen** (axes + overall).

## Goals / Non-goals

- **Goals:** (1) re-orient the solver/geometry/docs to van Veen's exact convention, atomically;
  (2) deliver the body-frame per-component van Veen comparison #36 deferred, graded as an overall
  scalar match with the band as a floor; (3) verify the stroke *motion* now reproduces van Veen's
  translational sweep; (4) an analysis-layer rotation-equivariance guard that the relabel/extraction is
  correct, decoupled from the motion change.
- **Non-goals:** time-resolved curve match (T4); medium-grid LEV convergence (T3); sphere CC-V5 docs
  (#29); changing force *magnitude* reconstruction (T1b/#36 — CC-V4); regenerating Track-B's corpus.

## Decisions

### D1 — Decouple "invariance" (analysis guard) from the "motion fix" (van Veen gate)
The refactor changes physics, so there is no old↔new sim invariance to grade. Split into two graded
things, kept separate per **CC-V4**:
- **Invariance guard = analysis-layer rotation-equivariance.** The field-based force extractor must
  satisfy `F(Q·field) = Q·F(field)` for any rotation `Q` that permutes/rotates the grid axes. Proven as
  a **cluster-free property test** on synthetic fields (and, where a plotfile is available, on the
  committed field rotated in memory). This is the pure-rotation control pair — it validates the
  relabel/extraction with no re-run and **never** compares new-extractor-new-geom vs
  old-extractor-old-geom.
- **Motion fix = van Veen body-frame gate.** Graded on the NEW-convention re-run (D5).

### D2 — The kinematics refactor (WingKinematics.H) is a motion correction
Target: stroke `Rz(φ)` about lab vertical z; pitch α about the span; span along y in the reference
geometry. Cleanest composition consistent with van Veen fig 1f: `R = Rz(φ)·Ry(α)` (θ deviation about
the remaining axis, default 0). A **kinematic** oracle (D6) confirms the span-tip now sweeps ±70°.

**Reproducible-pin mechanism (review B1/B2, corrected).** `WingKinematics.H` lives in the **separate**
`talmolab/IAMReX` repo; the `:fp64` image clones IAMReX at the commit pinned in `docker/build-args.env`
(line 9) **and** `docker/Dockerfile.fp64` (ARG line 17), which currently both equal `7ece065d` (= the
fork HEAD). An in-container hot-patch (`cp` into `/opt/cfd/IAMReX/Source/` + local rebuild) produces a
binary whose source is captured by **no** commit — unreproducible, violating CC-V3. The refactor MUST
therefore follow the canonical workflow (`openspec/runai-dev-workflow.md:130-141`): (1) commit
`WingKinematics.H` on the fork → SHA `X`; (2) bump `IAMREX_COMMIT` to `X` in **both** pin files (they
must match — a documented footgun; guarded by a new `test_iamrex_pin_consistent`); (3) push `main` so
GHA rebuilds/publishes `:fp64`; (4) re-run with `--image-pull-policy Always`. The Python **kinematics
mirror** (D6) is validated against this exact composition by a golden-value test so the un-CI-testable
C++ cannot silently drift from the analysis. The local `make -j USE_CUDA=TRUE` timestamp check is only a
pre-push sanity gate, not the reproducibility mechanism.

**Pin-before-push CI hazard (review round 2).** `docker.yml`'s `build-fp64` job has **no
`continue-on-error`**, and `Dockerfile.fp64:74-77` does `git clone … && git checkout ${IAMREX_COMMIT}`.
So if `IAMREX_COMMIT` is bumped to `X` and pushed to mosquito-cfd `main` **before** `X` is merged/pushed
to `talmolab/IAMReX`, the build hard-fails (`git checkout X` on a repo lacking `X`) and **red-Xs main**.
Ordering is therefore load-bearing: the mirror-pinning Python PR (PR-B) is opened with the **old** pin
(CI-green, reviewable in parallel with the fork PR-A); only **after PR-A merges → `X` exists** is the
pin-bump commit (+ `test_iamrex_pin_consistent`) pushed onto PR-B's branch; then PR-B merges (triggering
the `:fp64` publish). The GHA digest is read from the `docker.yml` job-summary block (docker.yml:135-142,
a `$GITHUB_STEP_SUMMARY` render, not a workflow artifact) — a manual operator step. The bidirectional
mirror↔C++ conformance is a **human cross-check at the fork PR** (no cross-repo CI), backed by a fork-side
golden test that `WingKinematics.H` evaluates to the D2 composition the Python mirror pins.

### D3 — Boundary conditions: infinite-span periodic (framing corrected vs the roadmap)
The committed `inputs.3d.validation` is **already** `geometry.is_periodic = 0 1 0` with
`ns.lo_bc/hi_bc = 2 0 4` — i.e. x outflow, **y periodic**, **z wall** — while the span currently runs
along **z**. So the roadmap row's "z wall → periodic" mis-describes the file (review docs B3 / CI I2).
The correct deltas after span→y are: keep `is_periodic = 0 1 0` (now the periodic axis **coincides with
the span**, the infinite-span model), change **z from wall(4) → outflow(2)** (z is now vertical/lift),
**widen the z domain** for lift clearance, and re-place the hinge for the span-along-y geometry (the
current `hinge_z = 2.5` is a span-z artifact). The deck rewrite MUST be diffed against the actual
committed file, not the stale description, to avoid a partial no-op or an accidental BC regression (no
CI lints the deck — a `test_deck_infinite_span_periodic` parse guards it). This is a genuine physics
change, **not** part of the invariance guard (D1) — graded by the van Veen gate (D5). LEV/wake
convergence under these BCs is **T3**.

### D4 — Match van Veen's exact convention (sourced verbatim)
van Veen 2022 §1.2 / eq 1.1–1.2 / fig 1f: **x=chord-wise, y=spanwise, z=wing-normal**; body-frame
`F = (F_x chord, F_z normal)`, spanwise ignored; `F_transl = ½ρω²S_yy·C_F(α)`, `S_yy = ∫c(y)y²dy`. Our
`compute_force_reference` already implements that `F_ref` (#36), so T2a reuses it unchanged and adds
only the **frame** (body-frame chord/normal rotation). `docs/coordinate-convention.md` is the canonical
narrative source for this (D12); it states the convention with a diagram and the verbatim citations.

### D5 — Body-frame decomposition + overall scalar-match oracle
Rotate lab `ib_force (Fx,Fy,Fz)` into the wing body frame by the **analytic** `R(t)ᵀ` (the same matrix
the solver applies), giving `CF_chord = (Rᵀ·F)_x / F_ref` and `CF_normal = (Rᵀ·F)_z / F_ref`. Grade an
**overall scalar match**: cycle-mean **and** peak `|CF_chord|`, `|CF_normal|` within a stated tolerance
of van Veen's reported overall values, with `[0.5,1.5]` (`VAN_VEEN_BAND`, test-pinned, **not loosened**)
as a floor. The match target(s) and tolerance are **named, test-guarded constants**
(`VAN_VEEN_CF_TARGETS`, `VAN_VEEN_MATCH_TOL`) — mirroring `test_van_veen_band_is_not_loosened` — so
"never reverse-fit" is *enforced*, not merely prose (review TDD §8). The grader is proven on synthetic
fixtures with **injected** targets in **both** directions (passes within tolerance, fails outside), so
it is fully testable before the real numbers exist. **Two graded modes, kept distinct in the spec
scenarios:** (a) the always-on floor (`VAN_VEEN_BAND` not loosened) — live and CI-gradeable now; (b) the
`[when VAN_VEEN_CF_TARGETS pinned]` tolerance match.

**van Veen targets — SOURCED (task 0.1, open-access PDF Fig 4a/4b/4e + eqs 3.1–3.8, in OUR
`F_ref = ½ρω²S_yy` normalization):**
- Wing-**normal** translational `C_Fz,transl(α) ≈ 3.4·sin(α)` (least-squares sine fit, Fig 4a; peak
  ≈3.4 at α=90°, ≈2.4 at α=45°, ≈2.0 at α=36°); added-mass `C_Fz,AM` up to ≈+1.5, Wagner `C_Fz,WE` to
  ≈−1.5 (opposing). Chord-wise **tangential** `C_Fx,transl` **small** (~0.2–0.3 peak at low α, Fig 4b).
- Euler order confirmed verbatim (§2.4, Fig 2 caption): `R = Rz(stroke,z_world)·Ry(pitch,wing-y)`;
  x=chord→trailing edge, y=span→tip, z=wing-normal. (van Veen labels stroke `γ`/pitch `φ`; repo `φ`/`α`
  — same structure; documented to avoid conflation.)
- Encode `VAN_VEEN_CF_TARGETS` from these (normal amplitude ≈3.4·sin α; tangential small) + a
  `VAN_VEEN_MATCH_TOL`. **Comparison caveat (bounds the tolerance):** our `ib_force` is the **total**
  hydrodynamic force while van Veen's `C_Fz` is transl+AM+WE, so body-frame `CF_normal` ≈ van Veen's
  **total** normal coefficient (translational dominant) at the instantaneous α. The **precise
  per-instant per-component** match needs the §3.3 mosquito-wingbeat curves digitized = **T4**; T2a
  grades the `[0.5,1.5]` **floor** per component (live) + an **overall-magnitude** check of peak
  `CF_normal` against `C_Fz,transl(α≈45°)≈2.4` and peak `CF_chord` small, gap **reported**, not
  reverse-fit.

The rotation axes/order are passed **explicitly** (no hard-coded streamwise axis) — the
`stress_integral` Decision-9 analog — so the analysis layer cannot re-introduce a #1-style mislabel.

### D6 — Stroke-motion verification is (mostly) cluster-free
The motion question is settled at the **kinematic** level without CFD: evaluate the refactored `R(t)` on
the wing markers and assert the span-tip's horizontal excursion is `≈ r·(1−cos)` of a ±70° arc (sweeps
with **stroke**, ≠ 0 at the α=0 midstroke), and that the OLD composition gives `r·sin α` (≈0 at
midstroke). The **force** consequence is the D5 gate on the re-run. This is deliverable #3.

### D7 — Axis-general extractor (force-extraction), full vector, explicit axis
`stress_integral.py`'s `cd_from_drag`/`sphere_cv_drag_cd` hard-code +x as streamwise. Generalize the
core to accept the streamwise/freestream axis explicitly and return the full `(Fx,Fy,Fz)` momentum-flux
vector; the sphere entry point keeps its current x-default behavior (backward compatible). The
rotation-equivariance property (D1) is a test on this generalized core. The wing has no freestream, so
its use is the general control-volume force vector (unsteady term included where a two-plotfile pair
exists); the *graded* wing oracle remains the D5 body-frame `ib_force` gate — the extractor's role here
is the **invariance instrument**, not the wing's headline number.

### D8 — Atomicity (the boundary includes the pinned SHA)
`coordinate-convention.md`, the RESULTS frame-description + the RESULTS IAMReX-fork SHA header, the
regenerated **figures**, the geometry/deck, **and the `IAMREX_COMMIT` pin bump** all cross the `main`
boundary **in one mosquito-cfd PR (PR-B)** — the atomic unit is *geometry + deck + docs + figures +
pinned-SHA* (review round 2 git). If the span-along-y geometry merged while the pin still pointed at the
old span-along-z solver, `main` would carry a geometry driven by the wrong solver — the exact state the
atomicity gate forbids. The `WingKinematics.H` docstring co-lands via the **fork PR (PR-A)**, cross-
referenced by SHA `X`. Because git-history atomicity is not `pytest`-assertable, it is a **pre-merge
checklist gate**, backed by `test_iamrex_pin_consistent` for the two pin files.

### D10 — Figures are docs; they co-land and regenerate in the atomic group
The `examples/flapping_wing/` figure scripts hard-code the old convention (`generate_all_figures.py`:
`HINGE=(4,2,2.5)`, a duplicate old `rotation_matrix`, "Span z"/"xz projection" labels;
`generate_validation_figures.py` `fig_v2_second_moment` reads the z column as span; `fig_v5`/frame
captions say "deferred to T2a"; `visualize.py` slices at the span-z hinge). They are embedded in
`RESULTS.md`, so leaving them stale beside new geometry breaks the D8 atomicity promise (figures ARE
docs — review docs B1). The atomic group therefore parametrizes the figure code off the convention +
the D6 mirror and **regenerates all figures** in the same commit.

### D11 — The generator gains a span-axis parameter (it currently cannot emit span-along-y)
`geometry/parametric_planform.py` hard-codes span along z (`y=cy` constant; docstring "z-direction").
Task 4's "regenerate via `generate-wing-planform`" is impossible without a code change (review docs B2),
so the generator + CLI gain a **span-axis** parameter (default = current span-z, backward compatible),
pinned by a test; `wing.vertex` is then regenerated with `--axis y`, never hand-edited.
**Coupling:** `R_GYRATION` (constants.py) is *traced from* the committed `wing.vertex`; regeneration may
shift it, silently moving `F_ref`. A `test_radius_of_gyration_matches_regenerated_vertex` re-traces and
either confirms or updates the constant (review TDD).

### D12 — One canonical source per layer (DRY), everything else cross-references
The axis convention + rotation will otherwise scatter across `coordinate-convention.md`,
`WingKinematics.H`, the Python mirror, `flapping_wing.py`, the memo, and the figure code (review docs
I5). Canonical **narrative** source = `docs/coordinate-convention.md` (convention + citations); the
`WingKinematics.H` docstring, `RESULTS.md`, and the memo cross-reference it rather than restating axes.
Canonical **code** source for `R(t)` = the D6 Python mirror, imported by both `flapping_wing.py` and the
figure scripts (kills the duplicate `rotation_matrix`). The coordinate-convention spec states this
"one canonical + refs" rule so the three doc locations can't drift.

### D13 — Visualization plotfiles persisted to the network drive, with the velocity fix (non-destructive)
The re-run enables plotfile output and sets **`ns.init_iter = 2`** (the committed validation deck still
has `init_iter = 0`, the [[flapping-wing-velocity-v2-fixed]] bug that writes `x_velocity = 0` to every
plotfile). Plotfiles are saved to `MOSQUITO_CFD_PLOTFILE_ROOT = Z:\users\eberrigan\
mosquito-cfd-benchmarks` so the `requires_plotfile` tests and the **new-convention velocity figure**
(`fig_velocity`, currently generated from `plt_v2_00500`) consume them; the velocity figure is
regenerated in the new convention as part of the atomic figure set (D10). Without both the plotfile save
**and** `init_iter = 2`, the visualization would be zeros / old-convention.

**Non-destructive (do NOT overwrite existing plotfiles).** The new run writes to a **distinct new run
directory** (a dedicated new-convention subdir under `MOSQUITO_CFD_PLOTFILE_ROOT` with its own
`amr.plot_file` prefix) — it MUST NOT overwrite the committed **old-convention** plotfiles
`examples/flapping_wing/plt_v2_00000`–`plt_v2_02000`, nor any existing run already on the Z: drive. The
old-convention `plt_v2_*` are **preserved** because they are the contrast baseline (the "old motion is
off" evidence; the old-convention velocity figure). Overwriting them would destroy exactly what T2a
compares against and is a non-reversible loss of committed data.

## Risks / open questions

- **van Veen overall `C_F` numbers not yet in-repo (CC-V2).** Mitigation: D5 gate degrades to the band
  floor until the numbers are extracted from the results section (the open-access PDF is available); the
  tolerance is stated when the numbers are pinned, never reverse-fit to pass.
- **Re-run availability.** Post-submission, single-tenant A40, operator-run/unattended; one coarse run.
  If the rebuild or run slips, the cluster-free pieces (guard, decomposition math, kinematic motion
  test, docs) still land and merge; the D5 force gate is marked pending the re-run artifact.
- **BC change vs invariance.** By construction the BC change lives only in the new van-Veen deck (D3);
  the invariance guard (D1) never depends on it, so the two cannot be conflated.
