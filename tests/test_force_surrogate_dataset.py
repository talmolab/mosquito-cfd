"""Tests for force_surrogate.dataset (TDD).

Cluster-free (roadmap CC-2): every test runs against the committed
``tests/fixtures/synthetic_ib_particle.csv`` plus a manifest — either the committed
``examples/prelim_sweep/sweep_manifest.json`` (corpus-shaped checks) or a small synthetic
manifest the test writes into ``tmp_path`` (validated-point / boundary checks, since no
committed config is at the validated stroke of 70 deg). No RunAI, GPU, or plotfiles.
"""

import json
import re
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
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, RHO, SPAN
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


# The committed fixture CSVs record the IB particle origin (4, 2, 4) in their X,Y,Z columns.
FIXTURE_ORIGIN = (4.0, 2.0, 4.0)


def _write_deck(
    path: Path,
    *,
    hinge: tuple[float, float, float] = FIXTURE_ORIGIN,
    particle: tuple[float, float, float] = FIXTURE_ORIGIN,
) -> Path:
    """Write a minimal IAMReX deck carrying only the keys extraction reads.

    The default hinge coincides with the fixture CSV's particle origin, so the moment shift is
    zero and the pre-existing ``CF_m* == M*/m_ref`` relationships hold (spec: the degenerate
    case of "Coefficients use the single-source per-config normalization").
    """
    lines = [f"particle_inputs.{a} = {v}" for a, v in zip("xyz", particle, strict=True)]
    lines += [
        f"particle_inputs.hinge_{a} = {v}" for a, v in zip("xyz", hinge, strict=True)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_manifest(
    path: Path,
    configs: list[dict],
    *,
    hinges: dict[str, tuple[float, float, float]] | None = None,
) -> Path:
    """Write a minimal sweep manifest (only the keys build_dataset reads), plus decks.

    Each config lacking an ``input_file`` gets one pointing at a minimal deck written beside
    the manifest (hinge from ``hinges[name]``, else the zero-shift default). A config that
    already carries ``input_file`` -- including ``None`` -- is written verbatim, so the
    missing-deck error paths stay reachable.
    """
    hinges = hinges or {}
    written = []
    for config in configs:
        if "input_file" not in config:
            rel = f"inputs/deck_{config.get('name', 'unnamed')}"
            _write_deck(
                path.parent / rel, hinge=hinges.get(config.get("name"), FIXTURE_ORIGIN)
            )
            config = {**config, "input_file": rel}
        written.append(config)
    path.write_text(json.dumps({"configs": written}), encoding="utf-8")
    return path


def _validated_point_config() -> dict:
    """A synthetic single config at the validated point (phi=70, f*=1.0).

    No committed-corpus config is at phi=70, so the f_ref ~ 200.27 anchor and the
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
    df, dropped, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
    assert dropped == []
    assert len(df) == n_configs * len(FIXTURE_TIME)


def test_columns_are_documented_schema():
    """Columns are exactly the 22-column schema. Spec: Columns are the documented schema."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    df, _, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
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
    df, _, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
    # The committed manifest has both train and holdout configs.
    by_name = {c["name"]: c["split"] for c in manifest["configs"]}
    for name, group in df.groupby("config_name"):
        assert set(group["split"]) == {by_name[name]}
    assert set(df["split"]) == {"train", "holdout"}


def test_complete_build_reports_no_drops():
    """A complete build returns dropped == []. Spec: Complete build reports no drops."""
    manifest = json.loads(COMMITTED_MANIFEST.read_text(encoding="utf-8"))
    csv_paths = {c["name"]: FIXTURE for c in manifest["configs"]}
    _, dropped, _ = build_dataset(COMMITTED_MANIFEST, csv_paths)
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
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})

    f_ref = compute_force_reference(
        f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).f_ref
    m_ref = compute_moment_reference(
        f_star=1.0, phi_amp_deg=70.0, r_gyr=R_GYRATION, span=SPAN, chord=CHORD, rho=RHO
    ).m_ref
    assert f_ref == pytest.approx(200.27, rel=1e-3)
    np.testing.assert_allclose(df["CF_x"].to_numpy(), FIXTURE_FX / f_ref)
    np.testing.assert_allclose(df["CF_mx"].to_numpy(), FIXTURE_MX / m_ref)
    # Not round literals: 50/200.27 ~ 0.2497.
    assert df["CF_x"].to_numpy()[1] == pytest.approx(50.0 / f_ref)


