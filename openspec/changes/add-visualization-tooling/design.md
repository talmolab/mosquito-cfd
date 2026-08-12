# Design: visualization tooling

## D1. Package placement — new `visualization/`, not `benchmarks/` or `force_surrogate/`

**Problem:** the 8 vault scripts split roughly into "general CFD field diagnostics" (LEV
isosurface, velocity slices, wing kinematics — none of these are force-surrogate-specific; the
same LEV video technique applies to any flapping-wing run, validated or sweep) and "force-surrogate
evaluation" (coarse-vs-fine holdout comparison, config-mean-collapse — these read
`holdout_predictions.parquet`/`metrics.json`, artifacts that only exist because a surrogate model
was trained).

**Decision:** split along that line rather than lumping everything into one package:

- `src/mosquito_cfd/visualization/` (new) — `wing_render.py`, `flow_video.py`,
  `kinematics_video.py`. These take a plotfile directory (or none, for kinematics-only) and
  kinematics/hinge parameters; they know nothing about force-surrogate training, parquet schemas,
  or sweep manifests beyond the same optional `--config`/`--corpus-dir` convenience lookup
  `make_wing_phase_diagnostic.py` already established.
- `src/mosquito_cfd/force_surrogate/comparison_figure.py` (extends the existing package,
  neighboring `evidence_figure.py`) — reads `holdout_predictions.parquet` and `metrics.json`,
  genuinely force-surrogate-specific.

**Why not fold the videos into `benchmarks/`:** `benchmarks/` (`lev.py`, `stress_integral.py`,
`wing_lev.py`) is pure analysis/extraction — no matplotlib, no video/figure I/O anywhere in that
package today. Adding rendering code there would mix "compute a diagnostic" with "make a picture of
it," which the repo has so far kept separate (`benchmarks/lev.py` computes; nothing in `benchmarks/`
plots). `visualization/` imports *from* `benchmarks/` (the extraction/analysis primitives) the same
way `force_surrogate/wing_phase_diagnostic.py` imports from `benchmarks/wing_kinematics.py` — one
direction of dependency, no cycle.

## D2. New dependencies: `scipy` + `scikit-image` + `imageio-ffmpeg`, lazy-imported, `viz` group

**What's needed and why:** the vault's own working implementation already answers "what does LEV
isosurface + video rendering need" — `skimage.measure.marching_cubes` (isosurface extraction from
the Q-criterion field), `scipy.spatial.ConvexHull` (wing planform outline from scattered vertex
markers), `scipy.ndimage.map_coordinates` (vorticity color sampled at isosurface vertices), and
`imageio_ffmpeg.get_ffmpeg_exe()` feeding `matplotlib.animation.FFMpegWriter` (mp4 encoding via a
bundled static ffmpeg binary — no system `ffmpeg` install required on any platform). `pyvista`/`vtk`
were considered and rejected: the vault scripts already solved this with matplotlib + scikit-image,
that solution is *proven* (the videos exist and are correct per the README's fact-checking), and
swapping rendering stacks would be unrequested scope with no functional benefit.

**Dependency group, not base deps:** these three packages are needed by the `visualization/`
package's rendering path — **not only `flow_video.py`**, corrected after review found the original
claim here was wrong: `wing_render.wing_outline` uses `scipy.spatial.ConvexHull` (task 6), and
`kinematics_video.py` writes an actual `.mp4` via `imageio_ffmpeg.get_ffmpeg_exe()` +
`FFMpegWriter`, the same mechanism `flow_video.py` uses — so `wing_render.py` needs `scipy` and
`kinematics_video.py` needs `imageio_ffmpeg` too. Only `comparison_figure.py` (matplotlib/pandas/
numpy static figures, no video, no convex-hull geometry) is genuinely base-deps-only. Gating the
three `viz` packages behind a new dependency group (mirroring `train`'s existing pattern in
`pyproject.toml`) still keeps `uv sync`'s default install lean for anyone not touching
visualization at all.

**Why CI installs `viz` (unlike `train`, which CI deliberately skips):** `train`'s deps
(`nvidia-physicsnemo`, `torch`) are GPU-oriented, Linux-marker-gated, and slow/heavy to install —
CI has no GPU and gains nothing from installing them. `scipy`/`scikit-image`/`imageio-ffmpeg` are
lightweight, pure-Python-wheel, cross-platform packages with no GPU requirement — installing them in
CI costs little and buys real test coverage of the new modules' non-plotfile-dependent logic (CLI
arg validation, digest validation, mode-selection errors). `.github/workflows/ci.yml`'s Test job
changes from `uv sync --frozen` to `uv sync --frozen --group viz`.

