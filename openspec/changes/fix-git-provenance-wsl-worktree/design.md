## Context

`get_git_info(repo_path)` runs four `git` subprocess calls against `repo_path` (or `Path.cwd()`).
Today, if the very first one (`git rev-parse HEAD`) fails, the whole function gives up and returns
`{"error": "git not available or not a repository"}`. That's the right behavior when git is truly
absent or the directory truly isn't a repo — but it's also what happens when a Linux git binary
(WSL) can't parse a Windows-written worktree `gitdir:` pointer, which is a resolvable path
problem, not an absence of git or of a repository.

## Goals / Non-Goals

- **Goal:** when the failure is specifically "a worktree pointer file names a Windows-absolute
  path a POSIX git can't parse," resolve it ourselves and retry, rather than reporting failure.
- **Goal:** never regress the existing honest-failure behavior for every other cause (no git
  binary, directory truly isn't a repo, permissions, etc.) — the fallback must still fire for
  those, unchanged.
- **Non-goal:** handle the mirror-image case (a Linux-created worktree read by Windows git). Git
  for Windows' own git.exe already understands POSIX-style paths reasonably well in most
  configurations, and no failure of that direction has been observed; adding untested handling
  for a case with no evidence it occurs would be speculative.
- **Non-goal:** any change to where or how git worktrees get created. This fix only touches how
  `get_git_info()` *reads* an existing worktree.

## Decision: read-time retry with a translated env, not a rewritten pointer file

**Chosen: detect-and-retry inside `get_git_info()`.** Read `<repo>/.git`; if it is a *file* (a
worktree pointer, never true of a normal repo's real gitdir *directory*) and its `gitdir:` value
matches a Windows drive-letter absolute path (`^[A-Za-z]:[\\/]`), translate it to
`/mnt/<lowercase-drive>/<rest, forward-slashed>` and retry the same git calls with
`GIT_DIR=<translated>` / `GIT_WORK_TREE=<repo_path>` merged into the subprocess environment.

**Rejected: rewrite the `.git` pointer file itself to a POSIX path.** This would fix WSL-side git
but break Windows-side git, which does not resolve `/mnt/c/...` — trading one platform's failure
for the other's on the very same worktree. The retry approach fixes the *read*, in the Python
layer, without touching on-disk git state at all; both platforms keep working independently.

**Rejected: a general-purpose Windows↔WSL path-translation utility shared across the codebase.**
`cluster/argo/scripts/submit_workflow.sh` already has its own `to_local_path` for NFS path mapping
— a different mapping (`/hpi/hpi_dev/...` → `/mnt/hpi_dev/...`) for a different purpose (cluster
submission, not git). Unifying them would require reconciling two mapping schemes (drive-letter
vs. a fixed NFS mount prefix) for no immediate benefit; scope this fix narrowly to the one
proven-real case instead.

**Rejected: retroactively patch already-produced `run_metadata.json` files.** Considered and
explicitly rejected in `fix-force-surrogate-sweep-hinge`'s own `tasks.md` — the correct historical
git state for a past run can't be reconstructed without literally checking out an old commit
(riskier than leaving an honest error marker), and retraining to regenerate it would perturb
already-verified, non-bitwise-reproducible numbers. This change only prevents the bug from
recurring; it does not touch existing artifacts.

## Risks / Trade-offs

- The retry only fires when the *first* attempt fails — a real repository that always succeeds
  (the overwhelming common case, including every CI run) takes the exact same code path as today,
  at the exact same cost (one subprocess call, not two).
- The Windows-path regex is intentionally conservative (`^[A-Za-z]:[\\/]`) — anything that doesn't
  match falls straight through to the existing error fallback, so a malformed or unexpected
  `.git` pointer file can't cause a new class of failure; the worst case is identical to today's
  behavior.
- No sanity check that the translated `/mnt/<drive>/...` path actually exists before retrying —
  the retry attempt's own success/failure *is* the check. This keeps the logic simple and testable
  (mock `subprocess.run`, no real filesystem probing needed) and avoids a second way for the
  detection logic itself to be subtly wrong.
