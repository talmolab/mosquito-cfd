## MODIFIED Requirements

### Requirement: Argo sweep-submission parallelism is overridable without mutating the committed workflow

`cluster/argo/scripts/submit_workflow.sh`'s `full` command SHALL accept an optional `--parallelism`
flag that overrides the submitted workflow's concurrency without editing the checked-in workflow
file — since Argo's `spec.parallelism` is a hardcoded `int` field with no `{{...}}`
parameter-templating support (see this capability's base spec, "Concurrency and total runtime are
bounded," which this requirement is additive to, not a replacement for) and `argo submit` provides
no CLI override for it. When the flag is supplied, the script SHALL apply the override by submitting an anchored,
self-verifying `sed`-patched temporary copy of the workflow file, leaving the committed file
unchanged on disk. When the flag is **omitted**, the script SHALL submit the committed workflow
file unpatched — there is no separate hardcoded default that could drift from the committed
file's actual value. This requirement is a sibling of, and independent of, "Argo sweep-submission
provisions the NFS workspace before submitting" (below) — the two flags compose freely and neither
implies the other.

#### Scenario: `--parallelism` overrides concurrency without touching the committed file

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 1`
- **When** the command runs
- **Then** the sed-patched temporary copy of the workflow that would be passed to `argo submit`
  has `parallelism: 1`, and `cluster/argo/workflows/force-surrogate-sweep.yaml` on disk is
  byte-identical (same `sha256`) before and after the command runs — this is verified cluster-free
  (a stub `argo` executable capturing what it was invoked with), not against a live cluster

#### Scenario: Omitting `--parallelism` is a true no-op, not a re-patch with a hardcoded default

- **Given** `cluster/argo/scripts/submit_workflow.sh full` invoked with no `--parallelism` flag
- **When** the command runs
- **Then** the committed `force-surrogate-sweep.yaml` is passed to `argo submit` **unpatched** —
  no temporary file is created at all — so its `parallelism: 3` is whatever the committed file
  actually says, not a second, independently-hardcoded "3" in the shell script that could silently
  diverge if the committed value is ever changed

#### Scenario: An invalid `--parallelism` value is rejected before any file is touched

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (or a negative or
  non-integer value, e.g. `-1` or `abc`)
- **When** the command runs
- **Then** it fails fast with a clear error before creating any temporary file or invoking `argo
  submit`, and the committed workflow file is untouched

#### Scenario: A failed substitution is never silently submitted

- **Given** the workflow file's top-level `parallelism: <N>` line is missing or does not match
  the expected anchored pattern (e.g. the line was reformatted)
- **When** `--parallelism` is supplied
- **Then** the script fails with a clear error rather than submitting an unpatched temporary copy
  that would silently run at the wrong concurrency

#### Scenario: `--parallelism` and provisioning compose without interfering with each other

- **Given** `cluster/argo/scripts/submit_workflow.sh full --parallelism 0` (an invalid value) with a valid, current corpus-dir/workspace-hostpath pair
- **When** the command runs
- **Then** it still fails fast on the invalid `--parallelism` value before invoking the stub `argo`, and provisioning's copy step (if it already ran) has no bearing on that rejection — an invalid `--parallelism` is not masked or bypassed by provisioning having succeeded first

### Requirement: Re-normalization preserves surrogate skill (scale-invariance)

Re-deriving force/moment coefficients under a different per-configuration convention SHALL rescale
the CFD targets and the surrogate predictions by the **same** constant, leaving the held-out **R²**
and the predicted-vs-CFD relationship invariant. The frozen corpus's raw force/moment columns and
IB-particle CSVs SHALL NOT be regenerated for a re-normalization convention change; only derived
coefficients change, and no surrogate retraining SHALL be required for that case. This
frozen-corpus guarantee has exactly **one** documented exception: `fix-force-surrogate-sweep-hinge`
regenerated the raw corpus once to correct a wing-hinge geometry defect present in every
configuration since the corpus was first generated (the hinge was frozen from a pre-refactor deck
against a geometry file that had since moved to a new axis convention). That regeneration is not a
precedent for routine re-runs — any future raw-corpus regeneration requires its own equally
explicit, equally documented exception.

#### Scenario: R² is invariant under re-normalization

- **Given** the committed `examples/prelim_sweep/surrogate/holdout_predictions.parquet` (`CF_x_true/pred`, `CF_z_true/pred`, …) whose `R²` matches `metrics.json`
- **When** both the `*_true` and `*_pred` columns are multiplied by the convention factor `k = f_ref_old / f_ref_new` (≈ 3.119)
- **Then** the recomputed per-target `R²` for `CF_x` and `CF_z` each equals the original within `1e-9`, confirming no retrain is needed
- **And** the `RMSE`/`MAE` rescale by exactly `k` (reported honestly), while the scatter shape is unchanged (axes relabeled)

#### Scenario: Raw corpus stays frozen under re-normalization; only derived coefficients move

- **Given** a re-normalization convention change (not a geometry-defect fix) re-derives the corpus coefficients
- **When** `dataset.parquet` is regenerated
- **Then** its raw `Fx, Fy, Fz, Mx, My, Mz` column **values** are exactly equal (e.g. `pandas.testing.assert_frame_equal(..., check_exact=True)`) to the committed corpus, only the derived `CF_*` columns change (each new column equals the old divided by `k`), and the committed `metrics.json` per-target `R²` is reused unchanged (within `1e-9`)

#### Scenario: Degenerate re-normalization is rejected

- **Given** a convention factor that is undefined — `f_ref_new = 0` (so `k` divides by zero) or a `holdout_predictions.parquet` missing a required `CF_*_true`/`CF_*_pred` column
- **When** the scale-invariance check is run
- **Then** it raises `ValueError` (or `KeyError` for the missing column) rather than emitting `inf`/`NaN` R² or silently skipping the target

#### Scenario: A documented geometry-defect fix is the sole exception to the frozen-corpus guarantee

- **Given** the corpus's raw force columns were generated from a deck with an incorrect wing-hinge placement (a geometric defect, not a normalization-convention choice)
- **When** the corpus is regenerated to fix that defect
- **Then** the regeneration is accompanied by an OpenSpec change (`fix-force-surrogate-sweep-hinge`) that names the defect, and this requirement's "SHALL NOT be regenerated" clause is understood to apply to normalization-convention changes, not to this documented correctness exception

## ADDED Requirements

### Requirement: Sweep base deck hinge is geometrically consistent with the wing geometry

Every hand-authored sweep base deck SHALL place `particle_inputs.hinge_{x,y,z}` at the wing's own
**root** along the geometry's actual span axis — this applies to
`examples/prelim_sweep/base_inputs.3d.validation` and
`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` — derived from the referenced
`particle_inputs.geometry_file` marker extent — **not** merely matched by byte-identity to another
committed file. Along the span axis, the hinge-to-centre arm SHALL equal the geometry's own
half-span (from its marker extent) within a documented tolerance; along the two non-span axes, the
hinge SHALL exactly equal the wing centre (`particle_inputs.{x,y,z}`) — no spurious offset. This
guard is independent of, and in addition to, any byte-identity/deck-invariance guard elsewhere in
this spec, precisely because byte-identity alone cannot detect a value that is self-consistently
wrong.

#### Scenario: Coarse and fine base decks place the hinge at the span root

- **Given** `examples/prelim_sweep/base_inputs.3d.validation`, `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`, and the committed `examples/flapping_wing/wing.vertex`
- **When** each deck's hinge is checked against the vertex file's marker extent along the span axis (y)
- **Then** each deck's `hinge_y` arm from `particle_inputs.y` equals the vertex file's own half-span within tolerance, and `hinge_x`/`hinge_z` exactly equal `particle_inputs.x`/`particle_inputs.z`

#### Scenario: The live validation deck already satisfies the guard (calibration baseline)

- **Given** `examples/flapping_wing/inputs.3d.validation` (never affected by the bug this guard targets)
- **When** the same geometric-consistency check is applied to it
- **Then** it passes, confirming the guard's tolerance is calibrated against a known-correct deck and not merely tuned to accept the corrected sweep decks

#### Scenario: A midspan-pivot hinge is rejected

- **Given** a synthetic deck whose hinge equals the wing centre along the span axis (zero arm — the pre-fix defect's exact shape)
- **When** the geometric-consistency check is applied
- **Then** it raises / reports failure, naming the expected vs actual span arm

#### Scenario: A spurious non-span-axis offset is rejected

- **Given** a synthetic deck whose span-axis hinge arm correctly equals the geometry's half-span, but whose non-span-axis hinge coordinate (e.g. `hinge_z` when the span axis is y) differs from the wing centre (`particle_inputs.z`) by a nonzero offset — the second, independently wrong half of the original defect's exact shape (`hinge_z = 2.5` against a wing centre `z = 4.0`)
- **When** the geometric-consistency check is applied
- **Then** it raises / reports failure, naming the offending non-span axis and the expected-vs-actual coordinate — a deck can fail this scenario while passing the span-arm scenario above, and both checks are required independently

### Requirement: Cluster-free wing-phase geometric diagnostic

The force-surrogate module SHALL provide a reusable, parameterized function that renders a sweep
configuration's wing-marker positions at four phases of one wingbeat (t = 0, T/4, T/2, 3T/4) in the
stroke plane, computed from the configuration's kinematics, hinge, and `wing.vertex` alone — no CFD
run, plotfile, or force CSV required. It SHALL use the canonical
`mosquito_cfd.benchmarks.wing_kinematics` rotation functions (not a re-derived rotation), and SHALL
emit the same three-artifact provenance convention as the evidence figure: `<name>.png`,
`<name>_metrics.json` (the numeric span-arm/hinge values the figure displays, matching the
geometric-consistency guard's own computation), and a `run_metadata.json` via
`capture_surrogate_run_metadata`. A thin CLI driver SHALL default to a documented representative
sample of configurations (not all 54, since the kinematics amplitude/frequency doesn't affect
hinge correctness) with an explicit `--config all` override, and the sampling choice SHALL be
documented in the figures README (no silent caps).

#### Scenario: Diagnostic figure matches the geometric-consistency guard's own numbers

- **Given** a sweep configuration and the committed `wing.vertex`
- **When** the wing-phase diagnostic is built for that configuration
- **Then** its `<name>_metrics.json` span-arm and hinge values are numerically identical to what the geometric-consistency guard (this spec) computes for the same deck — the figure and the automated check are provably checking the same underlying geometry, not two independently-tunable numbers

#### Scenario: Runs without any CFD output present

- **Given** a sweep configuration's input deck and `wing.vertex`, with no force CSV, plotfile, or cluster access available
- **When** the wing-phase diagnostic is built
- **Then** it succeeds, using only the deck's kinematics/hinge parameters and the geometry file

#### Scenario: Default sample is documented, not silent

- **Given** the CLI driver invoked with no `--config` argument
- **Then** it renders a documented, named subset of configurations (not all 54) and states in its own `--help` text and the figures README which configurations are included and why

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
workspace). It fails fast and loudly rather than causing the submitted workflow's pods to retry a
mount for hours (issue #62) or, worse, silently run against stale or mismatched geometry.
Provisioning SHALL default to on and SHALL be skippable via an explicit `--no-provision` flag for
an operator who has already verified the workspace is current. This is additive to, and
independent of, the existing `--parallelism` override — sibling requirements, not a replacement for
either (cross-referenced from both requirements' descriptions, not a one-way pointer).

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

#### Scenario: A missing canonical `wing.vertex` source fails clearly

- **Given** `WING_VERTEX_SOURCE` resolving to a path that does not exist
- **When** provisioning runs
- **Then** it fails with a clear error naming the missing source, before the stub `argo` is invoked — not a bare `cp: cannot stat` message

#### Scenario: A corpus-dir/workspace-hostpath basename mismatch is rejected

- **Given** `--corpus-dir examples/prelim_sweep` (the coarse corpus) together with `--workspace-hostpath .../examples/prelim_sweep_fine` (the fine corpus's path) — the exact mistake of overriding one flag without the other
- **When** `submit_workflow.sh full` runs
- **Then** it fails with a clear error naming both mismatched paths, before any copy or the stub `argo` is invoked

#### Scenario: `--no-provision` skips the copy but still submits

- **Given** `submit_workflow.sh full --no-provision`, with a `--workspace-hostpath` that already contains different content than the local corpus-dir
- **When** the command runs
- **Then** the workspace-hostpath's existing content is left unchanged (no copy attempted), and the stub `argo` is still invoked with the submission proceeding normally

#### Scenario: Provisioned `wing.vertex` always matches the canonical file, independent of which corpus-dir is used

- **Given** at least two different `--corpus-dir`/`--workspace-hostpath` pairs (coarse and fine), neither of which carries its own committed `wing.vertex`
- **When** provisioning runs for each independently
- **Then** each resolved workspace's `wing.vertex` is byte-identical to the single canonical `examples/flapping_wing/wing.vertex`, never a different or stale copy, **for every corpus-dir tested** — this is the specific defect this requirement exists to prevent (this session found the live coarse corpus's NFS `wing.vertex` did not match any git-committed version)

#### Scenario: The script's own hardcoded defaults name the same corpus

- **Given** `submit_workflow.sh`'s built-in `CORPUS_DIR` and `WORKSPACE_HOSTPATH` defaults, with neither overridden
- **When** their basenames are compared
- **Then** they match — a static guard so a future edit to only one default (exactly the failure class this requirement fixes) is caught before it ever reaches the runtime basename-mismatch check on a real submission

#### Scenario: `--help` documents the new flags

- **Given** `submit_workflow.sh help`
- **When** the command runs
- **Then** its output names both `--corpus-dir` and `--no-provision`

### Requirement: Corpus-generation CLI drivers require an explicit timestamp

Both corpus-generation CLI drivers SHALL require `--timestamp` as an explicit, ISO-8601-validated
CLI argument with **no default value** — this applies to `examples/prelim_sweep/generate_sweep.py`
and `examples/prelim_sweep_fine/generate_full_corpus.py`. A real regeneration run must supply a
fresh, caller-chosen, well-formed timestamp — never silently reuse a literal from the script's
original authoring session (which would misleadingly stamp a corrected corpus's provenance as if
generated on the original, pre-fix date), and never accept an empty or malformed value that
`required=True` alone would not catch.

#### Scenario: Omitting `--timestamp` is rejected

- **Given** either driver invoked with no `--timestamp` argument
- **When** `main()` parses arguments
- **Then** it exits non-zero via argparse's own "required argument" error, before any file is read or written

#### Scenario: An empty or malformed `--timestamp` value is rejected

- **Given** either driver invoked with `--timestamp ""` or a non-ISO-8601 string (e.g. `"not-a-timestamp"`)
- **When** `main()` parses arguments
- **Then** it exits non-zero before any file is read or written — presence of the flag alone is not sufficient; the value must parse as ISO-8601

#### Scenario: A frozen-path rejection is not masked by the timestamp requirement

- **Given** a CLI invocation with `--output` pointed at a frozen/protected path (e.g. the committed pilot directory) **and** an explicit, valid `--timestamp` supplied
- **When** `main()` runs
- **Then** it exits via the frozen-path guard's own `SystemExit` (naming the protected path), not via a missing-`--timestamp` argparse error — the two guards are independently reachable, and supplying `--timestamp` is what makes that possible to observe
