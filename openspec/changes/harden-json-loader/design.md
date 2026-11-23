# Design: harden-json-loader (#175)

## Context

`share-light-corpus-helpers` (PR #177) hardened two loaders and left the third alone:

- `mosquito_cfd._manifest`: UTF-8, then `except (ValueError, RecursionError)`, then a top-level-object
  check. It does not wrap `OSError`.
- `mosquito_cfd._provenance.read_run_metadata`: the same three checks, and it wraps `OSError` too.
- `force_surrogate.sidecar.load_json_clear_error`: `JSONDecodeError` only.

The user's decisions (2026-11-22) are recorded in D1, D2, D3, D5, D6, D7 and D8.

## Evidence (gathered before proposing)

**E1. Committed JSON audit** (scratchpad `audit_json.py` on `c898b24`).

- Every file from `git ls-files '*.json'` whose basename contains `sweep_manifest`,
  `sweep_provenance` or `run_metadata` was read with the strict rules: UTF-8, `json.loads` with
  `(ValueError, RecursionError)` caught, and a top-level `dict`.
- **Result:** 56 files (46 run_metadata, 7 by manifest name, 3 provenance), 0 failures, and no
  byte-order mark.
- The four real manifests also pass `load_manifest_configs`. The three `sweep_manifest.units.json`
  files are units sidecars that only match the name pattern.

**E2. Exceptions** (Python 3.11.13 from `uv.lock`, Windows; confirmed by the TDD reviewer):

- 100000-level nesting raises `RecursionError`.
- `{"a": <5000 digits>}` raises `ValueError("Exceeds the limit (4300 digits) …")` with no cause. This
  depends on `sys.get_int_max_str_digits()` being in `(0, 5000)`.
- A directory path raises `PermissionError` on Windows and `IsADirectoryError` on Linux. Both are
  `OSError`, and neither is a `ValueError`.
- A leading UTF-8 byte-order mark raises `JSONDecodeError("Unexpected UTF-8 BOM …")`.

**E3. Exception handlers.** Nothing in `src/` or `scripts/` catches `RecursionError`, or the
`AttributeError`/`TypeError` a non-object would cause, around these loaders. The two
`except (TypeError, ValueError)` sites (`runner.py:473`, `run_one_config.py:218`) wrap `int()`. No
caller catches `source_config_fields`'s `KeyError`.

**E4. `source_config_fields` on committed manifests.**

- Every config of `examples/prelim_sweep` (27), `examples/prelim_sweep_fine` (27) and
  `examples/prelim_sweep_fine_pilot` (3), with the deck its `input_file` names, returns without
  raising on `c898b24`.
- The fixture manifest's decks are not committed at their `input_file` paths. Its tests use
  `tests/fixtures/run_metadata/inputs.3d.s35_f085_p45`.

**E5. Current behaviour at the gate** (TDD reviewer, on `c898b24`):

- A `[]` manifest already raises `_manifest`'s message, because the gate's own read returns the
  list and `build_dataset` then rejects it.
- Non-UTF-8 or `[]` run_metadata returns a failed `GateResult`.
- Nested run_metadata raises `RecursionError`.

## Decisions

### D1. `_json_loader.py`: one loader, stdlib only

```python
def load_json_clear_error(path: Path | str, *, label: str, require_object: bool = True) -> Any:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} {path} is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        raise ValueError(f"{label} {path} is not valid JSON: {exc}") from exc
    if require_object and not isinstance(data, dict):
        raise ValueError(f"{label} {path} top level is a {type(data).__name__}, not an object")
    return data
```

- **Location.** It sits at the top of the package so `_manifest` can share it; `sidecar` imports
  `benchmarks.metadata`, so `_manifest` cannot import from there.
- **Re-export.** `sidecar` re-exports it with the redundant-alias form, as
  `share-light-corpus-helpers` D4 did for `dataset`. The old docstring's "leaf module, no circular
  import" rationale moves into `_json_loader`'s module docstring, where it is still true.
- **Messages.** Specified once, in the spec. Two of them coincide with existing pinned messages
  for a given label: the JSON and UTF-8 messages with `label="sweep manifest"` match `_manifest`'s,
  and the non-object message with `label="pod-side run_metadata.json"` matches
  `load_pod_run_metadata`'s.
- **Strict UTF-8.** It decodes with `utf-8`, not `utf-8-sig`, so a byte-order mark stays "not valid
  JSON", as it is today. No committed file has one (E1).
- **Return type.** `Any`, since with `require_object=False` any JSON value comes back. The old
  `-> dict` annotation was already untrue.

### D2. The object check is on by default; two callers opt out

Of the eight call sites today, two move to `load_manifest_configs` (D6, D7), leaving six.
`dataset` opts out (below). The other five expect a mapping and get the check without a code
change:

- the gate's two provenance reads (`run_acceptance_gate`, `record_check_result`);
- `corpus_guards._load_manifest`;
- `load_pod_run_metadata`;
- the gate's own run_metadata read. This one is only defence in depth (D6).

`read_units_sidecar` joins them (D8). The two opt-outs:

- **`_manifest`**: keeps its pinned `manifest {path} top level is a {type}, not an object; not a
  sweep manifest`.
- **`dataset._verify_deck_sha256`**: keeps `ConfigExtractionError` (D4).

**`_manifest`'s import contract.** `_manifest` now imports `mosquito_cfd._json_loader`. Two live
statements that it "imports only the standard library" therefore become "the standard library
and `mosquito_cfd._json_loader`". Both get MODIFIED deltas:

- the `force-surrogate` requirement "Sweep-manifest reading lives in a shared
  standard-library-only module";
- the `field-surrogate` scenario "Reading provenance does not load the force-surrogate stack", in
  "Corpus snapshots carry run identity and digest-pinned provenance".

Two looser phrases are left as they are, because they stay true transitively: `_manifest` loads
only the standard library and one stdlib-only sibling. They are `field-surrogate` spec line 618
("the shared, standard-library-only reader") and `docs/field_surrogate/roadmap.md:340`
("stdlib-only `mosquito_cfd._manifest`").

The test helper `_assert_stdlib_only(path, allowed=())` changes with it. These semantics were
prototyped in round 2:

- **`ImportFrom`.** Check `node.module` only (the names after `import` are attributes, not
  modules). Accept it if `level == 0` and either its first component is in
  `sys.stdlib_module_names`, or `node.module` is exactly in `allowed`.
- **`Import`.** Check each `alias.name` the same way.
- **Accepted:** `import mosquito_cfd._json_loader` and
  `from mosquito_cfd._json_loader import load_json_clear_error`.
- **Rejected:** `from mosquito_cfd import _json_loader`, `from mosquito_cfd import force_surrogate`,
  `import mosquito_cfd`, `import mosquito_cfd._json_loader.sub` and
  `import mosquito_cfd._json_loaderx`.

  Rejecting `from mosquito_cfd import _json_loader` matches the import form task 2.1's monkeypatch
  test pins. Do not copy `test_corpus_imports_no_force_surrogate_or_benchmarks`' "module +
  module.alias" expansion: under any-passes semantics it would accept `from mosquito_cfd import
  force_surrogate`.
- **Recursion.** For each allowed import found, apply the helper with no allow-list to
  `PKG_DIR / (name.removeprefix("mosquito_cfd.") + ".py")`.
- **Self-test.** `test_stdlib_only_allow_list_is_exact` pins every verdict above. Mutation M21
  mutates the exact match to a prefix match in both directions.

The fresh-interpreter test `test_manifest_alone_loads_nothing_heavy` still checks the whole import
chain at run time.

### D3. `OSError` is not wrapped

Only the file's *contents* are labelled. Some callers check existence first: the gate's
provenance and run_metadata reads, `dataset`, and `load_pod_run_metadata`. The rest pass the error
from opening the path straight through to their caller, as they do today: the gate's and
`source_config_fields`' manifest reads (through `_manifest`), `corpus_guards`, and
`read_units_sidecar`. `test_pod_run_metadata_raises_on_missing_file` pins `FileNotFoundError`. A directory or an
unreadable file keeps raising its `OSError` subclass, as `_manifest` does. `_provenance` keeps
wrapping, because its contract says every error is a `ValueError` (D5).

### D4. `dataset` preserves `ConfigExtractionError` by checking `__cause__`

```python
try:
    metadata = load_json_clear_error(metadata_path, label="run_metadata file", require_object=False)
except ValueError as exc:
    if isinstance(exc.__cause__, UnicodeDecodeError):
        raise ConfigExtractionError(
            f"run metadata for config {name!r} at {metadata_path} is not UTF-8: {exc.__cause__}"
        ) from exc.__cause__
    raise
```

- **Unchanged message.** It interpolates the same `UnicodeDecodeError` text as today.
- **Unchanged chain.** The `from` target is the `UnicodeDecodeError`, as today.
- **Why not subclass exceptions?** The issue asks for `type(e) is ValueError` exactly at every
  caller. Checking `__cause__` keeps that and relies only on D1's explicit `raise … from exc`
  (mutations M15–M18 test the coupling).
- **The other two cases.** Deep nesting and the digit limit become the labelled `ValueError`. Like
  malformed JSON today, they propagate out of the gate rather than becoming a
  `ConfigExtractionError`.
- **Docstrings.** The `ConfigExtractionError` docstring's "malformed-file errors … stay plain
  `ValueError`" names these two cases. `_verify_deck_sha256`'s docstring describes the
  `__cause__` hand-off.

### D5. `_provenance` keeps its loader; a drift test guards all three

Routing `_provenance` through `_json_loader` would need a message-format hook, plus its `OSError` wrapping
kept outside the shared loader. That is more machinery than one caller justifies. Instead,
`test_every_loader_rejects_the_same_inputs_as_value_errors` runs the five payloads through all
three loaders.

It is written in task 2, after `_json_loader` exists. It passes when written, so it is a guard,
not a red. Its
strength comes from mutations M1–M3 applied to `_json_loader` and to `_provenance`. `_manifest` has no
except tuple of its own after task 2, so M1–M3 on `_json_loader` cover it.

### D6. The gate reads the manifest through `load_manifest_configs`, in the same commit as D1

`configs = load_manifest_configs(manifest_path)` replaces the gate's own read, and both
`manifest["configs"]` loops use `configs`.

- **Why the same commit as the loader.** At `c898b24` a `[]` manifest already raises `_manifest`'s
  message (E5). With D1's default object check alone, the gate's own read would raise the generic
  message first, which is a transient regression. Doing D6 in the same commit avoids it.
- **Red and guard cases.** `test_gate_manifest_errors_are_the_shared_readers` is mixed (round 2,
  reproduced):
  - `[]` and `5` are guards, green before and after;
  - deep nesting, the digit limit and non-UTF-8 are reds, because at `c898b24` the gate's own
    unhardened read raises `RecursionError`, an unlabelled `ValueError` and a bare
    `UnicodeDecodeError` before `build_dataset` runs.
- **M9.** M9 reverts the gate to `load_json_clear_error(manifest_path, label="sweep manifest")`,
  with the default object check. The `require_object=False` variant is an *equivalent* mutant,
  because `build_dataset` then raises `_manifest`'s message. Record it as equivalent.
- **The gate's own run_metadata read.** `build_dataset` receives the same `run_metadata_paths` and
  parses every non-dropped config's file first, in `_verify_deck_sha256`. So a bad run_metadata
  file surfaces from `dataset`:
  - non-UTF-8 or non-object becomes a gate failure;
  - nesting or the digit limit raises a labelled `ValueError`.

  The gate's own object check is defence in depth, has no killable mutant, and the spec says so.

### D7. `source_config_fields` reads through `load_manifest_configs`

- **What changes.** `configs = load_manifest_configs(manifest_path)` replaces `load_json_clear_error`
  plus `.get("configs", [])`.
- **What stays.**
  - The lookup.
  - The `KeyError` for an absent config, with the same message and `available` list.
  - `_entry_field`'s `KeyError` for `max_step`.
- **What becomes `ValueError`.** Everything the reader rejects, before the lookup (BREAKING minor,
  `proposal.md`). The old pinned test with a config of only `name` and `max_step` is replaced by
  two tests: a missing required key raises `ValueError`, and a missing `max_step` is still a
  `KeyError`.
- **Imports.** `metadata_capture` gains `from mosquito_cfd._manifest import load_manifest_configs`.
  `_manifest` is light, so this cannot create a cycle.

### D8. `read_units_sidecar`

It loads through `load_json_clear_error(path, label="units sidecar")` with the object check on, so
the non-object message names the path. `_validate_units` still runs on the loaded mapping and is
unchanged for writes. `json` stays imported in `sidecar.py`, because `write_units_sidecar` uses
it.

## Risks

- **`__cause__` coupling (D4).** Covered by tests and by mutations M15–M18.
- **Merge with `fix-stale-spec-claims`.**
  - `docs/CHANGELOG.md` collides. It is written last, after `git merge origin/main`.
  - Its `corpus_guards.py` comment hunk and inserted gate tests are disjoint from this change. The
    new gate tests go next to the related existing tests, not at the end of the file.
  - Its live-spec guard checks only its registered requirements.
- **The digit-limit payload depends on the interpreter setting.** `tests/_json_payloads.py` asserts
  `0 < sys.get_int_max_str_digits() < 5000` at import, so a changed setting fails loudly instead of
  confusingly.
- **CPython message wording.** Tests derive `JSONDecodeError` and `UnicodeDecodeError` text from
  the same input at run time. They do not hard-code it, except where existing tests already do.
- **Module name.** CPython ships a C accelerator named `_json`, listed in
  `sys.stdlib_module_names`. A module at `src/mosquito_cfd/_json.py` would shadow it whenever
  `src/mosquito_cfd` itself was on `sys.path[0]`, for example a script run from there. The module is
  therefore named `_json_loader` (round 2). `tests/_json_payloads.py` does not shadow anything.

## Mutation plan

Run in a throwaway worktree at the final code SHA, with `PYTHONDONTWRITEBYTECODE=1` and
`PYTHONPATH=<mutation worktree>/src`. Restore each file from saved bytes, and run nothing else at
the same time. If `git merge origin/main` later changes code in a touched file, re-run that file's
mutants at the post-merge SHA.

| ID | Mutant | Expected killer |
|---|---|---|
| M1 | `_json_loader` / `_provenance`: drop `RecursionError` from the except tuple | deep-nesting tests; drift test |
| M2 | `_json_loader` / `_provenance`: narrow `ValueError` to `json.JSONDecodeError` | digit-limit tests; drift test |
| M3 | `_json_loader` / `_provenance`: remove the UTF-8 wrap | non-UTF-8 tests (`type is ValueError`); drift test |
| M4 | `_json_loader`: default `require_object=False` | non-object tests at gate provenance, `corpus_guards`, pod metadata, units |
| M5 | `_json_loader`: drop the object check | as M4, plus the direct loader test |
| M6 | `dataset`: drop the `__cause__` branch | `test_undecodable_run_metadata_is_a_named_extraction_error`; gate non-UTF-8 test |
| M7 | `dataset`: `require_object=True` | `test_non_object_run_metadata_is_an_extraction_error`; gate `[]` run_metadata test |
| M8 | `_manifest`: `require_object=True` | pinned non-object manifest message tests |
| M9 | gate: manifest via `load_json_clear_error(…, label="sweep manifest")` (default object check) | `test_gate_manifest_errors_are_the_shared_readers` (`[]`, `5`). The `require_object=False` variant is equivalent (D6) |
| M10 | `source_config_fields`: revert to `load_json_clear_error` + `.get` | missing-required-key test; `[]` exact message; `{"configs": 5}`; duplicate |
| M11 | `read_units_sidecar`: revert to its old loader | units tests |
| M12 | `_json_loader`: wrap `OSError` as `ValueError` | directory tests (loader, pod metadata, units) |
| M13 | `sidecar`: its own copy instead of the re-export | identity test |
| M14 | `_json_loader` (and separately `_manifest`): `import mosquito_cfd.force_surrogate` | stdlib-only AST tests; fresh-interpreter tests |
| M15 | `_json_loader`: `from None` on the UTF-8 branch; separately, on the JSON branch | `__cause__` assertions in the loader tests; M15-UTF-8 also `test_undecodable…` and the gate non-UTF-8 test |
| M16 | `dataset`: `from exc` instead of `from exc.__cause__` | `__cause__` isinstance check in `test_undecodable…` |
| M17 | `dataset`: `{exc}` instead of `{exc.__cause__}` in the message | exact message in `test_undecodable…` |
| M18 | `dataset`: `isinstance(exc.__cause__, ValueError)` | digit-limit case of `test_unparseable_run_metadata_is_a_labelled_value_error` |
| M19 | `read_units_sidecar`: `require_object=False` | exact `[]` units message |
| M20 | gate / `record_check_result` provenance read: `require_object=False` | `[]` and `5` provenance tests |
| M21a | `_assert_stdlib_only`: `any(name.startswith(a) for a in allowed)` | allow-list self-test (`_json_loaderx`, `_json_loader.sub`) |
| M21b | `_assert_stdlib_only`: `any(a.startswith(name) for a in allowed)` | allow-list self-test (`from mosquito_cfd import force_surrogate`, `import mosquito_cfd`) |
