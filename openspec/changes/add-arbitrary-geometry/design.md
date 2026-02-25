## Design Overview

This document specifies the technical implementation for arbitrary geometry and prescribed kinematics in IAMReX for APEX proposal validation.

## 1. Parametric Wing Planform Generator (Python)

### 1.1 Mathematical Definitions

**Rectangular planform**:
```
For marker at grid position (i, j):
  x = center_x + (j - n_chord/2 + 0.5) * spacing
  y = center_y
  z = center_z + (i - n_span/2 + 0.5) * spacing

where:
  n_chord = floor(chord / spacing)
  n_span = floor(span / spacing)
```

**Elliptic planform**:
```
For spanwise position z ∈ [-span/2, span/2]:
  local_chord(z) = chord * sqrt(1 - (2*z/span)²)

For each z station:
  n_chord_local = floor(local_chord(z) / spacing)
  x ∈ [-local_chord(z)/2, local_chord(z)/2]
```

### 1.2 Marker Density Guidelines

From van Veen et al. (2022) and IBM best practices:

| Resolution | Marker Spacing | Markers per Wing | Use Case |
|------------|----------------|------------------|----------|
| Coarse | 50 μm | ~1,200 | Development, debugging |
| Medium | 20 μm | ~7,500 | Initial validation |
| Fine | 10 μm | ~30,000 | Production, publication |

**Rule of thumb**: Marker spacing ≈ Δx_fluid / 2 for proper force spreading.

### 1.3 Python Implementation

```python
# src/mosquito_cfd/geometry/parametric_planform.py

import numpy as np
from enum import Enum

class PlanformShape(Enum):
    RECTANGULAR = "rectangular"
    ELLIPTIC = "elliptic"

def generate_planform(
    shape: PlanformShape,
    span: float,           # meters
    chord: float,          # meters (mean chord for elliptic)
    spacing: float,        # meters
    center: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Generate Lagrangian markers for wing planform.

    Returns:
        markers: (N, 3) array of marker positions
    """
    cx, cy, cz = center
    markers = []

    if shape == PlanformShape.RECTANGULAR:
        n_span = int(span / spacing)
        n_chord = int(chord / spacing)
        for i in range(n_span):
            for j in range(n_chord):
                x = cx - chord/2 + (j + 0.5) * spacing
                y = cy
                z = cz - span/2 + (i + 0.5) * spacing
                markers.append([x, y, z])

    elif shape == PlanformShape.ELLIPTIC:
        n_span = int(span / spacing)
        for i in range(n_span):
            z_rel = -span/2 + (i + 0.5) * spacing
            z_norm = 2 * z_rel / span  # Normalized to [-1, 1]
            local_chord = chord * np.sqrt(max(0, 1 - z_norm**2))
            n_chord_local = max(1, int(local_chord / spacing))
            for j in range(n_chord_local):
                x = cx - local_chord/2 + (j + 0.5) * (local_chord / n_chord_local)
                y = cy
                z = cz + z_rel
                markers.append([x, y, z])

    return np.array(markers)
```

### 1.4 Vertex File I/O

```python
# src/mosquito_cfd/geometry/vertex_io.py

import numpy as np

def write_vertex_file(markers: np.ndarray, filepath: str) -> None:
    """Write markers to .vertex format (count + x,y,z per line)."""
    with open(filepath, 'w') as f:
        f.write(f"{len(markers)}\n")
        for m in markers:
            f.write(f"{m[0]:.10e} {m[1]:.10e} {m[2]:.10e}\n")

def read_vertex_file(filepath: str) -> np.ndarray:
    """Read markers from .vertex file."""
    with open(filepath, 'r') as f:
        n_markers = int(f.readline().strip())
        markers = np.zeros((n_markers, 3))
        for i in range(n_markers):
            line = f.readline().strip().split()
            markers[i] = [float(x) for x in line[:3]]
    return markers
```

## 2. External Geometry Loading (C++)

### 2.1 Vertex File Reader

