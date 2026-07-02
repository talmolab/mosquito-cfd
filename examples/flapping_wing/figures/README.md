# Flapping-wing figures

Figures for the coarse validation run (64×32×64, one wingbeat, Re ≈ 100) documented in
[`../RESULTS.md`](../RESULTS.md). Two families, from two scripts.

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

> **Fidelity caveat:** the coarse 64×32×64 grid (Δx = 0.125) does **not** resolve the leading-edge
> vortex — these are plausibility/pedagogy figures. LEV resolution is Tier T3; time-resolved force-curve
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

## Regenerate

```bash
# Flapping-wing figures (velocity slice needs a plotfile on the Z: drive):
uv run python examples/flapping_wing/generate_all_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/<run>/plt00500

# Force-normalization figures (cluster-free):
uv run python examples/flapping_wing/generate_validation_figures.py
```

Each figure is written as both `.pdf` (vector, for papers) and `.png` (preview).
