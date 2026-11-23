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
| `fig_wing_phases` | Marker positions at t = 0, T/4, T/2, 3T/4 in the **x–y stroke plane** — the span-tip sweeps a ±70° arc (a stroke about the vertical axis, van Veen's rotation order). |
| `fig_forces` | Lab-frame force coefficients `CF_x, CF_y, CF_z` (steady window t ≥ 0.05), normalized by the van Veen `F_ref = ½ρω_peak²S_yy = 200.27`. |
| `fig_velocity` | Induced x-velocity, top-down z-slice at the wing/stroke plane (z = 4). Confirms real fluid coupling (induced dipole, `u ∈ [−10, +1.9]`). |

**Reading `fig_velocity`:** the snapshot is t = 0.25 — the **stroke extreme** (φ = +70°, φ̇ = 0, wing
momentarily stopped, α = 0), so the visible lobe is the **shed wake** of the preceding half-stroke, not
active lift generation (translational normal force ∝ sin α → ≈ 0 here). A dedicated **downwash / lift**
figure (vertical `w`-velocity, chord-normal slice, at a lift-relevant phase) is tracked in **issue #39**.

> **Fidelity caveat:** the coarse 64×32×64 grid (Δx = 0.125) **under-resolves** the leading-edge
> vortex — these are plausibility/pedagogy figures. The **Tier T3b grid-convergence comparison below**
> (`fig_lev_coarse_vs_medium`) shows the LEV on the coarse vs medium 128³ grid; the **Tier T4
> per-component decomposition** (`fig_force_decomposition` below) compares van Veen's quasi-steady model
> (transl + added-mass + Wagner, replotted at our kinematics — Fig 4 polars, not a digitized Fig 3–4) to
> the CFD total (normal peak magnitude graded; phase/curve reported).

## Force-normalization figures (V1–V5) — `generate_validation_figures.py`

The `standardize-force-normalization` (#36) story: the van Veen radius-of-gyration convention, not the
axis convention. Values snapshotted in `validation_figures_summary.json`.

| File | Shows |
|------|-------|
| `V1_three_convention_CF` | The three `F_ref` conventions: peak-tip 624.79 → mean-tip 253.22 → **van Veen radius-of-gyration 200.27** (the adopted one). |
| `V2_second_moment` | Radius of gyration `r_gyr = 1.698` and spanwise second moment `S_yy = 6.80`, traced from the committed `wing.vertex`. |
| `V3_scale_invariance` | Held-out R² of the coarse force surrogate is unchanged by re-normalization (`ΔR² < 1e-9` for `CF_x`, `CF_z`). Right panels: the committed van Veen coefficients as stored. Left panels: the same coefficients on the peak-tip reference, divided by k = F_ref(r_tip)/F_ref(r_gyr) ≈ 3.12. These are today's on-wing force coefficients (van Veen normalization) re-expressed on F_ref(r_tip), not the pre-#36 corpus. Axes are lab-frame coefficients of the force on the wing ([sign convention](../../../docs/coordinate-convention.md#force-and-moment-sign)). R² values are in `validation_figures_summary.json`. |
| `V4_added_mass` | The solver's internal-fluid term (`ρ_f·SumU`, called added mass in the code) as an RMS fraction of the IB force on the wing, for the contrast-baseline `forces.csv`: ~10 % stroke, ~40 % lift (reported, not gated). |
| `V5_lab_vs_body` | Lab- vs body-frame force decomposition at the α = 45° pitch amplitude. |

## Grid convergence (T3b) — `make_grid_convergence_figure.py` / `make_lev_figure.py`

Tier **T3b** ([#46](https://github.com/talmolab/mosquito-cfd/issues/46)): the wing re-run on a **medium
128×64×128** grid (only `amr.n_cell` changes vs the coarse deck; `:fp64 @ f93dc794`). **Report-only** —
quantifies grid sensitivity, does not gate.

| File | Shows |
|------|-------|
| `fig_grid_convergence` | Peak body-frame `CF_chord` / `CF_normal`, coarse → medium, with the pinned T2a target as a dashed line (read from `VAN_VEEN_CF_TARGETS`; under review in [#154](https://github.com/talmolab/mosquito-cfd/issues/154)) — recomputed from the committed CSVs. **CF_chord drops 66.5 %** (0.923 → 0.554, toward ~0.3): coarse-grid under-resolution was a major contributor to the #40 chord excess. But it is **not grid-converged** (GCI band 0.28–0.83), so whether the residual gap is more grid error or physical is undetermined from 2 grids. `CF_normal` is grid-settled (−11.7 %). **Cluster-free.** |
| `fig_lev_coarse_vs_medium` | Vorticity magnitude at mid-stroke (t ≈ 0.5, stroke-plane slice z = 4), coarse vs medium. The leading-edge / tip vortex is **resolved on both grids**, visibly **sharper on the medium** — the qualitative view behind "peak vorticity ×1.8, resolution-fair ∫Q⁺ +9 %". *The bright band on the wing markers is partly the immersed-boundary regularization layer, not pure shed vorticity.* **Needs the plotfiles on the Z: drive.** |

## Per-component decomposition (T4) — `make_force_decomposition_figure.py`

Tier **T4** ([#40](https://github.com/talmolab/mosquito-cfd/issues/40)): van Veen's quasi-steady model
(translational + added-mass + Wagner) built from published coefficients and **replotted at our
kinematics** (not a digitized figure), fed the angle of attack derived from the wing's motion, vs
the CFD total on the **fine 256³ grid** (`forces_fine.csv`, T3c/#52 — the finest grid available).
**Cluster-free.** The numbers and the limits of the comparison are stated in one place, the T4
subsection of [`../RESULTS.md`](../RESULTS.md).

| File | Shows |
|------|-------|
| `fig_force_decomposition` | Model translational / added-mass / Wagner / total vs the CFD IB force on the wing ([sign](../../../docs/coordinate-convention.md#force-and-moment-sign); fine grid), for `CF_chord` and `CF_normal` over the steady window. The **normal peak magnitude** agrees within the graded tolerance, and the CFD normal peak comes slightly before the model's (reported). The model's normal force and the CFD's each have a positive lobe on each half-stroke, with a small negative dip before each reversal; both chord forces change sign each half-stroke. The kink in the model's normal curve at mid-stroke is its Wagner term changing sign, and the model's peak falls just after it. The CFD's second normal peak is lower than its first. The CFD **chord** is several times the model's: reported, not explained by the model (#40 is open). **Cluster-free.** |

## Grid convergence (T3c, 3-grid) — `make_grid_convergence_3grid_figure.py` / `make_force_timeseries_3grid_figure.py`

Tier **T3c** ([#50](https://github.com/talmolab/mosquito-cfd/issues/50)): 3-grid Richardson analysis adding the fine 256×128×256 grid. Both components converge monotonically. **Cluster-free.**

| File | Shows |
|------|-------|
| `fig_grid_convergence_3grid` | Peak body-frame CF_chord / CF_normal for all 3 grids. Richardson extrapolant (dashed) + GCI band (shaded). Two reference lines, each read from its source when the figure is drawn: the peak of van Veen's quasi-steady model (from `decompose_wing_force` on the fine-grid CSV) and the pinned T2a target (from `VAN_VEEN_CF_TARGETS`; not the paper's value, [#154](https://github.com/talmolab/mosquito-cfd/issues/154)). CF_chord: not tightly converged (GCI_fine=27.6 %) and well above the model peak. CF_normal: nearly converged, GCI_fine=3.7 %. p_obs ≈ 1.37–1.38 for both. |
| `fig_force_timeseries_3grid` | Body-frame CF_chord and signed CF_normal time series over one wingbeat, all 3 grids overlaid. Shows where grids agree (normal waveform shape) and where they differ (chord magnitude and late-cycle asymmetry at coarse). Dashed lines mark the peak of van Veen's quasi-steady model (from `decompose_wing_force` on the fine-grid CSV): at both signs in the chord panel, where the force changes sign each half-stroke, and on the positive side in the normal panel. |

## Regenerate

```bash
# Flapping-wing figures (velocity slice needs a plotfile on the Z: drive):
uv run python examples/flapping_wing/generate_all_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/<run>/plt00500

# Force-normalization figures (cluster-free):
uv run python examples/flapping_wing/generate_validation_figures.py

# T3b grid-convergence bar chart (cluster-free, from the committed CSVs):
uv run python examples/flapping_wing/make_grid_convergence_figure.py

# T4 per-component decomposition (cluster-free, from the committed CSVs):
uv run python examples/flapping_wing/make_force_decomposition_figure.py

# T3b LEV vorticity comparison (needs the coarse t2a-newconv4 + medium t3b-medium plotfiles on Z:):
MOSQUITO_CFD_PLOTFILE_ROOT=Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing \
    uv run python examples/flapping_wing/make_lev_figure.py

# T3c 3-grid Richardson convergence chart (cluster-free):
uv run python examples/flapping_wing/make_grid_convergence_3grid_figure.py

# T3c force time-series overlay, all 3 grids (cluster-free):
uv run python examples/flapping_wing/make_force_timeseries_3grid_figure.py
```

Each figure is written as both `.pdf` (vector, for papers) and `.png` (preview).