```cpp
// Source/particles/VertexFileReader.cpp

#include <AMReX_Particles.H>
#include <fstream>
#include <vector>

void ReadVertexFile(
    const std::string& filename,
    std::vector<amrex::RealVect>& markers,
    const amrex::RealVect& center,
    amrex::Real scale)
{
    std::ifstream file(filename);
    if (!file.is_open()) {
        amrex::Abort("Cannot open vertex file: " + filename);
    }

    int n_markers;
    file >> n_markers;
    markers.resize(n_markers);

    for (int i = 0; i < n_markers; ++i) {
        amrex::Real x, y, z;
        file >> x >> y >> z;
        // Apply scale and translate to center
        markers[i][0] = x * scale + center[0];
        markers[i][1] = y * scale + center[1];
        markers[i][2] = z * scale + center[2];
    }

    amrex::Print() << "Read " << n_markers << " markers from " << filename << "\n";
}
```

### 2.2 Integration with ParticleInit

In `ParticleInit.cpp`, add case for `geometry_type = 4`:

```cpp
// In particle initialization routine
int geometry_type = pp.query("geometry_type", geometry_type);

if (geometry_type == 4) {
    // External vertex file
    std::string geometry_file;
    pp.get("geometry_file", geometry_file);

    amrex::RealVect center;
    pp.query("center_x", center[0]);
    pp.query("center_y", center[1]);
    pp.query("center_z", center[2]);

    amrex::Real scale = 1.0;
    pp.query("scale", scale);

    std::vector<amrex::RealVect> markers;
    ReadVertexFile(geometry_file, markers, center, scale);

    // Store as reference positions for kinematics
    m_reference_positions = markers;

    // Initialize particles at reference positions
    for (const auto& pos : markers) {
        // Add particle at pos with zero velocity
        AddParticle(pos, {0.0, 0.0, 0.0});
    }
}
```

## 3. Hardcoded Sinusoidal Kinematics (C++)

### 3.1 Euler Angle Convention

Following van Veen et al. (2022) and standard insect flight convention:

1. **Stroke angle φ**: Rotation about body-fixed vertical axis (dorsal-ventral)
2. **Pitch angle α**: Rotation about wing spanwise axis (leading/trailing edge)
3. **Deviation angle θ**: Rotation about body-fixed anterior-posterior axis

**Rotation order**: φ → θ → α (extrinsic, ZYX convention)

### 3.2 Rotation Matrix

```cpp
// Compute rotation matrix for given Euler angles
void ComputeRotationMatrix(
    amrex::Real phi,    // stroke angle (radians)
    amrex::Real alpha,  // pitch angle (radians)
    amrex::Real theta,  // deviation angle (radians)
    amrex::Real R[3][3])
{
    amrex::Real cp = std::cos(phi),   sp = std::sin(phi);
    amrex::Real ca = std::cos(alpha), sa = std::sin(alpha);
    amrex::Real ct = std::cos(theta), st = std::sin(theta);

    // R = Rz(phi) * Ry(theta) * Rx(alpha)
    R[0][0] = cp*ct;
    R[0][1] = cp*st*sa - sp*ca;
    R[0][2] = cp*st*ca + sp*sa;

    R[1][0] = sp*ct;
    R[1][1] = sp*st*sa + cp*ca;
    R[1][2] = sp*st*ca - cp*sa;

    R[2][0] = -st;
    R[2][1] = ct*sa;
    R[2][2] = ct*ca;
}
```

### 3.3 Kinematics Update Function

