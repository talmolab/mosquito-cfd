## MODIFIED Requirements

### Requirement: Run provenance with caller-supplied timestamp and container digest

The force-surrogate module SHALL capture run provenance by reusing the existing benchmarks metadata
capture. It SHALL (a) require a digest-pinned Docker image **reference**, not merely a tag and not a
bare digest with no repository, and (b) accept a **caller-supplied timestamp**, so artifacts are
reproducible rather than stamped with wall-clock time at runtime (CC-1).

`validate_image_digest(value)` SHALL accept exactly the values for which
`mosquito_cfd._provenance.is_pinned_image_ref(value)` is true. That rule is defined in the
`field-surrogate` capability, "Corpus snapshots carry run identity and digest-pinned provenance".
`validate_image_digest` SHALL return the value **unchanged**, with no whitespace stripping. It SHALL
raise `ValueError` for every other value, whatever its type. The message SHALL contain the substrings
`content-addressable`, `sha256` and `digest`, SHALL name the expected
`<repo>@sha256:<64 hex>` form, and SHALL end with the `repr` of the offending value.
`capture_surrogate_run_metadata` SHALL record the unchanged value under `docker_image`.

**BREAKING:** a bare digest, a tag with a digest appended, text around a digest, and surrounding
whitespace were accepted before (whitespace was stripped). They are now refused.

#### Scenario: Run provenance includes container digest

- **Given** a digest-pinned image reference, an existing inputs file, and a caller-supplied ISO timestamp
- **When** `capture_surrogate_run_metadata` is called
- **Then** the returned metadata records the git commit, the supplied image reference unchanged (under `docker_image`), and the inputs hash

#### Scenario: Caller-supplied timestamp recorded

- **Given** a caller-supplied ISO-8601 timestamp string
- **When** `capture_surrogate_run_metadata` is called
- **Then** the returned metadata's `timestamp` equals the supplied value verbatim (an ISO-8601 string), not the runtime wall clock

#### Scenario: Missing digest rejected

- **Given** an empty or missing Docker image digest
- **When** `capture_surrogate_run_metadata` is called
- **Then** it raises `ValueError` rather than recording provenance without a pinned image

#### Scenario: Mutable tag rejected

- **Given** a mutable image tag (e.g. `ghcr.io/talmolab/mosquito-cfd:latest`) with no `sha256:` digest
- **When** `capture_surrogate_run_metadata` is called
- **Then** it raises `ValueError` — only a digest-pinned `<repo>@sha256:<64 hex>` reference is accepted

#### Scenario: Loosely formed or wrongly typed image values are rejected, not normalized

- **Given** each of the following in turn:
  - a bare `"sha256:" + "a" * 64`;
  - `"ghcr.io/x:latest #sha256:" + "a" * 64`;
  - `"garbage sha256:" + "a" * 64 + " junk"`;
  - a valid reference with a leading space, a trailing space, or a trailing newline;
  - `"repo@sha256:" + "a" * 65`;
  - `5`, `None`, `b"ghcr.io/x@sha256:" + b"a" * 64`, and `["ghcr.io/x@sha256:" + "a" * 64]`
- **When** `validate_image_digest` is called on each
- **Then** each raises exactly `ValueError` (`type(e) is ValueError`, never `TypeError` or
  `AttributeError`) whose message contains `content-addressable`, `sha256`, `digest` and the
  value's `repr`

#### Scenario: A valid reference is returned exactly as given

- **Given** `"ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64` and the tag-plus-digest form
  `"ghcr.io/talmolab/mosquito-cfd:fp64@sha256:" + "a" * 64`
- **When** `validate_image_digest` is called on each, and `capture_surrogate_run_metadata` is called with each
- **Then** each is returned, and recorded under `docker_image`, as the identical string

## ADDED Requirements

### Requirement: Sweep-manifest reading lives in a shared standard-library-only module

The sweep-manifest reader SHALL be defined in `mosquito_cfd._manifest`, a module that imports only
the standard library. `mosquito_cfd.force_surrogate.dataset` SHALL re-export `load_manifest_configs`
as the **same object** (`is`), and so does `mosquito_cfd.force_surrogate`, which re-exports it from
`dataset`. Every existing importer therefore keeps working unchanged.

