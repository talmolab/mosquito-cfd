# Design: improve-field-reader-perf-memory

Every decision keeps the returned values, shapes, dtypes and flags bit-identical. Each saving is stated
as a measurement, and each measurement as a test.

Notation: `N` is the number of cells, `k` is the number of fields, and `S` is one field's size in bytes
(`8·N`). Measurements were taken on Windows with Python 3.11.13, yt 4.4.2 and numpy 2.4.2, the
versions `uv.lock` pins for CI.

## D1. `_scan` lists with `os.scandir`; everything else stays `pathlib`

Before the change, `_scan` iterates `run.iterdir()` and calls `entry.is_dir()` on each `plt`-named
entry. On Python 3.11, `Path.iterdir()` is `for name in os.listdir(self): yield
self._make_child_relpath(name)`, which carries no file type. Every `is_dir()` is therefore a fresh
`stat()`. #112 estimates 1–5 ms per stat on cluster NFS; that figure was not measured.

After the change:

```python
with os.scandir(run) as it:          # `with` closes the directory handle deterministically
    for entry in it:
        match = _PLT_PATTERN.fullmatch(entry.name)
        if not (match and _is_dir(entry)):   # DirEntry.is_dir(), with Path.is_dir()'s skip list
            continue
        ...
        found[step] = run / entry.name   # the same Path that iterdir() produced
```

- **Same result.**
  - Values are `run / entry.name`, so the returned paths, the duplicate message and `plotfile()`'s
    return values are unchanged.
  - `DirEntry.is_dir()` follows symlinks by default, as `Path.is_dir()` does.
  - It takes the type from the listing where the OS provides it: on Windows, and on Linux via
    `d_type`. On `DT_UNKNOWN` (possible on NFS, e.g. plain v3 `READDIR` or a `nordirplus`
    mount) and for every symlink it falls back to a C-level `stat()`. So on NFS the saving is a
    Python-level syscall per entry, and a round trip only where the attribute cache would not
    have answered; that has not been measured on the cluster.
- **Errors.** On an entry whose type cannot be read, `Path.is_dir()` (3.11) returns `False` for
  `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP`, for Windows errors 21, 123 and 1921, and on
  `ValueError`. It raises on any other `OSError`. `DirEntry.is_dir()` returns `False` only for
  `FileNotFoundError` and raises otherwise, so `_scan` calls it through `_is_dir()`, which applies
  `Path.is_dir()`'s list. The verdict on every entry is therefore unchanged.

  **Why the list, not `DirEntry.is_dir()` alone (changed in pre-PR review).** The approved design
  accepted the louder behaviour "only on a damaged or racing filesystem". Review reproduced it on
  Linux: a symlink loop or a symlink through a file made `steps()` raise, so one broken link took
  down a config's whole step list where `Path.is_dir()` had skipped it. The user chose to keep
  the old verdict.
- **Why `os` here.** CI pins Python 3.11, and through 3.13 no `Path` API exposes the
  `DirEntry`. 3.13 builds `iterdir()` on `scandir` but yields bare `Path` objects; 3.14's
  `Path.info` would cache the type, which can replace this when the floor reaches 3.14. The
  `os.scandir` docs: using it "instead of `listdir()` can significantly increase the performance of
  code that also needs file type or file attribute information".
- **What the tests can see.** The tests count Python-level `os.stat` calls. `Path.is_dir` reaches
  `os.stat` on 3.11–3.13 (CI pins 3.11), but not on 3.14 on Windows. A C-level fallback stat on
  `DT_UNKNOWN` is invisible to them. So they pin "no per-entry Python-level stat", the part the code
  controls. The filesystem saving is measured separately (tasks 0.1 and 8.4): Python-level call
  counts on a local synthetic corpus, and wall time of a `steps()` pass over the real corpus on Z:.

**Test-infrastructure consequence.** The corpus tests patch `Path.iterdir` in three places. After
this change a patched `iterdir` is never called, so the forced-order tests would pass vacuously.
Each patch becomes a fake `os.scandir` that asserts it was called (task 1.2).

## D2. `_PLT_PATTERN`: ASCII digits, whole name (#145)

