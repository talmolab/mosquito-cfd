# Tasks: share-light-corpus-helpers

## Conventions

These are the user's standing rules for this change. They are restated so that the implementer has
them in one place.

- **Red, then green, in one commit.**
  - Write each red test first and run it.
  - Confirm that it fails **for the stated reason**, and paste the failing assertion into the commit
    body.
  - Commit the test with the change that makes it pass, so ruff and pytest are green after **every**
    commit.
  - Anchors (tests that pass at the current HEAD and pin behavior about to be preserved) go in their
    own commit, before the change.
  - Tick each checkbox in the commit that does the work.
  - Local commits are allowed only after the user approves. Push only when the user asks.
- **Commit messages.**
  - Use the titles below.
  - **No closing keyword, negated or not.** Write "advances #160" / "advances #159", and never paste
    a pytest output line containing `Fixes #N`.
  - The PR body alone carries `Fixes #160` and `Fixes #159`, and only if each is fully resolved.
  - Trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Environment.**
  - Work in `.claude/worktrees/shared-light-corpus-helpers` (branch `shared-light-corpus-helpers`,
    base `c87e39c`).
  - Run `unset VIRTUAL_ENV; PYTHONPATH=src uv run pytest … -p no:cacheprovider`.
- **Before every commit:**
  - `uv run ruff check` and `uv run ruff format --check` on exactly
    `src/ tests/ scripts/ examples/prelim_sweep/ examples/prelim_sweep_fine_pilot/ examples/prelim_sweep_fine/`.
    Check exit codes with `>/dev/null && echo OK`, never through `| tail`.
  - `openspec validate share-light-corpus-helpers --strict`.
- **Tests.**
  - Assert exception types exactly (`type(e) is ValueError`). `pytest.raises` accepts subclasses, and
    `UnicodeDecodeError` is a `ValueError`.
  - Pin message formats, never a bare substring that the path already contains. Build expected paths
    from the same `Path` object with `f"{path}"`, never `.resolve()` and never a forward-slash string
    (on Windows, `tmp_path` uses 8.3 short names).
  - Write expected key lists out as literals, not imported from the module under test.
- **Mutation testing.**
  - Use a throwaway worktree at the **final code SHA**, with `PYTHONDONTWRITEBYTECODE=1`.
  - Restore from saved bytes, never with `git checkout`.
  - Never run it alongside another test run.
- **Files.** Use `pathlib.Path` and LF endings. Write scratchpad scripts with the Write tool. Never
  use a bare `git stash`.
- **Do not touch:**
  - `force_surrogate/__init__.py`, `force_surrogate/train.py`, `evidence_figure.py`;
  - `tests/test_committed_surrogate_provenance.py`;
  - `docs/field_surrogate/roadmap.md`;
  - `experiments/`;
  - any other worktree, or the shared checkout.

  Task 6.4 verifies this.

## 0. Baselines and the proposal commit

- [ ] 0.1 Run the full suite at `c87e39c` in this worktree, and record the pass, skip and fail counts.
- [x] 0.2 The #160 baseline (design E1) is already recorded. It will be re-run in 2.4.
- [x] 0.3 Commit `openspec/changes/share-light-corpus-helpers/**` with this checkbox and 0.2 ticked:
  `docs(openspec): propose share-light-corpus-helpers (advances #160, #159)`.

## 1. Move `_provenance` to the top level, then add the predicates

- [ ] 1.1 **Pure move (no behavior change).**
  - `git mv src/mosquito_cfd/field_surrogate/_provenance.py src/mosquito_cfd/_provenance.py` with the
    content untouched.
  - Change `corpus.py:32`'s import path.
  - Move `test_reading_provenance_loads_no_force_surrogate_stack` and
    `test_provenance_module_imports_only_the_standard_library`
    (`tests/test_field_surrogate_corpus.py:1050–1095`) into the new `tests/test_light_corpus_helpers.py`,
    changing only their paths.
  - Add `test_provenance_lives_at_the_top_level`: `mosquito_cfd._provenance` imports, and
    `importlib.util.find_spec("mosquito_cfd.field_surrogate._provenance") is None`.
    Expected red before the `git mv`: `ModuleNotFoundError`.
  - Verify with `git show -M --name-status HEAD` that the commit shows
    `R100	src/mosquito_cfd/field_surrogate/_provenance.py	src/mosquito_cfd/_provenance.py`.
  - The new test file imports the helpers it needs (`_corpus`, `_write_run_metadata`, `_CFG`) from
    `test_field_surrogate_corpus`. That works because `pyproject.toml:106` sets
    `pythonpath = ["tests"]`.
  - Commit: `refactor(provenance): move field_surrogate/_provenance.py to mosquito_cfd/ (advances #159)`.
