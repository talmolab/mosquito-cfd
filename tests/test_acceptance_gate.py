"""Tests for force_surrogate.acceptance_gate (TDD, design.md D6).

Cluster-free: builds a minimal 2-config synthetic corpus tree (manifest, decks, force CSVs,
per-config metadata, provenance) per test, precisely controlling one failure mode at a time.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from mosquito_cfd.force_surrogate.acceptance_gate import (
    record_check_result,
    run_acceptance_gate,
)

_IB_HEADER = "iStep,time,X,Y,Z,Vx,Vy,Vz,Rx,Ry,Rz,Fx,Fy,Fz,Mx,My,Mz,Fcpx,Fcpy,Fcpz,Tcpx,Tcpy,Tcpz,SumUx,SumUy,SumUz,SumTx,SumTy,SumTz"


def _write_csv(path: Path, *, n_rows: int, cf_x_pattern: str) -> None:
    """Write a force CSV whose Fx values give a controlled settled-beat (wingbeat>=1) CF_x
    pattern -- the pattern applies specifically to the wingbeat>=1 subset, not the whole series,
    since that is what the symmetry check actually measures.

    Config kinematics are fixed (stroke=35, f*=0.85, pitch=30) across all tests, so f_ref is
    constant and CF_x is proportional to Fx.
    """
    times = [(i + 1) * (2.5 / n_rows) for i in range(n_rows)]
    wingbeats = [int(t * 0.85) for t in times]
    settled_idx = [i for i, wb in enumerate(wingbeats) if wb >= 1]
    n_settled = len(settled_idx)
    if cf_x_pattern == "symmetric":
        settled_fx = np.linspace(-100.0, 100.0, n_settled)  # symmetric around 0
    elif cf_x_pattern == "truncated":
        settled_fx = np.linspace(
            50.0, 100.0, n_settled
        )  # all positive -> large mean/peak
    else:
        raise ValueError(cf_x_pattern)

    fx = np.zeros(n_rows)
    fx[settled_idx] = settled_fx
    lines = [_IB_HEADER]
    for i in range(n_rows):
        row = [0] * 29
        row[0] = i
        row[1] = times[i]
        row[11] = fx[i]
        lines.append(",".join(str(v) for v in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_corpus(
    tmp_path: Path,
    *,
    n_rows: int = 10,
    cf_x_pattern: str = "symmetric",
    interior_dt_below_nominal: bool = False,
    field_capture: bool = False,
    cc_f1: dict
    | None = "unset",  # "unset" sentinel distinguishes from an explicit None
) -> dict:
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    config_name = "s35_f085_p30"
    manifest = {
        "configs": [
            {
                "index": 0,
                "name": config_name,
                "stroke_amp_deg": 35.0,
                "frequency_fstar": 0.85,
                "pitch_amp_deg": 30.0,
                "reynolds": 42.0,
                "split": "train",
                "max_step": n_rows,
            }
        ]
    }
    manifest_path = corpus_dir / "sweep_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    csv_path = corpus_dir / f"forces_{config_name}.csv"
    _write_csv(csv_path, n_rows=n_rows, cf_x_pattern=cf_x_pattern)

    metadata_path = corpus_dir / f"run_metadata_{config_name}.json"
    metadata_path.write_text(
        json.dumps(
            {
                "interior_dt_below_nominal": interior_dt_below_nominal,
                "realized_dt": {"min": 3e-4 if interior_dt_below_nominal else 5e-4},
            }
        ),
        encoding="utf-8",
    )

    provenance: dict = {}
    if field_capture:
        provenance["field_capture"] = {"plot_int": 100, "init_iter": 2}
    if cc_f1 != "unset":
        provenance["cluster_run"] = {"cc_f1": cc_f1}
    provenance_path = corpus_dir / "sweep_provenance.json"
    provenance_path.write_text(json.dumps(provenance), encoding="utf-8")

    return {
        "manifest_path": manifest_path,
        "csv_paths": {config_name: csv_path},
        "run_metadata_paths": {config_name: metadata_path},
        "provenance_path": provenance_path,
        "config_name": config_name,
    }


def test_healthy_corpus_passes(tmp_path):
    c = _make_corpus(tmp_path)
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert result.passed, result.failures


def test_cfl_limited_config_fails(tmp_path):
    c = _make_corpus(tmp_path, interior_dt_below_nominal=True)
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("CFL-limited" in f for f in result.failures)


def test_row_count_mismatch_fails(tmp_path):
    """Manifest claims max_step=10 but the CSV only has 8 rows -- recomputed, not trusted."""
    c = _make_corpus(tmp_path, n_rows=8)
    manifest = json.loads(c["manifest_path"].read_text(encoding="utf-8"))
    manifest["configs"][0]["max_step"] = 10
    c["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")

    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("row count" in f for f in result.failures)


def test_truncated_config_fails_the_symmetry_check(tmp_path):
    c = _make_corpus(tmp_path, cf_x_pattern="truncated")
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("symmetry ratio" in f for f in result.failures)


def test_missing_cc_f1_result_fails_a_field_capture_corpus(tmp_path):
    c = _make_corpus(tmp_path, field_capture=True, cc_f1="unset")
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("CC-F1" in f for f in result.failures)


def test_present_passing_cc_f1_result_does_not_fail_the_gate(tmp_path):
    c = _make_corpus(
        tmp_path,
        field_capture=True,
        cc_f1={
            "plotfile": "plt00100",
            "x_velocity_min": -2.3,
            "x_velocity_max": 10.3,
            "verdict": "pass",
        },
    )
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert result.passed, result.failures


def test_partial_mid_sweep_cc_f1_does_not_satisfy_the_gate(tmp_path):
    """A cluster_run record whose only evidence is a partial mid-sweep check does not satisfy
    the post-run gate."""
    c = _make_corpus(
        tmp_path,
        field_capture=True,
        cc_f1={"plotfile": "plt00100", "verdict": "pass", "partial": True},
    )
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("partial" in f for f in result.failures)


def test_non_field_capture_corpus_does_not_require_cc_f1(tmp_path):
    c = _make_corpus(tmp_path, field_capture=False, cc_f1="unset")
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert result.passed, result.failures


def test_gate_recomputes_row_count_rather_than_trusting_metadata(tmp_path):
    """The self-certification guard: even if run_metadata's own claims look fine, the gate's row
    count comes from re-reading the raw CSV, not from any metadata field."""
    c = _make_corpus(tmp_path, n_rows=8)
    manifest = json.loads(c["manifest_path"].read_text(encoding="utf-8"))
    manifest["configs"][0]["max_step"] = 10
    c["manifest_path"].write_text(json.dumps(manifest), encoding="utf-8")
    # Hand-edit the metadata to claim everything is fine -- the gate must not be fooled, because
    # it never reads a row count FROM the metadata at all.
    metadata = json.loads(
        c["run_metadata_paths"]["s35_f085_p30"].read_text(encoding="utf-8")
    )
    metadata["interior_dt_below_nominal"] = False
    metadata["timing"] = {"timesteps": 10}  # a lie
    c["run_metadata_paths"]["s35_f085_p30"].write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed
    assert any("row count" in f for f in result.failures)


def test_missing_run_metadata_file_fails(tmp_path):
    c = _make_corpus(tmp_path)
    c["run_metadata_paths"]["s35_f085_p30"].unlink()
    result = run_acceptance_gate(
        manifest_path=c["manifest_path"],
        csv_paths=c["csv_paths"],
        run_metadata_paths=c["run_metadata_paths"],
        provenance_path=c["provenance_path"],
    )
    assert not result.passed


# ---------------------------------------------------------------------------
# record_check_result
# ---------------------------------------------------------------------------


def test_record_check_result_persists_cc_f1(tmp_path):
    provenance_path = tmp_path / "sweep_provenance.json"
    provenance_path.write_text(
        json.dumps({"field_capture": {"plot_int": 100}}), encoding="utf-8"
    )

    record_check_result(
        provenance_path,
        "cc_f1",
        plotfile="plt00100",
        x_velocity_min=-2.3,
        x_velocity_max=10.3,
        verdict="pass",
    )

    written = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert written["cluster_run"]["cc_f1"]["verdict"] == "pass"
    assert written["cluster_run"]["cc_f1"]["x_velocity_max"] == 10.3
    assert written["field_capture"]["plot_int"] == 100  # existing content preserved


def test_record_check_result_records_parallelism_and_deadline(tmp_path):
    provenance_path = tmp_path / "sweep_provenance.json"
    provenance_path.write_text("{}", encoding="utf-8")

    record_check_result(
        provenance_path, "orchestration", parallelism=3, active_deadline_seconds=98280
    )

    written = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert written["cluster_run"]["orchestration"]["parallelism"] == 3
    assert written["cluster_run"]["orchestration"]["active_deadline_seconds"] == 98280


def test_record_check_result_accumulates_multiple_checks(tmp_path):
    provenance_path = tmp_path / "sweep_provenance.json"
    provenance_path.write_text("{}", encoding="utf-8")

    record_check_result(provenance_path, "cc_f1", verdict="pass")
    record_check_result(provenance_path, "orchestration", parallelism=3)

    written = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert "cc_f1" in written["cluster_run"]
    assert "orchestration" in written["cluster_run"]
