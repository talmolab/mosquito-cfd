"""Force-surrogate coarse-vs-fine comparison and config-mean-collapse diagnostic figures.

OpenSpec change ``add-visualization-tooling``. Numerical correctness against synthetic fixtures
(never real corpus data in this test file) -- specifically guards against conflating
``metrics.json``'s ``config_resolved`` block (config-mean R2) with its separate ``per_target``
block (RMSE), the documented gotcha in the tooling this capability replaces.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.comparison_figure import (
    build_coarse_vs_fine_comparison,
    build_config_mean_collapse_diagnostic,
)

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"


def _tiny_predictions_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "config_name": ["cfgA", "cfgA", "cfgA", "cfgB", "cfgB", "cfgB"],
            "phase": [0.0, 0.33, 0.66, 0.0, 0.33, 0.66],
            "CF_x_true": [1.0, 2.0, 3.0, -1.0, -2.0, -3.0],
            "CF_x_pred": [1.1, 1.9, 3.2, -0.9, -2.1, -2.8],
            # A second coefficient with DIFFERENT values than CF_x, so a test exercising
            # coefficient="CF_z" can't coincidentally pass by reading the wrong column.
            "CF_z_true": [10.0, 12.0, 14.0, -5.0, -6.0, -7.0],
            "CF_z_pred": [10.5, 11.5, 14.5, -5.2, -5.8, -7.3],
        }
    )


def _write_parquet(df: pd.DataFrame, path) -> None:
    df.to_parquet(path)


def _tiny_metrics(
    config_mean_r2: float, per_target_rmse: float, coefficient: str = "CF_x"
) -> dict:
    return {
        "config_resolved": {coefficient: {"config_mean_r2": config_mean_r2}},
        "per_target": {coefficient: {"rmse": per_target_rmse}},
    }


def test_committed_comparison_figure_inputs_match_in_memory_tiny_fixtures():
    """The parquet/JSON files committed under tests/fixtures/comparison_figure/inputs/ (used to
    generate the two committed reference PNGs, per README.md there) are byte-for-value-identical
    to this file's own ``_tiny_predictions_df``/``_tiny_metrics`` helpers.

    Three /review-pr rounds on add-visualization-tooling PR3 flagged the same gap: nothing
    enforced this correspondence, so the committed reference figures could silently go stale if
    these in-memory fixtures ever changed. This is the guard.
    """
    inputs_dir = Path(__file__).parent / "fixtures" / "comparison_figure" / "inputs"

    coarse = pd.read_parquet(inputs_dir / "coarse_predictions.parquet")
    pd.testing.assert_frame_equal(coarse, _tiny_predictions_df())

    expected_fine = _tiny_predictions_df()
    expected_fine["CF_x_true"] = expected_fine["CF_x_true"] * 0.1
    fine = pd.read_parquet(inputs_dir / "fine_predictions.parquet")
    pd.testing.assert_frame_equal(fine, expected_fine)

    diag_coarse = pd.read_parquet(inputs_dir / "diagnostic_coarse_predictions.parquet")
    diag_fine = pd.read_parquet(inputs_dir / "diagnostic_fine_predictions.parquet")
    pd.testing.assert_frame_equal(diag_coarse, _tiny_predictions_df())
    pd.testing.assert_frame_equal(diag_fine, _tiny_predictions_df())

    coarse_metrics = json.loads((inputs_dir / "coarse_metrics.json").read_text())
    fine_metrics = json.loads((inputs_dir / "fine_metrics.json").read_text())
    assert coarse_metrics == _tiny_metrics(config_mean_r2=0.944, per_target_rmse=0.133)
    assert fine_metrics == _tiny_metrics(config_mean_r2=-31.95, per_target_rmse=0.05)


def test_committed_reference_pngs_exist_and_are_nonempty():
    """Operationalizes spec.md's "figure scripts ship one committed reference PNG" scenarios
    as an actual CI-enforced check, rather than leaving it as a doc-only claim (the /review-openspec
    round that added the diagnostic-PNG scenario found the requirement had no test backing it).
    """
    fixtures_dir = Path(__file__).parent / "fixtures" / "comparison_figure"
    for name in (
        "coarse_vs_fine_comparison.png",
        "diagnostic_config_mean_collapse.png",
    ):
        path = fixtures_dir / name
        assert path.exists(), f"{name} missing from {fixtures_dir}"
        assert path.stat().st_size > 0, f"{name} is empty"


def test_coarse_vs_fine_panel_means_match_groupby(tmp_path):
    """Per-config mean marker positions match a direct pandas groupby on the same data."""
    coarse_df = _tiny_predictions_df()
    fine_df = _tiny_predictions_df()
    fine_df["CF_x_true"] = fine_df["CF_x_true"] * 0.1  # distinct fine-grid values

    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(coarse_df, coarse_path)
    _write_parquet(fine_df, fine_path)

    result = build_coarse_vs_fine_comparison(
        coarse_predictions_path=coarse_path,
        fine_predictions_path=fine_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    expected_coarse = coarse_df.groupby("config_name")[
        ["CF_x_true", "CF_x_pred"]
    ].mean()
    expected_fine = fine_df.groupby("config_name")[["CF_x_true", "CF_x_pred"]].mean()

    for cfg in ("cfgA", "cfgB"):
        assert result["coarse"][cfg]["true_mean"] == pytest.approx(
            expected_coarse.loc[cfg, "CF_x_true"]
        )
        assert result["coarse"][cfg]["pred_mean"] == pytest.approx(
            expected_coarse.loc[cfg, "CF_x_pred"]
        )
        assert result["fine"][cfg]["true_mean"] == pytest.approx(
            expected_fine.loc[cfg, "CF_x_true"]
        )
        assert result["fine"][cfg]["pred_mean"] == pytest.approx(
            expected_fine.loc[cfg, "CF_x_pred"]
        )


def test_coarse_vs_fine_comparison_writes_three_artifacts(tmp_path):
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    build_coarse_vs_fine_comparison(
        coarse_predictions_path=coarse_path,
        fine_predictions_path=fine_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    assert (tmp_path / "coarse_vs_fine_comparison.png").exists()
    assert (tmp_path / "coarse_vs_fine_comparison_metrics.json").exists()
    meta = json.loads(
        (tmp_path / "coarse_vs_fine_comparison_run_metadata.json").read_text()
    )
    assert meta["timestamp"] == TS
    assert "sha256:" in meta["docker_image"]


def test_coarse_vs_fine_comparison_rejects_mutable_docker_tag(tmp_path):
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    with pytest.raises(ValueError):
        build_coarse_vs_fine_comparison(
            coarse_predictions_path=coarse_path,
            fine_predictions_path=fine_path,
            out_dir=tmp_path,
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TS,
        )
    assert not (tmp_path / "coarse_vs_fine_comparison.png").exists()


def test_config_mean_collapse_diagnostic_matches_metrics_json(tmp_path):
    """The diagnostic's reported R2 matches config_resolved exactly, never per_target."""
    # Deliberately distinct values so a config_resolved/per_target swap is caught.
    coarse_metrics = _tiny_metrics(config_mean_r2=0.944, per_target_rmse=0.133)
    fine_metrics = _tiny_metrics(config_mean_r2=-31.95, per_target_rmse=0.05)

    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(coarse_metrics))
    fine_metrics_path.write_text(json.dumps(fine_metrics))

    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    result = build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    assert result["coarse"]["config_mean_r2"] == pytest.approx(0.944)
    assert result["fine"]["config_mean_r2"] == pytest.approx(-31.95)
    # Never the per_target RMSE values -- the exact conflation this requirement prevents.
    assert result["coarse"]["config_mean_r2"] != pytest.approx(0.133)
    assert result["fine"]["config_mean_r2"] != pytest.approx(0.05)