- [ ] 1.2 **Red.** In `tests/test_light_corpus_helpers.py`:
  - `test_is_full_commit_sha_table` and `test_is_pinned_image_ref_table` cover exactly the value
    lists in the field-surrogate scenario "The shared predicates accept exactly the strict forms and
    never raise". That includes `"g"*40`, `"@sha256:"+…`, the uppercase repository and digest, the
    space in the repository, and `"ghcr.io/x:latest #@sha256:"+…`.
  - Each `False` case also asserts that the call does not raise.
  - Expected red: `AttributeError`, because the module has no `is_full_commit_sha`.
  - Upgrade the two tests moved in 1.1 to design D7:
    - the provenance subprocess becomes child (c), with inherited `env`, `cwd=REPO_ROOT`, the
      `mosquito_cfd.__file__` check, and the forbidden set `{mosquito_cfd.force_surrogate,
      mosquito_cfd.field_surrogate, mosquito_cfd.benchmarks, pandas, pyarrow, matplotlib.pyplot}`;
    - the AST test refuses relative imports and `importlib.import_module` / `__import__` calls.

    Expected red: none on the code. These are stricter anchors of an already-clean module, so record
    them as anchors. Their discriminating power is shown in §5 (S6 mutants).
- [ ] 1.3 **Green.**
  - Add `is_full_commit_sha` and `is_pinned_image_ref` (design D2), and use them in `run_provenance`.
  - Rewrite the module docstring for the new location and role:
    - shared by `field_surrogate`, `force_surrogate` and `benchmarks`;
    - drop the "deliberately not reused (#159)" paragraph and the description of the force side as
      loose;
    - update the `_IMAGE_RE` comment to name the predicate.
  - The existing provenance corpus tests (`tests/test_field_surrogate_corpus.py:900–1060`) pass
    unchanged.
  - Commit: `feat(provenance): total is_full_commit_sha and is_pinned_image_ref predicates (advances #159)`.

## 2. `_manifest`: pin, extract and re-export, then switch `FieldCorpus`

- [ ] 2.1 **Anchor (green at HEAD, own commit).** Add `test_manifest_reader_messages_are_pinned`,
  which imports `load_manifest_configs` from `mosquito_cfd.force_surrogate.dataset`. It covers
  object-top-level manifests with:
  - no `configs`;
  - `configs` = `{}`;
  - `configs` = `[5]`;
  - a config missing `reynolds`;
  - a duplicate name;
  - and a file holding `{`.

  Each case asserts `type(e) is ValueError` and the **literal** full message as the current reader
  produces it. A missing path asserts `FileNotFoundError`.

  Also add `test_build_dataset_still_sees_a_patched_dataset_reader` to
  `tests/test_force_surrogate_dataset.py`. It does
  `monkeypatch.setattr(dataset, "load_manifest_configs", spy)`, then runs `build_dataset(...)` on the
  `tests/fixtures/synthetic_ib_particle.csv` setup (`_write_manifest` and `FIXTURE`), and asserts that
  `spy` is called once. It is green at HEAD.

  Commit: `test(manifest): pin load_manifest_configs messages before the move (advances #160)`.
- [ ] 2.2 **Red, written against `force_surrogate.dataset.load_manifest_configs`** (so the red shows
  the real defect, not `ModuleNotFoundError`). Expected red is recorded per test.
  - `test_non_object_manifest_top_level_is_a_value_error`: top level `5`, `"configs"` and `null`
    each give `type(e) is ValueError`, naming the path and the type.
    - Red: `TypeError` for `5`, `"configs"` and `null`; the old "has no 'configs' key" message
      for `[]`.
  - `test_unparseable_manifest_is_a_value_error`:
    - 100000-level nesting and a 5000-digit integer each give a message starting
      `sweep manifest <path> is not valid JSON: `;
    - non-UTF-8 bytes (`b"\xff\xfe{"`) give a message starting
      `sweep manifest <path> is not valid UTF-8: `;
    - all three with `type(e) is ValueError`.
    - Red: `RecursionError`; the unprefixed `Exceeds the limit` message; `UnicodeDecodeError`.
  - `test_manifest_reexport_is_the_same_object`: `_manifest.load_manifest_configs is
    dataset.load_manifest_configs is mosquito_cfd.force_surrogate.load_manifest_configs`, and `is` for
    `_REQUIRED_CONFIG_KEYS` and `_validate_configs`.
    - Red: `ModuleNotFoundError`. That is the right reason here.
  - `test_manifest_module_imports_only_the_standard_library` (AST, design D7).
    - Red: file not found.
  - `test_manifest_alone_loads_nothing_heavy`: subprocess child (b) from design D7.
    - Red: `ModuleNotFoundError` in the child.
