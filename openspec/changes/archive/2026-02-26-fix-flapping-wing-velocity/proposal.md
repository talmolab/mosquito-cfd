# Proposal: Fix Flapping Wing Marker Velocities

## Summary

Two bugs in IAMReX's diffused IB implementation prevent the flapping wing simulation from
running correctly. The first causes zero IB force (wing has no effect on fluid). The second
causes exponential velocity blow-up (simulation crashes at step ~157) due to IB force
overcorrection. Both are fixed in `talmolab/IAMReX` `feature/arbitrary-geometry`.

- Fix 1 committed: `69ac635` (surface velocity)
- Fix 2 committed: `2e9a851c` (marker volume dv)
- Validated: 200-step GPU simulation stable, plotfiles written ✓

## Why

The flapping wing simulation was non-functional due to two bugs in IAMReX's diffused IB
implementation: the wing had zero effect on the fluid (zero IB force), and after fixing that,
the simulation crashed with exponential velocity blow-up at step ~157. These bugs blocked all
flapping-wing CFD validation work.

## What Changes

- **`ExternalGeometry.H`**: Added `vel_x/y/z` PinnedVectors to `ExternalGeometryData`; added
  `dt` parameter to `UpdateExternalGeometryPositions` to enable velocity computation.
- **`DiffusedIB.H`**: Declared `SetExternalGeometryMarkerVelocities(const kernel&)`.
- **`DiffusedIB.cpp`**: Implemented `SetExternalGeometryMarkerVelocities` (subtracts wing
  velocity from `U_Marker` after `VelocityInterpolation`); replaced `dv = h³` with
  `dv = h × d_nn²` for surface geometry (geometry_type == 4).

## Root Cause 1: Zero IB Force (Marker Velocity Never Set)

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

## Fix 1: Set Marker Velocities Correctly

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

## Root Cause 2: IB Force Overcorrection (dv = h³ for Surface Markers)

After Fix 1, the simulation produces non-zero velocities but exponentially growing ones —
crashing with `|u| = 5.8e12` at step 157. Root cause: `InitParticles` sets `dv = h*h*h`
for all geometry types, including surface markers from vertex files.

For vertex-file geometry, the Lagrangian marker spacing `d_nn` is typically finer than the
Eulerian grid cell size `h`. The IB force spreading step distributes each marker's force
over nearby Eulerian cells weighted by a kernel:

```
F_cell = Σ_markers  (vel_wing - U_fluid) / dt  ×  dv  ×  kernel(x_cell - x_marker)
```

When `d_nn < h`, approximately `(h/d_nn)²` markers fall within each cell's kernel support.
With `dv = h³`, the total force per cell is multiplied by `(h/d_nn)²` — a 6.1× overcorrection
for the validation case (`d_nn = 0.0505`, `h = 0.125`). This drives the fluid 6× past the
wing velocity each timestep, causing exponential runaway.

## Fix 2: Correct Marker Volume for Surface Geometry

In `DiffusedIB.cpp`, `InitParticles`, replace `dv = h*h*h` for `geometry_type == 4` with:

```
dv = h * d_nn²
```

where:
- `d_nn²` is the area element represented by each surface marker
- `h` is the IB layer thickness (one cell wide)
- When `d_nn = h`, this reduces to `h³` (consistent with volume markers)

`d_nn` is estimated from the average nearest-neighbor distance over a sample of up to 200
markers using an O(N_sample × N) search in the xz plane (markers lie on a surface, y ≈ 0).

### Why This Formula

The correct surface IB formulation enforces the no-slip condition by applying a force equal to:

```
F_total = ρ × A_wing × h × (vel_wing - U_fluid) / dt
```

where `A_wing = N_markers × d_nn²`. Each marker's `dv = h × d_nn²` contributes one area
element. With `(h/d_nn)²` markers per cell, the forces sum to exactly `h³` per cell — the
same as a single volume marker, eliminating the overcorrection.

## Expected Outcome

- Fix 1: `max(abs(u/v/w)) > 0` at step 2+ (first non-zero IB response)
- Fix 2: simulation stable for full validation run; max velocities bounded at O(wing tip velocity)

## Test Plan (Completed)

**Fix 1 validation** (`flapping-wing-val7`, CPU debug binary):
- 50-step CPU test (test3.log): `max(abs(u/v/w)) = 12.66` at step 1, decreases to 10.17 at step 2 (IB braking) ✓

**Fix 2 validation** (`flapping-wing-val8`, CPU + GPU):
- CPU (test3.log, 50 steps): velocities stabilize at ~27, no blow-up ✓
- GPU (test5.log, 200 steps): all steps complete, final |u|≈10, |v|≈18, |w|≈6, plotfiles written ✓

**Commits**: `talmolab/IAMReX@69ac635` (Fix 1), `talmolab/IAMReX@2e9a851c` (Fix 2)
**Docker image**: `talmolab/mosquito-cfd@1a2ff62` triggers CI rebuild with both fixes

## Container Workflow Reference

- **Container**: `flapping-wing-val7` (RunAI workspace, image `ghcr.io/talmolab/mosquito-cfd:fp64`)
- **Workspace mount**: `/workspace` in container = `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/flapping_wing/` on cluster NFS
- **Local access**: `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\` on Windows (via `\\multilab-na.ad.salk.edu\hpi_dev` mapped to `Z:`)
- **Source files**: baked into image at `/opt/cfd/IAMReX/Source/` — must be copied from `/workspace/` inside container after staging
- **Build target (CPU)**: `make -j$(nproc)` → `amr3d.gnu.DEBUG.MPI.ex`
- **Build target (CUDA/GPU)**: `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.MPI.CUDA.ex`
- **Exec command**: `runai workspace exec flapping-wing-val7 -- sh -c '...'`