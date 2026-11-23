## ADDED Requirements

### Requirement: The generator reads the sweep manifest through the shared validated reader

`metadata_capture.source_config_fields` SHALL read the sweep manifest through
`mosquito_cfd._manifest.load_manifest_configs`, the same reader `build_dataset` and `FieldCorpus`
use (see the `force-surrogate` capability, "Sweep-manifest reading lives in a shared
standard-library-only module"). Every manifest that reader rejects SHALL raise its `ValueError`
before the config lookup. That covers:

- a file that is not valid UTF-8 or not valid JSON;
- a top level that is not an object, or a missing or non-list `configs`;
- a non-mapping config, a config missing one of the reader's required keys, or a duplicate config
  name.

A config absent from the manifest SHALL still raise `KeyError` naming the config and listing the
available names. A manifest entry missing `max_step` SHALL still raise `KeyError` naming
`max_step`; `max_step` is not one of the reader's required keys. Every committed sweep manifest
SHALL still be accepted.

#### Scenario: A config missing a required key is a ValueError

- **GIVEN** a sweep manifest whose only config has `name` and `max_step` and no other key
- **WHEN** `source_config_fields` is called for that config
- **THEN** it raises exactly `ValueError` naming the missing required keys, including
  `stroke_amp_deg`, and does not raise `KeyError`

#### Scenario: A missing max_step is still a KeyError

- **GIVEN** a sweep manifest whose only config has every key the reader requires, but no `max_step`
- **WHEN** `source_config_fields` is called for that config, with a deck that has every key it reads
- **THEN** it raises `KeyError` naming `max_step`

#### Scenario: An absent config is still a KeyError

- **GIVEN** the committed fixture sweep manifest
- **WHEN** `source_config_fields` is called for a config name it does not contain
- **THEN** it raises `KeyError` naming that config

#### Scenario: Unparseable and wrongly shaped manifests are ValueErrors

- **GIVEN** sweep manifests nested 100000 levels deep, holding a 5000-digit integer inside an
  object, of non-UTF-8 bytes, of `[]`, of `5`, and of `{}`
- **WHEN** `source_config_fields` reads each
- **THEN** each raises exactly `ValueError` naming the manifest path, never `RecursionError`,
  `AttributeError`, `TypeError` or `KeyError`
- **AND** the `[]` message is `manifest <path> top level is a list, not an object; not a sweep
  manifest`

#### Scenario: Wrongly shaped config lists are ValueErrors

- **GIVEN** sweep manifests of `{"configs": 5}`, of `{"configs": [5]}`, and with two otherwise
  valid configs sharing one name
- **WHEN** `source_config_fields` reads each
- **THEN** each raises exactly `ValueError` with the shared reader's message (`manifest 'configs'
  must be a list`, `manifest config 0 is not a mapping`, `duplicate config name`). These messages
  do not name the path; that is the shared reader's existing wording.

#### Scenario: Every committed sweep manifest is still accepted

- **GIVEN** each config of the committed sweep manifests under `examples/prelim_sweep`,
  `examples/prelim_sweep_fine` and `examples/prelim_sweep_fine_pilot`, with the deck its
  `input_file` names; and config `s35_f085_p45` of `tests/fixtures/run_metadata/sweep_manifest.json`
  with `tests/fixtures/run_metadata/inputs.3d.s35_f085_p45`
- **WHEN** `source_config_fields` is called for each
- **THEN** each returns the config's fields without raising

## MODIFIED Requirements

### Requirement: git commit is always recorded as a full 40-character SHA

The metadata generator SHALL source the git commit hash for its output from, in order of
precedence: (1) an explicit `--git-commit` override supplied by the caller, used verbatim after
validation and never consulting the pod's `git` block at all; otherwise (2) the pod-side
`run_metadata.json`'s `git.commit` field, verbatim (already a full SHA when present, produced by
`get_git_info()`). It SHALL NOT truncate, re-derive, or accept a hand-typed abbreviated hash as a
silent substitute in either path: an override that is not a full 40-character SHA SHALL be
rejected with a clear validation error, exactly as an invalid/missing pod-sourced value is today.

"Full 40-character SHA" SHALL mean that `mosquito_cfd._provenance.is_full_commit_sha(value)` is
true. That rule is defined in the `field-surrogate` capability, "Corpus snapshots carry run identity
and digest-pinned provenance". **BREAKING:** a trailing newline was accepted by the previous
`^…$` + `re.match` check and is now refused.

Each rejection of a `git` block, `git.commit` or `--git-commit` value SHALL be a `ValueError`
whatever the value's type, and its message SHALL contain the offending value's `repr`. An absent
key counts as `None` and reports as `None`. That covers:

- a `git` block that is absent, `null`, or not a JSON object (a list of `[key, value]` pairs
  included, which the old `dict(...)` coercion accepted);
- a `git.commit` or `--git-commit` value that is not a string.

A valid override SHALL be checked and returned before the pod's `git` block is read at all, so an
absent or `null` `git` block does not block it.

Loading a pod-side `run_metadata.json` whose top level is not a JSON object SHALL raise `ValueError`
naming the path (previously `AttributeError`). A missing file still raises `FileNotFoundError`.
Every other rejection of the file's contents SHALL also be exactly a `ValueError` labelled
`pod-side run_metadata.json <path>`: bytes that are not valid UTF-8, and JSON the parser refuses
with `ValueError` or `RecursionError` (nesting beyond the recursion limit, an integer beyond
Python's digit limit). See the `force-surrogate` capability, "Force-surrogate JSON files load
through one labelled loader".

#### Scenario: full SHA passes through unmodified when no override is supplied

- **GIVEN** a pod-side `run_metadata.json` with `git.commit` = a 40-character hex string, and no
  `--git-commit` override supplied
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is the identical 40-character string

#### Scenario: a truncated pod-sourced commit is rejected

- **GIVEN** a pod-side `run_metadata.json` whose `git.commit` is a truncated (e.g. 7-character)
  string, and no `--git-commit` override supplied
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error naming the offending value, rather than passing it
  through

#### Scenario: a pod-side git block with no commit key at all is rejected absent an override

- **GIVEN** a pod-side `run_metadata.json` whose `git` block is
  `{"error": "git not available or not a repository"}` (the exact shape produced when the pod
  image has no `.git` directory at all), and no `--git-commit` override supplied
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error, rather than raising an unrelated `KeyError` or
  silently producing output with a missing/empty `git.commit`

#### Scenario: a manual override bypasses the pod value entirely

- **GIVEN** a pod-side `run_metadata.json` whose `git` block has no valid `commit` (e.g. the
  missing-key shape above), and a caller-supplied `--git-commit` equal to a valid 40-character SHA
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is exactly the supplied override value, the output's `git`
  dict includes `"source": "cli-override"`, and the pod's own `git` block is never consulted (the
  generator does not raise even though that block has no valid commit)

#### Scenario: a malformed manual override is rejected

- **GIVEN** a caller-supplied `--git-commit` value that is not a full 40-character hex string
  (e.g. a truncated or non-hex value)
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error naming the offending override value, rather than
  passing it through or silently falling back to the pod's own value

#### Scenario: an uppercase or mixed-case override is rejected, matching existing validation

- **GIVEN** a caller-supplied `--git-commit` value that is 40 characters long but contains
  uppercase hex digits (e.g. all-uppercase)
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear validation error, identically to how an uppercase pod-sourced
  `git.commit` is rejected today — case is not folded or normalized for either path

#### Scenario: a manual override wins even when the pod's own commit is valid

- **GIVEN** a pod-side `run_metadata.json` whose `git.commit` is already a valid, different
  40-character SHA, and a caller-supplied `--git-commit` equal to a different valid 40-character
  SHA
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is exactly the supplied override value (not the pod's), and
  the output's `git` dict includes `"source": "cli-override"` — the override always takes
  precedence, whether or not the pod's own value happened to be valid

#### Scenario: a trailing newline is not a full SHA

- **GIVEN** a pod-side `git.commit` of `"a" * 40 + "\n"` with no override, and separately a
  `--git-commit` override of `"a" * 40 + "\n"`
- **WHEN** the generator attempts to assemble metadata
- **THEN** each raises exactly `ValueError` whose message contains `repr("a" * 40 + "\n")`, as for a
  truncated SHA

#### Scenario: a wrongly typed pod-side git block is a ValueError

- **GIVEN** pod metadata whose `git` is, in turn: absent, `null`, `["x"]`, `"abc"`,
  `[["commit", "a" * 40]]`, or `{"commit": 123}`
- **WHEN** `extract_git_info` (no override) processes each
- **THEN** each raises exactly `ValueError`, never `TypeError`, and the message contains the
  offending value's `repr`. The list of pairs is refused, not coerced to a dict.

#### Scenario: a wrongly typed override is a ValueError

- **GIVEN** a `--git-commit` override of `123`
- **WHEN** `resolve_git_info` processes it
- **THEN** it raises exactly `ValueError` whose message contains `123`

#### Scenario: a valid override never reads the pod's git block

- **GIVEN** pod metadata with `"git": null`, and separately pod metadata with no `git` key at all,
  each with a `--git-commit` override of `"b" * 40`
- **WHEN** `resolve_git_info` processes each
- **THEN** each returns `{"commit": "b" * 40, "source": "cli-override"}` without raising

#### Scenario: a pod-side file whose top level is not an object is a ValueError

- **GIVEN** pod-side `run_metadata.json` files holding `[]`, and holding `5`
- **WHEN** `load_pod_run_metadata` loads each
- **THEN** each raises exactly `ValueError` naming the path (never `AttributeError`); and a path that
  does not exist still raises `FileNotFoundError`

#### Scenario: an unparseable pod-side run_metadata.json is a labelled ValueError

- **GIVEN** a pod-side `run_metadata.json` nested 100000 levels deep, one holding a 5000-digit
  integer, and one of non-UTF-8 bytes
- **WHEN** `load_pod_run_metadata` reads each
- **THEN** each raises exactly `ValueError`. The first two messages begin
  `pod-side run_metadata.json <path> is not valid JSON: ` and the third begins
  `pod-side run_metadata.json <path> is not valid UTF-8: `.
