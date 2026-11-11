# Tasks: harden-field-corpus-requests

## Conventions

- **Red, then green, in one commit.** Write each red test first, run it, and check that it fails for
  the reason stated in the task. Then commit it **together with** the guard that makes it pass, one
  commit per guard, so CI is green at every commit. Record the red-run evidence as text in the commit
  body.
- **Anchor tests** are tests that pass today. They pin existing behaviour, and the task says so. They
  can be committed on their own.
- **Message assertions** match the guard's own text, never a string that could also appear in a path.
  `tmp_path` contains the test name, so a substring such as `"fps"` or `"plt100"` can match the path
  instead of the error.
- **Spies** are installed only after `FieldCorpus(root)` and the fixture copy are built. Each spy
  test also has a positive control: the same spy must record at least one call on a path that really
  does I/O, so a spy that silently never fires doesn't pass the test by default.
- **Environment:** run `uv sync --frozen --group viz` before the full suite. Without the viz group,
  `test_flow_video.py` errors.
- **Mutation testing:** every guard is mutation-tested (section 6). Restore the file from saved bytes,
  never with `git checkout`.

## 1. #122: reject inverted region requests (`snapshot.py`, `stress_integral.py`)

1.1 [x] Caller audit. Re-grep the `read_field_snapshot` and `extract_eulerian_box` callers and check
    them against the design D1 table. Record the result in the PR body.

1.2 [x] **Anchor** (commit separately, before 1.3). `test_zero_width_request_is_not_inverted`
    (snapshot tests): `lo == hi` at an interior point gives `(1,1,1)`, at the upper edge `(0,0,0)`,
    at `(+inf,)*3` `(0,0,0)`, and at `(-inf,)*3` `(0,0,0)`. This kills a `>` → `>=` mutant.

1.3 [x] **Red tests**, in `tests/test_field_surrogate_snapshot.py`:
    - (a) `test_inverted_request_is_rejected`, parametrized over the seven requests in the spec
      scenario, including `(2.6→2.4, halo 0)` and `(4→3, halo 2)`, which have non-empty padded
      ranges. It asserts
      `match=r"inverted region request \(lo > hi\): axis x: lo=4\.0 > hi=2\.0"` (or the
      per-case equivalent). For the y-only case it also asserts that `"axis x"` and `"axis z"` are
      absent. This fails today: the reader returns cells.
    - (b) the same inverted request against a non-existent plotfile path raises the same message.
      This fails today with a yt/OS error.
    - (c) with `monkeypatch.setitem(sys.modules, "yt", None)`, the inverted request raises the
      inversion `ValueError`, not `ImportError`. This fails today with `ImportError`.
    - (d) add `("inverted", {"lo": (4.0,)*3, "hi": (2.0,)*3}, r"inverted region request")` to
      `NARROWED_REQUESTS`. `test_wrapper_argument_narrowing_is_pinned` then checks that the frozen
      copy accepts it and the wrapper raises. The wrapper half fails today.

1.4 [x] In the same commit as 1.3:
    - Remove `inverted` and `inverted_halo1` from `REGION_CASES`. No count literal depends on its
      length; the script uses `len()` at run time.
    - Rewrite the comment above `REGION_CASES` (lines 282–289). The oracle test and
      `verify_eulerian_box_ab.py` both iterate it. Inverted requests are rejected
      (`harden-field-corpus-requests` D1) and tested separately.
    - Fix the comment at line 510 to state the parity region including `lo <= hi`.

1.5 [x] **Implement** in the same commit: `_check_not_inverted(lo_v, hi_v)` in `read_field_snapshot`,
    called right after the two `_corner` calls and before `import yt`. The message format is
    `inverted region request (lo > hi): axis y: lo=4.0 > hi=2.0`; when several axes are inverted they
    are joined with `"; "`, and values go through `float()`. Leave `_region_bounds` unchanged.
    Rewrite its floor comment at line 183: through the public reader, the floor now serves only
    `lo == hi` (for example, a point on a cell face), while the parity sweep still feeds it inverted
    triples. Without that explanation the floor looks removable.

1.6 [x] **Docstrings and docs**, in the same commit:
    - `read_field_snapshot`:
      - add `lo <= hi` to the parity condition;
      - drop "for a non-inverted request";
      - add the inverted case to `Raises:`.
    - `extract_eulerian_box`:
      - in the body paragraph, add `lo <= hi` to the parity condition;
      - say an inverted request now raises where the pre-refactor function returned a region;
      - in `Raises:`, add "if `lo > hi` on any axis" before "The pre-refactor function raised only
        for the last two", so that sentence stays true.
    - `check_field_capture_velocity`: add the inverted case to `Raises:`.
    - `openspec/project.md:364`: append "and its `lo > hi` rejection (`harden-field-corpus-requests`
      D1)".

