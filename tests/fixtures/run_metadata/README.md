# `run_metadata` test fixtures

Cluster-free TDD fixtures for `tests/test_metadata_capture.py` (OpenSpec change
`automate-run-metadata-capture`). All values here are cross-checked against the real,
already-committed, already-corrected pilot config `s35_f085_p45`
(`examples/prelim_sweep_fine_pilot/`) as **read-only ground truth** — nothing here is ever
written back to that directory.

- `forces_s35_f085_p45.csv` — exact copy of the committed force CSV. Last row:
  `iStep=4705, time=2.3525` (one `dt=0.0005` short of the deck's `stop_time=2.352941176...`).
- `sweep_manifest.json` — exact copy of the committed manifest (per-config kinematics/reynolds/
  max_step; note `dt` is the manifest-level nominal, not per-config).
- `inputs.3d.s35_f085_p45` — exact copy of the committed deck (source of `amr.n_cell` /
  `ns.fixed_dt`, which are **not** in the manifest).
- `pod_run_metadata.json` — a hand-reconstructed pod-side `run_metadata.json` matching the real
  shape `capture_surrogate_run_metadata`/`capture_run_metadata` produce (see
  `src/mosquito_cfd/benchmarks/metadata.py`, `src/mosquito_cfd/force_surrogate/sidecar.py`,
  `run_one_config.py`'s `_write_run_metadata`). Uses the real git commit SHA and image digest from
  the committed `run_metadata_s35_f085_p45.json`. `rows=4706` matches the CSV's row count.
- `run.log` — synthetic excerpt with a realistic AMReX "The Arena" max-used line (`7998 MiB`,
  matching the figure in `docs/force_surrogate/fine-grid-pilot-report.md`). The exact AMReX log
  line format is not verified against a real captured `run.log` (none is committed — it's
  gitignored); `metadata_capture.parse_arena_max_mib`'s regex is intentionally tolerant of MiB/MB
  and "Arena ... used ... N" phrasing rather than pinned to this exact string.
- `argo_status_simple.json` — a canned `argo get <name> -o json`-shaped response with one
  `Succeeded` node, `startedAt`/`finishedAt` spanning exactly `s35_f085_p45`'s real committed
  `timing.wall_time_s` (`9448.466969`).
- `argo_status_with_retry.json` — a canned response with one `Failed` Pod node, one `Succeeded`
  Pod node, AND a `Succeeded` `"type": "Retry"` wrapper node (matching real Argo's node model for
  a step with `retryStrategy`, as `cluster/argo/workflow-templates/force-surrogate-single-config.yaml`
  configures) whose `startedAt` spans back to the first (failed) attempt but whose `finishedAt`
  ties the real successful attempt's. Tests both that `wall_time_s` reflects only the final
  successful **Pod** attempt's duration (not the full span including the failed attempt) and that
  the `Retry` wrapper node is excluded rather than winning the tie. Not tied to a real pilot
  config (synthetic workflow/pod names).
- `argo_status_multi_config.json` — a canned response modeling a multi-config fan-out sweep
  (issue #65), with **three** distinct `Succeeded` `Pod`-type nodes keyed by three distinct pod
  names (following the real `force-surrogate-sweep-vb8t5` naming pattern), each with a
  sequential, non-overlapping `startedAt`/`finishedAt` window: `...-1111111111` (1800s),
  `...-2222222222` (3600s), `...-3333333333` (9200s, both the longest-duration AND the
  latest-finishing of the three). Used to prove that pod-scoped lookup in `compute_wall_time_s`
  selects the correct node matching a given `pod_name` — e.g. `...-2222222222`'s own 3600s
  duration — rather than the unfiltered global maximum across the whole workflow (which would
  wrongly return `...-3333333333`'s 9200s for every config sharing this workflow).

Test data only — do not import fixtures from anywhere outside `tests/`.
