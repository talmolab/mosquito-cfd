## ADDED Requirements

### Requirement: Parametric Wing Planform Generator

The system shall provide a Python CLI tool to generate Lagrangian marker files for wing planforms.

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

IAMReX shall support loading immersed boundary markers from external `.vertex` files.

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

IAMReX shall update wing marker positions each timestep according to van Veen et al. (2022) sinusoidal kinematics.

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

The implementation shall reproduce van Veen et al. (2022) simulation parameters.

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

Force data from moving bodies shall be extractable using the existing analysis pipeline.

#### Scenario: Force components available in particle data

**Given** a completed simulation with flapping wing
**When** reading the plot file with yt
**Then** `particle_real_comp3/4/5` contain force components (Fx, Fy, Fz)

#### Scenario: Forces vary periodically

**Given** a simulation running for multiple wingbeats
**When** extracting force time series
**Then** forces show periodic behavior with period T = 1/600 s

---

## FUTURE Requirements (Post-Award)

### Requirement: Input-File Configurable Kinematics

*Not implemented for APEX proposal. Documented for future extension.*

The system shall support reading kinematics parameters from the input file.

#### Scenario: User specifies frequency

**Given** an input file with `particle_inputs.frequency = 717.0`
**When** IAMReX runs
**Then** the wingbeat frequency is 717 Hz (not hardcoded 600 Hz)

---

### Requirement: Time Series Kinematics

*Not implemented for APEX proposal. Documented for future extension.*

The system shall support reading arbitrary kinematics from external files.

#### Scenario: Load measured kinematics

**Given** a kinematics file with columns (time, phi, alpha, theta)
**When** IAMReX runs
**Then** angles are interpolated from the file at each timestep

---

### Requirement: MJCF Geometry Extraction

*Not implemented for APEX proposal. Documented for future extension.*

The system shall support extracting geometry from MuJoCo XML files.

#### Scenario: Convert MJCF to vertex

**Given** an MJCF file with a wing body mesh
**When** running `uv run mjcf-to-vertex --mjcf mosquito.xml --body left_wing`
**Then** a `.vertex` file is created with surface markers matching the mesh geometry