import marimo

app = marimo.App(width="medium", app_title="E0b: how many beats until the forces repeat?")


@app.cell
def _():
    import json
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
    d = pd.read_parquet(HERE / "outputs" / "beat_convergence.parquet")
    w = np.load(HERE / "outputs" / "beat_waveforms.npz")
    control = json.loads((HERE / "outputs" / "control.json").read_text())
    FIG = HERE / "figures"
    HERE30 = HERE / "outputs_s45_f100_p30_fields"
    return FIG, HERE30, TARGETS, control, d, mo, np, pd, plotting, plt, w


@app.cell
def _(TARGETS, d):
    prev = d.pivot(index="beat", columns="target", values="diff_from_previous_over_peak")[list(TARGETS)]
    last = d.pivot(index="beat", columns="target", values="diff_from_last_over_peak")[list(TARGETS)]
    mean = d.pivot(index="beat", columns="target", values="mean")[list(TARGETS)]
    n_beats = int(d.beat.max())
    return last, mean, n_beats, prev


@app.cell
def _(control, last, mean, mo, n_beats, prev):
    raw_max = max(control[c] for c in ("Fx", "Fy", "Fz", "Mx", "My", "Mz"))
    mo.md(
        f"""
        # E0b. How many beats until the forces repeat?

        ## Question
        E0 showed that the second beat of every corpus run differs from the first by up to a fifth
        of peak. Does the flow settle if the run continues, and how far is the beat the surrogate
        trains on (beat 2) from the settled waveform?

        ## Method
        One coarse-grid run of the centre config `s45_f100_p45`, continued from 2 to {n_beats}
        wingbeats (12,000 steps) on the local RTX A5000, in the corpus's own container image
        (pinned by digest). The deck is the committed coarse deck with only `max_step`,
        `stop_time`, checkpointing and the GPU memory arena changed. Coefficients come from the
        repo's own extractor. Each beat is resampled to a 256-point phase grid and compared with
        the beat before it and with beat {n_beats}; differences are RMS over the beat divided by
        beat {n_beats}'s peak, with phase below 0.05 excluded as in E0.

        **Control.** The first {control["rows_compared"]:,} steps (the two beats the corpus has)
        were compared row by row with the committed coarse dataset at `80d653a`. `Fx`, `Fz`, `Mx`
        and `Mz` are identical; the largest raw difference in any component is {raw_max:.1e}
        (`Fy`, `My`). The local run is a continuation of the corpus run, not a different one.

        **Data used:** `experiments/e0b_long_run/run_s45_f100_p45/IB_Particle_1.csv` (generated
        here, not committed) and `examples/prelim_sweep/dataset.parquet` at `80d653a` for the control.

        ## Result
        **The forces do settle, and beat 2 is most of the way there.**

        - Beat 2 differs from beat {n_beats} by {last.loc[2].min():.1%} to {last.loc[2].max():.1%}
          of peak, depending on the component (largest: `{last.loc[2].idxmax()}`). Beat 1 differs
          by up to {last.loc[1].max():.0%}.
        - After beat 2 the beat-to-beat change shrinks by a factor of about 1.5 to 3.5 per
          beat: for `CF_z` it is {prev.loc[3, "CF_z"]:.1%}, {prev.loc[4, "CF_z"]:.1%},
          {prev.loc[5, "CF_z"]:.2%}, {prev.loc[6, "CF_z"]:.2%} for beats 3 to 6. By beat
          {n_beats} every component changes by under {prev.loc[n_beats].max():.2%} of peak per beat.
        - The mean of `CF_z` goes {mean.loc[1, "CF_z"]:.3f} → {mean.loc[2, "CF_z"]:.3f} →
          {mean.loc[n_beats, "CF_z"]:.3f} (beats 1, 2, {n_beats}): the large drop is in the first
          beat, and the later drift is small.
        - Running 4 beats instead of 2 would bring every component within
          {last.loc[4].max():.1%} of peak of beat {n_beats}.

        The Track B surrogate's held-out error on the fine grid is 1.1–1.8% of peak (E1; median over configs, 2.5% worst). On this
        config the beat-2 start-up residue ({last.loc[2].min():.1%}–{last.loc[2].max():.1%}) is
        the same size or larger for `CF_z`, `CF_mx` and `CF_my`. So the surrogate reproduces its
        training data more closely than that data represents steady flapping.
        """
    )
    return


@app.cell
def _(last, mo, prev):
    def table():
        a = prev.add_prefix("vs previous: ").round(4)
        b = last.add_prefix("vs last: ").round(4)
        return a.join(b).reset_index()

    mo.ui.table(table(), selection=None)
    return


@app.cell
def _(FIG, TARGETS, plotting, plt, prev):
    def decay():
        fig, ax = plt.subplots(figsize=(7.5, 4.2))
        beats = prev.index[1:]
        for t in TARGETS:
            ax.plot(beats, prev.loc[beats, t], marker="o", ms=5, color=plotting.TARGET_COLOR[t], label=t)
        ax.axhspan(0.011, 0.018, color=plotting.GRID, zorder=0)
        ax.text(beats[-1], 0.0142, "Track B held-out error (fine grid, E1)", ha="right", va="center",
                fontsize=8, color=plotting.INK2)
        ax.set_yscale("log")
        ax.set_xticks(list(beats), [f"{b - 1}→{b}" for b in beats])
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.set_xlabel("beat pair")
        ax.set_ylabel("RMS change / peak (log scale)")
        ax.set_title("Coarse grid, centre config: change from one beat to the next")
        ax.legend(ncol=3, loc="lower left")
        plotting.save(fig, FIG / "beat_to_beat_change.png")
        return FIG / "beat_to_beat_change.png"

    decay_png = decay()
    return (decay_png,)


