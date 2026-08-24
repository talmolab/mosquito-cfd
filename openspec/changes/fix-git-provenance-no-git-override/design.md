## Context

This is a distinct root cause from issue #77/PR #78 (`fix-git-provenance-wsl-worktree-v2`, just
merged, archived at
`openspec/changes/archive/2026-08-24-fix-git-provenance-wsl-worktree-v2/`), which fixed
`get_git_info()` misparsing a *valid* Windows-created worktree's `.git` pointer file when read
from WSL — a path-parsing bug on the local/driver host. That change's own proposal explicitly
scoped this issue out:

> "Issue #66 (pod-side containers with no `.git` directory at all, hard-failing on
> `extract_git_info`'s SHA validation) is a distinct root cause in a different code path
> (`force_surrogate/metadata_capture.py::extract_git_info`) and is explicitly **out of scope** for
> this change."

> "However, the retry path added here is unreachable there: the image's `COPY` list never
> includes `.git`, so pod-side `.git` doesn't exist at all (neither directory nor worktree
> pointer), `_worktree_retry_env` returns `None`, and pod-side output is byte-for-byte unchanged.
> This is issue #66's territory (pod-side git-less containers) and stays out of scope for this
> change."

This change does not touch `get_git_info()`'s WSL-worktree retry logic (added by #78) — it adds a
new, independent fallback tier that only runs after that retry has already failed.

Separately, issue #66's failure has two independent time dimensions that a single mechanism can't
cover:

- **Retroactive**: pod-side `run_metadata.json` files already sitting on NFS from the blocked
  27-config corpus run were captured *before* any image change can exist. Only a caller-supplied
  value at metadata-generation time can recover provenance for those.
- **Prospective**: every future run on an unmodified `:fp64` image will hit the exact same failure
  forever unless something automatic changes. A CLI flag that a human must remember to pass every
  time is a standing operational hazard, not a fix.

Hence the two-mechanism (hybrid) design, confirmed with the user during scoping rather than
picking one of the issue's two originally-proposed options.

## Goals / Non-Goals

**Goals:**
- Let an operator regenerate metadata for already-collected pod-side artifacts with no valid git
  block, given the commit they independently verified built the image.
- Make every future CI-built `:fp64` image self-describing for git provenance, with no manual
  step.
- Leave `extract_git_info()` and #78's WSL-worktree retry logic completely unmodified — this
  change only adds new call paths around them.

**Non-goals:**
- Retroactively rebuilding or relabeling already-published image digests (not possible after the
  fact — a rebuild changes the digest).
- Fixing issue #65 (`compute_wall_time_s` per-config filtering).
- Giving the baked-commit fallback branch/dirty-state fidelity — there is no `.git` in the image,
  so only the commit SHA is ever knowable via this path.

## Decisions

### Decision 1: `resolve_git_info()` wraps `extract_git_info()` rather than adding a parameter to it

**What was considered:** adding `git_commit_override: str | None = None` directly as a new
parameter on `extract_git_info()` itself.

**Why rejected:** `extract_git_info()`'s current contract is "read and validate the pod's own
`git` block" — a pure reader with one job. `resolve_wall_time_s()` (the explicit precedent named
in scoping) is itself a *separate* function layered on top of `compute_wall_time_s()`, not a
parameter bolted onto `compute_wall_time_s()`. Mirroring that shape exactly: `resolve_git_info()`
is the new override-aware entry point; `extract_git_info()` stays a pure pod-block reader, used
internally by `resolve_git_info()` only when no override is supplied. This keeps
`extract_git_info()`'s existing tests, docstring, and every other reference to it completely
untouched.

### Decision 2: the override is still validated as a 40-character SHA, unlike `wall_time_s_override`

**What was considered:** accepting the override verbatim with no format check, exactly matching
`resolve_wall_time_s`'s `float(wall_time_s_override)` (a type cast, not a semantic validation).

