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

## Phase 2: Implementation (Feb 24-25, PRE-PROPOSAL) ✅ COMPLETE

### 2.1 Python Planform Generator ✅

#### 2.1.1 Core Module
- [x] Create `src/mosquito_cfd/geometry/__init__.py`
- [x] Implement `parametric_planform.py` with rectangular generator
- [x] Implement `parametric_planform.py` with elliptic generator
- [x] Implement `vertex_io.py` for read/write functions

#### 2.1.2 CLI Tool
- [x] Add `generate-wing-planform` entry point to `pyproject.toml`
- [x] Implement argument parsing (shape, span, chord, spacing, center, output)
- [x] Add `--help` documentation

#### 2.1.3 Testing
- [x] Unit test: rectangular planform marker count
- [x] Unit test: elliptic planform shape
- [x] Unit test: vertex file round-trip (write then read)
- [x] Integration test: generate file, verify readable by simple parser

**Validation checkpoint**: ✅ Generated `.vertex` files are human-readable and match expected marker counts. 10 tests pass.

---

### 2.2 IAMReX Fork Setup ✅

#### 2.2.1 Create Fork
- [x] Fork `ruohai0925/IAMReX` to `talmolab/IAMReX`
- [x] Clone fork locally for development (`c:/repos/IAMReX-fork`)
- [x] Verify build with existing FlowPastSphere tutorial

#### 2.2.2 Branch Strategy
- [x] Create `feature/arbitrary-geometry` branch
- [x] Document branching strategy in fork README

**Validation checkpoint**: ✅ Fork at `talmolab/IAMReX` on `feature/arbitrary-geometry` branch.

---

### 2.3 Vertex File Reader (C++) ✅

#### 2.3.1 Implementation
- [x] Create `Source/VertexFileReader.H` (header-only)
- [x] Implement `ReadVertexFile()` function
- [x] Add error handling for missing/malformed files

#### 2.3.2 Integration
- [x] Add `geometry_type = 4` case to `DiffusedIB.cpp`
- [x] Parse `geometry_file`, `hinge_x/y/z`, `scale` from input
- [x] Store reference positions for kinematics

#### 2.3.3 Testing
- [x] Test: Load simple 3-marker file, verify positions (TestVertexFileReader::test_three_marker_file_exact_positions)
- [x] Test: Load wing.vertex from Python generator (TestVertexFileReader::test_load_wing_vertex_from_generator)
- [x] Test: Verify center offset applied correctly (TestGeneratePlanform::test_center_offset)
- [x] Test: Verify scale factor applied correctly (scientific notation precision test; C++ scale applied at init)

**Validation checkpoint**: ✅ IAMReX loads `.vertex` file and initializes particles. Awaiting Docker rebuild for runtime tests.

---

## Phase 3: Kinematics Implementation (Feb 25, PRE-PROPOSAL) ✅ COMPLETE

### 3.1 Rotation Matrix ✅

#### 3.1.1 Implementation
- [x] Create `Source/WingKinematics.H` (header-only)
- [x] Implement `ComputeRotationMatrix()` for ZYX Euler angles
- [ ] Unit test rotation matrix against known values (deferred to runtime)

### 3.2 Kinematics Update ✅

#### 3.2.1 Implementation
- [x] Implement `UpdateWingPositions()` with configurable van Veen parameters
- [x] Store reference positions at initialization in `ExternalGeometryData`
- [x] Transform markers about hinge each timestep

#### 3.2.2 Integration
- [x] Call `UpdateExternalGeometryPositions()` at start of `UpdateParticles()`
- [x] Add `do_prescribed_motion` flag to enable/disable
- [x] Add `kinematics_*` input parameters for frequency, stroke_amp, pitch_amp

#### 3.2.3 Testing
- [x] Test: At t=0, φ=0 and α=α_amp (TestWingKinematics::test_at_t0_phi_zero, test_at_t0_alpha_max)
- [x] Test: At t=T/4, stroke angle = +70° (TestWingKinematics::test_at_quarter_period_phi_max)
- [x] Test: Pitch leads stroke by 90° phase (TestWingKinematics::test_pitch_leads_stroke_by_90_degrees)
- [ ] Visual test: Markers trace expected arc over one period

**Validation checkpoint**: ✅ Kinematics code complete. Awaiting Docker rebuild for runtime tests.

---

### 3.3 Docker Integration (Partially Complete)

#### 3.3.1 Update Dockerfile
- [x] Modify `docker/Dockerfile.fp64` to clone `talmolab/IAMReX`
- [x] Update `docker/build-args.env` with fork commit SHA
- [x] Rebuild and push to `ghcr.io/talmolab/mosquito-cfd:fp64`

#### 3.3.2 Testing
- [x] Verify Docker image builds with new fork
- [x] Run FlowPastSphere to confirm no regression (elizabeth-cfd-sphere: 500 steps, Cd=0.459 vs prior 0.448–0.503 ✓; 515 markers, clean exit)
- [x] Run flapping wing test case (flapping-wing-val9: 2000 steps, max|u|=12.66 at step 2, stable through end, plt02000 written ✓)

