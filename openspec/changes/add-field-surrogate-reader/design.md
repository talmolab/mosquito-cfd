# Design — add-field-surrogate-reader

## D1. `lo`/`hi`/`halo` semantics are preserved exactly

Domain clamping, `±inf` as "full extent", the `i_hi = min(max(i_hi, i_lo + 1), ddims)` index
arithmetic, and the read-the-full-level-0-covering-grid-then-slice strategy are carried over verbatim.
This is what makes the legacy wrapper behavior-identical. `flow_video.py` depends on the clipping
behaviour and derives its box origin from the returned `x`/`y`/`z` rather than from its own request —
its own docstring documents this, so it is not restated here.

**Correction found in review:** an earlier draft of the spec claimed the reader yields "at least one
cell per axis". That is **false** at the upper domain edge. Reproduced against the reference
arithmetic on the 6³ fixture:

| request | cells |
|---|---|
| `lo = hi = (2,2,2)` (interior) | `[1 1 1]` |
| `lo = hi = (6,6,6)` (upper edge) | `[0 0 0]` |
| `lo = (7,7,7), hi = (9,9,9)` (outside) | `[0 0 0]` |

The `ddims` clamp removes the floor the `i_lo + 1` term just applied. Zero-cell regions are reachable
and already handled downstream — `check_field_capture_velocity` has a dedicated empty-region error
path. The spec now states this accurately instead of promising a floor the code does not provide.

## D2. Three spec deltas are staleness corrections, generated mechanically

Three specs describe `extract_eulerian_box` as the place the `yt` read happens:

- `flapping-wing-grid-convergence`'s "(no new plotfile reader, no re-derivation)";
- `force-extraction`'s "`extract_eulerian_box` reads an AMReX plotfile via `yt.load` + …";
- `visualization-tooling`'s lazy-import requirement, which cites
  `stress_integral.extract_eulerian_box` as its **exemplar**.

The third was missed in the first draft and is the clearest case of the three: after the refactor
`extract_eulerian_box` contains no `import yt` at all, so the named exemplar stops demonstrating the
convention it is cited for.

All three `MODIFIED` blocks were produced by copying the source requirement byte-for-byte and applying
a single targeted edit, verified by `diff` to differ in exactly one hunk. Retyping a 95-line
requirement to reword one parenthetical is a silent-spec-corruption risk and was deliberately avoided.
**Anyone revising these must not re-wrap or retype the untouched lines** — the byte-exactness is what
makes the deltas reviewable.

Two specs are deliberately **not** modified:

- `force-extraction`'s "Plotfile Eulerian-box adapter" says "The package SHALL provide a yt-based
  adapter …" and names no module path. Satisfied as written, before and after.
- `force-surrogate`'s CC-F1 says the velocity check "SHALL be built on the existing
  `…extract_eulerian_box` reader rather than a new plotfile reader". This constrains **which function
  the caller calls**, not where that function's internals live, and the caller is unchanged (D3). It
  is therefore not stale by the same test that condemns the other three.

## D3. No in-repo caller is re-pointed at the new reader

CC-F1's `SHALL` (above) stays satisfied only while `check_field_capture_velocity` keeps calling the
wrapper.

There is a second, sharper reason. **21** test sites replace `extract_eulerian_box` as a *module
global* on `stress_integral` — 10 `monkeypatch.setattr(si, …)` in `test_stress_integral.py`, 9
string-path patches in `test_flow_video.py`, 2 in `test_make_flow_video_cli.py`. All four internal call
sites in `stress_integral.py` (`sphere_cv_drag_cd`, `check_field_capture_velocity`, and the two in
`sphere_cv_steadiness_fraction`) must keep resolving that module global, or those fakes are silently
bypassed and the affected tests pass while testing nothing.

**Not 24.** `test_wing_lev.py`'s 3 patches target `wing_lev`'s *own* module global, which this refactor
never touches; counting them inflates an argument that does not need them. The per-file tally and line
numbers live in `tasks.md`, not here and not in the spec, because they rot.

