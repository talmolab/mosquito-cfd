## MODIFIED Requirements

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
