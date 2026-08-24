## 1. Path-translation helper (TDD)

- [x] 1.1 Write `test_translate_windows_worktree_gitdir_forward_slashes`: given
      `"gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo"`, assert the helper returns
      `"/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"`. Verify it fails (function doesn't exist
      yet) before implementing.
- [x] 1.2 Write `test_translate_windows_worktree_gitdir_backslashes`: given a backslash-variant
      gitdir line (`"gitdir: C:\\repos\\mosquito-cfd\\.git\\worktrees\\foo"`), assert it
      normalizes to the same forward-slash `/mnt/c/...` result as 1.1.
- [x] 1.3 Write `test_translate_windows_worktree_gitdir_lowercase_drive_letter`: given a
      lowercase-drive variant (`"gitdir: c:/repos/..."`), assert it still matches and lowercases
      consistently in the output.
- [x] 1.4 Write `test_translate_windows_worktree_gitdir_rejects_posix_path`: given a POSIX-style
      gitdir line (`"gitdir: /home/user/repo/.git/worktrees/foo"`), assert the helper returns
      `None`.
- [x] 1.5 Write `test_translate_windows_worktree_gitdir_rejects_malformed_input`: given malformed
      content (e.g. `"Cfoo"`, `""`, a line with no `gitdir:` prefix and no drive letter), assert
      `None` is returned rather than raising.
- [x] 1.6 Write `test_translate_windows_worktree_gitdir_strips_trailing_newline`: given
      `"gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n"` (matching how git actually writes
      `.git` pointer files — trailing `\n` included), assert the helper still returns
      `"/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"` with no embedded newline. *(Added during
      `/review-openspec`: TDD-reviewer IMPORTANT finding — real pointer files always end in `\n`
      and no original test covered it.)*
- [x] 1.7 Write `test_translate_windows_worktree_gitdir_mixed_separators`: given
      `"gitdir: C:/repos\\mosquito-cfd/.git/worktrees/foo"` (forward and back slashes mixed in one
      line — plausible in the wild since git sometimes mixes them), assert it still normalizes to
      `"/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"`. *(Added during `/review-openspec`:
      TDD-reviewer IMPORTANT finding — 1.2's pure-backslash case doesn't cover this.)*
- [x] 1.8 Implement `_translate_windows_worktree_gitdir(gitdir_line: str) -> str | None` in
      `src/mosquito_cfd/benchmarks/metadata.py` until tests 1.1-1.7 pass.

## 2. Retry-environment builder (TDD)

- [x] 2.1 Write `test_worktree_retry_env_reads_windows_pointer_file`: given a temp dir containing
      a `.git` file with Windows-style gitdir content, assert
      `_worktree_retry_env(repo_dir)` returns `{"GIT_DIR": "/mnt/c/...", "GIT_WORK_TREE": str(repo_dir)}`.
- [x] 2.2 Write `test_worktree_retry_env_returns_none_for_real_gitdir_directory`: given a temp dir
      where `.git` is a real directory (e.g. `(tmp_path / ".git").mkdir()`), assert the function
      returns `None` without attempting to read it as a file.
- [x] 2.3 Write `test_worktree_retry_env_returns_none_when_git_pointer_is_not_windows_style`:
      given a `.git` file with POSIX-style gitdir content, assert `None` is returned.
- [x] 2.4 Write `test_worktree_retry_env_returns_none_when_no_git_at_all`: given a temp dir with
      no `.git` path at all, assert `None` is returned (no exception).
- [x] 2.5 Implement `_worktree_retry_env(repo_dir: Path) -> dict[str, str] | None` until tests
      2.1-2.4 pass.

## 3. `get_git_info` retry integration (TDD)

- [x] 3.1 Write `test_get_git_info_unaffected_when_first_attempt_succeeds`: mock
      `subprocess.run` to succeed on the first call for all git invocations; assert the returned
      dict matches current behavior exactly and that `_worktree_retry_env` is never called (e.g.
      via a mock that raises if invoked, or a call-count assertion).
- [x] 3.2 Write `test_get_git_info_does_not_retry_for_non_worktree_failure`: mock
      `subprocess.run` to fail (or use a real temp dir with no `.git`) with no worktree pointer
      present; assert exactly one subprocess invocation attempt (no retry) and the existing
      `{"error": "git not available or not a repository"}` result.
- [x] 3.3 Write `test_get_git_info_does_not_retry_for_posix_worktree_pointer`: against a real temp
      dir whose `.git` is a file with POSIX-style gitdir content, call `get_git_info(repo_dir)`
      directly (not just the lower-level `_translate_windows_worktree_gitdir`/`_worktree_retry_env`
      helpers) and assert no retry occurs and the existing error result is returned. *(Added
      during `/review-openspec`: TDD-reviewer noted this scenario was only exercised at the
      helper level, not end-to-end through `get_git_info` itself.)*
