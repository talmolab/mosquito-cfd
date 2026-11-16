## ADDED Requirements

### Requirement: Snapshot reads are bit-identical and release yt's memory before returning

`read_field_snapshot` SHALL return, for every request, arrays equal to those of a full level-0
covering grid read and sliced in memory. They SHALL match in values, dtype, shape, strides, C- and
F-contiguity, `writeable`, and `base is None`. The metadata SHALL be equal in the same way: `x`, `y`,
`z`, `dx`, `time`, `source`, `max_level` and `field_names`.

The reader SHALL release yt's memory as it reads:
- each field's entry in the covering grid's `field_data` cache SHALL be removed as soon as that field
  has been copied, so that at most one field is cached at a time;
- the covering grid's data SHALL be cleared once all fields are read.

Before returning a snapshot, on every path that loaded the plotfile, the reader SHALL:
- drop its covering-grid and dataset references;
- run a **full** cyclic garbage collection.

The full collection is needed because yt's dataset, index, field-info and covering-grid objects form
reference cycles that reference counting cannot free. Under normal (enabled) automatic GC, these
objects are promoted to the oldest generation during the read itself. A young-generation collection
therefore frees none of them, and each read's cycle would accumulate until Python's next full
collection; this was measured on CPython 3.11, the version CI pins, and a full collection frees the
cycle on any version. The returned snapshot SHALL reference no yt object.

#### Scenario: Outputs are bit-identical to a full-grid reference

- **Given** the following inputs:
  - the committed 6³ fixture;
  - a generated anisotropic plotfile;
  - when `MOSQUITO_CFD_PLOTFILE_ROOT` names a directory containing `t3c-fine/plt*`, the last such
    real multi-FAB wing plotfile.

  The reference reads the full level-0 covering grid with `yt` in the test and slices it in memory.
- **When** `read_field_snapshot` is called over all eight canonical fields with:
  - every region-parity case and every outside-the-domain divergence case, at their recorded `halo`
    values 0 to 3, mapped onto each plotfile's domain;
  - on the real plotfile, only the full extent, `halo2`, `x_slab_only`, `outside_domain` and
    `above_within_reach_offface_h2` cases.
- **Then** every returned array and metadata field equals the reference's on every listed property;
  and `extract_eulerian_box` still matches the frozen pre-refactor copy across the parity matrix,
  including its zero-cell cases.

#### Scenario: Each field leaves the covering-grid cache once copied

- **Given** a recording proxy over the real covering grid that forwards `field_data` and
  `clear_data`
- **When** a full-extent read of the six default fields runs
- **Then** at each field read no earlier field remains in `field_data`; `field_data` is already empty
  at the moment `clear_data()` is called; and `clear_data()` is called exactly once

#### Scenario: Field-cache release bounds the peak

- **Given** a generated 96³ single-level plotfile with six FP64 fields, `S` the size of one field
  in bytes (8 × cells), a warm-up read, and a full collection before each traced read
- **When** full-extent reads of one field and of six fields are each traced with `tracemalloc`
- **Then** the six-field peak exceeds the one-field peak by at most `7.5·S`

#### Scenario: The dataset is dead when the read returns, with automatic GC enabled

- **Given** a generated 64³ single-level plotfile, `yt.load` wrapped to keep a weak reference to each
  real `yt` `Dataset` it creates (never to a test proxy around one), automatic garbage collection **enabled**, and a warm-up read
