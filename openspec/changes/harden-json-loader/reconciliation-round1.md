# Reconciliation: review round 1 (harden-json-loader)

Reviewers: Subagent 1 (spec, Sonnet), 2 (TDD, Opus), 4 (docs, Sonnet), 5 (git, Sonnet). Subagent 3
was skipped: no CI, Docker, dependency or packaging change. Subagent 6 was skipped: no numerics or
scientific claims.

Each BLOCKING and IMPORTANT finding is quoted verbatim (trimmed with "…"). "Where" gives the line
on which the reviewer's mechanism now appears. Line numbers are as of this revision.

## BLOCKING

**B1 (Subagent 1 M1, Subagent 2 B1, Subagent 4 B1; three reviewers independently).** "`_assert_stdlib_only` (`tests/test_light_corpus_helpers.py:69-93`) asserts that `name.split(".")[0] in sys.stdlib_module_names` … Task 2.2 and D2 make `_manifest.py` do `from mosquito_cfd._json import load_json_clear_error`, which fails that assertion … The live requirement … says `_manifest` 'imports only the standard library'. It will be false … Extend `_assert_stdlib_only(path, allowed=())` … so it accepts an import only if it is stdlib or listed in `allowed`, and recursively applies itself to each allowed module's file … Add a test that `_assert_stdlib_only` still rejects `from mosquito_cfd.force_surrogate import x` when only `mosquito_cfd._json` is allowed, so the allowlist is not a prefix match … Add a MODIFIED delta for that requirement … M14 … should also cover `_manifest`."

- **Addressed.**
  - The helper gains an exact-name `allowed`, and recurses into each allowed module.
  - An allow-list self-test rejects `mosquito_cfd.force_surrogate` and the prefix-lookalike
    `mosquito_cfd._jsonx`.
  - `_manifest`'s test passes `allowed=("mosquito_cfd._json",)`.
  - A MODIFIED delta rewrites the live requirement's import contract and adds a scenario.
  - M14 covers `_manifest` too, and M21 mutates the helper to a prefix match.
- **Where:**
  - `design.md:108` (the `_assert_stdlib_only(path, allowed=())` rule);
  - `tasks.md:83-86` (the helper change and `test_stdlib_only_allow_list_is_exact`);
  - `tasks.md:157` (`allowed=("mosquito_cfd._json",)`);
  - `specs/force-surrogate/spec.md:183` (MODIFIED sentence) and `:249` (new scenario);
  - `proposal.md:78` (Impact);
  - `design.md:248` (M21) and the M14 row.

**B2 (Subagent 1 M2).** "The run-metadata ADDED scenario 'Unparseable and wrongly shaped manifests are ValueErrors' is false for one payload … `{"configs": 5}` … `_manifest._validate_configs` … raises `manifest 'configs' must be a list, got int` with no path … Drop `{"configs": 5}` from the 'naming the path' sentence."

- **Addressed.** `{"configs": 5}` moves to a new scenario. That scenario names the shared reader's
  messages and says they carry no path; so do `{"configs": [5]}` and the duplicate-name case. The
  "naming the path" scenario keeps only payloads whose messages do name it.
- **Where:**
  - `specs/run-metadata/spec.md:50-57` (the scenario "Wrongly shaped config lists are ValueErrors":
    "These messages do not name the path");
  - `tasks.md:189-192` (`test_source_config_fields_rejects_wrongly_shaped_config_lists`).

## IMPORTANT

**I1 (Subagent 2 I1).** "Task 4.1's stated reds are partly wrong … 5 of the 7 cases [already green after task 1] … `{"configs": 5}` is not 'an AttributeError from .get'. It is `TypeError: 'int' object is not iterable` … For `[]`, pin the exact `_manifest` message … State that the duplicate case uses the valid fixture `_DECK`."

- **Addressed.**
  - `[]` pins `_manifest`'s exact message, so it is a genuine red.
  - Nesting, digit limit, UTF-8 and `5` are labelled guards.
  - `{"configs": 5}` is recorded as a `TypeError`, and `{"configs": [5]}` as an `AttributeError`.
  - The duplicate case uses `_DECK`.
