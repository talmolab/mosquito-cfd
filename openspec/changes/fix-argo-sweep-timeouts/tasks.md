# Tasks — fix-argo-sweep-timeouts

TDD throughout: each implementation task names the test written first and the behavior it
verifies before the code exists. Branch: `fix-argo-sweep-timeouts` (off `main`). Everything in
this change is cluster-free — no GPU time, no live Argo submission. The actual corpus
resubmission is a separate, later, explicitly-confirmed operator action, not part of this task
list.

---

## 1. `retryStrategy.backoff.maxDuration` bump (issue #64, TDD, cluster-free)

- [x] 1.1 **Test first:** in `tests/test_argo_workflows.py`, extend
  `test_single_config_template_retry_strategy` with a new assertion that the `backoff:` block
  contains `maxDuration: "4h"` (block-anchored the same way the existing `limit: 5` assertion is,
  via `re.search` scoped to text following `retryStrategy:`), and keep the existing `limit: 5`/
  `retryPolicy` assertions unchanged. Fails: the committed template still says `"30m"`.
- [x] 1.2 **Implement:** in `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`,
  change `backoff.maxDuration` from `"30m"` to `"4h"`. Leave `limit: 5`, `retryPolicy:
  "OnFailure"`, `duration: "2m"`, and `factor: 2` unchanged. 1.1 passes.
- [x] 1.3 **Verify:** `uv run pytest tests/test_argo_workflows.py -v` — all pass, including the
  pre-existing `test_workflow_has_image_and_parallelism_and_deadline`'s
  `"activeDeadlineSeconds: 86400" in text` assertion (unaffected by this task; confirm rather than
  assume).

---

## 2. `--active-deadline-seconds` override flag (issue #63, TDD, cluster-free)

**Systemic note (closes a bug class round 3 flagged, not just round 2's single instance in task
3.0):** `tests/test_submit_workflow_active_deadline.py`'s shared invocation helper MUST bake
`--no-provision` into every base invocation **unconditionally**, exactly mirroring
`tests/test_submit_workflow_parallelism.py`'s own `_run_submit_workflow` helper (which already
does this, with the comment "this test file is entirely about `--parallelism`; provisioning ...
must not touch real NFS defaults here"). Do this at the helper level, not by remembering to add
`--no-provision` to each individual test's argument list — `provision()` runs on *every* `full`
invocation regardless of which flag is under test, so any test that omits it either fails for the
wrong reason (a `provision()` precondition fires first) or, worse, attempts a real `mkdir -p`/
`cp -r` against the default NFS-translated path on an operator's live WSL shell. This is the same
bug class task 3.0 was found to have individually; fixing it once in the shared helper (as the
existing parallelism test file already does) removes the need to get it right at every call site.
Individual tasks below may still mention `--no-provision` explicitly where the test is
specifically about a provisioning-interaction edge case (e.g. 3.2/3.3's intentionally-broken
manifest fixtures) — that mention documents reliance on the baked-in behavior, not a second,
separate flag the test must remember to add itself.

- [x] 2.1 **Test first (flag alone):** create `tests/test_submit_workflow_active_deadline.py`,
  mirroring `tests/test_submit_workflow_parallelism.py`'s stub-`argo`-on-`PATH` fixture and
  invocation helper (**including its unconditional `--no-provision` baked into every base
  invocation** — see the note above). Add `test_active_deadline_override_patches_only_the_temp_copy`: invoke
  `full --active-deadline-seconds 172800` (no `--parallelism`); assert the stub's captured
  workflow file contains `activeDeadlineSeconds: 172800` and its `parallelism:` line still reads
  the committed default (`3`); assert the real `force-surrogate-sweep.yaml`'s sha256 on disk is
  unchanged before/after. Fails: flag doesn't exist yet.
- [x] 2.2 **Test first (true no-op):** add
  `test_omitting_both_deadline_and_parallelism_is_a_true_noop`: invoke `full` with neither flag;
  assert no temp file is ever created (no stub-invocation marker for a patched copy — reuse the
  existing pattern of asserting the captured file is byte-identical to the committed workflow).
