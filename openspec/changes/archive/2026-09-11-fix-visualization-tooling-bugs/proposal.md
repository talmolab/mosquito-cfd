# Fix visualization-tooling bugs (issues #87, #88)

## Why

Two real, reproducible bugs in `src/mosquito_cfd/visualization/` were found during
`/submit-cluster-sweep`'s pre-full-sweep visual review of the `examples/prelim_sweep_fine` smoke
run (workflow `force-surrogate-smoke-mgqzm`, config `s35_f085_p30`). Both are pure Python
visualization/reporting bugs with no effect on the CFD simulation, IAMReX inputs, or any committed
force/plotfile data — but both silently produce wrong output today with no error, no crash, no
non-zero exit code.

**Issue #87** — `kinematics_video._span_tip_index` picks the marker at max `|span|`, tie-breaking
by nearest chord-axis position to `x=0`. The committed `wing.vertex` has an exact 3-way tie on
*both* sides of the wing (`y = -1.475` and `y = +1.475`), and `np.argmin` always resolves a tie to
the first array occurrence — the `y = -1.475` side, independent of wing geometry. For
`examples/prelim_sweep_fine`'s convention (`center = (4, 2, 4)`, `hinge = (4, 0.5, 4)` — hinge on
the negative-`y` side of center), this makes the function pick the **root** marker (next to the
hinge) as "tip," not the true tip on the far side. Confirmed visually: the rendered tip-marker dot
sits at the hinge. This corrupts the `span_arm`/`chord_axis_extent` fields written to
`<label>_kinematics_preview_metrics.json` (observed `span_arm=0.025` instead of the correct ~2.98)
and the video's own tracked-tip overlay, for every config sharing this vertex file with a
hinge/center pair that doesn't coincide in `y`.

**Issue #88** — `flow_video.build_flow_video`'s `lev-3d` field mode (the Q-criterion vortex
isosurface video) never actually shows the vortex. The isosurface data itself is correct (verified
directly: `render_lev_frame` returns valid triangles/facecolors with strong Q values at multiple
timesteps). The bug is in `_draw_wing_scene`'s interaction with the shared Axes3D's
`computed_zorder=False` setting — correct for `combined-3d`/`zvelocity-3d`, where the field is a
thin 2-D slice plane and "wing always in front" is physically true, but wrong for `lev-3d`, whose
isosurface is a real 3-D volume that interleaves in depth with the wing. The static
zorder (wing 20–22 vs. mesh 1) makes the wing fully occlude the isosurface every frame, silently —
the script exits 0 and writes a valid, non-empty mp4.

The confirmed fix for #88 is not a guess: the original vault script that produced the
proven-correct reference video this mode was generalized from
(`C:\vaults\physics surrogate models\duncan-meeting-2026-08-11\videos\make_t3c_fine_lev_3d.py`,
which rendered `t3c-fine-lev-3d.mp4`) renders `lev-3d` differently in two specific ways — see
`design.md` D3 for the full mechanism and why both are reproduced together.

## What Changes

- **`kinematics_video._span_tip_index`** gains hinge-awareness: among markers tied at max `|span|`,
  select the one **farthest from the hinge** (the true tip, away from the pivot), falling back to
  the existing nearest-chord-axis-to-zero rule only as a secondary tie-break. `build_kinematics_video`
  passes the hinge through in the correct (local, pre-`center`-offset) reference frame.
- **`flow_video.build_flow_video`**'s 3-D Axes3D creation makes `computed_zorder` conditional on
  `field_mode`: unchanged (`False`) for `combined-3d`/`zvelocity-3d`, dropped (mplot3d's
  `True` default) for `lev-3d`.
- **`flow_video.render_lev_frame`**'s returned facecolors carry a documented, overridable alpha
  (default matching the vault's `0.65`) instead of the colormap's opaque default, following the
  same "documented CLI-overridable rendering constant, never auto-computed" convention this
  capability already established for `Q_THRESHOLD`/`VORT_VMIN`/`VORT_VMAX` (`design.md` D4 in the
  archived `add-visualization-tooling` change).
- Regression tests for both bugs, and a correction to an existing test
  (`test_chord_axis_extent_matches_root_hinge_arm`) whose own "expected value" computation
  duplicated issue #87's buggy tie-break logic and would otherwise keep passing against a
  self-consistently-wrong implementation.

## Impact

- **Affected specs**: `visualization-tooling` (two new requirements — see `specs/visualization-tooling/spec.md`)
- **Affected code**: `src/mosquito_cfd/visualization/kinematics_video.py`,
  `src/mosquito_cfd/visualization/flow_video.py`, `scripts/make_flow_video.py` (new
  `--lev-mesh-alpha` CLI flag)
- **Affected tests**: `tests/test_kinematics_video.py`, `tests/test_flow_video.py`
- **Not affected**: the CFD solver, IAMReX inputs, any committed corpus/force/plotfile data, Docker
  images, or CI beyond the existing Python test suite. `examples/prelim_sweep_fine`'s in-progress
  cluster sweep (`force-surrogate-sweep-pzdhl`) is unrelated and untouched by this change.
