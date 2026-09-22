## ADDED Requirements

### Requirement: Framework-neutral field snapshot contract

The package SHALL provide `mosquito_cfd.field_surrogate.snapshot.read_field_snapshot`, a single
`yt`-based reader returning an immutable `FieldSnapshot` describing an axis-aligned region of a
single-level AMReX plotfile. The snapshot SHALL carry, in **code units with no conversion**: the
requested fields as bare FP64 numpy arrays indexed `[ix, iy, iz]`; the cell-center coordinate arrays
`x`, `y`, `z`; the per-axis spacing `dx` as a `float64` array of shape `(3,)`; the plotfile's physical
`time` as a Python `float`; and the provenance fields `source` and `max_level`.

Immutability SHALL be enforced, not merely declared: the dataclass is frozen, every array it exposes
is non-writable (`arr.flags.writeable is False`), **and every array owns its data**
(`arr.base is None`). Owning the data is the load-bearing half: marking a *view* non-writable leaves
its `base` reachable and writable, so the array can be mutated through it and the guarantee is a
facade. Note that `np.ascontiguousarray` does not copy a slice that is already C-contiguous — which
includes the full-extent read and any single-axis slab — so it cannot be relied on to produce an
owning array.

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
  `0`, and whose `source` resolves to the plotfile path

#### Scenario: Snapshot arrays own their data and cannot be mutated through a base

- **Given** a full-extent read and a sub-box read of the fixture — the full-extent case being the one
  where `np.ascontiguousarray` returns a view rather than a copy
- **When** the returned snapshots are inspected
- **Then** in **both** cases every exposed array reports `flags.writeable is False` **and**
  `base is None`, so there is no reachable writable buffer behind it; assigning into any array raises;
  and two reads of the same region do not share memory

### Requirement: Field selection validated before any array is read

The reader SHALL accept a caller-selected field set drawn from a canonical short-name map covering
every component the wing plotfiles write (`u`, `v`, `w`, `gradpx`, `gradpy`, `gradpz`, `density`,
`tracer`), defaulting to the six that the LEV and control-volume callers require. It SHALL reject an
unknown short name, and reject a canonical name absent from the plotfile, **before** reading any field
array. It SHALL read exactly the requested fields and no others.

It SHALL reject duplicate short names: a duplicate silently desynchronises `arrays` (a dict, which
collides) from `field_names` (a tuple, which does not), yielding a `PointCloud` whose column count
exceeds the number of distinct fields and duplicating a training column, and it re-reads the same
field once per repetition.

It SHALL verify the plotfile's **on-disk** precision is `float64`, via the dtype yt parses from the
FAB RealDescriptor (`ds.index._dtype`). Inspecting the returned array's dtype does **not** work and
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
- **Then** it raises `ValueError` naming the observed on-disk precision, and no snapshot is
  constructed — even though every array yt would return from it reports `dtype == float64`

#### Scenario: Duplicate field names are rejected

- **Given** the committed fixture
- **When** `read_field_snapshot` is called with a `fields` tuple naming the same short name twice
- **Then** it raises `ValueError` identifying the duplicate, and a recording proxy confirms no field
  array was read — rather than returning a snapshot whose `arrays` has fewer entries than
  `field_names` and whose point cloud carries a duplicated column

### Requirement: Region semantics identical to the legacy Eulerian-box adapter

The region semantics SHALL be byte-identical to the existing adapter's, because the legacy wrapper's
behavioral equivalence depends on them: `lo`/`hi` physical corners clamped to the domain; `±inf`
accepted as "full extent" along an axis, per axis independently; an optional `halo` of extra cells on
every side, clipped at the domain boundary; and the read performed as a full level-0 covering grid
sliced in memory.

`halo` SHALL be a non-negative integer. A negative `halo` silently *erodes* the region (and can
silently yield a zero-cell result), and a fractional `halo` is truncated per-face by `int()`,
producing an **asymmetric** pad — two extra cells on one side and one on the other — which is a wrong
answer for any consumer that differentiates across the pad.

