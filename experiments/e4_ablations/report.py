import marimo

app = marimo.App(width="medium", app_title="E4: Track B ablations")


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
    a = pd.read_parquet(HERE / "outputs" / "ablations.parquet")
    cv = pd.read_parquet(HERE / "outputs" / "ridge_cv.parquet")
    chosen = pd.read_parquet(HERE / "outputs" / "ridge_chosen.parquet")
    FIG = HERE / "figures"
    return FIG, TARGETS, a, chosen, cv, mo, np, pd, plotting, plt


@app.cell
def _(TARGETS, a, chosen, pd):
    per_fit = a.groupby(["arm", "kind", "seed"]).agg(skill=("skill", "mean"), n_params=("n_params", "first")).reset_index()
    arms = per_fit.groupby(["arm", "kind"]).agg(median=("skill", "median"), min=("skill", "min"), max=("skill", "max"),
                                                 n_params=("n_params", "first")).reset_index()
    arms = arms[~arms.arm.str.startswith("ridge")]  # the grid ridge arms were scored on holdout; only the CV choice is reported
    ridge_row = pd.DataFrame([{"arm": f"ridge, {int(chosen.harmonics.iloc[0])} harmonics x degree {int(chosen.degree.iloc[0])} (chosen by CV)",
                               "kind": "ridge", "median": chosen.skill.mean(), "min": chosen.skill.mean(),
                               "max": chosen.skill.mean(), "n_params": int(chosen.n_params.iloc[0])}])
    arms = pd.concat([arms, ridge_row], ignore_index=True).sort_values("median", ascending=False).reset_index(drop=True)
    base = a[a.arm == "baseline"]
    rmse = pd.DataFrame({
        "MLP baseline RMSE (median of 5 seeds)": base.groupby("target").rmse.median(),
        "ridge RMSE": chosen.set_index("target").rmse,
        "MLP baseline skill (median)": base.groupby("target").skill.median(),
        "ridge skill": chosen.set_index("target").skill,
    }).loc[list(TARGETS)]
    rmse["RMSE ratio, MLP / ridge"] = rmse.iloc[:, 0] / rmse.iloc[:, 1]
    A = arms.set_index("arm")
    return A, arms, rmse


@app.cell
def _(A, chosen, cv, mo, rmse):
    _h, _d, _np = int(chosen.harmonics.iloc[0]), int(chosen.degree.iloc[0]), int(chosen.n_params.iloc[0])
    _ridge = A[A.kind == "ridge"].iloc[0]
    mo.md(
        f"""
        # E4. Which inputs, and how much model, does the hover force map need?

        ## Question
        Track B is a 3-layer, 64-wide MLP on five inputs (stroke amplitude, frequency, pitch
        amplitude, sin and cos of phase). Which of those inputs matter, is the network the right
        size, and does it need to be a network at all?

        ## Method
        Every MLP arm is trained for seeds 1234 to 1238 on the committed split and scored on the 6
        held-out configs; the baseline arm reproduces the committed 5-seed skill ranges exactly.
        Skill is 1 - MSE / MSE of the phase-only baseline, averaged over the six targets.

        The non-neural comparator is ridge regression on Fourier harmonics in phase multiplied by
        polynomials in the three kinematic inputs. Its size is chosen by leave-one-config-out
        cross-validation **inside the 21 non-holdout configs** (54 candidates), and only that one
        choice is scored on the holdout, so the holdout did not pick it.

        **Data used:** `examples/prelim_sweep_fine/dataset.parquet` at `80d653a` (re-extracted in
        #146), second beat.

        ## Result
        **A linear model beats the MLP on this corpus.** The cross-validated choice is {_h}
        harmonics x degree-{_d} polynomials ({_np:,} coefficients, solved in closed form, no
        seeds). Its held-out skill is {_ridge["median"]:.4f} against
        {A.loc["baseline", "median"]:.4f} for the MLP baseline, and its RMSE is
        {rmse["RMSE ratio, MLP / ridge"].min():.1f} to {rmse["RMSE ratio, MLP / ridge"].max():.1f}
        times lower on every target. Periodic hover over this grid is a smooth, low-dimensional
        family of waveforms, and a harmonic expansion is its natural description.

        **The MLP is short of phase resolution, not capacity.** Adding the second and third phase
        harmonics as inputs lifts it from {A.loc["baseline", "median"]:.4f} to
        {A.loc["harmonics_3", "median"]:.4f} at almost the same size. Making it 30 times larger
        (256 wide, 5 deep) reaches {A.loc["width256_depth5", "median"]:.4f}. One hidden layer is
        not enough at any width tried ({A.loc["width256_depth1", "median"]:.2f} at 256 wide).

        **Pitch amplitude is essential, stroke amplitude matters, frequency barely does.**
        Dropping pitch gives {A.loc["drop_pitch_amp_deg", "median"]:.2f} (worse than the
        phase-only baseline), dropping stroke gives {A.loc["drop_stroke_amp_deg", "median"]:.2f},
        and dropping frequency still gives {A.loc["drop_frequency_fstar", "median"]:.3f}. The
        coefficients are already divided by a reference force that scales with frequency squared,
        so what is left for frequency to explain is the Reynolds-number effect across 43 to 90.
        Giving the model Reynolds number in place of frequency changes nothing
        ({A.loc["re_instead_of_fstar", "median"]:.4f}).
        """
    )
    return


