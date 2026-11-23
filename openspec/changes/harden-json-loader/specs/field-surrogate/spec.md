## MODIFIED Requirements

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
  - the import statements of `mosquito_cfd/_provenance.py`, found by walking the file's AST (nested
    imports included), name only standard-library modules, with no relative import and no call to
    `importlib.import_module` or `__import__`;
  - the import statements of `mosquito_cfd/_manifest.py`, found the same way, name only
    standard-library modules and exactly `mosquito_cfd._json_loader` (as `import
    mosquito_cfd._json_loader` or `from mosquito_cfd._json_loader import …`), with no relative import
    and no dynamic import; and the import statements of `mosquito_cfd/_json_loader.py` name only
    standard-library modules.

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
