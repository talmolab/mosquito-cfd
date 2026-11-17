import marimo

app = marimo.App(width="medium", app_title="E6: can Mesh_Reduced encode the near-wing flow?")


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

    plotting.use_style()
    OUT, FIG = HERE / "outputs", HERE / "figures"
    base = "run_ds8_enc3_piv4_p15_h128_s1234"
    short = json.loads((OUT / f"{base}.json").read_text())
    long = json.loads((OUT / f"{base}_e600.json").read_text())
    probe = json.loads((OUT / "probe_p15_h128.json").read_text())
    return FIG, long, mo, np, pd, plotting, plt, probe, short


@app.cell
def _(long, np):
    pod = {int(k): v for k, v in long["pod"]["pod_same_training_configs"].items()}
    ranks = np.array(sorted(pod))
    errs = np.array([pod[r] for r in ranks])
    # POD rank that gives the same held-out error as the trained model (log-log interpolation)
    equiv = float(np.exp(np.interp(-np.log(long["test_rel_error"]), -np.log(errs), np.log(ranks))))
    return equiv, errs, pod, ranks


@app.cell
def _(equiv, long, mo, pod, short):
    L = long["latent_size"]
    mo.md(
        f"""
        # E6. Can stock `Mesh_Reduced` encode the near-wing flow?

        ## Question
        The roadmap's arm B is PhysicsNeMo's `Mesh_Reduced` as the field encoder. Does the stock
        model train on this workstation, and does it compress the near-wing velocity field better
        than POD when both get the same number of latent values?

        ## Method
        - **Model.** `physicsnemo.models.mesh_reduced.Mesh_Reduced` (PhysicsNeMo 2.1.1) with its
          default size: `processor_size=15`, `hidden_dim_processor=128`,
          {long["n_params"] / 1e6:.1f} million parameters. Only the encoder-decoder is trained;
          the `Sequence_Model` that would step the latent in time is not used.
        - **Graph.** The near-wing patch of E5 (6 × 4 × 3 length units around the wing),
          block-averaged 8× to {long["grid"][0]} × {long["grid"][1]} × {long["grid"][2]} =
          {long["n_nodes"]:,} nodes, with 6-neighbour edges ({long["n_edges"]:,} directed). Node
          input: 3 velocity components, divided by the config's reference speed and standardised.
          Edge input: relative position and length (4 values). The model is not given the wing
          position or the kinematic parameters.
        - **Latent.** {long["n_pivotal"]} pivotal nodes on a regular 4-node sub-lattice ×
          `output_encode_dim=3` = **{L} values per snapshot**.
        - **Training.** MSE reconstruction, Adam, learning rate 1e-4 with cosine decay, batch 4,
          seed 1234. Two runs of the same model: {short["args"]["epochs"]} epochs
          ({short["hours"]:.1f} h) and {long["args"]["epochs"]} epochs ({long["hours"]:.1f} h).
          The reported weights are those with the lowest validation error.
        - **Split.** The corpus's 6 holdout configs are the test set ({long["n_test"]} snapshots);
          3 of the other 21 configs are validation ({long["n_val"]}); 18 train
          ({long["n_train"]}).
        - **Comparator.** POD fitted on the same 18 training configs, truncated to {L} modes.
        - **Error.** As in E5: ‖x − x̂‖ / ‖x − training mean‖, pooled over held-out snapshots.
        - **Environment.** WSL2, RTX A5000 24 GB, torch 2.12.1+cu126, torch_geometric 2.8.1.
          `torch_scatter` 2.1.2 and `torch_cluster` 1.6.3 are wheels built for torch 2.11: no
          matching wheel existed for 2.12. They import and run on the GPU here, but this
          combination is not a supported one.

        **Data used:** beat-1 velocity snapshots (the second wingbeat) of all 27 configs from the
        fine corpus plotfiles under `examples/prelim_sweep_fine/runs/` on the cluster share, 558
        snapshots, each provenance-checked (`ns.cfl = 0.6`, `fixed_dt = 5e-4`, 256 × 128 × 256);
        the final plotfile of each run is excluded (see step 0).

        ## Result
        **It trains, but at {L} latent values it reconstructs held-out flow
        {long["test_rel_error"] / pod[L]:.1f} times worse than POD.**

        | | Held-out error | Training-config error |
        |---|---|---|
        | `Mesh_Reduced`, {short["args"]["epochs"]} epochs | {short["test_rel_error"]:.1%} | {short["train_rel_error"]:.1%} |
        | `Mesh_Reduced`, {long["args"]["epochs"]} epochs | {long["test_rel_error"]:.1%} | {long["train_rel_error"]:.1%} |
        | POD, {L} modes | {pod[L]:.1%} | — |

        - The {long["args"]["epochs"]}-epoch model's held-out error equals that of POD with about
          **{equiv:.0f} modes**, so it uses its {L} latent values about
          {L / equiv:.0f} times less efficiently than a linear basis.
        - Four times more training cut the held-out error from {short["test_rel_error"]:.0%} to
          {long["test_rel_error"]:.0%}; validation error was flat over the last 100 epochs, so this
          training schedule is used up.
        - Its error on the training configs ({long["train_rel_error"]:.1%}) is half its held-out
          error, and both are above POD's held-out error: the model is limited by fitting as much
          as by generalisation.
        - Held-out error by config ranges from
          {min(long["test_rel_error_per_config"].values()):.0%} to
          {max(long["test_rel_error_per_config"].values()):.0%}; the worst is
          `{max(long["test_rel_error_per_config"], key=long["test_rel_error_per_config"].get)}`.
        - Cost: {long["peak_gib"]:.1f} GiB peak GPU memory at batch 4, 36 s per epoch, and
          {1000 * long["encode_seconds_per_batch"]["1"]:.0f} ms to encode one snapshot.
        """
    )
    return


