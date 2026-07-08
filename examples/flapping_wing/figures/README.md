# Flapping-wing figures

Figures for the flapping-wing validation run (coarse 64×32×64, one wingbeat, Re ≈ 100) documented in
[`../RESULTS.md`](../RESULTS.md), plus the **Tier T3b grid-convergence comparison** (coarse vs medium
128×64×128). Three families, from several scripts.

**Axis convention** (van Veen 2022 / Bomphrey 2017, Tier T2a): **x = chord** (streamwise),
**y = span**, **z = vertical / lift**; stroke `Rz(φ)` about the vertical z, pitch `Ry(α)` about the
span y. See [`../../../docs/coordinate-convention.md`](../../../docs/coordinate-convention.md).

## Flapping-wing figures — `generate_all_figures.py`

Kinematics + forces + flow for the validated **new-convention** run
(`../forces_t2a_newconv.csv`, IAMReX `f93dc794`; provenance in `../run_metadata_t2a.json`).

| File | Shows |
|------|-------|
| `fig_planform` | Elliptic planform, 908 Lagrangian markers, span along **y**, chord along x (span 3c × chord 1c, 0.05c spacing). |
| `fig_kinematics` | Prescribed Euler angles over one wingbeat: stroke `φ(t) = 70°·sin(2πt)`, pitch `α(t) = 45°·cos(2πt)` (90° phase lead). |
| `fig_wing_phases` | Marker positions at t = 0, T/4, T/2, 3T/4 in the **x–y stroke plane** — the span-tip sweeps a ±70° arc (the van Veen translational stroke). |
| `fig_forces` | Lab-frame force coefficients `CF_x, CF_y, CF_z` (steady window t ≥ 0.05), normalized by the van Veen `F_ref = ½ρω²S_yy = 200.27`. |
| `fig_velocity` | Induced x-velocity, top-down z-slice at the wing/stroke plane (z = 4). Confirms real fluid coupling (induced dipole, `u ∈ [−10, +1.9]`). |

**Reading `fig_velocity`:** the snapshot is t = 0.25 — the **stroke extreme** (φ = +70°, φ̇ = 0, wing
momentarily stopped, α = 0), so the visible lobe is the **shed wake** of the preceding half-stroke, not
active lift generation (translational normal force ∝ sin α → ≈ 0 here). A dedicated **downwash / lift**
figure (vertical `w`-velocity, chord-normal slice, at a lift-relevant phase) is tracked in **issue #39**.

> **Fidelity caveat:** the coarse 64×32×64 grid (Δx = 0.125) **under-resolves** the leading-edge
> vortex — these are plausibility/pedagogy figures. The **Tier T3b grid-convergence comparison below**
> (`fig_lev_coarse_vs_medium`) shows the LEV on the coarse vs medium 128³ grid; time-resolved force-curve
> validation vs van Veen fig 3–4 is Tier T4.

## Force-normalization figures (V1–V5) — `generate_validation_figures.py`

The `standardize-force-normalization` (#36) story: the van Veen radius-of-gyration convention, not the
axis convention. Values snapshotted in `validation_figures_summary.json`.

| File | Shows |
|------|-------|
| `V1_three_convention_CF` | The three `F_ref` conventions: peak-tip 624.79 → mean-tip 253.22 → **van Veen radius-of-gyration 200.27** (the adopted one). |
| `V2_second_moment` | Radius of gyration `r_gyr = 1.698` and spanwise second moment `S_yy = 6.80`, traced from the committed `wing.vertex`. |
| `V3_scale_invariance` | The force surrogate is scale-invariant: held-out R² is unchanged by re-normalization (`ΔR² = 0` for `CF_x`, `CF_z`). |
| `V4_added_mass` | Added-mass term (`ρ_f·SumU`) as an RMS fraction of `ib_force`: ~10 % stroke, ~40 % lift (reported, not gated). |
| `V5_lab_vs_body` | Lab- vs body-frame force decomposition at the α = 45° pitch amplitude. |

## Grid convergence (T3b) — `make_grid_convergence_figure.py` / `make_lev_figure.py`

Tier **T3b** ([#46](https://github.com/talmolab/mosquito-cfd/issues/46)): the wing re-run on a **medium
128×64×128** grid (only `amr.n_cell` changes vs the coarse deck; `:fp64 @ f93dc794`). **Report-only** —
quantifies grid sensitivity, does not gate.

| File | Shows |
|------|-------|
| `fig_grid_convergence` | Peak body-frame `CF_chord` / `CF_normal`, coarse → medium, vs the van Veen reference — recomputed from the committed CSVs. **CF_chord drops 66.5 %** (0.923 → 0.554, toward ~0.3): coarse-grid under-resolution was a major contributor to the #40 chord excess. But it is **not grid-converged** (GCI band 0.28–0.83), so whether the residual gap is more grid error or physical is undetermined from 2 grids. `CF_normal` is grid-settled (−11.7 %). **Cluster-free.** |
| `fig_lev_coarse_vs_medium` | Vorticity magnitude at mid-stroke (t ≈ 0.5, stroke-plane slice z = 4), coarse vs medium. The leading-edge / tip vortex is **resolved on both grids**, visibly **sharper on the medium** — the qualitative view behind "peak vorticity ×1.8, resolution-fair ∫Q⁺ +9 %". *The bright band on the wing markers is partly the immersed-boundary regularization layer, not pure shed vorticity.* **Needs the plotfiles on the Z: drive.** |

## Regenerate

```bash
# Flapping-wing figures (velocity slice needs a plotfile on the Z: drive):
uv run python examples/flapping_wing/generate_all_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/<run>/plt00500

# Force-normalization figures (cluster-free):
uv run python examples/flapping_wing/generate_validation_figures.py

# T3b grid-convergence bar chart (cluster-free, from the committed CSVs):
uv run python examples/flapping_wing/make_grid_convergence_figure.py

# T3b LEV vorticity comparison (needs the coarse t2a-newconv4 + medium t3b-medium plotfiles on Z:):
MOSQUITO_CFD_PLOTFILE_ROOT=Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing \
    uv run python examples/flapping_wing/make_lev_figure.py
```

Each figure is written as both `.pdf` (vector, for papers) and `.png` (preview).