**Why rejected:** confirmed explicitly during scoping. A wrong wall-time number is an obviously
wrong number; a wrong or truncated commit SHA silently corrupts provenance in a way that looks
fine downstream (still a string in the right field) until someone tries to check out that commit
and it doesn't exist, or it aliases an unrelated abbreviated hash. Provenance correctness matters
more here than for a numeric override, so `resolve_git_info()` validates `git_commit_override`
against the same `_FULL_SHA_RE` pattern `extract_git_info()` already uses, raising the same class
of `ValueError` on a malformed value.

**Case-sensitivity is intentionally unchanged, not a new gap:** `_FULL_SHA_RE` (`^[0-9a-f]{40}$`)
only matches lowercase hex, so an uppercase or mixed-case 40-character override (e.g. from a UI
that displays hashes uppercase) is rejected as malformed — identically to how `extract_git_info`
already treats an uppercase pod-sourced `git.commit` today. This change does not introduce
case-folding for either path; it is called out explicitly here (and covered by a test, see
`tasks.md`) as a deliberate non-goal rather than an overlooked edge case.

### Decision 3: the baked-commit fallback lives inside `get_git_info()`, as a new tier after the #78 retry

**What was considered:** a wholly separate function (e.g. `read_baked_commit_env()`) called from
`capture_run_metadata()` or from `extract_git_info()`/`resolve_git_info()` instead, leaving
`get_git_info()` scoped strictly to "ask actual git."

**Why chosen instead:** confirmed during scoping. `get_git_info()` is already the single function
responsible for producing the pod's git provenance dict by whatever means are available — #78
already established the precedent of `get_git_info()` trying more than one strategy internally
(direct query, then WSL-worktree-translated retry) before giving up. Adding the baked-env-var
check as one more internal fallback tier, after the existing retry and before the final error
dict, keeps all "how do we know the commit" logic in one place and is purely additive: it never
runs before or instead of the #78 retry, only after both the direct attempt and that retry have
already failed.

### Decision 4: `"unknown"` is the Dockerfile default, treated as absent

**What was considered:** omitting the `ARG` default entirely, so an unparameterized local build
leaves `MOSQUITO_CFD_COMMIT` unset/empty rather than `"unknown"`.

**Why chosen instead:** confirmed during scoping — `unknown` is an explicit, greppable sentinel
in `docker inspect`/`docker history` output for a locally-built dev image, more discoverable than
an empty string. `get_git_info()`'s new fallback treats both an unset env var and the literal
string `"unknown"` as "no baked commit available" and falls through to the honest error dict
either way, so a local dev build never fabricates a fake commit.

### Decision 5: the new ARG/ENV/LABEL are declared late in `Dockerfile.fp64`, not in the existing top-of-file pinned-dependency block

**What was considered:** adding `MOSQUITO_CFD_COMMIT` to the existing top `ARG` block (lines
16-20) and the existing `LABEL` block (lines 23-31 — lines 23-25 are `org.opencontainers.image.*`
labels, lines 26-31 are the `com.mosquito-cfd.*` ones), directly alongside
`IAMREX_COMMIT`/`AMREX_COMMIT`/`CUDA_ARCH` — the "obvious" place given the precedent those labels
already establish.

**Why rejected** (caught in `/review-openspec`'s CI/CD review round — a real, confirmed bug, not a
style preference): `MOSQUITO_CFD_COMMIT` is `github.sha`, which is **different on every single CI
build** — unlike `IAMREX_COMMIT`/`AMREX_COMMIT`/`CUDA_ARCH`, which only change when a maintainer
deliberately bumps `build-args.env`. BuildKit's cache key for each instruction chains from its
parent's key; a `LABEL` referencing an ARG whose value changes every build gets a new cache key
every build, and every subsequent instruction's key changes too. The existing top `LABEL` block
sits *before* the expensive `git clone`/`RUN make -j$(nproc)` layers (the Dockerfile's own comment
calls this build step "this takes a while"). Adding a per-commit-varying value to that early block
would invalidate the GHA build cache (`cache-to: type=gha,mode=max,scope=fp64`) for those
expensive layers on every single CI run, silently defeating the cache the workflow already pays to
maintain.

