# Tasks: harden-field-reader-pre-f3

## Conventions

- **Red, then green, in one commit.**
  - Write each red test first and run it.
  - Check that it fails for the stated reason, recorded per row where rows differ, and paste the
    failing assertion into the commit body.
  - Commit the test with the change that makes it pass, so ruff and pytest are green after **every**
    commit.
  - Anchors (tests that pass on `main` and pin behaviour about to be protected) go in their own
    commit, before the change.
  - Tick each checkbox in the commit that does the work.
  - Local commits are allowed only after the user approves the proposal. Push only when the user
    asks.
- **Commit messages.**
  - Conventional prefixes, with the exact titles given below.
  - **No closing keyword for any issue, negated or not.** Write "advances #N". The repo's
    default squash body concatenates commit messages.
  - The PR body alone carries `Fixes #151`, `Fixes #144` and `Advances #113`, subject to the
    user's confirmation.
- **Environment.**
  - Work in this worktree (`.claude/worktrees/harden-field-reader`, branch
    `harden-field-reader-pre-f3`), never the shared checkout.
  - Run `uv sync --frozen --group viz`, then
    `unset VIRTUAL_ENV; PYTHONPATH=src uv run pytest … -p no:cacheprovider`.
- **Before every commit:**
  - `ruff check` and `ruff format --check` on exactly
    `src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`;
  - `openspec validate harden-field-reader-pre-f3 --strict`.
- **Tests.**
  - Compare snapshots only with `_assert_snapshot_equivalent`, never `==`: the dataclass `__eq__`
    raises on arrays.
  - Error-message assertions pin a format such as `f"config {cfg!r}"`, the field name or
    `max_level=2`. Never assert a bare substring the path already contains.
  - Exception types are asserted exactly (`type(e) is …`).
- **Mutation testing.**
  - Set `PYTHONDONTWRITEBYTECODE=1`.
  - Restore from bytes saved before mutating, never with `git checkout`.
  - Regenerate the runner's substring edits after any re-indent.
- **Files.** Use `pathlib.Path`, LF endings, and scratchpad scripts written with the Write tool. Never
  use a bare `git stash`.
