"""E5 variant: the same POD in a wing-fixed frame, to separate "the body moves through the grid"
from the flow's own complexity.

Works on the patch block-averaged 4x (cell size 0.125), so it is indicative, not a full-resolution
result. The lab-frame comparator is the same 4x patch. The wing-fixed box is 2 chords x 3.2 x 2 in
(chord, span, normal), which stays inside the patch for every pose in the sweep (span wraps
periodically in y).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from experiments.field import cache, pod
from experiments.field.wingframe import wing_frame_sample
from mosquito_cfd.benchmarks.wing_kinematics import euler_angles, rotation_matrix

OUT = Path(__file__).parent / "outputs"
E6 = Path(__file__).parents[1] / "e6_mesh_reduced" / "outputs"
HINGE = np.array([4.0, 0.5, 4.0])
DOWN, DX = 4, 0.03125
RANKS = (1, 2, 4, 8, 16, 32, 64, 128, 256)


def main() -> None:
    idx = pd.read_parquet(OUT / "index.parquet")
    lab = np.load(E6 / f"patch_ds{DOWN}.npy") / idx.u_ref.to_numpy()[:, None, None, None, None]
    spacing = DX * DOWN
    origin = [lo + spacing / 2 for lo in cache.PATCH_LO]
    ax = [np.arange(-1.0 + spacing / 2, 1.0, spacing), np.arange(spacing / 2, 3.2, spacing), np.arange(-1.0 + spacing / 2, 1.0, spacing)]
    xi = np.stack(np.meshgrid(*ax, indexing="ij"), axis=-1).reshape(-1, 3)
    wing = np.empty((len(idx), len(xi), 3), dtype=np.float32)
    for i, row in idx.iterrows():
        r = rotation_matrix(*euler_angles(row.time, frequency=row.frequency_fstar,
                                          stroke_amp_rad=np.deg2rad(row.stroke_amp_deg),
                                          pitch_amp_rad=np.deg2rad(row.pitch_amp_deg)))
        wing[i] = wing_frame_sample(lab[i], origin, spacing, r, HINGE, xi, periodic_len=(None, 4.0, None))
    train = np.flatnonzero(~idx.holdout.to_numpy())
    test = np.flatnonzero(idx.holdout.to_numpy())
    rows = []
    energies = {}
    for name, x in (("lab frame, patch 4x", lab.reshape(len(idx), -1)), ("wing frame, box 4x", wing.reshape(len(idx), -1))):
        p = pod.fit(x[train])
        e = pod.energy_fraction(p)
        energies[name] = e
        for r in RANKS:
            rows.append({"frame": name, "r": r, "n_dof": x.shape[1], "train_error": pod.recon_error(p, x[train], r),
                         "heldout_error": pod.recon_error(p, x[test], r),
                         "modes_90": int(np.searchsorted(e, 0.9) + 1), "modes_99": int(np.searchsorted(e, 0.99) + 1)})
    out = pd.DataFrame(rows)
    out.to_parquet(OUT / "wingframe.parquet", index=False)
    np.savez_compressed(OUT / "wingframe_energy.npz", **{k.replace(",", "").replace(" ", "_"): v for k, v in energies.items()})
    pd.set_option("display.width", 200)
    print(out.pivot(index="r", columns="frame", values="heldout_error").round(3))
    print(out.groupby("frame")[["modes_90", "modes_99", "n_dof"]].first())


if __name__ == "__main__":
    main()
