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
- [x] 1.2.4 Implement `analyze_forces.py` for wing/ellipsoid force coefficients — not that
  filename, but functionally delivered and exceeded via
  `src/mosquito_cfd/benchmarks/{heaving_ellipsoid,flapping_wing,van_veen_model}.py`
  (self-consistency, added-mass, body-frame decomposition, van Veen QS-model reconstruction)
- [x] 1.2.5 Implement `generate_figures.py` for publication plots — **DONE Feb 24 (benchmarks/results/figures/)**
- [ ] 1.2.6 Add CLI entry points in `pyproject.toml` — GENUINELY OPEN: `[project.scripts]` only
  has `generate-wing-planform`; no benchmark-analysis CLI exists

### 1.3 Run Scripts
- [x] 1.3.1 Create `examples/flow_past_sphere/run.sh` with metadata capture
- [x] 1.3.2 Create `examples/heaving_ellipsoid/run.sh` with metadata capture
- [x] 1.3.3 Create `examples/*/visualize.py` scripts — **DONE Feb 24**
- [ ] 1.3.4 Create `benchmarks/run_all.sh` master script — GENUINELY OPEN: not found anywhere
  in the repo

## Phase 2: FlowPastSphere Validation (Case 1)

### 2.1 Grid Convergence Study
- [x] 2.1.1 Create input files for grid resolutions (using IAMReX defaults)
- [x] 2.1.2 Run coarse grid (128×64×64) simulation — **COMPLETED: 51 min, Cd=0.503**
- [x] 2.1.3 Run medium grid (256×128×128) simulation — **COMPLETED: 4.97 hr, Cd=0.448**
- [ ] 2.1.4 Run fine grid (512×256×256) simulation to steady state — arguably moot now: T1b
  resolved the Cd question via a periodic-duct control-volume balance on the existing 2-grid pair
  without needing a 3rd grid (see 2.1.5 note); a 3rd grid would only sharpen the observed-order
  fit (2.2.2, still genuinely open), not re-litigate the "~60% low" question
