## Tasks

> **Commit granularity note**: within sections 2-4 below, which each follow a write-test(s)-then-
> implement TDD structure, the "write test(s)" and "implement" checkboxes are separate tracking
> steps but must land in the **same commit** — a commit containing only a newly-added failing
> test (with no implementation) would leave `pytest -v` red on `main`'s history at that commit,
> unlike every commit in this repo's actual git history. Commit once each section's
> implementation task is green. Section 1 (fixture + README, no test/implement split) and section
> 5 (verification-only, expected to produce no diff) don't fit this pattern; section 6 is one
> commit bundling its doc/changelog/project.md content tasks, with its `openspec validate`/
> `ruff`/`pytest` tasks run as pre-commit gates against that commit rather than as separate
> commits of their own.

### 1. New multi-config fixture

- [x] 1. Add `tests/fixtures/run_metadata/argo_status_multi_config.json`: a single Argo workflow
    status (mirroring `argo_status_simple.json`'s shape) whose `status.nodes` dict has **three**
    distinct `Succeeded`, `Pod`-type nodes, each keyed by a distinct realistic pod name (following
    the real `force-surrogate-sweep-vb8t5` naming pattern, e.g.
    `"force-surrogate-sweep-vb8t5-run-config-1111111111"`,
    `"...-run-config-2222222222"`, `"...-run-config-3333333333"`). Construct the three nodes'
    `startedAt`/`finishedAt` windows to be **sequential and non-overlapping**, in the order
    `1111111111` (earliest, ~1800s duration) → `2222222222` (middle, ~3600s duration) →
    `3333333333` (latest, ~9200s duration) — so node `3333333333` unambiguously has **both** the
    longest duration **and** the latest absolute `finishedAt` of the three. This distinction
    matters: the fixture must make "longest duration" and "finishes last" coincide on the same
    node, so that a test asserting against node `2222222222` (neither the longest nor the
    latest-finishing) fails cleanly under today's unfixed global-max `compute_wall_time_s` and
    passes only once pod-scoped selection is implemented.
- [x] 2. Add a descriptive bullet for `argo_status_multi_config.json` to
    `tests/fixtures/run_metadata/README.md`, matching the existing one-bullet-per-fixture
    convention used for `argo_status_simple.json`/`argo_status_with_retry.json`: describe the
    three-node shape, the sequential non-overlapping timestamps, and what it exists to prove
    (pod-scoped lookup selects the correct non-latest node rather than the global maximum).

### 2. `compute_wall_time_s(status, *, pod_name=None)` — TDD [depends: 1]

- [x] 3. Write `test_wall_time_selects_matching_pod_node_in_multi_config_status` in
    `tests/test_metadata_capture.py`, next to the existing `test_wall_time_from_argo_status_timestamps`:
    load `argo_status_multi_config.json`, call
    `mc.compute_wall_time_s(status, pod_name="force-surrogate-sweep-vb8t5-run-config-2222222222")`
    (the middle node — neither the longest-duration nor the latest-finishing one), and assert the
    result equals that specific node's own duration, computed independently in the test from its
    own `startedAt`/`finishedAt` (not copy-pasted from the fixture-authoring step). This must fail
    under today's unfixed `compute_wall_time_s` (which would return node `3333333333`'s ~9200s
    duration instead).
- [x] 4. Write `test_wall_time_pod_name_none_preserves_global_max_behavior_on_multi_config_status`:
    call `mc.compute_wall_time_s(status, pod_name=None)` (and separately with no `pod_name`
    argument at all) against the same `argo_status_multi_config.json` fixture, and assert the
    result equals node `3333333333`'s (globally-latest-finishing) duration — pinning today's
    exact fallback behavior explicitly so a future change cannot silently alter the
    omitted-`pod_name` path without a test failing. Confirm by inspection that the two pre-existing
    tests `test_wall_time_from_argo_status_timestamps` and
    `test_wall_time_reflects_only_final_successful_attempt` (both call `compute_wall_time_s(status)`
    with no `pod_name` at all, against their existing single-candidate fixtures) need no changes.
