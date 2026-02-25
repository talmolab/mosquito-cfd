## CRITICAL TIMELINE

**APEX Proposal Deadline: February 27, 2026**

Flapping wing validation results MUST be included in the proposal to demonstrate scientific capability. Implementation must complete before deadline.

| Day | Date | Deliverable |
|-----|------|-------------|
| Day 1 | Feb 24 | Fork IAMReX, implement vertex reader, Python planform generator |
| Day 2 | Feb 25 | Implement kinematics, rebuild Docker image |
| Day 3 | Feb 26 | Run validation, extract forces, generate visualizations |
| Day 4 | Feb 27 | Document results in RESULTS.md, integrate into proposal |

---

## Phase 1: Documentation (COMPLETE)

### 1.1 OpenSpec Proposal
- [x] 1.1.1 Create `add-arbitrary-geometry` change directory
- [x] 1.1.2 Write proposal.md with APEX scope vs future extensions
- [x] 1.1.3 Write design.md with technical architecture
- [x] 1.1.4 Write spec.md with requirements and scenarios
- [x] 1.1.5 Write tasks.md (this file)

### 1.2 Literature Review
- [x] 1.2.1 Extract van Veen et al. (2022) kinematic parameters
- [x] 1.2.2 Extract Bomphrey et al. (2017) experimental data
- [x] 1.2.3 Document validation criteria and acceptance thresholds

---

## Phase 2: Implementation (Feb 24-25, PRE-PROPOSAL)

### 2.1 Python Planform Generator

#### 2.1.1 Core Module
- [ ] Create `src/mosquito_cfd/geometry/__init__.py`
- [ ] Implement `parametric_planform.py` with rectangular generator
- [ ] Implement `parametric_planform.py` with elliptic generator
- [ ] Implement `vertex_io.py` for read/write functions

#### 2.1.2 CLI Tool
- [ ] Add `generate-wing-planform` entry point to `pyproject.toml`
- [ ] Implement argument parsing (shape, span, chord, spacing, center, output)
- [ ] Add `--help` documentation

#### 2.1.3 Testing
- [ ] Unit test: rectangular planform marker count
- [ ] Unit test: elliptic planform shape
- [ ] Unit test: vertex file round-trip (write then read)
- [ ] Integration test: generate file, verify readable by simple parser

**Validation checkpoint**: Generated `.vertex` files should be human-readable and match expected marker counts.

---

### 2.2 IAMReX Fork Setup

#### 2.2.1 Create Fork
- [ ] Fork `ruohai0925/IAMReX` to `talmolab/IAMReX`
- [ ] Clone fork locally for development
- [ ] Verify build with existing FlowPastSphere tutorial

#### 2.2.2 Branch Strategy
- [ ] Create `feature/arbitrary-geometry` branch
- [ ] Document branching strategy in fork README

**Validation checkpoint**: Fork builds and runs FlowPastSphere identically to upstream.

---

### 2.3 Vertex File Reader (C++)

#### 2.3.1 Implementation
- [ ] Create `Source/particles/VertexFileReader.cpp`
- [ ] Implement `ReadVertexFile()` function
- [ ] Add error handling for missing/malformed files

#### 2.3.2 Integration
- [ ] Add `geometry_type = 4` case to `ParticleInit.cpp`
- [ ] Parse `geometry_file`, `center_x/y/z`, `scale` from input
- [ ] Store reference positions for kinematics

#### 2.3.3 Testing
- [ ] Test: Load simple 3-marker file, verify positions
- [ ] Test: Load wing.vertex from Python generator
- [ ] Test: Verify center offset applied correctly
- [ ] Test: Verify scale factor applied correctly

**Validation checkpoint**: IAMReX loads `.vertex` file and initializes particles at correct positions.

---

## Phase 3: Kinematics Implementation (Feb 25, PRE-PROPOSAL)

### 3.1 Rotation Matrix

#### 3.1.1 Implementation
- [ ] Create `Source/particles/WingKinematics.cpp`
- [ ] Implement `ComputeRotationMatrix()` for ZYX Euler angles
- [ ] Unit test rotation matrix against known values

### 3.2 Kinematics Update

#### 3.2.1 Implementation
- [ ] Implement `UpdateWingKinematics()` with hardcoded van Veen parameters
- [ ] Store reference positions at initialization
- [ ] Transform markers about hinge each timestep

#### 3.2.2 Integration
- [ ] Call `UpdateWingKinematics()` at start of each timestep
- [ ] Add `m_do_prescribed_motion` flag to enable/disable

#### 3.2.3 Testing
- [ ] Test: At t=0, markers at reference positions (φ=0)
- [ ] Test: At t=T/4, stroke angle = +70°
- [ ] Test: Pitch leads stroke by 90° phase
- [ ] Visual test: Markers trace expected arc over one period

**Validation checkpoint**: Wing markers move in expected flapping pattern.

---

### 3.3 Docker Integration

#### 3.3.1 Update Dockerfile
- [ ] Modify `docker/Dockerfile.fp64` to clone `talmolab/IAMReX`
- [ ] Update `docker/build-args.env` with fork commit SHA
- [ ] Rebuild and push to `ghcr.io/talmolab/mosquito-cfd:fp64`

#### 3.3.2 Testing
- [ ] Verify Docker image builds with new fork
- [ ] Run FlowPastSphere to confirm no regression
- [ ] Run flapping wing test case

**Validation checkpoint**: Docker image contains working arbitrary geometry + kinematics.

---

## Phase 4: Validation (Feb 26-27, PRE-PROPOSAL)

### 4.1 Flapping Wing Example

