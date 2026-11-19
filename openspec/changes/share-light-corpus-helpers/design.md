# Design: share-light-corpus-helpers

## Context

`harden-field-reader-pre-f3` (PR #169, archived at
`openspec/changes/archive/2026-11-18-harden-field-reader-pre-f3/`) added a stdlib-only
`field_surrogate/_provenance.py`. Its design gave two reasons:

- **D4:** reading provenance must not import `force_surrogate`;
- **D8:** the strict rules (full match; no strip or default; `ValueError` only).

It deliberately left alone:

- **#160.** `FieldCorpus._configs()` lazily imports `force_surrogate.dataset.load_manifest_configs`.
  That runs `force_surrogate/__init__.py`, which loads pandas, pyarrow and `matplotlib.pyplot`, and
  `evidence_figure.py`, which calls `matplotlib.use("Agg")`.
- **#159.** The force-side validators are looser than the field side's:
  - `metadata_capture._FULL_SHA_RE` is `^[0-9a-f]{40}$` used with `.match`, and `$` matches before a
    final `\n`. `benchmarks/metadata._baked_commit_env` is a third copy with the same bug.
  - `sidecar.validate_image_digest` runs `.search` for `sha256:<64 hex>` on the stripped value, and
    so accepts a bare digest, a tag with a digest appended, and junk around a digest.
  - Wrong types escape as `TypeError` or `AttributeError`.

The user confirmed these decisions on 2026-11-18:

- top-level modules, moved rather than shimmed;
- the full-strict image rule;
- the benchmarks SHA site included;
- the manifest moved with a top-level-object guard.

## Evidence (gathered before proposing)

**E1. #160 baseline** on `c87e39c` (scratchpad `baseline_imports.py`, warm disk; #160 measured
about 4.6 s cold):

| Step | Time | `sys.modules` | Heavy modules loaded |
|---|---|---|---|
| `import mosquito_cfd.field_surrogate.corpus` | 0.37 s | 211 | none |
| first `FieldCorpus(root).config_ids()` | 2.77 s | 787 | `mosquito_cfd.force_surrogate`, `pandas`, `pyarrow`, `matplotlib.pyplot` |

After the change: 0.00 s, 212 → 214 modules, none of them loaded. The saving covers manifest and
metadata reads only. A worker's first `snapshot()` still imports yt (about 3 s, ~1200 modules,
`matplotlib` but not `pyplot`), a pre-existing cost that F3 should absorb with a forkserver preload
or persistent workers (PR review, performance lens).

**E2. Committed `*run_metadata*.json` audit.** All 50 files from `git ls-files '*run_metadata*.json'`
were run through the old and strict checks (scratchpad `audit_run_metadata.py`). Task 6.2 re-runs
the audit with the shipped predicates.

| Files | Old commit / image | Strict commit / image | Effect |
|---|---|---|---|
| 27 `examples/prelim_sweep_fine/run_metadata_<config>.json` | pass / pass | pass / pass | none |
| fine and coarse `run_metadata.json`, `surrogate/` and `figures/`; T2a, T2b, T3b; 2 `tests/fixtures/comparison_figure/*` | pass / pass | pass / pass | none |
| `examples/flapping_wing/run_metadata_t3c.json` | **fail / fail** (`81d6306`, `:fp64`) | fail / fail | none: already failing, and no code re-validates it |
| 3 `examples/prelim_sweep_fine_pilot/run_metadata_*.json` | pass / **fail** | pass / fail | none: already failing, and no code re-validates them |
| `tests/fixtures/run_metadata/pod_run_metadata.json` | pass / pass | pass / **fail** (bare `sha256:f546…`) | **updated** to the full reference |
| 4 Argo-status and manifest fixtures | n/a | n/a | none |

The pilot files use the pre-#59 split schema. `docker_image` is the tag `ghcr.io/talmolab/mosquito-cfd:fp64`,
and a separate `image_digest` field holds `sha256:f546ead9…`; the image check reads only
`docker_image`. The fixture README's statement that its digest comes from the pilot file is
therefore correct: the digest is that file's `image_digest`. The repository is named in
`docs/force_surrogate/fine-grid-pilot-report.md:48`
(`ghcr.io/talmolab/mosquito-cfd@sha256:f546ead9…`).