```cpp
// Source/particles/WingKinematics.cpp

void UpdateWingKinematics(
    amrex::Real time,
    const std::vector<amrex::RealVect>& reference_positions,
    const amrex::RealVect& hinge,
    amrex::ParticleContainer& particles)
{
    // Van Veen et al. (2022) parameters - HARDCODED FOR VALIDATION
    constexpr amrex::Real freq = 600.0;                      // Hz
    constexpr amrex::Real omega = 2.0 * M_PI * freq;
    constexpr amrex::Real phi_amp = 70.0 * M_PI / 180.0;     // ±70° stroke
    constexpr amrex::Real alpha_0 = 45.0 * M_PI / 180.0;     // 45° pitch
    constexpr amrex::Real theta_amp = 0.0;                   // No deviation (planar)

    // Current angles
    amrex::Real phi = phi_amp * std::sin(omega * time);
    amrex::Real alpha = alpha_0 * std::cos(omega * time);  // 90° phase lead
    amrex::Real theta = theta_amp * std::sin(2.0 * omega * time);

    // Compute rotation matrix
    amrex::Real R[3][3];
    ComputeRotationMatrix(phi, alpha, theta, R);

    // Update each particle position
    int i = 0;
    for (auto& particle : particles) {
        // Reference position relative to hinge
        amrex::RealVect ref_rel = reference_positions[i] - hinge;

        // Rotate about hinge
        amrex::RealVect new_pos;
        new_pos[0] = hinge[0] + R[0][0]*ref_rel[0] + R[0][1]*ref_rel[1] + R[0][2]*ref_rel[2];
        new_pos[1] = hinge[1] + R[1][0]*ref_rel[0] + R[1][1]*ref_rel[1] + R[1][2]*ref_rel[2];
        new_pos[2] = hinge[2] + R[2][0]*ref_rel[0] + R[2][1]*ref_rel[1] + R[2][2]*ref_rel[2];

        particle.pos(0) = new_pos[0];
        particle.pos(1) = new_pos[1];
        particle.pos(2) = new_pos[2];

        // Compute velocity (time derivative of position)
        // For prescribed motion, velocity = d(R*r)/dt
        // Simplified: use finite difference or analytical derivative
        // ... (implementation details)

        ++i;
    }
}
```

### 3.4 Integration Point

Call `UpdateWingKinematics()` at the start of each timestep in the main time-stepping loop:

```cpp
// In NavierStokes::Advance() or equivalent
if (m_do_prescribed_motion) {
    UpdateWingKinematics(
        m_time,
        m_reference_positions,
        m_hinge_position,
        m_particle_container
    );
}
```

## 4. Non-Dimensionalization Schemes

### 4.1 Design Decision: Two Input File Regimes

**Problem**: Non-dimensionalization affects runtime, Reynolds number, and CFL stability. A single configuration cannot optimize for both quick validation and physically accurate production runs.

**Solution**: Provide two input file configurations:

| File | Purpose | Runtime | Physics Accuracy |
|------|---------|---------|------------------|
| `inputs.3d.validation` | Debug, verify code correctness | ~10 min | Approximate |
| `inputs.3d.production` | APEX figures, literature comparison | ~1.4 hr/wingbeat | Accurate |

### 4.2 Non-Dimensionalization Theory

**Reference quantities**:
- L_ref = chord (characteristic length)
- U_ref = characteristic velocity
- T_ref = L_ref / U_ref (characteristic time)
- ν_ref = U_ref × L_ref / Re (viscosity for target Re)

**Dimensionless frequency**:
```
f* = f_physical × T_ref = f_physical × L_ref / U_ref
```

**Wing tip velocity** (from kinematics):
```
V_tip* = 2π × f* × φ_amp_rad × (span*/2)
       ≈ 11.5 × f*  (for φ_amp = 70°, span* = 3)
```

**Effective Reynolds number**:
```
Re_eff = V_tip* × L* / ν*
```

### 4.3 Validation Regime (f* = 1.0)

**Rationale**: Minimize steps per wingbeat for fast turnaround.

| Parameter | Value | Derivation |
|-----------|-------|------------|
| f* | 1.0 | 1 wingbeat = 1 time unit |
| V_tip* | ~11.5 | High tip velocity |
| ν* | 0.115 | Re_eff = 11.5 / 0.115 = 100 |
| dt | 0.0005 | CFL-safe for V_tip* = 11.5 |
| Steps/wingbeat | 2,000 | 1.0 / 0.0005 |
| Grid | 64×32×64 | Coarse for speed |

**CFL check**:
```
dt_CFL = CFL × dx / V_max
       = 0.3 × (8/64) / 11.5
       = 0.3 × 0.125 / 11.5
       ≈ 0.0033

dt = 0.0005 < dt_CFL ✓
```

**Trade-offs**:
- ✅ Fast (~10 min for 1 wingbeat)
- ✅ Sufficient for code verification
- ⚠️ Lower resolution, approximate forces
- ⚠️ Not suitable for publication

