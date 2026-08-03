## Why

`add-fine-grid-training-pilot` (PR #58, merged) proved fine-256³ CFD is CFL-stable across this
sweep's kinematic range at the standard `dt=5e-4` — all 3 pilot configs (pitch=45° only)
completed with no fallback needed — and measured a real, per-step-constant cost rate (~2.01
s/step), projecting the full 27-config regeneration at **~61.2 hours (~2.55 days)** serial
single-A40 wall time. `automate-run-metadata-capture` (PR #59, merged) built the tool
(`metadata_capture.assemble_run_metadata` / `scripts/generate_run_metadata.py`) needed to
generate all 27 `run_metadata_<config>.json` files without hand-authoring — the pilot's own 3
hand-authored files had a `final_time` bug and a truncated-SHA bug, exactly the class of mistake
the new tool exists to prevent.

Both pilot gates are now cleared. What remains before the actual 27-config regeneration can be
submitted is scaffolding: a deck-generation driver for the full grid (the pilot's own script is
hardcoded to 3 configs and `n_holdout=0`), and a way to run the existing fan-out Argo workflow at
`parallelism=1` (serial) instead of its committed default of `3`, since talmo-lab's RunAI quota
is at 176.73% allocation (35.35/20.00 GPUs, confirmed today) — the same pressure the pilot
succeeded under with zero preemptions, and the preemption/retry path is still otherwise
unverified.

## What Changes

This proposal delivers the **cluster-free scaffolding** only — generating and committing the 27
decks/manifest (no GPU time required) and the submission tooling needed for the future live run.
It does **not** submit the actual cluster workflow (see Non-goals; not repeated below).

- New `examples/prelim_sweep_fine/generate_full_corpus.py`: a thin driver over the unmodified
  `mosquito_cfd.force_surrogate.sweep.generate_sweep()`, mirroring
  `examples/prelim_sweep_fine_pilot/generate_pilot.py`'s shape (`argparse` `--output`/
  `--timestamp`, a `_validate_output_dir` isolation guard) but calling `generate_sweep()` with
  **no** `configs=`/`n_holdout=` override — `configs` defaults to `build_kinematic_grid()`'s full
  27-point grid, `n_holdout` defaults to `N_HOLDOUT=6` (valid against 27 configs, unlike the
  pilot's degenerate 3-config case which needed `n_holdout=0`). Points at the already-committed
  `examples/prelim_sweep_fine_pilot/base_inputs.3d.fine` (reused unmodified — no new base deck).
  Output tree: `examples/prelim_sweep_fine/` (matches the path already used in
  `scripts/generate_run_metadata.py`'s own docstring example).
- Run the new script and **commit its output** — 27 decks (`inputs/inputs.3d.*`),
  `sweep_manifest.json`, `sweep_manifest.units.json`, `sweep_provenance.json` — the same
  lightweight, deterministic artifacts the pilot committed for its 3 configs (confirmed via `git
  ls-files examples/prelim_sweep_fine_pilot/`: decks and manifests are committed, only `runs/` —
  the heavy per-run CFD output — is gitignored, and that pattern already generalizes to
  `examples/prelim_sweep*/runs/`, covering this new directory with no `.gitignore` change needed).
- New `--parallelism` flag on `cluster/argo/scripts/submit_workflow.sh`'s `full` command: Argo's
  `spec.parallelism` is a hardcoded `int` field with no `{{...}}` templating support, and `argo
  submit --help` confirms there is no CLI override for it. The flag has **no default** — when
  omitted, `full` submits the committed `force-surrogate-sweep.yaml` unchanged, exactly as today;
  only when explicitly passed does the script sed-patch an anchored, self-verifying temp copy and
  submit that instead (see `design.md` D4 for the exact mechanism and why an earlier "always patch
  with a hardcoded default of 3" draft was rejected as a second, driftable source of truth) —
  purely additive, no change to the checked-in workflow file either way.
- OpenSpec: an `ADDED Requirements` delta on the `force-surrogate` capability (see
  `specs/force-surrogate/spec.md` in this change), analogous to the pilot's own 5 additions.

## Non-goals (explicit)

- **Does not submit the actual 27-config cluster workflow.** That is a separate, later,
  explicitly-confirmed operator action after this PR merges — ~2.55+ days of GPU time on shared
  lab infrastructure is not something to run on a general go-ahead for the whole plan.
- **Does not add any CFL-fallback tooling** for the 18 untested pitch=30°/60° configs (the pilot
  only stress-tested pitch=45°). Decision: keep the fallback fully manual, exactly like the
  pilot's own `design.md` D6 — if a config diverges at `dt=5e-4`, hand-maintain a second base deck
  with `ns.fixed_dt=0.00025` and regenerate just that one config via `generate_sweep(configs=[
  that_config], dt=2.5e-4)`. No code is added for a fallback that, per the pilot's own evidence
  (0 of 3 configs needed it), may never be exercised. Documented as a runbook in `design.md`.
- Does not modify `generate_sweep()`, `sweep.py`, or any pod-runtime code
  (`run_one_config.py`/`runner.py`/`sidecar.py`).
- Does not touch `examples/prelim_sweep/` (frozen coarse corpus) or
  `examples/prelim_sweep_fine_pilot/` (pilot, already committed).
- Does not hand-author any `run_metadata_*.json` — the actual 27-config metadata generation
  (after cluster runs complete) uses `scripts/generate_run_metadata.py` per config, out of scope
  here because it depends on cluster-run artifacts this proposal does not produce.
- Does not change `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`'s GPU/
  memory/`retryStrategy` settings.

## Impact

- Affected specs: `force-surrogate` (`ADDED Requirements` delta).
- Affected code: new `examples/prelim_sweep_fine/generate_full_corpus.py` +
  `tests/test_full_corpus_deck.py`; one new `--parallelism` flag in
  `cluster/argo/scripts/submit_workflow.sh` (including its usage-header doc) + new
  `tests/test_submit_workflow_parallelism.py`; the `ci.yml` lint-path list (adds
  `examples/prelim_sweep_fine/`); `openspec/project.md` (Current State bullets).
- New committed data: `examples/prelim_sweep_fine/` — 27 decks, `sweep_manifest.json`,
  `sweep_manifest.units.json`, `sweep_provenance.json` (lightweight, deterministic; no CFD output
  yet). `examples/prelim_sweep_fine/runs/` is already covered by the generalized
  `examples/prelim_sweep*/runs/` `.gitignore` pattern.
- Cluster cost: **none** for this proposal (cluster-free scaffolding only). The deferred future
  submission is ~61.2h/~2.55 days serial single-A40, requiring my separate, explicit go-ahead.
