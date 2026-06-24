# New-session handoff — Tier T1b (force-extraction fix)

Paste the block below into a fresh Claude Code session started in `c:\repos\mosquito-cfd`.

---

```
We're working in the talmolab/mosquito-cfd repo (c:\repos\mosquito-cfd). I want to start
**Tier T1b** of the aerodynamics-validation program.

START BY invoking the `roadmap-driven-pipeline` skill — this is a tier of that program, and
each tier is a fresh session driven from a handoff prompt. Then follow its per-tier loop.
(If that skill is not installed in this environment, proceed from this self-contained prompt.)

CONTEXT (read these first, in order):
1. docs/aerodynamics_validation/t1a-findings.md — the T1a diagnosis. THIS IS THE SPEC. It gives the
   correct reconstruction, the verified field mapping, and the key result: the diffused-IB force
   reconstruction is NOT recoverable from the markers (accumulated F_ib not persisted; loop_ns=2;
   IB_Particle CSV discarded), BUT an independent control-volume / surface-stress integral of Cd IS
   computable from committed fields with no re-run. Read §4.b, §4.c, §6, §7 closely.
2. docs/aerodynamics_validation/roadmap.md — priority guard + the T1a (✅) / T1b rows.
3. GitHub issue #26 (`gh issue view 26`) — T1a's now-closed tracking issue (the exit decision).
4. examples/flow_past_sphere/RESULTS.md — the Cd discrepancy (0.503 coarse / 0.448 medium vs 1.087)
   and the dumped particle_real_comp sums.
5. src/mosquito_cfd/benchmarks/analyze_sphere.py — the current (raw-sum, wrong) extractor to replace.

THE TASK (T1b — force-extraction fix), IN TWO STAGES:

STAGE 1 — the re-run-free cross-check (ANALYSIS-ONLY, pre-June-30 eligible). DO THIS FIRST.
Implement the control-volume momentum / surface-stress drag integral (t1a-findings §4.b) in
`mosquito_cfd.benchmarks`, reading the committed plotfiles on the Z: drive:
  Z:\users\eberrigan\mosquito-cfd-benchmarks\flow_past_sphere_coarse\plt10000  (coarse 128×64×64)
  Z:\users\eberrigan\mosquito-cfd-benchmarks\flow_past_sphere_10k\plt10000     (medium 256×128×128)
Fields present & sufficient: x/y/z_velocity, gradpx/y/z (∇p; p cancels up to a constant on a closed
surface), with μ = ns.vel_visc_coef = 0.01 and ρ = 1 (both in job_info). Use plt09900 for the
unsteady term (≈0 at steady state). Place the control-volume boundary a few cells OUTSIDE the
regularization support so the smeared IB band doesn't contaminate the stress.
This computation DECIDES the path:
  - H1 — it yields Cd ≈ 1.087  -> the deficit was force-EXTRACTION; the flow field is fine.
    T1b is DONE as an analysis-only fix (no re-run). Land it.
  - H2 — it yields Cd ≈ 0.45   -> the diffuse-IB FLOW FIELD itself underpredicts drag.
    STOP. Do NOT implement a marker-based extractor or re-run now. Record the H2 finding and DEFER
    the solver fix + re-run to post-submission (priority guard), co-landing with T2a. See
    t1a-findings §6 options (a)/(b)/(c) for the eventual solver path.

STAGE 2 — only if H1: replace the ad-hoc ~2.4× factor with the principled extractor, wired so
`extract_sphere_cd` returns the CV/stress Cd. Keep the old marker path only as a documented
diagnostic, not the reported number.

ORACLE / TDD NORTH STAR: sphere Cd = 1.087 ± tol (Johnson & Patel 1999), from existing plt10000 on
BOTH grids; the coarse↔medium pair should now converge TOWARD literature. Tolerance is fixed up front
and NEVER loosened to pass (roadmap CC-V2). Use cluster-free fixtures where possible (CC-V3); a small
committed plotfile slice or synthetic field is ideal for the unit test.

HOW TO RUN IT: this IS production code -> run /new-feature, which orchestrates the full flow
(scope -> /openspec:proposal -> /review-openspec -> /openspec:apply with TDD -> /pre-merge-check ->
PR -> after merge /openspec:archive). Tests BEFORE implementation (TDD). PR uses /review-pr +
/pre-merge-check. Base the branch off `docs/aerodynamics-validation-roadmap` (the program's
integration branch; not yet on main).

DOWNSTREAM (record as T1b tasks; act only on the H1 success path — frozen artifacts are reinterpreted,
not edited):
- CC-V5: supersede every copy of the "~60% low Cd / under investigation" claim — add-apex-benchmarking
  (proposal.md, tasks.md 2.1.5/2.2.4, specs/apex-benchmarks/spec.md) + benchmarks/METHODS.md
  Known-Limitation #1. The already-SUBMITTED APEX PDF is immutable and intentionally keeps the old
  note — record that the drift is intentional.
- CC-V6: re-caption (never regenerate) the frozen Track-B corpus — examples/prelim_sweep/README.md,
  force_surrogate/evidence_figure.py, corpus captions/run_metadata — to cite the resolved factor.
  F_ref≈624.8 is pure kinematics and unaffected.
- METHODS.md IAMReX commit pin is skewed (c5f8e2a vs fork 7ece065d) — note it; full reconcile is T2b.

HARD CONSTRAINTS:
- Stage 1 (CV cross-check) is ANALYSIS-ONLY and pre-June-30 OK. A SOLVER re-run (H2 path) is NOT —
  it defers post-submission and must not consume the single-tenant A40 / operator during the crunch.
- Do NOT touch the axis convention / issue #1 (that's T2a, post-submission). The sphere drag is the
  x-projection only and cannot exercise #1.
- BACKGROUND track. It must NOT compete with the NVIDIA grant (~June 30). If it can't be done in
  spare cycles, park it.
- Keep the two defects separate (CC-V4): T1b fixes force MAGNITUDE; #1/T2a fixes orientation/labeling.

CLOSE THE LOOP when T1b merges (H1) or is recorded as deferred (H2): tick the T1b row in the roadmap,
and write the T2a handoff prompt to docs/aerodynamics_validation/handoff_t2a.md.
```
