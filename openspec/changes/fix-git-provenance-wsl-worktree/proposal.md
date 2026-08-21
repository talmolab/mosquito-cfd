## Why

`get_git_info()` (`src/mosquito_cfd/benchmarks/metadata.py`) is the single source of the
`git.commit`/`branch`/`dirty`/`diff_hash` block every `run_metadata.json` in this repo carries
(CC-1, `run-metadata` spec). It silently falls back to `{"error": "git not available or not a
repository"}` whenever its underlying `git rev-parse HEAD` subprocess call fails for any reason —
correct, honest behavior for a genuinely missing git binary or a non-repository directory.

But it also fires that same fallback for a case that is neither: a **git worktree created by Git
for Windows and later read by a Linux git binary (as run inside WSL)**. A worktree's `.git` is not
a directory but a *pointer file* naming where the real gitdir lives — e.g.
`gitdir: C:/repos/mosquito-cfd/.git/worktrees/<name>`. Git for Windows writes that path in Windows
drive-letter syntax. A Linux git does not recognize `C:/...` as absolute (POSIX absolute paths
start with `/`), so it treats the whole string as *relative*, concatenates it onto the current
working directory, and fails to find any such path — reporting exactly the same
"not a git repository" condition `get_git_info()` already handles, but for a worktree that is in
fact perfectly valid.

This was found and confirmed while training the Track B force-surrogate on the local A5000 via
WSL2 against a Windows-created worktree (`fix-force-surrogate-sweep-hinge`,
`examples/prelim_sweep/surrogate/run_metadata.json`): the resulting `run_metadata.json` lost its
`git.commit` entirely, even though the worktree was completely valid and `git rev-parse HEAD` on
the Windows side of the same checkout resolved fine.

## What Changes

- **`get_git_info()` retries once with a translated `GIT_DIR`/`GIT_WORK_TREE`** when its first
  attempt fails: it reads `<repo>/.git` (only if it's a *file*, i.e. a worktree pointer, never a
  real gitdir directory), and if that file's `gitdir:` value is a Windows-style absolute path
  (`C:/...` or `C:\...`), translates it to the WSL-mounted equivalent (`/mnt/c/...`) and retries
  the same git subprocess calls with that env override. If the retry also fails (or there was
  nothing to translate), the existing honest `{"error": ...}` fallback is unchanged.
- No other call site changes: `capture_run_metadata()`, `capture_surrogate_run_metadata()`, and
  every consumer of `git.commit`/`git.error` keep their current contract. This is a pure
  robustness fix inside `get_git_info()`.
- New dedicated unit tests for `mosquito_cfd.benchmarks.metadata` (no such file exists today —
  `get_git_info` is currently only exercised indirectly through higher-level capture functions).

## Non-goals (explicit)

- **Not retroactively patching already-produced `run_metadata.json` files** that hit this bug
  before the fix (e.g. the one found in `fix-force-surrogate-sweep-hinge`). Reconstructing the
  historical git state (which commit was `HEAD`, what the working-tree diff looked like) for a
  run that already completed is knowable in principle but risks encoding a subtly wrong
  historical state; the existing honest `"error"` marker for that one run is left as a disclosed,
  accepted residual (see that change's `tasks.md`).
- **Not rewriting the worktree's `.git` pointer file** to a WSL-style path. That would break
  Windows-side git (Git for Windows does not resolve `/mnt/c/...`), trading one platform's
  breakage for the other's. The retry lives entirely in the Python metadata layer, at read time,
  and touches no on-disk git state.
- **Not a general Windows/WSL path-translation utility.** The translation logic here is scoped
  narrowly to a worktree's `gitdir:` pointer content, not a reusable path-mapping helper for other
  parts of the codebase (`cluster/argo/scripts/submit_workflow.sh`'s `to_local_path` already
  solves an analogous but distinct problem — NFS path mapping for cluster submission — and is not
  touched by this change).

## Impact

- Affected specs: `run-metadata` (`ADDED Requirements` delta).
- Affected code: `src/mosquito_cfd/benchmarks/metadata.py` (`get_git_info`, two new private
  helpers); new `tests/test_benchmarks_metadata.py`.
- No data/artifact changes, no cluster cost, no CI/Docker changes. Cluster-free: the new tests
  exercise the translation/retry logic with `monkeypatch`, never touching real git or a real WSL
  environment (CI runs a single `ubuntu-latest` job with a normal, non-worktree checkout, so the
  existing fast path is what CI already exercises either way).