- [x] 2.3 **Test first (invalid value rejected before mutation):** add
  `test_invalid_active_deadline_seconds_rejected_before_touching_anything`, parametrized over
  `0`, `-1`, `abc` (mirroring the existing parallelism test's parametrization); assert non-zero
  exit, a clear message, the stub never invoked, and the committed file's sha256 unchanged.
- [x] 2.4 **Test first (missing/reformatted anchor line fails loudly):** add
  `test_missing_active_deadline_line_fails_loudly_not_silently`, using the `SWEEP_WORKFLOW_FILE`
  env-var test-injection seam to point at a `tmp_path` copy of the real workflow with its
  `activeDeadlineSeconds:` line deleted; invoke `full --active-deadline-seconds 100000`; assert a
  non-zero exit with a clear "expected exactly one..." message and the stub never invoked.
- [x] 2.5 **Test first (composes with `--parallelism` onto one temp copy):** add
  `test_parallelism_and_active_deadline_together_patch_the_same_temp_copy`: invoke `full
  --parallelism 1 --active-deadline-seconds 200000`; assert the captured file has **both**
  `parallelism: 1` and `activeDeadlineSeconds: 200000` simultaneously (proves one shared patched
  copy, not two divergent ones or a second overwriting the first).
- [x] 2.6 **Test first (help text documents the flag and the coupling):** add
  `test_help_documents_active_deadline_seconds_and_the_coupling_risk`: invoke `submit_workflow.sh
  help`; assert `"--active-deadline-seconds"` appears in stdout, and that the coupling
  risk/relationship with `--parallelism` is mentioned (assert a distinctive substring from the
  new header text, not just the flag name alone). Traces to the delta spec's new "Help text
  documents the flag and the coupling risk" scenario.
- [x] 2.7 **Implement:** add `ACTIVE_DEADLINE_SECONDS=""` alongside `PARALLELISM=""`; parse
  `--active-deadline-seconds` in the flag-parsing loop; in the `full)` case, restructure the
  existing `--parallelism`-only temp-copy logic per `design.md` D1's corrected snippet:
  1. Immediately after `require_image`/`provision` (both **unchanged** — do not drop the
     `provision` call), validate `$PARALLELISM`'s format (`^[1-9][0-9]*$`, `die` otherwise) if it
     is set — **before** it is used for anything else, including auto-scale in task group 3. This
     ordering is load-bearing, not stylistic: see task 3.0 below.
  2. Resolve `effective_deadline` and gate temp-copy creation on *either* `PARALLELISM` or a
     non-empty `effective_deadline`.
  3. `cp` the committed file to `$tmp` once, then apply the parallelism patch (if needed) and the
     deadline patch (if needed) as two independent anchored `sed -i` + self-verify steps on that
     same `$tmp`, each with its own `die` message (the deadline patch keeps its own
     positive-integer check too, as defense-in-depth on the explicit-flag path).
  Update the usage header (the `help` command's `sed -n` range) to document the new flag and the
  parallelism/deadline coupling risk. Re-check (and bump if needed) the hardcoded line range
  `help` prints, same discipline as the original `--parallelism` task. 2.1–2.6 pass.
- [x] 2.8 **Verify:** `uv run pytest tests/test_submit_workflow_active_deadline.py
  tests/test_submit_workflow_parallelism.py tests/test_submit_workflow_provision.py -v` — new
  tests pass, and the pre-existing parallelism AND provision tests still pass unchanged (proves
  the restructuring in 2.7 didn't regress `--parallelism`-only behavior or drop the `provision()`
  call).

---

## 3. Auto-scale fallback when `--parallelism` is overridden without an explicit deadline (issue #63, TDD, cluster-free)

- [x] 3.0 **Test first (regression guard: invalid `--parallelism` still fails cleanly once
  auto-scale exists):** add
  `test_invalid_parallelism_still_rejected_cleanly_when_autoscale_would_fire`, parametrized over
  `0`, `-1`, `abc`; invoke `full --parallelism <bad> --no-provision` with **no**
  `--active-deadline-seconds` and the **default** `--corpus-dir` (`examples/prelim_sweep`, whose
  real manifest exists, so auto-scale would actually be attempted if reached). **`--no-provision`
  is required here too** (round-2 review caught this: without it, `provision()` runs first per
  the corrected ordering and attempts `mkdir -p` on the real default
  `WORKSPACE_HOSTPATH`/`/mnt/hpi_dev/...` translation — failing with a permissions error for the
  wrong reason in most environments, and risking a real mutation of production NFS state on an
  operator's live WSL shell where the mount exists). With `--no-provision`, `provision()` is
  skipped entirely and the test exercises exactly the parallelism-validation-before-autoscale
  ordering it's named for. Assert: non-zero exit,
  `"positive integer" in result.stderr` (or equivalent clear-message check), **`"Traceback" not
  in result.stderr`**, and the stub is never invoked. This is a regression test for a validation-
  ordering bug two independent reviewers found in an earlier draft of this design: resolving
  `effective_deadline`/calling the auto-scale python one-liner *before* validating
  `$PARALLELISM`'s format lets `0` reach a `ZeroDivisionError` and `abc` reach a `ValueError` —
  both uncaught Python tracebacks, not `die()` messages. The *existing* parametrized parallelism
  test only checks the exit code, not stderr content, so it would keep "passing" while silently
  masking exactly this regression — this new test is what actually catches it. Fails against the
  design's uncorrected ordering; passes once task 2.7's validate-before-use ordering is in place
  (this task is listed under group 3, not group 2, specifically because it can only meaningfully
  fail/pass once `compute_auto_deadline_seconds` exists to be reached — write it now, but it also
  re-verifies task 2.7's ordering).
- [x] 3.1 **Test first (auto-scale fires and matches the formula on a small fixture):** add
  `test_parallelism_without_explicit_deadline_autoscales`: build a `tmp_path` corpus dir with a
  hand-written `sweep_manifest.json` using the **real production schema**
  (`{"configs": [{...}, {...}, {...}]}` — confirmed against `examples/prelim_sweep_fine/
  sweep_manifest.json`; do NOT invent a different shape like `{"n_configs": 3}`, since
  `compute_auto_deadline_seconds` reads `json.load(...)["configs"]`) containing exactly 3 config
  entries, so the expected value is hand-computable per `design.md` D2's formula:
  `ceil(3 * 2.4 / parallelism + 4) * 3600` (e.g. `43200` at `parallelism=1`); invoke `full
  --parallelism <value> --corpus-dir <fixture> --no-provision` (no `--active-deadline-seconds`);
  assert the captured file's `activeDeadlineSeconds` equals the hand-computed expected value.
  Repeat for at least two different `--parallelism` values to confirm the formula's
  parallelism-dependence, not just a hardcoded constant. Fails: auto-scale doesn't exist yet.
- [x] 3.1a **Test first (boundary: zero-config manifest):** add
  `test_autoscale_zero_configs_degenerates_to_retry_margin_only`: same fixture shape as 3.1 but
  with an empty `"configs": []`; invoke `full --parallelism 1 --corpus-dir <fixture>
  --no-provision`; assert `activeDeadlineSeconds == 14400` exactly (`ceil(0*2.4/1+4)*3600`) —
  confirms the formula degrades gracefully rather than erroring on an edge-case corpus.
- [x] 3.1b **Test first (boundary: very large `--parallelism`):** add
  `test_autoscale_with_very_large_parallelism_does_not_crash_or_underflow`: reuse 3.1's 3-config
  fixture; invoke `full --parallelism 1000000 --corpus-dir <fixture> --no-provision`; assert
  success and `activeDeadlineSeconds == 18000` (`ceil(3*2.4/1000000 + 4)*3600 =
  ceil(4.0000072)*3600 = 5*3600` — `math.ceil` rounds up past any nonzero fractional remainder,
  however tiny, so this is 5h; round-3 review caught an earlier draft wrongly asserting `14400`
  (4h) here — confirm `18000`, not `14400`, when implementing) — confirms no integer/float
  overflow and a sane floor.
- [x] 3.2 **Test first (explicit flag always wins over auto-scale):** add
  `test_explicit_active_deadline_takes_precedence_over_autoscale`: invoke `full --parallelism 1
  --active-deadline-seconds 999999 --corpus-dir <a fixture whose manifest path is intentionally
  wrong/missing> --no-provision`; assert the captured file has `activeDeadlineSeconds: 999999`
  and the command succeeds — proves auto-scale (which would fail trying to read the missing/wrong
  manifest) is never invoked when the explicit flag is given. **`--no-provision` is required**:
  `provision()` itself demands `sweep_manifest.json` exist for `full` and would `die` on this
  intentionally-broken fixture before the code path under test is ever reached — without it, the
  test would pass for the wrong reason (testing `provision()`'s pre-existing guard, not this
  proposal's precedence rule).
- [x] 3.3 **Test first (missing manifest when auto-scale would fire fails clearly):** add
  `test_autoscale_missing_manifest_fails_with_clear_message_not_a_traceback`: invoke `full
  --parallelism 2 --corpus-dir <a dir that exists but has no sweep_manifest.json> --no-provision`
  (no explicit deadline); assert non-zero exit with a `die`-style message, not a raw Python
  traceback, and the stub never invoked. **`--no-provision` is required** — same reason as 3.2:
  `provision()`'s own manifest-existence check would otherwise fire first, testing the wrong code
  path.
- [x] 3.4 **Implement:** add a `compute_auto_deadline_seconds(manifest_path, parallelism)` shell
  function per `design.md` D2's corrected version: a `command -v python3` precondition check
  (clear `die` message if absent — this script has no prior Python dependency, so this is a new,
  explicitly-guarded precondition, not an assumed one), an explicit `[[ -f "$manifest_path" ]]`
  existence check (clear `die` message, not a bare python crash), then the stdlib-only `python3
  -c` one-liner (`PER_CONFIG_HOURS = 2.4`, `RETRY_MARGIN_HOURS = 4`, `math.ceil(n *
  PER_CONFIG_HOURS / parallelism + RETRY_MARGIN_HOURS) * 3600`) wrapped with `|| die ...` to catch
  malformed JSON or an unexpected schema with one clear message rather than a bare traceback.
  Wire it into the `full)` case: `effective_deadline` resolves to `$ACTIVE_DEADLINE_SECONDS` if
  set, else `compute_auto_deadline_seconds "$CORPUS_DIR/sweep_manifest.json" "$PARALLELISM"` if
  `$PARALLELISM` is set (already validated by task 2.7's hoisted check), else empty (no patch).
  3.0–3.3, 3.1a, 3.1b pass.
- [x] 3.5 **Verify:** `uv run pytest tests/test_submit_workflow_active_deadline.py -v` — all pass,
  full file green end to end.

---

## 4. OpenSpec spec delta

- [x] 4.1 Add `openspec/changes/fix-argo-sweep-timeouts/specs/force-surrogate/spec.md` with `##
  ADDED Requirements` covering: (a) `--active-deadline-seconds` override without mutating the
  committed workflow, mirroring the existing `--parallelism` requirement's scenario structure;
  (b) the auto-scale fallback's trigger condition, formula, and precedence vs. an explicit value;
  (c) the `retryStrategy.backoff.maxDuration` bump to `4h`. Each requirement has at least one
  `#### Scenario:` block. Cross-reference the existing "Argo sweep-submission parallelism is
  overridable..." requirement as a sibling, same pattern that requirement itself used to
  reference the base "Cluster-side Argo orchestration of the corpus" requirement.
- [x] 4.2 `openspec validate fix-argo-sweep-timeouts --strict` passes with zero errors.

---

## 4a. Documentation updates (review-identified gap — both docs go stale otherwise)

- [x] 4a.1 **Update `cluster/argo/README.md`**: it documents `submit_workflow.sh`'s flags under
  `### NFS provisioning (automatic, closes #62)` (covering `--corpus-dir`/`--no-provision` in
  bullet-list style — confirmed by reading the real file; it has no section literally named
  "Flags:", that label only exists in the script's own header comment). Add a new bullet or
  subsection for `--active-deadline-seconds` (what it does, that it mirrors `--parallelism`) and
  the auto-scale fallback (when it fires, that an explicit flag always wins), and a one-line note
  that `retryStrategy.backoff.maxDuration` is now `4h`. This is the primary operator-facing doc
  for exactly the failure mode (`--parallelism` overridden, deadline forgotten) issue #63
  describes — leaving it stale defeats the point of fixing the underlying bug.
- [x] 4a.2 **Update `openspec/project.md`**: its existing Pending bullet about the 27-config
  corpus resubmission currently says something like "...needs a separate, explicit go-ahead
  (shared lab GPU quota, unverified preemption/retry path)." Edit it to reflect that the
  deadline/parallelism coupling is now fixed and the retry path now covers the full configured
  `limit: 5` sequence — following the precedent set by `add-fine-grid-corpus-full` and
  `automate-run-metadata-capture`, both of which added/edited a `project.md` bullet on landing.

---

## 5. Verification

- [x] 5.1 `uv run ruff check .` and `uv run ruff format --check .` clean.
- [x] 5.2 `uv run pytest tests/test_argo_workflows.py tests/test_submit_workflow_active_deadline.py
  tests/test_submit_workflow_parallelism.py tests/test_submit_workflow_provision.py -v` — all
  pass, including the boundary tests (3.0, 3.1a, 3.1b) and the provisioning-preserved check (2.8).
- [x] 5.3 Full suite `uv run pytest` is green — no regressions elsewhere (in particular,
  `tests/test_submit_workflow_provision.py` unaffected by the `full)` case restructuring in task
  2.7).
- [x] 5.4 `openspec validate --all --strict` — only pre-existing, unrelated failures (if any)
  remain; nothing newly introduced by this change.

---

## 6. Commit & PR discipline

- [x] 6.1 Commit grouping, each individually green under local verification (this repo
  squash-merges to `main` — confirmed via `git log --oneline` showing every merged PR as exactly
  one commit on `main`, so only the PR tip is CI-checked; intermediate-commit-green is purely
  local discipline, not a CI-enforced one, but still followed here for reviewability/
  bisectability):
  1. `chore(openspec): add fix-argo-sweep-timeouts` — the entire OpenSpec change directory
     (`proposal.md`, `design.md`, `tasks.md`, `specs/force-surrogate/spec.md` — the spec delta is
     a proposal-time artifact, already fully authored before any code change, per this repo's
     OpenSpec convention). Verify: `openspec validate fix-argo-sweep-timeouts --strict`.
  2. `fix(cluster): bump retry backoff maxDuration to 4h (#64)` — task group 1.
  3. `feat(cluster): add submit_workflow.sh --active-deadline-seconds override (#63)` — task
     group 2 only (the flag alone, mirroring `--parallelism`; on review, this is a complete,
     independently-mergeable fix for issue #63's literal ask on its own, not requiring the
     auto-scale fallback to be coherent).
  4. `feat(cluster): auto-scale deadline when parallelism is overridden without an explicit one
     (#63)` — task group 3, layered onto commit 3's files (a UX improvement on top of the flag,
     not a correctness dependency of it — reviewed and revised from an earlier single-commit plan
     for smaller, more bisectable diffs).
  5. `docs(cluster): document --active-deadline-seconds and update project.md` — task group 4a
     (`cluster/argo/README.md`, `openspec/project.md`).
- [x] 6.2 PR body/commits reference `#63` and `#64` without an unintended closing keyword unless
  actually closing them, **and must not accidentally close #65** (explicitly out of scope,
  deferred to its own future change) — grep case-insensitively over the full commit-message set
  and PR body draft before opening: `grep -inE '(clos|fix|resolv)[a-z]*:?\s*(#63|#64|#65|,\s*#
  (63|64|65))'` (widened from a #63/#64-only pattern to also catch a comma-listed `#65` sharing a
  closing verb's scope, e.g. "fixes #63, #64; see also #65" — GitHub's parser can associate a
  single leading closing verb across a comma-separated issue list).
- [x] 6.3 Single PR, opened after the full commit sequence is locally green — both issues bundled
  by design (same subsystem, diagnosed from the same two failed runs, a partial fix still leaves
  resubmission broken), not split into two PRs.
