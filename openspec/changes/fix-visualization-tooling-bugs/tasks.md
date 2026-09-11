## 1. Fix #87 — `_span_tip_index` hinge-awareness

- [x] 1.1 **Test first**: add
      `test_span_tip_index_picks_side_farthest_from_hinge_on_exact_tie` to
      `tests/test_kinematics_video.py`, importing `_span_tip_index` directly. Use
      `examples/flapping_wing/wing.vertex`'s real local markers, hinge expressed in the local frame
      as `(4.0, 0.5, 4.0) - (4.0, 2.0, 4.0) = (0.0, -1.5, 0.0)`. Assert the returned index's local
      `y` is `+1.475` (positive side), not `-1.475`. Run it and confirm it **fails** against the
      current implementation (it will resolve to the `-1.475` side).
- [x] 1.2 **Test first**: add `test_span_tip_index_unique_max_span_ignores_hinge` — a small synthetic
      markers array with one unique max-`|span|` marker and an arbitrary hinge; assert that marker's
      index is returned regardless of hinge position. Confirm it passes against the current
      implementation too (a non-regression control case).
- [x] 1.3 **Test first**: add
      `test_span_tip_index_falls_back_to_nearest_x_when_hinge_distances_also_tie` — a synthetic
      markers array with 2+ candidates tied at max `|span|` *and* tied at equal distance from the
      hinge (e.g. hinge equidistant between two candidates at the same `|span|`); assert the
      candidate nearest `x=0` wins, exercising `design.md` D2's secondary tie-break. This case is
      vacuously true against the current implementation (which always falls back to the nearest-`x`
      rule), so it isn't expected to fail pre-fix — it exists to pin the post-fix fallback behavior
      and must still pass after 1.5's implementation.
