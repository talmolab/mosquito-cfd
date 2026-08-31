## Why

`compute_wall_time_s()` (`src/mosquito_cfd/force_surrogate/metadata_capture.py:465-505`) takes
the single globally-latest-finishing node across an entire Argo workflow's `status.nodes`, which
silently gives every config in a multi-config fan-out workflow the same wrong `wall_time_s`
(confirmed empirically against real `force-surrogate-sweep-vb8t5` data — see `design.md`
Context). This was explicitly deferred from PR #82/#83 (issues #63/#64) and is now the last
blocker before the user's 27-config corpus resubmission, whose entire deliverable is per-config
metadata.

## What Changes

Add optional pod-scoped node selection to the wall-time-resolution chain, with the pod name
auto-derived from data `assemble_run_metadata` already loads — no new CLI flag, no Argo template
change, no `run_one_config.py` change:

1. **`compute_wall_time_s(status, *, pod_name=None)`** gains a new keyword-only `pod_name`
   parameter.
   - When `pod_name` is supplied: look up `status["status"]["nodes"].get(pod_name)` directly
     (Argo status node dict keys are the pod's own full name — confirmed via
     `tests/fixtures/run_metadata/argo_status_simple.json` and the real `vb8t5` workaround, which
     matched nodes by exact dict-key equality to `orchestration.pod`). The matched node must have
     `phase == "Succeeded"`, `type != "Retry"`, and both `startedAt`/`finishedAt`. If no node has
     that key, or the matched node fails any of those checks, raise `ValueError` naming the
     supplied `pod_name` and listing the available candidate keys — **no silent fallback to the
     global max**, since that would mask exactly the bug this change fixes.
   - When `pod_name` is `None` (omitted): preserve today's exact behavior — the unfiltered global
     `max()` across all Succeeded, non-Retry candidates. Every existing single-candidate fixture
     and test keeps passing unmodified.
2. **`resolve_wall_time_s(..., pod_name=None)`** gains the same keyword-only parameter and passes
   it straight through to `compute_wall_time_s` on the Argo-query path (the override path is
   unaffected — `pod_name` is irrelevant when `wall_time_s_override` is supplied).
3. **`assemble_run_metadata`** auto-derives `pod_name` from
   `orchestration.get("pod")` (the `orchestration` dict is already built at
   `metadata_capture.py:634` from the pod's own `run_metadata.json`, itself populated from Argo's
   `{{pod.name}}` template variable via `run_one_config.py`'s `--pod` argument — see
   `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`). It passes that value to
   `resolve_wall_time_s`. No new parameter is added to `assemble_run_metadata`'s own signature and
   no new CLI flag is added to `scripts/generate_run_metadata.py` — the value is always already
   available and always correct (it is the pod's own self-report), so there is nothing for an
   operator to remember to pass.
4. **Backward compatibility for pod metadata predating `orchestration.pod`**: if
   `orchestration.get("pod")` is `None` (an old pod-side `run_metadata.json` written before the
   `orchestration.pod` field existed), `assemble_run_metadata` passes `pod_name=None` through,
   reproducing today's global-max behavior rather than raising — old pod metadata keeps working,
   it just isn't protected against the multi-config ambiguity (which it predates by construction:
   the field didn't exist yet, meaning this metadata is old enough it can't itself be from a
   multi-pod fan-out that used this pipeline).

## Impact

- **Affected code**: `src/mosquito_cfd/force_surrogate/metadata_capture.py` only
  (`compute_wall_time_s`, `resolve_wall_time_s`, `assemble_run_metadata`). No changes to
  `scripts/generate_run_metadata.py`'s CLI surface, `cluster/argo/` YAML, or
  `run_one_config.py`.
- **Affected tests**: `tests/test_metadata_capture.py` (new regression tests) and a new fixture
  file, `tests/fixtures/run_metadata/argo_status_multi_config.json` (plus its accompanying
  `README.md` bullet). `tests/test_generate_run_metadata_cli.py` is expected to need **no**
  changes (no new CLI flag; existing `--wall-time-s`/`--workflow-name` tests exercise paths
  unaffected by this fix) — verified explicitly in `tasks.md`, not assumed.
- **Affected specs**: `run-metadata` — `## MODIFIED Requirements` delta to the existing
  "wall-clock timing is computed from a completed Argo workflow's persisted status, with a manual
  override for garbage-collected workflows" requirement, adding pod-scoped node selection and a
  new scenario for the multi-config fan-out case.
- **Not affected / explicitly out of scope**: issues #63/#64 (already fixed, PR #82/#83, unrelated
  subsystem — bash/YAML cluster/argo tooling vs. this pure-Python metadata module); issue #79
  (species-naming docs); issue #77 (process-gap tracking); the 3 already-committed
  `examples/prelim_sweep_fine_pilot/run_metadata_*.json` pilot files (unaffected, single-config,
  hand-verified already per the module's own non-goals).
- **Rollout**: pure code + test change, no infrastructure/image rebuild required. Unblocks (but
  does not itself trigger) the user's separate, explicit go-ahead to resubmit the full 27-config
  cluster corpus.
