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
  --field-mode wake-slice --plotfile-dir <plt-dir> --out-dir <out> --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex>
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

- **GIVEN** any `comparison_figure.py` figure builder, which reads eight input files under the roles
  `coarse_dataset`, `coarse_predictions`, `coarse_metrics`, `coarse_surrogate_run_metadata`,
  `fine_dataset`, `fine_predictions`, `fine_metrics` and `fine_surrogate_run_metadata`
- **WHEN** the run-metadata sidecar is written
- **THEN** each role in `input_files` records that file's own path and SHA256 — the generic
  `capture_surrogate_run_metadata` helper's single `inputs.hash` field records only the one file
  passed as its primary `inputs_file`, so each additional input must be hashed and recorded
  separately for full provenance

### Requirement: Optional visualization dependencies are lazily imported

`scipy`, `scikit-image`, and `imageio_ffmpeg` SHALL be imported inside the specific functions that
need them, not at module import time, **in every `visualization/` module that uses one of
them** — `wing_render.py` (`scipy.spatial.ConvexHull`), `flow_video.py`
(`scipy`/`skimage`/`imageio_ffmpeg`), and `kinematics_video.py` (`imageio_ffmpeg`) — following the
existing lazy-`yt`-import convention, which is implemented in
`mosquito_cfd.field_surrogate.snapshot.read_field_snapshot` and preserved through its
`stress_integral.extract_eulerian_box` wrapper.

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
and arbitrary. Each figure that `scripts/make_coarse_vs_fine_figures.py` renders (`skill_ranges`,
`error_histograms`, `cycle_mean_r2_diagnostic`) SHALL have exactly one committed reference PNG,
rendered from the committed coarse and fine force-surrogate artifacts (real corpus data, not a
synthetic fixture) and committed with its `<name>_metrics.json` and `<name>_run_metadata.json`
under `examples/prelim_sweep_fine/figures/coarse_vs_fine/`. No synthetic-fixture render of these
figures SHALL be committed: the unit tests build their own synthetic inputs in a temporary
directory, and a rendered toy fixture is not documentation.

#### Scenario: a freshly rendered video does not appear in `git status` regardless of output directory

- **GIVEN** a clean working tree
- **WHEN** `make_flow_video.py --out-dir <any-caller-chosen-directory>` writes
  `s45_f115_p60_flow_wake-slice.mp4`
- **THEN** `git status` does not list that file as untracked, because its filename matches the
  `*_flow_*.mp4` `.gitignore` pattern independent of which directory it was written to

#### Scenario: each coarse-vs-fine figure has one committed real-data reference output

- **GIVEN** the repository at HEAD
- **WHEN** `examples/prelim_sweep_fine/figures/coarse_vs_fine/` is inspected
- **THEN** for each of `skill_ranges`, `error_histograms` and `cycle_mean_r2_diagnostic`, the PNG,
  `<name>_metrics.json` and `<name>_run_metadata.json` each pass `git ls-files --error-unmatch`,
  the PNG begins with the PNG file signature, and `tests/fixtures/comparison_figure/` does not exist

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

Every quantity a `comparison_figure.py` figure plots that `metrics.json` also records SHALL either be
read verbatim from `metrics.json` or be recomputed from the committed predictions and dataset and
required to equal the recorded value before anything is written; the remaining quantities (waveform
RMS, cycle-mean spread, histogram counts) SHALL be computed from the committed predictions and
dataset by the formulas stated in this capability. The builder SHALL raise `ValueError` naming the
corpus, target and quantity when a check fails, and SHALL write no file in that case.

**Tolerance form T.** Wherever this capability compares a recomputed `a` with a recorded `b` "in
form T", it SHALL require `|a − b| ≤ 1e-12·max(1, |b|)`.

The specific checks are:

- `skill_ranges` SHALL read each seed's skill verbatim from `seed_sweep.runs[i].per_target.<c>.skill`.
- `error_histograms` SHALL rebuild the phase-only baseline with `train.build_phase_only_baseline`.
  - The returned definition SHALL equal `phase_baseline_skill.phase_baseline`, with lists compared
    as lists.
  - The recomputed baseline RMSE SHALL equal `phase_baseline_rmse` to `rel=1e-9, abs=0`.
  - The recomputed `1 − skill` SHALL equal `1 − phase_baseline_skill.per_target.<c>.skill` to
    `rel=1e-9, abs=0`.
- `cycle_mean_r2_diagnostic` SHALL recompute the primary seed's cycle-mean R² with the arithmetic of
  `train.compute_config_resolved`. It is recomputed, not read, and required to equal the recorded
  value. The recomputed `1 − R²` SHALL equal the recorded `1 − R²` in form T, both for
  `config_resolved.<c>.config_mean_r2` and for `seed_sweep.runs[0].per_target.<c>.config_mean_r2`.

