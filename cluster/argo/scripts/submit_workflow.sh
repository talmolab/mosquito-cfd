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
#              --parallelism N overrides the submitted workflow's concurrency (default: the
#              committed force-surrogate-sweep.yaml's own value, unpatched) by submitting an
#              anchored, self-verifying sed-patched temp copy -- the committed file is never
#              edited. Omit the flag to submit the committed file exactly as-is.
#
# IMPORTANT: pin --image to the POST-MERGE :fp64 @sha256: digest (the value emitted by the
# docker.yml "Emit FP64 image digest to job summary" step on the merge commit — never an older one).
# See cluster/argo/README.md for the full precondition checklist.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Respect a pre-set WORKFLOW (e.g. a test injecting a mangled copy to exercise the parallelism
# patch's failure path) -- matches the "${VAR:-default}" idiom already used below for every other
# override in this script. Normal invocations never set this, so behavior is unchanged. NOTE:
# this seam is script-wide, not scoped to `full` -- `lint` also reads $WORKFLOW, so a stray
# `export WORKFLOW=...` left over from testing would silently make `lint` validate the wrong file.
WORKFLOW="${WORKFLOW:-$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-sweep.yaml}"
SMOKE_WORKFLOW="$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-smoke.yaml"
TEMPLATE="$(cd "$SCRIPT_DIR/../workflow-templates" && pwd)/force-surrogate-single-config.yaml"

NAMESPACE="${ARGO_NAMESPACE:-runai-talmo-lab}"
IMAGE="${FP64_IMAGE:-}"            # ghcr.io/talmolab/mosquito-cfd@sha256:<digest> — REQUIRED
WORKSPACE_HOSTPATH="${WORKSPACE_HOSTPATH:-/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep}"
# A reproducible caller timestamp recorded in every run_metadata.json (override with TIMESTAMP=...).
TIMESTAMP="${TIMESTAMP:-$(date -u +%Y-%m-%dT%H:%M:%S%z)}"
# The force-CSV name (escape hatch; verify on the smoke run). Threaded to pods + verify-complete.
CSV_NAME="${CSV_NAME:-IB_Particle_1.csv}"
# For `smoke`: which single config to run as the pre-flight (defaults to the first sweep config).
SMOKE_CONFIG_NAME="${SMOKE_CONFIG_NAME:-s35_f085_p30}"
SMOKE_INPUT_FILE="${SMOKE_INPUT_FILE:-inputs/inputs.3d.s35_f085_p30}"
SMOKE_MAX_STEP="${SMOKE_MAX_STEP:-4706}"
# Per-pod host RAM (K8s memory, distinct from GPU VRAM). Defaults match the
# add-fine-grid-training-pilot bump; override for a coarse-grid-sized re-run (e.g.
# POD_MEMORY_LIMIT=32Gi POD_MEMORY_REQUEST=16Gi) without editing the shared WorkflowTemplate.
POD_MEMORY_LIMIT="${POD_MEMORY_LIMIT:-64Gi}"
POD_MEMORY_REQUEST="${POD_MEMORY_REQUEST:-32Gi}"
# Empty = flag not given = submit $WORKFLOW unpatched (true no-op, no second hardcoded default
# that could drift from the committed file's actual value). Only sed-patch a temp copy when this
# is explicitly set via --parallelism.
PARALLELISM=""

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
    --csv-name) CSV_NAME="$2"; shift 2;;
    --namespace) NAMESPACE="$2"; shift 2;;
    --pod-memory-limit) POD_MEMORY_LIMIT="$2"; shift 2;;
    --pod-memory-request) POD_MEMORY_REQUEST="$2"; shift 2;;
    --parallelism) PARALLELISM="$2"; shift 2;;
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
    # Submitted as a wrapper Workflow (not --from workflowtemplate) so the nfs-workspace volume the
    # template mounts is actually defined — a bare --from would reference an undefined volume.
    argo submit "$SMOKE_WORKFLOW" -n "$NAMESPACE" --watch \
      --parameter image="$IMAGE" \
      --parameter docker-digest="$IMAGE" \
      --parameter timestamp="$TIMESTAMP" \
      --parameter workspace-hostpath="$WORKSPACE_HOSTPATH" \
      --parameter config-name="$SMOKE_CONFIG_NAME" \
      --parameter input-file="$SMOKE_INPUT_FILE" \
      --parameter max-step="$SMOKE_MAX_STEP" \
      --parameter csv-name="$CSV_NAME" \
      --parameter pod-memory-limit="$POD_MEMORY_LIMIT" \
      --parameter pod-memory-request="$POD_MEMORY_REQUEST"
    ;;
  full)
    require_image
    workflow_file="$WORKFLOW"
    if [[ -n "$PARALLELISM" ]]; then
      [[ "$PARALLELISM" =~ ^[1-9][0-9]*$ ]] \
        || die "--parallelism must be a positive integer (got: $PARALLELISM)"
      # `|| true` is required under `set -euo pipefail`: grep -c on ZERO matches exits non-zero,
      # which would otherwise kill the script here instead of reaching the die() message below.
      n_matches=$(grep -c '^  parallelism: [0-9]\+$' "$WORKFLOW" || true)
      [[ "$n_matches" -eq 1 ]] \
        || die "expected exactly one top-level 'parallelism:' line in $WORKFLOW, found $n_matches"
      tmp="$(mktemp --suffix=.yaml)"
      trap 'rm -f "$tmp"' EXIT
      sed -E "s/^(  parallelism: )[0-9]+\$/\1${PARALLELISM}/" "$WORKFLOW" > "$tmp"
      grep -q "^  parallelism: ${PARALLELISM}\$" "$tmp" \
        || die "parallelism patch did not apply as expected"
      workflow_file="$tmp"
    fi
    echo "Submitting the full fan-out sweep (image=$IMAGE, timestamp=$TIMESTAMP, parallelism=${PARALLELISM:-unchanged}) ..."
    argo submit "$workflow_file" -n "$NAMESPACE" --watch \
      --parameter image="$IMAGE" \
      --parameter docker-digest="$IMAGE" \
      --parameter timestamp="$TIMESTAMP" \
      --parameter workspace-hostpath="$WORKSPACE_HOSTPATH" \
      --parameter csv-name="$CSV_NAME" \
      --parameter pod-memory-limit="$POD_MEMORY_LIMIT" \
      --parameter pod-memory-request="$POD_MEMORY_REQUEST"
    ;;
  help|--help|-h)
    sed -n '2,22p' "${BASH_SOURCE[0]}"
    ;;
  *)
    die "unknown command: $COMMAND (try: template | lint | smoke | full | help)"
    ;;
esac
