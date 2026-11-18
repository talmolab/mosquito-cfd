# harden-field-reader-pre-f3

## Why

F3 will load F2 field snapshots in multi-worker `DataLoader`s. Before it does:
- `FieldSnapshot` cannot be pickled (#151);
- `flow_video` silently drops frames from step 100000 on (#144);
- the reader fails unhelpfully or silently, and drops the run's digest-pinned provenance (#113).

## Context

### Where each #113 item stands on `main` (`80d653a`): measured against `tests/fixtures/lev_boxlib_plt`

| #113 item | On `80d653a` | This change |
|---|---|---|
| Regular file / empty dir passed as plotfile | `YTUnidentifiedDataType` dump | `NotADirectoryError` / `FileNotFoundError` before `import yt` (D2) |
| Garbage `Header` | yt's `ValueError: invalid literal for int()` | **Out of scope** (D2) |
| Inverted corners | **Already fixed** by #140 | none |
| Zero-cell → DoMINO dict | `(0,3)`, `(0,6)`, `(0,0,0,3)`, `(3,1)`, no error | refused at `FieldCorpus.snapshot` and `to_domino_volume` (D5) |
| `to_domino_volume` mutability | **Already fixed:** all five keys `writeable=False` | none (already specified) |
| `source` not normalized | `'tests\\fixtures\\lev_boxlib_plt'` | `Path(...).absolute().as_posix()` (D3) |
| `(config_id, step)` dropped | dropped | carried on the snapshot (D4) |
| `run_metadata.json` digest | dropped | `FieldCorpus.run_metadata()` + `git_commit`/`docker_image` on the snapshot (D4) |
| `fields="gradpx"` | `unknown field name(s) ['g','r','a','d','p','x']` | `ValueError` suggesting `("gradpx",)` (D6) |
| 2-D / empty global params | folded to `(6,1)` / accepted as `(0,1)` | `ValueError` (D6) |
| NaN/inf global params; step aliasing; `plotfile()` message; non-int `step` | **Already fixed** by #140 | none |
| `yt.set_log_level` global side effect | commented, but not marked as inherited | comment marks it inherited (D6) |
| AMR refusal names `read_field_snapshot` via `extract_eulerian_box` | still | caller-neutral message, still naming CC-F3 (D6) |

The measured facts the design rests on are in design.md, in one place each:
- pickle: D1;
- the Z: corpus provenance: D4;
- `resolve()` on Z:: D3.

## What Changes

- **#151.** `FieldSnapshot` round-trips through every pickle protocol, `ForkingPickler`, a spawned
  worker process, `copy.copy` and `copy.deepcopy`. On receipt its arrays are re-frozen and owning
  (D1).
- **#113: path pre-check.** `read_field_snapshot` refuses a non-plotfile path with a builtin
  `FileNotFoundError` / `NotADirectoryError` before `import yt` (D2).
- **#113: provenance.**
  - `source` becomes absolute and POSIX-spelled.
  - `FieldSnapshot` gains `config_id`, `step`, `git_commit`, `docker_image` and `run_id`, each
    defaulting to `None`. `run_id` was added after the pre-PR review (D8.2).
  - New `FieldCorpus.run_metadata(config_id)`.
  - `FieldCorpus.snapshot` fills the five fields from the run's own `run_metadata.json`, strictly
    validated, before any yt work (D3, D4).
  - A new dependency-free module `field_surrogate/_provenance.py` holds the strict checks (D4).
- **#113: zero-cell refusal** in `FieldCorpus.snapshot` and `to_domino_volume` (D5).
- **#113: argument checks first.** `FieldCorpus.snapshot` validates its region arguments before any
  I/O (D4).
- **#113: smaller items** (D6).
  - Bare-string `fields` is rejected.
  - Global params must be 1-D and non-empty.
  - The AMR message no longer names a function.
  - The `yt.set_log_level` comment is marked as inherited.
- **#144.** `corpus._scan` becomes the public `corpus.scan_plotfiles`. `flow_video` discovers frames
  with it (D7).
- **Docs.**
  - Docstrings: `snapshot.py`, `corpus.py`, `domino_adapter.py` and `flow_video.py`.
  - The `scripts/make_flow_video.py` `--plotfile-dir` help text.
  - `openspec/project.md`'s "Field Surrogate Reader (Stage 2)" section.
  - `docs/CHANGELOG.md`.
  - `docs/field_surrogate/roadmap.md`'s F3 dependency line (tasks §9).

### BREAKING

Each item is also marked in `docs/CHANGELOG.md`.

- **`FieldCorpus.snapshot` requires valid run provenance.** A run directory without a valid
  `run_metadata.json` now raises `ValueError` where it used to return a snapshot. Valid means:
  - a 40-hex commit;
  - an `<image>@sha256:<64 hex>` reference;
  - a `config` equal to the run;
  - `status == "completed"`, a non-empty `run_id`, and no `git.dirty: true` (added after the pre-PR
    review, design D8.2).

  All 27 real fine-corpus runs pass (D4). `read_field_snapshot` is unaffected.
- **`FieldCorpus.snapshot` and `to_domino_volume` refuse zero-cell snapshots.**
- **`FieldSnapshot.source` changes spelling** from `str(path)` to `Path(path).absolute().as_posix()`.
  The type is still `str`.
- **`fields` given as a bare `str`/`bytes` is rejected.** `fields="uvw"` used to work by accident.
- **`to_domino_volume` rejects 2-D, 0-d or empty global parameters.**
- **`flow_video` frame discovery changes:**
  - it renders frames from step 100000 on (the fix);
  - it skips non-directory `plt*` entries;
  - it raises on two directories for one step, where it used to render both;
  - a nonexistent `plotfile_dir` still raises `ValueError`.
- **Pickling or copying a `FieldSnapshot` with a non-FP64 array raises `ValueError`** (D8.3). Only
  hand-built snapshots can have one; the reader never produces one.
- **`FieldSnapshot` gains five trailing defaulted fields** (`run_id` added in D8.2). This is additive
  for construction.
  `repr` shows them. `==` was already unusable between two distinct snapshots: the dataclass `eq`
  compares numpy arrays and can raise (any array with more than one element, or with none). This
  change does not alter that.

### Impact on parallel work (grepped, read-only)

`explore-surrogate-experiments` at `414c552`:
- `experiments/field/build_cache.py:50` and `experiments/field/probe.py:36` call
  `corpus.snapshot(config, step)` over the full domain.
  - They read `.arrays`, `.x/.y/.z`, `.dx` and `.time`, and never write.
  - They use the committed 27-config manifest against the Z: runs, which all carry valid metadata.
  - **They do not break.**
  - Note: `build_cache.py:52-60` catches every exception and continues. A provenance failure would
    be logged per step there, not stop the run. That is that worktree's choice, and it is unaffected
    for valid runs.
- `experiments/tests/test_field.py:56` uses only `steps()`, which is unchanged.
- Nothing there uses `.source`, `to_domino_volume`, `read_field_snapshot`, pickling or a
  `DataLoader`.

In this repository, `benchmarks.stress_integral.extract_eulerian_box` is the only other reader
caller. It passes a tuple `fields`, does not expose the new fields, and inherits the path pre-check.

### Out of scope

- **#143:** its own PR, by the user's decision.
- **#152 and #112 item 4:** these need a spec change and #107's multi-FAB fixture.
- **#107** and **#153**.
- **Garbage-`Header` detection** (D2).
- **Cross-host joinability of `source`** (D3).
- **Tightening `force_surrogate.sidecar.validate_image_digest` and `metadata_capture._FULL_SHA_RE`.**
  Both are looser than this change's checks: `search` accepts junk around a digest, and the `$` anchor
  accepts a trailing newline. Filed as #159. The manifest path's own import of the force-surrogate stack is #160.
- **Making `FieldSnapshot.__eq__` usable.**
- **Any change to the arrays `read_field_snapshot` returns.** Bit-parity is re-verified (§7).

## Impact

- **Specs:**
  - `field-surrogate`: MODIFIED "Framework-neutral field snapshot contract", "Field selection
    validated before any array is read", "Corpus addressing by config and step" and "DoMINO
    volume-half adapter…"; ADDED "Corpus snapshots carry run identity and digest-pinned provenance"
    and "Training-facing entry points refuse zero-cell snapshots".
  - `visualization-tooling`: ADDED "`flow_video` discovers plotfile frames with the corpus's own
    listing".
- **Code:**
  - `src/mosquito_cfd/field_surrogate/snapshot.py`, `corpus.py` and `domino_adapter.py`;
  - new `src/mosquito_cfd/field_surrogate/_provenance.py`;
  - `src/mosquito_cfd/visualization/flow_video.py`;
  - `scripts/make_flow_video.py` (help text only).
- **Tests:**
  - `tests/test_field_surrogate_snapshot.py`, `test_field_surrogate_corpus.py` and
    `test_field_surrogate_domino_adapter.py`;
  - new `tests/_spawn_workers.py` and `tests/_torch_workers.py`;
  - `tests/test_flow_video.py` and `test_flow_video_plotfile.py`.
- **Docs:** `openspec/project.md`, `docs/CHANGELOG.md` and `docs/field_surrogate/roadmap.md`.
- **Dependencies, Docker, CI:** no change.
  - The torch `DataLoader` test is skipped where torch is absent: CI and the default sync, since torch
    is in the Linux-gated `train` group. It is run once on this host with `uv run --with torch`, and
    the result goes in the PR body (tasks §2.3).
  - The spawn-worker test runs everywhere, with a timeout.
- **Issues:**
  - The PR fixes #151 and #144, and advances #113.
  - Every #113 item is done here, already done on main, or deferred (garbage Header).