def test_phase_and_wingbeat_tag_every_timestep(tmp_path):
    """phase=(t*f*) mod 1, wingbeat=floor(t*f*); boundary at t*f*=1.0.

    Spec: Phase and wingbeat tag every timestep, no rows dropped. f*=1.0 is required
    so the fixture's time=1.0 row lands exactly on the boundary.
    """
    cfg = _validated_point_config()  # frequency_fstar = 1.0
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert len(df) == len(FIXTURE_TIME)  # no rows dropped
    np.testing.assert_allclose(df["phase"].to_numpy(), [0.0, 0.25, 0.5, 0.75, 0.0])
    np.testing.assert_array_equal(df["wingbeat"].to_numpy(), [0, 0, 0, 0, 1])
    assert ((df["phase"].to_numpy() >= 0.0) & (df["phase"].to_numpy() < 1.0)).all()
    assert df["wingbeat"].dtype == np.int64


def test_name_based_parse_is_robust_to_column_order(tmp_path):
    """A column-reordered CSV yields identical coefficients. Spec: Name-based parse."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df_canonical, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})

    reordered = pd.read_csv(FIXTURE)[list(reversed(IB_PARTICLE_COLUMNS))]
    reordered_path = tmp_path / "reordered.csv"
    reordered.to_csv(reordered_path, index=False)
    df_reordered, _, _ = build_dataset(manifest, {cfg["name"]: reordered_path})

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
    df, dropped, _ = build_dataset(manifest, {cfg["name"]: empty})
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
    df, dropped, _ = build_dataset(
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
    df, dropped, _ = build_dataset(
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
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert len(df) == len(FIXTURE_TIME)


# ---------------------------------------------------------------------------
# write_dataset: units sidecar + parquet round-trip
# ---------------------------------------------------------------------------


def _build_demo(tmp_path):
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
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


# ---------------------------------------------------------------------------
# Robustness: NaN, degenerate kinematics, malformed inputs, real-frequency phase
# ---------------------------------------------------------------------------


def test_nan_force_row_propagates_to_nan_coefficient(tmp_path):
    """A NaN force in a CSV row becomes a NaN coefficient (row kept, not dropped)."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    raw = pd.read_csv(FIXTURE)
    raw.loc[0, "Fx"] = np.nan
    nan_csv = tmp_path / "nan.csv"
    raw.to_csv(nan_csv, index=False)
    df, dropped, _ = build_dataset(manifest, {cfg["name"]: nan_csv})
    assert dropped == []
    assert len(df) == len(FIXTURE_TIME)
    assert np.isnan(df["CF_x"].iloc[0])


def test_degenerate_frequency_raises(tmp_path):
    """A config with frequency_fstar=0 makes f_ref=0 -> ValueError mid-build."""
    cfg = {**_validated_point_config(), "frequency_fstar": 0.0}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ValueError):
        build_dataset(manifest, {cfg["name"]: FIXTURE})


def test_missing_csv_column_raises_naming_config(tmp_path):
    """A CSV missing a required column raises ValueError naming the config + column."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    raw = pd.read_csv(FIXTURE).drop(columns=["Mx"])
    bad = tmp_path / "bad.csv"
    raw.to_csv(bad, index=False)
    with pytest.raises(ValueError, match="Mx"):
        build_dataset(manifest, {cfg["name"]: bad})


def test_manifest_without_configs_key_raises(tmp_path):
    """A manifest with no 'configs' key raises a clear ValueError (not bare KeyError)."""
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"grid": {}}), encoding="utf-8")
    with pytest.raises(ValueError, match="configs"):
        build_dataset(path, {})


def test_configs_not_a_list_raises(tmp_path):
    """A 'configs' that is not a list raises a clear ValueError."""
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"configs": {"name": "x"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="must be a list"):
        build_dataset(path, {})


def test_malformed_manifest_json_raises_clear_file_identified_error(tmp_path):
    """`load_manifest_configs` is the first thing `scripts/check_corpus_acceptance.py`'s CLI
    calls against `--manifest` (before `run_acceptance_gate` even runs) -- a raw, contextless
    `json.JSONDecodeError` here reproduces the exact CLI failure mode review round 1 was
    supposed to eliminate, just via a different, unpatched call path (review round 2 on
    PR #97)."""
    path = tmp_path / "m.json"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match=re.escape(str(path))):
        build_dataset(path, {})


def test_config_not_a_mapping_raises(tmp_path):
    """A config entry that is not a mapping raises a clear ValueError naming its index."""
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"configs": ["not-a-dict"]}), encoding="utf-8")
    with pytest.raises(ValueError, match="config 0 is not a mapping"):
        build_dataset(path, {})


def test_config_missing_required_key_raises_naming_index(tmp_path):
    """A config missing a required key raises ValueError naming the config index."""
    cfg = _validated_point_config()
    del cfg["reynolds"]
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ValueError, match="reynolds"):
        build_dataset(manifest, {cfg["name"]: FIXTURE})


