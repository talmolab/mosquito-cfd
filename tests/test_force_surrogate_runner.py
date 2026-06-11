"""Tests for force_surrogate.runner (TDD, PR3).

Cluster-free (roadmap CC-2): every test runs against the committed
``examples/prelim_sweep/sweep_manifest.json``, the committed 29-column header
(``IB_PARTICLE_COLUMNS``), and synthetic CSVs/manifests written into ``tmp_path``. The cluster
launch is an injected fake ``executor`` — no RunAI, GPU, container, or plotfiles.

Synthetic CSVs are written LF-explicit (``write_bytes``) so row counts match on Windows (dev)
and Linux (CI); layout assertions compare ``Path`` objects, never ``/``-joined strings.
"""

import ast
import inspect
import json
import re
import shlex
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate import runner as runner_mod
from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS
from mosquito_cfd.force_surrogate.runner import (
    DEFAULT_IAMREX_BINARY,
    IB_PARTICLE_CSV,
    Completion,
    ExecResult,
    build_run_command,
    build_wsl_command,
    check_completion,
    run_sweep,
)

REPO = Path(__file__).resolve().parent.parent
COMMITTED_MANIFEST = REPO / "examples" / "prelim_sweep" / "sweep_manifest.json"

# Obviously-synthetic sentinel digest — a test never ran a real container.
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "0" * 64
TS = "2026-06-30T00:00:00+00:00"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, n_rows: int, *, header=True, newline="\n", good_header=True):
    """Write a synthetic IB-particle CSV with ``n_rows`` data rows (LF-explicit by default)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if header:
        cols = IB_PARTICLE_COLUMNS if good_header else ["wrong", "header"]
        lines.append(",".join(cols))
    row = ",".join(["0"] * len(IB_PARTICLE_COLUMNS))
    lines.extend(row for _ in range(n_rows))
    text = newline.join(lines)
    if lines:
        text += newline
    path.write_bytes(text.encode("utf-8"))


def _cfg(name: str, *, max_step: int = 5, **over):
    """A minimal sweep config carrying every key load_manifest_configs + the runner read."""
    config = {
        "index": 0,
        "name": name,
        "stroke_amp_deg": 45.0,
        "frequency_fstar": 1.0,
        "pitch_amp_deg": 45.0,
        "reynolds": 60.0,
        "split": "train",
        "input_file": f"inputs/inputs.3d.{name}",
        "max_step": max_step,
    }
    config.update(over)
    return config


def _make_manifest(tmp_path: Path, configs: list[dict], *, make_decks=True) -> Path:
    """Write a fixture manifest into tmp_path; optionally create each config's deck file."""
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(json.dumps({"configs": configs}), encoding="utf-8")
    if make_decks:
        for config in configs:
            if "input_file" in config:
                deck = tmp_path / config["input_file"]
                deck.parent.mkdir(parents=True, exist_ok=True)
                deck.write_text(f"# deck {config['name']}\n", encoding="utf-8")
    return manifest


class FakeExecutor:
    """Records each (command, cwd) and simulates a run by writing a CSV into the cwd it is handed."""

    def __init__(
        self, *, rows=5, rows_by_name=None, returncode_by_name=None, write=True
    ):
        self.calls: list[tuple[list[str], Path]] = []
        self.rows = rows
        self.rows_by_name = dict(rows_by_name or {})
        self.returncode_by_name = dict(returncode_by_name or {})
        self.write = write

    def __call__(self, command, *, cwd) -> ExecResult:
        cwd = Path(cwd)
        self.calls.append((list(command), cwd))
        name = cwd.name
        if self.write:
            _write_csv(cwd / IB_PARTICLE_CSV, self.rows_by_name.get(name, self.rows))
        return ExecResult(self.returncode_by_name.get(name, 0))

    @property
    def commands(self):
        return [c for c, _ in self.calls]

    @property
    def cwds(self):
        return [d for _, d in self.calls]

    @property
    def names(self):
        return [d.name for _, d in self.calls]


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


# ---------------------------------------------------------------------------
# build_run_command (spec: Per-configuration cluster run command construction)
# ---------------------------------------------------------------------------


