# Predicted-vs-CFD force-surrogate evidence figure (PR6)

## Why

Track B's roadmap (`docs/force_surrogate/roadmap.md`, row 6 — the final ⬜ row) culminates in **one
figure** for the NVIDIA Academic Grant *Evidence-of-Readiness*: predicted-vs-CFD force coefficients
on **held-out kinematic configurations**, with a Sane–Dickinson quasi-steady baseline overlay and an
annotated >1,000× inference-vs-CFD speedup. The figure proves the data→surrogate→inference pipeline
runs end-to-end on local hardware and that the NVIDIA PhysicsNeMo stack is usable — it is *not* a
claim of validated aerodynamics (GitHub issue #24).

Everything the figure consumes is already committed by PR5 (`add-force-surrogate-train`, PR #23):
`examples/prelim_sweep/surrogate/holdout_predictions.parquet` (the versioned prediction file) and
`metrics.json` (config-resolved skill + inference timing). PR6 adds **only** local plotting code — no
solver work, no cluster, no GPU (CC-6).

This is the *easy* surrogate, deliberately reduced (roadmap "This is the easy surrogate, not the
funded one"). The figure caption must keep it honest: pipeline readiness on coarse-grid forces, not
validated aerodynamics.

> **Non-gating / upside only.** Hard cutoff ~**June 24, 2026**. If PR6 slips, the figure is cut and
> the proposal stands on the already-validated sphere/ellipsoid/flapping benchmarks (roadmap line 11).

## What Changes

- **New tested module** `src/mosquito_cfd/force_surrogate/evidence_figure.py` (force-only, pure local):
  - Loads the committed `holdout_predictions.parquet` + `metrics.json`; computes nothing the trainer
    already computed — it **reads** the config-resolved skill and inference timing rather than
    re-deriving them.
  - **Predicted-vs-CFD scatter** for **CF_x, CF_z, CF_my** on the 6 held-out configs (CC-4): CFD-true
    (x) vs surrogate-pred (y), 1:1 reference line, points distinguished by config, per-panel
    **config-resolved R² + RMSE** annotation.
  - **Headline moment = CF_my**, labeled "**aerodynamic moment (M_y component)**" — *not* "pitch
    moment". It is the only moment with genuine config-resolved signal (see `design.md` D1); the
    repo's axis convention differs from biomechanics standard (issue #1), so the figure names the
    component rather than asserting a biomechanical pitch interpretation. **Issue #1 stays open**
    (its fix is a solver-level refactor + full cluster corpus re-run — out of scope, CC-6).
  - **Sane–Dickinson translational quasi-steady baseline** computed via the **CC-3**
    `compute_force_reference(...)` helper (no inline `F_ref`/`U_tip` re-derivation): coefficient
    `CF_trans(t) = F_trans(t) / F_ref = (U(t)/U_tip)²·C_L(α_eff(t))`, `U(t)/U_tip = cos(2π·phase)`
    taken from the parquet `phase` column, `C_L(α)` the Dickinson-1999 empirical fit. Overlaid on the
    lift (CF_z) force panel — the force the translational term physically predicts — annotated to show
    **baseline RMSE > surrogate RMSE** (surrogate ≥ analytic model). Scoped honestly to hovering
    (Sane & Dickinson 2002). NOT overlaid on the moment panel (a translational force model does not
    predict a moment).
  - **Annotations**: the >1,000× speedup as a **batched GPU-throughput** figure
    (`inference.throughput_rows_per_s` ÷ the coarse-grid A40 CFD throughput ≈ 3.7×10⁶×), disclosed as
    **batched (N=12,535 parallel evals) vs a sequential coarse-grid A40 CFD timestep rate** (the
    headline = latency-speedup × batch-size, so the batch size is stated) — *not* a per-evaluation
    claim (the like-for-like per-evaluation floor is ~310×, reported alongside) — plus per-panel RMSE.
  - **Honest caption** (CC-4): coarse grid 64×32×64, ~2.4× diffused-IB underestimate, per-axis
    config-resolved R² (CF_x 0.94, CF_z 0.83, CF_my 0.99), an explicit statement that the aggregate
    R²≈0.98 is ~99.9% the shared phase waveform and overstates skill (CF_y config-resolved R² is
    negative), that **CF_mx/CF_mz are excluded** because they are ≈99.9% the shared waveform (stated
    with its reason), and that the **surrogate is fit to sibling configs while the baseline is
    zero-parameter** — a lower surrogate RMSE shows within-range interpolation, not "ML beats theory".
    To stay legible the **on-figure caption is compact** (positive headline + a terse Caveats line + a
    terse Baseline line + a README pointer); the **full** disclosure prose lives in
    `examples/prelim_sweep/README.md` and `evidence_figure_metrics.json` (honesty test-enforced off the
    PNG).
- **New thin CLI driver** `scripts/make_evidence_figure.py` over the tested module (mirrors
  `extract_forces.py`/`run_sweep.py`).
- **Committed artifacts** under `examples/prelim_sweep/figures/`: `evidence_figure.png` (≥200 dpi),
  `evidence_figure_metrics.json` (per-axis surrogate vs Sane–Dickinson baseline RMSE + the
  config_mean_r2 the figure annotates — makes every number on the figure auditable/regenerable), and
  `run_metadata.json` (git/seed/inputs hash + caller-supplied timestamp — CC-1).
- **Cluster-free TDD** (CC-2): tiny synthetic predictions parquet + metrics dict fixtures; tests
  assert the baseline math against known arrays, the panel/annotation content, the artifact schemas,
  and the provenance digest guard. No RunAI, no GPU, no plotfiles.

## Capabilities

- **force-surrogate** (MODIFIED): adds the evidence-figure requirements (figure content, the CF_my
  headline pick, the Sane–Dickinson baseline, the honest caption/annotations, committed artifacts +
  provenance, cluster-free tests, force-only scope guard).

## Impact

- **Affected specs**: `force-surrogate` (ADDED requirements only — no existing requirement changes).
- **Affected code**: new `evidence_figure.py` + `scripts/make_evidence_figure.py`; new committed
  artifacts under `examples/prelim_sweep/figures/`. Reuses `compute_force_reference` (CC-3),
  `capture_surrogate_run_metadata`/`validate_image_digest` (CC-1) unchanged.
- **No** solver, container, cluster, CI-infra, or dependency changes (matplotlib/pandas/numpy already
  pinned). Closes Track B on merge.
- **Out of scope (CC-6)**: any plotfile/field reading, DoMINO/latent-dynamics, RL, and the issue-#1
  coordinate refactor.
