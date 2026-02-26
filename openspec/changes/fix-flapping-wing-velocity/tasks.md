## Tasks

### Fix: Set marker velocities to wing surface velocity

**Root cause (corrected)**: `InteractWithEuler` computes IB force as
`F = (kernel.velocity + omega×r - U_Marker)/dt`. For the flapping wing:
- `kernel.velocity = 0` (hinge doesn't translate)
- `kernel.omega = 0` (never updated to wing instantaneous angular velocity)
- `U_Marker` = fluid velocity at marker (written by `VelocityInterpolation`)
→ `F = -U_fluid/dt ≈ 0` since fluid is initially at rest.

**Actual fix** (different from initial proposal):
- `vel_x/y/z` holds prescribed wing surface velocity (computed via finite diff in `UpdateParticles`)
- After `VelocityInterpolation` writes `U_Marker = U_fluid`, **subtract** wing velocity:
  `U_Marker -= vel_wing` → `F = (vel_wing - U_fluid)/dt` ✓
- Call MUST be AFTER `VelocityInterpolation`, not before.

**Files changed**: `ExternalGeometry.H`, `DiffusedIB.H`, `DiffusedIB.cpp`

1. [x] Add `vel_x/y/z` PinnedVectors to `ExternalGeometryData` in `ExternalGeometry.H`
2. [x] Add `dt` param to `UpdateExternalGeometryPositions`; call `ComputeMarkerVelocities`
       to populate `vel_x/y/z`
3. [x] Declare `SetExternalGeometryMarkerVelocities(const kernel&)` in `DiffusedIB.H`
4. [x] Implement `SetExternalGeometryMarkerVelocities` in `DiffusedIB.cpp`
       (GPU kernel: `U_Marker[i] -= vel_x[id-1]` — note subtraction, NOT assignment)
5. [x] In `InteractWithEuler`, insert call **AFTER** `VelocityInterpolation`
       (initial incorrect placement was before VelocityInterpolation; VelocityInterpolation
       overwrites U_Marker with U_fluid, erasing the wing velocity we just set)
6. [x] In `UpdateParticles`, pass `dt` to `UpdateExternalGeometryPositions`

### Fix 2: Correct IB marker volume dv for surface geometry

**Root cause**: `dv = h*h*h` assumes each marker represents a volume element. For surface
markers with spacing d_nn < h, each Eulerian cell receives ~(h/d_nn)^2 markers → the IB
force is over-applied by that factor → velocities blow up exponentially.

**Fix**: Replace `dv = h*h*h` with `dv = h * d_nn^2` (area element × cell thickness).
d_nn estimated via O(N_sample × N) nearest-neighbor search on up to 200 sampled markers.

For the validation case: d_nn=0.0505, h=0.125 → old dv=0.00195, new dv=0.000319 (6.1x smaller).

17. [x] Diagnose IB over-forcing: step 2 |u|=18.94 (vs expected ~11.5); exponential growth to 5e12
18. [x] Implement dv fix in DiffusedIB.cpp (nearest-neighbor estimate, ~35 lines)
19. [x] Test CPU binary (test3.log, 50 steps): |u| stabilizes at ~27, no blow-up ✓
20. [x] Test GPU binary (test5.log, 200 steps): |u| stable at 10-28, all steps complete ✓
21. [x] Commit fix: `talmolab/IAMReX@2e9a851c` (feature/arbitrary-geometry)
22. [x] Update `docker/build-args.env` and `Dockerfile.fp64` with new SHA
23. [x] Push `talmolab/mosquito-cfd@887c5f9` to trigger CI rebuild

### Test in running container (before CI rebuild)

**Container access**:
- Local staging: `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\`
  (= `/workspace/` in container = `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/flapping_wing/`)
- Copy into image: `runai workspace exec flapping-wing-val7 -- sh -c 'cp /workspace/*.{cpp,H} /opt/cfd/IAMReX/Source/'`
- CPU build: `make -j$(nproc)` → `amr3d.gnu.DEBUG.MPI.ex`
- GPU build: `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.MPI.CUDA.ex`

7. [x] `flapping-wing-val7` container alive (submitted with `sleep infinity`)
8. [x] Stage source files to Z: workspace path; copy into container source dir
9. [x] Rebuild CPU debug binary: `make -j$(nproc)` → SUCCESS (`amr3d.gnu.DEBUG.MPI.ex`)
10. [x] Run 50-step CPU test (test3.log): step1 |u|=12.66, step2 |u|=10.17 (braking ✓)
11. [x] Rebuild CUDA debug binary (test5): `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.DEBUG.MPI.CUDA.ex`

### Commit and rebuild Docker image

12. [x] Commit surface velocity fix to `talmolab/IAMReX` `feature/arbitrary-geometry`
13. [x] Update `docker/build-args.env` with new SHA (2e9a851c)
14. [x] Update hardcoded `ARG IAMREX_COMMIT` in `Dockerfile.fp64`
15. [x] Push to trigger CI rebuild (~13 min with GHA cache for early layers)
16. [ ] Resubmit validation job with rebuilt Docker image, confirm stable run

### Lessons learned

- **`U_Marker` is fluid velocity, not wing velocity**: After `VelocityInterpolation`, `U_Marker`
  holds `U_fluid`. Don't overwrite with wing velocity — subtract it instead.
- **Call order matters**: `SetExternalGeometryMarkerVelocities` must run AFTER `VelocityInterpolation`.
- **Container workspace mount**: To edit container source files, stage to
  `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\` (mapped NFS), then copy inside.
- **Two make targets**: CPU debug (`make`) ≠ GPU/CUDA (`make USE_CUDA=TRUE`). The validation
  run uses the CUDA binary; the CPU binary is useful for logic testing only.
- **CUDA build can silently use stale object files**: Always verify binary timestamp is AFTER
  source edit. Running `touch file.cpp` before `make USE_CUDA=TRUE` forces recompilation.
- **Surface IB dv formula**: `dv = h^3` is correct only for volume markers (d_nn ≈ h).
  For finer surface markers, `dv = h * d_nn^2` prevents (h/d_nn)^2 overcorrection.
- **"pure virtual method called" at shutdown**: Debug builds may abort during global destructor
  cleanup after AMReX finalizes. This does NOT indicate simulation failure — check that
  all requested steps completed and output files were written before the abort.