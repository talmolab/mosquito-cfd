## Why

The Track B force-surrogate corpus must be produced by running PR2's 27-config sweep through the
pinned `:fp64` container on the A40 (PR3, `add-force-surrogate-sweep-runner`). The first real
full-corpus run via PR3's `scripts/run_sweep.py` driver produced **1 of 27 configs**. The
on-cluster root cause is fundamental to the transport, not a fluke:

- `scripts/run_sweep.py` runs on the operator's laptop and drives each config via
  `runai workspace exec`, which **blocks on a ~10-minute streaming connection**. That stream
  **drops intermittently** (config 1 held 11.5 min; config 2's stream `EOF`'d after ~4 min).
- When the exec stream drops, **RunAI does not kill the in-container `mpirun`** — the orphaned
  `amr3d` kept running and held **34 GB of the A40**, so every later config crashed on a busy GPU.
  A cascade: 1 completed, 26 failed.

The fix is to stop driving long GPU runs from a laptop over a fragile exec stream and instead run
**each config as its own pod whose main process *is* `mpirun`** — Kubernetes-managed, so there is
no exec stream to drop and no orphaned GPU process (pod teardown kills everything), with built-in
retries, running entirely cluster-side (no laptop/VPN dependency for the multi-hour bake). This is
exactly the **Argo Workflows + RunAI** pattern the lab already runs in production (`gapit3-gwas-pipeline`,
`sleap-roots-pipeline`).

## What Changes

### Extends capability: `force-surrogate`