def test_config_mean_collapse_diagnostic_writes_three_artifacts(tmp_path):
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    assert (tmp_path / "diagnostic_config_mean_collapse.png").exists()
    assert (tmp_path / "diagnostic_config_mean_collapse_metrics.json").exists()
    meta = json.loads(
        (tmp_path / "diagnostic_config_mean_collapse_run_metadata.json").read_text()
    )
    assert meta["timestamp"] == TS


def test_config_mean_collapse_diagnostic_rejects_mutable_docker_tag(tmp_path):
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    with pytest.raises(ValueError):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TS,
        )
    assert not (tmp_path / "diagnostic_config_mean_collapse.png").exists()


def test_coarse_vs_fine_comparison_rejects_nonfinite_values(tmp_path):
    """A NaN in the predictions must not silently produce a wrong comparison figure."""
    df = _tiny_predictions_df()
    df.loc[0, "CF_x_true"] = np.nan
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(df, coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    with pytest.raises(ValueError, match="non-finite"):
        build_coarse_vs_fine_comparison(
            coarse_predictions_path=coarse_path,
            fine_predictions_path=fine_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (tmp_path / "coarse_vs_fine_comparison.png").exists()


def test_coarse_vs_fine_comparison_rejects_missing_coefficient_columns(tmp_path):
    """A coefficient with no matching columns in the predictions parquet fails clearly, via the
    same _validate_predictions_finite guard as the non-finite-value case above -- previously only
    the non-finite-*value* branch was tested, not the missing-*column* branch.
    """
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    with pytest.raises(ValueError, match="missing required column"):
        build_coarse_vs_fine_comparison(
            coarse_predictions_path=coarse_path,
            fine_predictions_path=fine_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
            coefficient="CF_missing",
        )
    assert not (tmp_path / "coarse_vs_fine_comparison.png").exists()


def test_config_mean_collapse_diagnostic_rejects_missing_coefficient_columns(tmp_path):
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    with pytest.raises(ValueError, match="missing required column"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
            coefficient="CF_missing",
        )
    assert not (tmp_path / "diagnostic_config_mean_collapse.png").exists()


def test_config_mean_collapse_diagnostic_rejects_nonfinite_values(tmp_path):
    df = _tiny_predictions_df()
    df.loc[0, "CF_x_pred"] = np.inf
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(df, coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))

    with pytest.raises(ValueError, match="non-finite"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (tmp_path / "diagnostic_config_mean_collapse.png").exists()


def test_coarse_vs_fine_comparison_hashes_the_fine_predictions_input(tmp_path):
    """The fine-grid predictions parquet's own hash is recorded, not just its path string."""
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    build_coarse_vs_fine_comparison(
        coarse_predictions_path=coarse_path,
        fine_predictions_path=fine_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    meta = json.loads(
        (tmp_path / "coarse_vs_fine_comparison_run_metadata.json").read_text()
    )
    assert (
        meta["fine_predictions_sha256"]
        == hashlib.sha256(fine_path.read_bytes()).hexdigest()
    )


def test_config_mean_collapse_diagnostic_hashes_all_secondary_inputs(tmp_path):
    """The three non-primary inputs (fine metrics + both predictions parquets) are each hashed."""
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    meta = json.loads(
        (tmp_path / "diagnostic_config_mean_collapse_run_metadata.json").read_text()
    )
    assert (
        meta["fine_metrics_sha256"]
        == hashlib.sha256(fine_metrics_path.read_bytes()).hexdigest()
    )
    assert (
        meta["coarse_predictions_sha256"]
        == hashlib.sha256(coarse_pred_path.read_bytes()).hexdigest()
    )
    assert (
        meta["fine_predictions_sha256"]
        == hashlib.sha256(fine_pred_path.read_bytes()).hexdigest()
    )


def test_config_mean_collapse_diagnostic_missing_config_resolved_key_names_it(tmp_path):
    """A malformed metrics.json raises a KeyError naming the missing key, not a bare one."""
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps({"per_target": {"CF_x": {"rmse": 0.1}}}))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    with pytest.raises(KeyError, match="config_resolved"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )


def test_config_mean_collapse_diagnostic_missing_coefficient_entry_names_it(tmp_path):
    """config_resolved present but missing the coefficient's own entry -- the second of
    _config_resolved_r2's three _require call sites, previously untested (round 2 review).
    """
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps({"config_resolved": {}}))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    with pytest.raises(KeyError, match="CF_x"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )


def test_config_mean_collapse_diagnostic_missing_config_mean_r2_leaf_names_it(tmp_path):
    """config_resolved.<coef> present but missing config_mean_r2 itself -- the third of
    _config_resolved_r2's three _require call sites, previously untested (round 2 review) and
    easily confused with the separate present-but-null case, which is a different code path.
    """
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps({"config_resolved": {"CF_x": {}}}))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    with pytest.raises(KeyError, match="config_mean_r2"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )


