# Mutation results: harden-json-loader (#175)

## How it was run

- **Where.** A throwaway worktree, detached at the final code SHA `a160969`. `git rev-parse HEAD`
  was checked before running. The worktree was removed afterwards, with a clean status.
- **Restoring.** Each file was restored from its saved bytes, never with `git checkout`, and the
  script asserted the bytes matched after every mutant.
- **Environment.** `PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH=<mutation worktree>/src`, using this
  worktree's `.venv` interpreter with the working directory set to the mutation worktree.
  `test_light_corpus_helpers` asserts the package it imports is that tree.
- **Isolation.** Nothing else ran at the same time. The full suite had already finished: 2638
  passed, 27 skipped.
- **Scripts.** `mutate.py` ran every mutant in the table. `mutate_extra.py` re-ran M9, M9eq and M14
  (see "Corrections to the first run").

A mutant counts as killed when the listed test files fail. The killers are the failing tests.

## Results

| ID | Mutant | Verdict | Killed by |
|---|---|---|---|
| M1a | `_json_loader`: drop `RecursionError` from the except tuple | killed | `test_unparseable_file_is_a_labelled_value_error[deep_nesting-*]`; drift test `[deep_nesting-_json_loader]`, `[deep_nesting-_manifest]` |
| M1b | `_provenance`: the same | killed | drift test `[deep_nesting-_provenance]` |
| M2a | `_json_loader`: narrow `ValueError` to `json.JSONDecodeError` | killed | `test_unparseable_file_is_a_labelled_value_error[int_digit_limit-*]`; drift test `[int_digit_limit-_json_loader]`, `[int_digit_limit-_manifest]` |
| M2b | `_provenance`: the same | killed | drift test `[int_digit_limit-_provenance]` |
| M3a | `_json_loader`: remove the UTF-8 wrap | killed | `test_unparseable_file_is_a_labelled_value_error[non_utf8-*]`; drift test `[non_utf8-_json_loader]`, `[non_utf8-_manifest]` |
| M3b | `_provenance`: remove `UnicodeDecodeError` from its wrap | killed | drift test `[non_utf8-_provenance]` |
| M4 | `_json_loader`: default `require_object=False` | killed (20 tests) | `test_non_object_top_level_is_a_labelled_value_error` (all 8); drift test `[list,int-_json_loader]`; gate provenance, `record_check_result`, `corpus_guards`, units `[list,int]` |
| M5 | `_json_loader`: drop the object check | killed (20 tests) | as M4 |
| M6 | `dataset`: drop the `__cause__` branch | killed | `test_undecodable_run_metadata_is_a_named_extraction_error`; `test_gate_reports_extraction_errors_for_bad_run_metadata[non_utf8]` |
| M7 | `dataset`: `require_object=True` | killed | `test_non_object_run_metadata_is_a_named_extraction_error` (4 cases; at `a160969` also the since-merged duplicate `test_non_object_run_metadata_is_an_extraction_error`); `test_gate_reports_extraction_errors_for_bad_run_metadata[list]` |
| M8 | `_manifest`: `require_object=True` | killed | `test_non_object_manifest_top_level_is_a_value_error` (4 cases); `test_manifest_uses_the_shared_loader` |
| M9 | gate: revert to its own read with the default object check (faithful, below) | killed | `test_gate_manifest_errors_are_the_shared_readers[list]`, `[int]` |
| M9eq | gate: the same with `require_object=False` (faithful) | **survived: equivalent**, as D6 predicted | `build_dataset` raises `_manifest`'s message for `[]`/`5`, and the hardened loader labels the other payloads |
| M10 | `source_config_fields`: revert to `load_json_clear_error` + `.get` | killed | `…missing_required_key_is_a_value_error`; `…rejects_unparseable_manifests[list]`, `[empty_object]`; `…rejects_wrongly_shaped_config_lists` (all 3) |
| M11 | `read_units_sidecar`: revert to its old loader | killed | `test_read_units_sidecar_labels_every_content_failure` (all 6) |
| M12 | `_json_loader`: wrap `OSError` as `ValueError` | killed | `test_missing_file_is_file_not_found`; `test_directory_is_an_os_error_not_a_value_error`; `test_pod_run_metadata_directory_is_an_os_error`; `test_read_units_sidecar_directory_is_an_os_error` |
| M13 | `sidecar`: its own wrapper instead of the re-export | killed | `test_sidecar_name_is_the_shared_loader` |
| M14a | `_json_loader`: import a heavy module (`mosquito_cfd.benchmarks`; separately `pandas`) | killed | `test_json_module_imports_only_the_standard_library`; `test_json_alone_loads_nothing_heavy`; `test_stdlib_only_allow_list_is_exact` (the 2 accepted statements, by recursion); `test_manifest_module_imports_only_the_standard_library`; `test_manifest_alone_loads_nothing_heavy` (+ `test_manifest_read_loads_no_force_surrogate_stack` for `pandas`) |
| M14b | `_manifest`: the same | killed | `test_manifest_module_imports_only_the_standard_library`; `test_manifest_alone_loads_nothing_heavy` (+ `test_manifest_read_loads_no_force_surrogate_stack` for `pandas`) |
| M15a | `_json_loader`: `from None` on the UTF-8 branch | killed | `test_unparseable_file_is_a_labelled_value_error[non_utf8-*]` (`__cause__`); `test_undecodable_run_metadata_is_a_named_extraction_error`; `test_gate_reports_extraction_errors_for_bad_run_metadata[non_utf8]` |
| M15b | `_json_loader`: `from None` on the JSON branch | killed | `test_unparseable_file_is_a_labelled_value_error` (the 5 JSON cases × 2 modules) |
| M16 | `dataset`: `from exc` instead of `from exc.__cause__` | killed | `test_undecodable_run_metadata_is_a_named_extraction_error` (`__cause__` isinstance) |
| M17 | `dataset`: `{exc}` instead of `{exc.__cause__}` | killed | `test_undecodable_run_metadata_is_a_named_extraction_error` (exact message) |
| M18 | `dataset`: `isinstance(exc.__cause__, ValueError)` | killed | `test_unparseable_run_metadata_is_a_labelled_value_error[int_digit_limit]` |
| M19 | `read_units_sidecar`: `require_object=False` | killed | `test_read_units_sidecar_labels_every_content_failure[list]`, `[int]` |
| M20a | `run_acceptance_gate` provenance read: `require_object=False` | killed | `test_gate_rejects_unparseable_provenance[list]`, `[int]` |
| M20b | `record_check_result` provenance read: `require_object=False` | killed | `test_record_check_result_rejects_unparseable_provenance[list]`, `[int]` |
| M21a | `_assert_stdlib_only`: `any(name.startswith(a) for a in allowed)` | killed | `test_stdlib_only_allow_list_is_exact[import mosquito_cfd._json_loaderx]`, `[import mosquito_cfd._json_loader.sub]` |
| M21b | `_assert_stdlib_only`: `any(a.startswith(name) for a in allowed)` | killed | `test_stdlib_only_allow_list_is_exact[from mosquito_cfd import force_surrogate]`, `[from mosquito_cfd import _json_loader]`, `[import mosquito_cfd]` |

