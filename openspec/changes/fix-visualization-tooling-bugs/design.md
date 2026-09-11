## D1. `_span_tip_index`'s hinge argument is expressed in the *local* (pre-`center`-offset) frame

**Problem:** `build_kinematics_video` calls `_span_tip_index(local_markers)` with `local_markers`
straight from `read_vertex_file` (centered on the wing's own local origin, before `center_arr` is
added). `hinge_arr`, by contrast, is a global/world position (`kin_kwargs["hinge"]`, e.g.
`(4.0, 0.5, 4.0)`). Passing `hinge_arr` to a function operating on `local_markers` without
translating frames would compare a local-frame array against a global-frame point — coincidentally
not a crash (both are shape `(3,)`), but silently wrong, since `hinge_arr` is offset by whatever
`center_arr` is (never zero for any real config).

**Decision:** `_span_tip_index` takes a `hinge` argument in the **same local frame** as
`local_markers`, i.e. the caller passes `hinge_arr - center_arr`. This keeps the function itself
frame-agnostic and testable in isolation (it never needs to know about `center`), and mirrors how
`local_markers` itself is already local-frame. `build_kinematics_video` is the one call site that
knows about both frames and does the subtraction.

## D2. Tie-break order: farthest-from-hinge first, nearest-chord-axis-to-zero second

**Problem:** the current tie-break (nearest `x=0`) has no hinge awareness at all. The committed
`wing.vertex`'s exact 3-way tie means the fix must define a total order over the tied candidates
that doesn't itself depend on which side happens to be scanned first.

**Decision:** among candidates tied at max `|span|` (within the existing `_TIE_TOLERANCE`), select
whichever is farthest from `hinge` (Euclidean distance in the local frame). This directly encodes
"the tip is the point on the wing farthest from the pivot it rotates about," which is the physical
definition of `span_arm` the function's own docstring already claims. The existing nearest-`x=0`
rule is kept as a **secondary** tie-break, for the residual (currently unobserved, but not
provably impossible for an arbitrary future `.vertex` file) case where two candidates are tied at
both max `|span|` and identical distance from the hinge.

## D3. Reproducing the vault script's lev-3d rendering exactly, not a novel approach

**Problem:** the issue's "Suggested fix" section listed three options (per-object depth sort,
per-triangle depth-sorted wing, wing transparency) without prescribing one. Rather than pick
one speculatively, the vault directory
(`C:\vaults\physics surrogate models\duncan-meeting-2026-08-11\videos\make_t3c_fine_lev_3d.py`) was
read directly — it is the actual working script `flow_video.py`'s `lev-3d` mode was generalized
from, and its output video is the field-capture change's own referenced proof of correctness.

**Decision:** reproduce both of that script's specific choices, since they were tuned together
(the transparency compensates for cases where the per-object depth sort still gets the ordering
"wrong" from a strict z-buffer perspective, e.g. a wing polygon whose face is nearer camera than
the mesh's average centroid but farther than some individual mesh triangles — with translucency,
the mesh stays visible either way):

1. `lev-3d`'s `Axes3D` omits `computed_zorder=False` (uses mplot3d's default `True`).
2. `render_lev_frame`'s facecolors get `alpha = 0.65` applied (matching the vault's own value)
   rather than the colormap's opaque default.

This is a **new documented CLI-overridable constant** (`DEFAULT_LEV_MESH_ALPHA = 0.65`), not a
hardcoded literal, following the same convention `Q_THRESHOLD`/`VORT_VMIN`/`VORT_VMAX` already
established in this capability (`design.md` D4, archived `add-visualization-tooling` change) — a
different config's isosurface geometry may benefit from a different alpha, and the value is
empirical tuning, not a universal constant.

**Alternative considered and rejected:** per-triangle depth-sorting the wing alongside the mesh
(the issue's third option) would be more physically exact but is meaningfully more implementation
complexity for a visualization-only diagnostic script, is unrequested scope beyond what's needed to
match the already-proven-correct reference rendering, and — critically — is *not* what produced the
video this mode is supposed to reproduce. Reproducing the proven approach is preferred over a novel
one with unverified visual output.

## D4. `combined-3d`/`zvelocity-3d` are unaffected

Both fixes are scoped strictly to `lev-3d`. `combined-3d`/`zvelocity-3d` keep
`computed_zorder=False` exactly as today (the thin-slice-plane-vs-wing depth relationship is
genuinely static there, unlike `lev-3d`'s two real 3-D volumes) and `render_lev_frame`'s new alpha
parameter is not invoked by either of those modes (they use `render_velocity_slice_frame`, a
separate function, untouched by this change).