def test_config_mean_collapse_diagnostic_rejects_missing_phase_column(tmp_path):
    """A predictions frame without `phase` fails clearly before any figure work, instead of a
    bare KeyError('phase') deep inside the waveform panel's sort_values call (round 2 review).
    """
    df = _tiny_predictions_df().drop(columns=["phase"])
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(df, coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))

    with pytest.raises(ValueError, match="phase"):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (tmp_path / "diagnostic_config_mean_collapse.png").exists()


def test_coarse_vs_fine_comparison_rejects_missing_config_name_column(tmp_path):
    df = _tiny_predictions_df().drop(columns=["config_name"])
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(df, coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)

    with pytest.raises(ValueError, match="config_name"):
        build_coarse_vs_fine_comparison(
            coarse_predictions_path=coarse_path,
            fine_predictions_path=fine_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (tmp_path / "coarse_vs_fine_comparison.png").exists()


def test_config_mean_collapse_diagnostic_waveform_panel_is_sorted_by_phase(
    tmp_path, monkeypatch
):
    """The bottom-row waveform plot sorts by phase before plotting -- pins the existing
    .sort_values("phase") call so it can't be silently dropped without a test noticing (round 2
    review found this was correct but unpinned). The function closes its own figure before
    returning, so this captures it via a wrapped plt.subplots rather than plt.gcf() afterward.
    """
    shuffled = pd.DataFrame(
        {
            "config_name": ["cfgA"] * 4,
            "phase": [0.66, 0.0, 0.99, 0.33],
            "CF_x_true": [3.0, 1.0, 4.0, 2.0],
            "CF_x_pred": [3.2, 1.1, 4.4, 2.2],
        }
    )
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(shuffled, coarse_pred_path)
    _write_parquet(shuffled, fine_pred_path)
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))

    captured = {}
    real_subplots = plt.subplots

    def spy_subplots(*args, **kwargs):
        fig, axes = real_subplots(*args, **kwargs)
        captured["fig"] = fig
        return fig, axes

    monkeypatch.setattr(
        "mosquito_cfd.force_surrogate.comparison_figure.plt.subplots", spy_subplots
    )

    build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    # The bottom-left axes' first Line2D (the "true" waveform) must be phase-ordered, even
    # though the figure itself is already closed by the time this runs.
    bottom_left_ax = captured["fig"].axes[2]
    plotted_x = bottom_left_ax.lines[0].get_xdata()
    assert list(plotted_x) == sorted(plotted_x)


