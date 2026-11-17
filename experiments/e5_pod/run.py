"""E5: POD spectrum of the velocity field, and how well a basis transfers to unseen configs (plan Task 7).

    --stage matrices   stack the cached snapshots into memory-mapped matrices (once)
    --stage gram       snapshot inner products for the patch and the downsampled whole domain
    --stage analyze    spectra, held-out reconstruction error, force probe, mode slices

Velocities are divided by each config's reference speed u_ref = 2 pi f* phi0 r_gyr (the speed the
force coefficients are normalized with), so every config carries comparable weight.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, dataset_path, holdout_configs, load_dataset
from experiments.common.record import write_run_record
from experiments.field import cache, pod
from mosquito_cfd.force_surrogate.constants import R_GYRATION

OUT = Path(__file__).parent / "outputs"
MAT = cache.CACHE_ROOT / "matrices"
FIELDS = {"patch_u": "near-wing patch, full resolution", "full4_u": "whole domain, 4x downsampled"}
RANKS = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def u_ref(stroke_amp_deg: float, fstar: float) -> float:
    return 2.0 * np.pi * fstar * np.deg2rad(stroke_amp_deg) * R_GYRATION


def load_index() -> pd.DataFrame:
    idx = pd.read_parquet(OUT / "index.parquet")
    return idx


def matrices() -> None:
    OUT.mkdir(exist_ok=True)
    MAT.mkdir(parents=True, exist_ok=True)
    idx = cache.index(cache.CACHE_ROOT)
    idx = idx[idx.wingbeat == 1].sort_values(["config", "step"]).reset_index(drop=True)
    meta = load_dataset("fine").groupby("config_name")[["stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"]].first()
    idx = idx.join(meta, on="config")
    idx["u_ref"] = [u_ref(s, f) for s, f in zip(idx.stroke_amp_deg, idx.frequency_fstar)]
    idx["holdout"] = idx.config.isin(holdout_configs())
    assert idx.config.nunique() == 27 and not idx.isna().any().any()
    shapes = {}
    for key in FIELDS:
        first = cache.load(cache.CACHE_ROOT, idx.config[0], int(idx.step[0]), (key,))[key]
        shapes[key] = first.shape
        mm = np.lib.format.open_memmap(MAT / f"{key}.npy", mode="w+", dtype=np.float32, shape=(len(idx), first.size))
        for i, row in idx.iterrows():
            mm[i] = cache.load(cache.CACHE_ROOT, row.config, int(row.step), (key,))[key].ravel()
        mm.flush()
        del mm
        print(key, shapes[key], len(idx), flush=True)
    idx.drop(columns=["path"]).to_parquet(OUT / "index.parquet", index=False)
    np.savez(OUT / "shapes.npz", **{k: np.array(v) for k, v in shapes.items()})


def gram() -> None:
    for key in FIELDS:
        mm = np.load(MAT / f"{key}.npy", mmap_mode="r")
        np.save(OUT / f"gram_{key}.npy", pod.gram(mm))
        print("gram", key, mm.shape, flush=True)


def _phase_force(idx: pd.DataFrame) -> np.ndarray:
    """The six force coefficients at each snapshot's phase (second beat, periodic interpolation)."""
    df = load_dataset("fine")
    df = df[df.wingbeat == 1]
    out = np.empty((len(idx), 6))
    for cfg, rows in idx.groupby("config"):
        d = df[df.config_name == cfg].sort_values("phase")
        for j, t in enumerate(TARGETS):
            out[rows.index, j] = np.interp(rows.phase.to_numpy(), d.phase.to_numpy(), d[t].to_numpy(), period=1.0)
    return out


