## ADDED Requirements

### Requirement: Force-surrogate JSON files load through one labelled loader

`load_json_clear_error(path, *, label, require_object=True)` SHALL be defined in
`mosquito_cfd._json_loader`, a module that imports only the standard library.
`mosquito_cfd.force_surrogate.sidecar.load_json_clear_error` SHALL be the **same object** (`is`).
Reading a file through `mosquito_cfd._json_loader` SHALL NOT import `mosquito_cfd.force_surrogate`,
`mosquito_cfd.field_surrogate`, `mosquito_cfd.benchmarks`, pandas, pyarrow or `matplotlib.pyplot`.
`path` MAY be a `str` or a `Path`.

The file SHALL be decoded as strict UTF-8 (`utf-8`, not `utf-8-sig`). Every rejection of the
file's contents SHALL be exactly a `ValueError` (not a subclass) with one of the messages below.
The UTF-8 and JSON rejections SHALL be raised `from` the underlying exception. The non-object
rejection has no underlying exception.

- bytes that are not valid UTF-8: `{label} {path} is not valid UTF-8: {exc}`;
- anything `json.loads` refuses with `ValueError` or `RecursionError`:
  `{label} {path} is not valid JSON: {exc}`. That covers malformed JSON, an empty file, a leading
  UTF-8 byte-order mark, an integer beyond Python's digit limit, and nesting beyond the recursion
  limit. For a `json.JSONDecodeError` this is the message the loader produced before this
  requirement;
- when `require_object` is true, a top level that is not a JSON object:
  `{label} {path} top level is a {Python type name}, not an object` (`list`, `int`, `str`,
  `NoneType`, and so on).

With `require_object=False` the loader SHALL return any JSON value unchecked. A JSON object SHALL
be returned unchanged. Errors opening the path SHALL NOT be wrapped: a missing file SHALL raise
`FileNotFoundError`, and any other `OSError` (a directory, a permission error) SHALL escape as
raised.

#### Scenario: The sidecar name is the shared loader

- **Given** `mosquito_cfd._json_loader` and `mosquito_cfd.force_surrogate.sidecar`
- **When** their `load_json_clear_error` attributes are compared
- **Then** they are the identical object (`is`)

#### Scenario: The loader imports only the standard library

- **Given** the source of `mosquito_cfd._json_loader`
- **When** every import in it is inspected, and a file is read through it in a fresh interpreter
- **Then** every import names a standard-library module, and none of the modules listed in the
  requirement is loaded

#### Scenario: Unparseable files are labelled ValueErrors

- **Given** files of these bytes:
  - `[` × 100000 then `]` × 100000 (deep nesting);
  - `{"a": ` + `9` × 5000 + `}` (digit limit);
  - `\xff\xfe{` (not UTF-8);
  - `{` (malformed);
  - nothing (empty);
  - `\xef\xbb\xbf{}` (a UTF-8 byte-order mark)
- **When** `load_json_clear_error(path, label="probe")` reads each
- **Then** each raises exactly `ValueError` whose `__cause__` is the underlying `RecursionError`,
  `ValueError`, `UnicodeDecodeError` or `json.JSONDecodeError`. The not-UTF-8 message begins
  `probe <path> is not valid UTF-8: `, and every other message begins
  `probe <path> is not valid JSON: `.
- **And** the malformed file's message equals `probe <path> is not valid JSON: ` followed by the
  text of the `json.JSONDecodeError` that `json.loads("{")` raises

#### Scenario: A non-object top level is a labelled ValueError unless opted out

- **Given** files holding `[]`, `5`, `"x"` and `null`
- **When** `load_json_clear_error(path, label="probe")` reads each
- **Then** each raises exactly `ValueError` with the message
  `probe <path> top level is a <name>, not an object`, where `<name>` is `list`, `int`, `str` and
  `NoneType` respectively
- **And** with `require_object=False`, each is returned unchanged

#### Scenario: A valid object is returned unchanged, from a str or a Path

- **Given** a file holding `{"a": [1, 2.5, "x", null]}`
- **When** `load_json_clear_error` reads it, once given a `Path` and once given a `str`
- **Then** both return `{"a": [1, 2.5, "x", None]}`

#### Scenario: Errors opening the path are not wrapped

- **Given** a path that does not exist, and a path that is a directory
- **When** `load_json_clear_error` reads each
- **Then** the first raises `FileNotFoundError`, and the second raises an `OSError` that is not a
  `ValueError`

### Requirement: Callers of the shared JSON loader label every content failure

The loader's callers SHALL use it as follows. The payloads named below are those of the scenario
"Unparseable files are labelled ValueErrors", plus the top levels `[]` and `5`.

- **`acceptance_gate`.**
  - Its sweep-provenance reads (in `run_acceptance_gate` and `record_check_result`) use the object
    check.
  - It reads the sweep manifest through `mosquito_cfd._manifest.load_manifest_configs`.
  - Its own run_metadata read uses the object check as defence in depth. `build_dataset` parses
    the same file first, so a bad run_metadata file's error comes from `dataset` (below).
  - `record_check_result` SHALL leave the provenance file's bytes unchanged when the read fails.
- **`corpus_guards`.** Its sweep-manifest read uses the object check.
- **`dataset`.** Its per-config run_metadata read (deck-hash reconciliation) uses
  `require_object=False`.
  - A non-object top level, and bytes that are not valid UTF-8, SHALL each still raise
    `ConfigExtractionError` with the message they raised before this requirement. That error is
    chained `from` the underlying `UnicodeDecodeError` in the UTF-8 case.
  - Nesting beyond the recursion limit and an integer beyond the digit limit SHALL raise the
    loader's `ValueError` beginning `run_metadata file <path> is not valid JSON: `. That propagates
    out of `run_acceptance_gate`, as malformed JSON always has.
