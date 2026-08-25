"""``submit_workflow.sh full --active-deadline-seconds``: override, and the auto-scale fallback.

OpenSpec change ``fix-argo-sweep-timeouts`` (issue #63: ``activeDeadlineSeconds`` doesn't scale
when ``--parallelism`` is overridden). Cluster-free: a stub ``argo`` executable on ``PATH``
intercepts the ``argo submit`` call, mirroring ``tests/test_submit_workflow_parallelism.py``'s
shape exactly, including baking ``--no-provision`` into every invocation unconditionally (this
file is entirely about ``--active-deadline-seconds``/auto-scale, not provisioning, which is
exercised in its own ``tests/test_submit_workflow_provision.py`` and must not touch real NFS
defaults or the real default corpus-dir's ``provision()`` preconditions here).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# Mirrors tests/test_submit_workflow_parallelism.py's shell resolution exactly.
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
    """Invoke ``submit_workflow.sh full`` with a stub ``argo`` on ``PATH``.

    ``--no-provision`` is baked into every invocation unconditionally (see module docstring) --
    no individual test needs to remember to add it itself. Returns the completed process, the
    path the stub would capture the workflow file to (may not exist if the stub was never
    invoked), and the path to a marker file that exists iff the stub was actually invoked.
    """
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir(exist_ok=True)
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
        [
            _BASH,
            str(_SUBMIT_SH),
            "full",
            "--image",
            _FAKE_IMAGE,
            "--no-provision",
            *args,
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, capture_file, invoked_marker


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 2. --active-deadline-seconds override flag
# ---------------------------------------------------------------------------


def test_active_deadline_override_patches_only_the_temp_copy(tmp_path):
    before = _sha256(_WORKFLOW_YAML)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path, ["--active-deadline-seconds", "172800"]
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    captured = capture_file.read_text()
    assert "activeDeadlineSeconds: 172800" in captured
    assert "parallelism: 3" in captured  # committed default, untouched
    assert _sha256(_WORKFLOW_YAML) == before


def test_omitting_both_deadline_and_parallelism_is_a_true_noop(tmp_path):
    before = _sha256(_WORKFLOW_YAML)

    result, capture_file, invoked_marker = _run_submit_workflow(tmp_path, [])

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert capture_file.read_bytes() == _WORKFLOW_YAML.read_bytes()
    assert _sha256(_WORKFLOW_YAML) == before


@pytest.mark.parametrize("bad_value", ["0", "-1", "abc"])
def test_invalid_active_deadline_seconds_rejected_before_touching_anything(
    tmp_path, bad_value
):
    before = _sha256(_WORKFLOW_YAML)

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path, ["--active-deadline-seconds", bad_value]
    )

    assert result.returncode != 0
    assert "positive integer" in result.stderr
    assert not invoked_marker.exists()
    assert _sha256(_WORKFLOW_YAML) == before


def test_missing_active_deadline_line_fails_loudly_not_silently(tmp_path):
    mangled = tmp_path / "mangled-workflow.yaml"
    lines = _WORKFLOW_YAML.read_text().splitlines(keepends=True)
    mangled.write_text(
        "".join(line for line in lines if "activeDeadlineSeconds:" not in line)
    )

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        ["--active-deadline-seconds", "100000"],
        extra_env={"SWEEP_WORKFLOW_FILE": str(mangled)},
    )

    assert result.returncode != 0
    assert "expected exactly one" in result.stderr
    assert not invoked_marker.exists()


def test_parallelism_and_active_deadline_together_patch_the_same_temp_copy(tmp_path):
    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        ["--parallelism", "1", "--active-deadline-seconds", "200000"],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    captured = capture_file.read_text()
    assert "parallelism: 1" in captured
    assert "activeDeadlineSeconds: 200000" in captured


def test_help_documents_active_deadline_seconds_and_the_coupling_risk():
    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), "help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--active-deadline-seconds" in result.stdout
    lowered = result.stdout.lower()
    assert "coupled" in lowered or "coupling" in lowered
