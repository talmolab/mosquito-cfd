import marimo

app = marimo.App(width="medium", app_title="E0: are two beats enough?")


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    HERE = Path(__file__).parent
    sys.path.insert(0, str(HERE.parents[1]))
    from experiments.common import plotting
    from experiments.common.data import TARGETS, load_dataset, waveforms

    plotting.use_style()
    d = pd.read_parquet(HERE / "outputs" / "beat_diff.parquet")
    prof = np.load(HERE / "outputs" / "beat_diff_profiles.npz")
    FIG = HERE / "figures"
    return FIG, TARGETS, d, load_dataset, mo, np, plotting, plt, prof, waveforms


@app.cell
def _(TARGETS, d):
    cols = ["rms_over_peak", "rms_over_peak_first_half", "rms_over_peak_second_half", "mean_shift_over_peak"]
    med = d.groupby(["grid", "target"])[cols].median()
    rng = d.groupby(["grid", "target"])["rms_over_peak"].agg(["min", "max"])
    summary = med.join(rng).loc[[(g, t) for g in ("fine", "coarse") for t in TARGETS]]
    fine = summary.loc["fine"]
    worst, best = fine["rms_over_peak"].idxmax(), fine["rms_over_peak"].idxmin()
    return best, fine, summary, worst


@app.cell
def _(best, fine, mo, worst):
    mo.md(
        f"""
        # E0. Are two beats enough?

        ## Question
        Every run in both corpora is two wingbeats long and the surrogate trains on the second.
        How different are the two beats, per force and moment component?

        ## Method
        For each of the 27 configs, on each grid, both beats are resampled onto one 256-point phase
        grid and subtracted. The difference is reported as its RMS over the beat divided by the
        second beat's peak magnitude. Phase below 0.05 is excluded so the impulsive-start spike in beat 1
        (visible in the overlay below, gone by about phase 0.03) does not count. No model is involved; this is CFD against itself.

        **Data used:** `examples/prelim_sweep/dataset.parquet` and
        `examples/prelim_sweep_fine/dataset.parquet` at `80d653a` (re-extracted in #146), all 27
        configs, both beats. No duplicated time rows were found in either dataset.

        ## Result
        **The second beat is not a repeat of the first.** On the fine grid the median
        beat-to-beat difference ranges from {fine.loc[best, "rms_over_peak"]:.1%} of peak
        (`{best}`) to {fine.loc[worst, "rms_over_peak"]:.1%} of peak (`{worst}`).

        - `CF_z`, `CF_mx` and `CF_my` change by {fine.loc["CF_z", "rms_over_peak"]:.0%},
          {fine.loc["CF_mx", "rms_over_peak"]:.0%} and {fine.loc["CF_my", "rms_over_peak"]:.0%} of
          peak between beats. For `CF_z` the difference in the second half of the beat
          ({fine.loc["CF_z", "rms_over_peak_second_half"]:.0%}) is about as large as in the first
          half ({fine.loc["CF_z", "rms_over_peak_first_half"]:.0%}), so it is not a start-up
          effect that has died away by mid-beat.
        - `CF_x`, `CF_y` and `CF_mz` change by {fine.loc["CF_mz", "rms_over_peak"]:.0%} to
          {fine.loc["CF_y", "rms_over_peak"]:.0%} of peak. Their second-half difference
          ({fine.loc["CF_x", "rms_over_peak_second_half"]:.1%} for `CF_x`) is smaller than the
          first-half one ({fine.loc["CF_x", "rms_over_peak_first_half"]:.1%}), so these are
          settling, slowly.
        - The change in `CF_z` is mostly a downward shift: its beat-mean drops by
          {-fine.loc["CF_z", "mean_shift_over_peak"]:.0%} of peak from beat 1 to beat 2 (median
          over configs). That is the direction expected if the wing's own downwash is still
          building up, which is an interpretation, not something this experiment tests.
        - The pattern is the same on the coarse grid, and it is largest at low pitch amplitude
          (30 degrees) in every stroke and frequency group.
        """
    )
    return


@app.cell
def _(mo, summary):
    mo.ui.table(
        summary.reset_index()
        .round(4)
        .rename(
            columns={
                "rms_over_peak": "median RMS diff / peak",
                "rms_over_peak_first_half": "first half of beat",
                "rms_over_peak_second_half": "second half of beat",
                "mean_shift_over_peak": "median mean shift / peak",
                "min": "min over configs",
                "max": "max over configs",
            }
        ),
        selection=None,
    )
    return


