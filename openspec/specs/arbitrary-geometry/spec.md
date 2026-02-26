# arbitrary-geometry Specification

## Purpose
TBD - created by archiving change fix-external-geometry-crash. Update Purpose after archive.
## Requirements
### Requirement: GPU-Safe Marker Position Storage

The arbitrary geometry implementation SHALL store marker positions in `amrex::Gpu::PinnedVector<Real>` (pinned host memory), which is directly accessible from both CPU and GPU without explicit copy.

**Note**: The original proposal described a `Gpu::copy()` approach. Investigation showed the actual root cause was arena initialization ordering; switching to `PinnedVector` is simpler and avoids the ordering problem entirely.

#### Scenario: Initialize marker positions

**Given** a `.vertex` file with N markers has been read into host vectors

**When** `InitializeExternalGeometry()` fills `pos_x/y/z`

**Then**:
- `pos_x`, `pos_y`, `pos_z` are `amrex::Gpu::PinnedVector<amrex::Real>`
- CPU writes directly: `data.pos_x[i] = reference_positions[i][0]`
- GPU kernels read via `pos_x.dataPtr()` without any explicit transfer
- No `amrex::Gpu::DeviceVector` or `amrex::Gpu::copy()` calls needed

#### Scenario: Update marker positions each timestep

**Given** kinematics have been applied to update `current_positions`

**When** `UpdateExternalGeometryPositions()` syncs positions

**Then**: CPU writes directly into `pos_x/y/z` PinnedVector elements — GPU reads the updated values on the next kernel launch without any explicit copy

---

### Requirement: Level-Set Field for External Geometry

The `calculate_phi_nodal()` function SHALL compute a valid level-set field for `geometry_type == 4`.

#### Scenario: phi_nodal computed for external geometry

**Given** a kernel with `geometry_type == 4` and `num_markers` Lagrangian markers at current positions

**When** `calculate_phi_nodal(phi_nodal, kernel)` is called in `UpdateParticles()`

**Then**:
- No `amrex::Abort` is called
- For each nodal grid point `(i,j,k)`, `phi_nodal(i,j,k)` = `(min_dist_to_nearest_marker - dx) / radius`
- The computation runs as a GPU kernel over the nodal box
- `phi_nodal < 0` for grid points within one `dx` of a marker
- `phi_nodal > 0` for grid points farther than one `dx` from all markers

#### Scenario: No regression for sphere and ellipsoid

**Given** `geometry_type == 1` (sphere) or `geometry_type == 2` (ellipsoid)

**When** `calculate_phi_nodal()` is called

**Then**: Behavior is identical to before this fix — sphere/ellipsoid level-set formulas unchanged

---

### Requirement: Runtime Stability Through First Timestep

The simulation SHALL complete at least one full timestep without crashing.

#### Scenario: First timestep completes

**Given** inputs.3d.validation with `geometry_type = 4` and a valid `.vertex` file

**When** the simulation advances from step 0 to step 1

**Then**:
- `InitialWithLargrangianPoints` succeeds (markers at correct positions)
- `VelocityInterpolation`, `ComputeLagrangianForce`, `ForceSpreading` all complete
- `UpdateParticles` completes (including `calculate_phi_nodal` for geometry_type=4)
- `plt00000` and `chk00000` are written to output directory

