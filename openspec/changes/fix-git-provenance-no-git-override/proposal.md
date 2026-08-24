## Why

`extract_git_info()` (`src/mosquito_cfd/force_surrogate/metadata_capture.py:330-349`) hard-fails
with `ValueError` unless the pod-side `run_metadata.json`'s `git.commit` field is already a full
40-character SHA, with **no override mechanism at all**. This unconditionally fails for every run
on the `:fp64` image, because `Dockerfile.fp64` only `COPY`s `pyproject.toml`/`src/` into the
image (lines 122-125) — no `.git` directory at all. Pod-side `get_git_info()`
(`src/mosquito_cfd/benchmarks/metadata.py:102-138`) correctly and honestly reports
`{"error": "git not available or not a repository"}` in this case (there genuinely is no
repository), but that dict has no `commit` key, so `extract_git_info()` raises every time.

This already blocked generating `run_metadata_<config>.json` for the full 27-config fine-grid
corpus; the reporter worked around it by hand-verifying which commit built the pinned image
digest and patching a local copy of the metadata, without touching the NFS originals (issue #66).

This is a distinct root cause from issue #77/PR #78 (`fix-git-provenance-wsl-worktree-v2`, just
merged) — see `design.md`'s Context section for that change's own explicit scope carve-out. This
proposal does not touch `get_git_info()`'s WSL-worktree retry logic added by #78 — it adds a new,
independent fallback tier that only runs after that retry has already failed.

## What Changes

Two complementary mechanisms (decided during scoping — see `design.md` for the full rationale for
choosing both instead of either alone):

1. **CLI override (`--git-commit`)** — retroactively fixes already-collected pod-side metadata
   (like the blocked 27-config corpus's existing files) that predates any image change. A new
   `resolve_git_info()` function in `metadata_capture.py` mirrors `resolve_wall_time_s`'s
   override-precedence pattern: when `--git-commit` is supplied, it is validated as a full
   40-character SHA and used verbatim — the pod's `git` block is never consulted at all. When
   absent, behavior is unchanged (falls through to today's `extract_git_info`).
2. **Build-time-baked commit (`MOSQUITO_CFD_COMMIT`)** — automatically fixes every future run
   with no manual step. `Dockerfile.fp64` gains a new `ARG MOSQUITO_CFD_COMMIT=unknown`, exposed
   to the running container via a matching `ENV`, and a new `LABEL com.mosquito-cfd.commit=...`.
   These are declared **late** in the file (near `WORKDIR /opt/cfd/mosquito-cfd`, right before the
   `COPY pyproject.toml ...` step) rather than in the existing top-of-file pinned-dependency
   `ARG`/`LABEL` block — `github.sha` changes on every build, unlike the stable
   `IAMREX_COMMIT`/`AMREX_COMMIT`/`CUDA_ARCH` values labeled there, and declaring it early would
   invalidate the Docker layer cache for the expensive upstream AMReX/IAMReX build steps on every
   single CI run (see `design.md` Decision 5a). `.github/workflows/docker.yml`'s `build-fp64` job
   passes
   `MOSQUITO_CFD_COMMIT=${{ github.sha }}` as a new build-arg — extending the existing
   `github.sha`-tagging convention already used for image tags, not inventing a new one.
   `get_git_info()` gains one new fallback tier, purely additive after the existing #78
   WSL-worktree retry: if the baked `MOSQUITO_CFD_COMMIT` env var is set to something other than
   the `"unknown"` default, it returns `{"commit": <value>, "source": "docker-image-build-arg"}`
   instead of the honest error dict. A locally-built dev image (no `--build-arg` passed) keeps the
   `"unknown"` default and is treated as absent, so it still gets the honest error — it must not
   silently claim a fake commit.

`extract_git_info()` itself is unchanged (signature, behavior, and docstring) — `resolve_git_info`
wraps it rather than modifying it, so every existing caller/test of `extract_git_info` continues
to work unmodified.

## Impact

- **Affected code**:
  - `src/mosquito_cfd/force_surrogate/metadata_capture.py` (new `resolve_git_info()`; new
    `git_commit: str | None = None` parameter on `assemble_run_metadata`)
  - `scripts/generate_run_metadata.py` (new `--git-commit` CLI flag)
  - `src/mosquito_cfd/benchmarks/metadata.py` (`get_git_info()` gains one new fallback branch; new
    private helper for reading/validating the baked env var, itself format-validated per
    `design.md` Decision 8 so every consumer of `get_git_info()` — not just this proposal's own
    pipeline — gets a trustworthy-or-absent value)
  - `src/mosquito_cfd/force_surrogate/sweep.py`: not modified, but its pre-existing
    `_git_commit()` (an untouched second consumer of `get_git_info()`, feeding
    `sweep_provenance.json`) benefits automatically from Decision 8's validation, since it applies
    no format checking of its own
  - `docker/Dockerfile.fp64` (new `ARG`/`ENV`/`LABEL` for `MOSQUITO_CFD_COMMIT`)
  - `.github/workflows/docker.yml` (`build-fp64` job's `build-args:` block gains one new line)
- **Affected documentation**:
  - `src/mosquito_cfd/force_surrogate/metadata_capture.py`'s module docstring (the authoritative
    field-provenance reference for `assemble_run_metadata`'s output — its `git` bullet must
    describe the new override/fallback precedence and the new `source` field)
  - `docs/CHANGELOG.md` — a `### Fixed` entry for issue #66, matching the granularity #78's own
    change established one change ago for the sibling issue
- **Affected specs**: `run-metadata` (MODIFIED requirement for the CLI-override path; ADDED
  requirement for the baked-commit fallback path)
- **Not affected / explicitly out of scope**: issue #65 (`compute_wall_time_s` per-config
  filtering — same file, distinct bug); `get_git_info()`'s WSL-worktree retry logic itself (only
  extended with a new tier *after* it, never modified); `build-args.env` (holds pinned *upstream*
  dependency commits only — `github.sha` is dynamic per-build and doesn't belong there; the new
  build-arg is passed directly in `docker.yml` instead).
- **CI permissions**: none required. `github.sha` is a built-in workflow context value, not a
  permission-gated API call; the existing job-level `contents: read`/`packages: write` blocks
  already present on `build-fp64` are sufficient.
- **Rollout**: the baked-commit path only takes effect once `:fp64` is rebuilt via this updated
  workflow; images already published before this change lack `MOSQUITO_CFD_COMMIT` entirely (env
  var absent, not `"unknown"`) and fall through to the honest error dict exactly as today, unless
  an operator supplies `--git-commit` manually for runs from those older images.
