"""E2 residual map: leave-one-config-out residuals for all 27 configs (plan Task 5).

    --stage train    (WSL2/GPU) 27 configs x 5 seeds, resumable -> outputs/fits/<config>_<seed>.npy
    --stage analyze  -> outputs/loco_residuals.npz + outputs/loco_summary.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, dataset_path, load_dataset, phase_grid, waveforms
from experiments.common.record import write_run_record
from experiments.common.splits import carve_validation
from experiments.common.stats import position_class, reversal_share

OUT = Path(__file__).parent / "outputs"
FITS = OUT / "fits"
SEEDS = (1234, 1235, 1236, 1237, 1238)
N_PHASE = 256


def train(device: str) -> None:
    from experiments.common.fit import fit_predict
    from mosquito_cfd.force_surrogate.train import filter_converged_beat

    df = filter_converged_beat(load_dataset("fine"))
    configs = sorted(df.config_name.unique())
    FITS.mkdir(parents=True, exist_ok=True)
    failures = []
    for cfg in configs:
        pool = [c for c in configs if c != cfg]
        for seed in SEEDS:
            path = FITS / f"{cfg}_{seed}.npy"
            if path.exists():
                continue
            try:
                tr, va = carve_validation(pool, seed=seed)
                fit = fit_predict(df, tr, va, [cfg], seed=seed, device=device)
                test = df.loc[fit.test_index, ["config_name", "phase", "wingbeat"]].copy()
                test[list(TARGETS)] = fit.preds
                np.save(path, waveforms(test, n_phase=N_PHASE)[cfg])
                print(f"ok {cfg} {seed} {fit.seconds:.0f}s", flush=True)
            except Exception as exc:
                failures.append({"config": cfg, "seed": seed, "error": f"{type(exc).__name__}: {exc}"})
                print(f"FAIL {cfg} {seed}: {exc}", flush=True)
    (OUT / "failures.json").write_text(json.dumps(failures, indent=2))
    write_run_record(OUT, inputs=[dataset_path("fine")], seeds=list(SEEDS), device=device, stage="train",
                     design="leave-one-config-out; validation = carve_validation(other 26, seed), 4 configs")


def analyze() -> None:
    fine, coarse = load_dataset("fine"), load_dataset("coarse")
    wf, wc = waveforms(fine, n_phase=N_PHASE), waveforms(coarse, n_phase=N_PHASE)
    w0 = waveforms(fine, wingbeat=0, n_phase=N_PHASE)
    meta = fine.groupby("config_name")[["stroke_amp_deg", "frequency_fstar", "pitch_amp_deg", "split"]].first()
    configs, ph = sorted(wf), phase_grid(N_PHASE)
    pred = np.stack([[np.load(FITS / f"{c}_{s}.npy") for s in SEEDS] for c in configs])  # (27, 5, 256, 6)
    cfd = np.stack([wf[c] for c in configs])  # (27, 256, 6)
    peak = np.abs(cfd).max(axis=1)  # (27, 6)
    resid = pred - cfd[:, None]
    np.savez_compressed(OUT / "loco_residuals.npz", phase=ph, configs=np.array(configs), seeds=np.array(SEEDS),
                        pred=pred, cfd=cfd, peak=peak, coarse=np.stack([wc[c] for c in configs]),
                        beat0=np.stack([w0[c] for c in configs]))
    rows = []
    for i, c in enumerate(configs):
        m = meta.loc[c]
        for j, t in enumerate(TARGETS):
            mean_sq = (resid[i, :, :, j] ** 2).mean(axis=0)  # seed-mean squared residual by phase
            rows.append({
                "config": c, "target": t, "stroke_amp_deg": m.stroke_amp_deg, "frequency_fstar": m.frequency_fstar,
                "pitch_amp_deg": m.pitch_amp_deg, "committed_split": m.split,
                "position": position_class(m.stroke_amp_deg, m.frequency_fstar, m.pitch_amp_deg),
                "err_over_peak": float(np.sqrt(mean_sq.mean()) / peak[i, j]),
                "err_over_peak_min_seed": float(np.sqrt((resid[i, :, :, j] ** 2).mean(axis=1)).min() / peak[i, j]),
                "err_over_peak_max_seed": float(np.sqrt((resid[i, :, :, j] ** 2).mean(axis=1)).max() / peak[i, j]),
                "bias_over_peak": float(resid[i, :, :, j].mean() / peak[i, j]),
                "seed_spread_over_peak": float(pred[i, :, :, j].std(axis=0).mean() / peak[i, j]),
                "reversal_share_resid": reversal_share(mean_sq, ph),
                "reversal_share_coarse_fine": reversal_share((wc[c][:, j] - wf[c][:, j]) ** 2, ph),
                "reversal_share_seed_var": reversal_share(pred[i, :, :, j].var(axis=0), ph),
                "reversal_share_cfd_sq": reversal_share(cfd[i, :, j] ** 2, ph),
            })
    out = pd.DataFrame(rows)
    out.to_parquet(OUT / "loco_summary.parquet", index=False)
    write_run_record(OUT / "analyze", inputs=[dataset_path("fine"), dataset_path("coarse")], stage="analyze")
    pd.set_option("display.width", 220)
    print(out.groupby("target")[["err_over_peak", "reversal_share_resid", "reversal_share_coarse_fine", "reversal_share_cfd_sq"]].median().round(3))
    print(out.groupby("position")["err_over_peak"].agg(["median", "max", "count"]).round(4))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["train", "analyze"], required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    train(a.device) if a.stage == "train" else analyze()
