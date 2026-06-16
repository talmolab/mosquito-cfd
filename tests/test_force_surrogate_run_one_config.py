"""Tests for force_surrogate.run_one_config (TDD, add-force-surrogate-argo-sweep).

Cluster-free (roadmap CC-2): the CFD run is an injected fake ``mpi_runner`` that writes a
synthetic CSV into the cwd it is handed — no RunAI, GPU, container, or plotfiles. Synthetic CSVs
are written LF-explicit (``write_bytes``, via the PR3 helper pattern) so row counts match on
Windows (dev) and Linux (CI); layout assertions compare ``Path`` objects, never ``/``-joined
strings.

Imports are from the **submodule** ``mosquito_cfd.force_surrogate.run_one_config`` (never the
top-level re-export) so a missing/renamed symbol surfaces here, not as a silent fallback (the PR3
lesson). The ``__init__`` re-export is checked separately by ``test_run_config_is_reexported``.
"""

import ast
import inspect
import json
import re
from pathlib import Path

import pytest

import mosquito_cfd.force_surrogate as pkg
from mosquito_cfd.force_surrogate import run_one_config as roc_mod
from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS
from mosquito_cfd.force_surrogate.run_one_config import main, run_config
from mosquito_cfd.force_surrogate.runner import IB_PARTICLE_CSV, RUN_LOG, ExecResult

# Obviously-synthetic sentinel digest — a test never ran a real container.
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "0" * 64
MUTABLE_TAG = "ghcr.io/talmolab/mosquito-cfd:latest"
TS = "2026-06-30T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers (mirror the PR3 runner test helpers)
# ---------------------------------------------------------------------------


def _write_csv(path: Path, n_rows: int, *, newline="\n"):
    """Write a synthetic IB-particle CSV with ``n_rows`` data rows (LF-explicit)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(IB_PARTICLE_COLUMNS)]
    row = ",".join(["0"] * len(IB_PARTICLE_COLUMNS))
    lines.extend(row for _ in range(n_rows))
    text = newline.join(lines) + newline
    path.write_bytes(text.encode("utf-8"))


def _walk_strings(obj):
    """Yield every string nested anywhere in a JSON-like structure (keys and values)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_strings(key)
            yield from _walk_strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _walk_strings(value)


def _assert_portable(meta: dict):
    """No nested string is an absolute host mount path (drive-letter or /hpi/)."""
    for s in _walk_strings(meta):
        assert not re.match(r"^[A-Za-z]:[\\/]", s), f"absolute drive path leaked: {s!r}"
        assert not s.startswith("/hpi/"), f"absolute cluster path leaked: {s!r}"


class FakeRunner:
    """Records each (argv, cwd) and simulates a run by writing a CSV into the cwd it is handed."""

    def __init__(
        self,
        *,
        rows=5,
        returncode=0,
        raise_exc=None,
        csv_name=IB_PARTICLE_CSV,
        stdout="",
        stderr="",
        write=True,
    ):
        self.calls: list[tuple[list[str], Path]] = []
        self.rows = rows
        self.returncode = returncode
        self.raise_exc = raise_exc
        self.csv_name = csv_name
        self.stdout = stdout
        self.stderr = stderr
        self.write = write

    def __call__(self, argv, *, cwd) -> ExecResult:
        self.calls.append((list(argv), Path(cwd)))
        if self.raise_exc is not None:
            raise self.raise_exc("simulated runner error")
        if self.write:
            _write_csv(Path(cwd) / self.csv_name, self.rows)
        return ExecResult(self.returncode, self.stdout, self.stderr)


def _setup(
    tmp_path: Path, *, name="s35_f085_p30", max_step=5, input_file=None, make_deck=True
):
    """Stage a deck + wing.vertex under tmp_path/ws and return run_config kwargs.

    ``container_workspace`` stays the portable default ``/workspace`` so the recorded command is
    portable; ``deck_path`` points at the real fixture deck so ``deck_sha256`` is computed.
    """
    input_file = input_file or f"inputs/inputs.3d.{name}"
    ws = tmp_path / "ws"
    deck = ws / input_file
    if make_deck:
        deck.parent.mkdir(parents=True, exist_ok=True)
        deck.write_text(f"# deck {name}\n", encoding="utf-8")
    wing = ws / "wing.vertex"
    wing.parent.mkdir(parents=True, exist_ok=True)
    wing.write_text("0 0 0\n", encoding="utf-8")
    return {
        "name": name,
        "input_file": input_file,
        "max_step": max_step,
        "output_root": tmp_path / "runs",
        "docker_digest": DIGEST,
        "timestamp": TS,
        "wing_vertex": str(wing),
        "deck_path": str(deck),
    }


