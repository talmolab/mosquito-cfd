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

## 6. Fixes found by `/review-pr`'s 5-agent team on PR #83 itself

- [x] 6.1 **BLOCKING (spec)**: the `## MODIFIED Requirements` delta silently dropped 6 of the
  base requirement's 13 scenarios (only 7 existing + 1 new were included) — would have deleted
  those scenarios from the canonical spec on archive. Fixed: regenerated the delta from the
  actual current committed spec text, all 13 existing scenarios plus 2 new ones (see 6.2) = 15.
- [x] 6.2 **BLOCKING (correctness), live-reproduced by the reviewer**: an exact-path-identity
  check alone is insufficient — if `--corpus-dir` is nested inside `--workspace-hostpath`'s own
  `inputs/` tree (coincidentally-matching basename deep in the path), the two real paths are
  genuinely different, yet `rm -rf "$local_workspace/inputs"` still destroys `corpus_dir`
  entirely. Fixed: the check is now a symmetric ancestor-or-equal comparison
  (`"${corpus_real}/" == "${workspace_real}/"* || "${workspace_real}/" == "${corpus_real}/"*`),
  not a bare `!=`. New regression test:
  `test_provision_dies_when_corpus_dir_is_nested_inside_workspace_hostpaths_inputs`.
- [x] 6.3 **Documented, not fixed**: on a case-**in**sensitive filesystem (this repo's own
  Windows/Git-Bash dev environment, empirically confirmed by the reviewer — NOT the real
  WSL/Linux production target), two differently-cased paths naming the same real directory
  bypass the check (`realpath -m` does not case-fold). Accepted as a known, documented
  limitation (code comment + proposal.md) rather than adding runtime filesystem-case-sensitivity
  detection — disproportionate complexity for a gap that doesn't reach the real target
  environment.
- [x] 6.4 **IMPORTANT (testing)**: the symlink case was asserted in the code comment/proposal
  but never tested, despite being feasible on `ubuntu-latest` CI. Fixed: new test
  `test_provision_dies_when_workspace_hostpath_is_a_symlink_to_corpus_dir` (skips gracefully on
  a dev machine that can't create symlinks without elevation — still runs fully on CI).
- [x] 6.5 **IMPORTANT (docs)**: `proposal.md`'s GNU-coreutils justification cited `sed -i` as an
  existing precedent in this script — factually wrong (only `sed -n`/`sed -E` are used, no
  `sed -i`). Fixed: corrected to accurately say `realpath` is a genuinely new dependency,
  justified by the real `mktemp --suffix=` precedent instead.
- [x] 6.6 **Verify**: `uv run pytest tests/test_submit_workflow_provision.py -v` — 26 passed, 1
  skipped (symlink test, environment-gated); `openspec validate fix-provision-same-path-data-loss
  --strict` passes; full suite green.

## 7. Fixes found by round-2 `/review-pr` on PR #83 (verifying round 1's fixes + fresh findings)

- [x] 7.1 **IMPORTANT (correctness), live-reproduced by the reviewer**: the fix only guarded
  `--corpus-dir`/`--workspace-hostpath`; `WING_VERTEX_SOURCE` had no analogous same-path/nesting
  check against the resolved workspace. If `WING_VERTEX_SOURCE` resolves at or under
  `$local_workspace` (e.g. inside the `inputs/` tree the replace-not-merge step wipes, or
  exactly at the destination `wing.vertex` path), the canonical source could be deleted or
  corrupted before the final `cp` reads from it — the identical defect class, just for the wing
  source. Fixed: the same equal-to-or-nested-inside check now also applies to
  `WING_VERTEX_SOURCE`. New regression test:
  `test_provision_dies_when_wing_vertex_source_is_inside_workspace_hostpath`.
- [x] 7.2 **IMPORTANT (testing)**: the sibling-prefix disambiguation (e.g. `.../staging` vs
  `.../staging_other`) was verified correct by hand-tracing the bash glob logic, but had zero
  regression-test coverage — a future "simplification" to a bare substring comparison could
  silently reintroduce a false positive with nothing to catch it. Fixed: new test
  `test_provision_does_not_false_positive_on_sibling_prefix_paths`, using matching basenames
  with prefix-related parent directories so it actually reaches the new check's logic (a
  `prelim_sweep`/`prelim_sweep_fine`-style pair never reaches it at all — the pre-existing
  basename-mismatch guard rejects it first).
- [x] 7.3 **IMPORTANT (spec fidelity)**: the requirement's normative SHALL prose only described
  rejecting "the same real filesystem path" (identity/aliasing) — it never stated the
  ancestor/nesting rule in SHALL language, even though task 6.2's scenario and the shipped code
  both enforce it. Fixed: the SHALL prose now states the equal-to-or-nested-inside rule
  directly, and a new sentence extends it to `WING_VERTEX_SOURCE` per 7.1. Two new scenarios
  added (`WING_VERTEX_SOURCE` nesting, sibling-prefix non-false-positive) — 15 → 17 total
  scenarios in the delta.
- [x] 7.4 **Verify**: `uv run pytest tests/test_submit_workflow_provision.py -v` — 28 passed, 1
  skipped; `openspec validate fix-provision-same-path-data-loss --strict` passes; full suite
  (`uv run pytest`) — 766 passed, 20 skipped, 0 failed.
