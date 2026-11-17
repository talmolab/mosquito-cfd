import marimo

app = marimo.App(width="medium", app_title="E5: POD of the velocity field")


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

    plotting.use_style()
    res = pd.read_parquet(HERE / "outputs" / "results.parquet")
    spec = np.load(HERE / "outputs" / "spectra.npz")
    idx = pd.read_parquet(HERE / "outputs" / "index.parquet")
    FIG = HERE / "figures"
    HERE_WING = HERE / "outputs" / "wingframe.parquet"
    NAME = {"patch_u": "near-wing patch (full resolution)", "full4_u": "whole domain (4x downsampled)"}
    return FIG, HERE_WING, NAME, idx, mo, np, pd, plotting, plt, res, spec


@app.cell
def _(idx, res):
    rank = res[res.scope == "rank"].set_index(["field", "r"])
    per = res[res.scope == "per_config"]
    pooled = res[res.scope == "pooled_train"].set_index("field")
    P = rank.loc["patch_u"]
    F = rank.loc["full4_u"]
    n_train = int((~idx.holdout).sum())
    n_test = int(idx.holdout.sum())
    per_cfg = per[per.field == "patch_u"]
    return F, P, n_test, n_train, per_cfg, pooled, rank


@app.cell
def _(F, P, idx, mo, n_test, n_train, per_cfg, pooled):
    mo.md(
        f"""
        # E5. How many numbers describe the flow? POD of the velocity field

        ## Question
        April's slides sized the flow latent at "between 64 and 256 dimensions". How many linear
        modes does the captured velocity field need, and does a basis built from some configs
        describe configs it has never seen?

        ## Method
        Proper orthogonal decomposition (the method of snapshots) of the velocity field, mean
        removed, on two regions: the near-wing patch at full resolution (x 1 to 7, y 0 to 4,
        z 2.5 to 5.5; 192 x 128 x 96 cells, 7.1 million values per snapshot) and the whole domain
        downsampled 4x (64 x 32 x 64). Each config's velocity is divided by its reference speed
        (the one the force coefficients use), so configs carry comparable weight.

        - **Basis:** the {n_train} second-beat snapshots of the 21 training configs.
        - **Latent-sizing number:** the relative reconstruction error (error norm over field norm,
          both about the training mean) of the {n_test} snapshots of the 6 held-out configs when
          projected on the first r modes of that basis.
        - **Force probe:** linear regression from the first r mode coefficients to the six force
          coefficients at the same instant, fitted on training configs, scored on held-out ones.

        The patch is too large to decompose directly, so everything is computed from inner
        products between snapshots; a test pins that route to the direct one.

        **Data used:** {len(idx)} live plotfiles of `Z:\\...\\prelim_sweep_fine\\runs\\`, second
        beat of all 27 configs (18 to 24 per config), each checked for `ns.cfl = 0.6`,
        `dt = 5e-4`, the 256x128x256 grid and IAMReX `f93dc794`; all `.old.*` directories excluded; the final plotfile of the f* = 0.85 and 1.0 runs is excluded; for f* = 1.15 the final plotfile (step 3478, phase 0.9999, 78 steps after the previous one) is included. Force labels from
        `examples/prelim_sweep_fine/dataset.parquet` at `80d653a`.

        ## Result
        **A 64-to-256-dimensional linear latent reconstructs an unseen config's near-wing
        velocity to within {P.loc[64, "heldout_error"]:.0%} down to {P.loc[256, "heldout_error"]:.0%}.**

        | modes r | held-out error, patch | training error, patch | held-out error, whole domain | force probe R2 (patch) |
        |---|---|---|---|---|
        | 8 | {P.loc[8, "heldout_error"]:.0%} | {P.loc[8, "train_error"]:.0%} | {F.loc[8, "heldout_error"]:.0%} | {P.loc[8, "probe_r2"]:.2f} |
        | 16 | {P.loc[16, "heldout_error"]:.0%} | {P.loc[16, "train_error"]:.0%} | {F.loc[16, "heldout_error"]:.0%} | {P.loc[16, "probe_r2"]:.2f} |
        | 32 | {P.loc[32, "heldout_error"]:.0%} | {P.loc[32, "train_error"]:.0%} | {F.loc[32, "heldout_error"]:.0%} | {P.loc[32, "probe_r2"]:.2f} |
        | 64 | {P.loc[64, "heldout_error"]:.0%} | {P.loc[64, "train_error"]:.0%} | {F.loc[64, "heldout_error"]:.0%} | {P.loc[64, "probe_r2"]:.2f} |
        | 128 | {P.loc[128, "heldout_error"]:.0%} | {P.loc[128, "train_error"]:.1%} | {F.loc[128, "heldout_error"]:.0%} | {P.loc[128, "probe_r2"]:.3f} |
        | 256 | {P.loc[256, "heldout_error"]:.1%} | {P.loc[256, "train_error"]:.1%} | {F.loc[256, "heldout_error"]:.1%} | {P.loc[256, "probe_r2"]:.3f} |

        - **The basis transfers.** Up to 16 modes, held-out configs are reconstructed as well as
          the training configs themselves. Beyond that a gap opens (at 256 modes,
          {P.loc[256, "heldout_error"]:.1%} held out against {P.loc[256, "train_error"]:.1%} in
          sample): the later modes are describing individual training snapshots.
        - **There is no sharp low-rank cut-off.** The pooled spectrum needs
          {int(pooled.loc["patch_u", "modes_90"])} modes for 90% of the fluctuation energy and
          {int(pooled.loc["patch_u", "modes_99"])} for 99%. Each halving of the error costs
          roughly a fourfold increase in modes.
        - **One config alone is nearly full rank.** A single config's second beat needs
          {int(per_cfg.modes_99.median())} modes for 99% of its energy out of only
          {int(per_cfg.n_snap.median())} snapshots, so the snapshot count, not the flow, is setting
          that number.
        - **The near-wing patch is not harder than the whole domain** (same errors within a few
          points), so the wake below the patch is not where the difficulty is.
        - **Forces need far fewer modes than the field.** Eight modes give a linear force probe
          R2 of {P.loc[8, "probe_r2"]:.2f} and 16 give {P.loc[16, "probe_r2"]:.2f}.
        """
    )
    return


