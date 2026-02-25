## Design Overview

This document specifies the scientific methodology for APEX proposal benchmarking. Every measurement must be reproducible, quantified with uncertainties, and traceable to code/data versions.

## Validation Methodology

### Case 1: FlowPastSphere at Re=100

#### Physical Setup
| Parameter | Value | Justification |
|-----------|-------|---------------|
| Reynolds number | 100 | Below unsteady transition (~270), steady wake |
| Sphere diameter D | 1.0 (dimensionless) | Reference length scale |
| Inflow velocity U | 1.0 (dimensionless) | Reference velocity |
| Kinematic viscosity ν | 0.01 | Re = UD/ν = 100 |
| Domain | 20D × 10D × 10D | Sphere at 5D from inlet |

#### Grid Convergence Protocol
1. **Coarse grid**: 128 × 64 × 64 (base resolution)
2. **Medium grid**: 256 × 128 × 128 (refinement ratio r = 2)
3. **Fine grid**: 512 × 256 × 256 (refinement ratio r = 2)

**Richardson extrapolation**:
```
f_exact ≈ f_fine + (f_fine - f_medium) / (r^p - 1)
```
where p is the observed order of convergence:
```
p = ln[(f_coarse - f_medium) / (f_medium - f_fine)] / ln(r)
```

**Grid Convergence Index (GCI)**:
```
GCI_fine = Fs * |ε| / (r^p - 1)
```
where Fs = 1.25 (safety factor), ε = (f_fine - f_medium) / f_fine

#### Drag Coefficient Calculation
The drag force on the sphere:
```
F_D = ∫∫_S (p n_x + τ_x) dA
```

Drag coefficient:
```
Cd = F_D / (0.5 ρ U² A)
```
where A = πD²/4 is the frontal area.

**IAMReX extraction**: Read pressure and velocity from plot files, compute surface integrals using yt or custom post-processing.

#### Acceptance Criteria
| Metric | Literature | Acceptance Range |
|--------|------------|------------------|
| Cd | 1.087–1.10 | 1.03–1.15 (±5%) |
| GCI_fine | — | < 2% |
| Observed p | ~2 (second order) | 1.5–2.5 |

### Case 2: Flat Plate Heaving

#### Physical Setup
| Parameter | Value | Justification |
|-----------|-------|---------------|
| Plate chord c | 1.0 (dimensionless) | Reference length |
| Plate thickness | 0.02c | Thin plate (IBM) |
| Heaving amplitude h₀ | 0.5c | Moderate amplitude |
| Heaving frequency f | varies | Set to achieve Re = 100 |
| Reynolds number | Re = 2πfh₀c/ν = 100 | Match sphere case |

#### Kinematics
Sinusoidal heaving:
```
y(t) = h₀ sin(2πft)
ẏ(t) = 2πfh₀ cos(2πft)
```

Strouhal number:
```
St = fA/U = 2fh₀/U_∞
```
where A = 2h₀ is the peak-to-peak amplitude.

#### Force Decomposition
Instantaneous force coefficients:
```
CL(t) = L(t) / (0.5 ρ U_ref² c)
CD(t) = D(t) / (0.5 ρ U_ref² c)
```
where U_ref = max(ẏ) = 2πfh₀.

**Phase-averaged forces**: Average over multiple cycles after initial transient.

#### Validation References
- **Wang (2000)**: 2D heaving foil at low Re
- **Sane & Dickinson (2002)**: Quasi-steady force model
- **Theoretical**: Added mass coefficient for thin plate

### Case 3: Simplified Mosquito Wing

#### Physical Setup
| Parameter | Symbol | Value | Unit | Source |
|-----------|--------|-------|------|--------|
| Wing span | R | 3.0 | mm | van Veen et al. (2022), *Aedes aegypti* |
| Mean chord | c | 1.0 | mm | van Veen et al. (2022) |
| Wing thickness | t | 18 | μm | van Veen et al. (2022) |
| Flap frequency | f | **717 ± 59** | Hz | Bomphrey et al. (2017) |
| Stroke amplitude | φ₀ | **39 ± 4** | degrees | Bomphrey et al. (2017) |
| Rotation amplitude | α₀ | 45 | degrees | Derived from wing pitch |
| Air density | ρ | 1.184 | kg/m³ | Standard (25°C) |
| Kinematic viscosity | ν | 1.56×10⁻⁵ | m²/s | Air at 25°C |

**Critical note on kinematics**: Mosquito stroke amplitude (39°) is **dramatically smaller** than fruit flies (160°) or honeybees (90°). This unique kinematics—the smallest of any hovering animal—shifts force production toward **rotational mechanisms** at stroke reversal, including trailing-edge vortices and rotational drag (Bomphrey et al. 2017).

