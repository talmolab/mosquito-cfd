## Phase 1: Infrastructure Setup

### 1.1 Directory Structure
- [x] 1.1.1 Create `benchmarks/` directory structure
- [x] 1.1.2 Create `examples/flow_past_sphere/` with inputs and scripts
- [x] 1.1.3 Create `examples/heaving_ellipsoid/` with inputs and scripts
- [x] 1.1.4 Create `benchmarks/results/` subdirectories (figures/, tables/) — **DONE Feb 24**
- [x] 1.1.5 Add `benchmarks/.gitignore` for large output files — **DONE Feb 24**

### 1.2 Python Analysis Module
- [x] 1.2.1 Create `src/mosquito_cfd/benchmarks/__init__.py`
- [x] 1.2.2 Implement `metadata.py` with enhanced provenance tracking
- [x] 1.2.3 Implement `analyze_sphere.py` for Cd extraction
- [ ] 1.2.4 Implement `analyze_forces.py` for wing/ellipsoid force coefficients
- [x] 1.2.5 Implement `generate_figures.py` for publication plots — **DONE Feb 24 (benchmarks/results/figures/)**
- [ ] 1.2.6 Add CLI entry points in `pyproject.toml`

### 1.3 Run Scripts
- [x] 1.3.1 Create `examples/flow_past_sphere/run.sh` with metadata capture
- [x] 1.3.2 Create `examples/heaving_ellipsoid/run.sh` with metadata capture
- [x] 1.3.3 Create `examples/*/visualize.py` scripts — **DONE Feb 24**
- [ ] 1.3.4 Create `benchmarks/run_all.sh` master script

## Phase 2: FlowPastSphere Validation (Case 1)

### 2.1 Grid Convergence Study
- [x] 2.1.1 Create input files for grid resolutions (using IAMReX defaults)
- [x] 2.1.2 Run coarse grid (128×64×64) simulation — **COMPLETED: 51 min, Cd=0.503**
- [x] 2.1.3 Run medium grid (256×128×128) simulation — **COMPLETED: 4.97 hr, Cd=0.448**
- [ ] 2.1.4 Run fine grid (512×256×256) simulation to steady state
- [x] 2.1.5 Extract Cd from each resolution — **Extracted, ~60% below literature (needs investigation)**

### 2.2 Convergence Analysis
- [ ] 2.2.1 Compute Richardson extrapolation for Cd
- [ ] 2.2.2 Calculate observed order of convergence
- [ ] 2.2.3 Compute Grid Convergence Index (GCI)
- [ ] 2.2.4 Compare Cd to literature (Johnson & Patel 1999: Cd=1.087)

### 2.3 Validation Deliverables
- [x] 2.3.1 Generate velocity field visualizations — **plt10000_*.png (steady state)**
- [ ] 2.3.2 Generate `fig_sphere_cd_convergence.pdf` plot
- [ ] 2.3.3 Create `sphere_convergence.csv` table
- [ ] 2.3.4 Document validation in `benchmarks/METHODS.md`

## Phase 3: Thin Ellipsoid Wing Approximation (Case 2)

**Note**: IAMReX only supports sphere, ellipsoid, and cylinder geometries (no flat plate).
We use a thin ellipsoid to approximate the wing shape. Future work will extend IAMReX
to read external marker files for arbitrary geometry (see [cfd-approach.md](C:\vaults\physics surrogate models\cfd-approach.md)).

### 3.1 Ellipsoid Geometry Setup
- [x] 3.1.1 Configure thin ellipsoid as wing approximation:
  - Semi-axis a (chord/2): 0.5 (dimensionless)
  - Semi-axis b (thickness): 0.02 (very thin)
  - Semi-axis c (span/2): 1.5 (dimensionless)
  - geometry_type = 2 (ellipsoid)
- [x] 3.1.2 Validate ellipsoid aspect ratio matches wing AR=3

### 3.2 Heaving Motion Setup
- [x] 3.2.1 Configure constant heaving velocity (simple case first):
  - velocity_y = 0.5 (heaving velocity, half freestream)
  - Re = U * chord / ν = 1.0 * 1.0 / 0.01 = 100
- [x] 3.2.2 Document limitations of constant velocity vs time-varying
- [x] 3.2.3 Note: Full 3-angle kinematics requires IAMReX code modification

### 3.3 Input File Configuration
- [x] 3.3.1 Create `examples/heaving_ellipsoid/inputs.3d.heaving_ellipsoid`
- [x] 3.3.2 Configure domain: 20 × 10 × 10 (scaled to ellipsoid)
- [x] 3.3.3 Set fluid properties: ν = 0.01 (dimensionless, Re=100)
- [x] 3.3.4 Set timestep: Δt = 0.01 (match FlowPastSphere)
- [x] 3.3.5 Configure ellipsoid center and velocity

