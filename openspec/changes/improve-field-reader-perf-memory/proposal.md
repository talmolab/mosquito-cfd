# improve-field-reader-perf-memory

## Why

F3's training loop will read thousands of field snapshots, from several DataLoader workers, on a
24 GB A5000 or over cluster NFS. #112 and #120 measured filesystem calls and memory the F2 reader does
not need. This change removes them before F3 is written around them, keeping every returned array
bit-identical.

Headline. The setup:
- a synthetic 256×128×256 single-FAB plotfile with six FP64 fields of 67 MB each;
- `read_field_snapshot` itself, traced with `tracemalloc`, **automatic GC enabled**;
- a warm-up read, then three reads, each starting from a full collection;
- `measurements/reader_memory.py`, run on `90b2a72` (exported) and on this branch.

| full-extent read | peak per read | held on return¹ | time per read | dataset alive on return |
|---|---|---|---|---|
| today | 1329–1331 MB | 456–458 MB | 5.3–5.6 s | yes |
| this change | 927–928 MB | 8–9 MB | 4.4–4.8 s | no |

¹ Memory still traced right after the call returns, not counting the returned arrays. Today the
six cached fields (403 MB) sit inside a yt reference cycle that waits for Python's old-generation
collection, which runs irregularly; until it does, each read's cycle adds to the last.

The real 256-FAB wing plotfile shows the same pattern (D4): peak 1193 → 790 MB, held 462 → 11 MB.

The full collection is process-wide, so its cost depends on the caller, not the plotfile: about
30 ms with only yt loaded, about 0.56 s with 10 M tracked objects, and about 2 ms after
`gc.freeze()` (D4).

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
  - unwraps each field through `.d`, a view of yt's buffer, instead of `to_ndarray()`, which makes
    a transient full-domain copy. This saves an allocation and a copy per field, not peak memory
    (added in pre-PR review);
  - drops each field from yt's cache once it has been copied;
  - clears the covering grid;
  - drops its yt references;
  - runs a full `gc.collect()` before returning a snapshot, on both the full and the zero-cell
    path (D4). Its cost scales with the caller's tracked objects, and the docstring says so.
- **Smaller items (#112 item 5).**
  - **Zero-cell regions.** A region with zero cells builds no covering grid and reads no field.
    It still runs every plotfile guard first. Today it reads all six fields (403 MB of field data
    at 256×128×256) to return nothing (D5).
  - **BREAKING (minor): `cell_volume`.** `PointCloud.cell_volume` becomes a read-only zero-stride
    broadcast instead of an `N`-element buffer of one repeated value (D6).
  - **`to_point_cloud` temporaries.** `to_point_cloud` frees its meshgrid temporaries once `coords`
    is built.

    Together with the broadcast, its peak falls from 104·N to 72·N bytes for six fields, 0.87 GB to
    0.60 GB at 256×128×256 (D6).
- **DoMINO `grid` (#112 item 2), documentation only.** The adapter documents that its `grid` is the
  snapshot's own cell centres, unlike stock DoMINO's `grid`. Choosing that grid is left to F3. Keys
  and values are unchanged (D7).
- **Pathlib.** Paths stay `pathlib.Path` throughout. The one `os` call is `os.scandir`: on the
  version CI pins (3.11), and through 3.13, no `Path` API keeps the `DirEntry` (D1).

The one breaking change is `cell_volume`'s array type, marked **BREAKING** as this repository
marks any change a caller can observe. There are no signature changes and no new dependencies.
Every returned value is unchanged. The corpus listing skips and raises on the same entry errors as
before, broken symlinks included. The one difference: for an entry whose type the listing itself
reports, no `stat` is made, so a stat-only error there (for example `EACCES` on a directory that is
readable but not searchable, or `ESTALE` on NFS) no longer surfaces, and the entry counts as a
directory. Nothing changes in the solver, decks, Docker or committed artifacts.
Merging to `main` does rebuild and republish the `:fp64` and `:python` images, which copy `src/`.

`cell_volume` is still read-only, as before, but it now differs in four ways:
- it can no longer be made writable at all;
- for `N > 1` it is not C-contiguous, so buffer-protocol consumers that need contiguous memory fail;
- its `base` is set;
- pickling it produces a dense, writable copy.

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