**Decision:** the wrapper is a hard contract, not a convenience. Enforced by an executable scenario
(sentinel reaches all four call sites), not by a code-reading task.

## D4. `yt` stays lazy, and the package `__init__` stays import-free

`import yt` lives inside `read_field_snapshot`. If `field_surrogate/snapshot.py` imported it at module
scope and `stress_integral.py` imported that module at top level, importing `stress_integral` would
eagerly pull in `yt`.

**A second import hazard, found in review.** `field_surrogate/__init__.py` must not eagerly import its
submodules, for two independent reasons:

1. **Import weight.** Measured at HEAD: `import mosquito_cfd.benchmarks.stress_integral` is 0.20 s
   with neither `pandas` nor `yt` loaded. `corpus` reaches `force_surrogate.dataset` → `pandas`. An
   `__init__` re-export of `FieldCorpus` would make the chain
   `stress_integral → field_surrogate/__init__ → corpus → pandas` and take `stress_integral` to
   ~1.2 s, propagating to `wing_lev`, `flow_video`, and the `make_flow_video` CLI.
2. **A real import cycle.** `benchmarks/__init__` imports `stress_integral`; after the refactor that
   reaches `field_surrogate`; an eager `corpus` import reaches `force_surrogate/__init__`, which
   imports `runner`/`sidecar`/`sweep`/`run_one_config` — **all four of which import
   `mosquito_cfd.benchmarks.metadata`**, re-entering a partially-initialized `benchmarks`. It happens
   not to raise today only because `benchmarks/__init__` imports `metadata` (line 11) before
   `stress_integral` (line 18). That is a landmine armed by statement order in two `__init__.py`
   files.

**Rules:** `field_surrogate/__init__.py` is docstring-only, no submodule imports; `stress_integral.py`
imports the submodule path directly, never through the package.

## D5. Multi-level plotfiles are refused, but the contract is AMR-ready

Every corpus deck sets `amr.max_level = 0`, and CC-F3's choice between interpolating onto a uniform
base grid and keeping the native multi-level structure as an unstructured point cloud is explicitly
**undecided**. This change does not decide it and does not pre-commit a `plot_int` value.

Dropping the check would not average levels: `covering_grid(level=0, …)` on a refined plotfile returns
the **coarse** data and ignores the refined patches, silently discarding the near-wing resolution the
refinement paid for. The refusal stays and the message names CC-F3.

The contract is shaped so the eventual decision is **additive**: `PointCloud.cell_volume` exists
(constant today) and `FieldSnapshot.max_level` is recorded rather than inferred. A future multi-level
reader returns the same `PointCloud` with a varying `cell_volume` and no downstream consumer changes.
The dense array view is structurally uniform-grid-only and will not be extended.

**Testing note.** The refusal must not be tested with a `MagicMock`: a mock's auto-created attributes
make `ds.index.max_level != 0` true even if the implementation reads the *wrong* attribute, so the
test would pass against a guard that is dead on every real plotfile. The test uses an explicit proxy
over the real fixture dataset overriding only `index.max_level`, plus a companion assertion that the
same proxy at `max_level == 0` **succeeds** — which is what proves the implementation reads the
attribute the proxy overrides.

## D6. The DoMINO adapter emits the volume half only

Stock DoMINO is a geometry→fields surrogate (see `proposal.md`, which is the single home for that
finding). Of `forward()`'s inputs this corpus can honestly supply **four** — `volume_mesh_centers`,
`grid`, and the two `global_params_*`. It additionally supplies `volume_fields`, which is the
datapipe's **target** rather than a `forward()` input. The rest — `geometry_coordinates`, `sdf_grid`,
`sdf_nodes`, `surf_grid`, `sdf_surf_grid`, `surface_mesh_*` — are not produced here.

Three specifics:

- **No batch dimension.** DoMINO's datapipe adds one; a second would be wrong.
- **Global parameters are caller-supplied.** Choosing the reference is a training-time normalization
  policy and belongs to F3, so the reader does not bake one in.
- **Absent keys are absent.** Zero-filling `sdf_nodes` would produce a dict that looks trainable and
  silently is not.

### Why not the full DoMINO dict?

