# Tasks — add-field-surrogate-reader

TDD throughout. All tests are **unmarked** and fixture-based so they gate CI (`requires_plotfile`
tests auto-skip on the runner and are never a gate). Fixture properties are documented in
`tests/fixtures/README.md` (task 35) — not restated here, since this file is deleted at archive.

**Standing rules for every task below:**

- Every new `src/` symbol carries its google-style docstring in the same commit that introduces it —
  ruff's `D` ruleset is enforced on `src/` (and ignored under `tests/**`), so there is no
  "docstrings later" commit. `D417` requires every parameter documented in `Args:`.
- New tests resolve the fixture as `Path(__file__).resolve().parent / "fixtures" / "lev_boxlib_plt"`,
  never the cwd-relative form used in `tests/test_stress_integral.py`.
- Proxies over `yt` objects are hand-written classes, **never** `unittest.mock.MagicMock` — a mock
  auto-creates any attribute, so a test can pass against an implementation reading the wrong one.
- No new committed plotfile fixture. If that ever becomes necessary, it needs a matching
  `.gitattributes` `-text` rule (the existing rule is scoped to `lev_boxlib_plt/**` only) and a
  regenerability test; add a task then rather than improvising.

# PR A - additive (no existing `src/` line changes)

## 1. Package skeleton

1. [x] **Test first** (`tests/test_field_surrogate_snapshot.py`): in a **subprocess**
   (`subprocess.run([sys.executable, "-c", …])`), import `mosquito_cfd.field_surrogate`, each of its
   three submodules, and `mosquito_cfd.benchmarks.stress_integral`; assert no module named `yt` or
   beginning `yt.` is in `sys.modules`, and likewise no `pandas`. A subprocess is **required**: an
   in-process check is order-coupled — the sibling corpus test file sorts earlier and imports `yt`,
   so an in-process probe fails deterministically in full-suite CI while passing during solo TDD.
2. [x] **Test first**: a static AST check over `src/mosquito_cfd/field_surrogate/*.py` asserting every
   `import yt` / `from yt import …` node has a function as its nearest enclosing scope. Survives a
   future fourth submodule.