def _read_meta(output_root, name):
    return json.loads(
        (Path(output_root) / name / "run_metadata.json").read_text("utf-8")
    )


def _main_argv(tmp_path, *, name="cfg_a", max_step=5, **over):
    """Build a main() argv with a real wing.vertex/deck staged under tmp_path."""
    ws = tmp_path / "ws"
    deck = ws / "inputs" / f"inputs.3d.{name}"
    deck.parent.mkdir(parents=True, exist_ok=True)
    deck.write_text("# deck\n", encoding="utf-8")
    wing = ws / "wing.vertex"
    wing.write_text("0 0 0\n", encoding="utf-8")
    argv = [
        "--config-name",
        name,
        "--input-file",
        f"inputs/inputs.3d.{name}",
        "--max-step",
        str(max_step),
        "--output-root",
        str(tmp_path / "runs"),
        "--docker-digest",
        DIGEST,
        "--timestamp",
        TS,
        "--wing-vertex",
        str(wing),
        "--deck-path",
        str(deck),
    ]
    for key, value in over.items():
        argv.extend([f"--{key.replace('_', '-')}", str(value)])
    return argv


# ---------------------------------------------------------------------------
# Single-configuration pod run
# ---------------------------------------------------------------------------


def test_completed_run_writes_checked_output_and_provenance(tmp_path):
    """Scenario: Completed run writes the checked output and provenance."""
    kw = _setup(tmp_path, name="s35_f085_p30", max_step=5)
    fake = FakeRunner(rows=5, stdout="solver ok\n")
    outcome = run_config(**kw, mpi_runner=fake)

    assert outcome.status == "completed"
    csv_path = Path(kw["output_root"]) / "s35_f085_p30" / IB_PARTICLE_CSV
    assert outcome.csv_path == csv_path and csv_path.exists()
    assert (Path(kw["output_root"]) / "s35_f085_p30" / RUN_LOG).read_text(
        "utf-8"
    ) == "solver ok\n"

    meta = _read_meta(kw["output_root"], "s35_f085_p30")
    assert meta["docker_image"] == DIGEST
    assert meta["deck_sha256"] is not None  # deck present → hashed
    assert meta["timestamp"] == TS
    assert meta["command"] == [
        "mpirun", "--allow-run-as-root", "-np", "1",
        "/opt/cfd/IAMReX/Tutorials/FlowPastSphere/amr3d.gnu.MPI.CUDA.ex",
        "/workspace/inputs/inputs.3d.s35_f085_p30",
    ]  # fmt: skip
    assert meta["status"] == "completed"
    # the recorded argv matches what the runner was actually handed
    assert fake.calls[0][0] == meta["command"]


def test_wing_geometry_is_staged_into_run_dir(tmp_path):
    """Scenario: Wing geometry is staged into the run directory."""
    kw = _setup(tmp_path, name="cfg_a")
    run_config(**kw, mpi_runner=FakeRunner(rows=5))
    staged = Path(kw["output_root"]) / "cfg_a" / "wing.vertex"
    assert staged.exists()
    assert staged.read_bytes() == Path(kw["wing_vertex"]).read_bytes()


def test_incomplete_run_signals_retry_exit_codes(tmp_path):
    """Scenario: Incomplete run signals retry — main() exit 0 iff completed else 1."""
    # full → 0
    assert (
        main(_main_argv(tmp_path / "full", max_step=5), mpi_runner=FakeRunner(rows=5))
        == 0
    )
    # short CSV (runner returned 0 but too few rows) → 1
    assert (
        main(_main_argv(tmp_path / "short", max_step=5), mpi_runner=FakeRunner(rows=2))
        == 1
    )
    # non-zero runner return → 1
    assert (
        main(
            _main_argv(tmp_path / "rc", max_step=5),
            mpi_runner=FakeRunner(rows=5, returncode=6),
        )
        == 1
    )