def test_build_run_command_targets_run_dir_and_deck():
    """Spec: Command targets the per-config run directory and deck."""
    config = _cfg("s35_f085_p30", max_step=4706)
    cmd = build_run_command(config, workspace="sweep-runner")
    assert cmd[:5] == ["runai", "workspace", "exec", "sweep-runner", "--"]
    assert cmd[5:7] == ["sh", "-c"]
    inner = cmd[7]
    assert "cd /workspace/runs/s35_f085_p30" in inner
    assert "wing.vertex" in inner
    assert "mpirun --allow-run-as-root -np 1" in inner
    assert DEFAULT_IAMREX_BINARY in inner
    assert "/workspace/inputs/inputs.3d.s35_f085_p30" in inner


def test_build_run_command_all_committed_configs_distinct():
    """Spec: Every corpus configuration yields a distinct, correctly-targeted command."""
    configs = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))["configs"]
    run_dirs = []
    for config in configs:
        inner = build_run_command(config, workspace="ws")[7]
        assert f"/workspace/runs/{config['name']}" in inner
        assert f"/workspace/{config['input_file']}" in inner
        run_dirs.append(f"/workspace/runs/{config['name']}")
    assert len(configs) == 27
    assert len(set(run_dirs)) == 27


def test_build_run_command_is_pure_no_io(tmp_path):
    """Spec: Command construction is pure (no cluster, no I/O)."""
    before = set(tmp_path.iterdir())
    build_run_command(_cfg("x"), workspace="ws")
    assert set(tmp_path.iterdir()) == before


def test_build_run_command_missing_input_file_raises():
    """Spec: Configuration missing a consumed key is rejected (here at command construction)."""
    config = _cfg("x")
    del config["input_file"]
    with pytest.raises(ValueError, match="input_file"):
        build_run_command(config, workspace="ws")


# ---------------------------------------------------------------------------
# check_completion (spec: Run completion verification)
# ---------------------------------------------------------------------------


def test_check_completion_full_length_passes(tmp_path):
    """Spec: Full-length CSV passes."""
    csv = tmp_path / IB_PARTICLE_CSV
    _write_csv(csv, 5)
    result = check_completion(csv, 5)
    assert result == Completion(True, 5, "ok")


def test_check_completion_empty_and_short(tmp_path):
    """Spec: Empty and short CSVs are flagged incomplete."""
    empty = tmp_path / "empty.csv"
    _write_csv(empty, 0)
    assert check_completion(empty, 5) == Completion(False, 0, "empty")

    short = tmp_path / "short.csv"
    _write_csv(short, 2)
    res = check_completion(short, 5)
    assert not res.complete and res.reason == "short" and res.rows == 2


def test_check_completion_missing_and_bad_header(tmp_path):
    """Spec: Missing CSV and wrong header are distinguished."""
    assert check_completion(tmp_path / "nope.csv", 5) == Completion(False, 0, "missing")

    bad = tmp_path / "bad.csv"
    _write_csv(bad, 5, good_header=False)
    res = check_completion(bad, 5)
    assert not res.complete and res.reason == "bad_header"


def test_check_completion_threshold_boundary_is_exact(tmp_path):
    """Spec: Row-count threshold boundary is exact (ceil(4706*0.99) = 4659)."""
    ok = tmp_path / "ok.csv"
    _write_csv(ok, 4659)
    assert check_completion(ok, 4706, threshold=0.99) == Completion(True, 4659, "ok")

    just_short = tmp_path / "short.csv"
    _write_csv(just_short, 4658)
    res = check_completion(just_short, 4706, threshold=0.99)
    assert not res.complete and res.reason == "short" and res.rows == 4658


