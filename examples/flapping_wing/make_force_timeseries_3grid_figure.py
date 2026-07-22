"""Force time-series overlay figure (Tier T3c): CF_chord and CF_normal, all 3 grids.

Cluster-free — reconstructs body-frame time series from the three committed CSVs via
``reconstruct_wing_body_forces``. Writes ``figures/fig_force_timeseries_3grid.{png,pdf}``.

Run: ``uv run python examples/flapping_wing/make_force_timeseries_3grid_figure.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mosquito_cfd.benchmarks.wing_convergence import reconstruct_wing_body_forces

_HERE = Path(__file__).parent
_GRIDS = [
    ("Coarse 64×32×64",    _HERE / "forces_t2a_newconv.csv", "#aec7e8", 1.4),
    ("Medium 128×64×128",  _HERE / "forces_medium.csv",      "#4c72b0", 1.8),
    ("Fine 256×128×256",   _HERE / "forces_fine.csv",        "#08306b", 2.2),
]
_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)
_WINDOW_T0 = 0.05

# Van Veen reference bands: (label, ymin, ymax, color, alpha, text_y_frac)
_VV_BANDS = {
    "cf_chord":  ("van Veen QS range 0.30–0.43",  0.30, 0.43, "#2ca02c", 0.15),
    "cf_normal": ("van Veen target range 2.16–2.48", 2.16, 2.48, "#2ca02c", 0.15),
}


def make_figure(
    out: Path = _HERE / "figures" / "fig_force_timeseries_3grid.png",
) -> Path:
    """Draw CF_chord and CF_normal time series for all 3 grids and save PNG + PDF."""
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax_chord, ax_normal = axes

    # Collect time series for each grid
    series = []
    for label, csv, color, lw in _GRIDS:
        d = reconstruct_wing_body_forces(csv, **_KIN)
        mask = d.time >= _WINDOW_T0
        series.append((label, d.time[mask], d.cf_chord[mask], np.abs(d.cf_normal[mask]), color, lw))

    # Plot van Veen bands FIRST (so they sit behind data and their handles enter the legend)
    for ax, comp in [(ax_chord, "cf_chord"), (ax_normal, "cf_normal")]:
        lbl, ymin, ymax, color, alpha = _VV_BANDS[comp]
        ax.axhspan(ymin, ymax, color=color, alpha=alpha, label=lbl, zorder=1)
        # Direct text annotation at right edge of band (avoids cluttering the legend)
        ax.annotate(
            lbl,
            xy=(0.99, (ymin + ymax) / 2),
            xycoords=("axes fraction", "data"),
            ha="right", va="center", fontsize=8, color=color,
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7),
        )

    # Plot CFD data lines
    for label, t, cf_chord, cf_normal, color, lw in series:
        ax_chord.plot(t, cf_chord, color=color, lw=lw, label=label, alpha=0.92, zorder=3)
        ax_normal.plot(t, cf_normal, color=color, lw=lw, label=label, alpha=0.92, zorder=3)

    # Styling — draw legend AFTER all artists are added
    for ax, ylabel, title in [
        (ax_chord,  "CF_chord  (tangential)",  "CF_chord — body-frame tangential force"),
        (ax_normal, "|CF_normal|  (lift)",      "|CF_normal| — body-frame lift force"),
    ]:
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.axhline(0, color="k", lw=0.6, ls="--", alpha=0.4, zorder=2)
        ax.grid(alpha=0.2, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        # Grid-only legend (exclude the van Veen band handle from the legend)
        handles, labels = ax.get_legend_handles_labels()
        grid_handles = [(h, l) for h, l in zip(handles, labels) if "van Veen" not in l]
        if grid_handles:
            hs, ls = zip(*grid_handles)
            ax.legend(hs, ls, fontsize=9, loc="upper right", framealpha=0.85)

    ax_normal.set_xlabel("Time  (wingbeats)", fontsize=10)
    ax_normal.set_xlim(_WINDOW_T0, 1.0)

    fig.suptitle(
        "Body-frame force coefficients: coarse / medium / fine grid overlay  (T3c)\n"
        "van Veen normalization,  F_ref = 200.27,  steady window t ≥ 0.05",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
