## Tasks

### 1. Ellipsoid Annotation
- [x] 1.1 Add matplotlib Ellipse patch to `examples/heaving_ellipsoid/visualize.py`
- [x] 1.2 Draw ellipse at body location with semi-axes (0.5, 0.02) — **at ACTUAL position from particles**
- [x] 1.3 Verify annotation visible in regenerated figures

### 2. Descriptive Naming
- [x] 2.1 Update `visualize_velocity()` in ellipsoid script to use descriptive names
- [x] 2.2 Update `visualize_forces()` to use descriptive name
- [x] 2.3 Update sphere `visualize.py` output naming
- [x] 2.4 Update `generate_figures.py` to handle new naming convention

### 3. Plot Titles
- [x] 3.1 Add informative title to sphere velocity plots
- [x] 3.2 Add informative title to ellipsoid velocity plots
- [x] 3.3 Update force plot title with simulation parameters

### 4. Figure Manifest
- [x] 4.1 Create manifest schema in `generate_figures.py`
- [x] 4.2 Generate `manifest.json` with metadata for each figure
- [x] 4.3 Include source plotfile, grid, time, case info

### 5. Fix Ellipsoid Body Position
- [x] 5.1 Read actual particle positions from plotfile (particle_position_x/y/z)
- [x] 5.2 Compute mean position to find current body center
- [x] 5.3 Update marker to show actual position, not initial position

### 6. Address Periodic Boundary Artifacts
- [x] 6.1 Generate figures from t=5 timestep (plt_1k00500) — **body at y=7.5, wake developed but not wrapped**
- [x] 6.2 Add explanation of timestep choice and force sign convention — **documented in METHODS.md**
- [x] 6.3 Document future simulation improvements in METHODS.md:
  - Heave in x-direction (non-periodic)
  - Larger y-domain
  - Non-periodic y-boundary option

### 7. Regenerate Figures
- [x] 7.1 Run updated `generate_figures.py` with data paths
- [x] 7.2 Verify all figures have annotations and titles
- [x] 7.3 Verify manifest.json is complete
- [x] 7.4 Remove old cryptically-named figures

## Validation

- [x] Visual inspection: ellipsoid body marker at ACTUAL position (not initial)
- [x] Visual inspection: ellipsoid visible near center (using t=5 timestep)
- [x] Filenames are self-documenting
- [x] manifest.json contains all figure metadata
- [x] Figures suitable for APEX proposal

## Parallelizable Tasks
- [parallel] 1.1-1.3 (ellipsoid annotation) and 2.3, 3.1 (sphere updates)
- [parallel] 3.1, 3.2, 3.3 (title additions)
- [parallel] 5.1-5.3 (body position) and 6.1-6.2 (periodic boundary)