**Reynolds number** (Bomphrey et al. 2017):
```
Re = 50–300 (instantaneous Re across wingbeat cycle)
```
This is lower than typical fruit fly Re (~100-250), reflecting the smaller stroke amplitude.

#### Geometry: Flat Plate Approximation
For initial benchmarking, the wing is a flat rectangular plate:
```
Wing area = R × c = 3 mm × 1 mm = 3 mm²
Aspect ratio AR = R/c = 3
Thickness = 0 (IBM surface markers)
```

**Lagrangian markers**:
- Spacing: Δx_marker = 0.05 mm (coarse) to 0.01 mm (fine)
- Marker count: 60×20 = 1,200 (coarse) to 300×100 = 30,000 (fine)

#### Kinematics: 3-Angle Flapping (Bomphrey et al. 2017)
Wing orientation defined by three Euler angles at wing root:

**Stroke angle** (flapping in horizontal plane):
```
φ(t) = φ₀ sin(2πft)
```
where φ₀ = **39°** (Bomphrey et al. 2017), f = **717 Hz**.

**Rotation angle** (wing pitch):
```
α(t) = α₀ sin(2πft + ψ_α)
```
where ψ_α = π/2 (90° phase advance, rotation leads stroke), α₀ ≈ 45°.

**Deviation angle** (out-of-plane motion):
```
θ(t) = θ₀ sin(4πft)  # Second harmonic, small amplitude (~5°)
```

For simplified case: θ(t) = 0 (planar stroke).

#### Computational Domain
| Parameter | Value |
|-----------|-------|
| Domain size | 10R × 10R × 10R = 30 mm³ |
| Base grid | 128³ |
| AMR levels | 2-3 |
| Finest resolution | 0.05 mm (coarse), 0.01 mm (fine) |
| Active cells | ~1M (coarse), ~50M (fine) |

#### Output Quantities
1. **Force coefficients**: CL(t), CD(t), CM(t) over one wingbeat
2. **Mean coefficients**: <CL>, <CD>, lift-to-drag ratio
3. **Vorticity fields**: ω magnitude at key phases (mid-stroke, reversal)
4. **Vortex structures**: Q-criterion isosurfaces showing LEV, TEV, tip vortex

#### Validation Approach
Since we use simplified geometry, direct comparison with van Veen et al. is qualitative. Validation criteria:
1. **Force magnitude**: CL_mean in range 0.5–1.5 (typical for Re~100 hovering)
2. **Force timing**: Peak forces at mid-stroke (expected for quasi-steady)
3. **LEV formation**: Leading-edge vortex visible during translation
4. **Physical plausibility**: Force direction consistent with wing motion

## Performance Measurement Methodology

### Timing Protocol
1. **Warmup**: Discard first 10 timesteps (JIT compilation, GPU cache)
2. **Measurement region**: Time 100+ timesteps
3. **Repetitions**: 3 independent runs (restart from same checkpoint)
4. **Report**: mean ± standard deviation

### Metrics Captured
| Metric | Source | Unit |
|--------|--------|------|
| Wall time total | system time | seconds |
| Time per timestep | total / n_steps | seconds |
| Poisson solve time | AMReX timer | seconds |
| IB force time | AMReX timer | seconds |
| Regrid time | AMReX timer | seconds |
| GPU memory | nvidia-smi peak | GB |
| GPU utilization | nvidia-smi average | % |

### Scaling Estimation
**Single GPU baseline** → **Target platform projection**

A40 (FP64: 0.585 TFLOPS, 696 GB/s) → A100 (FP64: 9.7 TFLOPS, 2039 GB/s)

**Projection bounds** (actual performance to be measured):
| Bound | Speedup | Formula |
|-------|---------|---------|
| Memory-bound | 2.9× | A100_bandwidth / A40_bandwidth = 2039/696 |
| Compute-bound | 16.6× | A100_TFLOPS / A40_TFLOPS = 9.7/0.585 |

CFD performance typically falls between these bounds depending on problem size and solver characteristics. We will measure actual scaling and report the observed ratio.

### Resource Estimation for Proposal
**Target**: 10 wingbeats of single mosquito wing at full resolution

