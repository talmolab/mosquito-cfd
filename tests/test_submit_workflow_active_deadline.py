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
import json
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


def _make_manifest_corpus(root: Path, name: str, n_configs: int) -> Path:
    """Build a fixture corpus dir with just a ``sweep_manifest.json`` (the real production
    schema, ``{"configs": [...]}`` -- confirmed against ``examples/prelim_sweep_fine/
    sweep_manifest.json``; NOT ``{"n_configs": N}``, since ``compute_auto_deadline_seconds``
    reads ``json.load(...)["configs"]``). ``inputs/`` is deliberately omitted: with
    ``--no-provision`` baked in, ``provision()`` never runs, so only the manifest matters.
    """
    corpus = root / name
    corpus.mkdir(parents=True)
    configs = [{"name": f"config_{i}"} for i in range(n_configs)]
    (corpus / "sweep_manifest.json").write_text(
        json.dumps({"configs": configs}), encoding="utf-8"
    )
    return corpus


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


# ---------------------------------------------------------------------------
# 3. Auto-scale fallback when --parallelism is overridden without an explicit deadline
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_value", ["0", "-1", "abc"])
def test_invalid_parallelism_still_rejected_cleanly_when_autoscale_would_fire(
    tmp_path, bad_value
):
    """Regression test: an earlier draft resolved effective_deadline (and called the auto-scale
    python one-liner) BEFORE validating $PARALLELISM's format, so `0` reached a
    ZeroDivisionError and `abc` reached a ValueError -- both uncaught Python tracebacks instead
    of a clean die(). The real default --corpus-dir (examples/prelim_sweep) has a real manifest,
    so auto-scale would actually be attempted if the validation-ordering bug were reintroduced.
    """
    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path, ["--parallelism", bad_value]
    )

    assert result.returncode != 0
    assert "positive integer" in result.stderr
    assert "Traceback" not in result.stderr
    assert not invoked_marker.exists()


@pytest.mark.parametrize("parallelism,expected", [("1", 43200), ("3", 25200)])
def test_parallelism_without_explicit_deadline_autoscales(
    tmp_path, parallelism, expected
):
    # ceil(3 * 2.4 / parallelism + 4) * 3600:
    #   parallelism=1: ceil(7.2/1 + 4)  = ceil(11.2) = 12 -> 43200
    #   parallelism=3: ceil(7.2/3 + 4)  = ceil(6.4)  = 7  -> 25200
    # --workspace-hostpath's basename must match --corpus-dir's (the new consistency check that
    # scopes auto-scale to a workspace/corpus pair it can trust) -- any path works since
    # --no-provision means it's never actually touched, only its basename is compared.
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            parallelism,
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(tmp_path / corpus.name),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert f"activeDeadlineSeconds: {expected}" in capture_file.read_text()


def test_autoscale_zero_configs_degenerates_to_retry_margin_only(tmp_path):
    corpus = _make_manifest_corpus(tmp_path, "empty_corpus", n_configs=0)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(tmp_path / corpus.name),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "activeDeadlineSeconds: 14400" in capture_file.read_text()


def test_autoscale_with_very_large_parallelism_does_not_crash_or_underflow(tmp_path):
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1000000",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(tmp_path / corpus.name),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    # ceil(3*2.4/1000000 + 4)*3600 = ceil(4.0000072)*3600 = 5*3600 = 18000 (not 14400 --
    # math.ceil rounds up past any nonzero fractional remainder, however tiny).
    assert "activeDeadlineSeconds: 18000" in capture_file.read_text()


def test_explicit_active_deadline_takes_precedence_over_autoscale(tmp_path):
    missing_corpus = tmp_path / "does_not_exist"

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--active-deadline-seconds",
            "999999",
            "--corpus-dir",
            str(missing_corpus),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "activeDeadlineSeconds: 999999" in capture_file.read_text()


def test_autoscale_missing_manifest_fails_with_clear_message_not_a_traceback(tmp_path):
    corpus = tmp_path / "corpus_without_manifest"
    corpus.mkdir()

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "2",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(tmp_path / corpus.name),
        ],
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert not invoked_marker.exists()


@pytest.mark.parametrize(
    "case_id,manifest_text",
    [
        ("invalid_json", "not valid json {{{"),
        ("missing_configs_key", json.dumps({"no_configs_key": []})),
        ("configs_is_null", json.dumps({"configs": None})),
        ("configs_is_a_string", json.dumps({"configs": "not-a-list"})),
        ("configs_is_a_dict", json.dumps({"configs": {"a": 1}})),
    ],
    ids=[
        "invalid_json",
        "missing_configs_key",
        "configs_is_null",
        "configs_is_a_string",
        "configs_is_a_dict",
    ],
)
def test_autoscale_malformed_manifest_fails_with_clear_message_not_a_traceback(
    tmp_path, case_id, manifest_text
):
    """Regression test covering every malformed shape the delta spec enumerates (invalid JSON,
    a missing "configs" key, and "configs" present but not a list) -- not just the single
    non-list case a code-quality review round found by live-reproducing a KeyError. None of
    these must leak a raw Python traceback.
    """
    corpus = tmp_path / f"malformed_corpus_{case_id}"
    corpus.mkdir()
    (corpus / "sweep_manifest.json").write_text(manifest_text, encoding="utf-8")

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "2",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(tmp_path / corpus.name),
        ],
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert not invoked_marker.exists()


