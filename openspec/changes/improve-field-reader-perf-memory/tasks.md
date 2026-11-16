# Tasks: improve-field-reader-perf-memory

## Conventions

- **Red, then green, in one commit.**
  - Write each red test first and run it.
  - Check that it fails for the reason stated, and record that output (the assertion and any
    measured value) in the commit body.
  - Commit the test with the change that makes it pass, so CI is green at every commit.
- **Anchors.** An anchor pins behaviour that holds today. Anchors are numbered and committed *before*
  the change they protect.
- **Bit-identity.** 3.1 (full-grid reference) and the frozen legacy oracle run on every commit from
  3.1 on, with halo 0–3 included.
- **Spies.**
  - Install spies after `FieldCorpus(root)` and every fixture copy are built.
  - Filter to paths under the corpus root, so `shutil`, pytest and yt calls are not counted.
  - Accept `str`, `bytes`, `PathLike` and fd arguments.
  - Every spy or fake has a positive control: it must record a call where real I/O happens.
- **Memory tests (design.md D9).**
  - Do a warm-up read of the same file, and run `gc.collect()` before each traced read.
  - Leave automatic GC **enabled** unless a test states otherwise.
  - In `finally`, restore the prior `tracemalloc` and GC state (`is_tracing()`, `isenabled()`).
  - Skip if a trace is already running on entry.
  - Assertions are deterministic (`weakref`) or differential in units of `S` (one field's bytes). Never assert an
    absolute MB figure.
- **Environment.**
  - Use `unset VIRTUAL_ENV; PYTHONPATH=src uv run pytest … -p no:cacheprovider`. The shared venv's
    editable install points at the main checkout.
  - Run `uv sync --frozen --group viz` first.
- **Mutation testing.**
  - Set `PYTHONDONTWRITEBYTECODE=1`.
  - Restore files from bytes saved before mutating, never with `git checkout`.
  - The table is in 8.1.
- **Files and shell.** Use LF endings. Put longer scripts in the scratchpad, not in heredocs.
- **Git.**
  - Commit and push only when the user asks; never use a bare `git stash`.
  - Commit messages never contain closing keywords, negated or not.
  - Once the branch is pushed, take `main` with `git merge origin/main`, not a rebase and force-push.
    The repo squash-merges.
- **Do not touch:**
  - the force-surrogate training, metrics, figures and README;
  - #109's follow-ups #133, #135, #137, #138 and #139;
  - #114, #115, #124, #130 and #131.

## 0. Baselines and the proposal commit (before any code change)

0.1 [x] **Corpus pass.**
    - Build a scratchpad script on a local synthetic corpus: 27 configs × 200 empty `plt` dirs and a
      valid manifest.
    - Over `config_ids() → steps() → plotfile()` for every pair at `90b2a72`, count:
      - manifest loads;
      - `os.scandir`, `os.listdir` and `os.stat` calls under the root;
      - wall time.
    - Also time one `steps()` pass over every config of the real corpus,
      `Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine`, read-only.
    - Record the method and the numbers here.

    **Result at `90b2a72`** (Python 3.11.13, Windows, local NTFS; script `base_corpus.py`):
    - **Synthetic pass:** 5400 `(config, step)` pairs, 1 manifest load, 0 `os.scandir`,
      27 `os.listdir`, 10827 `os.stat`, 0.90 s. The `stat` count is 27 run-directory checks, plus
      5400 per-entry `is_dir` calls inside `steps()`, plus 5400 canonical `is_dir` calls in
      `plotfile()`.
    - **Real corpus on Z:, one `steps()` pass:** 26 manifest configs, 1098 steps. Best of three:
      2.33 s cold, then 0.32 s and 0.26 s warm.

0.2 [x] **Reader memory, with automatic GC enabled.** Method:
    - a warm-up read, then three full-extent reads of the six default fields in one process;
    - after each read, record the peak above its starting level, the traced memory held after
      return minus the returned arrays, the read time, and whether a `weakref` to the dataset is
      alive.

    Run it at `90b2a72` on the synthetic 256×128×256 file and on the real
    `Z:/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine/runs/s35_f085_p30/plt01000`
    (256 FABs). Do the same for an `outside_domain` zero-cell read. The design's D4 table gives the
    synthetic numbers already measured.

    **Result at `90b2a72`** (script `base_reader.py`): the second table in design.md D4. The
    dataset was alive on every return. Each read took 3.8–4.9 s.

0.3 [x] **Point cloud.** Record the `to_point_cloud()` peak on in-memory 64³ and 256×128×256
    snapshots with `k = 6`.

    **Result at `90b2a72`** (script `base_pc.py`):
    - 64³: 27.3 MB.
    - 256×128×256: 872.4 MB.
    - Both sizes: 104.0 bytes per cell, 1.444× `coords + values`, `cell_volume` strides `(8,)`.

0.4 [x] **First commit:** `docs(openspec): propose improve-field-reader-perf-memory`. It contains the
    change directory with the 0.x numbers.

## 1. Corpus listing with `os.scandir` (#112 item 1; `corpus.py`)

1.1 [ ] **Anchors**, in one `test(field-surrogate)` commit, all passing today:
    - `test_symlinked_plotfile_directory_counts`, per the spec scenario.
      - The symlink `plt300` uses a non-canonical name, so both `steps()` and `plotfile()` go
        through the listing.
      - It is skipped with a reason where `os.symlink` raises.
    - `test_plotfile_presence_is_reread_and_the_manifest_is_not`, per the spec scenario.
    - The manifest-once half of the corpus pass. The existing
      `test_manifest_is_parsed_from_disk_only_once_per_instance` already pins it for one instance;
      extend it to the full pass.

1.2 [ ] **Migrate the test infrastructure** in the same commit as 1.4.
    - **The fakes.** `_IoSpy`, `_listing_order` and the nested `reverse_numeric_iterdir` become fake
      `os.scandir`s:
      - each is a context manager over the real `DirEntry`s, in the forced order;
      - each records its own calls under the corpus root;
      - every test that installs one asserts it was called at least once.
    - **The counting tests.** `test_missing_step_lists_the_run_directory_once`,
      `test_noncanonical_step_resolves_with_one_listing` and
      `test_canonical_plotfile_resolves_without_listing` assert on `scandir:`. The last one gains a
      positive control: a `plt7` lookup on the same spy records exactly one `scandir:`.
    - **Red today:**
      - every migrated forced-order test fails on its "fake was called" assertion;
      - the two `== 1` counting tests fail;
      - the canonical test's positive control fails.

      The duplicate-message and numeric-sort assertions themselves still pass, because the code
      sorts. That is why liveness is asserted separately.

1.3 [ ] **Red tests:**
    - `test_listing_costs_one_scandir_and_no_per_entry_stat`, per the spec scenario. It fails
      today: there are 0 `scandir` calls, and `stat` calls grow with the entry count.
    - The scandir half of the corpus-pass test, with `plt7` in the first config as its positive
      control. It fails today with 0 calls.
    - `test_failing_entry_type_check_is_skipped_only_when_gone`, per the spec scenario.
      - **Skip half:** a real dangling symlink `plt00200`, skipped with a reason where `os.symlink`
        raises. It passes today and after the change.
      - **Propagate half:** a fake `scandir` yields a stub entry whose `is_dir()` raises
        `PermissionError`. Today `Path.is_dir` is called instead of the stub's, so the stub never
        raises and this half fails.

      **Why a real symlink instead of a stub, changed during implementation.** CPython's
      `DirEntry.is_dir()` catches `FileNotFoundError` itself and returns `False`, so no real entry
      raises it. A stub that raised it would force a `try/except` modelling nothing real.
    - `test_scan_closes_the_listing_on_the_duplicate_raise`. A spy wraps the real `os.scandir`, with no
      forced-order fake, and asserts the iterator was closed exactly once when `steps()` raises on
      `plt100` beside `plt00100`. It fails today: the spy is never called.

1.4 [ ] **Implement:**
    - `_scan` uses `with os.scandir(run) as it:` and `entry.is_dir()`, and returns
      `run / entry.name` (D1);
    - add `import os`, in isort order;
    - update the module and class docstrings: the listing cost, and that `_scan` is the only `os`
      use.

    Commit: `perf(field-surrogate): list each run directory with one os.scandir, no per-entry stat`.

## 2. Plotfile names (#145; `corpus.py`)

2.1 [ ] **Red test:** `test_only_ascii_digit_whole_name_plotfiles_count`, per the spec scenario.
    - The real directory `plt١٠٠` is tested alone and beside `plt00100`.
    - A fake `scandir` yields stub entries named `plt١٠٠` and `plt100\n`, each with
      `is_dir() → True`, beside the real `plt00100`. This runs on every OS.
    - Fails today: `plt١٠٠` lists as step 100, and both stubs make the scan raise "ambiguous".

2.2 [ ] **Implement:**
    - `_PLT_PATTERN = re.compile(r"plt([0-9]+)")` with `.fullmatch()`;
    - update its comment;
    - fix the `steps()` docstring (`corpus.py:162`): "not one or more ASCII digits", not "not an
      integer".

    Commit: `fix(field-surrogate): plotfile names match ASCII digits and the whole name`.

## 3. Covering-grid release and teardown (#120, #112 item 3; `snapshot.py`)

3.1 [ ] **Anchor**, committed alone before any `snapshot.py` change:
    `test_read_is_bit_identical_to_a_full_grid_reference`.
    - **The reference helper:**
      - `yt.load`, then the full level-0 `covering_grid`;
      - `to_ndarray()[sl]` with `sl` from `_region_bounds`;
      - an owning read-only copy;
      - axes computed as `dle + (arange + 0.5)·dx`, the same arithmetic as the reader. A `linspace`
        reference differs by an ULP on non-dyadic grids.
    - **Caching.** The reference is cached per (plotfile, fields), and slices are taken from it.
    - **Cases and fields:** `REGION_CASES` + `DIVERGENCE_CASES` × all eight `CANONICAL_FIELDS`.
    - **Plotfiles.** The 6³ fixture, where shapes are also checked against the tables' literal
      counts, and `asym_plotfile`, with coordinates mapped by `_map`. `_map` is imported from
      `scripts/verify_eulerian_box_ab.py` with `spec_from_file_location`.
    - **Properties compared:** every property in the spec scenario.
    - **The `requires_plotfile` variant:**
      - it uses the last `plt*` in `$MOSQUITO_CFD_PLOTFILE_ROOT/t3c-fine` and skips with a reason
        if that is absent;
      - the reference is built once, at module scope;
      - it runs over the spec's named subset.

3.2 [ ] **Anchor**, committed alone: `test_guards_fire_before_the_zero_cell_short_circuit`.
    - The request is `REGION_CASES`' `outside_domain`.
    - It is made against four plotfiles, and each must raise its own guard's error:
      - the `max_level=1` proxy;
      - a proxy whose index lacks `_dtype` (as in `test_missing_private_dtype_attribute_is_a_hard_failure`);
      - the genuine fp32 plotfile;
      - a fixture written without one of the requested fields.
    - It passes today.

3.3 [ ] **Proxy updates**, in the 3.7 commit:
    - `_ProxyDataset.covering_grid` records construction in a **separate** `grid_log`, so the
      existing `log == [...]` assertions (test_field_surrogate_snapshot.py:232, :243, :777) are
      unchanged.
    - `_RecordingGrid` and `_PoisonGrid` (:1182, a class nested inside
      `test_nan_and_inf_field_values_pass_through_bit_identically`) forward `field_data` and `clear_data`, so the NaN
      test does not hit `AttributeError`.

3.4 [ ] **Red:** `test_each_field_leaves_the_covering_grid_cache_once_copied`. The proxy asserts two
    things:
    - inside `__getitem__`, that no earlier field is in `field_data`;
    - inside `clear_data()`, that `field_data` is already empty, and that `clear_data()` is called
      once.

    Fails today on the second field read.

3.5 [ ] **Red:** `test_field_cache_release_bounds_the_peak`, on 96³: peak(6) − peak(1) ≤ 7.5·S.
    Today it measures 9.7–11.0·S.

3.6 [ ] **Red:** `test_dataset_is_dead_when_the_read_returns`, full-extent half.
    - It wraps `yt.load` with `monkeypatch` to record a `weakref.ref` to each real yt `Dataset`,
      never to a `_ProxyDataset`, which dies on return even when the dataset lives.
    - Automatic GC stays enabled.
    - It asserts the reference is dead on return, and that no snapshot attribute is a yt object.
    - Fails today: the dataset is alive.

3.7 [ ] **Implement D4:**
    - pop each field after copying it, and `del raw`;
    - `cg.clear_data()`;
    - read `time` and `max_level`, then `del cg, ds`, then `gc.collect()`, with the rationale
      comment;
    - `import gc`;
    - update the docstring;
    - update the `stress_integral.py:250-255` comment to "copies or freshly allocates".

    Then run 3.1, the oracle, the ownership tests and the full suite.

    Commit: `perf(field-surrogate): release the covering-grid cache and the yt dataset before returning`.

## 4. Zero-cell short-circuit (#112 item 5; `snapshot.py`)

4.1 [ ] **Red:** `test_zero_cell_region_reads_nothing`.
    - Cases: `upper_edge`, `outside_domain`, `above_beyond_reach_h2` and `x_below_yz_inside_h1`. The
      last is empty on one axis only, which kills the `any → all` mutant.
    - It asserts `grid_log == []` and no field read, and that each array matches 3.1's reference.

4.2 [ ] **Red:** `test_zero_cell_read_costs_no_field_sized_memory`, on 96³: peak(6 fields) −
    peak(`fields=()`) < S. Today the gap is at least 6·S.

4.3 [ ] **Anchor**, committed after 3.7 and before 4.4: extend 3.6 with the zero-cell half, the
    dataset is dead after an `outside_domain` read. It already passes after 3.7, because the
    zero-cell request still takes the full read path. Once 4.4 adds the short-circuit, it kills the
    "zero-cell path returns before teardown" mutant.

4.4 [ ] **Implement D5:** the short-circuit after `_region_bounds`, then the shared teardown; update
    the docstring.

    Commit: `perf(field-surrogate): zero-cell regions build no covering grid and read no field`.

## 5. Point cloud (#112 item 5; `snapshot.py`)

5.1 [ ] **Red:** `test_constant_cell_volume_is_a_read_only_broadcast`, per the spec scenario,
    including the zero-cell `(0,)` case. Fails today: strides are `(8,)`.

5.2 [ ] **Red:** `test_point_cloud_peak_is_its_outputs`, at ≤ `1.02 × (coords + values) + 64 KiB`.
    Today it measures 1.44×.

5.3 [ ] **Implement D6:**
    - `del gx, gy, gz`;
    - `cell_volume` as a broadcast over a read-only 0-d array;
    - in the `PointCloud.cell_volume` and `to_point_cloud` docstrings, state that it cannot be made
      writable, is not C-contiguous, has `base` set, and unpickles as a dense writable copy; and
      give the `np.ascontiguousarray` remedy.

    5.1 and 5.2 are one commit: the bound in 5.2 fails with the `del` alone.

    Commit: `perf(field-surrogate): broadcast cell_volume and free the meshgrid in to_point_cloud`.

## 6. DoMINO `grid` documentation (#112 item 2)

6.1 [ ] **Red:** `test_grid_paragraph_states_the_upstream_difference`, in
    `tests/test_field_surrogate_domino_adapter.py`.
    - It extracts the module-docstring paragraph that contains `` `grid` `` and `interp_res`.
    - In that paragraph it asserts `interp_res`, `sdf_grid`, "snapshot's resolution" and `F3`.
    - Fails today: no such paragraph.

6.2 [ ] **Implement D7's paragraph:**
    - cite PhysicsNeMo `8211352` (2026-11-12) and the file names;
    - label which claim each verification date covers (2026-09-21 versus 2026-11-12);
    - update `to_domino_volume`'s `grid` description.

6.3 [ ] Reword `docs/field_surrogate/roadmap.md:165-166` to match D7. The current text says "full
    volume" versus "a small SDF bounding grid". It becomes: the snapshot's own cell centres, versus
    a fixed-resolution `interp_res` grid paired with `sdf_grid`. Keep "arm C's to fix", which is
    F3's arm C, so the roadmap stays consistent with itself.

    Commit (6.1–6.3): `docs(field-surrogate): DoMINO grid is the snapshot's cell centres, not upstream's interp_res grid`.

## 7. Pathlib pass

7.1 [ ] Read `corpus.py`, `snapshot.py` and `domino_adapter.py` and record the result in the PR body:
    - every path is a `Path`;
    - the only `os` use is `os.scandir`;
    - `str(plotfile_path)` remains only where yt or the `source` field needs a string.

    Any other finding lands as its own commit with a test.

## 8. Verification

8.1 [ ] **Mutation-test** each guard and each new test, against the killer listed.

    **Corpus**

    | mutant | killer |
    |---|---|
    | `os.scandir` → `iterdir` + `Path.is_dir` | 1.3 |
    | `entry.is_dir()` → `Path(entry.path).is_dir()` | 1.3 |
    | `is_dir(follow_symlinks=False)` | 1.1, the symlink test (where `os.symlink` is permitted); and `test_listing_follows_symlinks_on_every_os`, a symlink-shaped stub entry, added in 1.4 because the real symlink test skips on Windows without developer mode |
    | `found[step] = entry` or `entry.path` | `test_noncanonical_step_resolves_with_one_listing` |
    | `with` dropped | 1.3 `test_scan_closes_the_listing_on_the_duplicate_raise` (a spy wrapping the real `os.scandir`) |
    | `is_dir()` wrapped in `except OSError: False` | 1.3 (`PermissionError` stub) |
    | `_configs` cache bypassed | 1.1, 1.3 |
    | `[0-9]` → `\d` | 2.1 |
    | `fullmatch` → `match`, with `$` restored | 2.1 (the stub entry) |
    | duplicate check before the `is_dir` filter | the migrated forced-order test |
    | `sorted` dropped from `steps()` | the migrated reverse-numeric test |
    | duplicate message in listing order | the migrated forced-order test |

    **Snapshot**

    | mutant | killer |
    |---|---|
    | pop removed | 3.4, 3.5 |
    | pop keyed by short name (no-op) | 3.4, 3.5 |
    | pop moved after the loop | 3.4, 3.5 |
    | `clear_data()` removed | 3.4 |
    | `gc.collect()` removed | 3.6 |
    | `gc.collect()` → `gc.collect(0)` or `gc.collect(1)` | 3.6 |
    | `gc.collect()` before `del cg, ds` | 3.6 |
    | `del ds` omitted | 3.6 |
    | `del cg` omitted | 3.6 (the covering grid references the dataset) |
    | short-circuit removed | 4.1, 4.2 |
    | condition `any` → `all` | 4.1 (`x_below_yz_inside_h1`) |
    | short-circuit before each of the four guards | 3.2 |
    | zero-cell path returns before teardown | 4.3 |
    | zero-cell arrays writable, or a view | 3.1, 4.1, plus the wrapper's refuse-to-unfreeze path |
    | `time` read after `del ds` | the whole suite |

    **Point cloud**

    | mutant | killer |
    |---|---|
    | `del` removed | 5.2 |
    | `cell_volume` → `np.full` | 5.1, 5.2 |
    | 0-d base writable | 5.1 |

    **Survivors to record honestly:**
    - **`del raw` removed.** About +1·S peak, under the 7.5·S bound. Optionally kill it with a
      proxy-held `weakref` to each earlier buffer's owning ndarray.
    - **`order="F"` on empty arrays.** Equivalent: zero-size strides are `(0,0,0)` in both orders.

    Record the kill table in the PR body. Each test fix for a surviving mutant is its own `test(...)`
    commit.

8.2 [ ] **CI's commands:**
    - `uv sync --frozen --group viz`;
    - `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`;
    - `uv run ruff format --check` on the same paths;
    - `uv run pytest -v -m "not gpu"`.

    Locally, not in CI, also run `openspec validate improve-field-reader-perf-memory --strict`.
    Report the added test time, locally and on CI.

8.3 [ ] **Real multi-FAB verification over Z:**
    - Run `scripts/verify_eulerian_box_ab.py --sphere-root
      Z:/users/eberrigan/mosquito-cfd-benchmarks --wing-root
      Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing`. It must be bit-exact at the expected
      count.
    - Run 3.1's `requires_plotfile` variant with `MOSQUITO_CFD_PLOTFILE_ROOT=Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing`.
    - Repeat 0.2 with the GC-on method on `plt01000`. The dataset must be dead on return, and held
      memory must stay flat across reads.

8.4 [ ] Re-run 0.1 (including the real-corpus `steps()` pass) and 0.3 and build the before/after tables for the PR body, in #140's format:
    environment, file, method, numbers.

8.5 [ ] **`docs/CHANGELOG.md`**, in a last commit of its own. Do not collide with #109 PR3's entries.
    - Under `### Changed`: peak and retention, the full collection per read, the zero-cell
      short-circuit, the `os.scandir` listing and the `cell_volume` broadcast.
    - Under `### Fixed`: #145 and the trailing-newline name.

    Before it, a `docs(openspec)` commit records measurements and the kill table and ticks the boxes.

8.6 [ ] **PR body:**
    - `Closes #120` and `Closes #145`, each on its own line;
    - "advances #112", since item 4 remains;
    - no negated closing keyword;
    - the already-done findings;
    - the measurement tables;
    - the kill table;
    - the 8.3 results;
    - the image-republish note.

    No squash body is drafted: the user merges with GitHub's default. Keep branch commit messages
    clean, since they make up that default body.

8.7 [ ] **After merge**, post a comment on #112 that:
    - lists what this PR closed;
    - says item 4 remains;
    - corrects the post-#140 comment, which said `_configs()` re-parses and the `grid` is
      duplicated, when both were fixed in `1146552`;
    - notes that its "Advances #20" footer names an unrelated closed issue.
