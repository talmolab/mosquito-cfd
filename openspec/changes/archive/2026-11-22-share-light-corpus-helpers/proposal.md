# share-light-corpus-helpers

## Why

`FieldCorpus`'s first manifest read imports the whole force-surrogate stack (pandas, pyarrow,
`matplotlib.pyplot` and a backend switch; 2.8–4.6 s per spawned training worker, #160), and the
force-surrogate provenance validators are looser than the field side's strict ones (#159). Both are
fixed by moving the manifest reader and the provenance checks into small standard-library-only
modules above both packages; the evidence is in `design.md` E1–E3.

## What Changes

- **New `mosquito_cfd/_manifest.py`** (stdlib only).
  - Holds `load_manifest_configs`, `_REQUIRED_CONFIG_KEYS` and `_validate_configs`, moved from
    `force_surrogate/dataset.py`.
  - Has its own JSON load.
  - `force_surrogate.dataset` re-exports all three as the same objects.
  - Messages are unchanged for object-top-level manifests, with the documented exceptions in
    design D4. A non-object top level, deep nesting, a digit-limit integer and non-UTF-8 bytes all
    raise `ValueError` naming the path. The non-object message starts `manifest <path>`, like the
    existing "has no 'configs' key" message; the JSON and UTF-8 messages start
    `sweep manifest <path>`, like the existing invalid-JSON message.
- **`git mv field_surrogate/_provenance.py` to `mosquito_cfd/_provenance.py`.**
  - It gains the total predicates `is_full_commit_sha(value)` and `is_pinned_image_ref(value)`.
  - It becomes the single definition of both rules, and `run_provenance` uses them.
  - The old private path is removed.
- **`FieldCorpus` reads the manifest through `mosquito_cfd._manifest`.** A first manifest read loads
  no `force_surrogate`, pandas, pyarrow or `matplotlib.pyplot`.
- **Force-surrogate and benchmarks provenance checks use the predicates.**
  - `metadata_capture.extract_git_info` and `resolve_git_info`, and `benchmarks/metadata._baked_commit_env`:
    full-match commit SHAs.
  - `metadata_capture.load_pod_run_metadata`, `extract_git_info` and `resolve_git_info`: wrongly
    typed values raise `ValueError` naming the value.
  - `sidecar.validate_image_digest`: full-match a digest-pinned reference, with no strip, and return
    the input unchanged.
- **The force side does not check `status`, `run_id` or `git.dirty`** (design D6).
- **Docs and help text:**
  - the eight `--docker-digest` argparse help strings;
  - the `sidecar`, `metadata_capture` and `_provenance` docstrings;
  - the `field_surrogate/__init__.py` docstring;
  - the fixture README;
  - `docs/CHANGELOG.md`, including the stale `field_surrogate/_provenance.py` path in its #169 entry.

### BREAKING

- **BREAKING:** `validate_image_digest`, and so `capture_surrogate_run_metadata` and every
  `--docker-digest` CLI and the Argo `validate` step, rejects the following. Previously these were
  accepted:
  - a bare `sha256:<64 hex>`;
  - a tag with a digest appended (`ghcr.io/x:latest #sha256:<hex>`);
  - text around a digest;
  - surrounding whitespace, which was previously stripped.

  It returns its input unchanged. Every documented invocation in the repository already passes the
  full `ghcr.io/talmolab/mosquito-cfd@sha256:<64hex>` reference, except one `visualization-tooling`
  spec example, which is MODIFIED here.
- **BREAKING:** `scripts/generate_run_metadata.py` rejects a pod-side `docker_image` that is a bare
  digest, and a `git.commit` or `--git-commit` with a trailing newline.
- **BREAKING (minor):** wrongly typed `git`, `git.commit`, `--git-commit` or `docker_image` values,
  and a non-object top level in the pod file or the sweep manifest, raise `ValueError` instead of
  `TypeError` or `AttributeError`. For a top-level array, the manifest message changes from
  "has no 'configs' key" to one naming the JSON type.
