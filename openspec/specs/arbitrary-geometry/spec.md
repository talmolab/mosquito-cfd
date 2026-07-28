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

### Requirement: Parametric Wing Planform Generator

The system SHALL provide a Python CLI tool to generate Lagrangian marker files for wing planforms.

#### Scenario: Generate rectangular flat plate

**Given** the user wants a rectangular wing approximation
**When** they run `uv run generate-wing-planform --shape rectangular --span 3e-3 --chord 1e-3 --marker-spacing 50e-6 --output wing.vertex`
**Then** a `.vertex` file is created with markers forming a uniform rectangular grid of 60×20 = 1,200 points

#### Scenario: Generate elliptic planform

**Given** the user wants a more realistic elliptic wing shape
**When** they run `uv run generate-wing-planform --shape elliptic --span 3e-3 --chord 1e-3 --marker-spacing 50e-6 --output wing.vertex`
**Then** a `.vertex` file is created with markers following an elliptic planform where local chord varies as c(z) = c₀√(1-(2z/span)²)

#### Scenario: Verify marker spacing

**Given** a generated `.vertex` file
**When** the user loads it and computes inter-marker distances
**Then** the mean spacing matches the requested `--marker-spacing` within 10%

---

### Requirement: External Geometry Loading in IAMReX

IAMReX SHALL support loading immersed boundary markers from external `.vertex` files.

#### Scenario: Load vertex file

**Given** an input file with `particle_inputs.geometry_type = 4` and `particle_inputs.geometry_file = wing.vertex`
**When** IAMReX initializes
**Then** the particles are created at positions read from `wing.vertex`

#### Scenario: Apply center offset

**Given** an input file with `particle_inputs.center_x/y/z = 0.015`
**When** the vertex file contains a marker at (0, 0, 0)
**Then** the marker is placed at (0.015, 0.015, 0.015) in the simulation domain

#### Scenario: Apply scale factor

**Given** an input file with `particle_inputs.scale = 1000.0` (converting mm to m)
**When** the vertex file contains markers in millimeters
**Then** the markers are scaled to meters in the simulation

---

### Requirement: Prescribed Sinusoidal Kinematics

IAMReX SHALL update wing marker positions each timestep according to van Veen et al. (2022) sinusoidal kinematics.

#### Scenario: Stroke angle varies sinusoidally

**Given** a simulation running with prescribed kinematics
**When** time = T/4 (quarter period, T = 1/600 s)
**Then** the stroke angle φ = φ₀ = 70° (maximum stroke)

#### Scenario: Pitch leads stroke by 90°

**Given** a simulation running with prescribed kinematics
**When** time = 0 (start of wingbeat)
**Then** stroke angle φ = 0° AND pitch angle α = 45° (pitch at maximum when stroke crosses zero)

#### Scenario: Markers rotate about hinge

**Given** a wing with hinge at (0.015, 0.015, 0.015)
**When** kinematics are applied
**Then** all markers rotate about the hinge point (not the domain origin)

#### Scenario: Marker positions are updated each timestep

**Given** a simulation with Δt = 1×10⁻⁷ s
**When** advancing from step n to step n+1
**Then** marker positions are recomputed based on the new time t = (n+1)×Δt

---

### Requirement: Validation Against Van Veen Parameters

The implementation SHALL reproduce van Veen et al. (2022) simulation parameters.

#### Scenario: Frequency matches van Veen

**Given** the hardcoded kinematics implementation
**Then** wingbeat frequency = 600 Hz exactly

#### Scenario: Stroke amplitude matches van Veen

**Given** the hardcoded kinematics implementation
**Then** stroke amplitude = ±70° (140° peak-to-peak)

#### Scenario: Pitch angle matches van Veen

**Given** the hardcoded kinematics implementation
**Then** pitch angle at midstroke = 45°

#### Scenario: Reynolds number range achievable

**Given** van Veen parameters and standard air properties (ν = 1.56×10⁻⁵ m²/s)
**When** computing Re = U_tip × chord / ν
**Then** Re is in the range 100–300 for typical tip velocities

---

### Requirement: Force Output Compatibility

Force data from moving bodies SHALL be extractable using the existing analysis pipeline.

#### Scenario: Force components available in particle data

**Given** a completed simulation with flapping wing
**When** reading the plot file with yt
**Then** `particle_real_comp3/4/5` contain force components (Fx, Fy, Fz)

#### Scenario: Forces vary periodically

**Given** a simulation running for multiple wingbeats
**When** extracting force time series
**Then** forces show periodic behavior with period T = 1/600 s

---

