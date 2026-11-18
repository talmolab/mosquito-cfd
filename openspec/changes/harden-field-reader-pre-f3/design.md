# Design: harden-field-reader-pre-f3

## Context

F2 built the reader in OpenSpec change `add-field-surrogate-reader` (#105/#106). #140 hardened its
requests and #150 made it cheaper. This change removes the reader's remaining defects before F3
builds `DataLoader`s on it. It never changes the values `read_field_snapshot` returns: every
decision below touches only what happens before `import yt`, or the object built after the arrays
are final.

## D1. Pickling: `__reduce__` to a rebuild function that re-imposes the invariants

**Measured** under numpy 2.4.2 / CPython 3.11, on arrays returned by the reader over the fixture.

| Transport | 3-D field array (`arrays["u"]`) | 1-D coordinate (`x`) |
|---|---|---|
| `pickle` protocols 2, 3, 4 | `writeable=True`, `base` is a `bytes` | `writeable=True`, `base=None` |
| `pickle` protocol 5 | `writeable=False`, `base` is an `ndarray` | `writeable=False`, `base` is an `ndarray` |
| `ForkingPickler` (protocol 4) | `writeable=True`, `base` is a `bytes` | `writeable=True`, `base=None` |
| `copy.deepcopy` | `writeable=True`, `base=None` | `writeable=True`, `base=None` |

Zero-size arrays need their own rule. The reader allocates them with `np.empty(shape)`, which gives
all-zero strides, e.g. `(0, 0, 0)`. After any pickle they come back with C strides, `(8, 8, 8)` or
`(288, 48, 8)` for a `(0, 6, 6)` region of the fixture. The same holds for a zero-size `x`: the
reader gives `(0,)` (which `np.empty((0,))` reproduces), and a pickle gives `(8,)`.

The spec's invariant is `writeable is False` **and** `base is None`, with the same strides. No
transport delivers it, so the rebuild re-imposes it.

**Decision.** `FieldSnapshot.__reduce__` returns `(_rebuild_field_snapshot, (state,))`.
- `state` maps **every** dataclass field name, from `dataclasses.fields(FieldSnapshot)`, to its
  value, with `arrays` as a plain `dict` in `field_names` order.
- Building `state` from `dataclasses.fields` means a field added later is carried automatically.
  The four provenance fields have defaults, so a hard-coded list that omitted one would silently
  unpickle it as `None`.

`_rebuild_field_snapshot` is module-level, so pickle can import it. It normalizes each array in
`arrays`, `x`, `y`, `z` and `dx`:
- `size == 0` → `np.empty(a.shape, dtype=np.float64)`. That is the reader's own zero-cell allocation
  (#150 D5), so the strides match.
- `base is not None` → `np.array(a, dtype=np.float64, order="C", copy=True)`.
- Every array then gets `setflags(write=False)`.

It also restores the scalars and the mapping:
- `time` goes through `float()`;
- `max_level` through `int()`;
- `step` through `int()` when it is not `None`;
- `arrays` becomes a `MappingProxyType` again;
- then the constructor is called.

**Why `__reduce__`, not `__setstate__`.** A frozen dataclass's `__setstate__` must use
`object.__setattr__`, bypassing `__init__`. `__reduce__` rebuilds through the constructor, the path
the reader uses.

**`copy.copy`** goes through the same path. It shares the original's owning, read-only arrays,
correct for an immutable value. On main it already works, because the `MappingProxyType` is shared
shallowly.

**Cost.** Every pickle transport copies each field array once more on receipt (the 3-D arrays arrive
`bytes`-backed at protocols 2–4 and as views at 5). The receiver's transient peak per array is two
copies of it. The alternative is to accept a read-only array whose `base` is the private unpickled
`bytes`, which nothing else references. That would weaken the spec's `base is None` invariant, which
exists so "no writable object shares its memory" is checkable by a single attribute. The copy is
kept. F3 may still choose to send tensors or point clouds instead of whole snapshots.

**Rejected: a plain-`dict` `arrays`.** That is mutable, so a caller could add or replace a field and
desynchronize it from `field_names`.

**`==` is out of scope.** The dataclass's generated `__eq__` compares numpy arrays and can raise on two
distinct snapshots; this predates the change. Tests compare snapshots property by property
(`_assert_snapshot_equivalent`), never with `==`.

## D2. Path pre-check: `is_dir()` + `(p / "Header").is_file()`, after argument checks, before `import yt`

**Order.**
1. All argument checks, in the existing order (`fields` type, names and duplicates; `halo`; corners;
   inversion). They are factored into `_validate_request` (D4).
2. The path checks.
3. `import yt`.

Argument errors therefore stay independent of the filesystem.

**Errors.**

| Input | Raises |
|---|---|
| Path does not exist | `FileNotFoundError` |
| Path exists but is not a directory | `NotADirectoryError` |
| Directory without a regular `Header` file | `FileNotFoundError` naming `Header` |

Each message names the path. These are the builtin types for exactly these conditions. Any other
`OSError` from the checks, such as `EACCES`, propagates unchanged.

- `is_file()` follows symlinks, so a `Header` symlink to a file passes, and a dangling one is "no
  `Header`".
- yt's own boxlib detector also requires `Header`, so the pre-check refuses nothing yt would have
  read.

**Cost.** Two `stat`s per read, negligible next to a yt read.

**Garbage `Header` (out of scope).** Detecting it means parsing the Header and duplicating yt's
parser. The existence check already covers a plotfile caught mid-write, because AMReX writes
`Header` last.

## D3. `source`: `Path(p).absolute().as_posix()`

The user chose this.
- `absolute()` does no I/O and follows neither symlinks nor mapped drives.
- `resolve()` (measured) turns `Z:/users/...` into `//multilab-na.ad.salk.edu/hpi_dev/users/...`,
  yet another spelling, and expands 8.3 short names (`ELIZAB~1`).
- `absolute()` also does not collapse `..`: `a/../b` and `b` give different `source` values. That
  keeps `source` a faithful record of the path the caller used. It also makes `..` the
  OS-independent test that distinguishes `absolute()` from `resolve()` and `os.path.abspath`.

**Limitation.** No spelling makes Windows, WSL and cluster reads of the same bytes equal. `source`
locates the plotfile on the host that read it. Identity across hosts is `(config_id, step)` plus
`git_commit` and `docker_image` (D4).

## D4. Provenance: strict, read-through, before any yt work, with no heavy imports

**Where the record is.** Each pod writes `runs/<config>/run_metadata.json`, which is
`FieldCorpus.run_dir(config)/run_metadata.json` (`cluster/argo/README.md:124`).

**Verified on Z:** all **27** fine-corpus run directories hold one. In each:
- `config` equals the directory name;
- `git.commit` is `5d5f1ad49da19f9aeafeeaf86e535d04ef28d6c5`;
- `docker_image` is `ghcr.io/talmolab/mosquito-cfd@sha256:92817878…68a47`.

The Z: corpus root's own `sweep_manifest.json` lists 26 configs. It is the trimmed resubmission
manifest; `s55_f115_p30` is absent from it but its run is present and valid. The committed
27-config `examples/prelim_sweep_fine/sweep_manifest.json` addresses all 27.

**Why a new leaf module rather than reusing `metadata_capture`.**

1. **Looseness** (the deciding reason).
   - `extract_git_info`'s `^[0-9a-f]{40}$` with `.match` accepts a trailing newline.
   - `validate_image_digest`'s `.search` accepts a bare `sha256:<64>`, `repo:latest #sha256:<64>`
     and junk around a digest, and strips whitespace.
   - Wrong types escape as `TypeError`/`AttributeError`, and a missing file as `FileNotFoundError`.
   - Each of these contradicts the strictness this change specifies.
2. **Not adding an import.** Importing any `force_surrogate.*` submodule runs that package's
   `__init__`, which pulls in pandas, pyarrow and `force_surrogate.evidence_figure`. The latter calls
   `matplotlib.use("Agg")` at import, about 4.6 s cold. The provenance path should not add that.

   **Measured caveat:** `FieldCorpus._configs()` *already* imports
   `force_surrogate.dataset.load_manifest_configs`, which the live spec requires ("Sweep-manifest
   parsing SHALL reuse…"). So on main, a `FieldCorpus`'s first manifest read switches the matplotlib
   backend to `Agg`. This change neither causes nor fixes that. It specifies only that provenance
   adds no such import. #160 proposes moving manifest parsing to a light module, and #159 proposes
   tightening the force-surrogate validators.

**`field_surrogate/_provenance.py`** imports only `json`, `re` and `pathlib`.
- **`read_run_metadata(path, *, config_id) -> dict`.** Raises `ValueError` (same prefix as below,
  field tag `run_metadata.json`) when:
  - it is not a regular file;
  - an `OSError` or `UnicodeDecodeError` occurs on read, chained;
  - the JSON is invalid;
  - the top level is not an object.
- **`run_provenance(meta, *, config_id, path) -> tuple[str, str]`.** Requires each of the following
  to be a `str`:
  - `meta["config"] == config_id`;
  - `meta["git"]["commit"]`, `fullmatch` `[0-9a-f]{40}`;
  - `meta["docker_image"]`, `fullmatch` `[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}`.

  Any absence, wrong type or mismatch raises `ValueError` with the fixed prefix
  `run_metadata for config {config_id!r} ({path}): ` followed by the failed field's dotted name
  (`run_metadata.json`, `config`, `git`, `git.commit`, `docker_image`). The image pattern is
  `[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}`, fullmatched. It checks the digest suffix and a
  plausible repository, not the full OCI grammar.

The `force_surrogate` validators are left alone (out of scope). #159 proposes tightening
them, possibly onto this module.

**API.**
- **`FieldCorpus.run_metadata(config_id) -> dict`.** It calls `run_dir(config_id)` (manifest
  membership plus the directory), then `read_run_metadata`. It is a fresh parse each call, never
  cached, so mutation cannot leak and a file the pod writes at run end is seen.
- **`FieldCorpus.snapshot(config_id, step, *, lo, hi, halo, fields)`**, in this order:
  1. `_validate_step(step)`, then `snapshot._validate_request(lo, hi, halo, fields)`. Both are pure,
     with no I/O, so an argument error is reported as such whatever the corpus state.
  2. `plotfile(config_id, step)`: manifest, run directory, the step's presence.
  3. `read_run_metadata(runs_dir / config_id / "run_metadata.json", config_id=...)` and
     `run_provenance(...)`.

     **Why not `run_metadata(config_id)`?** The implementation calls the same reader directly.
     `plotfile()` has already checked the manifest and the run directory, so going through
     `run_metadata()` would repeat those checks, and `run_provenance` needs the file's path for its
     messages anyway. The behaviour is identical: same reader, same errors, same file.
  4. `read_field_snapshot(...)`.
  5. The zero-cell refusal (D5).
  6. `dataclasses.replace(snap, config_id=config_id, step=step, git_commit=..., docker_image=...)`.
     This copies no array.

  The provenance checks come **before** the read, so a corpus without provenance fails in
  milliseconds, not after a 256-cubed read.
- **`_validate_request`** is the existing argument-check sequence from `read_field_snapshot`,
  extracted unchanged and returning the normalized `(lo_v, hi_v, halo, fields)`.
  `read_field_snapshot` calls it, so its own ordering is unchanged. A second call from the corpus
  costs microseconds.

**No fabrication.** This keeps the rule in `add-field-surrogate-reader` design D7 that a digest is
never fabricated. #113 points out that the record already exists, so it is copied, never inferred.
`read_field_snapshot` leaves all four fields `None`. The corpus path has no fallback.

## D5. Zero-cell refusal at both training-facing entry points

The user chose to guard both.
- `FieldCorpus.snapshot` is the corpus entry point for every field consumer: arms B and C (C then
  passes through `to_domino_volume`), and the experiments' E7 `kin2field` cache builder (`experiments/field/build_cache.py`). Arm A, the
  windowed force MLP, reads no field snapshots (`roadmap.md:285`).
- `to_domino_volume` accepts any snapshot, including one from a bare `read_field_snapshot`.

The test is `0 in (x.size, y.size, z.size)`.
- In `FieldCorpus.snapshot` it runs after the read, which costs nothing for a zero-cell region
  thanks to #150's short-circuit.
- In `to_domino_volume` it runs after the global-params checks and before `to_point_cloud`.
- A full-extent read with `fields=()` has cells and zero columns. It is not refused, since the test
  is on the axes, not on `values.size`.

`read_field_snapshot` is unchanged. Its zero-cell result is specified, and `check_field_capture_velocity`
has its own empty-region path.

## D6. Smaller items

- **`fields` as `str`/`bytes`** → `ValueError` as the first check in `_validate_request`. A tuple or
  list is accepted, as before.
- **Global params.** Each argument's `np.asarray(x, dtype=float64)` must have `ndim == 1` and
  `size >= 1`. This is checked per argument, before the existing length and finiteness checks and
  before the snapshot is touched, so the error names the argument and its shape.
- **AMR message.** It becomes "requires a single-level plotfile; `<path>` has `max_level=N`…",
  still naming CC-F3, without naming a function.
- **`yt.set_log_level` comment.** It gains "inherited from the pre-refactor adapter; process-global".

## D7. `flow_video` reuses the corpus listing

`_plotfile_frames(d)`:
1. If `Path(d)` is not a directory, raise `ValueError` naming it. This keeps the documented
   `ValueError` for a nonexistent directory: today the glob returns nothing and raises the
   "no plotfiles" `ValueError`, while `os.scandir` would raise `FileNotFoundError`.
2. Return `[p for _, p in sorted(scan_plotfiles(d).items())]`.
3. If that list is empty, raise `ValueError` naming the directory and `plt<digits>`.

**Why reuse.** One definition of "a plotfile" means the two consumers cannot disagree again, which is
#144's root cause. It covers the ASCII-digit full match, directories only, the `Path.is_dir()`-
equivalent skip list and the duplicate refusal.

**Naming and imports.**
- `_scan` becomes `scan_plotfiles`, public and documented. There is no external caller and no alias.
- It is **not** exported from `field_surrogate/__init__.py`, which is deliberately import-free (see
  `add-field-surrogate-reader` design D4). `flow_video` imports `mosquito_cfd.field_surrogate.corpus`
  directly.
- `corpus.py` imports only `snapshot`, `_messages`, `_provenance` and numpy at module scope. There is
  no cycle.

## Verification strategy

- **Bit-parity.**
  - The full-grid reference test.
  - The frozen legacy oracle, with halo 0–3.
  - `scripts/verify_eulerian_box_ab.py` on the real Z: plotfiles: 159 cases, before and after.
- **Mutation testing.** One mutation per guard and per new test (tasks §8), run with
  `PYTHONDONTWRITEBYTECODE=1` and restored from saved bytes.
- **Worker boundary.**
  - A spawn-context `ProcessPoolExecutor` test runs on every OS, with a timeout. It exercises the same
    `ForkingPickler` queue as a `DataLoader` worker.
  - The real `DataLoader` test is `importorskip("torch")`. It is run once on this host with
    `uv run --with torch`, and the result is recorded in the PR body.