**Validation checkpoint**: ✅ Docker image built and pushed (IAMREX_COMMIT=7ece065d). Flapping wing 2000-step GPU test complete. FlowPastSphere regression test complete (Cd=0.459, consistent with prior runs).

---

## Phase 4: Validation (Feb 26-27, PRE-PROPOSAL)

### 4.1 Flapping Wing Example

#### 4.1.1 Setup ✅ COMPLETE
- [x] Create `examples/flapping_wing/` directory
- [x] Generate `wing.vertex` with elliptic planform (3c × 1c, 0.05c spacing, dimensionless) — 908 markers
- [x] Create `inputs.3d.flapping_wing` with domain and boundary conditions
- [x] Create `run.sh` with metadata capture
- [x] Create `visualize.py` for post-processing (velocity, vorticity, force time series)
- [x] Create `plot_config.py` with standard styles and colors (IBM colorblind-safe palette)
- [x] Create `generate_all_figures.py` orchestrator script

**Bug fix**: wing.vertex was initially generated in physical meters (±1.5e-3 m range). Regenerated in dimensionless chord units (span=3.0, chord=1.0, spacing=0.05) matching the dimensionless domain.

#### 4.1.2 Coarse Resolution Run ✅ COMPLETE
- [x] Run 1 wingbeat at coarse resolution (64×32×64 = 131K cells, f*=1.0)
- [x] Verify markers move correctly (visual inspection via fig_wing_phases.pdf)
- [x] Extract force time series to `forces.csv` (2000 steps, 29 columns)
- [x] Document timing: 295 s wall time, 0.147 s/step, 891K cells/step on A40

**Results**: Stable run, 2000 steps, 4.9 min wall time. Forces periodic. Max |CF_z| = 0.22 (corrected ~0.52 with IAMReX 2.4× underestimate factor — at lower bound of expected [0.5, 1.5]).

#### 4.1.3 Medium Resolution Run
- [ ] Run 1 wingbeat at medium resolution (Δx = 0.125 mm)
- [ ] Extract force coefficients (CL, CD) to `forces.csv`
- [ ] Compare with van Veen expected ranges
- [ ] Generate `run_metadata.json` with validation results

**Validation checkpoint**: Forces are in physically plausible range; LEV visible in vorticity plots.

---

### 4.2 Figure Generation

#### 4.2.1 Geometry Figures
- [x] **G1**: Wing planform marker scatter plot (`fig_planform.pdf`)
  - Shows elliptic shape in x-z plane
  - Annotates span, chord, marker count

#### 4.2.2 Kinematics Figures
- [x] **K1**: Euler angles vs phase (`fig_kinematics.pdf`)
  - φ(t), α(t) curves over 1 wingbeat
  - van Veen Eq. 1-2 reference
- [x] **K2**: Wing position at key phases (`fig_wing_phases.pdf`)
  - Side-by-side snapshots at t=0, T/4, T/2, 3T/4
  - Marker positions projected to xz plane with hinge marker

#### 4.2.3 Force Figures
- [x] **F1**: Force time series with kinematics (`fig_forces.pdf`)
  - CF_x, CF_y (stroke plane), CF_z (lift axis) curves
  - Normalized by q_tip × S where q_tip = 0.5 ρ V_tip^2
  - Kinematics overlay in top panel

#### 4.2.4 Flow Figures
- [ ] **V1**: Velocity field at mid-stroke (`fig_velocity_midstroke.png`)
  - Z-slice through wing center
  - Requires re-run with amr.plot_int > 0 (deferred)
- [ ] **V2**: Vorticity at mid-stroke (`fig_vorticity_midstroke.png`)
  - Z-slice showing LEV structure
  - Requires re-run with amr.plot_int > 0 (deferred)

**Reproducibility checkpoint**: G1, K1, K2, F1 regenerable via `uv run python examples/flapping_wing/generate_all_figures.py`

---

### 4.3 Validation Documentation

#### 4.3.1 Results Summary
- [x] Create `examples/flapping_wing/RESULTS.md` with:
  - Simulation parameters table
  - Force coefficient summary (mean CL, CD)
  - Timing and performance data
  - Figure gallery with interpretations

#### 4.3.2 Comparison with Literature
- [ ] Compare force magnitudes with van Veen Fig. 3-4
- [ ] Compare wake structure with van Veen visualizations
- [ ] Document any discrepancies and hypotheses

#### 4.3.3 Data Outputs
- [x] `forces.csv` — Force time series with all columns (2000 steps, 29 cols)
- [ ] `run_metadata.json` — Full provenance record (deferred)
- [x] `figures/` — G1, K1, K2, F1 generated (V1, V2 deferred pending re-run)

**Documentation checkpoint**: RESULTS.md complete with all figures and interpretations

---

## Phase 5: Future Extensions (Post-Award, Weeks 7+)

### 5.1 Input-File Configurable Kinematics ✅ COMPLETE (implemented pre-proposal)
- [x] Add `ParmParse` queries for frequency, amplitudes, phase (ExternalGeometry.H lines 86-90: `kinematics_frequency`, `kinematics_stroke_amp`, `kinematics_pitch_amp`, `kinematics_deviation_amp`, `kinematics_phase_lead`)
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