1.7 [x] **`sphere_cv_steadiness_fraction` guard** (separate commit, red then green):
    - Red: a test in `tests/test_stress_integral.py` with `x_inlet > x_outlet` (and
      `x_inlet == x_outlet`, which kills `>=` → `>`) and
      `extract_eulerian_box` monkeypatched to fail the test if called. It asserts
      `match=r"x_inlet .* must be strictly upstream of x_outlet"`. This fails today: the box read
      runs first.
    - Green: copy `sphere_cv_drag_cd`'s guard to the top of the function and add it to `Raises:`.

## 2. #122: `build_flow_video` validates `box_margin` (`flow_video.py`)

2.1 [x] **Fix the template test first** (its own commit). Change `test_rejects_non_positive_fps` to
    assert `match=r"fps must be positive, got 0"` and to monkeypatch `flow_video._plotfile_frames`
    with a function that raises `AssertionError("plotfile I/O before fps check")`. Then show that the
    test now fails with the fps guard deleted. It passes as written today even with the guard gone,
    because the `tmp_path` in the I/O error message contains "fps".

2.2 [x] **Red**: `test_rejects_invalid_box_margin`, parametrized over `box_margin ∈ {-1.0, 0, 0.0,
    nan, inf, -inf, np.float64(-1.0), True, "3"}` × all four `FIELD_MODES`. It:
    - asserts `match=r"box_margin must be a finite number > 0, got"`;
    - asserts the value's text appears in the message;
    - uses the same `_plotfile_frames` tripwire as 2.1;
    - asserts `plt.get_fignums()` is unchanged.

    It fails today: every case reaches the tripwire.

2.3 [x] **Implement** in the same commit as 2.2:
    - Add `_validate_box_margin` right after the `fps` check. It accepts `int`/`float`/`np.integer`/
      `np.floating`, rejects `bool`, requires `math.isfinite(x) and x > 0`, and raises `ValueError`
      for everything else.
    - Update the `build_flow_video` docstring: `box_margin` is "used by lev-3d; validated in every
      mode", and `Raises:` gains the new case.
    - Update the `scripts/make_flow_video.py` `--box-margin` help text to match.

## 3. #121: `step` validation (`corpus.py`)

3.1 [x] **Anchor**: `np.int64(100)`, `np.int32(100)` and `0` resolve `plt00100` and `plt00000`. This
    passes today.

3.2 [x] **Red**: `test_invalid_step_is_rejected_before_any_io`, parametrized over `step ∈ {"100",
    100.0, True, np.bool_(True), -1, None}` × `{plotfile, snapshot}`.
    - Build a fresh `FieldCorpus` for each parameter.
    - Only after construction, install spies on
      `mosquito_cfd.force_surrogate.dataset.load_manifest_configs` and on `Path.is_dir` and
      `Path.iterdir`. The first is observed because `_configs` imports it lazily.
    - Assert `ValueError` with `match=r"step must be a non-negative integer, got "` plus
      `re.escape(repr(step))`, and that every spy recorded zero calls.
    - Positive control: the same spies on a fresh instance record ≥ 1 call for `plotfile(c, 100)`.
    - The spies cover the `Path` API only, and the test says so.

    It fails today: `"100"` gives the "no plotfile" message, `100.0` resolves, and `-1` scans.

3.3 [x] **Implement** in the same commit: `_validate_step(step) -> int`, called first in `plotfile()`.
    Update the `plotfile()`/`snapshot()` docstrings: the `step` argument is "non-negative integer
    timestep", and `Raises:` lists a bad `step`, an unknown config or missing run directory, and
    duplicates; `snapshot()` also lists "anything `read_field_snapshot` raises (including `lo > hi`)".

## 4. #121: one shared scan with duplicate detection (`corpus.py`)

4.1 [x] Audit: confirm that no committed fixture or test builds a run directory with two names for
    the same step. (`test_missing_step_message_does_not_claim_a_fixed_digit_width` renames a
    directory; it does not copy one.) Record the grep in the PR body.

4.2 [x] **Red**: `test_duplicate_step_directories_raise`. Directories `plt100`, `plt00100` and
    `plt200`; `Path.iterdir` is patched to list `plt100` first. Assert that both `steps()` and
    `plotfile(c, 200)` raise with `match=r"two plotfile directories parse to step 100: plt00100,
    plt100"`. Fails today: `[100, 100, 200]`, and `plotfile` returns `plt200`.

