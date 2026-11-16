"""Measure ``read_field_snapshot`` memory and time per read, with automatic GC enabled.

Usage (from the repository root; point PYTHONPATH at the source tree being measured)::

    PYTHONPATH=src python reader_memory.py <plotfile> [full|zero] [reads]

Method: one warm-up read, then ``reads`` traced reads (default 3) in one process. Before each
traced read a full ``gc.collect()`` runs, so every read starts from the same clean baseline and
an earlier read's uncollected garbage cannot be freed mid-read and offset the peak. Per read it
reports:

- ``peak_MB``: ``tracemalloc`` peak above the read's starting level;
- ``held_MB``: memory still traced right after the call returns, minus the returned arrays,
  measured BEFORE any collection -- what the read leaves behind for Python's collector;
- ``t_s``: wall time of the call;
- ``ds_alive``: whether a weak reference to the real yt ``Dataset`` is alive on return.

``zero`` requests a region far below the domain (zero cells on every axis).
"""

import gc
import subprocess
import sys
import time
import tracemalloc
import weakref

import yt

from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

path = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "full"
reads = int(sys.argv[3]) if len(sys.argv) > 3 else 3
yt.set_log_level("error")
refs = []
real_load = yt.load


def load_spy(*args, **kwargs):
    ds = real_load(*args, **kwargs)
    refs.append(weakref.ref(ds))
    return ds


yt.load = load_spy
INF = float("inf")
if mode == "full":
    request = {"lo": (-INF,) * 3, "hi": (INF,) * 3}
else:
    request = {"lo": (-1e9,) * 3, "hi": (-1e9 + 1,) * 3}

del_snap = read_field_snapshot(path, **request)  # warm-up
del del_snap
rows = []
for _ in range(reads):
    gc.collect()
    tracemalloc.start()
    start = tracemalloc.get_traced_memory()[0]
    t0 = time.perf_counter()
    snap = read_field_snapshot(path, **request)
    elapsed = time.perf_counter() - t0
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    payload = sum(a.nbytes for a in snap.arrays.values())
    payload += sum(a.nbytes for a in (snap.x, snap.y, snap.z))
    alive = refs[-1]() is not None
    del snap
    rows.append((peak - start, current - start - payload, elapsed, alive))

sha = subprocess.run(
    ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True
).stdout.strip()
print(f"cwd git {sha}  python {sys.version.split()[0]}  yt {yt.__version__}  mode={mode}")
print(f"file {path}")
print("read  peak_MB  held_MB    t_s  ds_alive")
for i, (peak, held, elapsed, alive) in enumerate(rows, 1):
    print(f"{i:4d} {peak / 1e6:8.0f} {held / 1e6:8.0f} {elapsed:6.2f}  {alive}")
