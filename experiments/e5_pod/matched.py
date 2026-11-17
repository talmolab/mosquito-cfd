"""E5 follow-up: lab frame against wing frame on the same fluid, at full resolution.

The earlier wing-frame variant (``wingframe.py``) compared a 4x block-averaged wing-fixed box with
the whole lab patch, which is a different and larger region. Here both frames describe exactly the
fluid inside one wing-fixed box, at the corpus's own cell size (0.03125):

* ``wing``        POD of the field resampled onto the wing-fixed box, in wing axes.
* ``lab_masked``  POD of the lab field with every cell outside the box set to zero. Same fluid, same
                  energy, lab coordinates.
* ``lab_patch``   POD of the whole lab patch (as in E5), with its error counted only inside the box.

The box is chord +-0.75, span 0..3.0 (hinge to tip), normal +-0.875: the largest box on a 1/8 grid
that reaches the tip and stays inside the patch, without overlapping itself through the periodic
span boundary, at every pose in the sweep.

    --stage build     wing-frame matrix and lab masks (memory-mapped, under the field cache)
    --stage gram      inner products for ``wing`` and ``lab_masked``
    --stage analyze   spectra and held-out errors
    --stage control   the whole-patch lab POD again on a field smoothed as hard as a trilinear
                      resample can smooth it, to show the resample is not what helps the wing frame
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.record import write_run_record
from experiments.field import cache, pod
from experiments.field.matched import HalfCellSmoothed, box_mask, masked_gram, restricted_residuals
from experiments.field.wingframe import wing_frame_sample
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix

OUT = Path(__file__).parent / "outputs"
MAT = cache.CACHE_ROOT / "matrices"
HINGE = np.array([4.0, 0.5, 4.0])
DX = 0.03125
BOX_LO, BOX_HI = (-0.75, 0.0, -0.875), (0.75, 3.0, 0.875)
PERIOD_Y = 4.0
RANKS = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def _rot(row) -> np.ndarray:
    return rotation_matrix(*euler_angles(row.time, frequency=row.frequency_fstar,
                                         stroke_amp_rad=np.deg2rad(row.stroke_amp_deg),
                                         pitch_amp_rad=np.deg2rad(row.pitch_amp_deg)))


def _patch_axes() -> list[np.ndarray]:
    shape = tuple(np.load(OUT / "shapes.npz")["patch_u"])
    return [lo + DX / 2 + DX * np.arange(n) for lo, n in zip(cache.PATCH_LO, shape[:3])]


def build() -> None:
    idx = pd.read_parquet(OUT / "index.parquet")
    patch = np.load(MAT / "patch_u.npy", mmap_mode="r")
    x, y, z = _patch_axes()
    shape = (len(x), len(y), len(z), 3)
    ax = [np.arange(lo + DX / 2, hi, DX) for lo, hi in zip(BOX_LO, BOX_HI)]
    xi = np.stack(np.meshgrid(*ax, indexing="ij"), axis=-1).reshape(-1, 3)
    wing = np.lib.format.open_memmap(MAT / "matched_wing_u.npy", mode="w+", dtype=np.float32, shape=(len(idx), xi.size))
    masks = np.lib.format.open_memmap(MAT / "matched_mask.npy", mode="w+", dtype=np.bool_, shape=(len(idx), len(x) * len(y) * len(z)))
    out_of_patch = 0
    for i, row in idx.iterrows():
        r = _rot(row)
        pts = HINGE + xi @ r.T
        out_of_patch += int(((pts[:, 0] < x[0]) | (pts[:, 0] > x[-1]) | (pts[:, 2] < z[0]) | (pts[:, 2] > z[-1])).sum())
        field = np.asarray(patch[i], dtype=np.float64).reshape(shape) / row.u_ref
        wing[i] = wing_frame_sample(field, [x[0], y[0], z[0]], DX, r, HINGE, xi, periodic_len=(None, PERIOD_Y, None)).ravel()
        masks[i] = box_mask(x, y, z, r, HINGE, BOX_LO, BOX_HI, period_y=PERIOD_Y).ravel()
        if i % 50 == 0:
            print("build", i, len(idx), flush=True)
    wing.flush()
    masks.flush()
    assert out_of_patch == 0, f"{out_of_patch} wing-box points fall outside the patch"
    np.savez(OUT / "matched_shapes.npz", wing=np.array([len(a) for a in ax] + [3]), n_box_points=len(xi))
    print("built", wing.shape, masks.shape, "cells per mask:", int(masks[0].sum()), "box points:", len(xi), flush=True)


def gram() -> None:
    idx = pd.read_parquet(OUT / "index.parquet")
    wing = np.load(MAT / "matched_wing_u.npy", mmap_mode="r")
    np.save(OUT / "gram_matched_wing.npy", pod.gram(wing, block=20_000))
    print("gram wing", flush=True)
    patch = np.load(MAT / "patch_u.npy", mmap_mode="r")
    masks = np.load(MAT / "matched_mask.npy", mmap_mode="r")
    np.save(OUT / "gram_matched_lab_masked.npy", masked_gram(patch, masks, scale=1.0 / idx.u_ref.to_numpy(), block_cells=6_000))
    print("gram lab_masked", flush=True)


def analyze() -> None:
    idx = pd.read_parquet(OUT / "index.parquet")
    scale = 1.0 / idx.u_ref.to_numpy()
    train, test = np.flatnonzero(~idx.holdout.to_numpy()), np.flatnonzero(idx.holdout.to_numpy())
    pod.assert_no_holdout(idx.iloc[train], tuple(sorted(idx.config[idx.holdout].unique())))
    grams = {
        "wing": np.load(OUT / "gram_matched_wing.npy"),
        "lab_masked": np.load(OUT / "gram_matched_lab_masked.npy"),
        "lab_patch": np.load(OUT / "gram_patch_u.npy") * scale[:, None] * scale[None, :],
    }
    rows, spectra, fits = [], {}, {}
    for name, g in grams.items():
        g_tt, g_ht, sq_h = g[np.ix_(train, train)], g[np.ix_(test, train)], np.diag(g)[test]
        p = pod.fit_gram(g_tt)
        fits[name] = (p, g_ht)
        e = pod.energy_fraction_gram(p)
        spectra[f"{name}/energy"] = e
        centred = pod.centred_sq_norm(p, g_ht, sq_h)
        z = pod.encode_gram(p, g_ht)
        for r in RANKS:
            res = np.clip(centred - (z[:, :r] ** 2).sum(axis=1), 0.0, None)
            rows.append({"frame": name, "scored_on": "box" if name != "lab_patch" else "whole patch", "r": r,
                         "heldout_error": float(np.sqrt(res.sum() / centred.sum())),
                         "heldout_error_vs_total": float(np.sqrt(res.sum() / sq_h.sum())),
                         "modes_90": int(np.searchsorted(e, 0.90) + 1), "modes_99": int(np.searchsorted(e, 0.99) + 1),
                         "total_energy": float(sq_h.sum()), "centred_energy": float(centred.sum())})
    # whole-patch POD, error counted only inside the box
    patch = np.load(MAT / "patch_u.npy", mmap_mode="r")
    masks = np.load(MAT / "matched_mask.npy", mmap_mode="r")
    p, g_ht = fits["lab_patch"]
    rr = restricted_residuals(patch, masks, train, test, p, pod.encode_gram(p, g_ht), RANKS, scale=scale, block_cells=6_000)
    for j, r in enumerate(RANKS):
        rows.append({"frame": "lab_patch", "scored_on": "box", "r": r,
                     "heldout_error": float(np.sqrt(rr["residual"][:, j].sum() / rr["centred"].sum())),
                     "heldout_error_vs_total": float(np.sqrt(rr["residual"][:, j].sum() / rr["total"].sum())),
                     "total_energy": float(rr["total"].sum()), "centred_energy": float(rr["centred"].sum())})
    out = pd.DataFrame(rows)
    out.to_parquet(OUT / "matched.parquet", index=False)
    np.savez_compressed(OUT / "matched_spectra.npz", **spectra, box_residual=rr["residual"], box_centred=rr["centred"],
                        box_total=rr["total"], energy_wing=np.diag(grams["wing"]), energy_lab_masked=np.diag(grams["lab_masked"]))
    ratio = np.diag(grams["wing"]) / np.diag(grams["lab_masked"])
    write_run_record(OUT / "matched_record", inputs=[OUT / "index.parquet"], box_lo=BOX_LO, box_hi=BOX_HI,
                     ranks=RANKS, n_train=len(train), n_test=len(test),
                     wing_over_lab_energy=[float(ratio.min()), float(np.median(ratio)), float(ratio.max())])
    pd.set_option("display.width", 220)
    out["key"] = out.frame + " / " + out.scored_on
    print(out.pivot(index="r", columns="key", values="heldout_error").round(4))
    print(out.pivot(index="r", columns="key", values="heldout_error_vs_total").round(4))
    print(out.dropna(subset=["modes_90"]).groupby("frame")[["modes_90", "modes_99"]].first())
    print("wing / lab_masked energy per snapshot: min %.4f median %.4f max %.4f" % (ratio.min(), np.median(ratio), ratio.max()))


def control() -> None:
    idx = pd.read_parquet(OUT / "index.parquet")
    scale = 1.0 / idx.u_ref.to_numpy()
    train, test = np.flatnonzero(~idx.holdout.to_numpy()), np.flatnonzero(idx.holdout.to_numpy())
    shape = tuple(int(v) for v in np.load(OUT / "shapes.npz")["patch_u"])
    view = HalfCellSmoothed(np.load(MAT / "patch_u.npy", mmap_mode="r"), shape)
    masks = np.load(MAT / "matched_mask.npy", mmap_mode="r")
    gpath = OUT / "gram_matched_lab_smoothed.npy"
    if not gpath.is_file():
        np.save(gpath, pod.gram(view, block=int(np.prod(shape[1:]))))
        print("gram lab_smoothed", flush=True)
    g = np.load(gpath) * scale[:, None] * scale[None, :]
    g_ht, sq_h = g[np.ix_(test, train)], np.diag(g)[test]
    p = pod.fit_gram(g[np.ix_(train, train)])
    e = pod.energy_fraction_gram(p)
    rr = restricted_residuals(view, masks, train, test, p, pod.encode_gram(p, g_ht), RANKS, scale=scale,
                              block_cells=shape[1] * shape[2])
    rows = []
    for j, r in enumerate(RANKS):
        rows.append({"frame": "lab_patch_smoothed", "scored_on": "whole patch", "r": r,
                     "heldout_error": pod.recon_error_gram(p, g_ht, sq_h, r),
                     "modes_90": int(np.searchsorted(e, 0.90) + 1), "modes_99": int(np.searchsorted(e, 0.99) + 1)})
        rows.append({"frame": "lab_patch_smoothed", "scored_on": "box", "r": r,
                     "heldout_error": float(np.sqrt(rr["residual"][:, j].sum() / rr["centred"].sum())),
                     "heldout_error_vs_total": float(np.sqrt(rr["residual"][:, j].sum() / rr["total"].sum())),
                     "total_energy": float(rr["total"].sum())})
    out = pd.DataFrame(rows)
    out.to_parquet(OUT / "matched_control.parquet", index=False)
    raw_total = float(np.load(OUT / "matched_spectra.npz")["box_total"].sum())
    pd.set_option("display.width", 220)
    print(out.pivot(index="r", columns="scored_on", values="heldout_error").round(4))
    print(out.dropna(subset=["modes_90"])[["modes_90", "modes_99"]].iloc[0].to_dict())
    print("smoothed / raw energy inside the box (held-out): %.4f" % (float(rr["total"].sum()) / raw_total))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["build", "gram", "analyze", "control"], required=True)
    {"build": build, "gram": gram, "analyze": analyze, "control": control}[ap.parse_args().stage]()
