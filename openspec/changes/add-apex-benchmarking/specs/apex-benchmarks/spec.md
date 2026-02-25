# APEX Benchmarks Specification

## ADDED Requirements

### Requirement: FlowPastSphere Validation

The system must validate IAMReX against the canonical FlowPastSphere benchmark at Re=100, demonstrating grid convergence and quantitative agreement with published literature.

#### Scenario: Grid Convergence Study

**Given** FlowPastSphere input files at three resolutions (128³, 256³, 512³)
**When** simulations are run to steady state and drag coefficient extracted
**Then** Richardson extrapolation yields Cd within ±5% of literature value (1.087-1.10)
**And** Grid Convergence Index (GCI) is less than 2%
**And** observed order of convergence is between 1.5 and 2.5

#### Scenario: Validation Artifacts

**Given** completed FlowPastSphere convergence study
**When** analysis scripts are executed
**Then** `fig_sphere_cd_convergence.pdf` is generated showing Cd vs 1/Δx with error bars
**And** `fig_sphere_wake.png` is generated showing velocity field in wake region
**And** `sphere_convergence.csv` contains columns: resolution, cells, Cd, Cd_error, time_s

---

### Requirement: Mosquito Wing Simulation

The system must simulate a simplified mosquito wing (flat plate) with prescribed flapping kinematics, extracting force coefficients suitable for APEX proposal.

#### Scenario: Wing Marker Generation

**Given** van Veen et al. (2022) wing parameters (span=3mm, chord=1mm)
**When** `generate-markers` is invoked with appropriate spacing
**Then** a marker file is produced with correct spatial distribution
**And** marker count matches expected value for given spacing (±5%)

#### Scenario: Wing Force Extraction

**Given** completed mosquito wing simulation for one wingbeat
**When** force analysis is executed
**Then** CL(t) and CD(t) time series are extracted
**And** mean lift coefficient is in physically plausible range (0.5-1.5)
**And** `fig_wing_forces.pdf` shows force coefficients vs normalized time

#### Scenario: Wing Vorticity Visualization

**Given** completed mosquito wing simulation with plot files at multiple phases
**When** visualization script is executed for mid-stroke phase
**Then** `fig_wing_vorticity.png` shows vorticity isosurfaces
**And** leading-edge vortex (LEV) structure is visible

---

### Requirement: Performance Timing

The system must measure simulation performance with statistical rigor, enabling accurate resource estimation for APEX proposal.

#### Scenario: Timing Measurement Protocol

**Given** a benchmark case (FlowPastSphere or wing)
**When** timing is measured
**Then** at least 3 independent runs are performed
**And** mean and standard deviation of time per timestep are computed
**And** warmup period (first 10 steps) is excluded from statistics

#### Scenario: Timing Breakdown

**Given** completed timing measurements
**When** AMReX timers are analyzed
**Then** percentage breakdown is computed for: Poisson solve, IB forces, regrid, other
**And** `fig_timing_breakdown.pdf` shows stacked bar chart

#### Scenario: Resource Projection

**Given** timing measurements on A40 (FP64: 0.585 TFLOPS)
**When** projection to A100 (FP64: 9.7 TFLOPS) is computed
**Then** projected time uses formula: T_A100 = T_A40 / 13.2 (with 0.8 efficiency)
**And** `resource_projection.csv` contains GPU-hour estimates for proposal milestones

---

### Requirement: Reproducibility Metadata

Every benchmark run must capture complete provenance information enabling exact reproduction of results.

#### Scenario: Metadata Capture

**Given** a simulation run is executed
**When** run completes
**Then** `run_metadata.json` is generated containing:
  - run_id (UUID)
  - timestamp (ISO8601)
  - git_commit (SHA)
  - docker_image with digest
  - inputs_hash (SHA256 of input file)
  - hardware fingerprint (GPU model, count, CUDA version)
  - timing summary
  - output file manifest

#### Scenario: Metadata Verification

**Given** `run_metadata.json` from a previous run
**When** metadata is loaded and validated
**Then** all required fields are present
**And** git commit can be checked out
**And** Docker image can be pulled by digest
**And** input file hash matches stored value

---

### Requirement: Methods Documentation

A comprehensive methods document must be produced suitable for inclusion in APEX proposal or publication appendix.

#### Scenario: METHODS.md Content

**Given** completed benchmark suite
**When** `benchmarks/METHODS.md` is reviewed
**Then** it contains sections for:
  1. Simulation Framework (IAMReX version, build config)
  2. Validation Cases (physical setup, BCs)
  3. Grid Convergence Methodology (Richardson extrapolation)
  4. Force Computation (surface integral algorithms)
  5. Wing Kinematics (motion equations)
  6. Performance Measurement (timing protocol)
  7. Reproducibility (metadata schema, Docker usage)
  8. References

#### Scenario: Methods Completeness

**Given** METHODS.md
**When** a reader attempts to reproduce the benchmarks
**Then** all necessary information is present to:
  - Pull correct Docker image
  - Locate input files
  - Execute simulations
  - Reproduce analysis and figures

---

### Requirement: Deliverables Assembly

All figures, tables, and documentation must be assembled in a structured output directory.

#### Scenario: Figure Generation

**Given** completed benchmark analysis
**When** `generate_report.py` is executed
**Then** all required figures exist in `benchmarks/results/figures/`:
  - `fig_sphere_cd_convergence.pdf`
  - `fig_sphere_wake.png`
  - `fig_wing_forces.pdf`
  - `fig_wing_vorticity.png`
  - `fig_timing_breakdown.pdf`

#### Scenario: Table Generation

**Given** completed benchmark analysis
**When** analysis scripts complete
**Then** all required tables exist in `benchmarks/results/tables/`:
  - `sphere_convergence.csv`
  - `wing_forces.csv`
  - `timing_summary.csv`
  - `resource_projection.csv`

#### Scenario: Metadata Archive

**Given** all benchmark runs complete
**When** results are assembled
**Then** `benchmarks/results/metadata/` contains JSON files for every run
**And** each JSON file passes schema validation

---

## Cross-References

- [CFD Infrastructure](../../../../specs/cfd-infrastructure/spec.md) - Docker images, CI/CD
- [Run Metadata](../../../../specs/run-metadata/spec.md) - Base provenance tracking
- [Wing Markers](../../../../specs/wing-markers/spec.md) - Lagrangian marker generation