This guards against conflating `metrics.json` blocks (`config_resolved`, `per_target`,
`phase_baseline_skill`, `seed_sweep`) — a documented, previously made mistake in the tooling this
capability replaces — and against a dataset or baseline definition that no longer matches the
surrogate it is drawn with.

#### Scenario: the skill-range values are the seed sweep, verbatim

- **GIVEN** synthetic coarse and fine corpora whose `metrics.json` is assembled exactly as the
  trainer assembles it, with five distinct per-seed skills per target
- **WHEN** `skill_ranges` is built
- **THEN** its sidecar's per-seed values equal `seed_sweep.runs[i].per_target.<c>.skill` in seed
  order; none equals any `r2`, `rmse`, `config_mean_r2`, `phase_baseline_r2` or
  `phase_baseline_rmse` value; and the primary seed's value equals
  `phase_baseline_skill.per_target.<c>.skill`

#### Scenario: a baseline that does not reproduce metrics.json is refused

- **GIVEN** a synthetic corpus whose `metrics.json` `phase_baseline_rmse` for `CF_x` is multiplied by
  `1 + 1e-8`, and separately one multiplied by `1 + 1e-11`
- **WHEN** `error_histograms` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and "phase-only baseline" and
  writes no file; the second succeeds

#### Scenario: a recorded skill that does not reproduce is refused

- **GIVEN** a synthetic corpus whose recorded `CF_x` skill is set to `1 − (1 − skill)·(1 + 1e-8)`,
  and separately to `1 − (1 − skill)·(1 + 1e-11)`, in `runs[0]` (before `summarize_seed_sweep`, so
  `range` stays consistent) and in `phase_baseline_skill` together
- **WHEN** `error_histograms` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and `skill`; the second succeeds

#### Scenario: a baseline definition that differs is refused

- **GIVEN** a synthetic corpus whose `phase_baseline.reference_configs` lists the same
  configurations in a different order
- **WHEN** `error_histograms` is built
- **THEN** it raises `ValueError` naming the corpus and `reference_configs`, and no file is written

#### Scenario: the diagnostic's R² is recomputed, matches, and is not swapped for another block

- **GIVEN** a synthetic corpus whose six holdout configurations each have an even number of rows and
  constant true values 1, 2, 3, 4, 5, 6, with primary-seed predictions offset per configuration by
  +1, −1, +1, −1, +1, −1 plus a ±0.5 alternation within each configuration
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the recorded primary-seed `config_mean_r2` equals the fixture's `config_resolved` value
  and `23/35` in form T (on `1 − R²`); the recorded σ equals `sqrt(35/12)` and ε equals `1` to
  `rel=1e-12, abs=0`; and the recorded value equals no `per_target` or `phase_baseline_skill` value

#### Scenario: a recorded R² that disagrees with the recomputation is refused

- **GIVEN** the previous fixture (R² = 23/35) with `config_resolved.CF_x.config_mean_r2` multiplied
  by `1 + 1e-10`, and separately by `1 + 1e-14`
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the first raises `ValueError` naming the corpus, `CF_x` and `config_mean_r2` and writes
  no file; the second succeeds

#### Scenario: a null config-mean R² passes through as null, never as a number