def test_duplicate_config_names_rejected(tmp_path):
    """Two configs with the same name raise (would corrupt the per-name join)."""
    a = _validated_point_config()
    b = {**_validated_point_config(), "index": 1, "split": "holdout"}
    manifest = _write_manifest(tmp_path / "m.json", [a, b])
    with pytest.raises(ValueError, match="duplicate"):
        build_dataset(manifest, {a["name"]: FIXTURE})


def test_per_config_normalization_varies_with_stroke(tmp_path):
    """Same raw Fx but different stroke -> different CF_x (per-config F_ref, not global)."""
    lo = {**_validated_point_config(), "index": 0, "name": "lo", "stroke_amp_deg": 35.0}
    hi = {**_validated_point_config(), "index": 1, "name": "hi", "stroke_amp_deg": 55.0}
    manifest = _write_manifest(tmp_path / "m.json", [lo, hi])
    df, _, _ = build_dataset(manifest, {"lo": FIXTURE, "hi": FIXTURE})
    cf_lo = df[df["config_name"] == "lo"]["CF_x"].to_numpy()
    cf_hi = df[df["config_name"] == "hi"]["CF_x"].to_numpy()
    # Larger stroke -> larger F_ref -> smaller |CF_x| for the same raw force.
    assert np.abs(cf_hi[1]) < np.abs(cf_lo[1])


def test_phase_wingbeat_at_non_unity_frequency(tmp_path):
    """At f*=0.85 (a real sweep value), wingbeat=floor(time*f*) is assigned correctly.

    The fixture time (0..1.0) never crosses a beat boundary at f*=0.85 (boundary at
    time=1/0.85=1.176), so all rows are wingbeat 0 with phase = time*0.85 -- confirming
    the tag is computed from the recorded time, no spurious boundary snapping.
    """
    cfg = {**_validated_point_config(), "frequency_fstar": 0.85}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    np.testing.assert_array_equal(df["wingbeat"].to_numpy(), [0, 0, 0, 0, 0])
    np.testing.assert_allclose(df["phase"].to_numpy(), FIXTURE_TIME * 0.85)


def test_empty_build_has_stable_dtypes(tmp_path):
    """The all-dropped empty frame has the SAME dtypes as a populated frame (schema stable)."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    populated, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    empty, dropped, _ = build_dataset(
        manifest, {cfg["name"]: tmp_path / "absent.csv"}, allow_missing=True
    )
    assert dropped == [cfg["name"]]
    assert len(empty) == 0
    assert empty.dtypes.to_dict() == populated.dtypes.to_dict()


# ---------------------------------------------------------------------------
# init_iter deduplication (#94) -- ns.init_iter=N writes 1+N rows at iStep=0;
# keep the last (converged) one, drop the rest.
# ---------------------------------------------------------------------------

INIT_ITER_FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "forces_init_iter2.csv"
)


def _write_init_iter_csv(path: Path, init_iter: int, n_real_steps: int = 2) -> Path:
    """Write a CSV with ``1 + init_iter`` rows at iStep=0 (first all-zero, rest distinct
    nonzero, ascending magnitude) followed by ``n_real_steps`` further distinct steps.
    """
    header = ",".join(IB_PARTICLE_COLUMNS)
    rows = []

    def row(istep: int, time: float, fx: float) -> str:
        vals = {c: 0 for c in IB_PARTICLE_COLUMNS}
        vals.update(
            iStep=istep,
            time=time,
            Fx=fx,
            Fy=fx / 2,
            Fz=fx / 3,
            Mx=fx / 4,
            My=fx / 5,
            Mz=fx / 6,
        )
        return ",".join(str(vals[c]) for c in IB_PARTICLE_COLUMNS)

    rows.append(row(0, 0.0, 0.0))  # first init iteration: all-zero
    for k in range(1, init_iter + 1):
        rows.append(row(0, 0.0, -10.0 * k))  # later init iterations: nonzero, distinct
    for s in range(1, n_real_steps + 1):
        rows.append(row(s, 0.0005 * s, 50.0 * s))
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def test_dedup_removes_duplicate_init_rows_keeps_last(tmp_path):
    """3 rows at iStep=0 (init_iter=2) collapse to 1: the last, non-zero row is kept."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: INIT_ITER_FIXTURE})
    assert (df["time"] == 0.0).sum() == 1
    first_row = df.iloc[0]
    assert (
        first_row["Fx"] == -15.0
    )  # the third (last) iStep=0 row's value, not 0 or -10
    assert len(df) == 3  # 3 distinct iStep values: 0, 1, 2


