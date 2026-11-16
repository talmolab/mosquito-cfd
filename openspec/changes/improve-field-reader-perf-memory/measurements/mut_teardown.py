"""Write the teardown mutant table (task 8.1, section 3 rows) as JSON, for the post-4.4 layout.

The full-read loop sits inside the `else:` of the zero-cell branch, so its body is indented 12
spaces and `cg.clear_data()` 8. The del/gc rows live in mut_zero.py.
"""

import json
import sys

F = "src/mosquito_cfd/field_surrogate/snapshot.py"
T = "tests/test_field_surrogate_snapshot.py::"
CACHE = T + "test_each_field_leaves_the_covering_grid_cache_once_copied"
PEAK = T + "test_field_cache_release_bounds_the_peak"
DEAD = T + "test_dataset_is_dead_when_the_read_returns"
BIT = T + "test_read_is_bit_identical_to_a_full_grid_reference"
POP = "            cg.field_data.pop(field, None)\n"
CLEAR = "        cg.clear_data()\n"
AFTER = "        for f in requested:\n            cg.field_data.pop(f, None)\n" + CLEAR
rows = [
    ("pop removed", [[POP, ""]], [CACHE]),
    ("pop removed (peak killer)", [[POP, ""]], [PEAK]),
    ("pop keyed by short name", [[POP, "            cg.field_data.pop(name, None)\n"]], [CACHE]),
    ("pop keyed by short name (peak killer)",
     [[POP, "            cg.field_data.pop(name, None)\n"]], [PEAK]),
    ("pop moved after the loop", [[POP, ""], [CLEAR, AFTER]], [CACHE]),
    ("pop moved after the loop (peak killer)", [[POP, ""], [CLEAR, AFTER]], [PEAK]),
    ("clear_data() removed", [[CLEAR, ""]], [CACHE]),
    ("gc.collect() removed", [["    gc.collect()\n", ""]], [DEAD]),
    ("gc.collect() -> gc.collect(0)", [["    gc.collect()\n", "    gc.collect(0)\n"]], [DEAD]),
    ("gc.collect() -> gc.collect(1)", [["    gc.collect()\n", "    gc.collect(1)\n"]], [DEAD]),
    ("time read after del ds",
     [["    time = float(ds.current_time)\n", ""],
      ["    gc.collect()\n", "    gc.collect()\n    time = float(ds.current_time)\n"]], [BIT]),
    ("del raw removed (expected survivor)", [["            del raw\n", ""]], [CACHE, PEAK, DEAD]),
]
table = [{"name": n, "file": F, "edits": e, "tests": t} for n, e, t in rows]
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(table, fh, indent=1)
print(len(table), "mutants")
