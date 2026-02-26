# RunAI Dev Workflow: Fast Iteration Without Docker Rebuild

## Problem

Full Docker image rebuild takes ~13-16 minutes (CUDA compilation). For iterating on
IAMReX C++ source changes, this is too slow for debugging.

## Solution: In-Container Edit + Rebuild

Keep a persistent RunAI workspace alive with `sleep infinity`. Stage source files from
the local machine via the NFS-mounted workspace, copy them into the container, and rebuild
with `make` in-place. Turnaround time: ~2-5 min (incremental C++ compile, no CUDA unless
touching CUDA kernels).

---

## Setup: Launch a Long-Lived Container

```bash
wsl -e bash -c "
export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml
/home/elizabeth/.runai/bin/runai workspace submit <name> \
  -p talmo-lab \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --image-pull-policy Always \
  --gpu-devices-request 1 \
  --preemptible \
  --host-path path=/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/flapping_wing,mount=/workspace,readwrite \
  -- bash -c 'cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
    mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex /workspace/inputs.3d.validation \
    2>&1 | tee /workspace/sim.log; sleep infinity'
"
```

The `sleep infinity` keeps the container alive after the simulation finishes so you can
exec into it for debugging and in-place rebuilds.

---

## Workspace Mount Mapping

| Location | Path |
|----------|------|
| Windows (local) | `Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\` |
| Cluster NFS | `/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/flapping_wing/` |
| Inside container | `/workspace/` |

`Z:` = `\\multilab-na.ad.salk.edu\hpi_dev` (mapped via Salk VPN / multilab-na)

The **IAMReX source** is baked into the image at `/opt/cfd/IAMReX/Source/` — it is NOT
volume-mounted. You must copy files in after staging them to `/workspace/`.

---

## Fast Iteration Loop

### 1. Edit locally
Edit IAMReX source files in `c:\repos\IAMReX-fork\Source\`:
```
DiffusedIB.cpp
DiffusedIB.H
ExternalGeometry.H
WingKinematics.H
VertexFileReader.H
```

### 2. Stage to shared workspace
```powershell
cp c:\repos\IAMReX-fork\Source\DiffusedIB.cpp "Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\"
cp c:\repos\IAMReX-fork\Source\DiffusedIB.H   "Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\"
cp c:\repos\IAMReX-fork\Source\ExternalGeometry.H "Z:\users\eberrigan\mosquito-cfd\examples\flapping_wing\"
```
Or in bash:
```bash
WSDIR="Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing"
cp c:/repos/IAMReX-fork/Source/DiffusedIB.cpp "$WSDIR/"
cp c:/repos/IAMReX-fork/Source/DiffusedIB.H  "$WSDIR/"
cp c:/repos/IAMReX-fork/Source/ExternalGeometry.H "$WSDIR/"
```

### 3. Install and rebuild inside container
```bash
CONTAINER=flapping-wing-val7
RUNAI="wsl -e bash -c 'export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && /home/elizabeth/.runai/bin/runai workspace exec $CONTAINER --'"

# Copy into source tree
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
  /home/elizabeth/.runai/bin/runai workspace exec $CONTAINER -- sh -c \
  'cp /workspace/DiffusedIB.cpp /workspace/DiffusedIB.H /workspace/ExternalGeometry.H \
   /opt/cfd/IAMReX/Source/ && echo Installed'"

# Build (CPU debug — fast, ~2 min, no CUDA required)
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
  /home/elizabeth/.runai/bin/runai workspace exec $CONTAINER -- sh -c \
  'cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
   make -j\$(nproc) > /workspace/make.log 2>&1 && echo BUILD_OK || echo BUILD_FAIL'"

# Check result
tail -5 "Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/make.log"
```

### 4. Run logic test
```bash
# 5-step CPU test (fast, ~3 min, verifies logic without GPU overhead)
wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml && \
  /home/elizabeth/.runai/bin/runai workspace exec $CONTAINER -- sh -c \
  'cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere && \
   mpirun --allow-run-as-root -np 1 ./amr3d.gnu.DEBUG.MPI.ex \
   /workspace/inputs.3d.validation max_step=5 amr.plot_int=0 amr.check_int=0 \
   > /workspace/test.log 2>&1'"

# Check velocities
grep "max.abs.u" "Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/test.log"
```

---

## Build Targets

| Command | Executable | When to use |
|---------|-----------|-------------|
| `make -j$(nproc)` | `amr3d.gnu.DEBUG.MPI.ex` | Logic testing — fast incremental build, no GPU needed |
| `make -j$(nproc) USE_CUDA=TRUE` | `amr3d.gnu.MPI.CUDA.ex` | GPU validation — required for cluster runs; ~10 min |

The validation submission command uses `amr3d.gnu.MPI.CUDA.ex`. Always rebuild the CUDA
binary before committing if your changes affect GPU kernels.

---

## When to Do a Full Docker Rebuild

Only needed when:
- Adding new dependencies (new AMReX versions, new `.cpp` files to the build)
- Changes that need to be reproducible in CI/other environments
- Final validation before submission to compute cluster

Full rebuild workflow:
1. Commit changes to `talmolab/IAMReX` `feature/arbitrary-geometry`
2. Update `IAMREX_COMMIT` in `docker/build-args.env` and `docker/Dockerfile.fp64`
3. Push to `talmolab/mosquito-cfd` `main` → GHA builds new `:fp64` image (~16 min)
4. Resubmit validation job: `runai workspace submit ... --image-pull-policy Always ...`

---

## Checking CI / Logs

```bash
# List recent CI runs (requires no expired GITHUB_TOKEN — unset if you get 403)
unset GITHUB_TOKEN && gh run list --repo talmolab/mosquito-cfd --limit 5

# View failed job logs
unset GITHUB_TOKEN && gh run view <run-id> --repo talmolab/mosquito-cfd --log-failed

# Check build.log from inside container (via Z: drive)
tail -20 "Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/make.log"
tail -40 "Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/test.log"
```

> **Note**: If `gh` commands fail with HTTP 403, run `unset GITHUB_TOKEN` first.
> The system GITHUB_TOKEN (if set) may be a fine-grained token that the `talmolab` org
> blocks for tokens with lifetime > 366 days.