- [x] 2.1.5 Extract Cd from each resolution — **Extracted, ~60% below literature (needs investigation)**
  — **SUPERSEDED (T1a/T1b, [#29](https://github.com/talmolab/mosquito-cfd/issues/29)):** this was
  a force-extraction bug (IB markers summed only the last multidirect sub-iteration's force), not a
  flow-field deficit. The corrected drag (periodic-duct control-volume balance) is 2.64× the marker
  value and converges toward literature. See
  [`docs/aerodynamics_validation/t1a-findings.md` §8](../../../docs/aerodynamics_validation/t1a-findings.md).
  This line is retained verbatim as the historical record behind the already-submitted APEX PDF.

### 2.2 Convergence Analysis
- [ ] 2.2.1 Compute Richardson extrapolation for Cd — SUPERSEDED by the T1b/T2b control-volume
  Richardson extrapolation (1.03–1.13 bracket, `flow_past_sphere/RESULTS.md`), which uses the
  corrected CV Cd rather than the original IB-marker values this task was scoped against
- [ ] 2.2.2 Calculate observed order of convergence — GENUINELY OPEN: only two sphere grids exist,
  so the order is *assumed* (p=1 vs p=2 bracket), never independently fitted; would need a 3rd grid
- [ ] 2.2.3 Compute Grid Convergence Index (GCI) — GENUINELY OPEN: no GCI% has been computed for
  the sphere case (unlike the wing's T3c `GCI_fine` treatment); could be computed cheaply from the
  existing 2-grid CV data but hasn't been
- [ ] 2.2.4 Compare Cd to literature (Johnson & Patel 1999: Cd=1.087) — **SUPERSEDED (T1a/T1b,
  [#29](https://github.com/talmolab/mosquito-cfd/issues/29)):** an unrun to-do under the original
  IB-marker-based plan, not a stale claim. The comparison against literature genuinely happened,
  just via the control-volume Richardson bracket (1.03–1.13, or 1.00–1.11 confinement-corrected)
  instead — graded **H1′** in `flow_past_sphere/RESULTS.md`

### 2.3 Validation Deliverables
- [x] 2.3.1 Generate velocity field visualizations — **plt10000_*.png (steady state)**
- [x] 2.3.2 Generate `fig_sphere_cd_convergence.pdf` plot — delivered as `fig_forces_convergence.pdf`
  (different filename, same content: Cd vs time, coarse+medium vs literature); annotation
  corrected in this session to reflect the T1b force-extraction-bug resolution rather than the
  stale "known diffused-IB scaling" framing
- [ ] 2.3.3 Create `sphere_convergence.csv` table — GENUINELY OPEN: `forces_coarse.csv`/
  `forces_medium.csv` are per-grid time series, not the resolution/Cd/error summary table this
  task calls for
- [x] 2.3.4 Document validation in `benchmarks/METHODS.md` — Case 1 section + "Known Limitations
  #1" fully documents the T1a/T1b resolution

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
- [x] 3.6.3 Compare with quasi-steady theory (added mass) — `examples/heaving_ellipsoid/RESULTS.md`
  "T2b re-validation" section (added-mass fraction vs. van Veen 15%/31%);
  `tests/test_heaving_ellipsoid.py` covers this
- [x] 3.6.4 Generate force time series visualization — **DONE Feb 24 (heaving_ellipsoid_forces.png)**

### 3.7 Deliverables
- [x] 3.7.1 Generate `fig_ellipsoid_forces.pdf` (force vs time) — **DONE Feb 24**
- [x] 3.7.2 Generate `fig_ellipsoid_wake.png` (velocity field) — **DONE Feb 24 (plt_1k01000_*.png)**
- [x] 3.7.3 Create `ellipsoid_forces.csv` time series — **DONE Feb 24**
- [x] 3.7.4 Document thin ellipsoid approximation in METHODS.md — "Known Limitations" #2-5 cover
  the geometry constraint, kinematics constraint, periodic-boundary wraparound, and
  pure-translation-not-lift limitations

### 3.8 Future: Complex Geometry Path
- [x] 3.8.1 Document plan to extend IAMReX for flat plate (geometry_type=4) — not just documented,
  **implemented**: `examples/flapping_wing/` uses external-vertex geometry_type=4 (`wing.vertex`,
  908 markers), delivered via the (now-archived) `add-arbitrary-geometry` change
- [x] 3.8.2 Document IBAMR as alternative for immediate flat plate support —
  `examples/heaving_ellipsoid/README.md`: "Use IBAMR for immediate flat plate support (CPU-only)"
- [x] 3.8.3 Add MJCF → .vertex converter roadmap for geometry consistency — present as "Extension
  3: MJCF Geometry Extraction" in the (now-archived) `add-arbitrary-geometry` proposal (a concrete
  `mjcf-to-vertex` CLI spec, not yet implemented — tracked as genuinely-open Phase 5 there)

## Phase 4: Performance Benchmarking

### 4.1 Single-GPU Timing

**GENUINELY OPEN** (2026-07-27 audit): no 3-repeat-run timing statistics (mean±std) exist anywhere
in the repo, despite design.md's protocol requiring them; single-A40 hardware could run these, the
time just hasn't been spent.

- [ ] 4.1.1 Run FlowPastSphere 3× for timing statistics (1 GPU)
- [ ] 4.1.2 Run mosquito wing (coarse) 3× for timing statistics (1 GPU)
- [ ] 4.1.3 Extract timing breakdown (Poisson, IB, regrid)
- [ ] 4.1.4 Record GPU memory and utilization

### 4.2 Multi-GPU Scaling

**BLOCKED** (2026-07-27 audit): multi-GPU nodes were never available — all measurements to date are
single-A40/A5000 (per `docs/aerodynamics_validation/roadmap.md`: "same single-tenant Salk RunAI
A40"). Needs cluster access this project doesn't currently have.

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
  — **superseded**: `timestep_cfl_analysis.md` later found the steps/wingbeat assumption (5,000)
  was ~2× too high vs. the CFL-derived value (2,570); kept as the historical Feb 2026 estimate
- [x] 4.3.4 Estimate GPU-hours for proposal milestones — **~86k A100 hours total** —
  **superseded**: `h100_resource_estimate.md` retargets the whole estimate from A100/APEX to
  H100/NVIDIA Academic Grant (see that doc for the current ~30k H100-hr ask)
- [x] 4.3.5 Create `resource_projection.csv` — **Created in benchmarks/results/tables/**

### 4.4 Performance Deliverables

**GENUINELY OPEN / partially BLOCKED**: depends on data from 4.1 (open) and 4.2 (blocked) above.

- [ ] 4.4.1 Generate `fig_timing_breakdown.pdf` (single GPU)
- [ ] 4.4.2 Generate `fig_scaling_efficiency.pdf` (1/2/4 GPU)
- [ ] 4.4.3 Create `timing_summary.csv`
- [ ] 4.4.4 Create `scaling_results.csv`
- [ ] 4.4.5 Document performance in METHODS.md

## Phase 5: Reproducibility and Documentation

### 5.1 Metadata System
- [x] 5.1.1 Implement JSON metadata schema — `src/mosquito_cfd/benchmarks/metadata.py`
  `capture_run_metadata()`
- [x] 5.1.2 Auto-capture git, Docker, hardware info — same function: hostname/GPU/CUDA via
  `socket.gethostname()` etc., `docker_image` param, git SHA
- [x] 5.1.3 Generate metadata for all benchmark runs — `run_metadata_{t2a,t2b,t3b,t3c}.json` under
  `examples/flapping_wing/` and `examples/heaving_ellipsoid/`, plus
  `examples/prelim_sweep/run_metadata.json`
- [ ] 5.1.4 Store metadata in `benchmarks/results/metadata/` — GENUINELY OPEN as literally scoped:
  that directory doesn't exist; metadata instead lives per-example (`run_metadata_*.json` alongside
  each case), a deliberate (if undocumented) deviation from the original single-directory plan

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
- [ ] 5.3.3 Verify all metadata files present — not independently re-verified this session (no
  specific claim to check against); leaving unchecked rather than assuming
- [x] 5.3.4 Run `generate_figures.py` to verify reproducibility — **DONE Feb 24**
- [x] 5.3.5 Update `openspec/project.md` with benchmark status — done this session (2026-07-27):
  `project.md`'s Overview/Goals/Hardware/Current-State sections updated to reflect the denied APEX
  submission and the NVIDIA Academic Grant (H100) pivot

## Phase 6: APEX Proposal Integration

**Status note (2026-07-27 audit):** the proposal WAS drafted, reviewed, and submitted by the Feb
27, 2026 deadline (`docs/aerodynamics_validation/t1a-findings.md` and `roadmap.md` both reference
"the already-submitted APEX proposal PDF is immutable" — submission cannot happen without drafting
and reviewing first). It was subsequently **denied**; the target moved to the NVIDIA Academic Grant
(H100). 6.1.1-6.2.4 below are ticked as done for that (now-historical) submission; the PDF itself
lives outside this repo and is not touched.

### 6.1 Proposal Sections
- [x] 6.1.1 Draft "Scientific Impact" using validation results
- [x] 6.1.2 Draft "Goals & Resources" using timing projections
- [x] 6.1.3 Draft "Methodology" referencing METHODS.md
- [x] 6.1.4 Prepare figures for proposal PDF

### 6.2 Review and Submission
- [x] 6.2.1 Internal review of benchmarks
- [x] 6.2.2 Verify all claims have supporting data
- [x] 6.2.3 Final metadata archive
- [x] 6.2.4 Submit to APEX (deadline: Feb 27, 2026) — submitted; **denied**; see Overview/Status
  note above

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
- [x] 3.6.3 Compare with quasi-steady theory (added mass) — optional — done (see §3.6 above)
- [x] 3.7.3 Create `ellipsoid_forces.csv` time series — **DONE Feb 24**
- [x] 5.3.5 Update `openspec/project.md` with benchmark status — done this session (see §5.3 above)
- [x] 6.1.1-6.1.4 Proposal section drafts — done (see Phase 6 status note above)
- [x] 6.2.1-6.2.3 Review — done (see Phase 6 status note above)

### Day 4 (Feb 27)
- [x] 6.2.4 Submit to APEX — submitted; denied (see Overview)

## Parallelizable Tasks
- [parallel] 2.1.2, 2.1.3, 2.1.4 (grid convergence runs on different nodes)
- [parallel] 4.1.1, 4.1.2 (timing runs)
- [parallel] 3.7.1-3.7.3 and 2.3.1-2.3.3 (figure generation)