# Add visualization tooling (LEV/wake/kinematics videos + coarse-vs-fine figures)

## Why

Eight visualization scripts exist today only as one-off, uncommitted files in an external vault
(`C:\vaults\physics surrogate models\duncan-meeting-2026-08-11\{videos,figures}\`), built for a
single 2026-08-11 conference-pitch deck: four CFD-derived videos of the T3c-fine benchmark
(x-velocity wake slice, combined 3D wing+slice, LEV Q-criterion isosurface, z-velocity slice), one
pure-kinematics preview video, one field-capture wake video of a real held-out sweep-config CFD
run, and two force-surrogate evaluation figures (coarse-vs-fine holdout comparison, a config-mean-
collapse diagnostic). None of them are tested, documented, run-metadata-traceable, or usable on any
config other than the one they were hand-written for.

This matters beyond the deck: the `fix-force-surrogate-sweep-hinge` follow-on plans a mid-sweep
check — after just a few of the corrected 27-config corpus's runs finish, visually confirm the wing
geometry/kinematics look right (an LEV/wake video, a coarse-vs-fine-style comparison) *before*
burning the remaining GPU-hours on a full run that could be re-running the same class of geometry
bug this change's sibling proposal just fixed. The vault scripts cannot serve that use case as
written — each is hardcoded to one specific config's plotfile path, hinge, and kinematics.

The vault scripts also already duplicate work the repo has a canonical answer for: they re-derive
their own local `rotation_matrix`/`euler_angles` functions instead of importing
`mosquito_cfd.benchmarks.wing_kinematics` (the single canonical Python source for wing rotation,
per that module's own CC-3 DRY requirement) — exactly the kind of duplicate-implementation risk
that convention exists to prevent.

## What Changes

- **New `src/mosquito_cfd/visualization/` package** (new capability, spans both general CFD
  diagnostics and force-surrogate evaluation — see `design.md` D1 for why it's not folded into
  `benchmarks/` or `force_surrogate/`):
  - `wing_render.py` — shared wing marker/outline transform helpers, built on the canonical
    `benchmarks.wing_kinematics.{rotation_matrix,euler_angles}` and `geometry.vertex_io.read_vertex_file`
    (replaces the vault scripts' duplicated rotation code).
  - `flow_video.py` — one generalized CFD-field video builder, parameterized by config name (or
    explicit plotfile directory + kinematics/hinge override) and a field mode
    (`wake-slice` | `combined-3d` | `lev-3d` | `zvelocity-3d`), covering what were 5 separate
    hardcoded vault scripts: `t3c-fine-wake.mp4` and `field-capture-s45_f115_p60-wake.mp4` both
    collapse into `wake-slice` (both are 2D top-down x-velocity slices, differing only in
    `--config`/`--plotfile-dir`), and `t3c-fine-combined-3d.mp4`/`t3c-fine-lev-3d.mp4`/
    `t3c-fine-zvelocity-3d.mp4` map 1:1 onto `combined-3d`/`lev-3d`/`zvelocity-3d`. Built on the
    existing `benchmarks.stress_integral.extract_eulerian_box` +
    `benchmarks.lev.{q_criterion,vorticity_magnitude}`.
  - `kinematics_video.py` — cluster-free, pure-kinematics preview video (no plotfile needed) —
    directly serves "sanity-check geometry before the CFD run even starts," a stronger version of
    the mid-sweep-check goal than any of the vault's CFD-derived videos.
- **New `src/mosquito_cfd/force_surrogate/comparison_figure.py`** — coarse-vs-fine holdout
  comparison and config-mean-collapse diagnostic figure builders, parameterized by
  `holdout_predictions.parquet` paths (not hardcoded to `prelim_sweep`/`prelim_sweep_fine`).
- **Four new thin CLI drivers** under `scripts/`, following `make_wing_phase_diagnostic.py`'s
  established pattern exactly (`argparse`, required `--docker-digest`/`--timestamp`, `--out-dir`,
  library does the work): `make_flow_video.py`, `make_kinematics_video.py`,
  `make_comparison_figure.py`, `make_config_mean_collapse_diagnostic.py`.
- **New optional `viz` dependency group** in `pyproject.toml` (`scipy`, `scikit-image`,
  `imageio-ffmpeg` — needed for marching-cubes isosurfaces and mp4 encoding; not currently a
  dependency anywhere in the repo). Unlike the existing `train` group, `viz` is lightweight and
  cross-platform, so CI installs it (`uv sync --frozen --group viz`) rather than skip-gating tests
  around it — see `design.md` D2.
- **Every generated artifact gets the CC-1 run-metadata sidecar** (`capture_surrogate_run_metadata`
  + `validate_image_digest`, fail-fast before any file write) — none of the vault scripts do this
  today.
- **Committed reference outputs**: one small reference PNG per figure/diagnostic script, generated
  from the same tiny synthetic fixture used by that script's unit test (see `design.md` D6's
  fixture-vs-real-data split) — **not** from real corpus data. `examples/prelim_sweep_fine/surrogate/`
  (the real fine-grid holdout data the vault's original comparison figure used) does not exist on
  `main` today — it only ever existed on the throwaway `duncan-meeting-prep` branch and is stale
  regardless (hinge-buggy, per `fix-force-surrogate-sweep-hinge`) — so regenerating the *real*
  two-grid comparison figure is out of scope here (see `## Out of Scope`) and tracked as a follow-up
  once that data lands post-cluster-run. Generated mp4 videos are **not** committed (450 KB–1.5 MB
  each, not diff-reviewable) — `.gitignore`d by output-filename convention (not by directory, since
  `--out-dir` is caller-supplied — see `design.md` D5), with the exact regeneration command
  documented instead.
- **Docs**: a new `openspec/project.md` "Visualization Tooling" section (package layout, CLI
  invocation examples, the mid-sweep partial-corpus check workflow) and a pointer to the two
  documented hinge-caveat cases from the vault README (video "as-run buggy hinge" vs. "corrected
  hinge for display" — see `design.md` D3) so that provenance travels with the code, not only the
  vault.

## Out of Scope

- No cluster job submission, no change to the in-flight `fix-force-surrogate-sweep-hinge` branch or
  PR #71, and no re-running of the actual 27-config sweep. This proposal ships Python tooling only,
  tested against synthetic fixtures plus the existing `requires_plotfile` gated-test convention
  (auto-skipped without `$MOSQUITO_CFD_PLOTFILE_ROOT`) for the real-plotfile path.
- Regenerating the *real* `coarse_vs_fine_comparison.png`/diagnostic figures against actual
  fine-grid corpus holdout data — `examples/prelim_sweep_fine/surrogate/` doesn't exist on `main`
  (verified this session); it depends on the corrected fine-grid corpus's cluster run, which is
  itself gated on `fix-force-surrogate-sweep-hinge`/PR #71's own explicit go-ahead. This proposal's
  committed reference PNGs use synthetic fixtures instead (see `## What Changes`); re-running the
  figure scripts against real data once it exists is a follow-up, tracked in `openspec/project.md`'s
  Pending section alongside the existing full-corpus cluster-run item.
- No 3D rendering library other than the vault's proven `matplotlib` (`mpl_toolkits.mplot3d`) +
  `scikit-image` (`marching_cubes`) + `scipy` stack — `pyvista`/`vtk` were considered (see
  `design.md` D2) and rejected as an unnecessary new dependency for this scope.
- Auto-computed Q-criterion thresholds / colorbar ranges are not in scope. The generalized
  `flow_video.py` keeps the vault's empirically-tuned defaults (`Q_THRESHOLD=300`,
  `VORT_VMIN/VMAX=40/250`) as CLI-overridable parameters, not an auto-percentile computation —
  see `design.md` D4.

## Impact

- **Affected specs**: new capability `visualization-tooling` (this change adds it).
- **Affected code**: new `src/mosquito_cfd/visualization/` package, new
  `src/mosquito_cfd/force_surrogate/comparison_figure.py`, four new `scripts/*.py` CLI drivers,
  new `tests/test_{wing_render,flow_video,kinematics_video,comparison_figure}*.py`,
  `pyproject.toml` (new `viz` group) + `uv.lock` (regenerated in the same commit — see `design.md`
  D2), `.github/workflows/ci.yml` (**Test job only** — installs `--group viz`; the Lint job's path
  list already covers `src/` and `scripts/` recursively, no change needed there), `.gitignore` (new
  filename-scoped mp4 patterns), `openspec/project.md` (new "Visualization Tooling" section, plus a
  one-line fix to the existing Dependencies list which already omits the `train` group and would
  otherwise now also omit `viz`), `docs/CHANGELOG.md` (new entry, per project convention).
- **Not affected**: any cluster path, `examples/prelim_sweep*` decks/manifests, the force-surrogate
  training pipeline, any already-validated benchmark result, or any Dockerfile (none of the three
  images `COPY scripts/` or install any dependency group beyond the base `uv sync --frozen` — these
  tools are dev-host-only, matching `make_wing_phase_diagnostic.py`'s own precedent).

## Deviation discovered during implementation

### PR1 review rounds added input-validation and correctness guards `tasks.md` task 10/22-25 didn't name

Four rounds of `/review-pr` on PR1 (`wing_render.py` + `comparison_figure.py`) found real bugs and
fixed them directly in code, but `tasks.md`'s task 10 text ("Implement `wing_render.py`:
`transform_markers`, `wing_outline`, `leading_edge_mask`...") and tasks 22-25's text were never
updated to name what was actually added. Per this proposal's own convention (documenting deviations
rather than leaving them silent — see e.g. `openspec/changes/archive/2026-07-02-refactor-wing-axis-convention/proposal.md`),
the additions are recorded here instead of silently rewriting the historical task text, and the
`spec.md` scenarios that were missing for these behaviors have been added retroactively in this same
PR1 pass:

- **`wing_render.py`**: `_require_xyz_columns` (rejects any non-`(N, 3)` marker array with a named
  `ValueError`), `wing_outline`'s `QhullError`→`ValueError` wrapping for degenerate/collinear
  (chord, span) projections, and the empty-markers/non-finite-hinge guards in `transform_markers`.
  All three are now covered by `spec.md`'s new "degenerate or malformed marker input is rejected"
  scenario under the hinge-rotation requirement.
- **`comparison_figure.py`**: the `config_mean_r2` `None`/JSON-`null` sentinel pass-through (a
  legitimate near-zero-between-config-variance diagnostic result, not an error), the independent
  SHA256 hashing of every secondary input file (`fine_predictions_sha256`,
  `coarse_predictions_sha256`, `fine_metrics_sha256` — `capture_surrogate_run_metadata`'s own
  `inputs.hash` only covers the single primary `inputs_file` argument), and a
  `try`/`finally`-around-`plt.subplots()` guard so a downstream error (a non-creatable `out_dir`, a
  malformed `metrics.json`) never leaves an unclosed `matplotlib.Figure` behind. The first two are
  now covered by new `spec.md` scenarios; the `Figure`-leak guard is left as an internal robustness
  property (matching the rest of this capability's specs, which document observable input/output
  contracts, not resource-cleanup implementation details) and is not elevated to a spec scenario.

No task-13-level scope change resulted — Phase 1 and Phase 4's checked-off tasks (1-10, 22-25) still
accurately describe what was implemented and tested; this section exists because the *description*
of that implementation needed to catch up, not because the plan itself was wrong.

### PR2 added `config_kwargs`/`resolve_kinematics_kwargs` to `wing_render.py`, not named in tasks.md

Tasks 13 and 18 both require a "config name or explicit override" resolution test in
`test_flow_video.py`/`test_kinematics_video.py`, but dependency order (Phase 5, the CLI drivers,
comes *after* Phases 2/3) rules out putting this resolution logic in the not-yet-existing CLI
scripts the way `make_wing_phase_diagnostic.py`'s `_config_kwargs`/`_sweep_config_kwargs` do it.
Since `flow_video.py` and `kinematics_video.py` both need the identical behavior (`design.md` D3),
it was added once to `wing_render.py` (`config_kwargs`, `resolve_kinematics_kwargs`) — the shared
Phase 1 substrate both later phases already depend on — rather than duplicated in each module. This
is the one place `visualization/` imports from `force_surrogate` (`read_deck_value`,
`parse_config_name`), a narrow exception to `design.md` D1's package-boundary framing (which
otherwise keeps `visualization/` ignorant of force-surrogate specifics); the imported functions are
generic deck/config-name string parsing, not force-surrogate-specific computation. No `spec.md`
change resulted — the "config or explicit override" requirement's scenarios are already satisfied
by this shared implementation, exercised through both consuming modules' own tests.