- [ ] 2.3 **Green.**
  - Create `src/mosquito_cfd/_manifest.py` (design D4).
  - In `dataset.py`, delete the three definitions and re-export them from `_manifest` with the
    redundant-alias form in design D4 (`… as _REQUIRED_CONFIG_KEYS`, and so on). A plain import
    fails ruff `F401`, because `dataset.py` has no `__all__`. Remove `load_json_clear_error` from
    `dataset.py`'s imports only if nothing else there uses it.
  - Switch the anchor's and 2.2's imports to `mosquito_cfd._manifest`.
  - Add `test_field_and_force_paths_raise_the_same_manifest_error`. For top level `5` and for a
    missing `reynolds`, `FieldCorpus(root).config_ids()` and `dataset.load_manifest_configs` each give
    `type(e) is ValueError` with equal messages. Before this commit the top-level-`5` case is red
    (`TypeError` on both paths). After it, it is green, and it stays green through 2.4.
  - `corpus.py` is **untouched** in this commit.
  - Commit: `refactor(manifest): extract stdlib-only _manifest.py and re-export from force_surrogate.dataset (advances #160)`.
- [ ] 2.4 **Red, then green: `FieldCorpus` switch (atomic).**
  - Red:
    - `test_manifest_read_loads_no_force_surrogate_stack` (child (a), design D7).
      - Red: the child lists `mosquito_cfd.force_surrogate`, `pandas`, `pyarrow` and `matplotlib.pyplot`.
    - `test_corpus_imports_no_force_surrogate_or_benchmarks` (AST of `corpus.py`).
      - Red: it finds the lazy `force_surrogate.dataset` import.
  - Green:
    - `corpus.py` does `from mosquito_cfd import _manifest` and `_configs()` calls
      `_manifest.load_manifest_configs`. Remove the lazy import and its comment, and update
      `corpus.py:258–260`.
    - In the same commit, retarget every `fs_dataset.load_manifest_configs` patch in
      `tests/test_field_surrogate_corpus.py`: `:262–267`, `:276–287`, `:310–321` and
      `_IoSpy.__init__` (class at `:592`, patch import at `:603`). Also update the `:254` import, the `:237` comment and the
      `:618` "lazily" comment.
    - Reword the `field_surrogate/__init__.py` docstring. Keep the cycle explanation, and drop the
      `corpus` → `force_surrogate.dataset` → pandas clause.
  - Re-run `baseline_imports.py`. Pass criterion: none of `mosquito_cfd.force_surrogate`, `pandas`,
    `pyarrow` or `matplotlib.pyplot` loaded after `config_ids()`. Record the time and module count in
    the commit body.
  - Commit: `perf(field-surrogate): read the sweep manifest through _manifest, not force_surrogate (advances #160)`.

## 3. Commit rule and `ValueError`-only (`metadata_capture`, `benchmarks`)