@app.cell
def _(FIG, errs, long, plotting, plt, ranks, short):
    def compare():
        fig, ax = plt.subplots(figsize=(7.5, 4.3))
        ax.plot(ranks, errs, marker="o", ms=5, color=plotting.SERIES[0], label="POD (same 18 training configs)")
        L = long["latent_size"]
        for run, color in ((short, plotting.MUTED), (long, plotting.SERIES[1])):
            ax.scatter([L], [run["test_rel_error"]], s=70, color=color, zorder=3,
                       edgecolor=plotting.SURFACE, linewidth=2,
                       label=f"Mesh_Reduced, {run['args']['epochs']} epochs")
            ax.annotate(f"{run['test_rel_error']:.0%}", (L, run["test_rel_error"]), xytext=(8, 0),
                        textcoords="offset points", va="center", fontsize=9, color=plotting.INK2)
        ax.set_xscale("log", base=2)
        ax.set_yscale("log")
        ax.set_xticks(list(ranks), ["" if r == 256 else str(r) for r in ranks])
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.yaxis.set_minor_formatter(lambda v, _: "")
        ax.set_yticks([0.05, 0.1, 0.2, 0.4])
        ax.set_xlabel("latent values per snapshot")
        ax.set_ylabel("held-out reconstruction error")
        ax.set_title("Near-wing velocity, 8× block-averaged patch (4,608 nodes)")
        ax.legend(loc="lower left")
        plotting.save(fig, FIG / "mesh_reduced_vs_pod.png")
        return FIG / "mesh_reduced_vs_pod.png"

    compare_png = compare()
    return (compare_png,)


@app.cell
def _(compare_png, mo):
    mo.image(src=str(compare_png))
    return


@app.cell
def _(FIG, long, plotting, plt, pod, short):
    def curves():
        fig, ax = plt.subplots(figsize=(7.5, 4.0))
        for run, color in ((short, plotting.MUTED), (long, plotting.SERIES[1])):
            h = run["history"]
            ax.plot([r["epoch"] + 1 for r in h], [r["val_rel_error"] for r in h], color=color, lw=1.6,
                    label=f"{run['args']['epochs']}-epoch run")
        ax.axhline(pod[long["latent_size"]], color=plotting.SERIES[0], lw=1.5, ls="--")
        ax.text(600, pod[long["latent_size"]] * 1.08, "POD, 216 modes (held-out)", ha="right", fontsize=8,
                color=plotting.INK2)
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(lambda v, _: f"{100 * v:g}%")
        ax.yaxis.set_minor_formatter(lambda v, _: "")
        ax.set_yticks([0.05, 0.1, 0.2, 0.4, 0.8])
        ax.set_xlabel("epoch")
        ax.set_ylabel("validation reconstruction error")
        ax.set_title("Mesh_Reduced validation error during training")
        ax.legend(loc="upper right")
        plotting.save(fig, FIG / "training_curves.png")
        return FIG / "training_curves.png"

    curves_png = curves()
    return (curves_png,)


@app.cell
def _(curves_png, mo):
    mo.image(src=str(curves_png))
    return


@app.cell
def _(mo, pd, probe):
    def probe_table():
        rows = []
        for p in probe:
            rows.append({
                "grid": "×".join(str(s) for s in p["shape"]), "nodes": p["n_nodes"],
                "latent values": p.get("latent_size"),
                "peak GPU memory (GiB)": round(p["peak_gib"], 1) if p["ok"] else "out of memory",
                "seconds per training step (batch 1)": round(p["seconds_per_step"], 2) if p["ok"] else None,
            })
        return pd.DataFrame(rows)

    mo.vstack([
        mo.md(
            """
            ## How large a graph the stock model fits
            One training step at batch 1 for each graph size. Memory grows at about 0.6 MiB per
            node; the 36,864-node case ran only by spilling out of GPU memory. The full fine grid has
            8.4 million cells and the full-resolution patch 2.4 million.
            """
        ),
        mo.ui.table(probe_table(), selection=None),
    ])
    return


@app.cell
def _(mo):
    mo.md(
        """
        ## Caveats
        - **One model, one seed, one schedule.** No tuning of learning rate, latent shape, pivotal
          layout or width. A tuned model would do better; by how much is unknown.
        - **Small data.** 374 training snapshots from 18 configs. A linear basis is hard to beat
          with this little data, and the gap may narrow with more data. The corpus stores only about
          20 snapshots per beat, so more would mean re-running the CFD with denser output.
        - **Coarse input favours POD.** 8× block-averaging removes the fine structure that made
          POD slow to converge at full resolution in E5 (16% at 64 modes there, 11% here). The
          stock model cannot be run at that resolution on this GPU, so the comparison could only
          be made here.
        - **Regular grid as a graph.** `Mesh_Reduced` is built for unstructured meshes; on a
          regular grid a convolutional autoencoder is the natural neural comparator, and was not
          run.
        - **Reconstruction only.** Nothing here tests whether the latent is easier to step forward
          in time than POD coefficients, which is the reason to want a learned latent at all.
        - The `torch_scatter` / `torch_cluster` wheels do not match the installed torch (see
          Method).

        ## Next step
        Do not adopt stock `Mesh_Reduced` as the F3 encoder on this evidence. Use POD in the
        wing-fixed frame (E5: 99% of energy in 30 modes instead of 67) as the baseline latent, and
        make any neural encoder beat it at equal size before it earns a place. If a neural arm is
        wanted, a 3-D convolutional autoencoder on the wing-frame box is the cheaper experiment,
        and it can run at 4× rather than 8× block-averaging on this GPU.
        """
    )
    return


if __name__ == "__main__":
    app.run()
