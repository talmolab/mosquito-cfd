# Measurement and mutation scripts

These scripts produced every number in this change's proposal, design.md D4 and D6, tasks.md 0.x
and 8.x, and the CHANGELOG entry. They live with the change and are not run by CI. Run them from
the repository root with `PYTHONPATH` pointing at the source tree being measured. For "before",
export it without checking it out, for example
`git archive 90b2a72 src | tar -x -C <scratch>`.

| script | measures |
|---|---|
| `make_plotfile.py` | writes the synthetic 256×128×256 six-field plotfile, using `tests/fixtures/make_lev_boxlib_fixture.py` |
| `reader_memory.py` | `read_field_snapshot` per read: `tracemalloc` peak, memory held on return, time, and whether the yt dataset is alive; each read starts from a full collection |
| `gc_cost.py` | read time and a bare `gc.collect()` as the caller's heap grows, with and without `gc.freeze()` |
| `corpus_pass.py` | a `config_ids → steps → plotfile` pass over a synthetic 27×200 corpus (manifest loads, `os.scandir`/`os.listdir`/`os.stat` calls, wall time); optionally a timed `steps()` pass over a real corpus root |
| `point_cloud.py` | the `to_point_cloud()` peak on in-memory snapshots |
| `mutate.py` | the mutation runner: restores files from saved bytes, and needs `PYTHONDONTWRITEBYTECODE=1` |
| `mut_*.py`, `mut_dview.json` | the mutant tables (task 8.1); each `.py` writes its JSON table |

Environment for the recorded numbers: Windows 11, Python 3.11.13, yt 4.4.2, numpy 2.4.2. The
synthetic files were on local NTFS, and the real corpus was read from `Z:` over SMB.

Mutation tables match whole indented lines as substrings. After any change that re-indents the
code, regenerate a table before trusting its results (tasks.md 8.1).
