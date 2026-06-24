# New-session handoff — Tier T1a (force-extraction diagnosis)

Paste the block below into a fresh Claude Code session started in `c:\repos\mosquito-cfd`.

---

```
We're working in the talmolab/mosquito-cfd repo (c:\repos\mosquito-cfd). I want to start
**Tier T1a** of the aerodynamics-validation program.

START BY invoking the `roadmap-driven-pipeline` skill — this is a tier of that program, and
each tier is a fresh session driven from a handoff prompt. Then follow its per-tier loop.

CONTEXT (read these first, in order):
1. docs/aerodynamics_validation/roadmap.md — the program roadmap. Read the priority guard, the
   "finding that drives Tier 1", the oracle table, and the T1a/T1b rows.
2. GitHub issue #26 (`gh issue view 26`) — T1a's tracking issue and exit criterion.
3. examples/flow_past_sphere/RESULTS.md — the sphere Cd discrepancy (0.503 coarse / 0.448 medium
   vs literature 1.087) and the dumped particle_real_comp sums.
4. src/mosquito_cfd/benchmarks/analyze_sphere.py — the current (raw-sum) force extractor.
5. The IAMReX diffused-IB force path in the fork (talmolab/IAMReX @ 7ece065d) — the source of truth
   for how forces are deposited/spread onto the IB particles.

THE TASK (T1a — diagnosis only):
Determine the CORRECT diffused-IB force reconstruction, and decide whether the corrected sphere Cd
is computable from the ALREADY-COMMITTED plotfiles (plt10000, both grids) with NO re-run.
- Read the IAMReX source to find the right reconstruction (kernel weights; which particle_real_comp*
  hold what; whether a pressure/viscous term is separate). Consult the upstream maintainer
  (Dr. Yadong Zeng / ruohai0925/IAMReX; the FP32 thread issue #59 is a contact point) if ambiguous.
- CONFIRM every field that reconstruction needs is actually present in the committed plt10000 for
  BOTH grids. (Precedent for missing fields: the x_velocity=0 / ns.init_iter=0 plotfile bug in
  flapping_wing/RESULTS.md — do not assume a field is persisted.)

EXIT CRITERION (issue #26):
A written reconstruction spec PLUS a clear yes/no answer to: "Is the corrected sphere Cd computable
from the committed plotfile fields, with no re-run?"
- Yes -> T1b is analysis-only and pre-deadline-eligible.
- No  -> T1b needs a solver fix + re-run, which DEFERS to post-submission (priority guard) and
  co-lands with T2a.

DELIVERABLE / HOW TO RECORD IT:
T1a is investigation, not production code — it does NOT need an OpenSpec change or TDD. Write the
findings to docs/aerodynamics_validation/t1a-findings.md (reconstruction spec + the yes/no + the
field-availability check per grid). Commit it on a branch off `docs/aerodynamics-validation-roadmap`
(that branch holds the roadmap and is not yet pushed — base off it). Open a PR; use /review-pr and
/pre-merge-check before merge.

WHEN T1b STARTS (next tier, NOT now): that's where the real code lands — use /new-feature to
orchestrate (-> /openspec:proposal -> /review-openspec -> /openspec:apply with TDD against the
sphere Cd=1.087 oracle -> /pre-merge-check -> PR -> /openspec:archive).

HARD CONSTRAINTS:
- ANALYSIS ONLY. No new simulations, no cluster/GPU runs, no re-runs.
- Do NOT implement the corrected extractor yet (that's T1b).
- Do NOT touch the axis convention / issue #1 (that's T2a, post-submission).
- This is a BACKGROUND track. It must NOT compete with the NVIDIA grant (~June 30). If it can't be
  done in spare cycles, park it.

CLOSE THE LOOP when T1a merges: tick the T1a row in the roadmap, and write the T1b handoff prompt
to docs/aerodynamics_validation/handoff_t1b.md.
```
