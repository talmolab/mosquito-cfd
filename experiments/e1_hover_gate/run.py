"""E1 hover gate: Track B held-out error against three CFD-uncertainty yardsticks (plan Task 4).

    --stage train    (WSL2/GPU) seeds 1234-1238 on the committed split -> outputs/predictions.parquet
    --stage analyze  (anywhere) -> outputs/gate_table.parquet
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, dataset_path, holdout_configs, load_dataset, phase_grid, waveforms
from experiments.common.record import write_run_record

OUT = Path(__file__).parent / "outputs"
E0 = Path(__file__).parents[1] / "e0_periodicity" / "outputs" / "beat_diff.parquet"
SEEDS = (1234, 1235, 1236, 1237, 1238)
N_PHASE = 256
GCI = {"cf_normal": 0.037, "cf_chord": 0.276}  # T3c GCI_fine, examples/flapping_wing/RESULTS.md


def train(device: str) -> None:
    from experiments.common.fit import fit_predict, skill
    from mosquito_cfd.force_surrogate.train import filter_converged_beat, make_config_splits

    df = filter_converged_beat(load_dataset("fine"))
    frames, skills = [], []
    for seed in SEEDS:
        split = make_config_splits(df, seed=seed, n_val_configs=3)
        fit = fit_predict(df, split.train_configs, split.val_configs, split.test_configs, seed=seed, device=device)
        test = df.loc[fit.test_index, ["config_name", "time", "phase", "wingbeat"]].copy()
        test["seed"] = seed
        test[list(TARGETS)] = fit.preds
        frames.append(test)
        s = skill(df, split.train_configs + split.val_configs, split.test_configs, fit.preds)
        skills += [{"seed": seed, "target": t, **s[t], "val_configs": ",".join(split.val_configs)} for t in TARGETS]
        print(seed, {t: round(s[t]["skill"], 4) for t in TARGETS}, flush=True)
    OUT.mkdir(exist_ok=True)
    pd.concat(frames).to_parquet(OUT / "predictions.parquet", index=False)
    pd.DataFrame(skills).to_parquet(OUT / "seed_skill.parquet", index=False)
    write_run_record(OUT, inputs=[dataset_path("fine")], seeds=list(SEEDS), device=device, stage="train")


def rms(a) -> float:
    return float(np.sqrt(np.mean(np.square(a))))


def body_frame(w: np.ndarray, cfg_row: pd.Series) -> dict[str, np.ndarray]:
    """Rotate a (n_phase, 6) lab-frame waveform's force part into chord/normal with the repo's helper."""
    from mosquito_cfd.benchmarks.flapping_wing import body_frame_coefficients
    from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix

    f = float(cfg_row["frequency_fstar"])
    rots = np.stack([
        rotation_matrix(*euler_angles(ph / f, frequency=f, stroke_amp_rad=np.deg2rad(cfg_row["stroke_amp_deg"]),
                                      pitch_amp_rad=np.deg2rad(cfg_row["pitch_amp_deg"])))
        for ph in phase_grid(N_PHASE)
    ])
    return body_frame_coefficients(w[:, :3], rots, 1.0)


def analyze() -> None:
    fine, coarse = load_dataset("fine"), load_dataset("coarse")
    meta = fine.groupby("config_name")[["stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"]].first()
    wf, wc = waveforms(fine, n_phase=N_PHASE), waveforms(coarse, n_phase=N_PHASE)
    preds = pd.read_parquet(OUT / "predictions.parquet")
    wp = {seed: waveforms(g, n_phase=N_PHASE) for seed, g in preds.groupby("seed")}
    e0 = pd.read_parquet(E0)
    e0 = e0[e0.grid == "fine"].set_index(["config", "target"])["rms_over_peak"]
    rows = []

    def add(config, component, frame, yardstick, errs, value):
        rows.append({"config": config, "component": component, "frame": frame, "yardstick": yardstick,
                     "err_median": float(np.median(errs)), "err_min": float(np.min(errs)), "err_max": float(np.max(errs)),
                     "yardstick_value": float(value), "inside": bool(np.max(errs) <= value),
                     "inside_median": bool(np.median(errs) <= value)})

    for cfg in holdout_configs():
        for j, t in enumerate(TARGETS):
            peak = float(np.max(np.abs(wf[cfg][:, j])))
            errs = [rms(wp[s][cfg][:, j] - wf[cfg][:, j]) / peak for s in SEEDS]
            add(cfg, t, "lab", "coarse_vs_fine", errs, rms(wc[cfg][:, j] - wf[cfg][:, j]) / peak)
            add(cfg, t, "lab", "beat1_vs_beat2", errs, e0[(cfg, t)])
        bf, bc = body_frame(wf[cfg], meta.loc[cfg]), body_frame(wc[cfg], meta.loc[cfg])
        bp = {s: body_frame(wp[s][cfg], meta.loc[cfg]) for s in SEEDS}
        for comp in ("cf_normal", "cf_chord"):
            pk = float(np.max(np.abs(bf[comp])))
            errs = [abs(float(np.max(np.abs(bp[s][comp]))) - pk) / pk for s in SEEDS]
            add(cfg, comp, "body_peak", "t3c_gci", errs, GCI[comp])
            add(cfg, comp, "body_peak", "coarse_vs_fine_peak", errs, abs(float(np.max(np.abs(bc[comp]))) - pk) / pk)
    table = pd.DataFrame(rows)
    table["margin"] = table["yardstick_value"] / table["err_median"]
    table.to_parquet(OUT / "gate_table.parquet", index=False)
    np.savez_compressed(OUT / "waveforms.npz", phase=phase_grid(N_PHASE),
                        **{f"fine/{c}": wf[c] for c in holdout_configs()}, **{f"coarse/{c}": wc[c] for c in holdout_configs()},
                        **{f"pred{s}/{c}": wp[s][c] for s in SEEDS for c in holdout_configs()})
    write_run_record(OUT / "analyze", inputs=[dataset_path("fine"), dataset_path("coarse"), E0], seeds=list(SEEDS), stage="analyze")
    pd.set_option("display.width", 200)
    print(table.groupby(["frame", "component", "yardstick"])[["err_median", "yardstick_value", "margin"]].median().round(4))
    print(table.groupby(["frame", "yardstick"])[["inside", "inside_median"]].mean())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["train", "analyze"], required=True)
    ap.add_argument("--device", default="cuda")
    a = ap.parse_args()
    train(a.device) if a.stage == "train" else analyze()
