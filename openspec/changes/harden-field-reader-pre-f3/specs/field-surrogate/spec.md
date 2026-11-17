## MODIFIED Requirements

### Requirement: Framework-neutral field snapshot contract

The package SHALL provide `mosquito_cfd.field_surrogate.snapshot.read_field_snapshot`, a single
`yt`-based reader returning an immutable `FieldSnapshot` describing an axis-aligned region of a
single-level AMReX plotfile. The snapshot SHALL carry, in **code units with no conversion**: the
requested fields as bare FP64 numpy arrays indexed `[ix, iy, iz]`; the cell-center coordinate arrays
`x`, `y`, `z`; the per-axis spacing `dx` as a `float64` array of shape `(3,)`; the plotfile's physical
`time` as a Python `float`; and the provenance fields `source` and `max_level`.

`source` SHALL be a `str` equal to `Path(plotfile_path).absolute().as_posix()`: absolute, with
forward slashes on every OS, and computed without touching the filesystem. `..` segments are kept as
the caller wrote them, so `a/../b` and `b` give different values. It is deliberately **not**
`Path.resolve()`, which on a mapped Windows drive rewrites `Z:/users/...` to a UNC form
`//<server>/<share>/...`, another spelling of the same bytes (`harden-field-reader-pre-f3` design
D3). `source` is a
**per-host locator**, not a cross-host identity: reads of the same plotfile from Windows, WSL and
the cluster still spell it differently. The cross-host identity of a corpus snapshot is
`(config_id, step)` plus the run's digest-pinned provenance (see "Corpus snapshots carry run
identity and digest-pinned provenance").

The snapshot SHALL also carry four optional provenance fields, each defaulting to `None`:
`config_id` (`str`), `step` (`int`), `git_commit` (a 40-character lowercase hex `str`) and
`docker_image` (a `str` that fully matches `[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}`).
`read_field_snapshot` SHALL
leave all four `None`, since a bare plotfile path does not establish them, and SHALL NOT infer any of
them from the path or fabricate a value. Only `FieldCorpus.snapshot` fills them.

