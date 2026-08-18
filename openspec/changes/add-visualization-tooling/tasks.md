## Tasks

**Dependency order:** Phase 0 (infra) has no code dependents but must land first (later phases
import the new `viz` group). Phase 1 (`wing_render.py`) is shared by Phases 2 and 3 — do it first.
Phase 4 (`comparison_figure.py`) is independent of Phases 1-3 (no shared code, no `viz`-group
dependency) and can run in parallel. Phase 5 (CLI drivers) depends on whichever library phase it
wraps. Phase 6 (docs) depends on everything else being named/stable. Phase 7 is final validation.

**Suggested PR split** (this change, unlike `fix-force-surrogate-sweep-hinge`, touches no
already-shipped simulated data and nothing here is cluster-gated, so a lighter split than that
change's 4-PR stack is enough). Phase 5's CLI drivers all depend on library code from more than one
earlier phase (`make_flow_video.py`/`make_kinematics_video.py` need Phase 1-3;
`make_comparison_figure.py`/`make_config_mean_collapse_diagnostic.py` need Phase 4) and are written
as one task each, so Phase 5 is **not** split across PRs — it lands whole, after both of its
dependency phases:

- **PR 1** — Phase 0 + Phase 1 + Phase 4 (infra, `wing_render.py`, `comparison_figure.py` — library
  code only, no CLI drivers yet). Independent of `flow_video.py`/`kinematics_video.py`. Note:
  `wing_render.py` itself needs the `viz` group (`scipy.spatial.ConvexHull`, per `design.md` D2's
  correction), which is fine since Phase 0 (also in this PR) already installs it in CI.
- **PR 2** — Phase 2 + Phase 3 (the two video builders) + Phase 5 in full (all four CLI drivers,
  since two of them depend on Phase 4 from PR 1 and the other two depend on this PR's own Phase
  2/3). Depends on PR 1.
- **PR 3** — Phase 6 (docs, reference-PNG regen, CHANGELOG) + Phase 7 (final validation).

### Phase 0 — dependency infrastructure

1. [x] Add a `viz` dependency group to `pyproject.toml`: `scipy`, `scikit-image`,
   `imageio-ffmpeg`. Use `uv add --group viz scipy scikit-image imageio-ffmpeg` (not a hand-typed
   version range) so the resolved versions are recorded concretely, not left as an "if it matters"
   guess. Add a comment explaining why this group is lightweight/cross-platform and installed in
   CI, unlike `train`.
2. [x] **Run `uv lock` (not `--frozen`) and commit the regenerated `uv.lock` in the same commit as
   task 1's `pyproject.toml` change.** Verified this session: none of the three new packages exist
   anywhere in the current `uv.lock`, and `--frozen` refuses to update a lockfile — a later CI step
   that runs `uv sync --frozen --group viz` without this step will fail on a fresh checkout with
   "The lockfile at uv.lock needs to be updated." This is not optional cleanup; it is a hard
   prerequisite for task 3.
3. [x] Update `.github/workflows/ci.yml`'s Test job: `uv sync --frozen` → `uv sync --frozen --group
   viz`. Verify: `uv sync --frozen --group viz && uv run python -c "import scipy, skimage,
   imageio_ffmpeg"` succeeds locally from a clean clone (not just the existing dev environment,
   which may already have these packages installed some other way).
4. [x] Add `*_flow_*.mp4` and `*_kinematics_preview.mp4` to `.gitignore` (filename-convention-scoped
   per `design.md` D5, not directory-scoped — `--out-dir` is caller-supplied and arbitrary, so a
   directory-scoped pattern would miss anything written elsewhere). Mirror the existing
   scoped-comment style around the `IB_Particle_*.csv` entry.

### Phase 1 — `wing_render.py` shared helpers (TDD)

