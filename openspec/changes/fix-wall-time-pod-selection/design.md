## Context

Issue #65. `compute_wall_time_s` takes the global-max Succeeded/non-Retry node across an entire
Argo workflow's `status.nodes`. Correct for one-config-per-workflow submissions; wrong for the
multi-config fan-out full sweep, where every config in the same workflow silently gets the same
(wrong) `wall_time_s`.

Confirmed against real `force-surrogate-sweep-vb8t5` data: querying that workflow's raw status
showed 24 distinct `Succeeded` `Pod`-type nodes with clearly different `startedAt`/`finishedAt`
pairs (e.g. one config ran `2026-08-04T21:21:56Z`-`23:59:56Z`, another ran
`2026-08-07T05:08:18Z`-`07:05:11Z`). `compute_wall_time_s` returns the latter's ~2-hour duration
for all 24 configs — silently corrupting every `run_metadata_<config>.json`'s
`timing.wall_time_s` except (by chance) the one config that genuinely finished last. The existing
test suite doesn't catch this: every fixture exercising `compute_wall_time_s`
(`argo_status_simple.json`, `argo_status_with_retry.json`) has exactly one real Succeeded/non-Retry
candidate node, so `max()` over a single-element (or single-config, multi-attempt) candidate list
happens to be correct regardless of the missing per-config filtering.

## Goals / Non-Goals

- Goal: make `wall_time_s` correct per-config in a multi-config fan-out workflow.
- Goal: zero behavior change for every existing single-config caller/fixture/test.
- Goal: no new required input for operators — the pod name is already durably recorded.
- Non-goal: changing the Argo WorkflowTemplate, `run_one_config.py`, or the sweep-level fan-out
  template itself.
- Non-goal: adding a `--pod-name` CLI override (see Decision 3).

## Decisions

### Decision 1: match by exact dict-key equality against `orchestration.pod`, not by field content

Argo status `nodes` dict keys are the pod's own full name (confirmed via
`tests/fixtures/run_metadata/argo_status_simple.json`: the single node's key,
`force-surrogate-smoke-xwm4b-run-config-3125566197`, is byte-identical to
`pod_run_metadata.json`'s `orchestration.pod`). The real `vb8t5` manual workaround (per issue #65)
already used exactly this matching strategy successfully. A direct `dict.get(pod_name)` lookup is
simpler and cheaper than filtering-then-`max()`-over-one, and, being an exact-match lookup, cannot
accidentally match a different config's node the way a looser heuristic (e.g. substring match on
`displayName`, which is always the generic template name `"run-config"` for every config — not
unique) could.

### Decision 2: unmatched `pod_name` raises `ValueError`, never falls back silently

Considered: falling back to the global max with a logged warning when `pod_name` doesn't match
any node. Rejected — that reintroduces the exact failure mode this change exists to close, just
with an extra log line most operators running a long-lived, human-supervised batch job over dozens
of configs are unlikely to notice in time. A typo'd or genuinely-missing pod name should stop the
run for that config loudly, not silently produce another wrong `wall_time_s`.

### Decision 3: no new `--pod-name` CLI flag

`assemble_run_metadata` already loads the pod's own `run_metadata.json` before calling
`resolve_wall_time_s`, and that file already contains `orchestration.pod` — the pod's own
self-report of its own name, always correct for the pod being processed. There is no scenario
where an operator legitimately needs to supply a *different* pod name than the one the pod itself
already recorded; adding a CLI override would only add an easy way to mis-attribute one config's
metadata to another pod's timing, which is precisely the bug class being fixed. If a future need
for an override does arise (e.g. recovering metadata for a pod whose own `run_metadata.json` was
lost), that is a distinct problem better solved by reconstructing `orchestration.pod`, not by a
`resolve_wall_time_s`-level override.

### Decision 4: `pod_name=None` (omitted) preserves today's unfiltered global-max behavior exactly