The missing keys all require wing geometry at the snapshot's instant, and building them here would
mean either (a) reading IB markers from the plotfile — real plotfiles carry `particle_position_*`, but
**the synthetic fixture does not**, so this could not be tested cluster-free (**CC-F4**); or
(b) regenerating the wing pose from planform + kinematics, real geometry work whose phase convention
must match the solver's exactly or the wing is posed wrongly beside the right flow field, with nothing
crashing. Both belong with F3, where the encoder that consumes them exists.

The docstring records the two facts from `proposal.md`'s DoMINO section that a future reader would
otherwise rediscover the hard way, and a test asserts they are present — following the repo's existing
precedent of docstring-claim tests (`tests/test_no_false_diffused_ib_claim.py`).

## D7. No `run_metadata.json` and no units sidecar — decided, not overlooked

CC-1 requires every stage producing an artifact to emit `run_metadata.json` with a digest-pinned
`docker_image`; CC-5 requires a `<artifact>.units.json` sidecar for data-producing modules. **This
change writes no artifact.** The reader returns in-memory objects; the corpus-wide `.npy` export that
*would* produce files is deferred (D8).

Precedent for a stage legitimately skipping `capture_surrogate_run_metadata` is
`add-force-surrogate-sweep-config`'s design: a pure generator invokes no container, so a placeholder
digest would be **false provenance**. The same reasoning applies — a reader that runs no container has
no image digest to pin, and inventing one would violate the verification principle that "a metadata
field computable from the inputs alone is not evidence about a run".

Instead, `FieldSnapshot` carries `source` and `max_level` as in-memory provenance, and preserves the
plotfile's physical `time` so snapshots are never compared across mismatched phases.

**Consequence for F3/F4:** the first module in this track that writes a training artifact inherits both
obligations and must decide then whether `UNITS_VOCABULARY` needs a code-units entry. Flagged here so
it is not silently skipped later.

## D8. Corpus addressing is in; bulk export is out

`FieldCorpus` converts a filesystem-path API into a training-set API and supplies
`global_params_values` from the manifest. It reuses `load_manifest_configs` so a malformed manifest
raises identically on both paths, and it discovers steps from the `plt*` directories actually present
rather than trusting a deck's `plot_int` — a run can be truncated, as 15 of 27 configs were at
`ns.cfl = 0.3`.

`root` is caller-supplied because the corpus lives on cluster NFS, reachable per `project.md`'s three
documented mappings (`Z:\users\eberrigan\…` on Windows, `/mnt/hpi_dev/…` under WSL, `/hpi/hpi_dev/…`
on the cluster). Note that `sweep_provenance.json` records its CC-F1 plotfile under a fourth spelling,
`/z/users/…`, which matches none of the three — a pre-existing inconsistency, not something this
change should propagate into examples.

Bulk `.npy` export is deferred: it cannot be exercised at real scale locally, and it is a short loop
once F3 knows the shape it wants.

## D9. `project.md` accuracy fixes are in scope after all

An earlier draft deferred these to a follow-up issue. Review made the case for fixing them here, and
it is right on the decisive point: **the `D` ruleset is an instruction this change's own tasks depend
on.** A contributor writing `field_surrogate/` from `project.md`'s conventions section would not learn
that google-style docstrings are mandatory on every public symbol under `src/`, and would fail task
32's lint. Likewise `line-length: 100` instructs contributors to write lines `ruff format --check`
rejects. Wrong instructions in the authoritative conventions doc are worse than absent ones, and there
is direct precedent: PR #75 bundled exactly this class of `project.md` accuracy fix into a
section-addition docs PR.

Four verified inaccuracies, all fixed in this change:

| `project.md` | actual |
|---|---|
| `line-length: 100` | `pyproject.toml` says `88`, with `E501` ignored (the formatter owns length) |
| Rules "E, F, I, UP" | also selects `D` (pydocstyle, google), with `tests/**` exempt |
| dependency list | omits `pyarrow>=18.0.0` |
| lint command `uv run ruff check .` | fails with 27 errors; CI runs an explicit path list |

