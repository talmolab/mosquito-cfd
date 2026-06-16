#!/usr/bin/env bash
# ==============================================================================
# Monitor the force-surrogate Argo sweep (add-force-surrogate-argo-sweep)
# ==============================================================================
# Run from WSL with KUBECONFIG exported, e.g.:
#   wsl -e bash -c "export KUBECONFIG=~/.kube/kubeconfig-runai-talmo-lab.yaml \
#     && cluster/argo/scripts/monitor_workflow.sh logs force-surrogate-sweep-abcde"
#
# Commands:
#   list                      List force-surrogate workflows in the namespace
#   get   <workflow-name>     Show the DAG status / node tree for one workflow
#   logs  <workflow-name>     Follow logs across all pods of one workflow
#   stop  <workflow-name>     Terminate a workflow (pod teardown frees the A40 — no orphaned amr3d)
# ==============================================================================
set -euo pipefail

NAMESPACE="${ARGO_NAMESPACE:-runai-talmo-lab}"
COMMAND="${1:-list}"
NAME="${2:-}"

die() { echo "ERROR: $*" >&2; exit 1; }
require_name() { [[ -n "$NAME" ]] || die "this command needs a <workflow-name> (see: monitor_workflow.sh list)"; }

case "$COMMAND" in
  list)
    argo list -n "$NAMESPACE" | grep -E "force-surrogate|NAME" || echo "no force-surrogate workflows"
    ;;
  get)
    require_name
    argo get "$NAME" -n "$NAMESPACE"
    ;;
  logs)
    require_name
    argo logs "$NAME" -n "$NAMESPACE" --follow
    ;;
  stop)
    require_name
    argo terminate "$NAME" -n "$NAMESPACE"
    ;;
  help|--help|-h)
    sed -n '2,18p' "${BASH_SOURCE[0]}"
    ;;
  *)
    die "unknown command: $COMMAND (try: list | get | logs | stop | help)"
    ;;
esac
