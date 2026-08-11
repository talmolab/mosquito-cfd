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
    (corpus / "inputs" / "inputs.3d.s35_f085_p30").write_text(
        "dummy deck\n", encoding="utf-8"
    )
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


def test_provision_copies_and_verifies_by_hash_for_full(
    tmp_path, canonical_wing_vertex
):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert (
        workspace / "inputs" / "inputs.3d.s35_f085_p30"
    ).read_text() == "dummy deck\n"
    # Content-equality, not just existence -- a truncated/corrupted-but-cp-succeeded manifest copy
    # must be caught, matching the rigor already applied to inputs/ and wing.vertex.
    assert (workspace / "sweep_manifest.json").read_text() == (
        corpus / "sweep_manifest.json"
    ).read_text()
    assert (workspace / "sweep_manifest.units.json").read_text() == (
        corpus / "sweep_manifest.units.json"
    ).read_text()
    assert (
        workspace / "wing.vertex"
    ).read_bytes() == canonical_wing_vertex.read_bytes()


def test_provision_copies_and_verifies_by_hash_for_smoke(
    tmp_path, canonical_wing_vertex
):
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
    assert (
        workspace / "inputs" / "inputs.3d.s35_f085_p30"
    ).read_text() == "dummy deck\n"
    assert (
        workspace / "wing.vertex"
    ).read_bytes() == canonical_wing_vertex.read_bytes()
    assert not (workspace / "sweep_manifest.json").exists()


def test_provision_fails_when_corpus_dir_does_not_exist(
    tmp_path, canonical_wing_vertex
):
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


def test_provision_fails_when_corpus_dir_is_a_file_not_a_directory(
    tmp_path, canonical_wing_vertex
):
    """Distinct error from 'does not exist' -- the path IS there, just not a directory."""
    not_a_dir = tmp_path / "corpus" / "prelim_sweep"
    not_a_dir.parent.mkdir(parents=True)
    not_a_dir.write_text("oops, a file", encoding="utf-8")
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(not_a_dir), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "not a directory" in result.stderr
    assert "does not exist" not in result.stderr


def test_provision_fails_when_inputs_missing_within_existing_corpus_dir(
    tmp_path, canonical_wing_vertex
):
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


def test_provision_fails_when_manifest_missing_for_full(
    tmp_path, canonical_wing_vertex
):
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