def test_dedup_time_strictly_increasing(tmp_path):
    """After dedup, time is strictly increasing (no duplicate timestamps)."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: INIT_ITER_FIXTURE})
    diffs = np.diff(df["time"].to_numpy())
    assert np.all(diffs > 0)


@pytest.mark.parametrize("init_iter", [0, 1, 2, 5])
def test_dedup_parametrized_over_init_iter(tmp_path, init_iter):
    """The extractor is init_iter-value-agnostic: always exactly 1 row per distinct iStep,
    always keeping the LAST duplicate, regardless of how many init iterations were written."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    csv_path = _write_init_iter_csv(tmp_path / f"forces_init{init_iter}.csv", init_iter)
    df, _, _ = build_dataset(manifest, {cfg["name"]: csv_path})
    n_real_steps = 2
    assert len(df) == 1 + n_real_steps  # iStep 0 (deduped to 1) + n_real_steps
    assert (df["time"] == 0.0).sum() == 1
    expected_last_fx = -10.0 * init_iter if init_iter > 0 else 0.0
    assert df.iloc[0]["Fx"] == expected_last_fx


def test_dedup_is_noop_without_duplicates(tmp_path):
    """Regression: extraction of a CSV with no duplicate iStep (the coarse-corpus shape,
    init_iter=None) is byte-for-byte unaffected by the dedup logic."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert len(df) == len(FIXTURE_TIME)
    np.testing.assert_array_equal(df["Fx"].to_numpy(), FIXTURE_FX)
    np.testing.assert_array_equal(df["time"].to_numpy(), FIXTURE_TIME)


def test_dedup_raises_on_non_monotonic_istep(tmp_path):
    """A checkpoint-restart CSV that re-emits a range of already-seen iStep values (not
    just duplicate iStep=0) raises, naming the config -- keep="last" on such a CSV would
    silently discard the earlier, correct rows rather than the restart's stale ones."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    header = ",".join(IB_PARTICLE_COLUMNS)

    def row(istep: int, time: float) -> str:
        vals = {c: 0 for c in IB_PARTICLE_COLUMNS}
        vals.update(iStep=istep, time=time)
        return ",".join(str(vals[c]) for c in IB_PARTICLE_COLUMNS)

    # 0,1,2,3, then restart re-emits 2,3,4 -- non-monotonic iStep sequence.
    rows = [row(s, s * 0.0005) for s in (0, 1, 2, 3, 2, 3, 4)]
    csv_path = tmp_path / "restart.csv"
    csv_path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=cfg["name"]):
        build_dataset(manifest, {cfg["name"]: csv_path})


def test_dedup_raises_when_duplicates_occur_at_nonzero_istep(tmp_path):
    """The only expected duplicate-iStep pattern is `ns.init_iter`'s re-emission at iStep=0.
    A CSV whose iStep never advances past a nonzero value (e.g. a solver-writer bug, not
    init_iter) is vacuously monotonic (diff=0 everywhere) and would otherwise silently collapse
    to a single row under keep='last' with no warning -- review round 1 on PR #97."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    header = ",".join(IB_PARTICLE_COLUMNS)

    def row(istep: int, time: float) -> str:
        vals = {c: 0 for c in IB_PARTICLE_COLUMNS}
        vals.update(iStep=istep, time=time)
        return ",".join(str(vals[c]) for c in IB_PARTICLE_COLUMNS)

    rows = [row(5, t) for t in (0.0, 0.0005, 0.001, 0.0015, 0.002)]
    csv_path = tmp_path / "constant_istep.csv"
    csv_path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=cfg["name"]):
        build_dataset(manifest, {cfg["name"]: csv_path})


def test_missing_istep_column_raises_naming_config(tmp_path):
    """iStep is now a required column (it is the dedup key); its absence raises."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    df = pd.read_csv(FIXTURE).drop(columns=["iStep"])
    csv_path = tmp_path / "no_istep.csv"
    df.to_csv(csv_path, index=False)
    with pytest.raises(ValueError, match=cfg["name"]):
        build_dataset(manifest, {cfg["name"]: csv_path})


# ---------------------------------------------------------------------------
# Moment reference point: hinge-referenced moments (fix-moment-reference-hinge, PR2)
# ---------------------------------------------------------------------------

FIXTURE_RAW = pd.read_csv(FIXTURE)


def _m_ref(cfg: dict) -> float:
    return compute_moment_reference(
        f_star=cfg["frequency_fstar"],
        phi_amp_deg=cfg["stroke_amp_deg"],
        r_gyr=R_GYRATION,
        span=SPAN,
        chord=CHORD,
        rho=RHO,
    ).m_ref


def _csv_with(tmp_path: Path, name: str, **columns) -> Path:
    """The committed fixture with some columns overwritten (scalars broadcast)."""
    raw = FIXTURE_RAW.copy()
    for col, values in columns.items():
        raw[col] = values
    path = tmp_path / name
    raw.to_csv(path, index=False)
    return path


