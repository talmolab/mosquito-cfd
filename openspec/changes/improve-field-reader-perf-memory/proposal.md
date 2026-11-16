# improve-field-reader-perf-memory

## Why

F3's training loop will read thousands of field snapshots, from several DataLoader workers, on a
24 GB A5000 or over cluster NFS. #112 and #120 measured filesystem calls and memory the F2 reader does
not need. This change removes them before F3 is written around them, keeping every returned array
bit-identical.

Headline, measured on `main` (`90b2a72`). The setup:
- a synthetic 256×128×256 single-FAB plotfile with six FP64 fields of 67 MB each;
- traced with `tracemalloc`;
- **automatic GC enabled**, as in production.

Method and the other sizes are in design.md D4.

| full-extent read (each read after a warm-up) | peak per read | held after reads 1, 2, 3¹ | dataset alive on return |
|---|---|---|---|
| today | 926–1330 MB | 457, 511, 565 MB | yes |
| this change | 927 MB (prototype) | 8, 9, 9 MB (prototype) | no |

¹ Memory still traced once the call returns, not counting the returned arrays. Today the six cached
fields (403 MB) sit inside a yt reference cycle. Each read's cycle then waits for Python's
old-generation collection, which runs irregularly, so at least one read's cache stays held after
the call returns. The "today" row is `read_field_snapshot` at `90b2a72` (task 0.2). The "this
change" row comes from a prototype of the teardown, and task 8.4 replaces it with the
implemented reader's numbers.

The full collection costs 69–89 ms of a 4.7–5.5 s read.

The returned data is unchanged. Each field is copied before yt's cached copy is dropped. The full
garbage collection added after each read frees only objects nothing can reach any more (D4).

Two items listed as open on #112 have **already been done on `main`**, in #105's final merge
(`1146552`). This change pins them; it does not redo them.
- `FieldCorpus._configs()` already parses the manifest once per instance.
- `to_domino_volume`'s `grid` is already a free view of `volume_mesh_centers`.

The post-#140 comment on #112 says both are still open; task 8.7 corrects it.

## What Changes

- **`FieldCorpus` listing (#112 item 1).**
  - The run directory is listed with `os.scandir`, and each entry's type comes from its `DirEntry`.
    `steps()` then costs one listing and no per-entry `stat`.
  - Paths are still returned as `pathlib.Path`.
  - The duplicate-step error, the non-directory filter, and #140's canonical fast path are
    unchanged (design.md D1).
- **Plotfile names (#145).** A plotfile name is `plt` followed by ASCII digits only, matched against
  the whole name. This excludes `plt١٠٠` (#145). It also excludes a POSIX name with a trailing
  newline, which today's `$` anchor accepts (D2).
- **Covering-grid teardown (#120, absorbing #112 item 3).** `read_field_snapshot`:
  - drops each field from yt's cache once it has been copied;
  - clears the covering grid;
  - drops its yt references;
  - runs a full `gc.collect()` before returning, on every path that loaded the plotfile (D4).
- **Smaller items (#112 item 5).**
  - **Zero-cell regions.** A region with zero cells builds no covering grid and reads no field.
    It still runs every plotfile guard first. Today it reads all six fields (403 MB of field data
    at 256×128×256) to return nothing (D5).
  - **`cell_volume`.** `PointCloud.cell_volume` becomes a read-only zero-stride broadcast instead
    of an `N`-element buffer of one repeated value (D6).
  - **`to_point_cloud` temporaries.** `to_point_cloud` frees its meshgrid temporaries once `coords`
    is built.

    Together with the broadcast, its peak falls from 104·N to 72·N bytes for six fields, 0.87 GB to
    0.60 GB at 256×128×256 (D6).
- **DoMINO `grid` (#112 item 2), documentation only.** The adapter documents that its `grid` is the
  snapshot's own cell centres, unlike stock DoMINO's `grid`. Choosing that grid is left to F3. Keys
  and values are unchanged (D7).
- **Pathlib.** Paths stay `pathlib.Path` throughout. The one `os` call is `os.scandir`: on the
  version CI pins (3.11), and through 3.13, no `Path` API keeps the `DirEntry` (D1).

Nothing here is breaking. There are no signature changes and no new dependencies. Nothing changes in
the solver, decks, Docker or committed artifacts. Merging to `main` does rebuild and republish the
`:fp64` and `:python` images, which copy `src/`.

`cell_volume` is still read-only, as before, but it now differs in three ways:
- it can no longer be made writable at all;
- it is not C-contiguous;
- its `base` is set.

No in-repo code consumes it. Callers that need a dense buffer call `np.ascontiguousarray` (D6).

## Out of scope

- **#112 item 4 (sub-box covering grids).** These need their own spec change. Both
  `field-surrogate` and `force-extraction` pin "full level-0 covering grid, sliced in memory". They
  also need a multi-FAB A/B and a fixture. Per the user's decision this is a separate follow-up PR,
  and #112 stays open for it.
- **#107** (a general fixture) and **#113** (reader robustness and provenance).
- **A manifest mtime check.** It would cost a `stat` on every call (D3).
- **Not to be touched:** the force-surrogate training, metrics, figures and README; #109's follow-ups
  #133, #135, #137, #138 and #139; and #114, #115, #124, #130 and #131.

## Impact

- **Affected specs.** In `field-surrogate`:
  - ADDED: two requirements, one for covering-grid release and one for zero-cell regions.
  - MODIFIED: five requirements — Field selection, Region semantics, Point-cloud view, Corpus
    addressing and DoMINO
    adapter.
- **Specs that need no delta.** `force-extraction` and `flapping-wing-grid-convergence` describe a
  non-empty level-0 covering-grid read, which is still performed exactly that way. The fp32 check
  that `force-extraction` cites is satisfied by the on-disk `ds.index._dtype` guard, and that guard
  still runs on every path.
- **Affected code:**
  - `src/mosquito_cfd/field_surrogate/corpus.py`;
  - `src/mosquito_cfd/field_surrogate/snapshot.py`;
  - `src/mosquito_cfd/field_surrogate/domino_adapter.py` (docstring only);
  - `src/mosquito_cfd/benchmarks/stress_integral.py` (one comment).
- **Affected tests:**
  - `tests/test_field_surrogate_corpus.py`: spies and forced-order fakes move to `os.scandir`.
  - `tests/test_field_surrogate_snapshot.py`: proxies, including `_PoisonGrid`, forward
    `field_data` and `clear_data`; adds new bit-identity, teardown, memory and zero-cell tests.
  - `tests/test_field_surrogate_domino_adapter.py`.
- **Docs:**
  - `docs/CHANGELOG.md`: `### Changed` and `### Fixed`.
  - `docs/field_surrogate/roadmap.md`: its one-line description of `grid` is reconciled with D7.
- **Callers.** `extract_eulerian_box` gains the savings without changes, and through it so do
  `benchmarks/wing_lev.py`, `examples/flapping_wing/make_lev_figure.py`,
  `flow_video`'s per-frame `lev-3d` read and the sphere control-volume tools.
- **Issues.** This closes #120 and #145, and advances #112.
