"""CLI smoke tests for scripts/make_kinematics_video.py (OpenSpec change add-visualization-tooling)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"

_REPO_ROOT = Path(__file__).resolve().parents[1]
_VERTEX_PATH = _REPO_ROOT / "examples" / "flapping_wing" / "wing.vertex"


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "make_kinematics_video", Path("scripts/make_kinematics_video.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_args(tmp_path: Path) -> list[str]:
    return [
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
        "4.0",
        "2.0",
        "4.0",
        "--hinge",
        "4.0",
        "0.5",
        "4.0",
        "--stroke-amp-deg",
        "70.0",
        "--pitch-amp-deg",
        "45.0",
        "--frequency-fstar",
        "1.0",
        "--n-frames",
        "5",
    ]


def test_cli_rejects_missing_required_flags():
    cli = _load_cli()
    with pytest.raises(SystemExit):
        cli.main([])


def test_cli_rejects_malformed_hinge_wrong_arity(tmp_path):
    cli = _load_cli()
    args = _base_args(tmp_path)
    idx = args.index("--hinge")
    args[idx : idx + 4] = ["--hinge", "4.0", "0.5"]  # only 2 of the required 3 values
    with pytest.raises(SystemExit):
        cli.main(args)


def test_cli_rejects_malformed_center_wrong_arity(tmp_path):
    cli = _load_cli()
    args = _base_args(tmp_path)
    idx = args.index("--center")
    args[idx : idx + 4] = ["--center", "4.0", "2.0"]
    with pytest.raises(SystemExit):
        cli.main(args)


def test_cli_smoke_renders_kinematics_preview(tmp_path):
    cli = _load_cli()
    rc = cli.main(_base_args(tmp_path))

    assert rc == 0
    assert (tmp_path / "out" / "test_kinematics_preview.mp4").exists()
