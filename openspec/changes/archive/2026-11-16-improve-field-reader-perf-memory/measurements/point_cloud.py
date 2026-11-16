"""Task 0.3 / 8.4: to_point_cloud() traced peak on in-memory snapshots, k = 6 fields."""

import gc
import subprocess
import tracemalloc

import numpy as np

from mosquito_cfd.field_surrogate.snapshot import DEFAULT_FIELDS, FieldSnapshot

sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
print(f"git {sha}")
for shape in ((64, 64, 64), (256, 128, 256)):
    n = int(np.prod(shape))
    rng = np.random.default_rng(0)
    arrays = {f: rng.standard_normal(shape) for f in DEFAULT_FIELDS}
    snap = FieldSnapshot(
        arrays=arrays, x=np.arange(shape[0]) + 0.5, y=np.arange(shape[1]) + 0.5,
        z=np.arange(shape[2]) + 0.5, dx=np.full(3, 1.0), time=0.0, source="mem", max_level=0,
        field_names=DEFAULT_FIELDS,
    )
    snap.to_point_cloud()  # warm-up
    gc.collect()
    tracemalloc.start()
    start = tracemalloc.get_traced_memory()[0]
    tracemalloc.reset_peak()
    pc = snap.to_point_cloud()
    peak = tracemalloc.get_traced_memory()[1] - start
    tracemalloc.stop()
    outputs = pc.coords.nbytes + pc.values.nbytes
    print(f"shape={shape} N={n} peak={peak / 1e6:.1f} MB = {peak / n:.1f} B/cell; "
          f"coords+values={outputs / 1e6:.1f} MB; peak/outputs={peak / outputs:.3f}; "
          f"cell_volume strides={pc.cell_volume.strides}")
    del pc, snap, arrays
