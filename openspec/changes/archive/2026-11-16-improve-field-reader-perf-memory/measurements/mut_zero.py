"""Write the zero-cell + updated teardown mutant table (task 8.1, snapshot rows) as JSON."""

import json
import sys

F = "src/mosquito_cfd/field_surrogate/snapshot.py"
T = "tests/test_field_surrogate_snapshot.py::"
READS = T + "test_zero_cell_region_reads_nothing"
MEM = T + "test_zero_cell_read_costs_no_field_sized_memory"
GUARDS = T + "test_guards_fire_before_the_zero_cell_short_circuit"
DEAD0 = T + "test_dataset_is_dead_after_a_zero_cell_read"
DEAD = T + "test_dataset_is_dead_when_the_read_returns"
BIT = T + "test_read_is_bit_identical_to_a_full_grid_reference"
LOAD = "    ds = yt.load(str(plotfile_path))\n"
EARLY = (
    LOAD
    + "    _z = bool(np.any(np.equal(*_region_bounds(lo_v, hi_v, halo,"
    " dle=np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64),"
    " dre=np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64),"
    " ddims=np.asarray(ds.domain_dimensions, dtype=np.int64)))))\n"
)
GUARD_LINES = {
    "AMR guard": "    if ds.index.max_level != 0:\n",
    "_dtype attribute guard": '    if not hasattr(ds.index, "_dtype"):\n',
    "fp32 guard": '    if on_disk.kind != "f" or on_disk.itemsize != 8:\n',
    "missing-field guard": "    if missing:\n",
}
rows = [
    ("short-circuit removed", [["    if np.any(i_hi == i_lo):\n", "    if False:\n"]], [READS]),
    ("short-circuit removed (memory killer)",
     [["    if np.any(i_hi == i_lo):\n", "    if False:\n"]], [MEM]),
    ("condition any -> all",
     [["    if np.any(i_hi == i_lo):\n", "    if np.all(i_hi == i_lo):\n"]], [READS]),
]
for label, line in GUARD_LINES.items():
    rows.append((f"short-circuit before the {label}",
                 [[LOAD, EARLY], [line, line.replace(":\n", " and not _z:\n")]], [GUARDS]))
rows += [
    ("zero-cell path returns before teardown",
     [["    gc.collect()\n", "    if not np.any(i_hi == i_lo):\n        gc.collect()\n"]], [DEAD0]),
    ("zero-cell arrays writable", [["            empty.setflags(write=False)\n", ""]], [BIT]),
    ("zero-cell arrays a view",
     [["            empty = np.empty(shape, dtype=np.float64)\n",
       "            empty = np.empty(tuple(s + 1 for s in shape), dtype=np.float64)"
       "[tuple(slice(0, s) for s in shape)]\n"]], [BIT]),
    ("gc.collect() before del ds",
     [["    del ds\n    gc.collect()\n", "    gc.collect()\n    del ds\n"]], [DEAD]),
    ("del ds omitted", [["    del ds\n    gc.collect()\n", "    gc.collect()\n"]], [DEAD]),
    ("del cg omitted", [["        del cg\n", ""]], [DEAD]),
]
table = [{"name": n, "file": F, "edits": e, "tests": t} for n, e, t in rows]
with open(sys.argv[1], "w", encoding="utf-8", newline="\n") as fh:
    json.dump(table, fh, indent=1)
print(len(table), "mutants")
