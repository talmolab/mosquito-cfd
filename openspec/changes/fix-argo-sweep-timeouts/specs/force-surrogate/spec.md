## ADDED Requirements

### Requirement: Argo sweep-submission deadline is overridable without mutating the committed workflow

`cluster/argo/scripts/submit_workflow.sh`'s `full` command SHALL accept an optional
`--active-deadline-seconds` flag that overrides the submitted workflow's `activeDeadlineSeconds`
without editing the checked-in workflow file — mirroring the existing `--parallelism` requirement
("Argo sweep-submission parallelism is overridable without mutating the committed workflow"),
which this requirement is additive to and independent of. Since the committed
`activeDeadlineSeconds: 86400` (24h) was implicitly sized for the committed default
`parallelism: 3`, overriding `--parallelism` alone without a matching deadline change can silently
doom a submission to a deadline-kill before completion (the failure mode observed in
`force-surrogate-sweep-7wrk7`, 0/27 configs completed at `parallelism=1`). When the flag is
supplied, the script SHALL apply the override by submitting an anchored, self-verifying
`sed`-patched temporary copy of the workflow file — the same mechanism as `--parallelism`, and
when both flags are supplied together, both patches SHALL land on the same temporary copy. When
the flag is **omitted** and `--parallelism` is also omitted, the script SHALL submit the
committed workflow file unpatched.

#### Scenario: `--active-deadline-seconds` overrides the deadline without touching the committed file

- **Given** `cluster/argo/scripts/submit_workflow.sh full --active-deadline-seconds 172800` (no
  `--parallelism`)
- **When** the command runs
- **Then** the sed-patched temporary copy passed to `argo submit` has
  `activeDeadlineSeconds: 172800` and an unchanged `parallelism:` line (the committed default),
  and `cluster/argo/workflows/force-surrogate-sweep.yaml` on disk is byte-identical (same
  `sha256`) before and after the command runs

#### Scenario: `--parallelism` and `--active-deadline-seconds` compose onto one temporary copy

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1
  --active-deadline-seconds 200000`
- **When** the command runs
- **Then** the single sed-patched temporary copy passed to `argo submit` has **both**
  `parallelism: 1` and `activeDeadlineSeconds: 200000` set correctly, and the committed workflow
  file is unchanged on disk

#### Scenario: Omitting both flags remains a true no-op

- **Given** `cluster/argo/scripts/submit_workflow.sh full` invoked with neither `--parallelism`
  nor `--active-deadline-seconds`
- **When** the command runs
- **Then** the committed `force-surrogate-sweep.yaml` is passed to `argo submit` unpatched — no
  temporary file is created at all

#### Scenario: An invalid `--active-deadline-seconds` value is rejected before any file is touched

- **Given** `cluster/argo/scripts/submit_workflow.sh full --active-deadline-seconds 0` (or a
  negative or non-integer value)
- **When** the command runs
- **Then** it fails fast with a clear error before creating any temporary file or invoking `argo
  submit`, and the committed workflow file is untouched

#### Scenario: A failed deadline substitution is never silently submitted

- **Given** the workflow file's top-level `activeDeadlineSeconds: <N>` line is missing or does not
  match the expected anchored pattern
- **When** `--active-deadline-seconds` is supplied
- **Then** the script fails with a clear error rather than submitting an unpatched or
  partially-patched temporary copy

#### Scenario: Help text documents the flag and the coupling risk

- **Given** `cluster/argo/scripts/submit_workflow.sh help`
- **When** the command runs
- **Then** its output documents `--active-deadline-seconds`, and separately documents the
  coupling risk that overriding `--parallelism` without a matching deadline change can silently
  doom a submission to a deadline-kill — not just the flag's existence in isolation

### Requirement: An overridden parallelism without an explicit deadline auto-scales the deadline instead of silently reusing a stale default

`cluster/argo/scripts/submit_workflow.sh full` SHALL compute a replacement `activeDeadlineSeconds`
instead of leaving the committed 24h value unpatched whenever `--parallelism` is overridden and
`--active-deadline-seconds` is **not** explicitly given. The computed value
SHALL be derived from the actual config count in the resolved `--corpus-dir`'s
`sweep_manifest.json` (not a hardcoded constant), a documented per-config-hours estimate, the
given parallelism, and a fixed retry margin, rounded up to a whole hour. An explicitly-supplied
`--active-deadline-seconds` SHALL always take precedence over the auto-computed value, and no
auto-scale computation SHALL be attempted when an explicit value is given.

#### Scenario: Overriding parallelism alone auto-scales the deadline

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares exactly 3 configs (the real
  `{"configs": [...]}` schema), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** the sed-patched temporary copy's `activeDeadlineSeconds` equals
  `ceil(3 * 2.4 / 1 + 4) * 3600 = 43200` seconds — not the committed default, and not a value
  independent of the actual manifest's config count. More generally, for any config count and
  parallelism, the computed value equals `ceil(config_count * 2.4 / parallelism + 4) * 3600`

#### Scenario: An explicit deadline is never overridden by auto-scale

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1
  --active-deadline-seconds 999999 --no-provision` with a `--corpus-dir` whose manifest is
  missing or otherwise unreadable
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` in the patched copy — the
  auto-scale computation is never attempted, so an unreadable manifest under this combination of
  flags does not cause a failure

#### Scenario: Auto-scale falls back to a working Python interpreter

- **Given** a `full` invocation where auto-scale is eligible to fire, and `python3` resolves on
  `PATH` but is non-functional (e.g. a Windows App-Execution-Alias stub), while `python` on
  `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** auto-scale succeeds by falling back to `python` — the script probes each candidate
  by actually invoking it, not merely checking that `PATH` resolution succeeds, and the broken
  `python3` is never used for the real computation

