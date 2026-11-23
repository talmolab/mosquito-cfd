"""Bench summary figure (add-surrogate-comparison-bench, 7a; CPU tier).

Scenario "The summary figure shows every entry and split" (requirement "Bench artifacts,
provenance and claim scope").
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.container import ErrorbarContainer  # noqa: E402

from mosquito_cfd.surrogate_bench.figure import (  # noqa: E402
    summary_figure,
    write_summary_figure,
)

ENTRIES = ["mlp_h1", "mlp_h3", "mlp_w256d5", "mlp_w256d5_h3", "ridge", "ridge_fixed"]
SPLITS = [f"split_{i}" for i in range(14)]


def _rows():
    rng = np.random.default_rng(0)
    rows = []
    for entry in ENTRIES:
        for split in SPLITS:
            lo = float(rng.uniform(0.9, 0.99))
            hi = lo if entry.startswith("ridge") else lo + 0.005
            rows.append(
                {
                    "entry": entry,
                    "split": split,
                    "skill_min": lo,
                    "skill_max": hi,
                    "skill_median": (lo + hi) / 2,
                }
            )
    return pd.DataFrame(rows)


def test_one_error_bar_per_entry_and_split():
    fig = summary_figure(_rows())
    ax = fig.axes[0]
    containers = [c for c in ax.containers if isinstance(c, ErrorbarContainer)]
    assert len(containers) == len(ENTRIES)
    n_points = sum(len(c.lines[0].get_xdata()) for c in containers)
    assert n_points == len(ENTRIES) * len(SPLITS)
    labels = [t.get_text() for t in ax.get_xticklabels()]
    assert labels == SPLITS
    assert [t.get_text() for t in ax.get_legend().get_texts()] == ENTRIES


def test_the_bars_span_the_seed_range():
    rows = _rows()
    fig = summary_figure(rows)
    ax = fig.axes[0]
    container = [c for c in ax.containers if isinstance(c, ErrorbarContainer)][0]
    first = rows[rows["entry"] == ENTRIES[0]].iloc[0]
    segments = container.lines[2][0].get_segments()
    ys = sorted(segments[0][:, 1])
    assert ys[0] == first["skill_min"] and ys[1] == first["skill_max"]


def test_the_figure_is_written(tmp_path):
    path = tmp_path / "bench_summary.png"
    write_summary_figure(_rows(), path)
    assert path.exists() and path.stat().st_size > 0
