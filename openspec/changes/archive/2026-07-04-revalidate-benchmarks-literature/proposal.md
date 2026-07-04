# Re-validate benchmarks against literature oracles (Tier T2b)

## Why

Tier **T2a** (PR #38) re-oriented the flapping wing to the van Veen convention and delivered the
body-frame per-component comparison; Tier **T1b** replaced the ad-hoc ~2.4× sphere factor with the
principled control-volume extractor. What remains — Tier **T2b** of the aerodynamics-validation program
([`docs/aerodynamics_validation/roadmap.md`](../../../docs/aerodynamics_validation/roadmap.md), the T2b
row + oracle table) — is to **grade each benchmark against its literature oracle in the current
convention** and to **reconcile two documentation-provenance defects** that make the validated record
non-reproducible:

1. **Sphere (Re=100)** — the T1b control-volume Cd (coarse 1.342 / medium 1.184 / Richardson p=2 **1.131**,
   +4.0%) has never been *graded* against the literature point **Cd = 1.087** (Johnson & Patel 1999). No
   single grid is within ±5%, and the committed run is a **transversely-periodic array** (pitch 10 D,
   5 D upstream) carrying an estimated **+3–6% confinement offset** above the isolated value. T2b grades
   the residual as the **confined-array offset (H1′)** — analysis-only, on the committed T1b numbers.
2. **Heaving ellipsoid (Re=100)** — the roadmap oracle is **self-consistency** (forces Δ<1% after t=7)
   **+ added-mass-fraction sanity** vs van Veen (15% lift / 31% drag). The committed `forces.csv` has
   only `time,Fx,Fy,Fz` (no `SumU*`), and its drag drifts ~1.05% over t=7→t=10 at 1.0-unit resolution —
   too coarse to grade Δ or the added-mass share. T2b **re-runs** the ellipsoid on the pinned `:fp64`
   image to capture the 29-column IB-particle output (with `SumU*`), then grades both.
3. **Flapping wing** — the `[0.5,1.5]` band is being used as a two-sided per-component gate, but under the
   corrected motion the lab CF_x peak is **2.37** and van Veen's *own* body-frame normal is **~2.4** —
   both legitimately exceed 1.5 (see committed `figures/fig_forces.png`). The band's *provenance* is an
   O(1) **mean-lift-coefficient plausibility range** for hovering at Re 100–300
   ([add-arbitrary-geometry proposal.md:133](../../changes/add-arbitrary-geometry/proposal.md); [apex
   spec:43](../../changes/add-apex-benchmarking/specs/apex-benchmarks/spec.md)), *not* a van Veen
   per-component target. Its **floor (0.5)** is meaningful (it caught the old peak-tip normalization bug,
   CF_z ~0.22 < 0.5); its **ceiling (1.5)** conflicts with correct physics. T2b **formally demotes the
   band to a lower-bound O(1) sanity floor** (constant `(0.5,1.5)` **unchanged**, not-loosened guard
   **kept** — a labeling/role change, **not** a loosening) and makes the van Veen **body-frame targets**
   (`VAN_VEEN_CF_TARGETS` normal 2.4 / chord 0.3, tol 0.6, delivered in T2a) the graded per-component
   oracle.

Two documentation-provenance defects block reproducibility of the validated record:

- **Issue [#3](https://github.com/talmolab/mosquito-cfd/issues/3) (open)** — a RESULTS.md headline number
  was once non-reproducible from the committed CSV. T2a regenerated RESULTS.md to the van Veen
  `F_ref = 200.27` + new run (CF_x now `[−2.35, +2.37]`), so the *original* defect is moot — but #3 must be
  **re-validated against the CURRENT document**: assert **every** headline number recomputes from the
  committed forces CSVs over the stated window, then **close #3**.
- **METHODS.md pin skew** ([benchmarks/METHODS.md:15](../../../benchmarks/METHODS.md)) — pins
  `commit c5f8e2a` on the **upstream** `ruohai0925/IAMReX`, whereas the solver is now the
  **`talmolab/IAMReX` fork @ `f93dc794`** (baked into `docker/build-args.env` + `docker/Dockerfile.fp64`,
  guarded by `test_iamrex_pin_consistent`). This is a **repo divergence + hash skew**, and the existing
  pin-consistency test does **not** cover METHODS.md. T2b reconciles both and adds the assertion.

This tier **re-grades against oracles only**. Per **CC-V4** it keeps the T1b/#36 **magnitude
reconstruction** and the T2a **labeling/motion** work strictly separate: T2b does **not** re-derive the
extractor, the body-frame decomposition, or resolve the CF_chord PARTIAL (that is
[#40](https://github.com/talmolab/mosquito-cfd/issues/40) / **T4**).

## What Changes

Four workstreams (three benchmark re-grades + one documentation reconciliation), each landing with its
test written first (see `tasks.md`):

1. **Sphere — confinement-corrected literature grade (H1′).** Add a small analysis grader that takes the
   T1b control-volume Cd (and the Richardson-extrapolated value) and **divides** it by the stated
   `(1 + [3–6%])` confined-array offset, asserting the **isolated-equivalent** Cd brackets **1.087 within a
   stated tolerance (±5%)** — recording the verdict as **H1′ (extraction resolved; residual = confinement)**.
   Grader is **cluster-free** on the pinned Richardson value 1.131 (isolated-equivalent
   `1.131/(1+[0.03,0.06]) = [1.067, 1.098]` ∋ 1.087); a `requires_plotfile` companion re-runs
   `extract_sphere_cd(method="cv")` (guarded against the marker default) on the committed `plt10000` where
   the Z: drive is mounted. This requirement **sharpens** the existing "Literature validation classifies
   the extraction-vs-field hypothesis" force-extraction requirement (cross-referencing its offset
   provenance, not restating it) into a graded literature verdict. **No new sphere sim; the extractor is
   reused verbatim (CC-V4).**

2. **Ellipsoid — re-run for `SumU`, then self-consistency + added-mass sanity.** Operator-run the
   committed `inputs.3d.heaving_ellipsoid` on the pinned `:fp64` image (IAMReX `f93dc794`) with the
   29-column IB-particle output enabled; commit the resulting `forces_t2b_ib.csv` + `run_metadata_t2b.json`.
   Add a grader that, from the committed re-run CSV: (a) asserts **self-consistency** — the drag/lift
   relative change is **< 1% within the steady window (t ≥ 7)** by a pinned criterion; (b) computes the
   **added-mass fraction** (`ρ_f·SumU` relative to `ib_force`, the same `WriteIBForceAndMoment` algebra
   as the wing), asserts it is a **bounded, physical value that decays after the impulsive start**
   (constant-velocity heave ⇒ near-zero steady added mass), and **reports it against van Veen's 15%/31%
   ballpark** as an order-of-magnitude sanity (**not** a tight match — CC-V2). Reference-area Cd/CL stay
   *reported, not graded* (the ellipsoid is **not** a literature Cd point).

3. **Flapping — band-as-floor demotion + van Veen targets as the oracle + RESULTS #3 re-validation.**
   - **Demote the band to a floor:** `VAN_VEEN_BAND` value and its not-loosened guard are **unchanged**;
     the flapping gate grades the **lower bound only** (peak `|CF|` clears `0.5` = O(1) sanity, catches
     under-normalization), while the **upper bound is reported, not gated** (a per-component peak above
     1.5 is expected because van Veen's own body-frame normal ~2.4 exceeds it).
   - **Van Veen body-frame targets are the graded per-component oracle:** T2b **reproduces** the T2a
     `body_frame_overall_match` verdict (CF_normal **2.61 PASS** / CF_chord **0.92 PARTIAL**) from the
     committed new-convention CSV; it does **not** re-derive the decomposition or resolve the chord
     PARTIAL (#40 / T4).
   - **Issue #3 re-validation:** a test recomputes **every** RESULTS.md headline number
     (CF_x/CF_z ranges, `max|CF_x|`, `max|CF_z|`, the phase-table `Fz`, the body-frame 2.61/0.92, the
     added-mass fractions) from the committed CSVs (`forces_t2a_newconv.csv`; `forces.csv` for the
     contrast baseline) over the stated window **before** any doc edit; then **close #3**.

4. **METHODS.md pin reconciliation + consistency test.** Reconcile METHODS.md's **repo divergence + hash
   skew** and the adjacent stale references it drags along: line 15 → **`talmolab/IAMReX @ f93dc794`** (repo
   **and** hash); the stale `Dockerfile.iamrex` → `Dockerfile.fp64`; the sphere analysis example's
   known-wrong default `method="marker"` → `method="cv"`; the ellipsoid run-command block → the actual T2b
   re-run; the illustrative `run_metadata.json` block → include `iamrex_commit`; the upstream FP32 issue
   link (`ruohai0925/IAMReX#59`, legitimate) annotated that the **fork** is built; Known-Limitation #1
   refreshed (a pointer to the sphere H1′ verdict; the "~60% low / 2.64×" substance stays with **CC-V5/#29**).
   Add a **cluster-free** assertion that the METHODS.md IAMReX commit is a **prefix of** (equality modulo
   the repo's conventional abbreviation) the full 40-hex `IAMREX_COMMIT` in `docker/build-args.env`
   (complementing, not duplicating, `test_iamrex_pin_consistent`, which checks `build-args.env` ↔
   `Dockerfile.fp64`), plus a **negative-content** test that the stale `c5f8e2a` / `Dockerfile.iamrex` /
   marker-example strings are gone — both written **before** the doc edit (they go red on the current doc).

## Impact

- **Affected specs:** `force-extraction` (**ADDED** — confinement-corrected sphere Cd literature grade);
  `flapping-wing-validation` (**MODIFIED** — band demoted to a floor; **ADDED** — van Veen targets are the
  per-component oracle + RESULTS reproducibility); `heaving-ellipsoid-validation` (**NEW capability** —
  self-consistency + added-mass sanity + re-run provenance); `benchmark-provenance` (**NEW capability** —
  METHODS.md IAMReX pin consistency).
- **Affected code (this repo):** `src/mosquito_cfd/benchmarks/` — a sphere confinement-grader (new
  function alongside `analyze_sphere.py` / `stress_integral.py`, **reusing** `extract_sphere_cd`), an
  ellipsoid grader (`heaving_ellipsoid.py`, reusing `added_mass_force` from `flapping_wing.py`), and the
  flapping `plausibility_gate` floor semantics (**preserving its `cf_x_ceiling_margin`/`cf_z_floor_margin`
  return keys**, which existing tests assert); `tests/` — new reproducibility, band-floor, ellipsoid
  (with a cluster-free synthetic fixture), and METHODS-pin (prefix-match + negative-content) tests;
  `benchmarks/METHODS.md` (pin + adjacent stale refs); `examples/flow_past_sphere/RESULTS.md` (add the H1′
  grade **and reconcile the pre-existing "≈1.00–1.11" isolated-equivalent line** against the new
  `[1.067,1.098]`); `examples/heaving_ellipsoid/{RESULTS.md,forces_t2b_ib.csv,run_metadata_t2b.json}`;
  `examples/flapping_wing/RESULTS.md` (band-role clarification only); the roadmap **T2b Tiers row + the
  oracle-grounding rows (flapping "band"→"floor", axis-convention "floor" wording) + the reconciliation-log
  hash note (`7ece065d`→`f93dc794`)**.
- **New cluster run (post-submission, operator/A40, unattended):** **one** ellipsoid re-run via the
  documented RunAI/WSL pattern (CLAUDE.md), on the pinned `:fp64` image, saving the 29-col CSV +
  plotfiles to `MOSQUITO_CFD_PLOTFILE_ROOT`. The sphere and flapping re-grades are **analysis-only** on
  committed artifacts. All other tests are cluster-free / CI-gradeable.
- **Reproducibility (CC-V3):** the ellipsoid re-run captures `run_metadata_t2b.json` via
  `capture_surrogate_run_metadata` — the pinned `:fp64` **digest** (containing `sha256:`), the
  **IAMReX commit `f93dc794`** (via `extra={"iamrex_commit": ...}`), the inputs hash, and a
  **caller-supplied** timestamp. `requires_plotfile` tests auto-skip without `MOSQUITO_CFD_PLOTFILE_ROOT`.
  All Python via `uv`.
- **Explicitly out of scope:** **T3** (medium-grid convergence + LEV); **T4 / #40** (time-resolved curve
  match + per-component force decomposition that resolves the CF_chord PARTIAL); **loosening** the
  `VAN_VEEN_BAND` value; **CC-V5** (the sphere "~60% low / 2.64×" doc cleanup, #29 — the ellipsoid
  RESULTS.md's line-91 "60% discrepancy" note is **left as-is**, deferred to #29). **Track-B's frozen
  corpus** (`examples/prelim_sweep/base_inputs.3d.validation`) is **never regenerated** — this change
  touches no sweep deck.
- **Issues:** re-validates and **closes #3**; advances the roadmap T2b row; **defers** the CF_chord
  resolution to #40. A PR links (a) #3 and (b) the roadmap T2b tier.

## Deviations discovered during implementation

### Why roadmap line 213 got a forward-pointer, not a hash rewrite

The plan (and the CI-review finding) called for "correcting" the stale fork hash `7ece065d` at
`roadmap.md:213`. During implementation that line turned out to sit **inside the dated frozen
"Reconciliation log — adversarial roadmap review (2026-06-24)"** section — the same historical block as
lines 190-191 (which the docs review had already ruled must not be rewritten). On 2026-06-24 the fork pin
genuinely *was* `7ece065d`; rewriting it to `f93dc794` would falsify a dated record. So — consistent with
the frozen-log treatment of 190-191 — line 213 received a **parenthetical forward-pointer** ("the fork pin
is now `f93dc794` post-T2a, reconciled in T2b") instead of a hash rewrite. `tasks.md` (5.1) is updated to
match. This removes the "wrong current hash" confusion the reviewer flagged without editing history.
