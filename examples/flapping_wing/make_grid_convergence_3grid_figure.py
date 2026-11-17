"""3-grid Richardson convergence figure (Tier T3c): peak body-frame CF, coarse/medium/fine.

Cluster-free — recomputes peaks and Richardson analysis directly from the three committed
IB-particle CSVs. Writes ``figures/fig_grid_convergence_3grid.{png,pdf}``.

Run: ``uv run python examples/flapping_wing/make_grid_convergence_3grid_figure.py``
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mosquito_cfd.benchmarks.flapping_wing import (
    VAN_VEEN_CF_TARGETS,
    decompose_wing_force,
)
from mosquito_cfd.benchmarks.wing_convergence import (
    wing_grid_convergence_from_body_forces,
)

_HERE = Path(__file__).parent
_COARSE = _HERE / "forces_t2a_newconv.csv"
_MEDIUM = _HERE / "forces_medium.csv"
_FINE = _HERE / "forces_fine.csv"

_XTICKS = [0, 1, 2]
_XLABELS = ["Coarse\n64³", "Medium\n128³", "Fine\n256³"]
# Reference lines, each read from its source when the figure is drawn (never a typed number):
# the peak of van Veen's quasi-steady model from decompose_wing_force on the fine-grid CSV, and
# the pinned T2a target from VAN_VEEN_CF_TARGETS. Keys: (decompose key, targets key).
_REFERENCE_KEYS = {
    "cf_chord": ("chord_peak_model", "cf_chord_peak"),
    "cf_normal": ("normal_peak_model", "cf_normal_peak"),
}
_MODEL_LABEL = "van Veen QS model peak (T4, fine grid)"
_TARGET_LABEL = "T2a target (pinned)"
_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)
_TITLES = {"cf_chord": "CF_chord  (tangential)", "cf_normal": "CF_normal  (lift)"}
_COLORS = {"cf_chord": "#c44e52", "cf_normal": "#4c72b0"}
_VV_COLOR = "#2ca02c"


def make_figure(
    out: Path = _HERE / "figures" / "fig_grid_convergence_3grid.png",
) -> Path:
    """Draw the 3-grid Richardson convergence figure and save PNG + PDF."""
    conv = wing_grid_convergence_from_body_forces(_COARSE, _MEDIUM, _FINE, **_KIN)
    model = decompose_wing_force(_FINE, **_KIN)

    fig, axes = plt.subplots(1, 2, figsize=(10, 5))

    for ax, comp in zip(axes, ("cf_chord", "cf_normal")):
        d = conv[comp]
        vals = [d["cf_coarse"], d["cf_medium"], d["cf_fine"]]
        color = _COLORS[comp]
        h0 = d["cf_exact_richardson"]
        gci = d["gci_fine"]
        p_obs = d["observed_order"]
        model_key, target_key = _REFERENCE_KEYS[comp]

        # Two reference lines, no shaded band between them: they are different quantities.
        ax.axhline(
            model[model_key], ls=(0, (4, 2)), lw=1.3, color=_VV_COLOR, zorder=2,
            label=_MODEL_LABEL,
        )
        ax.axhline(
            VAN_VEEN_CF_TARGETS[target_key], ls=":", lw=1.3, color="#7f7f7f", zorder=2,
            label=_TARGET_LABEL,
        )

        # Richardson extrapolant (only when monotone / p_obs > 0)
        if math.isfinite(h0) and math.isfinite(gci):
            ax.axhline(h0, ls="--", lw=1.6, color=color, alpha=0.55, zorder=2)
            ax.axhspan(h0 * (1 - gci), h0 * (1 + gci), color=color, alpha=0.08, zorder=1)
            ax.text(
                2.08, h0,
                f"Richardson\n{h0:.3f}",
                color=color, fontsize=8, va="bottom", alpha=0.8,
            )

        # CFD data line
        ax.plot(_XTICKS, vals, "o-", color=color, lw=2.2, ms=9, zorder=4)

        # Value labels above each point
        for x, v in zip(_XTICKS, vals):
            ax.annotate(
                f"{v:.3f}",
                xy=(x, v), xytext=(0, 12),
                textcoords="offset points",
                ha="center", fontsize=10, fontweight="bold", color=color,
                bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8),
                zorder=5,
            )

        # p_obs + GCI in bottom-right corner (show "N/A" for non-monotone)
        p_str = f"{p_obs:.2f}" if math.isfinite(p_obs) else "N/A"
        g_str = f"{gci * 100:.0f} %" if math.isfinite(gci) else "N/A"
        ax.text(
            0.97, 0.04,
            f"p_obs = {p_str}     GCI_fine = {g_str}",
            transform=ax.transAxes,
            ha="right", va="bottom", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", alpha=0.9),
        )

        ax.set_title(_TITLES[comp], fontsize=12, fontweight="bold", pad=10)
        ax.set_xticks(_XTICKS)
        ax.set_xticklabels(_XLABELS, fontsize=10)
        ax.set_xlim(-0.5, 2.8)
        ax.grid(axis="y", alpha=0.25, zorder=0)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=8, loc="upper right", framealpha=0.9)

    axes[0].set_ylabel("Peak body-frame |CF|  (van Veen normalization)", fontsize=10)
    fig.suptitle(
        "Flapping-wing 3-grid Richardson convergence (T3c, report-only)",
        fontsize=12, fontweight="bold", y=0.98,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight", metadata={"CreationDate": None})
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
