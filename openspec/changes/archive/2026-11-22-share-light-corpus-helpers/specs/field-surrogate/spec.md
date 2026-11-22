## MODIFIED Requirements

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

Sweep-manifest parsing SHALL call `mosquito_cfd._manifest.load_manifest_configs` (the shared,
standard-library-only reader that `mosquito_cfd.force_surrogate.dataset` re-exports as the same
object) rather than re-reading the JSON, so a malformed manifest raises the same guarded error on the
field and force paths. Reading the manifest SHALL NOT import `mosquito_cfd.force_surrogate`, `pandas`,
`pyarrow` or `matplotlib.pyplot`: the first manifest read happens inside every training data-loader worker, and
importing the force-surrogate stack there costs seconds per spawned worker and switches the process's
matplotlib backend. A missing config, a missing step, and a missing corpus root SHALL each raise a
self-describing error naming what was looked for and where.

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

#### Scenario: Reading the manifest does not load the force-surrogate stack

- **Given** a fresh interpreter (a subprocess, so no earlier test has imported anything) and a corpus
  root holding a valid sweep manifest
- **When** it imports `mosquito_cfd.field_surrogate.corpus` and calls `FieldCorpus(root).config_ids()`
- **Then**:
  - the call returns the manifest's config names;
  - none of `mosquito_cfd.force_surrogate`, `pandas`, `pyarrow` or `matplotlib.pyplot` is in
    `sys.modules`;
  - the interpreter's `mosquito_cfd.__file__` lies in the source tree under test.

  Separately, `field_surrogate/corpus.py` contains no import of `mosquito_cfd.force_surrogate` or
  `mosquito_cfd.benchmarks` anywhere in its AST, nested imports included.

#### Scenario: A malformed manifest raises the same error on the field and force paths

- **Given** a sweep manifest whose top level is the JSON number `5`, and separately one whose config
  is missing `reynolds`
- **When** `FieldCorpus(root).config_ids()` and `mosquito_cfd.force_surrogate.dataset.load_manifest_configs`
  each read it
- **Then** both raise exactly `ValueError` (`type(e) is ValueError` on each path) with the identical
  message, and
  `mosquito_cfd.force_surrogate.dataset.load_manifest_configs is mosquito_cfd._manifest.load_manifest_configs`

### Requirement: Corpus snapshots carry run identity and digest-pinned provenance

The repository SHALL provide a private, dependency-free module `mosquito_cfd._provenance` (at the
top level of `mosquito_cfd`, so `force_surrogate` and `benchmarks` can share its checks without
importing `field_surrogate`), importing nothing beyond the standard library, with two functions.
`mosquito_cfd.field_surrogate._provenance` SHALL no longer exist; it was private, and its only
importers were `field_surrogate.corpus` and the tests.

**`read_run_metadata(path, *, config_id) -> dict`** returns the parsed JSON object unchanged. It
SHALL raise `ValueError`, with the message prefix below and the field tag `run_metadata.json`, when
any of the following holds:
- `path` is not a regular file;
- reading or decoding it raises `OSError` or `UnicodeDecodeError` (chained);
- it is not valid JSON, including JSON the parser refuses with `ValueError` or `RecursionError`
  (an integer beyond Python's digit limit, or nesting deeper than the recursion limit);
- its top level is not a JSON object.

**`run_provenance(meta, *, config_id, path) -> tuple[str, str, str]`** returns
`(git_commit, docker_image, run_id)`. It SHALL raise `ValueError` when any of the following holds:
- `meta["config"]` is absent, is not a `str`, or differs from `config_id`. A `run_metadata.json`
  copied into the wrong run directory must not lend its digest to another run's plotfiles.
- `meta["status"]` is absent or is not the string `"completed"`. A failed or incomplete run, whose
  late plotfiles may be unphysical, cannot lend its provenance to a training example.
- `meta["run_id"]` is absent, is not a `str`, or is blank (empty or whitespace only). The value is
  returned unstripped.
- `meta["git"]` is not an object, or `meta["git"]["commit"]` is absent, is not a `str`, or does not
  fully match `[0-9a-f]{40}`. The full match refuses a trailing newline and uppercase hex.
- `meta["git"]["dirty"]` is present and is not `False`. A run built from a dirty tree names a commit
  that did not produce the code.
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
`run_metadata.json` (the file itself), `config`, `status`, `run_id`, `git`, `git.commit`,
`git.dirty` or `docker_image`.

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
2. Resolve `plotfile(config_id, step)` and apply `read_field_snapshot`'s plotfile-directory check
   to it (a `Header` file must exist). A plotfile still being written is therefore reported as such,
   not as a provenance error.
3. Read and validate the run's provenance.
4. Read the plotfile with the **normalized** arguments that step 1 returned. An iterator or generator
   `fields` is consumed once, in step 1, and its names are what step 4 reads.
5. Apply the zero-cell refusal.

The provenance checks SHALL run before the plotfile is read, so a corpus without valid provenance
fails before the cost of a yt read.

The returned snapshot's `config_id` and `step` SHALL be the validated arguments (`step` a Python
`int` even when given as `np.integer`). Its `git_commit`, `docker_image` and `run_id` SHALL be the
values `run_provenance` returned. Nothing SHALL be fabricated, defaulted or inferred: there is no fallback
to `None`, to the running checkout's git, or to an image tag. Its arrays, coordinates, `dx`, `time`,
`max_level`, `field_names` and `source` SHALL be exactly those `read_field_snapshot` returns for
`plotfile(config_id, step)`.

