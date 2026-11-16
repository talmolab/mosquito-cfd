"""Sanity mutants proving the 3.1 anchor can fail."""

import json
import sys

F = "src/mosquito_cfd/field_surrogate/snapshot.py"
K = ["tests/test_field_surrogate_snapshot.py::test_read_is_bit_identical_to_a_full_grid_reference"]
rows = [
    ("field copy -> view",
     [['arr = np.array(raw[sl], dtype=np.float64, order="C", copy=True)', "arr = raw[sl]"]]),
    ("field order C -> F",
     [['arr = np.array(raw[sl], dtype=np.float64, order="C", copy=True)',
       'arr = np.array(raw[sl], dtype=np.float64, order="F", copy=True)']]),
    ("axes off by half a cell",
     [["(np.arange(ddims[axis]) + 0.5) * dx[axis]", "(np.arange(ddims[axis]) + 0.0) * dx[axis]"]]),
    ("arrays left writable",
     [["        arr.setflags(write=False)\n", ""]]),
]
table = [{"name": n, "file": F, "edits": e, "tests": K} for n, e in rows]
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(table, fh, indent=1)
print(len(table), "mutants")
