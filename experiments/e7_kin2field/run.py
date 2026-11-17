"""E7: predict the near-wing velocity field of an unseen config from kinematics and phase alone.

The E4 ridge model (Fourier harmonics in phase x polynomials in stroke amplitude, frequency and
pitch amplitude) is fitted to the POD coefficients of the 21 training configs and asked for the
coefficients of the 6 holdout configs. The decoded field's error is compared with

* ``reconstruction``  the same number of modes given the holdout snapshot's own coefficients
                      (the best any model writing through this basis can do);
* ``nearest``         reusing the training snapshot nearest in kinematics and phase (no model);
* 100%                predicting the training-mean field (the error is relative to that).

Three descriptions of the flow, as in E5 follow-up 2: ``wing`` (wing-fixed box, wing axes),
``lab_masked`` (the same fluid in lab axes) and ``lab_patch`` (the whole lab patch).

Everything comes from the Gram matrices E5 saved, so no field data is read. Model size (harmonics,
degree, ridge strength) is chosen by leave-one-config-out inside the training configs, at 64 modes.
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.record import write_run_record
from experiments.field import pod
from experiments.field.kin2field import field_error_sq, fit_predict, nearest_snapshot_error_sq

E5 = Path(__file__).parents[1] / "e5_pod" / "outputs"
OUT = Path(__file__).parent / "outputs"
RANKS = (8, 16, 32, 64, 128, 256)
R_SELECT = 64
GRID = list(product((1, 2, 3, 4, 6, 8), (1, 2, 3), (1e-8, 1e-6, 1e-4, 1e-3, 1e-2, 1e-1)))


def _select(idx_tr: pd.DataFrame, z_tr: np.ndarray) -> tuple[pd.DataFrame, tuple[int, int, float]]:
    """Leave-one-config-out coefficient error for every grid point; the POD basis is kept fixed."""
    cfg = idx_tr.config.to_numpy()
    rows = []
    for h, d, a in GRID:
        sse = 0.0
        for c in np.unique(cfg):
            m = cfg == c
            sse += float(((fit_predict(idx_tr[~m], z_tr[~m], idx_tr[m], harmonics=h, degree=d, alpha=a) - z_tr[m]) ** 2).sum())
        rows.append({"harmonics": h, "degree": d, "alpha": a, "cv_rel_coef_error": float(np.sqrt(sse / (z_tr**2).sum()))})
    cv = pd.DataFrame(rows)
    best = cv.loc[cv.cv_rel_coef_error.idxmin()]
    return cv, (int(best.harmonics), int(best.degree), float(best.alpha))


def main() -> None:
    idx = pd.read_parquet(E5 / "index.parquet").reset_index(drop=True)
    scale = 1.0 / idx.u_ref.to_numpy()
    train, test = np.flatnonzero(~idx.holdout.to_numpy()), np.flatnonzero(idx.holdout.to_numpy())
    pod.assert_no_holdout(idx.iloc[train], tuple(sorted(idx.config[idx.holdout].unique())))
    grams = {
        "wing": np.load(E5 / "gram_matched_wing.npy"),
        "lab_masked": np.load(E5 / "gram_matched_lab_masked.npy"),
        "lab_patch": np.load(E5 / "gram_patch_u.npy") * scale[:, None] * scale[None, :],
    }
    idx_tr, idx_te = idx.iloc[train], idx.iloc[test]
    summary, per_snap, cvs, saved = [], [], [], {}
    for name, g in grams.items():
        g_tt, g_ht = g[np.ix_(train, train)], g[np.ix_(test, train)]
        p = pod.fit_gram(g_tt)
        z_tr, z_te = pod.encode_gram(p, g_tt), pod.encode_gram(p, g_ht)
        centred = pod.centred_sq_norm(p, g_ht, np.diag(g)[test])
        cv, (h, d, a) = _select(idx_tr, z_tr[:, :R_SELECT])
        cvs.append(cv.assign(frame=name))
        z_hat = fit_predict(idx_tr, z_tr[:, : max(RANKS)], idx_te, harmonics=h, degree=d, alpha=a)
        near, pick = nearest_snapshot_error_sq(idx, g, train, test)
        saved[f"{name}/z_pred"], saved[f"{name}/z_true"] = z_hat, z_te[:, : max(RANKS)]
        saved[f"{name}/vecs"], saved[f"{name}/sing"] = p.vecs[:, : max(RANKS)], p.sing[: max(RANKS)]
        saved[f"{name}/nearest_row"] = pick
        tot = centred.sum()
        for r in RANKS:
            pred = field_error_sq(z_te[:, :r], z_hat[:, :r], centred)
            floor = field_error_sq(z_te[:, :r], z_te[:, :r], centred)
            summary.append({"frame": name, "r": r, "harmonics": h, "degree": d, "alpha": a,
                            "prediction": float(np.sqrt(pred.sum() / tot)),
                            "reconstruction": float(np.sqrt(floor.sum() / tot)),
                            "nearest": float(np.sqrt(near.sum() / tot))})
            if r == R_SELECT:
                per_snap.append(idx_te[["config", "phase", "step"]].assign(
                    frame=name, r=r, pred_sq=pred, floor_sq=floor, nearest_sq=near, centred_sq=centred))
    pd.DataFrame(summary).to_parquet(OUT / "summary.parquet")
    pd.concat(per_snap).to_parquet(OUT / "per_snapshot.parquet")
    pd.concat(cvs).to_parquet(OUT / "cv.parquet")
    np.savez(OUT / "coefficients.npz", train=train, test=test, **saved)
    write_run_record(OUT, inputs=[E5 / "index.parquet", *(E5 / f for f in ("gram_matched_wing.npy", "gram_matched_lab_masked.npy", "gram_patch_u.npy"))],
                     experiment="e7_kin2field", ranks=list(RANKS), r_select=R_SELECT)
    s = pd.DataFrame(summary)
    print(s.to_string(index=False, float_format=lambda v: f"{v:.4g}"))
    ps = pd.concat(per_snap)
    pc = ps.groupby(["frame", "config"])[["pred_sq", "floor_sq", "nearest_sq", "centred_sq"]].sum()
    print((np.sqrt(pc[["pred_sq", "floor_sq", "nearest_sq"]].div(pc.centred_sq, axis=0))).to_string(float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
