"""One-off probes before bulk caching: read timing, patch coverage of the vorticity, marker check."""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

import numpy as np

from experiments.field import cache
from experiments.field.provenance import check_plotfile
from mosquito_cfd.field_surrogate.corpus import FieldCorpus

CORPUS_ROOT = Path("Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine")
OUT = Path(__file__).parent / "outputs"
PROBES = [("s55_f115_p60", 2600), ("s35_f085_p30", 3500), ("s45_f100_p45", 3000)]


def enstrophy(u, v, w, dx):
    g = lambda a, ax: np.gradient(a, dx, axis=ax)  # noqa: E731
    wx, wy, wz = g(w, 1) - g(v, 2), g(u, 2) - g(w, 0), g(v, 0) - g(u, 1)
    return wx**2 + wy**2 + wz**2


def main() -> None:
    corpus = FieldCorpus(CORPUS_ROOT)
    out = {"reads": [], "stale_dirs_listed": 0}
    for config, step in PROBES:
        plt = corpus.plotfile(config, step)
        check_plotfile(plt, step)
        out["stale_dirs_listed"] += sum(".old" in str(corpus.plotfile(config, s)) for s in corpus.steps(config))
        tracemalloc.start()
        t0 = time.perf_counter()
        snap = corpus.snapshot(config, step)
        secs = time.perf_counter() - t0
        peak = tracemalloc.get_traced_memory()[1] / 2**20
        tracemalloc.stop()
        freq = corpus.global_params(config)["frequency_fstar"]
        arrays = cache.build_arrays(snap, freq)
        ens = enstrophy(snap.arrays["u"], snap.arrays["v"], snap.arrays["w"], float(snap.dx[0]))
        frac = {}
        for zlo in (2.5, 2.0, 1.5, 1.0, 0.5):
            sx, sy, sz = (cache.axis_slice(c, a, b) for c, a, b in
                          zip((snap.x, snap.y, snap.z), (1.0, 0.0, zlo), cache.PATCH_HI))
            frac[str(zlo)] = float(ens[sx, sy, sz].sum() / ens.sum())
        out["reads"].append({"config": config, "step": step, "seconds": secs, "peak_mib": peak,
                             "n_steps_listed": len(corpus.steps(config)), "phase": float(arrays["phase"]),
                             "wingbeat": int(arrays["wingbeat"]), "patch_shape": arrays["patch_u"].shape,
                             "enstrophy_fraction_by_zlo": frac, "u_min": float(snap.arrays["u"].min()),
                             "u_max": float(snap.arrays["u"].max())})
        print(out["reads"][-1], flush=True)
    OUT.mkdir(exist_ok=True)
    (OUT / "probe.json").write_text(json.dumps(out, indent=2, default=list))


if __name__ == "__main__":
    main()
