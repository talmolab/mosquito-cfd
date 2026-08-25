## MODIFIED Requirements

### Requirement: Argo sweep-submission provisions the NFS workspace before submitting

`cluster/argo/scripts/submit_workflow.sh`'s `full` and `smoke` commands SHALL provision the
`--workspace-hostpath` from the local, git-committed corpus directory (its `inputs/` and the
canonical `examples/flapping_wing/wing.vertex`; `sweep_manifest*.json` additionally for `full`,
which reads it, but not for `smoke`, which runs a single named deck and never reads the manifest)
**before** calling `argo submit`, translating the cluster-hostPath convention
(`/hpi/hpi_dev/...`) to the WSL-visible mount point (`/mnt/hpi_dev/...`, per
`openspec/project.md`'s path table) before any filesystem operation — `submit_workflow.sh` runs
inside WSL, so operating on the unstranslated cluster-path string would silently no-op or write to
the wrong location while still reporting success. Provisioning SHALL replace (not merge into) any
prior `inputs/` content at the destination, SHALL verify the copy of `wing.vertex` specifically by
content hash (the one artifact with a documented history of silently drifting; `inputs/` and the
manifest rely on the replace-not-merge behavior plus `cp`'s own failure under `set -euo pipefail`),
and SHALL reject a `--corpus-dir`/`--workspace-hostpath` pair whose basenames don't match
(preventing one corpus's decks from being silently provisioned onto a different corpus's
workspace). Provisioning SHALL additionally reject a `--corpus-dir`/`--workspace-hostpath` pair
that resolves to the **same real filesystem path** (whether via an identical literal path, or two
differently-spelled paths — relative vs. absolute, a trailing slash, a symlink — that name the
same real directory), checked **before** the destructive replace-not-merge step: without this
check, staging a corpus onto itself deletes the corpus's own `inputs/` via `rm -rf` before the
subsequent `cp -r` can read from it, since a basename-only comparison cannot distinguish this case
from two genuinely distinct corpora. It fails fast and loudly rather than causing the submitted
workflow's pods to retry a mount for hours (issue #62) or, worse, silently run against stale or
mismatched geometry. Provisioning SHALL default to on and SHALL be skippable via an explicit
`--no-provision` flag for an operator who has already verified the workspace is current. This is
additive to, and independent of, the existing `--parallelism` override — sibling requirements, not
a replacement for either (cross-referenced from both requirements' descriptions, not a one-way
pointer).

#### Scenario: A stale or missing NFS workspace is provisioned before submission

- **Given** a `--corpus-dir` containing `inputs/` + `sweep_manifest.json` whose basename matches `--workspace-hostpath`'s basename, and a `--workspace-hostpath` (resolved to its local mount point) that is empty or contains stale content
- **When** `submit_workflow.sh full` runs (verified cluster-free via a stub `argo` executable and a `tmp_path`-rooted `--workspace-hostpath`/`CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX`, per the existing `--parallelism` test convention — never a live cluster or real NFS mount)
- **Then** the resolved local workspace directory contains a byte-identical copy of `inputs/` and `sweep_manifest*.json` (verified by content equality at the test level, mirroring the existing `--parallelism` test's hashlib convention) and a copy of `wing.vertex` whose content hash the script **itself** verifies against the canonical source before proceeding — `wing.vertex` gets script-internal verification because it is the one artifact with a documented history of silently drifting; `inputs/`/the manifest rely on the replace-not-merge behavior (below) plus `cp`'s own failure under `set -euo pipefail` — and this provisioning completes before the stub `argo` is ever invoked

#### Scenario: A dropped config does not survive provisioning (replace, not merge)

- **Given** a `--workspace-hostpath` whose `inputs/` already contains a deck for a config that no longer exists in the current `--corpus-dir` (e.g. a config dropped when the corpus grid changed)
- **When** provisioning runs
- **Then** that stale deck is gone from the resulting `inputs/` afterward — provisioning replaces the destination's `inputs/` wholesale rather than only adding/overwriting matching filenames, so a shrunk or changed corpus can never leave an orphaned, silently-stale deck behind (the same failure class as a stale `wing.vertex`, just for `inputs/`)

#### Scenario: `smoke` provisions without requiring a manifest

- **Given** a `--corpus-dir` containing `inputs/` but no `sweep_manifest.json` (a lone deck being smoke-tested ad hoc, before any manifest exists)
- **When** `submit_workflow.sh smoke` runs
- **Then** provisioning succeeds (copying `inputs/` and `wing.vertex` only) and the stub `argo` is invoked — `smoke` never requires the manifest, unlike `full`

#### Scenario: The default cluster-to-local path translation is exactly right

- **Given** `CLUSTER_NFS_PREFIX`/`LOCAL_NFS_PREFIX` left at their real-world defaults (not overridden by a test — the script is sourced directly so the translation function is called with production defaults, not a test-substituted prefix pair)
- **When** the path-translation function is applied to `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep`
- **Then** it returns `/mnt/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep` exactly — a pure string-substitution check requiring no real filesystem or mount, since the real mount can't be exercised in CI

#### Scenario: A sibling cluster export sharing the prefix string is not mistranslated

- **Given** a hostpath under a *different* cluster export that happens to share `CLUSTER_NFS_PREFIX` as a string prefix but not as a path component (e.g. `/hpi/hpi_dev_archive/...` against the default `/hpi/hpi_dev` prefix)
- **When** the path-translation function is applied
- **Then** it returns the input unchanged (no translation applied) rather than silently rewriting it under `LOCAL_NFS_PREFIX`'s tree, which has no relationship to that sibling export — the prefix match is anchored on a path-component boundary (exact match or followed by `/`), not a bare string prefix

#### Scenario: A missing corpus-dir, a corpus-dir that is a file, or a corpus-dir missing inputs/, fails before any cluster action

- **Given**, separately: a `--corpus-dir` that does not exist at all; a `--corpus-dir` path that exists but is a file, not a directory; and a `--corpus-dir` that exists but whose `inputs/` subdirectory does not
- **When** `submit_workflow.sh full` runs for each
- **Then** each fails with a clear, **distinguishable** error (naming which condition applies — nonexistent vs. not-a-directory vs. missing `inputs/`), and the stub `argo` is never invoked for any of them (mirrors the existing `--parallelism` "fails before touching anything" convention)

#### Scenario: `full` additionally requires a manifest and its units sidecar; `smoke` does not

- **Given**, separately, a `--corpus-dir` containing `inputs/` but no `sweep_manifest.json`, and one containing `sweep_manifest.json` but no `sweep_manifest.units.json`
- **When** `submit_workflow.sh full` runs for each
- **Then** each fails with a clear error naming the specific missing file, before any copy or the stub `argo` is invoked — distinct from the `smoke` scenario above, where the identical corpus-dir provisions successfully because `smoke` never requires either manifest file

#### Scenario: A `--corpus-dir`/`--workspace-hostpath` pair resolving to the same real path is rejected before any deletion

- **Given** a `--corpus-dir` and a `--workspace-hostpath` that either are the identical literal
  path, or are two differently-spelled paths (e.g. one with a trailing slash, or a `./`-relative
  spelling) that resolve to the same real directory
- **When** `submit_workflow.sh full` (or `smoke`) runs
- **Then** it fails fast with a clear, `die`-style error message before any filesystem mutation
  — in particular, before the `rm -rf` that would otherwise delete the corpus's own `inputs/`
  before the subsequent `cp -r` could read from it — and the corpus directory's `inputs/`
  contents are verified to still exist on disk afterward, not just that the command exited
  non-zero
