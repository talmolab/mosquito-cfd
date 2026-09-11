## MODIFIED Requirements

### Requirement: Isosurface threshold, colorbar ranges, and mesh translucency are documented, overridable CLI parameters, never auto-computed

`make_flow_video.py`'s `lev-3d` and `zvelocity-3d` modes SHALL expose `--q-threshold`,
`--vort-vmin`, `--vort-vmax`, and (`lev-3d` only) `--lev-mesh-alpha` (and the corresponding
velocity-slice color-range flags) as optional CLI arguments, defaulting to the values empirically
validated against the T3c-fine benchmark (`Q_THRESHOLD=300.0`, `VORT_VMIN=40.0`,
`VORT_VMAX=250.0`, `LEV_MESH_ALPHA=0.65`). No percentile or other automatic threshold or alpha
computation SHALL be performed.

#### Scenario: the documented default reproduces the T3c-fine benchmark video's threshold

- **GIVEN** `make_flow_video.py --field-mode lev-3d` invoked with no `--q-threshold` flag
- **WHEN** the isosurface is extracted
- **THEN** `Q_THRESHOLD=300.0` is used, matching the value documented in this capability's
  generating proposal and the original T3c-fine video

#### Scenario: an explicit override replaces the default for a different config's field distribution

- **GIVEN** `make_flow_video.py --field-mode lev-3d --q-threshold 150.0` invoked for a config whose
  Q-field distribution differs from T3c-fine's
- **WHEN** the isosurface is extracted
- **THEN** the marching-cubes level used is `150.0`, not the default `300.0`

#### Scenario: the documented default mesh alpha reproduces the proven vault rendering

- **GIVEN** `make_flow_video.py --field-mode lev-3d` invoked with no `--lev-mesh-alpha` flag
- **WHEN** the isosurface mesh is rendered
- **THEN** `LEV_MESH_ALPHA=0.65` is used, matching the value the original
  `duncan-meeting-2026-08-11` vault video was rendered with

#### Scenario: an explicit mesh-alpha override replaces the default

- **GIVEN** `make_flow_video.py --field-mode lev-3d --lev-mesh-alpha 0.4` invoked
- **WHEN** the isosurface mesh is rendered
- **THEN** the rendered mesh's facecolors carry alpha `0.4`, not the default `0.65`

## ADDED Requirements

### Requirement: The kinematics-preview tip marker is selected by distance from the hinge, not by array position

`kinematics_video._span_tip_index` SHALL select, among markers tied at maximum `|span|` (within
its existing tolerance), the one **farthest from the hinge** — not merely the first array
occurrence or the one nearest the chord centerline. The nearest-chord-axis-to-zero rule remains
only as a secondary tie-break for the residual case where multiple candidates are also tied on
distance from the hinge.

#### Scenario: an exact max-span tie resolves to the side away from the hinge

- **GIVEN** `examples/flapping_wing/wing.vertex`, whose local markers have an exact 3-way tie at
  max `|span|` on both `y = -1.475` and `y = +1.475`, with `center = (4, 2, 4)` and
  `hinge = (4, 0.5, 4)` (hinge on the negative-`y` side of center, matching
  `examples/prelim_sweep_fine`'s convention)
- **WHEN** `build_kinematics_video` computes `span_arm` and the tracked-tip trajectory
- **THEN** the selected tip marker is on the `y = +1.475` side (farthest from the hinge), giving
  `span_arm` approximately `2.98`, not the `y = -1.475` (root/hinge-adjacent) side that would give
  `span_arm` approximately `0.025`

#### Scenario: a unique max-span marker is chosen regardless of hinge position

- **GIVEN** a synthetic `.vertex` fixture whose max-`|span|` marker is unique (no tie)
- **WHEN** `_span_tip_index` is called with any hinge position
- **THEN** that unique marker is selected, unaffected by the hinge-distance tie-break (which only
  applies among tied candidates)

### Requirement: `flow_video`'s `lev-3d` mode renders the Q-criterion isosurface visibly alongside the wing

`build_flow_video`'s `lev-3d` field mode SHALL NOT force `computed_zorder=False` on its `Axes3D`
(unlike `combined-3d`/`zvelocity-3d`, where the field is a thin 2-D slice and a static
wing-in-front ordering is physically correct); it SHALL rely on mplot3d's default per-artist depth
sorting. `render_lev_frame`'s returned facecolors SHALL carry a documented, overridable alpha
(default `0.65`, matching the empirically-proven vault rendering) rather than fully opaque, so the
isosurface remains visible even where per-artist depth sorting still orders the wing in front of
part of the mesh.

#### Scenario: the isosurface is not fully occluded by the wing overlay

- **GIVEN** a synthetic Q-field producing a well-formed isosurface (following the existing
  `_synthetic_lev_box` fixture pattern in `tests/test_flow_video.py`) positioned so it visually
  overlaps the wing's rendered footprint
- **WHEN** `build_flow_video(field_mode="lev-3d", ...)` renders a frame
- **THEN** the isosurface mesh's facecolors are not fully opaque (alpha < 1.0), and the `Axes3D` for
  this mode is not created with `computed_zorder=False`

#### Scenario: `combined-3d`/`zvelocity-3d` keep their existing wing-always-in-front behavior

- **GIVEN** `build_flow_video` invoked with `field_mode="combined-3d"` or `field_mode="zvelocity-3d"`
- **WHEN** the 3-D `Axes3D` is created
- **THEN** `computed_zorder=False` is still passed, unchanged from before this change
