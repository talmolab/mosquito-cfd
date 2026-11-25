"""The settling figure: step change per wingbeat, one panel per coefficient (add-settled-beat-corpus).

Reads only ``settling_report.json`` (built by :func:`.settling.build_settling_report`), so every
plotted number is a recomputed, committed one. :func:`figure_metrics` returns exactly what is
plotted; the driver writes it beside the PNG as the figure's table view.

Encoding: colour is the configuration (fixed categorical order), line style is the grid (solid
fine, dashed coarse), every point has a marker, and a legend names all six series. The
tolerance is a grey reference line; each run's noise floor is reported in the sidecar.
"""

from __future__ import annotations

from typing import Any

from mosquito_cfd.force_surrogate.settling import TARGETS

# Categorical slots 1-3 of the reference palette, validated on the light surface (worst adjacent
# CVD Delta E 9.2; aqua is below 3:1 contrast, so the legend and the metrics sidecar carry
# identity as well as colour).
CONFIG_COLORS = {
    "s35_f085_p30": "#2a78d6",
    "s45_f100_p30": "#eb6834",
    "s55_f115_p30": "#1baf7a",
}
GRID_STYLES = {"fine": "-", "coarse": "--"}
SURFACE = "#fcfcfb"
INK = "#2b2b29"
MUTED = "#6b6a64"
TOLERANCE_GREY = "#8a8983"


def figure_metrics(report: dict[str, Any]) -> dict[str, Any]:
    """Every number the figure plots, keyed by run and target.

    Raises:
        ValueError: If a run's configuration or grid has no assigned colour or line style.
    """
    series: dict[str, dict[str, Any]] = {}
    for name, run in sorted(report["runs"].items()):
        if run["config"] not in CONFIG_COLORS:
            raise ValueError(
                f"settling figure: no colour for configuration {run['config']!r}"
            )
        if run["grid"] not in GRID_STYLES:
            raise ValueError(f"settling figure: no line style for grid {run['grid']!r}")
        series[name] = {
            target: {
                "steps": dict(run["targets"][target]["steps"]),
                "noise_floor": run["targets"][target]["noise_floor"],
            }
            for target in TARGETS
        }
    return {
        "tolerance": report["constants"]["SETTLED_TOLERANCE"],
        "decision": report.get("decision"),
        "series": series,
    }


def _legend_order(runs: dict[str, Any]) -> list[tuple[str, Any]]:
    """Runs ordered by configuration (fixed colour order), then fine before coarse."""
    config_rank = {c: i for i, c in enumerate(CONFIG_COLORS)}
    grid_rank = {g: i for i, g in enumerate(GRID_STYLES)}
    return sorted(
        runs.items(),
        key=lambda item: (config_rank[item[1]["config"]], grid_rank[item[1]["grid"]]),
    )


def render(report: dict[str, Any]):
    """Draw the figure; returns the matplotlib ``Figure``."""
    import matplotlib.pyplot as plt

    metrics = figure_metrics(report)
    fig, axes = plt.subplots(
        2, 3, figsize=(12, 7), sharex=True, sharey=True, facecolor=SURFACE
    )
    for ax, target in zip(axes.flat, TARGETS, strict=True):
        ax.set_facecolor(SURFACE)
        for name, run in _legend_order(report["runs"]):
            steps = metrics["series"][name][target]["steps"]
            beats = sorted(int(b) for b in steps)
            values = [steps[str(b)] for b in beats]
            ax.plot(
                beats,
                values,
                color=CONFIG_COLORS[run["config"]],
                linestyle=GRID_STYLES[run["grid"]],
                linewidth=2,
                marker="o",
                markersize=5,
                markeredgecolor=SURFACE,
                markeredgewidth=1,
                label=f"{run['config']} ({run['grid']})",
            )
        ax.axhline(
            metrics["tolerance"],
            color=TOLERANCE_GREY,
            linewidth=1,
            linestyle=":",
            label="1% tolerance",
        )
        ax.set_yscale("log")
        ax.set_title(target, color=INK, fontsize=11, loc="left")
        ax.grid(True, which="major", color="#e4e3df", linewidth=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c9c8c2")
        ax.tick_params(colors=MUTED, labelsize=9)
    for ax in axes[1]:
        ax.set_xlabel("wingbeat b", color=MUTED)
    fig.supylabel(
        "step change from previous beat (RMS, fraction of peak)",
        color=MUTED,
        fontsize=10,
    )
    handles, labels = axes.flat[0].get_legend_handles_labels()
    # A long sample so solid (fine) and dashed (coarse) read apart around the marker.
    fig.legend(
        handles,
        labels,
        loc="lower center",
        ncol=4,
        frameon=False,
        fontsize=9,
        labelcolor=INK,
        handlelength=4.5,
    )
    decision = metrics.get("decision") or {}
    subtitle = (
        f"decision: {decision.get('action')}, N* = {decision.get('n_star')}"
        if decision
        else "decision: not computed"
    )
    fig.suptitle(
        "Beat-to-beat step change per coefficient (8-beat settling runs)\n" + subtitle,
        color=INK,
        fontsize=12,
        x=0.01,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    return fig
