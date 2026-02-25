## Why

IAMReX currently supports only **3 hardcoded geometries** (sphere, ellipsoid, cylinder). To validate mosquito wing aerodynamics for the APEX proposal and generate training data for neural surrogates, we need:

1. **Flat plate / wing planform geometry** — not available in upstream IAMReX
2. **Prescribed flapping kinematics** — markers must move with 3-angle Euler rotation each timestep
3. **Validation against published CFD** — reproduce van Veen et al. (2022) results

### CRITICAL: Pre-Proposal Implementation Required

**Deadline**: APEX proposal due **February 27, 2026**

To include flapping wing validation results in the APEX proposal, we must implement arbitrary geometry support **before** the deadline. This is not a post-award task—it's required to demonstrate the scientific capability that justifies the GPU allocation request.

**Implementation window**: Feb 24-27, 2026 (4 days)

### Scope: Pre-Proposal vs Future Extensions

| Component | Pre-Proposal (Feb 24-27) | Future Extension (Post-Award) |
|-----------|--------------------------|-------------------------------|
| **Geometry** | Parametric planform → `.vertex` file | MJCF extraction, STL mesh sampling |
| **Kinematics** | Hardcoded van Veen sinusoidal in C++ | Input-file parameters, time series files |
| **Species** | Single validation case (van Veen) | Parameter sweep (Culex, Anopheles, Drosophila) |
| **Bodies** | Single wing | Multi-wing, full body |
| **Validation** | Force coefficients + LEV visualization | Quantitative comparison with literature |

## What Changes (APEX Scope)

### Component 1: Parametric Wing Planform Generator (Python)

Generate `.vertex` marker files from parametric wing shapes.

**Supported planforms**:
- **Rectangular** — simple flat plate baseline
- **Elliptic** — standard aerodynamic planform (theoretical optimum)

**CLI usage**:
```bash
uv run generate-wing-planform \
  --shape elliptic \
  --span 3.0e-3 \           # 3 mm (van Veen)
  --chord 1.0e-3 \          # 1 mm mean chord
  --marker-spacing 0.05e-3 \ # 50 μm (coarse) or 0.01e-3 (fine)
  --output wing.vertex
```

**Output format** (`.vertex` - simple marker file):
```
<number_of_markers>
x1 y1 z1
x2 y2 z2
...
```

### Component 2: External Geometry Loading (C++)

Add `geometry_type = 4` to IAMReX for reading external marker files.

**New input parameters**:
```
particle_inputs.geometry_type = 4
particle_inputs.geometry_file = wing.vertex
particle_inputs.center_x = 0.025        # Wing hinge position [m]
particle_inputs.center_y = 0.025
particle_inputs.center_z = 0.025
```

### Component 3: Hardcoded Sinusoidal Kinematics (C++)

Implement van Veen et al. (2022) kinematics directly in C++.

**Equations** (from van Veen 2022, Section 2.2):
```cpp
// Van Veen et al. (2022) kinematics - hardcoded for validation
const Real freq = 600.0;                    // Hz
const Real omega = 2.0 * M_PI * freq;
const Real phi_amp = 70.0 * M_PI / 180.0;   // ±70° stroke amplitude
const Real alpha_0 = 45.0 * M_PI / 180.0;   // 45° midstroke pitch

// Stroke angle (rotation in stroke plane)
Real phi = phi_amp * std::sin(omega * time);

// Pitch angle (wing rotation about spanwise axis)
// 90° phase lead: pitch leads stroke
Real alpha = alpha_0 * std::cos(omega * time);

// Deviation angle (out-of-plane, small)
Real theta = 0.0;  // Simplified: planar stroke
```

**Implementation**: Add `update_wing_kinematics()` function in `ParticleUpdate.cpp` that:
1. Stores reference marker positions at t=0
2. Each timestep: compute rotation matrix from (φ, α, θ)
3. Transform all markers about hinge point