#### Scenario: Auto-scale fails clearly when no working interpreter is found at all

- **Given** a `full` invocation where auto-scale is eligible to fire, and neither `python3` nor
  `python` on `PATH` is a genuinely working interpreter
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter error

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest is unreadable

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` that exists but has no `sweep_manifest.json`, and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear, `die`-style error message before invoking `argo submit`,
  not an uncaught interpreter traceback

#### Scenario: Auto-scale fails clearly, not with a raw crash, when the manifest exists but is malformed

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 2 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` exists but is malformed (invalid JSON, missing the
  `"configs"` key, or `"configs"` present but not a list), and no `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error message before invoking `argo submit`, not an
  uncaught interpreter traceback and not a silently wrong deadline computed from a misread value

#### Scenario: Auto-scale refuses to fire when `--corpus-dir` and `--workspace-hostpath` name different corpora

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` and `--workspace-hostpath` whose basenames do not match, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** it fails fast with a clear error before invoking `argo submit` — `--no-provision`
  skips `provision()`'s own basename-match guard, so auto-scale (which reads `--corpus-dir`'s
  manifest independently of `--workspace-hostpath`) must not silently compute a deadline from
  the wrong corpus's config count

#### Scenario: An explicit deadline never triggers the basename-consistency check

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --active-deadline-
  seconds 999999 --no-provision` with a `--corpus-dir` and `--workspace-hostpath` whose
  basenames do not match
- **When** the command runs
- **Then** the command succeeds with `activeDeadlineSeconds: 999999` — the basename-consistency
  check is scoped to the auto-scale trigger path only, and an explicit `--active-deadline-
  seconds` never enters that path

#### Scenario: An invalid `--parallelism` is rejected before auto-scale is ever attempted

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (or `-1` or `abc`),
  no `--active-deadline-seconds`, and a `--corpus-dir` whose manifest exists and is readable
- **When** the command runs
- **Then** it fails fast with a clear "positive integer" error message and no interpreter
  traceback appears in its output — `--parallelism` is validated before it is ever passed to the
  auto-scale computation, not after

#### Scenario: A degenerate config count does not crash the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1 --no-provision` with a
  `--corpus-dir` whose `sweep_manifest.json` declares zero configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** the computed `activeDeadlineSeconds` equals `14400` (just the 4-hour retry margin,
  `ceil(0 * 2.4 / 1 + 4) * 3600`) — the formula degrades gracefully rather than erroring or
  producing a nonsensical value

#### Scenario: A very large parallelism does not overflow or underflow the formula

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1000000 --no-provision`
  with a `--corpus-dir` whose `sweep_manifest.json` declares 3 configs, and no
  `--active-deadline-seconds`
- **When** the command runs
- **Then** the computed `activeDeadlineSeconds` equals `18000` (`ceil(3 * 2.4 / 1000000 + 4) *
  3600 = ceil(4.0000072) * 3600 = 5 * 3600` — the config-count term contributes only `0.0000072`,
  but `ceil` still rounds up past that nonzero remainder to `5`, not `4`) — the formula produces
  a sane, correctly-rounded floor rather than a nonsensical tiny, negative, or overflowed value

### Requirement: retryStrategy backoff can cover the full configured retry limit

`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`'s `retryStrategy.backoff` SHALL
cap cumulative retry backoff (`maxDuration`) high enough that all `limit`-configured retries can
actually be attempted before Argo gives up, given the corpus's real per-attempt runtimes and
observed preemption frequency — not a value that exhausts itself partway through the configured
retry budget, as `maxDuration: "30m"` did for `duration: "2m"`/`factor: 2` (exhausted after 3 of 5
configured retries).

#### Scenario: The full retry sequence fits within maxDuration

- **Given** the `force-surrogate-single-config` WorkflowTemplate's `retryStrategy`
- **When** its `backoff` block is inspected
- **Then** `limit: 5`, `duration: "2m"`, `factor: 2` are unchanged, and `maxDuration` is `"4h"` —
  the cumulative backoff sequence for all 5 configured retries (`2m+4m+8m+16m+32m = 62m`) fits
  well within the cap, so a config that needs multiple preemption-driven retries is not cut off
  by `maxDuration` before its configured `limit` is exhausted
