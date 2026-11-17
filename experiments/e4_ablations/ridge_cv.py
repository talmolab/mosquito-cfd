"""Ridge comparator, chosen honestly: pick (harmonics, degree, alpha) by leave-one-config-out
cross-validation inside the 21 non-holdout configs, then score that single choice on the holdout.

Also scores the chosen ridge on E3's nested random subsets, for a like-for-like data-efficiency curve.
CPU only, deterministic.
"""

from __future__ import annotations

from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, dataset_path, holdout_configs, load_dataset
from experiments.common.fit import skill
from experiments.common.record import write_run_record
from experiments.common.ridge import fourier_poly_fit_predict, n_coefficients
from experiments.common.splits import nested_subsets
from experiments.e3_data_efficiency.run import CORNERS_CENTRE, SIZES, STAR, SUBSET_SEEDS
from mosquito_cfd.force_surrogate.train import filter_converged_beat

OUT = Path(__file__).parent / "outputs"
GRID = list(product((2, 4, 6, 8, 12, 16), (1, 2, 3), (1e-8, 1e-6, 1e-4)))
STRIDE = 4  # rows per beat thinned 4x for the CV search only (E3 shows thinning does not matter)


def mean_skill(df, base, test, preds) -> float:
    s = skill(df, base, test, preds)
    return float(np.mean([s[t]["skill"] for t in TARGETS]))


def main() -> None:
    df = filter_converged_beat(load_dataset("fine"))
    test = list(holdout_configs())
    pool = sorted(set(df.config_name) - set(test))
    thin = df[df.groupby("config_name").cumcount() % STRIDE == 0]

    rows = []
    for h, d, alpha in GRID:
        sse = np.zeros(6)
        sst = np.zeros(6)
        for left in pool:
            rest = [c for c in pool if c != left]
            pred = fourier_poly_fit_predict(thin, rest, [left], harmonics=h, degree=d, alpha=alpha)
            y = thin[thin.config_name == left][list(TARGETS)].to_numpy(dtype=float)
            sse += ((pred - y) ** 2).sum(axis=0)
            sst += ((y - y.mean(axis=0)) ** 2).sum(axis=0)
        rows.append({"harmonics": h, "degree": d, "alpha": alpha, "cv_nmse": float(np.mean(sse / sst)),
                     "n_params": n_coefficients(h, d)})
    cv = pd.DataFrame(rows).sort_values("cv_nmse").reset_index(drop=True)
    best = cv.iloc[0]
    h, d, alpha = int(best.harmonics), int(best.degree), float(best.alpha)

    pred = fourier_poly_fit_predict(df, pool, test, harmonics=h, degree=d, alpha=alpha)
    s = skill(df, pool, test, pred)
    chosen = pd.DataFrame([{"target": t, "skill": s[t]["skill"], "rmse": s[t]["rmse"], "harmonics": h, "degree": d,
                            "alpha": alpha, "n_params": n_coefficients(h, d)} for t in TARGETS])
    test_df = df[df.config_name.isin(test)][["config_name", "phase"]].copy()
    test_df[list(TARGETS)] = pred
    test_df.to_parquet(OUT / "ridge_chosen_predictions.parquet", index=False)

    curve = []
    for ss in SUBSET_SEEDS:
        subs = nested_subsets(pool, SIZES, seed=ss)
        for n in SIZES:
            p = fourier_poly_fit_predict(df, subs[n], test, harmonics=h, degree=d, alpha=alpha)
            curve.append({"design": "random", "n": n, "subset_seed": ss, "skill": mean_skill(df, subs[n], test, p)})
    for name, design in (("corners_centre", CORNERS_CENTRE), ("star", STAR)):
        p = fourier_poly_fit_predict(df, design, test, harmonics=h, degree=d, alpha=alpha)
        curve.append({"design": name, "n": len(design), "subset_seed": -1, "skill": mean_skill(df, design, test, p)})

    cv.to_parquet(OUT / "ridge_cv.parquet", index=False)
    chosen.to_parquet(OUT / "ridge_chosen.parquet", index=False)
    pd.DataFrame(curve).to_parquet(OUT / "ridge_curve.parquet", index=False)
    write_run_record(OUT / "ridge_cv", inputs=[dataset_path("fine")], grid=GRID, cv_stride=STRIDE,
                     chosen={"harmonics": h, "degree": d, "alpha": alpha})
    pd.set_option("display.width", 200)
    print(cv.head(8).round(6))
    print(chosen.round(4))
    print(pd.DataFrame(curve).groupby(["design", "n"]).skill.agg(["median", "min", "max"]).round(4))


if __name__ == "__main__":
    main()