`examples/prelim_sweep/sweep_provenance.json`'s historical `docker_image_digest: "sha256:0762…"` is a
hand-written record that no code validates.

**E3. Parallel work** (checked read-only):

- No parallel change's spec delta MODIFIES any requirement this change touches. That covers
  `add-surrogate-comparison-bench` (F3a), `fix-stale-spec-claims`, `add-real-comparison-figures`,
  `docs-surrogate-comparison-plan` (#171) and `explore-surrogate-experiments`.
- F3a and `fix-stale-spec-claims` both MODIFY force-surrogate "Committed evidence-figure artifacts
  with provenance". This change therefore does **not** MODIFY that requirement (D8).
- `experiments/e0b_long_run/analyze.py` imports `force_surrogate.dataset.load_manifest_configs`, and
  the experiments use `corpus.snapshot`. Both keep working.
- F3a plans to edit `force_surrogate/train.py`, `__init__.py` and
  `tests/test_committed_surrogate_provenance.py`. This change edits none of them.
- No tracked caller passes a bare digest:
  - `cluster/argo/scripts/submit_workflow.sh` requires `@sha256:`;
  - `docker.yml` emits the pinned reference.

## Decisions

### D1. Two top-level private modules: `mosquito_cfd/_manifest.py` and `mosquito_cfd/_provenance.py`

The modules sit next to the existing `mosquito_cfd/_messages.py`. `field_surrogate`, `force_surrogate`
and `benchmarks` each import them without importing one another.

`mosquito_cfd/__init__.py` holds only `__version__`, so importing either module costs only the
standard library. Neither module imports anything from `mosquito_cfd`, so neither can join an
import cycle.

`_provenance.py` moves with a **pure** `git mv`, in its own commit, with only the import-path edits
in its importers. That keeps 100% rename similarity for `git log --follow` and per-commit review.
Its content changes come in a later commit.

There is no shim. The module was private, and its importers are `corpus.py` and the tests (grepped,
including the other worktrees).

### D2. Shared rules are total predicates, defined once

`_provenance.is_full_commit_sha(value: object) -> bool` and `is_pinned_image_ref(value: object) -> bool`
each return `isinstance(value, str) and bool(PATTERN.fullmatch(value))`, so neither can raise. The
patterns are defined **only** here. The specs state each regex once, in the field-surrogate
requirement, and the other capabilities refer to the predicates.

Callers keep their own messages and exception policy. Predicates are shared rather than compiled
patterns because the #159 bugs were *usage* errors: `.match` with `^…$`, and `.search`. A predicate
fixes the usage as well as the pattern.

### D3. `FieldCorpus` reaches the reader through a module attribute

`corpus.py` does `from mosquito_cfd import _manifest` and calls `_manifest.load_manifest_configs(...)`,
so the tests have one patch point. A name import would bind a copy that a patch of `_manifest`
cannot reach.

The tests that patch `fs_dataset.load_manifest_configs` today must be retargeted:

| Tests | What they assert | With a stale target |
|---|---|---|
| `:267` | a replaced return value | fails loudly |
| `:281–287`, `:315–321` | a call count of 1 | fails loudly |
| `_IoSpy` (`:592–625`), used by `:690` and `:1034` | `spy.calls == []` | **passes vacuously** |

All `_IoSpy` users share the one class. `:699` asserts `spy.count("load_manifest") == 1` through it,
which is the positive control. A mutation check confirms that `:699` goes red when the spy patches
the old name.

`force_surrogate.dataset` binds `load_manifest_configs` by re-export, and `build_dataset` resolves it
through `dataset`'s globals. A patch of `dataset.load_manifest_configs` therefore still reaches
`build_dataset`, and a test pins that. `force_surrogate/__init__.py` re-exports from `dataset`, so
`mosquito_cfd.force_surrogate.load_manifest_configs` is the same object, and a test pins that too.

### D4. Manifest loading in `_manifest`, and the parity boundary

`load_json_clear_error` lives in `force_surrogate/sidecar.py`, which imports `benchmarks.metadata`,
so `_manifest` has its own loader:

1. `path.read_text(encoding="utf-8")`. A missing file raises `FileNotFoundError`, unchanged.
   `UnicodeDecodeError` raises `ValueError(f"sweep manifest {path} is not valid UTF-8: {exc}")`.
   It was a bare `UnicodeDecodeError`, which is a subclass, so `except ValueError` callers are
   unaffected.
2. `json.loads(text)`. `except (ValueError, RecursionError)` raises
   `ValueError(f"sweep manifest {path} is not valid JSON: {exc}")`. That message is byte-identical
   to the old one for a `JSONDecodeError`. It newly covers:
   - the int-digit limit, which previously raised Python's own `ValueError("Exceeds the limit (4300 digits)…")`;
   - `RecursionError`.
3. `if not isinstance(manifest, dict)`: raise
   `ValueError(f"manifest {path} top level is a {type(manifest).__name__}, not an object; not a sweep manifest")`.
4. The existing `configs` check and `_validate_configs`, unchanged.

`dataset.py` has no `__all__`. After the move it no longer uses `_REQUIRED_CONFIG_KEYS` or
`_validate_configs` itself, so a plain import would fail ruff `F401`. It re-exports them with the
redundant-alias form, which ruff and type checkers treat as an explicit re-export:

```python
from mosquito_cfd._manifest import (
    _REQUIRED_CONFIG_KEYS as _REQUIRED_CONFIG_KEYS,
)
from mosquito_cfd._manifest import (
    _validate_configs as _validate_configs,
)
from mosquito_cfd._manifest import (
    load_manifest_configs as load_manifest_configs,
)
```

### Why three import statements instead of one?

The approved design showed a single parenthesized import. Ruff's isort runs with
`combine-as-imports` off, its default, so it splits aliased names into one statement each (`I001`
on the combined form). Behavior is identical. The identity test pins all three names, and
mutation D1 confirms it.

**Parity boundary.** Messages are unchanged for every object-top-level manifest that is valid UTF-8,
whose JSON the parser accepts, and that the old reader rejected. The documented exceptions are:

- the top-level-array message;
- the int-digit and non-UTF-8 cases, which gain a `sweep manifest <path>` prefix;
- deep nesting, which was a `RecursionError` before.

The anchor test pins the literal messages before the move.

### D5. `validate_image_digest` is full-strict and returns its input unchanged

It returns `value` when `is_pinned_image_ref(value)` holds. Otherwise it raises:

```
ValueError("docker_image_digest must be a content-addressable, digest-pinned image reference of the
form '<repo>@sha256:<64 hex>' (e.g. 'ghcr.io/talmolab/mosquito-cfd@sha256:...'); a mutable
tag like ':latest' or a bare 'sha256:...' digest is not accepted. Got {value!r}")
```

An absent key reports as `Got None`, which is `repr(None)`. Before this change, `or ""` made it
report as `Got ''`.

The message keeps the substrings `content-addressable`, `sha256` and `digest`, which existing tests
match on:

- `test_force_surrogate_sidecar.py:31,39`;
- `test_flow_video.py:53`, `test_kinematics_video.py:49`, `test_force_surrogate_driver.py:280` and
  `test_force_surrogate_run_one_config.py:305`;
- `test_metadata_capture.py:294`.

It names the expected form and ends with the value's `repr`.

The rule has three parts:

- **No strip:** whitespace means a value was hand-pasted, and silently cleaning it is what PR #169
  D8 forbids.
- **No bare digest:** it cannot be pulled.
- **Tag plus digest is accepted:** `ghcr.io/x:fp64@sha256:<hex>`, which OCI resolves by the
  digest, and which `_provenance` already accepts.

`extract_docker_image` passes `pod_metadata.get("docker_image")`, with no `or ""`.

### D6. Force-side scope: commit, image and `ValueError`; never `status`, `run_id` or `dirty`

`status`, `run_id` and `dirty` stay field-side only, for three reasons:

- `capture_surrogate_run_metadata` records real local `dirty: true` runs (`run_metadata_t2a.json`);
- `assemble_run_metadata` already refuses a non-`completed` status;
- the fine-corpus files have no `dirty` key.

**`extract_git_info`:**

- `git = pod_metadata.get("git")`.
  - Anything that is not a `dict` raises `ValueError(f"git must be an object; got {git!r}")`. That
    covers absent (reported as `None`), `null`, `["x"]`, `"abc"` and a list of pairs.
  - Today `["x"]` and `"abc"` raise `dict()`'s own `ValueError` ("dictionary update sequence
    element…"), whose message has no `repr`. An absent `git` today reports `got ''`. A list of pairs
    is accepted.
- `commit = git.get("commit")`.
  - `is_full_commit_sha` must hold, else `ValueError(f"git commit must be a full 40-character lowercase hex SHA; got {commit!r}")`.
    An absent `commit` reports `None`.
  - The `(length N)` suffix is dropped.
- It returns `dict(git)`.

**`resolve_git_info`:**

- It checks the override **first**, and only that. A valid override returns
  `{"commit": override, "source": "cli-override"}` without reading `pod_metadata` at all, even if
  `git` is absent or `null`.
- An invalid override raises the same message form, naming `--git-commit`.

**`load_pod_run_metadata`:** a non-`dict` top level raises
`ValueError(f"pod-side run_metadata.json {path} top level is a {type}, not an object")`. The
`RecursionError` gap in `sidecar.load_json_clear_error` is out of scope and filed as a follow-up.

### D7. Fresh-interpreter tests run in a subprocess that provably imports this tree

Each test runs `subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, env=os.environ | {"PYTHONPATH": str(SRC)})`.
That is the inherited environment, which Windows needs for `SYSTEMROOT`, following
`tests/test_field_surrogate_snapshot.py:53`.

The child prints JSON `{"file": mosquito_cfd.__file__, "loaded": sorted(forbidden ∩ sys.modules)}`.
The parent asserts two things:

- `loaded == []`;
- `Path(file).resolve()` lies under the parent's own `Path(mosquito_cfd.__file__).resolve().parent`.

The second check stops a mutation worktree's child from importing another tree's editable install.

Children and their forbidden sets:

| Child | Action | Forbidden in `sys.modules` |
|---|---|---|
| (a) | `FieldCorpus(root).config_ids()` | `mosquito_cfd.force_surrogate`, `pandas`, `pyarrow`, `matplotlib.pyplot` |
| (b) | `_manifest.load_manifest_configs` | (a)'s set plus `mosquito_cfd.field_surrogate` and `mosquito_cfd.benchmarks` |
| (c) | `_provenance` read and validate | (b)'s set |

An AST test also checks that `field_surrogate/corpus.py` contains no import of
`mosquito_cfd.force_surrogate` or `mosquito_cfd.benchmarks` anywhere, nested imports included. That
covers code paths the children do not exercise.

The stdlib-only AST check on `_manifest.py` and `_provenance.py` refuses:

- relative imports;
- names outside `sys.stdlib_module_names`;
- calls to `importlib.import_module` or `__import__`.

### D8. Image-digest wording elsewhere in `force-surrogate` and `heaving-ellipsoid-validation`

Seven force-surrogate requirements describe the image as "a digest containing `sha256:`". So does
`heaving-ellipsoid-validation`'s CC-V3 requirement. All of them reach `validate_image_digest`.
MODIFYing all seven would collide with F3a and `fix-stale-spec-claims` on "Committed evidence-figure
artifacts with provenance".

So the change instead:

- ADDs one force-surrogate requirement stating that every such phrase in the capability means a
  reference accepted by `validate_image_digest`, that is, `is_pinned_image_ref`;
- MODIFIES the single heaving-ellipsoid requirement, which no parallel change touches.

## Risks and trade-offs

- **An out-of-repo script or a hand-typed submission passing a bare digest now fails fast.** This is
  fail-closed and corrupts no data. The message names the expected form. In-flight pods run the
  code baked into their image, so they are unaffected until the image is rebuilt.
  - The PR body says: after merge, pass the full `<repo>@sha256:` reference.
  - Rollback is `git revert` of the squash commit; nothing persisted depends on the strictness.
- **Retargeting the corpus tests' patch point** could make two `_IoSpy` assertions vacuous (D3).
  The guards are `:699` and a mutant.
- **The OS-sensitive tests** (subprocess, environment, path-in-message) run on Linux (`gh-04`) or in
  CI before `/pre-merge-check`, not only on the Windows dev box.
