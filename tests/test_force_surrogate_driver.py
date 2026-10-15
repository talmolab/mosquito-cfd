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
    # Non-canonical on purpose: resolve() would collapse the "..", so recording the path
    # verbatim is observable (an already-canonical tmp_path made the two indistinguishable).
    given = input_dir / ".." / input_dir.name
    out = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    metadata = tmp_path / "run_metadata.json"
    rc = _load_driver().main(
        [
            "--manifest", str(manifest),
            "--input-dir", str(given),
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
    assert inputs["input_dir"] == given.as_posix()
    assert "/../" in inputs["input_dir"]
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
    with pytest.raises(ValueError, match="sha256"):
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


def _main_args(manifest, input_dir, tmp_path, *extra):
    return [
        "--manifest", str(manifest),
        "--input-dir", str(input_dir),
        "--out", str(tmp_path / "dataset.parquet"),
        "--units", str(tmp_path / "dataset.units.json"),
        "--metadata", str(tmp_path / "run_metadata.json"),
        "--docker-digest", SENTINEL_DIGEST,
        "--timestamp", TS,
        *extra,
    ]  # fmt: skip


def _write_run_metadata(input_dir, name, deck_sha256):
    (input_dir / name / "run_metadata.json").write_text(
        json.dumps({"config": name, "deck_sha256": deck_sha256}), encoding="utf-8"
    )


def test_run_metadata_name_anchors_decks_to_each_runs_own_metadata(tmp_path):
    """--run-metadata-name reads <input-dir>/<name>/<file>: the metadata each CFD run wrote
    beside its CSV. The coarse corpus has no per-config metadata beside its manifest, so this
    is the only way its decks can be checked against the runs. Tasks 32k, 32u."""
    import hashlib

    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"])
    for name in ("a", "b"):
        deck = tmp_path / "inputs" / f"inputs.3d.{name}"
        _write_run_metadata(
            input_dir, name, hashlib.sha256(deck.read_bytes()).hexdigest()
        )
    # Non-canonical on purpose (M09): a resolve()d anchor would collapse the "..", and on
    # the operator's mapped drive would record a network path.
    given = input_dir / ".." / input_dir.name

    args = _main_args(
        manifest, given, tmp_path, "--run-metadata-name", "run_metadata.json"
    )
    assert _load_driver().main(args) == 0
    meta = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    for name in ("a", "b"):
        anchor = meta["moment_reference"]["configs"][name][
            "deck_sha256_verified_against"
        ]
        assert anchor == (given / name / "run_metadata.json").as_posix()
        assert "/../" in anchor


def test_run_metadata_name_rejects_a_deck_changed_since_its_run(tmp_path):
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    _write_run_metadata(input_dir, "a", "0" * 64)
    args = _main_args(
        manifest, input_dir, tmp_path, "--run-metadata-name", "run_metadata.json"
    )
    with pytest.raises(ValueError, match="deck_sha256"):
        _load_driver().main(args)
    assert not (tmp_path / "dataset.parquet").exists()


@pytest.mark.parametrize(
    "anchor", ["missing-file", "no-deck-sha256", "misspelled-flag"]
)
def test_run_metadata_name_fails_closed_when_a_config_is_unanchored(tmp_path, anchor):
    """The flag is an explicit opt-in to verification: an extracted config left unanchored
    (file absent, no deck_sha256 in it, or the flag value misspelled) fails extraction
    before anything is written, instead of silently recording "unverified". Task 32t."""
    import hashlib

    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"])
    good = hashlib.sha256(
        (tmp_path / "inputs" / "inputs.3d.a").read_bytes()
    ).hexdigest()
    _write_run_metadata(input_dir, "a", good)
    _write_run_metadata(input_dir, "b", good)  # decks a and b are identical
    flag_value = "run_metadata.json"
    if anchor == "missing-file":
        (input_dir / "b" / "run_metadata.json").unlink()
    elif anchor == "no-deck-sha256":
        (input_dir / "b" / "run_metadata.json").write_text("{}", encoding="utf-8")
    else:
        flag_value = "run_metdata.json"
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="not anchored"):
        _load_driver().main(
            _main_args(manifest, input_dir, tmp_path, "--run-metadata-name", flag_value)
        )
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "name", ["sub/run_metadata.json", "../run_metadata.json", "ABSOLUTE", "", "."]
)
def test_run_metadata_name_must_be_a_bare_file_name(tmp_path, name):
    """A path in the flag would anchor outside <input-dir>/<config>/ (an absolute one makes
    every config share one file). Rejected before any extraction. Task 32t.

    A VALID anchor is placed wherever the bad name would point, so only the name check can
    reject it: without that check this extraction would succeed, anchored to the wrong file.
    """
    import hashlib

    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    if name == "ABSOLUTE":
        name = str(tmp_path / "shared.json")
    good = hashlib.sha256(
        (tmp_path / "inputs" / "inputs.3d.a").read_bytes()
    ).hexdigest()
    would_read = input_dir / "a" / name
    if name and name != "." and not would_read.is_dir():
        would_read.parent.mkdir(parents=True, exist_ok=True)
        would_read.write_text(json.dumps({"deck_sha256": good}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a bare file name"):
        _load_driver().main(
            _main_args(manifest, input_dir, tmp_path, "--run-metadata-name", name)
        )
    assert not (tmp_path / "dataset.parquet").exists()


def test_run_metadata_name_with_allow_missing_anchors_what_was_extracted(tmp_path):
    """A config dropped under --allow-missing consumed no CSV, so it needs no anchor; the
    configs that were extracted still must be anchored and are recorded so (M15)."""
    import hashlib

    manifest, input_dir = _make_run_tree(tmp_path, ["a", "b"], omit=["b"])
    deck = tmp_path / "inputs" / "inputs.3d.a"
    _write_run_metadata(input_dir, "a", hashlib.sha256(deck.read_bytes()).hexdigest())
    args = _main_args(
        manifest, input_dir, tmp_path,
        "--run-metadata-name", "run_metadata.json", "--allow-missing",
    )  # fmt: skip
    assert _load_driver().main(args) == 0
    meta = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["dropped_configs"] == ["b"]
    anchor = meta["moment_reference"]["configs"]["a"]["deck_sha256_verified_against"]
    assert anchor == (input_dir / "a" / "run_metadata.json").as_posix()


def test_without_run_metadata_name_the_runs_metadata_is_not_consulted(tmp_path):
    """The default keeps the beside-the-manifest convention (the fine corpus's committed
    per-config files), so a run-directory file is ignored unless asked for."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    _write_run_metadata(input_dir, "a", "0" * 64)
    assert _load_driver().main(_main_args(manifest, input_dir, tmp_path)) == 0
    meta = json.loads((tmp_path / "run_metadata.json").read_text(encoding="utf-8"))
    assert (
        meta["moment_reference"]["configs"]["a"]["deck_sha256_verified_against"] is None
    )


def _snapshot(root):
    """Every path under ``root`` with its bytes (None for directories). Comparing snapshots
    detects any leftover or changed file, whatever it is named (M17)."""
    return {
        p.relative_to(root).as_posix(): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def _seed_previous_outputs(tmp_path):
    out = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    metadata = tmp_path / "run_metadata.json"
    out.write_bytes(b"previous parquet")
    units.write_text("previous units", encoding="utf-8")
    metadata.write_text("previous metadata", encoding="utf-8")
    return out, units, metadata


def _run(driver, manifest, input_dir, out, units, metadata):
    return driver.main(
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


def test_a_failure_while_writing_changes_nothing(tmp_path, monkeypatch):
    """Everything is written to temporaries before anything is moved, so a failure while
    writing leaves the directory exactly as it was: previous outputs intact, no temporary
    left behind. Task 32r / spec: A failed write leaves the previous outputs in place."""
    driver = _load_driver()
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    out, units, metadata = _seed_previous_outputs(tmp_path)

    def broken_dump(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(driver.json, "dump", broken_dump)
    before = _snapshot(tmp_path)
    with pytest.raises(OSError, match="disk full"):
        _run(driver, manifest, input_dir, out, units, metadata)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("which", ["out", "units", "metadata"])
def test_a_directory_target_is_rejected_before_anything_is_written(tmp_path, which):
    """Any of the three targets being a directory would otherwise fail only at its move, after
    earlier outputs had been replaced (M10: every target, not just --units)."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    out, units, metadata = _seed_previous_outputs(tmp_path)
    target = {"out": out, "units": units, "metadata": metadata}[which]
    target.unlink()
    target.mkdir()
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="director"):
        _run(_load_driver(), manifest, input_dir, out, units, metadata)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "pair", [("out", "units"), ("units", "metadata"), ("out", "metadata")]
)
def test_duplicate_output_paths_are_rejected(tmp_path, pair):
    """Two outputs at one path silently lost one of them (the later move overwrote it)."""
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    paths = dict(zip(("out", "units", "metadata"), _seed_previous_outputs(tmp_path)))
    paths[pair[1]] = paths[pair[0]]
    before = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="same path"):
        _run(
            _load_driver(),
            manifest,
            input_dir,
            paths["out"],
            paths["units"],
            paths["metadata"],
        )
    assert _snapshot(tmp_path) == before