### 4.4 Production Regime (f* = 0.1)

**Rationale**: Proper velocity scaling where V_tip* ~ 1, matching literature conventions.

| Parameter | Value | Derivation |
|-----------|-------|------------|
| f* | 0.1 | Physically grounded scaling |
| V_tip* | ~1.15 | Matches Re definition |
| ν* | 0.01 | Standard Re = 1.15 / 0.01 ≈ 115 |
| dt | 0.001 | CFL-safe for V_tip* ~ 1 |
| Steps/wingbeat | 10,000 | 10 / 0.001 |
| Grid | 128×64×128 | Medium resolution |

**CFL check**:
```
dt_CFL = CFL × dx / V_max
       = 0.3 × (8/128) / 1.15
       = 0.3 × 0.0625 / 1.15
       ≈ 0.016

dt = 0.001 < dt_CFL ✓
```

**Trade-offs**:
- ✅ Accurate Reynolds number scaling
- ✅ Comparable to van Veen et al. (2022)
- ✅ Publication quality
- ⚠️ Slower (~1.4 hr/wingbeat)

### 4.5 Mosquito-Specific Considerations (Future)

**Key difference**: Mosquitoes have uniquely small stroke amplitude.

| Species | Stroke Amp | Frequency | Re Range | Source |
|---------|------------|-----------|----------|--------|
| Fruit fly | ±80° | 200 Hz | 100-300 | van Veen 2022 |
| **Mosquito** | **±20°** | 717 Hz | 50-300 | Bomphrey 2017 |

For mosquito-specific simulations, update:
- `kinematics_stroke_amp = 20.0` (not 70.0)
- Adjust viscosity for target Re
- Consider higher frequency effects on timestep

### 4.6 Summary Decision Matrix

```
Use Case                    → Input File
────────────────────────────────────────────
Quick debug, code check     → inputs.3d.validation
Publication figures         → inputs.3d.production
Grid convergence study      → inputs.3d.production (vary grid)
Mosquito-specific science   → (future: inputs.3d.mosquito)
```

---

## 5. Computational Domain Setup

### 5.1 Domain Sizing (van Veen-style)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Domain | 10R × 10R × 10R | R = span = 3 mm → 30 mm cube |
| Wing center | (5R, 5R, 5R) | Centered in domain |
| Boundary conditions | Inflow (x-lo), outflow (x-hi), slip (y, z) | Far-field approximation |

### 5.2 Grid Resolution

| Level | Δx | Cells (per dimension) | Active cells |
|-------|----|-----------------------|--------------|
| Base | 0.5 mm | 60 | 216,000 |
| AMR L1 | 0.25 mm | +refinement near wing | ~500,000 |
| AMR L2 | 0.125 mm | +refinement near wing | ~2,000,000 |

### 5.3 Time Stepping

| Parameter | Value | Derivation |
|-----------|-------|------------|
| Wingbeat period | T = 1/600 Hz = 1.67 ms | van Veen frequency |
| CFL target | 0.5 | Standard for stability |
| Timestep | Δt ≈ 1×10⁻⁷ s | Set by CFL with fine grid |
| Steps per wingbeat | ~16,700 | T / Δt |

## 6. Validation Outputs

### 6.1 Force Extraction

From IAMReX particle data:
- `particle_real_comp3` → F_x (drag direction)
- `particle_real_comp4` → F_y (lift direction)
- `particle_real_comp5` → F_z (spanwise)

**Force coefficients**:
```
CL = F_lift / (0.5 * ρ * U_tip² * A_wing)
CD = F_drag / (0.5 * ρ * U_tip² * A_wing)

where:
  U_tip = 2πf * R * φ_amp  (tip velocity at midstroke)
  A_wing = span * chord    (planform area)
```

### 6.2 Flow Visualization

Using yt library:
- Velocity magnitude slices at z = wing_center
- Vorticity magnitude (Q-criterion) isosurfaces
- Streamlines showing LEV, TEV structures

### 6.3 Visualization Code Architecture