- **BREAKING (minor):** `get_git_info`'s baked-commit fallback treats `MOSQUITO_CFD_COMMIT="<40 hex>\n"`
  as malformed.
- **BREAKING (minor):** the private `mosquito_cfd.field_surrogate._provenance` is removed. Use
  `mosquito_cfd._provenance`.

No committed corpus artifact changes status under the stricter checks (design, Evidence E2).

### Out of scope

- `force_surrogate/__init__.py`'s eager imports, and `evidence_figure.py`'s import-time
  `matplotlib.use("Agg")`. F3a edits `__init__.py`; follow-up #174.
- The four "Pinned ``sha256:`` …" docstrings in `evidence_figure.py:849` and
  `train.py:928, 935, 1206`. F3a owns those files. The text is left as is and recorded in the
  follow-up issue.
- `docs/field_surrogate/roadmap.md` (waits for #171).
- #143, #152, #107, and the garbage-`Header` item on #113.
- Other wrong-type paths in `assemble_run_metadata` (`rows`, `deck_sha256`), and a deeply nested
  pod-side `run_metadata.json`. The latter still escapes as `RecursionError` through
  `sidecar.load_json_clear_error`; follow-up #175.
- Parsing the full OCI reference grammar.

## Impact

- **Affected specs** (MODIFIED unless noted):
  - `field-surrogate`:
    - "Corpus addressing by config and step"
    - "Corpus snapshots carry run identity and digest-pinned provenance"
  - `force-surrogate`:
    - "Run provenance with caller-supplied timestamp and container digest"
    - ADDED "Sweep-manifest reading lives in a shared standard-library-only module"
    - ADDED "Image digest wording throughout this capability means a digest-pinned reference"
  - `run-metadata`:
    - "git commit is always recorded as a full 40-character SHA"
    - "docker image identity is a single unambiguous, digest-validated field"
    - "get_git_info falls back to a build-time-baked commit when git itself is completely unavailable"
  - `heaving-ellipsoid-validation`: "Ellipsoid re-run captures pinned, verifiable provenance (CC-V3)"
  - `visualization-tooling`: "Video and figure generators resolve parameters from a named config or
    an explicit override, never a hardcoded constant" (the example digest only)
- **Affected code:**
  - new `src/mosquito_cfd/_manifest.py`;
  - `src/mosquito_cfd/_provenance.py`, moved from `field_surrogate/`;
  - `field_surrogate/corpus.py` and `field_surrogate/__init__.py` (docstring);
  - `force_surrogate/dataset.py`, `force_surrogate/sidecar.py` and `force_surrogate/metadata_capture.py`;
  - `benchmarks/metadata.py`;
  - the `--docker-digest` help text in `scripts/{extract_forces,make_comparison_figure,make_config_mean_collapse_diagnostic,make_evidence_figure,make_flow_video,make_kinematics_video,make_wing_phase_diagnostic,train_surrogate}.py`;
  - the "Pinned ``sha256:`` …" parameter docstrings in `force_surrogate/{comparison_figure,dataset,runner,run_one_config,wing_phase_diagnostic}.py` and `visualization/{flow_video,kinematics_video}.py`.
- **Behavior changes with no edit:** every caller of `validate_image_digest` or
  `capture_surrogate_run_metadata` (grep at implementation time for the PR body), including
  `cluster/argo/workflows/force-surrogate-sweep.yaml`'s `validate` step.
- **Fixtures and docs:**
  - `tests/fixtures/run_metadata/pod_run_metadata.json` and its README;
  - `docs/CHANGELOG.md`.
- **Tests:**
  - new `tests/test_light_corpus_helpers.py`;
  - `tests/test_field_surrogate_corpus.py`, `tests/test_metadata_capture.py`,
    `tests/test_force_surrogate_sidecar.py`, `tests/test_benchmarks_metadata.py` and
    `tests/test_generate_run_metadata_cli.py`.
- **Issues:** resolves #160 and #159. Follow-ups: #174 (the `matplotlib.use("Agg")` import side effect and four docstrings in
  F3a's files) and #175 (`load_json_clear_error`'s `RecursionError`, digit-limit and non-object gaps).
