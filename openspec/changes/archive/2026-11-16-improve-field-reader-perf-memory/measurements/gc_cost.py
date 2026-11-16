"""Measure how the reader's per-read cost grows with the CALLER's heap.

Usage (from the repository root)::

    PYTHONPATH=src python gc_cost.py <plotfile> <extra_million_objects> [freeze]

The process first allocates ``extra_million_objects`` million small tracked containers (one
dict holding a list each, i.e. two tracked objects per entry, standing in for a training
process's heap). With ``freeze``, ``gc.freeze()`` then moves them to the permanent generation.
It then does one warm-up read and five timed full-extent reads of three fields, and reports the
mean read time, plus the time of one bare ``gc.collect()`` in the same process.
"""

import gc
import statistics
import sys
import time

import yt

from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

path = sys.argv[1]
millions = float(sys.argv[2])
freeze = len(sys.argv) > 3 and sys.argv[3] == "freeze"
yt.set_log_level("error")
heap = [{"a": [i]} for i in range(int(millions * 1e6))]
if freeze:
    gc.freeze()
INF = float("inf")
request = {"lo": (-INF,) * 3, "hi": (INF,) * 3, "fields": ("u", "v", "w")}
read_field_snapshot(path, **request)  # warm-up
times = []
for _ in range(5):
    t0 = time.perf_counter()
    read_field_snapshot(path, **request)
    times.append(time.perf_counter() - t0)
t0 = time.perf_counter()
gc.collect()
collect = time.perf_counter() - t0
print(
    f"extra={millions:g}M dicts+lists freeze={freeze} tracked={len(gc.get_objects()) / 1e6:.2f}M "
    f"read_mean={statistics.mean(times) * 1e3:.0f}ms "
    f"read_range={min(times) * 1e3:.0f}-{max(times) * 1e3:.0f}ms "
    f"bare_collect={collect * 1e3:.0f}ms"
)
