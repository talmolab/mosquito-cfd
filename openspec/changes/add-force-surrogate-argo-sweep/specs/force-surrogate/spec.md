## ADDED Requirements

### Requirement: Single-configuration pod run

The force-surrogate module SHALL provide a per-configuration run entrypoint suitable for a
container whose **main process is the CFD run itself** (so the orchestrator manages its lifecycle,
with no remote exec stream to drop and no orphaned GPU process). For one sweep configuration it SHALL
stage `wing.vertex` into the run directory, invoke `mpirun` through an **injected runner seam** (so
the logic is unit-tested cluster-free, CC-2), write the run's captured output to `run.log`, verify
completion via the published `check_completion` (29-column header + rows ≥ `ceil(max_step · threshold)`),
and write a per-run `run_metadata.json` via `capture_surrogate_run_metadata` recording the pinned
container **digest**, the deck's manifest-relative path and SHA256, a **caller-supplied** timestamp,
and the orchestrator provenance (workflow uid, pod, node, retry attempt). The entrypoint SHALL signal
**non-zero on an incomplete run** so the orchestrator retries, and the per-run output path SHALL match
PR4's `<output-root>/<name>/IB_Particle_1.csv` driver contract. For this pod transport the hardware
provenance is captured **natively** (the base local probe), **superseding** the PR3 laptop driver's
exec-probe `source: "container"` path (the pod runs *on* the compute GPU, so no probe is needed).

#### Scenario: Completed run writes the checked output and provenance

- **Given** a config and an injected runner that writes a full-length `IB_Particle_1.csv` into the run directory
- **When** `run_config` is called
- **Then** the run's status is `"completed"`, `<output-root>/<name>/IB_Particle_1.csv` passes `check_completion`, `run.log` holds the runner's output, and `<output-root>/<name>/run_metadata.json` records the `sha256:` digest under `docker_image`, the deck SHA256, the timestamp verbatim, the `mpirun` command, and the supplied orchestrator provenance (workflow uid / pod / node / retry)

#### Scenario: Wing geometry is staged into the run directory

- **Given** a config and an injected runner that writes a full-length `IB_Particle_1.csv`
- **When** `run_config` is called
- **Then** the wing geometry (`wing.vertex`) is present in the run directory (`<output-root>/<name>/wing.vertex`) and byte-identical to the source vertex file — the CFD deck resolves its geometry relative to the run directory, so an unstaged geometry would be a silent solver failure rather than a `check_completion` failure

#### Scenario: Incomplete run signals retry

- **Given** an injected runner that returns success but writes a short (or empty) CSV, or returns non-zero
- **When** `run_config` is called and then the `main()` entrypoint returns
- **Then** the run's status is `"failed"`, a `run_metadata.json` is still written (the attempt is auditable, `status = "failed"`), and `main()` returns a **non-zero** exit code so the orchestrator retries the configuration on a fresh pod

#### Scenario: Native compute hardware is recorded (no exec probe)

- **Given** `run_config` running inside the pod that executes the CFD on the GPU
- **When** the run metadata is captured
- **Then** the `hardware` block is the base local capture (`get_hardware_info`: `hostname` present; the override-only keys `source`/`workspace` **absent**), since the pod runs on the compute node itself — it does **not** use an in-container exec probe (which the laptop driver needed) and does not record a different host. This is provable **cluster-free, with no GPU**: the entrypoint does **not** import `capture_compute_hardware`/`build_probe_command` and `run_config` takes no `hardware`/`compute_hardware`/`executor` parameter (asserted structurally via AST + signature), and the output-shape assertion never requires `gpus` to be non-empty (CI has no GPU)

#### Scenario: Mutable tag rejected

- **Given** a mutable image tag (no `sha256:` digest)
- **When** `run_config` writes its provenance
- **Then** it raises `ValueError` (inherited from `capture_surrogate_run_metadata`) rather than recording an unpinned image

#### Scenario: Malformed configuration fails fast (no wasted A40 retries)

- **Given** a non-positive `max_step` (or an empty `input_file`/`name`) passed to `run_config`, or a missing/non-integer `--max-step` on the `main()` CLI
- **When** `run_config` / `main()` is invoked
- **Then** `run_config` raises a clear `ValueError` naming the configuration and the offending field, and `main()`'s argparse rejects a missing/non-integer flag with a non-zero exit — the published `load_manifest_configs` validator does **not** require `input_file`/`max_step`, so a hopeless config is rejected **once**, not retried five times on the A40

#### Scenario: A raised runner is a clean failure, not a crash

