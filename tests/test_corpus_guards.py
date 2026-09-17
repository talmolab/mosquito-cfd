"""Tests for force_surrogate.corpus_guards (issue #20, TDD).

Cluster-free: every test runs against either a synthetic tmp_path corpus (for each failure
mode, precisely controlled) or the real committed `examples/prelim_sweep` corpus (confirming the
guards pass against real data, not just synthetic fixtures built to satisfy them).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import corpus_guards as cg
from mosquito_cfd.force_surrogate.sidecar import write_units_sidecar

_DATASET_UNITS = {
    "time": "dimensionless",
    "phase": "dimensionless",
    "stroke_amp_deg": "deg",
    "frequency_fstar": "dimensionless (f*)",
    "pitch_amp_deg": "deg",
    "reynolds": "dimensionless",
    "Fx": "dimensionless",
    "Fy": "dimensionless",
    "Fz": "dimensionless",
    "Mx": "dimensionless",
    "My": "dimensionless",
    "Mz": "dimensionless",
    "CF_x": "dimensionless",
    "CF_y": "dimensionless",
    "CF_z": "dimensionless",
    "CF_mx": "dimensionless",
    "CF_my": "dimensionless",
    "CF_mz": "dimensionless",
}


def _write_deck(path: Path, max_step: int) -> None:
    path.write_text(f"max_step = {max_step}\nstop_time = 1.0\n", encoding="utf-8")


def _make_config(name: str, max_step: int, split: str = "train") -> dict:
    return {
        "name": name,
        "input_file": f"inputs/inputs.3d.{name}",
        "max_step": max_step,
        "stroke_amp_deg": 35.0,
        "frequency_fstar": 0.85,
        "pitch_amp_deg": 30.0,
        "reynolds": 42.0,
        "split": split,
    }


def _make_row(config_name, i, n, *, wingbeat, cf_x) -> dict:
    return {
        "config_name": config_name,
        "index": 0,
        "time": (i + 1) * 0.01,
        "phase": 0.5,
        "wingbeat": wingbeat,
        "stroke_amp_deg": 35.0,
        "frequency_fstar": 0.85,
        "pitch_amp_deg": 30.0,
        "reynolds": 42.0,
        "split": "train",
        "Fx": cf_x * 10,
        "Fy": 0.0,
        "Fz": 0.0,
        "Mx": 0.0,
        "My": 0.0,
        "Mz": 0.0,
        "CF_x": cf_x,
        "CF_y": 0.0,
        "CF_z": 0.0,
        "CF_mx": 0.0,
        "CF_my": 0.0,
        "CF_mz": 0.0,
    }


def _build_synthetic_corpus(
    tmp_path: Path,
    *,
    name: str = "synthetic",
    n_rows: int = 10,
    deck_max_step: int | None = None,
    manifest_max_step: int = 10,
    holdout_names: list[str] | None = None,
    duplicate_time: bool = False,
    inject_nan: bool = False,
    omit_units_key: bool = False,
    omit_per_config_metadata: bool = False,
    cf_x_pattern: str = "symmetric",  # "symmetric" | "truncated" | "spike"
) -> cg.CorpusEntry:
    """Build a minimal, precisely-controllable synthetic corpus for one failure mode at a time."""
    corpus_dir = tmp_path / name
    (corpus_dir / "inputs").mkdir(parents=True)
    config_name = "s35_f085_p30"
    _write_deck(
        corpus_dir / "inputs" / f"inputs.3d.{config_name}",
        deck_max_step if deck_max_step is not None else manifest_max_step,
    )
    manifest = {
        "configs": [_make_config(config_name, manifest_max_step)],
        "holdout": {"config_names": holdout_names or []},
    }
    (corpus_dir / "sweep_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    rows = []
    if cf_x_pattern == "symmetric":
        # wingbeat 1: symmetric around 0 -> ratio ~0
        cf_values = np.linspace(-1.0, 1.0, n_rows)
    elif cf_x_pattern == "truncated":
        # all positive, large mean relative to peak -> fails the ratio check
        cf_values = np.linspace(0.5, 1.0, n_rows)
    elif cf_x_pattern == "spike":
        cf_values = np.full(n_rows, 6.0)  # exceeds the tripwire
    else:
        raise ValueError(cf_x_pattern)

    for i in range(n_rows):
        rows.append(_make_row(config_name, i, n_rows, wingbeat=1, cf_x=cf_values[i]))
    if duplicate_time:
        rows.append(dict(rows[0]))  # duplicate the first row's time -> non-monotonic
    if inject_nan:
        rows[0]["Fx"] = float("nan")

    df = pd.DataFrame(rows)
    df.to_parquet(corpus_dir / "dataset.parquet", index=False)

    units = dict(_DATASET_UNITS)
    if omit_units_key:
        del units["CF_x"]
    write_units_sidecar(corpus_dir / "dataset.units.json", units)

    if not omit_per_config_metadata:
        (corpus_dir / f"run_metadata_{config_name}.json").write_text(
            "{}", encoding="utf-8"
        )

    return cg.CorpusEntry(
        name=name,
        path=corpus_dir,
        has_parquet=True,
        has_per_config_metadata=not omit_per_config_metadata,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_is_non_empty_and_schema_fields_honored():
    assert len(cg.CORPUS_REGISTRY) > 0
    for entry in cg.CORPUS_REGISTRY:
        assert isinstance(entry.has_parquet, bool)
        assert isinstance(entry.has_per_config_metadata, bool)


def test_missing_expected_parquet_fails_loudly(tmp_path):
    """A corpus registered has_parquet=True but lacking one fails loudly, not silently."""
    corpus_dir = tmp_path / "missing_parquet"
    corpus_dir.mkdir()
    entry = cg.CorpusEntry(
        name="missing_parquet",
        path=corpus_dir,
        has_parquet=True,
        has_per_config_metadata=False,
    )
    failures = cg.check_parquet_exists_if_registered(entry)
    assert failures
    assert "missing_parquet" in failures[0]


def test_registered_absent_parquet_is_not_a_failure(tmp_path):
    """A corpus correctly registered has_parquet=False (not yet built) is not an error."""
    corpus_dir = tmp_path / "not_yet_built"
    corpus_dir.mkdir()
    entry = cg.CorpusEntry(
        name="not_yet_built",
        path=corpus_dir,
        has_parquet=False,
        has_per_config_metadata=False,
    )
    assert cg.check_parquet_exists_if_registered(entry) == []


# ---------------------------------------------------------------------------
# Manifest/deck tier (applies regardless of parquet)
# ---------------------------------------------------------------------------


def test_deck_max_step_matches_manifest(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, deck_max_step=10, manifest_max_step=10)
    assert cg.check_deck_matches_manifest_max_step(entry) == []


def test_deck_max_step_mismatch_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, deck_max_step=999, manifest_max_step=10)
    failures = cg.check_deck_matches_manifest_max_step(entry)
    assert failures
    assert "999" in failures[0] and "10" in failures[0]


def test_holdout_matches_manifest(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, holdout_names=[])
    assert cg.check_holdout_matches_manifest(entry) == []


def test_holdout_mismatch_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, holdout_names=["s35_f085_p30"])
    failures = cg.check_holdout_matches_manifest(entry)
    assert failures


# ---------------------------------------------------------------------------
# Parquet tier
# ---------------------------------------------------------------------------


def test_row_count_matches_manifest(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, n_rows=10, manifest_max_step=10)
    assert cg.check_parquet_row_counts(entry) == []


def test_row_count_mismatch_fails(tmp_path):
    """This is the #94-class defect: extra duplicate rows inflate the count past max_step."""
    entry = _build_synthetic_corpus(tmp_path, n_rows=12, manifest_max_step=10)
    failures = cg.check_parquet_row_counts(entry)
    assert failures
    assert "12" in failures[0] and "10" in failures[0]