def test_check_completion_crlf_and_trailing_newline(tmp_path):
    """Spec: row count is correct for \\r\\n line endings and a trailing newline (no phantom row)."""
    crlf = tmp_path / "crlf.csv"
    _write_csv(crlf, 5, newline="\r\n")  # carriage returns exact via write_bytes
    assert check_completion(crlf, 5).rows == 5

    # A CSV that ends with a trailing newline must not count a phantom data row.
    trailing = tmp_path / "trailing.csv"
    header = ",".join(IB_PARTICLE_COLUMNS)
    body = "\n".join(",".join(["0"] * len(IB_PARTICLE_COLUMNS)) for _ in range(5))
    trailing.write_bytes((header + "\n" + body + "\n").encode("utf-8"))
    assert check_completion(trailing, 5).rows == 5


# ---------------------------------------------------------------------------
# run_sweep — output layout, provenance, seam (spec: several)
# ---------------------------------------------------------------------------


def test_run_sweep_output_layout_matches_driver_contract(tmp_path):
    """Spec: Runner output is the path the extractor reads (<root>/<name>/IB_Particle_1.csv)."""
    manifest = _make_manifest(tmp_path, [_cfg("a"), _cfg("b")])
    out = tmp_path / "runs"
    fake = FakeExecutor(rows=5)
    outcomes = run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    assert [o.name for o in outcomes] == ["a", "b"]
    assert all(o.status == "completed" for o in outcomes)
    for name in ("a", "b"):
        # PR4's scripts/extract_forces.py resolves <input-dir>/<name>/IB_Particle_1.csv.
        pr4_path = out / name / "IB_Particle_1.csv"
        assert pr4_path.exists()
        assert (out / name / IB_PARTICLE_CSV) == pr4_path