3. [x] Create `__init__.py` plus `snapshot.py`, `corpus.py`, `domino_adapter.py` as **docstring-only
   stubs** (a module docstring satisfies `D100`/`D104`; no functions means no `D103`). `__init__.py`
   performs **no submodule imports** — per D4 an eager `corpus` re-export both ~6×'s
   `stress_integral`'s import cost and arms a `benchmarks → field_surrogate → force_surrogate →
   benchmarks` cycle.

## 2. Reader core (`snapshot.py`)

4. [x] **Test first**: reading the fixture over full extent gives `u`/`v`/`w` matching the analytic
   solid-body rotation `(-Ωy, Ωx, 0)` at `Ω = 1.3`; arrays bare `np.float64` indexed `[ix, iy, iz]`;
   `dx == [1,1,1]`; `time == 0.5` and `type(time) is float`; `max_level == 0`; `Path(source)` resolves
   to the fixture path.
5. [x] Implement `FieldSnapshot` (frozen dataclass) and a minimal full-extent `read_field_snapshot`
   with lazy `import yt`.
6. [x] **Test first**: snapshot arrays report `flags.writeable is False`; two reads of the same region
   do not share memory (`np.shares_memory` is `False`); assignment into a returned array raises.
7. [x] **Test first**: `fields=("u","density","tracer")` returns exactly those three, `field_names` in
   the requested order, and a **recording proxy** over the covering grid confirms exactly the three
   corresponding `('boxlib', …)` tuples were read and no others. Also assert a default
   `extract_eulerian_box` call reads exactly six — otherwise a default of all eight would silently add
   33% I/O to a per-frame video loop with nothing failing.
8. [x] **Test first**: an unknown short name, and a canonical name absent from the plotfile, each raise
   `ValueError` naming the field **with the recording proxy showing zero reads**. Build the
   absent-field case by regenerating the fixture into `tmp_path` via
   `make_lev_boxlib_fixture.write_fixture` with a reduced field tuple (extend `write_fixture` to take
   `fields=FIELDS`, a two-line change) — the committed fixture has all eight, so there is no
   absent-field plotfile otherwise. Do **not** take a "use a plotfile lacking the field" shortcut that
   skips the zero-reads half.
9. [x] **Test first**: a dataset proxy returning `float32` for one required field and `float64` for
   the rest raises `ValueError` naming the field and both dtypes, and constructs no snapshot. This
   guard is uncatchable by any equality test against the FP64 fixture, and is untested at HEAD.
10. [x] Implement the canonical short-name map, field validation, and the dtype-before-cast guard.

## 3. Region semantics (the D1 compatibility surface)

11. [x] **Test first**: parametrize over the clamping matrix on the 6³ fixture — full `±inf`; a
    non-cell-aligned interior box; an exactly cell-aligned box; `halo` both unclipped and clipped at
    the boundary; mixed `±inf` on some axes only; a zero-width **interior** request (→ 1 cell/axis); a
    request at the upper domain edge (→ **0 cells**, per D1's correction); a request wholly outside the
    domain (→ 0 cells); and an inverted `lo > hi` request. Do not assert "halo adds exactly 2h cells"
    unconditionally — that holds only unclipped (`halo=3` on a 2-cell box gives 6, not 8).
12. [x] Implement the region semantics, preserving `i_hi = min(max(i_hi, i_lo + 1), ddims)` exactly.
13. [x] **Test first**: decide and pin the behaviour for a non-finite, non-`±inf` `lo`/`hi` (today
    `np.floor(nan).astype(int64)` yields `INT64_MIN` with a `RuntimeWarning`, degrading silently to a
    full read). Prefer rejecting with a clear `ValueError`; whichever is chosen, pin it.

## 4. Point-cloud view

14. [x] **Test first**: `coords (N,3)` / `values (N,F)` with `N == nx·ny·nz`; a chosen cell's row index
    equals its independently-computed C-order index and holds that cell's own centre and values;
    `cell_volume == prod(dx)` everywhere; `PointCloud` arrays are non-writable.
15. [x] **Test first**: a 1-cell snapshot flattens to `(1,3)`/`(1,F)` and a 0-cell snapshot to
    `(0,3)`/`(0,F)` — no raise, no collapsed dimension.
16. [x] Implement `PointCloud` and `FieldSnapshot.to_point_cloud()`.

## 5. AMR refusal

17. [x] **Test first**: a hand-written proxy wrapping the **real** fixture dataset, overriding only
    `index.max_level` to non-zero, makes `read_field_snapshot` raise `ValueError` containing the
    observed level and `CC-F3`, with zero field reads — **plus** a companion assertion that the same
    proxy left at `max_level == 0` succeeds, which is what proves the guard reads the attribute the
    proxy overrides. (The matching assertion *through* `extract_eulerian_box` belongs to PR B — until
    the delegation lands, the wrapper still raises its own pre-existing message.)
18. [x] Implement the guard with the CC-F3-naming message. Note in the commit body that the message
    wording changes from the current `"extract_eulerian_box requires a single-level plotfile"` — no
    test asserts that string today, so nothing breaks, but a log-grepper should not be misled.

# PR B - the refactor (see D12)

## 6. Delegation of `extract_eulerian_box` (the risky step)

19. [x] Create `tests/fixtures/legacy_extract_eulerian_box.py`: the current body of
    `extract_eulerian_box` copied **byte-for-byte from HEAD before any edit**, as
    `legacy_extract_eulerian_box`, with a header comment recording the source commit SHA.
20. [x] **Test first — differential, not self-referential**: for every case in the task-11 clamping
    matrix, assert the refactored `extract_eulerian_box` and `legacy_extract_eulerian_box` return
    dicts with identical **key sets** (`sorted(a) == sorted(b)`, so `time`/`source`/`max_level` cannot
    leak in), `np.testing.assert_array_equal` on every value, and matching Python **types** — `dx` an
    `ndarray` of `dtype float64` shape `(3,)`, `current_time` a `float`. Per D10, comparing the wrapper
    to a re-pack of `read_field_snapshot` instead would be tautological.
21. [x] **Test first**: with `si.extract_eulerian_box` replaced by a sentinel, each of
    `sphere_cv_drag_cd`, `check_field_capture_velocity`, and `sphere_cv_steadiness_fraction` reaches
    the sentinel — the executable form of D3's invariant, replacing a code-reading check.
22. [x] **Test first**: a field containing NaN/Inf passes through the reader **bit-identically**
    (`assert_array_equal` with NaN positions preserved), so `check_field_capture_velocity`'s downstream
    guard still sees what it expects. All six of its existing NaN/Inf tests monkeypatch the reader
    away, so none of them exercise the read path.
23. [x] Refactor `extract_eulerian_box` to delegate and re-pack, preserving import path, signature,
    lazy `yt`, and the exact keys `u, v, w, gradpx, gradpy, gradpz, x, y, z, dx, current_time`. Import
    `field_surrogate.snapshot` by submodule path, never through the package (D4).
24. [x] Run the full existing suite; `test_stress_integral.py`, `test_wing_lev.py`,
    `test_flow_video.py`, `test_make_flow_video_cli.py` must pass **unchanged** — no test edits are
    permitted to make the refactor pass. Note this is necessary but weak: all 21 patch sites replace
    the wrapper, so none of them executes a line of the new reader.

# PR A continued

## 7. Corpus addressing (`corpus.py`)

25. [x] **Test first** (`tests/test_field_surrogate_corpus.py`): a synthetic corpus tree under
    `tmp_path` (a minimal sweep manifest plus a config dir holding a copy of the fixture named
    `plt00100`) — `config_ids()`, `steps()`, `global_params()`, `snapshot()` all behave.
26. [x] **Test first**: `steps()` on a dir containing `plt00100`, `plt01000`, a regular **file** named
    `plt00200`, a dir `plt00300.old`, and a dir `pltXXXXX` returns exactly `[100, 1000]` ascending, and
    returns identically across two calls (glob order is filesystem-dependent). Include a truncated
    config, the real `ns.cfl = 0.3` failure mode.
27. [x] **Test first**: a missing config, a missing step, and a missing corpus root each raise a
    `ValueError` naming what was sought and the path searched; a malformed manifest surfaces
    `load_manifest_configs`'s guarded error, not a bare `KeyError`.
28. [x] Implement `FieldCorpus`, reusing `force_surrogate.dataset.load_manifest_configs` (D8).

## 8. DoMINO volume-half adapter (`domino_adapter.py`)

29. [x] **Test first** (`tests/test_field_surrogate_domino_adapter.py`): the returned dict's key set is
    **exactly** the five volume-half keys with shapes `(N,3)`, `(N,F)`, `(nx,ny,nz,3)`, `(P,1)`,
    `(P,1)` and no leading batch dimension; the six geometry-half keys are absent by key membership,
    not zero-filled.
30. [x] **Test first**: `grid[0,0,0] == (x[0], y[0], z[0])` **and** `grid[nx-1,0,0] == (x[-1], y[0],
    z[0])` — the second is what catches an `indexing="xy"` meshgrid swap, since `[0,0,0]` is invariant
    under it.
31. [x] **Test first**: (a) an AST check that `domino_adapter.py` contains no `import torch` /
    `import physicsnemo` at **any** scope; and (b) a subprocess import with `sys.modules["torch"]` and
    `["physicsnemo"]` poisoned to `None`, then import and call. Plain "it imports on CI" cannot fail on
    a runner where neither package is installed, and (b) also has teeth on the A5000 dev host where
    `--group train` **is** installed.
32. [x] **Test first**: the adapter's documentation states that `volume_fields` is a target rather than
    an encoder input, that this corpus has no pressure field and carries its gradient instead, and
    names each of the six absent keys. Precedent: `tests/test_no_false_diffused_ib_claim.py`.
33. [x] Implement `to_domino_volume` with the D6 docstring.

## 9. Docs

**PR assignment.** Tasks 35-37 are PR A (independent of the refactor). Tasks 34, 38, 39 are PR B -
the stale docstrings only become stale once the delegation lands, and the CC-F2 resolution note and
F2 status glyph both record a state that is not true until then. Task 40 (CHANGELOG) gets one entry
per PR, each with its own number.


34. [x] Rewrite the four docstrings the refactor makes inaccurate: `stress_integral.py`'s module
    docstring ("the yt adapter is the only cluster-touching code"), its `# --- yt adapter …` section
    comment, `extract_eulerian_box`'s own docstring (every mechanic it describes now lives one module
    away — reduce to a wrapper description pointing at `read_field_snapshot` and D3), and
    `wing_lev.py`'s "the only cluster-touching read" parenthetical. "Preserving docstring intent" is
    not a specification for this rewrite, hence the explicit list.
