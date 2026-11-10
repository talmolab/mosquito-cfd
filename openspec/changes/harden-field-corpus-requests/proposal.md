# harden-field-corpus-requests

## Why

The review of #105 found four input-handling gaps in the F2 field-surrogate reader. All four predate
#105. In the first three, a caller bug gets through without an error:

- **#122:** an inverted region request (`lo > hi` on some axis) returns a small arbitrary region.
- **#121:** a non-integer `step` is either accepted or produces a misleading error.
- **#121:** two directories for the same step are resolved by filesystem listing order.

The fourth is cost. `FieldCorpus.plotfile()` lists and stats the run directory even when the
plotfile has AMReX's canonical name (#121).

The work is local and cluster-free. There is no solver, deck, Docker or dependency change, and no
committed artifact changes. It is independent of the #109 force-sign work.

## What Changes

- **BREAKING:** `read_field_snapshot` raises `ValueError` when `lo > hi` on any axis. The check runs
  before `yt` is imported. `extract_eulerian_box` delegates to it and inherits the rejection. This is
  a second documented divergence from the frozen legacy adapter (design.md D1). Before, the reader
  returned a small region derived from the padded indices, without an error.
- **BREAKING:** `FieldCorpus.plotfile()`, and therefore `snapshot()`, accepts only an `int` or
  `np.integer` step, not a `bool`, with value `>= 0`. The check runs before any manifest read or
  filesystem access (D4).
- **BREAKING:** two directories that parse to the same step make `steps()` and `plotfile()`'s
  fallback scan raise. Before, `steps()` returned the step twice and `plotfile()` returned whichever
  directory came first in the listing (D5).
- `FieldCorpus.plotfile()` returns `runs/<config>/plt{step:05d}` after a single `is_dir()` when that
  path is a directory. Otherwise it scans the run directory. The fast path trusts the canonical name
  (D2).
- `build_flow_video` requires `box_margin` to be a finite real number `> 0`, checked next to `fps`
  (D3).
- `sphere_cv_steadiness_fraction` checks `x_inlet < x_outlet` before reading a plotfile, as
  `sphere_cv_drag_cd` already does. That way an inverted slab is reported in the caller's terms, not
  as the reader's `lo`/`hi` error (D1).
- The existing `test_rejects_non_positive_fps` passes even with its guard deleted. It matches `"fps"`
  against an error message that contains the `tmp_path`. It is fixed alongside the new `box_margin`
  test, which is modelled on it.

The breaking changes reject only inputs that were always caller bugs. No in-repo caller passes one
(tasks 1.1 and 4.1).

## Out of scope

- **#112:** the rest of `FieldCorpus`'s NFS cost, namely `steps()`'s listing and the fallback path's
  `run_dir()` stat. #121's own comment assigns this to #112.
- **#113, #120 and #107:** the other reader follow-ups.

## Impact

- **Affected specs:**
  - `field-surrogate`: 3 MODIFIED requirements (Region semantics, Eulerian-box adapter delegation,
    Corpus addressing).
  - `visualization-tooling`: 1 ADDED requirement.
- **Affected code:**
  - `src/mosquito_cfd/field_surrogate/snapshot.py`
  - `src/mosquito_cfd/field_surrogate/corpus.py`
  - `src/mosquito_cfd/visualization/flow_video.py`
  - `src/mosquito_cfd/benchmarks/stress_integral.py`: the `sphere_cv_steadiness_fraction` guard, plus
    docstrings for `extract_eulerian_box` and `check_field_capture_velocity`
  - `scripts/make_flow_video.py`: `--box-margin` help text only
- **Affected tests:**
  - `tests/test_field_surrogate_snapshot.py`
  - `tests/test_field_surrogate_corpus.py`
  - `tests/test_flow_video.py`
  - `tests/test_stress_integral.py`
- **Affected docs:**
  - `docs/CHANGELOG.md`: a new `### Fixed` entry, plus amendments to the Unreleased #106 entries
  - `openspec/project.md`: one clause
- **Real-plotfile check:** `scripts/verify_eulerian_box_ab.py` iterates `REGION_CASES`, so it stops
  comparing the two inverted cases on real plotfiles. Nothing replaces them there, because the
  rejection happens before `yt.load` (D1).
- **Published images:** merging rebuilds `:fp64` and `latest-python` from the new `src/`. Docker
  files are unchanged, and production Argo pins image digests.