- **Given** an injected `mpi_runner` that **raises** (e.g. the real subprocess hitting a missing binary or a transient `OSError`)
- **When** `run_config` is called
- **Then** it records `status == "failed"` with the exception captured in `run.log`, still writes the `run_metadata.json` (`status="failed"`), and `main()` returns a non-zero exit code — a **clean** pod failure the orchestrator retries, not an uncaught traceback

#### Scenario: Provenance is portable

- **Given** a completed run's `run_metadata.json`
- **When** every nested string is inspected
- **Then** no value is an absolute host mount path (no `^[A-Za-z]:\\` drive-letter path, none starting with `/hpi/`); the deck is identified by its manifest-relative path plus SHA256, and the recorded command uses container (`/workspace/...`) paths

### Requirement: Cluster-side Argo orchestration of the corpus

The repository SHALL provide Argo Workflows artifacts that run the committed 27-config corpus
robustly on the cluster as the production path, **superseding** the laptop `runai exec` driver (which
is retained as a documented local/dev fallback). Each configuration SHALL run as its own pod whose
main process is the CFD run, with a full-GPU request, run-as-root for `mpirun`, and automatic retries;
the workflow SHALL fan out over the configurations declared in `sweep_manifest.json` under a bounded
concurrency, and SHALL gate overall success on every configuration's CSV passing the completion check.

#### Scenario: Each config gets a dedicated GPU, runs as root, and is retried

- **Given** the `force-surrogate-single-config` WorkflowTemplate
- **When** a configuration runs under it
- **Then** each config gets a **dedicated full A40** (the template declares `resources.limits` `nvidia.com/gpu: 1` — no fractional sharing, so IAMReX's ~34 GB never collides), runs **as root** for `mpirun` (`securityContext` `runAsUser: 0`), and a dropped/preempted run is **retried on a fresh pod** (`retryStrategy` with a limit + backoff); it is annotated `runai/preemptible: "true"`, sets `serviceAccountName: default` in namespace `runai-talmo-lab`, and invokes `mosquito_cfd.force_surrogate.run_one_config`. These load-bearing fields are verified **cluster-free** by asserting them in the manifest (each in its correct block — `nvidia.com/gpu: 1` under `limits:`, `runAsUser: 0` under `securityContext`); **`argo lint` is the authoritative structural validator**.

#### Scenario: Workflow fans out over the manifest configs (not a hardcoded list)

- **Given** the `force-surrogate-sweep` Workflow
- **When** a sweep runs
- **Then** its per-config tasks are **derived from `sweep_manifest.json`** (an `extract-configs` step using `load_manifest_configs` feeds a `withParam` fan-out — there is no hardcoded list of the 27 `s*_f*_p*` config names), under a bounded `parallelism` parameter (default 3), with the container image pinned by an `@sha256:` parameter at submit time, the prelim_sweep workspace mounted, and `serviceAccountName: default`

#### Scenario: Concurrency and total runtime are bounded

- **Given** the `force-surrogate-sweep` Workflow
- **When** it is submitted
- **Then** concurrent GPU pods are capped by the `parallelism` workflow parameter (default 3 — the limited A40 quota, not an unbounded 27-way burst) and the run is bounded by `activeDeadlineSeconds` (24 h), so a wedged run is killed rather than holding the quota indefinitely; per-pod `retryStrategy` backoff (not the deadline) handles transient failures

#### Scenario: A stale image is caught before any GPU pod

- **Given** the workflow's `validate` step, which runs the pinned image **before** the fan-out
- **When** the pinned image does not contain `run_one_config` (a digest pinned before the module shipped), or the manifest is missing
- **Then** `validate` **fails the workflow immediately** — before any GPU pod is scheduled — so a stale-digest mistake costs seconds, not 27 configs × 5 retries of A40 time

#### Scenario: Completion is gated by check_completion, not assumed

- **Given** the workflow's final `verify-complete` step
- **When** the fan-out finishes
- **Then** that step runs **`check_completion`** over **every** configuration's `IB_Particle_1.csv` and **fails the workflow** if any configuration is incomplete — overall success means a complete corpus, not merely that pods exited

#### Scenario: Dataset extraction is not in scope of the workflow

- **Given** the sweep workflow
- **When** its steps are inspected
- **Then** it produces the per-config IB-particle CSV corpus and gates completeness, but contains **no** dataset-build step (no `extract_forces`/`dataset.parquet`) and **no** plotfile/field token (PR4's `extract_forces.py` remains the downstream local step; force-only is preserved — `amr.plot_int = -1`, no plotfile/field reader)
