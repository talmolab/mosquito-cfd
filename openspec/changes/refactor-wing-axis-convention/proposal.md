# Refactor wing axis convention to match van Veen (Tier T2a, issue #1) — **BREAKING**

**BREAKING:** this changes the wing's prescribed **motion** (not just axis labels), re-orients the
geometry, and re-pins the IAMReX solver commit — so all prior flapping-wing runs are **superseded** and
carried only as labelled contrast baselines, not re-gradeable against the new convention (cf. #36, which
landed as `feat(force-surrogate)!`).

## Why

The flapping-wing simulation uses an axis convention that does **not** match the insect-biomechanics
literature it validates against (van Veen et al. 2022, *JFM* 936:A3; Bomphrey 2017). Concretely
(`IAMReX-fork/Source/WingKinematics.H`, `examples/flapping_wing/wing.vertex`,
`examples/flapping_wing/inputs.3d.validation`):

- The wing **span runs along z** and the stroke is `Rz(φ)` **about that same span axis**. A span
  point at body offset `(0,0,r)` maps to `(r·sφ·sα, −r·cφ·sα, r·cα)` — its horizontal excursion is
  `r·sin α`, **zero at the α=0 midstroke**. The span-tip sweeps via *pitch*, not *stroke*, so it does
  **not** trace van Veen's ±70° translational arc (issue #1 note, 2026-06-30).
- Consequently issue #1's premise "forces are axis-invariant (a pure relabel)" is **false for the
  motion**: no fixed rotation turns "stroke axis ∥ span" into "stroke axis ⊥ span". The refactor is a
  **motion correction**, and forces will genuinely change.
- #36 met the flapping plausibility gate only as a **lab-frame O(1) magnitude** check and explicitly
  **deferred** the faithful **body-frame per-component** van Veen comparison to this tier
  (`examples/flapping_wing/RESULTS.md` "Frame and tier caveat").

