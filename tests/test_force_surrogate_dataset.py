"""Tests for force_surrogate.dataset (TDD).

Cluster-free (roadmap CC-2): every test runs against the committed
``tests/fixtures/synthetic_ib_particle.csv`` plus a manifest — either the committed
``examples/prelim_sweep/sweep_manifest.json`` (corpus-shaped checks) or a small synthetic
manifest the test writes into ``tmp_path`` (validated-point / boundary checks, since no
committed config is at the validated stroke of 70 deg). No RunAI, GPU, or plotfiles.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import (
    build_dataset,
    build_run_metadata,
    compute_force_reference,
    compute_moment_reference,
    read_units_sidecar,
    write_dataset,
)
from mosquito_cfd.force_surrogate.constants import CHORD, R_TIP, RHO, SPAN
from mosquito_cfd.force_surrogate.dataset import (
    _DATASET_UNITS,
    DATASET_COLUMNS,
    IB_PARTICLE_COLUMNS,
)

# Measured columns get a units entry; string/bookkeeping columns are omitted.
_NON_MEASURED = {"config_name", "split", "index", "wingbeat"}
_MEASURED = [c for c in DATASET_COLUMNS if c not in _NON_MEASURED]

REPO = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_ib_particle.csv"
COMMITTED_MANIFEST = REPO / "examples" / "prelim_sweep" / "sweep_manifest.json"
COMMITTED_UNITS = REPO / "examples" / "prelim_sweep" / "dataset.units.json"

# Fixture raw forces/moments (for ratio assertions).
FIXTURE_FX = np.array([0.0, 50.0, -30.0, 75.0, -100.0])
FIXTURE_MX = np.array([0.0, 20.0, -40.0, 90.0, -70.0])
FIXTURE_TIME = np.array([0.0, 0.25, 0.5, 0.75, 1.0])


def _write_manifest(path: Path, configs: list[dict]) -> Path:
    """Write a minimal sweep manifest (only the keys build_dataset reads)."""
    path.write_text(json.dumps({"configs": configs}), encoding="utf-8")
    return path


def _validated_point_config() -> dict:
    """A synthetic single config at the validated point (phi=70, f*=1.0).

    No committed-corpus config is at phi=70, so the f_ref ~ 624.79 anchor and the
    phase/wingbeat time*f*=1.0 boundary can only be exercised by a synthetic config.
    """
    return {
        "index": 0,
        "name": "s70_f100_p45",
        "stroke_amp_deg": 70.0,
        "frequency_fstar": 1.0,
        "pitch_amp_deg": 45.0,
        "reynolds": 100.0,
        "split": "train",
    }


# ---------------------------------------------------------------------------
# Corpus-shaped checks (committed sweep_manifest.json + fixture CSV)
# ---------------------------------------------------------------------------


def test_one_row_per_config_and_timestep():
    """N configs x T timesteps -> N*T rows. Spec: One row per config and timestep."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    n_configs = len(manifest["configs"])
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    df, dropped = build_dataset(COMMITTED_MANIFEST, csv_paths)
    assert dropped == []
    assert len(df) == n_configs * len(FIXTURE_TIME)


def test_columns_are_documented_schema():
    """Columns are exactly the 22-column schema. Spec: Columns are the documented schema."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    df, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
    assert list(df.columns) == DATASET_COLUMNS
    assert DATASET_COLUMNS == [
        "config_name",
        "index",
        "time",
        "phase",
        "wingbeat",
        "stroke_amp_deg",
        "frequency_fstar",
        "pitch_amp_deg",
        "reynolds",
        "split",
        "Fx",
        "Fy",
        "Fz",
        "Mx",
        "My",
        "Mz",
        "CF_x",
        "CF_y",
        "CF_z",
        "CF_mx",
        "CF_my",
        "CF_mz",
    ]


def test_holdout_split_carried_through():
    """Each row carries its config's split verbatim. Spec: Held-out split carried through."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    df, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
    # The committed manifest has both train and holdout configs.
    by_name = {c["name"]: c["split"] for c in manifest["configs"]}
    for name, group in df.groupby("config_name"):
        assert set(group["split"]) == {by_name[name]}
    assert set(df["split"]) == {"train", "holdout"}