- **`metadata_capture.load_pod_run_metadata`.** Uses the object check with the label
  `pod-side run_metadata.json`.
- **`sidecar.read_units_sidecar`.** Uses the object check with the label `units sidecar`, then
  validates the units as before.

No caller SHALL wrap an error from opening the path.

#### Scenario: Callers see labelled ValueErrors, never RecursionError, AttributeError or TypeError

- **Given** files nested 100000 levels deep, holding a 5000-digit integer inside an object, of the
  bytes `\xff\xfe{`, of `[]`, and of `5`
- **When** each is read, in turn, through each of these entry points:
  - as the sweep provenance of `run_acceptance_gate` on an otherwise valid corpus;
  - as the provenance of `record_check_result`;
  - as `corpus_guards`' sweep manifest, via `check_deck_matches_manifest_max_step`;
  - as a pod-side `run_metadata.json`, via `load_pod_run_metadata`;
  - as a units sidecar, via `read_units_sidecar`
- **Then** each raises exactly `ValueError` naming the path
- **And** `record_check_result` leaves the provenance file's bytes unchanged

#### Scenario: The gate's manifest errors are the shared reader's

- **Given** sweep manifests nested 100000 levels deep, holding a 5000-digit integer inside an
  object, of the bytes `\xff\xfe{`, of `[]`, and of `5`
- **When** `run_acceptance_gate` reads each
- **Then** each raises exactly `ValueError`. The first three messages begin `sweep manifest <path> `,
  and the `[]` and `5` messages are
  `manifest <path> top level is a <list|int>, not an object; not a sweep manifest`.

#### Scenario: Per-config run metadata keeps its extraction errors

- **Given** a config's run_metadata file of non-UTF-8 bytes, and one whose top level is `[]`
- **When** `build_dataset` reads each
- **Then** each raises `ConfigExtractionError` with the message it raised before this requirement.
  The non-UTF-8 one is chained from a `UnicodeDecodeError`.
- **And** `run_acceptance_gate`, given either file, returns a failed `GateResult` naming that
  config rather than raising

#### Scenario: Deep or huge per-config run metadata is a labelled ValueError

- **Given** a config's run_metadata file nested 100000 levels deep, and one holding a 5000-digit
  integer
- **When** `build_dataset` reads each, and when `run_acceptance_gate` reads each
- **Then** each raises exactly `ValueError` beginning `run_metadata file <path> is not valid JSON: `

#### Scenario: Units sidecar messages name the file

- **Given** a units sidecar of `{` and one whose top level is `[]`
- **When** `read_units_sidecar` reads each
- **Then** the first raises exactly `ValueError` beginning `units sidecar <path> is not valid JSON: `,
  and the second raises exactly `ValueError` with the message
  `units sidecar <path> top level is a list, not an object`

#### Scenario: Opening errors are not wrapped by callers

- **Given** a directory passed as the path
- **When** `load_pod_run_metadata` and `read_units_sidecar` read it
- **Then** each raises an `OSError` that is not a `ValueError`

### Requirement: The three JSON loaders reject the same inputs

`mosquito_cfd._provenance.read_run_metadata` SHALL keep its own loader, because its message format and
its contract that every error is a `ValueError` (opening errors included) differ. It SHALL reject
the same contents as `mosquito_cfd._json_loader.load_json_clear_error` and
`mosquito_cfd._manifest.load_manifest_configs`, each as exactly a `ValueError` naming the path.

#### Scenario: Every loader rejects the same inputs

- **Given** files nested 100000 levels deep, holding a 5000-digit integer inside an object, of the
  bytes `\xff\xfe{`, of `[]`, and of `5`
- **When** `mosquito_cfd._json_loader.load_json_clear_error`, `mosquito_cfd._manifest.load_manifest_configs`
  and `mosquito_cfd._provenance.read_run_metadata` each read every file
- **Then** every call raises exactly `ValueError` whose message contains the file's path

## MODIFIED Requirements

### Requirement: Sweep-manifest reading lives in a shared standard-library-only module

The sweep-manifest reader SHALL be defined in `mosquito_cfd._manifest`, a module that imports only
the standard library and `mosquito_cfd._json_loader`, which itself imports only the standard
library (see "Force-surrogate JSON files load through one labelled loader"). It SHALL load the
file through `mosquito_cfd._json_loader.load_json_clear_error` with the label `sweep manifest` and
`require_object=False`, keeping its own non-object check and message.
`mosquito_cfd.force_surrogate.dataset` SHALL re-export `load_manifest_configs` as the **same
object** (`is`), and so does `mosquito_cfd.force_surrogate`, which re-exports it from `dataset`.
Every existing importer therefore keeps working unchanged.

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

#### Scenario: The manifest reader imports only the standard library and the shared loader

- **Given** the source of `mosquito_cfd._manifest`
- **When** every import in it (nested ones included) is inspected
- **Then** each names a standard-library module or exactly `mosquito_cfd._json_loader`, and
  `mosquito_cfd._json_loader`'s own imports all name standard-library modules
- **And** reading a manifest through `mosquito_cfd._manifest` in a fresh interpreter loads none of
  `mosquito_cfd.force_surrogate`, `mosquito_cfd.field_surrogate`, `mosquito_cfd.benchmarks`, pandas,
  pyarrow or `matplotlib.pyplot`
