# Standardize force coefficients on the van Veen convention + validate the flapping wing

## Why

The repo normalizes flapping-wing force coefficients by the **peak wingtip velocity**
(`F_ref = ½ρ·U_tip,peak²·S ≈ 624.79`), which makes the wing's coefficients look ~2–3× too small
versus the insect-flight literature (`max|CF_x| ≈ 0.45`, `max|CF_z| ≈ 0.20`). This spawned a false
narrative — documented in `examples/flapping_wing/RESULTS.md`, `evidence_figure.py`, and the
roadmaps — that *"IAMReX's diffused-IB force is ~2.4× low,"* conflating the wing's normalization
with the sphere's **real** ~2.64× force-extraction bug (T1b / #29). They are different defects.

A derivation spike on the committed geometry and forces (recorded in `design.md`) establishes:

- The wing has **no force-extraction bug** — it reads the correct accumulated `kernel.ib_force`
  from `IB_Particle_1.csv`. The apparent shortfall is purely a **normalization convention**.
- **van Veen et al. (2022, JFM 936:A3)** define the translational force coefficient as
  `F = ½ρ·ω²·S_yy·C_F` (their eq 1.1) — stroke rate `ω` at the **radius of gyration** and the
  **spanwise second moment of area** `S_yy = ∫c(y)y²dy`, *not* "wingtip velocity × planform area."
- From the actual 908-marker `wing.vertex`: radius of gyration `r₂ = sqrt(S_yy/S) = 1.6985`
  (the geometric midspan is 1.5; the load is tip-weighted), `S_yy = 6.797`, so
  `F_ref = ½ρ·ω_peak²·S_yy ≈ 200.27` — a factor `(r_tip/r₂)² = 3.119` below the current value.
  (The issue's assumed "(π/2)² = 2.47 peak-vs-mean" mechanism is **not** what van Veen does; the
  factor is geometry, not a sinusoid average.)
- Under this convention the wing lands in band on **raw `ib_force`**: `max|CF_x| ≈ 1.34–1.41`,
  `max|CF_z| ≈ 0.61–0.68` (window-dependent), both inside the van Veen plausibility band
  `[0.5, 1.5]` **with no correction factor**.

The force-surrogate is **scale-invariant**: re-normalization rescales the CFD targets and the
surrogate predictions by the same constant, so held-out **R² is unchanged** (verified exactly on the
committed `holdout_predictions.parquet`: `ΔR² = 0`). No retrain, no CFD re-run.

## What Changes

This is an **analysis-only** umbrella change. Raw CFD/forces are **never** regenerated; only
**derived** coefficients change.

- **A. Normalization helper (CC-3 single source). [BREAKING]** Re-define `compute_force_reference` to
  the van Veen convention `F_ref = ½ρ·ω_peak²·S_yy`, parameterized on the **radius of gyration**
  `r_gyr` (= `R_GYRATION ≈ 1.6985`, a new constant derived from `wing.vertex` with a traceability
  test) instead of the tip arm. This is **BREAKING**: the regression-locked reference values move
  (`f_ref`/`m_ref` 624.79 → ≈200.27; dataset `CF_x = 50/f_ref` 0.080 → 0.250) **and** the
  `ForceReference` fields are renamed `u_tip_max → u_ref`, `q_tip → q_ref`. Update the CC-3 regression
  lock and every dependent test/caller in lockstep (one atomic commit — see `design.md` D2).
- **B. Track-B propagation.** Re-derive the corpus force coefficients under the new convention (raw
  force columns untouched), regenerate the evidence figure + metrics, and add a **scale-invariance
  regression test** asserting held-out R² is unchanged within `1e-9`.
- **C. Roadmap invariants.** Rewrite **CC-V6** (re-deriving CF ≠ regenerating CFD; the "2.4×" was a
  normalization convention, **not** a diffused-IB underestimate and **not** the sphere's 2.64×
  extraction bug) and **CC-3** (new `F_ref`).
