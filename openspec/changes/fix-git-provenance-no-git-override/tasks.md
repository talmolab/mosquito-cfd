## Tasks

### 1. `resolve_git_info()` in `metadata_capture.py` — the CLI-override path

- [x] 1. Write `test_extract_git_info_rejects_missing_commit_key` in
   `tests/test_metadata_capture.py`, next to the existing `test_git_commit_must_be_full_sha`:
   given `pod_metadata["git"] = {"error": "git not available or not a repository"}` (the exact
   real-world payload `get_git_info()` produces for a `.git`-less pod), assert
   `mc.extract_git_info(pod_metadata)` still raises `ValueError` (matching `"40-character"`).
   Verifies the actual #66 failure shape has coverage — today's suite only exercises a truncated
   7-character SHA, never the missing-key case.
- [x] 2. Write `test_resolve_git_info_falls_through_to_extract_git_info_when_no_override`: call
   `mc.resolve_git_info(pod_metadata, git_commit_override=None)` against a valid fixture pod
   metadata and assert it returns the identical dict `mc.extract_git_info(pod_metadata)` would.
   Verifies the no-override path is unchanged passthrough.
- [x] 3. Write `test_resolve_git_info_raises_when_no_override_and_pod_commit_missing`: reuse the
   missing-key `git` block from task 1, call `mc.resolve_git_info(pod_metadata,
   git_commit_override=None)`, and assert `ValueError` matching `"40-character"`. Pins the actual
   code path `assemble_run_metadata` uses in production (`resolve_git_info`, not
   `extract_git_info` directly) for the real #66 failure shape — task 1 alone only proves
   `extract_git_info` itself still raises, not that `resolve_git_info`'s delegation preserves it.
