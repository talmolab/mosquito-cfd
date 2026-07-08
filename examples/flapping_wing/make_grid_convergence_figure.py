"""Grid-convergence figure (Tier T3b): peak body-frame CF, coarse vs medium, vs van Veen.

Cluster-free — recomputes the coarse->medium relative change + 2-grid GCI band directly from the two
committed IB-particle CSVs (via ``wing_grid_convergence_from_body_forces``), so the headline
convergence figure is reproducible with no cluster access. Writes
``figures/fig_grid_convergence.{png,pdf}``.

Run: ``uv run python examples/flapping_wing/make_grid_convergence_figure.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mosquito_cfd.benchmarks.wing_convergence import (
    wing_grid_convergence_from_body_forces,
)

_HERE = Path(__file__).parent
_COARSE = _HERE / "forces_t2a_newconv.csv"
_MEDIUM = _HERE / "forces_medium.csv"
_VAN_VEEN = {"cf_chord": 0.3, "cf_normal": 2.4}  # van Veen 2022 translational reference
_LABELS = {
    "cf_chord": "CF_chord (tangential)",
    "cf_normal": "CF_normal (lift)",
}


def make_figure(out: Path = _HERE / "figures" / "fig_grid_convergence.png") -> Path:
    """Draw the coarse->medium peak-CF convergence bar chart and save PNG + PDF."""
    conv = wing_grid_convergence_from_body_forces(
        _COARSE, _MEDIUM, f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0
    )
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2))
    for ax, comp in zip(axes, ("cf_chord", "cf_normal")):
        d = conv[comp]
        coarse, medium, ref = d["cf_coarse"], d["cf_medium"], _VAN_VEEN[comp]
        bars = ax.bar(
            [0, 1],
            [coarse, medium],
            width=0.55,
            color=["#c44e52", "#4c72b0"],
            edgecolor="black",
            zorder=3,
        )
        ax.axhline(
            ref,
            ls="--",
            lw=2,
            color="#55a868",
            zorder=2,
            label=f"van Veen 2022 ~ {ref}",
        )
        for b, v in zip(bars, (coarse, medium)):
            ax.text(
                b.get_x() + b.get_width() / 2,
                v + 0.02 * max(coarse, ref),
                f"{v:.3f}",
                ha="center",
                va="bottom",
                fontsize=10,
                fontweight="bold",
            )
        ax.annotate(
            f"{100 * d['relative_change']:+.1f}%\n(GCI {d['gci_p2']:.2f}-{d['gci_p1']:.2f})",
            xy=(1, medium),
            xytext=(0.5, max(coarse, ref) * 0.72),
            ha="center",
            fontsize=9,
            arrowprops=dict(arrowstyle="->", color="gray"),
        )
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["coarse\n64x32x64", "medium\n128x64x128"])
        ax.set_title(_LABELS[comp], fontsize=11)
        ax.set_ylim(0, max(coarse, ref) * 1.25)
        ax.grid(axis="y", alpha=0.3, zorder=0)
        ax.legend(fontsize=8, loc="upper right")
    axes[0].set_ylabel("peak body-frame |CF|  (van Veen normalization)")
    fig.suptitle(
        "Flapping-wing grid convergence (T3b): peak force coefficients, coarse -> medium (report-only)",
        fontsize=12,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