- **When** `read_field_snapshot` returns a full-extent snapshot, and separately a zero-cell snapshot
  (`REGION_CASES`' `outside_domain`)
- **Then** in both cases the dataset's weak reference is dead on return, and no attribute of the
  returned snapshot is a `yt` object

### Requirement: Zero-cell regions read no field data

A request whose region holds zero cells on any axis SHALL NOT build a covering grid or read any field.
Every plotfile guard SHALL run first, in its existing order:
- the multi-level refusal;
- the on-disk precision attribute check and fp32 guard;
- the missing-field check.

Each returned field array SHALL be a fresh, read-only, owning, zero-size FP64 array of the region's
shape. The reader SHALL then perform the same teardown as a non-empty read.

#### Scenario: A zero-cell region reads nothing

- **Given** the committed fixture behind a proxy that records covering-grid construction in its own
  log
- **When** `read_field_snapshot` is called on `REGION_CASES`' `upper_edge` and `outside_domain`, on
  `DIVERGENCE_CASES`' `above_beyond_reach_h2`, and on `x_below_yz_inside_h1`, which is empty on the
  x axis only
- **Then** no covering grid was constructed and no field was read, and each returned array equals the
  full-grid reference on every listed property

#### Scenario: A zero-cell read costs no field-sized memory

- **Given** a generated 96³ plotfile, `S` the size of one field in bytes, a warm-up read, and a full
  collection before each traced read
- **When** `REGION_CASES`' `outside_domain` request (`lo=(7,7,7)`, `hi=(9,9,9)`, `halo=0`, mapped
  onto the file's domain) is traced with the six default fields and with `fields=()`
- **Then** the two peaks differ by less than `S`

#### Scenario: Guards still fire before the zero-cell short-circuit

- **Given** `REGION_CASES`' `outside_domain` request
- **When** it is made:
  - against a proxy reporting `max_level = 1`;
  - against a proxy whose index lacks `_dtype`;
  - against a genuine fp32 plotfile;
  - against a plotfile written without one of the requested fields.
- **Then** each raises its own guard's `ValueError`, exactly as for a non-empty request: the CC-F3
  refusal, the precision-undeterminable refusal, the on-disk precision error, and the missing-field
  error

## MODIFIED Requirements

### Requirement: Field selection validated before any array is read

The reader SHALL accept a caller-selected field set drawn from a canonical short-name map covering
every component the wing plotfiles write (`u`, `v`, `w`, `gradpx`, `gradpy`, `gradpz`, `density`,
`tracer`), defaulting to the six that the LEV and control-volume callers require. It SHALL reject an
unknown short name, and reject a canonical name absent from the plotfile, **before** reading any field
array. It SHALL read exactly the requested fields and no others, and none at all for a region with
zero cells on any axis (see "Zero-cell regions read no field data").

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

### Requirement: Region semantics match the legacy adapter wherever the request meets the domain

The region semantics SHALL be identical to the existing adapter's whenever, on every axis,
`lo <= hi`, `lo <= domain_right_edge` and `hi > domain_left_edge`. In that region the two SHALL return
the same cells. In both, `±inf` is accepted as "full extent" along an axis, per axis independently, an
optional `halo` adds extra cells on every side, and the read is performed as a full level-0 covering
grid sliced in memory. This reader alone departs from that for a region with zero cells on some
axis: such a request SHALL build no covering grid, SHALL read no field, and SHALL return the same
empty arrays the full read would have produced, only after every plotfile guard has run. See
"Zero-cell regions read no field data".

"The legacy adapter" here means the **pre-refactor** `extract_eulerian_box`, frozen in
`tests/fixtures/legacy_extract_eulerian_box.py`. Once the delegation below lands, the importable
`extract_eulerian_box` is a wrapper over this reader, so a comparison against it is a
self-comparison; every legacy comparison SHALL use the frozen copy.

There are two deliberate differences from legacy.

The first is how `halo` interacts with the domain edge ("halo is reach"). The
request's cell range SHALL be padded by `halo` first, and only the part of the padded range inside
the domain SHALL be kept. So a request up to `halo` cells outside the domain returns the in-domain
cells it reaches, and one farther out returns zero cells on that axis. The legacy adapter instead
clamps the corners onto the domain edge *before* padding. It therefore returns edge cells for a
request arbitrarily far outside the domain — and, at `halo = 0`, a spurious cell at index 0 for a
request wholly below it. Outside the parity region this reader SHALL return no more cells than
legacy.

The second is that an **inverted** request — `lo > hi` on any axis, compared on the raw corners —
SHALL raise `ValueError` naming each inverted axis and only those, with its `lo` and `hi` values,
before `yt` is imported. The legacy adapter never errors here: it returns a small region built from
the padded indices (one cell at `halo = 0`, up to `2·halo + 1` cells otherwise, or none after domain
clipping), so a swapped corner pair or a sign error in a `centre ± margin` computation silently yields
a plausible-looking region. The comparison is strict: `lo == hi` is a zero-width request, not an
inverted one, and keeps the behaviour below. Infinite corners compare normally, so `lo = +inf` with
`hi = -inf` is rejected while `lo = hi = ±inf` is not.

`halo` SHALL be a non-negative integer. A negative `halo` silently *erodes* the region (and can
silently yield a zero-cell result), and a fractional `halo` is truncated per-face by `int()`,
producing an **asymmetric** pad — two extra cells on one side and one on the other — which is a wrong
answer for any consumer that differentiates across the pad.

Cells cover the half-open `[domain_left_edge, domain_right_edge)`, and upper bounds are exclusive
everywhere. A zero-width request inside the domain SHALL yield one cell (the cell containing it). A
point exactly on the upper edge, and a range ending exactly on the lower edge, SHALL yield none.
For `halo >= 1` the two edges SHALL behave the same: a point on either edge reaches exactly `halo`
cells inward. At `halo = 0` they differ by construction of the half-open coverage: a point on the
lower edge yields cell 0, and a point on the upper edge yields none.

These edge statements are exact when the cell spacing `(domain_right_edge - domain_left_edge) /
domain_dimensions` is exactly representable, as it is for every corpus deck: power-of-two cell counts
on integer extents. On other grids, float rounding at a cell face can move an edge point by one cell,
e.g. placing a point exactly on the upper edge in the last cell. The legacy adapter shares this
behaviour, since it uses the same floor/ceil of the same quotient.

Zero-cell regions are a reachable, supported outcome — `check_field_capture_velocity` already has a
dedicated empty-region error path — and SHALL NOT be silently widened to one cell on either side of
the domain.

#### Scenario: An invalid halo is rejected

- **Given** the committed fixture
- **When** `read_field_snapshot` is called with a negative `halo`, or a fractional one
- **Then** it raises `ValueError` in both cases — rather than silently eroding the region, or padding
  it asymmetrically because each face truncates independently

#### Scenario: An inverted request is rejected before yt is imported

- **Given** the committed 6³ fixture
- **When** `read_field_snapshot` is called with `lo=(4,4,4), hi=(2,2,2)` at `halo` 0 and 1;
  `lo=(9,9,9), hi=(-9,-9,-9)`; `lo=(2.6,)*3, hi=(2.4,)*3`; `lo=(4,)*3, hi=(3,)*3` at `halo` 2 (a
  non-empty padded range); `lo=(1,4,1), hi=(5,2,5)` (y only); and `lo=(+inf,0,0), hi=(-inf,6,6)`
- **Then** each raises `ValueError` whose message names exactly the inverted axes with their values —
  the y-only case names `y` and neither `x` nor `z` — and the same request raises the same error when
  `yt` cannot be imported and when the plotfile path does not exist

#### Scenario: A zero-width request is not treated as inverted

- **Given** the committed 6³ fixture
- **When** `read_field_snapshot` is called with `lo = hi` inside the domain, on the upper edge, at
  `+inf` on every axis, and at `-inf` on every axis
- **Then** none raises, and they return `(1, 1, 1)`, `(0, 0, 0)`, `(0, 0, 0)` and `(0, 0, 0)` cells
  respectively

#### Scenario: Region semantics match the legacy adapter across the parity matrix

- **Given** the committed 6³ fixture with domain `[0, 6]³` and `dx = 1`
- **When** `read_field_snapshot` is called with each of:
  - full `±inf` extent;
  - a non-cell-aligned interior box and an exactly cell-aligned box;
  - `halo` values that do and do not clip at the boundary;
  - mixed `±inf` on some axes only;
  - a zero-width interior request;
  - a point on the lower edge and a point on the upper edge, each with `halo` 0 and 2;
  - a request less than one cell below the domain with `halo` 1
- **Then** each returned region matches the frozen pre-refactor copy's for the same request

#### Scenario: Region semantics outside the domain are pinned against legacy

- **Given** the same fixture
- **When** `read_field_snapshot` and the frozen pre-refactor copy are called with requests outside the domain
  on some axis:
  - wholly below the domain, with `halo` 0 and 2;
  - below and above, each within and beyond `halo` reach;
  - a range ending exactly on the lower edge;
  - a `-inf` point;
  - a request outside on one axis only
- **Then** each result equals its separately recorded literal: the frozen copy returns edge cells,
  while `read_field_snapshot` returns only the in-domain cells the padded request reaches (zero when
  beyond reach)

#### Scenario: The parity region holds across a sweep

- **Given** the pure region-bounds helper and a literal transcription of the legacy arithmetic
- **When** both are evaluated over a sweep of per-axis `(lo, hi, halo)` values, including `±inf`,
  inverted requests, and values within `1e-12` of either edge
- **Then** they agree on every triple with `lo <= domain_right_edge` and `hi > domain_left_edge`, and
  the helper never returns more cells than legacy on any triple — a superset of the parity region:
  the helper still agrees with legacy on inverted triples, which only the public reader rejects


### Requirement: Point-cloud view built for a later AMR decision

`FieldSnapshot` SHALL provide `to_point_cloud()` returning an immutable `PointCloud` with `coords`
`(N, 3)`, `values` `(N, F)`, `field_names` fixing the column meaning, and `cell_volume` `(N,)`. The
flattening SHALL be C-order over `(nx, ny, nz)` and SHALL be documented as part of the contract, so
`coords` and `values` stay aligned across calls and across releases.

`cell_volume` SHALL be present even though it is constant on a uniform grid. This is the deliberate
extension point for the still-open **CC-F3** AMR decision: a future multi-level reader returns the same
`PointCloud` type with a varying `cell_volume`, so no downstream consumer changes. The dense array view
is structurally uniform-grid-only and SHALL NOT be extended to represent nested refinement.

While `cell_volume` is constant, it SHALL be a read-only, zero-stride `(N,)` broadcast of a read-only
0-d array (`np.broadcast_to`), not an `N`-element buffer of one repeated value. Its values, shape and
dtype are unchanged. Its documentation SHALL state how it differs from a dense array:
- it cannot be made writable;
- for `N > 1` it is not C-contiguous;
- its `base` is the 0-d array;
- pickling it produces a dense, writable copy.

Callers that need a dense buffer SHALL materialize one with `np.ascontiguousarray`.

`to_point_cloud()` SHALL release its meshgrid temporaries once `coords` is built. Its peak
allocation is then `coords` and `values` coexisting, with no other `N`-sized buffer.

#### Scenario: Point cloud is aligned and complete

- **Given** a `FieldSnapshot` over a region of `nx × ny × nz` cells with `F` fields
- **When** `to_point_cloud()` is called
- **Then** `coords` has shape `(nx·ny·nz, 3)`, `values` has shape `(nx·ny·nz, F)`, the row index of any
  chosen cell equals its C-order index computed independently, that row holds the cell's own centre
  coordinates and its own field values, and `cell_volume` equals `dx[0]·dx[1]·dx[2]` for every row

#### Scenario: Degenerate regions flatten without special-casing

- **Given** a snapshot of exactly one cell, and separately a zero-cell snapshot from an
  outside-the-domain request
- **When** `to_point_cloud()` is called on each
- **Then** the one-cell snapshot yields `coords (1, 3)` / `values (1, F)`, and the zero-cell snapshot
  yields `coords (0, 3)` / `values (0, F)` rather than raising or collapsing a dimension

#### Scenario: The constant cell volume is a read-only broadcast, not a repeated buffer

- **Given** a `FieldSnapshot` over `nx × ny × nz` cells with an anisotropic `dx`
- **When** `to_point_cloud()` is called
- **Then** `cell_volume` has shape `(nx·ny·nz,)`, dtype `float64`, strides `(0,)`, and every value
  equal to `dx[0]·dx[1]·dx[2]`. Its `flags.writeable` is `False`, and `setflags(write=True)` raises
  `ValueError`. No array in its `base` chain is writable. The same holds for a zero-cell snapshot,
  with shape `(0,)`.

#### Scenario: Building the point cloud allocates only its outputs at peak

- **Given** a `FieldSnapshot` built in memory, with no plotfile, over 64³ cells with six fields
- **When** `to_point_cloud()` is traced with `tracemalloc`
- **Then** the traced peak is at most `1.02 × (coords.nbytes + values.nbytes) + 64 KiB`


### Requirement: Corpus addressing by config and step

The package SHALL provide `mosquito_cfd.field_surrogate.corpus.FieldCorpus`, addressing plotfiles by
`(config_id, step)` against a **caller-supplied** corpus root, because the real corpus lives on cluster
NFS and is not in the repository. It SHALL expose the available config ids, the available steps for a
config, that config's kinematic parameters, and a snapshot accessor forwarding to
`read_field_snapshot`.

Steps SHALL be discovered from the `plt*` **directories** actually present on disk, never assumed from
a deck's `plot_int` — a run can be truncated, as 15 of 27 configs were at `ns.cfl = 0.3`. Entries that
are not directories, or whose suffix after `plt` is not one or more ASCII digits, SHALL be ignored,
and the returned step list SHALL be sorted ascending and deterministic across calls. A plotfile name
SHALL be `plt` followed by one or more **ASCII** digits `0-9` and nothing else, matched against the
whole name. A non-ASCII decimal digit (e.g. `plt١٠٠`) or a trailing newline (`plt100\n`) does not
make a plotfile name.

Listing a run directory SHALL cost one `os.scandir` call and no per-entry Python-level `stat`. The
directory filter SHALL use each `DirEntry`'s own `is_dir()`, which follows symlinks as
`Path.is_dir()` does. An entry whose type check fails with `FileNotFoundError` (removed mid-listing,
or a dangling symlink) SHALL be skipped; any other `OSError` from the check SHALL propagate rather
than being silently skipped. Returned plotfile paths
SHALL be `pathlib.Path` objects equal to `run_dir / name`. This is the only place the corpus uses
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

- **Given** a corpus root containing a sweep manifest and a config directory holding `plt00100`
- **When** `FieldCorpus.snapshot(config_id, step=100)` is called
- **Then** it returns the `FieldSnapshot` for that plotfile, and `global_params(config_id)` returns that
  config's kinematics from the manifest

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

#### Scenario: A failing entry type check is skipped only when the entry is gone

- **Given** a real `plt00100` beside a dangling symlink `plt00200`, on a platform where creating the
  symlink succeeds; and, separately, a listing that yields beside `plt00100` one `plt`-named entry
  whose `is_dir()` raises `PermissionError`
- **When** `steps(config_id)` is called
- **Then** the first returns `[100]`, and the second raises that `PermissionError`

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
them.

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