- **Where:** `tasks.md:182-192`.

**I2 (Subagent 2 I2).** "Task 1 ships a known regression that task 3 undoes … At c898b24 a `[]` manifest at the gate already raises `_manifest`'s message … Task 1 turns on the default object check in the gate's own read … move `test_gate_manifest_errors_are_the_shared_readers` into 1.1 as a guard … Then do the D6 routing in task 1, or merge task 3 into task 1."

- **Addressed.** The D6 routing is now part of task 1, and the test is a 1.1 guard over the five
  payloads. The old task 3 is gone.
- **Where:**
  - `design.md:163` (D6 heading: "in the same commit as D1"), and the rationale at `:166-171`;
  - `tasks.md:98-102`;
  - the task 1 heading.

**I3 (Subagent 2 I3).** "Several mutants are missing for guards this change adds. M15: `_json` replaces `from exc` with `from None` … M16: `dataset` uses `from exc` instead of `from exc.__cause__` … M17: `dataset` interpolates `{exc}` instead of `{exc.__cause__}` … M18: `dataset` widens the check to `isinstance(exc.__cause__, ValueError)` … M19: `read_units_sidecar` passes `require_object=False` … M20: the gate's or `record_check_result`'s provenance read passes `require_object=False`."

- **Addressed.** All six are added exactly as worded, each with its killer.
- **Where:** `design.md:242-247` (M15–M20).

**I4 (Subagent 2 I4).** "M9 is ambiguous and one reading is an equivalent mutant … Specify M9 as 'revert to the default `require_object=True` read' … the gate's own run_metadata object check is unreachable … Either label it defence-in-depth in the spec or drop it."

- **Addressed.**
  - M9 is the default-object-check read, and the `require_object=False` variant is recorded as
    equivalent.
  - The spec labels the gate's own run_metadata check as defence in depth.
- **Where:**
  - `design.md:236` (M9) and `:173-174` (equivalent);
  - `design.md:181`;
  - `specs/force-surrogate/spec.md:92`.

**I5 (Subagent 2 I5).** "The per-task green lists miss affected test files … 0.2 … omits the new `tests/test_json_loader.py` … `test_field_surrogate_corpus.py`, `test_force_surrogate_driver.py`, `test_force_surrogate_runner.py` and `test_force_surrogate_run_sweep_driver.py` … `test_generate_run_metadata_cli.py` … `test_force_surrogate_sweep.py`."

- **Addressed.** All the named files are in the 0.3 list. Every green step runs that list plus
  `tests/test_json_loader.py`.
- **Where:** `tasks.md:32-46`.

**I6 (Subagent 2 I6).** "'Callers see labelled ValueErrors' requires all five payloads for each caller. Missing: gate sweep manifest with `5` … units sidecar with `5` … Add `{}` and `{"configs": [5]}` to `test_source_config_fields_rejects_unparseable_manifests` … 'Every committed sweep manifest SHALL still be accepted' through `source_config_fields`: 7.3 checks only `load_manifest_configs`. Also run `source_config_fields` on one config of each of the four real manifests."

- **Addressed.**
  - `5` is added to the gate-manifest guard and to the units test.
  - `{}` and `{"configs": [5]}` are added to the `source_config_fields` tests.
  - A guard calls `source_config_fields` on **every** config of the three `examples/` manifests
    (57 calls) and on the fixture config. That goes beyond "one config each", because every config
    already passes (design E4). The fixture manifest's decks are not committed at their
    `input_file` paths, so its config uses `_DECK`.
  - A spec scenario covers the committed-manifest case.
- **Where:**
  - `tasks.md:98`, `:212`, `:182`, `:191`, `:193-195`;
  - `specs/run-metadata/spec.md:59-65`.

**I7 (Subagent 4 I1).** "CHANGELOG plan (8.2) does not match the file's conventions … One change is written as one bullet. It carries the OpenSpec slug in parentheses and the issue at the end … `**BREAKING (minor):**` is used inline on sub-bullets … Task 8.2 should also say that `docs/CHANGELOG.md` line 52 … is a historical release note … do not edit it."