`re.compile(r"^plt(\d+)$")` with `.match()` has two flaws:
- `\d` matches any Unicode decimal digit, and `int("١٠٠") == 100` (#145).
- `$` also matches before a trailing `\n`, so `"plt100\n"` parses as step 100. POSIX filesystems
  allow that name.

AMReX writes neither name. But #140's duplicate check depends on this pattern, so either name next to
a real `plt00100` makes `steps()` raise "ambiguous".

The fix is `re.compile(r"plt([0-9]+)")` with `.fullmatch()`. Leading zeros and any digit width still
parse.

Both names are tested through `_scan` with stub entries, so the test runs on every OS (task 2.1).

## D3. Manifest cache: pin it, no mtime check

`_configs()` already caches per instance (`1146552`). The class docstring tells callers to construct
a new `FieldCorpus` to pick up an edited manifest. An mtime check would cost one `stat` per public
call, which is the NFS cost #112 asks to remove, to detect an edit the sweep workflow never makes
mid-read. It is rejected.

Tests pin all of this:
- a corpus pass reads the manifest once;
- an edited manifest is seen by a new instance, not by the old one;
- a newly created plotfile is seen by the next `steps()` call, because presence is never cached.

## D4. Covering-grid teardown: full `gc.collect()` (#120)

### What holds the memory

1. **The field cache.**
   - `cg[field]` caches the field in `cg.field_data` for the life of `cg`.
   - `to_ndarray()` is a view of that cached buffer.
   - All `k` fields therefore stay cached on top of their copies.
   - While each copy is made, one extra field-sized buffer also exists transiently.
2. **A reference cycle.**
   - The dataset is referenced by its `BoxlibFieldInfo`, 257 `DerivedField`s and 401
     `FieldDetector` dicts. These were counted at 64³.
   - It is also referenced by the index and the covering grid, all in cycles. Reference counting
     cannot free them; only the cyclic collector can.
   - With automatic GC enabled, the many automatic collections during `yt.load` and the index
     build promote these objects to the **oldest generation before the read returns**.
     `gc.collect(0)` and `gc.collect(1)` then reach nothing. Only a full collection does.
   - Python runs that collection rarely, so each read's cycle, and today the field cache inside it,
     piles up until it does.
   - Breaking the cycle by hand would mean editing yt-private structures. `ds.close()` only closes
     the data file.

### Measurements

Automatic GC is **enabled**. Each value is per read, after a warm-up read. "Held" is the memory still
traced after return minus the returned arrays, after reads 1, 2 and 3.

| size | variant | peak per read | held after reads 1, 2, 3 | `ds` alive | collect cost |
|---|---|---|---|---|---|
| 64³ | pop + `clear_data`, no collection | — | 46, 92, 138 MB | yes | — |
| 64³ | + `gc.collect(0)` | — | 47, 92, 138 MB | yes | 0.1 ms |
| 64³ | + `gc.collect(1)` | — | 46, 92, 138 MB | yes | 0.8 ms |
| 64³ | + `gc.collect()` | — | 0, 0, 0 MB | no | 42 ms |
| 256×128×256 | today | 1263 MB | 457, 914, 1371 MB | yes | — |
| 256×128×256 | pop + `clear_data` | 927 MB | 55, 108, 163 MB | yes | — |
| 256×128×256 | + `gc.collect()` | 927 MB | 8, 9, 9 MB | no | 69–89 ms |

This table is from the design-time prototype. Its collect-cost column, 69–89 ms, holds only for a
process with little else in it. The cost grows with the number of tracked objects in the process,
not with the plotfile. The "54 ms with about 2 M more objects" first quoted here used mostly
untracked objects, which the collector never walks. The caller-heap table below replaces both
figures. Measurements taken with GC *disabled* are misleading here: nothing is ever promoted, so
generation 0 appears to suffice. Every measurement in this table has automatic GC enabled.

The rows above came from a standalone script that copies the reader's covering-grid loop. Task 0.2
re-measured through `read_field_snapshot` itself at `90b2a72`. The dataset was alive on every
return in both runs below. "Held" grows less regularly than in the table, because an old-generation
collection sometimes runs during the next read:

| file | request | peak per read | held after reads 1, 2, 3 |
|---|---|---|---|
| synthetic 256×128×256 | full extent | 1330, 926, 927 MB | 457, 511, 565 MB |
| synthetic 256×128×256 | `outside_domain` | 994, 590, 592 MB | 457, 511, 566 MB |
| real `plt01000`, 256 FABs | full extent | 1193, 789, 693 MB | 462, 521, 483 MB |
| real `plt01000`, 256 FABs | `outside_domain` | 858, 453, 358 MB | 462, 520, 483 MB |

**Those "peak" values are not comparable across reads (corrected in pre-PR review).** Each read's
peak was taken above its own starting level, and that level still held the previous read's
uncollected cycle. When an old-generation collection freed that cycle in the middle of the next
read, it offset the peak. That is why reads 2 and 3 above look as low as the change.

The definitive figures come from `measurements/reader_memory.py`. It runs a full collection
before each traced read, so every read starts clean. Held memory is taken right after return and
before any collection. Runs were on this branch at `ca241f2` and on `90b2a72` exported, with
Windows, Python 3.11.13 and yt 4.4.2:

| file | request | version | peak per read | held on return | time per read | `ds` alive |
|---|---|---|---|---|---|---|
| synthetic 256×128×256 | full extent | before | 1329–1331 MB | 456–458 MB | 5.3–5.6 s | yes |
| | | after | 927–928 MB | 8–9 MB | 4.4–4.8 s | no |
| | `outside_domain` | before | 993–995 MB | 456–458 MB | 5.9–6.5 s | yes |
| | | after | 49 MB | 0 MB | 1.3–1.4 s | no |
| real `plt01000`, 256 FABs | full extent | before | 1193 MB | 462 MB | 5.4–6.3 s | yes |
| | | after | 790–791 MB | 11 MB | 4.4–4.8 s | no |
| | `outside_domain` | before | 857–858 MB | 462 MB | 5.0–5.3 s | yes |
| | | after | 52–53 MB | 3 MB | 1.5–1.6 s | no |

The full-extent peak falls by 6 fields of the cache, about 6·S: 1330 − 928 = 402 MB = 6 × 67 MB.

**What the collection costs the caller.** Measured with `measurements/gc_cost.py`:
- the 128³ synthetic file, three fields, full extent;
- the mean of five reads after a warm-up;
- the process first allocates the stated number of dict+list pairs, each pair two tracked
  objects;
- the bare `gc.collect()` column is one collection timed afterwards in the same process.

| tracked objects in the process | before: read | before: bare collect | after: read | after: bare collect |
|---|---|---|---|---|
| 0.15 M (yt only) | 816 ms | 118 ms | 682 ms | 31 ms |
| 2.15 M | 852 ms | 262 ms | 775 ms | 125 ms |
| 10.15 M | 771 ms | 702 ms | 1290 ms | 563 ms |
| 10.15 M after `gc.freeze()` | 753 ms | 91 ms | 584 ms | 2 ms |

- At 10 M tracked objects the per-read collection adds about 0.5 s; `gc.freeze()` removes it.
- With a small heap the change is faster overall, because it skips the full-domain copy and holds
  less memory.
- "Before" pays the same collection cost too, but only when Python's own heuristic decides to run
  it, not on every read.

### After

```python
for name, field in zip(fields, requested):
    raw = cg[field].to_ndarray()
    ...                                   # dtype check, owning copy as today
    del raw
    cg.field_data.pop(field, None)        # drop the cached buffer as soon as it is copied
cg.clear_data()
```

Teardown runs on every path that loaded the plotfile and returns a snapshot, both the full read and
the zero-cell read (D5):
- `time` and `max_level` are read first;
- then `del cg` (where one exists) and `del ds`;
- then `gc.collect()`.

The returned snapshot references no yt object.

**Data safety.** A collection frees only objects unreachable from any live reference. It cannot free
anything the caller or the snapshot holds. Its side effects fall on the caller's process (amended
in pre-PR review; this paragraph first said "timing only"):
- the caller's own unreachable garbage is freed earlier, and its finalizers run at that point;
- it runs even when the caller has disabled automatic GC (`gc.isenabled()` is left unchanged);
- its cost scales with every tracked object in the process, not with the plotfile (measurements
  below);
