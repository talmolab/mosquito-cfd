"""E7 movies: CFD beside the 64-mode reconstruction and the prediction from kinematics, one holdout config.

Everything is computed in the wing-fixed box (wing axes) and drawn in the lab frame: the Q-criterion
surface is extracted in wing axes, where the three fields live, and its triangles are rotated back
with the wing's pose. Q and vorticity magnitude do not change under a fixed rotation of the axes, so
no resampling is involved. The surface is clipped to the box, identically in all three panels.

    --stage decode   fields for one config -> experiments/_cache/e7/<config>.npz (reads the share)
    --stage still    one frame as PNG
    --stage movie    all frames as mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.e5_pod.matched import BOX_LO, DX, HINGE, _rot
from experiments.field import pod

HERE = Path(__file__).parent
E5 = HERE.parent / "e5_pod" / "outputs"
REPO = HERE.parents[1]
SHARE = Path("Z:/users/eberrigan/mosquito-cfd/examples/explore_surrogate_2026-11/field_cache/matrices")
LOCAL = HERE.parent / "_cache" / "e7"
R = 64
# The corpus configs are gentler than the 70-degree T3c run the video defaults were tuned on.
Q_LEVEL, VORT_RANGE = 50.0, (10.0, 90.0)
ERR_MAX = 0.20  # top of the error colour scale, as a share of the reference speed (peak speed at the radius of gyration)
LAYOUTS = {
    "three": (("truth", "CFD"), ("recon", f"rebuilt from {R} numbers"), ("pred", "predicted from kinematics")),
    "diff": (("truth", "CFD"), ("pred", "predicted from kinematics"),
             ("diff", "CFD vortex surface, coloured by prediction error")),
}


class _Rows:
    """``a[:, lo:hi]`` restricted to some rows, without loading the other columns."""

    def __init__(self, a, rows):
        self._a, self._rows, self.shape = a, rows, (len(rows), a.shape[1])

    def __getitem__(self, key):
        return np.asarray(self._a[:, key[1]])[self._rows]


def decode(config: str) -> None:
    idx = pd.read_parquet(E5 / "index.parquet").reset_index(drop=True)
    train, test = np.flatnonzero(~idx.holdout.to_numpy()), np.flatnonzero(idx.holdout.to_numpy())
    co = np.load(HERE / "outputs" / "coefficients.npz")
    assert np.array_equal(co["train"], train) and np.array_equal(co["test"], test)
    sel = np.flatnonzero(idx.config.to_numpy()[test] == config)
    assert len(sel), f"{config} is not a holdout config"
    g = np.load(E5 / "gram_matched_wing.npy")
    p = pod.fit_gram(g[np.ix_(train, train)])
    wing = np.load(SHARE / "matched_wing_u.npy", mmap_mode="r")
    LOCAL.mkdir(parents=True, exist_ok=True)
    mpath = LOCAL / f"wing_modes_{R}.npz"
    if not mpath.exists():
        modes, mean = pod.modes_from_gram(p, _Rows(wing, train), R, block=60_000)
        np.savez(mpath, modes=modes, mean=mean)
    m = np.load(mpath)
    modes, mean = m["modes"].astype(np.float64), m["mean"].astype(np.float64)
    rows = idx.iloc[test[sel]]
    truth = np.asarray(wing[test[sel]], dtype=np.float64)
    out = {"truth": truth, "recon": co["wing/z_true"][sel, :R] @ modes + mean, "pred": co["wing/z_pred"][sel, :R] @ modes + mean}
    cen = ((truth - mean) ** 2).sum()
    for k in ("recon", "pred"):
        print(k, "error on this config:", float(np.sqrt(((out[k] - truth) ** 2).sum() / cen)))
    shape = tuple(np.load(E5 / "matched_shapes.npz")["wing"])
    np.savez(LOCAL / f"{config}.npz", shape=shape, **{k: (v * rows.u_ref.to_numpy()[:, None]).astype(np.float32) for k, v in out.items()})
    rows.to_parquet(LOCAL / f"{config}.parquet")


def _setup(config: str):
    from mosquito_cfd.visualization.flow_video import _draw_wing_scene, _euler_angles
    from mosquito_cfd.geometry.vertex_io import read_vertex_file
    from mosquito_cfd.visualization.wing_render import leading_edge_mask, resolve_kinematics_kwargs, wing_outline

    corpus = REPO / "examples" / "prelim_sweep_fine"
    kin = resolve_kinematics_kwargs(config_name=config, corpus_dir=corpus, center=None, hinge=tuple(HINGE),
                                    stroke_amp_deg=None, pitch_amp_deg=None, frequency_fstar=None)
    local = read_vertex_file(str(REPO / "examples" / "flapping_wing" / "wing.vertex"))
    centre = np.asarray(kin["center"], dtype=float)
    wing = dict(ref_markers=local + centre, outline_ref=wing_outline(local) + centre, is_leading=leading_edge_mask(local),
                hinge_arr=np.asarray(kin["hinge"], dtype=float))
    return kin, wing, _draw_wing_scene, _euler_angles


def _draw(axes, panels, fields, shape, rows, i, kin, wing, draw_wing, euler, limits):
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from mosquito_cfd.visualization.flow_video import _VIEW_AZIM, _VIEW_ELEV, render_lev_frame
    from mosquito_cfd.visualization.wing_render import transform_markers

    row = rows.iloc[i]
    rot = _rot(row)
    for ax, (key, title) in zip(axes, panels):
        ax.clear()
        if key == "diff":
            fr = _error_surface(fields["pred"][i], fields["truth"][i], shape, float(row.u_ref))
        else:
            f = fields[key][i].reshape(shape).astype(np.float64)
            fr = render_lev_frame(f[..., 0], f[..., 1], f[..., 2], DX, q_threshold=Q_LEVEL,
                                  vort_vmin=VORT_RANGE[0], vort_vmax=VORT_RANGE[1])
        if fr is not None:
            xi = fr["triangles"] + (np.asarray(BOX_LO) + DX / 2)
            ax.add_collection3d(Poly3DCollection(HINGE + xi @ rot.T, facecolors=fr["facecolors"], edgecolor="none", zorder=1))
        phi, alpha, theta = euler(float(row.time), kin)
        o = transform_markers(wing["outline_ref"], wing["hinge_arr"], phi, alpha, theta)
        o = np.vstack([o, o[:1]])
        ax.plot(o[:, 0], o[:, 1], o[:, 2], color="#111111", lw=2.0, zorder=20)
        ax.scatter(*[[c] for c in wing["hinge_arr"]], color="#111111", s=60, zorder=22, depthshade=False, edgecolor="white")
        ax.set_title(title, fontsize=13)
        ax.view_init(elev=_VIEW_ELEV, azim=_VIEW_AZIM)
        ax.set_xlim(*limits[0]); ax.set_ylim(*limits[1]); ax.set_zlim(*limits[2])
        ax.set_box_aspect([b - a for a, b in limits], zoom=0.82)
        ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
        ax.set_xticks(np.arange(2, 7)); ax.set_yticks(np.arange(1, 4)); ax.set_zticks([3, 4, 5])


def _error_surface(pred, truth, shape, u_ref):
    """The CFD field's Q surface, coloured by the size of the velocity error there (share of ``u_ref``)."""
    from scipy.ndimage import map_coordinates
    from skimage import measure

    import matplotlib

    SEQ = matplotlib.colormaps["YlOrRd"]
    from mosquito_cfd.benchmarks.lev import q_criterion

    f = truth.reshape(shape).astype(np.float64)
    q = q_criterion(f[..., 0], f[..., 1], f[..., 2], DX)
    if not (q.min() < Q_LEVEL < q.max()):
        return None
    verts, faces, _, _ = measure.marching_cubes(q, level=Q_LEVEL)
    err = np.linalg.norm(pred.reshape(shape).astype(np.float64) - f, axis=-1) / u_ref
    at_faces = map_coordinates(err, verts.T, order=1, mode="nearest")[faces].mean(axis=1)
    colours = SEQ(np.clip(at_faces / ERR_MAX, 0.0, 1.0))
    colours[:, 3] = 0.65  # same see-through level as the other panels, so the far side is not hidden
    return {"triangles": (verts * DX)[faces], "facecolors": colours}


