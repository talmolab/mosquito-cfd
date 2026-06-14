"""Tests for force_surrogate.sidecar (TDD red phase)."""

import json

import pytest

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate import (
    capture_surrogate_run_metadata,
    read_units_sidecar,
    validate_image_digest,
    write_units_sidecar,
)

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64


def test_validate_image_digest_accepts_and_strips():
    """A pinned sha256 digest passes and is returned stripped of surrounding whitespace."""
    assert validate_image_digest(f"  {DIGEST}  ") == DIGEST


def test_validate_image_digest_rejects_mutable_or_empty():
    """An empty/blank/mutable-tag reference is rejected (no I/O, parity with the capture guard)."""
    for bad in (
        "",
        "   ",
        "ghcr.io/talmolab/mosquito-cfd:latest",
        "repo@sha256:deadbeef",
    ):
        with pytest.raises(ValueError, match="content-addressable"):
            validate_image_digest(bad)


def test_units_sidecar_roundtrip(tmp_path):
    """write -> read returns an identical mapping (UTF-8 JSON)."""
    units = {
        "cf_x": "dimensionless",
        "stroke_amp": "deg",
        "frequency": "dimensionless (f*)",
    }
    path = tmp_path / "dataset.units.json"
    write_units_sidecar(path, units)
    assert read_units_sidecar(path) == units
    # the on-disk file is valid UTF-8 JSON (guards the ensure_ascii=False / JSON writer)
    assert json.loads(path.read_text(encoding="utf-8")) == units


def test_write_units_sidecar_rejects_unknown_unit(tmp_path):
    """An out-of-vocabulary unit raises ValueError naming column + unit."""
    with pytest.raises(ValueError) as exc:
        write_units_sidecar(tmp_path / "u.json", {"force": "newtons"})
    msg = str(exc.value)
    assert "force" in msg and "newtons" in msg


def test_write_units_sidecar_rejects_non_string_key_or_unit(tmp_path):
    """Non-string column keys/units are rejected (they don't round-trip through JSON)."""
    with pytest.raises(ValueError):
        write_units_sidecar(tmp_path / "k.json", {1: "dimensionless"})  # type: ignore[dict-item]
    with pytest.raises(ValueError):
        write_units_sidecar(tmp_path / "v.json", {"cf_x": 2.0})  # type: ignore[dict-item]


def test_read_units_sidecar_rejects_invalid(tmp_path):
    """Malformed JSON, non-object JSON, and illegal on-disk units all raise."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(ValueError):
        read_units_sidecar(bad)

    not_obj = tmp_path / "list.json"
    not_obj.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ValueError):
        read_units_sidecar(not_obj)

    illegal = tmp_path / "illegal.json"
    illegal.write_text(json.dumps({"force": "newtons"}), encoding="utf-8")
    with pytest.raises(ValueError):
        read_units_sidecar(illegal)


def test_capture_surrogate_run_metadata(tmp_path):
    """Records git commit, the digest, the inputs hash, and a caller timestamp."""
    inputs = tmp_path / "inputs.3d"
    inputs.write_text("ns.init_iter = 2\n", encoding="utf-8")
    ts = "2020-01-01T00:00:00+00:00"
    meta = capture_surrogate_run_metadata(
        docker_image_digest=DIGEST, inputs_file=inputs, timestamp=ts
    )
    assert "commit" in meta["git"] or "error" in meta["git"]
    assert meta["docker_image"] == DIGEST
    assert meta["inputs"]["hash"] == hash_file(inputs)
    assert meta["timestamp"] == ts

    # digest-only path omits the inputs block
    meta_no_inputs = capture_surrogate_run_metadata(docker_image_digest=DIGEST)
    assert "inputs" not in meta_no_inputs


def test_capture_surrogate_run_metadata_requires_digest():
    """Blank, missing, or mutable-tag references are rejected; only a sha256 digest passes."""
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(docker_image_digest="")
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(docker_image_digest="   ")
    # a mutable tag is not content-addressable -> rejected
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest"
        )
    # strings that merely contain "sha256:" but aren't a 64-hex digest -> rejected
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(docker_image_digest="repo@sha256:deadbeef")
    with pytest.raises(ValueError):
        capture_surrogate_run_metadata(
            docker_image_digest="ghcr.io/x:tag-sha256:nothex"
        )


def test_capture_surrogate_run_metadata_strips_digest_whitespace():
    """Surrounding whitespace is stripped before the digest is recorded."""
    meta = capture_surrogate_run_metadata(docker_image_digest=f"  {DIGEST}  ")
    assert meta["docker_image"] == DIGEST