Before `yt` is imported, and after **every** argument check (the `fields` type, names and
duplicates; `halo`; each corner's shape and NaN; inversion), `read_field_snapshot` SHALL check that the plotfile path names a directory containing a regular file
named `Header`. A path that does not exist SHALL raise `FileNotFoundError`; a path that exists but is
not a directory SHALL raise `NotADirectoryError`; a directory with no regular file `Header` (an empty
directory, a run directory passed in place of a `pltNNNNN`, or a plotfile still being written) SHALL
raise `FileNotFoundError`. Each message SHALL name the path and say what a plotfile directory must
contain. The checks follow symlinks, so a `Header` symlink to a regular file passes and a dangling
one counts as no `Header`; any other `OSError` raised by the checks (e.g. `EACCES`) SHALL propagate
unchanged. The reader's docstring SHALL list these errors under `Raises:`. A `Header` that exists but
is malformed is outside this check and still fails inside `yt`.

The snapshot SHALL survive `pickle` (every protocol from 2 to `pickle.HIGHEST_PROTOCOL`),
`multiprocessing`'s `ForkingPickler`, `copy.copy` and `copy.deepcopy`, so that a PyTorch `DataLoader`
worker (`num_workers > 0`) can return one. The round trip SHALL preserve every property this
requirement states, whatever the transport did to the arrays: every array bit-identical
(`tobytes()`), with the same dtype (FP64), shape and strides, `flags.writeable is False` and
`base is None`; `arrays` a read-only mapping with the same keys in the same order as `field_names`;
`time` a Python `float`; `max_level` (and `step`, when set) a Python `int`; and the provenance
fields equal. This holds for zero-cell snapshots too. Pickle transports restore arrays writable, or
backed by the pickle's own buffer, or as non-owning views, and restore zero-size arrays with
different strides. So the rebuild SHALL do two things:
- rebuild every zero-size array exactly as the reader allocates one;
- copy every other array whose `base` is not `None`.

It SHALL then mark every array read-only. It SHALL carry every dataclass field, enumerated from the
dataclass rather than from a hand-written list (`harden-field-reader-pre-f3` design D1). Tests SHALL
compare snapshots property by property: the dataclass's generated `==` compares numpy arrays and
can raise on two distinct snapshots (whenever an array has more than one element, or none).

The snapshot SHALL be protected against *accidental* mutation. That is, an ordinary assignment
must raise, and no writable object may share its memory. This is enforced, not merely declared:
- the dataclass is frozen;
- every array it exposes is non-writable (`arr.flags.writeable is False`);
- **every array owns its data** (`arr.base is None`).

Owning the data is what makes the read-only flag meaningful. A non-writable *view* leaves its `base`
reachable and writable, so the snapshot could be mutated through the covering-grid buffer without any
call touching the snapshot itself. Note that `np.ascontiguousarray` does not copy a slice that is
already C-contiguous — which includes the full-extent read and any single-axis slab — so it cannot
be relied on to produce an owning array.

This is not a guarantee against *deliberate* mutation. numpy lets the owner of a buffer call
`arr.setflags(write=True)` and then write to it. That applies to snapshot arrays and to
`to_domino_volume`'s outputs, where re-enabling writes on `volume_mesh_centers` would also change
`grid`, its view. Callers that need a mutable array SHALL copy it.

Owning the data also bounds retention: a small region must not keep the whole level-0 covering grid
alive behind a view. Two reads of the same region SHALL return arrays that do not share memory; note
that this holds trivially because each read allocates a fresh buffer, so a test asserting only
`shares_memory` between two reads does not exercise the ownership property.

#### Scenario: Reading the committed synthetic fixture cluster-free

- **Given** the committed synthetic single-level boxlib plotfile fixture and **no**
  `MOSQUITO_CFD_PLOTFILE_ROOT` (CI / off-cluster)
- **When** `read_field_snapshot` reads it over the full extent
- **Then** it returns a `FieldSnapshot` whose `u`/`v`/`w` reproduce the fixture's analytic solid-body
  rotation `(-Ωy, Ωx, 0)` with `Ω = 1.3` to within floating-point equality, whose arrays are bare FP64
  numpy indexed `[ix, iy, iz]`, whose `dx` is `[1, 1, 1]`, whose `time` is `0.5`, whose `max_level` is
  `0`, whose `source` equals `Path(fixture).absolute().as_posix()`, and whose `config_id`, `step`,
  `git_commit` and `docker_image` are all `None`

#### Scenario: `source` is absolute and POSIX-spelled whatever the caller passed

- **Given** the fixture addressed by a relative `Path`, by a relative `str`, and by an absolute
  Windows-separator `str` (on Windows)
- **When** `read_field_snapshot` reads each
- **Then** every `source` is the same absolute string, contains no backslash, and
  `Path(source).absolute() == Path(fixture).absolute()`; with the working directory set to the
  fixture's parent, the path `../<parent-name>/lev_boxlib_plt` gives a `source` that contains `/../`
  and equals `Path("../<parent-name>/lev_boxlib_plt").absolute().as_posix()`, on every OS (which
  `resolve()` and `os.path.abspath` would collapse); and a path through a directory symlink, where
  the platform permits creating one, keeps the symlink's spelling rather than its target's

#### Scenario: A path that is not a plotfile directory fails before yt is imported

- **Given** a path that does not exist, a regular file, an empty directory, and a directory holding
  only a subdirectory named `Header`; and an interpreter in which importing `yt` fails
- **When** `read_field_snapshot` is called on each with valid arguments
- **Then** the nonexistent path raises exactly `FileNotFoundError`, the regular file exactly
  `NotADirectoryError`, and the empty directory and the `Header`-subdirectory case exactly
  `FileNotFoundError` naming `Header`, each message containing `str(path)`, and none of them is an
  `ImportError`; while on a nonexistent path each invalid argument — `fields="u"`,
  `fields=("nope",)`, duplicate fields, `halo=-1`, a corner of shape `(2,)`, a NaN corner, and
  `lo > hi` — still raises its own `ValueError`, proving every argument check runs first

#### Scenario: A snapshot round-trips through every pickle protocol and copy

- **Given** a full-extent snapshot, a sub-box snapshot, a fully zero-cell snapshot and a snapshot
  empty on one axis only, each with `field_names` in a non-alphabetical order; a snapshot whose four
  optional provenance fields are set; and a hand-built snapshot whose `time` is `np.float64(0.5)`,
  `max_level` is `np.int64(0)` and `step` is `np.int64(100)`
- **When** each is passed through `pickle.dumps`/`loads` at every protocol from 2 to
  `pickle.HIGHEST_PROTOCOL`, through `multiprocessing.reduction.ForkingPickler`, through
  `copy.copy` and through `copy.deepcopy`
- **Then** every **result** (not only the original) satisfies every property of this requirement
  listed above (bit-identity, dtype, shape, strides, `writeable is False`, `base is None`, a
  read-only `arrays` mapping in `field_names` order, `type(time) is float`, `type(max_level) is int`,
  `type(step) is int` where set, equal provenance), and its `to_point_cloud()`
  has `coords`, `values` and `cell_volume` bit-identical to the original's and the same
  `field_names`

#### Scenario: A snapshot crosses a real worker-process boundary

- **Given** a `spawn`-context process pool whose worker, a function in an importable test-support
  module, reads the fixture and returns the `FieldSnapshot`, with the result awaited under a timeout
- **When** the parent receives it
- **Then** the worker ran in a different process, and the result is equivalent, under every
  round-trip property above, to a snapshot read in the parent; and, only where `torch` is
  importable, a `torch.utils.data.DataLoader` with `num_workers=2` over a module-level `Dataset`
  whose `__getitem__` returns a `FieldSnapshot`, run with `multiprocessing_context` `"spawn"` and,
  where available, `"fork"`, both with a module-level identity `collate_fn` and with
  `batch_size=None, collate_fn=None` (torch's `default_convert` path), yields snapshots satisfying
  the same properties

#### Scenario: Snapshot arrays own their data and cannot be mutated through a base

- **Given** a full-extent read and a sub-box read of the fixture — the full-extent case being the one
  where `np.ascontiguousarray` returns a view rather than a copy
- **When** the returned snapshots are inspected
- **Then** in **both** cases every exposed array reports `flags.writeable is False` **and**
  `base is None`, so no other writable object shares its memory; assigning into any array raises;
  and two reads of the same region do not share memory

### Requirement: Field selection validated before any array is read

The reader SHALL accept a caller-selected field set drawn from a canonical short-name map covering
every component the wing plotfiles write (`u`, `v`, `w`, `gradpx`, `gradpy`, `gradpz`, `density`,
`tracer`), defaulting to the six that the LEV and control-volume callers require. It SHALL reject an
unknown short name, and reject a canonical name absent from the plotfile, **before** reading any field
array. It SHALL read exactly the requested fields and no others, and none at all for a region with
zero cells on any axis (see "Zero-cell regions read no field data").

`fields` SHALL be a non-string iterable of short names. A bare `str` (or `bytes`) SHALL raise
`ValueError` before any other check, naming the value and suggesting the one-element tuple, because
`tuple("gradpx")` splits it into characters: a bare string would otherwise be read as one field
per character (`"uvw"` silently reads `u`, `v`, `w`, and `"gradpx"` reports six unknown one-letter
fields).

It SHALL reject duplicate short names: a duplicate silently desynchronises `arrays` (a dict, which
collides) from `field_names` (a tuple, which does not), yielding a `PointCloud` whose column count
exceeds the number of distinct fields and duplicating a training column, and it re-reads the same
field once per repetition.

It SHALL verify the plotfile's **on-disk** precision is 8-byte floating point, **before reading any
field array** -- a 512-cubed plotfile would otherwise be read in full, gigabytes and minutes, before
being refused -- via the dtype yt parses from the FAB RealDescriptor (`ds.index._dtype`). The check
SHALL compare the dtype's *format* (kind and itemsize), not equality against `np.float64`: a
big-endian `>f8` plotfile is bit-exactly valid double precision but compares unequal on a
little-endian host, and rejecting it would be a false negative with a misleading diagnosis. Inspecting the returned array's dtype does **not** work and
must not be relied upon: yt's AMReX frontend allocates its output buffers `float64`
unconditionally and widens the on-disk FAB into them, so an fp32 build yields `float64` arrays
carrying fp32-truncated values and a returned-dtype check can never fire. The returned-array check
MAY be kept as a defence-in-depth assertion, but it is not the guard.

#### Scenario: Selecting fields beyond the default six

- **Given** the committed fixture, which carries `density` and `tracer` in addition to the six
  velocity/pressure-gradient components
- **When** `read_field_snapshot` is called with `fields=("u", "density", "tracer")`
- **Then** the snapshot contains exactly those three arrays, `field_names` records them in the
  requested order, and a recording proxy over the covering grid confirms exactly the three
  corresponding `('boxlib', …)` tuples were read and no others

#### Scenario: An unknown or absent field is rejected before any read

- **Given** the committed fixture, and separately a fixture regenerated without one canonical field
- **When** `read_field_snapshot` is called with a short name outside the canonical map, or with a
  canonical name the plotfile does not carry
- **Then** it raises `ValueError` naming the offending field, and a recording proxy over the covering
  grid confirms **no** field array was read before the raise

#### Scenario: A genuine fp32 plotfile is refused rather than silently upcast

- **Given** a real single-precision boxlib plotfile — one whose FAB RealDescriptor declares `float32`,
  not merely a stub that returns a `float32` array
- **When** `read_field_snapshot` reads it
- **Then** it raises `ValueError` naming the observed on-disk precision, **no field array has been
  read**, and no snapshot is constructed — even though every array yt would return from it reports
  `dtype == float64`

#### Scenario: A big-endian double-precision plotfile is accepted

- **Given** a plotfile whose FAB RealDescriptor declares 8-byte reals in big-endian byte order, which
  yt reports as `>f8`
- **When** `read_field_snapshot` reads it
- **Then** it succeeds and the values are bit-exact, because `>f8` is valid double precision — an
  equality check against `np.float64` would reject it on a little-endian host and misreport it as an
  fp32 build

#### Scenario: Duplicate field names are rejected

- **Given** the committed fixture
- **When** `read_field_snapshot` is called with a `fields` tuple naming the same short name twice
- **Then** it raises `ValueError` identifying the duplicate, and a recording proxy confirms no field
  array was read — rather than returning a snapshot whose `arrays` has fewer entries than
  `field_names` and whose point cloud carries a duplicated column

#### Scenario: A bare string is not a field list

- **Given** the committed fixture, and separately a path that does not exist
- **When** `read_field_snapshot` is called with `fields="gradpx"`, `fields="uvw"`, `fields="u"` or
  `fields=b"u"`
- **Then** each raises `ValueError` saying `fields` must be a sequence of names and suggesting
  `("gradpx",)` (resp. the value as a one-element tuple), on the nonexistent path as well, so the
  check precedes the path check; while `fields=("gradpx",)` and `fields=["u", "v"]` read normally

### Requirement: Corpus addressing by config and step

The package SHALL provide `mosquito_cfd.field_surrogate.corpus.FieldCorpus`, addressing plotfiles by
`(config_id, step)` against a **caller-supplied** corpus root, because the real corpus lives on cluster
NFS and is not in the repository. It SHALL expose the available config ids, the available steps for a
config, that config's kinematic parameters, the run's own `run_metadata.json` read through
unchanged, and a snapshot accessor forwarding to `read_field_snapshot` that adds the run's identity
and digest-pinned provenance and refuses zero-cell regions (see "Corpus snapshots carry run identity
and digest-pinned provenance" and "Training-facing entry points refuse zero-cell snapshots").

The run-directory listing SHALL be exposed as the public function
`mosquito_cfd.field_surrogate.corpus.scan_plotfiles(directory) -> dict[int, Path]`, with exactly the
semantics this requirement gives `steps()` and `plotfile()`'s fallback (name pattern, directory
filter, skip list, duplicate error, one `os.scandir`), so that every plotfile consumer in the
repository, including `visualization.flow_video`, agrees on which plotfiles exist.

Steps SHALL be discovered from the `plt*` **directories** actually present on disk, never assumed from
a deck's `plot_int` — a run can be truncated, as 15 of 27 configs were at `ns.cfl = 0.3`. Entries that
are not directories, or whose suffix after `plt` is not one or more ASCII digits, SHALL be ignored,
and the returned step list SHALL be sorted ascending and deterministic across calls. A plotfile name
SHALL be `plt` followed by one or more **ASCII** digits `0-9` and nothing else, matched against the
whole name. A non-ASCII decimal digit (e.g. `plt١٠٠`) or a trailing newline (`plt100\n`) does not
make a plotfile name.

Listing a run directory SHALL cost one `os.scandir` call and no per-entry Python-level `stat`. The
directory filter SHALL use each `DirEntry`'s own `is_dir()`, which follows symlinks as
`Path.is_dir()` does. An entry whose type check fails in a way Python 3.11's `Path.is_dir()`
reported as "not a directory" SHALL be skipped, exactly as before the listing changed: errno
`ENOENT` (removed mid-listing, or a dangling symlink), `ENOTDIR` (a symlink through a file),
`EBADF`, `ELOOP` (a symlink loop), Windows errors 21, 123 and 1921, and `ValueError`. Any other
`OSError` from the check (e.g. `EACCES`, `EIO`) SHALL propagate rather than being silently skipped.
An entry whose type the listing itself reports is not stat'ed, so a stat-only error on it does
not arise.
Returned plotfile paths SHALL be `pathlib.Path` objects equal to `run_dir / name`. This is the only place the corpus uses
`os` rather than `pathlib`: on Python 3.11–3.13, no `Path` API exposes the `DirEntry`.

The manifest SHALL be read and parsed at most once per `FieldCorpus` instance, whatever the number of
public calls. Plotfile presence SHALL NOT be cached. A manifest edited on disk is picked up by
constructing a new instance; there is no mtime check, since that would cost a `stat` per call.

Two **directories** that parse to the same step (e.g. `plt100` and `plt00100`) SHALL make every
operation that lists the run directory — `steps()` and `plotfile()`'s fallback scan — raise
`ValueError` naming both directory names in sorted order, rather than returning the step twice or
returning whichever directory the filesystem lists first. A non-directory entry never counts toward a
duplicate.

`step` SHALL be an `int` or `np.integer`, not a `bool`, and SHALL be `>= 0`; anything else SHALL raise
`ValueError` showing the `repr` of the bad value before the manifest is read or the run directory is
touched.

`plotfile()` SHALL first test whether the canonical AMReX name `plt{step:05d}` is a directory and, if
so, return it without listing the run directory; only when that name is not a directory (absent, or a
non-directory entry) SHALL it scan. The fast path trusts the canonical name and so does not detect a
non-canonical twin of that step; the scan paths do. The manifest membership check SHALL still precede
the fast path, so an unknown config raises the same error on both paths.

`global_params` SHALL return **exactly** the kinematic parameters — `stroke_amp_deg`,
`frequency_fstar`, `pitch_amp_deg` — and no other manifest field. Returning the whole config would
leak `reynolds`, `split`, `input_file` and `index` into what a caller passes as
`global_params_values`.

Sweep-manifest parsing SHALL reuse `mosquito_cfd.force_surrogate.dataset.load_manifest_configs` rather
than re-reading the JSON, so a malformed manifest raises the same guarded error on both paths. A
missing config, a missing step, and a missing corpus root SHALL each raise a self-describing error
naming what was looked for and where.

#### Scenario: Resolving a snapshot by config and step

- **Given** a corpus root containing a sweep manifest and a config directory holding `plt00100` and a
  valid `run_metadata.json`
- **When** `FieldCorpus.snapshot(config_id, step=100)` is called
- **Then** it returns the `FieldSnapshot` for that plotfile, with arrays bit-identical to
  `read_field_snapshot` on the same path, and `global_params(config_id)` returns that config's
  kinematics from the manifest

#### Scenario: Step discovery ignores non-plotfile entries and is deterministic

- **Given** a config directory containing `plt00100`, `plt01000`, a regular *file* named `plt00200`, a
  directory `plt00300.old`, and a directory `pltXXXXX`
- **When** `steps(config_id)` is called twice
- **Then** both calls return exactly `[100, 1000]`, ascending

#### Scenario: Steps sort numerically, not lexically

- **Given** a config directory whose plotfile names have **inconsistent** zero-padding, such as
  `plt2`, `plt10` and `plt00100` — the regex permits any digit width
- **When** `steps(config_id)` is called
- **Then** it returns `[2, 10, 100]`. Uniformly padded names make lexical and numeric order coincide,
  so a matrix of padded names alone cannot detect a missing sort.

#### Scenario: Kinematic parameters are exactly the three, and nothing else

- **Given** a manifest config carrying kinematics alongside `reynolds`, `split`, `input_file` and
  `index`
- **When** `global_params(config_id)` is called
- **Then** its key set is exactly `{stroke_amp_deg, frequency_fstar, pitch_amp_deg}`

#### Scenario: Missing config, step, or root is self-describing

- **Given** a corpus root whose manifest omits the requested config; a config directory with no
  plotfile for the requested step; and separately a root path that does not exist
- **When** the caller requests a snapshot in each case
- **Then** each raises a `ValueError` naming the requested config, step, or root and the path searched,
  rather than a bare `KeyError` or `FileNotFoundError`

#### Scenario: A non-integer or negative step is rejected before any I/O

- **Given** a freshly constructed `FieldCorpus`, with manifest loading, `Path` directory checks, and
  `os.scandir` listings recorded from after construction
- **When** `plotfile()` or `snapshot()` is called with `step` equal to `"100"`, `100.0`, `True`,
  `np.bool_(True)`, `-1` or `None`
- **Then** each raises `ValueError` showing the `repr` of the bad `step`, and nothing was recorded;
  while `np.int64(100)`, `np.int32(100)` and `0` resolve their plotfiles

#### Scenario: Two directories for one step are an error, not a coin toss

- **Given** a config directory containing directories `plt100`, `plt00100` and `plt200` (a
  non-canonical name, so `plotfile(config_id, 200)` misses the fast path and scans), listed in an order
  that puts `plt100` first
- **When** `steps(config_id)` and `plotfile(config_id, 200)` are called
- **Then** both raise `ValueError` naming `plt00100` and `plt100`, in that order

#### Scenario: A non-directory entry is never a duplicate or a fast-path hit

- **Given** a config directory holding a regular file `plt00100` beside a directory `plt100`, and
  separately a regular file `plt100` beside a directory `plt00100`
- **When** `plotfile(config_id, 100)` and `steps(config_id)` are called on each
- **Then** the first resolves `plt100` through the scan and the second resolves `plt00100`, and
  `steps()` returns `[100]` in both without raising

#### Scenario: The canonical name resolves without listing the run directory

- **Given** a config directory holding `plt00100` and `plt100000`, and a spy on directory listing
- **When** `plotfile(config_id, 100)` and `plotfile(config_id, 100000)` are called
- **Then** each returns its canonical path and no directory listing was recorded; and when called for
  a step present only under a non-canonical name such as `plt7`, it lists the directory once and
  returns `plt7`, and for a step not present at all it lists the directory once and names the
  available steps

#### Scenario: The fast path does not see a non-canonical twin

- **Given** a config directory containing directories `plt100` and `plt00100`
- **When** `plotfile(config_id, 100)` is called
- **Then** it returns `plt00100` without raising, while `steps(config_id)` raises — the documented
  trade-off, pinned so a change to it is deliberate

#### Scenario: Listing a run directory costs one scandir and no per-entry stat

- **Given** two config directories, one holding 3 and the other 30 plotfile directories plus a
  regular file named like a plotfile, and `os.scandir` and `os.stat` calls under the corpus root
  recorded after construction
- **When** `steps(config_id)` is called on each
- **Then** each call records exactly one `os.scandir` of that run directory, which is the positive
  control that the spy fires, and the two calls record the same number of `os.stat` calls whatever
  the entry count

#### Scenario: A failing entry type check is skipped exactly where Path.is_dir() skipped it

- **Given** a listing that yields beside a real `plt00100` one `plt`-named entry whose `is_dir()`
  raises, in turn, each error in the skip list above; separately, one whose `is_dir()` raises
  `PermissionError` or an `EIO` `OSError`; and, on a platform where creating symlinks succeeds, a
  real `plt00100` beside a dangling symlink, a symlink loop and a symlink through a file
- **When** `steps(config_id)` is called
- **Then** every skip-list error and every real broken symlink yields `[100]`, while
  `PermissionError` and `EIO` propagate

#### Scenario: A corpus pass reads the manifest once and lists each run directory once

- **Given** a corpus of 3 configs × 5 canonically named plotfiles, plus a non-canonically named `plt7`
  in the first config, with manifest loads and `os.scandir` calls under the corpus root recorded
  after construction
- **When** `config_ids()`, then `steps()` for each config, then `plotfile()` for every
  `(config, step)` are called
- **Then** the manifest was loaded once, and `os.scandir` was called exactly 3 times, once per
  `steps()`. No `plotfile()` call for a canonically named step listed a directory, while
  `plotfile(first_config, 7)` recorded exactly one listing, the positive control

#### Scenario: Plotfile presence is re-read, the manifest is not

- **Given** a `FieldCorpus` whose `steps(config_id)` has returned `[100]`
- **When** a directory `plt00500` is created and `steps(config_id)` is called again; and, separately,
  the manifest on disk is rewritten to add a config
- **Then** the second `steps()` call returns `[100, 500]`; the existing instance's `config_ids()` is
  unchanged; and a newly constructed instance lists the added config

#### Scenario: A symlinked plotfile directory counts

- **Given** a config directory holding a real directory `plt00100` and a symlink `plt300` to another
  real directory, on a platform where creating the symlink succeeds
- **When** `steps(config_id)` and `plotfile(config_id, 300)` are called
- **Then** `steps()` returns `[100, 300]` and `plotfile(config_id, 300)` returns the symlink path.
  The non-canonical name sends both calls through the listing

#### Scenario: Only ASCII-digit, whole-name plotfile directories count

- **Given** a config directory holding a real directory `plt١٠٠` (Arabic-Indic digits), alone and
  beside a real `plt00100`; and a listing that yields entries named `plt١٠٠` and `plt100` followed by
  a newline, each reporting itself a directory, beside `plt00100`. The latter is simulated so it runs
  on every OS, including Windows, which forbids a newline in a name
- **When** `steps(config_id)` and `plotfile(config_id, 100)` are called
- **Then** with `plt١٠٠` alone, `steps()` returns `[]` and `plotfile(config_id, 100)` raises the
  missing-step error; in every other case `steps()` returns `[100]` without the ambiguity error and
  `plotfile(config_id, 100)` resolves `plt00100`

### Requirement: DoMINO volume-half adapter with the geometry gap stated, not filled

The package SHALL provide `mosquito_cfd.field_surrogate.domino_adapter.to_domino_volume`, emitting a
plain dict under DoMINO's own key names for the part this corpus can honestly supply:
`volume_mesh_centers` `(N, 3)`, `volume_fields` `(N, F)`, `grid` `(nx, ny, nz, 3)`,
`global_params_values` `(P, 1)`, and `global_params_reference` `(P, 1)`. It SHALL NOT add a batch
dimension, because DoMINO's own datapipe adds one. Global parameters SHALL be caller-supplied, so no
normalization policy is baked into the reader. They SHALL be rejected with `ValueError` if they
differ in length or contain a non-finite value (NaN or `±inf`), since nothing downstream checks
them. Each SHALL also be a non-empty one-dimensional sequence: input whose `np.asarray` has
`ndim != 1` (e.g. `[[1, 2, 3], [4, 5, 6]]`, which would otherwise fold to `(6, 1)` and pass the
length check against a differently shaped 2-D reference) or length 0 SHALL raise `ValueError`
naming the observed shape. The check SHALL run before the snapshot is touched.

`to_domino_volume` SHALL refuse a snapshot with zero cells on any axis (see "Training-facing entry
points refuse zero-cell snapshots").

Every returned array SHALL be read-only, matching `FieldSnapshot`'s own arrays, and none SHALL alias
the caller's input. `grid` SHALL be a reshaped view of `volume_mesh_centers` rather than a second
copy of the same coordinates.

The adapter's documentation SHALL state three things about `grid`:
- here it is the snapshot's own cell centres, at the snapshot's resolution;
- stock DoMINO's `grid` is instead a fixed-resolution `interp_res` grid paired with `sdf_grid`;
- choosing that grid is F3's decision.

The emitted key, shape and values SHALL be unchanged until F3 makes that decision.

The adapter SHALL import neither `physicsnemo` nor `torch`, at module scope or lazily, so the package
imports on the CPU-only CI runner and this change adds no dependency.

The adapter's documentation SHALL state, as a matter of scientific honesty (**CC-4**), that: stock
DoMINO is a geometry→fields surrogate whose flow-field values are **predicted outputs**, so
`volume_fields` is a training **target** and not an encoder input; `geometry_coordinates`, `sdf_grid`,
`sdf_nodes`, `surf_grid`, `sdf_surf_grid`, and the `surface_mesh_*` arrays are **not produced here**
and DoMINO cannot train without them; and this corpus's plotfiles carry **no pressure field**, only its gradient, so `volume_fields` is
velocity plus pressure-gradient rather than the velocity/pressure/turbulent-viscosity set DoMINO's own
examples assume.

#### Scenario: The emitted and absent key sets match an external specification

- **Given** the two key-set constants the adapter defines
- **When** they are compared against the key names written independently in the test
- **Then** they match exactly and are disjoint. Asserting only that the emitted keys equal the
  module's own constant is a tautology: moving a geometry-half key into the emitted set and
  zero-filling it would satisfy it.

#### Scenario: Only the volume half is emitted, and absences are real

- **Given** a `FieldSnapshot` and a caller-supplied set of global parameters
- **When** `to_domino_volume` is called
- **Then** the returned dict's key set is exactly the five volume-half keys with the stated shapes and
  no leading batch dimension, and `geometry_coordinates`, `sdf_grid`, `sdf_nodes`,
  `surface_mesh_centers`, `surface_normals`, and `surface_areas` are **absent from the dict** rather
  than present and zero-filled

#### Scenario: The grid is oriented to the snapshot's own axes

- **Given** a `FieldSnapshot` over a region with distinct extents on each axis
- **When** `to_domino_volume` is called
- **Then** `grid[0, 0, 0] == (x[0], y[0], z[0])` and `grid[nx-1, 0, 0] == (x[-1], y[0], z[0])`, so an
  `indexing="xy"` meshgrid swap is caught

#### Scenario: The adapter carries no GPU dependency

- **Given** an interpreter in which importing `torch` or `physicsnemo` would fail
- **When** `mosquito_cfd.field_surrogate.domino_adapter` is imported and `to_domino_volume` is called
- **Then** both succeed, and no `import torch` or `import physicsnemo` statement exists anywhere in the
  module at any scope

#### Scenario: The honesty claims are present in the documentation

- **Given** the adapter's documentation
- **When** it is inspected
- **Then** it states that `volume_fields` is a target rather than an encoder input, that this corpus
  has no pressure field and carries its gradient instead, and it names each of the eight absent keys.
  The paragraph that describes `grid` also names `interp_res` and `sdf_grid`, says it is at the
  snapshot's resolution, and names F3 as the owner of the choice

#### Scenario: Global parameters must be non-empty and one-dimensional

- **Given** a valid snapshot
- **When** `to_domino_volume` is called with `global_params_values=[[1, 2, 3], [4, 5, 6]]` and
  `global_params_reference=[[1, 2], [3, 4], [5, 6]]`; with both `()`; with a 0-d scalar; and with a
  1-D values sequence against a 2-D `(3, 1)` reference
- **Then** each raises `ValueError` naming the offending argument and its shape, while flat
  sequences of equal non-zero length succeed with `(P, 1)` outputs as before

## ADDED Requirements

### Requirement: Corpus snapshots carry run identity and digest-pinned provenance

The package SHALL provide a private, dependency-free module
`mosquito_cfd.field_surrogate._provenance`, importing nothing beyond the standard library, with two
functions.

**`read_run_metadata(path, *, config_id) -> dict`** returns the parsed JSON object unchanged. It
SHALL raise `ValueError`, with the message prefix below and the field tag `run_metadata.json`, when
any of the following holds:
- `path` is not a regular file;
- reading or decoding it raises `OSError` or `UnicodeDecodeError` (chained);
- it is not valid JSON;
- its top level is not a JSON object.

**`run_provenance(meta, *, config_id, path) -> tuple[str, str]`** returns
`(git_commit, docker_image)`. It SHALL raise `ValueError` when any of the following holds:
- `meta["config"]` is absent, is not a `str`, or differs from `config_id`. A `run_metadata.json`
  copied into the wrong run directory must not lend its digest to another run's plotfiles.
- `meta["git"]` is not an object, or `meta["git"]["commit"]` is absent, is not a `str`, or does not
  fully match `[0-9a-f]{40}`. The full match refuses a trailing newline and uppercase hex.
- `meta["docker_image"]` is absent, is not a `str`, or does not fully match
  `[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}`. The check covers the digest suffix and a non-empty
  repository of lowercase reference characters; it does not parse the full OCI reference grammar.
  That refuses:
  - a tag-only reference;
  - a bare `sha256:<hex>` with no repository;
  - a digest with text around it;
  - surrounding whitespace.

Every message from either function SHALL have exactly the form
`run_metadata for config <repr(config_id)> (<path>): <field>: <detail>`, built with the builtin
`repr`, so a test can assert that it starts with the prefix followed by `<field>: `. The path, which
contains `run_metadata.json`, cannot satisfy that assertion by accident. `<field>` SHALL be one of
`run_metadata.json` (the file itself), `config`, `git`, `git.commit` or `docker_image`.

The values returned SHALL be the file's strings exactly, never stripped or rewritten.

`FieldCorpus` SHALL expose **`run_metadata(config_id) -> dict`**. It SHALL check manifest membership
and the run directory as `run_dir()` does, then return
`read_run_metadata(run_dir / "run_metadata.json", config_id=config_id)`:
read through, with no key added, defaulted, renamed or derived. Each call SHALL parse the file afresh,
so a caller's mutation of one result, including nested values, cannot reach a later call.

**`FieldCorpus.snapshot(config_id, step, *, lo, hi, halo, fields)`** SHALL proceed in this order:
1. Validate `step` and the region arguments (`fields`, `halo`, `lo`, `hi`) with the same pure
   checks `read_field_snapshot` uses, before any I/O. An argument error is therefore reported as
   such whatever the corpus's state.
2. Resolve `plotfile(config_id, step)`.
3. Read and validate the run's provenance.
4. Read the plotfile.
5. Apply the zero-cell refusal.

The provenance checks SHALL run before the plotfile is read, so a corpus without valid provenance
fails before the cost of a yt read.

The returned snapshot's `config_id` and `step` SHALL be the validated arguments (`step` a Python
`int` even when given as `np.integer`). Its `git_commit` and `docker_image` SHALL be the values
`run_provenance` returned. Nothing SHALL be fabricated, defaulted or inferred: there is no fallback
to `None`, to the running checkout's git, or to an image tag. Its arrays, coordinates, `dx`, `time`,
`max_level`, `field_names` and `source` SHALL be exactly those `read_field_snapshot` returns for
`plotfile(config_id, step)`.

`_provenance.py` SHALL import only the standard library, and reading or validating provenance SHALL
NOT import `mosquito_cfd.force_surrogate`. Importing that package loads pandas and pyarrow and
switches the process's matplotlib backend. `FieldCorpus`'s manifest parsing already imports it through
`force_surrogate.dataset.load_manifest_configs`, as required above. That existing cost is unchanged by
this requirement and is tracked separately.

#### Scenario: A corpus snapshot carries its run's identity and digest

- **Given** a corpus whose run directory holds `plt00100` and a `run_metadata.json` with `config`
  equal to the config id, a 40-character lowercase `git.commit`, and a `docker_image` of the form
  `ghcr.io/talmolab/mosquito-cfd@sha256:<64 hex>`
- **When** `FieldCorpus.snapshot(config_id, np.int64(100))` is called
- **Then** the snapshot's `config_id`, `step` (`type(step) is int`), `git_commit` and
  `docker_image` equal the file's values exactly; and its arrays, coordinates, `dx`, `time`,
  `max_level`, `field_names` and `source` equal, property by property,
  `read_field_snapshot(plotfile(config_id, 100))`'s

#### Scenario: Missing or unverifiable provenance is refused before any read

- **Given** a run directory holding `plt00100`, and `run_metadata.json` in turn:
  - absent;
  - a directory;
  - non-UTF-8 bytes;
  - invalid JSON;
  - a top-level JSON array;
  - a `config` that is absent, `null`, or names a different config;
  - a `git` that is absent or `null`;
  - a `git.commit` that is absent, `123`, 7 characters, 40 uppercase hex characters, or 40 hex
    characters plus a trailing newline;
  - a `docker_image` that is absent, `5`, tagged `:latest`, a bare `sha256:<64 hex>`,
    `repo:latest #sha256:<64 hex>`, `:@sha256:<64 hex>`, `GHCR.io/x@sha256:<64 hex>`, or a valid
    reference with a leading space, a trailing space, or a trailing newline
- **When** `FieldCorpus.snapshot(config_id, 100)` is called with `yt.load` replaced by a function
  that fails the test if called
- **Then** each raises exactly `ValueError` whose message begins
  `run_metadata for config '<config_id>' (<path>): <field>: ` with the failed field (`run_metadata.json`
  for the file-level cases), and `yt.load` was never
  called; while the positive control with valid metadata does call it

#### Scenario: Argument errors and plotfile errors win over provenance errors

- **Given** a run directory holding `plt00100` and **no** `run_metadata.json`
- **When** `FieldCorpus.snapshot` is called with `fields="u"`, with `lo > hi`, with `step=-1`, with
  an unknown config, and with a step that has no plotfile
- **Then** each raises its own argument, config or step `ValueError` and not the provenance error,
  and the argument errors are raised with no manifest read and no directory listed

#### Scenario: run_metadata is read through, not reshaped

- **Given** a run directory whose `run_metadata.json` carries the real pod-side key set plus a key
  unknown to this package
- **When** `run_metadata(config_id)` is called twice, and the first result's top-level and nested
  (`["git"]["commit"]`) values are mutated
- **Then** each result is a `dict` (`type(result) is dict`) equal to `json.loads` of the file,
  including the extra key, and the second result is unaffected by the mutations; and for a config
  whose run directory exists but holds no `run_metadata.json` the call raises `ValueError` naming
  the expected path, with field `run_metadata.json`

#### Scenario: Reading provenance does not load the force-surrogate stack

- **Given** a fresh interpreter and a valid `run_metadata.json`
- **When** it imports `mosquito_cfd.field_surrogate._provenance` and calls `read_run_metadata` and
  `run_provenance` on that file
- **Then** neither `mosquito_cfd.force_surrogate`, `pandas` nor `matplotlib.pyplot` appears in
  `sys.modules`; and the module's import statements name only standard-library modules

### Requirement: Training-facing entry points refuse zero-cell snapshots

`read_field_snapshot` SHALL keep returning a zero-cell snapshot for a request that reaches no cell
on some axis (its existing, specified behaviour). The two entry points a training pipeline consumes
SHALL refuse one instead, because a zero-point example is structurally valid, concatenates into a
batch, and contributes nothing, a failure with no symptom:
- `FieldCorpus.snapshot` SHALL raise `ValueError` after the read when any of `x`, `y`, `z` is empty,
  naming the config, step, `lo`, `hi`, `halo` and the per-axis cell counts;
- `to_domino_volume` SHALL raise `ValueError` before building the point cloud when the snapshot has
  zero cells on any axis, naming the per-axis cell counts and the snapshot's `source`.

A request that yields at least one cell on every axis is unaffected.

#### Scenario: A zero-cell corpus request is refused

- **Given** a corpus with valid provenance and a request entirely beyond the domain on one axis
  (farther than `halo` cells), and separately a point request exactly on the upper domain edge
- **When** `FieldCorpus.snapshot` is called with each
- **Then** each raises `ValueError` naming the config, step, region and per-axis cell counts; while
  `read_field_snapshot` on the same plotfile and request still returns the zero-cell snapshot; a
  one-cell request (`lo == hi` inside the domain) through `FieldCorpus.snapshot` succeeds; and a
  full-extent request with `fields=()`, which has cells but no columns, succeeds

#### Scenario: A zero-cell snapshot cannot become a DoMINO example

- **Given** a zero-cell snapshot from `read_field_snapshot`, and a one-cell snapshot
- **When** `to_domino_volume` is called on each with valid global parameters
- **Then** the zero-cell call raises `ValueError` naming the per-axis cell counts and the snapshot's
  `source`, and the one-cell call returns `volume_mesh_centers` of shape `(1, 3)`; and a zero-cell
  snapshot passed with invalid global parameters raises the global-parameters error, proving those
  checks run first