def test_config_without_input_file_raises_naming_config(tmp_path):
    """No manifest `input_file` -> ValueError naming the config, never a bare TypeError/KeyError.

    Spec: A configuration with no locatable deck is rejected.
    """
    cfg = {**_validated_point_config(), "input_file": None}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ValueError, match=rf"{cfg['name']}.*input_file"):
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    no_key = _validated_point_config()
    manifest.write_text(json.dumps({"configs": [no_key]}), encoding="utf-8")
    with pytest.raises(ValueError, match=rf"{no_key['name']}.*input_file"):
        build_dataset(manifest, {no_key["name"]: FIXTURE})


def test_config_whose_deck_does_not_exist_raises_naming_resolved_path(tmp_path):
    """A declared deck absent on disk -> ValueError naming the config and the RESOLVED path
    (resolved against the manifest's own directory, not the CWD).

    Spec: A configuration with no locatable deck is rejected.
    """
    cfg = {**_validated_point_config(), "input_file": "inputs/nope"}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    resolved = tmp_path / "inputs" / "nope"
    with pytest.raises(ValueError, match=cfg["name"]) as excinfo:
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert str(resolved) in str(excinfo.value)


@pytest.mark.parametrize(
    "deck_text",
    [
        # hinge_y absent entirely
        "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_z = 4.0\n",
        # non-finite hinge
        "particle_inputs.hinge_x = 4.0\nparticle_inputs.hinge_y = nan\n"
        "particle_inputs.hinge_z = 4.0\n",
        "particle_inputs.hinge_x = inf\nparticle_inputs.hinge_y = 0.5\n"
        "particle_inputs.hinge_z = 4.0\n",
    ],
    ids=["missing-hinge_y", "nan-hinge_y", "inf-hinge_x"],
)
def test_deck_without_finite_hinge_raises_naming_config_and_deck(tmp_path, deck_text):
    """No silent fallback to the particle origin (that would reinstate particle-origin moments).

    `read_deck_value` names neither config nor deck, so extraction must wrap it.
    Spec: A deck without a declared hinge is rejected.
    """
    deck = tmp_path / "inputs" / "bad_deck"
    deck.parent.mkdir()
    deck.write_text(deck_text, encoding="utf-8")
    cfg = {**_validated_point_config(), "input_file": "inputs/bad_deck"}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ValueError, match=cfg["name"]) as excinfo:
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert str(deck) in str(excinfo.value)


@pytest.mark.parametrize("column", ["X", "Y", "Z"])
def test_csv_without_origin_column_raises_naming_config_and_column(tmp_path, column):
    """X,Y,Z are required: IAMReX writes the moment origin there.

    Spec: A CSV lacking the origin columns is rejected.
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    bad = tmp_path / "no_origin.csv"
    FIXTURE_RAW.drop(columns=[column]).to_csv(bad, index=False)
    with pytest.raises(ValueError, match=rf"{cfg['name']}.*'{column}'"):
        build_dataset(manifest, {cfg["name"]: bad})


@pytest.mark.parametrize("column", ["X", "Y", "Z"])
def test_moving_origin_rejected_under_exact_equality(tmp_path, column):
    """Any variation, however small, is rejected -- no tolerance.

    Spec: A moving moment origin is rejected rather than shifted.
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    moved = FIXTURE_RAW[column].to_numpy(dtype=float).copy()
    moved[-1] = np.nextafter(moved[-1], np.inf)  # one ulp
    csv = _csv_with(tmp_path, "moving.csv", **{column: moved})
    with pytest.raises(ValueError, match=rf"{cfg['name']}.*not constant"):
        build_dataset(manifest, {cfg["name"]: csv})


@pytest.mark.parametrize(
    "values",
    [[4.0, np.nan, 4.0, 4.0, 4.0], [np.nan] * 5, [np.inf] * 5],
    ids=["one-nan", "all-nan", "all-inf"],
)
@pytest.mark.parametrize("column", ["X", "Y", "Z"])
def test_non_finite_origin_rejected(tmp_path, values, column):
    """The hazard is pandas: `Series([4, nan, 4]).max() - .min() == 0` and `.nunique() == 1`
    both PASS a naive constancy check. Finiteness must be asserted explicitly.

    Spec: A NaN moment origin is rejected.
    """
    # Pin the hazard itself, so the test documents why an explicit check is needed.
    s = pd.Series([4.0, np.nan, 4.0])
    assert s.max() - s.min() == 0 and s.nunique() == 1

    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    csv = _csv_with(tmp_path, "nan_origin.csv", **{column: values})
    with pytest.raises(ValueError, match=rf"{cfg['name']}.*finite.*'{column}'"):
        build_dataset(manifest, {cfg["name"]: csv})


