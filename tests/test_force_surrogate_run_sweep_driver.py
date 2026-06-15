"""Smoke tests for the scripts/run_sweep.py driver (cluster-free, PR3).

Mirrors PR4's ``test_force_surrogate_driver.py``: loads the driver via
``importlib.util.spec_from_file_location`` and runs ``main()`` end-to-end with an **injected
fake executor**, so the real WSL/RunAI executor is never built and no cluster/GPU/container is
touched (CI has no ``wsl``).
"""

import importlib.util
import json
from pathlib import Path

from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS
from mosquito_cfd.force_surrogate.runner import IB_PARTICLE_CSV, ExecResult

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "scripts" / "run_sweep.py"

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "0" * 64
TS = "2026-06-30T00:00:00+00:00"
MAX_STEP = 3  # ceil(3 * 0.99) == 3, so 3 synthetic rows pass the completion check


def _load_driver():
    spec = importlib.util.spec_from_file_location("run_sweep_driver", DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def _write_csv(path: Path, n_rows: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [",".join(IB_PARTICLE_COLUMNS)]
    lines += [",".join(["0"] * len(IB_PARTICLE_COLUMNS)) for _ in range(n_rows)]
    path.write_bytes(("\n".join(lines) + "\n").encode("utf-8"))


class FakeExecutor:
    """Records each cwd and writes a synthetic CSV; ``fail_names`` write 0 rows (-> failed)."""

    def __init__(self, *, rows=MAX_STEP, fail_names=()):
        self.calls: list[Path] = []
        self.rows = rows
        self.fail_names = set(fail_names)

    def __call__(self, command, *, cwd) -> ExecResult:
        # Answer the in-container GPU probe with a canned A40 CSV; don't count it as a run.
        if "nvidia-smi" in list(command):
            return ExecResult(0, "NVIDIA A40, 49140, 550.54.14")
        cwd = Path(cwd)
        self.calls.append(cwd)
        _write_csv(
            cwd / IB_PARTICLE_CSV, 0 if cwd.name in self.fail_names else self.rows
        )
        return ExecResult(0)

    @property
    def names(self):
        return [c.name for c in self.calls]


def _make_tree(tmp_path: Path, names: list[str]) -> Path:
    configs = [
        {
            "index": i,
            "name": name,
            "stroke_amp_deg": 45.0,
            "frequency_fstar": 1.0,
            "pitch_amp_deg": 45.0,
            "reynolds": 60.0,
            "split": "train",
            "input_file": f"inputs/inputs.3d.{name}",
            "max_step": MAX_STEP,
        }
        for i, name in enumerate(names)
    ]
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(json.dumps({"configs": configs}), encoding="utf-8")
    for name in names:
        deck = tmp_path / "inputs" / f"inputs.3d.{name}"
        deck.parent.mkdir(parents=True, exist_ok=True)
        deck.write_text(f"# deck {name}\n", encoding="utf-8")
    return manifest


def _argv(manifest: Path, out: Path) -> list[str]:
    return [
        "--manifest", str(manifest),
        "--output-root", str(out),
        "--workspace", "ws",
        "--docker-digest", DIGEST,
        "--timestamp", TS,
    ]  # fmt: skip


def test_driver_smoke_writes_outputs(tmp_path):
    """main() exits 0 and writes per-config CSV + run_metadata for each config."""
    manifest = _make_tree(tmp_path, ["a", "b"])
    out = tmp_path / "runs"
    fake = FakeExecutor()
    rc = _load_driver().main(_argv(manifest, out), executor=fake)
    assert rc == 0
    for name in ("a", "b"):
        assert (out / name / "IB_Particle_1.csv").exists()
        assert (out / name / "run_metadata.json").exists()
    assert fake.names == ["a", "b"]


def test_driver_resume_issues_no_new_commands(tmp_path):
    """A second invocation resumes: every already-complete config is skipped (zero commands)."""
    manifest = _make_tree(tmp_path, ["a", "b"])
    out = tmp_path / "runs"
    driver = _load_driver()
    assert driver.main(_argv(manifest, out), executor=FakeExecutor()) == 0

    second = FakeExecutor()
    assert driver.main(_argv(manifest, out), executor=second) == 0
    assert second.names == []  # all skipped on resume


def test_driver_exits_nonzero_on_failure(tmp_path):
    """main() returns 1 when any config fails (here 'b' writes a short CSV)."""
    manifest = _make_tree(tmp_path, ["a", "b"])
    out = tmp_path / "runs"
    fake = FakeExecutor(fail_names=["b"])
    rc = _load_driver().main(_argv(manifest, out), executor=fake)
    assert rc == 1
