## Why

The full 27-config fine-grid force-surrogate corpus has now failed to complete on the cluster
**twice**, for two distinct, already-diagnosed reasons in the same subsystem
(`cluster/argo/`):

- **Issue #63**: `force-surrogate-sweep-7wrk7` (2026-08-03) was killed by Argo at exactly 24h
  (`activeDeadlineSeconds: 86400`) with **0/27 configs completed**. `--parallelism 1` (the
  quota-driven choice actually used, per the fine-grid pilot's recommendation) was passed to
  `submit_workflow.sh full`, but there is no equivalent override for `activeDeadlineSeconds` —
  the 24h ceiling was implicitly sized for the file's own default `parallelism: 3` (27 configs /
  3 workers × ~2.3–2.4h/config ≈ 21–22h, fits under 24h) and does not scale when parallelism is
  overridden. At `parallelism=1` the true serial runtime is ~64.8h (measured directly from the
  27 `run_metadata_*.json` files of the corpus's other real run, `force-surrogate-sweep-vb8t5`:
  mean 2.40h/config, sum 233,389s), ~2.7× the ceiling — guaranteed to hit the wall regardless of
  how cleanly the run otherwise proceeds.
- **Issue #64**: `force-surrogate-sweep-vb8t5` (2026-08-04→08-07) got 24/27 configs but lost the
  3 longest-running (`s35_f085_p30`, `s35_f085_p45`, `s45_f085_p60`, ~2.6h/attempt each) to
  preemption under talmo-lab's sustained ~155–176% GPU quota overrun. `force-surrogate-single-
  config.yaml`'s `retryStrategy` allows `limit: 5` (6 attempts) but caps cumulative backoff at
  `maxDuration: 30m` — `2m→4m→8m→16m` already sums to 30m after only 3 retries, so Argo gives up
  with `Max duration limit exceeded` with 2 of the 5 configured retries never used. This is
  exactly the risk the fine-grid pilot's own report flagged as untested ("no real preemption
  occurred in the pilot") — it happened for real here. The 3 configs were recovered only via a
  separate, one-off workflow (`force-surrogate-retry-failed-trz9k`) that inlined the template
  with `maxDuration: 4h`, not via the shared, committed template's own retry path.

Both bugs must be fixed before anyone resubmits the corpus, or it will likely fail the same way
again — a partial fix (only one issue landing) still leaves the resubmission broken. They are
bundled into one change because they are the same subsystem, diagnosed from the same two failed
runs, and fixing only one still blocks a clean resubmission.

Issue #65 (`compute_wall_time_s` has no per-config filtering, giving wrong `wall_time_s` in
metadata for multi-config fan-out workflows) is a different subsystem
(`src/mosquito_cfd/force_surrogate/metadata_capture.py`, not the Argo templates) and a post-run
metadata-correctness bug, not a run-completion blocker — explicitly out of scope, deferred to its
own future change.

## What Changes

- **`cluster/argo/scripts/submit_workflow.sh full`**: add an `--active-deadline-seconds N` flag
  that overrides the submitted workflow's `activeDeadlineSeconds`, mirroring the existing
  `--parallelism` mechanism exactly (anchored, self-verifying `sed`-patch onto a temp copy; the
  committed `force-surrogate-sweep.yaml` is never mutated). **Additionally**, when
  `--parallelism` is overridden and `--active-deadline-seconds` is *not* explicitly given, the
  script auto-computes a safe deadline from the sweep manifest's actual config count, a
  documented per-config-hours constant (2.4h, the measured `vb8t5` mean), the effective
  parallelism, and a fixed retry-margin (4h, matching the issue #64 `maxDuration` bump) — instead
  of silently leaving the stale 24h default in place. (Issue #63's own "Ask" section suggests a
  longer-term per-*step*-count cost model instead; this proposal uses the simpler, already-
  measured per-*config* mean — see `design.md` D2 for why, acknowledged explicitly as a deviation
  rather than assumed equivalent.) An explicit `--active-deadline-seconds`
  always takes precedence over the auto-computed value. When both `--parallelism` and
  `--active-deadline-seconds`/the auto-scaled value need to be applied, both patches land on the
  **same** temp copy, each independently self-verified. Omitting both flags remains a true no-op
  (unpatched committed file), exactly as today.
- **`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`**: bump
  `retryStrategy.backoff.maxDuration` from `30m` to `4h` (field-validated by the `trz9k` recovery
  workflow that already used this exact value to recover these exact 3 configs). `limit: 5`,
  `duration: 2m`, and `factor: 2` are unchanged — `2m→4m→8m→16m→32m` sums to 62m, now comfortably
  under the new 4h ceiling, so all 5 configured retries can actually run. This change is shared by
  both the `full` and `smoke` submission paths (both `templateRef` the same WorkflowTemplate) —
  no separate smoke-workflow change needed for retry behavior.
- **Documentation**: `submit_workflow.sh`'s usage header documents the new flag and the
  parallelism/deadline coupling risk (per issue #63's explicit ask) that the new flag + auto-scale
  fallback now close.
- **OpenSpec**: an `ADDED Requirements` delta on the `force-surrogate` capability (sibling
  requirements to the existing "Cluster-side Argo orchestration of the corpus" base requirement
  and the prior `--parallelism`/NFS-provisioning sibling requirements — same additive pattern).

## Non-goals (explicit)

- **Does not touch `cluster/argo/workflows/force-surrogate-smoke.yaml`'s `activeDeadlineSeconds`.**
  It runs exactly one config with no `parallelism` field; even worst-case (1 config × 6 attempts
  × up to the new 4h backoff ceiling) is nowhere near 24h, so the deadline cannot realistically
  bind there.
- **Does not build the pre-submit sanity-check** (estimate expected wall time vs. deadline, fail
  before submission) suggested in an issue #63 comment. That comment's author has GitHub
  `association: none` on this repo — no confirmed lab/collaborator affiliation could be verified —
  so this proposal treats the idea as unactioned; if it has merit on independent technical
  grounds, it is a candidate for its own future issue, not silently folded in here.
- **Does not address issue #65** (`compute_wall_time_s` per-config filtering) — different
  subsystem, separate future change.
- **Does not submit anything to the real cluster.** Real Argo submission is authorized for this
  work in principle, but each actual submission requires the user's explicit go-ahead at the time,
  separate from this proposal's approval. Verification here is cluster-free (text/regex assertions
  against the committed YAML + stub-`argo` shell tests), matching this repo's established offline
  testing pattern for `cluster/argo/`.
- **Does not change `limit`, `duration`, or `factor`** in the retry `backoff` block — only
  `maxDuration`.
- **Does not change the committed `activeDeadlineSeconds: 86400` default** in
  `force-surrogate-sweep.yaml` itself — only adds a way to override it. The existing test
  asserting the literal `"activeDeadlineSeconds: 86400"` string in the committed file is expected
  to keep passing unmodified.

## Impact

- Affected specs: `force-surrogate` (`ADDED Requirements` delta).
- Affected code:
  - `cluster/argo/scripts/submit_workflow.sh` (new `--active-deadline-seconds` flag, auto-scale
    fallback with a `python3`-on-PATH precondition check, usage-header doc) + new
    `tests/test_submit_workflow_active_deadline.py`.
  - `cluster/argo/workflow-templates/force-surrogate-single-config.yaml` (`maxDuration: 30m` →
    `4h`) + updated assertion in `tests/test_argo_workflows.py`.
- Affected docs: `cluster/argo/README.md` (new flag + auto-scale documented) and
  `openspec/project.md` (the "unverified preemption/retry path" Pending bullet updated to
  reflect that the retry path now covers the full configured `limit: 5` sequence).
- No changes to Python pod-runtime code, CFD solver integration, Docker images, or committed
  corpus data.
- Cluster cost: **none** for this proposal (all verification is cluster-free). The actual
  resubmission of the 27-config corpus is a separate, later, explicitly-confirmed operator action.
