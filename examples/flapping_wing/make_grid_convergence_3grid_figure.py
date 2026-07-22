"""3-grid Richardson convergence figure (Tier T3c): peak body-frame CF, coarse/medium/fine.

Cluster-free — recomputes peaks and Richardson analysis directly from the three committed
IB-particle CSVs. Writes ``figures/fig_grid_convergence_3grid.{png,pdf}``.

Run: ``uv run python examples/flapping_wing/make_grid_convergence_3grid_figure.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mosquito_cfd.benchmarks.wing_convergence import (
    wing_grid_convergence_from_body_forces,
)

_HERE = Path(__file__).parent
_COARSE = _HERE / "forces_t2a_newconv.csv"
_MEDIUM = _HERE / "forces_medium.csv"
_FINE = _HERE / "forces_fine.csv"

_DX = [0.125, 0.0625, 0.03125]
_LABELS = ["Coarse\n64×32×64", "Medium\n128×64×128", "Fine\n256×128×256"]
_VAN_VEEN = {"cf_chord": (0.3, 0.43), "cf_normal": (2.4, 2.48)}  # (translational, QS model)
_TITLES = {"cf_chord": "CF_chord  (tangential)", "cf_normal": "CF_normal  (lift)"}
_COLORS = {"cf_chord": "#c44e52", "cf_normal": "#4c72b0"}


def make_figure(
    out: Path = _HERE / "figures" / "fig_grid_convergence_3grid.png",
) -> Path:
    """Draw the 3-grid Richardson convergence figure and save PNG + PDF."""
    conv = wing_grid_convergence_from_body_forces(
        _COARSE, _MEDIUM, _FINE, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8))

    for ax, comp in zip(axes, ("cf_chord", "cf_normal")):
        d = conv[comp]
        vals = [d["cf_coarse"], d["cf_medium"], d["cf_fine"]]
        color = _COLORS[comp]

        # Grid points
        ax.plot(_DX, vals, "o-", color=color, lw=2, ms=9, zorder=4, label="CFD peak")
        for dx, v in zip(_DX, vals):
            ax.annotate(
                f"{v:.3f}",
                xy=(dx, v),
                xytext=(0, 10),
                textcoords="offset points",
                ha="center",
                fontsize=9,
                fontweight="bold",
                color=color,
            )

        # Richardson extrapolant + GCI band
        h0 = d["cf_exact_richardson"]
        gci = d["gci_fine"]
        ax.axhline(h0, ls="--", lw=1.8, color=color, alpha=0.6, zorder=2,
                   label=f"Richardson extrapolant {h0:.3f}")
        ax.axhspan(h0 * (1 - gci), h0 * (1 + gci), color=color, alpha=0.10, zorder=1,
                   label=f"GCI band ±{gci*100:.0f}%")

        # Van Veen reference lines
        vv_transl, vv_model = _VAN_VEEN[comp]
        ax.axhline(vv_transl, ls=":", lw=1.5, color="#55a868", zorder=2,
                   label=f"van Veen translational ~{vv_transl}")
        if vv_model != vv_transl:
            ax.axhline(vv_model, ls=(0, (3, 1, 1, 1)), lw=1.5, color="#55a868", alpha=0.7,
                       zorder=2, label=f"van Veen QS model ~{vv_model}")

        # Annotations
        p_obs = d["observed_order"]
        ax.set_title(_TITLES[comp], fontsize=12, fontweight="bold")
        ax.set_xlabel("Grid spacing  Δx", fontsize=10)
        ax.set_xscale("log")
        ax.set_xlim(0.18, 0.02)  # coarse on left, fine on right — reversed log
        ax.set_xticks(_DX)
        ax.set_xticklabels(_LABELS, fontsize=8.5)
        ax.grid(alpha=0.25, zorder=0)
        ax.legend(fontsize=8, loc="best")

        # p_obs label
        ax.text(
            0.97, 0.97,
            f"p_obs = {p_obs:.2f}\nGCI_fine = {gci*100:.1f} %",
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=9,
            bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="gray", alpha=0.8),
        )

    axes[0].set_ylabel("Peak body-frame |CF|  (van Veen normalization)", fontsize=10)
    fig.suptitle(
        "Flapping-wing 3-grid Richardson convergence (T3c, report-only)\n"
        "coarse → medium → fine, both components monotone",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
