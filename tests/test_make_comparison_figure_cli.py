"""CLI smoke tests for scripts/make_comparison_figure.py and
scripts/make_config_mean_collapse_diagnostic.py (OpenSpec change add-visualization-tooling).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2020-01-01T00:00:00+00:00"


def _load_cli(name: str, script_path: str):
    spec = importlib.util.spec_from_file_location(name, Path(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _tiny_predictions_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "config_name": ["cfgA", "cfgA", "cfgB", "cfgB"],
            "phase": [0.0, 0.5, 0.0, 0.5],
            "CF_x_true": [1.0, 2.0, -1.0, -2.0],
            "CF_x_pred": [1.1, 1.9, -0.9, -2.1],
        }
    )


def _tiny_metrics(config_mean_r2: float) -> dict:
    return {
        "config_resolved": {"CF_x": {"config_mean_r2": config_mean_r2}},
        "per_target": {"CF_x": {"rmse": 0.1}},
    }


# --- make_comparison_figure.py ------------------------------------------------------------------


def test_comparison_figure_cli_rejects_missing_required_flags():
    cli = _load_cli("make_comparison_figure", "scripts/make_comparison_figure.py")
    with pytest.raises(SystemExit):
        cli.main([])


def test_comparison_figure_cli_smoke(tmp_path):
    coarse_path = tmp_path / "coarse.parquet"
    fine_path = tmp_path / "fine.parquet"
    _tiny_predictions_df().to_parquet(coarse_path)
    _tiny_predictions_df().to_parquet(fine_path)

    cli = _load_cli("make_comparison_figure", "scripts/make_comparison_figure.py")
    rc = cli.main(
        [
            "--coarse-predictions",
            str(coarse_path),
            "--fine-predictions",
            str(fine_path),
            "--out-dir",
            str(tmp_path / "out"),
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
        ]
    )

    assert rc == 0
    assert (tmp_path / "out" / "coarse_vs_fine_comparison.png").exists()


# --- make_config_mean_collapse_diagnostic.py ----------------------------------------------------


def test_config_mean_collapse_diagnostic_cli_rejects_missing_required_flags():
    cli = _load_cli(
        "make_config_mean_collapse_diagnostic",
        "scripts/make_config_mean_collapse_diagnostic.py",
    )
    with pytest.raises(SystemExit):
        cli.main([])


def test_config_mean_collapse_diagnostic_cli_smoke(tmp_path):
    coarse_pred_path = tmp_path / "coarse.parquet"
    fine_pred_path = tmp_path / "fine.parquet"
    _tiny_predictions_df().to_parquet(coarse_pred_path)
    _tiny_predictions_df().to_parquet(fine_pred_path)
    coarse_metrics_path = tmp_path / "coarse_metrics.json"
    fine_metrics_path = tmp_path / "fine_metrics.json"
    coarse_metrics_path.write_text(json.dumps(_tiny_metrics(0.9)))
    fine_metrics_path.write_text(json.dumps(_tiny_metrics(-30.0)))

    cli = _load_cli(
        "make_config_mean_collapse_diagnostic",
        "scripts/make_config_mean_collapse_diagnostic.py",
    )
    rc = cli.main(
        [
            "--coarse-predictions",
            str(coarse_pred_path),
            "--fine-predictions",
            str(fine_pred_path),
            "--coarse-metrics",
            str(coarse_metrics_path),
            "--fine-metrics",
            str(fine_metrics_path),
            "--out-dir",
            str(tmp_path / "out"),
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
        ]
    )

    assert rc == 0
    assert (tmp_path / "out" / "diagnostic_config_mean_collapse.png").exists()
