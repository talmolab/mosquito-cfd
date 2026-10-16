# add-field-surrogate-reader

Stage-2 roadmap row **F2** (`docs/field_surrogate/roadmap.md`). **Local, cluster-free.** Touches
**CC-F2** (reuse the existing reader), **CC-F4** (cluster-free fixtures), and bears on **CC-F1**
(the field-capture velocity check must keep using `extract_eulerian_box`) and **CC-F3** (the AMR
decision, left open by design). No solver change, no deck change, no Docker change, no new dependency.

## Why

Stage 2's encoder (F3) needs flow-field snapshots as training input, and nothing in the repository
produces them in a form an ML pipeline can consume. What exists is
`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` — a `yt`-based Eulerian-box extractor
built for the T3b LEV diagnostic, now also used by `benchmarks/wing_lev.py`,
`visualization/flow_video.py`, and `examples/flapping_wing/make_lev_figure.py`. Per **CC-F2** this is
the thing to adapt. It returns a flat dict of six hardcoded fields with no way to request `density` or
`tracer`; it has no point-cloud view; it carries no provenance beyond the values themselves; and it is
addressed by filesystem path, so there is no "give me config X at step Y" interface over the
27-config corpus.

## What changes

A new package `src/mosquito_cfd/field_surrogate/`:

| Module | Contents |
|---|---|
| `snapshot.py` | `FieldSnapshot`, `PointCloud`, `read_field_snapshot()` — the single covering-grid read path |
| `corpus.py` | `FieldCorpus` — `(config_id, step)` → snapshot, kinematics from the sweep manifest |
| `domino_adapter.py` | `to_domino_volume()` — DoMINO volume-half key emission, no `physicsnemo` import |

`extract_eulerian_box` is refactored to **delegate** to `read_field_snapshot` and re-pack its existing
flat dict. Unchanged import path, signature, and keys; every in-repo caller keeps going through it.

## What this change deliberately does not do

`geometry_coordinates` (synthesizable from `generate_planform()` + `wing_kinematics.rotation_matrix(t)`);
`sdf_grid`/`sdf_nodes`; the `surface_mesh_*` arrays; corpus-wide `.npy` export; any AMR/multi-level
handling; any encoder, training, or figure code; reading the real corpus. See `design.md` D6 and D8.

## Scoping input: what DoMINO actually consumes

Verified 2026-09-21 against `NVIDIA/physicsnemo` `main` and the PhysicsNeMo 26.05 API docs, rather
than assumed from the roadmap. **Pin this version** — the finding is falsifiable only against a stated
revision.

- `DoMINO.forward()` consumes `geometry_coordinates`, `volume_mesh_centers`, `sdf_nodes`, `grid`,
  `sdf_grid`, `surf_grid`, `sdf_surf_grid`, `surface_mesh_centers`/`normals`/`areas`, and
  `global_params_values`/`_reference` — and **returns** `(volume_output, surface_output)`.
- **Flow-field values are predicted outputs, not inputs.** `volume_fields` is the datapipe's *target*.
- The submodule producing a latent is `GeometryRep`, which encodes **geometry**, not a flow snapshot.
- Its datapipe ingests STL + VTP + VTU, writes preprocessed `.npy` dicts, and adds the batch dimension
  itself.

**So the roadmap's F3 row — "DoMINO encoder: field snapshot → latent z" — does not describe stock
DoMINO.** Resolving that is F3's job (CC-4 honesty), not this change's. Its consequence here is that
F2 commits to a framework-neutral contract and emits DoMINO key names only through a thin,
explicitly-bounded volume-half adapter (D6).

## Impact

**Affected specs (3 modified, 1 added):**

- **Added:** `field-surrogate`.
- **Modified:** `flapping-wing-grid-convergence`, `force-extraction`, `visualization-tooling` — three
  staleness corrections, each one hunk (D2). No requirement is removed and no scenario is weakened.
  One prohibition is **deliberately narrowed**: `flapping-wing-grid-convergence`'s "no *new* plotfile
  reader" becomes "no *second* plotfile reader", because this change does create a new reader module
  while preserving the single-read-path property the prohibition exists to protect. That is a
  relaxation of the literal text, stated here rather than glossed (D2).
- **Unmodified but load-bearing:** `force-extraction`'s "Plotfile Eulerian-box adapter" requirement is
  capability-level ("the package SHALL provide a yt-based adapter") and names no module path, so the
  refactor satisfies it unchanged. `force-surrogate`'s CC-F1 requirement names `extract_eulerian_box`
  explicitly and stays satisfied because no caller is re-pointed; its "rather than a new plotfile
  reader" wording constrains the *caller*, not the reader's internals, so it is not stale (D2).

**New code:** `src/mosquito_cfd/field_surrogate/{__init__,snapshot,corpus,domino_adapter}.py`;
`tests/test_field_surrogate_{snapshot,corpus,domino_adapter}.py`;
`tests/fixtures/legacy_extract_eulerian_box.py` (the frozen pre-refactor oracle).

**Modified code:** `src/mosquito_cfd/benchmarks/stress_integral.py` — the delegation refactor and four
now-inaccurate docstrings; `src/mosquito_cfd/benchmarks/wing_lev.py` — one inaccurate docstring line.
This is the only existing, heavily-depended-on module the change edits, and D3 is devoted to its risk.

**CI:** `lint` and `test` only. `src/` and `tests/` are already in the lint job's hardcoded path list,
so `ci.yml` needs no edit. `yt` is a base dependency installed in CI, so the new fixture-based tests
gate CI rather than auto-skipping. Verified empirically: `uv lock --check` passes, `uv build --wheel`
already picks up undeclared subpackages, and `docker/Dockerfile.python` copies `src/` wholesale.

**Dependencies:** none added.

**Docs:** `openspec/project.md` gains `field_surrogate/` (and the already-missing `visualization/`) in
its directory tree, a short section, and four verified accuracy fixes (D9);
`tests/fixtures/README.md` gains the `lev_boxlib_plt/` entry it has always lacked;
`docs/field_surrogate/roadmap.md` gets a CC-F2 resolution note and the F2 status glyph; plus the
usual `docs/CHANGELOG.md` entry at pre-merge.

**Verification gap, stated up front:** CI cannot prove the refactor is safe on real plotfiles —
everything that exercises halo arithmetic, multi-FAB covering grids, non-unit `dx`, or a non-zero
domain origin is `requires_plotfile` and auto-skips on the runner. Tasks 33–34 close this with a
bit-exact A/B against the frozen oracle on real Z: plotfiles before merge (D11).
