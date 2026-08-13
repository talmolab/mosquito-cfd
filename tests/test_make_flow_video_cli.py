"""CLI smoke tests for scripts/make_flow_video.py (OpenSpec change add-visualization-tooling)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERTEX_PATH = _REPO_ROOT / "examples" / "flapping_wing" / "wing.vertex"


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "make_flow_video", Path("scripts/make_flow_video.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_args(tmp_path: Path, plotfile_dir: Path) -> list[str]:
    return [
        "--plotfile-dir",
        str(plotfile_dir),
        "--field-mode",
        "wake-slice",
        "--vertex-path",
        str(_VERTEX_PATH),
        "--label",
        "test",
        "--out-dir",
        str(tmp_path / "out"),
        "--docker-digest",
        DIGEST,
        "--timestamp",
        TS,
        "--center",
        "0.3",
        "0.3",
        "0.3",
        "--hinge",
        "0.3",
        "0.1",
        "0.3",
        "--stroke-amp-deg",
        "70.0",
        "--pitch-amp-deg",
        "45.0",
        "--frequency-fstar",
        "1.0",
    ]


def test_cli_rejects_missing_required_flags():
    cli = _load_cli()
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_rejects_invalid_field_mode(tmp_path):
    cli = _load_cli()
    args = _base_args(tmp_path, tmp_path / "plotfiles")
    idx = args.index("--field-mode")
    args[idx + 1] = "isosurface"
    with pytest.raises(SystemExit):
        cli.main(args)
    assert not (tmp_path / "out").exists()


def test_cli_rejects_malformed_hinge_wrong_arity(tmp_path):
    cli = _load_cli()
    args = _base_args(tmp_path, tmp_path / "plotfiles")
    idx = args.index("--hinge")
    args[idx : idx + 4] = ["--hinge", "0.3", "0.1"]  # only 2 of the required 3 values
    with pytest.raises(SystemExit):
        cli.main(args)


def test_cli_rejects_malformed_center_wrong_arity(tmp_path):
    cli = _load_cli()
    args = _base_args(tmp_path, tmp_path / "plotfiles")
    idx = args.index("--center")
    args[idx : idx + 4] = ["--center", "0.3", "0.3"]
    with pytest.raises(SystemExit):
        cli.main(args)


def test_cli_smoke_renders_wake_slice_video(tmp_path, monkeypatch):
    plotfile_dir = tmp_path / "plotfiles"
    for name in ("plt00000", "plt00100"):
        (plotfile_dir / name).mkdir(parents=True)

    n = 6
    dx = np.array([0.1, 0.1, 0.1])
    box = {
        "u": np.zeros((n, n, n)),
        "v": np.zeros((n, n, n)),
        "w": np.zeros((n, n, n)),
        "x": (np.arange(n) + 0.5) * dx[0],
        "y": (np.arange(n) + 0.5) * dx[1],
        "z": (np.arange(n) + 0.5) * dx[2],
        "dx": dx,
        "current_time": 0.0,
    }
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi, halo=0: dict(box),
    )

    cli = _load_cli()
    rc = cli.main(_base_args(tmp_path, plotfile_dir))

    assert rc == 0
    assert (tmp_path / "out" / "test_flow_wake-slice.mp4").exists()
