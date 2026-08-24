## Why

`get_git_info()` (`src/mosquito_cfd/benchmarks/metadata.py`) reports
`{"error": "git not available or not a repository"}` for a valid Windows-created git worktree
when the same repo is read from WSL — even though the worktree is completely valid and
`git rev-parse HEAD` succeeds fine from the Windows side. This silently drops git provenance
(`git.commit`, `git.branch`, `git.dirty`, etc.) from `run_metadata.json` for any local run
launched via WSL against a `.claude/worktrees/<name>`-style worktree, which is exactly the setup
used for local A5000 CFD testing (see `openspec/project.md`'s "Local A5000 CFD testing"
reference). It already caused a real loss of provenance in
`examples/prelim_sweep/surrogate/run_metadata.json` (PR #71).

**Root cause**: a git worktree's `.git` is not a directory but a *pointer file* naming the real
gitdir, e.g. `gitdir: C:/repos/mosquito-cfd/.git/worktrees/<name>`. Git for Windows writes this
path in drive-letter syntax. A Linux git binary (as invoked from WSL) does not recognize
`C:/...` as absolute, treats it as a relative path, fails to resolve it, and raises the same
"not a repository" condition `get_git_info()` uses for a genuinely missing repo — so a valid
worktree and a missing repo become indistinguishable to the caller.

This is issue #77. It was previously attempted in PR #76, which had a correct, well-tested fix
but skipped this project's required OpenSpec review and approval gates (went straight from
`openspec:proposal` to code in one session). PR #76 is not being merged; this proposal redoes
the change from scratch through the full `/new-feature` workflow. Where the redesign reaches the
same conclusions as PR #76, that's expected re-derivation, not copying — the point of the gate is
that a different design was allowed to emerge if warranted, and in this case the reactive
retry-on-failure design held up under review.

Issue #66 (pod-side containers with no `.git` directory at all, hard-failing on
`extract_git_info`'s SHA validation) is a distinct root cause in a different code path
(`force_surrogate/metadata_capture.py::extract_git_info`) and is explicitly **out of scope** for
this change.

## What Changes

- **`get_git_info()`** (`src/mosquito_cfd/benchmarks/metadata.py`) gains a **reactive retry**: if
  the initial `git rev-parse HEAD` (and friends) fails, and the repo's `.git` is a *file* (a
  worktree pointer) whose content names a Windows drive-letter gitdir, translate that path to its
  WSL mount equivalent (`C:/foo/bar` → `/mnt/c/foo/bar`) and retry the same git calls once with
  `GIT_DIR`/`GIT_WORK_TREE` set accordingly, inheriting the rest of the caller's environment.
  If the repo is not a Windows-worktree-pointer case, or the retry also fails, the existing
  `{"error": "git not available or not a repository"}` behavior is unchanged.
- No other function changes. `extract_git_info`, `sidecar.py`, and pod-side metadata capture
  (issue #66's territory) are untouched.
- No retroactive patching of already-committed `run_metadata.json` files (e.g.
  `examples/prelim_sweep/surrogate/run_metadata.json`) — those remain historical record of a
  since-fixed bug, per issue #77 and user confirmation during scoping.
- A new requirement is added to the `run-metadata` spec capturing this behavior, since the
  existing spec only constrains downstream passthrough/validation of an already-produced
  `git.commit`, not `get_git_info()`'s own worktree-resolution behavior.

## Impact

- **Affected code**: `src/mosquito_cfd/benchmarks/metadata.py` (`get_git_info`, plus new private
  helpers), `tests/test_benchmarks_metadata.py` (new).
- **Affected specs**: `run-metadata` (new requirement; no existing requirement modified).
- **Docker images**: `get_git_info()` IS compiled into the `:fp64`/`:python` images (via `COPY
  src/`) and IS executed pod-side by `run_one_config.py` on every cluster run (through
  `capture_surrogate_run_metadata` → `capture_run_metadata`). However, the retry path added here
  is unreachable there: the image's `COPY` list never includes `.git`, so pod-side `.git` doesn't
  exist at all (neither directory nor worktree pointer), `_worktree_retry_env` returns `None`, and
  pod-side output is byte-for-byte unchanged. This is issue #66's territory (pod-side git-less
  containers) and stays out of scope for this change.
- **Not affected**: CI (no workflow/Dockerfile touches this code path), the CFD solver,
  `extract_git_info` (the separate downstream *reader* of an already-written pod-side
  `run_metadata.json`, issue #66), any committed `run_metadata*.json` files.
- **Reproducibility**: strictly additive — a case that previously silently lost git provenance
  now captures it correctly; the common (non-worktree) path is byte-for-byte unchanged.
