# Change: add-sphere-stress-cd

Field-based sphere drag extractor — **Tier T1b, Stage 1** of the aerodynamics-validation program
([roadmap](../../../docs/aerodynamics_validation/roadmap.md); diagnosis in
[`t1a-findings.md`](../../../docs/aerodynamics_validation/t1a-findings.md)).

## Why

The committed sphere benchmark reports **Cd = 0.503 (coarse) / 0.448 (medium)** vs literature **1.087**
(Johnson & Patel 1999) — a ~2.4× deficit that *worsens* with refinement, so it is **not**
under-resolution. T1a determined the cause is a **force-extraction defect**, not a missing kernel
weight:

- `src/mosquito_cfd/benchmarks/analyze_sphere.py` sums the raw IB marker force `Σ particle_real_comp3`.
  T1a proved (exact identity `Σcomp3 = −(dv/dt)·Σcomp0 = −0.176 → Cd 0.448`) that `dv` is **already
  applied in-solver**, so the "missing dv" hypothesis in `RESULTS.md` is false.
- With `loop_ns=2` (multidirect forcing), the plotfile persists **only the last sub-iteration's** force
  increment; the **accumulated** IB force lives in `kernel.ib_force` → written only to a non-persisted
  `IB_Particle_*.csv`. So **the marker route cannot recover the corrected force from committed
  plotfiles** (t1a-findings §4.a).

T1a also established the way forward: **Cd is a physical quantity recoverable by an IB-marker-free
control-volume momentum / surface-stress integral** over the persisted Eulerian fields
(`x/y/z_velocity` + `gradpx/y/z`, with `μ = ns.vel_visc_coef = 0.01`, `ρ = 1`), with **no re-run**
(t1a-findings §4.b). This integral is also the **decisive experiment** distinguishing the two remaining
hypotheses (§4.c):

- **H1 — force-extraction bug:** the resolved flow field is correct; only the marker bookkeeping
  under-reports. ⇒ the field integral yields **≈ 1.087** ⇒ corrected Cd is recovered here, **analysis-
  only, pre-deadline-eligible.**
- **H2 — flow-field deficit:** the diffuse-IB velocity field itself under-produces drag. ⇒ the field
  integral also yields **≈ 0.45** ⇒ a solver fix + re-run is required, which **defers post-submission**
  (priority guard) and co-lands with T2a.
- **H1′ — correct, but setup-offset:** the run is a *transversely-periodic array* (sphere at pitch 10 D,
  5 D upstream), not an unbounded isolated sphere, so its true Cd is ≈ **1.12–1.15** (`+3–6%` confinement/
  blockage, inertial regime). A field Cd in ~1.09–1.15 whose isolated-equivalent is within ±5% of 1.087 is
  **correct** (extraction + field both right; the residual is the documented setup offset). H1′ does **not**
  confound H1-vs-H2 (a +4% offset cannot masquerade as a −59% deficit) but must be named so a correct
  confined result is not misread as exact literature agreement or clipped at the band edge.

The decisive computation is a **two-plane periodic-duct control-volume balance** (the single-plane wake
survey originally speced is invalid here — periodic y/z + blockage accelerate the bypass above `U∞`; see
design "Why two-plane periodic-duct…"). The H1/H2 question is a ~2.4× discrimination, so the two-plane
balance (which plateaus cleanly) is decisive on its own. `gradp` is confirmed the true unscaled `∇p`
(IAMReX `Projection.cpp:305`).

**Result (this change, run on the committed `plt10000`):** **H1/H1′** — coarse Cd = 1.342, medium = 1.184,
Richardson(p=2) = 1.131 (+4.0% vs 1.087), isolated-equivalent (÷ confinement) ≈ 1.10 (+1–2%);
field/marker ratio = 2.64×. **H2 (≈0.45) is decisively excluded**; the corrected sphere Cd is recovered
from committed fields **with no re-run**, the residual is the confined-array offset (H1′) + grid
convergence, and the grid pair converges toward literature.

## What Changes

- **New capability `force-extraction`**: a control-volume momentum / surface-stress drag integral that
  computes sphere Cd from a plotfile's Eulerian fields, independent of the IB markers.
- **New module** `src/mosquito_cfd/benchmarks/stress_integral.py`:
  - a **pure-numpy core** (`control_volume_drag`, `cd_from_drag`, `recover_pressure_from_grad`) operating
    on gridded field arrays + geometry (CV bounds, cell spacing, `μ`, `ρ`), returning a per-face/per-term
    breakdown — unit-testable with **no plotfile / no cluster**. **Each integrand term (momentum flux,
    pressure, viscous) is validated by its own analytic known-answer test** (a single slip-side oracle
    would leave the pressure term — which dominates sphere Cd at Re=100 — untested);
  - a thin **yt adapter** `extract_eulerian_box(plotfile, bounds)` reading the CV region via
    `covering_grid` with an explicit FP64 cast (the only cluster-touching part).
- `extract_sphere_cd` gains an opt-in `method="cv"` path returning the field-based Cd; the
  existing marker-sum path is **retained but relabelled a diagnostic** (`cd_marker_lastpass`), never the
  reported number. Return dict is **extended (back-compatible), not broken** (blast radius is docs-only).
- **Decision artifact**: running the extractor on the real `plt10000` (both grids; Z: drive is mounted
  for local analysis) yields the H1/H2 verdict, recorded in `t1a-findings.md` (a short "§8 Stage-1
  result" addendum) and `flow_past_sphere/RESULTS.md`.
- **Conditional (H1 only) doc reconciliation** — supersede **every** live "~60% low Cd / under
  investigation" copy (roadmap **CC-V5**, which warns ≥5 exist): `add-apex-benchmarking`
  (`proposal.md`, `tasks.md` 2.1.5, `specs/apex-benchmarks/spec.md`), `benchmarks/METHODS.md`
  Known-Limitation #1 + its `extract_sphere_cd` snippet, and `examples/heaving_ellipsoid/RESULTS.md`; note
  that the **already-submitted APEX PDF is immutable** and intentionally retains the original note. The
  frozen Track-B corpus and the "~2.4×" origin are **re-captioned, never regenerated** (CC-V6):
  `examples/prelim_sweep/README.md`, `force_surrogate/evidence_figure.py`,
  `examples/flapping_wing/RESULTS.md`, `docs/force_surrogate/roadmap.md`; `F_ref≈624.8` is pure kinematics
  and unaffected.

## Impact

- **Affected specs**: ADDS `force-extraction`. Does **not** modify `apex-benchmarks` (that spec is not
  yet archived; its ±5% sphere requirement is the downstream oracle this serves and is reconciled when
  `add-apex-benchmarking` archives).
- **Affected code**: new `stress_integral.py`; additive change to `analyze_sphere.py::extract_sphere_cd`
  + `__init__.py` export; new `tests/test_stress_integral.py`. No solver/Docker/CI-infra changes.
- **Dependencies**: uses the existing `yt>=4.4.2` dep (no new pins; FP64 preserved end-to-end).
- **Reproducibility**: the field-based Cd is deterministic from committed inputs; the local validation
  records plotfile path + grid + `μ`/`ρ` + CV bounds so the number is traceable.
- **Out of scope**: any solver change or re-run (H2 remediation — deferred post-submission); the axis-
  convention refactor (issue #1 / T2a); ellipsoid & wing field-based extraction (T2b reuse).
- **Priority guard**: Stage 1 is **analysis-only / pre-June-30 eligible**; if the run lands on H2, the
  remediation is recorded and deferred, not executed here.
