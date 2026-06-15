## Why

The PR3 sweep runner (`add-force-surrogate-sweep-runner`, merged) writes a per-run
`run_metadata.json` for reproducibility (CC-1). The **first real A40 smoke run** exposed a
provenance bug: the metadata's `hardware` block records the **driver host's** GPU
(`NVIDIA RTX A5000`, the operator's local machine) — **not the cluster A40 that actually ran the
CFD**. The runner executes locally and launches the simulation **remotely** via the injected
executor, but `capture_run_metadata` probes `nvidia-smi`/`nvcc` on the **local** machine. So the
single field that answers "which hardware produced these forces" is **wrong and misleading**.

The scientifically load-bearing pins (the `sha256:` image digest, the `deck_sha256`) are correct,
so the dataset stays reproducible — but the `hardware` field must record the **compute node**, not
the orchestrating host, for the provenance to be honest.

## What Changes

### Extends capability: `force-surrogate`

- **New in `src/mosquito_cfd/force_surrogate/runner.py`:**
  - `build_probe_command(workspace) -> list[str]` — **pure** construction of the RunAI
    `workspace exec … nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits`
    command that queries the **in-container** GPU (no `container_workspace` arg — `nvidia-smi` is
    cwd-independent).
  - `capture_compute_hardware(executor, workspace, *, output_root, container_workspace=...) -> dict`
    — runs the probe via the injected executor and parses the CSV into
    `{"source": "container", "workspace": …, "gpus": [{model, memory_mb, driver_version}], "gpu_count": N}`.
    If the probe fails (nonzero **or** raises), it returns an explicit
    `{"source": "unavailable", "workspace": …, "note": …}` marker — **never** the driver host's
    hardware — and does **not** abort the sweep.
  - `run_sweep` captures the compute hardware **lazily** (once, on the first config that actually
    runs — so a fully-resumed corpus issues no probe and stays a no-op) and threads it into every
    per-run `run_metadata.json`, **overriding** the base capture's local `hardware` block (the
    override rides `extra=`, which `capture_run_metadata` merges via `dict.update`).
- **`__init__.py`** re-exports `build_probe_command`, `capture_compute_hardware`.

### Resolved decisions

- **Override, not driver-host relabel.** Record the **actual** compute GPU (model/memory/driver) so
  the provenance is accurate, not merely honest-but-vague. Rejected: recording only the runai
  node-pool name (loses the driver version, which can matter for FP reproducibility).
- **Lazy probe.** Probe only when a config is about to run, so re-running a complete corpus (resume
  skips all) needs no workspace and issues no exec — a fully-complete corpus is a no-op.
- **Graceful failure.** A failed probe records an explicit `unavailable` marker (not the misleading
  driver host) and continues — a hardware-probe hiccup must not lose the 65-minute corpus.

## Impact

- **Spec:** `force-surrogate` capability gains 1 requirement (per-run provenance records the compute
  node's hardware), with the compute / failed-probe / lazy-probe scenarios.
- **Code:** additions to `src/mosquito_cfd/force_surrogate/runner.py`; `__init__.py` re-exports;
  `tests/test_force_surrogate_runner.py` additions (fake executor answers the `nvidia-smi` probe).
- **Reuses (no change):** the injected-executor seam, `capture_surrogate_run_metadata` (the override
  rides `extra=`; PR1/sidecar untouched). The base local hardware probe still runs and is overridden
  — a negligible, acknowledged cost (a future PR1 tweak could skip it).
- **Out of scope** (CC-6, force-only): no plotfile/field reading, no dataset/train/figure changes.
- No dependency/Dockerfile/CI change (stdlib-only); cluster-free tested (CC-2).
