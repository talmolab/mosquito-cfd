"""The bench summary figure: skill by entry and split, the seed range as an error bar.

Skill is not compared across splits (design D4); the figure places splits side by side only to
show where each entry breaks. A single-fit entry has a zero-width bar.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.figure import Figure

_OFFSET_WIDTH = 0.6


def summary_figure(rows: pd.DataFrame) -> Figure:
    """Build the figure.

    Args:
        rows: One row per (entry, split) with ``skill_min``, ``skill_max`` and
            ``skill_median``.

    Returns:
        A matplotlib ``Figure`` with one error-bar series per entry.
    """
    splits = list(dict.fromkeys(rows["split"]))
    entries = list(dict.fromkeys(rows["entry"]))
    fig = Figure(figsize=(max(8.0, 0.7 * len(splits)), 4.5), layout="constrained")
    ax = fig.add_subplot()
    offsets = np.linspace(-_OFFSET_WIDTH / 2, _OFFSET_WIDTH / 2, len(entries))
    x_of = {s: i for i, s in enumerate(splits)}
    for offset, entry in zip(offsets, entries, strict=True):
        mine = rows[rows["entry"] == entry]
        x = np.array([x_of[s] for s in mine["split"]], dtype=float) + offset
        mid = mine["skill_median"].to_numpy(dtype=float)
        err = np.vstack(
            [
                mid - mine["skill_min"].to_numpy(dtype=float),
                mine["skill_max"].to_numpy(dtype=float) - mid,
            ]
        )
        ax.errorbar(x, mid, yerr=err, fmt="o", capsize=2, label=entry)
    ax.set_xticks(range(len(splits)))
    ax.set_xticklabels(splits, rotation=45, ha="right")
    ax.set_ylabel("skill over the split's phase-only baseline")
    ax.set_title("Surrogate comparison bench: seed range per entry and split")
    ax.legend()
    return fig


def write_summary_figure(rows: pd.DataFrame, path: Path | str, dpi: int = 150) -> None:
    """Write :func:`summary_figure` as a PNG."""
    summary_figure(rows).savefig(Path(path), dpi=dpi)
