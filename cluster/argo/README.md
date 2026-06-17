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
- **Force-only (CC-6).** The workflow produces the per-config IB-particle CSV corpus only; PR4's
  `scripts/extract_forces.py → dataset.parquet` stays the downstream **local** step.

## Outputs

`runs/<config>/IB_Particle_1.csv` (+ `run.log`, `run_metadata.json`) under the prelim_sweep workspace.
Build the training table locally afterwards with PR4's `extract_forces.py`.
