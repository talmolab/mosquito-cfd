"""E4 Track B ablations: inputs, model size, and a Fourier-polynomial ridge comparator (plan Task 6)."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from experiments.common.data import TARGETS, dataset_path, load_dataset
from experiments.common.features import make_feature_fn
from experiments.common.jobs import JobLog
from experiments.common.record import write_run_record
from experiments.common.ridge import fourier_poly_fit_predict, n_coefficients

OUT = Path(__file__).parent / "outputs"
SEEDS = (1234, 1235, 1236, 1237, 1238)
ARMS: dict[str, dict] = {"baseline": {}}
ARMS |= {f"drop_{k}": {"features": {"drop": (k,)}} for k in ("stroke_amp_deg", "frequency_fstar", "pitch_amp_deg")}
ARMS |= {"re_instead_of_fstar": {"features": {"use_re": True}}}
ARMS |= {f"harmonics_{h}": {"features": {"harmonics": h}} for h in (2, 3, 4)}
ARMS |= {f"width{w}_depth{d}": {"width": w, "depth": d} for w in (16, 64, 256) for d in (1, 3, 5) if (w, d) != (64, 3)}


def main(device: str) -> None:
    from experiments.common.fit import fit_predict, skill
    from mosquito_cfd.force_surrogate.train import filter_converged_beat, make_config_splits

    df = filter_converged_beat(load_dataset("fine"))
    log = JobLog(OUT / "fits.jsonl")
    for arm, spec in ARMS.items():
        for seed in SEEDS:
            job = f"{arm}_i{seed}"
            if log.has(job):
                continue
            sp = make_config_splits(df, seed=seed, n_val_configs=3)
            fit = fit_predict(df, sp.train_configs, sp.val_configs, sp.test_configs, seed=seed, device=device,
                              feature_fn=make_feature_fn(**spec.get("features", {})),
                              width=spec.get("width", 64), depth=spec.get("depth", 3))
            s = skill(df, sp.train_configs + sp.val_configs, sp.test_configs, fit.preds)
            log.add(job, [{"arm": arm, "kind": "mlp", "seed": seed, "target": t, "skill": s[t]["skill"],
                           "rmse": s[t]["rmse"], "n_params": fit.n_params, "seconds": fit.seconds} for t in TARGETS])
            print(job, round(float(np.mean([s[t]["skill"] for t in TARGETS])), 4), flush=True)
    sp = make_config_splits(df, seed=1234, n_val_configs=3)
    pool = sp.train_configs + sp.val_configs  # ridge needs no validation carve: all 21 non-holdout configs
    for h in (2, 4, 8):
        for d in (1, 2, 3):
            job = f"ridge_h{h}_d{d}"
            if log.has(job):
                continue
            preds = fourier_poly_fit_predict(df, pool, sp.test_configs, harmonics=h, degree=d)
            s = skill(df, pool, sp.test_configs, preds)
            log.add(job, [{"arm": job, "kind": "ridge", "seed": -1, "target": t, "skill": s[t]["skill"],
                           "rmse": s[t]["rmse"], "n_params": n_coefficients(h, d), "seconds": 0.0} for t in TARGETS])
            print(job, round(float(np.mean([s[t]["skill"] for t in TARGETS])), 4), flush=True)
    log.frame().to_parquet(OUT / "ablations.parquet", index=False)
    write_run_record(OUT, inputs=[dataset_path("fine")], device=device, seeds=SEEDS, arms=list(ARMS))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    main(ap.parse_args().device)
