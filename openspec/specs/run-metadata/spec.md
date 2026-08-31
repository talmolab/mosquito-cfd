# run-metadata Specification

## Purpose
TBD - created by archiving change automate-run-metadata-capture. Update Purpose after archive.
## Requirements
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

The metadata generator SHALL source the git commit hash for its output from, in order of
precedence: (1) an explicit `--git-commit` override supplied by the caller, used verbatim after
validation and never consulting the pod's `git` block at all; otherwise (2) the pod-side
`run_metadata.json`'s `git.commit` field, verbatim (already a full SHA when present, produced by
`get_git_info()`). It SHALL NOT truncate, re-derive, or accept a hand-typed abbreviated hash as a
silent substitute in either path: an override that is not a full 40-character SHA SHALL be
rejected with a clear validation error, exactly as an invalid/missing pod-sourced value is today.

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

### Requirement: docker image identity is a single unambiguous, digest-validated field

The metadata generator SHALL record the docker image identity under one field, validated to match
the `sha256:[0-9a-f]{64}` digest format **exactly** (not a 64-character hex run embedded within a
longer hex sequence), and SHALL NOT split image identity across two inconsistent fields (a mutable
tag under one key and the digest under another).

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

#### Scenario: an overlong hex run is rejected, not truncated and accepted

- **GIVEN** a candidate digest of the form `sha256:` followed by 65 or more consecutive hex
  characters (one or more characters longer than a real SHA-256 digest)
- **WHEN** `validate_image_digest` checks it
- **THEN** it raises `ValueError` — the validator does not match only the first 64 characters of
  the hex run and silently accept the rest as valid

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

When a workflow's status contains more than one `Succeeded`, non-`Retry` candidate node (a
multi-config fan-out workflow, where several configs' pods share one Argo workflow), the
generator SHALL select the node belonging to the specific pod being processed — identified by the
pod's own name, sourced from that pod's `orchestration.pod` field (already recorded in its
`run_metadata.json`) — rather than an unfiltered global maximum across every node in the
workflow. Argo status node dict keys are the pod's own full name, so this selection SHALL be a
direct lookup by that key. If the pod name is available but no node with that key exists, or the
matched node is not itself a valid `Succeeded`, non-`Retry`, fully-timestamped candidate, the
generator SHALL raise a clear, actionable error rather than silently falling back to the
unfiltered global maximum — a silent fallback would reintroduce the exact cross-config
misattribution this scoped selection exists to prevent. When no pod name is available at all (a
single-config workflow, or pod-side metadata predating the `orchestration.pod` field), the
generator SHALL fall back to today's unfiltered global-maximum behavior unchanged.

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

#### Scenario: a multi-config fan-out workflow selects only the matching pod's node

- **GIVEN** a completed Argo workflow's status JSON containing three distinct `Succeeded`,
  non-`Retry` `Pod`-type nodes — one per config in a fan-out sweep — keyed by three distinct pod
  names with sequential, non-overlapping `startedAt`/`finishedAt` windows of roughly 1800s,
  3600s, and 9200s respectively (so the third pod has both the longest duration and the latest
  absolute `finishedAt` of the three), and a pod-side `run_metadata.json` whose
  `orchestration.pod` names the **second** pod (the ~3600s one) — neither the longest-duration
  nor the latest-finishing of the three
- **WHEN** the generator assembles that config's metadata
- **THEN** `timing.wall_time_s` is approximately `3600`, matching that specific pod's own
  duration, not the third pod's ~9200s duration despite the third pod finishing last across the
  whole workflow

#### Scenario: an unmatched pod name produces a clear error instead of a silent fallback

- **GIVEN** the same multi-config fan-out status JSON, and a pod name that does not match any
  node's key in `status.nodes` (e.g. a typo, or a node genuinely missing from the status)
- **WHEN** the generator attempts to compute `timing.wall_time_s` for that pod name
- **THEN** it raises a clear, actionable error naming the unmatched pod name, rather than
  silently falling back to the unfiltered global maximum across the other pods' nodes

#### Scenario: a matched pod node that is not itself a valid candidate produces a clear error

- **GIVEN** a workflow status where a node exists under the exact key named by a pod-side
  `run_metadata.json`'s `orchestration.pod`, but that node's `phase` is not `"Succeeded"`, or its
  `type` is `"Retry"`, or it is missing `startedAt`/`finishedAt`
- **WHEN** the generator attempts to compute `timing.wall_time_s` for that pod name
- **THEN** it raises a clear, actionable error naming the pod, rather than treating the mere
  existence of a matching key as sufficient