```python
# examples/flapping_wing/visualize.py

import argparse
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import yt

from .plot_config import STYLE, COLORS, LABELS

plt.rcParams.update(STYLE)


def extract_forces(plotfile: str) -> dict:
    """Extract force components and compute coefficients."""
    ds = yt.load(plotfile)
    ad = ds.all_data()

    # Sum forces over all markers
    fx = float(np.array(ad['all', 'particle_real_comp3']).sum())
    fy = float(np.array(ad['all', 'particle_real_comp4']).sum())
    fz = float(np.array(ad['all', 'particle_real_comp5']).sum())

    # Van Veen parameters (hardcoded for validation)
    span = 3.0e-3  # m
    chord = 1.0e-3  # m
    freq = 600.0  # Hz
    phi_amp = 70.0 * np.pi / 180.0  # rad
    rho = 1.225  # kg/m³ (air)

    # Reference quantities
    U_tip = 2 * np.pi * freq * span * phi_amp  # tip velocity
    A_wing = span * chord  # planform area
    q = 0.5 * rho * U_tip**2  # dynamic pressure

    # Force coefficients
    cl = -fy / (q * A_wing)  # lift (negative fy is upward)
    cd = -fx / (q * A_wing)  # drag (negative fx is forward)

    return {
        "time": float(ds.current_time),
        "fx": fx, "fy": fy, "fz": fz,
        "cl": cl, "cd": cd,
    }


def plot_forces(force_data: list[dict], output_path: Path):
    """Generate force coefficient vs phase plot (Figure F1)."""
    times = np.array([d["time"] for d in force_data])
    cl = np.array([d["cl"] for d in force_data])
    cd = np.array([d["cd"] for d in force_data])

    # Normalize to phase
    T = 1.0 / 600.0  # period
    phase = (times % T) / T  # normalized 0-1

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(phase, cl, color=COLORS['lift'], label=r'$C_L$', linewidth=2)
    ax.plot(phase, cd, color=COLORS['drag'], label=r'$C_D$', linewidth=2)

    # Acceptance range
    ax.axhspan(0.5, 1.5, alpha=0.1, color='green', label='Expected CL range')

    ax.set_xlabel(LABELS['phase'])
    ax.set_ylabel('Force coefficient')
    ax.legend(loc='upper right')
    ax.set_xlim(0, 1)
    ax.grid(True, alpha=0.3)

    plt.savefig(output_path, bbox_inches='tight')
    plt.savefig(output_path.with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()


def plot_velocity(plotfile: str, output_path: Path):
    """Generate velocity field slice (Figure V1)."""
    ds = yt.load(plotfile)

    # Z-slice through wing center
    slc = yt.SlicePlot(ds, 'z', 'x_velocity')
    slc.set_log('x_velocity', False)
    slc.set_cmap('x_velocity', 'RdBu_r')
    slc.annotate_title(f't = {float(ds.current_time):.4f} s')

    slc.save(str(output_path))


def plot_vorticity(plotfile: str, output_path: Path):
    """Generate vorticity field slice (Figure V2).

    Note: Requires computing vorticity from velocity gradients.
    yt can derive this if velocity fields are available.
    """
    ds = yt.load(plotfile)

    # Add vorticity derived field if not present
    def _vorticity_z(field, data):
        # ω_z = ∂v/∂x - ∂u/∂y
        dvdx = data['index', 'dy'] * 0  # placeholder - needs gradient
        dudy = data['index', 'dx'] * 0
        return dvdx - dudy

    # Use velocity magnitude as proxy for now
    slc = yt.SlicePlot(ds, 'z', ('gas', 'velocity_magnitude'))
    slc.set_log(('gas', 'velocity_magnitude'), False)
    slc.annotate_title(f'Flow structure at t = {float(ds.current_time):.4f} s')

    slc.save(str(output_path))
```

### 6.4 Metadata Tracking