- [x] 3.4 Write `test_get_git_info_retries_with_translated_env_on_worktree_failure`: mock
      `subprocess.run` so the first invocation (no env override) fails and a subsequent
      invocation (called with the translated `GIT_DIR`/`GIT_WORK_TREE` merged into
      `os.environ`) succeeds, against a temp dir with a Windows-style `.git` pointer file;
      assert the final result is the full git-info dict with no `error` key, and assert the
      retry call's `env` argument contains the translated `GIT_DIR`/`GIT_WORK_TREE` plus the
      rest of `os.environ` (not a minimal/explicit-only env).
- [x] 3.5 Write `test_get_git_info_falls_back_to_error_when_retry_also_fails`: mock
      `subprocess.run` so both the initial call and the retry (with translated env) fail; assert
      the result is `{"error": "git not available or not a repository"}` with no fabricated
      partial fields.
- [x] 3.6 Write `test_get_git_info_resolves_cwd_when_no_repo_path_given`: using
      `monkeypatch.chdir()` into a fixture temp dir whose `.git` is a Windows-style worktree
      pointer (no `repo_path` argument passed), with `subprocess.run` **mocked** so the first
      invocation (no env override) fails and the retry (called with the translated
      `GIT_DIR`/`GIT_WORK_TREE` merged into `os.environ`) succeeds — the same mock-first-call-
      fails/retry-succeeds pattern as test 3.4, not a real git/subprocess call (a real retry
      against a fabricated `/mnt/c/...` path would not resolve on a Linux CI runner and the test
      must not depend on it doing so). Assert `get_git_info()` — called exactly as the real
      production sites `capture_run_metadata()` and `sweep.py`'s `_git_commit()` call it, with
      zero arguments — performs the worktree check/retry against the current working directory
      and returns the full git-info dict on a successful (mocked) retry. *(Added during
      `/review-openspec` round 1: spec-quality reviewer's BLOCKING finding — the no-argument call
      path is the actual production trigger for issue #77 and was previously undesigned/untested;
      see design.md Decision 5. Mocking requirement added during round 2: TDD reviewer flagged
      that unmocked subprocess calls here would be CI-flaky.)*