def test_a_failure_while_moving_is_reported_and_never_replaces_the_parquet_first(
    tmp_path, monkeypatch
):
    """Three renames cannot be atomic. The parquet moves LAST, so a move failure can never
    leave a new parquet beside stale provenance; the error names what was already
    replaced, and the temporaries not yet moved are kept. Task 32r (M12: move order)."""
    driver = _load_driver()
    manifest, input_dir = _make_run_tree(tmp_path, ["a"])
    out, units, metadata = _seed_previous_outputs(tmp_path)
    real_replace = driver.os.replace
    moved_to = []

    def flaky_replace(src, dst):
        moved_to.append(Path(dst))
        if len(moved_to) == 2:
            raise PermissionError("[WinError 5] Access is denied")
        return real_replace(src, dst)

    monkeypatch.setattr(driver.os, "replace", flaky_replace)
    with pytest.raises(RuntimeError, match="already replaced") as excinfo:
        _run(driver, manifest, input_dir, out, units, metadata)

    assert out not in moved_to  # the parquet was never reached: it moves last
    assert out.read_bytes() == b"previous parquet"
    message = str(excinfo.value)
    assert str(moved_to[0]) in message  # the one output already replaced is named
    kept = [p for p in tmp_path.iterdir() if p.name.startswith(".") and p.is_file()]
    assert len(kept) == 2, kept  # the two outputs not yet moved, the parquet's included
    assert all(str(p) in message for p in kept)
