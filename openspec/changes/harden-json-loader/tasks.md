# Tasks: harden-json-loader (#175)

Every feature task is red → green in one commit. Write the tests and run them. Paste the output
into the commit body, under two headings: **Red** (tests that fail, with their failure) and
**Guards** (tests that pass before and after; list them by name only). A **Mixed** test is
listed under both headings, by parameter. Then implement and run again green.

Run tests as `unset VIRTUAL_ENV; PYTHONPATH=src uv run pytest <files> -p no:cacheprovider`. Every
commit message ends `(advances #175)` and carries the `Co-Authored-By` trailer. No commit message
contains a closing keyword.

**Payloads.** `tests/_json_payloads.py` (new, task 1) holds the byte strings named in the spec
scenario "Unparseable files are labelled ValueErrors", plus `b"[]"` and `b"5"`. At import it
asserts `0 < sys.get_int_max_str_digits() < 5000`. "The five payloads" below means deep nesting,
the digit limit, not UTF-8, `[]` and `5`. Assertions use `type(err) is ValueError` and check that
the path is in the message, never a bare `pytest.raises(ValueError)`.

**Helpers.** `_run_child`, `_HEAVY` and `_assert_stdlib_only` are imported from
`test_light_corpus_helpers`, as that file already imports helpers from
`test_field_surrogate_corpus`.

**New caller tests** go next to the existing tests for the same function, not at the end of the
file (merge overlap with `fix-stale-spec-claims`).

## 0. Pre-flight

- [x] 0.1 Commit the approved proposal, `openspec/changes/harden-json-loader/` only:
  `docs(openspec): propose harden-json-loader (advances #175)`. Later review-round edits to the
  proposal go in further `docs(openspec):` commits before task 1.
- [x] 0.2 Check `git rev-parse HEAD` equals that commit, and `git branch --show-current` is
  `harden-json-loader`. (`uv sync --frozen --group viz` has already run.)
- [x] 0.3 Baseline. Run these and record the counts:
  - `tests/test_light_corpus_helpers.py`
  - `tests/test_force_surrogate_sidecar.py`
  - `tests/test_acceptance_gate.py`
  - `tests/test_corpus_guards.py`
  - `tests/test_force_surrogate_dataset.py`
  - `tests/test_metadata_capture.py`
  - `tests/test_generate_run_metadata_cli.py`
  - `tests/test_field_surrogate_corpus.py`
  - `tests/test_force_surrogate_driver.py`
  - `tests/test_force_surrogate_runner.py`
  - `tests/test_force_surrogate_run_sweep_driver.py`
  - `tests/test_force_surrogate_sweep.py`

  Every green step below runs these plus `tests/test_json_loader.py`, once it exists.

## 1. The shared loader, its re-export, the gate's manifest routing, and every inheriting caller (D1–D4, D6)

The default object check fixes the gate's provenance reads, `corpus_guards` and
`load_pod_run_metadata` in one step. Without changes in the same commit, two things would break:

- `dataset` would regress (D4);
- the gate's `[]`-manifest message would regress (D6, E5).

So all of it is one commit.

