## ADDED Requirements

### Requirement: Full fine-grid corpus decks reuse the unmodified sweep generator with default grid and holdout

The 27 full-corpus decks SHALL be produced by calling the existing, unmodified
`mosquito_cfd.force_surrogate.sweep.generate_sweep()` against the pilot's already-committed fine
base deck (`examples/prelim_sweep_fine_pilot/base_inputs.3d.fine`) with **no** `configs=` or
`n_holdout=` override — `configs` SHALL default to `build_kinematic_grid()`'s full 27-point
Aedes grid and `n_holdout` SHALL default to `N_HOLDOUT` (6), unlike the pilot's forced
`n_holdout=0` (which was required only because 3 configs cannot support a 6-config holdout). No
new base deck and no changes to `sweep.py` itself.

#### Scenario: Full corpus generation uses the default 27-config grid and a non-degenerate holdout

- **Given** the fine base deck and no `configs=`/`n_holdout=` arguments supplied
- **When** `generate_sweep()` runs
- **Then** the resulting `sweep_manifest.json` has exactly 27 configs matching
  `build_kinematic_grid()`'s own `stroke_amp_deg`/`frequency_fstar`/`pitch_amp_deg` axes, and
  `manifest["holdout"]["n_holdout"] == 6` with a non-empty `config_names` list

#### Scenario: Full corpus decks are byte-reproducible

- **Given** the fine base deck and the default 27-config grid
- **When** `generate_sweep()` is called twice with identical arguments (aside from the
  caller-supplied timestamp)
- **Then** the two runs produce byte-identical `inputs/inputs.3d.<name>` deck files and an
  identical `sweep_manifest.json`

### Requirement: Full fine-grid corpus artifacts are isolated from the frozen coarse corpus and the pilot

Nothing generated for the full corpus SHALL write into, modify, or otherwise touch
`examples/prelim_sweep/` (the frozen coarse corpus) or `examples/prelim_sweep_fine_pilot/` (the
already-committed pilot). All full-corpus artifacts (generated decks, manifests, and — once the
future cluster run completes — force CSVs and run metadata) SHALL live under a separate
`examples/prelim_sweep_fine/` directory, and cluster submission SHALL target a full-corpus-
specific `WORKSPACE_HOSTPATH`, distinct from both the coarse corpus's and the pilot's.

#### Scenario: Full corpus output directory and workspace path are statically distinct from both the coarse corpus's and the pilot's

- **Given** the full-corpus generation script's output-directory constant and its configured
  `WORKSPACE_HOSTPATH`
- **When** each is compared against `examples/prelim_sweep/` and
  `examples/prelim_sweep_fine_pilot/` and their respective NFS hostpaths — as a static check, not
  one that requires actually running generation
- **Then** all four comparisons are confirmed distinct strings/paths before any generation happens

#### Scenario: The output directory guard rejects both frozen paths

- **Given** the full-corpus generation script's `_validate_output_dir` guard
- **When** it is called with `examples/prelim_sweep/` or `examples/prelim_sweep_fine_pilot/` as
  the requested `--output`
- **Then** it raises `ValueError` for both, and does not raise for the script's own real
  `OUTPUT_DIR`

#### Scenario: The CLI rejects a frozen-path `--output` without generating anything

- **Given** the full-corpus script's `main()` invoked with `--output` pointed at a decoy standing
  in for a frozen path (via a monkeypatched constant, never the real coarse-corpus or pilot
  directory)
- **When** `main()` runs
- **Then** it raises `SystemExit` before calling `generate_sweep()` — the guard's `ValueError` is
  converted to a `parser.error()` at the CLI boundary, exactly as the pilot's own
  `generate_pilot.py` does

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
file's actual value.

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
