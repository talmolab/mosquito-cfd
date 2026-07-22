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
    ("Coarse  64×32×64",   _HERE / "forces_t2a_newconv.csv", "#aec7e8", 1.2),
    ("Medium  128×64×128", _HERE / "forces_medium.csv",      "#4c72b0", 1.6),
    ("Fine    256×128×256",_HERE / "forces_fine.csv",         "#08306b", 2.0),
]
_KIN = dict(f_star=1.0, phi_amp_deg=70.0, pitch_amp_deg=45.0)
_WINDOW_T0 = 0.05


def make_figure(
    out: Path = _HERE / "figures" / "fig_force_timeseries_3grid.png",
) -> Path:
    """Draw CF_chord and CF_normal time series for all 3 grids and save PNG + PDF."""
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True)
    ax_chord, ax_normal = axes

    for label, csv, color, lw in _grids_sorted():
        d = reconstruct_wing_body_forces(csv, **_KIN)
        mask = d.time >= _WINDOW_T0
        ax_chord.plot(d.time[mask], d.cf_chord[mask], color=color, lw=lw,
                      label=label, alpha=0.92)
        ax_normal.plot(d.time[mask], np.abs(d.cf_normal[mask]), color=color, lw=lw,
                       label=label, alpha=0.92)

    # Styling
    for ax, ylabel, title in [
        (ax_chord,  "CF_chord  (tangential)",   "CF_chord — body-frame tangential force"),
        (ax_normal, "|CF_normal|  (lift)",       "CF_normal — body-frame lift force"),
    ]:
        ax.set_ylabel(ylabel, fontsize=10)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.axhline(0, color="k", lw=0.6, ls="--", alpha=0.4)
        ax.grid(alpha=0.2)
        ax.legend(fontsize=9, loc="upper left")

    # Van Veen reference bands
    ax_chord.axhspan(0.3, 0.43, color="#55a868", alpha=0.12,
                     label="van Veen target range 0.3–0.43")
    ax_normal.axhspan(2.16, 2.48, color="#4c72b0", alpha=0.10,
                      label="van Veen / Richardson range 2.16–2.48")

    ax_normal.set_xlabel("Time  (wingbeats)", fontsize=10)
    ax_normal.set_xlim(_WINDOW_T0, 1.0)

    fig.suptitle(
        "Body-frame force coefficients — coarse / medium / fine grid overlay  (T3c)\n"
        "van Veen normalization,  F_ref = 200.27,  steady window t ≥ 0.05",
        fontsize=11, fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return out


def _grids_sorted():
    return _GRIDS


if __name__ == "__main__":
    print("wrote", make_figure())
