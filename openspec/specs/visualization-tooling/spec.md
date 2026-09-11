# visualization-tooling Specification

## Purpose
TBD - created by archiving change add-visualization-tooling. Update Purpose after archive.
## Requirements
### Requirement: Video and figure generators resolve parameters from a named config or an explicit override, never a hardcoded constant

`flow_video.py` and `kinematics_video.py` SHALL accept either `--config <name> --corpus-dir <dir>`
(resolving hinge, center, and kinematics from that config's own generated deck) or explicit
`--hinge`, `--center`, `--stroke-amp-deg`, `--pitch-amp-deg`, `--frequency-fstar` overrides. No
plotfile path, hinge value, or kinematic parameter SHALL be a hardcoded module-level constant
reachable only by editing source.

#### Scenario: any of the 27 sweep configs can be rendered without editing source

- **GIVEN** a sweep corpus directory containing `sweep_manifest.json` and a generated deck for
  config `s35_f085_p30`
- **WHEN** `make_flow_video.py` is invoked with `--config s35_f085_p30 --corpus-dir <dir>
  --field-mode wake-slice --plotfile-dir <plt-dir> --out-dir <out> --docker-digest sha256:<64hex>
  --timestamp <iso8601>`
- **THEN** the video is rendered using that config's own hinge/center/kinematics read from its deck,
  with no source-code edit required

#### Scenario: an explicit override takes precedence over the config's own deck values

- **GIVEN** config `s45_f115_p60`'s own deck records the as-run hinge `(4.0, 2.0, 2.5)`
- **WHEN** `make_kinematics_video.py` is invoked with `--config s45_f115_p60 --corpus-dir <dir>
  --hinge 4.0 0.5 4.0`
- **THEN** the rendered video uses the explicit override hinge `(4.0, 0.5, 4.0)`, not the deck's own
  `(4.0, 2.0, 2.5)`

### Requirement: Every generated video or figure writes the CC-1 run-metadata sidecar

Every artifact-producing function in `visualization/` and `force_surrogate/comparison_figure.py` SHALL call `validate_image_digest` before any computation or file write, and SHALL write a `<name>_run_metadata.json` sidecar afterward via `capture_surrogate_run_metadata`, following the same provenance triple convention as `wing_phase_diagnostic.build_wing_phase_figure`.

#### Scenario: a mutable docker tag is rejected before any rendering work happens

- **GIVEN** a call to any `visualization/` or `comparison_figure.py` builder function with
  `docker_image_digest=":latest"`
- **WHEN** the function is invoked
- **THEN** it raises `ValueError` immediately, before reading any plotfile, extracting any field, or
  opening any matplotlib figure

#### Scenario: a rendered video has a matching run-metadata sidecar

- **GIVEN** a successful `flow_video` call that writes `<name>.mp4`
- **WHEN** the call returns
- **THEN** `<name>_run_metadata.json` also exists in the same output directory, containing the
  caller-supplied docker digest and ISO-8601 timestamp (never a wall-clock-derived value)

#### Scenario: a builder with more than one input file independently hashes every input, not just the primary one

- **GIVEN** a `comparison_figure.py` builder function that reads more than one input file (e.g.
  `build_config_mean_collapse_diagnostic`'s coarse/fine predictions parquets and coarse/fine
  `metrics.json` files)
- **WHEN** the run-metadata sidecar is written
- **THEN** every input file's own SHA256 is recorded under a distinct key (e.g.
  `fine_predictions_sha256`, `fine_metrics_sha256`) — the generic `capture_surrogate_run_metadata`
  helper's single `inputs.hash` field records only the one file passed as its primary `inputs_file`,
  so each additional input must be hashed and recorded separately for full provenance

### Requirement: Optional visualization dependencies are lazily imported

