"""Step 0 gate: does this environment reproduce the committed fine surrogate's seed 1234?

Pass = same validation configs and every target's held-out RMSE within 2% of the committed value.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from experiments.common.data import CORPUS_DIR, dataset_path, load_dataset
from experiments.common.fit import fit_predict, skill
from experiments.common.record import write_run_record
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS, filter_converged_beat, make_config_splits

OUT = Path(__file__).parent / "outputs"
TOL = 0.02


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()
    committed = json.loads((CORPUS_DIR["fine"] / "surrogate" / "metrics.json").read_text())
    run0 = committed["seed_sweep"]["runs"][0]
    assert run0["seed"] == 1234

    df = filter_converged_beat(load_dataset("fine"))
    split = make_config_splits(df, seed=1234, n_val_configs=3)
    fit = fit_predict(df, split.train_configs, split.val_configs, split.test_configs, seed=1234, device=args.device)
    got = skill(df, split.train_configs + split.val_configs, split.test_configs, fit.preds)

    rows, ok = [], split.val_configs == sorted(run0["val_configs"])
    for t in TARGET_COLUMNS:
        ref = run0["per_target"][t]
        rel = got[t]["rmse"] / ref["rmse"] - 1.0
        ok &= abs(rel) <= TOL
        rows.append({"target": t, "rmse": got[t]["rmse"], "committed_rmse": ref["rmse"], "rel_diff": rel,
                     "skill": got[t]["skill"], "committed_skill": ref["skill"]})
    result = {"pass": bool(ok), "val_configs": split.val_configs, "committed_val_configs": run0["val_configs"],
              "seconds_per_fit": fit.seconds, "device": args.device, "per_target": rows}
    OUT.mkdir(exist_ok=True)
    (OUT / "reproduction.json").write_text(json.dumps(result, indent=2))
    write_run_record(OUT, inputs=[dataset_path("fine")], seeds=[1234], device=args.device)
    print(json.dumps(result, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