The directory tree also omits `visualization/` today, so adding only `field_surrogate/` would leave a
new single-package inconsistency. Both are added.

## D10. The frozen oracle, not a self-comparison

Review caught that comparing the refactored `extract_eulerian_box` to a re-pack of
`read_field_snapshot` is **tautological**: after the refactor the wrapper *is* that re-pack, so the
test compares an implementation to itself and proves nothing about behavioral continuity — which is
the entire claim of D1.

Equivalence is therefore demonstrated against a **frozen oracle**: the pre-refactor implementation
copied byte-for-byte into `tests/fixtures/legacy_extract_eulerian_box.py` with its source commit
recorded, and diffed across a region matrix rather than one request. A single full-extent request
exercises none of the clamping branches (`-inf` → `i_lo = 0`, `+inf` → `i_hi = ddims`), leaving the
entire index-arithmetic surface — 100% of the refactor's real risk — untouched.

Three guards additionally cover what array equality cannot see: exact Python **types** for `dx` and
`current_time` (an `ndarray → tuple` erosion passes `assert_array_equal` while silently changing the
published contract), the exact **key set** (so snapshot-only fields cannot leak in), and the **fp32
dtype-before-cast ordering** (no equality test against an FP64 fixture can ever detect a
cast-then-check regression).

## D11. The real-plotfile verification gap is closed before merge, not asserted away

CI cannot prove the refactor safe. The only unmarked yt read in the suite uses a 6³ single-FAB
unit-spacing origin-aligned fixture; everything exercising halo arithmetic, sub-box clipping,
multi-FAB covering grids, non-unit `dx`, or a non-zero domain origin is `requires_plotfile` and
auto-skips on the runner. Additionally, three `raise` paths that this change moves wholesale — the
`max_level` guard, the missing-fields guard, and the fp32 guard — have **no** CI coverage at HEAD
(confirmed by grep: no test references their messages, and the one that does is `requires_plotfile`).

Mitigation, all before merge:

1. Close as much of the gap in CI as the fixture allows — the region matrix of D10. Clipping, the
   floor, and halo arithmetic are pure index math and need no cluster data.
2. Run the suite with the plotfile root mounted and record how many previously-skipped tests actually
   **ran** (`-rs`), per the project's own principle that a mandatory check with no recorded result is
   indistinguishable from one never run.
3. Bit-exact A/B against the frozen oracle on real plotfiles across the full region matrix —
   zero tolerance, not `allclose`. This is the only check covering multi-FAB grids, non-unit `dx`, and
   non-zero origins.
4. File a follow-up issue for a second committed fixture with anisotropic `dx`, a non-zero origin, and
   more than one FAB — the structural fix for "CI's only plotfile is degenerate", out of scope here.

## D12. Delivered as two PRs, split at the refactor boundary

This repository squash-merges, so a single PR collapses to one commit on `main` and `git revert`
would take the whole feature with it. The risk in this change is not evenly distributed: the new
package is purely additive and cannot regress any existing caller, while the `extract_eulerian_box`
delegation touches the only cluster-touching reader in the repo and is the one thing CI cannot fully
prove safe (D11).

- **PR A — additive.** The complete OpenSpec change directory (so `openspec validate --strict` passes
  on a whole change in one PR), the new `field_surrogate` package, its tests, and the docs that do
  not depend on the refactor. Not one existing line of `src/` changes.
- **PR B — the refactor.** The frozen oracle, the differential and sentinel tests, the delegation
  itself, the four stale docstrings, the roadmap CC-F2 note and F2 status glyph, the CHANGELOG entry,
  and the real-plotfile verification of D11.

PR B is small enough to read line by line and, critically, small enough that reverting its squashed
commit restores the previous reader with zero collateral — the new package stays in place and remains
usable by F3. Precedent for multi-PR OpenSpec changes in this repo: #73/#74/#75
(`add-visualization-tooling`), #85/#86 (`add-fine-corpus-field-capture`).

The OpenSpec change is archived only after **both** PRs merge, since the delegation requirement in the
`field-surrogate` spec is not satisfied until PR B lands.
