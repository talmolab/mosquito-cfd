"""Smoke tests for the scripts/extract_forces.py driver.

Cluster-free (CC-2): builds a fixture-derived per-config run tree in ``tmp_path`` and runs
the driver's ``main()`` end-to-end. No RunAI, GPU, or plotfiles.
"""

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "scripts" / "extract_forces.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_ib_particle.csv"

# Obviously-synthetic sentinel digest — a test invocation never ran a real container.
SENTINEL_DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "0" * 64
TS = "2026-06-10T00:00:00+00:00"


def _load_driver():
    spec = importlib.util.spec_from_file_location("extract_forces_driver", DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def _make_run_tree(tmp_path, names, *, omit=()):
    """Write a manifest + per-config <input-dir>/<name>/IB_Particle_1.csv tree."""
    configs = [
        {
            "index": i,
            "name": name,
            "stroke_amp_deg": 45.0,
            "frequency_fstar": 1.0,
            "pitch_amp_deg": 45.0,
            "reynolds": 60.0,
            "split": "train",
        }
        for i, name in enumerate(names)
    ]
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(json.dumps({"configs": configs}), encoding="utf-8")
    input_dir = tmp_path / "runs"
    fixture_text = FIXTURE.read_text(encoding="utf-8")
    for name in names:
        if name in omit:
            continue
        run = input_dir / name
        run.mkdir(parents=True)
        (run / "IB_Particle_1.csv").write_text(fixture_text, encoding="utf-8")
    return manifest, input_dir


def test_driver_smoke_writes_all_artifacts(tmp_path):
    """main() runs end-to-end: exit 0, parquet + units + metadata written and re-readable."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"])
    out = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    metadata = tmp_path / "run_metadata.json"

    rc = _load_driver().main(
        [
            "--manifest", str(manifest),
            "--input-dir", str(input_dir),
            "--out", str(out),
            "--units", str(units),
            "--metadata", str(metadata),
            "--docker-digest", SENTINEL_DIGEST,
            "--timestamp", TS,
        ]
    )  # fmt: skip
    assert rc == 0
    assert out.exists() and units.exists() and metadata.exists()
    df = pd.read_parquet(out)
    assert len(df) == 2 * 5  # 2 configs x 5 fixture timesteps
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    assert meta["timestamp"] == TS
    assert meta["dropped_configs"] == []


def test_driver_allow_missing_records_dropped_top_level(tmp_path):
    """--allow-missing skips an absent config and records it top-level in run_metadata."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"], omit=["b"])
    out = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    metadata = tmp_path / "run_metadata.json"

    rc = _load_driver().main(
        [
            "--manifest", str(manifest),
            "--input-dir", str(input_dir),
            "--out", str(out),
            "--units", str(units),
            "--metadata", str(metadata),
            "--docker-digest", SENTINEL_DIGEST,
            "--timestamp", TS,
            "--allow-missing",
        ]
    )  # fmt: skip
    assert rc == 0
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    assert meta["dropped_configs"] == ["b"]  # top-level, not nested under "extra"
    assert pd.read_parquet(out)["config_name"].unique().tolist() == ["a"]


def test_driver_malformed_manifest_raises_clear_error(tmp_path):
    """A manifest with no 'configs' surfaces a clear ValueError on the CLI path."""
    bad_manifest = tmp_path / "sweep_manifest.json"
    bad_manifest.write_text(json.dumps({"grid": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="configs"):
        _load_driver().main(
            [
                "--manifest", str(bad_manifest),
                "--input-dir", str(tmp_path / "runs"),
                "--out", str(tmp_path / "d.parquet"),
                "--units", str(tmp_path / "d.units.json"),
                "--metadata", str(tmp_path / "m.json"),
                "--docker-digest", SENTINEL_DIGEST,
                "--timestamp", TS,
            ]
        )  # fmt: skip
