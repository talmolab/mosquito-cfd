# Force-surrogate Argo sweep (cluster-side production path)

Runs PR2's committed 27-config kinematic corpus through the pinned `:fp64` IAMReX container on the
A40s, **one Argo pod per config whose main process is `mpirun`**. Because Kubernetes owns the
process, there is no `runai exec` stream to drop and no orphaned `amr3d` holding the GPU — the
failure that lost 26 of 27 configs on the first laptop-driven run (`scripts/run_sweep.py`, now the
[local/dev fallback](../../examples/prelim_sweep/README.md)).

## Layout

| File | Role |
|------|------|
| `workflow-templates/force-surrogate-single-config.yaml` | One A40 pod for one config (`nvidia.com/gpu: 1`, `runAsUser: 0`, `retryStrategy`, `preemptible: "true"` — the bare GPU-preemptible key, sleap-roots form). Runs the tested entrypoint `mosquito_cfd.force_surrogate.run_one_config` baked into `:fp64`. |
| `workflows/force-surrogate-sweep.yaml` | Fan-out DAG: `validate → extract-configs → withParam fan-out → verify-complete`. |
| `workflows/force-surrogate-smoke.yaml` | 1-config pre-flight wrapper (defines the `nfs-workspace` volume + one `templateRef`). |
| `scripts/submit_workflow.sh` | `template` / `lint` / `smoke` / `full`. |
| `scripts/monitor_workflow.sh` | `list` / `get` / `logs` / `stop`. |

## Prerequisites (hard preconditions — do them in order)

All commands run **from WSL with `KUBECONFIG` exported** — see
[`openspec/runai-dev-workflow.md`](../../openspec/runai-dev-workflow.md) for that boilerplate and the
Windows/Cluster/container [mount mapping](../../openspec/runai-dev-workflow.md#workspace-mount-mapping)
(the corpus lives in the `examples/prelim_sweep` NFS dir, mounted at `/workspace`).

1. **Merge** this change to `main`.
2. **Wait for `docker.yml` `build-fp64` to succeed (green).** The Argo pods run the module baked into
   `:fp64`, so the image must be rebuilt with `run_one_config` before you pin it.
3. **Copy the post-merge digest.** Take the `ghcr.io/talmolab/mosquito-cfd@sha256:…` line from the
   **"Emit FP64 image digest to job summary"** step of that `build-fp64` run. **Pin this post-merge
   digest — never reuse an older one** (the digest before this change predates the module; the
   `validate` step below would catch it, but pinning the right one avoids the round-trip).
4. **Lint + smoke before the fan-out.** `argo lint` is the authoritative structural validator (the
   CI text-assertions only guard field presence/co-location). Then run a **single config** to confirm
   it actually schedules onto an A40 and the GPU pod runs:
   ```bash
   wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
     && cluster/argo/scripts/submit_workflow.sh template \
     && cluster/argo/scripts/submit_workflow.sh lint \
     && cluster/argo/scripts/submit_workflow.sh smoke --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST>"
   ```
5. **Submit the full fan-out** once the smoke config completes:
   ```bash
   wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
     && cluster/argo/scripts/submit_workflow.sh full --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST>"
   ```

### NFS provisioning (automatic, closes #62)

Both `smoke` and `full` **provision** `--workspace-hostpath` from `--corpus-dir` (default
`examples/prelim_sweep`) before submitting — replacing (not merging into) any prior `inputs/`
content, copying `sweep_manifest*.json` (`full` only; `smoke` runs a single named deck and never
reads the manifest), and copying the canonical `examples/flapping_wing/wing.vertex`, **verifying
`wing.vertex` specifically by content hash** (the one artifact with a documented history of
silently drifting — `inputs/`/the manifest rely on the replace-not-merge behavior and `cp`'s own
failure instead). This closes a previously-manual, previously-missed step: an earlier session
found the coarse corpus's NFS `wing.vertex` didn't match any git-committed version at all (stale
from before the axis-convention refactor), sitting undetected on the cluster share for over a
month.

- **`--corpus-dir DIR`** — the local corpus to stage. Its basename **must match**
  `--workspace-hostpath`'s basename (provisioning refuses a mismatch, e.g. a coarse `--corpus-dir`
  paired with a fine-corpus `--workspace-hostpath`) — always pass both together when targeting a
  non-default corpus:
  ```bash
  wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
    && cluster/argo/scripts/submit_workflow.sh full --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
       --corpus-dir examples/prelim_sweep_fine --workspace-hostpath /hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine"
  ```