- **New module `src/mosquito_cfd/force_surrogate/run_one_config.py`** — the per-pod work, reusing the
  transport-agnostic library (PR3's runner was built with a swappable executor seam, D5, for exactly
  this):
  - `run_config(*, name, input_file, max_step, output_root, docker_digest, timestamp, mpi_runner,
    container_workspace=…, wing_vertex=…, deck_path=None, iamrex_binary=…, csv_name=IB_PARTICLE_CSV,
    threshold=…, extra_provenance=None) -> RunOutcome` — the three per-run fields are **explicit keyword
    args**, not a `config` dict or a config framework (D7: only three scalars cross the single-run boundary;
    OmegaConf/pydantic rejected — new dep + image-rebuild coupling, and no composition/override/interpolation
    need). (`deck_path` defaults to `container_workspace/input_file`; it splits the deck's real
    hash-location from the portable recorded command path — see design "Why `deck_path`".)
    Stages `wing.vertex` into the run dir, invokes the **injected `mpi_runner`** (the
    testable seam — the real impl runs `subprocess.run(["mpirun","--allow-run-as-root","-np","1",
    <iamrex_binary>,<deck>], cwd=run_dir)`), writes `run.log`, re-uses `check_completion`, and writes a
    per-run `run_metadata.json` via `capture_surrogate_run_metadata` (pinned digest + `deck_sha256` +
    caller timestamp + **native A40 hardware** — the pod runs *on* the A40, so the base `nvidia-smi`
    probe is correct; **no in-container exec probe needed**, unlike PR3-#13's laptop case) plus the
    Argo provenance (`workflow_uid`, `pod`, `node`, `retry`) passed via `extra_provenance`.
  - `main(argv)` — argparse (repo convention, mirrors `extract_forces.py`/`run_sweep.py`), builds the
    real subprocess `mpi_runner`, and **exits non-zero when the run is incomplete** so Argo retries.
  - Re-uses (no change): `IB_PARTICLE_CSV`, `RUN_LOG`, `check_completion`, `_format_run_log`,
    `capture_surrogate_run_metadata`, `hash_file`, the module constants. **Does not** use
    `build_run_command`/`build_wsl_command` (no `runai exec` in the Argo path — the pod runs `mpirun`
    directly).
- **`cluster/argo/workflow-templates/force-surrogate-single-config.yaml`** — an Argo `WorkflowTemplate`
  (one CFD config): the `:fp64` image, `command:["/opt/cfd/mosquito-cfd/.venv/bin/python","-m",
  "mosquito_cfd.force_surrogate.run_one_config", …]` (the synced venv interpreter — **not** `uv run`,
  which would do a network/sync check on each of 27 pods); the prelim_sweep NFS hostPath mounted at
  `/workspace`; **`resources.limits: {nvidia.com/gpu: 1}`** (a full A40 — IAMReX FP64 uses ~34 GB, so no
  `gpu-fraction` sharing); **`securityContext: {runAsUser: 0}`** (`mpirun --allow-run-as-root`; **not**
  `privileged` — least-privilege, GPU works without it); **`retryStrategy: {limit: 5, retryPolicy:
  OnFailure, backoff: {duration: 2m, factor: 2, maxDuration: 30m}}`**; `metadata.annotations:
  {runai/preemptible: "true"}`; Argo provenance env via `fieldRef` (`POD_NAME=metadata.name`,
  `NODE_NAME=spec.nodeName`) + template params (`{{workflow.uid}}`, `{{retries}}`).
- **`cluster/argo/workflows/force-surrogate-sweep.yaml`** — the fan-out `Workflow`: DAG `validate`
  (runs the pinned image **before any GPU pod** and `import mosquito_cfd.force_surrogate.run_one_config`
  + checks the manifest — the **stale-digest fail-fast**) `→ extract-configs` (read
  `/workspace/sweep_manifest.json` via `load_manifest_configs` → emit the configs as a JSON parameter) `→
  withParam fan-out` over the configs `→ verify-complete` (run `check_completion` over **every** config's
  `IB_Particle_1.csv`, failing the workflow otherwise). Workflow-level hostPath `volumes`,
  `serviceAccountName: default` (mandatory for `workflowtaskresults`), namespace `runai-talmo-lab`, a
  **`parallelism` parameter defaulting to 3** (moderate concurrency), and `activeDeadlineSeconds: 86400`.
- **`cluster/argo/scripts/submit_workflow.sh` + `monitor_workflow.sh`** — thin wrappers mirroring gapit
  (`argo submit/get/logs` via WSL + `KUBECONFIG`, `-n runai-talmo-lab`, `--parameter`), pinning the
  image by `@sha256:` digest.

### Resolved decisions (see `design.md`)

- **D1 — Full-GPU request, run as root.** `resources.limits: {nvidia.com/gpu: 1}` (no `gpu-fraction` —
  IAMReX needs the whole A40) + `securityContext: {runAsUser: 0}`. Mirrors `sleap-roots-pipeline`
  (gapit is CPU-only).
- **D2 — Moderate concurrency.** `parallelism` parameter, default 3; Argo retries absorb preemption.
- **D3 — Tested module baked into `:fp64`.** `run_one_config.py` ships automatically (the image already
  `COPY src/` + `uv sync`s) — **no Dockerfile change**; `docker.yml` rebuilds on merge → the operator
  pins the new digest.
- **D4 — Scope: sweep only.** The Argo workflow produces the corpus (the failing part). PR4's
  `extract_forces.py → dataset.parquet` stays the downstream **local** step (already merged; the `:fp64`
  image doesn't ship `scripts/`). The in-workflow `verify-complete` only checks completeness — it does
  **not** build the parquet.
- **D5 — `run_sweep.py` stays a documented local/dev fallback;** Argo is the production path.

## Impact

- **Spec:** `force-surrogate` capability gains 2 requirements (single-configuration pod run — 8 scenarios
  incl. fail-fast malformed-config, raised-runner, and native-hardware; cluster-side Argo orchestration —
  6 scenarios incl. the stale-image guard, `check_completion` gating, and force-only negative scope).
- **New code:** `src/mosquito_cfd/force_surrogate/run_one_config.py`, `tests/test_force_surrogate_run_one_config.py`,
  `tests/test_argo_workflows.py` (text-assertion validation of the YAML, cluster-free); `__init__.py`
  re-export of `run_config`.
- **New infra:** `cluster/argo/{workflow-templates,workflows,scripts}/…` + `cluster/argo/README.md`.
- **No Dockerfile / `build-args.env` / dependency / `uv.lock` change** (the module ships via the existing
  `COPY src/`; the YAML test is text-based — no `pyyaml`). The `:fp64` image must be rebuilt on merge so
  the digest the workflow pins contains `run_one_config` (handled by `docker.yml`; operator pins the new
  `@sha256:`).
- **Docs** (the complete list — Impact is the single source, 1:1 with tasks 6–8):
  - **`cluster/argo/README.md`** (new) — the operator flow with hard preconditions (pin the **post-merge**
    digest from the `docker.yml` job-summary step; `argo lint`/`--dry-run` + a **1-config smoke submit**
    before the fan-out); **cross-references** `openspec/runai-dev-workflow.md` and **links** (does not
    re-tabulate) the mount-mapping table.
  - **`examples/prelim_sweep/README.md`** — **restructured** (not appended): Argo is the production path;
    the existing `runai workspace exec` walkthrough is **demoted** under a "Local/dev fallback
    (`scripts/run_sweep.py`)" subheading, and the "two phases / long-lived workspace" prose is rewritten so
    it no longer presents the exec flow as *the* way.
  - **`openspec/project.md`** *and* the **root `README.md`** Directory Structure — both gain a `cluster/`
    tree entry.
- **Roadmap:** `docs/force_surrogate/roadmap.md` — rewrite the Inputs/Outputs "produced by
  `scripts/run_sweep.py`" clause → Argo (run_sweep = local fallback); **add a PR/issue-split table row**
  for this change (the table currently has none); cite the 1/27 exec-stream/orphan cascade once.
- **Reuses (no change):** the PR3 runner library (`check_completion`, the provenance helpers, the
  constants), the validated science (the smoke test confirmed the `IB_Particle_1.csv` contract:
  29 columns, rows = `max_step`), the committed `sweep_manifest.json` + decks + `wing.vertex` staging.
- **Out of scope** (CC-6, force-only): no science/deck/kinematics change; `amr.plot_int = -1` unchanged;
  PR4 extract (local) + PR5/PR6 unchanged; the final-plotfile/disk note is tracked in #14.
