"""Tests for force_surrogate.cfd_cost (add-fine-corpus-surrogate, design D3; TDD).

Torch-free and cluster-free: every fixture is a hand-written ``run_metadata_<config>.json`` in
``tmp_path`` carrying only the keys the helper reads.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate.cfd_cost import median_cfd_seconds_per_step

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "cfd_seconds_per_step.py"


def _meta(
    tmp_path: Path,
    config: str,
    wall: object,
    steps: object,
    gpu: object = "NVIDIA A40",
    drop: tuple[str, ...] = (),
) -> Path:
    record = {
        "config": config,
        "gpu_model": gpu,
        "timing": {"wall_time_s": wall, "timesteps": steps},
    }
    for key in drop:
        if key in ("wall_time_s", "timesteps"):
            del record["timing"][key]
        else:
            del record[key]
    path = tmp_path / f"run_metadata_{config}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _three(tmp_path: Path) -> list[Path]:
    return [
        _meta(tmp_path, "s35_f085_p30", 300.0, 200),
        _meta(tmp_path, "s45_f100_p45", 400.0, 200),
        _meta(tmp_path, "s55_f115_p60", 1000.0, 200),
    ]


# --- Known answers --------------------------------------------------------------------------


def test_known_answer_median_min_max_and_count(tmp_path):
    """Scenario: Known-answer median (300/400/1000 s over 200 steps each)."""
    result = median_cfd_seconds_per_step(_three(tmp_path))
    assert result == {
        "seconds_per_step": 2.0,
        "n_configs": 3,
        "gpu_model": "NVIDIA A40",
        "min": 1.5,
        "max": 5.0,
    }


def test_input_order_does_not_change_the_result(tmp_path):
    paths = _three(tmp_path)
    assert median_cfd_seconds_per_step(paths[::-1]) == median_cfd_seconds_per_step(
        paths
    )


def test_cost_is_per_step_not_per_wingbeat(tmp_path):
    """Two configs with the same per-step rate but different step counts (different f*)
    have the same cost: the per-step rate does not depend on the kinematics."""
    paths = [
        _meta(tmp_path, "s35_f085_p30", 4706 * 2.1, 4706),
        _meta(tmp_path, "s35_f115_p30", 3478 * 2.1, 3478),
    ]
    result = median_cfd_seconds_per_step(paths)
    assert result["seconds_per_step"] == pytest.approx(2.1, rel=1e-15)
    assert result["min"] == pytest.approx(result["max"], rel=1e-15)


def test_even_count_is_the_mean_of_the_middle_two(tmp_path):
    paths = [*_three(tmp_path), _meta(tmp_path, "s55_f085_p30", 2000.0, 200)]
    # per step: 1.5, 2.0, 5.0, 10.0 -> (2.0 + 5.0) / 2
    assert median_cfd_seconds_per_step(paths)["seconds_per_step"] == 3.5


# --- Validation -----------------------------------------------------------------------------


def test_no_paths_raises():
    with pytest.raises(ValueError, match="no run metadata"):
        median_cfd_seconds_per_step([])


@pytest.mark.parametrize("key", ["config", "gpu_model"])
def test_missing_identity_key_raises_naming_the_file(tmp_path, key):
    path = _meta(tmp_path, "s35_f085_p30", 300.0, 200, drop=(key,))
    with pytest.raises(ValueError, match=re.escape(path.name)):
        median_cfd_seconds_per_step([path])


@pytest.mark.parametrize(
    "bad",
    ["missing", None, True, "300", 0.0, -1.0, math.nan, math.inf],
    ids=["missing", "None", "bool", "str", "zero", "negative", "nan", "inf"],
)
def test_bad_wall_time_raises_naming_the_file(tmp_path, bad):
    """Scenario: Malformed or empty metadata is rejected."""
    drop = ("wall_time_s",) if bad == "missing" else ()
    path = _meta(tmp_path, "s35_f085_p30", bad, 200, drop=drop)
    with pytest.raises(ValueError, match=re.escape(path.name)):
        median_cfd_seconds_per_step([path])


@pytest.mark.parametrize(
    "bad",
    ["missing", None, True, "200", 0, -5, 200.5],
    ids=["missing", "None", "bool", "str", "zero", "negative", "fractional"],
)
def test_bad_timestep_count_raises_naming_the_file(tmp_path, bad):
    drop = ("timesteps",) if bad == "missing" else ()
    path = _meta(tmp_path, "s35_f085_p30", 300.0, bad, drop=drop)
    with pytest.raises(ValueError, match=re.escape(path.name)):
        median_cfd_seconds_per_step([path])


def test_duplicate_config_raises(tmp_path):
    first = _meta(tmp_path, "s35_f085_p30", 300.0, 200)
    dup_dir = tmp_path / "dup"
    dup_dir.mkdir()
    second = _meta(dup_dir, "s35_f085_p30", 400.0, 200)
    with pytest.raises(ValueError, match="s35_f085_p30"):
        median_cfd_seconds_per_step([first, second])


def test_two_gpu_models_raise(tmp_path):
    paths = [
        _meta(tmp_path, "s35_f085_p30", 300.0, 200),
        _meta(tmp_path, "s45_f100_p45", 400.0, 200, gpu="NVIDIA A100"),
    ]
    with pytest.raises(ValueError, match="GPU model"):
        median_cfd_seconds_per_step(paths)


# --- Script ---------------------------------------------------------------------------------


def test_script_prints_the_median_of_per_config_files_only(tmp_path):
    """Scenario: The script reads only per-configuration files (the corpus-level
    ``run_metadata.json`` has no ``timing`` and would raise if it were read)."""
    # A non-round median (4001 / 1999 s/step), so a rounded print would not read back exactly.
    paths = [
        _meta(tmp_path, "s35_f085_p30", 300.0, 200),
        _meta(tmp_path, "s45_f100_p45", 4001.0, 1999),
        _meta(tmp_path, "s55_f115_p60", 9000.0, 200),
    ]
    (tmp_path / "run_metadata.json").write_text(
        json.dumps({"git": {"commit": "x"}}), encoding="utf-8"
    )
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--metadata-dir", str(tmp_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    expected = median_cfd_seconds_per_step(paths)["seconds_per_step"]
    assert expected == 4001.0 / 1999
    assert float(done.stdout.strip()) == expected
