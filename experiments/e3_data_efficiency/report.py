import marimo

app = marimo.App(width="medium", app_title="E3: data efficiency")


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
    c = pd.read_parquet(HERE / "outputs" / "curve.parquet")
    ridge = pd.read_parquet(HERE.parent / "e4_ablations" / "outputs" / "ridge_curve.parquet")
    chosen = pd.read_parquet(HERE.parent / "e4_ablations" / "outputs" / "ridge_chosen.parquet")
    FIG = HERE / "figures"
    return FIG, TARGETS, c, chosen, mo, np, pd, plotting, plt, ridge


@app.cell
def _(c, np, pd, ridge):
    # one number per fit: mean skill over the six targets
    fit = c.groupby(["design", "n", "job", "subset_seed", "init_seed"], dropna=False).agg(
        skill=("skill", "mean"), row_stride=("row_stride", "first")).reset_index()
    rnd = fit[fit.design == "random"]
    curve = rnd.groupby("n").skill.agg(["median", "min", "max"])
    curve["worse than baseline"] = rnd.groupby("n").skill.apply(lambda s: float((s < 0).mean()))
    per_target = c[c.design == "random"].groupby(["n", "target"]).skill.median().unstack()

    def variance_split(g):
        total = g.skill.var(ddof=0)
        between_subset = g.groupby("subset_seed").skill.mean().var(ddof=0)
        return pd.Series({"spread (std)": np.sqrt(total),
                          "share from which configs were drawn": between_subset / total if total > 0 else np.nan})

    split = rnd.groupby("n")[["skill", "subset_seed"]].apply(variance_split)
    structured = fit[fit.design.isin(["corners_centre", "star", "random_fixed_epochs"])].groupby(
        ["design", "n"]).skill.agg(["median", "min", "max"])
    thin = fit[fit.design == "row_thinning"].groupby("row_stride").skill.agg(["median", "min", "max"])
    rcurve = ridge[ridge.design == "random"].groupby("n").skill.agg(["median", "min", "max"])
    rstruct = ridge[ridge.design != "random"].set_index("design").skill
    return curve, fit, per_target, rcurve, rnd, rstruct, split, structured, thin


@app.cell
def _(chosen, curve, mo, rcurve, rstruct, structured, thin):
    _h, _d = int(chosen.harmonics.iloc[0]), int(chosen.degree.iloc[0])
    mo.md(
        f"""
        # E3. How many CFD configs did the hover surrogate need?

        ## Question
        The fine corpus cost about 61 A40-hours for 27 configs. How does held-out skill fall as
        configs are taken away, does a designed subset beat a random one, and how densely in time
        does the force need to be sampled?

        ## Method
        The 6 held-out configs are fixed. From the other 21, nested random subsets of
        n = 3, 6, ..., 21 configs are drawn 5 times; each is trained with 5 initialisations
        (25 fits per n). **n counts every CFD run used**: about one in seven of the n configs is
        set aside for validation, at least one. Skill is 1 - MSE / MSE of the phase-only baseline,
        with the baseline rebuilt from the same n configs, averaged over the six targets.

        Alongside: two designed subsets (the 8 corners plus the centre; the centre plus the 5
        available face centres), trained for a fixed 2000 epochs with no validation set, and the
        same-size random subsets trained the same way for a fair comparison. The ridge comparator
        chosen in E4 ({_h} Fourier harmonics x degree-{_d} polynomials) is scored on the same
        subsets. Finally the training rows are thinned to every k-th time step.

        **Data used:** `examples/prelim_sweep_fine/dataset.parquet` at `80d653a` (re-extracted in
        #146), second beat.

        ## Result
        **About 15 configs are enough for the MLP; below 12 the result depends on which configs
        you happened to run.**

        - Median skill is {curve.loc[21, "median"]:.3f} at n = 21, {curve.loc[18, "median"]:.3f}
          at 18 and {curve.loc[15, "median"]:.3f} at 15, with every fit at n >= 15 above
          {curve.loc[15, "min"]:.2f}.
        - At n = 12 the median is still {curve.loc[12, "median"]:.3f} but the worst fit drops to
          {curve.loc[12, "min"]:.2f}; at n = 9 the range is {curve.loc[9, "min"]:.2f} to
          {curve.loc[9, "max"]:.2f}; at n = 6 the median is {curve.loc[6, "median"]:.2f}; and at
          n = 3 every fit is worse than the phase-only baseline.

        **Designed subsets did not beat random ones.** Corners plus centre (9 runs) reaches
        {structured.loc[("corners_centre", 9), "median"]:.3f}, against
        {structured.loc[("random_fixed_epochs", 9), "median"]:.3f} for random 9-config subsets
        trained the same way. The one-factor-at-a-time star (6 runs) fails outright at
        {structured.loc[("star", 6), "median"]:.2f}, against
        {structured.loc[("random_fixed_epochs", 6), "median"]:.2f} for random 6-config subsets: it
        contains no config where two parameters change together.

        **The ridge model needs the nearly full grid.** It is the best model at n = 21
        ({rcurve.loc[21, "median"]:.4f}) and matches that at 18 in the median
        ({rcurve.loc[18, "median"]:.4f}), but at 15 its range is {rcurve.loc[15, "min"]:.2f} to
        {rcurve.loc[15, "max"]:.3f} and below that it is worse than the baseline. On corners plus
        centre it scores {rstruct["corners_centre"]:.2f}. Its polynomial terms extrapolate badly
        when a level of a parameter is missing; the MLP degrades more gracefully.

        **Time resolution of the force output is not a constraint.** Keeping every 100th row
        (about 20 force samples per beat instead of about 2000) leaves skill at
        {thin.loc[100.0, "median"]:.3f}, against {thin.loc[1.0, "median"]:.3f} with every row.
        """
    )
    return


