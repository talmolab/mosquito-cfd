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

from mosquito_cfd.force_surrogate.cfd_cost import median_cfd_seconds_per_wingbeat

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "cfd_seconds_per_wingbeat.py"


def _meta(
    tmp_path: Path,
    config: str,
    wall: object,
    cycles: object,
    gpu: object = "NVIDIA A40",
    drop: tuple[str, ...] = (),
) -> Path:
    record = {
        "config": config,
        "gpu_model": gpu,
        "cycles_completed": cycles,
        "timing": {"wall_time_s": wall},
    }
    for key in drop:
        if key == "wall_time_s":
            del record["timing"]["wall_time_s"]
        else:
            del record[key]
    path = tmp_path / f"run_metadata_{config}.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _three(tmp_path: Path) -> list[Path]:
    return [
        _meta(tmp_path, "s35_f085_p30", 300.0, 2.0),
        _meta(tmp_path, "s45_f100_p45", 400.0, 2.0),
        _meta(tmp_path, "s55_f115_p60", 1000.0, 2.0),
    ]


# --- Known answers --------------------------------------------------------------------------


def test_known_answer_median_min_max_and_count(tmp_path):
    """Scenario: Known-answer median (300/400/1000 s over 2 beats each)."""
    result = median_cfd_seconds_per_wingbeat(_three(tmp_path))
    assert result == {
        "seconds_per_wingbeat": 200.0,
        "n_configs": 3,
        "gpu_model": "NVIDIA A40",
        "min": 150.0,
        "max": 500.0,
    }


def test_input_order_does_not_change_the_result(tmp_path):
    paths = _three(tmp_path)
    assert median_cfd_seconds_per_wingbeat(
        paths[::-1]
    ) == median_cfd_seconds_per_wingbeat(paths)


def test_non_integer_cycle_count_is_used_as_is(tmp_path):
    """Committed cycles_completed are ~1.9995, not 2: no rounding."""
    path = _meta(tmp_path, "s35_f100_p30", 3999.0, 1.9995)
    result = median_cfd_seconds_per_wingbeat([path])
    assert result["seconds_per_wingbeat"] == 3999.0 / 1.9995


def test_even_count_is_the_mean_of_the_middle_two(tmp_path):
    paths = [
        *_three(tmp_path),
        _meta(tmp_path, "s55_f085_p30", 2000.0, 2.0),
    ]
    # per-wingbeat: 150, 200, 500, 1000 -> (200 + 500) / 2
    assert median_cfd_seconds_per_wingbeat(paths)["seconds_per_wingbeat"] == 350.0


# --- Validation -----------------------------------------------------------------------------


def test_no_paths_raises():
    with pytest.raises(ValueError, match="no run metadata"):
        median_cfd_seconds_per_wingbeat([])


@pytest.mark.parametrize("key", ["config", "gpu_model"])
def test_missing_identity_key_raises_naming_the_file(tmp_path, key):
    path = _meta(tmp_path, "s35_f085_p30", 300.0, 2.0, drop=(key,))
    with pytest.raises(ValueError, match=re.escape(path.name)):
        median_cfd_seconds_per_wingbeat([path])


@pytest.mark.parametrize("field", ["wall_time_s", "cycles_completed"])
@pytest.mark.parametrize(
    "bad",
    ["missing", None, True, "300", 0.0, -1.0, math.nan, math.inf],
    ids=["missing", "None", "bool", "str", "zero", "negative", "nan", "inf"],
)
def test_bad_timing_value_raises_naming_the_file(tmp_path, field, bad):
    """Scenario: Malformed or empty metadata is rejected."""
    wall: object = 300.0
    cycles: object = 2.0
    drop: tuple[str, ...] = ()
    if bad == "missing":
        drop = (field,)
    elif field == "wall_time_s":
        wall = bad
    else:
        cycles = bad
    path = _meta(tmp_path, "s35_f085_p30", wall, cycles, drop=drop)
    with pytest.raises(ValueError, match=re.escape(path.name)):
        median_cfd_seconds_per_wingbeat([path])


def test_duplicate_config_raises(tmp_path):
    first = _meta(tmp_path, "s35_f085_p30", 300.0, 2.0)
    dup_dir = tmp_path / "dup"
    dup_dir.mkdir()
    second = _meta(dup_dir, "s35_f085_p30", 400.0, 2.0)
    with pytest.raises(ValueError, match="s35_f085_p30"):
        median_cfd_seconds_per_wingbeat([first, second])


def test_two_gpu_models_raise(tmp_path):
    paths = [
        _meta(tmp_path, "s35_f085_p30", 300.0, 2.0),
        _meta(tmp_path, "s45_f100_p45", 400.0, 2.0, gpu="NVIDIA A100"),
    ]
    with pytest.raises(ValueError, match="GPU model"):
        median_cfd_seconds_per_wingbeat(paths)


# --- Script ---------------------------------------------------------------------------------


def test_script_prints_the_median_of_per_config_files_only(tmp_path):
    """Scenario: The script reads only per-configuration files (the corpus-level
    ``run_metadata.json`` has no ``timing`` and would raise if it were read)."""
    # A non-round median (4001 / 1.9995), so a rounded print would not read back exactly.
    paths = [
        _meta(tmp_path, "s35_f085_p30", 300.0, 2.0),
        _meta(tmp_path, "s45_f100_p45", 4001.0, 1.9995),
        _meta(tmp_path, "s55_f115_p60", 9000.0, 2.0),
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
    expected = median_cfd_seconds_per_wingbeat(paths)["seconds_per_wingbeat"]
    assert float(done.stdout.strip()) == expected
