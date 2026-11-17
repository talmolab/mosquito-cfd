"""Build the local field cache from the fine corpus on Z: (resumable, provenance-checked).

    uv run python -m experiments.field.build_cache --worker 0 --n-workers 3 --min-beat 1
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

from experiments.common.data import CORPUS_DIR
from experiments.field import cache
from experiments.field.probe import CORPUS_ROOT
from experiments.field.provenance import DT, ProvenanceError, check_plotfile
from mosquito_cfd.field_surrogate.corpus import FieldCorpus

MIN_FREE_GB = 60


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker", type=int, default=0)
    ap.add_argument("--n-workers", type=int, default=1)
    ap.add_argument("--min-beat", type=int, default=1, help="skip snapshots in earlier beats")
    ap.add_argument("--max-beat", type=int, default=99)
    ap.add_argument("--root", type=Path, default=cache.CACHE_ROOT)
    args = ap.parse_args()
    args.root.mkdir(parents=True, exist_ok=True)
    # The manifest copy on Z: lists 26 configs (s55_f115_p30 is absent, a leftover of a trimmed
    # resubmission); the committed manifest lists all 27, so that one addresses the runs.
    corpus = FieldCorpus(CORPUS_ROOT, manifest=CORPUS_DIR["fine"] / "sweep_manifest.json")
    fail_path = args.root / f"failures_worker{args.worker}.json"
    failures: list[dict] = []
    configs = [c for i, c in enumerate(corpus.config_ids()) if i % args.n_workers == args.worker]
    for config in configs:
        freq = corpus.global_params(config)["frequency_fstar"]
        for step in corpus.steps(config):
            _, beat = cache.phase_and_beat(step * DT, freq)
            if not args.min_beat <= beat <= args.max_beat or cache.is_cached(args.root, config, step):
                continue
            if shutil.disk_usage(args.root).free / 2**30 < MIN_FREE_GB:
                print(f"STOP: under {MIN_FREE_GB} GB free", flush=True)
                return 2
            t0 = time.perf_counter()
            try:
                check_plotfile(corpus.plotfile(config, step), step)
                snap = corpus.snapshot(config, step)
                cache.write_atomic(args.root, config, step, cache.build_arrays(snap, freq))
                print(f"ok {config} {step} beat={beat} {time.perf_counter() - t0:.1f}s", flush=True)
            except ProvenanceError as exc:
                print(f"STOP provenance: {exc}", flush=True)
                failures.append({"config": config, "step": step, "error": f"provenance: {exc}"})
                fail_path.write_text(json.dumps(failures, indent=2))
                return 3
            except Exception as exc:  # a failed read is recorded and skipped; rerun retries it
                failures.append({"config": config, "step": step, "error": f"{type(exc).__name__}: {exc}"})
                fail_path.write_text(json.dumps(failures, indent=2))
                print(f"FAIL {config} {step}: {exc}", flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
