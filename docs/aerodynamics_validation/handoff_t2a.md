# New-session handoff — Tier T2a (axis-convention refactor, issue #1)

Paste the block below into a fresh Claude Code session started in `c:\repos\mosquito-cfd`.

> **Bounds: POST-SUBMISSION.** T2a is out-of-bounds before the NVIDIA grant deadline (~June 30) — it
> requires a solver refactor + cluster re-runs on the single-tenant A40 and must not compete with the
> grant crunch (roadmap priority guard / CC-V1). Start it only after submission.

---

```
We're working in the talmolab/mosquito-cfd repo (c:\repos\mosquito-cfd). I want to start
**Tier T2a** of the aerodynamics-validation program.

START BY invoking the `roadmap-driven-pipeline` skill if installed; otherwise proceed from this
self-contained prompt.

CONTEXT (read first, in order):
1. docs/aerodynamics_validation/roadmap.md — priority guard, the T2a row, CC-V4, and the
   "Issue #1 placement" paragraph.
2. GitHub issue #1 — the axis-convention defect (the authoritative spec of what is mislabeled).
3. docs/aerodynamics_validation/t1a-findings.md (esp. §8) — T1b landed the field-based extractor
   `extract_sphere_cd(method="cv")` / `mosquito_cfd.benchmarks.stress_integral`. T2a uses this
   extractor as its INVARIANCE INSTRUMENT (the sphere magnitude bug is already fixed and is
   strictly separate from the labeling bug — CC-V4).
4. src/mosquito_cfd/benchmarks/stress_integral.py — note `cd_from_drag`/`sphere_cv_drag_cd` assume
   the streamwise axis is +x (sphere stage). For the WING under the new convention, the streamwise
   axis differs — pass the streamwise/freestream axis EXPLICITLY (design Decision 9); the core
   returns the full (Fx,Fy,Fz) vector for this reason. Do NOT re-introduce a #1-style mislabeling
   in the analysis layer.

THE TASK (T2a — solver + convention + doc, ATOMIC):
Refactor the wing axis convention (issue #1): `wing.vertex` span -> y, BC/domain reshape
(`z` wall -> periodic), `WingKinematics.H` Euler order, hinge coords — AND in the SAME change:
`docs/coordinate-convention.md` + the `WingKinematics.H` docstring + the RESULTS frame-description.
No interim commit may carry new-convention geometry with old-convention docs.

EXIT CRITERION: forces are INVARIANT under the documented transform, graded with the T1b
`method="cv"` extractor on BOTH old- and new-convention runs (never new-extractor-new-geom vs
old-extractor-old-geom). Keep the two defects strictly separate (CC-V4): T2a changes
orientation/labeling only; the magnitude fix already shipped in T1b.

HOW TO RUN IT: this lands solver + Python + docs -> run /new-feature (OpenSpec proposal ->
/review-openspec -> /openspec:apply with TDD -> /pre-merge-check -> PR -> /openspec:archive).
Coarse re-runs only (operator/A40, unattended). The contingency from T1 (a solver re-run) co-lands
here to share one re-run cycle.

HARD CONSTRAINTS:
- POST-SUBMISSION only (priority guard). No A40/operator time before the grant ships.
- Keep magnitude (T1b) and labeling (#1) strictly separate (CC-V4).
- Track-B frozen corpus is never regenerated.

ALSO PENDING (independent of T2a, can be done anytime as docs-only): the CC-V5/CC-V6 supersession
follow-up from T1b — supersede the remaining "~60% low / ~2.4x" claims in add-apex-benchmarking,
examples/heaving_ellipsoid/RESULTS.md, examples/prelim_sweep/README.md,
force_surrogate/evidence_figure.py, examples/flapping_wing/RESULTS.md, docs/force_surrogate/roadmap.md
(resolved factor = 2.64x; field Cd ~1.13). The submitted APEX PDF is immutable.

CLOSE THE LOOP when T2a merges: tick the T2a row in the roadmap, write handoff_t2b.md.
```