def test_time_strictly_increasing(tmp_path):
    entry = _build_synthetic_corpus(tmp_path)
    assert cg.check_time_strictly_increasing(entry) == []


def test_duplicate_time_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, duplicate_time=True)
    failures = cg.check_time_strictly_increasing(entry)
    assert failures


def test_no_nan_or_inf(tmp_path):
    entry = _build_synthetic_corpus(tmp_path)
    assert cg.check_no_nan_or_inf(entry) == []


def test_nan_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, inject_nan=True)
    failures = cg.check_no_nan_or_inf(entry)
    assert failures


def test_units_match_parquet(tmp_path):
    entry = _build_synthetic_corpus(tmp_path)
    assert cg.check_units_match_parquet(entry) == []


def test_units_drift_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, omit_units_key=True)
    failures = cg.check_units_match_parquet(entry)
    assert failures


def test_per_config_metadata_present(tmp_path):
    entry = _build_synthetic_corpus(tmp_path)
    assert cg.check_per_config_metadata_present(entry) == []


def test_per_config_metadata_missing_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, omit_per_config_metadata=True)
    entry = cg.CorpusEntry(
        name=entry.name, path=entry.path, has_parquet=True, has_per_config_metadata=True
    )
    failures = cg.check_per_config_metadata_present(entry)
    assert failures


