"""E3 data efficiency: held-out skill versus number of CFD configs used (plan Task 6).

n counts every config the model used (training + validation). Fixed 6-config holdout.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from experiments.common.data import TARGETS, dataset_path, holdout_configs, load_dataset
from experiments.common.jobs import JobLog
from experiments.common.record import write_run_record
from experiments.common.splits import carve_validation, nested_subsets

OUT = Path(__file__).parent / "outputs"
SIZES = (3, 6, 9, 12, 15, 18, 21)
SUBSET_SEEDS = (0, 1, 2, 3, 4)
INIT_SEEDS = (1234, 1235, 1236, 1237, 1238)
STRIDES = (1, 10, 40, 100)
CORNERS_CENTRE = [f"s{s}_f{f}_p{p}" for s in (35, 55) for f in ("085", "115") for p in (30, 60)] + ["s45_f100_p45"]
# The full star needs the six face centres; s45_f100_p60 is a held-out config, so it has five.
STAR = ["s45_f100_p45", "s35_f100_p45", "s55_f100_p45", "s45_f085_p45", "s45_f115_p45", "s45_f100_p30"]


def main(device: str) -> None:
    from experiments.common.fit import fit_predict, skill
    from mosquito_cfd.force_surrogate.train import filter_converged_beat

    df = filter_converged_beat(load_dataset("fine"))
    test = list(holdout_configs())
    pool = sorted(set(df.config_name) - set(test))
    assert not set(CORNERS_CENTRE + STAR) & set(test)
    assert set(CORNERS_CENTRE + STAR) <= set(pool)
    log = JobLog(OUT / "fits.jsonl")

    def run(job, design, used, train, val, init_seed, **extra):
        if log.has(job):
            return
        fit = fit_predict(df, train, val, test, seed=init_seed, device=device, row_stride=extra.get("row_stride", 1))
        s = skill(df, used, test, fit.preds)
        log.add(job, [{"design": design, "n": len(used), "init_seed": init_seed, "target": t, "skill": s[t]["skill"],
                       "rmse": s[t]["rmse"], "n_val": len(val), "seconds": fit.seconds, **extra} for t in TARGETS])
        print(job, round(sum(s[t]["skill"] for t in TARGETS) / 6, 4), flush=True)

    for ss in SUBSET_SEEDS:
        subs = nested_subsets(pool, SIZES, seed=ss)
        for n in SIZES:
            tr, va = carve_validation(subs[n], seed=ss)
            for init in INIT_SEEDS:
                run(f"random_n{n}_s{ss}_i{init}", "random", subs[n], tr, va, init, subset_seed=ss)
        for n in (6, 9):  # same random subsets, trained like the structured designs (no validation, fixed epochs)
            for init in INIT_SEEDS:
                run(f"randomfixed_n{n}_s{ss}_i{init}", "random_fixed_epochs", subs[n], subs[n], [], init, subset_seed=ss)
    for name, design in (("corners_centre", CORNERS_CENTRE), ("star", STAR)):
        for init in INIT_SEEDS:
            run(f"{name}_i{init}", name, design, design, [], init, subset_seed=-1)
    tr, va = carve_validation(pool, seed=0)
    for k in STRIDES:
        for init in INIT_SEEDS:
            run(f"thin_k{k}_i{init}", "row_thinning", pool, tr, va, init, subset_seed=0, row_stride=k)
    log.frame().to_parquet(OUT / "curve.parquet", index=False)
    write_run_record(OUT, inputs=[dataset_path("fine")], device=device, sizes=SIZES, subset_seeds=SUBSET_SEEDS,
                     init_seeds=INIT_SEEDS, corners_centre=CORNERS_CENTRE, star=STAR)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    main(ap.parse_args().device)
