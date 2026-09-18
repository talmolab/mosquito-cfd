"""``submit_workflow.sh smoke``: rejects orchestration flags it silently ignored before, and
defaults to the corpus's CFL-worst config rather than its mildest one (issue #92's prevention --
see design.md D1/D2: the smoke pre-flight exists to catch problems before the 27-way fan-out, and
was previously aimed at the one config structurally unable to reveal a CFL-limiting problem).
Cluster-free: a stub ``argo`` on ``PATH`` intercepts the ``argo submit`` call and captures argv.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
_BASH = str(_GIT_BASH) if _GIT_BASH.exists() else (shutil.which("bash") or "bash")
_SUBMIT_SH = Path("cluster/argo/scripts/submit_workflow.sh").resolve()
_FAKE_IMAGE = f"ghcr.io/x@sha256:{'a' * 64}"

_STUB_SOURCE = """#!/bin/sh
touch "$STUB_INVOKED_MARKER"
echo "$@" > "$STUB_ARGV_FILE"
exit 0
"""


def _write_stub(stub_dir: Path) -> Path:
    stub_path = stub_dir / "argo"
    stub_path.write_bytes(_STUB_SOURCE.encode("utf-8"))
    stub_path.chmod(0o755)
    return stub_path


def _run_smoke(
    tmp_path: Path, extra_args: list[str]
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir(exist_ok=True)
    _write_stub(stub_dir)
    invoked_marker = tmp_path / "stub_invoked"
    argv_file = tmp_path / "stub_argv"

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env["STUB_INVOKED_MARKER"] = str(invoked_marker)
    env["STUB_ARGV_FILE"] = str(argv_file)
    env["NO_PROVISION"] = "true"

    result = subprocess.run(
        [
            _BASH,
            str(_SUBMIT_SH),
            "smoke",
            "--image",
            _FAKE_IMAGE,
            "--no-provision",
            *extra_args,
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    return result, invoked_marker, argv_file


def test_smoke_rejects_parallelism_flag(tmp_path):
    """`smoke` previously silently accepted --parallelism and ignored it (only `full` consumed
    the global-loop-parsed value) -- now dies with a clear message instead."""
    result, invoked_marker, _ = _run_smoke(tmp_path, ["--parallelism", "3"])
    assert result.returncode != 0
    assert "parallelism" in (result.stderr + result.stdout).lower()
    assert not invoked_marker.exists()


def test_smoke_rejects_active_deadline_seconds_flag(tmp_path):
    result, invoked_marker, _ = _run_smoke(
        tmp_path, ["--active-deadline-seconds", "3600"]
    )
    assert result.returncode != 0
    assert "active-deadline-seconds" in (result.stderr + result.stdout).lower()
    assert not invoked_marker.exists()


def test_smoke_defaults_to_the_cfl_worst_config(tmp_path):
    """SMOKE_CONFIG_NAME/SMOKE_INPUT_FILE/SMOKE_MAX_STEP now default to s55_f115_p30 (cfl_req
    0.490, the worst of the 27-config Aedes grid per design.md D2), not s35_f085_p30 (the
    mildest) -- so the pre-flight can actually catch a CFL-limiting problem before the fan-out.
    """
    result, invoked_marker, argv_file = _run_smoke(tmp_path, [])
    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    argv = argv_file.read_text(encoding="utf-8")
    assert "config-name=s55_f115_p30" in argv
    assert "input-file=inputs/inputs.3d.s55_f115_p30" in argv
    assert "max-step=3478" in argv


def test_smoke_config_name_still_overridable_via_env(tmp_path):
    """An operator can still override the smoke config explicitly."""
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir(exist_ok=True)
    _write_stub(stub_dir)
    invoked_marker = tmp_path / "stub_invoked"
    argv_file = tmp_path / "stub_argv"

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env["STUB_INVOKED_MARKER"] = str(invoked_marker)
    env["STUB_ARGV_FILE"] = str(argv_file)
    env["NO_PROVISION"] = "true"
    env["SMOKE_CONFIG_NAME"] = "s35_f085_p30"
    env["SMOKE_INPUT_FILE"] = "inputs/inputs.3d.s35_f085_p30"
    env["SMOKE_MAX_STEP"] = "4706"

    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), "smoke", "--image", _FAKE_IMAGE, "--no-provision"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "config-name=s35_f085_p30" in argv_file.read_text(encoding="utf-8")
