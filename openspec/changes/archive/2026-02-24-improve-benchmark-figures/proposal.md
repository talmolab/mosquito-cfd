## Why

The current benchmark figures are difficult to interpret:

1. **Missing body annotations**: The ellipsoid is invisible in velocity plots (only 0.02 units thick) while the sphere has a visible circle annotation
2. **Cryptic filenames**: `plt_1k01000_x_velocity.png` doesn't convey case, time, or conditions
3. **No metadata**: Figures lack accompanying information about simulation parameters
4. **Periodic boundary artifacts**: Wake wraps around domain, confusing viewers

For the APEX proposal (deadline Feb 27, 2026), reviewers need to quickly understand what each figure shows.

## What Changes

### 1. Consistent Body Annotations

Add visible annotations showing body location/outline on all velocity field plots:
- **Sphere**: Already has `annotate_sphere()` (white circle) — no change needed
- **Ellipsoid**: Add ellipse patch showing the thin wing cross-section (currently only has a `+` marker)

### 2. Descriptive Figure Naming

Replace plotfile-based names with descriptive names:

| Current | Proposed |
|---------|----------|
| `plt10000_x_velocity.png` | `sphere_Re100_steady_x_velocity.png` |
| `plt_1k01000_x_velocity.png` | `ellipsoid_heaving_t10_x_velocity.png` |
| `heaving_ellipsoid_forces.png` | `ellipsoid_heaving_force_history.png` |

### 3. Figure Manifest with Metadata

Create `benchmarks/results/figures/manifest.json`:

```json
{
  "figures": [
    {
      "filename": "sphere_Re100_steady_x_velocity.png",
      "case": "flow_past_sphere",
      "description": "Streamwise velocity at steady state (Re=100)",
      "simulation_time": 100.0,
      "grid": "256x128x128",
      "source_plotfile": "plt10000"
    }
  ],
  "generated": "2026-02-24T12:00:00Z",
  "generator": "generate_figures.py"
}
```

### 4. Informative Plot Titles

Add titles to each figure showing:
- Case name and key parameters
- Simulation time
- Field being visualized

### 5. Fix Ellipsoid Body Position Marker

**Problem**: The current + marker shows the *initial* position (y=0 in plot coords), but after t=10 the ellipsoid has moved 5 units upward (velocity_y=0.5 × t=10) to y=+5.

**Solution**: Read actual particle positions from plotfile and mark current body location:
```python
# Extract particle positions from plotfile
ad = ds.all_data()
x_pos = np.mean(ad['all', 'particle_position_x'])
y_pos = np.mean(ad['all', 'particle_position_y'])
```

### 6. Address Periodic Boundary Artifacts

**Problem**: Ellipsoid heaves in y-direction, which has periodic boundaries. Wake wraps from y=+5 to y=-5, creating confusing dual-wake appearance.

**Immediate fixes** (for APEX deadline):
1. Use earlier timestep (t=1-2) where body is near initial position and wake hasn't wrapped
2. Add caption explaining periodic boundary effect

**Future simulation improvements** (document in METHODS.md):
- Heave in x-direction (non-periodic) instead of y
- Use larger y-domain so wake doesn't reach boundary
- Use non-periodic y-boundary with proper outflow conditions

## Impact

### Modified Files
- `examples/flow_past_sphere/visualize.py` — add title, update output naming
- `examples/heaving_ellipsoid/visualize.py` — add ellipse annotation, title, update output naming
- `benchmarks/results/figures/generate_figures.py` — generate manifest, use new naming

### New Files
- `benchmarks/results/figures/manifest.json` — figure metadata

### Dependencies
- Builds on `add-apex-benchmarking` (uses existing visualization infrastructure)

### Related Changes
- [add-arbitrary-geometry](../add-arbitrary-geometry/proposal.md) — Uses same figure naming and metadata conventions for flapping wing validation figures

## Scope

This is a focused improvement for APEX proposal readability. Out of scope:
- Changing simulation parameters to avoid periodic boundary effects
- Adding new visualization types (vorticity, streamlines)
- Interactive visualizations
