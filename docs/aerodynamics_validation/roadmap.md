# Aerodynamics validation — program roadmap

Tier-by-tier program to turn the mosquito-CFD benchmarks from *"physically plausible after a
hand-applied correction factor"* into **validated aerodynamics** — forces that match canonical
literature **without** an ad-hoc scaling fudge, in a coordinate convention that matches insect
biomechanics. Authored with the `roadmap-driven-pipeline` skill and revised after an adversarial
roadmap-level review (reconciliation log at the bottom). Each tier = one just-in-time OpenSpec
change (some tiers decompose into a small set), oracle-graded, started from a written handoff prompt.

- **Sibling roadmap:** [`docs/force_surrogate/roadmap.md`](../force_surrogate/roadmap.md) (Track B, the
  NVIDIA *Evidence-of-Readiness* surrogate). This roadmap is its CFD-fidelity counterpart.
- **Related in-flight OpenSpec change:** `add-apex-benchmarking` (the sphere/ellipsoid/flapping
  benchmarks live there; it carries an **unmet, blocking** acceptance criterion — "Cd within ±5% of
  literature" — plus the "~60% low Cd / under investigation" note that **Tier 1 closes**).

---

## ⚠️ Priority guard — BACKGROUND track, and ONLY Tier 1 is in-bounds before June 30

The **NVIDIA Academic Grant (~June 30, 2026) is the hard-deadline priority.** This roadmap **never
gates** the grant. The guard is precise about *which* tiers may run before submission:

- **Before June 30: only T1a/T1b may proceed.** They are **analysis-only** (no new simulations, no
  GPU, no operator cluster time) — they cannot compete with grant writing or with Track B's A40 corpus.
- **T2/T3/T4 are post-submission.** They require a solver refactor + cluster re-runs on the **same
  single-tenant Salk RunAI A40** and **same operator** that Track B and the grant need during the
  crunch — so they are explicitly out-of-bounds until after submission.
- **The T1→T2 co-land contingency (below) is itself deferred:** if T1a determines a solver-level fix is
  needed *before* June 30, the solver work still waits until after submission. T1's *finding* can land
  pre-deadline; T1's *re-run remediation*, if any, cannot.
- If validated numbers land before submission, the proposal's "Evidence of readiness" can quietly
  upgrade. If not, **nothing changes** — the grant stands on the existing benchmarks + the
  force-surrogate proof-of-concept exactly as drafted, with CFD kept instrumental (≤30% of hours).

---

## The finding that drives Tier 1

The diffused-IB force deficit is **not** under-resolution — it is a **force-extraction methodology
bug**. Canonical sphere, Re=100, literature Cd = **1.087** (Johnson & Patel 1999; Clift 1978 = 1.09):

| Grid | Cells | Computed Cd | vs literature |
|---|---|---|---|
| Coarse 128×64×64 | 0.5M | 0.503 | −54% |
| Medium 256×128×128 | 4.2M | 0.448 | **−59%** |

Refining the grid 8× moved Cd *away* from literature, so the ~2.4× deficit cannot be resolution.
[`flow_past_sphere/RESULTS.md`](../../examples/flow_past_sphere/RESULTS.md) reads the force as the raw
sum of `particle_real_comp3/4/5`, but the **diffused IB spreads force over a regularization kernel** —
the correct total force likely needs **kernel-weighted integration**, and the `comp`-field mapping must
be verified against IAMReX source.

> **Unverified premise (gated by T1a).** "Fixable on existing plotfiles" assumes the corrected force is
> reconstructable from *persisted* fields. This repo has direct precedent for IAMReX silently omitting
> an internally-computed field from plotfiles (the `x_velocity=0` / `ns.init_iter=0` defect,
> `flapping_wing/RESULTS.md`). So T1a must first confirm every field the correct reconstruction needs is
> present in the committed `plt10000` for **both** grids before the no-re-run promise is made.

---

## Oracle grounding

| Case | Oracle | Tier | Source |
|---|---|---|---|
| Flow past sphere (Re=100) | **Cd = 1.087 ± tol** — a true literature point | T1b | Johnson & Patel 1999; Clift 1978 (1.09) |
| Axis convention | force **invariance** under the documented transform, graded with the **T1b extractor on both** old- and new-convention runs (never new-extractor-new-geom vs old-extractor-old-geom) | T2a | issue #1 |
| Heaving ellipsoid (Re=100) | **self-consistency** (forces Δ<1% after t=7) **+ added-mass-fraction sanity** vs van Veen (15% lift / 31% drag). **Not** a literature Cd point. | T2b | METHODS.md Case 2; van Veen 2022 |
| Flapping wing — **plausibility gate** | CF_x, CF_z within the literature band **[0.5, 1.5]** **without** the correction factor | T2b/T3 | van Veen et al. 2022, *JFM* 936:A3 |
| Flapping wing — **validation** | **time-resolved** CF_x(t), CF_z(t) match van Veen Fig 3–4 (digitized curve: peak magnitude + peak-phase + curve RMSE within tol) | **T4** | van Veen 2022 Fig 3–4 |
| Pitching moment | **reported, not validated** — no van Veen moment number exists in-repo and the repo's axis convention is non-standard until T2a. CF_my is carried as a number, **not** graded against an oracle, until a literature moment target is sourced. | (deferred) | — |

> **Tolerances are stated per tier and are NOT loosened to make a tier pass** (skill invariant). Only
> tiers with a real number behind them are graded; the moment is explicitly *un-graded* until a target
> exists (an oracle with no number violates CC-V2 and is forbidden).

---

## Tiers

Status: ⬜ not started | 🟡 in flight | ✅ merged. Each tier = one tracking issue/EPIC; tiers that
decompose list their changes. Change-level sub-issues are filed **when the tier is decomposed**, not
upfront.

| # | Tier | Oracle / exit criterion | New sims? | Bounds |
|---|---|---|---|---|
| ✅ **T1a** ([#26](https://github.com/talmolab/mosquito-cfd/issues/26), PR [#27](https://github.com/talmolab/mosquito-cfd/pull/27)) | **Diagnosis** — read IAMReX diffused-IB source / consult upstream maintainer; determine the correct force reconstruction; **confirm every field it needs is in the committed `plt10000` for both grids.** Exit decides T1b's path. | **DONE → [`t1a-findings.md`](t1a-findings.md).** Spec delivered; `dv` is already in-solver (RESULTS' "missing dv" is false); fields verified present both grids. **Answer (split): IB-marker route NO** (accumulated `F_ib` not persisted, `loop_ns=2`; CSV discarded); **independent CV/stress integral route = re-run-free & computable from committed `u`+`gradp`, not yet executed** — it is the decisive H1 (extraction-bug)/H2 (flow-field-deficit) test. | No | **pre-June 30 OK** |
| ✅ **T1b** ([add-sphere-stress-cd](../../openspec/changes/archive/2026-06-24-add-sphere-stress-cd/)) | **Force-extraction fix** — principled field-based extractor in `mosquito_cfd.benchmarks` (`extract_sphere_cd(method="cv")`), replacing the ad-hoc ~2.4× factor. | **DONE → [t1a-findings §8](t1a-findings.md). H1 confirmed, NO re-run.** Periodic-duct CV balance on committed `plt10000`: coarse 1.342, medium 1.184, Richardson(p=2) **1.131 (+4.0%)**, isolated-equiv bracket **≈1.0–1.1** (±~1–5% viscous + unfitted order); field/marker = **2.64×**. **H2 excluded**; grid pair converges toward literature; residual = confined-array offset (H1′) + grid convergence. Literal 1.087±5% on one grid → T2b (refine/de-confine). | **No (analysis-only — the "Yes" branch)** | **pre-June 30 OK** |
| **T2a** | **Axis-convention refactor (issue #1) — solver + convention + doc, atomic** — `wing.vertex` span→y, BC/domain reshape (`z` wall→periodic), `WingKinematics.H` Euler, hinge coords, **`docs/coordinate-convention.md` + the `WingKinematics.H` docstring + the RESULTS frame-description all in the SAME change.** | Forces **invariant** under the documented transform, graded with the **T1b extractor on both sides**; no interim commit carries new-convention geometry with old-convention docs. | Yes (coarse) | **post-submission** |
| **T2b** | **Literature re-validation** — re-run sphere/ellipsoid/flapping (new convention, T1b extractor); grade against oracles; reconcile RESULTS **#3** (CF_x bound) & **#4** (CF_z mask) and the **METHODS.md IAMReX commit pin** (currently skewed: `c5f8e2a` vs fork `7ece065d`). | Sphere Cd=1.087; ellipsoid self-consistency + added-mass sanity; flapping CF in band without fudge; RESULTS reproducible. | Yes (coarse) | **post-submission** |
| **T3** | **Medium-grid flapping convergence** — author/run the **new-convention** 128×64×128 deck (the existing `inputs.3d.production` is old-convention/old-BCs and must be re-authored for the new BCs). Confirm CF grid-converged **coarse-new ↔ medium-new** and the LEV resolved. | CF converged within tol across the new-convention coarse↔medium pair; LEV present. | Yes (A40 unattended) | **post-submission** |
| **T4** | **Time-resolved force-curve validation** — digitize van Veen Fig 3–4; compare CF_x(t)/CF_z(t) waveforms (peak magnitude, peak phase, curve RMSE). This tier is what earns the word *"validated"* for the wing; T2b/T3 only establish in-band plausibility. | Curve RMSE + peak-phase within stated tol vs van Veen. | reuses T3 runs | **post-submission** |

**Sequencing.** T1a → T1b → T2a → T2b → T3 → T4. T1 is independent and the only pre-deadline work.
**Issue #1 placement:** folded into **T2a**, *not* T1 — the sphere oracle is axis-symmetric (drag is the
x-projection only) so it cannot exercise #1; and #1 needs the T1b extractor as its invariance
*instrument*. #1 is otherwise independent of T1's magnitude fix (the two defects — mis-scaled vs
mislabeled — are kept strictly separate; CC-V4).

**Contingency (deferred per guard).** If T1a finds the fix requires **solver-level** changes (IAMReX must
*emit* kernel-weighted forces rather than post-process them), the solver work co-lands with T2a to share
one re-run cycle — **and waits until after June 30** regardless. Even in that branch, **Track B's frozen
corpus is never regenerated** (it is a digest-pinned proof-of-pipeline artifact) — only re-captioned
(CC-V6).

---

## Cross-cutting concerns (program invariants)

- **CC-V1. Background track.** Only T1 is in-bounds before June 30 (see priority guard). T2–T4 and any
  re-run remediation are post-submission.
- **CC-V2. Oracle-graded, tolerances fixed, no number → no oracle.** Every *graded* tier states its
  literature oracle + tolerance up front; debug to meet it, never loosen it. A criterion with no
  literature number behind it (e.g. the pitching moment today) is carried as *reported, not validated*,
  never as a gradeable oracle.
- **CC-V3. Reuse force-surrogate provenance conventions.** `run_metadata.json` (pinned `:fp64` digest,
  IAMReX commit, inputs hash, caller-supplied timestamp — never wall-clock baked into logic);
  cluster-free fixtures where a test can run without GPU/cluster.
- **CC-V4. Two distinct defects, kept separate.** T1 changes *how force magnitude is reconstructed*; the
  already-committed Track-B corpus values are **frozen and reinterpreted, not edited**. Issue #1/T2a
  changes *orientation/labeling* (forces are already axis-invariant per issue #1). Never conflate the
  two in one test or one claim.
- **CC-V5. Supersede *every* copy of the "60% low Cd" claim; the submitted APEX artifact is immutable.**
  When T1b lands, update **all** live locations, not just one: `add-apex-benchmarking/proposal.md`,
  `tasks.md` (checkboxes 2.1.5 / 2.2.4), `specs/apex-benchmarks/spec.md` (the ±5% requirement +
  scenario), and `benchmarks/METHODS.md` Known-Limitation #1. The **already-submitted APEX proposal PDF
  is immutable and intentionally retains the original note** — record that so the drift reads as
  intentional, not an error.
- **CC-V6. Re-derive (don't regenerate the CFD) the Track-B corpus coefficients under the van Veen
  convention.** *Resolved by `standardize-force-normalization` (#32).* The wing/Track-B "~2.4×" was a
  **normalization-convention mismatch** — the repo normalized by **peak wingtip** velocity; van Veen
  (eq 1.1) normalizes by the stroke rate at the **radius of gyration** (second moment of area `S_yy`),
  a geometry factor of **(r_tip/r_gyr)² = 3.12×**. It is **not** a diffused-IB force deficit and **not**
  the sphere's 2.64× extraction bug (those two were conflated). The **raw** CFD (IB-particle CSVs, raw
  force/moment columns) stays frozen/digest-pinned; only the **derived** coefficients are re-derived
  (`dataset.parquet` CF columns, `holdout_predictions.parquet`, the evidence figure + metrics) — the
  surrogate is scale-invariant, so held-out R² is unchanged and no retrain is needed. `F_ref` **does**
  move (624.79 → 200.27 at the validated point; it is *not* "unaffected"). The "~2.4× diffused-IB
  underestimate" language in `examples/prelim_sweep/README.md`, `force_surrogate/evidence_figure.py`,
  `examples/flapping_wing/RESULTS.md`, and `docs/force_surrogate/roadmap.md` is **removed**, not
  re-captioned to a different number.

---

## Tracking issues

- **Per tier:** one EPIC/tracking issue, drafted just-in-time to
  `c:\vaults\physics surrogate models\nvidia-proposal\github_issues\` then filed (talmolab/mosquito-cfd
  is Elizabeth's own repo — no external-repo go-ahead needed).
- **Existing issues this roadmap absorbs:** **#1** (axis → T2a), **#3** (CF_x reproducibility → T2b),
  **#4** (CF_z label → T2b). The force-extraction action item in `flow_past_sphere/RESULTS.md` becomes
  **T1a/T1b**'s tracking issue ([#26](https://github.com/talmolab/mosquito-cfd/issues/26)).
- Every PR links (a) its tracking issue and (b) the roadmap tier it advances; closes its sub-issue on merge.

---

## Out of scope (belongs elsewhere)

- **Full LHS production corpus, DoMINO/latent-dynamics surrogate, RL-in-loop** — NVIDIA-grant-funded
  deliverables (grant plan + `force_surrogate/roadmap.md`), not this roadmap.
- **Fine grid (256³+) flapping** — expensive; defer to H100 (grant) unless the coarse/medium pair already
  satisfies the T3/T4 oracles.
- **The force-only surrogate itself** — done (Track B). This roadmap validates the *CFD* it is trained on.

---

## Reconciliation log — adversarial roadmap review (2026-06-24)

Three lenses (factual / dependency-sequencing / completeness-scope-safety) reviewed v1 against live
state. Factual lens: all 10 claims TRUE (incl. confirming `plt10000` carries the per-marker force data).
Reconciled findings:

- **[BLOCKING] T1 "analysis-only" premise unverified** (IAMReX-omits-fields precedent) → split into **T1a
  diagnosis** gating the no-re-run promise; T1a exit = "corrected Cd computable from committed fields?".
- **[BLOCKING] T2 invariance oracle un-gradeable** (changed extractor *and* geometry at once) → invariance
  now graded with the **T1b extractor on both sides**; rationale corrected (#1 is independent of T1's
  magnitude fix; co-located in T2a only to amortize re-runs + use T1b as the invariance instrument).
- **[BLOCKING] Flapping "CF in [0.5,1.5]" is a plausibility band, not validation; title overclaimed** →
  added **T4 time-resolved curve validation**; relabeled T2b/T3 flapping check as a *plausibility gate*;
  reserved "validated" for the sphere (T1b) and the wing curve (T4).
- **[IMPORTANT] Moment oracle cites a nonexistent van Veen number + a rejected axis identity** →
  pitching moment downgraded to *reported, not validated* (CC-V2).
- **[IMPORTANT] T2 too big** → decomposed into **T2a** (solver+convention+doc, atomic) and **T2b**
  (re-validation + RESULTS/METHODS reconciliation).
- **[IMPORTANT] coordinate-convention.md must co-land with the solver change** → made an explicit T2a
  exit criterion (no interim mislabeled state).
- **[IMPORTANT] T3 used an old-convention/old-BC medium deck** (#1 changes BCs = a physics change to the
  LEV/wake T3 resolves) → T3 re-authors the **new-convention** deck; convergence is coarse-new↔medium-new.
- **[IMPORTANT] Ellipsoid oracle undefined but load-bearing** → fixed to self-consistency (Δ<1% after t=7)
  + added-mass sanity vs van Veen 15%/31%, not a Cd point.
- **[IMPORTANT] Priority guard punctured by T2/T3 + contingency** → guard rewritten: only T1 pre-June-30;
  T2–T4 + any re-run remediation deferred post-submission.
- **[IMPORTANT] CC-V5 fixed only 1 of ≥5 copies of the "60% low" claim; missed the unmet apex spec
  requirement + immutable submitted artifact** → CC-V5 expanded to the full checklist + immutability note.
- **[IMPORTANT] The Track-B corpus coefficients used the wrong (peak-tip) normalization** → **CC-V6**
  (re-derive the *derived* coefficients under the van Veen convention; the raw CFD stays frozen; `F_ref`
  *does* move 624.79 → 200.27). *Superseded by #32: the "~2.4×" was a normalization convention, not a
  diffused-IB deficit; the earlier "F_ref unaffected" assumption was wrong.*
- **[MINOR] CC-V4 wording implied committed corpus values change** → reworded to "frozen and
  reinterpreted, not edited"; contingency branch states the corpus is never regenerated.
- **[MINOR] METHODS.md IAMReX commit pin skew** (`c5f8e2a` vs fork `7ece065d`) → folded into T2b's
  RESULTS/METHODS reconciliation.