| Quantity | Value | Basis |
|----------|-------|-------|
| Wingbeat period | 1.4 ms | 1/717 Hz (Bomphrey 2017) |
| Timestep Δt | 1×10⁻⁷ s | van Veen et al. (2022) |
| Timesteps per wingbeat | ~14,000 | 1.4ms / 0.1μs |
| Time per timestep (A40) | ~5 s | From FlowPastSphere scaling |
| Time per wingbeat (A40) | ~19 hours | |
| Speedup A40→A100 | 2.9–16.6× | Memory-bound to compute-bound |
| Time per wingbeat (A100) | ~1.2–6.5 hours | Conservative range |
| 10 wingbeats (A100) | ~12–65 hours | |
| Node-hours (1 GPU/node) | 12–65 | Will measure actual |

## Metadata and Provenance

### Run Identifier
Each run assigned a UUID:
```
run_id = uuid4()
```

### Git Provenance
```python
{
    "repository": "talmolab/mosquito-cfd",
    "commit": git.rev_parse("HEAD"),
    "branch": git.symbolic_ref("HEAD"),
    "dirty": len(git.diff("HEAD")) > 0,
    "diff_hash": sha256(git.diff("HEAD")) if dirty else None
}
```

### Docker Provenance
```python
{
    "image": "ghcr.io/talmolab/mosquito-cfd:fp64",
    "digest": "sha256:...",  # Image digest
    "build_date": "2026-02-23T...",
    "iamrex_commit": "52ffb65...",
    "amrex_commit": "5261817..."
}
```

### Input Provenance
```python
{
    "inputs_file": "inputs.3d.flow_past_sphere",
    "inputs_hash": sha256(file_contents),
    "modified_params": {"max_step": 100}  # Command-line overrides
}
```

### Hardware Fingerprint
```python
{
    "hostname": socket.gethostname(),
    "gpu_model": nvidia_smi.query_gpu("name"),
    "gpu_count": len(cuda.devices),
    "cuda_version": cuda.version(),
    "driver_version": nvidia_smi.query_gpu("driver_version"),
    "total_memory_gb": nvidia_smi.query_gpu("memory.total") / 1024
}
```

### Output Manifest
```python
{
    "plot_files": ["plt00000", "plt00100", ...],
    "checkpoint_files": ["chk00100"],
    "log_file": "run.log",
    "stdout_hash": sha256(stdout),
    "final_time": 1.0,  # Simulation time
    "final_step": 100
}
```

## Deliverables Specification

### Figures (Publication Quality)

| Figure | Description | Format |
|--------|-------------|--------|
| `fig_sphere_cd_convergence.pdf` | Cd vs 1/Δx with error bars, Richardson extrapolation | matplotlib |
| `fig_sphere_wake.png` | Velocity magnitude slice through wake | yt SlicePlot |
| `fig_plate_forces.pdf` | CL, CD vs phase over 3 cycles | matplotlib |
| `fig_wing_forces.pdf` | CL, CD vs t/T for one wingbeat | matplotlib |
| `fig_wing_vorticity.png` | Vorticity isosurface at mid-stroke | yt VolumePlot |
| `fig_timing_breakdown.pdf` | Stacked bar: Poisson/IB/regrid/other | matplotlib |

### Tables (CSV + LaTeX)

| Table | Columns |
|-------|---------|
| `sphere_convergence.csv` | resolution, cells, Cd, Cd_error, time_s |
| `timing_summary.csv` | case, resolution, time_per_step_mean, time_per_step_std |
| `resource_projection.csv` | case, A40_hours, A100_hours_projected |

### Methods Document

`benchmarks/METHODS.md` structure:
1. **Simulation Framework**: IAMReX version, build configuration
2. **Validation Cases**: Physical setup, boundary conditions
3. **Grid Convergence**: Richardson extrapolation methodology
4. **Force Computation**: Surface integral algorithms
5. **Kinematics**: Wing motion equations
6. **Performance Measurement**: Timing protocol
7. **Reproducibility**: Metadata schema, Docker usage
8. **References**: Literature citations

## Implementation Notes

### Force Extraction from IAMReX

IAMReX outputs forces on immersed bodies to log files. If not available, post-process:

1. **Read plot file** with yt:
   ```python
   ds = yt.load("plt00100")
   ```

2. **Identify sphere/wing surface** (IBM markers stored separately)

3. **Interpolate pressure and velocity gradients** to surface

4. **Integrate** pressure and viscous forces:
   ```python
   F_pressure = ∫ p n dA
   F_viscous = ∫ τ · n dA
   ```

### AMR Considerations

With adaptive mesh refinement:
- Forces computed at finest level covering the body
- Ensure sufficient buffer cells around body
- Regrid interval affects transient behavior (set amr.regrid_int = 4-8)

### Numerical Settings (FP64)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| CFL | 0.5 | Standard stability |
| Projection tolerance | 1e-10 | Tight for validation |
| MG iterations | 200 max | Allow convergence |
| IB iterations | 3-5 | Force convergence |