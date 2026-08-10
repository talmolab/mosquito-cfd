"""``submit_workflow.sh``'s ``provision`` step: stage the local corpus onto the NFS workspace
before submitting, translating the cluster hostPath convention to WSL's local mount point.

OpenSpec change ``fix-force-surrogate-sweep-hinge`` (closes GitHub issue #62: the script had no
step to provision the NFS workspace-hostpath from the committed corpus, which twice let a stale or
wrong ``wing.vertex`` sit on the cluster share undetected). Cluster-free: a stub ``argo`` executable
on ``PATH`` intercepts the ``argo submit`` call, and ``CLUSTER_NFS_PREFIX``/``LOCAL_NFS_PREFIX`` are
left at their real defaults -- a plain ``tmp_path`` string is already outside the ``/hpi/hpi_dev``
prefix, so ``to_local_path`` is a no-op on it and no real NFS mount is ever touched.
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
_FAKE_IMAGE = f"ghcr.io/x@sha256:{'a' * 64}"

_STUB_SOURCE = """#!/bin/sh
# argv: submit <workflow-or-smoke-file> -n <namespace> --watch --parameter ...
touch "$STUB_INVOKED_MARKER"
exit 0
"""


def _write_stub(stub_dir: Path) -> Path:
    stub_path = stub_dir / "argo"
    stub_path.write_bytes(_STUB_SOURCE.encode("utf-8"))
    stub_path.chmod(0o755)
    return stub_path


def _make_corpus(root: Path, name: str, *, with_manifest: bool = True) -> Path:
    """Build a fake corpus dir at ``root/name`` with ``inputs/`` (+ optionally a manifest)."""
    corpus = root / name
    (corpus / "inputs").mkdir(parents=True)
    (corpus / "inputs" / "inputs.3d.s35_f085_p30").write_text("dummy deck\n", encoding="utf-8")
    if with_manifest:
        (corpus / "sweep_manifest.json").write_text("{}", encoding="utf-8")
        (corpus / "sweep_manifest.units.json").write_text("{}", encoding="utf-8")
    return corpus


def _run_submit_workflow(
    tmp_path: Path,
    command: str,
    args: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess, Path, Path]:
    """Invoke ``submit_workflow.sh <command>`` with a stub ``argo`` on ``PATH``.

    Returns the completed process, the resolved local workspace path (``--workspace-hostpath``,
    which is a plain tmp_path string here so ``to_local_path`` is a no-op), and a marker file that
    exists iff the stub ``argo`` was actually invoked.
    """
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir(exist_ok=True)
    _write_stub(stub_dir)

    invoked_marker = tmp_path / "stub_invoked"
    invoked_marker.unlink(missing_ok=True)

    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}{os.pathsep}{env['PATH']}"
    env["STUB_INVOKED_MARKER"] = str(invoked_marker)
    env.setdefault("WING_VERTEX_SOURCE", str(tmp_path / "canonical_wing.vertex"))
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), command, "--image", _FAKE_IMAGE, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result, invoked_marker


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def canonical_wing_vertex(tmp_path: Path) -> Path:
    path = tmp_path / "canonical_wing.vertex"
    path.write_text("908\n0.0 0.0 0.0\n", encoding="utf-8")
    return path


def test_provision_copies_and_verifies_by_hash_for_full(tmp_path, canonical_wing_vertex):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert (workspace / "inputs" / "inputs.3d.s35_f085_p30").read_text() == "dummy deck\n"
    assert (workspace / "sweep_manifest.json").exists()
    assert (workspace / "wing.vertex").read_bytes() == canonical_wing_vertex.read_bytes()


def test_provision_copies_and_verifies_by_hash_for_smoke(tmp_path, canonical_wing_vertex):
    # smoke doesn't need a manifest -- omit it to prove `full`'s requirement isn't shared.
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=False)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "smoke",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert (workspace / "inputs" / "inputs.3d.s35_f085_p30").read_text() == "dummy deck\n"
    assert (workspace / "wing.vertex").read_bytes() == canonical_wing_vertex.read_bytes()
    assert not (workspace / "sweep_manifest.json").exists()


def test_provision_fails_when_corpus_dir_does_not_exist(tmp_path, canonical_wing_vertex):
    missing_corpus = tmp_path / "does_not_exist"
    workspace = tmp_path / "workspace" / "does_not_exist"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(missing_corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "does not exist" in result.stderr


def test_provision_fails_when_inputs_missing_within_existing_corpus_dir(tmp_path, canonical_wing_vertex):
    corpus = tmp_path / "corpus" / "prelim_sweep"
    corpus.mkdir(parents=True)  # exists, but no inputs/ subdir
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "inputs/" in result.stderr


def test_provision_fails_when_manifest_missing_for_full(tmp_path, canonical_wing_vertex):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=False)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "sweep_manifest.json" in result.stderr


def test_provision_fails_on_corpus_workspace_basename_mismatch(tmp_path, canonical_wing_vertex):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep_fine"  # deliberately mismatched

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "prelim_sweep" in result.stderr and "prelim_sweep_fine" in result.stderr


def test_no_provision_flag_skips_copy_but_still_submits(tmp_path, canonical_wing_vertex):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    workspace.mkdir(parents=True)
    (workspace / "sentinel.txt").write_text("pre-existing, untouched\n", encoding="utf-8")

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        [
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(workspace),
            "--no-provision",
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert (workspace / "sentinel.txt").read_text() == "pre-existing, untouched\n"
    assert not (workspace / "inputs").exists()
    assert not (workspace / "wing.vertex").exists()


@pytest.mark.parametrize(
    "corpus_name",
    ["prelim_sweep", "prelim_sweep_fine"],
)
def test_provisioned_wing_vertex_matches_canonical_source(tmp_path, canonical_wing_vertex, corpus_name):
    corpus = _make_corpus(tmp_path / "corpus", corpus_name, with_manifest=True)
    workspace = tmp_path / "workspace" / corpus_name

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert _sha256_bytes((workspace / "wing.vertex").read_bytes()) == _sha256_bytes(
        canonical_wing_vertex.read_bytes()
    )


def test_to_local_path_default_mapping(tmp_path, canonical_wing_vertex):
    """Confirms the real default CLUSTER_NFS_PREFIX/LOCAL_NFS_PREFIX translation is applied.

    submit_workflow.sh dispatches on $1 immediately rather than exposing to_local_path as a
    separately-sourceable library function, so this exercises it end-to-end: point a
    --workspace-hostpath that DOES start with the default CLUSTER_NFS_PREFIX, override
    LOCAL_NFS_PREFIX to a tmp_path root, and confirm provisioning lands under the translated
    (tmp_path) location -- not literally under /hpi/hpi_dev, which doesn't exist on this test host.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    cluster_style_workspace = "/hpi/hpi_dev/users/testuser/mosquito-cfd/examples/prelim_sweep"
    local_root = tmp_path / "mnt_hpi_dev"
    local_root.mkdir()

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", cluster_style_workspace],
        extra_env={
            "CLUSTER_NFS_PREFIX": "/hpi/hpi_dev",
            "LOCAL_NFS_PREFIX": str(local_root).replace("\\", "/"),
        },
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    translated = local_root / "users/testuser/mosquito-cfd/examples/prelim_sweep"
    assert (translated / "wing.vertex").exists(), (
        "provisioning must land at the LOCAL_NFS_PREFIX-translated path, not the literal "
        "cluster-hostPath string, which does not exist on this test host"
    )


def test_parallelism_and_provisioning_do_not_interfere(tmp_path, canonical_wing_vertex):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        [
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(workspace),
            "--parallelism",
            "0",  # invalid
        ],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "parallelism" in result.stderr