## Scientific Validation

### Primary Reference: Van Veen et al. (2022)

> van Veen, W.G., van Leeuwen, J.L., & Muijres, F.T. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations, a systematic numerical study." *Journal of Fluid Mechanics*, 936, A3.
> [DOI:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31)

**Validation parameters** (from van Veen Table 1 and Section 2):

| Parameter | Symbol | Value | Notes |
|-----------|--------|-------|-------|
| Wing span | R | 3.0 mm | Characteristic length |
| Mean chord | c | 1.0 mm | AR = 3 |
| Wingbeat frequency | f | 600 Hz | Lower than Bomphrey's Culex (717 Hz) |
| Stroke amplitude | φ₀ | **±70°** (140° total) | Peak-to-peak |
| Pitch angle at midstroke | α₀ | **45°** | Angle of attack |
| Pitch-stroke phase | ψ | **90°** | Pitch leads stroke (cosine vs sine) |
| Deviation | θ | 0° | Planar stroke (simplified) |
| Reynolds number | Re | **100–300** | Instantaneous Re varies |
| Timestep | Δt | 1×10⁻⁷ s | ~16,700 steps/wingbeat |

**Acceptance criteria**:

| Metric | Criterion | Source |
|--------|-----------|--------|
| Mean lift coefficient | CL ∈ [0.5, 1.5] | Typical for Re 100–300 hovering |
| Force timing | Peak forces at mid-stroke | Quasi-steady expectation |
| LEV formation | Leading-edge vortex visible | Van Veen Fig. 3, Bomphrey Fig. 2 |
| Wake structure | Vortex shedding at reversal | Expected unsteady behavior |

### Supporting Reference: Bomphrey et al. (2017)

