import marimo

app = marimo.App(width="medium", app_title="E2: where do Track B's residuals cluster?")


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
    from experiments.common.data import TARGETS

    plotting.use_style()
    s = pd.read_parquet(HERE / "outputs" / "loco_summary.parquet")
    z = np.load(HERE / "outputs" / "loco_residuals.npz")
    FIG = HERE / "figures"
    return FIG, TARGETS, mo, np, pd, plotting, plt, s, z


@app.cell
def _(TARGETS, np, s, z):
    ph = z["phase"]
    resid = z["pred"] - z["cfd"][:, None]  # (27 configs, 5 seeds, 256 phases, 6 targets)
    peak = z["peak"]
    # per-config RMS over seeds at each phase, as a share of that config's peak; then median over configs
    prof_resid = np.median(np.sqrt((resid**2).mean(axis=1)) / peak[:, None, :], axis=0)
    prof_grid = np.median(np.abs(z["coarse"] - z["cfd"]) / peak[:, None, :], axis=0)
    prof_seed = np.median(z["pred"].std(axis=1) / peak[:, None, :], axis=0)
    by_target = s.groupby("target")[
        ["err_over_peak", "reversal_share_resid", "reversal_share_coarse_fine", "reversal_share_seed_var"]
    ].median().loc[list(TARGETS)]
    above = (s.reversal_share_resid > 0.2).groupby(s.target).mean().loc[list(TARGETS)]
    by_pos = s.groupby("position").err_over_peak.agg(["median", "max"]).loc[["centre", "face", "edge", "corner"]]
    worst = s.sort_values("err_over_peak").iloc[-1]
    # beat-boundary diagnostics: how sharp is the CFD waveform's kink where phase wraps, and which
    # way does the seed-mean residual lean just after phase 0 and just before phase 1?
    _ext = np.concatenate([z["cfd"][:, -3:], z["cfd"], z["cfd"][:, :3]], axis=1)
    _d2 = np.abs(np.diff(_ext, 2, axis=1))
    kink = dict(zip(TARGETS, np.median(_d2[:, 1:5].max(axis=1) / np.median(_d2, axis=1), axis=0)))
    _mean_resid = resid.mean(axis=1)
    after = dict(zip(TARGETS, (_mean_resid[:, :5].mean(axis=1) > 0).mean(axis=0)))
    before = dict(zip(TARGETS, (_mean_resid[:, 251:].mean(axis=1) > 0).mean(axis=0)))
    return above, after, before, by_pos, by_target, kink, ph, prof_grid, prof_resid, prof_seed, worst


@app.cell
def _(above, after, before, by_pos, by_target, kink, mo, worst):
    mo.md(
        f"""
        # E2. Where do Track B's residuals cluster?

        ## Question
        Are the kinematics-only surrogate's errors concentrated at stroke reversal, in particular
        components, or in particular corners of the sweep? Stroke reversal is where the literature
        puts the history-dependent effects (wake capture, rotational forces) that instantaneous
        kinematics cannot see, so a reversal peak would be a physical signal, not a fit artefact.

        ## Method
        Leave-one-config-out over all 27 fine-grid configs: each config is predicted by models
        that never saw it, 5 seeds each (135 fits). For each left-out config, validation is 4 of
        the other 26, drawn by the seed. Residuals are taken on a 256-point phase grid over the
        second beat and divided by that config's peak CFD magnitude.

        The **reversal share** is the fraction of a component's squared error that falls within
        0.05 of a stroke reversal (phase 0.25 and 0.75, where the stroke angle is extremal). Errors
        spread evenly over the beat would give 0.20.

        **Data used:** `examples/prelim_sweep_fine/dataset.parquet` at `80d653a` (re-extracted in
        #146), second beat, all 27 configs; `examples/prelim_sweep/dataset.parquet` for the
        coarse-versus-fine profile.

        ## Result
        **The residuals do not cluster at stroke reversal.** The median reversal share is
        {by_target.reversal_share_resid.min():.2f} to {by_target.reversal_share_resid.max():.2f}
        across the six components, below the 0.20 an even spread would give. It exceeds 0.20 in
        {above.min():.0%} to {above.max():.0%} of configs depending on the component, so there is
        no consistent excess.

        **The errors are small everywhere, including configs the model has to extrapolate to.**
        Median error is {by_pos.loc["centre", "median"]:.1%} of peak for the centre config,
        {by_pos.loc["face", "median"]:.1%} for face centres, {by_pos.loc["edge", "median"]:.1%}
        for edges and {by_pos.loc["corner", "median"]:.1%} for corners. The single worst case is
        `{worst.config}` `{worst.target}` at {worst.err_over_peak:.1%}.

        **The one clear feature in phase is at the beat boundary, not at reversal.** For `CF_x`,
        `CF_z`, `CF_mx` and `CF_mz` the residual is largest at phase 0 and 1 (figure below), and
        the cause is in the CFD, not the model:

        - Where the second beat's end is joined to its own start, the CFD waveform has a kink
          {kink["CF_z"]:.0f} to {kink["CF_mz"]:.0f} times sharper than anywhere else in the beat
          for those four components (second difference at the wrap over its typical value;
          `CF_y` and `CF_my` show about {kink["CF_y"]:.0f}).
        - The residual changes sign across it in nearly every config: for `CF_z` the surrogate is
          too low just after phase 0 in {1 - after["CF_z"]:.0%} of configs and too high just
          before phase 1 in {before["CF_z"]:.0%}.

        The model's phase input is periodic, so it predicts one smooth curve through a point where
        the CFD's second beat does not close on itself (E0). The spike is the surrogate averaging
        across a flow that is not yet periodic.

        **The rest of the structure is in the parameters.** Error is higher at the ends of each
        swept range than in the middle (below), and the six largest errors are all `CF_my` at
        30 degrees pitch.
        """
    )
    return


