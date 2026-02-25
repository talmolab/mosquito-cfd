## Tasks

### Fix 1: GPU-safe marker positions in ExternalGeometry.H

**Root cause (confirmed via Backtrace.0)**: `amrex::Gpu::copy(hostToDevice, ...)` segfaults
at ExternalGeometry.H:115 in AMReX 2e4b667c — the function fails when called with
`DeviceVector` iterators before the AMReX CUDA arena is fully initialized.

**Actual fix applied**: Change `pos_x/y/z` from `Gpu::DeviceVector` to `Gpu::PinnedVector`
(pinned host memory, accessible from both CPU and GPU without any explicit copy).

1. [x] Change struct fields to `amrex::Gpu::PinnedVector<amrex::Real> pos_x/y/z`
2. [x] In `InitializeExternalGeometry()`, use direct host assignment loop (no staging vector needed)
3. [x] Apply same simplification to `UpdateExternalGeometryPositions()`

Implemented in IAMReX commit `656602b`.

**Verification**: Simulation initializes without "Segfault" after "Read N markers" on new AMReX (gpu-node14).

---

### Fix 2: calculate_phi_nodal for geometry_type=4

3. [x] In `calculate_phi_nodal()` in `DiffusedIB.cpp`, add case before the `geometry_type > 2` abort:
   ```cpp
   } else if (geometry_type == 4) {
       // Nearest-marker signed distance field
       const auto* px = ...; // pos_x.dataPtr() from g_external_geometries
       const auto* py = ...;
       const auto* pz = ...;
       const int nm = ...; // num_markers
       amrex::ParallelFor(bx, [=] AMREX_GPU_DEVICE(int i, int j, int k) noexcept {
           Real Xn = i*dx[0]+plo[0], Yn = j*dx[1]+plo[1], Zn = k*dx[2]+plo[2];
           Real min_d = 1e10;
           for (int m = 0; m < nm; ++m) {
               Real d2 = (Xn-px[m])*(Xn-px[m]) + (Yn-py[m])*(Yn-py[m]) + (Zn-pz[m])*(Zn-pz[m]);
               min_d = amrex::min(min_d, std::sqrt(d2));
           }
           pnfab(i,j,k) = (min_d - dx[0]) / a;  // normalized, phi<0 at wing
       });
   }
   ```

**Verification**: Simulation runs past step 1 `UpdateParticles` without aborting.

---

### Fix 3: Push and rebuild

4. [x] Commit both fixes to `talmolab/IAMReX` on `feature/arbitrary-geometry` (commit `656602b`)
5. [x] Update `docker/build-args.env` with new IAMReX commit SHA
6. [x] Trigger Docker CI build for `fp64` image (mosquito-cfd commit `d37d2a4`)
7. [ ] Verify CI passes (`ghcr.io/talmolab/mosquito-cfd:fp64` published)

---

### Fix 4: End-to-end validation

8. [ ] Submit new validation job with updated `fp64` image (once CI passes)
10. [ ] Monitor: simulation runs past step 1 (no crash)
11. [ ] Monitor: simulation completes 100 steps (first plotfile written)
12. [ ] Check `plt00100` exists in `/workspace/` on cluster
13. [ ] Verify forces are non-zero: check `sim.log` for non-zero `max(abs(u/v/w))`

---

## Verification Matrix

| Test | Pass Condition | Location |
|------|---------------|----------|
| No segfault on init | "Initialized external geometry" printed | `sim.log` |
| No abort at step 1 | No "Unsupported geometry_type" error | `sim.log` |
| Wing moves | `max(abs(u/v/w)) > 0` at step 1 | `sim.log` |
| Plotfile written | `plt00100` directory exists | cluster workspace |
| Forces non-zero | `particle_real_comp3/4/5` non-zero in plotfile | visualize.py |