- **Addressed.** One `### Changed` bullet with the slug, sub-bullets, inline
  `**BREAKING (minor):**` sub-bullets, the issue reference at the end, and an instruction not to
  edit the historical line.
- **Where:** `tasks.md:258-269`.

**I8 (Subagent 4 I2).** "Stale text and docstrings the change creates, which the proposal does not list … `_manifest.py:1-14` … `import json` at line 17 is likely unused and ruff F401 will flag it … `sidecar.py:1-8` … rationale in `load_json_clear_error`'s own docstring … should move into `_json`'s docstring … `read_units_sidecar` `Raises:` … `ConfigExtractionError` docstring … should now name nesting and the digit limit … `_verify_deck_sha256` docstring should mention the `__cause__` hand-off … `run_acceptance_gate` docstring … has no `Raises:` section … Task 4.2 should be explicit that the `Raises:` line becomes KeyError for an absent config or `max_step`, and ValueError for everything the reader rejects."

- **Addressed.** Each docstring edit now sits in the green step of the task that makes it stale,
  with its content stated.
- **Where:**
  - `tasks.md:129-132` (`_json` docstring with the moved rationale);
  - `tasks.md:134-137` (`run_acceptance_gate` `Raises:`);
  - `tasks.md:138-139` (`dataset`, `ConfigExtractionError`);
  - `tasks.md:165-167` (unused `import json`; `_manifest` module docstring);
  - `tasks.md:200-201` (`source_config_fields` `Raises:`);
  - `tasks.md:219-220` (`read_units_sidecar` `Raises:`);
  - `design.md:148` (D4 Docstrings);
  - `design.md` D1 "Re-export" bullet.

  The live "Dimensionless units sidecar" scenario only requires a `ValueError`, so it stays true.
  The new requirement states the messages. A MODIFIED delta just to add a cross-reference was not
  added: SUGGESTION-level, and it would mean copying a whole requirement for one line.

**I9 (Subagent 4 I3).** "DRY violations: the message catalogue is restated about five times … The spec delta is the single source for the message contract … The 'five payloads' are defined in [three places] … Define them once … The BREAKING list is stated three times … Keep it in the proposal and have the CHANGELOG task reference it. Mutation M1-M14 is restated in `tasks.md` 7.2 and `design.md`. Tasks should only point to design."

- **Addressed.**
  - **Messages:** the message templates are gone from `proposal.md` and `design.md` D1, which
    point to the spec.
  - **Payloads:** defined in the spec scenario and `tests/_json_payloads.py`. Tasks refer to "the
    five payloads".
  - **BREAKING list:** lives in `proposal.md`. `tasks.md` 8.1 references it.
  - **Mutations:** listed only in `design.md`. `tasks.md` 5.5 points there.
