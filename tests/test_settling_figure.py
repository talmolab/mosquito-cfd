"""Settling figure (add-settled-beat-corpus task 5.4): its sidecar equals the report it plots."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate.settling import TARGETS
from mosquito_cfd.force_surrogate.settling_figure import (
    CONFIG_COLORS,
    figure_metrics,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "make_settling_figure.py"
CONFIGS = ("s35_f085_p30", "s45_f100_p30", "s55_f115_p30")


def _report() -> dict:
    runs = {}
    for g, grid in enumerate(("coarse", "fine")):
        for c, config in enumerate(CONFIGS):
            targets = {}
            for t, target in enumerate(TARGETS):
                steps = {
                    str(b): 0.3 * (0.6 + 0.01 * (c + g + t)) ** (b - 1)
                    for b in range(2, 9)
                }
                targets[target] = {
                    "steps": steps,
                    "noise_floor": 1e-5 * (1 + t),
                    "tail": 0.002,
                }
            runs[f"{grid}_{config}"] = {
                "grid": grid,
                "config": config,
                "b_last": 8,
                "targets": targets,
            }
    return {
        "status": "complete",
        "constants": {"SETTLED_TOLERANCE": 0.01},
        "runs": runs,
        "decision": {"action": "regenerate", "n_star": 6},
    }


def test_metrics_carry_every_plotted_number():
    report = _report()
    metrics = figure_metrics(report)
    assert metrics["tolerance"] == 0.01
    for name, run in report["runs"].items():
        for target in TARGETS:
            assert (
                metrics["series"][name][target]["steps"]
                == run["targets"][target]["steps"]
            )
            assert (
                metrics["series"][name][target]["noise_floor"]
                == run["targets"][target]["noise_floor"]
            )


def test_colours_follow_the_configuration_in_fixed_order():
    assert list(CONFIG_COLORS) == list(CONFIGS)
    assert list(CONFIG_COLORS.values()) == ["#2a78d6", "#eb6834", "#1baf7a"]


def test_unknown_configuration_is_rejected():
    report = _report()
    report["runs"]["fine_other"] = dict(
        report["runs"]["fine_s35_f085_p30"], config="other"
    )
    with pytest.raises(ValueError, match="other"):
        figure_metrics(report)


def test_script_writes_png_sidecar_and_metadata(tmp_path):
    report_path = tmp_path / "settling_report.json"
    report_path.write_text(json.dumps(_report()), encoding="utf-8")
    out = tmp_path / "out"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--report",
            str(report_path),
            "--out-dir",
            str(out),
            "--git-commit",
            "c" * 40,
            "--timestamp",
            "2026-11-30T12:00:00+00:00",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    png = out / "settling_figure.png"
    metrics = json.loads(
        (out / "settling_figure_metrics.json").read_text(encoding="utf-8")
    )
    meta = json.loads(
        (out / "settling_figure_run_metadata.json").read_text(encoding="utf-8")
    )
    assert png.stat().st_size > 10_000
    assert meta["png_sha256"] == hashlib.sha256(png.read_bytes()).hexdigest()
    assert meta["report_sha256"] == hashlib.sha256(report_path.read_bytes()).hexdigest()
    assert meta["git_commit"] == "c" * 40
    assert meta["renderer_sha256"]["scripts/make_settling_figure.py"]
    assert metrics == figure_metrics(_report())