#### 4.1.1 Setup
- [ ] Create `examples/flapping_wing/` directory
- [ ] Generate `wing.vertex` with elliptic planform (3mm × 1mm, 50μm spacing)
- [ ] Create `inputs.3d.flapping_wing` with domain and boundary conditions
- [ ] Create `run.sh` with metadata capture
- [ ] Create `visualize.py` for post-processing
- [ ] Create `plot_config.py` with standard styles and colors
- [ ] Create `generate_all_figures.py` orchestrator script

#### 4.1.2 Coarse Resolution Run
- [ ] Run 1 wingbeat at coarse resolution (Δx = 0.5 mm)
- [ ] Verify markers move correctly (visual inspection)
- [ ] Extract force time series to `forces.csv`
- [ ] Document timing (seconds/timestep, total wall time)
- [ ] Generate `run_metadata.json` with all hashes

#### 4.1.3 Medium Resolution Run
- [ ] Run 1 wingbeat at medium resolution (Δx = 0.125 mm)
- [ ] Extract force coefficients (CL, CD) to `forces.csv`
- [ ] Compare with van Veen expected ranges
- [ ] Generate `run_metadata.json` with validation results

**Validation checkpoint**: Forces are in physically plausible range; LEV visible in vorticity plots.

---

### 4.2 Figure Generation

#### 4.2.1 Geometry Figures
- [ ] **G1**: Wing planform marker scatter plot (`fig_planform.pdf`)
  - Shows elliptic shape in x-z plane
  - Annotates span, chord, marker count

#### 4.2.2 Kinematics Figures
- [ ] **K1**: Euler angles vs phase (`fig_kinematics.pdf`)
  - φ(t), α(t) curves over 1 wingbeat
  - Overlay van Veen Eq. 1-2 reference
- [ ] **K2**: Wing position at key phases (`fig_wing_phases.png`)
  - Side-by-side snapshots at t=0, T/4, T/2, 3T/4
  - 3D marker positions projected to stroke plane

#### 4.2.3 Force Figures
- [ ] **F1**: Force coefficients vs phase (`fig_forces.pdf`)
  - CL (blue), CD (orange) curves
  - Annotate acceptance range [0.5, 1.5]
  - Mark mid-stroke peak locations

#### 4.2.4 Flow Figures
- [ ] **V1**: Velocity field at mid-stroke (`fig_velocity_midstroke.png`)
  - Z-slice through wing center
  - Colormap: RdBu_r (diverging)
- [ ] **V2**: Vorticity at mid-stroke (`fig_vorticity_midstroke.png`)
  - Z-slice showing LEV structure
  - Annotate leading-edge vortex location

**Reproducibility checkpoint**: All figures regenerable via `generate_all_figures.py`

---

### 4.3 Validation Documentation

#### 4.3.1 Results Summary
- [ ] Create `examples/flapping_wing/RESULTS.md` with:
  - Simulation parameters table
  - Force coefficient summary (mean CL, CD)
  - Timing and performance data
  - Figure gallery with interpretations

#### 4.3.2 Comparison with Literature
- [ ] Compare force magnitudes with van Veen Fig. 3-4
- [ ] Compare wake structure with van Veen visualizations
- [ ] Document any discrepancies and hypotheses

#### 4.3.3 Data Outputs
- [ ] `forces.csv` — Force time series with all columns
- [ ] `run_metadata.json` — Full provenance record
- [ ] `figures/` — All generated figures (PDF + PNG)

**Documentation checkpoint**: RESULTS.md complete with all figures and interpretations

---

## Phase 5: Future Extensions (Post-Award, Weeks 7+)

### 5.1 Input-File Configurable Kinematics
- [ ] Add `ParmParse` queries for frequency, amplitudes, phase
- [ ] Test with Bomphrey 2017 parameters (717 Hz, 39° stroke)
- [ ] Document in design.md

### 5.2 Time Series Kinematics
- [ ] Implement kinematics file reader
- [ ] Add linear interpolation for arbitrary time points
- [ ] Test with synthetic and measured data

### 5.3 MJCF Converter
- [ ] Add `mujoco` dependency to `pyproject.toml`
- [ ] Implement `mjcf_to_vertex.py` for mesh extraction
- [ ] Test with mosquito MJCF model

### 5.4 Multi-Body Support
- [ ] Extend particle container for multiple bodies
- [ ] Add per-body kinematics configuration
- [ ] Test with two-wing configuration

---

## Task Dependencies

```
Feb 24:  Phase 2 (Fork + Vertex Reader + Python Generator)
              │
Feb 25:       └──> Phase 3 (Kinematics + Docker Rebuild)
                        │
Feb 26:                 └──> Phase 4.1 (Validation Runs)
                                  │
Feb 27:                           └──> Phase 4.2 (Results → APEX Proposal)
                                              │
Post-Award:                                   └──> Phase 5 (Extensions)
```

## Priority Summary

| Priority | Tasks | Deadline |
|----------|-------|----------|
| **P0** | 2.1–2.2 (Fork IAMReX + vertex reader) | Feb 24, 2026 |
| **P0** | 2.1.1–2.1.2 (Python planform generator) | Feb 24, 2026 |
| **P0** | 3.1–3.2 (Kinematics implementation) | Feb 25, 2026 |
| **P0** | 3.3 (Docker rebuild) | Feb 25, 2026 |
| **P0** | 4.1 (Validation runs) | Feb 26, 2026 |
| **P0** | 4.2 (Documentation + APEX integration) | Feb 27, 2026 |
| **P1** | 5.1–5.4 (Extensions) | Post-award |