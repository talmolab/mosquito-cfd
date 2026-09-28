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
DECK_TEXT = (
    "particle_inputs.x = 4.0\nparticle_inputs.y = 2.0\nparticle_inputs.z = 4.0\n"
    "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_y = 0.5\n"
    "particle_inputs.hinge_z = 4.0\n"
)


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
            "input_file": f"inputs/inputs.3d.{name}",
        }
        for i, name in enumerate(names)
    ]
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(json.dumps({"configs": configs}), encoding="utf-8")
    # The committed geometry: the fixture CSV's origin is (4, 2, 4), the pivot (4, 0.5, 4).
    (tmp_path / "inputs").mkdir()
    for name in names:
        (tmp_path / "inputs" / f"inputs.3d.{name}").write_text(
            DECK_TEXT, encoding="utf-8"
        )
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


def test_driver_records_moment_reference_and_extraction_inputs(tmp_path):
    """The corpus run_metadata.json names the moment reference point, the per-config offsets,
    the resolved --input-dir and the sha256 of every consumed CSV -- under the key names the
    spec fixes -- while dataset.units.json keeps its flat column->unit shape.

    Spec: Moment reference point travels with the corpus (design D6, D10).
    """
    import hashlib

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
    meta = json.loads(metadata.read_text(encoding="utf-8"))

    ref = meta["moment_reference"]
    assert ref["point"] == "wing_hinge"
    assert ref["definition"] == "docs/coordinate-convention.md#moments"
    assert ref["axes"] == "lab"
    assert ref["offset"] == "r_origin - r_hinge"
    assert ref["raw_moments_about"] == "particle_origin"
    assert ref["applies_to"] == ["CF_mx", "CF_my", "CF_mz"]
    assert set(ref["configs"]) == {"a", "b"}
    for name in ("a", "b"):
        record = ref["configs"][name]
        assert record["offset"] == [0.0, 1.5, 0.0]
        assert record["origin"] == [4.0, 2.0, 4.0]
        assert record["hinge"] == [4.0, 0.5, 4.0]
        assert record["deck"] == f"inputs/inputs.3d.{name}"
        deck = tmp_path / "inputs" / f"inputs.3d.{name}"
        assert record["deck_sha256"] == hashlib.sha256(deck.read_bytes()).hexdigest()
        assert record["deck_sha256_verified_against"] is None  # no per-config metadata
        assert "csv_sha256" not in record  # lives under extraction_inputs, once

    inputs = meta["extraction_inputs"]
    # As given, not resolved: resolving a mapped drive records a machine-specific UNC path.
    assert inputs["input_dir"] == input_dir.as_posix()
    assert inputs["csv_name"] == "IB_Particle_1.csv"
    # Hash of the bytes on disk that were consumed (write_text may have translated EOLs).
    assert inputs["csv_sha256"] == {
        name: hashlib.sha256(
            (input_dir / name / "IB_Particle_1.csv").read_bytes()
        ).hexdigest()
        for name in ("a", "b")
    }

    # The frame record is provenance, not a unit: the sidecar stays a flat unit map.
    sidecar = json.loads(units.read_text(encoding="utf-8"))
    assert all(isinstance(v, str) for v in sidecar.values())
    assert not {"moment_reference", "extraction_inputs"} & set(sidecar)


def test_driver_records_no_extraction_inputs_for_a_dropped_config(tmp_path):
    """A config skipped under --allow-missing consumed no CSV, so it has no hash or offset."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"], omit=["b"])
    metadata = tmp_path / "run_metadata.json"
    _load_driver().main(
        [
            "--manifest", str(manifest),
            "--input-dir", str(input_dir),
            "--out", str(tmp_path / "d.parquet"),
            "--units", str(tmp_path / "d.units.json"),
            "--metadata", str(metadata),
            "--docker-digest", SENTINEL_DIGEST,
            "--timestamp", TS,
            "--allow-missing",
        ]
    )  # fmt: skip
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    assert set(meta["moment_reference"]["configs"]) == {"a"}
    assert set(meta["extraction_inputs"]["csv_sha256"]) == {"a"}


def test_driver_writes_nothing_when_provenance_fails(tmp_path):
    """Metadata is captured BEFORE any output is written. So git state is recorded on the
    tree the extraction ran from (not one its own parquet already dirtied), and a
    provenance failure cannot leave a new parquet next to stale metadata."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    out = tmp_path / "dataset.parquet"
    with pytest.raises(ValueError):
        _load_driver().main(
            [
                "--manifest", str(manifest),
                "--input-dir", str(input_dir),
                "--out", str(out),
                "--units", str(tmp_path / "u.json"),
                "--metadata", str(tmp_path / "m.json"),
                "--docker-digest", "ghcr.io/talmolab/mosquito-cfd:latest",
                "--timestamp", TS,
            ]
        )  # fmt: skip
    assert not out.exists()
    assert not (tmp_path / "u.json").exists()