@app.cell
def _(FIG, NAME, np, plotting, plt, rank, spec):
    def spectrum_figure():
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.3))
        ax = axes[0]
        for (key, name), color in zip(NAME.items(), (plotting.SERIES[0], plotting.SERIES[1])):
            e = spec[f"{key}/pooled_energy"]
            ax.plot(np.arange(1, len(e) + 1), 1 - e, color=color, label=name)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_ylim(1e-4, 1)
        for level in (0.1, 0.01):
            ax.axhline(level, color=plotting.AXIS, lw=0.8, ls=":")
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.set_xlabel("number of modes")
        ax.set_ylabel("fluctuation energy not captured")
        ax.set_title("Pooled spectrum, 21 training configs (dotted: 90% and 99%)")
        ax.legend(loc="lower left", fontsize=8)

        ax = axes[1]
        p = rank.loc["patch_u"]
        cfg_cols = [c for c in p.columns if c.startswith("heldout_error/")]
        for c in cfg_cols:
            ax.plot(p.index, p[c], color=plotting.SERIES[0], lw=0.8, alpha=0.4)
        ax.plot(p.index, p.heldout_error, "o-", color=plotting.SERIES[0], label="held-out configs (thin: each of the 6)")
        ax.plot(p.index, p.train_error, "s--", color=plotting.MUTED, lw=1.6, label="training configs (in sample)")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(list(p.index), [str(int(r)) for r in p.index])
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.set_yticks([0.02, 0.05, 0.1, 0.2, 0.5])
        ax.set_xlabel("number of modes (latent size)")
        ax.set_ylabel("relative reconstruction error")
        ax.set_title("Near-wing patch: error against latent size")
        ax.legend(loc="lower left", fontsize=8)
        fig.suptitle("POD of the second-beat velocity field", x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "pod_spectrum_and_error.png")
        return FIG / "pod_spectrum_and_error.png"

    spectrum_png = spectrum_figure()
    return (spectrum_png,)


