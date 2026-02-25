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

**Note**: Force extraction uses `particle_real_comp3/4/5`. Same ~60% discrepancy observed for FlowPastSphere Cd suggests systematic calibration needed.

## Limitations Observed

1. **Constant velocity only**: IAMReX only supports constant prescribed velocities, not time-varying kinematics like sinusoidal heaving
2. **No rotation**: Full 3-angle flapping (φ, α, θ) requires IAMReX code modification
3. **Approximate geometry**: Ellipsoid is not a true flat plate; expect differences in force coefficients

## Next Steps

1. ~~**Run to quasi-steady state**: Extend to 1000 steps to observe force convergence~~ **DONE**
2. **Verify force extraction**: Confirm comp3/4/5 interpretation with IAMReX maintainer
3. **Generate visualizations**: Velocity field slices showing ellipsoid wake
4. **Compare with theory**: Quasi-steady added mass predictions
5. **Calibration study**: Compare sphere and ellipsoid discrepancies

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
