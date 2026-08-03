"""``submit_workflow.sh full --parallelism``: override without mutating the committed workflow.

OpenSpec change ``add-fine-grid-corpus-full``. Cluster-free: a stub ``argo`` executable on
``PATH`` intercepts the ``argo submit`` call so no real cluster access is needed. The stub
captures ``$2`` (the workflow-file argument, which always immediately follows the literal
``submit`` token in ``submit_workflow.sh``'s invocation shape -- never the last argument).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# On Windows, a bare "bash" can resolve to the WSL launcher shim (Windows\System32\bash.exe),
# which mangles native Windows paths (strips backslashes) rather than running them as a POSIX
# script argument. Prefer Git Bash explicitly when present -- it's already this repo's documented
# shell for scripts under cluster/argo/ (see openspec/project.md).
_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
_BASH = str(_GIT_BASH) if _GIT_BASH.exists() else (shutil.which("bash") or "bash")

_SUBMIT_SH = Path("cluster/argo/scripts/submit_workflow.sh").resolve()
_WORKFLOW_YAML = Path("cluster/argo/workflows/force-surrogate-sweep.yaml").resolve()
_FAKE_IMAGE = f"ghcr.io/x@sha256:{'a' * 64}"

_STUB_SOURCE = """#!/bin/sh
# argv: submit <workflow-file> -n <namespace> --watch --parameter ...
touch "$STUB_INVOKED_MARKER"
cp "$2" "$STUB_CAPTURE_FILE"
exit 0
"""


def _write_stub(stub_dir: Path) -> Path:
    stub_path = stub_dir / "argo"
    stub_path.write_bytes(_STUB_SOURCE.encode("utf-8"))
    stub_path.chmod(0o755)
    return stub_path


def _run_submit_workflow(
    tmp_path: Path,
    args: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Invoke ``submit_workflow.sh`` with a stub ``argo`` on ``PATH``.

    Returns the completed process, the path the stub would capture the workflow file to (may not
    exist if the stub was never invoked), and the path to a marker file that exists iff the stub
    was actually invoked.
    """
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir()
    _write_stub(stub_dir)

    capture_file = tmp_path / "captured_workflow.yaml"
    invoked_marker = tmp_path / "stub_invoked"

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env["STUB_CAPTURE_FILE"] = str(capture_file)
    env["STUB_INVOKED_MARKER"] = str(invoked_marker)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), "full", "--image", _FAKE_IMAGE, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, capture_file, invoked_marker


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_parallelism_override_patches_only_the_temp_copy(tmp_path):
    before = _sha256(_WORKFLOW_YAML)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path, ["--parallelism", "1"]
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "parallelism: 1" in capture_file.read_text()
    assert _sha256(_WORKFLOW_YAML) == before


def test_omitting_parallelism_is_a_true_noop(tmp_path):
    before = _sha256(_WORKFLOW_YAML)

    result, capture_file, invoked_marker = _run_submit_workflow(tmp_path, [])

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    # True no-op: the stub received the committed file itself, not a sed-patched copy that
    # happens to reproduce the same value.
    assert capture_file.read_bytes() == _WORKFLOW_YAML.read_bytes()
    assert _sha256(_WORKFLOW_YAML) == before


@pytest.mark.parametrize("bad_value", ["0", "-1", "abc"])
def test_invalid_parallelism_rejected_before_touching_anything(tmp_path, bad_value):
    before = _sha256(_WORKFLOW_YAML)

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path, ["--parallelism", bad_value]
    )

    assert result.returncode != 0
    assert not invoked_marker.exists(), (
        "stub must never be invoked for an invalid --parallelism"
    )
    assert _sha256(_WORKFLOW_YAML) == before


def test_help_documents_the_parallelism_flag():
    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), "help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--parallelism" in result.stdout


def test_missing_parallelism_line_fails_loudly_not_silently(tmp_path):
    mangled = tmp_path / "mangled-workflow.yaml"
    lines = _WORKFLOW_YAML.read_text().splitlines(keepends=True)
    mangled.write_text("".join(line for line in lines if "parallelism:" not in line))

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        ["--parallelism", "1"],
        extra_env={"SWEEP_WORKFLOW_FILE": str(mangled)},
    )

    assert result.returncode != 0
    assert "expected exactly one" in result.stderr
    assert not invoked_marker.exists()
