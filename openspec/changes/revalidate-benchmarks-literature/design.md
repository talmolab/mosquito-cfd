# Design — Re-validate benchmarks against literature oracles (Tier T2b)

## Context

T2b is an **oracle-grading + provenance-reconciliation** tier, not a solver or extractor change. The
magnitude reconstruction (T1b control-volume extractor, #36 normalization) and the labeling/motion
refactor (T2a van Veen convention + body-frame decomposition) are **already delivered**. Per **CC-V4**
these two defect classes stay strictly separate; T2b **consumes** their outputs and grades them, and must
not re-open either. The governing constraints (roadmap CC-V1..V6): oracle-graded with fixed tolerances
(no number → no oracle, CC-V2), reuse of the force-surrogate provenance conventions (CC-V3), and the
frozen Track-B corpus is never regenerated.

The design problems worth recording are: (1) how to grade the sphere against a literature point that no
single committed grid hits; (2) how to grade the ellipsoid when the committed data lacks the `SumU`
columns the added-mass oracle needs; (3) how to demote the `[0.5,1.5]` band without loosening it; and
(4) where the METHODS.md pin-consistency requirement lives.

## Decision 1 — Sphere: grade the confinement-corrected isolated-equivalent, not a single grid

**Problem.** Literature Cd = 1.087; committed control-volume Cd is coarse 1.342, medium 1.184, Richardson
(p=2) 1.131 (+4.0%). No single grid is within ±5%. The user's locked decision is to **document the
residual as the confined-array offset (H1′)**, not to run a new de-confined sphere.

**Decision.** Grade the **isolated-equivalent** Cd: take the confined value and **divide** it by the
stated `(1 + offset)` for the **+3–6%** transverse-array confinement offset (pitch 10 D, 5 D upstream —
already recorded in the `force-extraction` spec; the ADDED requirement **cross-references** that
provenance rather than restating it, to avoid two copies in one spec file post-archive), and assert the
resulting bracket contains 1.087 within tolerance. (The division form `cd/(1+offset)` — not the
subtractive `cd·(1−offset)` — is the one that yields the pinned bracket; the prose and the grader
docstring both use division so an implementer cannot code the wrong one.)

- Richardson 1.131 ÷ (1 + [0.03, 0.06]) → **isolated-equivalent ∈ [1.067, 1.098]**, which brackets 1.087
  to within ~±1–2% (comfortably inside ±5%). Verdict: **H1′** — extraction resolved (H1), residual
  explained by confinement, no re-run. The pre-existing sphere RESULTS.md "≈1.00–1.11" bracket (a wider
  viscous/order-budget estimate) is reconciled against this tighter pure-confinement bracket in the same
  edit, so the doc carries one explained pair, not two unexplained ones.
- **Tolerance is pinned up front** (±5% of 1.087, i.e. [1.033, 1.141]) and **not loosened** to pass
  (CC-V2). The offset band (3–6%) is a **stated physical input**, not fitted to the answer — the grader
  is proven to *fail* if the confined Cd is moved outside the correctable range.

**Why not a new de-confined run.** The roadmap allows "refine/de-confine to hit 1.087±5% on one grid
**OR** document the confined-array offset." The committed grid pair already converges toward literature
(coarse > medium, H2 excluded), and a new isolated-sphere run costs operator/A40 time for a residual that
is already physically explained. Preferring committed-artifact analysis (roadmap Bounds) makes H1′ the
right call. The `requires_plotfile` companion re-runs `extract_sphere_cd(method="cv")` verbatim on the
committed `plt10000` so the graded numbers are traceable to the extractor, not transcribed.

**CC-V4 guard.** The grader takes Cd **values** as inputs; it does not touch `stress_integral.py` /
`analyze_sphere.py` numerics. Re-grading ≠ re-deriving.

## Decision 2 — Ellipsoid: re-run for `SumU`, grade self-consistency + added-mass sanity

**Problem.** The committed `heaving_ellipsoid/forces.csv` has only `time,Fx,Fy,Fz` at 1.0-unit resolution;
the added-mass oracle needs `ρ_f·SumU`, and Δ<1% cannot be graded from 11 coarse points (the drag even
drifts ~1.05% over t=7→t=10). The user's locked decision is to **re-run** for the 29-column output.

**Decision.** One operator A40 re-run of the *unchanged* `inputs.3d.heaving_ellipsoid` on the pinned
`:fp64` image, with the IB-particle 29-column output enabled (same `WriteIBForceAndMoment` schema as the
wing). Commit `forces_t2b_ib.csv` + `run_metadata_t2b.json`. The grader (cluster-free on the committed
re-run CSV) does:

- **Self-consistency.** Assert the relative change of the streamwise-drag `Fx` and the heave-direction
  lift `Fy` (heave is prescribed in `+y`) is **< 1% within the steady window t ≥ 7**, by a **named, pinned
  criterion** (max consecutive-sample relative change over t ≥ 7). Measured on the finer re-run series, not
  assumed. The spanwise `Fz` (≈0 by symmetry) is not graded — to avoid a degenerate `0/0` — but a test
  confirms the re-run's `Fy` channel is non-zero so the lift-side gate is itself non-degenerate.
- **Added-mass fraction (sanity, reported not matched).** `added_mass = ρ_f·SumU` (reuse
  `flapping_wing.added_mass_force`). Assert the fraction relative to `ib_force` is **bounded (0 ≤ f < 1)**
  and **decays after the impulsive start** — the physical signature of a **constant-velocity** heave
  (acceleration ≈ 0 ⇒ near-zero *steady* added mass). **Report** the fraction against van Veen's
  **15% lift / 31% drag** wing ballpark as an order-of-magnitude sanity; do **not** assert a tight match
  (van Veen's numbers are for an *accelerating* wing — the ellipsoid's steady share is expected *below*
  them, and inventing a match would violate CC-V2).

**Why the ellipsoid is not re-oriented.** Geometry type 2 (ellipsoid) is a symmetric translating body,
untouched by the `WingKinematics.H` (type 4) motion refactor — like the sphere, it is convention-agnostic.
"Re-run in the new convention" for the ellipsoid means **re-run on the pinned f93dc794 image to capture
`SumU`**, not a geometry change. The deck is byte-unchanged.

**CC-V5 boundary.** The ellipsoid `RESULTS.md:91` "~60% discrepancy / systematic calibration" note is the
old force-extraction narrative and belongs to **CC-V5 / #29 (docs-only)**, explicitly out of T2b. T2b adds
the self-consistency + added-mass grading to that RESULTS.md but **leaves the CC-V5 line for #29** — noted
so the retained line reads as an intentional scope boundary, not an oversight.

## Decision 3 — Flapping: demote the band to a floor without loosening it

**Problem.** `[0.5,1.5]` is applied as a two-sided per-component gate, but correct physics (new-convention
lab CF_x 2.37; van Veen body-frame normal ~2.4) exceeds 1.5. The band's real provenance is a coarse O(1)
**mean-lift** plausibility range, not a van Veen per-component target.

**Decision.** A **labeling/role** change, value-preserving:

- The `VAN_VEEN_BAND == (0.5, 1.5)` constant and `test_van_veen_band_is_not_loosened` stay **exactly as
  is** — no widening. What changes is the *grading semantics*: the flapping gate grades the **floor** only
  (peak `|CF|` ≥ 0.5 = O(1) sanity, which caught the old peak-tip bug at CF_z ~0.22), and the **ceiling is
  reported, not gated** (a per-component peak above 1.5 is expected, not a failure).
- The **graded per-component oracle** is the van Veen **body-frame targets** (`VAN_VEEN_CF_TARGETS`
  normal 2.4 / chord 0.3, `VAN_VEEN_MATCH_TOL` 0.6) via `body_frame_overall_match` — **delivered in T2a**.
  T2b **reproduces** its verdict (CF_normal PASS, CF_chord PARTIAL) from committed data; it does not
  re-derive it.

**Why not just keep the two-sided gate on the old run.** The old-run test (`forces.csv`, 1.41/0.68) stays
green as a historical record, but it grades a **superseded** convention. Leaving the band's *documented
role* as "the van Veen gate" is the root confusion the user surfaced ("the band is the problem"). Naming
it a floor — while pointing the tight comparison at the body-frame targets that *are* van Veen's numbers —
resolves it honestly without touching the pinned value or straying into T4's decomposition work.

**Guard against silent loosening.** The band-floor grader is proven to still **fail** on an under-produced
(sub-0.5) coefficient, and `test_van_veen_band_is_not_loosened` remains. The demotion cannot become a way
to admit a genuinely wrong (too-small) coefficient.

## Decision 4 — Where the METHODS.md pin lives, and issue #3 re-validation ordering

**Pin consistency.** The METHODS.md IAMReX pin is documentation provenance for the benchmark methodology
doc, distinct from the CV extractor (`force-extraction`) and the run-provenance helper. It gets a small
**new capability `benchmark-provenance`** with one requirement: the METHODS.md IAMReX commit **agrees with
`docker/build-args.env`**, cluster-free, complementing `test_iamrex_pin_consistent` (which today checks only
`build-args.env` ↔ `Dockerfile.fp64`). Reconciling the **repo** (`ruohai0925` → `talmolab/IAMReX`) is a
prose edit; the **hash** (`c5f8e2a` → `f93dc794`) is what the test locks.

**Pin-format decision — prefix-match, not full-40-hex equality.** METHODS.md is a human doc; the repo's
prose refers to the pin by its **8-char abbreviation** (`f93dc794`) everywhere. The existing
`test_iamrex_pin_consistent` regex requires exactly 40 hex, which would (a) force an ugly full SHA into
prose and (b) fail to even *match* the current 7-char `c5f8e2a`, yielding an extraction error rather than a
clean mismatch on the test-first red step. So the new test uses a **7-to-40-hex extractor** on the METHODS
row and asserts `build_pin.startswith(methods_pin)` (`len(methods_pin) >= 7`) — equality *modulo* the
repo's abbreviation convention. This is a deliberate choice over full-40-hex equality: it keeps the doc
readable, produces a genuine `c5f8e2a`-mismatch red (not a parse error), and still fails on a *different*
commit. A 7-hex collision with a wrong commit is astronomically unlikely and would additionally have to
survive the fork-repo prose edit.

**Adjacent stale references travel with the pin.** Reconciling the pin exposes sibling defects in the same
doc that would otherwise silently contradict the reconciled image: a second `Dockerfile.iamrex` reference,
a sphere analysis example demonstrating the **known-wrong** `method="marker"` default (a provenance defect
in the same class T2b fixes), an ellipsoid run-command block that T2b's re-run supersedes, an illustrative
`run_metadata.json` missing `iamrex_commit`, and the roadmap's own reconciliation-log note naming a stale
*third* hash (`7ece065d`). These are all corrected in the pin workstream; the upstream FP32 issue link
(`ruohai0925/IAMReX#59`) is a legitimate reference to an upstream *issue* and is kept with a note that the
*fork* is what is built. The negative-content test targets the specific stale strings (`c5f8e2a`,
`Dockerfile.iamrex`, the `method="marker"` example) — **not** every `ruohai0925` occurrence — so the
legitimate upstream-issue link does not trip it.

**The `plausibility_gate` edit is key-preserving.** Demoting the band to a floor changes the *grading
semantics* but MUST keep the `cf_x_ceiling_margin` / `cf_z_floor_margin` return-dict keys, which the
existing `tests/test_flapping_wing_validation.py:118-119` assert on the old-run CSV (CF_x 1.41 → ceiling
margin 0.09 > 0, still green). This is a blast-radius the refactor must respect, not a free rename.

**Ellipsoid CI-gradeability + skip mechanism.** The added-mass/self-consistency **numerics** are graded
cluster-free on a synthetic fixture (shaped so the fraction decays past `t=7` and the steady Δ < 1%),
mirroring the `stress_integral` `_synthetic_box` known-answer pattern — so CI tests the logic, not just a
skip. The tests that read the *real* committed `forces_t2b_ib.csv` gate on **file existence**
(`skipif(not Path(...).exists())`, loaded **inside** the test body so collection never errors) — the
committed-artifact predicate, distinct from the `MOSQUITO_CFD_PLOTFILE_ROOT` env marker (which gates
plotfile-root reads). This keeps CI green before the operator run and makes the graded numbers traceable to
the solver output once it lands.

**Negative-result fallback (ellipsoid).** The re-run *measures* whether Δ<1% holds; design notes the coarse
series already drifts ~1.05%, so a fine re-run missing the gate is plausible. If it misses,
`SELF_CONSISTENCY_TOL` is **not** loosened (CC-V2) and the artifact is **not** committed (leaving 2.x
skipped, CI green); the miss is recorded as a **negative-result verdict** in RESULTS.md + a follow-up
issue. The other three workstreams (sphere, flapping, METHODS) are cluster-free and ship regardless — the
PR is reviewable and mergeable without the ellipsoid artifact.

**Issue #3 ordering (TDD, non-negotiable).** The reproducibility test recomputes **every** RESULTS.md
headline number from the committed CSVs and is written/passing **before** any RESULTS.md edit — so the
"validated record" is proven reproducible against live data, not curated to match. #3 is closed only after
that test is green.

## Risks / trade-offs

- **The ellipsoid re-run is the one cluster dependency.** If the A40/operator window slips, the ellipsoid
  grader tests are `requires_plotfile`/committed-CSV-gated and auto-skip until `forces_t2b_ib.csv` lands —
  the sphere, flapping, and METHODS workstreams proceed independently (analysis-only). The tier does not
  block on the run.
- **Confinement offset is a band, not a point.** Grading a bracket (not a single corrected value) is
  deliberate — it encodes the honest uncertainty (viscous flux + unfitted convergence order) rather than
  a false-precision single number, and the bracket must contain 1.087 *within* ±5%, not merely touch it.
- **Reproducing (not re-deriving) the T2a body-frame verdict** risks looking redundant. It is not: it
  proves the committed CSV still yields 2.61/0.92 under the current code — the reproducibility guarantee
  #3 is fundamentally about — and it is the hook the RESULTS #3 test asserts against.

## Alternatives considered

- **New de-confined sphere run** (Decision 1) — rejected: operator/A40 cost for an already-explained
  residual; roadmap permits the H1′ documentation branch.
- **Analytical (Lamb) added-mass for the ellipsoid** instead of re-running — rejected by the user in
  favor of the **measured** `ρ_f·SumU` from the solver, which is the faithful, like-for-like quantity vs
  van Veen (and vs the wing's own added-mass reporting).
- **Widening / removing `VAN_VEEN_BAND`** (Decision 3) — rejected: violates the hard constraint and the
  CC-V2 invariant; the floor is load-bearing and the ceiling is simply the wrong ruler, not a value to
  edit.
- **Folding the METHODS pin into `force-extraction`** — rejected: orthogonal concern; a dedicated
  `benchmark-provenance` capability keeps one narrative source per capability (OpenSpec DRY).
