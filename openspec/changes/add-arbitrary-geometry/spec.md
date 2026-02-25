## Requirements Specification

This document defines the acceptance criteria for arbitrary geometry support using Given/When/Then scenarios.

---

## Geometry Loading

### R1: Vertex File Reading

**Given** a `.vertex` file with the format:
```
<number_of_markers>
x1 y1 z1
x2 y2 z2
...
```

**When** IAMReX initializes particles with `geometry_type = 4`

**Then**:
- All markers are read and stored as Lagrangian particles
- Marker positions match the file contents (within floating-point precision)
- Reference positions are stored for kinematic transformations

### R2: Vertex File Error Handling

**Given** `geometry_type = 4` and `geometry_file` points to a non-existent file

**When** IAMReX attempts to initialize particles

**Then**:
- IAMReX aborts with a clear error message naming the missing file
- No undefined behavior or silent failures

### R3: Center and Scale

**Given** a `.vertex` file with markers centered at origin

**When** loading with `center_x=0.025`, `center_y=0.025`, `center_z=0.025`, `scale=1.0`

**Then**:
- All markers are translated by (0.025, 0.025, 0.025)
- Final positions = (file_x * scale + center_x, file_y * scale + center_y, file_z * scale + center_z)

---

## Planform Generator

### R4: Rectangular Planform

**Given** parameters: shape=rectangular, span=3mm, chord=1mm, spacing=0.05mm

**When** generating wing markers

**Then**:
- Markers form a rectangular grid in the x-z plane (y = center_y)
- Marker count = (span/spacing) × (chord/spacing) = 60 × 20 = 1,200 markers
- Markers are centered at the specified center position

### R5: Elliptic Planform

**Given** parameters: shape=elliptic, span=3mm, chord=1mm, spacing=0.05mm

**When** generating wing markers

**Then**:
- Markers form an elliptic outline in the x-z plane
- Local chord at each spanwise station: c(z) = chord × sqrt(1 - (2z/span)²)
- Total marker count < rectangular case (ellipse inscribed in rectangle)
- Markers are centered at the specified center position

### R6: Vertex File Output

**Given** generated markers from any planform

**When** writing to `.vertex` file

**Then**:
- First line contains integer marker count
- Subsequent lines contain `x y z` in scientific notation (%.10e format)
- File is human-readable and round-trips correctly (write→read→compare)

---

## Kinematics

### R7: Van Veen Sinusoidal Kinematics

**Given**:
- Hardcoded parameters: freq=600Hz, φ_amp=70°, α_0=45°, θ=0°
- Reference marker positions stored at t=0

**When** computing kinematics at time t

**Then**:
- Stroke angle: φ(t) = φ_amp × sin(2πft)
- Pitch angle: α(t) = α_0 × cos(2πft) [90° phase lead]
- Deviation: θ(t) = 0 [planar stroke]
- Rotation matrix R = Rz(φ) × Ry(θ) × Rx(α) [ZYX convention]

### R8: Marker Transformation

**Given**:
- Markers at reference positions relative to hinge
- Rotation matrix R computed from current angles

**When** updating marker positions

**Then**:
- Each marker: new_pos = hinge + R × (ref_pos - hinge)
- Transformation preserves marker spacing (rigid body rotation)
- No markers leave the computational domain

### R9: Velocity Computation

**Given** markers with prescribed motion

**When** computing marker velocities for IBM forcing

**Then**:
- Velocities are consistent with position changes (d(pos)/dt)
- Velocities are provided to the immersed boundary solver
- No velocity discontinuities at motion boundaries

---

## Validation Criteria

### R10: Force Coefficient Range

**Given** a 1-wingbeat simulation with van Veen parameters

**When** computing force coefficients

**Then**:
- Mean lift coefficient: CL ∈ [0.5, 1.5]
- Mean drag coefficient: CD > 0 (positive drag)
- Force coefficients computed as: C = F / (0.5 × ρ × U_tip² × A_wing)

### R11: Force Timing

**Given** force time series over one wingbeat

**When** analyzing force peaks

**Then**:
- Peak lift occurs near mid-stroke (phase ≈ 0.25 or 0.75, ±0.1 tolerance)
- Force magnitude varies with stroke phase (not constant)

### R12: LEV Formation

**Given** velocity/vorticity field at mid-stroke

**When** visualizing flow structure

**Then**:
- Leading-edge vortex (LEV) is visible in vorticity plots
- LEV is attached to wing surface (not fully shed)
- Flow structure qualitatively matches van Veen Fig. 3-4

---

## Metadata and Reproducibility

### R13: Auto-Detected Metadata

**Given** a completed simulation run

**When** generating `run_metadata.json`

**Then**:
- All fields are auto-detected at runtime (no hardcoded values)
- Git commit, branch, dirty status captured via `git` commands
- GPU model and CUDA version detected via `nvidia-smi` and `nvcc`
- File hashes computed via SHA256
- Input parameters parsed from inputs file

### R14: Figure Reproducibility

**Given** simulation output (plotfiles) and metadata

**When** running `generate_all_figures.py`

**Then**:
- All required figures (G1, K1, K2, F1, V1, V2) are regenerated
- Figures use consistent styling (plot_config.py)
- Figures include appropriate titles and annotations
- Output formats: PDF (vector) and PNG (raster, 300 DPI)

### R15: Data Provenance

**Given** `run_metadata.json` from any validation run

**When** reviewing provenance

**Then**:
- Exact IAMReX commit SHA is recorded
- Docker image digest is recorded (if containerized)
- Input file SHA256 hash allows verification
- Vertex file SHA256 hash allows verification

---

## Integration

### R16: Docker Build

**Given** the fork `talmolab/IAMReX` with arbitrary geometry support

**When** building `ghcr.io/talmolab/mosquito-cfd:fp64`

**Then**:
- Docker image builds successfully
- FlowPastSphere regression test passes (Cd ≈ 1.09)
- Flapping wing example runs without errors

### R17: Example Directory Structure

**Given** the completed implementation

**When** checking `examples/flapping_wing/`

**Then** the directory contains:
- `inputs.3d.flapping_wing` — IAMReX input file
- `wing.vertex` — Generated wing markers
- `run.sh` — Simulation launch script
- `visualize.py` — Post-processing script
- `generate_all_figures.py` — Figure generation orchestrator
- `plot_config.py` — Plotting style configuration
- `RESULTS.md` — Validation results documentation

---

## Priority

| Requirement | Priority | Deadline |
|-------------|----------|----------|
| R1–R3 (Geometry loading) | P0 | Feb 24, 2026 |
| R4–R6 (Planform generator) | P0 | Feb 24, 2026 |
| R7–R9 (Kinematics) | P0 | Feb 25, 2026 |
| R10–R12 (Validation criteria) | P0 | Feb 26, 2026 |
| R13–R15 (Metadata) | P0 | Feb 27, 2026 |
| R16–R17 (Integration) | P0 | Feb 27, 2026 |