```python
# examples/flapping_wing/metadata.py

import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of file."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return f"sha256:{sha256.hexdigest()}"


def get_git_info(repo_path: Path | None = None) -> dict:
    """Get current git commit, branch, and status."""
    cwd = str(repo_path) if repo_path else None
    try:
        commit = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], text=True, cwd=cwd
        ).strip()
        branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'], text=True, cwd=cwd
        ).strip()
        dirty = subprocess.call(
            ['git', 'diff', '--quiet'], cwd=cwd
        ) != 0
        remote_url = subprocess.check_output(
            ['git', 'config', '--get', 'remote.origin.url'], text=True, cwd=cwd
        ).strip()
        return {
            "commit": commit,
            "branch": branch,
            "dirty": dirty,
            "remote_url": remote_url,
        }
    except Exception as e:
        return {"commit": "unknown", "branch": "unknown", "dirty": True, "error": str(e)}


def get_gpu_info() -> dict:
    """Detect GPU model and count using nvidia-smi."""
    try:
        result = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version',
             '--format=csv,noheader,nounits'],
            text=True
        )
        lines = result.strip().split('\n')
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 3:
                gpus.append({
                    "model": parts[0],
                    "memory_mb": int(parts[1]),
                    "driver_version": parts[2],
                })
        return {
            "gpu_count": len(gpus),
            "gpus": gpus,
            "gpu_model": gpus[0]["model"] if gpus else "unknown",
            "driver_version": gpus[0]["driver_version"] if gpus else "unknown",
        }
    except Exception as e:
        return {"gpu_count": 0, "gpus": [], "error": str(e)}


def get_cuda_version() -> str:
    """Detect CUDA version from nvcc or nvidia-smi."""
    # Try nvcc first
    try:
        result = subprocess.check_output(['nvcc', '--version'], text=True)
        match = re.search(r'release (\d+\.\d+)', result)
        if match:
            return match.group(1)
    except Exception:
        pass

    # Fall back to nvidia-smi
    try:
        result = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=driver_version', '--format=csv,noheader'],
            text=True
        )
        # nvidia-smi shows CUDA version in header, parse it
        result = subprocess.check_output(['nvidia-smi'], text=True)
        match = re.search(r'CUDA Version: (\d+\.\d+)', result)
        if match:
            return match.group(1)
    except Exception:
        pass

    return "unknown"


def get_docker_info() -> dict:
    """Get Docker image info if running in container."""
    # Check for Docker environment
    if os.path.exists('/.dockerenv'):
        # Try to get image info from environment or labels
        image = os.environ.get('DOCKER_IMAGE', 'unknown')
        # Try to read image digest from /etc/hostname or cgroup
        try:
            with open('/proc/self/cgroup', 'r') as f:
                content = f.read()
                match = re.search(r'docker/([a-f0-9]+)', content)
                container_id = match.group(1)[:12] if match else "unknown"
        except Exception:
            container_id = "unknown"
        return {
            "in_container": True,
            "image": image,
            "container_id": container_id,
        }
    return {"in_container": False}


def parse_inputs_file(inputs_path: Path) -> dict:
    """Parse IAMReX inputs file to extract simulation parameters."""
    params = {}
    with open(inputs_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Try to parse as number
                try:
                    if '.' in value:
                        params[key] = float(value)
                    else:
                        params[key] = int(value)
                except ValueError:
                    params[key] = value
    return params


def count_vertex_markers(vertex_path: Path) -> int:
    """Count markers in vertex file."""
    with open(vertex_path, 'r') as f:
        first_line = f.readline().strip()
        return int(first_line)


def parse_amrex_timing(log_path: Path) -> dict:
    """Parse timing information from AMReX stdout log.

    AMReX outputs lines like:
        STEP 100 ends. TIME = 0.001 DT = 1e-05
        Coarse TimeStep time: 0.234567

    Returns dict with wall_time, timesteps, time_per_step, throughput.
    """
    timing = {
        "wall_time_s": 0.0,
        "timesteps": 0,
        "time_per_step_s": 0.0,
        "throughput_mcells_per_s": 0.0,
    }

    step_times = []
    max_step = 0
    n_cells = None

    with open(log_path, 'r') as f:
        for line in f:
            # Parse step completion
            if 'STEP' in line and 'ends' in line:
                match = re.search(r'STEP\s+(\d+)', line)
                if match:
                    max_step = max(max_step, int(match.group(1)))

            # Parse timestep timing
            if 'TimeStep time:' in line:
                match = re.search(r'TimeStep time:\s+([\d.e+-]+)', line)
                if match:
                    step_times.append(float(match.group(1)))

            # Parse cell count from grid info
            if 'total number of cells' in line.lower():
                match = re.search(r'(\d+)', line)
                if match:
                    n_cells = int(match.group(1))

    if step_times:
        timing["timesteps"] = max_step
        timing["time_per_step_s"] = sum(step_times) / len(step_times)
        timing["wall_time_s"] = sum(step_times)

        # Compute throughput if we know cell count
        if n_cells and timing["time_per_step_s"] > 0:
            timing["throughput_mcells_per_s"] = (
                n_cells / timing["time_per_step_s"] / 1e6
            )

    return timing


def compute_validation_metrics(force_data: list[dict], freq: float = 600.0) -> dict:
    """Compute validation metrics from force time series.

    Args:
        force_data: List of dicts with 'time', 'cl', 'cd' keys
        freq: Wingbeat frequency in Hz

    Returns:
        Dict with mean_cl, mean_cd, cl_range, peak detection, etc.
    """
    import numpy as np

    times = np.array([d["time"] for d in force_data])
    cl = np.array([d["cl"] for d in force_data])
    cd = np.array([d["cd"] for d in force_data])

    # Compute phase (0 to 1)
    T = 1.0 / freq
    phase = (times % T) / T

    # Basic statistics
    mean_cl = float(np.mean(cl))
    mean_cd = float(np.mean(cd))
    cl_range = [float(np.min(cl)), float(np.max(cl))]

    # Check acceptance criteria
    cl_in_range = 0.5 <= mean_cl <= 1.5

    # Find peak phase (should be near 0.25 for mid-stroke)
    peak_idx = np.argmax(np.abs(cl))
    peak_phase = float(phase[peak_idx])
    # Mid-stroke at phase 0.25 or 0.75 (±0.1 tolerance)
    peak_at_midstroke = (
        0.15 <= peak_phase <= 0.35 or 0.65 <= peak_phase <= 0.85
    )

    return {
        "mean_cl": round(mean_cl, 4),
        "mean_cd": round(mean_cd, 4),
        "cl_range": [round(x, 4) for x in cl_range],
        "cl_in_range": cl_in_range,
        "peak_phase": round(peak_phase, 4),
        "peak_at_midstroke": peak_at_midstroke,
        "lev_visible": None,  # Set manually after visual inspection
    }


def generate_run_metadata(
    run_id: str | None,
    inputs_file: Path,
    vertex_file: Path,
    geometry_params: dict,
    kinematics_params: dict,
    timing: dict,
    outputs: dict,
    validation: dict,
    iamrex_path: Path | None = None,
) -> dict:
    """Generate complete run metadata record with auto-detected values."""

    # Auto-generate run_id if not provided
    if run_id is None:
        run_id = f"flapping_wing_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # Parse inputs file for simulation params
    sim_params = parse_inputs_file(inputs_file)

    # Count actual markers
    num_markers = count_vertex_markers(vertex_file)

    # Detect hardware
    gpu_info = get_gpu_info()
    cuda_version = get_cuda_version()

    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git": get_git_info(),
        "iamrex_git": get_git_info(iamrex_path) if iamrex_path else None,
        "docker": get_docker_info(),
        "inputs_file": str(inputs_file.resolve()),
        "inputs_hash": compute_file_hash(inputs_file),
        "inputs_params": sim_params,
        "geometry": {
            "vertex_file": str(vertex_file.resolve()),
            "vertex_hash": compute_file_hash(vertex_file),
            "num_markers": num_markers,
            **geometry_params,
        },
        "kinematics": kinematics_params,
        "hardware": {
            **gpu_info,
            "cuda_version": cuda_version,
        },
        "timing": timing,
        "outputs": outputs,
        "validation": validation,
    }


def save_metadata(metadata: dict, output_path: Path):
    """Save metadata to JSON file with pretty formatting."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)
    print(f"Saved metadata to {output_path}")


def load_metadata(metadata_path: Path) -> dict:
    """Load metadata from JSON file."""
    with open(metadata_path, 'r') as f:
        return json.load(f)
```

