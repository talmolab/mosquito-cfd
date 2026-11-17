"""One matplotlib style for every experiment figure (static, light surface, slide-ready)."""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
TARGET_COLOR = dict(zip(("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"), SERIES))
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
SEQ = LinearSegmentedColormap.from_list("seq_blue", ["#f0efec", "#cde2fb", "#86b6ef", "#2a78d6", "#0d366b"])
DIV = LinearSegmentedColormap.from_list("div", ["#1c5cab", "#86b6ef", "#f0efec", "#f0a98a", "#b8431a"])


def use_style() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK, "axes.titlecolor": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 2.0,
        "axes.prop_cycle": mpl.cycler(color=SERIES), "font.size": 10, "axes.titlesize": 11,
        "axes.titleweight": "bold", "axes.titlelocation": "left", "legend.frameon": False,
        "savefig.dpi": 200, "savefig.bbox": "tight", "figure.dpi": 110,
    })


def save(fig, path) -> None:
    from pathlib import Path

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
