"""Settling run records, field change and report (add-settled-beat-corpus task 5.3).

Everything runs on a synthetic repository-shaped tree, so CI needs no CFD output or plotfiles.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS
from mosquito_cfd.force_surrogate.settling import (
    GATED_FILES,
    TARGETS,
    build_run_record,
    build_settling_report,
    field_change_for_run,
    frame_index,
    git_provenance,
    validate_run_record,
)

DT = 5e-4
IMAGE = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
COMMIT = "b" * 40
SETTLING_PY = "src/mosquito_cfd/force_surrogate/settling.py"
FORCES = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")


# --------------------------------------------------------------------------- tree helpers


def _forces(steps: np.ndarray) -> dict[str, np.ndarray]:
    t = steps * DT
    return {
        "Fx": -700.0 * np.sin(2 * np.pi * t) - 3.0,
        "Fy": 312.0 * np.cos(2 * np.pi * t),
        "Fz": 1234.5 * np.cos(2 * np.pi * t) + 0.25,
        "Mx": 88.0 * np.sin(4 * np.pi * t),
        "My": -50.0 * np.cos(2 * np.pi * t),
        "Mz": 3.0e4 * np.sin(2 * np.pi * t + 0.3),
    }


def _write_csv(path: Path, n_steps: int) -> None:
    steps = np.arange(n_steps)
    values = _forces(steps)
    lines = [",".join(IB_PARTICLE_COLUMNS)]
    for i, step in enumerate(steps):
        cells = []
        for column in IB_PARTICLE_COLUMNS:
            if column == "iStep":
                cells.append(str(int(step)))
            elif column == "time":
                cells.append(f"{step * DT:g}")
            elif column in values:
                cells.append(f"{values[column][i]:g}")
            else:
                cells.append("0")
        lines.append(",".join(cells))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_log(path: Path, n_steps: int, *, slow_step: int | None = None) -> None:
    lines = []
    for step in range(1, n_steps + 1):
        dt = 2.5e-4 if step == slow_step else DT
        lines.append(f"STEP = {step} TIME = {step * DT:g} DT = {dt:g}")
    lines.append("Run time = 1234.5")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cf_frame(config: str, n_beats: int, ratio: float) -> pd.DataFrame:
    max_step = round(n_beats / DT)
    time = np.arange(max_step) * DT
    phase = np.mod(time, 1.0)
    wingbeat = np.floor(time).astype(np.int64)
    data = {
        "config_name": config,
        "time": time,
        "phase": phase,
        "wingbeat": wingbeat,
        "frequency_fstar": 1.0,
    }
    base = np.sin(2 * np.pi * phase) + 0.3 * np.cos(4 * np.pi * phase)
    for target in TARGETS:
        data[target] = base + 0.05 * ratio ** (wingbeat + 1) * (
            np.cos(2 * np.pi * phase) + 0.5
        )
    return pd.DataFrame(data)


def _tree(tmp_path: Path, *, ratio: float = 0.2) -> dict:
    """A repo with one fine long run, one C1 control, a reference corpus and gated files."""
    repo = tmp_path / "repo"
    settling_dir = repo / "examples" / "settling_check"
    corpus = repo / "examples" / "corpus"
    for rel in (*GATED_FILES, SETTLING_PY):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        # Exact LF bytes: the real gated files are LF-pinned by .gitattributes, and git show
        # must hash the same bytes as the working tree on every platform.
        (repo / rel).write_bytes(f"# {rel}\n".encode())
    corpus.mkdir(parents=True)
    ref_steps = 4000
    steps = np.arange(ref_steps)
    reference = pd.DataFrame(
        {
            "config_name": "cfg",
            "time": [float(f"{s * DT:g}") for s in steps],
            **{
                k: [float(f"{v:g}") for v in vals] for k, vals in _forces(steps).items()
            },
        }
    )
    reference.to_parquet(corpus / "dataset.parquet", index=False)
    (corpus / "sweep_manifest.json").write_text(
        json.dumps(
            {"configs": [{"name": "cfg", "stop_time": 2.0, "frequency_fstar": 1.0}]}
        ),
        encoding="utf-8",
    )
    manifest = {
        "n_wingbeats": 8,
        "frames_per_beat": 20,
        "images": {"fine": IMAGE},
        "runs": [
            {
                "name": "fine_cfg",
                "grid": "fine",
                "config": "cfg",
                "kind": "long",
                "image": IMAGE,
                "max_step": 16000,
                "stop_time": 8.0,
                "n_wingbeats": 8,
                "source_deck": "examples/corpus/inputs/inputs.3d.cfg",
                "controls": ["C3", "C4"],
            }
        ],
        "controls": [
            {
                "name": "fine_c1_cfg",
                "grid": "fine",
                "config": "cfg",
                "kind": "C1",
                "image": IMAGE,
                "max_step": 400,
                "stop_time": 2.0,
                "source_deck": "examples/corpus/inputs/inputs.3d.cfg",
            }
        ],
    }
    deck_bytes = b"# settling deck\n"
    for entry in [*manifest["runs"], *manifest["controls"]]:
        entry["deck"] = f"fine/inputs/inputs.3d.{entry['name']}"
        entry["deck_sha256"] = hashlib.sha256(deck_bytes).hexdigest()
    settling_dir.mkdir(parents=True, exist_ok=True)
    (settling_dir / "settling_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (settling_dir / "fine").mkdir()
    _cf_frame("cfg", 8, ratio).to_parquet(
        settling_dir / "fine" / "dataset.parquet", index=False
    )
    long_dir = tmp_path / "runs" / "fine_cfg"
    _write_csv(long_dir / "IB_Particle_1.csv", 16000)
    _write_log(long_dir / "run.log", 16000)
    c1_dir = tmp_path / "runs" / "fine_c1_cfg"
    _write_csv(c1_dir / "IB_Particle_1.csv", 400)
    _write_log(c1_dir / "run.log", 400)
    for entry, run_dir in (
        (manifest["runs"][0], long_dir),
        (manifest["controls"][0], c1_dir),
    ):
        (run_dir / Path(entry["deck"]).name).write_bytes(deck_bytes)
        (run_dir / "command.txt").write_text(
            f"docker run --gpus all {IMAGE} mpirun ...\n", encoding="utf-8"
        )
    # The grid's extraction metadata, as scripts/extract_forces.py writes it.
    csv_sha = hashlib.sha256((long_dir / "IB_Particle_1.csv").read_bytes()).hexdigest()
    (settling_dir / "fine" / "run_metadata.json").write_text(
        json.dumps({"extraction_inputs": {"csv_sha256": {"cfg": csv_sha}}}),
        encoding="utf-8",
    )
    commit = _init_git(repo)
    return {
        "repo": repo,
        "settling_dir": settling_dir,
        "long": long_dir,
        "c1": c1_dir,
        "manifest": manifest,
        "commit": commit,
    }


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _init_git(repo: Path) -> str:
    """Make the tree a git repo whose HEAD is also the 'upstream' branch; return HEAD."""
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "add", "-A")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "init")
    _git(repo, "branch", "upstream")
    return _git(repo, "rev-parse", "HEAD")


def _provenance(
    t: dict, *, start_commit: str | None = None, launch_status: str = ""
) -> dict:
    launch = {
        "start_commit": start_commit or t["commit"],
        "git_status_porcelain": launch_status,
    }
    return git_provenance(t["repo"], launch=launch, upstream_ref="upstream")


def _record(t: dict, name: str, run_dir: Path, **overrides) -> dict:
    kwargs = dict(
        settling_dir=t["settling_dir"],
        repo_root=t["repo"],
        provenance=_provenance(t),
        iamrex_commit="f93dc794",
        hardware={"gpu_model": "NVIDIA RTX A5000"},
    )
    kwargs.update(overrides)
    return build_run_record(run_dir, name=name, **kwargs)


def _write_record(t: dict, record: dict) -> None:
    records = t["settling_dir"] / "records"
    records.mkdir(exist_ok=True)
    (records / f"{record['run']}.json").write_text(json.dumps(record), encoding="utf-8")


# --------------------------------------------------------------------------- records


def test_long_run_record_carries_c3_c4_and_provenance(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    assert record["controls"]["C3"]["passed"], record["controls"]["C3"]
    assert record["controls"]["C3"]["n_compared"] == 4000
    assert record["controls"]["C4"]["passed"]
    assert record["wall_time_s"] == 1234.5
    assert record["steps"] == 16000
    assert record["seconds_per_step"] == pytest.approx(1234.5 / 16000)
    prov = record["provenance"]
    assert prov["start_commit"] == t["commit"] == prov["head_commit"]
    assert prov["dirty_at_launch"] is False and prov["dirty_at_record"] is False
    assert record["image"] == IMAGE and IMAGE in record["command"]
    for rel in (*GATED_FILES, SETTLING_PY):
        sha = hashlib.sha256((t["repo"] / rel).read_bytes()).hexdigest()
        assert record["file_sha256"][rel] == sha
    csv_sha = hashlib.sha256((t["long"] / "IB_Particle_1.csv").read_bytes()).hexdigest()
    assert record["force_csv_sha256"] == csv_sha
    assert validate_run_record(record, t["manifest"]["runs"][0]) == []


def test_c1_record_compares_the_first_400_steps(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_c1_cfg", t["c1"])
    assert set(record["controls"]) == {"C1"}
    assert (
        record["controls"]["C1"]["passed"]
        and record["controls"]["C1"]["n_compared"] == 400
    )
    assert validate_run_record(record, t["manifest"]["controls"][0]) == []


def test_cfl_reduced_interior_step_fails_c4(tmp_path):
    t = _tree(tmp_path)
    _write_log(t["long"] / "run.log", 16000, slow_step=5000)
    record = _record(t, "fine_cfg", t["long"])
    assert record["controls"]["C4"]["passed"] is False


def test_unknown_run_name_raises(tmp_path):
    t = _tree(tmp_path)
    with pytest.raises(ValueError, match="nope"):
        _record(t, "nope", t["long"])


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("image", "ghcr.io/talmolab/mosquito-cfd:fp64", "image"),
        ("command", "", "command"),
        ("hardware", {}, "hardware"),
        ("steps", 15999, "steps"),
        ("wall_time_s", 0, "wall_time_s"),
        ("run", "other", "run"),
        ("iamrex_commit", "", "iamrex_commit"),
        ("seconds_per_step", None, "seconds_per_step"),
    ],
)
def test_incomplete_record_is_named(tmp_path, field, value, message):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    record[field] = value
    problems = validate_run_record(record, t["manifest"]["runs"][0])
    assert problems and any(message in p for p in problems)


def test_record_with_another_pinned_image_is_named(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    record["image"] = (
        "ghcr.io/talmolab/mosquito-cfd@sha256:" + "c" * 64
    )  # pinned, but not ours
    assert any(
        "image" in p for p in validate_run_record(record, t["manifest"]["runs"][0])
    )


def test_record_missing_a_declared_control_is_named(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    del record["controls"]["C4"]
    assert any("C4" in p for p in validate_run_record(record, t["manifest"]["runs"][0]))


# --------------------------------------------------------------------------- field change


@pytest.mark.parametrize("f_star", [0.85, 1.0, 1.15])
def test_frame_index_maps_time_triggered_plotfiles_to_beat_and_phase(f_star):
    plot_per = 1 / (20 * f_star)
    seen = []
    for m in range(1, 8 * 20):
        step = int(
            np.ceil(m * plot_per / DT - 1e-9)
        )  # first step whose end reaches m * per
        seen.append(
            frame_index(step, dt=DT, frequency_fstar=f_star, frames_per_beat=20)
        )
    assert seen == [(m // 20 + 1, m % 20) for m in range(1, 8 * 20)]


def test_frame_index_tolerates_a_plotfile_just_before_its_frame_time():
    # AMReX writes when the step end is within machine epsilon of the frame time, so a plotfile
    # can sit a hair before it; it is still that frame, not the previous one.
    assert frame_index(999, dt=0.001, frequency_fstar=1.0, frames_per_beat=1) == (2, 0)
    assert frame_index(
        3999, dt=DT, frequency_fstar=1.0, frames_per_beat=4
    ) == frame_index(4000, dt=DT, frequency_fstar=1.0, frames_per_beat=4)


def test_field_change_compares_matched_frames_with_the_last_beat(tmp_path):
    run = tmp_path / "run"
    fields = {}
    for m in range(0, 3 * 4 + 1):  # 3 beats, 4 frames per beat, plus the final plotfile
        step = m * 500
        plt = run / f"plt{step:05d}"
        plt.mkdir(parents=True)
        (plt / "Header").write_text(f"header {step}\n", encoding="utf-8")
        beat = m // 4 + 1
        velocity = np.zeros((2, 2, 2, 3))
        velocity[..., 0] = 0.2 * (
            3 - beat
        )  # beat 1 differs by 0.4, beat 2 by 0.2, beat 3 by 0
        fields[step] = velocity

    def reader(path, *, lo, hi):
        step = int(Path(path).name[3:])
        v = fields[step]
        return {"u": v[..., 0], "v": v[..., 1], "w": v[..., 2]}

    out = field_change_for_run(
        run,
        b_last=3,
        frequency_fstar=1.0,
        dt=DT,
        u_ref=1.0,
        frames_per_beat=4,
        box=((0, 0, 0), (1, 1, 1)),
        reader=reader,
    )
    assert out["beats"]["1"]["median"] == pytest.approx([0.4] * 4)
    assert out["beats"]["2"]["fraction_above"] == pytest.approx([1.0] * 4)
    assert "3" not in out["beats"]
    header = run / "plt00500" / "Header"
    assert (
        out["plotfile_header_sha256"]["500"]
        == hashlib.sha256(header.read_bytes()).hexdigest()
    )


def test_field_change_missing_matched_frame_raises(tmp_path):
    run = tmp_path / "run"
    for step in (
        0,
        2000,
        3000,
        4000,
    ):  # 2 frames per beat; beat 1 frame 1 (step 1000) missing
        (run / f"plt{step:05d}").mkdir(parents=True)
        (run / f"plt{step:05d}" / "Header").write_text("h\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frame"):
        field_change_for_run(
            run,
            b_last=2,
            frequency_fstar=1.0,
            dt=DT,
            u_ref=1.0,
            frames_per_beat=2,
            box=((0, 0, 0), (1, 1, 1)),
            reader=lambda *a, **k: None,
        )


# --------------------------------------------------------------------------- report


def test_complete_report_carries_constants_hash_metrics_and_decision(tmp_path):
    t = _tree(tmp_path)
    _write_record(t, _record(t, "fine_cfg", t["long"]))
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "complete"
    assert report["constants"]["SETTLED_TOLERANCE"] == 0.01
    prereg = t["repo"] / GATED_FILES[0]
    assert (
        report["preregistration_sha256"]
        == hashlib.sha256(prereg.read_bytes()).hexdigest()
    )
    assert report["git_commit"] == COMMIT
    run = report["runs"]["fine_cfg"]
    assert run["b_last"] == 8 and run["n_star"] == 5
    assert set(run["targets"]) == set(TARGETS)
    assert sorted(run["mean_cf_z"]) == [str(b) for b in range(1, 9)]
    assert (
        report["decision"]["action"] == "regenerate"
        and report["decision"]["n_star"] == 5
    )
    assert report["controls"]["fine_c1_cfg"]["C1"]["passed"]
    json.dumps(
        report, allow_nan=False
    )  # strictly JSON: infinities are encoded, not NaN/inf


def test_missing_control_marks_the_report_incomplete(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    del record["controls"]["C3"]
    _write_record(t, record)
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "controls_incomplete"
    assert any("C3" in m for m in report["missing"])


def test_missing_record_marks_the_report_incomplete(tmp_path):
    t = _tree(tmp_path)
    _write_record(t, _record(t, "fine_cfg", t["long"]))
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "controls_incomplete"
    assert any("fine_c1_cfg" in m for m in report["missing"])


def test_failed_control_is_reported_as_such(tmp_path):
    t = _tree(tmp_path)
    _write_log(t["long"] / "run.log", 16000, slow_step=7000)
    _write_record(t, _record(t, "fine_cfg", t["long"]))
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "control_failed"


def test_unsettled_run_encodes_an_infinite_tail_as_null(tmp_path):
    t = _tree(tmp_path, ratio=1.05)  # growing: not contracting
    _write_record(t, _record(t, "fine_cfg", t["long"]))
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["decision"]["action"] == "stop"
    assert report["runs"]["fine_cfg"]["targets"]["CF_x"]["tail"] is None
    json.dumps(report, allow_nan=False)


def test_script_writes_the_report_and_exits_non_zero_when_incomplete(tmp_path):
    t = _tree(tmp_path)
    _write_record(t, _record(t, "fine_cfg", t["long"]))
    out = tmp_path / "settling_report.json"
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_settling.py"
    args = [
        sys.executable,
        str(script),
        "--settling-dir",
        str(t["settling_dir"]),
        "--repo-root",
        str(t["repo"]),
        "--git-commit",
        COMMIT,
        "--out",
        str(out),
    ]
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 1, proc.stderr
    assert (
        json.loads(out.read_text(encoding="utf-8"))["status"] == "controls_incomplete"
    )
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    proc = subprocess.run(args, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- record script


def _record_script(t: dict, name: str, run_dir: Path, *extra: str):
    hardware = run_dir / "hardware.json"
    hardware.write_text(json.dumps({"gpu_model": "NVIDIA RTX A5000"}), encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "record_settling_run.py"
    args = [
        sys.executable,
        str(script),
        "record",
        "--name",
        name,
        "--run-dir",
        str(run_dir),
        "--settling-dir",
        str(t["settling_dir"]),
        "--repo-root",
        str(t["repo"]),
        "--upstream-ref",
        "upstream",
        "--iamrex-commit",
        "f93dc794",
        "--hardware-json",
        str(hardware),
        *extra,
    ]
    return subprocess.run(args, capture_output=True, text=True)


def _launch_script(t: dict, run_dir: Path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "record_settling_run.py"
    args = [
        sys.executable,
        str(script),
        "launch",
        "--run-dir",
        str(run_dir),
        "--repo-root",
        str(t["repo"]),
    ]
    return subprocess.run(args, capture_output=True, text=True)


def test_record_script_writes_a_valid_record_once(tmp_path):
    t = _tree(tmp_path)
    assert _launch_script(t, t["c1"]).returncode == 0
    launch = json.loads((t["c1"] / "launch.json").read_text(encoding="utf-8"))
    assert (
        launch["start_commit"] == t["commit"] and launch["git_status_porcelain"] == ""
    )
    proc = _record_script(t, "fine_c1_cfg", t["c1"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
    path = t["settling_dir"] / "records" / "fine_c1_cfg.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    assert validate_run_record(record, t["manifest"]["controls"][0]) == []
    before = path.read_bytes()
    again = _record_script(t, "fine_c1_cfg", t["c1"])
    assert again.returncode != 0 and "exists" in again.stdout + again.stderr
    assert path.read_bytes() == before


def test_record_script_refuses_a_dirty_checkout(tmp_path):
    t = _tree(tmp_path)
    (t["repo"] / GATED_FILES[0]).write_text("edited\n", encoding="utf-8")
    assert _launch_script(t, t["c1"]).returncode == 0
    proc = _record_script(t, "fine_c1_cfg", t["c1"])
    assert proc.returncode != 0 and "dirty" in proc.stdout + proc.stderr
    assert not (t["settling_dir"] / "records" / "fine_c1_cfg.json").exists()


def test_record_script_refuses_a_run_without_launch_json(tmp_path):
    t = _tree(tmp_path)
    proc = _record_script(t, "fine_c1_cfg", t["c1"])
    assert proc.returncode == 1 and "launch.json" in proc.stdout
    assert "record not written" in proc.stdout and "Traceback" not in proc.stderr


def test_second_record_is_not_blocked_by_the_first(tmp_path):
    t = _tree(tmp_path)
    for name, run_dir in (("fine_c1_cfg", t["c1"]), ("fine_cfg", t["long"])):
        assert _launch_script(t, run_dir).returncode == 0
    assert _record_script(t, "fine_c1_cfg", t["c1"]).returncode == 0
    proc = _record_script(t, "fine_cfg", t["long"])
    assert proc.returncode == 0, proc.stdout + proc.stderr
