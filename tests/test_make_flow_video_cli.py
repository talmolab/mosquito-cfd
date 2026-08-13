"""CLI smoke tests for scripts/make_flow_video.py (OpenSpec change add-visualization-tooling)."""

from __future__ import annotations

import importlib.util
import json
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


def test_cli_explicit_hinge_override_wins_over_config_deck(tmp_path, monkeypatch):
    """design.md D3's central scenario, exercised through argparse (not just the underlying
    resolve_kinematics_kwargs unit tests): --config/--corpus-dir resolves center/kinematics from
    the deck, but an explicit --hinge on the command line still takes precedence over the deck's
    own (as-run, possibly buggy) hinge.
    """
    plotfile_dir = tmp_path / "plotfiles"
    (plotfile_dir / "plt00000").mkdir(parents=True)
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

    corpus_dir = tmp_path / "corpus"
    (corpus_dir / "inputs").mkdir(parents=True)
    (corpus_dir / "inputs" / "inputs.3d.s45_f115_p60").write_text(
        "particle_inputs.x = 4.0\n"
        "particle_inputs.y = 2.0\n"
        "particle_inputs.z = 4.0\n"
        "particle_inputs.hinge_x = 4.0\n"
        "particle_inputs.hinge_y = 2.0\n"
        "particle_inputs.hinge_z = 2.5\n",  # the deck's own as-run, buggy hinge
        encoding="utf-8",
    )

    cli = _load_cli()
    rc = cli.main(
        [
            "--plotfile-dir",
            str(plotfile_dir),
            "--field-mode",
            "wake-slice",
            "--vertex-path",
            str(_VERTEX_PATH),
            "--label",
            "s45_f115_p60",
            "--out-dir",
            str(tmp_path / "out"),
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
            "--config",
            "s45_f115_p60",
            "--corpus-dir",
            str(corpus_dir),
            "--hinge",
            "4.0",
            "0.5",
            "4.0",  # corrected hinge override
        ]
    )

    assert rc == 0
    metadata = json.loads(
        (
            tmp_path / "out" / "s45_f115_p60_flow_wake-slice_run_metadata.json"
        ).read_text()
    )
    assert metadata["hinge"] == [
        4.0,
        0.5,
        4.0,
    ]  # the override, not the deck's [4.0, 2.0, 2.5]
    assert metadata["center"] == [
        4.0,
        2.0,
        4.0,
    ]  # unaffected -- still read from the deck