5. [x] Write `tests/test_wing_render.py::test_transform_markers_rotates_about_hinge_not_origin` —
   for a known hinge away from the origin and `phi=90°, alpha=0°, theta=0°`, assert the transformed
   marker matches a hand-computed 90° rotation **about the hinge**, and explicitly assert it differs
   from a rotation about the origin (catches the specific bug class this requirement exists to
   prevent). Must fail with `ImportError`/`AttributeError` first (module doesn't exist yet).
6. [x] Write `test_wing_outline_from_vertex_file` — the convex-hull outline computed from a small
   synthetic vertex array matches `scipy.spatial.ConvexHull` called directly on the same points.
7. [x] Write `test_leading_trailing_edge_split` — markers with `x >= 0` are classified "leading",
   matching the vault convention documented in the vault README.
8. [x] Write `test_transform_markers_rejects_zero_marker_input` and
   `test_transform_markers_rejects_non_finite_hinge` — an empty vertex array, and a NaN/inf hinge or
   center, both raise a clear `ValueError` naming the problem (mirrors
   `wing_phase_diagnostic.py`'s own degenerate-geometry guards; do not let a bad input silently
   propagate a garbage transform).
9. [x] Write `tests/test_wing_render.py::test_no_local_rotation_matrix_definition` and
    `test_no_top_level_viz_group_imports` — AST scans of every `.py` file under
    `src/mosquito_cfd/visualization/` (enumerate with `Path(...).rglob("*.py")`, not manual string
    path-joining, so the scan is separator-agnostic between the Windows dev host and the
    `ubuntu-latest` CI runner). The first asserts no top-level `def rotation_matrix` or `def
    euler_angles` exists anywhere in the package (spec requirement: rotation is imported from
    `wing_kinematics`, never reimplemented). The second asserts no file in the package has a
    top-level `import scipy`/`from scipy...`/`import skimage`/`from skimage...`/
    `import imageio_ffmpeg` — this check is package-wide, not `flow_video.py`-only, since
    `wing_render.py` (`scipy.spatial.ConvexHull`) and `kinematics_video.py` (`imageio_ffmpeg`) also
    touch `viz`-group packages (review found the original plan incorrectly assumed only
    `flow_video.py` did — see `design.md` D2's correction).
10. [x] Implement `wing_render.py`: `transform_markers`, `wing_outline`, `leading_edge_mask`,
    importing `rotation_matrix`/`euler_angles` from `mosquito_cfd.benchmarks.wing_kinematics` (no
    local reimplementation — spec requirement). `wing_outline` imports `scipy.spatial.ConvexHull`
    **inside the function**, not at module top (lazy-import convention, `design.md` D2 — this module
    needs the `viz` group despite living in Phase 1/PR 1, which is fine since Phase 0 already
    installs it in CI). Run tasks 5-9 green.

### Phase 2 — `flow_video.py` generalized CFD-field video builder (TDD)

11. [x] Write `tests/test_flow_video.py::test_rejects_mutable_docker_tag` — calling the builder with
    a `:latest`-style digest raises `ValueError` before any plotfile access (use a nonexistent path
    to prove no I/O was attempted).
12. [x] Write `test_rejects_unknown_field_mode` — `field_mode="isosurface"` raises `ValueError`
    naming the value and the 4 valid modes, without opening any plotfile path.
13. [x] Write `test_config_kwargs_resolves_from_deck` and
    `test_explicit_override_takes_precedence_over_deck` — mirrors
    `wing_phase_diagnostic.py`'s `_sweep_config_kwargs`/`_config_kwargs` split; use a small
    synthetic deck fixture, no real plotfile needed.
14. [x] **Write pure-numpy synthetic-field tests for BOTH of `flow_video.py`'s rendering
    primitives** (`design.md` D6) — review's third round found the original version of this task
    covered only one of the two and left 3 of 4 field modes with zero CI coverage, the exact gap
    this task exists to close:
    - `tests/test_flow_video.py::test_render_lev_frame_matches_solid_body_rotation` and
      `test_render_lev_frame_skips_below_threshold_field` — the Q-isosurface/vorticity-color path
      (`lev-3d`), mirroring `lev.py`'s own solid-body-rotation analytic fixture.
    - `test_render_velocity_slice_frame_matches_known_field` and
      `test_render_velocity_slice_frame_clips_to_vmin_vmax` — the 2D velocity-slice color-mapping
      path, using a small synthetic field with a known min/max. This one function serves both
      `wake-slice` (x-velocity) and `zvelocity-3d` (z-velocity) — test it once, generically over the
      field array, not tied to either mode's field name.
    All four are pure-numpy, no plotfile, no yt, and run in every CI build (need the `viz` group,
    already installed there, but no real CFD data). Together they cover the rendering math behind
    `wake-slice`, `lev-3d`, and `zvelocity-3d` (`combined-3d` needs no separate primitive — it
    composes `wing_render` + `render_velocity_slice_frame`, already covered by their own tests) —
    closing D6's CI-coverage gap for all four field modes, not just one. Also directly covers the
    "an unrecognized field mode fails fast" and Q-threshold default/override spec scenarios below.
15. [x] Write `test_default_q_threshold_is_300` and `test_q_threshold_override_reaches_marching_cubes`
    — the documented default (`300.0`) is used when `--q-threshold` is omitted, and an explicit
    value is what's actually passed to `skimage.measure.marching_cubes`'s `level` argument (spy/mock
    the call rather than requiring a real field). Also write
    `test_writes_metadata_sidecar_without_a_plotfile` — monkeypatch `extract_eulerian_box` to return
    a small synthetic box dict (no real plotfile, no `$MOSQUITO_CFD_PLOTFILE_ROOT` needed) and assert
    the top-level orchestration function still writes the `.mp4` + `_run_metadata.json` sidecar pair.
    This closes a gap review found: without it, sidecar-writing for `flow_video` was only checked by
    task 16's `requires_plotfile`-gated tests, which never run in CI.
16. [x] Write `tests/test_flow_video_plotfile.py::test_renders_wake_slice_video`,
    `test_renders_combined_3d_video`, `test_renders_lev_3d_video`, `test_renders_zvelocity_3d_video`
    — **all four field modes**, each marked `@pytest.mark.requires_plotfile` — against a real
    single-level plotfile under `$MOSQUITO_CFD_PLOTFILE_ROOT`, assert an `.mp4` + `_run_metadata.json`
    pair is written and the mp4 file is non-empty. `lev-3d` additionally asserts at least one frame
    found >10 cells above `Q_THRESHOLD` (matching the vault script's own skip-if-empty guard), and a
    degenerate-input variant (`test_lev_3d_skips_empty_isosurface_gracefully`) asserts a
    below-threshold field returns `None`/skips rather than crashing (mirrors the vault script's
    `n_above < 10` guard).
17. [x] Implement `flow_video.py`: field-mode dispatch, config/override resolution (reusing Phase
    1's `wing_render.py`), and the pure/adapter split from `design.md` D6. Lazily import
    `scipy`/`skimage`/`imageio_ffmpeg` inside the specific rendering functions that need them (never
    at module top). **Verify laziness with `sys.modules` poisoning, not a subprocess** — a
    `subprocess.run([sys.executable, "-c", "import ..."])` check inherits whatever environment
    pytest itself runs under, and CI always has the `viz` group installed (task 3), so it would pass
    identically whether the import is lazy or eager and proves nothing. Instead:
    ```python
    def test_flow_video_importable_without_viz_group(monkeypatch):
        for name in ("scipy", "skimage", "imageio_ffmpeg"):
            monkeypatch.setitem(sys.modules, name, None)  # forces ImportError on any import attempt
        import importlib
        import mosquito_cfd.visualization.flow_video as fv
        importlib.reload(fv)  # re-executes module top-level code with the three names poisoned
    ```
    (`sys.modules[name] = None` makes any `import <name>`, anywhere, raise `ImportError` for the
    duration of the test — this genuinely proves the module's top-level code path never imports
    them, unlike the subprocess form.) Task 9's package-wide AST scan already covers `flow_video.py`
    as a second, independent check — no separate scan needed here.
    Run tasks 11-16 green (16 requires local plotfile data; verify manually if
    `$MOSQUITO_CFD_PLOTFILE_ROOT` isn't set in this session — everything else in this phase runs in
    plain CI). This is a larger implementation task than most others in this plan (dispatch across 4
    field modes); consider committing the 2D `wake-slice`/`combined-3d` path and the 3D
    `lev-3d`/`zvelocity-3d` isosurface path as two separate commits within the same PR for
    reviewability, even though they land as one task here.

### Phase 3 — `kinematics_video.py` cluster-free preview video (TDD)

18. [x] Write `tests/test_kinematics_video.py::test_rejects_mutable_docker_tag`,
    `test_config_kwargs_resolves_from_deck_with_no_override` (the plain, no-override config-resolve
    path — review's second round found this was untested for `kinematics_video`, only for
    `flow_video`), and `test_explicit_hinge_override_takes_precedence_over_deck` (review's first
    round found this was originally only tested for `flow_video`, despite `design.md` D3's
    dual-hinge-caveat narrative being specifically about `kinematics_video`).
19. [x] Write `test_chord_axis_extent_matches_root_hinge_arm` — for the validated config's kinematics
    (`stroke φ` about lab-vertical z per `wing_kinematics.rotation_matrix`; `stroke_amp_deg=70`,
    hinge at the span root, `span_arm≈2.975`), assert the span-tip marker's **chord-axis (x) extent**
    (max minus min of that one coordinate across one full wingbeat — not a 3-D Euclidean peak-to-peak)
    is within 5% of `2 * span_arm * sin(radians(stroke_amp_deg))` — the chord-length displacement of
    a point at radius `span_arm` sweeping between `+stroke_amp` and `-stroke_amp` about the hinge.
    **Correctness note from review round 2**: this metric is the *chord*-axis extent, not the
    span-axis extent — worked through `rotation_matrix`'s actual composition, a pure-span-offset
    point's span-axis (y) extent under stroke alone is instead `span_arm*(1-cos(stroke_amp_rad))`
    (≈1.96 vs. the chord-axis's ≈5.59 at this config's amplitude — a ~2.9x difference, not
    interchangeable). Use the chord-axis form given here; do not swap in the span-axis formula
    without also renaming the test and re-deriving the tolerance. Pair with a negative-case fixture
    using a synthetic near-zero `span_arm` (midspan-pivot-style), asserting the extent collapses
    toward zero — the same geometric signature `design.md`'s sibling proposal's
    `assert_hinge_at_span_root` checks on the deck, applied here to the rendered trajectory instead.
    The committed `wing.vertex` actually has **three** tied markers at max span (chord positions
    ≈−0.06, 0, +0.06) rather than a single tip point — pick the one nearest the chord centerline
    (`x≈0`) for this test. The ≈0.06 chord offset perturbs the chord-axis extent by ≈2%, well inside
    the 5% tolerance regardless of which tied marker is picked, but the tie-break should still be
    stated explicitly rather than left to guess during implementation.
20. [x] Write `test_writes_metadata_sidecar_with_no_plotfile_access` — confirms this builder never
    opens a plotfile path (pure kinematics), by pointing at a nonexistent plotfile-adjacent path and
    confirming no error referencing it occurs.
21. [x] Implement `kinematics_video.py` reusing `wing_render.py` + `wing_kinematics`. This module
    also needs the `viz` group (`imageio_ffmpeg`/`FFMpegWriter` for mp4 encoding, same mechanism
    `flow_video.py` uses — per `design.md` D2's correction, not base-deps-only as originally
    claimed); import `imageio_ffmpeg` inside the video-writing function, never at module top (task 9
    covers this module in its package-wide AST scan). Run tasks 18-20 green.

### Phase 4 — `comparison_figure.py` force-surrogate evaluation figures (TDD, parallel with 1-3)

22. [x] Write `tests/test_comparison_figure.py::test_coarse_vs_fine_panel_means_match_groupby` — a
    tiny synthetic `holdout_predictions.parquet` fixture (a handful of rows, 2 configs); assert the
    per-config diamond positions the figure computes match `df.groupby("config_name")[[...]].mean()`
    computed directly on the same fixture, to floating-point equality.
23. [x] Write `test_config_mean_collapse_diagnostic_matches_metrics_json` — a tiny synthetic
    `metrics.json` fixture with **distinct, known values** in `config_resolved` vs. `per_target`;
    assert the diagnostic's reported R² matches `config_resolved` exactly and is never a value from
    `per_target` (regression guard against the two-different-blocks conflation documented in the
    vault README).
24. [x] Write `test_rejects_mutable_docker_tag` and `test_writes_metadata_sidecar` for both figure
    builders (same CC-1 pattern Phase 2/3 apply to their builders).
25. [x] Implement `comparison_figure.py`: `build_coarse_vs_fine_comparison`,
    `build_config_mean_collapse_diagnostic`. Run tasks 22-24 green.

### Phase 5 — CLI drivers (TDD: smoke tests, no real data needed)

26. [x] Write `tests/test_make_flow_video_cli.py`: rejects missing required flags, rejects an
    invalid `--field-mode`, rejects a malformed `--hinge`/`--center` (wrong arity — use
    `nargs=3, type=float`, the same pattern `src/mosquito_cfd/geometry/cli.py`'s existing `--center`
    flag already uses; `make_wing_phase_diagnostic.py` has no hinge/center CLI override to mirror
    here, since it only ever reads them from a deck), mirroring
    `test_wing_phase_diagnostic_cli.py`'s smoke-test style otherwise.
27. [x] Write `tests/test_make_kinematics_video_cli.py` and
    `tests/test_make_comparison_figure_cli.py` (same smoke-test style; the latter also covers
    `make_config_mean_collapse_diagnostic.py`).
28. [x] Implement `scripts/make_flow_video.py`, `scripts/make_kinematics_video.py`,
    `scripts/make_comparison_figure.py`, `scripts/make_config_mean_collapse_diagnostic.py` — thin
    `argparse` drivers over the Phase 1-4 library functions, matching
    `make_wing_phase_diagnostic.py`'s structure (module docstring with a runnable example,
    `main(argv) -> int`, `if __name__ == "__main__": raise SystemExit(main())`). Per `design.md` D3,
    `make_flow_video.py`/`make_kinematics_video.py`'s docstrings carry only a one-line pointer to the
    two hinge-caveat cases, not a restatement — and **must use the durable, change-ID-qualified
    form**, e.g. `` OpenSpec change `add-visualization-tooling` (`design.md` D3) `` — not a literal
    `openspec/changes/add-visualization-tooling/design.md` path, which goes dangling once this
    change is archived to `openspec/changes/archive/<date>-add-visualization-tooling/`. This mirrors
    `sweep.py`/`train.py`'s existing pointer convention and specifically avoids the mistake already
    present in `metadata_capture.py` (a literal pre-archival path, now dangling). Run tasks 26-27
    green.
29. [x] Confirm (no change expected): `ruff check src/ tests/ scripts/ ...` already walks `src/`
    recursively, so `src/mosquito_cfd/visualization/` needs no addition to the Lint job's explicit
    path list, and the four new `scripts/*.py` files land directly in the already-listed `scripts/`
    directory. Run the lint command locally against the new files to confirm before assuming.

### Phase 6 — reference outputs + docs

30. [x] Commit `coarse_vs_fine_comparison.png` and `diagnostic_config_mean_collapse.png` generated
    from the **synthetic test fixtures** used in tasks 22-23 (not real corpus data —
    `examples/prelim_sweep_fine/surrogate/` does not exist on `main`; see `proposal.md`'s `## Out of
    Scope`). Place under a clearly-labeled path (e.g. `docs/visualization/` or
    `tests/fixtures/comparison_figure/`, decided during implementation), **and add a short
    `README.md` (or file-header comment) in that same directory stating explicitly that these PNGs
    are synthetic-fixture-derived validation evidence, not real corpus results, with a pointer to
    the real-data follow-up** — review found that a "clearly-labeled path" alone isn't a durable
    signal to someone who lands directly in the directory later without reading this proposal; the
    filename `coarse_vs_fine_comparison.png` is otherwise identical to what a real evidence figure
    would be named. Add a `openspec/project.md` Pending-section line noting that regenerating the
    *real* comparison figure against actual fine-grid holdout data is deferred until that data
    exists (tracked alongside the existing full-corpus cluster-run item).
31. [x] Add a "Visualization Tooling" section to `openspec/project.md`: package layout
    (`visualization/`, `force_surrogate/comparison_figure.py`), the 4 CLI scripts with one example
    invocation each, the `viz` dependency group, the same durable change-ID-qualified pointer to
    `design.md` D3 for the hinge-caveat cases used in task 28 (not a restatement, not a literal
    path), and the mid-sweep partial-corpus check workflow (run `make_flow_video.py --field-mode
    wake-slice` against the first few completed configs' plotfiles before the full 27-config sweep
    finishes).
32. [x] Fix the existing "Python Environment / Dependencies" bullet list in `openspec/project.md`
    (currently lists only `numpy`/`matplotlib`/`pandas`/`yt`). Add one line noting the two optional
    groups accurately: `train` is described only in `pyproject.toml`'s own comment (no dedicated
    `project.md` section exists for it today — do not claim one), while `viz` is described in this
    change's new "Visualization Tooling" section (task 31).
33. [x] Add a `docs/CHANGELOG.md` entry matching the granularity of recent entries (e.g. PR #61, #52
    — multiple specific `### Added` bullets, not one collapsed sentence). At minimum two bullets: (1)
    naming `wing_render.py`/`flow_video.py`/`kinematics_video.py`/`comparison_figure.py` and the four
    `scripts/make_*.py` CLI drivers plus the new `viz` dependency group; (2) naming the committed
    synthetic reference PNGs and the `project.md` "Visualization Tooling" section + Dependencies-list
    fix. Each ends with the merging PR number, per convention.

### Phase 7 — validation

34. [x] `uv run ruff check` / `uv run ruff format --check` over the new files.
35. [x] `uv run pytest -v -m "not gpu"` — full suite green (Phase 2/3's `requires_plotfile` tests
    auto-skip without `$MOSQUITO_CFD_PLOTFILE_ROOT`, as in every other tier of this repo; everything
    else, including the new Phase 2 pure-rendering-math tests, runs and passes).
36. [x] `openspec validate add-visualization-tooling --strict`.
37. [ ] `/review-openspec` — adversarial re-review before requesting user approval.
