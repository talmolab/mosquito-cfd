## Tasks

### Phase 1 — TDD: pure translation helper (cluster-free, no subprocess/filesystem)

1. [x] Create `tests/test_benchmarks_metadata.py` (no dedicated test file exists today for
   `mosquito_cfd.benchmarks.metadata`). Write `test_translate_windows_worktree_gitdir_forward_slashes`:
   `"gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo"` → `/mnt/c/repos/mosquito-cfd/.git/worktrees/foo`.
   Must fail with `ImportError`/`AttributeError` first (the function doesn't exist yet).
2. [x] Write `test_translate_windows_worktree_gitdir_backslashes`: the same path with backslashes
   (`"gitdir: C:\\repos\\mosquito-cfd\\.git\\worktrees\\foo"`) normalizes to the identical
   forward-slashed result.
3. [x] Write `test_translate_windows_worktree_gitdir_lowercase_drive_letter`: an already-lowercase
   drive letter (`c:/...`) still resolves correctly (case-insensitive match, lowercase output).
4. [x] Write `test_translate_windows_worktree_gitdir_rejects_posix_path`: a normal Linux-created
   worktree pointer (`"gitdir: /home/user/repo/.git/worktrees/foo"`) returns `None` — nothing to
   translate, not a bug to retry.
5. [x] Write `test_translate_windows_worktree_gitdir_rejects_malformed_input`: a bare drive letter
   with no separator (`"gitdir: Cfoo"`) and an empty string both return `None` (conservative — no
   guessing on ambiguous input).
6. [x] Implement `_translate_windows_worktree_gitdir(gitdir_line: str) -> str | None` in
   `src/mosquito_cfd/benchmarks/metadata.py` per `design.md`. Run tasks 1-5 green.

### Phase 2 — TDD: worktree-pointer detection (tmp_path, still no real git/subprocess)

7. [x] Write `test_worktree_retry_env_reads_windows_pointer_file`: a `tmp_path` with a `.git`
   *file* containing a Windows-style `gitdir:` line returns
   `{"GIT_DIR": "/mnt/c/...", "GIT_WORK_TREE": str(tmp_path)}`.
8. [x] Write `test_worktree_retry_env_returns_none_for_real_gitdir_directory`: a `tmp_path` whose
   `.git` is a real *directory* (not a worktree pointer) returns `None` — never attempt the
   translation/retry path for an ordinary repository.
9. [x] Write `test_worktree_retry_env_returns_none_when_git_pointer_is_not_windows_style`: a
   `tmp_path` with a `.git` file naming a POSIX path returns `None`.
10. [x] Write `test_worktree_retry_env_returns_none_when_no_git_at_all`: a `tmp_path` with no
    `.git` entry at all returns `None`.
11. [x] Implement `_worktree_retry_env(repo_dir: Path) -> dict[str, str] | None` per `design.md`,
    using task 6's helper. Run tasks 7-10 green.

### Phase 3 — TDD: `get_git_info`'s retry integration (monkeypatched `subprocess.run`)

12. [x] Write `test_get_git_info_retries_with_translated_env_on_worktree_failure`: `tmp_path` has
    a Windows-style `.git` pointer file (per task 7's fixture shape); monkeypatch
    `metadata.subprocess.run` so a call with no matching `GIT_DIR`/`env=None` raises
    `subprocess.CalledProcessError`, but a call whose `env` contains the exact translated
    `GIT_DIR`/`GIT_WORK_TREE` succeeds with a fake `commit`/`branch`/`diff`/`remote` sequence.
    Assert `get_git_info(tmp_path)` returns the successfully-resolved `commit`/`branch`/`dirty`
    block (not `"error"`) — this is the spec's first scenario. Must fail first (no retry logic
    exists yet).
13. [x] Write `test_get_git_info_falls_back_to_error_when_retry_also_fails`: same Windows-style
    pointer fixture, but the monkeypatched `subprocess.run` raises `CalledProcessError` for *every*
    call regardless of `env`. Assert the result is exactly
    `{"error": "git not available or not a repository"}` — the second spec scenario (never
    fabricate a commit when both attempts fail).
14. [x] Write `test_get_git_info_does_not_retry_for_non_worktree_failure`: `tmp_path` has no
    `.git` at all (a genuinely-missing-repo case); monkeypatch `subprocess.run` to raise
    `CalledProcessError` and assert it is called exactly once (no retry attempted) and the result
    is the unchanged `{"error": ...}` fallback — the spec's third scenario, and a regression guard
    against ever retrying for the wrong reason.
15. [x] Write `test_get_git_info_unaffected_when_first_attempt_succeeds`: a normal (non-worktree)
    repo where the first `subprocess.run` call succeeds — assert the retry path is never invoked
    (e.g. via a monkeypatched `_worktree_retry_env` that would raise if called) and the returned
    shape (`commit`, `branch`, `dirty`, `diff_hash` when dirty, `repository`) is unchanged from
    today's behavior. Locks in zero regression for the common case.
16. [x] Refactor `get_git_info` to extract the existing subprocess-calling body into
    `_collect_git_info(cwd: str, env: dict[str, str] | None) -> dict[str, Any]` (raises on the
    primary `rev-parse` failure, exactly as today), then have `get_git_info` try it with
    `env=None`, catch failure, attempt `_worktree_retry_env`, retry once if it returned an
    override, and fall back to the honest error dict if both attempts fail. Update `get_git_info`'s
    docstring to describe the retry. Run tasks 12-15 green.

### Phase 4 — verification and sign-off

17. [x] `uv run pytest` — full suite green, no regressions in any existing consumer
    (`capture_run_metadata`, `capture_surrogate_run_metadata`, and their own test files).
18. [x] `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` clean.
19. [x] `openspec validate fix-git-provenance-wsl-worktree --strict` passes.
20. [x] Manual spot-check on the actual environment that surfaced this bug: from WSL, with the
    fix in place and *without* manually exporting `GIT_DIR`/`GIT_WORK_TREE`, run
    `uv run python -c "from mosquito_cfd.benchmarks.metadata import get_git_info; print(get_git_info())"`
    from inside a Windows-created worktree under `.claude/worktrees/` and confirm it now reports a
    real commit instead of `{"error": ...}`. Confirmed against this very worktree
    (`fix-git-provenance-wsl-worktree`, itself Windows-created): `git.commit` resolved to
    `3c91e394a9815ff26b8af36364a7831be63fec7e`, `branch` to
    `worktree-fix-git-provenance-wsl-worktree`, with no manual env var export.
21. [x] `/pre-merge-check`.