def test_complete_build_reports_no_drops():
    """A complete build returns dropped == []. Spec: Complete build reports no drops."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    _, dropped = build_dataset(COMMITTED_MANIFEST, csv_paths)
    assert dropped == []


# ---------------------------------------------------------------------------
# Validated-point + boundary checks (synthetic single-config manifest)
# ---------------------------------------------------------------------------


def test_coefficients_use_single_source_per_config_normalization(tmp_path):
    """CF_* == raw / per-config reference (ratio form, not round literals).

    Spec: Coefficients use the single-source per-config normalization.
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})

    f_ref = compute_force_reference(
        f_star=1.0, phi_amp_deg=70.0, r_tip=R_TIP, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    m_ref = compute_moment_reference(
        f_star=1.0, phi_amp_deg=70.0, r_tip=R_TIP, span=SPAN, chord=CHORD, rho=RHO
    ).m_ref
    assert f_ref == pytest.approx(624.79, rel=1e-3)
    np.testing.assert_allclose(df["CF_x"].to_numpy(), FIXTURE_FX / f_ref)
    np.testing.assert_allclose(df["CF_mx"].to_numpy(), FIXTURE_MX / m_ref)
    # Not round literals: 50/624.79 ~ 0.0800.
    assert df["CF_x"].to_numpy()[1] == pytest.approx(50.0 / f_ref)


def test_phase_and_wingbeat_tag_every_timestep(tmp_path):
    """phase=(t*f*) mod 1, wingbeat=floor(t*f*); boundary at t*f*=1.0.

    Spec: Phase and wingbeat tag every timestep, no rows dropped. f*=1.0 is required
    so the fixture's time=1.0 row lands exactly on the boundary.
    """
    cfg = _validated_point_config()  # frequency_fstar = 1.0
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert len(df) == len(FIXTURE_TIME)  # no rows dropped
    np.testing.assert_allclose(df["phase"].to_numpy(), [0.0, 0.25, 0.5, 0.75, 0.0])
    np.testing.assert_array_equal(df["wingbeat"].to_numpy(), [0, 0, 0, 0, 1])
    assert ((df["phase"].to_numpy() >= 0.0) & (df["phase"].to_numpy() < 1.0)).all()
    assert df["wingbeat"].dtype == np.int64


def test_name_based_parse_is_robust_to_column_order(tmp_path):
    """A column-reordered CSV yields identical coefficients. Spec: Name-based parse."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df_canonical, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})

    reordered = pd.read_csv(FIXTURE)[list(reversed(IB_PARTICLE_COLUMNS))]
    reordered_path = tmp_path / "reordered.csv"
    reordered.to_csv(reordered_path, index=False)
    df_reordered, _ = build_dataset(manifest, {cfg["name"]: reordered_path})

    for col in ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"):
        np.testing.assert_allclose(
            df_reordered[col].to_numpy(), df_canonical[col].to_numpy()
        )


# ---------------------------------------------------------------------------
# Missing vs empty CSV (distinguished by path existence, not row count)
# ---------------------------------------------------------------------------


def test_empty_csv_yields_no_rows(tmp_path):
    """A present header-only CSV contributes zero rows, no error. Spec: Empty force CSV."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    empty = tmp_path / "empty.csv"
    empty.write_text(",".join(IB_PARTICLE_COLUMNS) + "\n", encoding="utf-8")
    df, dropped = build_dataset(manifest, {cfg["name"]: empty})
    assert len(df) == 0
    assert dropped == []  # present-but-empty is NOT a drop
    assert list(df.columns) == DATASET_COLUMNS


def test_missing_csv_rejected_by_default(tmp_path):
    """An absent path raises ValueError naming the config. Spec: Missing CSV rejected."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ValueError, match=cfg["name"]):
        build_dataset(manifest, {cfg["name"]: tmp_path / "does_not_exist.csv"})
    # Also missing when the key is absent entirely.
    with pytest.raises(ValueError, match=cfg["name"]):
        build_dataset(manifest, {})


def test_allow_missing_skips_and_returns_dropped(tmp_path):
    """allow_missing emits present configs and returns dropped names. Spec: allow_missing."""
    present = _validated_point_config()
    absent = {
        "index": 1,
        "name": "s55_f100_p45",
        "stroke_amp_deg": 55.0,
        "frequency_fstar": 1.0,
        "pitch_amp_deg": 45.0,
        "reynolds": 78.0,
        "split": "train",
    }
    manifest = _write_manifest(tmp_path / "m.json", [present, absent])
    df, dropped = build_dataset(
        manifest,
        {present["name"]: FIXTURE},  # absent config has no path
        allow_missing=True,
    )
    assert dropped == [absent["name"]]
    assert set(df["config_name"]) == {present["name"]}
    assert len(df) == len(FIXTURE_TIME)


def test_allow_missing_all_dropped_yields_empty_framed_dataset(tmp_path):
    """If every config is dropped, the frame is empty but keeps the full schema."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, dropped = build_dataset(
        manifest, {cfg["name"]: tmp_path / "absent.csv"}, allow_missing=True
    )
    assert dropped == [cfg["name"]]
    assert len(df) == 0
    assert list(df.columns) == DATASET_COLUMNS


