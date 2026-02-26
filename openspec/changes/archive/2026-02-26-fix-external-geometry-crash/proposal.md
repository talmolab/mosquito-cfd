## Why

Two bugs in the `feature/arbitrary-geometry` IAMReX implementation blocked the flapping wing simulation from running (Feb 25, 2026): (1) per-element `Gpu::DeviceVector` assignment segfaulted with AMReX `2e4b667c` due to changed arena allocation behavior; (2) `calculate_phi_nodal()` explicitly aborted for `geometry_type > 2`, preventing IB force spreading for external geometry. Both bugs caused immediate crashes before any meaningful simulation steps could complete.

---

## What Changes

1. **`Source/ExternalGeometry.H`**: Replace per-element device assignment with staged `amrex::Gpu::copy()`.

2. **`Source/DiffusedIB.cpp`**: Add `geometry_type == 4` case to `calculate_phi_nodal()` using nearest-marker distance GPU kernel.

## Scope

Minimal bug fixes only — no behavior changes for geometry_type=1,2. Does not introduce new input parameters.

## Dependencies

- Depends on: `add-arbitrary-geometry` (same IAMReX fork, same branch)
- Must be merged before: APEX proposal validation runs (deadline Feb 27, 2026)