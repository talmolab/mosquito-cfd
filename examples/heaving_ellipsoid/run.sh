#!/bin/bash
# Run heaving ellipsoid simulation with output to current directory
#
# Usage (inside container):
#   cd /workspace
#   bash run.sh [max_step]

MAX_STEP=${1:-100}

cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere

echo "Running heaving ellipsoid for $MAX_STEP steps..."
echo "Output will be saved to /workspace/"

mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex /workspace/inputs.3d.heaving_ellipsoid \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=$MAX_STEP

echo "Done! Output files:"
ls -la /workspace/plt* /workspace/chk* 2>/dev/null || echo "No output files found"