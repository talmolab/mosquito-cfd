## ADDED Requirements

### Requirement: final_time and timesteps are derived from the committed force CSV, never the deck's stop_time

The metadata generator SHALL read the committed force CSV's actual last data row and use its
`time` value for `timing.final_time`, and its row count for `timing.timesteps`. It SHALL NOT use
the deck's `stop_time`/`ns.stop_time` value for `final_time` under any circumstance, since
IB-particle CSVs systematically end exactly one `dt` short of `stop_time` (a pre-existing writer
convention, not a divergence signal).

#### Scenario: CSV ends one dt short of stop_time

- **GIVEN** a config's committed force CSV whose last row has `iStep=4705, time=2.3525` and a
  deck with `stop_time=2.352941176`
- **WHEN** the generator assembles `run_metadata_<config>.json`
- **THEN** `timing.final_time` is `2.3525` (the CSV's last row) and `timing.timesteps` is `4706`
  (the row count), and neither value equals the deck's `stop_time`

### Requirement: git commit is always recorded as a full 40-character SHA

The metadata generator SHALL source the git commit hash verbatim from the pod-side
`run_metadata.json`'s `git.commit` field (already a full SHA, produced by `get_git_info`) and
SHALL NOT truncate, re-derive, or accept a hand-typed abbreviated hash as a substitute.

#### Scenario: full SHA passes through unmodified

- **GIVEN** a pod-side `run_metadata.json` with `git.commit` = a 40-character hex string
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output's `git.commit` is the identical 40-character string, and a generator run
  given a truncated (e.g. 7-character) commit string in its input raises a clear validation error
  rather than passing it through

### Requirement: docker image identity is a single unambiguous, digest-validated field

The metadata generator SHALL record the docker image identity under one field, validated to match
the `sha256:[0-9a-f]{64}` digest format, and SHALL NOT split image identity across two
inconsistent fields (a mutable tag under one key and the digest under another).

#### Scenario: digest-only image identity

- **GIVEN** a pod-side `run_metadata.json` with a validated `sha256:...` docker image digest
- **WHEN** the generator assembles the committed metadata file
- **THEN** exactly one field, named `docker_image`, carries the image identity, its value matches
  the digest regex, and no separate mutable-tag field is present

#### Scenario: malformed digest is rejected

- **GIVEN** a pod-side `run_metadata.json` whose docker image field does not match
  `sha256:[0-9a-f]{64}` (e.g. a bare tag like `ghcr.io/talmolab/mosquito-cfd:fp64`, or a
  truncated/malformed digest)
- **WHEN** the generator attempts to assemble metadata from it
- **THEN** it raises a clear validation error naming the offending value, rather than passing the
  invalid identity through to the committed output

### Requirement: run context is structured, not free-text narrative, except for one optional notes field

The metadata generator SHALL derive `stability`, `arena_max_mib`, `node`, and `gpu_model` as
independent structured fields rather than composing a free-text narrative paragraph. `stability`
SHALL be derived solely from the config's manifest-sourced `fixed_dt` value (see the
kinematics/grid requirement below) compared against the sweep's nominal `fixed_dt` — not from any
separately hand-set flag. An optional `notes` field MAY be present for exceptional human
commentary but SHALL NOT be required for a normal run, and the generator SHALL produce a complete,
valid metadata file when `notes` is omitted.

#### Scenario: Arena max parsed from run.log

- **GIVEN** a `run.log` containing an AMReX end-of-run report with a "The Arena" max-used line
  reporting `7998 MiB`
- **WHEN** the generator assembles the committed metadata file
- **THEN** `arena_max_mib` is `7998`, and no free-text field is required to convey this figure

#### Scenario: stability derived from fixed_dt alone

- **GIVEN** a config whose manifest-sourced `fixed_dt` equals the sweep's nominal `5e-4`, and a
  second config whose manifest-sourced `fixed_dt` is `2.5e-4` (the documented CFL fallback value)
- **WHEN** the generator assembles metadata for each
- **THEN** the first config's `stability` is `"stable_at_5e-4"` and the second's is
  `"stable_at_2.5e-4_fallback"`, with no separate `dt_reduced`-style input read or required

#### Scenario: notes omitted on a normal run

- **GIVEN** a run with no exceptional circumstances to document
- **WHEN** the generator assembles the committed metadata file without a `--notes` argument
- **THEN** the output is complete and valid with no `notes` key present (not an empty string)

### Requirement: pod-reported run status must be completed

The metadata generator SHALL refuse to assemble metadata when the pod-side `run_metadata.json`'s
reported `status` is not `"completed"`, rather than silently assembling a normalized file for a
failed or incomplete run.

#### Scenario: non-completed status is rejected

- **GIVEN** a pod-side `run_metadata.json` whose `status` field is `"failed"` (or any value other
  than `"completed"`)
- **WHEN** the generator attempts to assemble metadata for that config
- **THEN** it raises a clear error naming the offending status value, rather than producing a
  normalized `run_metadata_<config>.json` for a run that did not actually complete

### Requirement: deck identity is cross-validated against the pod's recorded hash and persisted in the output

The metadata generator SHALL compute a SHA256 hash of the `--deck` file actually supplied and
require it to match the pod-side `run_metadata.json`'s recorded `deck_sha256`, refusing to
assemble metadata on a mismatch or on a missing `deck_sha256`. The verified hash SHALL be
persisted in the assembled output (as `deck_sha256`) so deck identity remains auditable after the
pod-side artifacts (which are not committed) are cleaned up.