**Decision:** redeclare a second, local `ARG MOSQUITO_CFD_COMMIT=unknown` immediately after
`WORKDIR /opt/cfd/mosquito-cfd` (near the end of the file, right before
`COPY pyproject.toml uv.lock .python-version README.md LICENSE ./`), and add the matching `ENV`
and `LABEL` there together — after the expensive AMReX/AMReX-Hydro/IAMReX clone-and-build layers,
so only the last few layers (`COPY`/`uv sync`/workspace setup — already effectively invalidated on
most commits since `COPY src/` changes almost every push) are affected by this per-build-varying
value:

```dockerfile
WORKDIR /opt/cfd/mosquito-cfd

# Declared here (not in the top ARG/LABEL block) so this per-commit-varying value doesn't
# invalidate the cache for the expensive AMReX/IAMReX clone+build layers above -- github.sha
# changes on every CI build, unlike the pinned dependency commits labeled above.
ARG MOSQUITO_CFD_COMMIT=unknown
ENV MOSQUITO_CFD_COMMIT=${MOSQUITO_CFD_COMMIT}
LABEL com.mosquito-cfd.commit="${MOSQUITO_CFD_COMMIT}"

# Copy Python project files (uv sync will auto-install Python)
# LICENSE is required: pyproject's license-files = ["LICENSE"] makes uv_build error if it is
# absent from the build context (the project wheel is built here during uv sync).
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
COPY src/ ./src/
```

(the two comment lines shown above the final `COPY` already exist in the file today — preserve
them as-is; only the `ARG`/`ENV`/`LABEL` trio above them is new)

### Decision 6: `build-args.env` is not touched; the new build-arg is passed directly in `docker.yml`

`build-args.env` exists specifically to pin *upstream dependency* commits (`IAMREX_COMMIT`,
`AMREX_COMMIT`, `AMREX_HYDRO_COMMIT`) that are hand-updated only when those dependencies are
deliberately bumped. `MOSQUITO_CFD_COMMIT` is categorically different: it must equal the
triggering commit of *this* build, every single time, automatically — the opposite of a pinned,
occasionally-updated value. `docker.yml` already computes exactly that value
(`${{ github.sha }}`) for image tagging; this change reuses it as a build-arg on the same
`build-fp64` step rather than inventing a place for it in `build-args.env`.

### Decision 7: a `"source"` field distinguishes fallback-derived git info from real git output

Both new paths (`resolve_git_info`'s CLI override, and `get_git_info()`'s baked-commit fallback)
return a `git` dict containing only `{"commit": ..., "source": <tag>}` — no `branch`, `dirty`,
`diff_hash`, or `repository`, since none of those are knowable without an actual `.git` to
inspect. Tagging these dicts with `"source"` (`"cli-override"` / `"docker-image-build-arg"`)
keeps this distinction auditable in the committed `run_metadata_<config>.json` output, rather
than letting a fallback-derived record look indistinguishable from a real `git rev-parse`/`git
diff` result that happens to have fewer keys. The normal successful-git-query path is completely
unchanged — it does not gain a `"source"` key — preserving byte-for-byte parity for the common
case, consistent with #78's stated compatibility bar.

### Decision 8: `_baked_commit_env()` validates format itself, rather than trusting every downstream consumer to re-validate

**What was considered:** leaving `_baked_commit_env()` to accept any non-empty, non-`"unknown"`
string verbatim (as originally implemented), relying on `resolve_git_info`/`extract_git_info`'s
existing `_FULL_SHA_RE` check to catch a malformed value later, when `generate_run_metadata.py`
assembles the committed `run_metadata_<config>.json`.

