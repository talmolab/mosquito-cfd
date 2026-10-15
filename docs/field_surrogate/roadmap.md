# Field surrogate (Stage 2) — implementation roadmap

Umbrella tracking doc for the **field-based surrogate**: a latent-dynamics model
(zₜ, kinematicsₜ) → (zₜ₊₁, forcesₜ), the DreamerV3-style world-model architecture from the
2026-04-28 lab meeting deck (`content/04-mlsurrogates.md` in the vault), whose encoder and dynamics
architectures are decided empirically by F3's bake-off (see "F3 framing decision" below) rather than
fixed up front. Same conventions as `docs/force_surrogate/roadmap.md` (this doc's sibling,
"Track B"): OpenSpec changes authored just-in-time per PR, GitHub issues drafted lazily, status checkboxes here
are the source of truth.

**Relationship to Track B:** this was originally scoped as funded-only, gated on an NVIDIA H100
award (`docs/force_surrogate/roadmap.md` CC-6 / "Out of scope", now both superseded — see the note
there dated 2026-08-07). Not waiting for that award. This roadmap starts the work on the existing
Salk RunAI `talmo-lab` A40 allocation and the local RTX A5000, same hardware Track B used.

**Sequencing note (updated 2026-08-10):** Track B's frozen coarse corpus and the fine corpus's
committed decks carried a wing-hinge geometry defect since the 2026-07-02 axis-convention refactor
(fixed by `fix-force-surrogate-sweep-hinge`), which also found the fine corpus's prior cluster
regeneration (submitted via the already-merged `add-fine-grid-corpus-full` scaffolding; the actual
Argo job ran 2026-08-04→08-07) ran against that defect and needs re-running regardless of any
Stage-2 decision. That already-run job cost ~54 A40-GPU-hours (now sunk, invalidated by the hinge
defect); the pilot report's own pre-run projection for a full 27-config fine-grid regeneration is
~61 hours (~2.55 days) — the two numbers describe different things (actual sunk cost vs. a
separate projection), not a discrepancy. Rather than pay for a second full regeneration later,
**F1's standalone field-capture pilot below is superseded**: the corrected fine-grid re-run is
bundled with full 27-config field capture directly, in `add-fine-corpus-field-capture` — an
explicit, deliberate deviation from this roadmap's own
CC-F3 "measure storage on a small pilot before committing to the full corpus" default, decided
with the user rather than assumed. That follow-on change measures storage from the real run instead
of a preceding pilot (see its proposal's "Deviation and scoping decisions"). It must also re-confirm
`dt=5e-4` numerical stability against the corrected hinge before submitting — the fine-grid pilot's
stability result was measured against the buggy midspan pivot's roughly-half-length rotation arm and
is not confirmed to transfer (see `docs/force_surrogate/fine-grid-pilot-report.md`'s geometry note).
`talmo-lab`'s RunAI quota was already at 171.74% allocation during the fine-grid force pilot
(`docs/force_surrogate/fine-grid-pilot-report.md`) — still confirm quota headroom before submitting.

> **Resolved 2026-09-19 — it did not transfer.** The corrected-hinge fine-grid run (this note's own
> `add-fine-corpus-field-capture` regeneration) was submitted at the pilot's `ns.cfl = 0.3` and
> confirmed, per issue #92, that the pilot's stability result did **not** transfer to the corrected
> geometry: 15 of 27 configs were CFL-limited, truncating mid-wingbeat. The fix
> (`add-fine-corpus-run-verification`, `ns.cfl = 0.3 → 0.6`) is merged and the corpus has since been
> regenerated and re-run at `ns.cfl = 0.6`; `examples/prelim_sweep_fine/`'s 27 configs are now all
> stable at the validated `dt = 5e-4` with zero CFL limiting, confirmed by the post-run acceptance
> gate.

---

## Vision

Extend Track B's kinematics→force map into the architecture the NVIDIA Academic Grant draft
proposal describes (`nvidia-proposal/draft/proposal.md` in the vault — **unsubmitted**: the program
closed before submission and we are waiting for it to reopen): a latent state, plus a dynamics model
that rolls it forward — the piece that makes an eventual
RL-in-the-loop (MJX-Warp) training run possible, since a latent state is what would let the surrogate carry
flow history the wing's commanded motion alone does not determine. **Whether that history matters
on our data is an empirical question F3 answers**, not an assumption.

### Still the *not-yet-in-the-RL-loop* surrogate

| | **Track B (done)** | **This roadmap (Stage 2)** | **Funded / long-term** |
|---|---|---|---|
| Mapping | kinematics(+phase) → force coefficients | (z,k)→(z',forces), z from F3's winning arm | same, + RL-in-loop |
| Inputs | scalar kinematic parameters | kinematics window; CFD field snapshots (velocity + ∇p) | + multi-agent swarm scenes |
| Model | small PhysicsNeMo MLP | F3 bake-off: windowed MLP / `Mesh_Reduced` + `Sequence_Model` / DoMINO | + MJX-Warp deployment, ablations |
| In RL loop | no | no (this roadmap trains the surrogate only) | yes |

Framing carried over from Track B CC-4 (scientific honesty): report what this pipeline actually
achieves at each PR, not the hoped-for end-state.

## F3 framing decision (2026-10-15)

### The finding: stock DoMINO is geometry → fields, not fields → latent

Verified against `NVIDIA/physicsnemo` — `physicsnemo/models/domino/model.py` last changed at
`cbb1bf1` (2026-05-04), unchanged between the 2026-09-22 check and this decision:

- `DoMINO.forward()` reads geometry (`geometry_coordinates`, the `sdf_*` grids, `surface_mesh_*`),
  sampled positions (`volume_mesh_centers`, `pos_*`) and `global_params_*`, and **returns**
  `(volume_output, surface_output)`. No flow-field value is an input. `GeometryRep` is called as
  `geo_rep_volume(geo_centers_vol, p_grid, sdf_grid)` — it encodes geometry.
- The DoMINO paper (arXiv 2501.13350) abstract: *"DoMINO is a point cloud-based ML model that uses
  local geometric information to predict flow fields on discrete points."*
- PhysicsNeMo's transient DoMINO example (`transient_conjugate_heat_transfer_tank_fill`) is still
  geometry → fields: static geometry from the first timestep plus global parameters, all future
  timesteps in one forward pass, "no autoregressive rollout".

So the former F3 row, "DoMINO encoder: field snapshot → latent z", describes no DoMINO
configuration. **Provenance of the error:** the 2026-04-28 lab deck's slide 31 used DoMINO
*correctly* — encoder input = the wing surface point cloud (IB markers) — while its slide 29 caption
said "encoder compresses CFD snapshots → z". The June grant draft merged the two into one
self-contradicting sentence ("a DoMINO encoder (PhysicsNeMo's geometry neural operator) that
compresses each CFD flow state into a latent vector z"), and this roadmap inherited the flow-field
reading. The January 2026 slide deck (`eberrigan_physics_nemo_for_rl_proposal.pdf`, byte-identical
to `slides.pdf`) never mentions DoMINO.

**Why DoMINO-as-field-predictor alone is not the answer either:** a flapping wing passes through the
same pose twice per beat with different flow, so a pose → field map is ill-posed. Adding phase and
the config parameters as global parameters makes it well-posed **for fixed periodic kinematics**, but
once the commanded kinematics change mid-flight — an explicit goal after hover — the wake was built by
the previous command and there is no parameter vector to condition on. DoMINO has no state slot.

**PhysicsNeMo does ship a field → latent encoder:** `physicsnemo/models/mesh_reduced/` (last changed
`8e81b62`, 2026-02-11) — `Mesh_Reduced` (PbGMR-GMUS, arXiv 2201.09113), whose `encode()` takes node
field values to a latent at pivotal nodes, plus `Sequence_Model`, which rolls a latent sequence
forward with an optional physical `context` vector. Worked example:
`examples/cfd/vortex_shedding_mesh_reduced/`. **Unverified at our scale:** that example is 1,699
nodes in 2D; our corpus is 256×128×256 ≈ 8.4 M cells. On our fixed Eulerian IB grid the graph is
built once, never rebuilt, which removes the "graph rebuild each step" objection
`ml-surrogate-notes.md` raised against graph models (that objection assumes a body-fitted mesh) —
an inference, not a measurement.

### The decision

1. **F3 is a three-arm bake-off**, not an architecture commitment. One harness, the same held-out
   configs, two metrics (force error vs. CFD; inference latency):
   - **Arm A — first:** Track B's MLP with a **kinematics window** in place of instantaneous
     parameters + phase. The baseline any field model must beat.
   - **Arm B:** `Mesh_Reduced` encoder + `Sequence_Model` latent dynamics, kinematics as `context`.
   - **Arm C:** DoMINO used as designed — wing pose + phase + config parameters → fields.

   This is the draft proposal's promised "DoMINO-vs-DeepONet ablation", widened by one arm and given
   an honest baseline.
2. **Go/no-go gate after arm A.** If arm A's held-out force error is within the corpus's own CFD
   uncertainty, the hover corpus has no hidden state to encode. That uncertainty must be **measured
   before the gate is applied, not assumed** — it is component-dependent (T3c GCI_fine: CF_normal
   3.7%, CF_chord 27.6%), so the gate is applied per component.
   Arms B and C are built only after arm A reports.
3. **Commanded-change configs.** The 27-config corpus is fixed periodic prescribed kinematics, so it
   cannot show whether a latent is needed once commands change. A handful (~3–5) of configs with a
   mid-run kinematics step are **designed in F3's change and submitted only after arm A** reports.
4. **No regeneration for pressure.** IAMReX stores pressure **nodally**
   (`NS_setup.cpp:376`, `Press_Type` on `TheNodeType`) and `gradp` cell-centered (`:386`); plotfiles
   carry cell-centered state, so our decks have `gradpx/y/z` and no `p`. In incompressible flow `p` is
   a function of `u` via the pressure Poisson equation and is fixed only up to a constant, so
   velocity + ∇p is the complete prognostic state plus the gauge-invariant term worth precomputing.
   Every **new** deck — starting with the commanded-change configs — sets
   `amr.derive_plot_vars = avg_pressure` (`NS_setup.cpp:494`; no deck in the repo sets it today),
   so pressure comes free whenever new CFD runs for another reason. A full-corpus regeneration just
   for it would add ≈ +76 GB (+13%) — derived from #112's measured 67.1 MB/field, not measured.
5. **Harpreet Sethi deck waits for arm A's result**, then asks whether `Mesh_Reduced` is the right
   tool on a fixed Eulerian IB grid and whether it has been run at 10⁶–10⁷ nodes. This replaces the
   long-open "DoMINO for rapid motion" question (`ml-surrogate-notes.md` Open Question #2).
6. **The draft proposal's Stage-2 text is corrected when the program reopens**, folding in arm A's
   result and Harpreet's feedback, so it is rewritten once.
7. **F2's output carries forward.** `FieldSnapshot` / `PointCloud` / `FieldCorpus` serve all three
   arms unchanged (`PointCloud.coords` / `.values` are `Mesh_Reduced`'s `position_mesh` / `x`).
   `to_domino_volume` is kept for arm C but is **known incomplete**: `forward()` also reads six keys
   absent from `GEOMETRY_HALF_KEYS` (`pos_volume_closest`, `pos_volume_center_of_mass`,
   `pos_surface_center_of_mass`, `surface_mesh_neighbors`, `surface_neighbors_normals`,
   `surface_neighbors_areas`), and its `grid` is the full volume where stock DoMINO's is a small
   SDF bounding grid (#112). Both are arm C's to fix.

## Inputs and outputs

- **Input:** the same validated flapping-wing setup and sweep grid as Track B
  (`examples/prelim_sweep_fine/`, 27-config Aedes grid) — but with field output turned on for at
  least a pilot subset. **Force labels are already solved by Track B — do not recompute them.**
  Reuse the IB-particle CSV → coefficient pipeline (Track B PR1/PR4 helpers) for `F_t`; this
  roadmap only adds the field half.
- **Intermediate:** AMReX plotfiles (`plt00100`, ...) per pilot/corpus config, read via a `yt`-based
  extractor into either a uniform-grid array or an unstructured point cloud (decision: F1/F2).
- **Output:** F3's bake-off result (which arm, if any, beats a kinematics window), the winning
  latent-dynamics model, `metrics.json`, and a Stage-2 evidence figure comparing this surrogate against Track B's MLP and against CFD on
  held-out configurations (mirrors Track B CC-4).

## Hardware

- **CFD (field-capture pilot + corpus):** Salk RunAI **A40** (same `:fp64` container Track B uses;
  only `amr.plot_int` / `ns.init_iter` change in the decks — no rebuild expected).
- **Training:** local **RTX A5000** (24 GB), same as Track B, unless F1's storage/volume projection
  says otherwise (open question — flag if field-snapshot volume doesn't fit local disk/VRAM budget).

---

## Cross-cutting concerns

Numbered `CC-F*` to avoid colliding with Track B's `CC-1..7` (this doc's sibling); Track B's CC-1
(reproducibility), CC-2 (cluster-free fixtures), CC-3 (force normalization), CC-4 (scientific
honesty), and CC-5 (pure-data convention) all apply here unchanged and are not re-stated.

### CC-F1. `ns.init_iter = 2` is required for any field-capture deck — this is not optional.
**Known defect, already hit once in this repo:** with `ns.init_iter = 0`, IAMReX writes
`x_velocity = 0` to every plotfile — the velocity field is computed internally but silently never
persisted (`examples/flapping_wing/RESULTS.md`, "Note on the velocity field"). Forces are
unaffected (they use the interpolated marker velocity, not the plotfile field), which is exactly
why Track B's force-only decks never needed to notice this. Any F1+ deck **must** set
`ns.init_iter = 2` and F1 must assert the resulting plotfile's velocity field is non-zero
(`u` range check, mirroring the flapping-wing RESULTS.md confirmation: `u ∈ [-9.98, +1.90]`)
before trusting any of it as training data.

### CC-F2. Reuse the existing field reader — do not build one from scratch.
`ml-surrogate-notes.md` (2026-02-25) assumed "PhysicsNeMo has no native AMReX reader... a data
pipeline to PhysicsNeMo is not yet built." That's stale: `mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box`
(a `yt`-based Eulerian-box extractor, built for the T3b LEV work) already reads this repo's
plotfiles. F2 adapts/extends it rather than writing a new reader; a synthetic plotfile fixture for
CI already exists too (issue #33, closed — "committed synthetic AMReX plotfile fixture for CI
coverage of the yt adapter").

### CC-F3. Storage budget must be measured before committing to a full corpus, not assumed.
The `6–32 TB for 20 sims` figure in `ml-surrogate-notes.md` predates the fine 256×128×256 grid and
the AMR level count actually used — it is not a safe planning number here. F1's pilot must produce
a fresh per-config, per-`plot_int`-interval storage measurement (mirroring how Track B's fine-grid
pilot measured `s/step` before projecting the full-corpus cost) and choose:
  - **subsampling interval** (`amr.plot_int`) — balance temporal resolution against storage;
  - **AMR level handling** — interpolate all levels onto a uniform base grid (simpler, loses
    near-wing resolution) vs. keep the native multi-level structure as an unstructured point cloud
    (preserves resolution, maps onto DoMINO's point-cloud input more naturally, per
    `ml-surrogate-notes.md` "Moving Boundary Handling").

> **Superseded 2026-08-10 (see the Sequencing note above):** `add-fine-corpus-field-capture`
> measures storage from the full corrected 27-config run itself,
> not a preceding small pilot — a deliberate, user-approved deviation from this CC's own default,
> made necessary by that corpus needing to be regenerated regardless of the field-capture decision.

> **Storage measurement (2026-09-19, from the `add-fine-corpus-run-verification` re-run):** at
> `amr.plot_int = 100` (every 100 steps), the full 27-config corpus writes **≈0.58 TB of
> plotfiles** (441/369/324 plotfiles across the three `frequency_fstar`-grouped `max_step` values
> {4706, 4000, 3478}, ≈513 MB each) plus **≈0.23 TB of AMReX checkpoints** (restart-only, not
> field-surrogate training input) — **≈0.84 TB total** per full run. This is insensitive to the
> `ns.cfl` change itself (`ns.cfl` affects the realized timestep, not `plot_int`'s step-count
> cadence or per-plotfile size); the figure is not directly comparable to the earlier
> `add-fine-corpus-field-capture` sizing note above, which predated this corpus's second
> (CFL-driven) regeneration.

### CC-F4. Cluster-free fixtures for everything downstream of raw plotfiles.
Same convention as Track B CC-2: F2 (field reader) and F3 (bake-off arms) must be tested against the
committed synthetic plotfile fixture, not real cluster output — no RunAI, no GPU, no real
plotfiles in CI.

---

## PR / issue split

Status: ⬜ not started/superseded | 🟡 in flight | ✅ merged.

| # | OpenSpec change-id (proposed) | Scope | Env | Status |
|---|---|---|---|---|
| F1 | `add-field-surrogate-capture-pilot` | ~~Small (2–3 config) field-capture pilot~~ **Superseded 2026-08-10** — subsumed by the full-corpus field-capture run in `add-fine-corpus-field-capture` (see the Sequencing note above). Original scope: `ns.init_iter=2`, `amr.plot_int` on; assert non-zero velocity field (CC-F1); measure per-config storage at a few candidate `plot_int` intervals; go/no-go + subsampling recommendation for the full corpus (CC-F3). | cluster | ⬜ superseded |
| F2 | `add-field-surrogate-reader` | Adapt `stress_integral.extract_eulerian_box` into a general plotfile→array/point-cloud reader for encoder training input; tested against the existing synthetic plotfile fixture (CC-F2, CC-F4). | local | ⬜ |
| F3 | `add-field-surrogate-bakeoff` (was `add-field-surrogate-encoder`) | Three-arm bake-off (see "F3 framing decision"): arm A (windowed-kinematics MLP) first, then a measured-CFD-uncertainty go/no-go gate, then arm B (`Mesh_Reduced` + `Sequence_Model`) and arm C (DoMINO, geometry → fields). Also designs the ~3–5 commanded-change configs (with `avg_pressure`), submitted only after arm A. | A5000 (+ cluster for the new configs) | ⬜ |
| F4 | `add-field-surrogate-corpus-full` | Full-corpus field regeneration at F1's recommended subsampling/level policy, budgeted by F1's measured storage/time. **Re-scope after F3:** may be unnecessary if F3's gate finds no hidden state, or narrowed to the commanded-change configs. | cluster | ⬜ |
| F5 | `add-field-surrogate-dynamics` | Latent-dynamics model (zₜ, kinematicsₜ) → (zₜ₊₁, Fₜ) at production scale, architecture taken from F3's winning arm (DeepONet stays a candidate, not a commitment). Reuses Track B's force labels (`F_t`) unchanged — no force recomputation. | A5000 | ⬜ |
| F6 | `add-field-surrogate-evidence-figure` | Stage-2 evidence figure: predicted-vs-CFD on held-out configs, Stage-2 surrogate vs. Track B MLP vs. CFD (CC-4 honesty conventions carried over). | local | ⬜ |

**Dependency order:** F1 → F2 (can start in parallel once the fixture exists, cluster-free) → F3
(needs F2's reader + the fine corpus; arm A needs only Track B's labels) → F4 (only after F3's gate;
see its re-scope note) → F5 (needs F3's winning arm + Track B's existing force labels) → F6 (needs
F5's predictions). **F1 is superseded (see above); F2 onward now depend on
`add-fine-corpus-field-capture` for corpus data instead.**

## How to execute (per-PR loop)

Same as Track B: `/new-feature` per PR — feature branch → `/openspec:proposal` → `/review-openspec`
→ approval → `/openspec:apply` (TDD) → `/pre-merge-check`. Draft the GitHub issue first to
`c:\vaults\physics surrogate models\nvidia-proposal\github_issues\issue_<change-id>.md`, referencing
this roadmap row and the CC-F items it touches. Tick the status checkbox here on merge.

## Open questions (prioritized)

1. ~~**DoMINO for rapid motion**~~ **Resolved 2026-10-15** — moot: stock DoMINO is geometry →
   fields and cannot be the field encoder at all (see "F3 framing decision"). Replaced by #4 and #5.
2. **Storage/subsampling policy** (CC-F3) — no answer until F1 runs; do not pre-commit a `plot_int`
   value in F2/F3 design docs before F1's measurement exists.
3. **Does F5's latent-dynamics training need the pilot corpus (F1) or the full corpus (F4)?** —
   likely pilot-scale is enough to validate the training loop, full corpus needed for a trustworthy
   evidence figure (F6) — mirrors Track B's own coarse-grid-first, fine-grid-second sequencing.
   Confirm once F1 lands.
4. **What is the corpus's own CFD force uncertainty?** — F3's go/no-go gate is defined against it
   and it must be measured on this corpus, not assumed (T3c GCI_fine was CF_normal 3.7% but
   CF_chord 27.6%).
5. **Does `Mesh_Reduced` scale from 1,699 2-D nodes to ~8.4 M 3-D cells?** — unverified; the first
   question for Harpreet Sethi once arm A has a number.

## Out of scope (still deferred)

RL-in-the-loop (MJX-Warp PPO), multi-agent swarm scenes, multi-GPU scaling, the full LHS production
corpus. These remain genuinely H100-award-scale (RL training throughput, not the surrogate
architecture itself) — this roadmap trains and evaluates the Stage-2 surrogate, it does not put it
in an RL loop.