### 6.5 Figure Orchestration

```python
# examples/flapping_wing/generate_all_figures.py

"""Generate all validation figures for flapping wing case.

Usage:
    uv run python examples/flapping_wing/generate_all_figures.py \
        --data-dir /path/to/simulation/output \
        --output-dir examples/flapping_wing/figures/
"""

import argparse
from pathlib import Path

from visualize import (
    extract_forces,
    plot_forces,
    plot_velocity,
    plot_vorticity,
    plot_planform,
    plot_kinematics,
    plot_wing_phases,
)
from metadata import generate_run_metadata, save_metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--vertex-file", type=Path, default=Path("wing.vertex"))
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    # Find all plotfiles
    plotfiles = sorted(args.data_dir.glob("plt*"))
    plotfiles = [p for p in plotfiles if p.is_dir()]

    print(f"Found {len(plotfiles)} plotfiles")

    # G1: Planform
    print("Generating G1: Wing planform...")
    plot_planform(args.vertex_file, args.output_dir / "fig_planform.pdf")

    # K1: Kinematics
    print("Generating K1: Euler angles...")
    plot_kinematics(args.output_dir / "fig_kinematics.pdf")

    # K2: Wing phases (requires multiple plotfiles)
    print("Generating K2: Wing phases...")
    phase_files = [plotfiles[i] for i in [0, len(plotfiles)//4,
                                           len(plotfiles)//2, 3*len(plotfiles)//4]
                   if i < len(plotfiles)]
    plot_wing_phases(phase_files, args.output_dir / "fig_wing_phases.png")

    # F1: Forces
    print("Generating F1: Force coefficients...")
    force_data = [extract_forces(str(pf)) for pf in plotfiles]
    plot_forces(force_data, args.output_dir / "fig_forces.pdf")

    # Save force CSV
    import csv
    csv_path = args.output_dir / "forces.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['time', 'fx', 'fy', 'fz', 'cl', 'cd'])
        writer.writeheader()
        writer.writerows(force_data)
    print(f"Saved forces to {csv_path}")

    # V1: Velocity at mid-stroke
    midstroke_idx = len(plotfiles) // 4  # T/4
    print(f"Generating V1: Velocity at {plotfiles[midstroke_idx]}...")
    plot_velocity(str(plotfiles[midstroke_idx]),
                  args.output_dir / "fig_velocity_midstroke.png")

    # V2: Vorticity at mid-stroke
    print(f"Generating V2: Vorticity...")
    plot_vorticity(str(plotfiles[midstroke_idx]),
                   args.output_dir / "fig_vorticity_midstroke.png")

    print(f"\nAll figures saved to {args.output_dir}")
    print("Run with --help for more options")


if __name__ == "__main__":
    main()
```

