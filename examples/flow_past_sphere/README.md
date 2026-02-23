# Flow Past Sphere Example

Classic CFD validation case: uniform flow past a stationary sphere using the immersed boundary method.

## Physical Setup

```
Flow direction →
           ___
         /     \
    →   (   ●   )   →  Wake region
         \ ___ /

   Inflow          Sphere (r=0.5)      Outflow
   u = 1.0         at (5,5,5)
```

## Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Domain | 20 × 10 × 10 | Length allows wake development |
| Grid | 256 × 128 × 128 | ~4M cells |
| Reynolds | ~100 | Re = U·D/ν = 1.0·1.0/0.01 |
| Timestep | 0.01 | Fixed dt, CFL=0.3 |

## Running on Salk Cluster

```bash
# Submit workspace with persistent storage (outputs saved to cluster filesystem)
runai workspace submit <your-name>-cfd \
  --image ghcr.io/talmolab/mosquito-cfd:fp64 \
  --gpu-devices-request 1 \
  --preemptible \
  --host-path path=/hpi/hpi_dev/users/<username>/mosquito-cfd/examples/flow_past_sphere,mount=/workspace,readwrite

# Inside container:
cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=100
```

## Output Files

- `plt*` - Plot files (viewable with yt, VisIt, ParaView)
- `chk*` - Checkpoint files (for restarting)
- `Backtrace.*` - Debug info if simulation crashes

Outputs are saved to the mounted directory on the cluster filesystem and persist after the workspace exits.

## Performance

Verified on A40 GPU (Salk cluster):
- 100 timesteps: ~566 seconds (~9.4 minutes)
- Output files: ~1.4 GB for plt00100, ~1.4 GB for chk00100

## Visualization

Use yt (included in mosquito-cfd Python package):

```python
import yt
ds = yt.load("plt00100")
slc = yt.SlicePlot(ds, "z", "x_velocity")
slc.save()
```