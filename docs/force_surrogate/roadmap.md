# Force-surrogate (Track B) — implementation roadmap

Umbrella tracking doc for the **preliminary force-only surrogate** that produces the NVIDIA
Academic Grant *Evidence-of-Readiness* figure. This is the *only* place the full multi-PR
program lives. **OpenSpec changes are written just-in-time** when each PR is opened — not all
up front. **GitHub issues are drafted lazily** to
`c:\vaults\physics surrogate models\nvidia-proposal\github_issues\` as we approach each PR.
The status checkboxes here are the source of truth for what is done, in flight, and queued.

- **Vault plan / design (source of truth for *why*):** `c:\vaults\physics surrogate models\nvidia-proposal\planning\2026-06-05-nvidia-grant-proposal-plan.md` (Track B, B1–B6) and its design spec §9.
- **Hard cutoff:** ~**June 24, 2026**. **Upside only** — if any PR here slips past the cutoff, cut the figure and the proposal stands on the already-validated sphere/ellipsoid/flapping benchmarks. **Track B never gates submission.**

---

## Vision

A small **kinematics(+phase) → aerodynamic-force-coefficient** surrogate, trained on a bounded
local CFD corpus, yielding **one figure**: predicted-vs-CFD force coefficients (CF_x, CF_z, CF_m)
on **held-out kinematic configurations**, with a **Sane–Dickinson quasi-steady baseline overlay**
and an annotated **>1,000× inference-vs-CFD speedup** + validation RMSE. The figure proves the
data→surrogate→inference pipeline runs end-to-end on local hardware and that the NVIDIA
PhysicsNeMo stack is usable.

### This is the *easy* surrogate, not the funded one

| | **Track B (this roadmap)** | **Funded / long-term (Methods Stage 2)** |
|---|---|---|
| Mapping | instantaneous kinematics(+phase) → force coefficients | DoMINO encoder → latent **z**; dynamics net (zₜ, kinematics)→(zₜ₊₁, forces) |
| Inputs | scalar kinematic parameters | CFD **field snapshots** (velocity/pressure) |
| Model | small DeepONet / **MLP** | DoMINO + latent dynamics, hybrid physics losses, DoMINO-vs-DeepONet ablation |
| In RL loop | no | yes (MJX-Warp PPO) |

Per design §9: *"do not over-build pre-award: scaling, field-based DoMINO, and RL-in-loop are
what the H100 award funds."* Track B is a deliberately reduced proof-of-pipeline. Framing and the
CC-4 figure caption must keep it honest — readiness evidence, not the funded surrogate.

## Inputs and outputs

- **Input:** the validated flapping-wing setup — `examples/flapping_wing/inputs.3d.validation`,
  `wing.vertex`, container `ghcr.io/talmolab/mosquito-cfd:fp64` (IAMReX `7ece065d`) — plus a
  reduced kinematic sweep. **Force-only: `amr.plot_int = -1`** (no field plotfiles; forces come
  from the IB-particle CSV output — this sidesteps the velocity-field-in-plotfiles bug entirely).
- **Intermediate:** one IB-particle force CSV per sweep config (A40 runs).
- **Output:** `examples/prelim_sweep/dataset.parquet` (one row per (kinematics vector, time) →
  CF_x, CF_z, CF_m + raw Fx/Fy/Fz), a trained surrogate + `metrics.json`, and
  `examples/prelim_sweep/figures/evidence_figure.png`.

## Hardware

- **CFD (sweep):** Salk RunAI **A40** (FP64 container). ~2.4 min per coarse-grid wingbeat.
- **Training:** **local RTX A5000** (24 GB, FP32/TF32) — *not* RunAI (RunAI is A40-only).

---

## Cross-cutting concerns

These are program invariants — design them into the foundation (PR1), don't retrofit.

### CC-1. Reproducibility / provenance.
Pin the container by **digest** (not just `:fp64`). Every stage (sweep run, dataset build,
training) emits a `run_metadata.json`: container digest, IAMReX commit, inputs hash, git SHA,
host, and a caller-supplied timestamp (never wall-clock-at-runtime baked into logic). Reruns
reproduce bit-for-bit given the same seed.

**Follow-up (PR3 consumer, not PR1):** `docker.yml` publishes images by tag only and does not
surface a `sha256:` digest. Add a step emitting `build.outputs.digest` to the CI job summary so
operators can pin surrogate runs by digest (the foundation wrapper already *requires* a digest).

### CC-2. Cluster-free reusable fixtures.
PR1 commits, under `tests/fixtures/`, a tiny **synthetic IB-particle CSV** (a few timesteps with
analytically known forces) and a **2-config micro-sweep**. Every test in PR2/PR4/PR6 runs against
these — **no RunAI, no GPU, no real plotfiles**. This is the fixture base the user asked for.

### CC-3. Single-source force normalization.
The `F_ref = q_tip · S` math (U_tip_max = 2π·f\*·φ_amp·r_tip; q_tip = ½ρU²; S = π/4·span·chord)
lives in **one tested helper** in PR1 and is reused by the extractor (PR4) and figure (PR6) —
never re-derived inline (PR1 refactors the existing inline copy in `generate_all_figures.py` to
use the helper). Regression-locked to the formula values at the validated 70° point
(F_ref ≈ 624.79; RESULTS.md shows the rounded F_ref = 624.8), at `rtol=1e-3`.

### CC-4. Scientific honesty.
Evaluate on **held-out configurations**, not just held-out timesteps within a run (so we measure
the kinematics→force map, not within-run interpolation). The figure overlays the **Sane–Dickinson
quasi-steady baseline** so it shows the surrogate ≥ the analytic model. The caption frames it as
*pipeline readiness on coarse-grid forces*, **not** validated aerodynamics (coarse 64×32×64; the
IAMReX diffused-IB force underestimate, ~2.4×, still applies).

### CC-5. Pure-data convention.
The dataset carries **dimensionless coefficients + raw forces**; kinematic parameters in
documented units; one `dataset.units.json` sidecar (mirrors the circumnutation units-sidecar
convention). No silent unit mixing.

### CC-6. Scope guard (force-only).
**No** velocity-field/plotfile reading, **no** AMReX→PhysicsNeMo field reader, **no** RL
integration, **no** DoMINO/latent-dynamics. `amr.plot_int = -1` throughout. These are the funded
deliverables and are explicitly out of scope here.

### CC-7. Reynolds handling in the sweep (decide in PR2).
The validated ν\* = 0.115 sets Re≈100 at the 70° point. Changing stroke amplitude / frequency
changes U_tip and therefore Re unless ν\* is rescaled per config. PR2 (sweep-config) must choose
and document one policy: **(a) hold ν\* fixed** (Re varies across the sweep — simpler, surrogate
sees a Re range) or **(b) hold Re fixed** (rescale ν\* per config — cleaner kinematics isolation).
Record the choice in the dataset metadata either way.

---

## Sweep design

3-parameter grid, **biologically anchored on *Aedes aegypti*** (Bomphrey 2017), grounded in the
documented pre-APEX ranges (`cfd-approach.md`):

| Parameter | Levels | Grounding |
|---|---|---|
| Stroke amplitude φ | **{35, 45, 55}°** | brackets Bomphrey 39°±4°; within pre-APEX 35–50° |
| Dimensionless frequency f\* | **{0.85, 1.0, 1.15}** | ≡ ~610 / 717 / 824 Hz (f\*=1.0 ≡ Bomphrey 717 Hz); within pre-APEX 600–800 Hz |
| Pitch amplitude α | **{30, 45, 60}°** | within pre-APEX 30–60°; centred on validated 45° |

= **27 configs** (~65 min total A40 wall-clock at ~2.4 min each). **Hold out ~6 configs** for the
predicted-vs-CFD figure. Phase lead fixed at 90°, deviation 0° (validated values).

> **Provenance note.** The validated demo run uses a **70°** stroke, which is *not* the mosquito
> value — it is a generic large-amplitude demo (RESULTS.md loosely attributes it to van Veen 2022,
> which is a sweep study, not a 70° prescription). This sweep deliberately re-anchors on the Aedes
> 39° (Bomphrey). A one-line RESULTS.md clarification of the 70°-vs-39° distinction is a nice-to-have
> follow-up.

### Verified source numbers (provenance for this program)

| Quantity | Value | Source | Location |
|---|---|---|---|
| Aedes flap frequency | 717 ± 59 Hz | Bomphrey 2017 | vault `references.md`; repo `timestep_cfl_analysis.md:25` |
| Aedes stroke amplitude | 39° ± 4° | Bomphrey 2017 | repo `timestep_cfl_analysis.md:24` |
| Aedes wing length R | 3.0 mm | Bomphrey 2017 | repo `timestep_cfl_analysis.md:23` |
| Validated baseline kinematics | φ 70°, α 45°, f\* 1.0, dev 0°, phase-lead 90° | this repo | `inputs.3d.validation` (`kinematics_*`), `RESULTS.md:44–48` |
| Force reference | F_ref = 624.8 (q_tip 265.2 × S 2.356; U_tip 23.0) | this repo | `RESULTS.md:100–103`, `generate_all_figures.py:236–241` |
| Grid / dt / steps / ν\* | 64×32×64 / 5e-4 / 2000 / 0.115 | this repo | `inputs.3d.validation`, `RESULTS.md:70–76` |
| Diffused-IB force underestimate | ~2.4× (Cd 0.45 vs 1.09, Re=100 sphere) | this repo | `RESULTS.md:118` |

Citations: **Bomphrey et al. 2017**, *Nature* 544:92–95, DOI 10.1038/nature21727. **van Veen et al.
2022**, *J. Fluid Mech.* 936:A3, DOI 10.1017/jfm.2022.31.

---

## PR / issue split

Status: ⬜ not started | 🟡 in flight | ✅ merged. Each row = one PR = one OpenSpec change-id =
one GitHub issue. Issues + OpenSpec changes authored just-in-time.

| # | OpenSpec change-id | Scope | Env | Status |
|---|---|---|---|---|
| 1 | `add-force-surrogate-foundation` | `mosquito_cfd` surrogate-prep module skeleton; force-coefficient/normalization helpers (CC-3) **+ refactor the inline `F_ref` in `examples/flapping_wing/generate_all_figures.py` to source from the helper (closes CC-3 DRY)**; **reusable cluster-free fixtures** (CC-2); module constants; `run_metadata` + `units.json` sidecar conventions (CC-1, CC-5). Local, TDD. [PR #2](https://github.com/talmolab/mosquito-cfd/pull/2) | local | ✅ |
| 2 | `add-force-surrogate-sweep-config` | Sweep generator → 27 input files over the φ×f\*×α grid; `amr.plot_int=-1`; **document the Re policy (CC-7)**; tested against fixtures. | local | ⬜ |
| 3 | `add-force-surrogate-sweep-runner` | RunAI A40 batch runner looping the sweep through the pinned `:fp64` container; per-config output dir; `run_metadata` per run; dry-run/mocked test path. | cluster | ⬜ |
| 4 | `add-force-surrogate-dataset` | `scripts/extract_forces.py`: IB-particle CSV → coefficients (PR1 helper) → tidy `dataset.parquet` + `units.json`; tested against fixtures. | local | ⬜ |
| 5 | `add-force-surrogate-train` | kinematics(+phase)→force regressor; **PhysicsNeMo-primary, PyTorch DeepONet/MLP fallback** (de-risk PhysicsNeMo early; hard fallback checkpoint ~Jun 18); held-out-**config** split (CC-4); seeded; `metrics.json`; wandb. | A5000 | ⬜ |
| 6 | `add-force-surrogate-evidence-figure` | Predicted-vs-CFD scatter (CF_x/CF_z/CF_m) + **Sane–Dickinson baseline overlay** + speedup/RMSE annotation; ≥200 dpi; honest caption (CC-4). | local | ⬜ |

**Dependency order:** PR1 → PR2 → PR3 → PR4 → PR5 → PR6. PR4 can be built and fully tested against
fixtures **before** PR3's real corpus exists (CC-2), so PR3 (cluster) and PR4 (local) can proceed in
parallel once PR1+PR2 land. PR5 needs PR4's dataset; PR6 needs PR5's predictions + PR1's helpers.

---

## Standards → acceptance criteria (every PR)

- **Reproducibility:** `run_metadata` + pinned digest + explicit seeds; rerun → identical (CC-1).
- **Scientific accuracy:** coefficient math regression-tested vs RESULTS (CC-3); held-out-**config**
  evaluation + Sane–Dickinson baseline (CC-4); sweep numbers sourced (above).
- **Testability:** TDD, tests cite their OpenSpec spec scenario, cluster-free fixtures (CC-2),
  coverage reported.
- **Traceability:** one OpenSpec change + one GitHub issue per PR; roadmap checkbox updated on merge.
- **Documentation:** google-style docstrings; module docs; `RESULTS.md`/`METHODS.md` updates;
  `units.json` sidecar.

## How to execute (per-PR loop)

**`/new-feature` is the orchestrator for each PR.** It drives the full inner workflow —
feature branch (named `<change-id>`) → codebase exploration → clarifying questions →
`/openspec:proposal` scaffold (validated `--strict`) → `/review-openspec` → user approval →
`/openspec:apply` (TDD) → `/pre-merge-check`. The Claude dev commands `tdd`,
`lint`/`fix-formatting`, `coverage`, and `review-pr` are invoked *within* that flow, not run
standalone. The steps below wrap `/new-feature` with the issue-drafting and archive bookkeeping.

1. Pick the next ⬜ row.
2. Draft the GitHub issue body to `c:\vaults\physics surrogate models\nvidia-proposal\github_issues\issue_<change-id>.md` (reference this roadmap row, the CCs it touches, the sourced numbers) and open it.
3. Run **`/new-feature`** with the PR scope + issue reference. It creates the `<change-id>` branch, authors the OpenSpec change just-in-time (`proposal.md`, optional `design.md` → `docs/superpowers/specs/`, `tasks.md`, `specs/<capability>/spec.md`), runs `/review-openspec`, gets your approval, TDD-implements via `/openspec:apply`, and runs `/pre-merge-check` to open the PR linking issue + change-id.
4. After merge, `/openspec:archive <change-id>`.
5. Tick the status checkbox in this roadmap.

## Out of scope (funded work — not this program)

Velocity/pressure field reading, AMReX→PhysicsNeMo field reader, DoMINO encoder + latent dynamics,
RL-in-loop (MJX-Warp PPO), the full LHS production corpus, multi-GPU scaling, medium/fine-grid
validation. These are H100-award deliverables.