- [x] 1.4 **Test first**: fix `tests/test_kinematics_video.py::test_chord_axis_extent_matches_root_hinge_arm`'s
      own hand-rolled "expected" tip computation (lines ~111-128), which currently duplicates the
      buggy nearest-`x=0`-only tie-break — update it to compute the hinge-farthest index instead
      (using `_VALIDATED_CENTER`/`_VALIDATED_HINGE`, which already match
      `examples/prelim_sweep_fine`'s real convention). Also add an explicit
      `assert result["span_arm"] == pytest.approx(expected_span_arm, rel=0.01)` alongside the
      existing `chord_axis_extent` assertion, so the regression is caught directly rather than only
      transitively through the derived trigonometric formula. Run it now and confirm it **fails**
      against the current buggy `_span_tip_index` (the corrected expected `span_arm` is ~2.98; the
      current implementation returns ~0.025).
- [x] 1.5 Implement the fix: change `_span_tip_index(local_markers)` to
      `_span_tip_index(local_markers, hinge)`; among tied max-`|span|` candidates, select
      `np.argmax(np.linalg.norm(local_markers[candidates] - hinge, axis=1))`, falling back to the
      existing nearest-`x=0` rule only among any residual tie on that distance. Update the
      docstring to describe hinge-farthest selection, matching `design.md` D2. Also update the
      `_TIE_TOLERANCE` module-level comment (~lines 49-51), which currently restates the *old* rule
      ("picking the one nearest `x=0` keeps the tip's own chord-axis rest offset minimal") — correct
      it to describe the hinge-farthest rule so it doesn't contradict the corrected docstring.
- [x] 1.6 Update the call site in `build_kinematics_video` (~line 211) to pass
      `hinge_arr - center_arr` (the hinge in `local_markers`'s own frame) as the new argument.
- [x] 1.7 Run `uv run pytest tests/test_kinematics_video.py -v` — confirm every test (1.1-1.4, all
      new/corrected) passes.
      **Result**: 13/13 passed.
- [x] 1.8 Verify `flow_video.py` and `wing_phase_diagnostic.py` do not duplicate this same
      tie-break bug. Per issue #87, the `span_arm`-equivalent computation that's unaffected is in
      `wing_phase_diagnostic.py` (computed directly from `center - hinge`, no tip-marker search;
      `flow_video.py` has no `span_arm` concept at all) — confirm by reading, not by guessing; no
      code change expected here, but note the finding in this task's completion.
      **Finding confirmed**: `wing_phase_diagnostic.py:100` computes
      `span_arm = center_arr[axis_idx] - hinge_arr[axis_idx]` directly, no tip-marker search, no
      tie-break. `flow_video.py` has no `span_arm` concept anywhere (grep confirms only
      `kinematics_video.py` and `wing_phase_diagnostic.py` reference `span_arm`). No code change
      needed.
- [x] 1.9 Run `uv run ruff check src/mosquito_cfd/visualization/kinematics_video.py tests/test_kinematics_video.py`
      and `uv run ruff format --check` on the same files.
      **Result**: ruff check clean; ruff format applied one reflow to the new tie-break test's
      fixture array (cosmetic only, tests re-verified green after).
- [x] 1.10 **Visual verification** (unit tests alone are not sufficient here — this bug was only
      ever caught by looking at the rendered video, not by any prior unit test): after 1.5/1.6 land,
      actually render `scripts/make_kinematics_video.py` against the real bug scenario —
      `--config s35_f085_p30 --corpus-dir examples/prelim_sweep_fine` (Z: workspace mount; the exact
      config both issues were found on) or explicit `--vertex-path examples/flapping_wing/wing.vertex
      --center 4.0 2.0 4.0 --hinge 4.0 0.5 4.0` overrides — producing a real
      `<label>_kinematics_preview.mp4`. Extract at least one still frame to a PNG (`imageio_ffmpeg`/
      `ffmpeg -i <mp4> -frame_pts 1 -vf "select=eq(n\\,0)" frame.png`, or read a frame directly via
      `imageio`) and visually inspect it (via the `Read` tool) to confirm the black tip-marker dot
      sits at the far edge of the wing disc, clearly separated from the hinge dot — not coincident
      with or adjacent to it, which is what the pre-fix bug looked like (see issue #87's own
      description: "the rendered black tip-marker dot sits right next to the hinge"). Also confirm
      `<label>_kinematics_preview_metrics.json`'s `span_arm` is ~1.5, not ~0.025. Record the
      observation in the PR description, not just "tests pass."
      **Result**: rendered with the `s35_f085_p30` kinematics (`--center 4.0 2.0 4.0 --hinge 4.0
      0.5 4.0 --stroke-amp-deg 35.0 --pitch-amp-deg 30.0 --frequency-fstar 0.85`) using
      `examples/flapping_wing/wing.vertex`. Post-fix `span_arm=2.9756` (not the docs' earlier
      "~1.5" estimate, which only accounted for one leg of the hinge-to-tip distance — the actual
      hinge-to-tip distance spans the full hinge-to-center-to-tip offset; corrected in
      `proposal.md`/`spec.md` too). Confirmed pre-fix (stashed working tree) gives
      `span_arm=0.025000`, exactly matching issue #87's own reported observed value. Extracted
      stills from both renders: the pre-fix frame shows no visible dashed tip-trajectory line (it
      is collapsed to a sub-pixel loop coincident with the hinge dot); the post-fix frame shows a
      clearly visible dashed trajectory arc extending well away from the hinge dot. Matches issue
      #87's description exactly.

## 2. Fix #88 — `lev-3d` wing/isosurface z-order and mesh transparency

- [x] 2.1 **Test first**: in `tests/test_flow_video.py`, narrow
      `test_3d_scenes_disable_computed_zorder_so_wing_renders_above_the_field`'s parametrization
      down to `["combined-3d", "zvelocity-3d"]` only (still asserting
      `computed_zorder is False` for both) — confirm this narrowed test currently passes (no
      implementation change needed for this part).
- [x] 2.2 **Test first**: add `test_lev3d_scene_does_not_force_computed_zorder_false` — same
      `build_flow_video(field_mode="lev-3d", ...)` call/spy pattern as the test in 2.1, but assert
      the captured `add_axes` kwargs for the 3-D call do NOT contain `computed_zorder=False` (i.e.
      the key is absent or `True`). Confirm it **fails** against the current implementation.
- [x] 2.3 **Test first**: add `test_render_lev_frame_facecolors_are_translucent` — call
      `render_lev_frame` directly with a synthetic `u`/`v`/`w`/`dx` fixture that produces a
      non-`None` result (reuse `_synthetic_lev_box`-style helpers already in the test file), assert
      `result["facecolors"][:, 3]` is not all `1.0` and matches the new documented default alpha
      constant (`DEFAULT_LEV_MESH_ALPHA`). Confirm it **fails** against the current implementation
      (colormap default is opaque).
      (Implemented as two tests: `test_render_lev_frame_facecolors_are_translucent_by_default` and
      `test_render_lev_frame_mesh_alpha_is_overridable`, covering both the default and an explicit
      override.)
- [x] 2.4 **Test first**: add `test_lev3d_mesh_alpha_override_reaches_the_rendered_collection` — call
      `build_flow_video(field_mode="lev-3d", mesh_alpha=<custom value>, ...)` with the
      `_synthetic_lev_box` fixture, spy `Axes3D.add_collection3d` (following the pattern the file
      already uses for spying on axes/collection construction), and assert the captured
      `Poly3DCollection.get_facecolors()[:, 3]` equals the custom alpha, not the default `0.65` —
      confirming `mesh_alpha` is actually threaded end-to-end through `build_flow_video`/`_draw_lev`,
      not just accepted by `render_lev_frame` in isolation. Confirm it **fails** against the current
      implementation (no `mesh_alpha` parameter exists yet).
      (Implemented by spying `Poly3DCollection.__init__`'s `facecolors` kwarg instead of
      `get_facecolor()` post-render — `get_facecolor()` requires a completed 3-D projection pass
      and raises `AttributeError` once the figure is closed, which happens before the test can
      read it back.)
- [x] 2.5 Implement: in `build_flow_video`, make the `computed_zorder` kwarg passed to
      `fig.add_axes(..., projection="3d", ...)` conditional on `field_mode` — `False` for
      `combined-3d`/`zvelocity-3d`, omitted for `lev-3d` (per `design.md` D3/D4). Update the inline
      comment at ~lines 492-497 justifying `computed_zorder=False` (currently claims unconditionally
      that "the wing... always draws above the field... regardless of view angle") to scope that
      claim to `combined-3d`/`zvelocity-3d` only, since it becomes false for `lev-3d` once this task
      lands.
- [x] 2.6 Implement: add `DEFAULT_LEV_MESH_ALPHA = 0.65` as a module-level, documented,
      CLI-overridable constant in `flow_video.py` (alongside `DEFAULT_Q_THRESHOLD`/
      `DEFAULT_VORT_VMIN`/`DEFAULT_VORT_VMAX`); apply it to `render_lev_frame`'s returned
      `facecolors[:, 3]` via a new `mesh_alpha` parameter (documented in `render_lev_frame`'s own
      `Args:` docstring block, matching its existing per-parameter entries for `q_threshold`/
      `vort_vmin`/`vort_vmax`). Thread `mesh_alpha` through `build_flow_video` (documented in its
      `Args:` docstring block the same way) and `scripts/make_flow_video.py`'s CLI as a
      `--lev-mesh-alpha` flag, the same way `q_threshold`/`vort_vmin`/`vort_vmax` are already
      threaded and documented in `--help`.
- [x] 2.7 Run `uv run pytest tests/test_flow_video.py -v` — confirm every test (narrowed 2.1, new
      2.2/2.3/2.4, and all pre-existing tests) passes.
      **Result**: 31/31 passed.
- [x] 2.8 Run `uv run ruff check src/mosquito_cfd/visualization/flow_video.py scripts/make_flow_video.py tests/test_flow_video.py`
      and `uv run ruff format --check` on the same files.
      **Result**: clean, no changes needed.
- [x] 2.9 **Visual verification** (this bug was only caught by looking at the rendered video, and
      the isosurface data itself was already confirmed correct pre-fix — a passing unit test on
      `render_lev_frame` or axes kwargs alone does not prove the *rendered frame* actually shows the
      vortex): after 2.5/2.6 land, actually render `scripts/make_flow_video.py --field-mode lev-3d`
      against real plotfiles — either `examples/flapping_wing/t3c-fine` (Z: workspace mount; the
      same plotfiles the original vault video was rendered from, e.g. `plt00500`/`plt02300`/
      `plt04200`, matching issue #88's own spot-checked frames) or the completed
      `examples/prelim_sweep_fine/runs/s35_f085_p30` smoke run (the exact config the bug was found
      on; read-only — do not disturb the in-progress `force-surrogate-sweep-pzdhl` cluster sweep or
      any of its other configs). Extract several frames from the resulting mp4 to PNGs across
      different timesteps/phases and visually inspect them (via the `Read` tool) to confirm the
      Q-criterion isosurface (a translucent curled tube/mesh near the wing's leading edge) is now
      visible in at least some frames, not fully hidden behind the opaque wing disc as before (issue
      #88: "only the rotating wing disc, never the vortex, across the whole cycle"). Record the
      observation in the PR description, not just "tests pass."
      **Result**: rendered against the real `examples/flapping_wing/t3c-fine` plotfiles (21
      timesteps, `plt00000`-`plt02000`) with the vault's own kinematics (center=(4,2,4),
      hinge=(4,0.5,4), stroke 70°, pitch 45°, f*=1.0). Extracted 3 frames at t=0.1116, t=0.3605,
      t=0.5931: all three clearly show a translucent purple/blue Q-criterion isosurface (a curled
      tube extending well beyond the wing disc at t=0.1116/0.5931; a thin translucent sliver
      peeking around the wing's edge at t=0.3605), never fully hidden by the opaque wing. A direct
      pre-fix re-render for contrast was not completed (junctioning a subset of the t3c-fine
      plotfiles for a faster comparison run failed — `yt.load` cannot resolve a directory junction
      pointing across the Z: network mount, `OSError: [WinError 4392]`) — the pre-fix
      fully-occluded behavior is independently confirmed by (a) issue #88's own visual observation
      against this same data ("only the rotating wing disc, never the vortex, across the whole
      cycle") and (b) the pre-fix `computed_zorder=False` being unconditionally applied to lev-3d,
      captured directly by the original (now-narrowed) `test_3d_scenes_disable_computed_zorder_...`
      test before this fix.

## 3. Full-suite verification and archival

- [x] 3.1 Run `uv run pytest tests/ -v` (full suite) and confirm no regressions elsewhere.
- [x] 3.2 `openspec validate fix-visualization-tooling-bugs --strict` passes.

## 4. Delivery plan (not code — guidance for PR structure)

Sections 1 and 2 touch fully disjoint files (`kinematics_video.py`+its test vs. `flow_video.py`/
`scripts/make_flow_video.py`+its test) and have unrelated root causes. A two-PR split (one per
issue) was considered — matching this repo's `add-visualization-tooling` precedent
(PR1(#73)/PR2(#74)/PR3(#75) under one OpenSpec change) — but the user chose a **single combined
PR** instead, referencing both issues, given both fixes are small and were reviewed/implemented
together in one pass. Ship as one PR closing both #87 and #88, including Section 3's full-suite
verification and archiving this OpenSpec change.