- [x] 1.1 **Tests.**
  - **New `tests/test_json_loader.py`:**
    - **Red:** `test_json_module_imports_only_the_standard_library`, which runs
      `_assert_stdlib_only` on `_json_loader.py`. Fails with `FileNotFoundError`.
    - **Red:** `test_json_alone_loads_nothing_heavy` (fresh interpreter). Fails with
      `_run_child`'s `AssertionError`; the child's stderr shows `ModuleNotFoundError`.
    - **Red:** `test_sidecar_name_is_the_shared_loader`. Fails with `ModuleNotFoundError`.
    - **Mixed:** `test_unparseable_file_is_a_labelled_value_error`. It covers the six byte strings
      of the spec scenario: deep nesting, digit limit, not UTF-8, `{`, empty, BOM.
      - It is parametrized over the module, `mosquito_cfd._json_loader` and
        `mosquito_cfd.force_surrogate.sidecar`, imported inside the test.
      - Red: every `_json_loader` case (`ModuleNotFoundError`), and the sidecar's deep nesting,
        digit limit and not UTF-8 cases (`RecursionError`, an unlabelled `ValueError`, a bare
        `UnicodeDecodeError`).
      - Guards: the sidecar's `{`, empty and BOM cases, which the old function already labels as
        a `JSONDecodeError`.
      - It asserts the exact prefixes, and the `__cause__` type for every case.
    - **Red:** `test_json_decode_error_message_is_unchanged`, against `_json_loader` only
      (`ModuleNotFoundError`). The expected text is built from `json.loads("{")`'s own
      `JSONDecodeError`, not hard-coded.
    - **Red:** `test_non_object_top_level_is_a_labelled_value_error`, over `[]`/`5`/`"x"`/`null`,
      with exact messages (`list`, `int`, `str`, `NoneType`). Parametrized over both modules; the
      sidecar case returns the value today. With `require_object=False`, each value comes back
      unchanged.
    - **Red:** `test_valid_object_is_returned_unchanged`, given a `Path` and a `str`. The old
      sidecar function raises `AttributeError` for a `str`.
    - **Guards:** `test_missing_file_is_file_not_found` and
      `test_directory_is_an_os_error_not_a_value_error`.
  - **`tests/test_light_corpus_helpers.py`:**
    - Change `_assert_stdlib_only(path, allowed=())` per D2.
    - **Red:** `test_stdlib_only_allow_list_is_exact`. With `allowed=("mosquito_cfd._json_loader",)`,
      it writes one temp file per import statement and checks each verdict (D2 semantics):
      - accepted: `import mosquito_cfd._json_loader` and
        `from mosquito_cfd._json_loader import load_json_clear_error`;
      - rejected: `from mosquito_cfd import force_surrogate`, `from mosquito_cfd import
        _json_loader`, `import mosquito_cfd`, `import mosquito_cfd.force_surrogate`,
        `import mosquito_cfd._json_loaderx` and `import mosquito_cfd._json_loader.sub`.

      Before the helper change it fails with `TypeError`, an unexpected keyword.
  - **`tests/test_acceptance_gate.py`:**
    - **Red:** `test_gate_rejects_unparseable_provenance`, over the five payloads, via
      `run_acceptance_gate` with `_make_corpus`. Fails with `RecursionError`, an unlabelled
      `ValueError`, a bare `UnicodeDecodeError`, and `AttributeError` (`list.get`, `int.get`).
    - **Red:** `test_record_check_result_rejects_unparseable_provenance`, over the five payloads.
      It also asserts the provenance file's bytes are unchanged afterwards. Fails as above, with
      `AttributeError` for `.setdefault`.
    - **Red:** `test_gate_rejects_unparseable_run_metadata`, covering deep nesting and the digit
      limit. Expected: exactly `ValueError` beginning `run_metadata file <path> is not valid JSON: `.
      Fails with `RecursionError` and an unlabelled `ValueError`.
    - **Mixed:** `test_gate_manifest_errors_are_the_shared_readers`, over the five payloads.
      - Red: nesting, digit limit and UTF-8, whose messages must begin `sweep manifest <path> `. At
        `c898b24` the gate's own unhardened read raises `RecursionError`, an unlabelled
        `ValueError` and a bare `UnicodeDecodeError`.
      - Guards: `[]` and `5`, which give `manifest <path> top level is a <list|int>, not an object;
        not a sweep manifest` at `c898b24` (E5). They guard D6 against the regression the default
        object check would otherwise cause, and they kill M9.
    - **Guard:** `test_gate_reports_extraction_errors_for_bad_run_metadata`. Non-UTF-8 and `[]`
      run_metadata each return `passed=False`, with a failure naming the config.
  - **`tests/test_corpus_guards.py`:**
    - **Red:** `test_unparseable_manifest_is_a_labelled_value_error`, over the five payloads, via
      `check_deck_matches_manifest_max_step(CorpusEntry(name="t", path=tmp_path,
      has_parquet=False, has_per_config_metadata=False))`. Fails with `RecursionError`, an
      unlabelled `ValueError`, a bare `UnicodeDecodeError`, and `TypeError` (`list` indices,
      `int` not subscriptable).
  - **`tests/test_metadata_capture.py`:**
    - **Red:** `test_pod_run_metadata_rejects_unparseable_files`, covering deep nesting, the digit
      limit and non-UTF-8, with exact prefixes. Fails with `RecursionError`, an unlabelled
      `ValueError`, and a bare `UnicodeDecodeError`.
    - **Guard:** `test_pod_run_metadata_directory_is_an_os_error`.
    - The existing non-object test, `test_pod_run_metadata_rejects_non_object_top_level`, stays
      unchanged.
  - **`tests/test_force_surrogate_dataset.py`:**
    - **Red:** `test_unparseable_run_metadata_is_a_labelled_value_error`, covering deep nesting and
      the digit limit, through `build_dataset`.
    - **Guard:** `test_non_object_run_metadata_is_an_extraction_error`. A `[]` file raises
      `ConfigExtractionError` with the exact pre-change message. (After the pre-PR review this
      was folded into the existing `test_non_object_run_metadata_is_a_named_extraction_error`,
      now exact-type and exact-message for all four payloads; see `design.md`, Deviations.)
    - **Guard:** tighten `test_undecodable_run_metadata_is_a_named_extraction_error`:
      - assert the exact message, with the `UnicodeDecodeError` text computed by decoding the same
        bytes;
      - assert `isinstance(excinfo.value.__cause__, UnicodeDecodeError)`.