**Why rejected** (caught in this change's own pre-PR `/review-pr` self-review — two independent
review lenses converged on the same root gap, one of them at BLOCKING severity): `get_git_info()`
has more than one consumer. `src/mosquito_cfd/force_surrogate/sweep.py`'s `_git_commit()`
(pre-existing, untouched by this change) calls `get_git_info()` directly and does
`info.get("commit", info.get("error"))` with **no format validation of its own**, feeding the
result straight into the committed `sweep_provenance.json`'s `git_commit` field. Before this
fallback tier existed, that call site could only ever receive a real git-derived commit or the
literal error string — both safe. Once the baked-commit fallback was added, an unvalidated,
misconfigured `MOSQUITO_CFD_COMMIT` (trailing whitespace from a heredoc mistake, a truncated
`--short` SHA from a future CI refactor) would have flowed straight through `_git_commit()` into
that committed file with **no safety net at all** — `extract_git_info`'s validation only guards
the `force_surrogate/metadata_capture.py` pipeline, not this second, independent consumer, and
`sweep.py` also discards the `"source"` tag entirely, making a bad baked value indistinguishable
from genuine `git rev-parse` output in that file.

**Decision:** `_baked_commit_env()` now validates the env var against the same `_FULL_SHA_RE`
pattern (`^[0-9a-f]{40}$`, duplicated as a local constant in `benchmarks/metadata.py` — see the
comment there for why this is a small duplication rather than a new inter-module import) before
ever returning it, treating a malformed value identically to an absent or `"unknown"` one (falls
through to the honest error dict). This is defense-in-depth at the single point where the value
enters the system, so every current and future consumer of `get_git_info()` — not just the ones
this change's author remembered to check — gets a value that is either genuinely trustworthy or
absent, never a silently-wrong string. `sweep.py` required no code change: it now automatically
inherits the same guarantee through `get_git_info()`'s return contract.

While fixing this, the `"unknown"` sentinel and the two `source` tag strings
(`"cli-override"`, `"docker-image-build-arg"`) were also hoisted to named module-level constants
in their respective files (`_UNKNOWN_COMMIT_SENTINEL`, `_SOURCE_DOCKER_BUILD_ARG`,
`_SOURCE_CLI_OVERRIDE`) — a separate, smaller finding from the same review round (Code Quality
lens): these were previously bare literals repeated across implementation and test files with no
single source of truth, a low-probability but real drift risk if either were ever renamed.

### Why N instead of M? Task 24's pre-merge verification was done in isolation, not against the full `Dockerfile.fp64`

`tasks.md` task 24 called for building the *actual* `docker/Dockerfile.fp64` locally, with and
without `--build-arg MOSQUITO_CFD_COMMIT=...`, to confirm the env var lands correctly inside the
running container. During implementation this proved infeasible within the available session
time: `Dockerfile.fp64` clones and compiles AMReX/AMReX-Hydro/IAMReX from source (the file's own
comment: "this takes a while"), and neither a fresh build nor a build against a locally-cached
`:fp64` image (pulled from GHCR, not built locally, so it carried no BuildKit-inspectable
intermediate-layer cache) completed within a 10-minute build attempt -- it was still unpacking
`apt-get install` output when the attempt was cut off.

