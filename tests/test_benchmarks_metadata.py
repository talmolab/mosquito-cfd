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


def test_get_git_info_returns_error_dict_when_repo_path_is_a_file_not_directory(
    tmp_path,
):
    # Unlike a nonexistent path (FileNotFoundError, already caught pre-widening), an existing
    # FILE passed as cwd raises NotADirectoryError — this is the case that actually needs the
    # broadened `except (subprocess.CalledProcessError, OSError)` (FileNotFoundError alone
    # would not have caught it).
    not_a_dir = tmp_path / "some_file.txt"
    not_a_dir.write_text("not a directory", encoding="utf-8")

    result = mc.get_git_info(not_a_dir)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_returns_error_dict_when_cwd_resolution_raises_oserror(
    monkeypatch,
):
    def _raise_cwd():
        raise FileNotFoundError("current working directory no longer exists")

    monkeypatch.setattr(mc.Path, "cwd", staticmethod(_raise_cwd))

    result = mc.get_git_info()

    assert result == {"error": "git not available or not a repository"}


def test_worktree_retry_env_returns_none_when_is_file_raises_permission_error(
    tmp_path, monkeypatch
):
    # Path.is_file() swallows ENOENT/ENOTDIR internally but NOT PermissionError/EACCES — a
    # transient permission hiccup on the `.git` stat (locked file, ACL issue, momentary CIFS
    # unavailability, all realistic on this project's Windows/WSL/CIFS-mounted deployments)
    # must not propagate out of this function.
    def _raise_permission(self):
        raise PermissionError("simulated permission denial on .git stat")

    monkeypatch.setattr(mc.Path, "is_file", _raise_permission)

    assert mc._worktree_retry_env(tmp_path) is None


def test_get_git_info_does_not_crash_when_worktree_check_raises_permission_error(
    tmp_path, monkeypatch
):
    def _raise_permission(self):
        raise PermissionError("simulated permission denial on .git stat")

    monkeypatch.setattr(mc.Path, "is_file", _raise_permission)

    def fake_run(argv, **kwargs):
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

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


# ---------------------------------------------------------------------------
# 4. get_git_info build-time-baked-commit fallback (fix-git-provenance-no-git-override, #66)
# ---------------------------------------------------------------------------


def _always_fails_run(argv, **kwargs):
    raise subprocess.CalledProcessError(1, argv)


def test_get_git_info_uses_baked_commit_when_git_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "c" * 40)

    result = mc.get_git_info(tmp_path)

    assert result == {"commit": "c" * 40, "source": "docker-image-build-arg"}


def test_get_git_info_treats_unknown_sentinel_as_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "unknown")

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_no_baked_commit_env_falls_through_unchanged(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.delenv("MOSQUITO_CFD_COMMIT", raising=False)

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_ignores_baked_commit_when_direct_query_succeeds(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(mc.subprocess, "run", _fake_success_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "d" * 40)

    result = mc.get_git_info(tmp_path)

    assert result["commit"] == "abc123"
    assert result["branch"] == "main"
    assert result["dirty"] is False
    assert result["repository"] == "git@github.com:talmolab/mosquito-cfd.git"
    assert "source" not in result


def test_get_git_info_ignores_baked_commit_when_worktree_retry_succeeds(
    tmp_path, monkeypatch
):
    (tmp_path / ".git").write_text(
        "gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo\n", encoding="utf-8"
    )
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "e" * 40)

    def fake_run(argv, **kwargs):
        env = kwargs.get("env")
        if env is None:
            raise subprocess.CalledProcessError(1, argv)
        return _fake_success_run(argv, **kwargs)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)

    result = mc.get_git_info(tmp_path)

    assert result["commit"] == "abc123"
    assert "source" not in result


def test_get_git_info_attempts_direct_query_before_baked_commit_fallback(
    tmp_path, monkeypatch
):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(mc.subprocess, "run", fake_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "c" * 40)

    result = mc.get_git_info(tmp_path)

    assert calls, "the direct git query must actually be attempted, not skipped"
    assert result == {"commit": "c" * 40, "source": "docker-image-build-arg"}


def test_get_git_info_treats_malformed_baked_commit_as_absent_whitespace(
    tmp_path, monkeypatch
):
    """A misconfigured build-arg (e.g. trailing whitespace from a heredoc/shell mistake) must
    not be silently trusted as a commit -- unlike a well-formed baked value, it is treated the
    same as an absent/"unknown" one, matching how the CLI-override path (`resolve_git_info`)
    already validates format before trusting a human/build-supplied commit string."""
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", " ")

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_treats_malformed_baked_commit_as_absent_truncated(
    tmp_path, monkeypatch
):
    """A truncated SHA (e.g. `git rev-parse --short` used by mistake in the build pipeline)
    must not be silently trusted as a full commit."""
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "abc1234")

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}


def test_get_git_info_treats_malformed_baked_commit_as_absent_uppercase(
    tmp_path, monkeypatch
):
    """Matches the CLI-override path's case-sensitivity behavior (design.md Decision 2): not
    case-folded, an uppercase value is rejected rather than silently accepted."""
    monkeypatch.setattr(mc.subprocess, "run", _always_fails_run)
    monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "C" * 40)

    result = mc.get_git_info(tmp_path)

    assert result == {"error": "git not available or not a repository"}
