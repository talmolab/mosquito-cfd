# Benchmark Methods and Reproducibility

**Document Version**: 1.0
**Last Updated**: February 24, 2026
**For**: ALCF APEX Proposal Submission

## Overview

This document describes the methodology for GPU-accelerated CFD benchmarks used to estimate computational resource requirements for the APEX proposal. All simulations use the IAMReX solver with the diffused immersed boundary method on NVIDIA A40 GPUs.

## Software Stack

| Component | Version | Source |
|-----------|---------|--------|
| IAMReX | commit c5f8e2a | https://github.com/ruohai0925/IAMReX |
| AMReX | 24.11 | https://github.com/AMReX-Codes/amrex |
| CUDA | 12.4 | NVIDIA |
| GCC | 11.4 | Ubuntu 22.04 |
| MPI | OpenMPI 4.1.2 | Ubuntu packages |
| Docker image | ghcr.io/talmolab/mosquito-cfd:fp64 | This repository |

### Precision Decision

All benchmarks use **double precision (FP64)**. The IAMReX maintainer [does not test single precision](https://github.com/ruohai0925/IAMReX/issues/59), and preliminary testing showed numerical instabilities with FP32 builds.

## Hardware

### Development Platform (Measured)

| Specification | Value |
|---------------|-------|
| GPU | NVIDIA A40 |
| FP64 Performance | 0.585 TFLOPS |
| Memory Bandwidth | 696 GB/s |
| GPU Memory | 48 GB |
| System | Salk RunAI Cluster |

### Target Platform (APEX)

| Specification | Value |
|---------------|-------|
| GPU | NVIDIA A100 80GB |
| FP64 Performance | 9.7 TFLOPS |
| Memory Bandwidth | 2039 GB/s |
| GPU Memory | 80 GB |

### Performance Scaling Rationale

CFD solvers are typically **memory-bandwidth limited** due to the stencil operations in pressure solvers. We use the bandwidth ratio (2.9×) as our primary estimate for A40→A100 speedup, with the compute ratio (16.6×) as an upper bound:

| Factor | A40 | A100 | Ratio | Usage |
|--------|-----|------|-------|-------|
| FP64 TFLOPS | 0.585 | 9.7 | 16.6× | Upper bound |
| Memory BW (GB/s) | 696 | 2039 | 2.9× | **Primary estimate** |

## Benchmark Cases

### Case 1: FlowPastSphere (Re=100)

**Purpose**: Validate solver against canonical CFD benchmark.

| Parameter | Value |
|-----------|-------|
| Reynolds number | 100 |
| Sphere diameter | 1.0 (dimensionless) |
| Freestream velocity | 1.0 (x-direction) |
| Kinematic viscosity | 0.01 |
| Domain | 20 × 10 × 10 |
| Boundary conditions | Inflow (x=0), outflow (x=20), no-slip walls |
| Timestep | 0.01 (fixed) |
| Final time | 100.0 (10,000 steps) |

**Grid Resolutions**:

| Grid | Cells | IB Markers | Time/Step | Memory |
|------|-------|------------|-----------|--------|
| Coarse (128×64×64) | 524,288 | 129 | 0.30 s | 679 MB |
| Medium (256×128×128) | 4,194,304 | 515 | 1.76 s | 3,837 MB |

**Validation**: Literature Cd = 1.087 (Johnson & Patel 1999). See RESULTS.md for computed values and discrepancy investigation.

### Case 2: Heaving Ellipsoid (Re=100)

**Purpose**: Validate force computation for thin moving bodies approximating insect wings.

| Parameter | Value |
|-----------|-------|
| Geometry | Ellipsoid (IAMReX type 2) |
| Semi-axes | a=0.5, b=0.02, c=1.5 |
| Aspect ratio | 3:1 (matches mosquito wing) |
| Freestream velocity | 1.0 (x-direction) |
| Heave velocity | 0.5 (y-direction) |
| Domain | 20 × 10 × 10 |
| Grid | 256×128×128 (4.2M cells) |
| Timestep | 0.01 |
| Steps | 1,000 |

**Boundary Conditions**: x-direction uses inflow/outflow (non-periodic). y and z directions use periodic boundaries.

**Visualization Timestep**: Figures use t=5 (plt_1k00500) rather than the final timestep. At this time:
- Body has moved from y=5.0 to y=7.5 (2.5 units from periodic boundary)
- Wake is fully developed behind the body
- No periodic boundary artifacts in visualization

At t=10, the body reaches y=10.0 (the periodic boundary), and the wake begins wrapping around, creating visually confusing dual-wake patterns that don't represent the physics of interest.

**Force Sign Convention**: The lift force (Fy) is negative because the body heaves upward (+y) at constant velocity. The fluid exerts a resistive force opposing the motion (added mass + viscous drag). This is expected physics - the simulation captures:
- Added mass effects (from unsteady pressure buildup)
- Viscous drag (from boundary layer on thin ellipsoid surface)
- Form drag (from pressure distribution around the body)

**Note**: This is pure translation, not flapping flight. A wing generating lift requires pitching motion and/or angle of attack variation to create circulation.

**Validation**: Quasi-steady state reached by t=7.0 (forces change <1% thereafter).

## Measured Performance

### Throughput

| Case | Cells | Time/Step | Throughput |
|------|-------|-----------|------------|
| FlowPastSphere (coarse) | 524K | 0.30 s | 1.75 M cells/s |
| FlowPastSphere (medium) | 4.2M | 1.76 s | 2.38 M cells/s |
| Heaving ellipsoid | 4.2M | 1.89 s | 2.22 M cells/s |

### Scaling Behavior

**Superlinear scaling observed**: 8× cells → 5.9× time (throughput increased 36%). This is typical for GPU codes where larger problems achieve better occupancy and memory access patterns.

### Memory Usage

GPU memory scales linearly with cell count. With 48 GB available on A40, the maximum problem size is approximately 50M cells.

## Resource Estimation Methodology

### Per-Simulation Cost

For production mosquito wing simulations:

| Parameter | Value | Basis |
|-----------|-------|-------|
| Grid cells | 10M | Sufficient for Re~100 wing |
| Throughput | 2.38 M cells/s | Measured on A40 (medium grid) |
| A40 time/step | 4.20 s | 10M / 2.38M |
| A100 time/step | 1.45 s | A40 / 2.9 (bandwidth-limited) |
| Steps/wingbeat | 5,000 | Temporal resolution |
| Wingbeats | 100 | Statistical convergence |
| Total steps | 500,000 | 5000 × 100 |
| A100 hours/sim | 201 | 500k × 1.45s / 3600 |

### APEX Request

| Milestone | Simulations | GPU-hours |
|-----------|-------------|-----------|
| Code validation | 10 | 50 |
| Single wing baseline | 5 | 1,006 |
| Kinematic sweep (50 configs) | 50 | 10,061 |
| Re sensitivity (50 configs) | 50 | 10,061 |
| Production dataset | 250 | 50,307 |
| **Subtotal** | | **71,487** |
| **Contingency (20%)** | | **14,297** |
| **Total Request** | | **85,784** |

## Reproducibility

### Docker Image

All simulations use the verified FP64 Docker image:

```bash
docker pull ghcr.io/talmolab/mosquito-cfd:fp64
```

The image is built from `docker/Dockerfile.iamrex` in this repository.

### Run Commands

**FlowPastSphere (medium grid)**:
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

**Heaving Ellipsoid**:
```bash
runai workspace submit heaving-ellipsoid \
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

### Analysis Scripts

Force extraction and visualization:

```python
from mosquito_cfd.benchmarks.analyze_sphere import extract_sphere_cd

# Extract drag coefficient from plotfile
result = extract_sphere_cd('path/to/plt10000')
print(f"Cd = {result['cd']:.4f}")
```

### Metadata

Each benchmark run produces `run_metadata.json`:

```json
{
  "run_id": "uuid",
  "timestamp": "ISO8601",
  "git_commit": "sha256",
  "docker_image": "ghcr.io/talmolab/mosquito-cfd:fp64@sha256:...",
  "hardware": {
    "gpu_model": "NVIDIA A40",
    "cuda_version": "12.4"
  },
  "timing": {
    "wall_time_s": 17902,
    "timesteps": 10000,
    "time_per_step_s": 1.76
  }
}
```

## Known Limitations

1. **Force coefficient discrepancy**: Computed Cd is ~60% lower than literature. Under investigation - may be related to diffused IB force extraction method.

2. **Geometry constraints**: IAMReX only supports sphere, ellipsoid, and cylinder. Realistic wing shapes require geometry extension or alternative solver.

3. **Kinematics constraints**: Only constant prescribed velocities supported. Time-varying flapping requires IAMReX code modification.

4. **Periodic boundary in heave direction**: The heaving ellipsoid simulation uses periodic boundaries in the y-direction (heave direction). For long simulations, the wake wraps around. Future improvements:
   - Heave in x-direction (non-periodic) instead of y
   - Use larger y-domain so wake doesn't reach boundary
   - Implement non-periodic y-boundary with proper outflow conditions

5. **Pure translation, not flapping**: The heaving ellipsoid demonstrates force computation but does not produce aerodynamic lift. Actual flapping flight requires coordinated pitching motion to generate circulation.

## References

- Johnson, T. A., & Patel, V. C. (1999). Flow past a sphere up to a Reynolds number of 300. *J. Fluid Mech.*, 378, 19-70.
- Bomphrey, R. J., et al. (2017). Smart wing rotation and trailing-edge vortices enable high frequency mosquito flight. *Nature*, 544, 92-95.
- Li, X., et al. (2024). An open-source, adaptive solver for particle-resolved simulations. *Phys. Fluids*, 36(11), 113335.