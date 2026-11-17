"""Figure for E7: held-out field error against number of modes, prediction beside its two yardsticks."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from experiments.common.plotting import SERIES, save, use_style

HERE = Path(__file__).parent
TITLES = {"wing": "Wing-fixed box, wing axes", "lab_patch": "Whole near-wing patch, lab axes"}


def main() -> None:
    use_style()
    s = pd.read_parquet(HERE / "outputs" / "summary.parquet")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    for ax, (frame, title) in zip(axes, TITLES.items()):
        d = s[s.frame == frame]
        ax.axhline(100 * d.nearest.iloc[0], color=SERIES[2], lw=2)
        ax.plot(d.r, 100 * d.prediction, "o-", color=SERIES[1], lw=2, ms=7)
        ax.plot(d.r, 100 * d.reconstruction, "o-", color=SERIES[0], lw=2, ms=7)
        x = d.r.iloc[-1]
        ax.annotate("nearest training snapshot (no model)", (x, 100 * d.nearest.iloc[0]), xytext=(0, 5),
                    textcoords="offset points", ha="right", va="bottom")
        ax.annotate("predicted from kinematics", (x, 100 * d.prediction.iloc[-1]), xytext=(0, 6),
                    textcoords="offset points", ha="right", va="bottom")
        ax.annotate("rebuilt from the CFD snapshot", (64, 100 * d.reconstruction[d.r == 64].iloc[0]), xytext=(-10, -2),
                    textcoords="offset points", ha="right", va="top")
        ax.set_xscale("log", base=2)
        ax.set_xticks(list(d.r), [str(r) for r in d.r])
        ax.set_xlabel("POD modes")
        ax.set_title(title, loc="left")
        ax.set_ylim(0, 60)
    axes[0].set_ylabel("held-out velocity error (% of fluctuation)")
    fig.suptitle("Flow field of 6 unseen configs, predicted from kinematics and phase alone", x=0.01, ha="left")
    fig.tight_layout()
    save(fig, HERE / "figures" / "kin2field_error.png")


if __name__ == "__main__":
    main()