No mutant survived except the planned equivalent M9eq, so no killing tests were added.

## Corrections to the first run

The first `mutate.py` pass killed every mutant, but two kills did not test what they were meant to
test.

- **M9 / M9eq.**
  - The first version replaced the gate's read with
    `load_json_clear_error(...)["configs"]`, indexing at once. The pre-change gate indexed
    `manifest["configs"]` only *after* `build_dataset`. So the first M9eq was killed by a
    `TypeError` from indexing a list, not because it is distinguishable.
  - `mutate_extra.py` reverts faithfully: it reads into a variable, and indexes it just before
    the loops that use it.
  - M9 is still killed, by the `[]`/`5` guards. M9eq survives, which is the equivalence D6
    recorded.
- **M14.**
  - `import mosquito_cfd.force_surrogate` in `_json_loader` or `_manifest` is a circular import:
    `force_surrogate` → `dataset` → `_manifest` → `_json_loader`. The first run died at
    collection (exit 2), before any contract test ran.
  - Re-run with heavy modules that do not import back: `mosquito_cfd.benchmarks` and `pandas`.
    Both are in `_HEAVY`. The AST and fresh-interpreter tests kill each.

## E1 audit through the real loader (task 5.6)

```
$ PYTHONPATH=src .venv/Scripts/python.exe <scratchpad>/audit_loader.py .
loader: c:\repos\mosquito-cfd\.claude\worktrees\harden-json-loader\src\mosquito_cfd\_json_loader.py
checked 56 files: {'run_metadata': 46, 'sweep_manifest': 7, 'sweep_provenance': 3}; failures: 0
```

`audit_loader.py` calls `_json_loader.load_json_clear_error(path, label=kind)` with the default
object check on every file from `git ls-files '*.json'` whose basename contains `sweep_manifest`,
`sweep_provenance` or `run_metadata`.