`scipy`, `scikit-image`, and `imageio_ffmpeg` SHALL be imported inside the specific functions that
need them, not at module import time, **in every `visualization/` module that uses one of
them** — `wing_render.py` (`scipy.spatial.ConvexHull`), `flow_video.py`
(`scipy`/`skimage`/`imageio_ffmpeg`), and `kinematics_video.py` (`imageio_ffmpeg`) — following the
existing `stress_integral.extract_eulerian_box` lazy-`yt`-import convention.

#### Scenario: every visualization module is importable without the `viz` dependency group installed

- **GIVEN** a Python environment with the repo's base dependencies installed but not the `viz`
  group (no `scipy`/`scikit-image`/`imageio-ffmpeg`)
- **WHEN** `import mosquito_cfd.visualization.wing_render`,
  `import mosquito_cfd.visualization.flow_video`, and
  `import mosquito_cfd.visualization.kinematics_video` are each executed
- **THEN** every import succeeds; only calling a function that actually needs one of those packages
  (`wing_outline`, any `flow_video` rendering function, `kinematics_video`'s video-writing function)
  raises `ImportError`

### Requirement: Generated video files are excluded from version control by filename convention; figure scripts ship one committed reference PNG

`.gitignore` SHALL exclude generated video output by **filename convention**
(`*_flow_*.mp4`, `*_kinematics_preview.mp4`), not by directory, since `--out-dir` is caller-supplied
and arbitrary. Each figure-producing script (`make_comparison_figure.py`,
`make_config_mean_collapse_diagnostic.py`) SHALL have at least one committed reference PNG,
generated from that script's own small synthetic test fixture (not real corpus data, and not a
curated illustrative example — see the `comparison_figure.py` numerical-correctness requirement
below), serving as validation evidence that the script's plotting code runs and produces an
image, committed under `tests/fixtures/comparison_figure/` rather than `docs/` precisely because
it is fixture-derived, not documentation.

#### Scenario: a freshly rendered video does not appear in `git status` regardless of output directory

- **GIVEN** a clean working tree
- **WHEN** `make_flow_video.py --out-dir <any-caller-chosen-directory>` writes
  `s45_f115_p60_flow_wake-slice.mp4`
- **THEN** `git status` does not list that file as untracked, because its filename matches the
  `*_flow_*.mp4` `.gitignore` pattern independent of which directory it was written to

#### Scenario: the coarse-vs-fine comparison figure has a committed reference output

- **GIVEN** the repository at HEAD
- **WHEN** `tests/fixtures/comparison_figure/` is inspected
- **THEN** a `coarse_vs_fine_comparison.png` produced by `make_comparison_figure.py` against its
  synthetic test fixture is present and tracked by git

#### Scenario: the config-mean-collapse diagnostic figure has a committed reference output

- **GIVEN** the repository at HEAD
- **WHEN** `tests/fixtures/comparison_figure/` is inspected
- **THEN** a `diagnostic_config_mean_collapse.png` produced by
  `make_config_mean_collapse_diagnostic.py` against its synthetic test fixture is present and
  tracked by git

### Requirement: Wing rotation is computed exclusively via the canonical `wing_kinematics` module

No module under `visualization/` SHALL define its own `rotation_matrix` or `euler_angles`
function. All wing-pose transforms SHALL import `rotation_matrix`/`euler_angles` from
`mosquito_cfd.benchmarks.wing_kinematics`.

#### Scenario: a duplicate rotation implementation is absent from the new code

- **GIVEN** the `src/mosquito_cfd/visualization/` package at HEAD
- **WHEN** its modules are searched for a locally defined `rotation_matrix` or `euler_angles`
  function
- **THEN** none is found; all wing-pose rotations trace to a single import of
  `mosquito_cfd.benchmarks.wing_kinematics`

### Requirement: `flow_video.py` validates its field-mode argument against a closed set

`flow_video.py`'s field-mode parameter SHALL be restricted to exactly `wake-slice`, `combined-3d`,
`lev-3d`, and `zvelocity-3d`. An unrecognized value SHALL raise a `ValueError` naming the invalid
value and listing the valid options, before any plotfile I/O.

