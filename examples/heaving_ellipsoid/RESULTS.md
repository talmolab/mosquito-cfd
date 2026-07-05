# Heaving Ellipsoid Results

**Date**: February 23-24, 2026
**Platform**: NVIDIA A40 (Salk RunAI cluster)
**Docker Image**: `ghcr.io/talmolab/mosquito-cfd:fp64`

## Summary

Thin ellipsoid heaving through fluid at Re=100, approximating a flat plate wing for APEX proposal benchmarking. This test validates that IAMReX can handle:
1. Non-spherical geometry (ellipsoid)
2. Prescribed body motion (heaving)
3. Force computation on moving bodies

**Key Result**: Simulation reached quasi-steady state by t=7.0 (700 steps). Forces are stable.

## Configuration

| Parameter | Value | Description |
|-----------|-------|-------------|
| Geometry type | 2 (ellipsoid) | IAMReX built-in |
| Semi-axis a | 0.5 | Chord direction (x) |
| Semi-axis b | 0.02 | Thickness (y) - very thin |
| Semi-axis c | 1.5 | Span direction (z) |
| Aspect ratio | 3:1 | Matches mosquito wing AR |
| Center | (5.0, 5.0, 5.0) | Domain center |
| Freestream | 1.0 (x) | Inflow velocity |
| Heave velocity | 0.5 (y) | Prescribed heaving |
| Viscosity | 0.01 | Re = 100 |
| Domain | 20 × 10 × 10 | Dimensionless |
| Grid | 256 × 128 × 128 | 4.2M cells |
| Timestep | 0.01 | Fixed |
| Steps | 1000 | Quasi-steady state |

## Results

### Performance

| Run | Steps | Wall Time | Time/Step | GPU Memory |
|-----|-------|-----------|-----------|------------|
| Test | 100 | 205 s | 2.0 s | 3,837 MB |
| Quasi-steady | 1000 | 1891 s (~31 min) | 1.89 s | 3,837 MB |

**Comparison with FlowPastSphere (same grid)**:
- FlowPastSphere: 1.76 s/step
- Heaving ellipsoid: 1.89 s/step
- Overhead: ~7% (ellipsoid geometry + heaving motion)

### Velocity Field (at t=10.0)

| Component | Max Value | Description |
|-----------|-----------|-------------|
| u (x) | 1.21 | Freestream + wake |
| v (y) | 0.81 | Heaving-induced flow |
| w (z) | 0.53 | Spanwise flow |

The elevated y-velocity (0.81) compared to FlowPastSphere (0.46) confirms the heaving motion is working correctly.

### Force Time History

Simulation reached quasi-steady state by t=7.0 (forces change <1% thereafter):

| Step | Time | Fx (drag) | Fy (lift) | Fz |
|------|------|-----------|-----------|-----|
| 0 | 0.0 | 0.000 | 0.000 | 0.000 |
| 100 | 1.0 | -0.214 | 0.109 | 0.000 |
| 200 | 2.0 | -0.204 | 0.106 | 0.000 |
| 300 | 3.0 | -0.197 | 0.105 | 0.000 |
| 400 | 4.0 | -0.194 | 0.103 | 0.000 |
| 500 | 5.0 | -0.192 | 0.103 | 0.000 |
| 600 | 6.0 | -0.190 | 0.102 | 0.000 |
| 700 | 7.0 | -0.190 | 0.101 | 0.000 |
| 800 | 8.0 | -0.188 | 0.101 | 0.000 |
| 900 | 9.0 | -0.189 | 0.100 | 0.000 |
| 1000 | 10.0 | -0.188 | 0.100 | 0.000 |

**Convergence**: From t=7 to t=10, drag changed by <1% (0.190 to 0.188).

### Force Coefficients (Steady State, t=10)

Reference areas for thin ellipsoid (a=0.5, b=0.02, c=1.5):
- Frontal area: π×b×c = 0.094
- Planform area: π×a×c = 2.36

| Coefficient | Value | Reference Area | Notes |
|-------------|-------|----------------|-------|
| Cd | 4.0 | Frontal (0.094) | Very thin body |
| Cd | 0.16 | Planform (2.36) | Wing-like reference |
| CL | 0.085 | Planform (2.36) | Heaving-induced lift |
| L/D | 0.53 | - | Lift-to-drag ratio |