def test_provision_fails_when_units_sidecar_missing_for_full(
    tmp_path, canonical_wing_vertex
):
    """sweep_manifest.json alone isn't enough for `full` -- the units sidecar is also required.

    Regression: `provision` only checked sweep_manifest.json before staging the whole
    sweep_manifest*.json glob, so a corpus-dir missing only sweep_manifest.units.json would have
    "provisioned successfully" with a silently incomplete manifest set.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    (corpus / "sweep_manifest.units.json").unlink()
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "sweep_manifest.units.json" in result.stderr


def test_provision_fails_when_wing_vertex_source_missing(tmp_path):
    """A missing canonical wing.vertex source fails clearly, not via a raw `cp` error."""
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
        extra_env={"WING_VERTEX_SOURCE": str(tmp_path / "does_not_exist.vertex")},
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert "does not exist" in result.stderr


def test_provision_fails_when_wing_vertex_source_missing_leaves_workspace_untouched(
    tmp_path,
):
    """A bad WING_VERTEX_SOURCE must fail before any destructive mutation, not after.

    Regression: this precondition used to be checked AFTER inputs/ was already wiped and
    replaced, so a failure here left the workspace half-migrated -- fresh decks, stale/missing
    geometry -- exactly the "silent stale content" defect class (#62) this step exists to close,
    just reached through a different trigger. All preconditions must be validated before any
    rm -rf/cp runs.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    workspace.mkdir(parents=True)
    (workspace / "inputs").mkdir()
    pre_existing_deck = workspace / "inputs" / "inputs.3d.pre_existing"
    pre_existing_deck.write_text("pre-existing deck, must survive\n", encoding="utf-8")

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
        extra_env={"WING_VERTEX_SOURCE": str(tmp_path / "does_not_exist.vertex")},
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    assert pre_existing_deck.exists(), (
        "inputs/ must not be wiped/replaced before the wing.vertex source is validated"
    )


def test_provision_replaces_stale_inputs_not_merges(tmp_path, canonical_wing_vertex):
    """A config dropped from a shrunk/changed corpus must not survive provisioning.

    Regression: `cp -r` into a pre-existing inputs/ only adds/overwrites; it never removes files
    already present at the destination that no longer exist in the source -- the same class of
    silent-stale-content defect (#62) this whole step exists to close, just for inputs/ instead of
    wing.vertex.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    (workspace / "inputs").mkdir(parents=True)
    stale_deck = workspace / "inputs" / "inputs.3d.stale_dropped_config"
    stale_deck.write_text("this config was removed from the corpus\n", encoding="utf-8")

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert not stale_deck.exists(), (
        "stale config from a prior corpus must not survive provisioning"
    )
    assert (workspace / "inputs" / "inputs.3d.s35_f085_p30").exists()


def test_provision_replaces_stale_manifest_not_merges(tmp_path, canonical_wing_vertex):
    """A manifest file dropped from a prior corpus must not survive provisioning either.

    Regression: `inputs/` got replace-not-merge semantics (see
    test_provision_replaces_stale_inputs_not_merges above), but the manifest glob copy
    (`cp "$corpus_dir"/sweep_manifest*.json ...`) was left as merge-semantics -- the identical
    "stale artifact silently survives" defect (#62's whole reason for existing), just for the
    manifest instead of inputs/.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    workspace.mkdir(parents=True)
    stale_manifest = workspace / "sweep_manifest.legacy_extra.json"
    stale_manifest.write_text("{}", encoding="utf-8")

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert not stale_manifest.exists(), (
        "a manifest file no longer present in the corpus must not survive provisioning"
    )
    assert (workspace / "sweep_manifest.json").exists()
    assert (workspace / "sweep_manifest.units.json").exists()


def test_provision_fails_on_corpus_workspace_basename_mismatch(
    tmp_path, canonical_wing_vertex
):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep_fine"  # deliberately mismatched

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
    )

    assert result.returncode != 0
    assert not invoked_marker.exists()
    # Full quoted strings, not bare substrings -- "prelim_sweep" is itself a substring of
    # "prelim_sweep_fine", so asserting the bare words would be trivially satisfied by either half
    # alone. Confirm the error names both full paths distinctly.
    assert f"'{corpus}'" in result.stderr
    assert f"'{workspace}'" in result.stderr


def test_no_provision_flag_skips_copy_but_still_submits(
    tmp_path, canonical_wing_vertex
):
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    workspace.mkdir(parents=True)
    (workspace / "sentinel.txt").write_text(
        "pre-existing, untouched\n", encoding="utf-8"
    )

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


def test_no_provision_flag_skips_copy_but_still_submits_for_smoke(
    tmp_path, canonical_wing_vertex
):
    """The `--no-provision` gate is identically wired at the `smoke` call site, not just `full`."""
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=False)
    workspace = tmp_path / "workspace" / "prelim_sweep"
    workspace.mkdir(parents=True)
    (workspace / "sentinel.txt").write_text(
        "pre-existing, untouched\n", encoding="utf-8"
    )

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "smoke",
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
def test_provisioned_wing_vertex_matches_canonical_source(
    tmp_path, canonical_wing_vertex, corpus_name
):
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


def test_to_local_path_translation_via_env_override(tmp_path, canonical_wing_vertex):
    """Confirms the CLUSTER_NFS_PREFIX/LOCAL_NFS_PREFIX translation seam works end-to-end.

    submit_workflow.sh dispatches on $1 immediately rather than exposing to_local_path as a
    separately-sourceable library function, so this exercises it end-to-end: point a
    --workspace-hostpath that DOES start with the (overridden) CLUSTER_NFS_PREFIX, override
    LOCAL_NFS_PREFIX to a tmp_path root, and confirm provisioning lands under the translated
    (tmp_path) location -- not literally under /hpi/hpi_dev, which doesn't exist on this test host.
    This is deliberately an OVERRIDE test (proving the seam works), distinct from
    test_to_local_path_uses_real_default_prefix_mapping below (proving TODAY'S actual default is
    correct) -- neither one alone proves both properties.
    """
    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    cluster_style_workspace = (
        "/hpi/hpi_dev/users/testuser/mosquito-cfd/examples/prelim_sweep"
    )
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