### 3.4 IAMReX Verification
- [x] 3.4.1 Verify IAMReX supports geometry_type=2 (ellipsoid) — **CONFIRMED**
- [x] 3.4.2 Verify ellipsoid parameters: radius, radius2, radius3 — **CONFIRMED**
- [x] 3.4.3 Test single timestep execution — **COMPLETED**
- [x] 3.4.4 Verify ellipsoid renders correctly in output — **515 markers, heaving velocities observed**

### 3.5 Simulation Execution
- [x] 3.5.1 Run heaving ellipsoid test (~100 timesteps) — **205s total, 2.0s/step**
- [x] 3.5.2 Run heaving ellipsoid to quasi-steady state (~1000 steps) — **1891s (~31 min), 1.89s/step, quasi-steady at t=7**
- [x] 3.5.3 Extract timing data for performance comparison — **1.89s/step vs 1.76s/step sphere (+7%)**

### 3.6 Force Analysis
- [x] 3.6.1 Extract force components from particle data — **Fx=-0.188, Fy=0.100, Fz~0 (t=10)**
- [x] 3.6.2 Compute CL, CD coefficients for heaving body — **Cd=0.16, CL=0.085, L/D=0.53 (planform ref)**
- [ ] 3.6.3 Compare with quasi-steady theory (added mass)
- [x] 3.6.4 Generate force time series visualization — **DONE Feb 24 (heaving_ellipsoid_forces.png)**

### 3.7 Deliverables
- [x] 3.7.1 Generate `fig_ellipsoid_forces.pdf` (force vs time) — **DONE Feb 24**
- [x] 3.7.2 Generate `fig_ellipsoid_wake.png` (velocity field) — **DONE Feb 24 (plt_1k01000_*.png)**
- [x] 3.7.3 Create `ellipsoid_forces.csv` time series — **DONE Feb 24**
- [ ] 3.7.4 Document thin ellipsoid approximation in METHODS.md

### 3.8 Future: Complex Geometry Path
- [ ] 3.8.1 Document plan to extend IAMReX for flat plate (geometry_type=4)
- [ ] 3.8.2 Document IBAMR as alternative for immediate flat plate support
- [ ] 3.8.3 Add MJCF → .vertex converter roadmap for geometry consistency

## Phase 4: Performance Benchmarking

### 4.1 Single-GPU Timing
- [ ] 4.1.1 Run FlowPastSphere 3× for timing statistics (1 GPU)
- [ ] 4.1.2 Run mosquito wing (coarse) 3× for timing statistics (1 GPU)
- [ ] 4.1.3 Extract timing breakdown (Poisson, IB, regrid)
- [ ] 4.1.4 Record GPU memory and utilization

### 4.2 Multi-GPU Scaling
- [ ] 4.2.1 Configure mpirun for 2 GPUs: `mpirun -np 2`
- [ ] 4.2.2 Configure mpirun for 4 GPUs: `mpirun -np 4`
- [ ] 4.2.3 Run FlowPastSphere at 1, 2, 4 GPUs (strong scaling)
- [ ] 4.2.4 Run FlowPastSphere with scaled problem size (weak scaling)
- [ ] 4.2.5 Compute scaling efficiency: η = T₁ / (N × Tₙ)
- [ ] 4.2.6 Identify Poisson solver communication overhead