- in a forked DataLoader worker, a full collection writes the GC header of every inherited tracked
  object and so can break copy-on-write sharing of the parent's heap (reasoned, not measured);
- yt's `WeakValueDictionary` dataset cache no longer hands the next `yt.load` of the same file the
  previous `Dataset`. In yt 4.4.2, `yt.load` returned a fresh dataset regardless (checked in
  review), so nothing changes there.

The user kept the full collection after reviewing these costs, over two alternatives: disabling
automatic GC around the read and collecting generation 0 (flat cost, but about 0.9 MB of small
garbage per read left behind), and a keyword to skip the collection. The docstring documents the
cost and recommends `gc.freeze()` once after setup in long-lived callers: frozen objects are not
scanned, which removes the cost and the copy-on-write effect.

### Not done

- **No teardown on error paths.** The plotfile guards raise before any covering grid exists. Two
  raises can happen after one does: the `raw.dtype` defence-in-depth check inside the loop, and an
  I/O error from `cg[field]`. On those paths at most one field is cached, and the caller's next full
  collection frees the cycle. The spec's teardown requirement covers paths that return a snapshot.
- **`pop(field, None)` rather than `del`.** yt keys `field_data` by exactly the requested tuple; this
  was verified. The test proves the entry actually goes. Its proxy asserts two things:
  - at every field read, no earlier field is still cached;
  - `field_data` is already empty **when `clear_data()` is called**.

  Checking only after the loop would be vacuous, because `clear_data()` empties `field_data` itself.