> Bomphrey, R.J., Nakata, T., Phillips, N., & Walker, S.M. (2017). "Smart wing rotation and trailing-edge vortices enable high frequency mosquito flight." *Nature*, 544, 92-95.
> [DOI:10.1038/nature21727](https://doi.org/10.1038/nature21727)

**Experimental measurements** (real mosquitoes):

| Parameter | Value | Notes |
|-----------|-------|-------|
| Species | *Culex quinquefasciatus* | Southern house mosquito |
| Wingbeat frequency | **717 ± 59 Hz** | Higher than van Veen model |
| Stroke amplitude | **39° ± 4°** | "Smallest of any hovering animal" |
| Reynolds number | **50–300** | Instantaneous |

**Key insight**: Van Veen uses ±70° stroke (fruit-fly-like) while real mosquitoes use ±19.5°. Van Veen's parameters are chosen for systematic CFD study, not mosquito-specific realism. For APEX validation, we match van Veen's CFD methodology first, then extend to Bomphrey's mosquito parameters post-award.

### Why Van Veen for Initial Validation?

1. **Published CFD results** — we can compare force coefficients and flow structures
2. **Systematic methodology** — clear parameter definitions and boundary conditions
3. **Moderate stroke amplitude** — easier to validate than extreme mosquito kinematics
4. **Same solver class** — van Veen used immersed boundary CFD; IAMReX uses similar methodology

## Impact

### IAMReX Fork (talmolab/IAMReX)

**Modified files**:
| File | Changes |
|------|---------|
| `Source/particles/ParticleInit.cpp` | Add `.vertex` file reader for `geometry_type=4` |
| `Source/particles/ParticleUpdate.cpp` | Add `update_wing_kinematics()` with hardcoded van Veen params |

**New files**:
| File | Purpose |
|------|---------|
| `Source/particles/VertexFileReader.cpp` | Parse `.vertex` format, translate/scale markers |
| `Source/particles/WingKinematics.cpp` | 3-angle Euler rotation logic |

### This Repository (mosquito-cfd)

**New Python modules**:
```
src/mosquito_cfd/geometry/
├── __init__.py
├── parametric_planform.py   # Elliptic, rectangular wing generators
└── vertex_io.py             # Read/write .vertex files
```

**New example**:
```
examples/flapping_wing/
├── inputs.3d.flapping_wing  # IAMReX input file
├── generate_wing.py         # Generate wing.vertex
├── run.sh                   # Run simulation
├── visualize.py             # Post-process with yt
└── RESULTS.md               # Validation results
```

**Docker changes**:
- Update `docker/Dockerfile.fp64` to clone `talmolab/IAMReX` fork
- Update `docker/build-args.env` with fork commit SHA

### Integration with APEX Benchmarking

This change extends the `add-apex-benchmarking` validation cases with a third case:

| Case | Status | Purpose |
|------|--------|---------|
| FlowPastSphere | ✅ Complete | Code validation (Cd = 1.09) |
| Heaving Ellipsoid | ✅ Complete | Moving body forces |
| **Flapping Wing** | 🔄 This change | Insect-scale aerodynamics |

The flapping wing case becomes **Validation Case 3** in the APEX proposal, demonstrating the core scientific capability (insect flight CFD) that justifies the GPU allocation request.

**Proposal integration**:
- Add flapping wing results to `benchmarks/METHODS.md`
- Include force coefficient plots in `benchmarks/results/figures/`
- Update resource projections based on flapping wing timing data

**Related changes**:
- [improve-benchmark-figures](../improve-benchmark-figures/proposal.md) — Consistent naming, annotations, and `manifest.json` for all benchmark figures

### Validation Outputs

#### Required Figures

| ID | Figure | Purpose | Acceptance Criterion |
|----|--------|---------|---------------------|
| **G1** | Wing planform markers | Verify `.vertex` generation | Markers form correct elliptic shape |
| **K1** | Euler angles vs phase | Verify kinematics equations | φ, α match van Veen Eq. 1-2 |
| **K2** | Wing position at key phases | Verify rotation about hinge | Correct orientation at t=0, T/4, T/2, 3T/4 |
| **F1** | Force coefficients vs phase | Validate aerodynamic forces | CL ∈ [0.5, 1.5], peaks at mid-stroke |
| **V1** | Velocity field at mid-stroke | Show flow structure | Attached flow, no separation artifacts |
| **V2** | Vorticity at mid-stroke | Show LEV formation | Leading-edge vortex visible |

#### Figure Generation Scripts

All figures generated by reproducible Python scripts:

```
examples/flapping_wing/
├── visualize.py              # Main visualization script
│   ├── plot_planform()       # G1: Wing marker scatter plot
│   ├── plot_kinematics()     # K1: Euler angles vs time
│   ├── plot_wing_phases()    # K2: Wing position snapshots
│   ├── plot_forces()         # F1: CL/CD vs phase
│   ├── plot_velocity()       # V1: Velocity slices
│   └── plot_vorticity()      # V2: Vorticity contours
└── generate_all_figures.py   # Orchestrator script
```

**Usage**:
```bash
# Generate all validation figures
uv run python examples/flapping_wing/generate_all_figures.py \
    --data-dir /path/to/simulation/output \
    --output-dir examples/flapping_wing/figures/

# Generate specific figure
uv run python examples/flapping_wing/visualize.py forces \
    /path/to/plt00000 /path/to/plt00100 ... \
    --output examples/flapping_wing/figures/fig_forces.pdf
```

#### Metadata Schema

Each validation run produces `run_metadata.json`. All fields are **auto-detected** at runtime—no hardcoded values.

**Field sources**:
| Field | Source | Method |
|-------|--------|--------|
| `run_id` | Generated | UUID + timestamp |
| `timestamp` | System | `datetime.now(timezone.utc)` |
| `git.*` | Repository | `git rev-parse`, `git diff` |
| `docker.*` | Container | `/.dockerenv`, `/proc/self/cgroup` |
| `inputs_hash` | File | SHA256 of inputs file |
| `inputs_params` | File | Parsed from inputs file |
| `geometry.num_markers` | File | First line of `.vertex` file |
| `geometry.vertex_hash` | File | SHA256 of vertex file |
| `hardware.gpu_model` | System | `nvidia-smi --query-gpu=name` |
| `hardware.cuda_version` | System | `nvcc --version` or `nvidia-smi` |
| `timing.*` | Simulation | Parsed from AMReX output |
| `validation.*` | Analysis | Computed from force data |

**Example output**:

```json
{
  "run_id": "flapping_wing_20260226_143000_a1b2c3d4",
  "timestamp": "2026-02-26T14:30:00.123456+00:00",
  "git": {
    "commit": "abc123def456789...",
    "branch": "feature/arbitrary-geometry",
    "dirty": false,
    "remote_url": "https://github.com/talmolab/mosquito-cfd.git"
  },
  "iamrex_git": {
    "commit": "def456abc789012...",
    "branch": "feature/arbitrary-geometry",
    "dirty": false,
    "remote_url": "https://github.com/talmolab/IAMReX.git"
  },
  "docker": {
    "in_container": true,
    "image": "ghcr.io/talmolab/mosquito-cfd:fp64",
    "container_id": "a1b2c3d4e5f6"
  },
  "inputs_file": "/workspace/examples/flapping_wing/inputs.3d.flapping_wing",
  "inputs_hash": "sha256:1234567890abcdef...",
  "inputs_params": {
    "amr.n_cell": "256 256 256",
    "geometry.prob_lo": "0.0 0.0 0.0",
    "geometry.prob_hi": "0.03 0.03 0.03",
    "particle_inputs.geometry_type": 4
  },
  "geometry": {
    "vertex_file": "/workspace/examples/flapping_wing/wing.vertex",
    "vertex_hash": "sha256:fedcba0987654321...",
    "num_markers": 1247,
    "shape": "elliptic",
    "span_m": 3.0e-3,
    "chord_m": 1.0e-3,
    "marker_spacing_m": 5.0e-5
  },
  "kinematics": {
    "type": "van_veen_2022",
    "frequency_hz": 600.0,
    "stroke_amplitude_deg": 70.0,
    "pitch_amplitude_deg": 45.0,
    "phase_lead_deg": 90.0
  },
  "hardware": {
    "gpu_count": 1,
    "gpu_model": "NVIDIA A40",
    "driver_version": "550.54.14",
    "cuda_version": "12.4",
    "gpus": [
      {"model": "NVIDIA A40", "memory_mb": 45634, "driver_version": "550.54.14"}
    ]
  },
  "timing": {
    "wall_time_s": 3847.2,
    "timesteps": 16700,
    "time_per_step_s": 0.2303,
    "throughput_mcells_per_s": 72.8
  },
  "outputs": {
    "plot_files": ["plt00000", "plt00100", "plt00200", "..."],
    "figures": ["fig_forces.pdf", "fig_velocity_midstroke.png", "..."],
    "force_csv": "forces.csv"
  },
  "validation": {
    "mean_cl": 0.847,
    "mean_cd": 0.423,
    "cl_range": [0.312, 1.284],
    "cl_in_range": true,
    "peak_phase": 0.251,
    "peak_at_midstroke": true,
    "lev_visible": true
  }
}
```

#### Data Tables

Force time series saved as CSV:

```
examples/flapping_wing/results/forces.csv
```

| Column | Description | Units |
|--------|-------------|-------|
| `step` | Timestep number | - |
| `time` | Simulation time | s |
| `phase` | Normalized phase φ/φ₀ | - |
| `phi` | Stroke angle | rad |
| `alpha` | Pitch angle | rad |
| `fx` | X-force (drag direction) | N |
| `fy` | Y-force (lift direction) | N |
| `fz` | Z-force (spanwise) | N |
| `cl` | Lift coefficient | - |
| `cd` | Drag coefficient | - |

#### Plotting Standards

```python
# examples/flapping_wing/plot_config.py

import matplotlib.pyplot as plt

# Proposal-consistent style
STYLE = {
    'font.family': 'sans-serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'lines.linewidth': 1.5,
    'lines.markersize': 6,
    'figure.figsize': (7.0, 4.0),  # Half-page width
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
}

# Colorblind-safe palette (IBM)
COLORS = {
    'lift': '#648FFF',    # Blue
    'drag': '#FE6100',    # Orange
    'reference': '#785EF0',  # Purple (literature data)
}

# Standard axis labels
LABELS = {
    'phase': r'Phase $\phi/\phi_0$',
    'time': r'Time (ms)',
    'cl': r'Lift coefficient $C_L$',
    'cd': r'Drag coefficient $C_D$',
    'phi': r'Stroke angle $\phi$ (deg)',
    'alpha': r'Pitch angle $\alpha$ (deg)',
}
```

#### Reproducibility Checklist

- [ ] All figures regenerable from `generate_all_figures.py`
- [ ] `run_metadata.json` includes all input hashes
- [ ] Force CSV includes raw data for independent analysis
- [ ] Docker image SHA recorded for exact environment
- [ ] IAMReX fork commit SHA recorded
- [ ] Plotting code uses version-controlled `plot_config.py`

## Future Extensions (Post-Award)

### Extension 1: Input-File Configurable Kinematics

Replace hardcoded parameters with input file:
```
particle_inputs.kinematics_type = 1        # Sinusoidal
particle_inputs.frequency = 717.0          # Hz (configurable)
particle_inputs.stroke_amplitude = 39.0    # degrees
particle_inputs.pitch_amplitude = 45.0     # degrees
particle_inputs.pitch_phase = 90.0         # degrees
```

**Benefit**: Parameter sweeps without recompilation.

### Extension 2: Time Series Kinematics File

Read arbitrary φ(t), α(t), θ(t) from external file:
```
particle_inputs.kinematics_type = 2
particle_inputs.kinematics_file = measured_kinematics.csv
```

**File format**:
```
# time, phi_deg, alpha_deg, theta_deg
0.0, 0.0, 45.0, 0.0
0.0001, 12.3, 43.2, 0.5
...
```

**Benefit**: Use real measured kinematics (e.g., from Bomphrey's Dryad dataset).

### Extension 3: MJCF Geometry Extraction

Extract mesh from MuJoCo XML for RL pipeline consistency:
```bash
uv run mjcf-to-vertex --mjcf mosquito.xml --body left_wing --output wing.vertex
```

**Benefit**: Same geometry in CFD and MJX inference.

### Extension 4: Multi-Body Support

Multiple wings/bodies with independent kinematics:
```
particle_inputs.num_bodies = 2
particle_inputs.body_0.geometry_file = left_wing.vertex
particle_inputs.body_1.geometry_file = right_wing.vertex
```

**Benefit**: Two-wing mosquito, then full swarm.

## References

1. van Veen, W.G., van Leeuwen, J.L., & Muijres, F.T. (2022). "The unsteady aerodynamics of insect wings with rotational stroke accelerations, a systematic numerical study." *J. Fluid Mech.*, 936, A3. [DOI:10.1017/jfm.2022.31](https://doi.org/10.1017/jfm.2022.31)

2. Bomphrey, R.J., Nakata, T., Phillips, N., & Walker, S.M. (2017). "Smart wing rotation and trailing-edge vortices enable high frequency mosquito flight." *Nature*, 544, 92-95. [DOI:10.1038/nature21727](https://doi.org/10.1038/nature21727)

3. Bomphrey et al. (2017) supplementary data: [Dryad DOI:10.5061/dryad.tc29h](https://datadryad.org/dataset/doi:10.5061/dryad.tc29h)

4. IAMReX: [github.com/ruohai0925/IAMReX](https://github.com/ruohai0925/IAMReX)