- **GIVEN** a synthetic corpus whose six holdout configurations have true values alternating
  `0.5 ± 1` with an even number of rows each (so the cycle means are bitwise equal, `_r2` returns its
  sentinel, and `config_resolved` and every seed's `config_mean_r2` are JSON `null`), and whose
  training configurations' values differ from that alternation (so the skill stays finite)
- **WHEN** `cycle_mean_r2_diagnostic` is built
- **THEN** the recorded R² and every derived error for that target are JSON `null` (not `0`, not
  `NaN`); σ is recorded as computed, here exactly `0.0`; the sidecar's drawn state labels the target
  `n/a`; and no exception or warning is raised

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

### Requirement: `flow_video`'s near-field box margin is validated before any I/O

`build_flow_video` SHALL accept as `box_margin` any real number — an `int`, `float`,
`fractions.Fraction`, or numpy integer or floating scalar (`numbers.Real`), other than a `bool`,
`np.bool_` or `np.timedelta64` — that converts to a finite `float` strictly greater than zero, and
SHALL use that `float` as the margin. It SHALL reject every other value — including a `bool`, a
string, a `decimal.Decimal`, a `np.timedelta64` (a duration, not a length, although numpy registers
it as `numbers.Real`), `NaN`, `±inf`, zero, a negative number, an `int` too large to convert to a
`float`, and a `numbers.Real` whose conversion to `float` raises — with a `ValueError` naming
`box_margin` and its value (a numpy number or bool scalar shown as its plain Python value; a numpy
datetime or timedelta keeps numpy's repr), before any plotfile I/O or `Figure` creation, in every
field mode. A non-positive margin turns the `center ± box_margin` near-field request into an
inverted or zero-width region; without this check the caller would see the reader's `lo > hi` error,
naming values it never passed.

#### Scenario: an invalid box margin fails fast in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `-1`, `-1.0`, `0`, `0.0`, `nan`,
  `inf`, `-inf`, `np.float64(-1.0)`, `True`, `np.bool_(True)`, `"3"`, `Decimal("3")`, `10**400`,
  `-(10**400)`, `np.timedelta64(1, "s")`, `np.timedelta64(5, "ns")`, `np.datetime64("2020-01-01")`,
  or a registered `numbers.Real` whose `__float__` raises `TypeError` or `ValueError`, in each of the
  four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** it raises `ValueError` whose message is the `box_margin` validator's own and ends with the
  bad value, plotfile discovery was never reached, and no `Figure` was created

#### Scenario: a valid box margin passes validation in every mode

- **GIVEN** a call to `build_flow_video` with `box_margin` equal to `5e-324`, `1e-9`, `0.5`, `2`,
  `np.int64(2)`, `np.float32(0.5)` or `Fraction(1, 2)`, in each of the four field modes
- **WHEN** the function is invoked with plotfile discovery replaced by a function that fails the test
  if called
- **THEN** validation passes and the call reaches plotfile discovery (the replacement's failure is
  raised, not a `ValueError`)

#### Scenario: the lev-3d near-field box is built from the validated float

- **GIVEN** a `lev-3d` call to `build_flow_video` with `box_margin` equal to `Fraction(5, 2)` or
  `np.float32(2.5)`, and the near-field box reader replaced by a recorder
- **WHEN** the function is invoked
- **THEN** every requested box has `lo == center - 2.5` and `hi == center + 2.5` exactly, as float64
  arrays

### Requirement: `flow_video` discovers plotfile frames with the corpus's own listing

`flow_video` SHALL discover the frames of a run with
`mosquito_cfd.field_surrogate.corpus.scan_plotfiles`, the same object `FieldCorpus` uses, so that the
two agree on which plotfiles exist.

- **Names.** A frame directory name SHALL be `plt` followed by one or more ASCII digits, of any
  width. AMReX writes `plt{step:05d}`, which has six digits from step 100000 on, and the previous
  `plt?????` glob silently dropped those frames and every later one (#144).
- **Order.** Frames SHALL be ordered by their integer step, not by name.
- **Non-directories.** Entries that are not directories SHALL be skipped.
- **Duplicates.** Two directories that parse to the same step SHALL raise the corpus's
  `ValueError` naming both, rather than rendering the same instant twice.
- **Missing or empty directory.** A `plotfile_dir` that does not exist or is not a directory, and
  a directory with no plotfile, SHALL each raise `ValueError` naming the directory, as before. The
  message SHALL say which: "does not exist" only for a missing path, "is not a directory" for one
  that exists, and the no-plotfile message SHALL describe the accepted name as `plt<digits>`.

`build_flow_video`'s documentation and the `make_flow_video.py --plotfile-dir` help SHALL describe
the accepted names as `plt<digits>` of any width.

#### Scenario: Frames at step 100000 and beyond are rendered, in step order

- **GIVEN** a plotfile directory holding `plt99999`, `plt100000` and `plt00100`, a regular file
  named `plt00200`, a directory `plt00300.old`, and a directory `plt١٠٠` (non-ASCII digits)
- **WHEN** `flow_video`'s frame discovery runs on it
- **THEN** it returns exactly the paths for `plt00100`, `plt99999` and `plt100000`, in that order,
  which differs from lexical order (`plt100000` sorts before `plt99999` as a string); and
  `flow_video`'s `scan_plotfiles` is the same object as `corpus.scan_plotfiles`

#### Scenario: Duplicate, missing and empty directories are reported

- **GIVEN** a directory holding `plt100` and `plt00100`; a path that does not exist; a regular file;
  and an empty directory
- **WHEN** frame discovery runs on each
- **THEN** the first raises `ValueError` naming `plt00100` and `plt100`, and each of the others
  raises exactly `ValueError` naming the path, the empty-directory message naming `plt<digits>`

### Requirement: Comparison figures validate their inputs before writing anything

Each `comparison_figure.py` builder SHALL take the repository root as `root: Path` (the driver
passes `Path.cwd()`) and SHALL resolve the eight inputs as `root / <corpus dir> / ...`.

Before anything is written, it SHALL apply the guards below **in this order**: guard 1 once, then
guards 2–10 to the coarse corpus, then guards 2–10 to the fine corpus, then guard 11. On the first
that fails it SHALL raise `ValueError` naming the corpus, the role and the defect, with no file
written and no matplotlib figure left open. A test of a defect SHALL assert the message of the first
guard the defect trips.

1. The digest is validated, before any file is touched.
2. Each of the eight files exists.
3. Each JSON input is a JSON object without a `NaN` or `Infinity` literal.
4. The required columns are present: `config_name`, `time`, `phase`, `wingbeat`, `CF_c_true` and
   `CF_c_pred` in the predictions; `config_name`, `time`, `phase`, `wingbeat`, `split` and each
   target in the dataset.
5. The dataset sha256 equals the surrogate's `inputs.hash`.
6. The predictions are non-empty and have at least two configurations. Neither frame repeats a
   `(config_name, time)` key.
7. Every coefficient is finite.
8. **Beat structure.** Every dataset configuration has wingbeats exactly `0..N−1`, with the same N
   for all configurations. The prediction rows have wingbeats exactly
   `CONVERGED_MIN_WINGBEAT..N−1`, where `CONVERGED_MIN_WINGBEAT` equals
   `phase_baseline.converged_min_wingbeat`.
9. The predictions' `CF_c_true` equal the dataset's `split == "holdout"` rows with
   `wingbeat >= CONVERGED_MIN_WINGBEAT`, matched on `(config_name, time)` exactly.
10. **Seed sweep.**
    - Each `seed_sweep.range.<c>.<stat>` equals the NaN-aware min and max of its runs.
    - `runs[0].seed` equals `primary_seed`.
    - `runs[0].per_target.<c>.skill` equals `phase_baseline_skill.per_target.<c>.skill`, with a null
      equal only to a null.
    - A null `skill` or `config_mean_r2` is either null for every seed of that corpus and target, or
      for none of them.
    - No `config_mean_r2` exceeds 1.
11. **Pairing.** The coarse and fine corpora have equal dataset configuration sets, equal holdout
    configuration sets, equal seed lists, equal per-seed `val_configs` (present in both) and equal
    N.

Within those guards the loader SHALL also refuse:

- in guard 3, a non-finite number anywhere in a JSON input, including a literal that overflows to
  infinity (`1e999`) and an integer too large for a float;
- in guard 4, a `config_name` that is not a non-null string, a `wingbeat` that is not an integer
  column, and a `phase` or coefficient column that is not numeric (booleans included);
- in guard 9, a prediction row whose `phase` or `wingbeat` differs from the matched dataset row;
- in guard 10, a seed or `primary_seed` that is not an integer, a recorded statistic that is neither
  a number nor null, and a `seeds` list that differs from the runs' seeds.

#### Scenario: each defect is refused before any output

- **GIVEN** a valid synthetic corpus pair and, one at a time, each of these defects:
  - each of the eight input files removed, in turn;
  - a JSON input that is a list;
  - `metrics.json` containing a `NaN` literal;
  - each required column dropped;
  - an empty predictions frame;
  - one configuration only;
  - a repeated `(config_name, time)` key;
  - `+inf`, `−inf` and `NaN` in a `_true` and in a `_pred` column;
  - the coarse and the fine dataset sha256 each changed;
  - a dataset whose wingbeats are `{0, 2}`, and one configuration with an extra beat, both built
    before the dataset is hashed, so its hash still matches;
  - `phase_baseline.converged_min_wingbeat` set to `0`, and separately to the float `1.0`;
  - a prediction row with `wingbeat == 0`;
  - a `CF_x_true` changed by one ulp;
  - the fine predictions copied into the coarse directory;
  - a `range` off by one ulp at `min` and at `max`;
  - `runs[0].seed` differing from `primary_seed`;
  - `phase_baseline_skill.per_target.CF_x.skill` changed by one ulp, with `runs` and `range`
    unchanged;
  - one non-primary seed's skill set to `null` while the others are finite, placed before
    `summarize_seed_sweep`;
  - a non-primary `config_mean_r2` of `1.5`, and separately of `nextafter(1, 2)`, both placed
    before `summarize_seed_sweep`;
  - differing holdout configuration sets, seed lists or `val_configs`;
  - a training configuration dropped from, and separately one added to, the fine dataset, with
    the holdout sets unchanged;
  - `val_configs` missing from both corpora;
  - a coarse corpus with wingbeats `{0, 1}` beside a fine one with `{0, 1, 2}`
- **WHEN** each of the three builders is called
- **THEN** each raises `ValueError` whose message names the corpus and the first guard tripped (the
  file or role, the column, the hash pair, the quantity and seed), the output directory has no new
  file, and `matplotlib.pyplot.get_fignums()` is unchanged

#### Scenario: the digest is checked before any file

- **GIVEN** a mutable digest and corpus directories that do not exist
- **WHEN** each builder is called
- **THEN** the raised `ValueError` is the digest error, not a missing-file error

### Requirement: The coarse-vs-fine skill-range figure follows the pre-registered overlap rule

`comparison_figure.py` SHALL build `skill_ranges`. For each of the six targets it draws a coarse row
and a fine row on one shared skill axis. Each row shows:

- every per-seed skill over that corpus's phase-only baseline as a marker, the primary seed's
  marker distinct;
- the min–max of the per-seed skills as a bar.

A row whose skills are null (all of them, by the all-or-none guard) SHALL be labelled `n/a` with no
bar.

The metrics sidecar SHALL record:

- per target and corpus: the seeds and per-seed values, the min and max, the overlap cell from
  `ranges_overlap`, the number of markers drawn, the bar `[lo, hi]` or `null`, and the `n/a` label;
- the notes (`{target: text}`);
- the caption string.

`ranges_overlap` SHALL return `yes` exactly when `max(lo_coarse, lo_fine) <= min(hi_coarse, hi_fine)`
on the raw values, `no` otherwise, and `n/a` when either range is null.

A target whose cell is `no` SHALL carry the in-axes note
`ranges disjoint at <n> seeds each; see README before reading this as a grid effect`, with `<n>`
read from the data. No note or caption SHALL match `_readme_guards._COMPARATIVE`,
`_readme_guards._FINE_COMPARATIVE` or `_readme_guards._BANNED`.

#### Scenario: overlap agrees with the README guard

- **GIVEN** the committed coarse and fine `metrics.json`, and the hand-written pairs
  `[0.97, 0.98]`/`[0.98, 0.99]` (touching), `[0.97, 0.98]`/`[nextafter(0.98, 1), 0.99]` (one ulp
  apart), an overlapping pair, and a pair with a null range
- **WHEN** `ranges_overlap` and `_readme_guards.overlap_cell` are each applied
- **THEN** they return the same cell for every pair: `yes`, `no`, `yes` and `n/a` respectively, and
  on the committed data `no` for `CF_y` only

#### Scenario: only disjoint targets are annotated, without direction

- **GIVEN** synthetic metrics in which exactly `CF_y` has disjoint ranges, and separately metrics in
  which every range overlaps
- **WHEN** `skill_ranges` is built
- **THEN** the first sidecar's notes hold exactly one entry, for `CF_y`, and the second holds none;
  no note or caption matches `_COMPARATIVE`, `_FINE_COMPARATIVE` or `_BANNED`

#### Scenario: a target whose skills are all null

- **GIVEN** a synthetic corpus in which one target has the same constant value in every
  configuration, holdout included, so the baseline equals the truth, its SSE is zero and every seed's
  skill is `null` by construction
- **WHEN** `skill_ranges` is built
- **THEN** that target records one `null` per seed, a `null` range, overlap `n/a`, zero markers, a `null`
  bar and the `n/a` label, and carries no note

### Requirement: The error-histogram figure compares the surrogate with the phase-only baseline within each grid

`comparison_figure.py` SHALL build `error_histograms`, with one row per corpus and one column per
target. Each panel SHALL show, on the same holdout rows:

- the primary seed's surrogate error (`pred − true`);
- the phase-only baseline's error.

Each is divided by that corpus's **recomputed** baseline RMSE (`z`), and drawn as a log-scale
density on the fixed edges `numpy.linspace(-3, 3, 601)`, with
`density = counts / (n_rows · numpy.diff(edges))`. Here `n_rows` includes out-of-range rows.

Values with `z < −3` or `z > 3` SHALL be counted as below or above range. A value exactly at ±3
falls in the end bin, as `numpy.histogram` places it. Non-zero out-of-range counts SHALL be printed
in the axes as `outside ±3: <below> / <above>`.

Each panel SHALL be annotated `seed <primary> skill <x> (<n> seeds: <lo> to <hi>)`, with `<x>` from
`seed_sweep.runs[0].per_target.<c>.skill` and the range from `seed_sweep.range.<c>.skill`, read
verbatim. A target whose recorded skill is null SHALL be refused, naming the target.

The sidecar SHALL record:

- per corpus and target:
  - the recomputed `rmse0` and `rmse_surrogate`, and `skill = 1 − (rmse_surrogate / rmse0)²`;
  - `skill_recorded` and its range, read verbatim;
  - both count arrays and both below/above counts;
  - `n_rows`;
- the edges, once;
- the caption string.

#### Scenario: the counts follow the bin convention

- **GIVEN** a pure `_bin_counts(z, edges)` helper and `z` values `[-3.5, -3.0, 0.0, 3.0, 3.5]`
- **WHEN** it is applied with `numpy.linspace(-3, 3, 601)`
- **THEN** below is 1, above is 1, `-3.0` is in the first bin, `3.0` is in the last bin, and the
  counts plus below plus above equal 5

#### Scenario: the histogram counts are the normalised errors

- **GIVEN** a synthetic corpus with known errors, including values outside ±3 baseline RMSEs
- **WHEN** `error_histograms` is built
- **THEN** each recorded count array equals `numpy.histogram` of the normalised errors on the
  recorded edges, below/above equal the out-of-range counts, and counts plus below plus above equal
  `n_rows`

#### Scenario: the recomputed skill is consistent with its two RMSEs

- **GIVEN** any corpus the builder accepts
- **WHEN** `error_histograms` is built
- **THEN** for every target `(rmse_surrogate / rmse0)²` equals the recorded recomputed `1 − skill`
  to `rel=1e-12, abs=0`, and `skill_recorded` equals `runs[0].per_target.<c>.skill` exactly

### Requirement: The cycle-mean R² diagnostic shows why the metric is ill-conditioned, across all seeds

`comparison_figure.py` SHALL build `cycle_mean_r2_diagnostic` with two panels per corpus.

**Definitions.** Cycle means SHALL be computed as `train.compute_config_resolved` computes them:
numpy boolean-mask means in `numpy.unique` order. σ is the population standard deviation
(`ddof=0`) of the true cycle means.

**Scales panel** (log axis), per target, showing:

- the waveform RMS (RMS of `CF_c_true` about its holdout mean);
- σ;
- each seed's cycle-mean RMS error `ε_s = σ·sqrt(1 − R²_s)`, from that seed's committed
  `config_mean_r2`.

A zero or null scale value SHALL be drawn as a marker at the axis floor labelled `0` or `n/a`, never
as data on the log axis.

**Seeds panel** (symlog axis, linear within ±1): each seed's `config_mean_r2`, with 0 and 1 marked.

**Check.** When the recorded primary R² is non-null, the builder SHALL require the measured
primary-seed `ε²/σ²` to equal the recorded `1 − R²_primary` in form T.

**Sidecar.** It SHALL record every plotted value with its seed, the per-target drawn state (floor
markers and `n/a` labels) and the caption string. The figure SHALL NOT show one seed's value without
the others.

#### Scenario: every seed is plotted and the derived errors are exact

- **GIVEN** the 23/35 fixture with five seeds whose per-configuration offsets are 1, 3, 2, 0.5 and
  1.5 (so the second seed's R² is `−73/35`)
- **WHEN** the diagnostic is built
- **THEN** the sidecar holds five `ε_s`, each equal to `σ·sqrt(1 − R²_s)` to `rel=1e-12, abs=0`;
  the `−73/35` seed's `ε_s` equals 3 and is greater than σ; and the primary seed's measured `ε²/σ²`
  equals `1 − R²` in form T

#### Scenario: boundary values of R²

- **GIVEN** non-primary seeds whose `config_mean_r2` is `0.0`, `1.0` and `−1e6`, placed before
  `summarize_seed_sweep` so `range` stays consistent
- **WHEN** the diagnostic is built
- **THEN** `0.0` gives `ε_s == σ` exactly; `1.0` gives `ε_s == 0.0`, recorded as a floor marker
  labelled `0`; and `−1e6` is recorded and drawn, with no warning

#### Scenario: the scales are the stated statistics

- **GIVEN** a target whose true values alternate `+1`, `−1` within every configuration, each with an
  even number of rows
- **WHEN** the diagnostic is built
- **THEN** the recorded waveform RMS is `1.0` and σ is `0.0`

### Requirement: Comparison-figure captions and labels state the scope and never compare the grids

Each figure's caption SHALL be built by a pure `build_<figure>_caption` function.

**Every caption SHALL state:**

- `shipped surrogate (surrogate/)`;
- `lab-frame components of the IB force and moment on the wing; moments about the hinge`;
- the beat label:
  - `second wingbeat of 2-beat runs` when N = 2, otherwise `wingbeats 2–N of N-beat runs`;
  - `the corpus is to be regenerated with longer runs` exactly when N = 2.

**`skill_ranges` and `error_histograms` SHALL also state** `OWN_BASELINE_PHRASE`
(`each grid is scored against its own corpus's phase-only baseline`).

**`cycle_mean_r2_diagnostic` SHALL state instead**
`cycle-mean R² is computed on each grid's own <k> holdout configurations`, with `<k>` read from the
data.

**Figure-specific content:**

- **`skill_ranges` and `cycle_mean_r2_diagnostic`:** `<n> seeds`, and
  `observed spread, not a confidence interval`.
- **`skill_ranges`:**
  - `RULE_SENTENCE.format(n=<n>)`, where `RULE_SENTENCE` is
    `a target counts as moved only if its two {n}-seed ranges are disjoint (computed on the
    unrounded values; touching ranges count as overlapping)`;
  - `not a measurement of the effect of grid resolution on its own`.
- **`error_histograms`:**
  - `seed <primary>`;
  - `skill = 1 − (RMSE / RMSE₀)²`;
  - `not compared across the two rows`;
  - `consecutive timesteps of <k> configurations, not independent samples`.
- **`cycle_mean_r2_diagnostic`:** `a diagnostic of the metric, not a comparison of the grids`.

`<n>`, `<k>` and `<primary>` SHALL be read from the data, never hard-coded.

**Target labels:**

| target | label |
|---|---|
| `CF_x` | `CF_x (lab x force)` |
| `CF_y` | `CF_y (lab y force)` |
| `CF_z` | `CF_z (lab vertical force)` |
| `CF_mx` | `CF_mx (lab M_x about the hinge)` |
| `CF_my` | `CF_my (lab M_y about the hinge)` |
| `CF_mz` | `CF_mz (lab M_z about the hinge)` |

**Forbidden.** No caption, note or label SHALL match
`(?i)\b(?:(?:chord|span|drag|pitch|roll)\w*|normal)\b`, `_readme_guards._COMPARATIVE` or
`_readme_guards._FINE_COMPARATIVE`.

#### Scenario: the beat label follows the data

- **GIVEN** synthetic corpora with dataset wingbeats `{0, 1}` and prediction wingbeats `{1}`, and
  separately `{0, 1, 2, 3}` and `{1, 2, 3}`
- **WHEN** each figure's caption is built
- **THEN** the first contains `second wingbeat of 2-beat runs` and `the corpus is to be regenerated
  with longer runs`; the second contains `wingbeats 2–4 of 4-beat runs` and no regeneration phrase

#### Scenario: required and forbidden wording

- **GIVEN** each figure built on a synthetic corpus pair with a primary seed of 42, three seeds and
  six holdout configurations
- **WHEN** its caption, notes and labels are inspected
- **THEN** every required phrase is present with `seed 42`, `3 seeds` and `6` where the data supply
  them (never a hard-coded `1234` or `5`); the diagnostic caption does not contain
  `OWN_BASELINE_PHRASE`; and nothing matches a forbidden pattern

#### Scenario: the forbidden-word pattern matches whole framings only

- **GIVEN** the strings `normalised`, `timespan`, `wing-normal`, `spanwise`, `chordwise`, `spans` and
  `rolling`
- **WHEN** the forbidden-word pattern is applied
- **THEN** `normalised` and `timespan` do not match, and every other string matches

#### Scenario: the README carries the shared constants

- **GIVEN** the fine README's "Coarse vs fine" section with whitespace runs collapsed to one space
- **WHEN** it is searched case-insensitively
- **THEN** it contains `OWN_BASELINE_PHRASE` and `RULE_SENTENCE.format(n=5)`, where 5 is the
  committed seed count

### Requirement: Committed comparison figures stay current with their inputs and renderer

**Run-metadata contents.** Each `*_run_metadata.json` from `comparison_figure.py` SHALL record:

- `input_files`: role → `{path, sha256}`, for the eight roles;
- `inputs.file` and `inputs.hash` for `coarse_metrics`;
- `corpus_docker_images`: `{coarse, fine}`, from the two `surrogate/run_metadata.json`;
- `library_versions`: python, numpy, pandas, pyarrow and matplotlib;
- `renderer_sources`: the sha256 of the LF-normalised bytes of `comparison_figure.py` and
  `scripts/make_coarse_vs_fine_figures.py`, read from those files' own locations (not from `root`)
  and keyed by those fixed names, with `null` for a file that is absent (an installed package without
  the `scripts/` directory);
- `figure`;
- `png_sha256`: the sha256 of the PNG bytes written.

**Rendering.** Each figure SHALL be drawn and saved under matplotlib's `default` style, so a
caller's rcParams or a local `matplotlibrc`, which `git.dirty` cannot see, does not change the PNG.

**Portable paths.** Every recorded path SHALL be relative to `root`, written with forward slashes,
with no drive letter, no leading `/` and no `..`. A pure `_portable_path(path, root)` SHALL produce
it, resolving a relative path against `root` first, and SHALL refuse a path outside `root`.

**The checker.** A pure test helper `check_committed_figure(root, figure)` SHALL check the input
hashes before any recomputation. It SHALL re-raise any `ValueError` from the library as
`AssertionError` naming the figure and the role, and SHALL raise `AssertionError` naming the figure
and the failing field or role. It SHALL require:

- every `input_files` path to resolve under `root` to a file whose sha256 equals the recorded one,
  and `inputs.hash` to equal the `coarse_metrics` hash;
- the committed `<figure>_metrics.json` to equal the library's `compute_<figure>_metrics` on the
  committed inputs, at these tolerances:
  - exactly: values read verbatim, counts, edges, captions, notes and drawn states;
  - `rel=1e-12, abs=0`: every other float (σ, `ε_s`, waveform RMS, `rmse0`, `rmse_surrogate`, the
    recomputed `skill`), with exact zeros compared exactly;
- `renderer_sources` to equal the current files;
- `corpus_docker_images` to equal the two surrogate records;
- `docker_image` to equal `examples/prelim_sweep_fine/run_metadata.json`'s;
- the five `library_versions` keys to be non-null strings (not compared with the running
  environment);
- `git.commit` to be 40 hex characters and `git.dirty` to be false;
- `figure` to equal the name;
- the committed `<figure>.png` to have the recorded `png_sha256`.

**The CI test.** A CI test SHALL apply the checker to each committed figure, and SHALL require one
`timestamp` across the three. It SHALL also check independent anchors computed in the test itself:

- histogram counts, via `numpy.histogram` with the baseline from `train.build_phase_only_baseline`;
- the per-seed values, against `metrics.json`;
- σ.

**Re-rendering.** A render or re-render SHALL be done into a scratch directory outside the
repository, with the nine files then
copied into place, so that `git diff HEAD` stays empty during every render and `git.dirty` stays
false.

#### Scenario: the check fails for each kind of staleness

- **GIVEN** a synthetic repository layout in a temporary directory, rendered by the real builder with
  injected git metadata, and copies of it with, one at a time:
  - the last digit of the fine `metrics.json`'s first `skill` value changed;
  - `git.dirty` set to true;
  - a backslash path;
  - an absolute path;
  - a per-seed `skill` in `skill_ranges_metrics.json` moved by `1e-10` relative;
  - an `ε_s` in `cycle_mean_r2_diagnostic_metrics.json` moved by `1e-10` relative;
  - the recorded hash of `comparison_figure.py` changed;
  - another figure's PNG copied over this figure's PNG
- **WHEN** `check_committed_figure` runs on each copy
- **THEN** the unmodified layout passes, and each copy fails with `AssertionError` naming the
  figure and the role or field (`fine_metrics`, `git.dirty`, `path`, the sidecar key,
  `renderer_sources`, `png_sha256`)

#### Scenario: local matplotlib settings do not change the PNG

- **GIVEN** a valid synthetic corpus pair
- **WHEN** `skill_ranges` is rendered once plainly and once inside a `matplotlib.rc_context` that
  changes `lines.markersize`, `savefig.facecolor` and `font.size`
- **THEN** the two PNGs are byte-identical, and each run metadata's `png_sha256` is its PNG's sha256

#### Scenario: recorded paths are portable on every OS

- **GIVEN** `PureWindowsPath("C:/repo/examples/prelim_sweep/dataset.parquet")` with root
  `PureWindowsPath("C:/repo")`, the same as a `PurePosixPath`, the relative path
  `examples/prelim_sweep` with an absolute root, and a path outside the root
- **WHEN** `_portable_path` is applied
- **THEN** the first three give `examples/prelim_sweep/...` paths with forward slashes and the
  fourth is refused

#### Scenario: a dataset that is not the surrogate's training data is refused

- **GIVEN** a corpus directory whose `dataset.parquet` sha256 differs from its
  `surrogate/run_metadata.json` `inputs.hash`
- **WHEN** any figure is built
- **THEN** it raises `ValueError` naming the corpus and both hashes, and no file is written

### Requirement: Coarse-vs-fine figures are rendered one per invocation by a single driver

`scripts/make_coarse_vs_fine_figures.py` SHALL take these flags, all required:

- `--figure`, which accepts exactly `skill_ranges`, `error_histograms` or `cycle_mean_r2_diagnostic`;
- `--coarse-dir`;
- `--fine-dir`;
- `--out-dir`;
- `--docker-digest`;
- `--timestamp`.

It SHALL render exactly the named figure, passing `root=Path.cwd()`, and SHALL be a thin wrapper
over the library builder.

#### Scenario: one figure per invocation

- **GIVEN** synthetic corpus directories and an empty output directory
- **WHEN** the driver runs with `--figure error_histograms`
- **THEN** the output directory holds exactly `error_histograms.png`,
  `error_histograms_metrics.json` and `error_histograms_run_metadata.json`

#### Scenario: a missing or unknown flag value is a usage error

- **GIVEN** the driver
- **WHEN** it runs with `--figure coarse_vs_fine_comparison`, or without any one of the six flags
- **THEN** argparse exits with status 2 and no file is written