This is the only way to keep every existing single-candidate test and fixture
(`argo_status_simple.json`, `argo_status_with_retry.json`) passing with zero fixture changes, and
it is also the correct behavior for the case it covers: pod-side metadata written before
`orchestration.pod` existed has, by construction, never been part of a multi-pod fan-out through
this pipeline (the field didn't exist yet), so there is no real ambiguity to resolve for it in the
first place — it is exactly the single-candidate case the old behavior was written for.

## Risks / Trade-offs

- A pod whose own recorded `orchestration.pod` is itself wrong (e.g. hand-edited, or corrupted by
  some other bug) would now raise `ValueError` where it previously silently produced a
  (differently) wrong `wall_time_s`. This is treated as a feature, not a risk: an operator seeing
  a loud, specific error is better positioned to diagnose a corrupted pod metadata file than one
  silently trusting a wrong global-max value with no error at all.
- This fix's correctness depends on the sweep/fan-out-level Argo Workflow reusing the same per-pod
  `orchestration.pod`-recording mechanism already in place for single-config runs. **Verified, not
  merely assumed**: `cluster/argo/workflows/force-surrogate-sweep.yaml`'s `run-all-configs` DAG
  task fans out over the manifest via `withParam` using
  `templateRef: {name: force-surrogate-single-config, template: run-config}` — the exact same
  container template (including its `--pod {{pod.name}}` arg) already proven correct by the
  single-config path's own `pod_run_metadata.json`/`argo_status_simple.json` fixtures. This is
  also consistent with the real `vb8t5` data already having exactly that field per config. Before
  the next full-corpus resubmission, still worth spot-checking one config's actual
  `run_metadata.json` from that specific run to confirm `orchestration.pod` was populated as
  expected — the template reuse guarantees the *mechanism* is shared, not that a given run's
  output wasn't corrupted by some unrelated issue.
- **Deferred (not applied)**: matched-node validation checks `type != "Retry"` (excluding only the
  wrapper), not `type == "Pod"` (excluding every non-Pod type). A `Succeeded`, non-`Retry`,
  fully-timestamped `Steps`/`DAG` container node could in principle collide with a `pod_name` and
  pass validation. Not tightened here because `argo_status_simple.json`'s real single-config
  fixture node has **no `type` key at all** (only `phase`/`startedAt`/`finishedAt`) — real Argo
  leaf-pod nodes can apparently omit `type` entirely, so a strict `type == "Pod"` check would
  reject that shape and regress the single-config path this fix must not touch. Tightening
  correctly would require confirming real Argo's actual `type` semantics across the API versions
  in use, which is out of scope for this issue; flagged as a fast-follow if it ever proves
  necessary in practice, per this project's preference for minimal, tightly-scoped changes.

### Rollback / recovery if the `ValueError` fires unexpectedly in production

If a real pod's `orchestration.pod` doesn't match any node in the workflow status (e.g. a config
name typo, or a node genuinely missing from a partially-garbage-collected workflow) mid-way
through processing the 27-config resubmission's metadata, two levers already exist without
needing a code change:
1. **`--wall-time-s <value>` manual override** (pre-existing, unchanged by this proposal) bypasses
   the Argo query — and therefore the pod-name lookup — entirely for that one config, exactly as
   it already does today for a garbage-collected workflow.
2. Since every signature change in this proposal is purely additive and backward-compatible (see
   Migration Plan), a `git revert` of the merge commit is low-risk and restores the exact
   pre-fix (unfiltered global-max) behavior for every config, if the new validation turns out to
   be unexpectedly strict against some pod-metadata shape this proposal didn't anticipate.

## Migration Plan

None required — purely additive, backward-compatible function signatures (new keyword-only
parameters, all defaulting to `None`/current behavior). No data migration, no re-generation of
already-committed `run_metadata_<config>.json` files required by this change itself (though the
now-corrected pipeline is exactly what makes the pending 27-config corpus resubmission safe to
regenerate metadata from).

## Open Questions

None outstanding — the three design questions raised in the clarifying-questions step (parameter
shape/CLI surface, no-match fallback behavior, backward compatibility for omitted pod name) were
all resolved with the user before this proposal was drafted; see Decisions 1-4 above.