def test_header_only_csv_does_not_trip_the_origin_guard(tmp_path):
    """Zero rows -> zero contribution, no error from the constancy check on an empty array,
    and no offset recorded (there is no origin to derive one from).

    Spec: A header-only CSV contributes no rows without tripping the origin guard.
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(
        tmp_path / "m.json", [cfg], hinges={cfg["name"]: (4.0, 0.5, 4.0)}
    )
    empty = tmp_path / "empty.csv"
    empty.write_text(",".join(IB_PARTICLE_COLUMNS) + "\n", encoding="utf-8")
    df, dropped, provenance = build_dataset(manifest, {cfg["name"]: empty})
    assert len(df) == 0 and dropped == []
    assert provenance[cfg["name"]]["origin"] is None
    assert provenance[cfg["name"]]["offset"] is None


def test_shift_applied_with_a_non_committed_offset(tmp_path):
    """End-to-end through build_dataset with an offset that is NOT (0, 1.5, 0), on all three
    axes, so a hardcoded constant or a special-cased axis fails. Expected values are the
    hand-expanded cross product, not a call to the helper under test.

    Spec: Offset is derived, not hardcoded; Parallel-axis shift is applied at extraction.
    """
    cfg = _validated_point_config()
    hinge = (3.5, 0.25, 4.75)
    manifest = _write_manifest(tmp_path / "m.json", [cfg], hinges={cfg["name"]: hinge})
    df, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})

    dx, dy, dz = (o - h for o, h in zip(FIXTURE_ORIGIN, hinge, strict=True))
    assert (dx, dy, dz) == (0.5, 1.75, -0.75)
    fx, fy, fz = (FIXTURE_RAW[c].to_numpy(dtype=float) for c in ("Fx", "Fy", "Fz"))
    mx, my, mz = (FIXTURE_RAW[c].to_numpy(dtype=float) for c in ("Mx", "My", "Mz"))
    m_ref = _m_ref(cfg)
    np.testing.assert_allclose(
        df["CF_mx"], (mx + dy * fz - dz * fy) / m_ref, rtol=1e-12
    )
    np.testing.assert_allclose(
        df["CF_my"], (my + dz * fx - dx * fz) / m_ref, rtol=1e-12
    )
    np.testing.assert_allclose(
        df["CF_mz"], (mz + dx * fy - dy * fx) / m_ref, rtol=1e-12
    )
    # Non-vacuous: the fixture's forces make the shift visible on every moment axis.
    assert not np.allclose(df["CF_mx"], mx / m_ref)
    assert not np.allclose(df["CF_my"], my / m_ref)
    assert not np.allclose(df["CF_mz"], mz / m_ref)
    assert provenance[cfg["name"]]["offset"] == [0.5, 1.75, -0.75]


def test_committed_geometry_shift_is_spanwise_and_leaves_cf_my_invariant(tmp_path):
    """The committed geometry: origin (4,2,4), hinge (4,0.5,4) -> offset (0,1.5,0).
    CF_mx/CF_mz move by +a*Fz / -a*Fx (this clause pins cross-product ORDER); CF_my compares
    equal to My/m_ref (this does NOT pin order: F x d also has a zero y-term).

    Spec: A spanwise shift leaves the M_y component invariant.
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(
        tmp_path / "m.json", [cfg], hinges={cfg["name"]: (4.0, 0.5, 4.0)}
    )
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    a = 1.5
    fx, fz = FIXTURE_RAW["Fx"].to_numpy(float), FIXTURE_RAW["Fz"].to_numpy(float)
    mx, my, mz = (FIXTURE_RAW[c].to_numpy(float) for c in ("Mx", "My", "Mz"))
    m_ref = _m_ref(cfg)
    np.testing.assert_allclose(df["CF_mx"], (mx + a * fz) / m_ref, rtol=1e-12)
    np.testing.assert_allclose(df["CF_mz"], (mz - a * fx) / m_ref, rtol=1e-12)
    assert (df["CF_my"].to_numpy() == my / m_ref).all()


def test_offset_is_derived_per_configuration(tmp_path):
    """Two configs, identical CSVs, decks differing in hinge_y (the component that enters
    CF_mx) -> CF_mx differs by exactly (delta a)*Fz/m_ref. A derive-once-and-reuse bug emits
    identical columns. (Varying only hinge_x would leave CF_mx identical -- not a test.)

    Spec: The offset is derived independently for each configuration.
    """
    a_cfg = {**_validated_point_config(), "name": "a", "index": 0}
    b_cfg = {**_validated_point_config(), "name": "b", "index": 1}
    manifest = _write_manifest(
        tmp_path / "m.json",
        [a_cfg, b_cfg],
        hinges={"a": (4.0, 0.5, 4.0), "b": (4.0, 1.0, 4.0)},
    )
    df, _, provenance = build_dataset(manifest, {"a": FIXTURE, "b": FIXTURE})
    cf_a = df.loc[df["config_name"] == "a", "CF_mx"].to_numpy()
    cf_b = df.loc[df["config_name"] == "b", "CF_mx"].to_numpy()
    fz = FIXTURE_RAW["Fz"].to_numpy(float)
    np.testing.assert_allclose(
        cf_a - cf_b, (1.5 - 1.0) * fz / _m_ref(a_cfg), atol=1e-15
    )
    assert not np.array_equal(cf_a, cf_b)
    assert provenance["a"]["offset"] == [0.0, 1.5, 0.0]
    assert provenance["b"]["offset"] == [0.0, 1.0, 0.0]


