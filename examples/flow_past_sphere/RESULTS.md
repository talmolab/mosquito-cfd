# FlowPastSphere Validation Results

**Date**: February 23-24, 2026
**Platform**: NVIDIA A40 (Salk RunAI cluster)
**Docker Image**: `ghcr.io/talmolab/mosquito-cfd:fp64`

## Summary

FlowPastSphere at Re=100 is a canonical CFD validation case. We ran two grid resolutions to steady state (10,000 timesteps) to validate IAMReX and extract timing data for APEX proposal.

## Configuration

| Parameter | Value |
|-----------|-------|
| Reynolds number | 100 |
| Sphere diameter | 1.0 (dimensionless) |
| Sphere center | (5.0, 5.0, 5.0) |
| Domain | 20 × 10 × 10 |
| Freestream velocity | 1.0 (x-direction) |
| Kinematic viscosity | 0.01 |
| Timestep | 0.01 (fixed) |
| Final time | 100.0 (10,000 steps) |

## Grid Convergence Results

| Resolution | Cells | IB Markers | Wall Time | Time/Step | GPU Memory |
|------------|-------|------------|-----------|-----------|------------|
| 128×64×64 | 524,288 | 129 | 51 min | 0.30 s | 679 MB |
| 256×128×128 | 4,194,304 | 515 | 4.97 hr | 1.76 s | 3,837 MB |

### Scaling Analysis

- **Cell scaling**: 8× cells (coarse → medium)
- **Time scaling**: 5.9× wall time
- **Scaling**: Superlinear (8× cells → 5.9× time, throughput increased 36%)
- **Memory**: Linear with cell count

## Steady State Verification

Drag coefficient (Cd) vs simulation time:

| Time | Coarse Cd | Medium Cd |
|------|-----------|-----------|
| 10.0 | 0.504 | 0.450 |
| 20.0 | 0.503 | 0.449 |
| 40.0 | 0.503 | 0.448 |
| 60.0 | 0.503 | 0.448 |
| 80.0 | 0.503 | 0.448 |
| 100.0 | 0.503 | 0.448 |

**Conclusion**: Both simulations reached steady state by t=40 (4,000 timesteps).

## Drag Coefficient Analysis

### Computed Values

| Grid | Computed Cd | Literature Cd | Discrepancy |
|------|-------------|---------------|-------------|
| Coarse | 0.503 | 1.087 | -54% |
| Medium | 0.448 | 1.087 | -59% |

### Literature Reference
- Johnson & Patel (1999): Cd = 1.087 at Re = 100
- Clift et al. (1978): Cd = 1.09

### Investigation Required

The computed Cd is systematically ~60% lower than literature. Possible causes:

1. **Force extraction method**: We use `particle_real_comp3/4/5` as force components per IAMReX convention. This may not be correct for the diffused IB method.

2. **Diffused IB scaling**: The diffused IB method spreads forces over a regularization kernel. The total force may require integration with appropriate kernel weights.

3. **Component mapping**: The 9 `particle_real_comp` fields may store different quantities than assumed. Need to verify against IAMReX source code.

**Raw particle data at steady state (plt10000)**:
```
comp0: sum=3.69, mean=0.007 (possibly velocity correction x)
comp1: sum=-0.0002, mean~0 (possibly velocity correction y)
comp2: sum=0.0007, mean~0 (possibly velocity correction z)
comp3: sum=-0.176, mean=-0.0003 (assumed force x - USED FOR CD)
comp4: sum=0.00001, mean~0 (assumed force y)
comp5: sum=-0.00003, mean~0 (assumed force z)
comp6-8: all ~0
```

**Action item**: Consult IAMReX documentation or maintainer (Dr. Yadong Zeng) to verify correct force extraction procedure.

## Performance Data for APEX Proposal

### A40 Timing (Measured)

| Metric | Coarse | Medium | Unit |
|--------|--------|--------|------|
| Total cells | 524,288 | 4,194,304 | - |
| Steps | 10,000 | 10,000 | - |
| Wall time | 3,055 | 17,902 | seconds |
| Time per step | 0.30 | 1.76 | seconds |
| Throughput | 1.7M | 2.4M | cells/sec |
| GPU memory | 679 | 3,837 | MB |

### A100 Projection

| Factor | Ratio | Basis |
|--------|-------|-------|
| FP64 compute | 16.6× | A100 9.7 / A40 0.585 TFLOPS |
| Memory BW | 2.9× | A100 2039 / A40 696 GB/s |

**Conservative estimate** (memory-bound): 2.9× speedup
- Medium grid on A100: ~1 hr (vs 5 hr on A40)
- Enables ~50× more parameter sweeps in same wall time

**Optimistic estimate** (compute-bound): 16.6× speedup
- Medium grid on A100: ~18 min

## Output Files

### Cluster Storage
```
/hpi/hpi_dev/users/eberrigan/mosquito-cfd-benchmarks/
├── flow_past_sphere_coarse/
│   ├── plt00000, plt00100, ..., plt10000 (101 plot files)
│   └── chk00000, chk04000, chk08000, chk10000 (4 checkpoints)
└── flow_past_sphere_10k/
    ├── plt00000, plt00100, ..., plt10000 (101 plot files)
    └── chk00000, chk04000, chk08000, chk10000 (4 checkpoints)
```

### Plot File Contents
- `x_velocity`, `y_velocity`, `z_velocity`
- `density`, `tracer`
- `gradpx`, `gradpy`, `gradpz`
- `particles/` — IB marker data

## Visualization

Velocity field visualizations generated with yt are available in:
```
examples/flow_past_sphere/
├── plt00100_x_velocity.png
├── plt00100_y_velocity.png
└── plt00100_z_velocity.png
```

## Reproducibility

### Run Commands

**Coarse grid (128×64×64)**:
```bash
runai workspace submit sphere-coarse \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --gpu-devices-request 1 \
  --host-path path=/hpi/hpi_dev/users/$USER/mosquito-cfd-benchmarks,mount=/workspace \
  --command -- bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
    mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere \
    amr.n_cell='128 64 64' \
    amr.plot_file=/workspace/flow_past_sphere_coarse/plt \
    amr.check_file=/workspace/flow_past_sphere_coarse/chk \
    max_step=10000"
```

**Medium grid (256×128×128)**:
```bash
runai workspace submit sphere-medium \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --gpu-devices-request 1 \
  --host-path path=/hpi/hpi_dev/users/$USER/mosquito-cfd-benchmarks,mount=/workspace \
  --command -- bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
    mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere \
    amr.n_cell='256 128 128' \
    amr.plot_file=/workspace/flow_past_sphere_10k/plt \
    amr.check_file=/workspace/flow_past_sphere_10k/chk \
    max_step=10000"
```

### Analysis

Extract Cd using:
```python
from mosquito_cfd.benchmarks.analyze_sphere import extract_sphere_cd

result = extract_sphere_cd('Z:/users/eberrigan/mosquito-cfd-benchmarks/flow_past_sphere_10k/plt10000')
print(f"Cd = {result['cd']:.4f}")
```

## References

- Johnson, T. A., & Patel, V. C. (1999). Flow past a sphere up to a Reynolds number of 300. *Journal of Fluid Mechanics*, 378, 19-70.
- Clift, R., Grace, J. R., & Weber, M. E. (1978). *Bubbles, Drops, and Particles*. Academic Press.
- Li, X., et al. (2024). An open-source, adaptive solver for particle-resolved simulations. *Physics of Fluids*, 36(11), 113335.