def test_to_local_path_uses_real_default_prefix_mapping():
    """Proves TODAY'S real default /hpi/hpi_dev -> /mnt/hpi_dev mapping is correct.

    A pure string-substitution check with NO env override and no filesystem access -- sources the
    script (via `--help`, which runs no destructive action) so `to_local_path` is directly callable
    with the production defaults, closing the gap where nothing previously verified the literal
    default string (every other test overrides LOCAL_NFS_PREFIX/CLUSTER_NFS_PREFIX to a tmp_path
    root, so a future typo in the real default would have gone undetected).
    """
    script = (
        f"source {str(_SUBMIT_SH)!r} --help >/dev/null 2>&1\n"
        'to_local_path "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep"\n'
    )
    result = subprocess.run(
        [_BASH, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert (
        result.stdout.strip()
        == "/mnt/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep"
    )


def test_to_local_path_does_not_match_a_sibling_prefix():
    """A cluster export sharing the prefix STRING but not the path must not be mistranslated.

    Regression: the original `case "$p" in "$CLUSTER_NFS_PREFIX"*)` had no path-boundary check, so
    /hpi/hpi_dev_archive (a different, sibling export) would have matched the /hpi/hpi_dev prefix
    and been silently rewritten to /mnt/hpi_dev_archive -- a path that has no relationship to the
    real /hpi/hpi_dev -> /mnt/hpi_dev WSL mount.
    """
    script = (
        f"source {str(_SUBMIT_SH)!r} --help >/dev/null 2>&1\n"
        'to_local_path "/hpi/hpi_dev_archive/users/eberrigan/somewhere"\n'
    )
    result = subprocess.run(
        [_BASH, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    # Must pass through unchanged (no local mount known for this sibling export) -- NOT translated
    # under /mnt/hpi_dev, which would silently point at the wrong tree.
    assert result.stdout.strip() == "/hpi/hpi_dev_archive/users/eberrigan/somewhere"


def test_corpus_dir_and_workspace_hostpath_defaults_share_a_basename():
    """Static guard: the script's own hardcoded defaults must name the same corpus.

    Nothing else pins this invariant -- a future edit to only one default (exactly the failure
    class this whole change fixes) would go undetected until a real cluster submission hit the
    basename-mismatch guard live.
    """
    script = f'source {str(_SUBMIT_SH)!r} --help >/dev/null 2>&1\necho "$CORPUS_DIR|$WORKSPACE_HOSTPATH"\n'
    result = subprocess.run(
        [_BASH, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    corpus_dir, workspace_hostpath = result.stdout.strip().split("|")
    assert Path(corpus_dir).name == Path(workspace_hostpath).name


def test_help_documents_the_new_provisioning_flags():
    result = subprocess.run(
        [_BASH, str(_SUBMIT_SH), "help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--corpus-dir" in result.stdout
    assert "--no-provision" in result.stdout


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


def test_provision_dies_on_wing_vertex_hash_mismatch(tmp_path, canonical_wing_vertex):
    """The hash-verification `die` branch itself actually fires -- not just the happy path.

    This is the headline safety mechanism the whole PR exists to add (the motivating incident was
    a wing.vertex that silently didn't match any committed version for over a month); every other
    test here only exercises matching hashes or upstream failures (missing source file). A `cp`
    always makes the destination byte-identical to the source, so `expected != actual` cannot occur
    from any real filesystem state reachable in this test setup -- it can only be forced by
    substituting the hashing tool itself. `submit_workflow.sh`'s `SHA256SUM="${SHA256SUM:-sha256sum}"`
    is overridable for exactly this reason: some shells resolve well-known coreutils names (like
    `sha256sum`) to a fixed trusted location regardless of `PATH`, which is what `argo`'s
    PATH-based stub relies on -- `sha256sum` needed a dedicated override seam instead.
    """
    real_sha256sum = shutil.which("sha256sum")
    assert real_sha256sum, "sha256sum must be on PATH for this test to be meaningful"

    corpus = _make_corpus(tmp_path / "corpus", "prelim_sweep", with_manifest=True)
    workspace = tmp_path / "workspace" / "prelim_sweep"

    # provision() calls $SHA256SUM exactly twice, in order: once on $WING_VERTEX_SOURCE (the
    # source), then once on the provisioned destination copy. Counting invocations (via a counter
    # file) is robust regardless of how bash represents either path on this platform -- only the
    # 2nd (destination) call gets a wrong hash; the 1st (source) call delegates to the real tool.
    stub_dir = tmp_path / "stub_bin"
    stub_dir.mkdir(exist_ok=True)
    call_counter = tmp_path / "sha256sum_call_count"
    stub_sha256sum = stub_dir / "stub_sha256sum"
    stub_sha256sum.write_text(
        "#!/bin/sh\n"
        f'COUNT_FILE="{call_counter}"\n'
        'N=$( [ -f "$COUNT_FILE" ] && cat "$COUNT_FILE" || echo 0 )\n'
        "N=$((N + 1))\n"
        'echo "$N" > "$COUNT_FILE"\n'
        'if [ "$N" = "1" ]; then\n'
        f'  exec "{real_sha256sum}" "$1"\n'
        "else\n"
        '  echo "0000000000000000000000000000000000000000000000000000000000000000  $1"\n'
        "fi\n",
        encoding="utf-8",
    )
    stub_sha256sum.chmod(0o755)

    result, invoked_marker = _run_submit_workflow(
        tmp_path,
        "full",
        ["--corpus-dir", str(corpus), "--workspace-hostpath", str(workspace)],
        extra_env={"SHA256SUM": str(stub_sha256sum)},
    )

    assert result.returncode != 0
    assert "hash mismatch" in result.stderr
    assert not invoked_marker.exists(), "argo submit must not run after a hash mismatch"
