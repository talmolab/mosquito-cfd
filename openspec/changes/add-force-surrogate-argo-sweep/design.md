# Design — add-force-surrogate-argo-sweep

**Roadmap:** Track B CFD sweep (the corpus that feeds PR5/PR6). Builds on PR3
(`add-force-surrogate-sweep-runner`, merged) and its compute-hardware fix
(`fix-force-surrogate-compute-hardware`, #13). **Replaces** the laptop-driven `runai exec` transport
with cluster-side Argo orchestration; the PR3 Python **library** is reused unchanged.

## The failure this fixes (evidence)

See `proposal.md` *Why* for the narrative; the forensic specifics: config 2's `runai workspace exec`
stream `EOF`'d after ~4 min; RunAI left the in-container `amr3d` running (PID 63, **34 GB GPU held**),
so configs 3–27 crashed on a busy GPU (`exit 6`, 0 rows, zombie `amr3d`). The runner *logic* was correct
(recorded failures, continued, resume-safe — config 1's data is intact); the **transport** (synchronous
laptop→cluster exec streaming) is the wrong tool for long unattended GPU runs. The table makes the
transport contrast precise:

## Why Argo (and why it's not a rewrite)

Argo runs **each config as a pod whose main process is `mpirun`**, scheduled by RunAI on the cluster:

| Failure mode (laptop `runai exec`) | Argo pod-per-config |
|---|---|
| ~10-min exec **stream drops** | No stream — the pod *is* the run; K8s watches the process |
| Dropped stream **orphans `amr3d`** → GPU poisoned | Pod teardown kills the process group; next pod gets a clean GPU |
| Hand-rolled resume passes | Built-in `retryStrategy` (limit 5, exp. backoff) |
| Laptop + VPN must hold for ~5 h | Runs entirely cluster-side; submit and walk away |

**Not a rewrite:** PR3's runner has a *swappable executor seam* (D5) precisely so the transport can
change. The library (`check_completion`, `capture_surrogate_run_metadata`, the `deck_sha256`/digest
provenance, `IB_PARTICLE_CSV`, `RUN_LOG`, `_format_run_log`, the constants) is transport-agnostic. The
Argo path swaps the "drive a remote `runai exec` from the laptop" executor for "run `mpirun` directly
as the pod's process," reusing everything else. The smoke test already validated the science (the
`IB_Particle_1.csv` contract holds).

## API surface

```python
# src/mosquito_cfd/force_surrogate/run_one_config.py  (new — the per-pod entrypoint)

# MpiRunner = Callable[..., ExecResult];  mpi_runner(argv, *, cwd) -> ExecResult
def run_config(
    *,
    name,                   # config name → run dir <output_root>/<name>/
    input_file,             # deck path, relative to container_workspace
    max_step,               # for check_completion (rows ≥ ceil(max_step·threshold))
    output_root,            # in-pod: /workspace/runs
    docker_digest,          # pinned :fp64 @sha256: (recorded in provenance)
    timestamp,              # caller-supplied ISO-8601
    mpi_runner,             # injected seam (real: subprocess.run(mpirun...); test: fake writes CSV)
    container_workspace="/workspace",
    wing_vertex="/workspace/wing.vertex",
    deck_path=None,         # real FS path to the deck for hashing; default container_workspace/input_file
    iamrex_binary=DEFAULT_IAMREX_BINARY,
    csv_name=IB_PARTICLE_CSV,
    threshold=DEFAULT_COMPLETION_THRESHOLD,
    extra_provenance=None,  # Argo fields: workflow_uid, pod, node, retry
) -> RunOutcome: ...        # status "completed"/"failed"; metadata written either way

def main(argv=None, *, mpi_runner=None) -> int:
    # argparse; when mpi_runner is None, build the REAL subprocess runner (so the CLI works in
    # the pod) — tests pass a fake, so main() is unit-testable cluster-free. Returns 0 iff the
    # run completed, else 1 → Argo retries the pod.
```