**What was actually done instead:** the exact new `ARG`/`ENV`/`LABEL` trio was verified in
isolation against a minimal `FROM alpine` Dockerfile -- confirming the default (`unknown` with no
`--build-arg`) and override (the real value, both in the running container's `$MOSQUITO_CFD_COMMIT`
and in `docker inspect`'s `com.mosquito-cfd.commit` label) both work exactly as designed. Separately,
`hadolint` was run directly against the real, modified `docker/Dockerfile.fp64` and produced zero
new findings beyond the pre-existing warnings/info already present before this change (all below
`ci.yml`'s `failure-threshold: error` gate).

This is a narrower guarantee than a full end-to-end build: it confirms the ARG/ENV/LABEL mechanism
itself is correct and that the real file still lints clean, but does not prove the full image
still builds successfully top-to-bottom with these lines inserted (e.g. an unrelated syntax
mistake elsewhere in the diff would not be caught this way). Mitigations: (1) the actual edit is a
3-line, syntactically simple insertion with no interaction with the surrounding
`WORKDIR`/`COPY` lines (both preserved verbatim), independently confirmed by 3 rounds of
`/review-openspec` reading the real file; (2) `ci.yml`'s `dockerfile-lint` job (hadolint) still
runs this exact check on every PR; (3) `docker.yml`'s `build-fp64` job will perform the real,
full build automatically on merge to `main` -- if something is nonetheless wrong, it surfaces
there before any consumer pulls a broken image. A full local build remains recommended before
relying on a freshly-built `:fp64` image for a cluster run, per the existing "Image staleness
check" convention in `openspec/project.md`.

## Risks / Trade-offs

- **A stale/incorrect `--git-commit` override cannot be caught by format validation alone** — a
  well-formed but wrong 40-character SHA (e.g. a copy-paste of the wrong commit) will pass
  validation and be recorded as if correct. Mitigated by the CLI help text explicitly telling the
  operator this is unverified beyond format, and by the baked-commit path (which needs no
  human-supplied value at all) being the long-term fix for any run built by this updated CI.
- **The baked-commit path has the identical residual risk, for the identical reason** — a
  `MOSQUITO_CFD_COMMIT` that is well-formed but wrong (a stale value from a broken CI step, or a
  future refactor wiring the wrong ref) passes `_baked_commit_env()`'s format check just as
  readily as a mistyped `--git-commit` does; format validation can only catch malformed input, not
  semantically wrong input, on either path (caught during `/review-pr`'s final self-review round —
  the code already treats both paths identically, this bullet was just missing). Mitigated the
  same way the CLI path is: `docker.yml` computes `MOSQUITO_CFD_COMMIT` from `github.sha` on the
  same step that produces the image digest (see Decision 6), leaving no manual step where a human
  could substitute the wrong value, unlike the CLI override which is manually supplied every time.
  Separately: `force_surrogate/sweep.py`'s pre-existing `_git_commit()` (see Decision 8) discards
  the `"source"` tag when reading `get_git_info()`'s result, so a `sweep_provenance.json` entry
  produced from the baked-commit fallback is indistinguishable from a live `git rev-parse` result
  at that specific call site (though, per Decision 8, it is now guaranteed well-formed either way).
- **Images built before this change ships never gain `MOSQUITO_CFD_COMMIT`** — the fallback
  requires a rebuild. This is inherent to baking data in at build time and is explicitly accepted;
  the CLI override remains available indefinitely for metadata from older images.
- **Task group 4 (Dockerfile/CI) and task group 3 (`get_git_info()` fallback) are independently
  mergeable but not independently *useful*** — merging group 4 alone bakes `MOSQUITO_CFD_COMMIT`
  into the image with nothing yet reading it (a dead ARG/ENV/LABEL); merging group 3 alone adds a
  fallback branch that can never fire in any real `:fp64` image (unreachable outside the mocked
  unit tests). Neither ordering breaks tests or CI, and both are forward-compatible either way, but
  `tasks.md` calls this out explicitly so a partial merge isn't mistaken for a complete fix.
- **`docker.yml`'s `build-fp64` build-args wiring (`tasks.md` task 25) has no pre-merge
  verification** — `docker.yml` only triggers on `push` to `main`/tags or `workflow_dispatch`,
  never on a PR, so nothing exercises the actual `docker build` (and therefore the new
  `build-args:` line) before merge; `dockerfile-lint`'s hadolint check on PRs is lint-level only
  and would not catch a wiring mistake in `docker.yml` itself. Task 24's local `docker
  build`/`docker run` verification (a required pre-merge step — see `tasks.md`) is the only
  pre-merge signal this change gets; `ci.yml`'s `dockerfile-lint` job does run hadolint against
  `Dockerfile.fp64` itself on every PR, which is a real (if lint-level-only) pre-merge signal for
  task 23's Dockerfile edit specifically — just not for the `docker.yml` build-arg wiring, whose
  end-to-end correctness is confirmed only once `build-fp64` runs post-merge on `main`.
