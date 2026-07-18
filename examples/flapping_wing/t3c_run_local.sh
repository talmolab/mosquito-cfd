#!/usr/bin/env bash
# t3c_run_local.sh  — Fine-grid T3c run on local A5000 via Docker
#
# Intended to be executed INSIDE the fp64 container with /workspace mounted
# to examples/flapping_wing/.  Run from PowerShell:
#
#   docker run --rm --gpus all `
#     -v "c:/repos/mosquito-cfd/examples/flapping_wing:/workspace" `
#     ghcr.io/talmolab/mosquito-cfd:fp64 `
#     bash /workspace/t3c_run_local.sh 2>&1 | tee c:/repos/mosquito-cfd/examples/flapping_wing/sim-t3c-fine-local.log
#
# The run writes IB_Particle_1.csv (force data) to /workspace (= the host
# flapping_wing/ dir).  Plotfiles and checkpoints are suppressed to save disk.
#
# Differences vs cluster deck (inputs.3d.convergence_fine):
#   amrex.the_arena_init_size=18  (A5000 has 24 GB; default 3/4=18 GB anyway)
#   ns.fixed_dt=0.00025           D6 fallback: CFL=0.224 at Δx=0.03125
#   max_step=4000                 4000 * 0.00025 = 1.0 exactly one wingbeat
#   amr.plot_int=9999             no plotfiles (we only need forces CSV)
#   amr.check_int=9999            no checkpoints

set -euo pipefail

EXEC="/opt/cfd/IAMReX/Tutorials/FlowPastSphere/amr3d.gnu.MPI.CUDA.ex"
INPUTS="/workspace/inputs.3d.convergence_fine"

cd /workspace  # wing.vertex is a relative path in the inputs file

echo "=== T3c fine-grid local run started at $(date) ==="
echo "=== A5000 24 GB, arena cap 18 GiB, dt=0.00025, steps=4000 ==="

mpirun --allow-run-as-root -n 1 "${EXEC}" "${INPUTS}" \
  amrex.the_arena_init_size=18 \
  ns.fixed_dt=0.00025 \
  max_step=4000 \
  amr.plot_int=9999 \
  amr.check_int=9999

EXIT_CODE=$?
echo "=== DONE_EXIT=${EXIT_CODE} at $(date) ==="
exit "${EXIT_CODE}"