- [x] 4. Write `test_resolve_git_info_raises_when_no_override_and_pod_commit_truncated`: same shape
   as task 3, but for the pre-existing truncated-SHA case (`git.commit = "634c561"`, matching
   `test_git_commit_must_be_full_sha`'s fixture value) instead of the missing-key case — call
   `mc.resolve_git_info(pod_metadata, git_commit_override=None)` and assert `ValueError` matching
   `"40-character"`. Closes the same class of gap as task 3, symmetrically: without this, the
   truncated-SHA scenario would only be pinned at the `extract_git_info` layer, never at the
   `resolve_git_info` layer production code actually calls.
- [x] 5. Write `test_resolve_git_info_override_bypasses_pod_value`: build a `pod_metadata` whose
   `git` block is the missing-key error shape from task 1 (so calling `extract_git_info` on it
   would raise), call `mc.resolve_git_info(pod_metadata, git_commit_override="a" * 40)`, and
   assert it returns `{"commit": "a" * 40, "source": "cli-override"}` without raising. Verifies
   the override is used verbatim and the pod's own (invalid) git block is never consulted.
- [x] 6. Write `test_resolve_git_info_override_wins_over_valid_differing_pod_commit`: build a
   `pod_metadata` whose `git.commit` is a *valid* 40-character SHA (e.g. `"b" * 40`), call
   `mc.resolve_git_info(pod_metadata, git_commit_override="c" * 40)`, and assert the result is
   `{"commit": "c" * 40, "source": "cli-override"}` — the override wins even when the pod's own
   value was already valid, not just when it was invalid (closes the gap where every other
   override test only exercises an already-broken pod value).
- [x] 7. Write `test_resolve_git_info_rejects_malformed_override`: call `mc.resolve_git_info(...,
   git_commit_override="634c561")` (7 chars, mirroring the existing truncated-SHA test value) and
   assert `ValueError` matching `"40-character"`.
- [x] 8. Write `test_resolve_git_info_rejects_uppercase_hex_override`: call
   `mc.resolve_git_info(..., git_commit_override="A" * 40)` and assert `ValueError` matching
   `"40-character"` — `_FULL_SHA_RE` is lowercase-only by design (see `design.md` Decision 2); this
   pins that an uppercase override is rejected, not silently case-folded.
- [x] 9. Implement `resolve_git_info(pod_metadata, *, git_commit_override=None)` in
   `metadata_capture.py` per `design.md` Decision 1/2: validate `git_commit_override` against
   `_FULL_SHA_RE` when supplied and return `{"commit": git_commit_override, "source":
   "cli-override"}`; otherwise delegate to `extract_git_info(pod_metadata)` unchanged. Run tasks
   1-8 to green.

### 2. Thread `--git-commit` through `assemble_run_metadata` and the CLI [depends: 1]

- [x] 10. Write `test_assemble_run_metadata_accepts_git_commit_override` in
    `tests/test_metadata_capture.py` (alongside the existing `_assemble()` helper's tests): call
    `_assemble(git_commit="b" * 40)` against a fixture pod metadata whose `git.commit` is the
    missing-key error shape, and assert the output's `git.commit == "b" * 40` and
    `git["source"] == "cli-override"`.
- [x] 11. Change `assemble_run_metadata`'s `git_info = extract_git_info(pod_metadata)` line to
    `git_info = resolve_git_info(pod_metadata, git_commit_override=git_commit)`, adding a new
    `git_commit: str | None = None` keyword parameter to `assemble_run_metadata`'s signature (and
    docstring). Run task 10 to green; confirm all pre-existing `test_metadata_capture.py` tests
    (including the module's other `_assemble(...)` cases) still pass unmodified.
- [x] 12. Write `test_cli_git_commit_flag_overrides_pod_value` in
    `tests/test_generate_run_metadata_cli.py`. This file has no existing tmp_path-mutated-fixture
    helper (that pattern lives in `tests/test_metadata_capture.py`, e.g.
    `test_assemble_metadata_raises_on_row_count_mismatch_between_pod_and_csv`) — write it inline
    here: `json.loads((_FIXTURES / "pod_run_metadata.json").read_text(encoding="utf-8"))`, set
    `["git"] = {"error": "git not available or not a repository"}`, write the mutated dict to
    `tmp_path / "pod_run_metadata.json"` via `json.dump`, then build argv from `_base_args(output)`
    with `--pod-metadata` replaced by that `tmp_path` file and `--git-commit <40-char-sha>`
    appended. Assert the CLI exits 0 and the written output's `git.commit` equals the supplied
    override.
- [x] 13. Add `--git-commit` to `scripts/generate_run_metadata.py`'s argparse parser (default
    `None`, help text mirroring `--wall-time-s`'s style), and thread `git_commit=args.git_commit`
    into the `assemble_run_metadata(...)` call. Run task 12 to green.
- [x] 14. Update `metadata_capture.py`'s module docstring: revise the `git` field bullet (currently
    "passed through from the pod's own already-produced `run_metadata.json`") to describe the
    override/pod-value precedence, and document the new `source` key that appears on the output
    when either the CLI override or (indirectly, via a pod that itself used the baked-commit
    fallback) a non-live-git-derived value is used. This is the only field-provenance reference
    for `run_metadata_<config>.json`'s schema in the repo, so it must stay accurate.

### 3. `get_git_info()` build-time-baked-commit fallback [parallel with 1-2]

- [x] 15. Write `test_get_git_info_uses_baked_commit_when_git_unavailable` in
    `tests/test_benchmarks_metadata.py`, alongside the existing retry-integration tests: with
    `monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "c" * 40)` and `subprocess.run` mocked to always
    fail (no `.git` at all — `mc._worktree_retry_env` returns `None`), assert
    `mc.get_git_info(tmp_path)` returns `{"commit": "c" * 40, "source":
    "docker-image-build-arg"}`.
- [x] 16. Write `test_get_git_info_treats_unknown_sentinel_as_absent`: same setup as task 15 but
    `monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "unknown")`, assert `mc.get_git_info(tmp_path)`
    still returns `{"error": "git not available or not a repository"}`.
- [x] 17. Write `test_get_git_info_ignores_baked_commit_when_direct_query_succeeds`: use the
    existing `_fake_success_run` fixture (direct `git rev-parse` succeeds) plus
    `monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "d" * 40)`, and assert `mc.get_git_info(tmp_path)`
    returns the real git-derived dict (`commit == "abc123"` per `_fake_success_run`, `branch`,
    `dirty`, `repository` present) with no `"source"` key — the baked env var is never consulted.
- [x] 18. Write `test_get_git_info_ignores_baked_commit_when_worktree_retry_succeeds`: reuse the
    existing Windows-worktree-retry-succeeds fixture setup from the #78 tests plus
    `monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "e" * 40)`, assert the retry's real git-derived
    dict wins and no `"source"` key is present.
- [x] 19. Write `test_get_git_info_attempts_direct_query_before_baked_commit_fallback`: with no
    `.git` at all and `monkeypatch.setenv("MOSQUITO_CFD_COMMIT", "c" * 40)`, spy on
    `mc.subprocess.run` with a wrapper that **records each call and then raises
    `subprocess.CalledProcessError(1, argv)`** (mirroring the existing
    `test_get_git_info_does_not_retry_for_non_worktree_failure` failure-simulation pattern) —
    recording alone is not sufficient: `_collect_git_info` calls `subprocess.run([...],
    check=True, ...)`, so a spy that merely records and returns a benign
    `CompletedProcess(returncode=0, ...)` would make the direct query appear to *succeed*, and the
    baked-commit tier would never be reached at all. Assert both that the spy was called at least
    once AND that `mc.get_git_info(tmp_path)` still returns the baked-commit dict. Proves the new
    tier genuinely runs *after* the existing attempts, not before or instead of them — the same
    class of ordering guarantee `test_get_git_info_unaffected_when_first_attempt_succeeds` already
    proves for the #78 retry.
- [x] 20. Write `test_get_git_info_no_baked_commit_env_falls_through_unchanged`: with
    `monkeypatch.delenv("MOSQUITO_CFD_COMMIT", raising=False)` and no `.git` at all, assert
    `mc.get_git_info(tmp_path)` still returns today's plain
    `{"error": "git not available or not a repository"}` — confirms the new branch is inert when
    unset, not just when `"unknown"`.
- [x] 21. Implement the new fallback in `get_git_info()` per `design.md` Decision 3/4/6: add a
    private helper (e.g. `_baked_commit_env() -> str | None`, returning `None` for an absent or
    `"unknown"` value) and insert one new branch after the existing worktree-retry block, before
    the final `return {"error": ...}`. Do not modify any existing CODE line above that point. Run
    tasks 15-20 to green; confirm all pre-existing `test_benchmarks_metadata.py` tests
    (especially `test_get_git_info_unaffected_when_first_attempt_succeeds`, which asserts
    `_worktree_retry_env` is never even called) still pass unmodified.
- [x] 22. Update `get_git_info()`'s own docstring (`benchmarks/metadata.py`, currently describing
    only the direct-query-then-#78-WSL-worktree-retry two-tier behavior and stating "Returns:
    Dictionary with git commit, branch, dirty status, and diff hash") to describe the new third
    tier and its reduced return shape: when the baked-commit fallback fires, the returned dict is
    `{"commit": ..., "source": "docker-image-build-arg"}` only — no `branch`/`dirty`/`diff_hash`/
    `repository` keys, since there is no `.git` to derive them from. This is a docstring-only
    change (the one exception to task 21's "do not modify any existing CODE line above that
    point" — the docstring sits above the insertion point but carries no logic).

### 4. Docker image: bake `MOSQUITO_CFD_COMMIT` into `:fp64` [parallel with 1-3]

> **Note:** this task group is independently mergeable but not independently *useful* apart from
> task group 3 — see `design.md`'s Risks/Trade-offs. Bake without the code that reads it (group 3)
> and the ARG/ENV/LABEL sit unread; ship the fallback (group 3) without this group and it can
> never fire in a real image. Land both before considering issue #66 resolved end-to-end.

- [x] 23. In `docker/Dockerfile.fp64`, add the new `ARG`/`ENV`/`LABEL` trio **late in the file** —
    declare `ARG MOSQUITO_CFD_COMMIT=unknown` immediately after the existing
    `WORKDIR /opt/cfd/mosquito-cfd` line, followed by `ENV MOSQUITO_CFD_COMMIT=${MOSQUITO_CFD_COMMIT}`
    and `LABEL com.mosquito-cfd.commit="${MOSQUITO_CFD_COMMIT}"`, all immediately before
    `COPY pyproject.toml uv.lock .python-version README.md LICENSE ./` — preserve the two
    existing explanatory comment lines already sitting between `WORKDIR` and that `COPY`
    ("Copy Python project files..." / "LICENSE is required...") rather than deleting or
    duplicating them when inserting the new lines. **Do NOT** add these to the existing
    top-of-file `ARG` block (lines 16-20) or the existing `LABEL` block (lines 23-31; note lines
    23-25 of that block are `org.opencontainers.image.*` labels and lines 26-31 are the
    `com.mosquito-cfd.*` ones) — `github.sha` changes on every CI build, unlike the stable
    `IAMREX_COMMIT`/`AMREX_COMMIT`/`CUDA_ARCH` values declared there, and placing it that early
    would invalidate the Docker layer cache for the expensive upstream AMReX/IAMReX clone-and-build
    steps on every single build (see `design.md` Decision 5a for the exact snippet and rationale —
    found and fixed during `/review-openspec`'s CI/CD review round).
- [x] 24. **Pre-merge verification.** A full local build/run against the actual
    `docker/Dockerfile.fp64` proved infeasible within available session time (it compiles
    AMReX/AMReX-Hydro/IAMReX from source; a build attempt was still mid-`apt-get install` after
    10 minutes with no usable local layer cache — see `design.md`'s "Why N instead of M?"
    section). Verified instead: (1) the exact new `ARG`/`ENV`/`LABEL` trio, in isolation against a
    minimal `FROM alpine` Dockerfile — confirmed `unknown` with no `--build-arg`, and the real
    supplied value both in the running container's env and in `docker inspect`'s
    `com.mosquito-cfd.commit` label, with `--build-arg`; (2) `hadolint` run directly against the
    real, modified `docker/Dockerfile.fp64` — zero new findings beyond pre-existing
    warnings/info, all below `ci.yml`'s `failure-threshold: error` gate. A full end-to-end build
    still happens automatically via `docker.yml`'s `build-fp64` job on merge to `main` (this repo
    has no PR-time Docker build trigger); recommend a full local build before relying on a
    freshly-built `:fp64` image for a cluster run, per `openspec/project.md`'s existing "Image
    staleness check" convention.
- [x] 25. In `.github/workflows/docker.yml`'s `build-fp64` job, add
    `MOSQUITO_CFD_COMMIT=${{ github.sha }}` as a new line in the existing `build-args:` block
    (after `CUDA_ARCH=...`, around line 128). No workflow-level or job-level `permissions:` change
    needed (confirmed in `design.md`/`proposal.md`: `github.sha` requires no new grant). Note:
    this line's end-to-end correctness (that the workflow actually passes the right value through
    to a real build) is only confirmed once `build-fp64` runs post-merge on `main` — there is no
    PR-time equivalent, per task 24's note.
- [x] 26. Add a `### Fixed` entry to `docs/CHANGELOG.md` for issue #66, matching the granularity of
    the entry `fix-git-provenance-wsl-worktree-v2` added for issue #77.

### 5. Spec + full-suite validation [depends: 1-4]

- [x] 27. Run `openspec validate fix-git-provenance-no-git-override --strict` and resolve any
    issues.
- [x] 28. Run `uv run ruff check src/mosquito_cfd/force_surrogate/metadata_capture.py
    src/mosquito_cfd/benchmarks/metadata.py scripts/generate_run_metadata.py
    tests/test_metadata_capture.py tests/test_benchmarks_metadata.py
    tests/test_generate_run_metadata_cli.py` and `uv run ruff format --check` on the same file
    list; fix any violations.
- [x] 29. Run the full test suite (`uv run pytest tests/test_metadata_capture.py
    tests/test_generate_run_metadata_cli.py tests/test_benchmarks_metadata.py -v`) and confirm
    every pre-existing test still passes alongside the new ones from tasks 1-22.

### 6. `/review-pr` self-review fixes (pre-PR, `/pre-merge-check` Phase 3.5)

A 5-lens pre-PR self-review found one real gap two independent lenses converged on (see
`design.md` Decision 8): `_baked_commit_env()` had no format validation, unlike the CLI-override
path, and `force_surrogate/sweep.py`'s pre-existing `_git_commit()` (an untouched, undiscovered-
until-now second consumer of `get_git_info()`) applies no validation of its own and feeds the
result straight into a committed `sweep_provenance.json` — so a misconfigured build-arg could
have silently propagated a malformed value into that file with no safety net.