**`uv.lock` must be regenerated, not just `pyproject.toml`:** verified this session — none of
`scipy`/`scikit-image`/`imageio-ffmpeg` appear anywhere in the current `uv.lock` (not even
transitively). `--frozen` refuses to touch the lockfile; it hard-errors if the lockfile doesn't
already satisfy `pyproject.toml`'s declared groups. Editing `pyproject.toml` alone (adding the
`viz` group) and then running `uv sync --frozen --group viz` in CI **will fail** on a fresh
checkout. `uv lock` (no `--frozen`) must be run locally and the regenerated `uv.lock` committed
*in the same commit* as the `pyproject.toml` change — see `tasks.md` Phase 0.

**Lazy import, following the existing `extract_eulerian_box` convention:** `stress_integral.py`
already imports `yt` *inside* `extract_eulerian_box`, not at module top, specifically so the module
stays importable without that dependency installed. **All three `visualization/` modules that touch
a `viz`-group package** — `wing_render.py` (`scipy.spatial.ConvexHull` inside `wing_outline`),
`flow_video.py` (`scipy`/`skimage`/`imageio_ffmpeg` inside its rendering functions), and
`kinematics_video.py` (`imageio_ffmpeg` inside its video-writing function) — follow the same
pattern: imported inside the functions that need them, never at module top. This means every
`import mosquito_cfd.visualization.*` succeeds regardless of whether `uv sync --group viz` was run;
only *calling* a rendering/outline/video-writing function does, with whatever `ImportError` Python
gives naturally (no custom guard/message needed — the failure is immediate and unambiguous at the
one call site that needs the dependency). The spec's lazy-import requirement and its AST-scan test
(`tasks.md` task 9) cover the whole package, not `flow_video.py` alone.

## D3. Generalizing the hardcoded vault scripts: config-driven by default, explicit override always available

**Problem:** every vault video is hardcoded to one config's plotfile directory, hinge, and center.
Two of them are hardcoded *on purpose*, not by oversight, and that intent must survive
generalization:

- `wing-kinematics-s45_f115_p60.mp4` deliberately uses the **corrected** hinge `(4.0, 0.5, 4.0)`
  for display, even though that config's actual CFD training run used the **buggy** hinge
  `(4.0, 2.0, 2.5)` — because the buggy hinge produces a propeller-like silhouette that would be a
  worse, inaccurate-looking preview, and this video carries no CFD data (kinematics only).
- `field-capture-s45_f115_p60-wake.mp4` deliberately uses the **as-run buggy** hinge, because it
  visualizes a real CFD run's actual field data and changing the displayed hinge would desynchronize
  the picture from the physics it's showing.