def test_raw_moments_stay_bitwise_equal_to_csv(tmp_path):
    """Only derived CF_m* move; raw Mx/My/Mz (and Fx..Fz) are IAMReX's as-written values.

    Spec: Parallel-axis shift is applied at extraction ("raw ... bitwise equal").
    """
    cfg = _validated_point_config()
    manifest = _write_manifest(
        tmp_path / "m.json", [cfg], hinges={cfg["name"]: (3.5, 0.25, 4.75)}
    )
    df, _, _ = build_dataset(manifest, {cfg["name"]: FIXTURE})
    for col in ("Fx", "Fy", "Fz", "Mx", "My", "Mz"):
        np.testing.assert_array_equal(
            df[col].to_numpy(), FIXTURE_RAW[col].to_numpy(float)
        )


def test_build_provenance_records_origin_hinge_deck_and_csv_hashes(tmp_path):
    """The per-config record travels out of build_dataset with the data (a second derivation
    in the driver could drift from the applied one). Hashes are of the exact bytes consumed.

    Spec: Moment reference point travels with the corpus.
    """
    import hashlib

    cfg = _validated_point_config()
    manifest = _write_manifest(
        tmp_path / "m.json", [cfg], hinges={cfg["name"]: (4.0, 0.5, 4.0)}
    )
    _, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})
    deck = tmp_path / "inputs" / f"deck_{cfg['name']}"
    assert provenance[cfg["name"]] == {
        "origin": [4.0, 2.0, 4.0],
        "hinge": [4.0, 0.5, 4.0],
        "offset": [0.0, 1.5, 0.0],
        "deck": f"inputs/deck_{cfg['name']}",
        "deck_sha256": hashlib.sha256(deck.read_bytes()).hexdigest(),
        "deck_sha256_verified_against": None,
        "csv_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
    }


def test_dropped_config_has_no_provenance_record(tmp_path):
    """A config skipped under allow_missing consumed no CSV, so it carries no record."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    _, dropped, provenance = build_dataset(
        manifest, {cfg["name"]: tmp_path / "absent.csv"}, allow_missing=True
    )
    assert dropped == [cfg["name"]] and provenance == {}


def _write_config_run_metadata(manifest: Path, name: str, deck_sha256: str) -> Path:
    path = manifest.parent / f"run_metadata_{name}.json"
    path.write_text(
        json.dumps({"config": name, "deck_sha256": deck_sha256}), encoding="utf-8"
    )
    return path


def test_deck_is_reconciled_against_the_runs_recorded_deck_sha256(tmp_path):
    """The deck is mutable; the CSV is not. When the run recorded the hash of the deck it ran
    (every fine per-config run_metadata_<name>.json does), a working-tree deck edited since
    fails loudly instead of shifting about a hinge the solver never used.

    Spec: The moment origin offset is derived per configuration and validated (design D2).
    """
    import hashlib

    cfg = _validated_point_config()
    manifest = _write_manifest(
        tmp_path / "m.json", [cfg], hinges={cfg["name"]: (4.0, 0.5, 4.0)}
    )
    deck = tmp_path / "inputs" / f"deck_{cfg['name']}"
    good = hashlib.sha256(deck.read_bytes()).hexdigest()

    meta = _write_config_run_metadata(manifest, cfg["name"], good)
    _, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert provenance[cfg["name"]]["deck_sha256_verified_against"] == meta.name

    _write_config_run_metadata(manifest, cfg["name"], "0" * 64)
    with pytest.raises(ValueError, match=rf"{cfg['name']}.*deck_sha256") as excinfo:
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert str(deck) in str(excinfo.value)
    # Both hashes, so the operator can tell which side moved.
    assert good in str(excinfo.value) and "0" * 64 in str(excinfo.value)


def test_run_metadata_without_deck_sha256_is_recorded_as_unverified(tmp_path):
    """A per-config metadata file with no deck_sha256 is no anchor: extraction proceeds and
    records that the deck was NOT verified (the coarse corpus's known limitation), rather
    than claiming a verification that never happened."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    (manifest.parent / f"run_metadata_{cfg['name']}.json").write_text(
        "{}", encoding="utf-8"
    )
    _, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert provenance[cfg["name"]]["deck_sha256_verified_against"] is None