@app.cell
def _(FIG, TARGETS, d, plotting, plt):
    def heatmaps():
        fig, axes = plt.subplots(1, 2, figsize=(11, 7.5), sharey=True)
        vmax = float(d["rms_over_peak"].max())
        for ax, g in zip(axes, ("fine", "coarse")):
            piv = d[d.grid == g].pivot(index="config", columns="target", values="rms_over_peak")[list(TARGETS)]
            im = ax.imshow(piv.to_numpy(), aspect="auto", cmap=plotting.SEQ, vmin=0, vmax=vmax)
            ax.set_xticks(range(6), TARGETS)
            ax.set_yticks(range(len(piv)), piv.index, fontsize=8)
            ax.grid(False)
            for i in range(piv.shape[0]):
                for j in range(6):
                    v = piv.iat[i, j]
                    ax.text(j, i, f"{100 * v:.0f}", ha="center", va="center", fontsize=7,
                            color="#ffffff" if v > 0.55 * vmax else plotting.INK)
            ax.set_title(f"{g} grid")
        fig.suptitle("Beat 1 vs beat 2: RMS difference as % of the second beat's peak",
                     x=0.02, ha="left", fontweight="bold")
        fig.colorbar(im, ax=axes, fraction=0.03, pad=0.02, format=lambda v, _: f"{100 * v:.0f}%")
        plotting.save(fig, FIG / "beat_difference_heatmap.png")
        return FIG / "beat_difference_heatmap.png"

    heat_png = heatmaps()
    return (heat_png,)


@app.cell
def _(heat_png, mo):
    mo.image(src=str(heat_png))
    return


@app.cell
def _(FIG, TARGETS, load_dataset, plotting, plt, waveforms):
    def overlay(cfg="s45_f100_p45"):
        df = load_dataset("fine")
        df = df[df.config_name == cfg]
        w0, w1 = waveforms(df, wingbeat=0)[cfg], waveforms(df, wingbeat=1)[cfg]
        ph = [i / 256 for i in range(256)]
        fig, axes = plt.subplots(2, 3, figsize=(11, 5.2), sharex=True)
        for j, (ax, t) in enumerate(zip(axes.ravel(), TARGETS)):
            ax.plot(ph, w0[:, j], color=plotting.MUTED, lw=1.5, label="beat 1")
            ax.plot(ph, w1[:, j], color=plotting.SERIES[0], label="beat 2")
            ax.set_title(t)
            lo, hi = w1[:, j].min(), w1[:, j].max()
            ax.set_ylim(lo - 0.25 * (hi - lo), hi + 0.25 * (hi - lo))  # clips the beat-1 start spike
            for r in (0.25, 0.75):
                ax.axvline(r, color=plotting.AXIS, lw=0.8, ls=":")
        axes[0, 0].legend(loc="best")
        for ax in axes[1]:
            ax.set_xlabel("phase (dotted: stroke reversal)")
        fig.suptitle(f"Fine grid, centre config {cfg}: the two beats overlaid (start spike clipped)",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "beats_overlaid_centre_config.png")
        return FIG / "beats_overlaid_centre_config.png"

    overlay_png = overlay()
    return (overlay_png,)


@app.cell
def _(mo, overlay_png):
    mo.image(src=str(overlay_png))
    return


@app.cell
def _(FIG, TARGETS, d, np, plotting, plt, prof):
    def profile():
        ph = prof["phase"]
        keep = ph >= 0.05
        fig, axes = plt.subplots(2, 3, figsize=(11, 5.2), sharex=True, sharey=True)
        for j, (ax, t) in enumerate(zip(axes.ravel(), TARGETS)):
            for g, color in (("coarse", plotting.MUTED), ("fine", plotting.SERIES[0])):
                sub = d[(d.grid == g) & (d.target == t)].set_index("config")
                curves = []
                for cfg in sub.index:
                    diff = prof[f"{g}/{cfg}"][:, j]
                    peak = np.sqrt(np.mean(diff[keep] ** 2)) / sub.loc[cfg, "rms_over_peak"]
                    curves.append(np.abs(diff) / peak)
                ax.plot(ph[keep], np.median(curves, axis=0)[keep], color=color, label=g)
            ax.set_title(t)
            for r in (0.25, 0.75):
                ax.axvline(r, color=plotting.AXIS, lw=0.8, ls=":")
            ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
        axes[0, 0].legend(loc="best")
        for ax in axes[1]:
            ax.set_xlabel("phase (dotted: stroke reversal)")
        for ax in axes[:, 0]:
            ax.set_ylabel("|beat 2 - beat 1| / peak")
        fig.suptitle("Where in the beat the two beats differ (median over 27 configs)",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "beat_difference_by_phase.png")
        return FIG / "beat_difference_by_phase.png"

    profile_png = profile()
    return (profile_png,)


@app.cell
def _(mo, profile_png):
    mo.image(src=str(profile_png))
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **Two beats cannot show convergence.** This measures the change from beat 1 to beat 2. It
          cannot say how much beat 3 would differ from beat 2. A difference that has not shrunk by
          the end of beat 2 suggests the flow is still developing, but only a longer run can show
          where it settles.
        - Beat 1 starts from fluid at rest, so some difference is expected; the question is its
          size and whether it is decaying.
        - The normalization is each config's own second-beat peak, so a component with a small
          peak can show a large percentage from a small absolute change.
        - Lab-frame coefficients; nothing here is body-frame.

        ## Next step
        Run one coarse config for six beats on the local A5000 (approved) and measure the
        beat-to-beat change directly. Until then, treat every "error versus CFD" number from the
        two-beat corpora as error against a flow that may still be developing, especially for
        `CF_z`, `CF_mx` and `CF_my`.
        """
    )
    return


if __name__ == "__main__":
    app.run()