`_provenance.py` SHALL import only the standard library, and reading or validating provenance SHALL
NOT import `mosquito_cfd.force_surrogate`. Importing that package loads pandas and pyarrow and
switches the process's matplotlib backend. `FieldCorpus`'s manifest parsing does not import it either
(see "Corpus addressing by config and step").

The commit and image rules above SHALL each be defined once, in `mosquito_cfd._provenance`, as the
predicates `is_full_commit_sha(value) -> bool` and `is_pinned_image_ref(value) -> bool`. Each returns
`True` only for a `str` that fully matches its pattern, and `False` for any other value or type,
without raising. `run_provenance` SHALL use them, and so SHALL the force-surrogate and benchmarks
validators (see the `run-metadata` and `force-surrogate` capabilities), so the three sites cannot
drift apart again.

#### Scenario: A corpus snapshot carries its run's identity and digest

- **Given** a corpus whose run directory holds `plt00100` and a `run_metadata.json` with `config`
  equal to the config id, a 40-character lowercase `git.commit`, and a `docker_image` of the form
  `ghcr.io/talmolab/mosquito-cfd@sha256:<64 hex>`
- **When** `FieldCorpus.snapshot(config_id, np.int64(100))` is called
- **Then** the snapshot's `config_id`, `step` (`type(step) is int`), `git_commit`, `docker_image`
  and `run_id` equal the file's values exactly; and its arrays, coordinates, `dx`, `time`,
  `max_level`, `field_names` and `source` equal, property by property,
  `read_field_snapshot(plotfile(config_id, 100))`'s

#### Scenario: Missing or unverifiable provenance is refused before any read

- **Given** a run directory holding `plt00100`, and `run_metadata.json` in turn:
  - absent;
  - a directory;
  - non-UTF-8 bytes;
  - invalid JSON;
  - an integer with 5000 digits;
  - nesting 100000 levels deep;
  - a top-level JSON array;
  - a `config` that is absent, `null`, or names a different config;
  - a `status` that is absent or `"failed"`;
  - a `run_id` that is absent, `5`, `""`, or `" "`;
  - a `git` that is absent or `null`;
  - a `git.dirty` that is `true`, `"no"`, `null`, or `0`;
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

- **Given** a run directory holding `plt00100` and **no** `run_metadata.json`, and separately a run
  directory whose `plt00100` has no `Header` and no `run_metadata.json`
- **When** `FieldCorpus.snapshot` is called with `fields="u"`, with `lo > hi`, with `step=-1`, with
  an unknown config, with a step that has no plotfile, and on the `Header`-less plotfile
- **Then** each raises its own argument, config, step or plotfile error and not the provenance
  error (the `Header`-less case raises `FileNotFoundError` naming `Header`), and the argument errors
  are raised with no manifest read and no directory listed

#### Scenario: An iterator of field names is read, not consumed by validation

- **Given** a corpus with valid provenance
- **When** `FieldCorpus.snapshot` is called with `fields` a generator, and an iterator, of `"u"`
  and `"v"`
- **Then** the snapshot's `field_names` is `("u", "v")` and it carries both arrays

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
- **When** it imports `mosquito_cfd._provenance` and calls `read_run_metadata` and
  `run_provenance` on that file
- **Then**:
  - none of `mosquito_cfd.force_surrogate`, `mosquito_cfd.field_surrogate`, `mosquito_cfd.benchmarks`,
    `pandas`, `pyarrow` or `matplotlib.pyplot` appears in `sys.modules`;
  - the interpreter's `mosquito_cfd.__file__` lies in the source tree under test;
  - the same holds for a fresh interpreter that imports only `mosquito_cfd._manifest` and calls
    `load_manifest_configs`;
  - the import statements of both `mosquito_cfd/_provenance.py` and `mosquito_cfd/_manifest.py`,
    found by walking each file's AST (nested imports included), name only standard-library modules,
    with no relative import and no call to `importlib.import_module` or `__import__`.

#### Scenario: The shared predicates accept exactly the strict forms and never raise

- **Given** these values for the commit predicate:
  - `"a" * 40`, `"a" * 40 + "\n"`, `"A" * 40`, `"g" * 40`, `"a" * 39`, `"a" * 41`;
  - `123`, `None`, `b"a" * 40`;

  and these values for the image predicate:
  - `"ghcr.io/x@sha256:" + "a" * 64` and `"ghcr.io/x:fp64@sha256:" + "a" * 64`;
  - a bare `"sha256:" + "a" * 64`;
  - `"@sha256:" + "a" * 64`, which has an empty repository;
  - `"ghcr.io/X@sha256:" + "a" * 64` (uppercase repository) and `"ghcr.io/x y@sha256:" + "a" * 64`;
  - `"ghcr.io/x:latest #sha256:" + "a" * 64` and `"ghcr.io/x:latest #@sha256:" + "a" * 64`;
  - `"garbage sha256:" + "a" * 64 + " junk"`;
  - the valid reference with a leading space and with a trailing newline;
  - `"ghcr.io/x@sha256:" + "A" * 64` (uppercase digest), `"repo@sha256:" + "a" * 65` and
    `"repo@sha256:" + "a" * 63`;
  - `5`, `None` and `b"ghcr.io/x@sha256:" + b"a" * 64`
- **When** `is_full_commit_sha` and `is_pinned_image_ref` are called on them
- **Then** only `"a" * 40` and the two `ghcr.io/x…@sha256:<64 hex>` references return `True`; every
  other value returns `False` and none raises
