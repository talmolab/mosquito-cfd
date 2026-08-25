# Tasks — fix-provision-same-path-data-loss

TDD throughout. Branch: `fix-provision-same-path-data-loss` (off `main`). Cluster-free.

---

## 1. Regression tests (TDD)

- [x] 1.1 **Test first (identical literal paths):** in `tests/test_submit_workflow_provision.py`,
  add `test_provision_dies_before_deleting_inputs_when_corpus_dir_equals_workspace_hostpath`:
  build a corpus dir with `_make_corpus`, invoke `full --corpus-dir <dir> --workspace-hostpath
  <same dir>`; assert non-zero exit, a clear `die`-style message (not a raw `cp:` error), the
  corpus's `inputs/` directory **still exists** on disk afterward (the load-bearing assertion —
  proves the check ran before the destructive `rm -rf`, not just that the command eventually
  failed), and the stub `argo` never invoked. Fails against the current code: the `rm -rf`/`cp`
  sequence runs, deleting `inputs/` and producing a raw `cp: cannot stat ...` message, not a
  clean `die()`.
- [x] 1.2 **Test first (equivalent but differently-spelled paths):** add
  `test_provision_dies_when_corpus_dir_and_workspace_hostpath_resolve_to_the_same_real_path`:
  same corpus dir, but pass `--workspace-hostpath` as the corpus dir's path with a trailing
  slash appended (or via a `./`-relative spelling) — a different string, same real directory.
  Assert the same outcome as 1.1. Fails for the same reason (the existing basename-only check
  compares basenames, not real paths, and a trailing-slash/relative spelling still has a
  different-looking string that the current code never resolves).
- [x] 1.3 **Test first (distinct real paths still provision normally):** add/confirm a test (may
  already exist in the file) that a normal `--corpus-dir`/`--workspace-hostpath` pair pointing
  at genuinely different directories still provisions successfully — this new check must not
  false-positive on the common case. If an existing passing test already covers this
  (`test_provision_copies_and_verifies_by_hash_for_full` or similar), just confirm it still
  passes after 1.4's implementation; don't duplicate it.

## 2. Implementation (TDD)

- [x] 2.1 **Implement:** in `provision()`, after the existing basename-match guard and before
  `mkdir -p "$local_workspace"`, add: resolve `corpus_dir` and `local_workspace` via `realpath
  -m` (no existence requirement — `local_workspace` may not exist yet), compare, `die` with a
  clear message naming both the original and resolved paths if they match. 1.1–1.3 pass.
- [x] 2.2 **Verify:** `uv run pytest tests/test_submit_workflow_provision.py -v` — all pass,
  including every pre-existing test in the file (no regression).

## 3. OpenSpec spec delta

- [x] 3.1 Add `openspec/changes/fix-provision-same-path-data-loss/specs/force-surrogate/spec.md`
  with a `## MODIFIED Requirements` delta on "Argo sweep-submission provisions the NFS workspace
  before submitting" — full existing requirement text plus the new same-real-path precondition,
  plus a new `#### Scenario:` for it.
- [x] 3.2 `openspec validate fix-provision-same-path-data-loss --strict` passes.

## 4. Verification

- [x] 4.1 `uv run ruff check cluster/argo/scripts/submit_workflow.sh tests/
  test_submit_workflow_provision.py` (the test file only — the shell script isn't a ruff target)
  and `uv run ruff format --check tests/test_submit_workflow_provision.py` clean.
- [x] 4.2 Full suite `uv run pytest` green.
- [x] 4.3 `openspec validate --all --strict` — only pre-existing, unrelated failures remain.

## 5. Commit & PR

- [x] 5.1 Single commit (small, focused fix): `openspec/changes/.../`, `submit_workflow.sh`,
  `tests/test_submit_workflow_provision.py` together — this fix is too small to warrant
  splitting by concern the way `fix-argo-sweep-timeouts` did.
- [x] 5.2 Open PR referencing the finding's origin (PR #82's second review round) without an
  unintended closing keyword on any unrelated issue.
