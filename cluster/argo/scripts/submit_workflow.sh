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
# `smoke` and `full` both provision WORKSPACE_HOSTPATH from CORPUS_DIR before submitting (issue
# #62: nothing previously staged the NFS workspace from the committed corpus, so a stale/wrong
# wing.vertex could sit there undetected). Flags:
#   --corpus-dir DIR      Local corpus directory to stage (default: examples/prelim_sweep). Its
#                         basename MUST match --workspace-hostpath's basename -- provision refuses
#                         a mismatch (e.g. a coarse corpus-dir paired with a fine workspace-hostpath).
#   --no-provision        Skip provisioning (the operator has already verified NFS is current).
#
# IMPORTANT: pin --image to the POST-MERGE :fp64 @sha256: digest (the value emitted by the
# docker.yml "Emit FP64 image digest to job summary" step on the merge commit — never an older one).
# See cluster/argo/README.md for the full precondition checklist.
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Respect a pre-set SWEEP_WORKFLOW_FILE (e.g. a test injecting a mangled copy to exercise the parallelism
# patch's failure path) -- matches the "${VAR:-default}" idiom already used below for every other
# override in this script. Normal invocations never set this, so behavior is unchanged. NOTE:
# this seam is script-wide, not scoped to `full` -- `lint` also reads $SWEEP_WORKFLOW_FILE, so a stray
# `export SWEEP_WORKFLOW_FILE=...` left over from testing would silently make `lint` validate the wrong file.
SWEEP_WORKFLOW_FILE="${SWEEP_WORKFLOW_FILE:-$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-sweep.yaml}"
SMOKE_WORKFLOW="$(cd "$SCRIPT_DIR/../workflows" && pwd)/force-surrogate-smoke.yaml"
TEMPLATE="$(cd "$SCRIPT_DIR/../workflow-templates" && pwd)/force-surrogate-single-config.yaml"

NAMESPACE="${ARGO_NAMESPACE:-runai-talmo-lab}"
IMAGE="${FP64_IMAGE:-}"            # ghcr.io/talmolab/mosquito-cfd@sha256:<digest> — REQUIRED
WORKSPACE_HOSTPATH="${WORKSPACE_HOSTPATH:-/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep}"
# The local, git-committed corpus directory that `provision` stages onto WORKSPACE_HOSTPATH before
# submission (issue #62: nothing previously did this, so a stale/wrong NFS copy could sit
# undetected — confirmed this session for the coarse corpus's wing.vertex). Keep this in sync with
# WORKSPACE_HOSTPATH's basename (provision enforces this) when overriding either for another corpus.
CORPUS_DIR="${CORPUS_DIR:-examples/prelim_sweep}"
WING_VERTEX_SOURCE="${WING_VERTEX_SOURCE:-examples/flapping_wing/wing.vertex}"
# Overridable so tests can substitute a stub that deliberately reports a wrong hash (to exercise
# provision()'s die-on-mismatch branch) -- some shells resolve well-known coreutils names to a
# fixed trusted location regardless of PATH, making a PATH-based stub unreliable for this one.
SHA256SUM="${SHA256SUM:-sha256sum}"
NO_PROVISION=""   # empty = provision (default, on); set by --no-provision
# Cluster-hostPath vs. WSL-mount-point prefixes (openspec/project.md's path-mapping table).
# submit_workflow.sh runs inside WSL, so WORKSPACE_HOSTPATH's cluster-hostPath string (correct as
# an opaque value handed to `argo submit`) must be translated before any local filesystem op.
CLUSTER_NFS_PREFIX="${CLUSTER_NFS_PREFIX:-/hpi/hpi_dev}"
LOCAL_NFS_PREFIX="${LOCAL_NFS_PREFIX:-/mnt/hpi_dev}"
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
# Empty = flag not given = submit $SWEEP_WORKFLOW_FILE unpatched (true no-op, no second hardcoded default
# that could drift from the committed file's actual value). Only sed-patch a temp copy when this
# is explicitly set via --parallelism.
PARALLELISM=""

die() { echo "ERROR: $*" >&2; exit 1; }

require_image() {
  [[ -n "$IMAGE" ]] || die "set --image (or FP64_IMAGE) to the POST-MERGE :fp64 @sha256: digest"
  [[ "$IMAGE" == *"@sha256:"* ]] || die "pin --image by @sha256: digest, not a mutable tag ($IMAGE)"
}

# Translate a cluster-hostPath string (the value handed to `argo submit`) to the path WSL's own
# filesystem can actually read/write. A pure string substitution -- no filesystem access itself,
# so it's trivially unit-testable without any real mount. Anchored on a path-component boundary
# (exact match or followed by "/") so a sibling export sharing the prefix STRING but not the path
# (e.g. /hpi/hpi_dev_archive) is never silently mistranslated onto /mnt/hpi_dev's tree.
to_local_path() {
  local p="$1"
  case "$p" in
    "$CLUSTER_NFS_PREFIX"|"$CLUSTER_NFS_PREFIX"/*) echo "${LOCAL_NFS_PREFIX}${p#$CLUSTER_NFS_PREFIX}" ;;
    *) echo "$p" ;;   # already a local/relative path (e.g. a tmp_path fixture in tests)
  esac
}

# Stage the local, git-committed corpus onto the (translated) NFS workspace before submission.
# require_manifest distinguishes `full` (reads sweep_manifest.json) from `smoke` (a single named
# deck, never reads the manifest -- see force-surrogate-smoke.yaml).
provision() {
  local corpus_dir="$1" workspace_hostpath="$2" require_manifest="$3"
  local local_workspace; local_workspace="$(to_local_path "$workspace_hostpath")"

  # All preconditions are checked BEFORE any mutation below -- a bad WING_VERTEX_SOURCE used to be
  # checked only after inputs/ was already wiped and replaced, so a failure here left the workspace
  # in a half-migrated state (fresh decks, stale geometry) -- exactly the defect class this whole
  # step exists to close, just reached through a different trigger. Fail fast, mutate nothing.
  [[ -e "$corpus_dir" ]] || die "corpus dir $corpus_dir does not exist"
  [[ -d "$corpus_dir" ]] || die "corpus dir $corpus_dir exists but is not a directory"
  [[ -d "$corpus_dir/inputs" ]] || die "corpus dir $corpus_dir has no inputs/ -- generate it first"
  if [[ "$require_manifest" == "true" ]]; then
    [[ -f "$corpus_dir/sweep_manifest.json" ]] || die "corpus dir $corpus_dir has no sweep_manifest.json"
    [[ -f "$corpus_dir/sweep_manifest.units.json" ]] || die "corpus dir $corpus_dir has no sweep_manifest.units.json"
  fi
  [[ -f "$WING_VERTEX_SOURCE" ]] || die "canonical wing.vertex source $WING_VERTEX_SOURCE does not exist"
  # The exact defect this step exists to prevent: a coarse corpus-dir silently provisioned onto a
  # fine workspace-hostpath (or vice versa) because the two flags were overridden independently.
  [[ "$(basename "$corpus_dir")" == "$(basename "$workspace_hostpath")" ]] \
    || die "corpus-dir '$corpus_dir' and workspace-hostpath '$workspace_hostpath' name different corpora -- pass matching --corpus-dir/--workspace-hostpath"

  mkdir -p "$local_workspace" || die "cannot create/access local workspace path $local_workspace (resolved from $workspace_hostpath)"
  # Replace, don't merge: `cp -r`/`cp` into existing content only adds/overwrites, so a config or
  # manifest file dropped from a shrunk/changed corpus would otherwise survive undetected -- the
  # same class of silent-stale-content defect (#62) this whole step exists to close. Remove prior
  # inputs/ and any prior sweep_manifest*.json before staging the current corpus's.
  rm -rf "${local_workspace:?}/inputs"
  cp -r "$corpus_dir/inputs" "$local_workspace/"
  if [[ "$require_manifest" == "true" ]]; then
    rm -f "${local_workspace:?}"/sweep_manifest*.json
    cp "$corpus_dir"/sweep_manifest*.json "$local_workspace/"
  fi
  cp "$WING_VERTEX_SOURCE" "$local_workspace/wing.vertex"   # always the canonical file
  # Verify by hash immediately -- fail loudly here, not hours later in a pod's mount retry loop.
  # Scoped to wing.vertex: the one artifact with a documented history of silently drifting.
  # inputs/ and the manifest rely on `cp`'s own failure under `set -euo pipefail` above (and, for
  # inputs/, the destructive rm -rf just above, which removes the only silent-survival path).
  # NOTE: GNU sha256sum prepends a literal backslash to its output line when the filename itself
  # contains a backslash (its own escaping convention) -- strip it so a Windows-style path in
  # WING_VERTEX_SOURCE doesn't corrupt the extracted hash via a stray leading "\".
  local expected actual
  expected="$("$SHA256SUM" "$WING_VERTEX_SOURCE" | cut -d' ' -f1)"; expected="${expected#\\}"
  actual="$("$SHA256SUM" "$local_workspace/wing.vertex" | cut -d' ' -f1)"; actual="${actual#\\}"
  [[ "$expected" == "$actual" ]] || die "provisioned wing.vertex hash mismatch after copy"
}

# Parse: first arg is the command, the rest are --flag value overrides.
COMMAND="${1:-help}"; shift || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image) IMAGE="$2"; shift 2;;
    --workspace-hostpath) WORKSPACE_HOSTPATH="$2"; shift 2;;
    --corpus-dir) CORPUS_DIR="$2"; shift 2;;
    --no-provision) NO_PROVISION="true"; shift 1;;
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
    echo "Linting manifests (the authoritative structural check): $TEMPLATE, $SWEEP_WORKFLOW_FILE ..."
    argo lint "$TEMPLATE" -n "$NAMESPACE"
    argo lint "$SWEEP_WORKFLOW_FILE" -n "$NAMESPACE"
    ;;
  smoke)
    require_image
    [[ -n "$NO_PROVISION" ]] || provision "$CORPUS_DIR" "$WORKSPACE_HOSTPATH" false
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
    [[ -n "$NO_PROVISION" ]] || provision "$CORPUS_DIR" "$WORKSPACE_HOSTPATH" true
    workflow_file="$SWEEP_WORKFLOW_FILE"
    if [[ -n "$PARALLELISM" ]]; then
      [[ "$PARALLELISM" =~ ^[1-9][0-9]*$ ]] \
        || die "--parallelism must be a positive integer (got: $PARALLELISM)"
      # `|| true` is required under `set -euo pipefail`: grep -c on ZERO matches exits non-zero,
      # which would otherwise kill the script here instead of reaching the die() message below.
      n_matches=$(grep -c '^  parallelism: [0-9]\+$' "$SWEEP_WORKFLOW_FILE" || true)
      [[ "$n_matches" -eq 1 ]] \
        || die "expected exactly one top-level 'parallelism:' line in $SWEEP_WORKFLOW_FILE, found $n_matches"
      tmp="$(mktemp --suffix=.yaml)"
      trap 'rm -f "$tmp"' EXIT
      sed -E "s/^(  parallelism: )[0-9]+\$/\1${PARALLELISM}/" "$SWEEP_WORKFLOW_FILE" > "$tmp"
      grep -q "^  parallelism: ${PARALLELISM}\$" "$tmp" \
        || die "parallelism patch did not apply as expected"
      workflow_file="$tmp"
    fi
    echo "Submitting the full fan-out sweep ($workflow_file; image=$IMAGE, timestamp=$TIMESTAMP, parallelism=${PARALLELISM:-unchanged}) ..."
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
    sed -n '2,30p' "${BASH_SOURCE[0]}"
    ;;
  *)
    die "unknown command: $COMMAND (try: template | lint | smoke | full | help)"
    ;;
esac