- **D. Caption/claim cleanup.** Remove the false *"IAMReX diffused-IB force ~2.4× low"* claim from
  the wing `RESULTS.md`, `evidence_figure.py` (including the spec requirement text that embeds it),
  `examples/prelim_sweep/README.md`, and `docs/force_surrogate/roadmap.md`. This **absorbs the
  CC-V6 (normalization) half of #29**; the **sphere-side CC-V5 "~60% low" cleanup stays in #29**.
- **E. Wing reconstruction + validation.** Grade the **O(1) magnitude plausibility gate** on
  `ib_force` **alone** — `|CF_x|, |CF_z| ∈ [0.5, 1.5]` with no fudge over a physically-pinned steady
  window (these already pass: 1.34–1.41 / 0.61–0.68) — and report the rotation-invariant resultant
  `|CF|` as the frame-honest companion. The **added-mass** term (`SumU*`) is reported as a **separate
  decomposition** whose formula is locked to the IAMReX `WriteIBForceAndMoment` source **before** any
  combination, NOT folded into the graded coefficient (the raw `SumU*` is ~1000× ambiguous depending
  on whether a `d/dt` is required — it must not be allowed to decide the gate). Regenerate wing
  RESULTS/figures.
- **F. NVIDIA proposal.** Update the CF numbers; drop the "~2.4× underestimate" framing (now in-band).
- **Figures (TDD-backed).** V1 three-convention overlay; V2 planform + second-moment integrand;
  V3 scale-invariance scatter; V4 added-mass decomposition; V5 lab-vs-body-frame honesty figure.

### Explicitly out of scope (kept separate, per roadmap CC-V4)

- **Axis convention (#1 / T2a).** van Veen reports body-frame chord-wise/normal components; our
  forces are lab-frame and the stroke is `Rz(φ)` about the span axis (non-standard). The gate here is
  therefore a **lab-frame O(1) magnitude** check; the faithful body-frame per-component comparison and
  the **time-resolved** curve match are deferred to **T2a (#1)** and **T4**. The docs must say so and
  must not overclaim. (A note on the stroke-about-span *motion* concern is queued for #1.)
- **Sphere force-extraction (T1b).** The sphere's real ~2.64× extraction bug and its sphere-side doc
  cleanup (CC-V5) stay in T1b / #29. This change touches **zero** sphere figures or force numbers.

## Impact

- **Affected specs:** `force-surrogate` (MODIFIED: force normalization, moment normalization, dataset
  extraction validated-point, Sane–Dickinson reference; ADDED: re-normalization scale-invariance) and
  a new **`flapping-wing-validation`** capability (van Veen convention, added-mass reconstruction,
  plausibility gate).
- **Affected code:** `src/mosquito_cfd/force_surrogate/{normalization,constants,dataset,evidence_figure}.py`,
  `examples/flapping_wing/generate_all_figures.py`, plus the locked tests.
- **Affected docs:** wing `RESULTS.md`, `examples/prelim_sweep/README.md`,
  `docs/force_surrogate/roadmap.md` (CC-3), `docs/aerodynamics_validation/roadmap.md` (CC-V6), the
  NVIDIA proposal, and the regenerated evidence + wing figures/metrics.
- **BREAKING — regression-locked numbers + public API move:** `F_ref` 624.79 → ≈200.27; `m_ref`
  624.79 → ≈200.27; dataset validated-point `CF_x = 50/F_ref` 0.080 → 0.250; `ForceReference` fields
  `u_tip_max → u_ref`, `q_tip → q_ref` (consumed across `normalization.py`, `dataset.py`,
  `evidence_figure.py`, `generate_all_figures.py`, and 3 locked test files — all updated in one commit).
- **Issue reconciliation:** closes the CC-V6 (normalization) half of **#29** on merge; leaves CC-V5;
  does not touch **#1**.

> **Possible split.** If review finds this unwieldy, the normalization foundation (A–D, F) can split
> from the wing validation (E); E depends only on A. Folded for now per decision (see `design.md`).