- [x] 5. Write `test_wall_time_raises_on_unmatched_pod_name`: call
    `mc.compute_wall_time_s(status, pod_name="force-surrogate-sweep-vb8t5-run-config-9999999999")`
    (a key present in no fixture) against `argo_status_multi_config.json`, and assert
    `pytest.raises(ValueError, match="9999999999")`. Additionally assert that the raised message
    also contains at least one of the three real candidate keys (e.g.
    `"run-config-1111111111"` appears in `str(exc_info.value)`) — this is required by
    `proposal.md`'s "What Changes" #1 ("listing the available candidate keys"); without this
    assertion, that promised behavior would ship with zero test coverage.
- [x] 6. Write three tests exercising each independent branch of matched-node validation (all
    build an inline status dict shaped like the multi-config fixture, plus one additional node
    whose key is a specific `pod_name`, and each asserts `pytest.raises(ValueError, match=<that
    pod_name>)`):
    - `test_wall_time_raises_when_matched_pod_node_has_wrong_phase`: the extra node's `phase` is
      `"Failed"` (or `"Running"`).
    - `test_wall_time_raises_when_matched_pod_node_is_retry_type`: the extra node's `phase` is
      `"Succeeded"` but its `type` is `"Retry"`.
    - `test_wall_time_raises_when_matched_pod_node_missing_timestamps`: the extra node's `phase`
      is `"Succeeded"`, `type` is not `"Retry"`, but `startedAt` or `finishedAt` is absent.
    These three tests exist because an implementation that validates only one of
    `phase`/`type`/timestamp-presence on the pod-name-supplied path (e.g. only checks `phase`)
    would otherwise pass task 5 undetected — each branch needs its own dedicated failure case.
    (This scenario is intentionally covered only at the `compute_wall_time_s` unit level, not
    duplicated at the `assemble_run_metadata` level the way task 13 does for the unmatched-pod-
    name case — `resolve_wall_time_s`/`assemble_run_metadata` propagate any `ValueError` from
    `compute_wall_time_s` identically regardless of which validation branch raised it, so task 13
    already proves that propagation mechanism once and a second assemble-level test here would
    be redundant.)
- [x] 7. Implement the `pod_name: str | None = None` keyword-only parameter on
    `compute_wall_time_s` per `design.md` Decision 1/2/4: when `pod_name` is supplied, look up
    `nodes.get(pod_name)` directly; if absent, raise `ValueError` naming `pod_name` and listing
    the available candidate keys; if present, validate `phase == "Succeeded"`, `type != "Retry"`,
    and both timestamps present, raising `ValueError` naming `pod_name` if any check fails;
    otherwise return its duration. When `pod_name` is `None`, run the existing unmodified
    `candidates`-collection-then-`max()` logic unchanged. Run tasks 3-6 to green; confirm the two
    pre-existing wall-time tests from task 4 still pass unmodified.

### 3. `resolve_wall_time_s(..., pod_name=None)` passthrough [depends: 2]

- [x] 8. Write `test_resolve_wall_time_s_passes_pod_name_through_to_argo_query_path`: using the
    same fake-`argo_status_query` injection pattern as the existing
    `test_resolve_wall_time_s_calls_argo_status_query_when_no_override`, supply the multi-config
    status via the fake query and call
    `mc.resolve_wall_time_s(workflow_name="...", wall_time_s_override=None,
    pod_name="force-surrogate-sweep-vb8t5-run-config-2222222222", argo_status_query=fake_query)`;
    assert the result equals that node's own duration (not the global max).
