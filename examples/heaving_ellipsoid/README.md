# Heaving Ellipsoid Example

Thin ellipsoid heaving through fluid at Re=100, approximating a flat plate wing.

## Purpose

IAMReX only supports sphere, ellipsoid, and cylinder geometries. This example uses a **thin ellipsoid** to approximate a flat plate wing for APEX proposal benchmarking.

## Geometry

| Parameter | Value | Description |
|-----------|-------|-------------|
| Semi-axis a | 0.5 | Chord direction (x) |
| Semi-axis b | 0.02 | Thickness (y) - very thin |
| Semi-axis c | 1.5 | Span direction (z) |
| Aspect ratio | 3:1 | Matches mosquito wing AR |

## Physics

| Parameter | Value |
|-----------|-------|
| Reynolds number | 100 |
| Kinematic viscosity | 0.01 |
| Freestream velocity | 1.0 (x-direction) |
| Heaving velocity | 0.5 (y-direction) |

## Running

### Inside Docker container:

```bash
# Copy inputs to workspace
cp /opt/cfd/mosquito-cfd/examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid /workspace/

# Run simulation
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex /workspace/inputs.3d.heaving_ellipsoid \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=100
```

### On RunAI cluster:

```bash
runai submit heaving-ellipsoid \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --gpu 1 \
  --cpu 4 \
  --memory 32Gi \
  --pvc multilab-data-salk:/data \
  --command -- bash -c "cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
    mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex \
    /data/users/\$USER/mosquito-cfd/examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid \
    amr.plot_file=/data/users/\$USER/mosquito-cfd/examples/heaving_ellipsoid/plt \
    amr.check_file=/data/users/\$USER/mosquito-cfd/examples/heaving_ellipsoid/chk \
    max_step=1000"
```

## Limitations

1. **Constant velocity**: IAMReX only supports constant prescribed velocities, not time-varying kinematics
2. **Approximate geometry**: Ellipsoid is not a true flat plate; expect ~20% force coefficient differences
3. **No rotation**: Full 3-angle flapping kinematics requires IAMReX code modification

## Future Work

- Extend IAMReX to support `geometry_type=4` for flat plate from marker file
- Use IBAMR for immediate flat plate support (CPU-only)
- See [cfd-approach.md](C:\vaults\physics surrogate models\cfd-approach.md) for solver comparison

## References

- van Veen et al. (2022). Wing geometry for Aedes aegypti
- Bomphrey et al. (2017). Mosquito kinematics (f=717 Hz, phi_0=39 deg)