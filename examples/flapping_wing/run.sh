#!/bin/bash
# Run flapping wing simulation with external geometry
#
# Usage (inside container):
#   cd /workspace
#   cp /path/to/flapping_wing/* .
#
#   # Quick validation (~10 min)
#   bash run.sh validation
#
#   # Production run (~1.4 hr/wingbeat, 3 wingbeats)
#   bash run.sh production
#
#   # Custom max_step
#   bash run.sh validation 500
#
# Requires geometry_type=4 support in IAMReX (talmolab fork)

MODE=${1:-validation}
MAX_STEP=${2:-}

cd /opt/cfd/IAMReX/Tutorials/FlowPastSphere

echo "=============================================="
echo "  Flapping Wing Simulation"
echo "  Mode: $MODE"
echo "=============================================="

# Check that wing.vertex exists
if [ ! -f /workspace/wing.vertex ]; then
    echo "ERROR: wing.vertex not found in /workspace/"
    echo "Copy the example files first:"
    echo "  cp /path/to/examples/flapping_wing/* /workspace/"
    exit 1
fi

# Select input file based on mode
case $MODE in
    validation|val|v)
        INPUTS="/workspace/inputs.3d.validation"
        [ -z "$MAX_STEP" ] && MAX_STEP=2000
        echo "  Quick validation: ~10 min"
        echo "  Grid: 64x32x64, f*=1.0, Re_eff=100"
        ;;
    production|prod|p)
        INPUTS="/workspace/inputs.3d.production"
        [ -z "$MAX_STEP" ] && MAX_STEP=30000
        echo "  Production run: ~4 hr (3 wingbeats)"
        echo "  Grid: 128x64x128, f*=0.1, Re=100"
        ;;
    *)
        # Assume it's a custom inputs file
        INPUTS="/workspace/$MODE"
        [ -z "$MAX_STEP" ] && MAX_STEP=1000
        echo "  Custom inputs file: $INPUTS"
        ;;
esac

if [ ! -f "$INPUTS" ]; then
    echo "ERROR: Input file not found: $INPUTS"
    exit 1
fi

echo "  Max steps: $MAX_STEP"
echo "  Output: /workspace/"
echo ""

# Run the simulation
mpirun --allow-run-as-root -np 1 ./amr3d.gnu.MPI.CUDA.ex $INPUTS \
  amr.plot_file=/workspace/plt \
  amr.check_file=/workspace/chk \
  max_step=$MAX_STEP

echo ""
echo "=============================================="
echo "Done! Output files:"
ls -la /workspace/plt* /workspace/chk* 2>/dev/null || echo "No output files found"
