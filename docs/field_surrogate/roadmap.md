# Field surrogate (Stage 2) — implementation roadmap

Umbrella tracking doc for the **field-based surrogate**: DoMINO encoder over CFD flow-field
snapshots → latent **z**; latent-dynamics model (zₜ, kinematicsₜ) → (zₜ₊₁, forcesₜ), the
DreamerV3-style world-model architecture from the 2026-04-28 lab meeting deck (`content/04-mlsurrogates.md`
in the vault). Same conventions as `docs/force_surrogate/roadmap.md` (this doc's sibling, "Track B"):
OpenSpec changes authored just-in-time per PR, GitHub issues drafted lazily, status checkboxes here
are the source of truth.

**Relationship to Track B:** this was originally scoped as funded-only, gated on an NVIDIA H100
award (`docs/force_surrogate/roadmap.md` CC-6 / "Out of scope", now both superseded — see the note
there dated 2026-08-07). Not waiting for that award. This roadmap starts the work on the existing
Salk RunAI `talmo-lab` A40 allocation and the local RTX A5000, same hardware Track B used.

**Sequencing note (updated 2026-08-10):** Track B's frozen coarse corpus and the fine corpus's
committed decks carried a wing-hinge geometry defect since the 2026-07-02 axis-convention refactor
(fixed by `fix-force-surrogate-sweep-hinge`), which also found the fine corpus's prior cluster
regeneration (`add-fine-grid-corpus-full`, in flight as of 2026-08-07) ran against that defect and
needs re-running regardless of any Stage-2 decision. Rather than pay for a second ~54-A40-hour
fine-grid regeneration later, **F1's standalone field-capture pilot below is superseded**: the
corrected fine-grid re-run is bundled with full 27-config field capture directly, in the follow-on
change to `fix-force-surrogate-sweep-hinge` — an explicit, deliberate deviation from this roadmap's
own CC-F3 "measure storage on a small pilot before committing to the full corpus" default, decided
with the user rather than assumed. That follow-on change measures storage from the real run instead
of a preceding pilot (see its proposal's "Deviation and scoping decisions"). `talmo-lab`'s RunAI
quota was already at 171% allocation during the fine-grid force pilot
(`docs/force_surrogate/fine-grid-pilot-report.md`) — still confirm quota headroom before submitting.

---

## Vision

Extend Track B's kinematics→force map into the architecture the funded proposal actually described:
an encoder that compresses real CFD flow-field snapshots (not just scalar kinematics) into a latent
state, plus a dynamics model that rolls that latent state forward — the piece that makes an eventual
RL-in-the-loop (MJX-Warp) training run possible, since the encoder is what lets the surrogate see
the flow, not just the wing's commanded motion.

### Still the *not-yet-in-the-RL-loop* surrogate

| | **Track B (done)** | **This roadmap (Stage 2)** | **Funded / long-term** |
|---|---|---|---|
| Mapping | kinematics(+phase) → force coefficients | field snapshot → z; (z,k)→(z',forces) | same, + RL-in-loop |
| Inputs | scalar kinematic parameters | CFD field snapshots (velocity/pressure) | + multi-agent swarm scenes |
| Model | small PhysicsNeMo MLP | DoMINO encoder + DeepONet dynamics | + MJX-Warp deployment, ablations |
| In RL loop | no | no (this roadmap trains the surrogate only) | yes |

Framing carried over from Track B CC-4 (scientific honesty): report what this pipeline actually
achieves at each PR, not the funded end-state. In particular, **DoMINO's fitness for rapidly moving
geometry (insect-wing tip speeds) is an unverified claim** (`ml-surrogate-notes.md`, "Open Questions"
#2) — F3 below is the first empirical test of it, not a foregone conclusion.

## Inputs and outputs

- **Input:** the same validated flapping-wing setup and sweep grid as Track B
  (`examples/prelim_sweep_fine/`, 27-config Aedes grid) — but with field output turned on for at
  least a pilot subset. **Force labels are already solved by Track B — do not recompute them.**
  Reuse the IB-particle CSV → coefficient pipeline (Track B PR1/PR4 helpers) for `F_t`; this
  roadmap only adds the field half.
- **Intermediate:** AMReX plotfiles (`plt00100`, ...) per pilot/corpus config, read via a `yt`-based
  extractor into either a uniform-grid array or an unstructured point cloud (decision: F1/F2).
- **Output:** a trained DoMINO encoder + DeepONet latent-dynamics model, `metrics.json`, and a
  Stage-2 evidence figure comparing this surrogate against Track B's MLP and against CFD on
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

> **Superseded 2026-08-10 (see the Sequencing note above):** the follow-on change to
> `fix-force-surrogate-sweep-hinge` measures storage from the full corrected 27-config run itself,
> not a preceding small pilot — a deliberate, user-approved deviation from this CC's own default,
> made necessary by that corpus needing to be regenerated regardless of the field-capture decision.

### CC-F4. Cluster-free fixtures for everything downstream of raw plotfiles.
Same convention as Track B CC-2: PR2 (field reader) and PR3 (encoder) must be tested against the
committed synthetic plotfile fixture, not real cluster output — no RunAI, no GPU, no real
plotfiles in CI.

---

## PR / issue split

Status: ⬜ not started | 🟡 in flight | ✅ merged.

| # | OpenSpec change-id (proposed) | Scope | Env | Status |
|---|---|---|---|---|
| F1 | `add-field-surrogate-capture-pilot` | ~~Small (2–3 config) field-capture pilot~~ **Superseded 2026-08-10** — subsumed by the full-corpus field-capture run in the follow-on change to `fix-force-surrogate-sweep-hinge` (see the Sequencing note above). Original scope: `ns.init_iter=2`, `amr.plot_int` on; assert non-zero velocity field (CC-F1); measure per-config storage at a few candidate `plot_int` intervals; go/no-go + subsampling recommendation for the full corpus (CC-F3). | cluster | ⬜ superseded |
| F2 | `add-field-surrogate-reader` | Adapt `stress_integral.extract_eulerian_box` into a general plotfile→array/point-cloud reader for encoder training input; tested against the existing synthetic plotfile fixture (CC-F2, CC-F4). | local | ⬜ |
| F3 | `add-field-surrogate-encoder` | DoMINO encoder training scaffold: field snapshot → latent **z** (64–256 dim). Trained first at pilot scale (F1's small corpus) to get an early, honest read on the open "DoMINO for rapidly-moving geometry" question (CC-F5) before committing to the full corpus. | A5000 | ⬜ |
| F4 | `add-field-surrogate-corpus-full` | Full-corpus field regeneration at F1's recommended subsampling/level policy, budgeted by F1's measured storage/time. | cluster | ⬜ |
| F5 | `add-field-surrogate-dynamics` | DeepONet latent-dynamics model: (zₜ, kinematicsₜ) → (zₜ₊₁, Fₜ). Reuses Track B's force labels (`F_t`) unchanged — no force recomputation. | A5000 | ⬜ |
| F6 | `add-field-surrogate-evidence-figure` | Stage-2 evidence figure: predicted-vs-CFD on held-out configs, Stage-2 surrogate vs. Track B MLP vs. CFD (CC-4 honesty conventions carried over). | local | ⬜ |

**Dependency order:** F1 → F2 (can start in parallel once the fixture exists, cluster-free) → F3
(needs F1's pilot data + F2's reader) → F4 (only after F1's go/no-go + F3's pilot-scale training
gives an early skill read) → F5 (needs F3's encoder + Track B's existing force labels) → F6 (needs
F5's predictions). **F1 is superseded (see above); F2 onward now depend on the follow-on change to
`fix-force-surrogate-sweep-hinge` for corpus data instead.**

## How to execute (per-PR loop)

Same as Track B: `/new-feature` per PR — feature branch → `/openspec:proposal` → `/review-openspec`
→ approval → `/openspec:apply` (TDD) → `/pre-merge-check`. Draft the GitHub issue first to
`c:\vaults\physics surrogate models\nvidia-proposal\github_issues\issue_<change-id>.md`, referencing
this roadmap row and the CC-F items it touches. Tick the status checkbox here on merge.

## Open questions (prioritized)

1. **DoMINO for rapid motion** (CC-F5) — still unverified; F3's pilot-scale training is the first
   real signal, not before.
2. **Storage/subsampling policy** (CC-F3) — no answer until F1 runs; do not pre-commit a `plot_int`
   value in F2/F3 design docs before F1's measurement exists.
3. **Does F5's latent-dynamics training need the pilot corpus (F1) or the full corpus (F4)?** —
   likely pilot-scale is enough to validate the training loop, full corpus needed for a trustworthy
   evidence figure (F6) — mirrors Track B's own coarse-grid-first, fine-grid-second sequencing.
   Confirm once F1 lands.

## Out of scope (still deferred)

RL-in-the-loop (MJX-Warp PPO), multi-agent swarm scenes, multi-GPU scaling, the full LHS production
corpus. These remain genuinely H100-award-scale (RL training throughput, not the surrogate
architecture itself) — this roadmap trains and evaluates the Stage-2 surrogate, it does not put it
in an RL loop.