35. [x] Document `lev_boxlib_plt/` in `tests/fixtures/README.md` (currently titled "force-surrogate"
    and documenting 2 of 6 entries) — dimensions, `dx`, `current_time`, the eight fields, the analytic
    `Ω = 1.3` rotation and its known LEV answer, the regeneration command, the `.gitattributes` rule,
    and that it backs CC-F4 for the single read path. Retitle to drop "force-surrogate".
36. [x] `openspec/project.md`: add **both** `visualization/` (already missing) and `field_surrogate/`
    to the directory tree, plus a short `field_surrogate` section mirroring "Visualization Tooling".
37. [x] `openspec/project.md`, four verified accuracy fixes (D9): `line-length: 100 → 88` noting
    `E501` is ignored; add `D` (pydocstyle/google, `tests/**` exempt) to the Rules line; add
    `pyarrow>=18.0.0` to the dependency list; correct the lint command from `uv run ruff check .`
    (fails with 27 errors) to CI's explicit path list.
38. [x] `docs/field_surrogate/roadmap.md`: add a `> **Resolved …**` note under CC-F2 recording that the
    single read now lives in `read_field_snapshot` with `extract_eulerian_box` delegating, so
    "rather than writing a new reader" means one read *path*, not one module. While there, fix the
    dangling `CC-F5` references (only CC-F1..CC-F4 exist) and CC-F4's "PR2/PR3" → "F2/F3".