- [x] 1.2 **Green.**
  - Add `src/mosquito_cfd/_json_loader.py` per D1. Its module docstring states:
    - the stdlib-only contract;
    - the D3 rule;
    - the "leaf module" rationale moved from `sidecar`.
  - `sidecar.py`: replace the function with the redundant-alias re-export.
  - `acceptance_gate.py`: `configs = load_manifest_configs(manifest_path)` (D6). Add a `Raises:`
    section to `run_acceptance_gate`'s docstring: a manifest, provenance or run_metadata file that
    is not UTF-8, not JSON or not an object raises a `ValueError` naming the path; opening errors
    are not wrapped.
  - `dataset.py`: `_verify_deck_sha256` per D4, together with its docstring and the
    `ConfigExtractionError` docstring (D4, Docstrings).
  - `metadata_capture.load_pod_run_metadata`: drop its own `isinstance` check. Its docstring loses
    the "Not yet wrapped (#175)" list and states the D3 rule.

  Run the 0.3 files and `tests/test_json_loader.py` green.

  Commit: `fix(json): one stdlib loader labels every content failure for its callers (advances
  #175)`.

## 2. `_manifest` loads through `_json_loader`; drift test across the three loaders (D2, D5)

- [x] 2.1 **Tests** in `tests/test_json_loader.py` and `tests/test_light_corpus_helpers.py`:
  - **Red:** `test_manifest_uses_the_shared_loader`. It monkeypatches
    `mosquito_cfd._manifest.load_json_clear_error` with a recording stub that returns
    `{"configs": []}`, and asserts one call with `label="sweep manifest", require_object=False`.
    Fails with `AttributeError`. This fixes the import form
    `from mosquito_cfd._json_loader import load_json_clear_error`.
  - **Guard (edited):** change `test_manifest_module_imports_only_the_standard_library` to
    `_assert_stdlib_only(PKG_DIR / "_manifest.py", allowed=("mosquito_cfd._json_loader",))`. It is
    green when written. Left unchanged, it would go red the moment `_manifest` imports
    `_json_loader`.
  - **Guard:** `test_every_loader_rejects_the_same_inputs_as_value_errors` (D5), over the five
    payloads.
- [x] 2.2 **Green.**
  - `_manifest.load_manifest_configs` calls `load_json_clear_error(path, label="sweep manifest",
    require_object=False)`.
  - It keeps its non-object check and every message.
  - Remove the now-unused `import json` (ruff F401).
  - Update the module docstring: it imports the standard library and `_json_loader`, and parsing is
    delegated. Drop "as before the move".
  - Every pinned test in `test_light_corpus_helpers.py`, including the fresh-interpreter
    light-import tests, stays green.

  Commit: `refactor(manifest): load through the shared JSON loader (advances #175)`.

## 3. `source_config_fields` reads through `load_manifest_configs` (D7)

- [x] 3.1 **Tests** in `tests/test_metadata_capture.py`:
  - Replace `test_source_config_fields_raises_clear_error_on_missing_manifest_field` with:
    - **Red:** `test_source_config_fields_missing_required_key_is_a_value_error`. A config of only
      `name` and `max_step` raises exactly `ValueError` matching
      `missing required key\(s\).*stroke_amp_deg`. It raises `KeyError` today.
    - **Guard:** `test_source_config_fields_missing_max_step_is_still_a_key_error`. Every required
      key is present, `max_step` is absent, and the deck is `_DECK`.
  - **Red:** `test_source_config_fields_rejects_unparseable_manifests`, over the five payloads plus
    `{}`, with `type is ValueError` and the path in the message.
    - `[]` pins `_manifest`'s exact message. After task 1 it gives the generic `sweep manifest …`
      message, so it is red.
    - `{}` is red today: `KeyError … (available: [])`.
    - Nesting, digit limit, UTF-8 and `5` are guards after task 1.
  - **Red:** `test_source_config_fields_rejects_wrongly_shaped_config_lists`, with the deck
    `_DECK`. Each case asserts the shared reader's message (no path):
    - `{"configs": 5}`: `TypeError: 'int' object is not iterable` today;
    - `{"configs": [5]}`: `AttributeError` today;
    - two valid configs sharing one name: accepted today.
  - **Guard:** `test_source_config_fields_accepts_every_committed_manifest`. It covers every config
    of the three `examples/` manifests, with their decks (57 calls), and the fixture config with
    `_DECK` (E4).
  - `test_manifest_lookup_raises_on_missing_config` and
    `test_manifest_lookup_raises_on_malformed_manifest_json` stay unchanged.
- [x] 3.2 **Green.**
  - `source_config_fields` per D7.
  - Its docstring's `Raises:` says `ValueError` for anything the shared reader rejects, and
    `KeyError` for an absent config or a missing `max_step`.

  Commit: `fix(metadata-capture): read the manifest through the shared validated reader (advances
  #175)`. State BREAKING (minor) in the body.

