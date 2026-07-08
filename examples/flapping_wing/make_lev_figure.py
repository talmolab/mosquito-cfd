"""Leading-edge-vortex figure (Tier T3b): vorticity slice, coarse vs medium, at mid-stroke.

Needs the plotfiles on the cluster/Z: drive — set ``MOSQUITO_CFD_PLOTFILE_ROOT`` to the directory
containing the ``t2a-newconv4`` (coarse) and ``t3b-medium`` (medium) run dirs. Extracts the velocity
field over the wing near-field box via the reused ``extract_eulerian_box``, computes
``vorticity_magnitude`` (``benchmarks/lev.py``), and draws the mid-stroke (t ~ 0.5, ``plt01000``)
stroke-plane slice side by side with the wing markers overlaid. Writes
``figures/fig_lev_coarse_vs_medium.{png,pdf}``.

The bright band on the wing markers is partly the immersed-boundary regularization layer (the wing
surface); the genuine leading-edge / tip vortex is the structure trailing off the leading edge — sharper
on the medium grid. Run:
``MOSQUITO_CFD_PLOTFILE_ROOT=<...> uv run python examples/flapping_wing/make_lev_figure.py``
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mosquito_cfd.benchmarks.lev import vorticity_magnitude
from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

_HERE = Path(__file__).parent
_LO, _HI = (2.5, 0.0, 3.0), (5.5, 4.0, 5.0)  # wing near-field box
_Z_SLICE = 4.0  # stroke plane
_GRIDS = (
    ("coarse  64x32x64  (dx=0.125)", "t2a-newconv4"),
    ("medium  128x64x128  (dx=0.0625)", "t3b-medium"),
)


def _slice(root: Path, subdir: str):
    plt_dir = root / subdir / "plt01000"
    box = extract_eulerian_box(str(plt_dir), lo=_LO, hi=_HI)
    w = vorticity_magnitude(box["u"], box["v"], box["w"], box["dx"])
    k = int(np.argmin(np.abs(box["z"] - _Z_SLICE)))
    import yt

    yt.set_log_level("error")
    ad = yt.load(str(plt_dir)).all_data()
    mx = np.array(ad["all", "particle_position_x"])
    my = np.array(ad["all", "particle_position_y"])
    mz = np.array(ad["all", "particle_position_z"])
    near = np.abs(mz - _Z_SLICE) < 0.25
    return box["x"], box["y"], w[:, :, k].T, (mx[near], my[near])


def make_figure(out: Path = _HERE / "figures" / "fig_lev_coarse_vs_medium.png") -> Path:
    """Draw the coarse-vs-medium mid-stroke vorticity slice and save PNG + PDF."""
    root = os.environ.get("MOSQUITO_CFD_PLOTFILE_ROOT")
    if not root or not Path(root).is_dir():
        raise SystemExit(
            "set MOSQUITO_CFD_PLOTFILE_ROOT to the dir holding t2a-newconv4/ and t3b-medium/"
        )
    root = Path(root)
    data = [(_slice(root, sub), tag) for tag, sub in _GRIDS]
    vmax = np.percentile(
        data[1][0][2], 99
    )  # clip on the medium field so shed structure shows

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), sharex=True, sharey=True)
    for ax, ((x, y, w, mk), tag) in zip(axes, data):
        im = ax.imshow(
            w,
            origin="lower",
            extent=[x[0], x[-1], y[0], y[-1]],
            aspect="equal",
            cmap="inferno",
            vmin=0,
            vmax=vmax,
        )
        ax.scatter(mk[0], mk[1], s=2, c="cyan", alpha=0.5, label="wing markers")
        ax.set_title(tag, fontsize=11)
        ax.set_xlabel("x  (chordwise)")
        ax.legend(fontsize=8, loc="upper left", framealpha=0.6)
    axes[0].set_ylabel("y  (spanwise)")
    cb = fig.colorbar(im, ax=axes, fraction=0.025, pad=0.02)
    cb.set_label("vorticity magnitude ||omega||")
    fig.suptitle(
        "Leading-edge vortex at mid-stroke (t~0.5, stroke-plane slice z=4): coarse vs medium grid",
        fontsize=12,
        fontweight="bold",
    )
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    fig.savefig(out.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    print("wrote", make_figure())