### PR2's 3-D scenes shipped with no explicit axis limits or view angle — found by visually inspecting rendered output against the vault reference videos, not by any automated test

None of tasks 11-21's TDD instructions call for checking rendered *visual* composition (axis limits,
camera angle) — every test asserts numerical correctness or "a non-empty `.mp4` exists," which a
video with a collapsed, autoscaled-to-nothing 3-D scene still satisfies. The initial PR2
implementation of `flow_video.py`'s 3-D field modes (`combined-3d`/`lev-3d`/`zvelocity-3d`) and
`kinematics_video.py` never called `ax.view_init(...)` or `ax.set_xlim/ylim/zlim(...)` — every
frame relied on mplot3d's default per-frame autoscale-to-plotted-data. Two real, user-visible bugs
resulted, both invisible to the file-exists/non-zero-size tests already in place, only found by
actually rendering real T3c-fine videos and looking at them (compared frame-by-frame against the
vault's own reference videos in `c:\vaults\physics surrogate models\duncan-meeting-2026-08-11\videos\`,
which this whole change generalizes):

- **`flow_video.py`**: the velocity-slice plane (`combined-3d`/`zvelocity-3d`) and the LEV
  isosurface (`lev-3d`) autoscaled to whatever that one frame's plotted extent happened to be —
  for the slice modes this collapsed the entire 3-D scene into an unreadably thin sliver at the
  bottom of the axes (the wing, lifted only `_WING_Z_LIFT=0.6` above the plane, has almost no
  z-extent to autoscale against); for `lev-3d` the isosurface's own bounding box changes shape
  every frame as the vortex core evolves, so the axes visibly rescaled frame to frame, making the
  *stationary* hinge marker appear to move. Fixed with two new pure, unit-tested functions,
  `_lev_axis_limits`/`_velocity_slice_axis_limits`, deriving fixed limits from the already-computed
  box's own coordinate range (`lev-3d`) or the slice height ± a documented `_Z_VIEW_MARGIN`
  (`combined-3d`/`zvelocity-3d`), plus `ax.view_init(elev=28, azim=-60)` re-applied every frame
  (matching the vault scripts' own values — `ax.clear()` resets both every call).
  `test_lev_3d_axis_limits_are_stable_across_frames_with_different_isosurfaces` reproduces the bug
  report directly: two frames with genuinely different isosurface geometry must still render with
  identical axis limits. (That test's first version spied on `Axes3D.set_zlim` directly and failed
  even after the fix — mplot3d's own internal autoscale machinery calls `set_zlim` several
  *transient* times per frame during rendering; the test was corrected to spy on
  `FFMpegWriter.grab_frame` instead, which reflects only what is actually written to the video.)
- **`kinematics_video.py`**: the axis limits were computed from `ref_markers` (rest-frame,
  *unrotated* positions) union the tip marker's own rotated trajectory — any *other* marker that
  sweeps outside its own rest-frame footprint under rotation (which every non-tip marker does, to
  varying degrees) was never accounted for, so the wing visibly rendered outside the frame at
  points in the stroke cycle. Fixed with a new pure, unit-tested `_swept_bounding_box` function
  that samples every marker's *rotated* position at `_TRAJECTORY_SAMPLES` phases (not just the
  tip's), plus `ax.view_init(elev=22, azim=-65)` (matching the vault kinematics script, also
  missing before this fix).

No `spec.md` change resulted — visual composition (axis framing, camera angle) is an
implementation-quality property of the already-specified "render a video" requirements, not a
distinct scenario. No task-11–21-level scope change resulted either, for the same reason as the
PR1 deviation above: the checked-off tasks still accurately describe what was implemented and
tested; this section exists because rendering correctness turned out to have a dimension (visual
framing) that numeric/file-existence tests alone don't cover, and manual inspection against the
vault reference was what actually caught it.