# ---------------------------------------------------------------------------
# Force-only scope guard (CC-6)
# ---------------------------------------------------------------------------


def test_force_only_no_plotfile_parameter(tmp_path):
    """build_dataset consumes only CSV + manifest; no plotfile path. Spec: Force-only guard."""
    import inspect

    params = set(inspect.signature(build_dataset).parameters)
    assert not (params & {"plotfile", "plot_file", "field", "velocity"})
    # And it runs with no plotfile present.
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert len(df) == len(FIXTURE_TIME)


# ---------------------------------------------------------------------------
# write_dataset: units sidecar + parquet round-trip
# ---------------------------------------------------------------------------


def _build_demo(tmp_path):
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    return df


def test_units_sidecar_validates_and_covers_measured_columns(tmp_path):
    """dataset.units.json round-trips and maps every measured column.

    Spec: Units sidecar validates against the dimensionless vocabulary; Non-measured
    columns are omitted.
    """
    df = _build_demo(tmp_path)
    parquet = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    write_dataset(df, parquet, units)

    mapping = read_units_sidecar(units)
    # All measured columns present; non-measured absent (inverse check).
    assert set(mapping) == set(_MEASURED)
    assert _NON_MEASURED.isdisjoint(mapping)
    # Spot-check the unit assignments.
    assert mapping["CF_x"] == "dimensionless"
    assert mapping["CF_mz"] == "dimensionless"
    assert mapping["phase"] == "dimensionless"
    assert mapping["time"] == "dimensionless"
    assert mapping["reynolds"] == "dimensionless"
    assert mapping["stroke_amp_deg"] == "deg"
    assert mapping["pitch_amp_deg"] == "deg"
    assert mapping["frequency_fstar"] == "dimensionless (f*)"


def test_parquet_round_trip_preserves_values_and_dtypes(tmp_path):
    """write_dataset then read_parquet returns an equal frame (value/schema, not bytes).

    Spec test-strategy #4: float64 coeffs, int64 wingbeat, string cols via check_dtype=False.
    """
    df = _build_demo(tmp_path)
    parquet = tmp_path / "dataset.parquet"
    units = tmp_path / "dataset.units.json"
    write_dataset(df, parquet, units)

    rt = pd.read_parquet(parquet)
    assert list(rt.columns) == DATASET_COLUMNS
    # Coefficient/raw columns are float64; wingbeat is int64.
    for col in ("CF_x", "CF_mz", "Fx", "Mz", "time", "phase"):
        assert rt[col].dtype == np.float64
    assert rt["wingbeat"].dtype == np.int64
    # Value equality, ignoring string-column dtype drift (object<->string[pyarrow]).
    pd.testing.assert_frame_equal(
        rt.reset_index(drop=True), df.reset_index(drop=True), check_dtype=False
    )


# ---------------------------------------------------------------------------
# Dataset-build provenance (CC-1)
# ---------------------------------------------------------------------------

_DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
_TS = "2026-06-10T12:00:00+00:00"


def test_provenance_records_digest_timestamp_and_dropped_top_level():
    """run_metadata records digest + caller timestamp + TOP-LEVEL dropped_configs.

    Spec: Provenance records digest and caller timestamp; Dropped configurations recorded
    under allow_missing. dropped_configs lands at the top level because capture_run_metadata
    merges extra via dict.update (metadata.py).
    """
    meta = build_run_metadata(
        docker_image_digest=_DIGEST,
        timestamp=_TS,
        dropped_configs=["s55_f100_p45"],
    )
    assert meta["timestamp"] == _TS
    assert "sha256:" in meta["docker_image"]
    # Top-level key, NOT nested under "extra".
    assert meta["dropped_configs"] == ["s55_f100_p45"]
    assert "extra" not in meta or "dropped_configs" not in meta.get("extra", {})


def test_provenance_complete_build_has_empty_dropped():
    """A complete build records dropped_configs == []."""
    meta = build_run_metadata(
        docker_image_digest=_DIGEST, timestamp=_TS, dropped_configs=[]
    )
    assert meta["dropped_configs"] == []


def test_provenance_mutable_tag_rejected():
    """A mutable tag (no sha256 digest) raises. Spec: Mutable tag rejected."""
    with pytest.raises(ValueError):
        build_run_metadata(
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=_TS,
            dropped_configs=[],
        )


# ---------------------------------------------------------------------------
# Committed units contract (D10/option b — the only committed dataset artifact)
# ---------------------------------------------------------------------------


def test_committed_units_contract_matches_module():
    """The committed dataset.units.json equals the module contract and validates."""
    mapping = read_units_sidecar(COMMITTED_UNITS)
    assert mapping == _DATASET_UNITS
    assert set(mapping) == set(_MEASURED)