39. [x] Flip the F2 **Status glyph** `⬜ → ✅` in the roadmap table (it is a glyph, not a checkbox) —
    in-branch, since squash-merge leaves no opportunity to edit at merge time.
40. [x] `docs/CHANGELOG.md` entry with the PR number, per repo convention (also covered by
    `/pre-merge-check`).

## 10. Validation

**PR assignment.** Tasks 41-42 run on both PRs. Tasks 43-45 are PR B only - they verify the
delegation against real plotfiles and have nothing to check on the additive PR.


41. [x] `openspec validate add-field-surrogate-reader --strict`. Note this is **not** a CI gate — no
    workflow runs it — so it is a pre-push checklist item.
42. [x] Run the CI form locally **from Git Bash or WSL**, not PowerShell: `uv sync --frozen --group viz`,
    then `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`,
    the identical `ruff format --check` with the same six paths spelled out, then
    `uv run pytest -v -m "not gpu"`. (Pre-existing, unrelated: `test_provision_dies_on_wing_vertex_hash_mismatch`
    hard-asserts `shutil.which("sha256sum")` and fails under PowerShell only.)
43. [x] **Real-plotfile verification (D11), before merge.** With Z: mounted, run
    `MOSQUITO_CFD_PLOTFILE_ROOT=<root> uv run pytest -v -m "not gpu" -rs` and record in the PR **how
    many previously-skipped tests actually ran** — a mandatory check with no recorded result is
    indistinguishable from one never run.
44. [x] **Bit-exact A/B on real plotfiles (D11), before merge.** For ≥3 real plotfiles (sphere
    coarse/medium, wing T3b-medium), compare `extract_eulerian_box` against
    `legacy_extract_eulerian_box` over the full task-11 region matrix plus the pinned wing near-field
    box and the sphere inlet/outlet planes, with `assert_array_equal` — **zero tolerance, not
    `allclose`**. This is the only check covering multi-FAB covering grids, non-unit `dx`, and
    non-zero domain origins. Scratchpad script, output pasted into the PR; not a committed test.