#### Scenario: no pod name available falls back to the unfiltered global maximum unchanged

- **GIVEN** pod-side `run_metadata.json` whose `orchestration` block has no `pod` field at all
  (metadata predating that field's introduction)
- **WHEN** the generator assembles that config's metadata against a workflow status
- **THEN** `timing.wall_time_s` is computed exactly as it was before pod-scoped selection existed
  — the unfiltered global maximum across all `Succeeded`, non-`Retry` candidate nodes — and no
  error is raised solely for the pod name's absence

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

### Requirement: get_git_info resolves Windows-created worktrees when read from a Linux git binary

`get_git_info()` SHALL correctly recover git provenance (`commit`, `branch`, `dirty`, `diff_hash`
if dirty, `repository`) when invoked against a git worktree whose `.git` pointer file names a
gitdir using a Windows drive-letter path (e.g. `gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo`)
even when the invoking `git` binary is a Linux binary that cannot parse that path as absolute
(e.g. `git` run from WSL against a Windows-created worktree). On the first git invocation
failing, it SHALL check whether `.git` at the target repo path is a file (not a directory) whose
content matches a Windows drive-letter gitdir pattern; if so, it SHALL translate that path to its
`/mnt/<lowercase-drive>/...` equivalent and retry the git invocation once with `GIT_DIR` and
`GIT_WORK_TREE` set accordingly (inheriting the rest of the caller's environment). It SHALL NOT
alter behavior, output, or subprocess call count for any case where the first invocation succeeds,
where `.git` is a real directory, or where `.git` is a worktree pointer using a POSIX-style path.
It SHALL NOT raise any exception under any of these conditions — including a nonexistent or
non-directory `repo_path`, or a `.git` pointer file containing non-UTF-8 byte content — returning
the same honest error dict in every unresolvable case instead.

#### Scenario: Windows-worktree gitdir is translated and retried successfully

- **GIVEN** a repo directory whose `.git` is a file containing
  `gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo`, and the initial `git rev-parse HEAD` call
  against that directory fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it retries with `GIT_DIR=/mnt/c/repos/mosquito-cfd/.git/worktrees/foo` and
  `GIT_WORK_TREE=<repo_path>` set (merged with the caller's inherited environment), and if that
  retry succeeds, returns the full git-info dict (`commit`, `branch`, `dirty`, `repository`) with
  no `error` key

#### Scenario: non-worktree failure is not retried

- **GIVEN** a directory with no `.git` at all (or a `.git` directory, not a pointer file), and the
  initial `git rev-parse HEAD` call fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it makes exactly one git invocation attempt (no retry) and returns
  `{"error": "git not available or not a repository"}`, identical to current behavior

#### Scenario: POSIX-style worktree pointer is not misinterpreted as a Windows path

- **GIVEN** a repo directory whose `.git` is a file containing a POSIX-style gitdir path (e.g.
  `gitdir: /home/user/repo/.git/worktrees/foo`), and the initial git invocation fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** no retry is attempted (the path does not match the Windows drive-letter pattern), and
  the existing `{"error": "git not available or not a repository"}` result is returned

#### Scenario: retry also fails, honest error is preserved

- **GIVEN** a repo directory whose `.git` is a file naming a Windows-style gitdir path, and both
  the initial invocation and the retry (with translated `GIT_DIR`/`GIT_WORK_TREE`) fail
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` — the same honest
  failure as today, with no fabricated or partial git-info fields

#### Scenario: common case (first attempt succeeds) is unaffected

- **GIVEN** a normal repo directory (or a worktree already resolvable in the current environment)
  where the initial `git rev-parse HEAD` call succeeds
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the same git-info dict it would have returned before this change, and the
  worktree-pointer-check/retry logic is never invoked

#### Scenario: no repo_path given resolves against the current working directory

- **GIVEN** the process's current working directory is itself a Windows-created worktree whose
  `.git` names a Windows drive-letter gitdir, and the initial git invocation — run with
  `cwd=repo_dir`, where `repo_dir` has resolved to `Path.cwd()` since no `repo_path` was given —
  fails
- **WHEN** `get_git_info()` is called with no argument (matching the real production call sites in
  `capture_run_metadata()` and `sweep.py`'s `_git_commit()`, neither of which pass `repo_path`)
- **THEN** the worktree-pointer check and retry are performed against that same resolved
  `repo_dir`, and on a successful retry the full git-info dict is returned exactly as it would be
  for an explicit `repo_path`

#### Scenario: pathological inputs degrade to the honest error, never an unhandled exception

- **GIVEN** any of: (a) a `repo_path` pointing at a directory that does not exist (or a file, not
  a directory), (b) a `.git` pointer file whose content is not valid UTF-8, (c) the process's
  current working directory having been deleted when no `repo_path` is given, or (d) a
  permission error while checking or reading the `.git` pointer file
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` without raising
  `NotADirectoryError`, `FileNotFoundError`, `UnicodeDecodeError`, `PermissionError`, or any other
  exception to the caller

### Requirement: get_git_info falls back to a build-time-baked commit when git itself is completely unavailable

`get_git_info()` SHALL, only after its existing direct git query and Windows-worktree retry (see
the WSL-worktree-resolution requirement below) have both failed, check for a `MOSQUITO_CFD_COMMIT`
environment variable. If that variable is present, is not the literal string `"unknown"`, and is a
full 40-character lowercase-hex SHA, it SHALL return
`{"commit": <value>, "source": "docker-image-build-arg"}` instead of the honest error dict — this
is the mechanism by which a pod-side container with no `.git` directory at all (baked with this
value at Docker build time) still yields git provenance. If the variable is absent, empty, exactly
`"unknown"` (the Dockerfile's default for an unparameterized local build), or present but not a
full 40-character lowercase-hex SHA (e.g. truncated, uppercase, or containing whitespace — a
misconfigured build pipeline), it SHALL fall through to the existing
`{"error": "git not available or not a repository"}` result unchanged, exactly as if no baked
value had been supplied at all — this function SHALL NOT return an unvalidated string as a
`commit` under any circumstance, matching the same format guarantee the CLI-override path applies
to a human-supplied commit. This fallback SHALL NOT be consulted, and SHALL NOT alter behavior or
output, for any case where the direct git query or the Windows-worktree retry already succeeds.

#### Scenario: baked commit is used when git is entirely unavailable

- **GIVEN** a repo directory with no `.git` at all, the initial `git rev-parse HEAD` call fails,
  and the `MOSQUITO_CFD_COMMIT` environment variable is set to a 40-character commit SHA
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"commit": <that SHA>, "source": "docker-image-build-arg"}` with no `error`
  key

#### Scenario: the "unknown" sentinel is treated as absent

- **GIVEN** the same no-`.git` setup, but `MOSQUITO_CFD_COMMIT` is set to the literal string
  `"unknown"` (the Dockerfile's default value for a `docker build` run without
  `--build-arg MOSQUITO_CFD_COMMIT=...`)
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}`, identical to today's
  behavior — it does not fabricate a commit from the sentinel value

#### Scenario: a malformed baked commit is treated as absent, not silently trusted

- **GIVEN** the same no-`.git` setup, but `MOSQUITO_CFD_COMMIT` is set to a value that is not a
  full 40-character lowercase-hex SHA — e.g. whitespace (`" "`), a truncated short SHA
  (`"abc1234"`), or an uppercase value — the kind of value a misconfigured build pipeline could
  produce
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` — the malformed value
  is never returned as a `commit`, and this holds for every caller of `get_git_info()`
  (including ones outside the `force_surrogate/metadata_capture.py` pipeline, such as
  `force_surrogate/sweep.py`'s `_git_commit()`, which applies no format validation of its own and
  would otherwise propagate an unvalidated value straight into a committed provenance file)

#### Scenario: a successful direct git query is never overridden by the baked commit

- **GIVEN** a normal repo directory where the initial `git rev-parse HEAD` call succeeds, and
  `MOSQUITO_CFD_COMMIT` also happens to be set in the environment to some other value
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the real git-derived info dict (the actual `git rev-parse` commit, plus
  `branch`/`dirty`/`repository`), and the `MOSQUITO_CFD_COMMIT` environment variable is never
  consulted

#### Scenario: a successful Windows-worktree retry is never overridden by the baked commit

- **GIVEN** a Windows-created worktree whose `.git` pointer file resolves successfully via the
  existing WSL-worktree retry, and `MOSQUITO_CFD_COMMIT` is also set in the environment
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the retry's real git-derived info dict, and the `MOSQUITO_CFD_COMMIT`
  environment variable is never consulted

#### Scenario: the direct git query is always attempted before the baked commit is consulted

- **GIVEN** no `.git` at all, so the direct git query is bound to fail, and `MOSQUITO_CFD_COMMIT`
  is set to a valid 40-character commit SHA
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** the direct `git rev-parse HEAD` invocation is attempted (and observably fails) before
  the baked-commit dict is returned — the fallback tier is never consulted first, only after the
  direct attempt (and the Windows-worktree retry, when applicable) has already failed