@app.cell
def _(FIG, arms, plotting, plt):
    def arms_figure():
        g = arms[arms["median"] > 0.9].iloc[::-1].reset_index(drop=True)
        fig, ax = plt.subplots(figsize=(9, 0.42 * len(g) + 1.4))
        for i, r in g.iterrows():
            color = plotting.SERIES[1] if r.kind == "ridge" else (plotting.INK if r.arm == "baseline" else plotting.SERIES[0])
            ax.plot([r["min"], r["max"]], [i, i], color=color, lw=3, solid_capstyle="round")
            ax.plot(r["median"], i, "o", color=color, ms=8, mec=plotting.SURFACE, mew=1.5)
            ax.text(1.0005, i, f"{int(r.n_params):,}", va="center", fontsize=8, color=plotting.INK2)
        ax.set_yticks(range(len(g)), g.arm)
        ax.set_xlim(0.9, 1.0)
        ax.text(1.0005, len(g) - 0.3, "parameters", fontsize=8, color=plotting.INK2, va="bottom")
        ax.set_xlabel("held-out skill over the phase-only baseline (dot: median of 5 seeds; bar: range)")
        ax.set_title("Arms with skill above 0.9 (black: committed baseline; orange: ridge)")
        plotting.save(fig, FIG / "ablation_arms.png")
        return FIG / "ablation_arms.png"

    arms_png = arms_figure()
    return (arms_png,)


@app.cell
def _(arms_png, mo):
    mo.image(src=str(arms_png))
    return


@app.cell
def _(arms, cv, mo, rmse):
    mo.vstack([
        mo.md("**All arms**"),
        mo.ui.table(arms.round(4), selection=None, page_size=30),
        mo.md("**MLP baseline against the chosen ridge model, per target**"),
        mo.ui.table(rmse.reset_index().round(4), selection=None),
        mo.md("**Ridge cross-validation inside the 21 training configs (best 10 of 54; lower is better)**"),
        mo.ui.table(cv.head(10).round(6), selection=None),
    ])
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **The ridge result is specific to periodic hover on a full grid.** It has no way to
          represent a command that changes mid-run, and E3 shows it collapses when the grid has
          gaps, where the MLP degrades gracefully. It is the right baseline here, not a candidate
          for the RL surrogate.
        - With three levels per parameter, a cubic in one parameter cannot be told apart from a
          quadratic at the grid points, so "degree 3" here mostly buys cross terms. The ridge
          penalty picks the smallest-norm fit among the equivalent ones.
        - The cross-validation picked the largest harmonic count offered (16), so the search hit
          its edge; more harmonics might do slightly better still. The gain from 8 to 16 was
          small.
        - Seed ranges follow the repo's convention (one seed sets the validation carve and the
          initialisation). The ridge model has no seed, so it has no range.
        - All arms use 2000 epochs and the committed learning rate; a larger or richer-input MLP
          might want different settings, which were not tuned.
        - Scores are against two-beat CFD that is not yet periodic (E0); the kink at the beat
          boundary (E2) is something a model with more harmonics can fit more closely, which is
          fitting the CFD's non-periodicity, not physics.

        ## Next step
        Use the ridge model as the reference any hover force surrogate must beat, and add higher
        phase harmonics to Track B's inputs (a one-line change with a measurable gain). Neither
        changes the conclusion that the informative test is non-periodic motion.
        """
    )
    return


if __name__ == "__main__":
    app.run()