45. [x] (filed as #107) File the D11 follow-up issue: a second committed fixture with anisotropic `dx`, a non-zero
    domain origin, and >1 FAB, so CI stops depending on a degenerate plotfile.

## D11 verification results (recorded, per project.md's verification principles)

A mandatory check with no recorded result is indistinguishable from one never run, so the outcomes
live here rather than only in a terminal.

**Task 43 -- full suite with the plotfile root mounted.** All **13** `requires_plotfile` tests pass,
zero failures attributable to the refactor. They need **two different roots**, which is why a single
run showed 6 failures at first:

| root | tests | result |
|---|---|---|
| `Z:/users/eberrigan/mosquito-cfd-benchmarks` | 7 (incl. both direct `extract_eulerian_box` real-plotfile tests) | pass |
| `Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing` | 6 (`test_flow_video_plotfile.py` x5, `test_wing_lev_medium_vs_coarse`) | pass |

`test_wing_lev_medium_vs_coarse` is the strongest single signal: the T3b LEV composition on real
coarse+medium wing plotfiles, through `extract_eulerian_box`, reproducing its pinned numbers.

**Task 44 -- bit-exact A/B against the frozen oracle.** **80 region comparisons across 5 real
plotfiles, all bit-exact** (`assert_array_equal`, zero tolerance), comparing key set, values, dtype,
shape, Python type and writeability:

| plotfile | grid | dx |
|---|---|---|
| `flow_past_sphere_coarse/plt10000` | 128x64x64 | 0.15625 |
| `flow_past_sphere_10k/plt10000`, `plt05000` | 256x128x128 | 0.078125 |
| `t3c-fine/plt01000` | 256x128x256 | 0.03125 |
| `t2a-newconv4/plt01000` | 64x32x64 | 0.125 |

This covers the multi-FAB covering grids and non-unit `dx` that CI's 6-cubed fixture cannot reach.

**Gap that remains open.** Every plotfile in the project's data has `domain_left_edge = [0, 0, 0]`,
so the **non-zero domain origin path is verified nowhere** -- there is no such plotfile to test
against. Task 45's follow-up fixture exists to close this and is deliberately still open.

**Process note.** The first A/B run reported "ALL BIT-EXACT" after **zero** comparisons: MSYS
rewrote the `/z/users/...` form into a backslash path on the way into Python, every plotfile was
skipped, and the script had no guard against having done no work. Fixed by using the `Z:/` drive
form and making `checked == 0` a hard failure. Worth remembering for any future verification
script -- a pass with no recorded count is not a pass.
# Review corrections (post-#105/#106 subagent review)

Five reviewers on #105 and two on #106. The structural finding that drove these: **every mutation
derived from the implementation was caught; every mutation derived from a `SHALL` in the spec
survived.** Post-hoc mutation testing validates that tests agree with the code — precisely what the
skipped red phase fails to establish. So each correction below is written test-first, from the
corrected spec text, and verified by re-running the reviewer's surviving mutation.

## 11. Correctness (PR A)

46. [x] **Test first**: a **real** fp32 boxlib plotfile (FAB RealDescriptor declaring `float32`, via a
    new `real_dtype=` parameter on `make_lev_boxlib_fixture.write_fixture`, written to `tmp_path`) is
    refused. yt's AMReX frontend allocates output buffers `float64` unconditionally, so the shipped
    `raw.dtype != np.float64` predicate can never fire — verified by a reviewer who built such a file
    and had it accepted, reporting `float64` while carrying fp32-truncated values.
47. [x] Guard on `ds.index._dtype` (the dtype yt parses from the RealDescriptor). Keep the
    returned-array check as defence in depth, documented as such rather than as the guard.
48. [x] **Test first**: duplicate short names raise with zero field reads. Today `fields=("u","u")`
    gives `arrays` with 1 entry and `field_names` with 2, a point cloud with two identical columns,
    and one yt read per repetition.
49. [x] **Test first**: arrays satisfy `base is None` for a **full-extent** read (the case where
    `np.ascontiguousarray` returns the view, so `setflags(write=False)` leaves a writable, reachable
    base) as well as for a sub-box. Force the copy with `np.array(..., copy=True)`. Do **not** fix
    this with `raw.setflags(write=False)` — PR B's wrapper calls `setflags(write=True)` and would
    raise.
50. [x] **Test first**: a negative `halo` and a fractional `halo` each raise. `halo=1.9` currently
    pads asymmetrically (2 cells low, 1 high) because each face truncates independently.
51. [x] **Test first**: importing **only** `mosquito_cfd.field_surrogate` leaves no
    `mosquito_cfd.field_surrogate.*` in `sys.modules`. The existing probe imports the submodules
    itself, so it cannot see an eager re-export; verified by a reviewer whose eager-`__init__` mutant
    left the suite green.
52. [x] **Test first**: `global_params` returns exactly the three kinematic keys. `return dict(config)`
    currently survives, leaking `reynolds`/`split`/`input_file`/`index`.
53. [x] **Test first**: `steps()` sorts numerically with inconsistent padding (`plt2`, `plt10`,
    `plt00100`). Uniform padding makes lexical and numeric order coincide, so the shipped matrix
    cannot detect a dropped `sorted()`.
54. [x] **Test first**: the DoMINO key partition matches key names written **literally in the test**,
    not imported from the module. Both shipped tests read their expectations from the module under
    test, so moving `sdf_nodes` into the emitted set and zero-filling it left the suite green — the
    exact failure the spec and docstring call out.

## 12. Claim corrections (PR A + PR B)

55. [x] `project.md`: the reader returns an immutable `FieldSnapshot` — true only once task 49 lands;
    keep the wording and make it true, rather than softening it.
56. [x] `to_domino_volume` docstring: remove the "e.g. the kinematics from `FieldCorpus.global_params`"
    integration path, which returns a **dict** and raises `TypeError` if passed. Say the two sequences
    correspond positionally.
57. [x] Correct "IAMReX plotfiles carry no pressure field" to *this corpus's* plotfiles in the
    docstring and CHANGELOG, and cite the real verification at
    `openspec/changes/archive/2026-07-08-grade-wing-grid-convergence-medium/design.md:119`.
58. [x] Correct the two false comments claiming `ascontiguousarray` copies / arrays are "freshly
    allocated and unshared" (`snapshot.py`, and `stress_integral.py` in PR B).
59. [x] PR body + CHANGELOG (PR B): "behaviour unchanged" is falsified — a NaN corner and a scalar
    `lo`/`hi` both previously succeeded and now raise. State the narrowing.
60. [x] Fix the test-count claim (55, not 56) and make the patch-site count say which set it counts.

## 13. Guarding the guards (PR B)

61. [x] Add `tests/fixtures/legacy_extract_eulerian_box.py` to ruff's `exclude`, and add a
    content-hash test pinning it. Nothing currently stops `ruff format` from rewriting the frozen
    oracle, which would silently turn the equivalence claim into a comparison against modified code.
    A hash is squash-merge-safe; a `git show 86c729e` test is not.
62. [x] Move the writeability assertion into the parametrized differential (it covers 1 region of 11),
    and add an x-slab-only case — the shape `sphere_cv_drag_cd` actually requests in production, and
    one of the two zero-copy regimes.

## 14. Verification

63. [x] Re-run every surviving mutation from the review and confirm each now fails:
    `steps()` unsorted; `global_params` to `dict(config)`; `ascontiguousarray` to a bare view; eager
    `__init__` re-exports; `sdf_nodes` moved to the emitted set and zero-filled. Per
    `feedback-fixes-need-same-scrutiny-as-original-code`, re-run rather than re-read.
64. [x] Full CI-form lint/format/test from Git Bash, and `openspec validate --strict`.
65. [x] File issues for everything deliberately not done here: **#112** (measured performance --
    the 553K-stat NFS storm, the duplicated `grid`, covering-grid retention, sub-box reads) and
    **#113** (robustness and provenance -- unhelpful path errors, inverted corners, zero-cell
    training examples, mixed mutability, and surfacing the digest-pinned `run_metadata.json`
    that already sits beside every plotfile). **#107** covers the degenerate CI fixture.
