"""Per-component force-decomposition figure (Tier T4): van Veen model vs CFD, cluster-free.

Replots van Veen's (2022) quasi-steady model — translational / added-mass / Wagner / total — against
the CFD total ``ib_force`` body-frame coefficients, for the chord and normal separately, over the
steady window. Everything is recomputed from the committed IB-particle CSVs via
``decompose_wing_force`` (van Veen's *model* replotted at our operating point — NOT a digitized
figure; the time-resolved mosquito curves are van Veen Fig 13, not Fig 3-4). Writes
``figures/fig_force_decomposition.{png,pdf}``.

The plotted series are exactly the ``decompose_wing_force`` arrays (a test asserts the line ydata
equals them), so the figure can never silently drift from the graded math.

Run: ``uv run python examples/flapping_wing/make_force_decomposition_figure.py``
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mosquito_cfd.benchmarks.flapping_wing import decompose_wing_force

_HERE = Path(__file__).parent
_COARSE = _HERE / "forces_t2a_newconv.csv"
_MEDIUM = _HERE / "forces_medium.csv"


def make_figure(
    out: Path = _HERE / "figures" / "fig_force_decomposition.png",
    *,
    return_artifacts: bool = False,
):
    """Draw the chord/normal model-component vs CFD-total decomposition and save PNG + PDF.

    Args:
        out: Output PNG path (the PDF is written alongside).
        return_artifacts: If True, return ``(out, fig, result)`` with the figure left open so a
            test can inspect the plotted line data; otherwise close the figure and return ``out``.
    """
    result = decompose_wing_force(
        _COARSE,
        medium_csv=_MEDIUM,
        f_star=1.0,
        phi_amp_deg=70.0,
        pitch_amp_deg=45.0,
    )
    s = result["series"]
    t = s["time"]
    fig, (ax_chord, ax_normal) = plt.subplots(1, 2, figsize=(12, 4.6), sharex=True)
    panels = (
        (ax_chord, 0, "CF_chord (tangential)", "chord"),
        (ax_normal, 1, "CF_normal (lift)", "normal"),
    )
    for ax, idx, title, comp in panels:
        # Model components + total (van Veen model at our kinematics); CFD total on top.
        ax.plot(
            t, s["model_transl"][idx], color="#4c72b0", lw=1.4, label="translational"
        )
        ax.plot(
            t, s["model_added_mass"][idx], color="#55a868", lw=1.4, label="added-mass"
        )
        ax.plot(t, s["model_wagner"][idx], color="#c44e52", lw=1.4, label="Wagner")
        ax.plot(t, s[f"model_{comp}"], color="black", lw=2.0, label="model total")
        ax.plot(
            t,
            s[f"cfd_{comp}"],
            color="black",
            lw=1.6,
            ls="--",
            label="CFD total (ib_force)",
        )
        ax.axhline(0, color="gray", lw=0.5, ls=":")
        ax.set_title(title, fontsize=11)
        ax.set_xlabel("time (wingbeats)")
        ax.grid(alpha=0.25)
    ax_chord.set_ylabel("body-frame CF (van Veen normalization)")
    ax_normal.legend(fontsize=8, loc="upper right")
    fig.suptitle(
        "T4 per-component decomposition: van Veen model (transl + added-mass + Wagner) vs CFD total\n"
        f"normal peak model {result['normal_peak_model']:.2f} vs CFD {result['normal_peak_cfd']:.2f} "
        f"(graded, magnitude); phase gap {result['normal_peak_phase_gap']:.3f} cycle (reported)",
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    if return_artifacts:
        return out, fig, result
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
