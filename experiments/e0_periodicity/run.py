"""E0: how different are the two beats of each run? (plan Task 3)"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from experiments.common.data import TARGETS, dataset_path, load_dataset, phase_grid, waveforms
from experiments.common.record import write_run_record

OUT = Path(__file__).parent / "outputs"
N_PHASE = 256
START_SKIP = 0.05  # phase; the impulsive-start spike in beat 1 has decayed by about phase 0.03


def rms(a: np.ndarray) -> float:
    return float(np.sqrt(np.mean(a**2)))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    grid = phase_grid(N_PHASE)
    keep = grid >= START_SKIP
    first, second = keep & (grid < 0.5), grid >= 0.5
    rows, profiles = [], {}
    for g in ("coarse", "fine"):
        df = load_dataset(g)
        dup = int(df.duplicated(["config_name", "time"]).sum())
        w0, w1 = waveforms(df, wingbeat=0, n_phase=N_PHASE), waveforms(df, wingbeat=1, n_phase=N_PHASE)
        meta = df.groupby("config_name")[["stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"]].first()
        for cfg in sorted(w1):
            d = w1[cfg] - w0[cfg]
            profiles[f"{g}/{cfg}"] = d
            for j, t in enumerate(TARGETS):
                peak = float(np.max(np.abs(w1[cfg][:, j])))
                rows.append({
                    "grid": g, "config": cfg, "target": t, **meta.loc[cfg].to_dict(),
                    "nrms": rms(d[keep, j]) / rms(w1[cfg][:, j]),
                    "rms_over_peak": rms(d[keep, j]) / peak,
                    "rms_over_peak_first_half": rms(d[first, j]) / peak,
                    "rms_over_peak_second_half": rms(d[second, j]) / peak,
                    "mean_shift_over_peak": float(np.mean(d[keep, j])) / peak,
                    "duplicate_time_rows_in_grid": dup,
                })
    out = pd.DataFrame(rows)
    assert len(out) == 2 * 27 * 6 and not out.isna().any().any()
    out.to_parquet(OUT / "beat_diff.parquet", index=False)
    np.savez_compressed(OUT / "beat_diff_profiles.npz", phase=grid, **profiles)
    write_run_record(OUT, inputs=[dataset_path("coarse"), dataset_path("fine")], n_phase=N_PHASE, start_skip=START_SKIP)
    print(out.groupby(["grid", "target"])[["rms_over_peak", "rms_over_peak_first_half", "rms_over_peak_second_half"]].median().round(4))
    print("duplicate (config, time) rows:", out.groupby("grid").duplicate_time_rows_in_grid.first().to_dict())


if __name__ == "__main__":
    main()
