## MODIFIED Requirements

### Requirement: Region semantics match the legacy adapter wherever the request meets the domain

The region semantics SHALL be identical to the existing adapter's whenever, on every axis,
`lo <= hi`, `lo <= domain_right_edge` and `hi > domain_left_edge`. In that region the two SHALL return
the same cells. In both, `±inf` is accepted as "full extent" along an axis, per axis independently, an
optional `halo` adds extra cells on every side, and the read is performed as a full level-0 covering
grid sliced in memory.

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

### Requirement: The existing Eulerian-box adapter delegates rather than duplicating

`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` SHALL be refactored to delegate to
`read_field_snapshot` and re-pack the result into its existing flat dict (**CC-F2**). Its import path,
call signature, and returned key set (`u`, `v`, `w`, `gradpx`, `gradpy`, `gradpz`, `x`, `y`, `z`, `dx`,
`current_time`) SHALL be unchanged — exactly those keys, with no snapshot-only field such as `time`,
`source`, or `max_level` leaking in — and the value **types** SHALL be preserved, including `dx` as a
`float64` array of shape `(3,)` and `current_time` as a Python `float`.

Within the parity region (on every axis `lo <= hi`, `lo <= domain_right_edge` and
`hi > domain_left_edge`), equivalence SHALL be demonstrated against the **pre-refactor
implementation**, not against the new reader. A test comparing the refactored wrapper to a re-pack of
`read_field_snapshot` is tautological once the wrapper is that re-pack, and proves nothing about
behavioral continuity. Outside the parity region the wrapper inherits the reader's "halo is reach" rule
and returns no more cells than the pre-refactor implementation; that divergence SHALL be pinned against
the same frozen copy.

The wrapper's accepted inputs are deliberately narrower. It SHALL raise `ValueError` for a NaN corner,
a `lo` or `hi` that is not a 3-vector, an inverted request (`lo > hi` on any axis), a `halo` that is negative or not of an integer type (fractional, boolean, and integral floats such as `2.0` or 0-d arrays alike), and a plotfile whose on-disk
precision is fp32 — all of which the pre-refactor implementation accepted (the last silently, as
upcast float64).

Every in-repo caller SHALL continue to call `extract_eulerian_box` rather than `read_field_snapshot`
directly. This preserves the `force-surrogate` capability's CC-F1 requirement that the field-capture
velocity check be built on `extract_eulerian_box` "rather than a new plotfile reader", and it keeps the
module-global name resolvable: 21 test sites replace that module global, and an internal call site that
stopped resolving it would silently bypass those fakes, leaving tests green while testing nothing.

#### Scenario: Output matches the pre-refactor implementation across the parity matrix

- **Given** a frozen, content-hash-pinned copy of the pre-refactor `extract_eulerian_box`
  implementation, recorded with its source commit, and the committed fixture
- **When** both the refactored wrapper and the frozen copy are called on the same region for each case
  in the region-semantics parity matrix
- **Then** the two dicts have identical key sets, every array value is exactly equal, and `dx` and
  `current_time` match in Python type as well as value

#### Scenario: The wrapper's documented divergence is pinned against the frozen copy

- **Given** the same frozen copy and the outside-the-domain divergence cases
- **When** both are called on each divergence case
- **Then** the frozen copy returns the recorded legacy cell counts and the refactored wrapper returns
  the recorded `read_field_snapshot` cell counts, and every cell the wrapper returns is one the frozen
  copy returns with the identical value — so the wrapper's narrowed behaviour is asserted, not merely
  tolerated

#### Scenario: The wrapper's narrowed inputs raise where the frozen copy accepted

- **Given** the frozen copy, the committed fixture, and an fp32 plotfile written to a temporary
  directory
- **When** each is called with a NaN corner, a scalar `lo`, a scalar `hi`, an inverted request
  `lo=(4,4,4), hi=(2,2,2)`, a negative `halo`, a fractional `halo`, a boolean `halo`, and (separately)
  on the fp32 plotfile
- **Then** the refactored wrapper raises `ValueError` in every case, and the frozen copy raises in none
  — so each narrowing is pinned on both sides rather than merely claimed

#### Scenario: Internal call sites still resolve the patched module global

- **Given** `mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` replaced by a sentinel
- **When** `sphere_cv_drag_cd`, `check_field_capture_velocity`, and `sphere_cv_steadiness_fraction` are
  each invoked
- **Then** every one of them reaches the sentinel, proving no internal call site bypasses the module
  global by importing `read_field_snapshot` directly

### Requirement: Corpus addressing by config and step

The package SHALL provide `mosquito_cfd.field_surrogate.corpus.FieldCorpus`, addressing plotfiles by
`(config_id, step)` against a **caller-supplied** corpus root, because the real corpus lives on cluster
NFS and is not in the repository. It SHALL expose the available config ids, the available steps for a
config, that config's kinematic parameters, and a snapshot accessor forwarding to
`read_field_snapshot`.

Steps SHALL be discovered from the `plt*` **directories** actually present on disk, never assumed from
a deck's `plot_int` — a run can be truncated, as 15 of 27 configs were at `ns.cfl = 0.3`. Entries that
are not directories, or whose suffix after `plt` is not an integer, SHALL be ignored, and the returned
step list SHALL be sorted ascending and deterministic across calls.

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

- **Given** a freshly constructed `FieldCorpus`, with manifest loading and `Path` directory checks and
  listings recorded from after construction
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