## 7. Future Extension Points

### 7.1 Input-File Parameters

Replace hardcoded constants with `ParmParse` queries:

```cpp
// Future: read from input file
amrex::ParmParse pp("kinematics");
amrex::Real freq, phi_amp, alpha_0;
pp.get("frequency", freq);
pp.get("stroke_amplitude", phi_amp);  // degrees
pp.get("pitch_amplitude", alpha_0);   // degrees
phi_amp *= M_PI / 180.0;  // convert to radians
alpha_0 *= M_PI / 180.0;
```

### 7.2 Time Series File

Add interpolation from external file:

```cpp
// Future: read kinematics time series
std::vector<amrex::Real> t_data, phi_data, alpha_data, theta_data;
ReadKinematicsFile("kinematics.csv", t_data, phi_data, alpha_data, theta_data);

// Interpolate to current time
amrex::Real phi = LinearInterp(t_data, phi_data, time);
amrex::Real alpha = LinearInterp(t_data, alpha_data, time);
amrex::Real theta = LinearInterp(t_data, theta_data, time);
```

### 7.3 Multi-Body

Extend particle container to track multiple bodies:

```cpp
// Future: multiple wings
struct BodyConfig {
    std::string geometry_file;
    amrex::RealVect hinge;
    std::vector<amrex::RealVect> reference_positions;
    // Per-body kinematics parameters (or shared)
};
std::vector<BodyConfig> m_bodies;
```