# Tasks — fix-force-surrogate-compute-hardware

TDD throughout (tests first, citing the spec scenario; commit tests+impl together; cluster-free —
CC-2: the fake executor answers the `nvidia-smi` probe, no real RunAI/GPU).

## 1. Probe command + parse + capture (`runner.py`)

1. [x] **Tests first** (`tests/test_force_surrogate_runner.py`), citing spec *The probe command is pure and force-only*:
   - `build_probe_command("ws")` → `["runai","workspace","exec","ws","--","nvidia-smi","--query-gpu=name,memory.total,driver_version","--format=csv,noheader,nounits"]`; no I/O; no `plot`/deck/mpirun.
   - `capture_compute_hardware` against a fake executor returning canned `"NVIDIA A40, 49140, 550.54.14"` → `{"source":"container","workspace":"ws","gpus":[{"model":"NVIDIA A40","memory_mb":49140,"driver_version":"550.54.14"}],"gpu_count":1}`.
   - `capture_compute_hardware` against an executor that returns nonzero, and one that **raises** → both yield `{"source":"unavailable","workspace":"ws", ...}` (no GPU list, never the driver host), logged.
2. [x] Implement `build_probe_command`, `_parse_gpu_csv(stdout)`, and `capture_compute_hardware(executor, workspace, *, output_root, container_workspace=DEFAULT_CONTAINER_WORKSPACE)` in `runner.py`. Re-export the two public symbols from `__init__.py` in the same commit.

## 2. Wire into `run_sweep` (`runner.py`)

3. [x] **Tests first** citing spec *Recorded hardware is the compute node…*, *A failed hardware probe…*, *The hardware probe is lazy*:
   - Extend `FakeExecutor` to answer an `nvidia-smi` probe command (record it separately from run calls so existing `names`/`cwds`/`calls` assertions stay valid) with a canned A40 CSV (default), and a `probe_fail` mode (nonzero/raise).
   - A completed run's `run_metadata.json` `hardware` has `source=="container"` and `gpus[0].model=="NVIDIA A40"` (the **probe**, not the local host).
   - With `probe_fail`, `hardware.source=="unavailable"`, the config still completes, and no driver-host GPU appears.
   - **Lazy**: a fully-resumed corpus (all complete) issues **zero** executor calls (no probe) — assert the fake recorded no probe and no run command.
   - Portability still holds (`_assert_portable` over the new `hardware` block — no abs paths).
4. [x] Implement: `run_sweep` captures `compute_hardware` lazily (a `None` sentinel set on the first config that actually runs, via `capture_compute_hardware`), threads it into `_write_run_metadata`, which sets `extra["hardware"] = compute_hardware` (overriding the base capture's local block via `dict.update`). Run green.

## 3. Validate

5. [x] `uv run ruff check src/ tests/ scripts/` + `ruff format --check` clean; `uv run pytest` green; `runner.py` coverage stays 100%.
6. [x] `openspec validate fix-force-surrogate-compute-hardware --strict` passes.
7. [x] Re-read proposal/spec vs implementation; reconcile any drift.
