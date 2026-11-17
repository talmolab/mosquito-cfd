import marimo

app = marimo.App(width="medium", app_title="E1: hover gate")


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
    gate = pd.read_parquet(HERE / "outputs" / "gate_table.parquet")
    skill = pd.read_parquet(HERE / "outputs" / "seed_skill.parquet")
    wav = np.load(HERE / "outputs" / "waveforms.npz")
    FIG = HERE / "figures"
    SEEDS = (1234, 1235, 1236, 1237, 1238)
    LABEL = {
        "coarse_vs_fine": "coarse vs fine corpus (whole waveform)",
        "beat1_vs_beat2": "beat 1 vs beat 2 (whole waveform)",
        "t3c_gci": "T3c grid-convergence band (peak)",
        "coarse_vs_fine_peak": "coarse vs fine corpus (peak)",
    }
    return FIG, LABEL, SEEDS, TARGETS, gate, mo, np, pd, plotting, plt, skill, wav


@app.cell
def _(LABEL, gate, pd):
    def summarize():
        rows = []
        for (frame, comp, yard), g in gate.groupby(["frame", "component", "yardstick"], sort=False):
            rows.append({
                "frame": "lab, whole waveform" if frame == "lab" else "body, peak only",
                "component": comp,
                "surrogate error (median)": g.err_median.median(),
                "surrogate error (worst config, worst seed)": g.err_max.max(),
                "yardstick": LABEL[yard],
                "yardstick (median)": g.yardstick_value.median(),
                "yardstick (smallest config)": g.yardstick_value.min(),
                "configs inside (worst seed)": f"{int(g.inside.sum())}/{len(g)}",
                "margin (median)": g.margin.median(),
            })
        return pd.DataFrame(rows)

    summary = summarize()
    lab = gate[gate.frame == "lab"]
    body = gate[gate.frame == "body_peak"]
    return body, lab, summary


@app.cell
def _(body, gate, lab, mo, skill):
    _err = lab.drop_duplicates(["config", "component"])
    _sk = skill.groupby("target").skill.agg(["min", "max"])
    _n = body[(body.component == "cf_normal") & (body.yardstick == "t3c_gci")]
    _c = body[(body.component == "cf_chord") & (body.yardstick == "t3c_gci")]
    mo.md(
        f"""
        # E1. Hover gate: is Track B already as accurate as its CFD?

        ## Question
        On the six held-out hover configs, is the kinematics-only force surrogate's error inside
        the CFD's own uncertainty, component by component?

        ## Method
        The fine-corpus surrogate is retrained for seeds 1234 to 1238 on the committed split
        (same trainer, same settings; seed 1234 reproduces the committed `metrics.json` exactly).
        For each held-out config and component the error is the RMS of prediction minus fine CFD
        over the second beat, divided by that config's peak CFD magnitude. It is set beside three
        separate yardsticks, never merged:

        1. **Coarse versus fine corpus:** RMS difference between the 64x32x64 and 256x128x256 CFD
           waveforms for the same config, same normalization.
        2. **Beat 1 versus beat 2** of the fine CFD (from E0).
        3. **T3c grid-convergence band:** 3.7% on the normal force and 27.6% on chord, a statement
           about the peak magnitude in the wing's body frame. For this one, predictions and CFD are
           rotated into the body frame with the repo's `body_frame_coefficients` and compared at
           the peak.

        A config counts as inside a yardstick only if its **worst** seed is inside.

        **Data used:** `examples/prelim_sweep_fine/dataset.parquet` and
        `examples/prelim_sweep/dataset.parquet` at `80d653a` (re-extracted in #146), second beat,
        held-out configs {", ".join(f"`{c}`" for c in sorted(gate.config.unique()))}.

        ## Result
        **Track B is inside every yardstick, for every held-out config and component, on its
        worst seed.**

        - The surrogate's error is {_err.err_median.min():.1%} to {_err.err_median.max():.1%} of
          peak (median over seeds), and at most {_err.err_max.max():.1%} on the worst seed and
          config. Skill over the phase-only baseline is {_sk["min"].min():.3f} to
          {_sk["max"].max():.3f} across targets and seeds.
        - The CFD disagrees with itself by far more than that. Coarse and fine waveforms differ by
          {lab[lab.yardstick == "coarse_vs_fine"].yardstick_value.min():.0%} to
          {lab[lab.yardstick == "coarse_vs_fine"].yardstick_value.max():.0%} of peak, and the two
          beats by {lab[lab.yardstick == "beat1_vs_beat2"].yardstick_value.min():.0%} to
          {lab[lab.yardstick == "beat1_vs_beat2"].yardstick_value.max():.0%}.
        - The tightest comparison is the normal-force peak against the 3.7% band: the surrogate's
          peak error there is {_n.err_median.median():.1%} (median) and
          {_n.err_max.max():.1%} at worst, a margin of about {_n.margin.median():.1f}x. Chord peak
          error is {_c.err_median.median():.1%} against 27.6%.

        By the roadmap's rule this is a **pass** of the hover gate: on periodic hover, a
        kinematics-only model already reproduces the CFD more closely than the CFD is known.
        Arms B and C would have nothing to gain on these configs as force predictors.
        """
    )
    return


@app.cell
def _(mo, summary):
    mo.ui.table(summary.round(4), selection=None, page_size=20)
    return


