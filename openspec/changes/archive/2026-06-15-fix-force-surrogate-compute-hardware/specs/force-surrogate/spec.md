## ADDED Requirements

### Requirement: Per-run provenance records the compute node's hardware

The per-run provenance SHALL record the hardware that actually ran the CFD — the **compute node
inside the container** (the cluster GPU) — and SHALL NOT present the **driver host** (the machine
that orchestrates the run) as the simulation hardware. Because the runner executes locally and
launches the simulation remotely via the injected executor, the base metadata capture's *local*
hardware probe is misleading. The runner SHALL capture the compute node's GPU via the executor (an
`nvidia-smi` query in the container) and record it under `hardware`. If the probe fails — a nonzero
return or a raised exception — the runner SHALL record an explicit *unavailable* marker rather than
the driver host's hardware, and SHALL NOT abort the sweep. The probe SHALL be **lazy**: it runs only
when a configuration is about to run, so a fully-resumed (already-complete) corpus issues no probe.

#### Scenario: Recorded hardware is the compute node, not the driver host

- **Given** an executor whose in-container `nvidia-smi` probe reports a cluster GPU (e.g. `NVIDIA A40`)
- **When** `run_sweep` completes a configuration
- **Then** that run's `run_metadata.json` `hardware` records the **compute** GPU (its `gpus` list carries the A40's model/memory/driver, and a `source` of `"container"`), and does **not** present the driver host's GPU as the simulation hardware

#### Scenario: A failed hardware probe is recorded honestly, not as the driver host

- **Given** an executor whose `nvidia-smi` probe fails (returns nonzero, or raises)
- **When** `run_sweep` runs a configuration
- **Then** the run's `hardware` records an explicit `"unavailable"` marker naming the workspace, the driver host's GPU is **not** recorded as the compute hardware, and the sweep still completes the configuration (the probe failure is logged, never silent, and never fatal)

#### Scenario: The hardware probe is lazy

- **Given** a corpus in which every configuration already passes the completion check (resume skips all)
- **When** `run_sweep` is called with `resume=True`
- **Then** **no** executor command is issued at all — including no hardware probe — so a fully-complete corpus remains a no-op (the probe is captured only on the first configuration that actually runs)

#### Scenario: The probe command is pure and force-only

- **Given** a workspace name
- **When** `build_probe_command` is called
- **Then** it returns a `runai workspace exec … nvidia-smi --query-gpu=… --format=csv,noheader,nounits` command without performing any I/O, and the command reads only GPU metadata — no plotfile, field, or simulation side effect