@app.cell
def _(by_target, mo):
    mo.ui.table(
        by_target.reset_index().round(3).rename(columns={
            "err_over_peak": "error / peak (median over configs)",
            "reversal_share_resid": "reversal share: surrogate residual",
            "reversal_share_coarse_fine": "reversal share: coarse-fine CFD difference",
            "reversal_share_seed_var": "reversal share: seed-to-seed variance",
        }),
        selection=None,
    )
    return


@app.cell
def _(FIG, TARGETS, ph, plotting, plt, prof_grid, prof_resid, prof_seed):
    def phase_figure():
        fig, axes = plt.subplots(2, 3, figsize=(11, 5.6), sharex=True)
        for j, (ax, t) in enumerate(zip(axes.ravel(), TARGETS)):
            ax.plot(ph, prof_resid[:, j], color=plotting.SERIES[0], label="surrogate residual (RMS over seeds)")
            ax.plot(ph, prof_seed[:, j], color=plotting.SERIES[2], lw=1.5, label="seed-to-seed spread")
            ax.set_title(t)
            for r in (0.25, 0.75):
                ax.axvspan(r - 0.05, r + 0.05, color=plotting.GRID, alpha=0.6, lw=0)
            ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:.2f}%")
            ax.set_ylim(bottom=0)
        axes[0, 0].legend(loc="upper left", fontsize=7.5)
        for ax in axes[1]:
            ax.set_xlabel("phase (shaded: stroke reversal +/- 0.05)")
        for ax in axes[:, 0]:
            ax.set_ylabel("share of peak")
        fig.suptitle("Leave-one-config-out residual through the beat (median over 27 configs)",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "residual_by_phase.png")

        fig2, axes2 = plt.subplots(2, 3, figsize=(11, 5.6), sharex=True)
        for j, (ax, t) in enumerate(zip(axes2.ravel(), TARGETS)):
            ax.plot(ph, prof_grid[:, j], color=plotting.SERIES[1], label="coarse vs fine CFD")
            ax.plot(ph, prof_resid[:, j], color=plotting.SERIES[0], label="surrogate residual")
            ax.set_title(t)
            for r in (0.25, 0.75):
                ax.axvspan(r - 0.05, r + 0.05, color=plotting.GRID, alpha=0.6, lw=0)
            ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:.0f}%")
            ax.set_ylim(bottom=0)
        axes2[0, 0].legend(loc="upper left", fontsize=7.5)
        for ax in axes2[1]:
            ax.set_xlabel("phase (shaded: stroke reversal +/- 0.05)")
        for ax in axes2[:, 0]:
            ax.set_ylabel("share of peak")
        fig2.suptitle("The same residual beside the coarse-versus-fine CFD difference",
                      x=0.02, ha="left", fontweight="bold")
        fig2.tight_layout()
        plotting.save(fig2, FIG / "residual_vs_grid_difference_by_phase.png")
        return FIG / "residual_by_phase.png", FIG / "residual_vs_grid_difference_by_phase.png"

    phase_png, grid_png = phase_figure()
    return grid_png, phase_png


@app.cell
def _(mo, phase_png):
    mo.image(src=str(phase_png))
    return