@app.cell
def _(decay_png, mo):
    mo.image(src=str(decay_png))
    return


@app.cell
def _(FIG, TARGETS, n_beats, np, plotting, plt, w):
    def overlay():
        ph = w["phase"]
        keep = ph >= 0.05
        last_w = w[f"beat{n_beats}"]
        fig, axes = plt.subplots(2, 3, figsize=(11, 5.2), sharex=True)
        styles = ((1, plotting.MUTED, 1.2, "beat 1"), (2, plotting.SERIES[1], 1.6, "beat 2 (training beat)"),
                  (n_beats, plotting.SERIES[0], 2.0, f"beat {n_beats}"))
        for j, (ax, t) in enumerate(zip(axes.ravel(), TARGETS)):
            for b, color, lw, label in styles:
                ax.plot(ph[keep], w[f"beat{b}"][keep, j], color=color, lw=lw, label=label)
            ax.set_title(t)
            lo, hi = last_w[keep, j].min(), last_w[keep, j].max()
            ax.set_ylim(lo - 0.3 * (hi - lo), hi + 0.3 * (hi - lo))
            for r in (0.25, 0.75):
                ax.axvline(r, color=plotting.AXIS, lw=0.8, ls=":")
        axes[0, 0].legend(loc="best", fontsize=8)
        for ax in axes[1]:
            ax.set_xlabel("phase (dotted: stroke reversal)")
        fig.suptitle(f"Coarse grid, centre config: beats 1, 2 and {n_beats} overlaid",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "beats_overlaid.png")
        _ = np
        return FIG / "beats_overlaid.png"

    overlay_png = overlay()
    return (overlay_png,)


@app.cell
def _(mo, overlay_png):
    mo.image(src=str(overlay_png))
    return


@app.cell
def _(HERE30, TARGETS, last, mo, pd):
    d30 = pd.read_parquet(HERE30 / "beat_convergence.parquet")
    last30 = d30.pivot(index="beat", columns="target", values="diff_from_last_over_peak")[list(TARGETS)]
    _rows = "\n".join(
        f"        | {b} | {last30.loc[b].min():.1%}–{last30.loc[b].max():.1%} | {last.loc[b].min():.1%}–{last.loc[b].max():.1%} |"
        for b in (1, 2, 3, 4, 5)
    )
    mo.md(
        f"""
        ## Follow-up (2026-11-17): a 30° pitch config, and pictures of the flow

        **Question.** Does the slowest-looking corner of the sweep settle as fast as the centre
        config, and where in the flow does the beat-to-beat change sit?

        **Method.** Two more 6-beat coarse runs on the local A5000, both writing a plotfile every
        100 steps (20 per beat): `s45_f100_p30`, and `s45_f100_p45` again. Same image digest and
        deck as the corpus apart from `max_step`, `stop_time`, `amr.plot_int` and the memory cap.
        Controls: the first 4,000 steps of each match the committed coarse dataset to 1e-13, and
        the repeated 45° run matches the first one to 1e-15 over all 12,000 steps.

        **Result.** Distance from beat 6, as a share of beat 6's peak (range over the six
        components):

        | Beat | 30° pitch | 45° pitch |
        |---|---|---|
{_rows}

        At 30° pitch, beat 2 is up to {last30.loc[2].max():.1%} of peak from beat 6 and beat 4 is
        still up to {last30.loc[4].max():.1%}; it takes until beat 5 to come under 1%. So "four
        beats" is enough for the centre config and not for the low-pitch one.

        The velocity field changes more than the forces. In the near-wing region the median change
        between beat 2 and beat 6 at 30° pitch is about 4% of the reference wing speed, and a
        tenth of the region changes by 10% or more. The movies
        (`figures/*_beat2_vs_beat6_flow_lev-3d.mp4`, made by `settling_video.py`) show the vortex
        attached to the wing repeating closely while the vortex shed into the wake differs.

        **Caveats.** Still the coarse grid and one run per config. The statement about where the
        change sits comes from looking at a few frames, not from a measurement over the beat.
        """
    )
    return


@app.cell
def _(last, mo, n_beats, prev):
    mo.md(
        f"""
        ## Caveats
        - **Coarse grid only.** For this config the fine grid's beat-1-to-beat-2 change in `CF_z`
          (E0: 15% of peak) is of the same order as the coarse one here
          ({prev.loc[2, "CF_z"]:.0%}), but whether the fine grid settles at the same rate was not
          run; a 6-beat fine run was outside this exploration's local-GPU budget.
        - **The main run is one config,** the centre of the sweep. The follow-up above adds one
          30° pitch config, which settles more slowly. The other 25 configs were not run.
        - **Beat {n_beats} is the reference, not the limit.** It is still moving by up to
          {prev.loc[n_beats].max():.2%} of peak per beat, so the distances "vs last" slightly
          understate the distance to the truly periodic state. At the observed decay rate the
          remainder is about the size of that last step.
        - This experiment does not say why the flow takes several beats to settle (wake build-up,
          or the wing meeting its own wake through the spanwise-periodic boundary). Whatever the
          cause, it is a property of the corpus setup and is the same in every corpus run.

        ## Next step
        If the corpus is regenerated for any reason, run 5 beats and train on the fifth. Four
        beats cuts the start-up residue from {last.loc[2].max():.1%} to {last.loc[4].max():.1%}
        of peak on the centre config, but the 30° pitch follow-up is still at 1.6% after four and
        needs the fifth to come under 1%. This would also remove the kink at the beat boundary
        that E2 traced to non-periodic training data.
        """
    )
    return


if __name__ == "__main__":
    app.run()
