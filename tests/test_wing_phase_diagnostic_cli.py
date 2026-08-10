"""CLI driver for the wing-phase diagnostic (``scripts/make_wing_phase_diagnostic.py``).

OpenSpec change ``fix-force-surrogate-sweep-hinge``.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"


def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "make_wing_phase_diagnostic", Path("scripts/make_wing_phase_diagnostic.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_smoke_runs_default_sample(tmp_path):
    """main() with no --config runs the default named sample and writes its artifacts."""
    cli = _load_cli()
    rc = cli.main(
        [
            "--out-dir",
            str(tmp_path),
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
        ]
    )
    assert rc == 0
    for name in ("validated", "s35_f085_p30", "s55_f115_p60"):
        assert (tmp_path / f"{name}_wing_phases.png").exists()


def test_cli_smoke_runs_single_named_config(tmp_path):
    cli = _load_cli()
    rc = cli.main(
        [
            "--out-dir",
            str(tmp_path),
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
            "--config",
            "validated",
        ]
    )
    assert rc == 0
    assert (tmp_path / "validated_wing_phases.png").exists()
    assert not (tmp_path / "s35_f085_p30_wing_phases.png").exists()


def test_wing_phase_diagnostic_default_sample_is_documented(tmp_path, capsys):
    """--help names the default sample configs and states why they were chosen."""
    cli = _load_cli()
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    help_text = capsys.readouterr().out
    for name in ("validated", "s35_f085_p30", "s55_f115_p60"):
        assert name in help_text
