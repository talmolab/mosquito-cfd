# Change: Label every way a force-surrogate JSON file can fail to load (#175)

## Why

`force_surrogate.sidecar.load_json_clear_error` labels only malformed JSON with the file's label
and path. Deep nesting, the integer digit limit, non-UTF-8 bytes and a non-object top level all
escape unlabelled, or as `RecursionError`, `AttributeError` or `TypeError`. Two other loaders
already handle all four, each with its own copy of the code, so the three can drift apart.

## What Changes

What escapes today:

| Input | Today, through `load_json_clear_error` |
|---|---|
| JSON nested deeper than the recursion limit | `RecursionError`, which is not a `ValueError` |
| An integer beyond Python's 4300-digit limit | Python's own `ValueError("Exceeds the limit …")`, with no label or path |
| Bytes that are not valid UTF-8 | A bare `UnicodeDecodeError`, with no label |
| A top level that is not a JSON object | Returned unchecked; callers then raise `AttributeError` or `TypeError` |

The other two loaders are `mosquito_cfd._manifest` (#160) and
`mosquito_cfd._provenance.read_run_metadata` (PR #169 D8.5). `sidecar.read_units_sidecar` has the
same gap as `load_json_clear_error`.

- **New stdlib-only `mosquito_cfd/_json_loader.py`** holds
  `load_json_clear_error(path, *, label, require_object=True)`. Every rejection of the file's
  contents is exactly a labelled `ValueError`; the messages are specified once, in the
  `force-surrogate` delta ("Force-surrogate JSON files load through one labelled loader"). The
  malformed-JSON message is unchanged. Errors opening the path are not wrapped, following
  `_manifest`'s existing rule.
- **`sidecar.load_json_clear_error` becomes a re-export** of the same object. Callers' imports are
  unchanged.
- **`_manifest.load_manifest_configs` loads through `_json_loader`** with `require_object=False`, keeping
  every pinned message. `_manifest`'s "imports only the standard library" contract becomes "the
  standard library and `mosquito_cfd._json_loader`" (MODIFIED requirement). The stdlib-only test helper
  gains an exact-name allow-list.
- **`_provenance.read_run_metadata` keeps its own loader**, because its message format and its
  contract that every error is a `ValueError` (opening errors included) differ. A drift test sends
  the same bad inputs through all three loaders.
- **Callers** (spec: "Callers of the shared JSON loader label every content failure"):
  - `acceptance_gate`: its provenance reads get the object check. It reads the manifest through
    `load_manifest_configs`.
  - `corpus_guards`: its manifest read gets the object check.
  - `dataset`: it opts out of the object check and keeps its `ConfigExtractionError`s.
  - `metadata_capture.load_pod_run_metadata`: its own non-object check moves into the loader.
  - `metadata_capture.source_config_fields`: reads the manifest through `load_manifest_configs`.
    **BREAKING (minor).**
  - `sidecar.read_units_sidecar`: loads through `_json_loader`. **BREAKING (minor).**

### BREAKING items

- **BREAKING (minor): `source_config_fields` raises `ValueError` for a malformed manifest.** Before
  the change:
  - a config missing one of the reader's required keys (`name`, `index`, `stroke_amp_deg`,
    `frequency_fstar`, `pitch_amp_deg`, `reynolds`, `split`) was a `KeyError` naming the key, and
    only if that key was one this function reads;
  - a manifest with no `configs` key was a `KeyError` "config … not found (available: [])";
  - a non-list `configs` was a `TypeError`, and a non-mapping config an `AttributeError`;
  - a duplicate config name was accepted.

  These keep `KeyError`: a config absent from the manifest, and a `max_step` absent from the entry
  (`max_step` is not one of the reader's required keys). Every config of every committed manifest
  still passes (design E1, E4).
- **BREAKING (minor): wrong-shape files raise `ValueError`.** Deep nesting, and a non-object top
  level read through `load_json_clear_error`'s callers, now raise `ValueError` instead of
  `RecursionError`, `AttributeError` or `TypeError`. Nothing in the repository catches those
  (design E3).
- **BREAKING (minor): `read_units_sidecar`'s errors change.**
  - Messages change, with the type `ValueError` before and after:
    - invalid JSON: `{path} is not valid JSON: …` becomes
      `units sidecar {path} is not valid JSON: …`;
    - a non-object: `units must be a mapping, got list` becomes
      `units sidecar {path} top level is a list, not an object`.
  - Types change:
    - deep nesting was a `RecursionError` and becomes a labelled `ValueError`;
    - non-UTF-8 bytes were a bare `UnicodeDecodeError` (a `ValueError` subclass) and become
      exactly a labelled `ValueError`;
    - the digit limit was Python's unlabelled `ValueError` and becomes the labelled one.

## Impact

- Affected specs:
  - `force-surrogate`: three ADDED requirements (the loader; its callers; the three loaders reject
    the same inputs). One MODIFIED: "Sweep-manifest reading lives in a shared standard-library-only
    module", whose import contract now allows `mosquito_cfd._json_loader`.
  - `run-metadata`: one ADDED (the generator reads the manifest through the shared validated
    reader). One MODIFIED: the git-commit requirement replaces its "out of scope here, follow-up
    issue" sentence with a SHALL that labels every other pod-side content failure, and adds a
    scenario for it.
  - `field-surrogate`: one MODIFIED, "Corpus snapshots carry run identity and digest-pinned
    provenance". Its scenario "Reading provenance does not load the force-surrogate stack" lets
    `_manifest.py` import exactly `mosquito_cfd._json_loader`.
- Affected code:
  - `src/mosquito_cfd/_json_loader.py` (new) and `src/mosquito_cfd/_manifest.py`;
  - `src/mosquito_cfd/force_surrogate/`: `sidecar.py`, `acceptance_gate.py`, `corpus_guards.py`
    (`_load_manifest` only), `dataset.py` (`_verify_deck_sha256` and the `ConfigExtractionError`
    docstring), `metadata_capture.py` (`source_config_fields`, `load_pod_run_metadata`).
- Affected tests:
  - new `tests/test_json_loader.py` and `tests/_json_payloads.py`;
  - `tests/test_light_corpus_helpers.py` (the stdlib-only helper);
  - additions to the caller test files.
- Docs and change artifacts: `docs/CHANGELOG.md`, and `mutation-results.md` in this change
  directory.
- Not affected: committed data (every manifest, provenance and run_metadata file passes: E1, E4),
  the solver, Docker images and CI. `force_surrogate/__init__.py`, `train.py` and
  `evidence_figure.py` (F3a) are not touched.
- Overlap with `fix-stale-spec-claims`:
  - `docs/CHANGELOG.md`: a real `[Unreleased]` collision, resolved by writing the CHANGELOG entry
    last, after `git merge origin/main`.
  - `corpus_guards.py` and `tests/test_acceptance_gate.py`: disjoint hunks.

## Out of scope

- #174 (`evidence_figure.py`'s backend switch and the "Pinned sha256:" docstrings).
- What `_provenance.run_provenance` and `validate_image_digest` accept.
- **Type checks below the top level.** Examples: `realized_dt`, `cluster_run` or `cc_f1` that is not
  an object in `acceptance_gate`, and a non-mapping `configs` entry in `corpus_guards`. These can
  still raise `AttributeError` or `TypeError`. A follow-up issue will be filed (`tasks.md` 9.3).
- JSON reads that never went through `load_json_clear_error`:
  - `cfd_cost.py`;
  - `comparison_figure.py`, owned by `add-real-comparison-figures`;
  - `evidence_figure.py`, owned by F3a;
  - `benchmarks/metadata.py`.
