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

from mosquito_cfd.benchmarks.flapping_wing import (
    STEADY_WINDOW_T0,
    decompose_wing_force,
    reconstruct_wing_body_forces,
)

_HERE = Path(__file__).parent
_GRIDS = [
    ("Coarse 64×32×64",    _HERE / "forces_t2a_newconv.csv", "#aec7e8", 1.4),
    ("Medium 128×64×128",  _HERE / "forces_medium.csv",      "#4c72b0", 1.8),
    ("Fine 256×128×256",   _HERE / "forces_fine.csv",        "#08306b", 2.2),
]
_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)
_WINDOW_T0 = STEADY_WINDOW_T0

# Reference lines: the peak of van Veen's quasi-steady model (transl + added-mass + Wagner) on
# our kinematics, read from decompose_wing_force on the fine-grid CSV when the figure is drawn
# (never a typed number). The chord force changes sign each half-stroke, so its line is drawn at
# both signs; the normal force keeps a positive lobe on each half-stroke, so its line is drawn on
# the positive side only.
_MODEL_COLOR = "#2ca02c"
_MODEL_LABEL = "van Veen QS model peak (T4, fine grid)"


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
        series.append((label, d.time[mask], d.cf_chord[mask], d.cf_normal[mask], color, lw))

    # Model reference lines FIRST (so they sit behind the data).
    model = decompose_wing_force(_GRIDS[-1][1], **_KIN)
    chord_peak, normal_peak = model["chord_peak_model"], model["normal_peak_model"]
    line = dict(color=_MODEL_COLOR, ls="--", lw=1.4, zorder=2)
    ax_chord.axhline(+chord_peak, label=_MODEL_LABEL, **line)
    ax_chord.axhline(-chord_peak, **line)
    ax_normal.axhline(normal_peak, label=_MODEL_LABEL, **line)

    # Plot CFD data lines (signed CF_normal — consistent with T4 decomposition figure)
    for label, t, cf_chord, cf_normal, color, lw in series:
        ax_chord.plot(t, cf_chord, color=color, lw=lw, label=label, alpha=0.92, zorder=3)
        ax_normal.plot(t, cf_normal, color=color, lw=lw, label=label, alpha=0.92, zorder=3)

    # Styling — draw legend AFTER all artists are added
    for ax, ylabel, title in [
        (ax_chord,  "CF_chord  (tangential)",  "CF_chord — body-frame tangential force"),
        (ax_normal, "CF_normal  (wing-normal)",        "CF_normal — wing-normal force  (signed)"),
    ]:
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.axhline(0, color="k", lw=0.6, ls="--", alpha=0.4, zorder=2)
        ax.grid(alpha=0.2, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        # Grids first, then the model reference line.
        handles, labels = ax.get_legend_handles_labels()
        order = sorted(range(len(labels)), key=lambda k: labels[k] == _MODEL_LABEL)
        loc = "lower right" if ax is ax_chord else "upper left"
        ax.legend(
            [handles[k] for k in order],
            [labels[k] for k in order],
            fontsize=9,
            loc=loc,
            framealpha=0.85,
        )

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
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", metadata={"CreationDate": None})
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