## D5. Zero-cell short-circuit

The order of operations:
1. `_region_bounds` runs after the AMR, `_dtype`-presence, fp32 and missing-field guards; its inputs
   come from `ds`.
2. If `np.any(i_hi == i_lo)`, the reader skips `ds.covering_grid`.
3. In that case each field is `np.empty(shape, dtype=np.float64)`, made read-only.
4. Then the D4 teardown runs.

**Bit-identical.** A zero-size array has no values. Its observable properties are:
- shape and dtype;
- strides (`(0, 0, 0)`, the same in either order on numpy 2.4);
- C- and F-contiguity;
- `base is None` and `flags.owndata`;
- `writeable` and its type.

Checked for `(0,0,0)`, `(0,4,4)` and `(4,0,6)`: `np.empty` matches `np.array(raw[sl], copy=True)` on
every one. Axes, `dx`, `time`, `source`, `max_level` and `field_names` take unchanged code.

**Order matters:**
- **Guards before the short-circuit.** The guards fire before the short-circuit, so a zero-cell
  request on a bad plotfile still raises. Task 3.2 pins every guard with a zero-cell request.
- **Inversion check before `yt`.** The `lo > hi` rejection runs before `yt` is imported, unchanged.

**What callers see.**
- `extract_eulerian_box` refuses to unfreeze an array that does not own its data
  (`not value.flags.owndata`, `stress_integral.py:257`). The empty arrays own theirs, so the
  wrapper's zero-cell output is unchanged. `REGION_CASES`' `upper_edge` and `outside_domain` pin
  this against the frozen oracle.
- The wrapper's comment saying the reader "copies each array" becomes "copies or freshly allocates".
- The `raw.dtype` defence-in-depth check is skipped for an empty region. The real fp32 guard,
  `ds.index._dtype`, still runs.

## D6. `to_point_cloud`: free the meshgrid, broadcast `cell_volume`

Peak bytes per cell, by phase:

| phase | before | after |
|---|---|---|
| `coords` stack | 24 (gx/gy/gz) + 24 | 24 + 24 |
| `values` stack | 48 + 8k | 24 + 8k |
| `cell_volume` | 48 + 8k + 8 | 24 + 8k + 0 |

At `k = 6` the peak is 104·N before the change. The `del gx, gy, gz` alone brings it to 80·N, and the
broadcast `cell_volume` to 72·N. At 256×128×256 (N = 8,388,608) that is 0.87 GB to 0.60 GB. The
`values` stack uses `.ravel()` views of the snapshot's C-contiguous arrays. The remaining peak is
`coords` and `values` coexisting, and both are outputs.

`cell_volume = np.broadcast_to(v0, (n,))`, where `v0` is a read-only 0-d float64 holding
`float(np.prod(dx))`. Verified on numpy 2.4.2:
- **Write protection.** Strides are `(0,)` and `writeable` is `False`. `setflags(write=True)`
  raises `ValueError`. `base` is `v0`, which is read-only.
- **Layout.** For `N > 1` it is **not C-contiguous**: `memoryview(...).cast` fails, and so does any
  `double[::1]` consumer. Callers that need a dense buffer call `np.ascontiguousarray`.
- **Size.** `nbytes` still reports `8·N`, because it is computed from the shape. The test therefore
  asserts strides and base, and measures with `tracemalloc`.
- **Pickling.** A pickled copy unpickles as a dense, writable `(N,)` array. Crossing a DataLoader
  worker boundary costs `8·N` in both the producer (transiently) and the receiver.

No in-repo code consumes `cell_volume`. A future varying `cell_volume` (CC-F3) becomes a real array of
the same type.

## D7. DoMINO `grid`: upstream versus here

Upstream is PhysicsNeMo `8211352`, `main` on 2026-11-12, read from
`physicsnemo/datapipes/cae/domino_datapipe.py`, `models/domino/model.py` and
`models/domino/utils/utils.py`.
- `grid` is `create_grid(bbox_min, bbox_max, grid_resolution)`, a `linspace` regular grid of shape
  `(nx, ny, nz, 3)` over the volume bounding box.
