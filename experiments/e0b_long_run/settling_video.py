"""E0b movie: the same wing motion in an early beat and in beat 6, to show the flow has not settled.

Three panels at matching phase: the early beat, beat 6, and beat 6's vortex surface coloured by how
far the early beat's velocity is from it. Coarse grid (64 x 32 x 64), local 6-beat runs that wrote a
plotfile every 100 steps (20 per beat).

    --stage cache   near-wing velocity for every plotfile -> experiments/_cache/e0b/<run>.npz
    --stage still   one phase as PNG
    --stage movie   one beat as mp4
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from experiments.e5_pod.run import u_ref

HERE = Path(__file__).parent
REPO = HERE.parents[1]
LOCAL = HERE.parent / "_cache" / "e0b"
HINGE = np.array([4.0, 0.5, 4.0])
BOX_LO, BOX_HI = (1.0, 0.0, 2.5), (7.0, 4.0, 5.5)  # the near-wing patch used for the fine corpus
STEPS_PER_BEAT, PLOT_INT = 2000, 100
ALPHA = 0.65


def _params(config: str) -> tuple[float, float, float]:
    s, f, p = config.split("_")
    return float(s[1:]), float(f[1:]) / 100.0, float(p[1:])


def cache(config: str, suffix: str) -> None:
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    run = HERE / f"run_{config}{suffix}"
    steps = list(range(0, 6 * STEPS_PER_BEAT, PLOT_INT))
    u, t, axes = [], [], None
    for s in steps:
        box = extract_eulerian_box(str(run / f"plt{s:05d}"), lo=BOX_LO, hi=BOX_HI)
        u.append(np.stack([box["u"], box["v"], box["w"]], axis=-1).astype(np.float32))
        t.append(float(box["current_time"]))
        axes = (box["x"], box["y"], box["z"], np.atleast_1d(box["dx"]))
        if s % 2000 == 0:
            print("read", s, u[-1].shape, t[-1], flush=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    np.savez(LOCAL / f"{config}{suffix}.npz", u=np.stack(u), time=np.array(t), step=np.array(steps),
             x=axes[0], y=axes[1], z=axes[2], dx=axes[3])


def _surface(f, dx, q_level, colour_by, vmin, vmax, cmap):
    """Q surface of velocity field ``f``, coloured by the scalar field ``colour_by``."""
    import matplotlib
    from scipy.ndimage import map_coordinates
    from skimage import measure

    from mosquito_cfd.benchmarks.lev import q_criterion

    q = q_criterion(f[..., 0], f[..., 1], f[..., 2], dx)
    if not (q.min() < q_level < q.max()):
        return None
    verts, faces, _, _ = measure.marching_cubes(q, level=q_level)
    val = map_coordinates(colour_by, verts.T, order=1, mode="nearest")[faces].mean(axis=1)
    col = matplotlib.colormaps[cmap](np.clip((val - vmin) / (vmax - vmin), 0.0, 1.0))
    col[:, 3] = ALPHA
    return (verts * dx)[faces], col


def render(config: str, suffix: str, *, early: int, frame: int | None, fps: int, q_level: float, vort_max: float,
           diff_max: float) -> None:
    import imageio_ffmpeg
    import matplotlib

    matplotlib.use("Agg")
    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    import matplotlib.pyplot as plt
    from matplotlib.animation import FFMpegWriter, FuncAnimation
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from mosquito_cfd.benchmarks.lev import vorticity_magnitude
    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles
    from mosquito_cfd.geometry.vertex_io import read_vertex_file
    from mosquito_cfd.visualization.flow_video import _VIEW_AZIM, _VIEW_ELEV
    from mosquito_cfd.visualization.wing_render import transform_markers, wing_outline

    d = np.load(LOCAL / f"{config}{suffix}.npz")
    dx, origin = float(d["dx"][0]), np.array([d["x"][0], d["y"][0], d["z"][0]])
    stroke, fstar, pitch = _params(config)
    uref = u_ref(stroke, fstar)
    per = STEPS_PER_BEAT // PLOT_INT
    outline = wing_outline(read_vertex_file(str(REPO / "examples" / "flapping_wing" / "wing.vertex"))) + np.array([4.0, 2.0, 4.0])
    limits = [(HINGE[0] - 2.6, HINGE[0] + 2.6), (HINGE[1] - 0.4, HINGE[1] + 3.2), (HINGE[2] - 1.5, HINGE[2] + 1.5)]
    fig = plt.figure(figsize=(18, 6.6), facecolor="white")
    axes = [fig.add_axes([0.005 + 0.333 * k, 0.09, 0.325, 0.80], projection="3d") for k in range(3)]
    cb = fig.colorbar(ScalarMappable(Normalize(0, vort_max), "plasma"), cax=fig.add_axes([0.05, 0.075, 0.22, 0.022]),
                      orientation="horizontal", extend="max")
    cb.set_label("surface colour: vorticity magnitude (solver units)", fontsize=11)
    eb = fig.colorbar(ScalarMappable(Normalize(0, 100 * diff_max), "YlOrRd"), cax=fig.add_axes([0.77, 0.075, 0.20, 0.022]),
                      orientation="horizontal", extend="max")
    eb.set_label(f"right panel: velocity change, beat {early} to 6 (% of wing speed)", fontsize=11)
    fig.text(0.29, 0.07, f"Surface: Q = {q_level:g}, where rotation outweighs strain (a vortex).   Black line: wing outline.   "
             f"Dot: hinge.\nRight panel: the beat 6 surface again, coloured by how far beat {early}'s velocity is from beat 6's.",
             fontsize=11, va="center", ha="left", linespacing=1.6)
    titles = (f"beat {early}", "beat 6", f"beat 6 surface, coloured by its difference from beat {early}")

    def draw(k):
        a, b = d["u"][(early - 1) * per + k].astype(np.float64), d["u"][5 * per + k].astype(np.float64)
        diff = np.linalg.norm(a - b, axis=-1) / uref
        surfaces = (
            _surface(a, dx, q_level, vorticity_magnitude(a[..., 0], a[..., 1], a[..., 2], dx), 0, vort_max, "plasma"),
            _surface(b, dx, q_level, vorticity_magnitude(b[..., 0], b[..., 1], b[..., 2], dx), 0, vort_max, "plasma"),
            _surface(b, dx, q_level, diff, 0, diff_max, "YlOrRd"),
        )
        t = float(d["time"][5 * per + k])
        phi, alpha, theta = euler_angles(t, frequency=fstar, stroke_amp_rad=np.deg2rad(stroke), pitch_amp_rad=np.deg2rad(pitch))
        o = transform_markers(outline, HINGE, phi, alpha, theta)
        o = np.vstack([o, o[:1]])
        for ax, s, title in zip(axes, surfaces, titles):
            ax.clear()
            if s is not None:
                ax.add_collection3d(Poly3DCollection(s[0] + origin, facecolors=s[1], edgecolor="none", zorder=1))
            ax.plot(o[:, 0], o[:, 1], o[:, 2], color="#111111", lw=2.0, zorder=20)
            ax.scatter(*[[c] for c in HINGE], color="#111111", s=60, zorder=22, depthshade=False, edgecolor="white")
            ax.set_title(title, fontsize=13)
            ax.view_init(elev=_VIEW_ELEV, azim=_VIEW_AZIM)
            ax.set_xlim(*limits[0]); ax.set_ylim(*limits[1]); ax.set_zlim(*limits[2])
            ax.set_box_aspect([hi - lo for lo, hi in limits], zoom=0.82)
            ax.set_xlabel("x"); ax.set_ylabel("y"); ax.set_zlabel("z")
            ax.set_xticks(np.arange(2, 7)); ax.set_yticks(np.arange(1, 4)); ax.set_zticks([3, 4, 5])
        fig.suptitle(f"{config}, coarse grid, phase {k / per:.2f}: the same motion in beat {early} and in beat 6 "
                     "(vortex surface, Q criterion)", fontsize=14, y=0.985)

    (HERE / "figures").mkdir(exist_ok=True)
    stem = f"{config}_beat{early}_vs_beat6"
    if frame is not None:
        draw(frame)
        fig.savefig(HERE / "figures" / f"{stem}_frame{frame:02d}.png", dpi=110)
    else:
        FuncAnimation(fig, draw, frames=per, interval=int(1000 / fps)).save(
            HERE / "figures" / f"{stem}_flow_lev-3d.mp4", writer=FFMpegWriter(fps=fps, bitrate=4000), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=("cache", "still", "movie"))
    ap.add_argument("--config", default="s45_f100_p30")
    ap.add_argument("--suffix", default="_fields")
    ap.add_argument("--early", type=int, default=2)
    ap.add_argument("--frame", type=int, default=12)
    ap.add_argument("--fps", type=int, default=2)
    ap.add_argument("--q-level", type=float, default=20.0)
    ap.add_argument("--vort-max", type=float, default=40.0)
    ap.add_argument("--diff-max", type=float, default=0.10)
    a = ap.parse_args()
    if a.stage == "cache":
        cache(a.config, a.suffix)
    else:
        render(a.config, a.suffix, early=a.early, frame=a.frame if a.stage == "still" else None, fps=a.fps,
               q_level=a.q_level, vort_max=a.vort_max, diff_max=a.diff_max)