def render(config: str, *, frame: int | None, fps: int, layout: str = "three") -> None:
    import imageio_ffmpeg
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation

    d = np.load(LOCAL / f"{config}.npz")
    shape, rows = tuple(d["shape"]), pd.read_parquet(LOCAL / f"{config}.parquet")
    panels = LAYOUTS[layout]
    fields = {k: d[k] for k in ("truth", "recon", "pred")}
    kin, wing, draw_wing, euler = _setup(config)
    limits = [(HINGE[0] - 2.6, HINGE[0] + 2.6), (HINGE[1] - 0.4, HINGE[1] + 3.2), (HINGE[2] - 1.5, HINGE[2] + 1.5)]
    fig = plt.figure(figsize=(18, 6.6), facecolor="white")
    axes = [fig.add_axes([0.005 + 0.333 * k, 0.09, 0.325, 0.80], projection="3d") for k in range(3)]
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    cax = fig.add_axes([0.05, 0.075, 0.22, 0.022])
    cb = fig.colorbar(ScalarMappable(Normalize(*VORT_RANGE), "plasma"), cax=cax, orientation="horizontal")
    cb.set_label("surface colour: vorticity magnitude (solver units)", fontsize=11)
    key = (f"Surface: Q = {Q_LEVEL:g}, where rotation outweighs strain (a vortex).   Black line: wing outline.   Dot: hinge."
           + ("\nRight panel: the CFD surface again, coloured by how far the predicted velocity is from the CFD's."
              if layout == "diff" else ""))
    fig.text(0.29, 0.07, key, fontsize=11, va="center", ha="left", linespacing=1.6)
    if layout == "diff":
        SEQ = matplotlib.colormaps["YlOrRd"]
        eax = fig.add_axes([0.77, 0.075, 0.20, 0.022])
        eb = fig.colorbar(ScalarMappable(Normalize(0, 100 * ERR_MAX), SEQ), cax=eax, orientation="horizontal", extend="max")
        eb.set_label("right panel: velocity error (% of reference wing speed)", fontsize=11)

    def draw(i):
        _draw(axes, panels, fields, shape, rows, i, kin, wing, draw_wing, euler, limits)
        fig.suptitle(f"{config} (held out), phase {rows.phase.iloc[i]:.2f} of beat 2: vortex surface (Q criterion) "
                     "inside the wing-fixed box", fontsize=14, y=0.985)

    (HERE / "figures").mkdir(exist_ok=True)
    if frame is not None:
        draw(frame)
        fig.savefig(HERE / "figures" / f"{config}_{layout}_lev3d_frame{frame:02d}.png", dpi=110)
    else:
        anim = FuncAnimation(fig, draw, frames=len(rows), interval=int(1000 / fps))
        anim.save(HERE / "figures" / f"{config}_{layout}_flow_lev-3d.mp4", writer=FFMpegWriter(fps=fps, bitrate=4000), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=("decode", "still", "movie"))
    ap.add_argument("--config", default="s45_f100_p60")
    ap.add_argument("--frame", type=int, default=5)
    ap.add_argument("--fps", type=int, default=2)
    ap.add_argument("--layout", default="three", choices=tuple(LAYOUTS))
    a = ap.parse_args()
    if a.stage == "decode":
        decode(a.config)
    else:
        render(a.config, frame=a.frame if a.stage == "still" else None, fps=a.fps, layout=a.layout)