Behavior SHALL be unchanged for every manifest the previous reader accepted. A missing file SHALL
still raise `FileNotFoundError`. Error messages SHALL be unchanged for every manifest that meets all
of the following:

- its top level is a JSON object;
- it is valid UTF-8;
- the JSON parser accepts it;
- the previous reader rejected it.

The cases outside that boundary SHALL each raise `ValueError` naming the path:

- **a non-object top level** (`5`, a string, `null` or an array). This is checked before the
  `configs` lookup. It was a `TypeError`, or for an array the "has no 'configs' key" message.
- **JSON the parser refuses with `ValueError` or `RecursionError`.** That covers an integer beyond
  Python's digit limit (previously Python's own unprefixed message) and nesting beyond the recursion
  limit (previously `RecursionError`). The message begins `sweep manifest <path> is not valid JSON: `.
- **Bytes that are not valid UTF-8.** These were a bare `UnicodeDecodeError`. The message begins
  `sweep manifest <path> is not valid UTF-8: `.

#### Scenario: The re-export is the shared reader

- **Given** `mosquito_cfd._manifest`, `mosquito_cfd.force_surrogate.dataset` and `mosquito_cfd.force_surrogate`
- **When** their `load_manifest_configs` attributes are compared
- **Then** all three are the identical object (`is`)

#### Scenario: Existing rejections keep their messages

- **Given** object-top-level manifests with:
  - no `configs` key;
  - a non-list `configs`;
  - a non-mapping config;
  - a config missing a required key;
  - a duplicate config name;

  and separately, a file of invalid JSON (`{`)
- **When** `mosquito_cfd._manifest.load_manifest_configs` reads each
- **Then** each raises exactly `ValueError` with the literal message the pre-change reader produced
  for it, pinned by a test written before the move

#### Scenario: A missing manifest is still FileNotFoundError

- **Given** a manifest path that does not exist
- **When** `load_manifest_configs` reads it
- **Then** it raises `FileNotFoundError`

#### Scenario: A non-object top level is a ValueError

- **Given** sweep manifests whose top level is `5`, `"configs"`, `null`, and `[]`
- **When** `load_manifest_configs` reads each
- **Then** each raises exactly `ValueError` naming the path and the JSON type, never `TypeError`

#### Scenario: Unparseable manifests are reported as invalid JSON or invalid UTF-8

- **Given** a manifest nested 100000 levels deep, an object manifest whose `configs` holds a
  5000-digit integer, and a manifest of non-UTF-8 bytes
- **When** `load_manifest_configs` reads each
- **Then** each raises exactly `ValueError`. The first two messages begin
  `sweep manifest <path> is not valid JSON: `, and the third begins
  `sweep manifest <path> is not valid UTF-8: `.

### Requirement: Image digest wording throughout this capability means a digest-pinned reference

The accepted image value SHALL be exactly a reference for which
`mosquito_cfd._provenance.is_pinned_image_ref` is true, wherever a requirement or scenario in this
capability describes the Docker image as a digest "containing `sha256:`", a "pinned container
digest", or a value with "no `sha256:` digest". That is the rule `validate_image_digest` enforces (see "Run provenance with
caller-supplied timestamp and container digest"). A value merely containing `sha256:` SHALL NOT
satisfy those requirements. Examples are a bare `sha256:<64 hex>` and a tag with a digest appended.

This applies to:

- "Dataset build provenance";
- "Per-run cluster provenance with pinned digest";
- "Single-configuration pod run";
- "Cluster-side Argo orchestration of the corpus";
- "Training reproducibility and provenance";
- "Committed evidence-figure artifacts with provenance";

and to every other requirement whose code path reaches `validate_image_digest` or
`capture_surrogate_run_metadata`.

#### Scenario: A bare digest does not satisfy a "containing sha256:" requirement

- **Given** the bare value `"sha256:" + "a" * 64`, which contains `sha256:`
- **When** it is passed as the image digest to any entry point that a requirement in this
  capability describes as taking "a digest containing `sha256:`" (for example `dataset.build_run_metadata`,
  the sweep runner, or `run_one_config`)
- **Then** the entry point raises `ValueError` from `validate_image_digest`, and records no
  provenance for that value. Where an existing requirement already says the digest is validated
  before any computation or file write, that ordering still holds.