def test_per_config_metadata_guard_scoped_to_corpora_that_declare_it(tmp_path):
    """The coarse corpus (has_per_config_metadata=False) is never flagged for lacking
    per-config files -- it only ever had a dataset-build run_metadata.json."""
    entry = _build_synthetic_corpus(tmp_path, omit_per_config_metadata=True)
    entry = cg.CorpusEntry(
        name=entry.name,
        path=entry.path,
        has_parquet=True,
        has_per_config_metadata=False,
    )
    assert cg.check_per_config_metadata_present(entry) == []


# ---------------------------------------------------------------------------
# Physical invariant: normalized cycle-symmetry ratio
# ---------------------------------------------------------------------------


def test_symmetric_config_passes_the_ratio_check(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="symmetric")
    assert cg.check_symmetry_invariant(entry) == []


def test_truncated_config_fails_the_ratio_check(tmp_path):
    """The scenario this whole invariant exists for: a truncated settled beat is not symmetric."""
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="truncated")
    failures = cg.check_symmetry_invariant(entry)
    assert failures
    assert "s35_f085_p30" in failures[0]


def test_converged_beat_tripwire_passes_normal_forces(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="symmetric")
    assert cg.check_converged_beat_tripwire(entry) == []


def test_converged_beat_tripwire_fails_on_spike(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="spike")
    failures = cg.check_converged_beat_tripwire(entry)
    assert failures


# ---------------------------------------------------------------------------
# Offline-ness (the guard module imports no cluster/subprocess surface)
# ---------------------------------------------------------------------------


def test_guard_module_imports_no_cluster_or_subprocess_surface():
    import ast

    source = Path(cg.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"subprocess", "argo", "kubernetes", "socket"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert not (imported & forbidden), (
        f"guard module imports forbidden surface: {imported & forbidden}"
    )


def test_guard_module_reads_only_paths_under_repo_root():
    assert cg.REPO_ROOT.exists()
    for entry in cg.CORPUS_REGISTRY:
        assert cg.REPO_ROOT in entry.path.parents or entry.path == cg.REPO_ROOT


# ---------------------------------------------------------------------------
# Combined driver + real committed corpus (not just synthetic fixtures)
# ---------------------------------------------------------------------------


def test_run_all_guards_on_healthy_synthetic_corpus_passes(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="symmetric")
    assert cg.run_all_guards(entry) == []


def test_run_all_guards_on_truncated_synthetic_corpus_fails(tmp_path):
    entry = _build_synthetic_corpus(tmp_path, cf_x_pattern="truncated")
    assert cg.run_all_guards(entry) != []


@pytest.mark.parametrize(
    "entry", [e for e in cg.CORPUS_REGISTRY if e.has_parquet], ids=lambda e: e.name
)
def test_real_committed_corpus_passes_all_applicable_guards(entry):
    """The guards run against the ACTUAL committed corpus, not only synthetic fixtures built to
    satisfy them."""
    failures = cg.run_all_guards(entry)
    assert failures == [], f"{entry.name} failed guards: {failures}"


def test_fine_corpus_registry_entry_reflects_todays_state():
    """prelim_sweep_fine is registered has_parquet=False -- today's accurate fact (no parquet
    exists on main until PR #91 merges), not an oversight. Its deck/manifest-level guards still
    run cleanly against the committed decks/manifest/per-config metadata."""
    fine = next(e for e in cg.CORPUS_REGISTRY if e.name == "prelim_sweep_fine")
    assert fine.has_parquet is False
    assert fine.has_per_config_metadata is True
    assert cg.check_parquet_exists_if_registered(fine) == []
    assert cg.check_deck_matches_manifest_max_step(fine) == []
    assert cg.check_per_config_metadata_present(fine) == []