- [x] 30. Write `test_get_git_info_treats_malformed_baked_commit_as_absent_whitespace`,
    `..._truncated`, and `..._uppercase` in `tests/test_benchmarks_metadata.py`: set
    `MOSQUITO_CFD_COMMIT` to `" "`, `"abc1234"`, and `"C" * 40` respectively (with no `.git` at
    all), and assert `get_git_info()` still returns the honest error dict in each case, not a
    fabricated `commit`.
- [x] 31. Implement format validation in `_baked_commit_env()` (`benchmarks/metadata.py`): add a
    local `_FULL_SHA_RE` constant (mirroring `metadata_capture.py`'s) and reject any value that
    doesn't match it, treating it identically to an absent/`"unknown"` value. Run task 30 to
    green; confirm all pre-existing tests (including tasks 15-20's) still pass unmodified.
- [x] 32. Hoist the `"unknown"` sentinel and the two `source` tag strings
    (`"cli-override"`, `"docker-image-build-arg"`) to named module-level constants
    (`_UNKNOWN_COMMIT_SENTINEL`, `_SOURCE_DOCKER_BUILD_ARG` in `benchmarks/metadata.py`;
    `_SOURCE_CLI_OVERRIDE` in `metadata_capture.py`) — a separate Code Quality finding from the
    same review round (previously bare literals repeated across implementation and tests with no
    single source of truth).
- [x] 33. Write `test_cli_git_commit_flag_rejects_malformed_override` in
    `tests/test_generate_run_metadata_cli.py`: confirm format validation is enforced end-to-end
    through the CLI wrapper, not just at the `resolve_git_info` unit level it delegates to.
- [x] 34. Write `test_assemble_run_metadata_git_commit_override_wins_over_valid_pod_value` in
    `tests/test_metadata_capture.py`: confirm the override wins at the `assemble_run_metadata`
    level too (not just at the `resolve_git_info` unit level), even when the pod's own
    `git.commit` is already valid.
- [x] 35. Re-run `openspec validate --strict`, `ruff check`/`ruff format --check`, and the full
    targeted test suite; confirm 92/92 pass.