- [ ] 3.1 **Red** (record anchors separately from reds):
  - `tests/test_metadata_capture.py`:
    - Reds:
      - `extract_git_info` with commit `"a"*40+"\n"`, and `resolve_git_info(git_commit_override="a"*40+"\n")`:
        each gives `type(e) is ValueError` with the value's `repr` in the message. Red: accepted.
      - `"git": None`, `{"commit": 123}` and an override of `123`. Red: `TypeError`.
      - `"git": [["commit", "a"*40]]`. Red: accepted through `dict()` coercion.
      - `"git"` absent. Red: already a `ValueError`, but its message says `got ''`, not `None`.
      - `"git": ["x"]` and `"git": "abc"`. Red: already a `ValueError`, but `dict()`'s own message
        ("dictionary update sequence element…") has no `repr` of the value.
      - `load_pod_run_metadata` on a file holding `[]` or `5`. Red: no error at load, then
        `AttributeError` downstream. Assert at the load.
    - Anchor: a missing pod file gives `FileNotFoundError`.
    - `resolve_git_info({"git": None}, git_commit_override="b"*40)` and `resolve_git_info({}, …)`
      return `{"commit": "b"*40, "source": "cli-override"}`. Anchor: green today. It guards the
      override-first ordering.
  - `tests/test_benchmarks_metadata.py`: `MOSQUITO_CFD_COMMIT="a"*40+"\n"` makes `_baked_commit_env()`
    return `None`, and in the no-`.git` setup `get_git_info` returns the error dict. Red: the value is
    returned.
- [ ] 3.2 **Green** (design D6).
  - In `metadata_capture`: `extract_git_info`, `resolve_git_info` (override first) and
    `load_pod_run_metadata` use `is_full_commit_sha` and the type checks. Delete `_FULL_SHA_RE`.
  - In `benchmarks/metadata._baked_commit_env`: use `is_full_commit_sha`, and delete `_FULL_SHA_RE`
    and its "mirrors force_surrogate…" comment. Leave `metadata_capture.py:105`'s unrelated "mirrors"
    comment alone.
  - Commit: `fix(run-metadata): full-match commit SHAs and raise ValueError for wrongly typed git provenance (advances #159)`.

## 4. Image rule: `validate_image_digest` full-strict (atomic)

- [ ] 4.1 **Red.**
  - In `tests/test_force_surrogate_sidecar.py`:
    - Replace `test_validate_image_digest_accepts_and_strips` (`:20`) with
      `test_validate_image_digest_returns_value_unchanged`. The full reference and the
      `:fp64@sha256:` form are returned `==` the input. This is green for whitespace-free input; its
      red comes from the next test.
    - Add `test_validate_image_digest_rejects_loose_or_mistyped` over the force-surrogate scenario's
      list, `bytes` included. Assert `type(e) is ValueError`, with a message containing
      `content-addressable`, `sha256`, `digest` and the `repr`. Red: the bare, junk and whitespace
      values are accepted; `5` and a list give `AttributeError`; `bytes` gives `TypeError`.
    - Replace the `:131` strip assertion with a rejection, and add a `capture_surrogate_run_metadata`
      round-trip of both valid forms, unchanged.
  - In `tests/test_metadata_capture.py`: `extract_docker_image` gives `type(e) is ValueError`, with the
    `repr` in the message, for:
    - `docker_image` absent. Red: already a `ValueError`, but it reports `Got ''`, not `None`.
    - `None`. Anchor: it already reports `Got None`.
    - `5` (red: `AttributeError`);
    - a bare `sha256:<64>` (red: accepted);
    - a valid reference plus `"\n"` (red: accepted, stripped).
  - In `tests/test_generate_run_metadata_cli.py`: `main()` with a pod file whose `docker_image` is a
    bare digest raises `ValueError` matching `content-addressable`, and leaves no output file. Red:
    succeeds.