The index arithmetic SHALL be preserved exactly as
`i_hi = min(max(i_hi, i_lo + 1), ddims)`. Note that this yields **at least one cell per axis only for
regions that begin inside the domain**: a request at or beyond the upper domain edge clamps `i_lo` and
`i_hi` to `ddims` and correctly yields a **zero-cell** region. Zero-cell regions are a reachable,
supported outcome — `check_field_capture_velocity` already has a dedicated empty-region error path —
and SHALL NOT be silently widened to one cell.

#### Scenario: An invalid halo is rejected

- **Given** the committed fixture
- **When** `read_field_snapshot` is called with a negative `halo`, or a fractional one
- **Then** it raises `ValueError` in both cases — rather than silently eroding the region, or padding
  it asymmetrically because each face truncates independently

#### Scenario: Region semantics match the legacy adapter across the clamping matrix

- **Given** the committed 6³ fixture with domain `[0, 6]³` and `dx = 1`
- **When** `read_field_snapshot` is called with each of: full `±inf` extent; a non-cell-aligned
  interior box; an exactly cell-aligned box; `halo` values that do and do not clip at the boundary;
  mixed `±inf` on some axes only; a zero-width interior request; a request at the upper domain edge;
  and a request wholly outside the domain
- **Then** each returned region matches the legacy adapter's for the same request, the interior
  zero-width request yields one cell per axis, and the upper-edge and outside-domain requests each
  yield a zero-cell region rather than being widened

### Requirement: `yt` is imported lazily and confined to one covering-grid read path

`yt` SHALL be imported inside `read_field_snapshot`, never at module scope, so that importing
`mosquito_cfd.field_surrogate` or `mosquito_cfd.benchmarks.stress_integral` does not pull it in. After
this change `read_field_snapshot` SHALL be the repository's only Eulerian-box covering-grid read path
in `src/`; `stress_integral.py` SHALL contain no `yt.load` or `covering_grid` call of its own.

This is narrower than "the only `yt` call in the repository": `benchmarks/analyze_sphere.py` performs
its own `yt.load` for IB-particle access and is out of scope here.

`mosquito_cfd.field_surrogate.__init__` SHALL NOT eagerly import its submodules. `corpus` reaches
`force_surrogate.dataset`, whose package `__init__` imports modules that import
`mosquito_cfd.benchmarks.metadata` — so an eager re-export would create a
`benchmarks → field_surrogate → force_surrogate → benchmarks` import cycle whose survival depends only
on statement order inside two `__init__.py` files. `stress_integral.py` SHALL import the submodule path
directly rather than through the package.

#### Scenario: Importing the package does not import `yt`

- **Given** a fresh interpreter
- **When** `mosquito_cfd.field_surrogate`, each of its submodules, and
  `mosquito_cfd.benchmarks.stress_integral` are imported
- **Then** no module named `yt` or beginning `yt.` is present in `sys.modules`, and every `import yt`
  statement in the package has a function as its nearest enclosing scope

#### Scenario: Importing the package alone pulls in none of its submodules

- **Given** a fresh interpreter
- **When** only `mosquito_cfd.field_surrogate` is imported — not any submodule
- **Then** no `mosquito_cfd.field_surrogate.*` submodule appears in `sys.modules`, so neither the
  import-weight cost nor the `benchmarks → field_surrogate → force_surrogate → benchmarks` cycle can
  be reintroduced by an eager re-export. A probe that imports the submodules itself cannot observe
  this and does not discharge it.

### Requirement: Point-cloud view built for a later AMR decision

`FieldSnapshot` SHALL provide `to_point_cloud()` returning an immutable `PointCloud` with `coords`
`(N, 3)`, `values` `(N, F)`, `field_names` fixing the column meaning, and `cell_volume` `(N,)`. The
flattening SHALL be C-order over `(nx, ny, nz)` and SHALL be documented as part of the contract, so
`coords` and `values` stay aligned across calls and across releases.