def test_run_sweep_writes_portable_provenance(tmp_path):
    """Spec: Per-run provenance records digest + caller timestamp; portable, no inputs.file."""
    manifest = _make_manifest(tmp_path, [_cfg("a")])
    out = tmp_path / "runs"
    run_sweep(
        manifest,
        out,
        docker_digest=DIGEST,
        timestamp=TS,
        executor=FakeExecutor(rows=5),
        workspace="ws",
    )
    meta = json.loads((out / "a" / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["docker_image"] == DIGEST
    assert meta["timestamp"] == TS
    assert meta["config"] == "a"
    assert meta["status"] == "completed"
    assert meta["deck_sha256"] is not None  # the deck file exists, so it was hashed
    assert meta["deck"] == "inputs/inputs.3d.a"  # manifest-relative, not absolute
    assert (
        "inputs" not in meta
    )  # deck via extra=, never inputs_file= (no absolute inputs.file)
    _assert_portable(meta)


def test_run_sweep_seam_cwd_is_host_per_config_dir(tmp_path):
    """Spec/Seam: executor cwd == output_root/<name> (where the fake writes & check reads)."""
    manifest = _make_manifest(tmp_path, [_cfg("a"), _cfg("b")])
    out = tmp_path / "runs"
    fake = FakeExecutor(rows=5)
    run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    assert fake.cwds == [out / "a", out / "b"]
    # Recorded commands equal build_run_command per config (the science is asserted).
    for (cmd, _), name in zip(fake.calls, ("a", "b")):
        assert cmd == build_run_command(_cfg(name), workspace="ws")


def test_run_sweep_one_outcome_per_config(tmp_path):
    """Spec: One outcome per configuration."""
    configs = [_cfg(n) for n in ("a", "b", "c")]
    manifest = _make_manifest(tmp_path, configs)
    outcomes = run_sweep(
        manifest,
        tmp_path / "runs",
        docker_digest=DIGEST,
        timestamp=TS,
        executor=FakeExecutor(rows=5),
        workspace="ws",
    )
    assert [o.name for o in outcomes] == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# run_sweep — fail-fast validation (spec: Sweep input validation is fail-fast)
# ---------------------------------------------------------------------------


def test_run_sweep_rejects_mutable_tag_before_any_run(tmp_path):
    """Spec: Mutable tag rejected up front (zero commands issued)."""
    manifest = _make_manifest(tmp_path, [_cfg("a")])
    fake = FakeExecutor()
    with pytest.raises(ValueError):
        run_sweep(
            manifest,
            tmp_path / "runs",
            docker_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TS,
            executor=fake,
            workspace="ws",
        )
    assert fake.calls == []


@pytest.mark.parametrize("missing", ["input_file", "max_step"])
def test_run_sweep_missing_required_key_rejected_before_run(tmp_path, missing):
    """Spec: Configuration missing a consumed key is rejected before any run."""
    config = _cfg("a")
    del config[missing]
    manifest = _make_manifest(tmp_path, [config], make_decks=False)
    fake = FakeExecutor()
    with pytest.raises(ValueError, match=missing):
        run_sweep(
            manifest,
            tmp_path / "runs",
            docker_digest=DIGEST,
            timestamp=TS,
            executor=fake,
            workspace="ws",
        )
    assert fake.calls == []


def test_run_sweep_duplicate_names_rejected_before_run(tmp_path):
    """Spec: Duplicate configuration names are rejected before any run."""
    manifest = _make_manifest(tmp_path, [_cfg("a"), _cfg("a")])
    fake = FakeExecutor()
    with pytest.raises(ValueError):
        run_sweep(
            manifest,
            tmp_path / "runs",
            docker_digest=DIGEST,
            timestamp=TS,
            executor=fake,
            workspace="ws",
        )
    assert fake.calls == []


def test_run_sweep_empty_manifest_returns_empty(tmp_path):
    """Spec: Empty manifest yields no outcomes."""
    manifest = _make_manifest(tmp_path, [])
    fake = FakeExecutor()
    assert (
        run_sweep(
            manifest,
            tmp_path / "runs",
            docker_digest=DIGEST,
            timestamp=TS,
            executor=fake,
            workspace="ws",
        )
        == []
    )
    assert fake.calls == []


# ---------------------------------------------------------------------------
# run_sweep — idempotent resume (spec: Idempotent resume of a partial corpus)
# ---------------------------------------------------------------------------


def test_run_sweep_resume_skips_complete_and_keeps_metadata(tmp_path):
    """Spec: Already-complete config is skipped, the rest run; skipped metadata untouched."""
    manifest = _make_manifest(tmp_path, [_cfg("a"), _cfg("b")])
    out = tmp_path / "runs"
    _write_csv(out / "a" / IB_PARTICLE_CSV, 5)  # a is already complete
    sentinel = out / "a" / "run_metadata.json"
    sentinel.write_text('{"sentinel": true}', encoding="utf-8")

    fake = FakeExecutor(rows=5)
    outcomes = run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    by = {o.name: o for o in outcomes}
    assert by["a"].status == "skipped"
    assert by["b"].status == "completed"
    assert fake.names == ["b"]  # no command issued for the skipped config
    assert (
        sentinel.read_text(encoding="utf-8") == '{"sentinel": true}'
    )  # never re-stamped


def test_run_sweep_no_resume_reruns_complete(tmp_path):
    """Spec: Resume can be disabled."""
    manifest = _make_manifest(tmp_path, [_cfg("a")])
    out = tmp_path / "runs"
    _write_csv(out / "a" / IB_PARTICLE_CSV, 5)
    fake = FakeExecutor(rows=5)
    run_sweep(
        manifest,
        out,
        docker_digest=DIGEST,
        timestamp=TS,
        executor=fake,
        workspace="ws",
        resume=False,
    )
    assert fake.names == ["a"]  # re-run, not skipped


def test_run_sweep_resume_reruns_short_csv(tmp_path):
    """Spec: A partial (short) CSV is re-run, not skipped."""
    manifest = _make_manifest(tmp_path, [_cfg("a", max_step=5)])
    out = tmp_path / "runs"
    _write_csv(out / "a" / IB_PARTICLE_CSV, 1)  # present but short (1 < ceil(5*0.99)=5)
    fake = FakeExecutor(rows=5)
    outcomes = run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    assert fake.names == ["a"]  # re-run
    assert outcomes[0].status == "completed"


# ---------------------------------------------------------------------------
# run_sweep — failed runs (spec: Failed runs are isolated and surfaced)
# ---------------------------------------------------------------------------


def test_run_sweep_nonzero_return_is_failed_and_continues(tmp_path):
    """Spec: Nonzero executor return is recorded as failed and the sweep continues."""
    manifest = _make_manifest(tmp_path, [_cfg("a"), _cfg("b")])
    out = tmp_path / "runs"
    fake = FakeExecutor(rows=5, returncode_by_name={"a": 1})
    outcomes = run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    by = {o.name: o for o in outcomes}
    assert by["a"].status == "failed"
    assert by["b"].status == "completed"
    assert by["a"].metadata_path is not None  # metadata written for a failed run too
    assert fake.names == ["a", "b"]  # b still ran


def test_run_sweep_zero_return_short_csv_is_failed(tmp_path):
    """Spec: A run that completes but leaves a short CSV is failed (post-run re-check wins)."""
    manifest = _make_manifest(tmp_path, [_cfg("a", max_step=5)])
    out = tmp_path / "runs"
    fake = FakeExecutor(rows_by_name={"a": 1})  # returncode 0 but only 1 row
    outcomes = run_sweep(
        manifest, out, docker_digest=DIGEST, timestamp=TS, executor=fake, workspace="ws"
    )
    assert outcomes[0].status == "failed"  # NOT completed


# ---------------------------------------------------------------------------
# run_sweep — seam / force-only guard (spec: Cluster-free injected executor seam)
# ---------------------------------------------------------------------------


def test_runner_library_is_subprocess_free():
    """Spec: the tested library never imports subprocess (asserted on the module, not the driver)."""
    # AST of actual imports — robust to the docstring legitimately *mentioning* subprocess.
    tree = ast.parse(inspect.getsource(runner_mod))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert "subprocess" not in imported
    assert not hasattr(runner_mod, "subprocess")


def test_run_sweep_is_force_only(tmp_path):
    """Spec: No plotfile or field path is consumed or produced."""
    manifest = _make_manifest(tmp_path, [_cfg("a")])
    fake = FakeExecutor(rows=5)
    run_sweep(
        manifest,
        tmp_path / "runs",
        docker_digest=DIGEST,
        timestamp=TS,
        executor=fake,
        workspace="ws",
    )
    for inner in (cmd[7] for cmd in fake.commands):
        assert "plot" not in inner.lower()  # no plotfile output in the command
    params = inspect.signature(run_sweep).parameters
    assert not any("plot" in name for name in params)  # no plotfile argument


# ---------------------------------------------------------------------------
# build_wsl_command (spec: Cluster-free injected executor seam — WSL wrapping)
# ---------------------------------------------------------------------------


def test_build_wsl_command_preserves_inner_grouping():
    """Adversarial quoting: a naive ' '.join that drops the sh -c grouping must fail."""
    command = [
        "runai",
        "workspace",
        "exec",
        "ws",
        "--",
        "sh",
        "-c",
        "echo hi && cd /workspace/runs/s35_f085_p30",
    ]
    result = build_wsl_command(
        command, kubeconfig="~/.kube/cfg", runai_binary="/home/u/.runai/bin/runai"
    )
    assert result[:4] == ["wsl", "-e", "bash", "-c"]
    payload = result[4]
    prefix, joined = payload.split("; ", 1)
    # KUBECONFIG is exported (shlex.quote may quote the ~), round-tripping to the raw path.
    assert shlex.split(prefix) == ["export", "KUBECONFIG=~/.kube/cfg"]
    # The inner sh -c "<script>" grouping survives shlex round-trip; the runai token is absolute.
    assert shlex.split(joined) == [
        "/home/u/.runai/bin/runai",
        "workspace",
        "exec",
        "ws",
        "--",
        "sh",
        "-c",
        "echo hi && cd /workspace/runs/s35_f085_p30",
    ]


# ---------------------------------------------------------------------------
# Public API re-export
# ---------------------------------------------------------------------------


def test_public_api_reexported():
    """The runner public API is importable from the package top-level."""
    import mosquito_cfd.force_surrogate as fs

    for symbol in (
        "build_run_command",
        "check_completion",
        "run_sweep",
        "build_wsl_command",
        "ExecResult",
        "RunOutcome",
        "Completion",
    ):
        assert hasattr(fs, symbol), symbol