@app.cell
def _(FIG, TARGETS, body, lab, np, plotting, plt):
    def gate_figure():
        comps = list(TARGETS) + ["cf_normal", "cf_chord"]
        names = list(TARGETS) + ["normal (peak)", "chord (peak)"]
        fig, ax = plt.subplots(figsize=(9.5, 5))
        marks = {
            "coarse_vs_fine": (plotting.SERIES[1], "s", "coarse vs fine corpus"),
            "coarse_vs_fine_peak": (plotting.SERIES[1], "s", None),
            "beat1_vs_beat2": (plotting.SERIES[2], "D", "beat 1 vs beat 2"),
            "t3c_gci": (plotting.SERIES[3], "^", "T3c grid-convergence band"),
        }
        both = {**{c: lab for c in TARGETS}, "cf_normal": body, "cf_chord": body}
        for i, c in enumerate(comps):
            g = both[c][both[c].component == c]
            e = g.drop_duplicates("config")
            ax.plot([e.err_min.min(), e.err_max.max()], [i, i], color=plotting.SERIES[0], lw=3, solid_capstyle="round")
            ax.plot(e.err_median.median(), i, "o", color=plotting.SERIES[0], ms=9, mec=plotting.SURFACE, mew=1.5,
                    label="surrogate error (median; bar: all configs and seeds)" if i == 0 else None)
            for yard, (color, marker, label) in marks.items():
                y = g[g.yardstick == yard]
                if len(y):
                    seen = ax.get_legend_handles_labels()[1]
                    ax.plot(y.yardstick_value.median(), i, marker, color=color, ms=8, mec=plotting.SURFACE, mew=1.5,
                            ls="none", label=label if label and label not in seen else None)
        ax.set_yticks(range(len(comps)), names)
        ax.invert_yaxis()
        ax.set_xscale("log")
        ax.xaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.set_xlabel("share of the config's peak CFD magnitude (log scale; yardsticks: median over 6 held-out configs)")
        ax.axhline(5.5, color=plotting.AXIS, lw=0.8)
        ax.set_title("Hover gate: surrogate error sits below every CFD-uncertainty yardstick")
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
        plotting.save(fig, FIG / "hover_gate.png")
        return FIG / "hover_gate.png"

    gate_png = gate_figure()
    return (gate_png,)


@app.cell
def _(gate_png, mo):
    mo.image(src=str(gate_png))
    return


@app.cell
def _(FIG, SEEDS, TARGETS, np, plotting, plt, wav):
    def waveform_figure(cfg="s45_f100_p60"):
        ph = wav["phase"]
        fig, axes = plt.subplots(2, 3, figsize=(11, 5.4), sharex=True)
        for j, (ax, t) in enumerate(zip(axes.ravel(), TARGETS)):
            p = np.stack([wav[f"pred{s}/{cfg}"][:, j] for s in SEEDS])
            ax.plot(ph, wav[f"coarse/{cfg}"][:, j], color=plotting.MUTED, lw=1.3, label="CFD, coarse grid")
            ax.plot(ph, wav[f"fine/{cfg}"][:, j], color=plotting.INK, lw=2.2, label="CFD, fine grid")
            ax.fill_between(ph, p.min(0), p.max(0), color=plotting.SERIES[0], alpha=0.35, lw=0)
            ax.plot(ph, np.median(p, 0), color=plotting.SERIES[0], lw=1.4, ls="--", label="surrogate (5 seeds)")
            ax.set_title(t)
        axes[0, 0].legend(loc="best", fontsize=8)
        for ax in axes[1]:
            ax.set_xlabel("phase")
        fig.suptitle(f"Held-out config {cfg}: surrogate against fine CFD, with coarse CFD for scale",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / f"heldout_waveforms_{cfg}.png")
        return FIG / f"heldout_waveforms_{cfg}.png"

    wave_png = waveform_figure()
    return (wave_png,)


@app.cell
def _(mo, wave_png):
    mo.image(src=str(wave_png))
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **The yardsticks are weak, and that is part of the finding.** None of them is a proper
          uncertainty for these runs:
            - The T3c band is the peak magnitude only; from one 70/45 degree, f* = 1 point outside
              the sweep; in the body frame; and its fine run used `dt = 2.5e-4` while coarse and
              medium used 5e-4, so it mixes grid and timestep refinement. Applying 3.7% and 27.6%
              to every config is a borrowing. Moments have no such band at all.
            - Coarse versus fine is two grids, so it is a sensitivity, not a convergence estimate.
              It says the coarse grid is far from the fine one, not how far the fine one is from
              the truth.
            - Beat 1 versus beat 2 cannot show that beat 2 is converged (E0).
        - "Inside the CFD's uncertainty" means the surrogate reproduces **this** CFD to within the
          amount this CFD is known. It says nothing about agreement with a real wing.
        - Six held-out configs: five on edges of the sweep cube and one on a face; no corner is held out. E2 covers the
          corners with leave-one-config-out.
        - The seed ranges follow the repo's convention: one seed sets both the validation carve
          and the initialisation.
        - The body-frame rotation loads `benchmarks/flapping_wing.py`, which imports the
          quasi-steady model at module level; no output of that model is used.

        ## Next step
        The gate passes, so on hover the open question is no longer the surrogate but the CFD:
        longer runs to settle the beat-to-beat change, and a grid-convergence estimate inside the
        sweep. For the surrogate, the informative test is a config whose command changes mid-run,
        which no hover result can stand in for.
        """
    )
    return


if __name__ == "__main__":
    app.run()
