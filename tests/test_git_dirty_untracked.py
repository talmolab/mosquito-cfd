"""Real Git repositories must not label untracked source as clean."""

import hashlib
import subprocess

from mosquito_cfd.benchmarks.metadata import get_git_info


def test_untracked_paths_affect_dirty_and_hash(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True
        )

    git("init")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    (tmp_path / ".gitignore").write_text("scratch/\n")
    (tmp_path / "tracked.py").write_text("original\n")
    git("add", ".")
    git("commit", "-m", "fixture")
    assert get_git_info(tmp_path)["dirty"] is False
    (tmp_path / "scratch").mkdir()
    (tmp_path / "scratch/output").touch()
    assert get_git_info(tmp_path)["dirty"] is False
    first = tmp_path / "new source.py"
    first.touch()
    untracked = get_git_info(tmp_path)
    assert untracked["dirty"] is True
    assert len(untracked["diff_hash"]) == 12
    first.rename(tmp_path / "other source.py")
    renamed = get_git_info(tmp_path)
    assert renamed["diff_hash"] != untracked["diff_hash"]
    (tmp_path / "tracked.py").write_text("changed\n")
    mixed = get_git_info(tmp_path)
    assert mixed["diff_hash"] != renamed["diff_hash"]
    (tmp_path / "other source.py").unlink()
    tracked = get_git_info(tmp_path)
    assert tracked["dirty"] is True
    assert (
        tracked["diff_hash"]
        == hashlib.sha256(git("diff", "HEAD").stdout).hexdigest()[:12]
    )
    git("checkout", "--", "tracked.py")
    assert get_git_info(tmp_path)["dirty"] is False
