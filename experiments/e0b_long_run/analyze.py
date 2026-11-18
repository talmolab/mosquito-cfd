"""E0b: beat-to-beat convergence from one 6-beat coarse run (centre config, local A5000).

Control: the run's first 4000 steps must reproduce the committed coarse dataset for the same config.
Coefficients come from the repo's own per-config extractor, so normalization, hinge reference and
sign are exactly the dataset's.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import CORPUS_DIR, TARGETS, load_dataset, phase_grid, waveforms
from experiments.common.record import write_run_record
from mosquito_cfd.force_surrogate.dataset import _extract_config, load_manifest_configs

HERE = Path(__file__).parent
CONFIG = "s45_f100_p45"
RUN = HERE / f"run_{CONFIG}"
OUT = HERE / "outputs"
# The two later runs that also wrote plotfiles: python -m ... --config s45_f100_p30 --suffix _fields
N_PHASE, SKIP = 256, 0.05


def rms(a) -> float:
    return float(np.sqrt(np.mean(np.square(a))))


def main() -> None:
    global CONFIG, RUN, OUT
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=CONFIG)
    ap.add_argument("--suffix", default="", help="run folder is run_<config><suffix>; outputs go to outputs_<config><suffix>")
    a = ap.parse_args()
    if (a.config, a.suffix) != (CONFIG, ""):
        CONFIG, RUN, OUT = a.config, HERE / f"run_{a.config}{a.suffix}", HERE / f"outputs_{a.config}{a.suffix}"
    OUT.mkdir(exist_ok=True)
    manifest = CORPUS_DIR["coarse"] / "sweep_manifest.json"
    config = next(c for c in load_manifest_configs(manifest) if c["name"] == CONFIG)
    frame, _ = _extract_config(config, RUN / "IB_Particle_1.csv", manifest.parent, None)
    frame.to_parquet(OUT / "long_run.parquet", index=False)

    committed = load_dataset("coarse")
    committed = committed[committed.config_name == CONFIG].sort_values("time").reset_index(drop=True)
    n = min(len(frame), len(committed))
    head, committed = frame.sort_values("time").reset_index(drop=True).iloc[:n], committed.iloc[:n]
    control = {c: float(np.max(np.abs(head[c].to_numpy() - committed[c].to_numpy())))
               for c in ("time", "Fx", "Fy", "Fz", "Mx", "My", "Mz", *TARGETS)}
    control["rows_compared"] = int(len(committed))
    control["bit_exact_raw"] = bool(all(control[c] == 0.0 for c in ("Fx", "Fy", "Fz", "Mx", "My", "Mz")))

    beats = sorted(b for b in frame.wingbeat.unique() if (frame.wingbeat == b).sum() > 1900)
    w = {b: waveforms(frame, wingbeat=int(b), n_phase=N_PHASE)[CONFIG] for b in beats}
    keep = phase_grid(N_PHASE) >= SKIP
    last = w[beats[-1]]
    peak = np.abs(last).max(axis=0)
    rows = []
    for b in beats:
        for j, t in enumerate(TARGETS):
            rows.append({
                "beat": int(b) + 1, "target": t,
                "mean": float(w[b][keep, j].mean()), "peak_abs": float(np.abs(w[b][keep, j]).max()),
                "diff_from_previous_over_peak": rms((w[b] - w[b - 1])[keep, j]) / peak[j] if b - 1 in w else np.nan,
                "diff_from_last_over_peak": rms((w[b] - last)[keep, j]) / peak[j],
                "mean_shift_from_previous_over_peak": float((w[b] - w[b - 1])[keep, j].mean()) / peak[j] if b - 1 in w else np.nan,
            })
    out = pd.DataFrame(rows)
    out.to_parquet(OUT / "beat_convergence.parquet", index=False)
    np.savez_compressed(OUT / "beat_waveforms.npz", phase=phase_grid(N_PHASE), **{f"beat{int(b) + 1}": w[b] for b in beats})
    (OUT / "control.json").write_text(json.dumps(control, indent=2))
    write_run_record(OUT, inputs=[RUN / "IB_Particle_1.csv", RUN / "inputs.3d.long"], config=CONFIG,
                     image="ghcr.io/talmolab/mosquito-cfd@sha256:07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3",
                     hardware="local RTX A5000, Docker", beats=[int(b) + 1 for b in beats])
    pd.set_option("display.width", 200)
    print(control)
    print(out.pivot(index="beat", columns="target", values="diff_from_previous_over_peak")[list(TARGETS)].round(4))
    print(out.pivot(index="beat", columns="target", values="diff_from_last_over_peak")[list(TARGETS)].round(4))


if __name__ == "__main__":
    main()
