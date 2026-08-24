"""Tests for src/mosquito_cfd/benchmarks/metadata.py's WSL-worktree git-provenance retry.

TDD for fix-git-provenance-wsl-worktree-v2 (issue #77): a Windows-created git worktree's
``.git`` pointer file names its real gitdir with a Windows drive-letter path that a Linux
``git`` binary (as invoked from WSL) can't resolve. These tests cover the path-translation
helper, the retry-environment builder, and the ``get_git_info`` retry integration, using mocked
``subprocess.run`` and on-disk fixture ``.git`` pointer files only (no real WSL invocation, per
this change's confirmed test-strategy scoping decision).
"""

from __future__ import annotations

import os
import subprocess

import pytest

from mosquito_cfd.benchmarks import metadata as mc

# ---------------------------------------------------------------------------
# 1. Path-translation helper
# ---------------------------------------------------------------------------


def test_translate_windows_worktree_gitdir_forward_slashes():
    line = "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo"
    assert (
        mc._translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_backslashes():
    line = "gitdir: C:\\repos\\mosquito-cfd\\.git\\worktrees\\foo"
    assert (
        mc._translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_lowercase_drive_letter():
    line = "gitdir: c:/repos/mosquito-cfd/.git/worktrees/foo"
    assert (
        mc._translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_rejects_posix_path():
    line = "gitdir: /home/user/repo/.git/worktrees/foo"
    assert mc._translate_windows_worktree_gitdir(line) is None


@pytest.mark.parametrize("content", ["Cfoo", "", "not a gitdir line at all"])
def test_translate_windows_worktree_gitdir_rejects_malformed_input(content):
    assert mc._translate_windows_worktree_gitdir(content) is None


def test_translate_windows_worktree_gitdir_strips_trailing_newline():
    line = "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n"
    assert (
        mc._translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


def test_translate_windows_worktree_gitdir_mixed_separators():
    line = "gitdir: C:/repos\\mosquito-cfd/.git/worktrees/foo"
    assert (
        mc._translate_windows_worktree_gitdir(line)
        == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
    )


# ---------------------------------------------------------------------------
# 2. Retry-environment builder
# ---------------------------------------------------------------------------


def test_worktree_retry_env_reads_windows_pointer_file(tmp_path):
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n", encoding="utf-8"
    )
    assert mc._worktree_retry_env(tmp_path) == {
        "GIT_DIR": "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo",
        "GIT_WORK_TREE": str(tmp_path),
    }


def test_worktree_retry_env_returns_none_for_real_gitdir_directory(tmp_path):
    (tmp_path / ".git").mkdir()
    assert mc._worktree_retry_env(tmp_path) is None


def test_worktree_retry_env_returns_none_when_git_pointer_is_not_windows_style(
    tmp_path,
):
    (tmp_path / ".git").write_text(
        "gitdir: /home/user/repo/.git/worktrees/foo\n", encoding="utf-8"
    )
    assert mc._worktree_retry_env(tmp_path) is None


def test_worktree_retry_env_returns_none_when_no_git_at_all(tmp_path):
    assert mc._worktree_retry_env(tmp_path) is None


# ---------------------------------------------------------------------------
# 3. get_git_info retry integration
# ---------------------------------------------------------------------------


def _completed(stdout="", returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=""
    )


def _fake_success_run(argv, **kwargs):
    if argv[:2] == ["git", "rev-parse"]:
        return _completed("abc123\n")
    if argv[:2] == ["git", "symbolic-ref"]:
        return _completed("main\n")
    if argv[:2] == ["git", "diff"]:
        return _completed("")
    if argv[:2] == ["git", "remote"]:
        return _completed("git@github.com:talmolab/mosquito-cfd.git\n")
    raise AssertionError(f"unexpected subprocess call: {argv}")


def test_get_git_info_unaffected_when_first_attempt_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(mc.subprocess, "run", _fake_success_run)

    def _boom(*args, **kwargs):
        raise AssertionError(
            "_worktree_retry_env must not be called when the first attempt succeeds"
        )

    monkeypatch.setattr(mc, "_worktree_retry_env", _boom)

    result = mc.get_git_info(tmp_path)

    assert result["commit"] == "abc123"
    assert result["branch"] == "main"
    assert result["dirty"] is False
    assert result["repository"] == "git@github.com:talmolab/mosquito-cfd.git"
    assert "error" not in result


def test_get_git_info_does_not_retry_for_non_worktree_failure(tmp_path, monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert len(calls) == 1
    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_does_not_retry_for_posix_worktree_pointer(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text(
        "gitdir: /home/user/repo/.git/worktrees/foo\n", encoding="utf-8"
    )
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert len(calls) == 1
    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_retries_with_translated_env_on_worktree_failure(
    tmp_path, monkeypatch
):
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n", encoding="utf-8"
    )
    retry_envs = []
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs)
        env = kwargs.get("env")
        if env is None:
            raise subprocess.CalledProcessError(1, argv)
        retry_envs.append(env)
        return _fake_success_run(argv, **kwargs)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert result["commit"] == "abc123"
    assert "error" not in result
    assert retry_envs, "expected the retry to actually pass an env kwarg"
    for env in retry_envs:
        assert env["GIT_DIR"] == "/mnt/c/repos/mosquito-cfd/.git/worktrees/foo"
        assert env["GIT_WORK_TREE"] == str(tmp_path)
        for key, value in os.environ.items():
            assert env.get(key) == value
    assert all(kwargs.get("cwd") == str(tmp_path) for kwargs in calls)


def test_get_git_info_falls_back_to_error_when_retry_also_fails(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n", encoding="utf-8"
    )

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_resolves_cwd_when_no_repo_path_given(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    retry_envs = []
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(kwargs)
        env = kwargs.get("env")
        if env is None:
            raise subprocess.CalledProcessError(1, argv)
        retry_envs.append(env)
        return _fake_success_run(argv, **kwargs)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info()

    assert result["commit"] == "abc123"
    assert "error" not in result
    assert retry_envs, "expected the no-arg call to still retry with a translated env"
    assert all(kwargs.get("cwd") == str(tmp_path) for kwargs in calls)


def test_get_git_info_returns_error_dict_for_nonexistent_repo_path(tmp_path):
    missing = tmp_path / "does-not-exist"

    result = mc.get_git_info(missing)

    assert result == {"error": "git not available or not a repository"}


def test_worktree_retry_env_handles_non_utf8_pointer_content(tmp_path):
    # Invalid UTF-8 bytes must never raise UnicodeDecodeError; `errors="replace"` substitutes
    # U+FFFD, so the regex still matches around the garbled bytes and produces a (harmless,
    # non-resolvable) translation rather than crashing.
    (tmp_path / ".git").write_bytes(b"gitdir: C:/repos\xff\xfe/.git/worktrees/foo\n")

    result = mc._worktree_retry_env(tmp_path)

    assert result is not None
    assert result["GIT_DIR"] == "/mnt/c/repos\ufffd\ufffd/.git/worktrees/foo"


def test_get_git_info_handles_non_utf8_worktree_pointer(tmp_path, monkeypatch):
    (tmp_path / ".git").write_bytes(b"gitdir: C:/repos\xff\xfe/.git/worktrees/foo\n")

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}