def analyze() -> None:
    idx = load_index()
    scale = 1.0 / idx.u_ref.to_numpy()
    train = np.flatnonzero(~idx.holdout.to_numpy())
    test = np.flatnonzero(idx.holdout.to_numpy())
    pod.assert_no_holdout(idx.iloc[train], holdout_configs())
    forces = _phase_force(idx)
    rows, spectra = [], {}
    for key in FIELDS:
        g = np.load(OUT / f"gram_{key}.npy") * scale[:, None] * scale[None, :]
        # per-config spectra
        for cfg, r in idx.groupby("config"):
            p = pod.fit_gram(g[np.ix_(r.index, r.index)])
            e = pod.energy_fraction_gram(p)
            rows.append({"field": key, "scope": "per_config", "config": cfg, "holdout": bool(r.holdout.iloc[0]),
                         "n_snap": len(r), "modes_90": int(np.searchsorted(e, 0.90) + 1),
                         "modes_99": int(np.searchsorted(e, 0.99) + 1)})
        # pooled over the 21 training configs
        p = pod.fit_gram(g[np.ix_(train, train)])
        e = pod.energy_fraction_gram(p)
        spectra[f"{key}/pooled_energy"] = e
        spectra[f"{key}/pooled_sing"] = p.sing
        rows.append({"field": key, "scope": "pooled_train", "config": "21 training configs", "holdout": False,
                     "n_snap": len(train), "modes_90": int(np.searchsorted(e, 0.90) + 1),
                     "modes_99": int(np.searchsorted(e, 0.99) + 1)})
        g_tt, g_ht, sq_h = g[np.ix_(train, train)], g[np.ix_(test, train)], np.diag(g)[test]
        sq_t = np.diag(g)[train]
        z_train, z_test = pod.encode_gram(p, g_tt), pod.encode_gram(p, g_ht)
        for r in [r for r in RANKS if r <= len(p.sing)]:
            rec = {"field": key, "r": r, "train_error": pod.recon_error_gram(p, g_tt, sq_t, r),
                   "heldout_error": pod.recon_error_gram(p, g_ht, sq_h, r)}
            for cfg, rr in idx.iloc[test].groupby("config"):
                loc = np.flatnonzero(np.isin(test, rr.index))
                rec[f"heldout_error/{cfg}"] = pod.recon_error_gram(p, g_ht[loc], sq_h[loc], r)
            # force probe: ridge from the first r coefficients (standardized on training) to the six CFs
            a, b = z_train[:, :r], z_test[:, :r]
            sd = a.std(axis=0)
            a1 = np.column_stack([np.ones(len(a)), a / sd])
            b1 = np.column_stack([np.ones(len(b)), b / sd])
            reg = 1e-6 * len(a) * np.eye(a1.shape[1])
            reg[0, 0] = 0.0
            coef = np.linalg.solve(a1.T @ a1 + reg, a1.T @ forces[train])
            pred = b1 @ coef
            y = forces[test]
            rec["probe_r2"] = float(np.mean(1 - ((pred - y) ** 2).sum(0) / ((y - y.mean(0)) ** 2).sum(0)))
            rows.append({"scope": "rank", **rec})
        # the mean field's share: how much of the held-out energy is the training mean alone?
        total_h = float(sq_h.sum())
        centred_h = float(pod.centred_sq_norm(p, g_ht, sq_h).sum())
        rows.append({"field": key, "scope": "mean_share", "heldout_mean_removed_share": centred_h / total_h})
        if key == "patch_u":
            mm = np.load(MAT / f"{key}.npy", mmap_mode="r")
            shape = tuple(np.load(OUT / "shapes.npz")[key])
            n_modes = 6
            y_mid = shape[1] // 2  # mid-span plane only; the full modes are never formed
            plane = np.arange(np.prod(shape)).reshape(shape)[:, y_mid, :, :].ravel()
            sub = np.asarray(mm[:, plane][train], dtype=np.float64) * scale[train][:, None]
            subc = sub - sub.mean(axis=0)
            sl = (p.vecs[:, :n_modes].T @ subc) / p.sing[:n_modes, None]
            spectra["patch_u/mode_slices"] = sl.reshape(n_modes, shape[0], shape[2], 3).astype(np.float32)
            spectra["patch_u/mean_slice"] = sub.mean(axis=0).reshape(shape[0], shape[2], 3).astype(np.float32)
    pd.DataFrame(rows).to_parquet(OUT / "results.parquet", index=False)
    np.savez_compressed(OUT / "spectra.npz", **spectra)
    write_run_record(OUT, inputs=[dataset_path("fine")], n_snapshots=len(idx), n_train=len(train), n_test=len(test),
                     snapshots_used=[f"{c}/{s:05d}" for c, s in zip(idx.config, idx.step)], ranks=RANKS,
                     normalization="velocity / u_ref per config")
    res = pd.DataFrame(rows)
    pd.set_option("display.width", 220)
    print(res[res.scope == "rank"][["field", "r", "train_error", "heldout_error", "probe_r2"]].round(4))
    print(res[res.scope == "per_config"].groupby("field")[["modes_90", "modes_99", "n_snap"]].agg(["min", "median", "max"]))
    print(res[res.scope == "pooled_train"][["field", "n_snap", "modes_90", "modes_99"]])
    print(res[res.scope == "mean_share"][["field", "heldout_mean_removed_share"]])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["matrices", "gram", "analyze"], required=True)
    {"matrices": matrices, "gram": gram, "analyze": analyze}[ap.parse_args().stage]()