@app.cell
def _(curve, mo, split):
    mo.ui.table(curve.join(split).reset_index().round(3), selection=None)
    return


@app.cell
def _(FIG, curve, fit, np, plotting, plt, rcurve, rnd):
    def curve_figure():
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), gridspec_kw={"width_ratios": [1.25, 1]})
        ax = axes[0]
        n = curve.index.to_numpy()
        ax.fill_between(n, curve["min"].clip(lower=-0.5), curve["max"], color=plotting.SERIES[0], alpha=0.2, lw=0)
        ax.plot(n, curve["median"].clip(lower=-0.5), "o-", color=plotting.SERIES[0], label="MLP, random subsets (median, range of 25)")
        ax.plot(rcurve.index, rcurve["median"].clip(lower=-0.5), "s--", color=plotting.SERIES[1], lw=1.6,
                label="ridge, same subsets (median of 5)")
        for design, marker, label in (("corners_centre", "D", "MLP, 8 corners + centre"), ("star", "X", "MLP, centre + 5 face centres")):
            g = fit[fit.design == design]
            ax.plot(g.n.iloc[0], max(g.skill.median(), -0.5), marker, color=plotting.SERIES[2], ms=9,
                    mec=plotting.SURFACE, mew=1.5, ls="none", label=label)
        ax.axhline(0, color=plotting.AXIS, lw=1)
        ax.set_ylim(-0.55, 1.03)
        ax.set_xticks(n)
        ax.set_xlabel("CFD configs used (training + validation)")
        ax.set_ylabel("held-out skill over the phase-only baseline")
        ax.set_title("Whole range (values below -0.5 are drawn at -0.5)")
        ax.legend(loc="lower right", fontsize=8)

        ax = axes[1]
        sub = rnd[rnd.n >= 12]
        rng = np.random.default_rng(0)
        ax.plot(sub.n + rng.uniform(-0.5, 0.5, len(sub)), sub.skill, "o", color=plotting.SERIES[0], ms=4, alpha=0.55, mew=0)
        ax.plot(curve.index[curve.index >= 12], curve["median"][curve.index >= 12], "-", color=plotting.SERIES[0])
        ax.plot(rcurve.index[rcurve.index >= 15], rcurve["median"][rcurve.index >= 15], "s--", color=plotting.SERIES[1], lw=1.6)
        ax.set_ylim(0.9, 1.002)
        ax.set_xticks([12, 15, 18, 21])
        ax.set_xlabel("CFD configs used")
        ax.set_title("Zoom: every MLP fit at n >= 12")
        fig.suptitle("Held-out skill against the number of CFD configs", x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "data_efficiency.png")
        return FIG / "data_efficiency.png"

    curve_png = curve_figure()
    return (curve_png,)


@app.cell
def _(curve_png, mo):
    mo.image(src=str(curve_png))
    return


@app.cell
def _(mo, per_target, structured, thin):
    mo.vstack([
        mo.md("**Median skill per target, random subsets**"),
        mo.ui.table(per_target.reset_index().round(3), selection=None),
        mo.md("**Designed subsets and their like-for-like random comparators (fixed epochs, no validation)**"),
        mo.ui.table(structured.reset_index().round(3), selection=None),
        mo.md("**Row thinning at n = 21 (keep every k-th time step of the training rows)**"),
        mo.ui.table(thin.reset_index().round(4), selection=None),
    ])
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **This is the cost of interpolating inside a 3x3x3 grid**, scored on 6 held-out configs
          that are all interior (none is a corner). It says nothing about how many runs a wider or
          higher-dimensional sweep would need.
        - Five subset draws per n is few; the range at small n is wide and would move with more
          draws. The table gives the share of the spread that comes from which configs were drawn.
        - Skill is measured against the phase-only baseline built from the same n configs, so a
          weak baseline at small n flatters small-n skill slightly, not the reverse.
        - The designed subsets train without a validation set; that is why they are compared with
          random subsets trained the same way, not with the main curve.
        - The star design has 6 configs, not 7, because one face centre is a held-out config.
        - The ridge model's size was chosen with all 21 configs and then held fixed; a smaller
          ridge model would do better at small n. The comparison shows that this choice is brittle,
          not that linear models cannot work with fewer runs.
        - The CFD these fits are scored against is itself two beats long and not yet periodic (E0).

        ## Next step
        For the next corpus, this argues for spending runs on coverage across parameters and on
        longer runs, not on temporal output density: 15 well-spread configs at more beats each
        would likely serve the hover surrogate better than 27 at two beats.
        """
    )
    return


if __name__ == "__main__":
    app.run()
