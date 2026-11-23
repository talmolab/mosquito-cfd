"""The committed coarse-vs-fine figures match their inputs and renderer (add-real-comparison-figures).

Applies ``check_committed_figure`` to each committed figure, and checks independent anchors in the
test itself, so a stale figure (a changed corpus, retrained surrogate or edited renderer) fails CI
until it is re-rendered. A corpus regeneration makes this fail on purpose: retrain, then re-render
all three figures into a scratch directory and copy them in (``examples/prelim_sweep_fine/README.md``,
"Comparison figures").
"""

from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from _comparison_guards import COARSE_DIR, FIGURE_DIR, FINE_DIR, check_committed_figure

from mosquito_cfd.force_surrogate import comparison_figure as cf
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS, build_phase_only_baseline

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / FIGURE_DIR
FILES = [
    f"{f}{s}"
    for f in cf.FIGURES
    for s in (".png", "_metrics.json", "_run_metadata.json")
]


def _json(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("figure", cf.FIGURES)
def test_committed_figure_matches_its_inputs_and_renderer(figure):
    check_committed_figure(REPO, figure)


def test_all_nine_files_are_tracked_and_the_pngs_are_pngs():
    for name in FILES:
        path = OUT / name
        assert path.is_file(), name
        subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(REPO))],
            cwd=REPO,
            check=True,
            capture_output=True,
        )
    for figure in cf.FIGURES:
        assert (OUT / f"{figure}.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert not (REPO / "tests" / "fixtures" / "comparison_figure").exists()


def test_the_three_figures_share_one_render_timestamp():
    stamps = {_json(f"{f}_run_metadata.json")["timestamp"] for f in cf.FIGURES}
    assert len(stamps) == 1, stamps


def _metrics(corpus_dir):
    return json.loads(
        (REPO / corpus_dir / "surrogate" / "metrics.json").read_text("utf-8")
    )


def test_skill_ranges_anchor_on_metrics_json():
    sidecar = _json("skill_ranges_metrics.json")
    for corpus, d in (("coarse", COARSE_DIR), ("fine", FINE_DIR)):
        runs = _metrics(d)["seed_sweep"]["runs"]
        for c in TARGET_COLUMNS:
            assert sidecar["targets"][c][corpus]["values"] == [
                r["per_target"][c]["skill"] for r in runs
            ]
    disjoint = {c for c, e in sidecar["targets"].items() if e["overlap"] == "no"}
    assert set(sidecar["notes"]) == disjoint


def test_error_histogram_counts_anchor_on_an_independent_baseline():
    sidecar = _json("error_histograms_metrics.json")
    edges = np.linspace(-3.0, 3.0, 601)
    assert sidecar["edges"] == edges.tolist()
    for corpus, d in (("coarse", COARSE_DIR), ("fine", FINE_DIR)):
        pred = pd.read_parquet(REPO / d / "surrogate" / "holdout_predictions.parquet")
        dataset = pd.read_parquet(REPO / d / "dataset.parquet")
        base, _ = build_phase_only_baseline(
            dataset, pred["phase"].to_numpy(dtype=float)
        )
        recorded = _metrics(d)["phase_baseline_skill"]["per_target"]
        for j, c in enumerate(TARGET_COLUMNS):
            entry = sidecar["grids"][corpus][c]
            rmse0 = recorded[c]["phase_baseline_rmse"]
            t = pred[f"{c}_true"].to_numpy()
            for kind, values in (
                ("surrogate", pred[f"{c}_pred"].to_numpy()),
                ("baseline", base[:, j]),
            ):
                z = (values - t) / rmse0
                counts, _ = np.histogram(z[(z >= -3) & (z <= 3)], bins=edges)
                assert entry[f"counts_{kind}"] == counts.tolist(), (corpus, c, kind)
                total = counts.sum() + entry[f"below_{kind}"] + entry[f"above_{kind}"]
                assert total == len(pred)


def test_cycle_mean_scales_anchor_on_metrics_json():
    sidecar = _json("cycle_mean_r2_diagnostic_metrics.json")
    for corpus, d in (("coarse", COARSE_DIR), ("fine", FINE_DIR)):
        pred = pd.read_parquet(REPO / d / "surrogate" / "holdout_predictions.parquet")
        runs = _metrics(d)["seed_sweep"]["runs"]
        for c in TARGET_COLUMNS:
            entry = sidecar["grids"][corpus][c]
            means = pred.groupby("config_name")[f"{c}_true"].mean().to_numpy()
            sigma = float(np.std(means))
            assert math.isclose(entry["sigma"], sigma, rel_tol=1e-12, abs_tol=0)
            r2 = [r["per_target"][c]["config_mean_r2"] for r in runs]
            assert entry["config_mean_r2"] == r2
            for value, eps in zip(r2, entry["eps"], strict=True):
                assert math.isclose(eps, sigma * math.sqrt(1 - value), rel_tol=1e-9)
