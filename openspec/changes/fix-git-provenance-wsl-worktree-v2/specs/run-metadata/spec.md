## ADDED Requirements

### Requirement: get_git_info resolves Windows-created worktrees when read from a Linux git binary

`get_git_info()` SHALL correctly recover git provenance (`commit`, `branch`, `dirty`, `diff_hash`
if dirty, `repository`) when invoked against a git worktree whose `.git` pointer file names a
gitdir using a Windows drive-letter path (e.g. `gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo`)
even when the invoking `git` binary is a Linux binary that cannot parse that path as absolute
(e.g. `git` run from WSL against a Windows-created worktree). On the first git invocation
failing, it SHALL check whether `.git` at the target repo path is a file (not a directory) whose
content matches a Windows drive-letter gitdir pattern; if so, it SHALL translate that path to its
`/mnt/<lowercase-drive>/...` equivalent and retry the git invocation once with `GIT_DIR` and
`GIT_WORK_TREE` set accordingly (inheriting the rest of the caller's environment). It SHALL NOT
alter behavior, output, or subprocess call count for any case where the first invocation succeeds,
where `.git` is a real directory, or where `.git` is a worktree pointer using a POSIX-style path.
It SHALL NOT raise any exception under any of these conditions — including a nonexistent or
non-directory `repo_path`, or a `.git` pointer file containing non-UTF-8 byte content — returning
the same honest error dict in every unresolvable case instead.

#### Scenario: Windows-worktree gitdir is translated and retried successfully

- **GIVEN** a repo directory whose `.git` is a file containing
  `gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo`, and the initial `git rev-parse HEAD` call
  against that directory fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it retries with `GIT_DIR=/mnt/c/repos/mosquito-cfd/.git/worktrees/foo` and
  `GIT_WORK_TREE=<repo_path>` set (merged with the caller's inherited environment), and if that
  retry succeeds, returns the full git-info dict (`commit`, `branch`, `dirty`, `repository`) with
  no `error` key

#### Scenario: non-worktree failure is not retried

- **GIVEN** a directory with no `.git` at all (or a `.git` directory, not a pointer file), and the
  initial `git rev-parse HEAD` call fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it makes exactly one git invocation attempt (no retry) and returns
  `{"error": "git not available or not a repository"}`, identical to current behavior

#### Scenario: POSIX-style worktree pointer is not misinterpreted as a Windows path

- **GIVEN** a repo directory whose `.git` is a file containing a POSIX-style gitdir path (e.g.
  `gitdir: /home/user/repo/.git/worktrees/foo`), and the initial git invocation fails
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** no retry is attempted (the path does not match the Windows drive-letter pattern), and
  the existing `{"error": "git not available or not a repository"}` result is returned

#### Scenario: retry also fails, honest error is preserved

- **GIVEN** a repo directory whose `.git` is a file naming a Windows-style gitdir path, and both
  the initial invocation and the retry (with translated `GIT_DIR`/`GIT_WORK_TREE`) fail
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` — the same honest
  failure as today, with no fabricated or partial git-info fields

#### Scenario: common case (first attempt succeeds) is unaffected

- **GIVEN** a normal repo directory (or a worktree already resolvable in the current environment)
  where the initial `git rev-parse HEAD` call succeeds
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns the same git-info dict it would have returned before this change, and the
  worktree-pointer-check/retry logic is never invoked

#### Scenario: no repo_path given resolves against the current working directory

- **GIVEN** the process's current working directory is itself a Windows-created worktree whose
  `.git` names a Windows drive-letter gitdir, and the initial git invocation — run with
  `cwd=repo_dir`, where `repo_dir` has resolved to `Path.cwd()` since no `repo_path` was given —
  fails
- **WHEN** `get_git_info()` is called with no argument (matching the real production call sites in
  `capture_run_metadata()` and `sweep.py`'s `_git_commit()`, neither of which pass `repo_path`)
- **THEN** the worktree-pointer check and retry are performed against that same resolved
  `repo_dir`, and on a successful retry the full git-info dict is returned exactly as it would be
  for an explicit `repo_path`

#### Scenario: pathological inputs degrade to the honest error, never an unhandled exception

- **GIVEN** either (a) a `repo_path` pointing at a directory that does not exist (or a file, not
  a directory), or (b) a `.git` pointer file whose content is not valid UTF-8
- **WHEN** `get_git_info(repo_path)` is called
- **THEN** it returns `{"error": "git not available or not a repository"}` without raising
  `NotADirectoryError`, `FileNotFoundError`, `UnicodeDecodeError`, or any other exception to the
  caller