**Note**: Force extraction uses `particle_real_comp3/4/5`. Same ~60% discrepancy observed for FlowPastSphere Cd suggests systematic calibration needed. *(The "~60% discrepancy" framing here is the pre-T1b narrative and is left for the docs-only CC-V5 cleanup, [#29](https://github.com/talmolab/mosquito-cfd/issues/29); T2b does not touch it.)*

## T2b re-validation — self-consistency + added-mass sanity (van Veen convention)

**Oracle** (roadmap Tier T2b): self-consistency (forces Δ<1% after t=7) **+** added-mass-fraction sanity vs
van Veen (15% lift / 31% drag). **Not** a literature Cd point.

Re-run on the pinned `:fp64` image (`ghcr.io/talmolab/mosquito-cfd@sha256:a6431ef4…`, IAMReX
`talmolab/IAMReX @ f93dc794`) on a **RunAI talmo-lab preemptible A40** with the **byte-unchanged** deck,
emitting the 29-column IB-particle output (`forces_t2b_ib.csv`, `SumUx/SumUy/SumUz`; provenance
`run_metadata_t2b.json`). Graded by `mosquito_cfd.benchmarks.heaving_ellipsoid` (1000 steps, dt=0.01, 300
samples in the steady window). The deck is a **constant-velocity heave** (`Vy=0.5`) in a **freestream**
(`Vx=1.0`), so steady `Fx ≈ −0.49` is freestream drag and `Fy ≈ +0.26` is the heave-direction force.

| Check | Result | Verdict |
|---|---|---|
| **Self-consistency** (max consecutive Δ over t≥7) | drag `Fx` **0.16%**, heave-lift `Fy` **0.15%** | **PASS** (< 1%) |
| **Added-mass fraction** (`ρ_f·SumU` / `ib_force`, steady mean) | drag **1.1%**, lift **0.5%** | **sanity holds** |
| vs van Veen ballpark (15% lift / 31% drag) | ellipsoid share is **well below** the wing's | expected |

**Added-mass characterization (honest details).** The fraction is a brief **numerical startup spike**
(~5–6% at t≤0.03) then **flat at ~1% steady** — it does **not** decay from a physical transient (the
grader's mean-based `decays` flag is in fact `False`: the early-window and steady means are both ~1%).
About **49% of the `SumU` samples are exactly 0**, in a regular **~15.6-step sawtooth** — a
**sub-cell-translation discretization artifact**, not a solver bug: the body heaves at `Vy·dt = 0.005`
per step, far below the heave-direction cell size `dy = 10/128 = 0.078`, so between grid-cell crossings
the diffused-IB support's summed velocity `sum_u` is unchanged and `SumU = (sum_u_new − sum_u_old)/dt` is
**bit-exact 0**; it becomes non-zero only as the body crosses a cell — every `dy/(Vy·dt) ≈ 15.6` steps,
which matches the observed period (15/16). The forces `Fx/Fy` themselves are smooth and unaffected (the
self-consistency gate is unbothered). The **flapping wing shows no such zeros** — its markers sweep
continuously, so `sum_u` changes every step. Consequently the reported added-mass fraction is the mean
over *all* steps (diluted by the zeros); the **non-zero-only** (active-phase) steady share is ~**2.0% /
1.0%**. Either way it is far below van Veen's 15%/31%, so the sanity conclusion is unchanged.

> **The van Veen 15%/31% is an *upper reference the ellipsoid is expected to sit far below*, not a match
> target.** Added-mass force scales with **acceleration**; van Veen's 15%/31% is for an *accelerating,
> rotating* wing, whereas this deck is *constant-velocity* (steady acceleration ≈ 0). The IAMReX `SumU`
> term is the rate of change of fluid momentum in the IB support region, so the small ~1% is **consistent
> with the near-zero fluid-momentum rate expected at zero body acceleration** — a result *near* 15%/31%
> would have been the red flag. Accordingly the comparison is **reported, not graded** (CC-V2): the graded
> oracle is the **self-consistency** gate (passes with margin) plus the added-mass fraction being
> **bounded** and small. A tight reference would be the ellipsoid's own potential-flow added mass
> (deferred; the roadmap pinned van Veen as the in-repo anchor).

The spanwise `Fz` is ≈0 by symmetry (`max|Fz| = 4.6e-4` steady) and is not graded; `Fx`/`Fy` stay non-zero
at steady state, so the added-mass fraction has no zero-crossings.

> **NB — two force files, different extraction.** The older committed `forces.csv` (4-col) reads the
> `particle_real_comp3/4/5` marker last-sub-iteration values (steady `Fx −0.19 / Fy +0.10`); this run's
> `forces_t2b_ib.csv` reads `kernel.ib_force` (the accumulated IB force) and gives `−0.49 / +0.26`, ~**2.6×**
> larger. That is the accumulated-vs-last-pass extraction difference behind T1a/T1b — a solver-bookkeeping
> factor (`loop_ns=2` accumulation), **consistent in magnitude** with the sphere's 2.64× field-vs-marker
> gap but a **distinct mechanism** (not independently cross-validated).

## Limitations Observed

1. **Constant velocity only**: IAMReX only supports constant prescribed velocities, not time-varying kinematics like sinusoidal heaving
2. **No rotation**: Full 3-angle flapping (φ, α, θ) requires IAMReX code modification
3. **Approximate geometry**: Ellipsoid is not a true flat plate; expect differences in force coefficients
4. **`SumU` added-mass proxy is unreliable at sub-cell translation (T2b)**: because the body moves
   `Vy·dt = 0.005` per step, far below the cell size `dy = 0.078`, the diffused-IB `SumU` term is a
   ~15.6-step sawtooth (bit-exact 0 between grid-cell crossings; see the T2b section) — so the reported
   added-mass fraction is a diluted mean, reliable only to an order of magnitude. It suffices for the
   "≪ van Veen 15%/31%" sanity but not for a precise added-mass number; a finer grid, or the ellipsoid's
   own potential-flow (Lamb) added mass, would be the fix. Does **not** affect the graded self-consistency
   verdict (which is on the smooth `Fx`/`Fy`).

## Next Steps

1. ~~**Run to quasi-steady state**: Extend to 1000 steps to observe force convergence~~ **DONE**
2. **Verify force extraction**: Confirm comp3/4/5 interpretation with IAMReX maintainer
3. **Generate visualizations**: Velocity field slices showing ellipsoid wake
4. **Compare with theory**: Quasi-steady added mass predictions
5. **Calibration study**: Compare sphere and ellipsoid discrepancies

## Figures

| Figure | File | Description |
|--------|------|-------------|
| Geometry | [figures/fig_geometry.png](figures/fig_geometry.png) | Elliptic cross-sections (xz and xy planes) with annotated semi-axes |
| Force history | [figures/fig_forces.png](figures/fig_forces.png) | Cd and CL vs time (planform-referenced) |
| Validation | [figures/fig_validation.png](figures/fig_validation.png) | x-velocity field (t=5.0, body at y=7.5) + force history composite (matches proposal Figure 2) |

Generated with:
```bash
# CSV-based figures (no cluster access required):
uv run python examples/heaving_ellipsoid/generate_figures.py

# Velocity figure (requires plotfile on Z: drive):
uv run python examples/heaving_ellipsoid/generate_figures.py \
    --plotfile Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k00500
```

Inputs: `forces.csv` — 11-point time series (t=0–10) extracted from plt_1k* plotfiles.
Velocity figure uses `plt_1k00500` (t=5.0) — body at y=7.5, safely within y-periodic domain [0,10].

## Output Files

### Cluster Storage
```
/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/
├── plt_1k00000/     # Initial condition (t=0)
├── plt_1k00100/     # t=1.0
├── ...              # Every 100 steps
├── plt_1k01000/     # Final (t=10.0, quasi-steady)
├── chk_1k00000/     # Initial checkpoint
├── chk_1k01000/     # Final checkpoint
├── inputs.3d.heaving_ellipsoid
└── run.sh
```

### Local Repository
```
examples/heaving_ellipsoid/
├── inputs.3d.heaving_ellipsoid
├── run.sh
├── visualize.py
├── generate_figures.py
├── forces.csv
├── figures/
│   ├── fig_geometry.{pdf,png}
│   └── fig_forces.{pdf,png}
├── README.md
└── RESULTS.md
```

## Reproducibility

### Run Command (1000 steps)

```bash
runai workspace submit heaving-ellipsoid-1k \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --gpu-devices-request 1 \
  --host-path path=/hpi/hpi_dev/users/$USER/mosquito-cfd,mount=/workspace \
  --command -- bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
    mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex \
    /workspace/examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid \
    amr.plot_file=/workspace/examples/heaving_ellipsoid/plt_1k \
    amr.check_file=/workspace/examples/heaving_ellipsoid/chk_1k \
    max_step=1000"
```

### Analysis

```python
import yt
import numpy as np

# Load quasi-steady state output
ds = yt.load('Z:/users/eberrigan/mosquito-cfd/examples/heaving_ellipsoid/plt_1k01000')
ad = ds.all_data()

# Extract forces (force on fluid from IB markers)
fx = float(ad['all', 'particle_real_comp3'].sum())  # -0.188
fy = float(ad['all', 'particle_real_comp4'].sum())  # 0.100
fz = float(ad['all', 'particle_real_comp5'].sum())  # ~0

# Force on body = -force on fluid
F_drag = -fx  # 0.188
F_lift = -fy  # -0.100

# Reference areas
a, b, c = 0.5, 0.02, 1.5
A_planform = np.pi * a * c  # 2.356

# Force coefficients
q = 0.5 * 1.0 * 1.0**2  # dynamic pressure
Cd = F_drag / (q * A_planform)  # 0.16
CL = abs(F_lift) / (q * A_planform)  # 0.085
```

## References

- van Veen et al. (2022). Wing geometry for Aedes aegypti
- Bomphrey et al. (2017). Mosquito kinematics (f=717 Hz, φ₀=39°)
- Li et al. (2024). IAMReX solver description