- **Do not touch:**
  - `stress_integral._require_upstream` (#143);
  - the van Veen files;
  - `.claude/commands/review-openspec.md`;
  - the force-surrogate figures, metrics, README and training;
  - `force_surrogate/sidecar.py` and `metadata_capture.py`;
  - `experiments/`.

## 0. Baselines and the proposal commit

- [ ] 0.1 Run the full suite on `80d653a` in this worktree, once **with** `MOSQUITO_CFD_PLOTFILE_ROOT`
  set to the Z: plotfile root. Record the pass, skip and fail counts.
- [ ] 0.2 **Parity baseline.** Run these tests and record their pass counts:
  - `test_read_is_bit_identical_to_a_full_grid_reference`
  - `test_real_multi_fab_read_is_bit_identical_to_a_full_grid_reference`
  - `test_extract_eulerian_box_matches_the_frozen_pre_refactor_oracle` (halo 0–3)
  - `test_region_divergence_from_legacy_is_pinned`
  - `test_frozen_oracle_is_unmodified`
  - `test_legacy_wrapper_returns_writable_arrays_like_the_oracle`

  Run `scripts/verify_eulerian_box_ab.py` on Z:. 159 cases are expected.
- [ ] 0.3 Commit `docs(openspec): propose harden-field-reader-pre-f3` (the change directory only).

## 1. Snapshot provenance fields and `source` spelling (D3)

Commit: `feat(field-surrogate): FieldSnapshot carries an absolute POSIX source and four optional
provenance fields`. Files: `snapshot.py` and `tests/test_field_surrogate_snapshot.py`.

- [x] 1.1 **Red tests.**
  - With `monkeypatch.chdir(FIXTURE.parent)`, a relative `Path`, a relative `str` and (on Windows) a
    backslash `str` each give `source == FIXTURE.absolute().as_posix()`, with no `"\\"`.
  - With `monkeypatch.chdir(FIXTURE.parent)`, `Path("..") / FIXTURE.parent.name / FIXTURE.name` gives
    a `source` that contains `"/../"` and equals that path's `.absolute().as_posix()`. This kills
    `resolve()` and `os.path.abspath` on every OS.
  - A directory symlink keeps the link's spelling. Skip it on WinError 1314; it first runs in CI.
  - A bare read has `config_id`, `step`, `git_commit` and `docker_image` all `None`.
  - Update `:218` (`Path(snap.source) == FIXTURE`) and `:1421` (`snap.source == str(path)`) to the
    new contract.
  - **Expected red:** `AttributeError` on `config_id`; `source` has backslashes or is relative.
- [x] 1.2 **Green.**
  - Add the four trailing `= None` fields, documented.
  - Set `source=Path(plotfile_path).absolute().as_posix()`.
  - The `source` attribute doc says "absolute POSIX spelling; a per-host locator, not a cross-host
    identity".

## 2. #151: pickle and copy round-trip (D1)

Commit: `fix(field-surrogate): FieldSnapshot pickles and deep-copies, re-frozen and owning on
receipt`. Files: `snapshot.py`, `tests/test_field_surrogate_snapshot.py`, new
`tests/_spawn_workers.py` and new `tests/_torch_workers.py`.

- [x] 2.1 **Red tests.**
  - **Helper `_assert_snapshot_equivalent(original, result)`.** On **`result`**, it asserts, for
    every array (`arrays[*]`, `x`, `y`, `z`, `dx`):
    - `tobytes()` and `strides` equal to the original's;
    - `dtype == float64` and the same `shape`;
    - `flags.writeable is False` and `base is None`.

    It also asserts:
    - `type(arrays) is MappingProxyType` and `list(arrays) == list(field_names)`;
    - `type(time) is float` and `type(max_level) is int`;
    - `type(step) is int` when `step` is not `None`;
    - `field_names`, `source`, `config_id`, `step`, `git_commit` and `docker_image` equal to the
      original's;
    - `to_point_cloud()`'s `coords`, `values` and `cell_volume` equal by `tobytes()` and shape, and
      its `field_names` equal.
  - **Snapshots** with `fields=("w", "u", "density")`:
    - full-extent;
    - sub-box;
    - fully zero-cell;
    - empty on the x axis only;
    - one with all four provenance fields set via `dataclasses.replace`;
    - one built by hand with `time=np.float64(0.5)`, `max_level=np.int64(0)` and
      `step=np.int64(100)`.
  - **Transports:**
    - `pickle` protocols 2 to `HIGHEST_PROTOCOL`;
    - `ForkingPickler.dumps` + `pickle.loads`;
    - `copy.copy`;
    - `copy.deepcopy`.
  - On each result, assigning into `arrays["u"]` raises `ValueError`, and `result.arrays["u"] = …`
    raises `TypeError`.
  - **Expected red, per row:**
    - pickle, `ForkingPickler`, deepcopy: `TypeError: cannot pickle 'mappingproxy' object`;
    - the `copy.copy` rows are **green on main**, which is recorded;
    - the hand-built numpy-scalar row is red on `type(time)` once pickling works. Confirm this by
      temporarily dropping `float()`.
- [x] 2.2 **Red test: spawn worker.**
  - The worker `read_fixture_snapshot(path: str)` is in `tests/_spawn_workers.py` and returns
    `(os.getpid(), read_field_snapshot(path, full extent))`.
  - Run it with
    `ProcessPoolExecutor(1, mp_context=get_context("spawn")).submit(...).result(timeout=180)`,
    passing `str(FIXTURE.absolute())`. Read the committed fixture, never `tmp_path`.
  - Assert the child PID differs from the parent's, and compare the result with
    `_assert_snapshot_equivalent` against a parent read.
  - **Expected red:** `cannot pickle 'mappingproxy'`, carried in the future's exception.
- [x] 2.3 **Red test: DataLoader** (`pytest.importorskip("torch")`).
  - `tests/_torch_workers.py` defines a module-level `SnapshotDataset` (`__len__` 4, `__getitem__`
    reads the fixture) and a module-level `identity(x)`.
  - Parametrize `multiprocessing_context` over `"spawn"` and `"fork"`, skipping fork where
    unavailable. Run each with `num_workers=2` and:
    - `batch_size=None, collate_fn=identity`;
    - `batch_size=None, collate_fn=None` (torch's `default_convert` path).
  - Every item passes `_assert_snapshot_equivalent`.
  - The skip reason says it runs only with torch installed (`uv sync --group train` on Linux, or
    `uv run --with torch`).
  - **Run it once on this host:**
    `unset VIRTUAL_ENV; PYTHONPATH=src uv run --with torch pytest tests/test_field_surrogate_snapshot.py -k dataloader -p no:cacheprovider`.
    Paste the result in the commit body and the PR body. If torch cannot be installed here, say so
    and rely on 2.2, which goes through the same `ForkingPickler` queue.
- [x] 2.4 **Green.**
  - Add `FieldSnapshot.__reduce__`, whose `state` is built from `dataclasses.fields`.
  - Add `_rebuild_field_snapshot`, per D1:
    - a zero-size array becomes `np.empty(shape)`;
    - an array whose `base is not None` is copied;
    - every array then gets `setflags(write=False)`;
    - `float(time)`, `int(max_level)`, and `int(step)` when set;
    - `arrays` becomes a `MappingProxyType` again.
  - Class docstring: snapshots pickle and deep-copy; arrays are re-frozen and owning on receipt; a
    `DataLoader` with `batch_size >= 1` and `default_collate` cannot batch them, so supply a
    `collate_fn`.

## 3. #113: path pre-check (D2)

Commit: `fix(field-surrogate): read_field_snapshot rejects a non-plotfile path before importing yt`.

- [ ] 3.1 **Red tests**, every case with `sys.modules["yt"] = None`.
  - Exact types:
    - nonexistent → `FileNotFoundError`;
    - regular file → `NotADirectoryError`;
    - empty directory → `FileNotFoundError` with `"Header"`;
    - a directory holding a *subdirectory* `Header` → `FileNotFoundError` with `"Header"`.
  - Each message contains `str(path)`.
  - **Ordering control.** On a nonexistent path, each of these raises its own `ValueError`:
    - `fields=("nope",)`;
    - `fields=("u", "u")`;
    - `halo=-1`;
    - `halo=1.5`;
    - `lo` of shape `(2,)`;
    - `lo=(nan, 0, 0)`;
    - `lo > hi`.

    `fields="u"` joins this list in §6.
  - A docstring test: `read_field_snapshot.__doc__`'s `Raises:` names `FileNotFoundError` and
    `NotADirectoryError`.
  - **Expected red:** `ModuleNotFoundError` for every case under the poisoned import. Unpoisoned,
    the nonexistent case is already a yt `FileNotFoundError`, which is why every case is run
    poisoned.
- [ ] 3.2 **Green.**
  - Extract `_validate_request(lo, hi, halo, fields)` from `read_field_snapshot` unchanged.
  - Add `_check_plotfile_dir(path)` after it and before `import yt`.
  - Update the `Raises:` docstring.
- [ ] 3.3 **Regression.** Run `test_stress_integral.py`, `test_wing_lev.py`, `test_flow_video*.py`
  and `test_make_flow_video_cli.py`. They must be green.

## 4. #113: corpus provenance (D4)

Commit: `feat(field-surrogate): FieldCorpus.run_metadata and strict digest-pinned provenance on
corpus snapshots`. Files: new `_provenance.py`, `corpus.py` and `tests/test_field_surrogate_corpus.py`.

- [ ] 4.1 **Red tests: `_provenance`.**
  - **Helper `_write_run_metadata(run_dir, **overrides)`.** It writes the real pod-side key set
    (`run_id`, `timestamp`, `git`, `hardware`, `docker_image`, `config`, `deck`, `deck_sha256`,
    `command`, `ib_particle_csv`, `log`, `rows`, `max_step`, `threshold`, `status`,
    `orchestration`), plus an unknown extra key. It is **opt-in**: `_corpus()` does not write
    metadata by default.
  - Every case in the "Missing or unverifiable provenance" scenario is parametrized, through
    `FieldCorpus.snapshot` with `yt.load` replaced by a tripwire. Each raises exactly
    `ValueError`, and its message starts with exactly
    `f"run_metadata for config {cfg!r} ({path}): {field}: "`. That makes the field-name check
    non-vacuous, since the path contains `run_metadata.json` and the prefix contains `config`. Use
    builtin `repr`, not `plain_repr`.
  - **Positive control:** valid metadata calls `yt.load` and returns the exact `git_commit` and
    `docker_image`, byte for byte, unstripped.
- [ ] 4.2 **Red tests: `run_metadata()`.**
  - It returns `type is dict`, equal to `json.loads`, extra key included.
  - Mutating the top level and `["git"]["commit"]` of one result leaves the next result unaffected.
  - A run directory that exists but holds no `run_metadata.json` raises `ValueError` starting with
    the prefix followed by `run_metadata.json: `.
- [ ] 4.3 **Red tests: corpus snapshot.**
  - `snapshot(cfg, np.int64(100))` carries the four fields (`type(step) is int`), and is equivalent,
    property by property, to `read_field_snapshot(plotfile(cfg, 100))`.
  - **Ordering, with no metadata on disk:**
    - `fields="u"` (after §6; until then `fields=("nope",)`), `lo > hi` and `step=-1` each raise
      their own `ValueError`, with manifest loads and `os.scandir` recorded as zero;
    - an unknown config and a missing step raise their own errors.
  - **Import hygiene.** In a `subprocess` running a fresh interpreter:
    - import `mosquito_cfd.field_surrogate._provenance`;
    - call `read_run_metadata` and `run_provenance` on a valid file;
    - print whether `mosquito_cfd.force_surrogate`, `pandas` or `matplotlib.pyplot` is in
      `sys.modules`. All three must be absent.

    Also parse `_provenance.py` with `ast`:
    - any `ImportFrom` with `level > 0` fails the test;
    - otherwise each `Import` name's, and each `ImportFrom` `module`'s, first dotted component must
      be in `sys.stdlib_module_names` (`__future__` and `typing` are). The corpus's manifest path already imports `force_surrogate`, so no
    hygiene test goes through `FieldCorpus` (design D4 caveat).
  - Existing tests: only `test_field_surrogate_corpus.py:149` (the success path) gains metadata.
    `:180` and `:187` stay metadata-free, since they must raise first.
- [ ] 4.4 **Green.**
  - Add `_provenance.py` (D4).
  - Add `FieldCorpus.run_metadata`.
  - Rewrite `FieldCorpus.snapshot` to the D4 order, using `dataclasses.replace`.
  - Update the `Raises:` docstrings and the module docstring (one sentence on provenance).
- [ ] 4.5 **Real-corpus check (not a CI test).**
  - A scratchpad script uses the committed 27-config manifest against the Z: runs.
  - For each config it calls `run_metadata` and `snapshot(cfg, first_step, lo=hi=domain centre)` (a
    one-cell read).
  - It records `git_commit`, `docker_image` and the wall time.
  - Also replay `experiments/field/probe.py`'s call (`corpus.snapshot(config, step)`, full domain)
    for one config.
  - Paste the output in the commit body.

## 5. Zero-cell anchor and refusal (D5)

- [ ] 5.1 **Anchor commit:** `test(field-surrogate): anchor read_field_snapshot's zero-cell result`.
  - `read_field_snapshot` on a region beyond the domain by more than `halo`, and on a point on the
    upper edge, returns `(0, …)` arrays.
  - This passes on the branch as it stands.
- [ ] 5.2 **Red tests.**
  - `FieldCorpus.snapshot` with valid metadata, on those two requests, raises exactly `ValueError`
    naming `f"config {cfg!r}"`, `step=100`, `lo`, `hi`, `halo` and the per-axis counts.
  - A one-cell request succeeds.
  - `fields=()` over the full extent succeeds.
  - `to_domino_volume`:
    - a zero-cell snapshot raises, naming the counts and `source`;
    - a one-cell snapshot gives `(1, 3)`;
    - a zero-cell snapshot with 2-D global params raises the params error (ordering).
- [ ] 5.3 **Green.** Commit: `fix(field-surrogate): FieldCorpus.snapshot and to_domino_volume
  refuse zero-cell snapshots`.
  - Add the two guards.
  - Update both `Raises:` docstrings.

## 6. Smaller items (D6)

Commit: `fix(field-surrogate): reject bare-string fields and non-1-D global params; caller-neutral
AMR message`.

- [ ] 6.1 **Red tests.**
  - `fields` values `"gradpx"`, `"uvw"`, `"u"` and `b"u"` each raise `ValueError`, including on a
    nonexistent path:
    - the message names the value and suggests `('gradpx',)`;
    - `fields=("gradpx",)` and `fields=["u", "v"]` read normally (positive control).
  - Add `fields="u"` to §3's ordering list and to §4.3's.
  - Global params:
    - each of 2-D against 2-D, `()`, a 0-d scalar, and 1-D against `(3, 1)` raises, naming the
      argument and its shape;
    - with a sentinel snapshot whose attribute access raises, bad params raise the params error
      first.
  - AMR refusal (the existing `max_level` proxy):
    - `match=r"max_level=2"` and `"CC-F3"`;
    - `"read_field_snapshot requires"` is absent;
    - tighten the existing `"2" in str(exc)` assertion at `test_field_surrogate_snapshot.py:740`.
- [ ] 6.2 **Green.** Implement D6, including the `yt.set_log_level` comment. Update
  `to_domino_volume`'s and `read_field_snapshot`'s `Raises:`.

## 7. #144: flow_video frame discovery (D7)

Commit: `fix(visualization): flow_video discovers frames with the corpus's scan_plotfiles`. Files:
`corpus.py`, `flow_video.py`, `scripts/make_flow_video.py`, `tests/test_flow_video.py` and
`tests/test_flow_video_plotfile.py`.

- [ ] 7.1 **Red tests** in `tests/test_flow_video.py`.
  - `plt99999`, `plt100000`, `plt00100`, a file `plt00200`, a directory `plt00300.old` and a
    directory `plt١٠٠` give `[plt00100, plt99999, plt100000]`.
  - `flow_video.scan_plotfiles is corpus.scan_plotfiles`.
  - Duplicates `plt100`/`plt00100` raise naming both.
  - A nonexistent path, a regular file and an empty directory each raise exactly `ValueError` naming
    the path. The empty-directory message names `plt<digits>`.
  - **Expected red:** `plt100000` missing; the file `plt00200` included; `AttributeError` on
    `scan_plotfiles`.
- [ ] 7.2 **Green.**
  - Rename `_scan` to `scan_plotfiles` at its three references (`corpus.py:74`, `:219` and `:270`),
    with a public docstring. Do not export it from `field_surrogate/__init__.py`.
  - Rewrite `_plotfile_frames` per D7.
  - Update the `build_flow_video` docstring (`flow_video.py:463`, `:500`) and the
    `make_flow_video.py:68` help to `plt<digits>`.
  - Replace the `plt?????` glob at `tests/test_flow_video_plotfile.py:123` with `scan_plotfiles`.
  - Check that the `_plotfile_io_tripwire` tests and the `match="fps"` concern
    (`test_flow_video.py:877`) still hold.

## 8. Parity, full suite, mutation record

- [ ] 8.1 Re-run the 0.2 set and `scripts/verify_eulerian_box_ab.py` on Z:. The counts must equal
  the baseline, and the A/B total must be 159.
- [ ] 8.2 Run the full suite with `MOSQUITO_CFD_PLOTFILE_ROOT` set, so the edited
  `test_flow_video_plotfile.py` runs. It must be green, apart from 0.1's pre-existing items,
  unchanged.
- [ ] 8.3 **Mutation runner.** Use a scratchpad runner with saved-bytes restore and
  `PYTHONDONTWRITEBYTECODE=1`. Each mutant must be killed:

  | Area | Mutants |
  |---|---|
  | §1 | `resolve()` for `absolute()`; `os.path.abspath`; `str()` without `as_posix` (Windows-only kill, recorded) |
  | §2 | drop `setflags`; drop copy-if-`base` (red at every protocol); drop the zero-size `np.empty` (zero-cell strides red); normalize only `arrays`, not `x/y/z/dx`; a hard-coded field list without the four provenance fields; drop `float(time)`; drop `int(max_level)`; drop `int(step)`; plain `dict` for `arrays` |
  | §3 | no `Header` check; `exists()` for `is_dir()`; `exists()` for `Header.is_file()`; path check after `import yt`; path check before the argument checks; path check between the halo and corner checks |
  | §4 | skip the `config` check; `match` (not `fullmatch`) for either regex; drop each `isinstance`; validate after the read; fall back to `None` on a missing file; cache `run_metadata`'s dict; shallow-copy a cached dict; `run_metadata` before `plotfile`; drop `_validate_request` from `snapshot`; drop `int(step)`; import `force_surrogate` (or pandas) in `_provenance.py`; loosen the repository part back to `[^\s@]+` (killed by `:@sha256:<64>` and `GHCR.io/x@sha256:<64>`; `sha256:abc@sha256:<64>` is accepted by both patterns and does not kill it); `match` instead of `fullmatch` for the image (killed by the trailing-newline and trailing-space references) and for the commit (killed by the trailing-newline commit) |
  | §5 | remove each guard; test `values.size` instead of the axes (killed by `fields=()`); zero-cell check before the params check |
  | §6 | allow `bytes`; drop `ndim`; drop `size` |
  | §7 | sort by name; revert to a glob; reintroduce `plt?????`; drop the is-dir pre-check |

  Tabulate mutant → killing test → result in the PR body. For any survivor, add a test, or record why
  it is equivalent.

## 9. Docs and close-out

- [ ] 9.1 `openspec/project.md` §"Field Surrogate Reader (Stage 2)": add to its conventions list that
  snapshots pickle, that `FieldCorpus.snapshot` requires a valid `run_metadata.json` and carries
  `(config_id, step)` plus the digest, and that `source` is a per-host locator. Commit
  `docs(field-surrogate): project.md conventions for snapshot provenance and pickling`.
- [ ] 9.2 `docs/CHANGELOG.md`, the **last** commit before the PR, written after `git merge
  origin/main` (no rebase). Following #140's precedent:
  - under `### Fixed`, one bullet each for #151 and #144, plus the #113 hardening with the
    `**BREAKING:**` sub-bullets from proposal.md, ending `(#151)`, `(#144)`, `(advances #113)`;
  - under `### Added`, `FieldCorpus.run_metadata`, `scan_plotfiles` and the four snapshot fields.

  Put each entry at the top of its subsection. Commit `docs: CHANGELOG entries for
  harden-field-reader-pre-f3`.
- [ ] 9.3 Comment on #113 with the status table from proposal.md ("advances #113").
- [x] 9.4 Filed as #159 (validators) and #160 (manifest import), with the user's approval
  (2026-11-17). Original task text: File a follow-up issue: `force_surrogate.sidecar.validate_image_digest` uses `search`, and
  `metadata_capture._FULL_SHA_RE` uses `$`, so both are looser than `_provenance`'s full matches.
  Record the measured accepting inputs, and propose consolidating onto `_provenance`. File a second
  follow-up issue: `FieldCorpus._configs()` imports `force_surrogate.dataset`, so the first manifest
  read loads pandas and pyarrow, switches the matplotlib backend to `Agg`, and costs about 4.6 s per
  spawned worker. It proposes moving `load_manifest_configs` to a light module. Ask the user before
  filing either issue.
- [ ] 9.5 **After merge, with the user's go-ahead,** run `/cleanup-merged` in this worktree.
  `docs/field_surrogate/roadmap.md`'s F3 dependency line (`:285`) gains: "F2 snapshots are
  DataLoader-safe (picklable) and carry `(config_id, step)` + the run digest
  (harden-field-reader-pre-f3)". Commit it with the archive.