4.3 [x] **Red**: `test_non_directory_entries_never_duplicate`. A regular file `plt100` beside a
    directory `plt00100`: `steps()` returns `[100]`. A regular file `plt00100` beside a directory
    `plt100`: `steps()` returns `[100]` and `plotfile(c, 100)` returns `plt100`. This half is an
    anchor today; it kills a duplicate check placed before the `is_dir` filter **only if the
    directory lists before the file**, so the listing order is forced (design.md, Implementation
    notes). Implemented as `test_non_directory_entries_never_duplicate_or_resolve`.

4.4 [x] **Red**: `test_missing_step_lists_the_run_directory_once`, with an `iterdir` spy and a missing
    step. Assert exactly 1 listing (today: 2) and the literal `available steps: [7]`.
    **Anchor**: a step present only as `plt7` resolves with exactly 1 listing (today: 1).

4.5 [x] **Implement** in the same commit:
    - `_scan(run) -> dict[int, Path]`: regex, then `is_dir()`, then the duplicate check, with sorted
      basenames in the message.
    - `steps()` returns `sorted(_scan(...))`.
    - The `plotfile()` fallback uses `_scan`, and its miss message uses the same result.
    - Add a `Raises:` section to `steps()`.

## 5. #121: canonical fast path (`corpus.py`)

5.1 [x] **Red**: `test_canonical_plotfile_resolves_without_listing`. Directories `plt00100` and
    `plt100000`, with an `iterdir` spy. `plotfile(c, 100)` and `plotfile(c, 100000)` each return the
    canonical path with zero listings. Fails today: one listing each.

5.2 [x] **Anchor**: an unknown config with `runs/ghost/plt00100` present on disk still raises the
    manifest error. Passes today; kills a mutant that puts `_config` after the fast path.

5.3 [x] **Red**: `test_fast_path_does_not_see_a_noncanonical_twin`. With directories `plt100` and
    `plt00100`, `plotfile(c, 100)` returns `plt00100`, and `steps(c)` raises. This fails after
    section 4 and before 5.4, because the scan raises; it is the D2 trade-off pinned.

5.4 [x] **Implement** in the same commit:
    - `plotfile()`: validate the step, then `_config`, then `is_dir()` on the canonical path and return
      it if that is True; otherwise `run_dir` plus `_scan`.
    - Update the module and class docstrings. Today they say `steps()`/`plotfile()` "list `plt*`
      directories live on every call"; that becomes "`steps()` lists on every call; `plotfile()`
      stats the canonical name first and lists only on a miss".
    - The `plotfile()` docstring states the D2 blind spot.

## 6. Verification

6.1 [x] **Mutation-test** every guard, restoring from saved bytes. Each mutant is listed with the
    test(s) that must kill it:

    **Inverted-request check**
    - `>` → `>=`: 1.2
    - check on padded indices instead of raw corners: 1.3a (the 2.6/2.4 and 4/3 halo-2 cases)
    - check removed: 1.3a, 1.3d
    - check moved after `yt.load`: 1.3b
    - check moved between `import yt` and `yt.load`: 1.3c
    - every axis reported instead of only the inverted ones: 1.3a (y-only case)

    **Steadiness guard**
    - guard removed: 1.7

    **Tests for the guards themselves**
    - fps guard removed: 2.1

    **`box_margin` validation**
    - `<= 0` → `< 0`: 2.2 (the `0` and `0.0` cases)
    - finiteness check dropped: 2.2 (`inf`)
    - `bool` exclusion dropped: 2.2 (`True`)
    - checked only in `lev-3d`: 2.2 (the other three modes)
    - checked after `_plotfile_frames`: 2.2 (the tripwire)

    **`step` validation**
    - `bool` exclusion dropped: 3.2 (`True`)
    - `>= 0` dropped: 3.2 (`-1`)
    - `< 0` → `<= 0`: 3.1 (`0`)
    - `np.integer` dropped: 3.1 (`np.int64`)
    - validation after `_config`: 3.2 (manifest spy)

    **Duplicates and scan**
    - duplicate raise removed: 4.2
    - duplicates detected only in `steps()`: 4.2 (`plotfile(c, 200)`)
    - `sorted` dropped from the message: 4.2
    - duplicate check before the `is_dir` filter: 4.3 (with the forced listing order)
    - `is_dir` filter dropped: 4.3
    - miss path still calls `steps()`: 4.4

    **Fast path**
    - fast path removed: 5.1
    - `is_dir` → `exists`: 4.3 (regular file `plt00100`)
    - canonical path returned without the `is_dir` check: 4.3, 4.4
    - `_config` after the fast path: 5.2
    - `:05d` → `:d`: 5.1 (step 100)

    Record the kill table in the PR body. A surviving mutant means a test fix in its own `test(...)`
    commit.