def test_autoscale_dies_on_corpus_workspace_basename_mismatch(tmp_path):
    """Regression test: --no-provision skips provision()'s own basename-match guard, so without
    a separate check, auto-scale would silently compute a deadline from the WRONG corpus's
    manifest if --workspace-hostpath doesn't match --corpus-dir.
    """
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)
    mismatched_workspace = tmp_path / "a_totally_different_corpus_name"

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(mismatched_workspace),
        ],
    )

    assert result.returncode != 0
    assert "same corpus" in result.stderr
    assert not invoked_marker.exists()


def test_explicit_deadline_skips_the_basename_check_entirely(tmp_path):
    """An explicit --active-deadline-seconds never triggers auto-scale, so a mismatched
    --corpus-dir/--workspace-hostpath pair (which WOULD block auto-scale) does not block this.
    """
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)
    mismatched_workspace = tmp_path / "a_totally_different_corpus_name"

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--active-deadline-seconds",
            "999999",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(mismatched_workspace),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "activeDeadlineSeconds: 999999" in capture_file.read_text()


def _write_fake_interpreter(path: Path, marker: Path) -> None:
    """A self-contained fake interpreter -- no real Python needed (avoids Windows-path/exec
    portability issues entirely). It only needs to satisfy the two call shapes
    compute_auto_deadline_seconds actually uses: the presence probe (`-c ""`, must exit 0) and
    the real computation (`-c '<code>' manifest_path parallelism`, must print the expected
    result for this test file's fixed n_configs=3/parallelism=1 inputs). It also touches
    `marker` on the REAL computation call (not the presence probe) so tests can prove WHICH
    interpreter actually ran, not just that auto-scale succeeded somehow.
    """
    path.write_text(
        f'#!/bin/sh\nif [ -z "$2" ]; then exit 0; fi\ntouch "{marker}"\necho 43200\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_broken_interpreter(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\necho 'not a real interpreter' >&2\nexit 1\n", encoding="utf-8"
    )
    path.chmod(0o755)


def test_autoscale_prefers_python3_when_it_works(tmp_path):
    """python3 is tried FIRST -- when it works, python (the fallback) must never even run."""
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)
    interpreter_dir = tmp_path / "interpreter_bin"
    interpreter_dir.mkdir()
    python3_marker = tmp_path / "python3_ran"
    python_marker = tmp_path / "python_ran"
    _write_fake_interpreter(interpreter_dir / "python3", python3_marker)
    _write_fake_interpreter(interpreter_dir / "python", python_marker)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(corpus),
        ],
        # NOTE: extra_env overwrites (not merges with) the helper's own PATH, which prepends
        # its stub_dir (always tmp_path / "stub_bin") ahead of the real PATH so the stub `argo`
        # is found -- reconstruct that same ordering here with interpreter_dir prepended first,
        # or the argo stub would silently stop being found (and the real `argo`, if any is on
        # PATH, could be invoked instead).
        extra_env={
            "PATH": f"{interpreter_dir}{os.pathsep}{tmp_path / 'stub_bin'}{os.pathsep}{os.environ['PATH']}"
        },
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "activeDeadlineSeconds: 43200" in capture_file.read_text()
    assert python3_marker.exists(), "python3 should have run the real computation"
    assert not python_marker.exists(), (
        "python (the fallback) must never run when python3 works"
    )


def test_autoscale_falls_back_to_python_when_python3_is_broken(tmp_path):
    """The real gap this closes: a non-functional `python3` (e.g. Windows's App-Execution-Alias
    stub) that resolves via `command -v` but fails when actually invoked. python3 is present
    but broken; python must be tried next and actually used.
    """
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)
    interpreter_dir = tmp_path / "interpreter_bin"
    interpreter_dir.mkdir()
    python_marker = tmp_path / "python_ran"
    _write_broken_interpreter(interpreter_dir / "python3")
    _write_fake_interpreter(interpreter_dir / "python", python_marker)

    result, capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(corpus),
        ],
        extra_env={
            "PATH": f"{interpreter_dir}{os.pathsep}{tmp_path / 'stub_bin'}{os.pathsep}{os.environ['PATH']}"
        },
    )

    assert result.returncode == 0, result.stderr
    assert invoked_marker.exists()
    assert "activeDeadlineSeconds: 43200" in capture_file.read_text()
    assert python_marker.exists(), (
        "python (the fallback) should have run the real computation"
    )


def test_autoscale_dies_clearly_when_no_interpreter_works(tmp_path):
    """Both python3 and python are on PATH but neither actually runs -- must die() cleanly."""
    corpus = _make_manifest_corpus(tmp_path, "fixture_corpus", n_configs=3)
    interpreter_dir = tmp_path / "interpreter_bin"
    interpreter_dir.mkdir()
    for name in ("python3", "python"):
        _write_broken_interpreter(interpreter_dir / name)

    result, _capture_file, invoked_marker = _run_submit_workflow(
        tmp_path,
        [
            "--parallelism",
            "1",
            "--corpus-dir",
            str(corpus),
            "--workspace-hostpath",
            str(corpus),
        ],
        # See the sibling fallback test for why PATH must include the helper's stub_dir.
        extra_env={
            "PATH": f"{interpreter_dir}{os.pathsep}{tmp_path / 'stub_bin'}{os.pathsep}{os.environ['PATH']}"
        },
    )

    assert result.returncode != 0
    assert "none found working" in result.stderr
    assert not invoked_marker.exists()