van Veen's convention, sourced verbatim from the open-access paper (§1.2 / eq 1.1–1.2 / fig 1f), is:
**x = chord-wise, y = spanwise, z = wing-normal (vertical/lift)**; forces decomposed in the **wing
(body) frame** as `F = (F_x chord-wise, F_z wing-normal)` (spanwise ignored); normalization
`F_transl = ½ρω²S_yy·C_F(α)`, `S_yy = ∫₀ᴿ c(y)y²dy`. Our `compute_force_reference` already uses that
normalization (#36) — T2a adds the **frame** faithfulness the paper requires and re-orients the solver
to that convention so every future figure, paper, and collaborator reads one consistent frame.

This is Tier **T2a** of the aerodynamics-validation program (roadmap `docs/aerodynamics_validation/
roadmap.md`), post-submission and re-run-bound. It keeps the two magnitude defects (T1b sphere
extraction, #36 wing normalization) strictly separate from this labeling/motion change (**CC-V4**).

## What Changes

Three coupled deliverables, landing **atomically** (no interim commit may carry new-convention geometry
with old-convention docs):

1. **Axis-convention + motion refactor (issue #1).**
   - `IAMReX-fork/Source/WingKinematics.H`: refactor the Euler composition so **pitch α is about the
     span** (`Ry(α)`, was `Rx(α)`) and **stroke `Rz(φ)` is about the lab vertical z, perpendicular to
     the span** — the span-tip now traces the ±70° arc. Update the docstring to cite van Veen 2022 /
     Bomphrey 2017 fig 1a.
   - `examples/flapping_wing/wing.vertex`: re-orient so **span runs along y**, chord in x, wing flat in
     the x–y body plane (regenerated via `generate-wing-planform`, not hand-edited).
   - `examples/flapping_wing/inputs.3d.validation`: **infinite-span periodic** BC/domain. NB the
     committed deck is *already* `is_periodic = 0 1 0` (periodic in y) with a **z wall** and x outflow
     — so the real change is **z wall → outflow** (z becomes vertical/lift), the retained **y-periodic
     now coincides with the span** (mimics infinite span; tip no longer near a wall), plus z-domain
     widening and hinge re-placement for the span-along-y geometry. (It is *not* a "z wall → periodic"
     change — that framing, inherited from the roadmap row, mis-describes the current deck.)
   - `docs/coordinate-convention.md` (**new**): the project-wide convention with a labeled diagram,
     citing van Veen 2022 fig 1f + eq 1.1–1.2 and Bomphrey 2017 fig 1a.
   - `examples/flapping_wing/RESULTS.md`: update the frame description / "Frame and tier caveat" to the
     new convention (the caveat's deferred body-frame comparison is now *delivered*).

2. **Body-frame per-component van Veen comparison (deferred by #36).** Extend
   `src/mosquito_cfd/benchmarks/flapping_wing.py` to rotate the lab-frame `ib_force` `(Fx,Fy,Fz)` into
   the **instantaneous wing body frame** using the *known analytic* `R(t)` from the kinematics, yielding
   **`CF_chord` and `CF_normal`** series (van Veen `F = (F_x, F_z)`). The rotation/axes are passed
   **explicitly** — no hard-coded streamwise axis, no #1-style mislabeling in the analysis layer. The
   graded oracle is an **overall scalar match**: cycle-mean **and** peak `CF_chord`/`CF_normal` land
   within a stated tolerance of van Veen's reported overall values, with the `[0.5,1.5]` band as a
   floor. The OLD committed run's body-frame decomposition is reported as a **contrast baseline** (shows
   the old motion is off).

3. **Stroke-motion verification (issue #1 note).** A cluster-free **kinematic** test evaluates the
   refactored kinematics on the wing markers and asserts the span-tip traces the ±70° horizontal arc
   (position/velocity level), contrasted against the current stroke-∥-span motion; the **force**
   consequence is graded by deliverable #2 on the re-run.

**Invariance guard (analysis-layer, cluster-free).** Generalize the field-based extractor
(`stress_integral.py`) to accept an **explicit freestream/streamwise axis** and return the full
`(Fx,Fy,Fz)` vector, and prove it is **rotation-equivariant** — `F(Q·field) = Q·F(field)` — as a
property test on synthetic/committed fields (the pure-rotation control pair; *never*
new-extractor-new-geom vs old-extractor-old-geom). This is the CC-V4 "orientation/labeling only" piece:
it validates the relabel/analysis, decoupled from the motion fix.

## Impact

- **Affected specs:** `coordinate-convention` (**new**), `flapping-wing-validation` (modified + added),
  `force-extraction` (added).
- **Affected code (this repo):** `src/mosquito_cfd/benchmarks/{flapping_wing.py,stress_integral.py}`;
  `src/mosquito_cfd/geometry/{parametric_planform.py,cli.py}` (a **span-axis** parameter — the generator
  currently hard-codes span along z and cannot emit span-along-y); `src/mosquito_cfd/force_surrogate/
  constants.py` (re-trace `R_GYRATION` from the regenerated vertex if it shifts);
  `examples/flapping_wing/{wing.vertex,inputs.3d.validation,RESULTS.md}` and its **figure scripts**
  (`generate_all_figures.py`, `visualize.py`, `generate_validation_figures.py` — they hard-code span=z /
  the old rotation and are embedded in RESULTS); `docs/coordinate-convention.md` (new);
  `docker/build-args.env` + `docker/Dockerfile.fp64` (the **`IAMREX_COMMIT` pin bump** — both must
  match); the roadmap T2a row + oracle table + CC-V4.
- **Cross-repo (separate `talmolab/IAMReX` fork):** `Source/WingKinematics.H` is **not** a mosquito-cfd
  file — the two repos are linked only by the pinned `IAMREX_COMMIT`. The motion fix lands as a **fork
  PR** (merge → SHA `X`); this repo then bumps the pin to `X`. **Two linked PRs, fork-first**, cross-
  referenced by `X`; the mosquito-cfd PR does not merge until the fork PR is merged and the pin bumped
  (else new-convention geometry sits beside an old-convention pinned solver).
- **Re-runs (post-submission, operator/A40, unattended):** after the fork commit + pin bump, GHA
  rebuilds/publishes `:fp64`; then one **coarse** new-convention re-run via the canonical workflow
  (`openspec/runai-dev-workflow.md:130-141`, `--image-pull-policy Always`). The invariance guard,
  body-frame decomposition math, and stroke-motion kinematic test are **cluster-free** and CI-gradeable.
- **Visualization plotfiles saved to the network drive.** The new deck sets **`ns.init_iter = 2`** (the
  [[flapping-wing-velocity-v2-fixed]] fix — the committed validation deck still has `init_iter = 0`,
  which writes `x_velocity = 0` to every plotfile) and enables plot output; the re-run **saves plotfiles
  to `MOSQUITO_CFD_PLOTFILE_ROOT` = `Z:\users\eberrigan\mosquito-cfd-benchmarks`** so the
  `requires_plotfile` tests and the **new-convention velocity figure** (`fig_velocity`, currently from
  `plt_v2_00500`) consume them. Without this the velocity figure would be zeros / old-convention.
- **Reproducibility (CC-V3):** the re-run captures `run_metadata.json` — the **GHA-published `:fp64`
  digest** (read from the `docker.yml` job-summary block, docker.yml:135-142) and the **pinned
  `IAMREX_COMMIT=X`** threaded via `capture_run_metadata`'s **existing** `extra=` param
  (`extra={"iamrex_commit": X}`; no `metadata.py` change needed — the param already exists), inputs hash,
  caller-supplied timestamp. A local `get_git_info(fork)` clean-at-`X` check is a **secondary** sanity
  gate (the image's real provenance is the pinned SHA + digest, since GHA clones fresh). `requires_
  plotfile` tests auto-skip without `MOSQUITO_CFD_PLOTFILE_ROOT`. All Python via `uv`.
- **Explicitly out of scope:** the sphere "~60% low / 2.64×" doc cleanup (**CC-V5**, #29, docs-only);
  **time-resolved** curve-RMSE + peak-phase match vs van Veen fig 3–4 (**T4**); medium-grid convergence
  (**T3**); loosening the test-pinned `VAN_VEEN_BAND`. **Track-B's frozen corpus is never regenerated.**
  `examples/flapping_wing/inputs.3d.production` (old-convention, 128×64×128) is **deferred to T3** and
  intentionally NOT re-authored here — but because it shares the now-reoriented `wing.vertex`, this
  change adds a one-line banner to that deck flagging the T3 re-author so it isn't silently run with a
  span-along-y geometry and a span-along-z hinge.
- **Dependency / gate (CC-V2):** van Veen's reported **overall** `CF_chord`/`CF_normal` numeric targets
  must be extracted from the paper's results section before the tight scalar-match oracle can be graded;
  until pinned, the graded floor is the `[0.5,1.5]` band and the gap-to-van-Veen is *reported*, not
  graded. The convention itself (frame + normalization) is already sourced verbatim.

## Deviation discovered during implementation

### Why the Track-B sweep base was frozen (not left pointing at the live deck)

The refactor of `examples/flapping_wing/inputs.3d.validation` (per issue #1) surfaced an undocumented
coupling **no reviewer caught**: that deck was the **base template of the frozen Track-B corpus**
(`BASE_INPUTS` in `tests/test_force_surrogate_sweep.py`, recorded in
`examples/prelim_sweep/sweep_provenance.json`). Re-orienting it broke
`test_committed_sweep_matches_regeneration` (the corpus is byte-identity-pinned) — a **direct violation
of the hard constraint "Track-B's frozen corpus is never regenerated."**

**Resolution (honors both constraints):** a **byte-identical snapshot** of the pre-T2a deck was frozen
at `examples/prelim_sweep/base_inputs.3d.validation` (its `sha256` **exactly matches** the value already
recorded in `sweep_provenance.json`, `dfb1e24b…`), and Track-B's base pointer was moved to it (test +
provenance path + `sweep.py` docstring). The corpus decks/manifest are **unchanged** (36 sweep tests
green), so Track-B is *decoupled from* T2a rather than regenerated. `docs/coordinate-convention.md` and
the live deck carry the new convention; the frozen snapshot preserves the old one for Track-B. No
follow-up issue is needed — the coupling is fully resolved, not worked around.

### Why a second fork commit (DiffusedIB `d_nn` in 3D) was needed

The first operator A40 re-run (on the new convention) produced **all-zero IB forces**. Root cause:
`DiffusedIB.cpp` estimated the surface-marker spacing `d_nn` (for the volume element
`dv = h·d_nn²`, the [[surface-ib-marker-volume-fix]]) from the nearest-neighbor distance **in the xz
plane only**, with a hard-coded assumption "y-coordinate is near-zero" (the *old* convention, where
the wing lay flat in y). Under the new convention the wing is flat in **z** (span along y), so the xz
projection collapses the span → coincident markers → `d_nn=0 → dv=0 → zero force`. **Fixed in the
fork** (`98d46a62`) by computing `d_nn` in **full 3D** (orientation-invariant; reduces to the in-plane
spacing regardless of the flat axis). The pin was bumped `d4bf9829 → 98d46a62` and the image rebuilt.
This is a genuine solver bug the axis refactor *exposed* — it co-lands with T2a (same re-run cycle),
does not alter force *magnitude* reconstruction for the old convention, and is verified by the
non-zero-force re-run.