6.2 [x] Run CI's exact commands:
    - `uv sync --frozen --group viz`
    - `uv run ruff check src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`
    - the same paths with `uv run ruff format --check`
    - `uv run pytest -v -m "not gpu"`

    Do not use `/run-ci-locally`, which lints only `src/` (#96). Run the full suite before every
    commit. Finally, run `openspec validate harden-field-corpus-requests --strict`.

6.3 [x] Don't re-run `scripts/verify_eulerian_box_ab.py` on real plotfiles. The only change it can see
    is that two `REGION_CASES` entries are gone, and the rejection happens before `yt.load`. Say this
    in the PR body instead of claiming a real-plotfile run.

6.4 [x] `docs/CHANGELOG.md`, as the last commit on its own. #136 inserts at the top of `### Changed`,
    and these edits stay clear of that hunk:
    - **New entry** at the top of `### Fixed`: inverted requests, a bad `step`, duplicate steps and an
      invalid `box_margin` now raise; the steadiness guard; the canonical fast path.
    - **Amend line 14** (`### Added`, F2 reader): its parity claim gains "and `lo <= hi`".
    - **Amend line 40** (`### Changed`, #106 delegation): its "deliberate narrowings" list gains
      inverted requests `(#106, #122)`.

6.5 [x] PR body (#140):
    - `Closes #121` and `Closes #122`, each on its own line;
    - "#112 owns the remaining NFS listing cost", written exactly that way and never as "does not
      close" (a negated closing keyword still auto-closes);
    - the audits (1.1, 4.1);
    - the red-run evidence;
    - the kill table;
    - the 6.3 note;
    - the published-image note.

    Post the hand-written squash message as a PR comment.

## 7. Pre-PR review round (`/review-pr`, branch mode; no blocking findings)

7.1 [x] **Red then green:** `box_margin` given `10**400` or `-(10**400)` is a `ValueError`, not a
    `TypeError` (8 cases).
7.2 [x] **Red then green:** a numpy `step` is shown as its plain value in the message
    (`np.int64(-1)` → `got -1`).
7.3 [x] **Red then green:** a NaN `x_inlet`/`x_outlet` is rejected by
    `sphere_cv_steadiness_fraction` and `sphere_cv_drag_cd` themselves, via `not (x_inlet < x_outlet)`.
7.4 [x] Test gaps: `plotfile()` is checked on the first non-directory layout; the before-`yt.load`
    and before-`import yt` tests run over all of `INVERTED_REQUESTS`.
7.5 [x] The CHANGELOG entry is marked **BREAKING**. "Both narrowings" becomes "Each narrowing".
7.6 [x] Mutants 4/4 killed: try/except narrowed, numpy unwrap removed, and each NaN guard reverted
    to `>=`. design.md records the review round, the deliberate non-changes, and the follow-ups.

## 8. PR review round (`/review-pr` on #140; no blocking findings)

8.1 [x] **Spec first:** the `visualization-tooling` delta gains the valid-margin scenario and the
    `numbers.Real` rule; a `force-extraction` delta adds the inlet-upstream scenario; D3 and the
    proposal are updated. `openspec validate --strict` passes.
8.2 [x] **Anchors, then red then green (`box_margin`):** `1e-9`, `0.5`, `2`, `np.int64(2)` and
    `np.float32(0.5)` reach the plotfile tripwire in every mode (anchors: they pass today).
    `Fraction(1, 2)` reaching it, `Decimal("3")` and `np.bool_(True)` being rejected, and the new
    message are red first. Implementation: `numbers.Real` plus `float()`, returning the `float`.
    Re-run the four surviving mutants (`np.integer`/`np.floating` dropped, `> 1e-3`, `>= 1`); all
    must be killed.
8.3 [x] **Red then green (`halo` message):** `halo=np.float64(1.9)` is reported as `got 1.9`. Add
    `mosquito_cfd._messages.plain_repr` and use it for `step`, `halo` and `box_margin`; correct the
    three comments that claimed `_validate_halo` already did this.
8.4 [ ] **Refactor under green tests:** one `_require_upstream(x_inlet, x_outlet)` used by both
    `sphere_cv_*` functions; both `Raises:` docstrings say "not strictly less than (NaN included)".
    The NaN drag cases match the guard's own message and use the reader tripwire, like the
    steadiness test. Mutant: the helper reverted to `>=` must be killed in both functions.
8.5 [ ] CHANGELOG `box_margin` wording matches D3. Full CPU suite, ruff on CI's paths, and
    `openspec validate --strict` pass. Push; post a reply on #140 mapping each finding to its fix.
8.6 [ ] File follow-up issues: infinite inlet/outlet planes accepted; `flow_video`'s `plt?????`
    glob skips steps of 100000 or more; `_PLT_PATTERN`'s `\d` matches non-ASCII digits.