def test_config_mean_collapse_diagnostic_raises_before_any_figure_exists_on_metrics_error(
    tmp_path,
):
    """A malformed metrics.json fails before a Figure is ever created (no leak possible).

    ``_config_resolved_r2`` (which raises here) runs before ``plt.subplots`` is called -- see
    the "compute every fallible value BEFORE creating the matplotlib figure" comment in
    ``build_config_mean_collapse_diagnostic``. This asserts that ordering directly (zero
    figures at any point), rather than the now-vacuous "figure count unchanged" check a review
    round found: since no figure is ever created on this path, that assertion would hold even
    without the try/finally this fix also added -- it doesn't exercise the finally block at all.
    """
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps({"per_target": {"CF_x": {"rmse": 0.1}}}))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    open_before = len(plt.get_fignums())
    with pytest.raises(KeyError):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=tmp_path,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert len(plt.get_fignums()) == open_before


def test_config_mean_collapse_diagnostic_does_not_leak_figure_on_mkdir_error(tmp_path):
    """The actual try/finally leak guard, exercised post-Figure-creation (mirrors the sibling
    coarse-vs-fine test -- a review round found the metrics-error variant above never reaches
    ``plt.subplots`` at all, so it couldn't exercise this guard).
    """
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9, 0.1)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)
    blocked_out_dir = tmp_path / "blocked"
    blocked_out_dir.write_text("not a directory")

    open_before = len(plt.get_fignums())
    with pytest.raises(FileExistsError):
        build_config_mean_collapse_diagnostic(
            coarse_predictions_path=coarse_pred_path,
            fine_predictions_path=fine_pred_path,
            coarse_metrics_path=coarse_metrics_path,
            fine_metrics_path=fine_metrics_path,
            out_dir=blocked_out_dir,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert len(plt.get_fignums()) == open_before


def test_coarse_vs_fine_comparison_does_not_leak_figure_on_mkdir_error(tmp_path):
    """An out_dir that can't be created must not leave an unclosed matplotlib Figure behind."""
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_path)
    _write_parquet(_tiny_predictions_df(), fine_path)
    # A file (not a directory) at the target path makes Path.mkdir() raise FileExistsError.
    blocked_out_dir = tmp_path / "blocked"
    blocked_out_dir.write_text("not a directory")

    open_before = len(plt.get_fignums())
    with pytest.raises(FileExistsError):
        build_coarse_vs_fine_comparison(
            coarse_predictions_path=coarse_path,
            fine_predictions_path=fine_path,
            out_dir=blocked_out_dir,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert len(plt.get_fignums()) == open_before


def test_coarse_vs_fine_comparison_honors_non_default_coefficient(tmp_path):
    """The documented `coefficient` parameter is exercised with a non-default value (CF_z)."""
    coarse_df = _tiny_predictions_df()
    fine_df = _tiny_predictions_df()
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _write_parquet(coarse_df, coarse_path)
    _write_parquet(fine_df, fine_path)

    result = build_coarse_vs_fine_comparison(
        coarse_predictions_path=coarse_path,
        fine_predictions_path=fine_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
        coefficient="CF_z",
    )

    assert result["coefficient"] == "CF_z"
    expected = coarse_df.groupby("config_name")[["CF_z_true", "CF_z_pred"]].mean()
    assert result["coarse"]["cfgA"]["true_mean"] == pytest.approx(
        expected.loc["cfgA", "CF_z_true"]
    )
    # Not accidentally reading the CF_x columns instead.
    assert result["coarse"]["cfgA"]["true_mean"] != pytest.approx(
        coarse_df[coarse_df["config_name"] == "cfgA"]["CF_x_true"].mean()
    )


def test_config_mean_collapse_diagnostic_honors_non_default_coefficient(tmp_path):
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(
        json.dumps(_tiny_metrics(0.5, 0.2, coefficient="CF_z"))
    )
    fine_metrics_path.write_text(
        json.dumps(_tiny_metrics(-10.0, 0.1, coefficient="CF_z"))
    )
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    result = build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
        coefficient="CF_z",
    )

    assert result["coarse"]["config_mean_r2"] == pytest.approx(0.5)
    assert result["fine"]["config_mean_r2"] == pytest.approx(-10.0)


def test_config_mean_collapse_diagnostic_passes_through_null_config_mean_r2(tmp_path):
    """A JSON null config_mean_r2 (train.py's real near-zero-variance sentinel) passes through
    as None rather than crashing or being silently coerced to some other value.
    """
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(
        json.dumps({"config_resolved": {"CF_x": {"config_mean_r2": None}}})
    )
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0, 0.05)))
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _write_parquet(_tiny_predictions_df(), coarse_pred_path)
    _write_parquet(_tiny_predictions_df(), fine_pred_path)

    result = build_config_mean_collapse_diagnostic(
        coarse_predictions_path=coarse_pred_path,
        fine_predictions_path=fine_pred_path,
        coarse_metrics_path=coarse_metrics_path,
        fine_metrics_path=fine_metrics_path,
        out_dir=tmp_path,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )

    assert result["coarse"]["config_mean_r2"] is None
