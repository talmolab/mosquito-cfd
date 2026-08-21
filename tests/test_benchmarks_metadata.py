"""Tests for mosquito_cfd.benchmarks.metadata (TDD, fix-git-provenance-wsl-worktree).

Cluster-free: every test uses tmp_path fixtures and monkeypatched ``subprocess.run`` — no real
git, no real WSL environment, no network. CI runs a single ubuntu-latest job against a normal
(non-worktree) checkout, so these tests simulate the worktree-pointer scenario directly rather
than depending on CI happening to run inside one.
"""

from __future__ import annotations

import subprocess

import mosquito_cfd.benchmarks.metadata as metadata
from mosquito_cfd.benchmarks.metadata import (
    _translate_windows_worktree_gitdir,
    _worktree_retry_env,
    get_git_info,
)

# --- _translate_windows_worktree_gitdir ---------------------------------------------------


def test_translate_windows_worktree_gitdir_forward_slashes():
    """Scenario: a Windows-style gitdir pointer (forward slashes) resolves to /mnt/<drive>."""
    line = "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo"
    assert (
        _translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_backslashes():
    """Scenario: backslash-separated Windows paths normalize to the same forward-slashed result."""
    line = "gitdir: C:\\repos\\mosquito-cfd\\.git\\worktrees\\foo"
    assert (
        _translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_lowercase_drive_letter():
    """Scenario: an already-lowercase drive letter still resolves (case-insensitive match)."""
    line = "gitdir: c:/repos/mosquito-cfd/.git/worktrees/foo"
    assert (
        _translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_rejects_posix_path():
    """Scenario: a genuinely missing repository still reports the honest error (POSIX gitdir)."""
    line = "gitdir: /home/user/repo/.git/worktrees/foo"
    assert _translate_windows_worktree_gitdir(line) is None


def test_translate_windows_worktree_gitdir_rejects_malformed_input():
    """Scenario: a genuinely missing repository still reports the honest error (malformed/empty)."""
    assert _translate_windows_worktree_gitdir("gitdir: Cfoo") is None
    assert _translate_windows_worktree_gitdir("") is None


# --- _worktree_retry_env -------------------------------------------------------------------


def test_worktree_retry_env_reads_windows_pointer_file(tmp_path):
    """Scenario: Windows-worktree gitdir pointer is resolved on retry (env construction)."""
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo", encoding="utf-8"
    )
    env = _worktree_retry_env(tmp_path)
    assert env == {
        "GIT_DIR": "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo",
        "GIT_WORK_TREE": str(tmp_path),
    }


def test_worktree_retry_env_returns_none_for_real_gitdir_directory(tmp_path):
    """Scenario: a genuinely missing repository still reports the honest error (real gitdir dir).

    A real repository's ``.git`` is a directory, never a worktree pointer file — must never be
    mistaken for one.
    """
    (tmp_path / ".git").mkdir()
    assert _worktree_retry_env(tmp_path) is None


def test_worktree_retry_env_returns_none_when_git_pointer_is_not_windows_style(
    tmp_path,
):
    """Scenario: a genuinely missing repository still reports the honest error (POSIX pointer)."""
    (tmp_path / ".git").write_text(
        "gitdir: /home/user/repo/.git/worktrees/foo", encoding="utf-8"
    )
    assert _worktree_retry_env(tmp_path) is None


def test_worktree_retry_env_returns_none_when_no_git_at_all(tmp_path):
    """Scenario: a genuinely missing repository still reports the honest error (no .git)."""
    assert _worktree_retry_env(tmp_path) is None


# --- get_git_info retry integration (monkeypatched subprocess.run) -------------------------


def _fake_completed(
    stdout: str = "", returncode: int = 0
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["git"], returncode=returncode, stdout=stdout, stderr=""
    )


def test_get_git_info_retries_with_translated_env_on_worktree_failure(
    tmp_path, monkeypatch
):
    """Scenario: Windows-worktree gitdir pointer is resolved on retry (full get_git_info path)."""
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo", encoding="utf-8"
    )
    expected_env = {
        "GIT_DIR": "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo",
        "GIT_WORK_TREE": str(tmp_path),
    }

    def fake_run(args, *, env=None, check=False, **kwargs):
        has_override = env is not None and all(
            env.get(k) == v for k, v in expected_env.items()
        )
        if not has_override:
            raise subprocess.CalledProcessError(128, args)
        if args[:2] == ["git", "rev-parse"]:
            return _fake_completed("deadbeef" * 5 + "\n")
        if args[:2] == ["git", "symbolic-ref"]:
            return _fake_completed("main\n")
        if args[:2] == ["git", "diff"]:
            return _fake_completed("")
        if args[:2] == ["git", "remote"]:
            return _fake_completed("https://example.com/repo.git\n")
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(metadata.subprocess, "run", fake_run)
    result = get_git_info(tmp_path)
    assert result.get("error") is None
    assert result["commit"] == "deadbeef" * 5
    assert result["branch"] == "main"
    assert result["dirty"] is False
    assert result["repository"] == "https://example.com/repo.git"


def test_get_git_info_falls_back_to_error_when_retry_also_fails(tmp_path, monkeypatch):
    """Scenario: a Windows-style pointer that still fails to resolve on retry reports the
    honest error — never fabricate a commit when both attempts fail.
    """
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo", encoding="utf-8"
    )

    def always_fails(args, *, env=None, check=False, **kwargs):
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(metadata.subprocess, "run", always_fails)
    assert get_git_info(tmp_path) == {"error": "git not available or not a repository"}


def test_get_git_info_does_not_retry_for_non_worktree_failure(tmp_path, monkeypatch):
    """Scenario: a genuinely missing repository still reports the honest error, with no retry
    attempted (regression guard against retrying for the wrong reason).
    """
    calls = []

    def fake_run(args, *, env=None, check=False, **kwargs):
        calls.append(args)
        raise subprocess.CalledProcessError(128, args)

    monkeypatch.setattr(metadata.subprocess, "run", fake_run)
    result = get_git_info(tmp_path)  # no .git at all in tmp_path
    assert result == {"error": "git not available or not a repository"}
    assert len(calls) == 1  # exactly one attempt -- no retry for a non-worktree failure


def test_get_git_info_unaffected_when_first_attempt_succeeds(tmp_path, monkeypatch):
    """Scenario: the common case (git resolves on the first try) is unchanged -- no retry path
    is ever consulted, and the returned shape matches today's behavior.
    """

    def retry_env_would_raise(_repo_dir):
        raise AssertionError(
            "_worktree_retry_env must not be called when the first try works"
        )

    monkeypatch.setattr(metadata, "_worktree_retry_env", retry_env_would_raise)

    def fake_run(args, *, env=None, check=False, **kwargs):
        assert env is None  # first attempt always runs with no env override
        if args[:2] == ["git", "rev-parse"]:
            return _fake_completed("cafebabe" * 5 + "\n")
        if args[:2] == ["git", "symbolic-ref"]:
            return _fake_completed("main\n")
        if args[:2] == ["git", "diff"]:
            return _fake_completed("+changed line\n")
        if args[:2] == ["git", "remote"]:
            return _fake_completed("", returncode=1)
        raise AssertionError(f"unexpected git call: {args}")

    monkeypatch.setattr(metadata.subprocess, "run", fake_run)
    result = get_git_info(tmp_path)
    assert result["commit"] == "cafebabe" * 5
    assert result["branch"] == "main"
    assert result["dirty"] is True
    assert "diff_hash" in result
    assert "repository" not in result