@app.cell
def _(grid_png, mo):
    mo.image(src=str(grid_png))
    return


@app.cell
def _(FIG, TARGETS, plotting, plt, s):
    def parameter_figure():
        fig, axes = plt.subplots(1, 4, figsize=(12, 3.6), sharey=True)
        specs = [("stroke_amp_deg", "stroke amplitude (deg)"), ("frequency_fstar", "frequency f*"),
                 ("pitch_amp_deg", "pitch amplitude (deg)")]
        for ax, (col, label) in zip(axes, specs):
            for t in TARGETS:
                g = s[s.target == t].groupby(col).err_over_peak.median()
                ax.plot(range(len(g)), g.to_numpy(), "o-", color=plotting.TARGET_COLOR[t], ms=6, lw=1.6, label=t)
            ax.set_xticks(range(len(g)), [f"{v:g}" for v in g.index])
            ax.set_xlabel(label)
        order = ["centre", "face", "edge", "corner"]
        for t in TARGETS:
            g = s[s.target == t].groupby("position").err_over_peak.median().loc[order]
            axes[3].plot(range(4), g.to_numpy(), "o-", color=plotting.TARGET_COLOR[t], ms=6, lw=1.6)
        axes[3].set_xticks(range(4), ["centre\n(1)", "face\n(6)", "edge\n(12)", "corner\n(8)"])
        axes[3].set_xlabel("position in the 3x3x3 sweep")
        axes[0].set_ylabel("median error / peak")
        axes[0].yaxis.set_major_formatter(lambda v, _: f"{100 * v:.1f}%")
        axes[0].set_ylim(bottom=0)
        axes[0].legend(ncol=2, fontsize=8, loc="lower center")
        fig.suptitle("Left-out error by swept parameter and by position in the sweep",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "residual_by_parameter.png")
        return FIG / "residual_by_parameter.png"

    param_png = parameter_figure()
    return (param_png,)


@app.cell
def _(mo, param_png):
    mo.image(src=str(param_png))
    return


@app.cell
def _(FIG, TARGETS, plotting, plt, s):
    def heatmap():
        piv = s.pivot(index="config", columns="target", values="err_over_peak")[list(TARGETS)]
        fig, ax = plt.subplots(figsize=(6.2, 7.5))
        im = ax.imshow(piv.to_numpy(), aspect="auto", cmap=plotting.SEQ, vmin=0)
        ax.set_xticks(range(6), TARGETS)
        held = s.drop_duplicates("config").set_index("config").committed_split
        ax.set_yticks(range(len(piv)), [f"{c}{' *' if held[c] == 'holdout' else ''}" for c in piv.index], fontsize=8)
        ax.grid(False)
        vmax = piv.to_numpy().max()
        for i in range(piv.shape[0]):
            for j in range(6):
                v = piv.iat[i, j]
                ax.text(j, i, f"{100 * v:.1f}", ha="center", va="center", fontsize=7,
                        color="#ffffff" if v > 0.55 * vmax else plotting.INK)
        ax.set_title("Left-out error, % of peak (* = committed holdout config)")
        fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, format=lambda v, _: f"{100 * v:.1f}%")
        plotting.save(fig, FIG / "residual_heatmap.png")
        return FIG / "residual_heatmap.png"

    heat_png = heatmap()
    return (heat_png,)


@app.cell
def _(heat_png, mo):
    mo.image(src=str(heat_png))
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **This does not show there are no history effects in the flow.** On periodic hover the
          flow history is itself a function of the config and the phase, so a model given both can
          learn whatever the history does. The test only shows that nothing at reversal is harder
          to fit than the rest of the beat. A command that changes mid-run is the case where
          history could show up as error.
        - The kinematics here pitch the wing through horizontal at reversal (#142), which is not
          what insects do, so reversal in this corpus is not the reversal the literature describes.
        - Every residual is far below the CFD's own beat-to-beat and grid differences (E0, E1), so
          the pattern in these errors is a pattern inside the CFD's noise.
        - The 0.05 window around reversal is a choice; the phase profiles below show the whole beat.
        - Leave-one-config-out uses 22 training configs, one more than the committed split, and a
          4-config validation carve, so these errors are not directly comparable to E1's.
        - Seed ranges mix validation-carve and initialisation variation.

        ## Next step
        The useful follow-up is not on this corpus: run the commanded-change configs and repeat
        this residual-by-phase analysis on the beats after the switch, where a kinematics-only
        model has no way to know what the wake looked like before.
        """
    )
    return


if __name__ == "__main__":
    app.run()