- **`--no-provision`** — skip staging (you've already verified NFS is current by hand). Provisioning
  defaults to **on**; opt-in skipping is exactly how the original gap went undetected, so make this
  an explicit, deliberate choice, not a habit.

### Concurrency and deadline are coupled — override both together (issues #63/#64)

`full`'s `--parallelism N` overrides the submitted workflow's concurrency without editing the
committed `force-surrogate-sweep.yaml` (default: its own committed value, `3`). The committed
`activeDeadlineSeconds` (24h) was sized for that committed default — **overriding
`--parallelism` alone without also adjusting the deadline can silently doom a submission to a
deadline-kill partway through** (this is exactly what happened to
`force-surrogate-sweep-7wrk7`, killed at 24h with 0/27 configs done, when submitted with
`--parallelism 1` and no matching deadline change).

- **`--active-deadline-seconds N`** — overrides `activeDeadlineSeconds` the same way
  (anchored, self-verifying temp-copy patch; never edits the committed file). Compose freely
  with `--parallelism` — both land on the same patched temp copy.
- **Auto-scale fallback** — if `--parallelism` is overridden and `--active-deadline-seconds` is
  *omitted*, the script auto-computes a safe replacement deadline from the manifest's real
  config count (`ceil(config_count × 2.4h ÷ parallelism + 4h)`, rounded up to a whole hour)
  instead of silently leaving the stale committed default in place. Pass
  `--active-deadline-seconds` explicitly if you want a different value than the auto-scaled one
  — an explicit value always wins. **Auto-scale reads `--corpus-dir`'s manifest directly, not
  whatever is actually staged at `--workspace-hostpath`** — if the two flags' basenames don't
  match (the same coarse/fine mismatch `--no-provision` skipping `provision()`'s own guard could
  otherwise let through undetected), the script refuses to auto-scale rather than silently
  computing a deadline from the wrong corpus's config count; pass a matching `--corpus-dir`, or
  an explicit `--active-deadline-seconds` to skip auto-scale (and this check) entirely.
  ```bash
  wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
    && cluster/argo/scripts/submit_workflow.sh full --image ghcr.io/talmolab/mosquito-cfd@sha256:<DIGEST> \
       --parallelism 1"   # deadline auto-scales; or add --active-deadline-seconds N to override it explicitly
  ```
- **`retryStrategy.backoff.maxDuration`** (in `force-surrogate-single-config.yaml`, shared by
  `full` and `smoke`) is `4h` — enough for all `limit: 5` configured retries
  (`2m→4m→8m→16m→32m = 62m`) to actually run under talmo-lab's persistent GPU-quota-overrun
  preemption, not just the first 3 (the old `30m` cap exhausted after 3 of 5 retries, which is
  what lost `force-surrogate-sweep-vb8t5`'s 3 longest-running configs to preemption).

## Monitor

```bash
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
  && cluster/argo/scripts/monitor_workflow.sh list"          # find the workflow name
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
  && cluster/argo/scripts/monitor_workflow.sh get  force-surrogate-sweep-<id>"
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
  && cluster/argo/scripts/monitor_workflow.sh logs force-surrogate-sweep-<id>"
```

`stop` terminates a workflow; pod teardown frees the A40 (no orphaned `amr3d`).

## What the workflow guarantees

- **Provenance per run.** Each pod writes `runs/<config>/run_metadata.json` via the published
  `capture_surrogate_run_metadata`: the pinned image **digest**, the deck SHA256, a caller timestamp,
  native A40 hardware, and the Argo `orchestration` block (workflow uid / pod / retry). Kinematics are
  *not* duplicated here — they are pinned by the manifest (by config name) and the deck hash.
- **Completeness, not just exit.** `verify-complete` runs `check_completion` over **every** config's
  `IB_Particle_1.csv` and fails the workflow if any is short — overall success means a complete corpus.
- **Corpus-agnostic, CSV-only workflow steps (CC-6).** The workflow's own steps (`validate`, the
  fan-out, `verify-complete`) only ever read/write the per-config IB-particle CSV — regardless of
  whether the submitted corpus's decks are force-only (`amr.plot_int=-1`, e.g.
  `examples/prelim_sweep/`) or field-capture-enabled (e.g. `examples/prelim_sweep_fine/` as of
  `add-fine-corpus-field-capture`). The workflow neither inspects nor constrains
  `amr.plot_int`/`ns.init_iter`; any plotfiles a field-capture corpus's CFD run produces land on
  disk as a side effect of the deck, not as something this workflow reads, gates, or reports on.
  PR4's `scripts/extract_forces.py → dataset.parquet` stays the downstream **local** step either
  way.

## Outputs

`runs/<config>/IB_Particle_1.csv` (+ `run.log`, `run_metadata.json`) under the prelim_sweep workspace.
Build the training table locally afterwards with PR4's `extract_forces.py`.