@app.cell
def _(mo, spectrum_png):
    mo.image(src=str(spectrum_png))
    return


@app.cell
def _(FIG, np, plotting, plt, spec):
    def modes_figure():
        modes = spec["patch_u/mode_slices"]  # (6, nx, nz, 3) on the mid-span plane
        fig, axes = plt.subplots(2, 3, figsize=(11, 4.6), sharex=True, sharey=True)
        extent = (1.0, 7.0, 2.5, 5.5)
        for k, ax in enumerate(axes.ravel()):
            w = modes[k, :, :, 2].T  # vertical velocity component
            lim = float(np.abs(w).max())
            ax.imshow(w, origin="lower", extent=extent, cmap=plotting.DIV, vmin=-lim, vmax=lim, aspect="equal")
            ax.plot(4.0, 4.0, "+", color=plotting.INK, ms=8)
            ax.set_title(f"mode {k + 1}")
            ax.grid(False)
        for ax in axes[1]:
            ax.set_xlabel("x (chordwise)")
        for ax in axes[:, 0]:
            ax.set_ylabel("z (vertical)")
        fig.suptitle("First six modes, vertical velocity on the mid-span plane y = 2 (+ marks the hinge's x, z)",
                     x=0.02, ha="left", fontweight="bold")
        fig.tight_layout()
        plotting.save(fig, FIG / "pod_modes_midspan.png")
        return FIG / "pod_modes_midspan.png"

    modes_png = modes_figure()
    return (modes_png,)


@app.cell
def _(modes_png, mo):
    mo.image(src=str(modes_png))
    return


@app.cell
def _(FIG, plotting, plt, rank):
    def probe_figure():
        fig, ax = plt.subplots(figsize=(6, 3.8))
        for key, color, name in (("patch_u", plotting.SERIES[0], "near-wing patch"), ("full4_u", plotting.SERIES[1], "whole domain")):
            p = rank.loc[key]
            ax.plot(p.index, p.probe_r2, "o-", color=color, label=name)
        ax.set_xscale("log", base=2)
        ax.set_xticks(list(p.index), [str(int(r)) for r in p.index])
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("number of modes used")
        ax.set_ylabel("held-out R2, mean of six targets")
        ax.set_title("Linear force probe from mode coefficients")
        ax.legend(loc="lower right")
        plotting.save(fig, FIG / "pod_force_probe.png")
        return FIG / "pod_force_probe.png"

    probe_png = probe_figure()
    return (probe_png,)


@app.cell
def _(mo, probe_png):
    mo.image(src=str(probe_png))
    return


@app.cell
def _(mo, per_cfg):
    mo.vstack([
        mo.md("**Per-config spectra, near-wing patch (modes for 90% and 99% of each config's own fluctuation energy)**"),
        mo.ui.table(per_cfg[["config", "holdout", "n_snap", "modes_90", "modes_99"]].reset_index(drop=True),
                    selection=None, page_size=27),
    ])
    return