`run_config` takes the three per-run fields as **explicit keyword args** (`name`, `input_file`,
`max_step`) rather than a `config` dict (see D7) and **validates fail-fast** (a clear `ValueError`
naming the config if `max_step <= 0` or `name`/`input_file` is empty — the published
`load_manifest_configs` validator does **not** require `input_file`/`max_step`, so a hopeless config
must be caught before launch rather than retried five times on the A40; `main`'s argparse additionally
rejects a missing/non-integer `--max-step` flag with a non-zero exit). It then builds
`argv = ["mpirun","--allow-run-as-root","-np","1",
iamrex_binary, deck]` (deck = `<container_workspace>/<input_file>`), stages `wing.vertex` into the run
dir, and calls `mpi_runner(argv, cwd=run_dir)` **inside a `try/except Exception`** (a raised real
subprocess — missing binary, transient `OSError` — becomes `ExecResult(returncode=1, stderr=repr(exc))`
with the exception captured in `run.log`, a clean pod failure rather than a raw traceback; mirrors
PR3's `run_sweep` executor guard). It writes `run.log` from the result, `check_completion`s the CSV,
and writes `run_metadata.json` for **both** completed and failed attempts. **`status = "completed"` iff
the runner returned 0 *and* the CSV is complete; otherwise `"failed"`** → `main` exits 1 → Argo retries
(a fresh pod, clean GPU). `main` exits **0 iff completed, 1 otherwise** (the exact Argo retry signal).

**Why `deck_path` (a deviation from the originally-specced signature).** The recorded `mpirun`
command must use the **portable** in-container deck path (`<container_workspace>/<input_file>` →
`/workspace/...`, which the provenance-portability check enforces), but computing `deck_sha256`
needs the deck's **real** filesystem location. In the pod these coincide (`/workspace`), but a
cluster-free test cannot — Windows `tmp_path` is `C:\…`, which the portability assertion rejects, so
the test cannot set `container_workspace` to its fixture dir. This is exactly the two-root split PR3
already uses (`container_workspace` for the command vs `manifest_dir` for hashing). `deck_path`
makes it explicit and symmetric with the existing `wing_vertex` source param: it defaults to
`container_workspace/input_file` (the deck's real location in the pod, so the pod passes nothing
extra) and tests point it at the fixture deck while `container_workspace` stays `/workspace`.

## Key decisions

### D1. Full-GPU request + run as root
`resources.limits: {nvidia.com/gpu: 1}` requests a **whole** A40 — IAMReX FP64 used ~34 GB in the
smoke run, so a `gpu-fraction` (shared) GPU is wrong. `securityContext: {runAsUser: 0}` because
`mpirun --allow-run-as-root` and the IAMReX container run as root. Both come from the lab's
GPU-Argo precedent (`sleap-roots-pipeline/sleap-roots-predictor-template.yaml`:
`nvidia.com/gpu: 1`, `runAsUser: 0`); gapit is CPU-only and has no GPU example. **Rejected:**
`gpu-fraction` sharing (OOM at 34 GB).

**`runAsUser: 0` only — not `privileged: true`.** sleap-roots sets both; we deliberately drop
`privileged`. `mpirun --allow-run-as-root` needs only to *be* root, and the NVIDIA device plugin +
container runtime inject GPU access without host-device/kernel privileges. Least-privilege: omit
`privileged` (a future reviewer should not "fix" the divergence by re-adding it).

**Scheduling identity.** RunAI binds a pod to a project/queue; the lab's pattern (gapit, sleap) is
**project == namespace**, so `namespace: runai-talmo-lab` is the binding — no extra `runai/queue`
label is added (matching gapit). Because CI cannot test scheduling, the operator README mandates a
`argo lint`/`--dry-run` **and a single 1-config smoke submit** before the 27-way fan-out, to confirm
pods actually schedule onto an A40.

### D2. Moderate concurrency (parallelism = 3, parameterized)
The A40 quota is limited (PR3 D1 chose sequential to avoid contention). Under Argo+RunAI with
preemptible pods, modest fan-out is safe: a `parallelism` **workflow parameter** (default 3) caps
concurrent pods; `retryStrategy` re-runs any preempted pod on a fresh GPU. 3 cuts wall-clock ~3× vs
sequential (~1.5–2 h instead of ~5 h) without flooding the quota. The operator can set it to 1
(sequential) or higher.

### D3. Tested module baked into `:fp64`, no Dockerfile change
`run_one_config.py` lives in `src/mosquito_cfd/force_surrogate/`, which the `:fp64` Dockerfile already
`COPY src/` + `uv sync`s — so it ships in the image automatically with **no Dockerfile edit**. On merge,
`docker.yml` rebuilds `:fp64` (now containing the module) → the operator pins the **new** `@sha256:`
digest (the current `523c9035…` predates the module). The WorkflowTemplate runs the module via the
image's synced venv interpreter directly — **`/opt/cfd/mosquito-cfd/.venv/bin/python -m
mosquito_cfd.force_surrogate.run_one_config`** — *not* `uv run`: `uv run` does a project-resolution /
sync-staleness check on every call and may touch the network, an undesirable failure surface ×27 GPU
pods; the bare venv interpreter needs no PATH/`workingDir`/network. **Stale-digest fail-fast:** the
workflow's `validate` step runs the **same image** before any GPU pod and executes
`python -c "import mosquito_cfd.force_surrogate.run_one_config"` + checks the manifest is present —
so a digest pinned before the module shipped dies in seconds, not 27 × 5 A40 retries (the operator
README also states "pin the **post-merge** digest from the `docker.yml` *Emit FP64 image digest*
job-summary step — never reuse an older digest" as a hard precondition). **Rejected:** inline bash in
the pod command (untested glue) and mounting a script from NFS (not pinned by the digest).

### D4. Native hardware provenance (no exec-probe)
PR3-#13 added an in-container `nvidia-smi`-via-executor probe because the **laptop** driver's local
`nvidia-smi` saw the operator's A5000, not the A40. Under Argo the **pod runs on the A40**, so
`capture_run_metadata`'s base local `nvidia-smi`/`nvcc` probe captures the A40 **natively** — correct,
simpler, no override needed. `run_config` therefore calls `capture_surrogate_run_metadata` without a
`hardware` override — and, to make "native, not overridden" provable **cluster-free with no GPU**, it
**does not import** `capture_compute_hardware`/`build_probe_command` and takes **no** `hardware`/
`compute_hardware`/`executor` parameter. The test asserts this structurally (AST of imports + the
signature, mirroring PR3's AST subprocess-free check) plus the output shape (`hostname` present,
`source`/`workspace` absent — robust on a CI box with `gpus: []` *and* a dev box with a real GPU; it
never asserts `gpus == []`). **Note (acknowledged):** the `:fp64` image has no `.git`, so the in-pod
`git` block records `error` rather than a commit; the exact code is pinned content-addressably by the
recorded `docker_image` digest (and recoverable from it). Optionally the workflow may pass the git SHA
as a parameter into `extra_provenance` (operator knows it at submit time); not required.

### D5. Scope = the sweep; extract stays local
The Argo workflow covers **corpus production** (the failing part). PR4's `extract_forces.py →
dataset.parquet` stays the downstream **local** step (already merged, fast, and the `:fp64` image does
not ship `scripts/`). The in-workflow `verify-complete` step only **gates on completeness** (every
config's CSV passes `check_completion`); it does not build the parquet. `scripts/run_sweep.py` is
retained and documented as the **local/dev fallback** (e.g. a one-off config, or no Argo access).

### D6. Provenance & retry semantics
`run_config` writes `run_metadata.json` for **both** completed and failed pods (so a failed attempt is
auditable), recording the digest, `deck_sha256`, the exact `mpirun` argv, `rows`/`max_step`/`threshold`,
`status`, the `run.log` path, native hardware, and the Argo provenance (`workflow_uid`, `pod`, `node`,
`retry` from `extra_provenance`). On retry, Argo starts a fresh pod that overwrites the run dir's
artifacts — last (successful) attempt wins; the run-dir is the per-config output, the `runs/` tree is
gitignored (PR3). The `verify-complete` step is the workflow-level success gate.

### D7. Explicit run args, not a config dict or OmegaConf
`run_config` takes `name`/`input_file`/`max_step` as **explicit keyword args** — no `config` dict, no
config framework. Rationale: (a) at the single-run boundary only three scalars are needed, so a dict
would round-trip pointlessly (the pod's `main` would rebuild a dict from three CLI flags only for
`run_config` to read them back out); (b) **OmegaConf/pydantic were rejected** — they earn their weight
on hierarchical composition / CLI-override / interpolation / YAML-merge, none of which exists here (PR2
already fully materializes the manifest; the Argo fan-out threads three scalars), and either would add a
runtime dependency → `uv.lock` change → the `uv sync --frozen` image-rebuild coupling we avoid for the
same reason as `pyyaml` (D-text-assert); (c) it would ripple into **merged** code (`load_manifest_configs
-> list[dict]`, consumed by PR4's `build_dataset`). The "config" abstraction stays where it belongs — the
manifest level, in the already-merged `load_manifest_configs`; the Argo `extract-configs` step reads the
manifest and `withParam` threads `{{item.name}}`/`{{item.input_file}}`/`{{item.max_step}}` into the
template's CLI flags. **Kinematics are deliberately not added to the run args or `run_metadata.json`:** they
are already pinned three ways — the committed `sweep_manifest.json` (authoritative, by `name`), the input
deck (whose SHA256 is recorded as `inputs.hash`/`deck_sha256`), and PR4's `dataset.parquet` columns. Adding
them to the per-run sidecar would be a redundant 4th copy; the deck hash already makes every run
cryptographically traceable to its exact kinematics. If a future need arises for a self-describing sidecar,
thread them via `extra_provenance` then — not now.

## Argo artifacts (mirroring gapit + sleap)

- **`force-surrogate-single-config` WorkflowTemplate** (namespace `runai-talmo-lab`,
  `serviceAccountName: default`): container = `{{inputs.parameters.image}}` (pinned `@sha256:`),
  `command:["/opt/cfd/mosquito-cfd/.venv/bin/python","-m","mosquito_cfd.force_surrogate.run_one_config", …]`
  (the synced venv interpreter — no `uv run` network/sync), ENV/args for
  config-name/input-file/max-step/output-root/docker-digest/timestamp/threshold + Argo provenance
  (`fieldRef` for pod/node; `{{workflow.uid}}`/`{{retries}}`); `volumeMounts: [{name: nfs-workspace,
  mountPath: /workspace}]`; `resources.limits.nvidia.com/gpu: 1`; `securityContext.runAsUser: 0`;
  `retryStrategy` (limit 5, OnFailure, backoff 2m×2→30m); `annotations.runai/preemptible: "true"`.
- **`force-surrogate-sweep` Workflow**: workflow-level `volumes: [{name: nfs-workspace, hostPath:
  {path: {{workflow.parameters.workspace-hostpath}}, type: Directory}}]`; DAG `validate → extract-configs
  → run-all-configs (withParam over the configs JSON, templateRef the single-config template) →
  verify-complete`; `parallelism: {{workflow.parameters.parallelism}}` (default 3);
  `serviceAccountName: default`; `activeDeadlineSeconds: 86400` (24 h — generous so a slow-but-progressing
  run is not killed; per-pod `retryStrategy`/backoff handles the real failures; a corpus unfinished in
  24 h is wedged). **`validate`** runs the pinned image (before any GPU pod) and executes
  `python -c "import mosquito_cfd.force_surrogate.run_one_config"` + asserts `sweep_manifest.json` is
  present — the **stale-digest fail-fast**. `extract-configs` (the `:fp64` image) reads
  `/workspace/sweep_manifest.json` via `load_manifest_configs` and emits the configs JSON for the
  fan-out; `verify-complete` runs `check_completion` over **every** config's CSV and fails the workflow
  if any is incomplete.
- **`submit_workflow.sh`/`monitor_workflow.sh`**: `wsl -e bash -c "export KUBECONFIG=…; argo submit
  cluster/argo/workflows/force-surrogate-sweep.yaml -n runai-talmo-lab --parameter
  image=ghcr.io/talmolab/mosquito-cfd@sha256:… --parameter workspace-hostpath=/hpi/hpi_dev/…/prelim_sweep
  --parameter docker-digest=… --parameter timestamp=… --watch"`; monitor via `argo get`/`argo logs -f`.

## Test strategy (TDD, cluster-free — CC-2)

1. **`run_config`** (`tests/test_force_surrogate_run_one_config.py`) with an **injected fake
   `mpi_runner`** (writes a synthetic full/short CSV into `cwd`, mirroring the PR3 fake-executor):
   full-length CSV → `status="completed"`, `run_metadata.json` records digest + `deck_sha256` +
   timestamp + `command` (the `mpirun` argv) + the Argo `extra_provenance`; **short CSV → `status="failed"`
   and `main()` returns non-zero** (the Argo-retry signal); a **mutable digest is rejected** (inherited
   from `capture_surrogate_run_metadata`); provenance is **portable** (no absolute `Z:\`/`/hpi/` paths)
   and records **native** hardware (the base probe, not an override) + the Argo fields; `wing.vertex`
   is staged into the run dir; `run.log` captures the runner's stdout/stderr. A driver smoke test runs
   `main([...], mpi_runner=fake)` over a fixture tree and asserts exit 0 (complete) / 1 (short / non-zero
   / raised). Plus the failure-mode tests the spec adds: a **malformed config** (missing `input_file`/
   `max_step`, or `max_step <= 0`) raises a config-named `ValueError` with **no** runner call; a
   `mpi_runner` that **raises** → `status="failed"`, `run_metadata.json` still written, `main()==1` (clean
   pod failure, not a traceback); and the **native-hardware** claim is asserted *structurally* (AST: no
   `capture_compute_hardware`/`build_probe_command` import; `inspect.signature`: no `hardware`/
   `compute_hardware`/`executor` param) so it holds with **no GPU**. **Reuse is enforced positively** —
   an AST/import assertion that the module imports `check_completion`/`capture_surrogate_run_metadata`/
   `_format_run_log` from `runner`/`sidecar` (not reimplemented inline) — plus coverage of the
   `extra_provenance=None` default, the `main` argparse→provenance plumbing, a non-default
   `container_workspace`, `wing.vertex` staging, and the D6 retry-overwrite (last write wins).
2. **Argo YAML** (`tests/test_argo_workflows.py`, **text-assertion**, no `pyyaml`): parse-free checks that
   the WorkflowTemplate + Workflow files exist and contain the load-bearing contract —
   `serviceAccountName: default`, `namespace: runai-talmo-lab`, `nvidia.com/gpu: 1`, `runAsUser: 0`,
   `retryStrategy`/`limit: 5`, `runai/preemptible: "true"`, the `withParam` fan-out, a `parallelism`
   parameter, the `image` param, and the `run_one_config` invocation. The GPU/root asserts are
   **block-anchored** (the gpu line in the indented block immediately following `limits:`; `runAsUser: 0`
   under `securityContext`) so a `requests:`-vs-`limits:` swap can't pass, and the `.venv` interpreter is
   asserted as the **contiguous** command vector so `uv run` can't sneak in. These text asserts guard field
   presence/co-location only; **`argo lint` (operator-side, on the cluster) is the authoritative structural
   validator** (indentation, schema, reparented keys) — the CI test guards the contract fields cheaply and
   cluster-free; task 6 records the `argo lint`/`--dry-run` + 1-config smoke-submit step.

**Why text-assert, not `pyyaml`:** a real parse would need a new dev dependency → `uv.lock` change →
the `uv sync --frozen` image-build coupling PR4 (D11) had to manage. For a test that guards a handful
of required fields in operator-authored YAML (whose true validation is `argo lint`), text assertions
are sufficient and avoid that churn.
