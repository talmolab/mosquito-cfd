#!/usr/bin/env bash
# ==============================================================================
# Submit the force-surrogate Argo sweep (add-force-surrogate-argo-sweep)
# ==============================================================================
# Run this from WSL with KUBECONFIG already exported, e.g.:
#   wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
#     && cluster/argo/scripts/submit_workflow.sh full --image ghcr.io/talmolab/mosquito-cfd@sha256:<POST-MERGE digest>"
#
# Commands:
#   template   Install/update the single-config WorkflowTemplate on the cluster
#   lint       argo lint both manifests (authoritative structural validation)
#   smoke      Submit ONE config via the template (scheduling/GPU pre-flight before the 27-way fan-out)
#   full       Submit the full fan-out sweep workflow
#
# IMPORTANT: pin --image to the POST-MERGE :fp64 @sha256: digest (the value emitted by the
# docker.yml "Emit FP64 image digest to job summary" step on the merge commit — never an older one).
# See cluster/argo/README.md for the full precondition checklist.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW="$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-sweep.yaml"
TEMPLATE="$(cd "$SCRIPT_DIR/../workflow-templates" && pwd)/force-surrogate-single-config.yaml"

NAMESPACE="${ARGO_NAMESPACE:-runai-talmo-lab}"
IMAGE="${FP64_IMAGE:-}"            # ghcr.io/talmolab/mosquito-cfd@sha256:<digest> — REQUIRED
WORKSPACE_HOSTPATH="${WORKSPACE_HOSTPATH:-/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep}"
# A reproducible caller timestamp recorded in every run_metadata.json (override with TIMESTAMP=...).
TIMESTAMP="${TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%S%z)}"
# For `smoke`: which single config to run as the pre-flight (defaults to the first sweep config).
SMOKE_CONFIG_NAME="${SMOKE_CONFIG_NAME:-s35_f085_p30}"
SMOKE_INPUT_FILE="${SMOKE_INPUT_FILE:-inputs/inputs.3d.s35_f085_p30}"
SMOKE_MAX_STEP="${SMOKE_MAX_STEP:-4706}"

die() { echo "ERROR: $*" >&2; exit 1; }

require_image() {
  [[ -n "$IMAGE" ]] || die "set --image (or FP64_IMAGE) to the POST-MERGE :fp64 @sha256: digest"
  [[ "$IMAGE" == *"@sha256:"* ]] || die "pin --image by @sha256: digest, not a mutable tag ($IMAGE)"
}

# Parse: first arg is the command, the rest are --flag value overrides.
COMMAND="${1:-help}"; shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2;;
    --workspace-hostpath) WORKSPACE_HOSTPATH="$2"; shift 2;;
    --timestamp) TIMESTAMP="$2"; shift 2;;
    --namespace) NAMESPACE="$2"; shift 2;;
    *) die "unknown option: $1";;
  esac
done

case "$COMMAND" in
  template)
    echo "Installing WorkflowTemplate into $NAMESPACE ..."
    argo template create "$TEMPLATE" -n "$NAMESPACE" 2>/dev/null \
      || argo template update "$TEMPLATE" -n "$NAMESPACE"
    ;;
  lint)
    echo "Linting manifests (the authoritative structural check) ..."
    argo lint "$TEMPLATE" -n "$NAMESPACE"
    argo lint "$WORKFLOW" -n "$NAMESPACE"
    ;;
  smoke)
    require_image
    echo "1-config smoke pre-flight ($SMOKE_CONFIG_NAME) — confirms scheduling + GPU before the fan-out ..."
    argo submit --from "workflowtemplate/force-surrogate-single-config" -n "$NAMESPACE" --watch \
      -p image="$IMAGE" \
      -p config-name="$SMOKE_CONFIG_NAME" \
      -p input-file="$SMOKE_INPUT_FILE" \
      -p max-step="$SMOKE_MAX_STEP" \
      -p docker-digest="$IMAGE" \
      -p timestamp="$TIMESTAMP"
    ;;
  full)
    require_image
    echo "Submitting the full fan-out sweep (image=$IMAGE, timestamp=$TIMESTAMP) ..."
    argo submit "$WORKFLOW" -n "$NAMESPACE" --watch \
      --parameter image="$IMAGE" \
      --parameter docker-digest="$IMAGE" \
      --parameter timestamp="$TIMESTAMP" \
      --parameter workspace-hostpath="$WORKSPACE_HOSTPATH"
    ;;
  help|--help|-h)
    sed -n '2,22p' "${BASH_SOURCE[0]}"
    ;;
  *)
    die "unknown command: $COMMAND (try: template | lint | smoke | full | help)"
    ;;
esac