#### Scenario: an unrecognized field mode fails fast with a clear message

- **GIVEN** a call to the `flow_video` builder with `field_mode="isosurface"` (not a valid mode)
- **WHEN** the function is invoked
- **THEN** it raises `ValueError` mentioning `"isosurface"` and listing `wake-slice`, `combined-3d`,
  `lev-3d`, `zvelocity-3d` as the valid options, without opening the plotfile directory

### Requirement: Isosurface threshold and colorbar ranges are documented, overridable CLI parameters, never auto-computed

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

### Requirement: Wing marker transforms rotate about the hinge, not the origin

`wing_render.transform_markers` SHALL rotate reference-frame markers about the supplied `hinge`
point (translate to hinge-relative coordinates, apply the rotation, translate back), not about the
coordinate origin. This is the shared primitive both `flow_video.py` and `kinematics_video.py`
depend on for correct wing pose at any phase.

#### Scenario: a 90-degree stroke rotation matches a hand-computed rotation about the hinge

- **GIVEN** a single marker at a known reference position, a hinge point away from the origin, and
  `phi=90°, alpha=0°, theta=0°`
- **WHEN** `transform_markers` is called
- **THEN** the returned position equals the marker's position after rotating 90° about the **hinge**
  point specifically — not a rotation about the origin, which would give a different result for any
  hinge away from `(0, 0, 0)`

#### Scenario: degenerate or malformed marker input is rejected before any transform is attempted

- **GIVEN** any of: an empty markers array, a markers array shaped `(N, 2)` instead of `(N, 3)`, or a
  `hinge` containing a NaN/inf component
- **WHEN** `transform_markers` or `wing_outline` is called
- **THEN** a `ValueError` naming the specific problem (empty input, wrong column count, or
  non-finite value) is raised before any rotation or convex-hull computation is attempted — no
  garbage transform is silently returned

### Requirement: Force-surrogate comparison figures reproduce their source data exactly, not an approximation

`comparison_figure.build_coarse_vs_fine_comparison` SHALL compute per-config mean force values via
the same `groupby(...).mean()` aggregation the figure visualizes, and
`build_config_mean_collapse_diagnostic` SHALL report `config_resolved` R² values read verbatim from
the source `metrics.json`, never re-derived or approximated. This guards specifically against
conflating `metrics.json`'s `config_resolved` block (config-mean R²) with its separate `per_target`
block (RMSE) — a documented gotcha in the tooling this capability replaces (`evidence_figure.py`'s
`_config_mean_r2` vs `_per_target_rmse` split reads two different blocks; treating them as one view
of the same number is a real, previously-made mistake this requirement exists to prevent).

#### Scenario: per-config mean markers match a direct pandas groupby on the same data

- **GIVEN** a small synthetic `holdout_predictions.parquet` fixture with 2 configs, several rows each
- **WHEN** `build_coarse_vs_fine_comparison` computes the per-config mean marker positions
- **THEN** each position equals `df.groupby("config_name")[["CF_x_true", "CF_x_pred"]].mean()`
  computed directly on the same fixture, to floating-point equality

#### Scenario: the diagnostic's reported R² is not silently swapped for the RMSE block

- **GIVEN** a synthetic `metrics.json` fixture with distinct, known values in `config_resolved` and
  `per_target`
- **WHEN** `build_config_mean_collapse_diagnostic` reports its R² figure
- **THEN** the reported value matches the fixture's `config_resolved` block exactly, not any value
  from `per_target`

#### Scenario: a legitimate JSON `null` config-mean R² passes through unchanged, not as an error or a coerced number

- **GIVEN** a `metrics.json` fixture whose `config_resolved.<coefficient>.config_mean_r2` is JSON
  `null` (the value `train.py`'s `compute_config_resolved` legitimately writes when between-config
  variance is near-zero)
- **WHEN** `build_config_mean_collapse_diagnostic` reports that grid's R² value
- **THEN** the returned value is Python `None`, not `0.0`, `NaN`, or a raised exception

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