@app.cell
def _(FIG, HERE_WING, mo, pd, plotting, plt):
    def wing_frame():
        w = pd.read_parquet(HERE_WING)
        piv = w.pivot(index="r", columns="frame", values="heldout_error")
        lab, wing = "lab frame, patch 4x", "wing frame, box 4x"
        first = w.groupby("frame")[["modes_90", "modes_99"]].first()
        fig, ax = plt.subplots(figsize=(6.2, 4))
        ax.plot(piv.index, piv[lab], "o-", color=plotting.SERIES[0], label="lab frame (fixed patch)")
        ax.plot(piv.index, piv[wing], "s-", color=plotting.SERIES[1], label="wing frame (box moving with the wing)")
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(list(piv.index), [str(int(r)) for r in piv.index])
        ax.set_yticks([0.02, 0.05, 0.1, 0.2, 0.5])
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.set_xlabel("number of modes (latent size)")
        ax.set_ylabel("held-out relative reconstruction error")
        ax.set_title("Same snapshots, two frames of reference (4x downsampled)")
        ax.legend(loc="lower left", fontsize=8)
        plotting.save(fig, FIG / "pod_lab_vs_wing_frame.png")
        text = f"""
        ## Follow-up: the same POD in a wing-fixed frame

        The velocity was resampled onto a box that moves with the wing (2 chords x 3.2 span x 2
        normal, velocity expressed in wing axes) and the decomposition repeated, on the patch
        block-averaged 4x. **Moving with the wing roughly halves the number of modes needed.**

        | | lab frame (fixed patch) | wing frame (moving box) |
        |---|---|---|
        | modes for 90% of fluctuation energy | {int(first.loc[lab, "modes_90"])} | {int(first.loc[wing, "modes_90"])} |
        | modes for 99% | {int(first.loc[lab, "modes_99"])} | {int(first.loc[wing, "modes_99"])} |
        | held-out error at 16 modes | {piv.loc[16, lab]:.0%} | {piv.loc[16, wing]:.0%} |
        | held-out error at 64 modes | {piv.loc[64, lab]:.0%} | {piv.loc[64, wing]:.1%} |
        | held-out error at 256 modes | {piv.loc[256, lab]:.1%} | {piv.loc[256, wing]:.1%} |

        So a good part of the slow decay in the lab frame is the wing sweeping through a fixed
        grid, as expected. The two columns are not the same region: the wing box is smaller and
        holds only the flow next to the wing, while the fixed patch also holds the wake the wing
        has left behind. Part of the gain is therefore the easier region, not only the frame.
        """
        return FIG / "pod_lab_vs_wing_frame.png", text

    wing_png, wing_text = wing_frame()
    mo.vstack([mo.md(wing_text), mo.image(src=str(wing_png))])
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **These numbers are lower bounds on the latent a finer time sampling would need.** There
          are only 18 to 24 snapshots per beat. A basis cannot have more modes than snapshots, and
          structures that live between snapshots are not represented at all.
        - **The three frequency groups sample different phases** (a plotfile every 100 steps is a
          different fraction of the beat at each frequency), so a held-out config is partly being
          asked to interpolate in phase as well as in parameters.
        - **A wing moving through a fixed grid is the textbook slow-decay case for POD.** A sharp
          structure that translates needs many fixed modes to describe. The slow decay here is
          evidence about this frame of reference, not proof that the flow is intrinsically
          high-dimensional; a wing-fixed frame or a nonlinear encoder could do much better with the
          same data. That is what E6 tests.
        - Errors are about the training mean; the mean field itself holds roughly half of the
          held-out energy, so errors relative to the total field would be smaller.
        - The cells inside the immersed boundary are included; nothing is masked.
        - The force probe uses 128 held-out snapshots and predicts forces a kinematics-only model
          already gets to within 1 to 2 percent (E1); it shows the field modes carry the force
          information, not that a field model is needed for it.
        - Velocity only; the pressure gradient was cached downsampled but not analysed.
        - Second beat only, from runs that are not yet periodic (E0).

        ## Next step
        Compare against a nonlinear encoder at the same latent size on the same patch (E6). The
        wing-frame result suggests any encoder should be given the wing pose, or work in wing
        coordinates, before it is asked to compress the field. For a future corpus, a plotfile interval of 25 to 50 steps
        would lift the snapshot-count cap that limits every number here.
        """
    )
    return


if __name__ == "__main__":
    app.run()