### 4.3 Resource Estimation
- [x] 4.3.1 Compute time per timestep for each case — **0.30s coarse, 1.76s medium, 1.89s ellipsoid**
- [x] 4.3.2 Measure actual A40 performance — **2.38 M cells/s throughput, superlinear scaling**
- [x] 4.3.3 Extrapolate to A100 using measured characteristics — **2.9× speedup (bandwidth-limited)**
- [x] 4.3.4 Estimate GPU-hours for proposal milestones — **~86k A100 hours total**
- [x] 4.3.5 Create `resource_projection.csv` — **Created in benchmarks/results/tables/**

### 4.4 Performance Deliverables
- [ ] 4.4.1 Generate `fig_timing_breakdown.pdf` (single GPU)
- [ ] 4.4.2 Generate `fig_scaling_efficiency.pdf` (1/2/4 GPU)
- [ ] 4.4.3 Create `timing_summary.csv`
- [ ] 4.4.4 Create `scaling_results.csv`
- [ ] 4.4.5 Document performance in METHODS.md

## Phase 5: Reproducibility and Documentation

### 5.1 Metadata System
- [ ] 5.1.1 Implement JSON metadata schema
- [ ] 5.1.2 Auto-capture git, Docker, hardware info
- [ ] 5.1.3 Generate metadata for all benchmark runs
- [ ] 5.1.4 Store metadata in `benchmarks/results/metadata/`

### 5.2 METHODS.md — **DONE Feb 24**
- [x] 5.2.1 Write Section 1: Simulation Framework
- [x] 5.2.2 Write Section 2: Validation Cases
- [x] 5.2.3 Write Section 3: Grid Convergence Methodology
- [x] 5.2.4 Write Section 4: Force Computation
- [x] 5.2.5 Write Section 5: Wing Kinematics
- [x] 5.2.6 Write Section 6: Performance Measurement
- [x] 5.2.7 Write Section 7: Reproducibility
- [x] 5.2.8 Add References

### 5.3 Final Assembly
- [x] 5.3.1 Collect all figures into `benchmarks/results/figures/` — **DONE Feb 24**
- [x] 5.3.2 Collect all tables into `benchmarks/results/tables/` — **DONE Feb 24**
- [ ] 5.3.3 Verify all metadata files present
- [x] 5.3.4 Run `generate_figures.py` to verify reproducibility — **DONE Feb 24**
- [ ] 5.3.5 Update `openspec/project.md` with benchmark status

## Phase 6: APEX Proposal Integration

### 6.1 Proposal Sections
- [ ] 6.1.1 Draft "Scientific Impact" using validation results
- [ ] 6.1.2 Draft "Goals & Resources" using timing projections
- [ ] 6.1.3 Draft "Methodology" referencing METHODS.md
- [ ] 6.1.4 Prepare figures for proposal PDF

### 6.2 Review and Submission
- [ ] 6.2.1 Internal review of benchmarks
- [ ] 6.2.2 Verify all claims have supporting data
- [ ] 6.2.3 Final metadata archive
- [ ] 6.2.4 Submit to APEX (deadline: Feb 27, 2026)

## Task Dependencies

```
Phase 1 ──┬──> Phase 2 (Sphere) ──────────────────┐
          │                                        │
          └──> Phase 3 (Wing) ─────────────────────┼──> Phase 4 (Timing)
                                                   │
                                                   └──> Phase 5 (Docs) ──> Phase 6 (Submit)
```

## Priority Order (Given 4-Day Deadline)

### Day 1 (Feb 23) — COMPLETED
- [x] 1.1.1-1.1.2 Directory structure
- [x] 1.2.1-1.2.3 Python analysis module (metadata.py, analyze_sphere.py)
- [x] 2.1.2-2.1.3 FlowPastSphere 10k steps launched (coarse + medium grids)
- [x] Research: IAMReX geometry limitations (sphere/ellipsoid/cylinder only)
- [x] Research: IAMReX vs IBAMR comparison documented
- [x] Research: Surrogate training pipeline documented (PhysicsNeMo → MJX/Warp)

### Day 2 (Feb 24) — COMPLETED
- [x] 3.1.1-3.1.2 Thin ellipsoid geometry configuration
- [x] 3.3.1-3.3.5 Heaving ellipsoid input files
- [x] 3.5.1-3.5.2 Heaving ellipsoid to quasi-steady (1000 steps)
- [x] 3.6.1-3.6.2, 3.6.4 Ellipsoid force extraction and visualization
- [x] 3.7.1-3.7.2 Ellipsoid figures (forces + velocity)
- [x] 4.3.1-4.3.5 Resource estimation — **~86k A100 GPU-hrs (2.9× bandwidth-limited)**
- [x] 5.2.1-5.2.8 METHODS.md documentation
- [x] 5.3.1-5.3.2, 5.3.4 Final assembly (figures, tables, reproducibility verified)
- [x] Create visualize.py scripts for both examples

### Day 3 (Feb 25) — Remaining
- [ ] 3.6.3 Compare with quasi-steady theory (added mass) — optional
- [x] 3.7.3 Create `ellipsoid_forces.csv` time series — **DONE Feb 24**
- [ ] 5.3.5 Update `openspec/project.md` with benchmark status
- [ ] 6.1.1-6.1.4 Proposal section drafts
- [ ] 6.2.1-6.2.3 Review

### Day 4 (Feb 27)
- [ ] 6.2.4 Submit to APEX

## Parallelizable Tasks
- [parallel] 2.1.2, 2.1.3, 2.1.4 (grid convergence runs on different nodes)
- [parallel] 4.1.1, 4.1.2 (timing runs)
- [parallel] 3.7.1-3.7.3 and 2.3.1-2.3.3 (figure generation)