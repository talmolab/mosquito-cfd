## ADDED Requirements

### Requirement: git provenance resolves across a Windows-created worktree read from WSL

`get_git_info` SHALL detect when its primary git invocation fails because the target directory is
a git *worktree* whose `.git` pointer file names a Windows-style absolute path
(`gitdir: C:/...` or `gitdir: C:\...`) that the running (Linux) git binary cannot parse as
absolute, and SHALL retry once with that path translated to its WSL-mounted equivalent
(`/mnt/<drive>/...`) via an explicit `GIT_DIR`/`GIT_WORK_TREE` override, before falling back to
the existing `{"error": ...}` result. It SHALL NOT attempt this retry when `.git` is a real
directory (a non-worktree repository), when the pointer file's target is not a Windows-style
absolute path, or when the retry itself also fails — in every such case the existing honest
`{"error": "git not available or not a repository"}` fallback is unchanged.

#### Scenario: Windows-worktree gitdir pointer is resolved on retry

- **GIVEN** a directory whose `.git` is a file containing
  `gitdir: C:/repos/mosquito-cfd/.git/worktrees/my-worktree`, and a git binary that fails to
  resolve that path directly but succeeds when `GIT_DIR=/mnt/c/repos/mosquito-cfd/.git/worktrees/my-worktree`
  and `GIT_WORK_TREE=<the directory>` are set
- **WHEN** `get_git_info` is called with that directory as `repo_path`
- **THEN** the result contains a real `commit`/`branch`/`dirty` block (not `"error"`), sourced
  from the retried invocation

#### Scenario: a genuinely missing repository still reports the honest error

- **GIVEN** a directory with no `.git` at all, or whose `.git` is a file naming a path that is
  not Windows-style absolute (e.g. an ordinary Linux-created worktree pointer, or a malformed
  pointer)
- **WHEN** `get_git_info` is called with that directory as `repo_path`
- **THEN** the result is `{"error": "git not available or not a repository"}`, unchanged from
  today, with no retry attempted

#### Scenario: a Windows-style pointer that still fails to resolve on retry reports the honest error

- **GIVEN** a `.git` pointer file naming a Windows-style absolute path, but the translated
  `/mnt/<drive>/...` path does not correspond to a real gitdir (the retried git invocation also
  fails)
- **WHEN** `get_git_info` is called with that directory as `repo_path`
- **THEN** the result is `{"error": "git not available or not a repository"}` — the function
  never fabricates a commit hash when both attempts fail