def test_build_run_metadata_passes_extra_through_top_level():
    """build_run_metadata's `extra` was hardcoded to dropped_configs; the frame record needs
    a channel. Collisions with dropped_configs or base provenance keys are rejected rather
    than silently overwriting them."""
    meta = build_run_metadata(
        docker_image_digest=_DIGEST,
        timestamp=_TS,
        dropped_configs=[],
        extra={"moment_reference": {"point": "wing_hinge"}},
    )
    assert meta["moment_reference"] == {"point": "wing_hinge"}
    assert meta["dropped_configs"] == []
    for key in ("dropped_configs", "docker_image", "git", "timestamp"):
        with pytest.raises(ValueError, match=key):
            build_run_metadata(
                docker_image_digest=_DIGEST,
                timestamp=_TS,
                dropped_configs=[],
                extra={key: "clobber"},
            )


# ---------------------------------------------------------------------------
# Review round 1 on PR #118: every per-config input defect is a ConfigExtractionError that
# names the config, so the acceptance gate reports it instead of tracebacking.
# ---------------------------------------------------------------------------


def test_non_utf8_deck_is_a_named_extraction_error(tmp_path):
    from mosquito_cfd.force_surrogate import ConfigExtractionError

    deck = tmp_path / "inputs" / "latin1_deck"
    deck.parent.mkdir()
    deck.write_bytes(b"# caf\xe9\nparticle_inputs.hinge_x = 4.0\n")
    cfg = {**_validated_point_config(), "input_file": "inputs/latin1_deck"}
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    with pytest.raises(ConfigExtractionError, match=cfg["name"]) as excinfo:
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert str(deck) in str(excinfo.value)


@pytest.mark.parametrize("payload", ["[]", "null", '"text"', "3"])
def test_non_object_run_metadata_is_a_named_extraction_error(tmp_path, payload):
    """A per-config run_metadata that parses to a non-object raised a bare AttributeError."""
    from mosquito_cfd.force_surrogate import ConfigExtractionError

    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    meta = manifest.parent / f"run_metadata_{cfg['name']}.json"
    meta.write_text(payload, encoding="utf-8")
    with pytest.raises(ConfigExtractionError, match=cfg["name"]) as excinfo:
        build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert str(meta) in str(excinfo.value)


@pytest.mark.parametrize("column", ["X", "Y", "Z"])
def test_non_numeric_origin_is_a_named_extraction_error(tmp_path, column):
    from mosquito_cfd.force_surrogate import ConfigExtractionError

    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    csv = _csv_with(tmp_path, "text_origin.csv", **{column: "abc"})
    with pytest.raises(ConfigExtractionError, match=rf"{cfg['name']}.*'{column}'"):
        build_dataset(manifest, {cfg["name"]: csv})


def test_recorded_deck_sha256_matches_case_insensitively(tmp_path):
    """Uppercase hex is the same hash; a non-string record is an error, not a mismatch."""
    import hashlib

    from mosquito_cfd.force_surrogate import ConfigExtractionError

    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    deck = tmp_path / "inputs" / f"deck_{cfg['name']}"
    good = hashlib.sha256(deck.read_bytes()).hexdigest()

    _write_config_run_metadata(manifest, cfg["name"], good.upper())
    _, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert provenance[cfg["name"]]["deck_sha256_verified_against"] is not None

    (manifest.parent / f"run_metadata_{cfg['name']}.json").write_text(
        json.dumps({"deck_sha256": 12345}), encoding="utf-8"
    )
    with pytest.raises(ConfigExtractionError, match="deck_sha256"):
        build_dataset(manifest, {cfg["name"]: FIXTURE})


def test_explicit_run_metadata_paths_are_used_for_the_deck_check(tmp_path):
    """The acceptance gate takes an explicit run_metadata_paths mapping. The deck check must
    use the same files, not assume they sit beside the manifest, or a mismatch elsewhere is
    silently recorded as "unverified"."""
    cfg = _validated_point_config()
    manifest = _write_manifest(tmp_path / "m.json", [cfg])
    elsewhere = tmp_path / "metadata_elsewhere"
    elsewhere.mkdir()
    stale = elsewhere / f"run_metadata_{cfg['name']}.json"
    stale.write_text(json.dumps({"deck_sha256": "0" * 64}), encoding="utf-8")

    # Beside-the-manifest convention: nothing there, so no anchor.
    _, _, provenance = build_dataset(manifest, {cfg["name"]: FIXTURE})
    assert provenance[cfg["name"]]["deck_sha256_verified_against"] is None

    # Explicit mapping: the stale hash is found and rejected.
    with pytest.raises(ValueError, match="deck_sha256"):
        build_dataset(
            manifest, {cfg["name"]: FIXTURE}, run_metadata_paths={cfg["name"]: stale}
        )