- [ ] 4.2 **Green** (design D5).
  - `sidecar.validate_image_digest` uses `is_pinned_image_ref` with the D5 message. Remove `_DIGEST_RE`
    and its comment.
  - Rewrite the docstrings at `sidecar.py:118–139` (no "stripped" and no "Returns: The stripped
    digest") and `:155–164` (no "must contain `sha256:`").
  - `metadata_capture.extract_docker_image` passes `pod_metadata.get("docker_image")` with no `or ""`.
    Rewrite its docstring (`:505–516`) and the module docstring's `docker_image` line (`:22`):
    "`docker_image` is the pod's digest-pinned reference (`<repo>@sha256:<64 hex>`), recorded exactly
    as the pod wrote it."
  - Fixture `tests/fixtures/run_metadata/pod_run_metadata.json`: change `docker_image` to
    `ghcr.io/talmolab/mosquito-cfd@sha256:f546ead9afd9bf490cdc2b255ed0a254f4079262ea6cd4b3d1d7e6c86b0f286a`.
    Its README line becomes: "the git commit from `run_metadata_s35_f085_p45.json`'s `git.commit`,
    and the image as a single full reference: that file's `image_digest`, prefixed with the
    repository named in `docs/force_surrogate/fine-grid-pilot-report.md:48`."
  - In `tests/test_metadata_capture.py`:
    - `DIGEST` (`:42`) becomes a full reference;
    - the `startswith("sha256:")` asserts (`:288`, `:689`) become equality with the input or
      `is_pinned_image_ref`;
    - `:91` follows the `DIGEST` change.
  - Commit: `fix(force-surrogate): validate_image_digest full-matches a digest-pinned reference and returns it unchanged (advances #159)`.
- [ ] 4.3 **Docs and help-text sweep (own commit, after 4.2).**
  - Rewrite the eight `--docker-digest` `help=` strings to
    `"Digest-pinned image reference, <repo>@sha256:<64hex> (a bare sha256 digest or a mutable tag is rejected)."`.
    Each string ends with its own existing parenthetical where one adds information, such as
    `train_surrogate.py`'s "from the dataset's run_metadata.json". The eight strings are in:
    - `scripts/extract_forces.py:127`
    - `scripts/make_comparison_figure.py:47`
    - `scripts/make_config_mean_collapse_diagnostic.py:53`
    - `scripts/make_evidence_figure.py:51`
    - `scripts/make_flow_video.py:82`
    - `scripts/make_kinematics_video.py:64`
    - `scripts/make_wing_phase_diagnostic.py:136`
    - `scripts/train_surrogate.py:52`
  - Rewrite the "Pinned ``sha256:`` …" parameter docstrings to
    "Digest-pinned image reference (``<repo>@sha256:<64 hex>``; a mutable tag or bare digest is
    rejected)". They are at:
    - `force_surrogate/comparison_figure.py:155, :302`
    - `force_surrogate/dataset.py:716, :724`
    - `force_surrogate/runner.py:433`
    - `force_surrogate/run_one_config.py:175`
    - `force_surrogate/wing_phase_diagnostic.py:74`
    - `visualization/flow_video.py:477`
    - `visualization/kinematics_video.py:167`

    `sidecar.py:125, :178` are done in 4.2. **Do not** edit `evidence_figure.py:849` or
    `train.py:928, :935, :1206` (F3a's files). They go into the 6.1 follow-up issue.
  - Re-run the sweep:

    ```
    grep -rnE 'sha256: image digest|sha256 container digest|``sha256:``|validated .?.?sha256|--docker-digest sha256|[^@]sha256:<|contain(s|ing)? .?sha256:|whitespace is stripped|stripped digest' src scripts docs examples .claude cluster openspec/project.md
    ```

    The `[^@]` stops the correct `@sha256:<` text from matching. Fix every remaining
    *instruction*. Leave as they are: historical records (`sweep_provenance.json`, archived changes,
    `docs/CHANGELOG.md` history), and the do-not-touch files above.
  - Commit: `docs: describe --docker-digest as a full digest-pinned reference (advances #159)`.

## 5. Mutation testing (against the final code SHA, after 4.3)

Record each mutant's SHA, the mutant itself, the test that kills it, and the red output, in a table
appended to this file. Restore from saved bytes after each. A surviving non-equivalent mutant gets a
test, amended into its section's commit **before** the PR, not as a new commit.

- [ ] 5.1 **Provenance.**
  - `is_full_commit_sha`:
    - `fullmatch` → `match` with `^…$`;
    - drop the `isinstance` check (expect `TypeError` on `b"…"`);
    - `[0-9a-f]` → `[0-9a-z]`.
  - `is_pinned_image_ref`:
    - `fullmatch` → `search`;
    - drop the `isinstance` check;
    - the repository class → `.*`;
    - the repository made optional, `(?:[a-z0-9][a-z0-9._/:-]*@)?sha256:…`.
  - `run_provenance` back to inline regexes: an equivalent control that must survive.
  - Guards on the guards:
    - insert `importlib.import_module("mosquito_cfd.force_surrogate")` into a function in
      `_provenance` (the AST test must fail);
    - drop the parent's `mosquito_cfd.__file__` assertion while the child gets a wrong `PYTHONPATH`
      (record that this mutant survives without the assertion, and that the assertion kills it).
- [ ] 5.2 **Manifest.**
  - `_manifest`:
    - drop the top-level `isinstance(dict)` check;
    - narrow the except to `(json.JSONDecodeError, RecursionError)`;
    - drop `RecursionError`;
    - drop the `UnicodeDecodeError` handling;
    - change the invalid-JSON prefix.
  - `corpus._configs`:
    - restore the lazy `force_surrogate.dataset` import (the fresh-interpreter and AST tests must fail);
    - a **module-level** name import `from mosquito_cfd._manifest import load_manifest_configs`
      (the retargeted count tests must fail). A function-local name import would see patches and
      survive, so it is not this mutant.
  - `_manifest`: insert `importlib.import_module("pandas")` (the AST test must fail).
  - `dataset` keeps its own copy instead of re-exporting (the identity test must fail).
  - `_IoSpy` patches the old `fs_dataset` target (`:699` must fail).
- [ ] 5.3 **Force side and benchmarks.**
  - `extract_git_info`:
    - drop the `git` `isinstance` check;
    - keep the `dict(git)` coercion;
    - restore `_FULL_SHA_RE.match`.
  - `resolve_git_info`:
    - restore `.match` for the override;
    - type-check `git` before the override branch (the override-first anchors must fail).
  - `load_pod_run_metadata`: drop the top-level `isinstance` check.
  - `_baked_commit_env`: restore `^…$` with `.match`.
  - `validate_image_digest`:
    - restore `.strip()` before the check;
    - restore the `.search` pattern.
  - `extract_docker_image` restoring `or ""`: killed by 4.1's absent-key test, which expects the
    message to report `None`, not `''`.
  - Equivalent mutant to record, not hunt: `validate_image_digest` returning `value.strip()`. The
    predicate already refuses whitespace.
- [ ] 5.4 Commit the table: `docs(openspec): record mutation results for share-light-corpus-helpers (advances #160, #159)`.

## 6. Verification, follow-ups and close-out

- [x] 6.1 Ask the user, then file two follow-up issues (filed 2026-11-18 with the user's approval: #174, #175), each cross-linking #160 or #159:
  - `evidence_figure.py`'s import-time `matplotlib.use("Agg")` (F3a owns `force_surrogate/__init__.py`).
    This issue also lists the four "Pinned ``sha256:`` …" docstrings left in `evidence_figure.py:849`
    and `train.py:928, :935, :1206`;
  - `sidecar.load_json_clear_error` lets `RecursionError` escape from a deeply nested pod-side
    `run_metadata.json`.
- [ ] 6.2 Re-run every committed `*run_metadata*.json` through the **shipped**
  `is_full_commit_sha` and `is_pinned_image_ref`. Confirm that design E2's table still holds.
- [ ] 6.3 Run `tests/test_light_corpus_helpers.py` and the changed test files on Linux: `gh-04`, at
  the pushed SHA after the user allows a push, or CI. The subprocess, environment and
  path-in-message tests are OS-sensitive.
- [ ] 6.4 Check that this prints nothing:

  ```
  git diff --name-only c87e39c -- src/mosquito_cfd/force_surrogate/__init__.py src/mosquito_cfd/force_surrogate/train.py src/mosquito_cfd/force_surrogate/evidence_figure.py tests/test_committed_surrogate_provenance.py docs/field_surrogate/roadmap.md experiments/
  ```
- [ ] 6.5 `git merge origin/main` (no rebase). Run the full suite, lint, and
  `openspec validate --strict`.
- [ ] 6.6 Last commit: `docs(changelog): share-light-corpus-helpers (advances #160, #159)`.
  - Add the `docs/CHANGELOG.md` entries under `## [Unreleased]`, using the file's style: 2–3 bullets.
    Mark the image rule `**BREAKING:**`. Mark the type, newline and private-module items
    `**BREAKING (minor):**`.
  - Correct line 16's `field_surrogate/_provenance.py` to `mosquito_cfd/_provenance.py`.
- [ ] 6.6.1 Run `openspec validate share-light-corpus-helpers --strict` once more after 6.6.
- [ ] 6.7 Reconcile the implementation against `proposal.md`, `design.md` and every spec delta. Record
  any deviation in a `### Why N instead of M?` section before `/pre-merge-check`.
- [ ] 6.8 In the PR body:
  - note the image-rule rollout: after merge, `--docker-digest` takes the full reference;
  - list the caller grep;
  - mention F3a's worktree owner, because `validate_image_digest` tightens under their callers too.
- [ ] 6.9 After #171 merges, update the F3 dependency line in `docs/field_surrogate/roadmap.md` (near
  :285) in a separate docs PR. Not part of this change.
