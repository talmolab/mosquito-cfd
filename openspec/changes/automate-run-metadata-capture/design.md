# Design: automate run-metadata capture

## D1 — Post-run CLI, not pod instrumentation

Two real options were considered for where the automated generator plugs in:

1. **Post-run CLI** (chosen): reads already-existing artifacts (the pod's own gitignored
   `run_metadata.json`, the committed force CSV, `run.log`, the sweep manifest/deck) plus one
   read-only Argo workflow-status query for wall-clock timing. Touches no cluster-execution code.
2. **Instrument `run_one_config.py`**: add a wall-clock timer around the `mpi_runner` call and a
   `--workflow-name` CLI arg, so the pod's own `run_metadata.json` is already schema-complete and
   just needs copying/renaming to commit.

Chosen (1) because it keeps this change fully cluster-execution-code-free and unit-testable
without any live cluster access — the pod's runtime behavior (and the Argo WorkflowTemplate that
drives 27 real GPU jobs in the follow-on) stays untouched and unproven-code-free. The cost is one
external dependency at generation time: a working `argo`/`kubectl` session to query the completed
workflow's status. This is a read of **persisted, post-completion** status (not a live `pods/exec`
probe — the RBAC gap that blocks live `nvidia-smi` calls does not apply here), and `workflow-name`
is already known to the human running this tool from their own submission step, so no new
Argo-facing wiring is needed anywhere.

## D2 — Schema normalization, not backward compatibility

The current schema is inconsistent across two lineages:

| | t3c/t3b/t2a (`examples/flapping_wing/`) | pilot (`examples/prelim_sweep_fine_pilot/`) |
|---|---|---|
| Docker identity | `docker_image` (tag) + `image_digest` (separate key) | `docker_image` (digest, per `capture_surrogate_run_metadata`) |
| Provenance narrative | `image_tag`, `image_build`, `iamrex_commit` (free text) | none |
| Run context | `run_platform` (free-text narrative), `analysis_host` | `run_platform` (free-text narrative), `kinematics`, `orchestration`, `tier` |

Both lineages hand-author a free-text `run_platform` paragraph, and the t3c lineage's
`docker_image`/`image_digest` split doesn't match what the code that actually validates digests
(`capture_surrogate_run_metadata` / `validate_image_digest`) does — the schema and the code
disagree. Chosen: **normalize** to one clean, fully-structured schema for all future runs (fixing
both issues by construction) rather than preserving either lineage's shape. New files will not
byte-match old ones. `examples/flapping_wing/run_metadata_{t3c,t3b,t2a}.json` are left alone (not
blocking, different tier, out of scope per the proposal's non-goals).

The free-text `run_platform` narrative is replaced with structured, independently-derived fields:
- `stability`: `"stable_at_<dt>"` or similar, derived from the deck's `fixed_dt` and whether a
  CFL fallback was recorded (not re-derivable from `dt_reduced` alone if that flag itself was
  previously hand-set — see the manifest/deck sourcing in D3).
- `arena_max_mib`: parsed from the AMReX end-of-run "The Arena" line in `run.log`.
- `node`, `gpu_model`: from the pod's own `run_metadata.json` (`orchestration.node`) and hardware
  probe respectively.

One optional `notes` field remains for genuinely exceptional human commentary (e.g. explaining an
unusual truncated final step, as seen in `s35_f085_p45`'s benign last-step DT truncation) — it
must be omittable and is never required for a normal run, so it does not reintroduce the
hand-authoring failure mode this change removes.

## D3 — Sourcing kinematics/grid/fixed_dt from the manifest, not re-deriving them

`stroke_amp_deg`, `frequency_fstar`, `pitch_amp_deg`, `reynolds`, `amr.n_cell` (grid), and
`fixed_dt` are already present, per-config, in the committed `sweep_manifest.json` (or readable
directly from the generated deck file). The generator reads them from there rather than requiring
them as CLI arguments or re-deriving them from the CSV — this is the same "derivable, not
hand-typed" principle applied to config-time data instead of run-time data.

## D4 — Validation oracle: the 3 already-corrected pilot files, cluster-free

The 3 committed, already-hand-corrected `run_metadata_<config>.json` files plus their committed
force CSVs and manifest are sufficient ground truth to TDD this tool without any live cluster
access: tests feed the tool fixture copies of a pod-side `run_metadata.json`, a `run.log`, a force
CSV, and a canned Argo status-query response, and assert the tool reproduces the already-verified
values (`final_time`, full-SHA git commit, kinematics) for at least one of the 3 pilot configs.

**Open question, resolved during implementation:** whether to also run the new tool against the
real pilot artifacts (the actual `run_metadata.json` off the NFS run dir, the actual `run.log`,
etc., if still available) and replace the 3 committed pilot files with the tool's normalized-schema
output, proving real-world round-trip equivalence rather than only fixture-level equivalence. If
the underlying pod-side artifacts are no longer available (the `runs/` tree is gitignored and may
have been cleaned up), this is deferred and noted in `tasks.md` rather than silently skipped.