**Decision:** `flow_video.py`/`kinematics_video.py` accept **either** `--config <name>
--corpus-dir <dir>` (reads hinge/center/kinematics from that config's own generated deck, exactly
like `make_wing_phase_diagnostic.py`'s `_sweep_config_kwargs`) **or** explicit
`--hinge x y z --center x y z --stroke-amp-deg ... --pitch-amp-deg ... --frequency-fstar ...`
overrides that take precedence when supplied. This is not new design — it is the same
config-vs-explicit-kwargs split `wing_phase_diagnostic.py`'s `build_wing_phase_figure` already has
(it takes explicit `center`/`hinge`/angles as keyword arguments; the CLI script's `_config_kwargs`
helper is what resolves a config name into those values) — `flow_video.py`'s CLI driver reuses that
same resolution pattern rather than inventing a second one.

**This section is the single canonical explanation of the two hinge-caveat cases.** Per
documentation review, the new CLI scripts' docstrings (`tasks.md` Phase 5, task 28) and
`openspec/project.md`'s new docs section (`tasks.md` Phase 6, task 31) each carry only a one-line
pointer back to this section (`design.md` D3) rather than re-stating both cases — avoiding a 3-4x
duplication of the same substantive content across code comments, docs, and this design doc. The
pointer must use the durable, change-ID-qualified form (`` OpenSpec change
`add-visualization-tooling` (`design.md` D3) ``), not a literal pre-archival path — see task 28's
note on why (`metadata_capture.py`'s existing dangling-path mistake).

## D4. Empirically-tuned constants (Q-threshold, colorbar ranges) become documented CLI defaults, not auto-computed

The vault's `Q_THRESHOLD=300` (~99.4th percentile, checked against a representative T3c-fine frame)
and `VORT_VMIN/VMAX=(40, 250)` are frame-specific empirical tuning, not universal constants — a
different config's Q-field distribution will differ. Auto-computing a percentile-based threshold
per-video would generalize further, but is unrequested scope with its own failure modes (a
percentile computed from a near-empty or entirely-vortex-saturated field can silently pick a
meaningless threshold) that this proposal does not attempt to solve. Instead: `flow_video.py`
exposes `--q-threshold`/`--vort-vmin`/`--vort-vmax` (and the 2D-slice equivalents) as CLI flags with
the vault's proven values as defaults — the mid-sweep check's first uses (visually similar T3c-fine-
family kinematics) work out of the box; a visibly different config can override.

## D5. `.gitignore` scoping is filename-convention-based, not directory-based

**Problem, found in review:** `--out-dir` is caller-supplied and arbitrary (matching
`make_wing_phase_diagnostic.py`'s own `--out-dir` convention) — a `.gitignore` pattern scoped to a
specific directory (e.g. `examples/prelim_sweep*/figures/*.mp4`) does not fire for an mp4 written
anywhere else, silently defeating the "videos aren't committed" intent for any other output
location.

**Decision:** scope the pattern by **output filename**, not directory — matching how
`IB_Particle_*.csv` is actually scoped (by name, not by the directory a run happens to write into).
The CLI drivers name their outputs predictably: `flow_video.py` writes `<label>_flow_<field-mode>.mp4`
(e.g. `s45_f115_p60_flow_wake-slice.mp4`) and `kinematics_video.py` writes
`<label>_kinematics_preview.mp4`. `.gitignore` adds `*_flow_*.mp4` and `*_kinematics_preview.mp4` —
these match regardless of which directory a caller points `--out-dir` at.

## D6. Pure rendering math is separated from the yt/plotfile adapter, so it gets real CI coverage

**Problem, found in review:** every scenario that exercises `flow_video.py`'s actual field-to-pixel
logic (isosurface extraction, slice color-mapping, frame composition) was originally routed through
a `requires_plotfile`-marked test — which never runs in CI (no `$MOSQUITO_CFD_PLOTFILE_ROOT` there).
That would leave the module's actual rendering correctness with **zero** CI coverage, unlike
`benchmarks/lev.py` (tested against synthetic analytic fields, cluster-free) or
`benchmarks/stress_integral.py` (`extract_eulerian_box` isolates the one yt-touching function; the
CV-drag math around it is tested separately without yt).

**Decision:** `flow_video.py` follows the same split, for **each of its two distinct rendering
primitives** — review's third round found the original wording here named only one of the two and
so left 3 of the 4 field modes still zero-CI-coverage, undermining this section's own goal:

- `render_lev_frame(u, v, w, dx, q_threshold, vort_vmin, vort_vmax) -> Poly3DCollection` data — the
  Q-criterion isosurface/vorticity-color path, used by `lev-3d`.
- `render_velocity_slice_frame(field, dx, vmin, vmax) -> colored-slice data` — the 2D velocity-slice
  color-mapping path, used by `wake-slice` (x-velocity) and `zvelocity-3d` (z-velocity; same
  function, different field/colorbar-range arguments).
- `combined-3d` needs no third primitive: it is pure composition of `wing_render`'s wing-drawing
  (Phase 1) plus `render_velocity_slice_frame`'s output in one 3D scene — its CI coverage comes
  from its two components' own tests, not a dedicated combined-3d unit test.

Both primitives take plain numpy arrays and are unit-tested against small synthetic fields (a
solid-body-rotation Q-field and an empty-below-threshold field for the isosurface path, a small
synthetic velocity field with a known min/max for the slice path — mirroring `lev.py`'s own
analytic fixtures) with **no plotfile, no yt, no `viz`-group dependency required for the test to
exist** (the test file itself needs `scikit-image`/`scipy` to *run*, same as any other `viz`-gated
test, but needs no real CFD data). A separate, thin function per field mode reads the plotfile via
`extract_eulerian_box` and calls the appropriate pure renderer — that thin seam is the only part
still gated by `requires_plotfile`. This closes the CI-coverage gap for all four field modes, not
just `lev-3d`. See `tasks.md` Phase 2's added tasks.