#### Scenario: mismatched deck is rejected

- **GIVEN** a `--deck` file whose SHA256 hash does not match the pod-side `run_metadata.json`'s
  recorded `deck_sha256`
- **WHEN** the generator attempts to assemble metadata
- **THEN** it raises a clear error naming both the computed and pod-recorded hashes, rather than
  silently trusting the supplied `--deck` file

#### Scenario: verified deck hash is persisted in the output

- **GIVEN** a `--deck` file whose hash matches the pod-recorded `deck_sha256`
- **WHEN** the generator assembles the committed metadata file
- **THEN** the output includes a `deck_sha256` field with the verified hash, so which exact deck
  produced this file remains auditable even after the pod-side (uncommitted) artifacts are gone

### Requirement: kinematics, grid, fixed_dt, and max_step are sourced from the sweep manifest or deck

The metadata generator SHALL read `stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg`,
`reynolds`, grid resolution, `fixed_dt`, and `max_step` from the committed `sweep_manifest.json`
or the generated deck file for the given config, rather than accepting them as freeform CLI input
or requiring a human to re-type them.

#### Scenario: kinematics, grid, and timestep fields match the manifest entry

- **GIVEN** a config present in `sweep_manifest.json` with a specific `stroke_amp_deg`,
  `frequency_fstar`, `pitch_amp_deg`, `reynolds`, grid resolution, `fixed_dt`, and `max_step`
- **WHEN** the generator assembles metadata for that config
- **THEN** the output's `kinematics` block, `grid`, `fixed_dt`, and `max_step` fields all match the
  manifest entry's values exactly, with no CLI flag available to override any of them

### Requirement: wall-clock timing is computed from a completed Argo workflow's persisted status, with a manual override for garbage-collected workflows

The metadata generator SHALL compute `timing.wall_time_s` from a completed Argo workflow's
persisted start/finish timestamps, retrieved via a read-only status query (e.g. `argo get
<workflow-name> -o json`) given a workflow name supplied by the caller, reflecting only the
final successful attempt's duration (not any earlier retried/failed attempt). It SHALL NOT require
any modification to `run_one_config.py`, the Argo WorkflowTemplate, or any live `pods/exec` access.
Since completed Argo workflow objects may be garbage-collected before this tool is run, the
generator SHALL accept an optional `--wall-time-s` override that, when supplied, is used instead
of querying Argo at all.

#### Scenario: wall time from workflow status timestamps

- **GIVEN** a completed Argo workflow's status JSON with a `startedAt` and `finishedAt` timestamp
  for the relevant node
- **WHEN** the generator is invoked with that workflow's name
- **THEN** `timing.wall_time_s` equals the difference between `finishedAt` and `startedAt` in
  seconds, and no pod-level code change was required to produce it

#### Scenario: wall time reflects only the final successful attempt after a retry

- **GIVEN** a completed Argo workflow's status JSON showing one failed attempt followed by a
  successful retry, each with its own `startedAt`/`finishedAt`
- **WHEN** the generator computes `timing.wall_time_s`
- **THEN** it uses only the successful attempt's duration, not the sum including the failed
  attempt

#### Scenario: manual override bypasses the Argo query entirely

- **GIVEN** the source workflow has already been garbage-collected from the cluster
- **WHEN** the generator is invoked with `--wall-time-s 7032.46` instead of relying on a live Argo
  query
- **THEN** `timing.wall_time_s` is `7032.46` and no Argo query is attempted

#### Scenario: missing timestamps in an otherwise-successful query produce a clear error

- **GIVEN** an Argo status response that parses successfully but omits `startedAt` or
  `finishedAt` for the relevant node
- **WHEN** no `--wall-time-s` override is supplied
- **THEN** the generator raises a clear, actionable error rather than computing a nonsensical or
  `None` duration

### Requirement: pod-reported row count is cross-validated against the CSV

The metadata generator SHALL compare the pod-side `run_metadata.json`'s own reported row/step
count against the force CSV's independently-derived `timing.timesteps` (see the final_time
requirement above), and SHALL raise a clear error naming both values when they disagree, rather
than silently preferring one or producing a valid-looking output with an unresolved discrepancy.

#### Scenario: pod-reported row count disagrees with the CSV

- **GIVEN** a pod-side `run_metadata.json` reporting `rows=4700` and a force CSV whose last row
  gives `timesteps=4706`
- **WHEN** the generator attempts to assemble metadata for that config
- **THEN** it raises a clear error naming both the pod-reported and CSV-derived counts, rather than
  producing output that silently picks one

### Requirement: the generator is testable without live cluster or Argo access

The metadata generator SHALL be exercised by tests using fixture files and a fake/injected Argo
status response — covering CSV last-row parsing, `run.log` Arena-max parsing, manifest sourcing,
and schema assembly — with no live cluster, Argo, or RunAI dependency required to run the test
suite.

#### Scenario: fixture-driven reproduction of a known-correct pilot config

- **GIVEN** fixture copies of a pilot config's pod-side `run_metadata.json`, `run.log`, force CSV,
  manifest entry, and a canned Argo status response
- **WHEN** the generator is run against these fixtures in a test
- **THEN** the output's `final_time`, `git.commit`, and `kinematics` values match the
  already-committed, already-corrected `run_metadata_<config>.json` for that pilot config, and the
  test requires no network, cluster, or live Argo/kubectl call