- Its resolution is `DoMINODataConfig.grid_resolution`, which the model calls `interp_res`. The
  default is `(256, 96, 64)`; the example config uses `[128, 64, 64]`.
- It is paired with `sdf_grid`, the geometry's SDF on that grid. It is consumed only by the volume
  geometry encoding (`geo_rep_volume`, `volume_local_geo_encodings`).

Ours is the snapshot's own cell centres, at the snapshot's resolution, over the snapshot's region.
Both grids span a volume. They differ in who chooses the resolution and extent, and in that upstream
pairs the grid with an `sdf_grid` we do not produce. The roadmap line that says ours is "the full
volume" and theirs is "a small SDF bounding grid" is imprecise; task 6.3 rewords it.

Choosing DoMINO's grid belongs with producing `sdf_grid`, which is F3's (CC-4). The adapter keeps
emitting the view. Dropping it would break a dict that F3 has not consumed yet.

## D8. How bit-identity is verified

1. **The frozen legacy oracle**, unchanged. It runs every `REGION_CASES` entry at halo 0 to 3,
   including both zero-cell cases.
2. **A full-read reference** (task 3.1). A test helper:
   - reads the full level-0 covering grid with yt;
   - slices it by `_region_bounds`, which the sweep test pins against a literal legacy
     transcription;
   - on the 6³ fixture, also checks its shapes against the literal cell counts in the case tables.

   It covers what the oracle cannot: `DIVERGENCE_CASES`, all eight fields, and the metadata.
   - It runs on the 6³ fixture and on the anisotropic `asym_plotfile`. Coordinates are mapped with
     `scripts/verify_eulerian_box_ab.py`'s `_map`, loaded via importlib.
   - Under `requires_plotfile` it runs on the last `plt*` in `$MOSQUITO_CFD_PLOTFILE_ROOT/t3c-fine`.
     The reference is built once per process (an `lru_cache` keyed by path), and the test skips
     with a reason if the directory is absent.
3. **The real multi-FAB A/B.** `scripts/verify_eulerian_box_ab.py` is re-run on the sphere and wing
   roots over Z: (task 8.3). The real wing plotfiles are 256 FABs of 32³. This change alters the
   read loop, so the re-run is required; #140 could skip it.

## D9. Memory tests do not depend on the platform

yt has fixed costs that vary by platform and version: about 86 MB of one-time caches on the first
load, and a 48–78 MB peak just to load and index. An absolute threshold would be flaky. So every
memory test does three things:
- does a warm-up read of the same file;
- runs `gc.collect()` before each traced read;
- restores any prior `tracemalloc` and GC state (`is_tracing()`, `isenabled()`), skipping if a trace
  is already running.

Its assertion is either deterministic or differential:

- **Teardown.** Deterministic, not a threshold. The test wraps `yt.load` to keep a
  `weakref.ref` to the real yt `Dataset`, never to a test proxy around it: a proxy dies on return
  even when the dataset it wraps is alive, which would make the test vacuous. With **automatic GC enabled**, the dataset must be dead when
  `read_field_snapshot` returns. This is checked for a full read and for a zero-cell read.
  For the full read the test also hooks `YTCoveringGrid.__init__` and requires the real covering
  grid to be dead.

  **Why the grid as well, not the dataset alone (changed during implementation).** The covering
  grid holds its dataset only through a `weakref.proxy`. A reader that omitted `del cg` therefore
  still left the dataset dead, and that mutant survived the dataset-only check, while the grid
  outlived the call in a cycle of its own.
- **Field-cache release.** Peak(6 fields) − peak(1 field) ≤ 7.5·S, on a 96³ file. Measured
  9.7–11.1·S without the pop and 4.5–5.3·S with it, with GC on and off and in both read orders.
- **Zero-cell.** Peak(`outside_domain`, 6 fields) − peak(`outside_domain`, `fields=()`) < 1·S, on
  96³. Today's zero-cell read reads all six fields, which the `fields=()` read does not, so the
  difference today is at least 6·S (measured 13.9·S today, 7.9·S after the teardown commit,
  0.0–0.1·S with the short-circuit).
- **Point cloud.** Peak ≤ `1.02 × (coords.nbytes + values.nbytes) + 64 KiB`, on an in-memory 64³
  snapshot with `k = 6` and no yt. Measured 1.44× before the change and 1.0001× after.

The generated plotfiles come from `tests/fixtures/make_lev_boxlib_fixture.py` via `tmp_path_factory`
at module scope. They are never committed. The new tests took 36.5 s locally (task 8.2).
