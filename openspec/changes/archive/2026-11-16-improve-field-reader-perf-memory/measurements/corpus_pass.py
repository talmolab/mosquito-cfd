"""Task 0.1 / 8.4: FieldCorpus pass cost.

Usage: PYTHONPATH=src python base_corpus.py <work_dir> [<real_corpus_root>]

Synthetic: 27 configs x 200 empty plt dirs + manifest. Pass = config_ids() -> steps() ->
plotfile() for every pair. Counts manifest loads and os.scandir / os.listdir / os.stat calls
under the root (os.stat also catches Path.is_dir / Path.stat), plus wall time.
Real: wall time of one steps() pass over every config (read-only), best of 3.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import mosquito_cfd.force_surrogate.dataset as ds_mod
from mosquito_cfd.field_surrogate.corpus import FieldCorpus

work = Path(sys.argv[1])
real = Path(sys.argv[2]) if len(sys.argv) > 2 else None
root = work / "corpus"
names = [f"c{i:02d}" for i in range(27)]
if not root.exists():
    (root / "runs").mkdir(parents=True)
    configs = [
        {"name": n, "index": i, "input_file": f"inputs/inputs.3d.{n}", "stroke_amp_deg": 35.0,
         "frequency_fstar": 0.85, "pitch_amp_deg": 30.0, "reynolds": 42.5, "split": "train"}
        for i, n in enumerate(names)
    ]
    (root / "sweep_manifest.json").write_text(json.dumps({"schema_version": 1, "configs": configs}))
    for n in names:
        for s in range(200):
            (root / "runs" / n / f"plt{(s + 1) * 5:05d}").mkdir(parents=True)

rootstr = os.fspath(root)
counts = {"manifest": 0, "scandir": 0, "listdir": 0, "stat": 0}


def under(arg):
    if isinstance(arg, int):
        return False
    a = os.fsdecode(os.fspath(arg)) if arg is not None else os.getcwd()
    return os.path.abspath(a).startswith(os.path.abspath(rootstr))


def wrap(name):
    real_fn = getattr(os, name)

    def spy(*a, **k):
        if under(a[0] if a else k.get("path")):
            counts[name] += 1
        return real_fn(*a, **k)

    setattr(os, name, spy)


real_load = ds_mod.load_manifest_configs


def load_spy(*a, **k):
    counts["manifest"] += 1
    return real_load(*a, **k)


corpus = FieldCorpus(root)
ds_mod.load_manifest_configs = load_spy
for n in ("scandir", "listdir", "stat"):
    wrap(n)
t0 = time.perf_counter()
pairs = 0
for c in corpus.config_ids():
    for s in corpus.steps(c):
        corpus.plotfile(c, s)
        pairs += 1
dt = time.perf_counter() - t0
print(f"python {sys.version.split()[0]} git {subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()}")
print(f"synthetic pass: pairs={pairs} manifest_loads={counts['manifest']} scandir={counts['scandir']} "
      f"listdir={counts['listdir']} stat={counts['stat']} wall_s={dt:.3f}")

if real is not None:
    rc = FieldCorpus(real)
    best = []
    for _ in range(3):
        t0 = time.perf_counter()
        n = sum(len(rc.steps(c)) for c in rc.config_ids())
        best.append(time.perf_counter() - t0)
    print(f"real steps() pass: configs={len(rc.config_ids())} steps={n} wall_s={[round(b, 3) for b in best]}")