## 4. `read_units_sidecar` (D8)

- [x] 4.1 **Tests** in `tests/test_force_surrogate_sidecar.py`:
  - **Red:** `test_read_units_sidecar_labels_every_content_failure`. It covers:
    - `{`: exact prefix `units sidecar <path> is not valid JSON: `;
    - `[]`: the exact message;
    - deep nesting, digit limit, non-UTF-8 and `5`: `type is ValueError` with the
      `units sidecar <path> ` prefix.

    It fails today with the old prefix, `units must be a mapping`, `RecursionError`, an unlabelled
    `ValueError`, and a bare `UnicodeDecodeError`.
  - **Guard:** `test_read_units_sidecar_directory_is_an_os_error`.
- [x] 4.2 **Green.** `read_units_sidecar` loads through `load_json_clear_error(path, label="units
  sidecar")`, then calls `_validate_units`. Its `Raises:` says that content failures are labelled
  per `_json_loader` and that units outside the vocabulary are rejected.

  Commit: `fix(sidecar): units sidecar reads label every content failure (advances #175)`. State
  BREAKING (minor, message text) in the body.

## 5. Verification

- [x] 5.1 Run `grep -rnE --include=*.py "#175|Not yet wrapped" src/`. Expect no "Not yet
  wrapped", and check that each `#175` hit is a deliberate reference to this change, not a
  statement that something is still unfixed.
- [x] 5.2 Run `grep -n "except UnicodeDecodeError" src/mosquito_cfd/force_surrogate/dataset.py`,
  and expect no match: D4 uses `__cause__`.
- [x] 5.3 Run the full suite in the background, exactly as CI does: `uv run pytest -v -m "not
  gpu" -p no:cacheprovider`, with `PYTHONPATH=src`. It takes about 6 minutes.
- [x] 5.4 Run `uv run ruff check` and `uv run ruff format --check` on exactly `src/ tests/
  scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`.
  Check each exit code with `>/dev/null && echo OK`.
- [x] 5.5 Run mutations M1–M21b (`design.md`, "Mutation plan"). For each surviving mutant, add a
  killing test as its own red → green commit, or record why it is equivalent. Record each killer
  in `openspec/changes/harden-json-loader/mutation-results.md`.
- [x] 5.6 Re-run the E1 audit through `_json_loader.load_json_clear_error` on all 56 files, and expect 0
  failures. Paste the command and its output into `mutation-results.md`.
- [x] 5.7 Run `openspec validate harden-json-loader --strict`.
- [x] 5.8 Reconcile the implementation against `proposal.md`, `design.md`, both spec deltas and
  this file. Record any deviation as `### Why N instead of M?` in `design.md`.

## 6. Change artifacts commit

- [x] 6.1 Commit `mutation-results.md`, any `design.md`, `proposal.md` or `tasks.md` reconciliation
  edits, and the ticked task boxes: `docs(openspec): mutation results and reconciliation for
  harden-json-loader (advances #175)`.

## 7. Merge main

- [x] 7.1 Run `git merge origin/main`, with no rebase.
- [x] 7.2 Re-run the 0.3 files and `tests/test_json_loader.py`.
- [x] 7.3 If the merge changed code in a touched file, re-run that file's mutants.

## 8. CHANGELOG (last commit)

- [x] 8.1 In `docs/CHANGELOG.md`, under `[Unreleased]` → `### Changed`, add **one** bullet in the
  file's style:
  - The headline and the OpenSpec slug in parentheses: every way a force-surrogate JSON file can
    fail to load is a labelled `ValueError` (`harden-json-loader`).
  - Sub-bullets for the new `_json_loader.py` and the re-export, the callers, and `_manifest`'s import
    contract.
  - The three BREAKING items from `proposal.md`, each prefixed `**BREAKING (minor):**`.
  - Finish with `(advances #175)`, or `(fixes #175)` if 9.2 decides it is fully resolved.

  Do not edit the historical line "`load_json_clear_error`'s remaining gaps are #175".

  Commit: `docs(changelog): harden-json-loader entries (advances #175)`.

## 9. Pre-merge

- [ ] 9.1 Run `/pre-merge-check`.
- [ ] 9.2 The PR says `Fixes #175` only if every row of the issue's table and every listed caller is
  covered; otherwise it says `advances #175`. That applies to the PR title and body. Confirm CI is
  green on ubuntu, where the directory tests take the `IsADirectoryError` branch.
- [ ] 9.3 File a follow-up issue for type checks below the top level: `realized_dt`, `cluster_run`
  and `cc_f1` in `acceptance_gate`, and `configs` entries in `corpus_guards`. Link it from the PR.
