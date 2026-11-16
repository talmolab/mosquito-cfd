"""Write the point-cloud mutant table (task 8.1) as JSON."""

import json
import sys

F = "src/mosquito_cfd/field_surrogate/snapshot.py"
T = "tests/test_field_surrogate_snapshot.py::"
BCAST = T + "test_constant_cell_volume_is_a_read_only_broadcast"
PEAK = T + "test_point_cloud_peak_is_its_outputs"
rows = [
    ("del gx, gy, gz removed", [["        del gx, gy, gz\n", ""]], [PEAK]),
    ("cell_volume -> np.full",
     [["        cell_volume = np.broadcast_to(volume, (coords.shape[0],))\n",
       "        cell_volume = np.full(coords.shape[0], float(volume), dtype=np.float64)\n"
       "        cell_volume.setflags(write=False)\n"]], [BCAST]),
    ("cell_volume -> np.full (peak killer)",
     [["        cell_volume = np.broadcast_to(volume, (coords.shape[0],))\n",
       "        cell_volume = np.full(coords.shape[0], float(volume), dtype=np.float64)\n"
       "        cell_volume.setflags(write=False)\n"]], [PEAK]),
    ("0-d base writable", [["        volume.setflags(write=False)\n", ""]], [BCAST]),
]
table = [{"name": n, "file": F, "edits": e, "tests": t} for n, e, t in rows]
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(table, fh, indent=1)
print(len(table), "mutants")