`cell_volume` SHALL be present even though it is constant on a uniform grid. This is the deliberate
extension point for the still-open **CC-F3** AMR decision: a future multi-level reader returns the same
`PointCloud` type with a varying `cell_volume`, so no downstream consumer changes. The dense array view
is structurally uniform-grid-only and SHALL NOT be extended to represent nested refinement.

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

### Requirement: Multi-level plotfiles are refused with the open AMR decision named

`read_field_snapshot` SHALL raise `ValueError` on a plotfile whose `max_level` is not `0`, and the
message SHALL name the unresolved **CC-F3** AMR-level-handling decision rather than stating a bare
requirement. Silently proceeding is forbidden: `covering_grid(level=0, …)` on a refined plotfile
returns the **coarse** level-0 data and ignores the refined patches, discarding exactly the near-wing
resolution the refinement paid for — a quiet accuracy loss with no other symptom.

#### Scenario: A refined plotfile is refused, not silently coarsened

- **Given** a dataset proxy wrapping the real fixture that overrides only `index.max_level` to a
  non-zero value
- **When** `read_field_snapshot` reads it
- **Then** it raises `ValueError` reporting the observed `max_level` and naming the open CC-F3
  decision, no field array is read, and the same call against the unmodified proxy at `max_level == 0`
  succeeds — proving the guard reads the attribute the proxy overrides

### Requirement: The existing Eulerian-box adapter delegates rather than duplicating

`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` SHALL be refactored to delegate to
`read_field_snapshot` and re-pack the result into its existing flat dict (**CC-F2**). Its import path,
call signature, and returned key set (`u`, `v`, `w`, `gradpx`, `gradpy`, `gradpz`, `x`, `y`, `z`, `dx`,
`current_time`) SHALL be unchanged — exactly those keys, with no snapshot-only field such as `time`,
`source`, or `max_level` leaking in — and the value **types** SHALL be preserved, including `dx` as a
`float64` array of shape `(3,)` and `current_time` as a Python `float`.

Equivalence SHALL be demonstrated against the **pre-refactor implementation**, not against the new
reader. A test comparing the refactored wrapper to a re-pack of `read_field_snapshot` is tautological
once the wrapper is that re-pack, and proves nothing about behavioral continuity.

Every in-repo caller SHALL continue to call `extract_eulerian_box` rather than `read_field_snapshot`
directly. This preserves the `force-surrogate` capability's CC-F1 requirement that the field-capture
velocity check be built on `extract_eulerian_box` "rather than a new plotfile reader", and it keeps the
module-global name resolvable: 21 test sites replace that module global, and an internal call site that
stopped resolving it would silently bypass those fakes, leaving tests green while testing nothing.

#### Scenario: Output matches the pre-refactor implementation across the clamping matrix

- **Given** a frozen byte-for-byte copy of the pre-refactor `extract_eulerian_box` implementation,
  recorded with its source commit, and the committed fixture
- **When** both the refactored wrapper and the frozen copy are called on the same region for each case
  in the region-semantics clamping matrix
- **Then** the two dicts have identical key sets, every array value is exactly equal, and `dx` and
  `current_time` match in Python type as well as value

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

### Requirement: DoMINO volume-half adapter with the geometry gap stated, not filled

The package SHALL provide `mosquito_cfd.field_surrogate.domino_adapter.to_domino_volume`, emitting a
plain dict under DoMINO's own key names for the part this corpus can honestly supply:
`volume_mesh_centers` `(N, 3)`, `volume_fields` `(N, F)`, `grid` `(nx, ny, nz, 3)`,
`global_params_values` `(P, 1)`, and `global_params_reference` `(P, 1)`. It SHALL NOT add a batch
dimension, because DoMINO's own datapipe adds one. Global parameters SHALL be caller-supplied, so no
normalization policy is baked into the reader.

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
  has no pressure field and carries its gradient instead, and it names each of the eight absent keys