- [x] 9. Write `test_resolve_wall_time_s_override_ignores_pod_name`: define a spy
    `argo_status_query` callable that raises `AssertionError` if called (mirroring the existing
    `test_wall_time_s_override_bypasses_argo_query` pattern), call
    `mc.resolve_wall_time_s(workflow_name="some-workflow", wall_time_s_override=7032.46,
    pod_name="anything", argo_status_query=_spy_query)`, and assert the result is `7032.46` and
    the spy was never invoked — confirms `pod_name` has no effect on the override path, actually
    verified via a call-recording spy rather than merely omitting the argument.
- [x] 10. Implement the `pod_name: str | None = None` keyword-only parameter on
    `resolve_wall_time_s`, passed straight through to `compute_wall_time_s` on the Argo-query
    branch only. Run tasks 8-9 to green; confirm
    `test_resolve_wall_time_s_calls_argo_status_query_when_no_override` and
    `test_wall_time_s_override_bypasses_argo_query` still pass unmodified.

### 4. `assemble_run_metadata` auto-derives `pod_name` from `orchestration.pod` [depends: 3]

- [x] 11. Write `test_assemble_metadata_wall_time_selects_matching_pod_in_multi_config_workflow`
    in `tests/test_metadata_capture.py`, alongside the existing `_assemble()` helper's tests:
    write a `pod_metadata` fixture (a copy of `pod_run_metadata.json` with `orchestration.pod`
    overridden to `"force-surrogate-sweep-vb8t5-run-config-2222222222"`) to `tmp_path`, inject a
    fake `argo_status_query` returning the multi-config status, call
    `_assemble(pod_metadata_path=<that tmp_path file>, workflow_name="...", wall_time_s=None,
    argo_status_query=fake_query)` (no `--wall-time-s` override, so the real Argo-query +
    pod-selection path actually runs), and assert `result["timing"]["wall_time_s"]` equals that
    specific node's own duration (~3600s) — not the global max (~9200s), and not any value the
    module's other pre-existing tests happen to expect (those all use a `wall_time_s` override
    and never exercise this path at all today).
- [x] 12. Write `test_assemble_metadata_wall_time_falls_back_when_orchestration_pod_missing`: same
    setup as task 11, but delete the `pod` key from the `pod_metadata` copy's `orchestration`
    block entirely before writing it to `tmp_path`, and inject a fake `argo_status_query`
    returning `argo_status_simple.json` (single real candidate, so the fallback path has an
    unambiguous, correct answer); call `_assemble(pod_metadata_path=<that tmp_path file>,
    workflow_name="...", wall_time_s=None, argo_status_query=fake_query)` and assert
    `result["timing"]["wall_time_s"]` equals that single node's duration with no exception raised
    — confirms old-shaped pod metadata (predating `orchestration.pod`) still works.
- [x] 13. Write `test_assemble_metadata_raises_when_orchestration_pod_unmatched`: same setup as
    task 11, but override `orchestration.pod` to
    `"force-surrogate-sweep-vb8t5-run-config-9999999999"` (absent from the injected multi-config
    status) and call `_assemble(...)` with the same multi-config fake query; assert
    `pytest.raises(ValueError, match="9999999999")`. Proves the error from `compute_wall_time_s`
    actually propagates unmodified through `resolve_wall_time_s` and `assemble_run_metadata` at
    the full call-chain level, not only at the `compute_wall_time_s` unit level (task 5).
- [x] 14. Implement the change in `assemble_run_metadata`: after building
    `orchestration = dict(pod_metadata.get("orchestration", {}))` (existing line), pass
    `pod_name=orchestration.get("pod")` into the `resolve_wall_time_s(...)` call. Run tasks 11-13
    to green; confirm every pre-existing `_assemble(...)`-based test in
    `tests/test_metadata_capture.py` still passes unmodified (all of them supply a `wall_time_s`
    override, so `pod_name` is computed but never consulted for those cases).

### 5. Verify no CLI-level changes needed [depends: 4]