def test_run_config_short_csv_is_failed_with_metadata(tmp_path):
    """A short CSV → status failed, metadata still written (auditable)."""
    kw = _setup(tmp_path, name="cfg_a", max_step=10)
    outcome = run_config(**kw, mpi_runner=FakeRunner(rows=2))
    assert outcome.status == "failed"
    assert _read_meta(kw["output_root"], "cfg_a")["status"] == "failed"


def test_native_compute_hardware_no_override(tmp_path):
    """Scenario: Native compute hardware — base local capture, no exec-probe override."""
    kw = _setup(tmp_path, name="cfg_a")
    run_config(**kw, mpi_runner=FakeRunner(rows=5))
    hw = _read_meta(kw["output_root"], "cfg_a")["hardware"]
    # base get_hardware_info shape (robust to CI gpus:[] and a dev GPU); never assert gpus==[]
    assert "hostname" in hw
    assert (
        "source" not in hw and "workspace" not in hw
    )  # the override-only keys are absent


def test_native_hardware_is_structurally_native():
    """Scenario: Native compute hardware — provable cluster-free (AST + signature, no GPU)."""
    tree = ast.parse(inspect.getsource(roc_mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.update(alias.name for alias in node.names)
            if node.module:
                imported.add(node.module)
    # the module must NOT reach the laptop driver's exec-probe override
    assert "capture_compute_hardware" not in imported
    assert "build_probe_command" not in imported
    params = inspect.signature(run_config).parameters
    for forbidden in ("hardware", "compute_hardware", "executor"):
        assert forbidden not in params


def test_run_config_reuses_pr3_library_imports():
    """Reuse, not reimplementation: the PR3 library symbols are imported (positive AST check)."""
    tree = ast.parse(inspect.getsource(roc_mod))
    from_imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            from_imported.update(alias.name for alias in node.names)
    for symbol in (
        "check_completion",
        "capture_surrogate_run_metadata",
        "_format_run_log",
    ):
        assert symbol in from_imported, (
            f"{symbol} must be reused from the PR3 library, not reimplemented"
        )


def test_run_config_invokes_check_completion(tmp_path, monkeypatch):
    """Reuse is enforced by behaviour too: run_config actually calls runner.check_completion."""
    calls = []
    real = roc_mod.check_completion

    def spy(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(roc_mod, "check_completion", spy)
    kw = _setup(tmp_path, name="cfg_a")
    run_config(**kw, mpi_runner=FakeRunner(rows=5))
    assert calls, "run_config must invoke the reused check_completion, not a copy"


def test_mutable_tag_rejected(tmp_path):
    """Scenario: Mutable tag rejected."""
    kw = _setup(tmp_path, name="cfg_a")
    kw["docker_digest"] = MUTABLE_TAG
    with pytest.raises(ValueError, match="sha256"):
        run_config(**kw, mpi_runner=FakeRunner(rows=5))


def test_malformed_config_fails_fast(tmp_path):
    """Scenario: Malformed configuration fails fast — no runner call, clear ValueError."""
    # non-positive max_step
    kw = _setup(tmp_path, name="cfg_a", max_step=0)
    fake = FakeRunner(rows=5)
    with pytest.raises(ValueError, match="cfg_a"):
        run_config(**kw, mpi_runner=fake)
    assert fake.calls == []  # rejected before any runner invocation
    # empty input_file
    kw2 = _setup(tmp_path, name="cfg_b")
    kw2["input_file"] = ""
    fake2 = FakeRunner(rows=5)
    with pytest.raises(ValueError, match="cfg_b"):
        run_config(**kw2, mpi_runner=fake2)
    assert fake2.calls == []
    # empty name
    kw3 = _setup(tmp_path, name="cfg_c")
    kw3["name"] = ""
    fake3 = FakeRunner(rows=5)
    with pytest.raises(ValueError, match="empty"):
        run_config(**kw3, mpi_runner=fake3)
    assert fake3.calls == []
    # non-integer max_step (a library caller; argparse shields main, run_config guards itself)
    kw4 = _setup(tmp_path, name="cfg_d")
    kw4["max_step"] = "not-an-int"
    fake4 = FakeRunner(rows=5)
    with pytest.raises(ValueError, match="cfg_d"):
        run_config(**kw4, mpi_runner=fake4)
    assert fake4.calls == []


def test_deck_path_defaults_to_container_workspace(tmp_path):
    """deck_path=None resolves the deck under container_workspace/input_file (the in-pod default)."""
    name = "cfg_a"
    input_file = f"inputs/inputs.3d.{name}"
    ws = tmp_path / "ws"
    deck = ws / input_file
    deck.parent.mkdir(parents=True, exist_ok=True)
    deck.write_text("# deck\n", encoding="utf-8")
    wing = ws / "wing.vertex"
    wing.write_text("0 0 0\n", encoding="utf-8")
    output_root = tmp_path / "runs"
    # container_workspace points at the real fixture dir, deck_path omitted → default branch
    run_config(
        name=name,
        input_file=input_file,
        max_step=5,
        output_root=output_root,
        docker_digest=DIGEST,
        timestamp=TS,
        mpi_runner=FakeRunner(rows=5),
        container_workspace=str(ws),
        wing_vertex=str(wing),
    )
    assert (
        _read_meta(output_root, name)["deck_sha256"] is not None
    )  # default deck located + hashed


def test_malformed_config_main_argparse_rejects(tmp_path):
    """Scenario: Malformed configuration fails fast — main CLI rejects bad/missing --max-step."""
    # max_step 0 → run_config ValueError propagates (not a clean exit)
    with pytest.raises(ValueError):
        main(_main_argv(tmp_path / "zero", max_step=0), mpi_runner=FakeRunner(rows=5))
    # missing --max-step → argparse SystemExit (non-zero)
    argv = [a for a in _main_argv(tmp_path / "miss")]
    i = argv.index("--max-step")
    del argv[i : i + 2]
    with pytest.raises(SystemExit) as exc:
        main(argv, mpi_runner=FakeRunner(rows=5))
    assert exc.value.code != 0
    # non-integer --max-step → argparse SystemExit
    with pytest.raises(SystemExit):
        main(
            _main_argv(tmp_path / "nonint", max_step="abc"),
            mpi_runner=FakeRunner(rows=5),
        )


def test_raised_runner_is_clean_failure(tmp_path):
    """Scenario: A raised runner is a clean failure, not a crash."""
    kw = _setup(tmp_path, name="cfg_a")
    outcome = run_config(**kw, mpi_runner=FakeRunner(raise_exc=OSError))
    assert outcome.status == "failed"
    meta = _read_meta(kw["output_root"], "cfg_a")
    assert meta["status"] == "failed"
    log = (Path(kw["output_root"]) / "cfg_a" / RUN_LOG).read_text("utf-8")
    assert "OSError" in log  # repr(exc) captured in run.log, not an uncaught traceback
    # main() returns non-zero for the same case
    assert (
        main(_main_argv(tmp_path / "raise"), mpi_runner=FakeRunner(raise_exc=OSError))
        == 1
    )


def test_provenance_is_portable(tmp_path):
    """Scenario: Provenance is portable — no absolute host mount path leaks."""
    kw = _setup(tmp_path, name="cfg_a")
    run_config(
        **kw,
        mpi_runner=FakeRunner(rows=5),
        extra_provenance={
            "workflow_uid": "u1",
            "pod": "p1",
            "node": "n1",
            "retry": "0",
        },
    )
    meta = _read_meta(kw["output_root"], "cfg_a")
    _assert_portable(meta)
    assert meta["deck"] == "inputs/inputs.3d.cfg_a"  # manifest-relative, not absolute
    assert "/workspace/" in meta["command"][-1]  # container path in the command


def test_extra_provenance_none_default(tmp_path):
    """Default extra_provenance=None writes valid metadata with no orchestration block."""
    kw = _setup(tmp_path, name="cfg_a")
    run_config(**kw, mpi_runner=FakeRunner(rows=5))  # extra_provenance defaults to None
    meta = _read_meta(kw["output_root"], "cfg_a")
    assert "orchestration" not in meta


def test_main_argparse_to_provenance_plumbing(tmp_path):
    """The --workflow-uid/--pod/--node/--retry flows reach run_metadata under 'orchestration'."""
    argv = _main_argv(
        tmp_path,
        name="cfg_a",
        workflow_uid="abc",
        pod="pod-x",
        node="node-y",
        retry="2",
    )
    assert main(argv, mpi_runner=FakeRunner(rows=5)) == 0
    meta = _read_meta(tmp_path / "runs", "cfg_a")
    assert meta["orchestration"] == {
        "workflow_uid": "abc",
        "pod": "pod-x",
        "node": "node-y",
        "retry": "2",
    }


def test_container_workspace_is_honoured(tmp_path):
    """A non-default container_workspace changes the recorded deck path (not hardcoded)."""
    kw = _setup(tmp_path, name="cfg_a")
    run_config(**kw, mpi_runner=FakeRunner(rows=5), container_workspace="/data")
    meta = _read_meta(kw["output_root"], "cfg_a")
    assert meta["command"][-1] == "/data/inputs/inputs.3d.cfg_a"


def test_retry_overwrites_in_place(tmp_path):
    """D6: a second run (Argo retry) overwrites the run dir's artifacts — last write wins."""
    kw = _setup(tmp_path, name="cfg_a", max_step=5)
    # first attempt: short CSV → failed
    run_config(**kw, mpi_runner=FakeRunner(rows=2))
    assert _read_meta(kw["output_root"], "cfg_a")["status"] == "failed"
    # retry on the same run dir: full CSV → completed, single metadata/log (no *.1 duplication)
    run_config(**kw, mpi_runner=FakeRunner(rows=5))
    run_dir = Path(kw["output_root"]) / "cfg_a"
    assert _read_meta(kw["output_root"], "cfg_a")["status"] == "completed"
    assert sorted(p.name for p in run_dir.glob("run_metadata.json*")) == [
        "run_metadata.json"
    ]
    assert sorted(p.name for p in run_dir.glob("run.log*")) == ["run.log"]


def test_name_with_path_separator_is_rejected(tmp_path):
    """A config name that is not a single path segment is rejected (can't escape output_root)."""
    for bad in ("../evil", "a/b", "sub/../../x"):
        kw = _setup(tmp_path, name="cfg_a")
        kw["name"] = bad
        fake = FakeRunner(rows=5)
        with pytest.raises(ValueError, match="single path segment"):
            run_config(**kw, mpi_runner=fake)
        assert fake.calls == []  # rejected before any runner invocation


def test_missing_wing_vertex_is_clean_failure(tmp_path):
    """A missing wing.vertex source is a clean failed run (metadata written), not an uncaught crash."""
    kw = _setup(tmp_path, name="cfg_a")
    kw["wing_vertex"] = str(tmp_path / "does_not_exist.vertex")  # source missing
    outcome = run_config(**kw, mpi_runner=FakeRunner(rows=5))
    assert outcome.status == "failed"
    meta = _read_meta(kw["output_root"], "cfg_a")
    assert meta["status"] == "failed"
    log = (Path(kw["output_root"]) / "cfg_a" / RUN_LOG).read_text("utf-8")
    assert (
        "Error" in log or "error" in log
    )  # the staging exception is captured, not a traceback
    # main() returns non-zero for the same case (Argo retries on a fresh pod)
    argv = _main_argv(tmp_path / "mw", name="cfg_b")
    i = argv.index("--wing-vertex")
    argv[i + 1] = str(tmp_path / "missing.vertex")
    assert main(argv, mpi_runner=FakeRunner(rows=5)) == 1


def test_csv_name_is_threaded(tmp_path):
    """--csv-name (the escape hatch) flows to the verified/recorded CSV name."""
    kw = _setup(tmp_path, name="cfg_a", max_step=5)
    run_config(
        **kw,
        mpi_runner=FakeRunner(rows=5, csv_name="forces.csv"),
        csv_name="forces.csv",
    )
    meta = _read_meta(kw["output_root"], "cfg_a")
    assert meta["ib_particle_csv"] == "cfg_a/forces.csv"
    assert (Path(kw["output_root"]) / "cfg_a" / "forces.csv").exists()
    # via main: a wrong default name (no fake CSV under it) → incomplete → exit 1
    assert (
        main(
            _main_argv(tmp_path / "wrong", csv_name="forces.csv"),
            mpi_runner=FakeRunner(rows=5),
        )
        == 1
    )


def test_run_config_is_reexported():
    """The top-level package re-exports run_config (mirrors the PR3 public-API convention)."""
    assert hasattr(pkg, "run_config")
    assert pkg.run_config is run_config


def test_subprocess_mpi_runner_maps_returncode_and_output(tmp_path):
    """The real runner wraps subprocess.run into an ExecResult (portable, no cluster needed)."""
    import sys

    result = roc_mod._subprocess_mpi_runner(
        [sys.executable, "-c", "import sys; print('hi'); sys.exit(3)"],
        cwd=tmp_path,
    )
    assert result.returncode == 3
    assert "hi" in result.stdout