- [x] 3.7 Implement the retry integration in `get_git_info()`: resolve
      `repo_dir = repo_path if repo_path is not None else Path.cwd()` first (design.md Decision 5),
      extract the existing subprocess body into a helper parameterized by `env` (keeping the
      `subprocess.run` call at the same `mosquito_cfd.benchmarks.metadata.subprocess.run`
      qualified path, since `tests/test_metadata_capture.py` monkeypatches that exact attribute —
      a refactor that moves the call to a different module-qualified name would silently break
      that existing test's patch target), call it once against `repo_dir` with the caller's
      default environment, and on `(subprocess.CalledProcessError, OSError)` attempt
      `_worktree_retry_env(repo_dir)`; if it returns a non-`None` override, retry the same
      helper with `env={**os.environ, **override}`; on any failure of that retry, fall through to
      the existing `{"error": ...}` result. Run tests 3.1-3.6 (and 1.x/2.x) until all pass.
      *(Widened from `(subprocess.CalledProcessError, FileNotFoundError)` to
      `(subprocess.CalledProcessError, OSError)`, and the `repo_dir = ...` resolution wrapped in
      its own `try`/`except OSError`, during `/review-pr` pre-PR self-review — see design.md's
      "Why N instead of M?" section for the two crash bugs (`UnicodeDecodeError`,
      `NotADirectoryError`) this closes.)*
- [x] 3.8 Write `test_get_git_info_returns_error_dict_for_nonexistent_repo_path`: given a
      `repo_path` pointing at a nonexistent directory, assert `get_git_info()` returns the
      honest error dict rather than raising `NotADirectoryError`/`FileNotFoundError`.
- [x] 3.9 Write `test_worktree_retry_env_handles_non_utf8_pointer_content` and
      `test_get_git_info_handles_non_utf8_worktree_pointer`: given a `.git` pointer file
      containing invalid UTF-8 bytes, assert neither `_worktree_retry_env` nor `get_git_info()`
      raises `UnicodeDecodeError`. *(Tasks 3.8-3.9 added during `/review-pr` pre-PR self-review —
      three independent reviewer lenses each empirically reproduced one of these two crash bugs
      against the code as originally implemented per 3.7; not present in the original TDD plan
      since `/review-openspec`'s design-level rounds never executed the code against pathological
      byte content or nonexistent paths.)*
- [x] 3.10 Add `cwd`-kwarg assertions to `test_get_git_info_retries_with_translated_env_on_worktree_failure`
      and `test_get_git_info_resolves_cwd_when_no_repo_path_given`: assert every `subprocess.run`
      call actually received `cwd=str(repo_dir)`. *(Added during `/review-pr`: the TDD reviewer
      found this was the one unexercised assertion tied directly to Decision 5/finding #14, the
      most-debated design point in the whole proposal — the implementation was already correct,
      but nothing would have caught a regression.)*

## 4. Verification

- [x] 4.1 Run the full `tests/test_benchmarks_metadata.py` suite (new + any pre-existing tests in
      that file) and confirm all pass.
- [x] 4.2 Run the full project test suite (`uv run pytest -v -m "not gpu"`) to confirm no
      regression in `tests/test_metadata_capture.py` or any other consumer of
      `get_git_info`/`capture_run_metadata`.
- [x] 4.3 Run `uv run ruff check src/ tests/` and `uv run ruff format --check src/ tests/` and
      resolve any findings. This change only touches files under `src/`/`tests/`, so this covers
      everything CI's `lint` job would check for it — but note CI's actual lint job additionally
      covers `scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/
      examples/prelim_sweep_fine/`, so a green result here confirms *this change's* files pass,
      not that the full CI lint job is green independent of this change. *(Added during
      `/review-openspec` round 1: TDD-reviewer noted the original verification section covered
      pytest only. Wording corrected during round 2: TDD reviewer flagged the original "matching
      CI's lint job exactly" phrasing as factually wrong.)*
- [x] 4.4 **Merge gate, not just a checklist item**: manually verify against a real
      Windows-created worktree read from WSL (as in issue #77's repro), confirming
      `get_git_info()` now returns real `commit`/`branch`/`dirty` fields instead of the error
      dict. This session/environment has confirmed WSL access (`wsl --status` succeeds, Ubuntu
      default distro) — the implementing agent SHALL attempt this directly:
      1. Create a **detached** worktree at a path outside the tracked repo tree (e.g. a sibling or
         scratch directory), not inside it: `git worktree add <scratch-path> --detach`. Using
         `--detach` is required, not optional — this session is already on the feature branch in
         this checkout, and a bare `git worktree add <path>` (no branch/commit-ish argument)
         defaults to checking out the current branch, which git refuses since it's already
         checked out here.
      2. Confirm the new worktree's `.git` pointer names a Windows drive-letter gitdir.
      3. Run `wsl git rev-parse HEAD` (and `get_git_info()` itself) against it.
      4. **Clean up afterward**: `git worktree remove <scratch-path>` — this is not guaranteed to
         be gitignored on every clone (this repo's committed `.gitignore` has no
         `.claude/worktrees/`-style rule; the exclusion some clones see is a local, unshared
         `.git/info/exclude` entry). An orphaned worktree from the unrelated, non-merged PR #76
         attempt sat un-pruned in this repo's `git worktree list` for 3 days before being found
         during review and manually removed — don't reintroduce that class of residue here.
      5. Fall back to asking a human to perform/confirm this step only if step 1-3 cannot be
         completed in this environment.
      Record the confirmation (and which path — agent-run or human-run) in the PR description —
      this step cannot be automated in CI (per the confirmed test-strategy scoping decision) and
      is the only check that actually exercises the real bug this change fixes, so the PR SHALL
      NOT merge without this confirmation recorded, even if CI is green. *(Reworded during
      `/review-openspec` round 1: the git-workflow reviewer flagged this as a real merge gate, not
      an optional nicety. Ownership clarified during round 3: git-workflow reviewer noted the step
      never said who performs it or whether the implementing agent even has WSL access. `--detach`
      and cleanup added during round 4: git-workflow and CI/CD reviewers both independently caught
      that the original wording would likely fail outright in this exact session and leave
      residue afterward.)*
- [x] 4.5 Add a `docs/CHANGELOG.md` entry under `### Fixed`, matching the granularity of existing
      entries (e.g. "get_git_info() now resolves Windows-created worktrees read via WSL
      (previously silently dropped git provenance) (#77)"). *(Added during `/review-openspec`:
      documentation reviewer's BLOCKING finding — this repo's established convention adds a
      CHANGELOG entry for every bugfix change; two of the most recent changes did this
      explicitly.)*
- [x] 4.6 Run `openspec validate fix-git-provenance-wsl-worktree-v2 --strict` and resolve any
      issues.
- [x] 4.7 Run `/review-pr` on the local branch diff as a pre-PR self-review (5 independent
      reviewer lenses: code quality, TDD/testing, scientific rigor/reproducibility,
      performance/build, behavioral correctness) before opening the PR. Address every BLOCKING
      finding (tasks 3.8-3.10 above), then re-run 4.1-4.3 and 4.6 to confirm the fixes didn't
      regress anything. *(Added post-hoc to document `/pre-merge-check` Phase 3.5, which this
      change's implementation actually went through — three BLOCKING findings surfaced and were
      fixed; see design.md's "Why N instead of M?" section.)*