- [x] 15. Re-read `tests/test_generate_run_metadata_cli.py` and `scripts/generate_run_metadata.py`
    against the implemented change and confirm, explicitly (not just by assumption): (a) no new
    CLI flag was added (per `proposal.md`/`design.md` Decision 3), so no existing test's argv
    construction needs updating; (b) every existing CLI test either supplies `--wall-time-s`
    (bypassing the Argo-query/pod-selection path entirely) or exercises an unrelated error path
    (missing required args, malformed `--git-commit`), so none of them exercise the
    Argo-query-with-multiple-candidates scenario this change fixes. Run the full
    `tests/test_generate_run_metadata_cli.py` suite and confirm all pre-existing tests still pass
    with zero modifications. If this check surfaces a real gap (e.g. a CLI test that silently
    relied on the old buggy global-max behavior in a way that now changes), stop and add a task
    here to address it before proceeding — do not silently patch over a surprise.

### 6. Documentation + spec validation [depends: 1-5]

- [x] 16. Update `metadata_capture.py`'s module docstring's `timing.wall_time_s` bullet (currently:
    "computed from a completed Argo workflow's persisted status timestamps
    (:func:`query_argo_workflow_status`), reflecting only the final successful attempt — or a
    caller-supplied ``--wall-time-s`` override if the source workflow has already been
    garbage-collected.") to additionally describe pod-scoped node selection for multi-config
    fan-out workflows and the `ValueError` raised on an unmatched or invalid pod name, per this
    change's `spec.md` delta.
- [x] 17. Add a `### Fixed` entry to `docs/CHANGELOG.md` for issue #65, matching the granularity
    of the entry `fix-git-provenance-no-git-override` added for issue #66.
- [x] 18. Update `openspec/project.md`'s Pending bullet for the 27-config corpus resubmission
    (the one ending "...are fixed in `fix-argo-sweep-timeouts`:"): add a sentence noting that a
    third, metadata-only bug (issue #65 — `compute_wall_time_s` picking the globally-latest
    -finishing pod's duration for every config in a multi-config fan-out workflow) is now also
    fixed by this change, and that the resubmission is blocked only on the user's explicit
    go-ahead, not any known bug.
- [x] 19. Run `openspec validate fix-wall-time-pod-selection --strict` and resolve any issues.
- [x] 20. Run `uv run ruff check src/mosquito_cfd/force_surrogate/metadata_capture.py
    tests/test_metadata_capture.py` and `uv run ruff format --check` on the same file list; fix
    any violations. Then, before opening the PR, run `uv sync --frozen --group viz` followed by
    the full CI-equivalent checks exactly as `.github/workflows/ci.yml` invokes them —
    `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/
    examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`, `uv run ruff format --check`
    (same paths), and `uv run pytest -v -m "not gpu"` (the whole suite; CI treats exit code 5 —
    "no tests collected" — as acceptable too, though that won't occur here since the full suite
    always collects tests) — and confirm zero regressions anywhere in the repo, not only in the
    metadata_capture module.
- [x] 21. Run the targeted test suite (`uv run pytest tests/test_metadata_capture.py
    tests/test_generate_run_metadata_cli.py -v`) and confirm every pre-existing test still passes
    alongside the new ones from tasks 3-15.

### 7. `/review-pr` self-review fixes (pre-PR, `/pre-merge-check` Phase 3.5)

A 5-lens pre-PR self-review found no BLOCKING issues (TDD reviewer independently verified genuine
red→green via `git stash`; scientific-rigor reviewer confirmed the pod-scoped lookup is
structurally immune to cross-config misattribution). Two IMPORTANT findings, each independently
raised by more than one reviewer:

- [x] 22a. The unmatched-`pod_name` `ValueError`'s "available candidate keys" listed *every* raw
    node key (`sorted(nodes.keys())`), not filtered to genuine Succeeded/non-Retry candidates —
    on the real `vb8t5`-shaped 24+-config sweep (which also has per-config `Retry` wrapper nodes
    and DAG/Steps auxiliary nodes), this would dump 60-100+ mostly-irrelevant keys instead of a
    clean list of sibling pod names, undercutting the "clear, actionable error" goal. Fixed:
    filter to `phase == "Succeeded" and type != "Retry"` before listing (same predicate as the
    fallback branch). Added `test_wall_time_unmatched_pod_error_excludes_non_candidate_keys`
    (a `Retry`-wrapper node and a `Failed` Pod node must not appear in the message).
- [x] 22b. `assemble_run_metadata`'s own function-level `Raises:` docstring block didn't mention
    the new `ValueError` propagated from `compute_wall_time_s` on a pod-name mismatch (the
    *module*-level docstring was already updated in task 16, but the function-level block an
    operator debugging a crash is more likely to read was not). Fixed: added a clause.

Also addressed, from SUGGESTIONS raised by multiple reviewers:

- [x] 22c. The matched-but-invalid-node `ValueError` was generic ("not a valid Succeeded,
    non-Retry, fully-timestamped candidate") regardless of which check actually failed. Fixed:
    the message now names the specific reason (wrong phase / Retry-type / missing timestamps).
- [x] 22d. `_MULTI_POD_LATEST` (a test constant) was defined but never referenced. Fixed: wired
    into `test_wall_time_pod_name_none_preserves_global_max_behavior_on_multi_config_status` as
    an explicit cross-check that the fallback and an explicit lookup of the same pod agree.
- [x] 22e. `pod_name=""` behavior (treated as a literal, virtually-certain-to-be-unmatched pod
    name, not as "omitted") was correct but undocumented. Fixed: documented in
    `compute_wall_time_s`'s docstring.

Deferred (pre-existing, not introduced by this diff, out of this issue's scope): a non-dict node
value at a matched key would raise `AttributeError` instead of a clean `ValueError` — the exact
same latent assumption (`node.get(...)` on an unvalidated value) already exists in the pre-fix
global-max loop, so this diff neither introduces nor worsens it.

- [x] 23. Re-run `openspec validate --strict`, the full CI-equivalent `ruff check`/`ruff format
    --check`/`pytest -m "not gpu"` from task 20, and the targeted test suite after the fixes in
    22a-22e; confirm everything passes.

**Round 2** (re-verifying 22a/22b specifically, plus a fresh adversarial pass — same 3 lenses
that had findings in round 1; performance/build and behavioral-correctness were not re-run since
round 1 found nothing there and the round-1 fixes touched only error messages/docstrings, not
logic those lenses cover): all three lenses independently confirmed 22a/22b/22c/22d/22e are
genuinely resolved (not cosmetic) and that the correctness-critical pod-matching/duration-
arithmetic logic itself is byte-for-byte unchanged by the round-1 fixes. One new, empirically
confirmed gap:

- [x] 24. The three reason-differentiation tests (task 6, `..._wrong_phase`/`..._is_retry_type`/
    `..._missing_timestamps`) asserted only `pytest.raises(ValueError, match=<pod_name>)`, never
    the *specific* reason text — so a regression that scrambled which message belongs to which
    failure branch would pass undetected. Confirmed empirically, not just in principle: the
    reviewer swapped the phase/Retry-type reason strings in the implementation and reran
    `-k wall_time` — all 15 tests still passed. Fixed: each of the three tests now additionally
    asserts its own distinct reason substring (`"phase is 'Failed'"` / `"'Retry' wrapper"` /
    `"missing startedAt"`). Verified the fix actually closes the gap by repeating the same
    swap-and-rerun experiment against the strengthened tests: 2 of 3 now fail as expected, then
    reverted the swap and confirmed 69/69 pass again.
- [x] 25. Re-run the targeted test suite and `ruff check`/`ruff format --check` after task 24;
    confirm everything passes (69 passed, both clean).