- **Where:**
  - `proposal.md` "What Changes", first bullet ("the messages are specified once, in the
    `force-surrogate` delta");
  - `design.md` D1 "Messages" bullet;
  - `tasks.md:11-16`, `:235`, `:258-266`.

  Payload byte strings are still spelled out in each spec scenario, because Subagent 1 M3 asks
  that scenarios read independently.

**I10 (Subagent 5 IMPORTANT-1).** "No commit step for the OpenSpec proposal files … Commit the proposal first, as its own commit: `docs(openspec): propose harden-json-loader (advances #175)` … Review rounds that edit design.md will need follow-up commits; say so."

- **Addressed.**
- **Where:** `tasks.md:27-29` (task 0.1).

**I11 (Subagent 5 IMPORTANT-2).** "Tasks 6 and 7 produce files with no commit slot, but CHANGELOG must be last … Add one commit between task 5 and the merge: `docs(openspec): mutation results and reconciliation for harden-json-loader (advances #175)` … If 7.2 finds a surviving mutant and a killing test is added, that test is a task-style red/green commit of its own."

- **Addressed.**
- **Where:** `tasks.md:246-247` (task 6.1), `:235-237` (a surviving mutant gets its own red →
  green commit), and `:254` (re-run mutants after a code-changing merge).

**I12 (Subagent 5 IMPORTANT-3).** "The proposal's overlap note omits the `docs/CHANGELOG.md` collision with `fix-stale-spec-claims` … SUGGESTION: prefer inserting our new gate tests next to the existing `run_acceptance_gate` tests."

- **Addressed.** The proposal names the CHANGELOG collision and its mitigation. New caller tests go
  next to related tests, not at the end of the file.
- **Where:** `proposal.md:97-100`; `tasks.md` header ("New caller tests go next to the existing
  tests"); `design.md` Risks.

**I13 (Subagent 5 IMPORTANT-4, and Subagent 5 §2 IMPORTANT).** "the commit body must distinguish 'red' tests from 'guard, green before' tests … Say it for task 1 and task 3 too … Task 8.2's CHANGELOG commit message is not specified; define it: `docs(changelog): harden-json-loader entries (advances #175)` … the PR title must not contain a closing keyword either."

- **Addressed.**
  - Every test in every task is labelled **Red** or **Guard**, and the commit body has those two
    headings.
  - The CHANGELOG commit message is specified.
  - 9.2 covers the PR title.
- **Where:** `tasks.md:3-6`, the task 8 commit line, and task 9.2.

## SUGGESTIONS adopted

- **Subagent 2 S1.** `JSONDecodeError` and `UnicodeDecodeError` texts are derived at run time.
  Where: `tasks.md:73`, and the tightened `test_undecodable…` in task 1.1.
- **S2.** `tests/_json_payloads.py` asserts `0 < sys.get_int_max_str_digits() < 5000`. Where:
  `tasks.md:14`; `design.md:214`.
- **S3.** The loader tests are parametrized over `_json` and `sidecar`, so they are red for the
  real reason. Where: `tasks.md:67-70`.
- **S4.** `record_check_result` leaves the provenance bytes unchanged. Where: `tasks.md:93`;
  `specs/force-surrogate/spec.md:94`.
- **S5 and Subagent 1 M4 (BOM, empty file).** Both are in the loader scenario and tests. Strict
  `utf-8` is stated. Where: `specs/force-surrogate/spec.md:52`; `tasks.md:66`.
- **Subagent 1 M4 (`NoneType`).** Python type names are pinned. Where:
  `specs/force-surrogate/spec.md:24` and `:67`.
- **S6.** Happy path, and `str` or `Path` input. Where: `tasks.md:78`; the spec scenario "A valid
  object is returned unchanged, from a str or a Path".
- **S7.** Caller-level directory tests for `load_pod_run_metadata` and `read_units_sidecar`. Where:
  `tasks.md:116`, `:217`; the spec scenario "Opening errors are not wrapped by callers".
- **S10.** Task 5.3 is CI's exact pytest command, 5.2 greps for a stale `except UnicodeDecodeError`,
  and 5.6 records the audit. 9.2 checks ubuntu CI.
- **Subagent 1 M3.** The callers scenario restates its payloads inline.
- **Subagent 1 N2.** A gate scenario covers nested or huge run_metadata. Where:
  `specs/force-surrogate/spec.md:142`.
- **Subagent 1 N4.** The large requirement is split into three: the loader, its callers, and the
  three loaders. Where: `specs/force-surrogate/spec.md:83` and `:163`.
- **Subagent 1 N5.** Why is now 3 sentences, and the table moved to What Changes.
- **Subagent 1 N6.** `mutation-results.md` is listed in Impact.
- **Subagent 4 SUGGESTION.** The duplicated Context and Overlap text is trimmed: the design
  Context is cut, and Overlap lives in the proposal while the design keeps only the risk.

## Not adopted

- **Subagent 5's PR split ({1, 2} versus {3, 4, 5}).** The reviewer itself does not recommend it.
  One PR.
- **Subagent 2 S8** (the monkeypatch test fixes the import form). Accepted as stated, and noted in
  `tasks.md` 2.1.
- **Subagent 2 S9** (labels with format characters). No test needed, as the reviewer says.
