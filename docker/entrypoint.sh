#!/bin/bash
# =============================================================================
# Mosquito CFD Container Entrypoint
# =============================================================================

set -e

# Display build information
echo "=============================================="
echo "Mosquito CFD - IAMReX Container"
echo "=============================================="
echo ""
echo "Build Configuration:"
echo "  Precision:     ${PRECISION:-FP32}"
echo "  CUDA Arch:     ${CUDA_ARCH:-86}"
echo "  AMREX_HOME:    ${AMREX_HOME}"
echo ""
echo "Executables:"
ls -la /opt/cfd/IAMReX/Tutorials/FlowPastSphere/*.ex 2>/dev/null || echo "  (none found)"
echo ""
echo "Python Tools:"
echo "  generate-wing-planform  - Generate wing vertex files from parametric planform"
echo ""
echo "Quick Start:"
echo "  # Run FlowPastSphere example"
echo "  cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere"
echo "  mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex inputs.3d.flow_past_sphere max_step=10"
echo ""
echo "  # Generate wing vertex file (from mosquito-cfd project dir)"
echo "  cd /opt/cfd/mosquito-cfd && uv run generate-wing-planform --output /workspace/wing.vertex"
echo ""
echo "=============================================="

# If arguments provided, run them; otherwise start interactive shell
if [ $# -gt 0 ]; then
    exec "$@"
else
    exec /bin/bash
fi