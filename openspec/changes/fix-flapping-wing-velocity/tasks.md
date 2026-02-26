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
10. [ ] Run 5-step logic test with CPU binary, verify `max(abs(u/v/w)) > 0` at step 2+
11. [ ] Rebuild CUDA binary: `make -j$(nproc) USE_CUDA=TRUE` → `amr3d.gnu.MPI.CUDA.ex`

### Commit and rebuild Docker image

12. [ ] Commit fixes to `talmolab/IAMReX` `feature/arbitrary-geometry`
13. [ ] Update `docker/build-args.env` with new SHA
14. [ ] Update hardcoded `ARG IAMREX_COMMIT` in `Dockerfile.fp64`
15. [ ] Push to trigger CI rebuild (~13 min with GHA cache for early layers)
16. [ ] Resubmit validation job, confirm non-zero velocities in cluster run

### Lessons learned

- **`U_Marker` is fluid velocity, not wing velocity**: After `VelocityInterpolation`, `U_Marker`
  holds `U_fluid`. Don't overwrite with wing velocity — subtract it instead.
- **Call order matters**: `SetExternalGeometryMarkerVelocities` must run AFTER `VelocityInterpolation`.
- **Container workspace mount**: To edit container source files, stage to
  `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\` (mapped NFS), then copy inside.
- **Two make targets**: CPU debug (`make`) ≠ GPU/CUDA (`make USE_CUDA=TRUE`). The validation
  run uses the CUDA binary; the CPU binary is useful for logic testing only.