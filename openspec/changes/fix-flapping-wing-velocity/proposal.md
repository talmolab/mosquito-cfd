# Proposal: Fix Flapping Wing Marker Velocities

## Summary

The flapping wing simulation runs without crashing (fixes from `fix-external-geometry-crash`
applied) but produces zero velocity everywhere. The IB penalty force is effectively zero
because marker velocities are never set correctly for the wing surface motion.

## Root Cause (Corrected)

`InteractWithEuler` calls these in order:

```
InitialWithLargrangianPoints(kernel)  ← sets 908 particle POSITIONS from pos_x/y/z ✓
ResetLargrangianPoints()              ← zeroes ALL U/V/W_Marker = 0
VelocityInterpolation(EulerVel)       ← writes U_fluid at each marker → U/V/W_Marker = U_fluid
ComputeLagrangianForce(dt, kernel)    ← F = (kernel.velocity + omega×r - U_Marker)/dt
ForceSpreading(...)
VelocityCorrection(...)
```

`ComputeLagrangianForce` computes the IB penalty force as:
```
F = (Ub + ω×r - U_Marker) / dt
```
where:
- `Ub = kernel.velocity` = **0** (hinge is fixed, doesn't translate)
- `ω = kernel.omega` = **0** (kernel angular velocity never set for flapping wing)
- `U_Marker` = fluid velocity at marker (written by `VelocityInterpolation`)

So: `F = (0 + 0 - U_fluid) / dt ≈ 0` since `U_fluid ≈ 0` initially.

Note: `U_Marker` holds the **fluid** velocity at the marker (written by `VelocityInterpolation`),
NOT the wing surface velocity. The wing surface velocity should appear via `Ub + ω×r`,
but `kernel.omega` is never updated to reflect the wing's instantaneous angular velocity.

## Fix

Three-part change to `talmolab/IAMReX` `feature/arbitrary-geometry`:

1. **`ExternalGeometry.H`**: Add `vel_x/y/z` PinnedVectors to `ExternalGeometryData`.
   Initialize to zero. Compute and store in `UpdateExternalGeometryPositions()` by calling
   `ComputeMarkerVelocities(time, dt, ...)`. Add `dt` parameter to
   `UpdateExternalGeometryPositions`.

2. **`DiffusedIB.H`**: Declare new method `SetExternalGeometryMarkerVelocities(const kernel&)`.

3. **`DiffusedIB.cpp`**:
   - In `UpdateParticles`, pass `dt` to `UpdateExternalGeometryPositions`.
   - In `InteractWithEuler`, insert call to `SetExternalGeometryMarkerVelocities(kernel)`
     **after** `VelocityInterpolation` (not before!).
   - Implement `SetExternalGeometryMarkerVelocities`: after `VelocityInterpolation` has written
     `U_Marker = U_fluid`, **subtract** the wing surface velocity:
     ```cpp
     Up[i] -= vel_x[id-1];   // U_Marker becomes U_fluid - U_wing
     Vp[i] -= vel_y[id-1];
     Wp[i] -= vel_z[id-1];
     ```
     Then `ComputeLagrangianForce` computes:
     ```
     F = (0 + 0 - (U_fluid - U_wing)) / dt = (U_wing - U_fluid) / dt  ✓
     ```

## Why `-=` and not `=`

`VelocityInterpolation` sets `U_Marker = U_fluid`. `ComputeLagrangianForce` computes
`F = (Ub + ω×r - U_Marker) / dt`. With `Ub = 0`, `ω = 0`:
- Setting `U_Marker = U_wing` (wrong `=`) → `F = -U_wing/dt` (wrong direction!)
- Setting `U_Marker -= U_wing` (correct `-=`) → `F = (U_wing - U_fluid)/dt` ✓

## Expected Outcome

After fix: `max(abs(u/v/w)) > 0` post-advance at step 2+ (step 1 has zero wing velocity in
`vel_x/y/z` because `UpdateParticles` populates velocities for the *next* step's
`InteractWithEuler`; this is acceptable since initial fluid velocity is zero).

## Test Plan

1. Edit source files in `c:\repos\IAMReX-fork\Source\` locally
2. Copy to `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\`
   (= `/workspace/` in the `flapping-wing-val7` container — see Container Workflow below)
3. Inside container: `cp /workspace/*.{cpp,H} /opt/cfd/IAMReX/Source/`
4. CPU debug build: `make -j$(nproc)` → `amr3d.gnu.DEBUG.MPI.ex`
5. Logic test: 5-step run, check `max(abs(u/v/w)) > 0` at step 2+
6. GPU build: `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.MPI.CUDA.ex`
7. If passing: commit to `talmolab/IAMReX`, update `build-args.env`, trigger CI rebuild

## Container Workflow Reference

- **Container**: `flapping-wing-val7` (RunAI workspace, image `ghcr.io/talmolab/mosquito-cfd:fp64`)
- **Workspace mount**: `/workspace` in container = `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/flapping_wing/` on cluster NFS
- **Local access**: `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\` on Windows (via `\\multilab-na.ad.salk.edu\hpi_dev` mapped to `Z:`)
- **Source files**: baked into image at `/opt/cfd/IAMReX/Source/` — must be copied from `/workspace/` inside container after staging
- **Build target (CPU)**: `make -j$(nproc)` → `amr3d.gnu.DEBUG.MPI.ex`
- **Build target (CUDA/GPU)**: `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.MPI.CUDA.ex`
- **Exec command**: `runai workspace exec flapping-wing-val7 -- sh -c '...'`