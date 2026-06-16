"""Text-assertion tests for the Argo sweep manifests (add-force-surrogate-argo-sweep).

These guard the *presence and co-location* of the load-bearing contract fields in the operator-
authored YAML, cluster-free and with no new dependency (no ``pyyaml`` → no ``uv.lock``/``uv sync
--frozen`` image-build coupling). Structural validity — indentation, schema, reparented keys — is
delegated to operator-side ``argo lint`` + a 1-config smoke submit (see ``cluster/argo/README.md``);
the GPU/root asserts here are **block-anchored** (the gpu line in the indented block immediately
following ``limits:``; ``runAsUser: 0`` under ``securityContext``) so a ``requests:``-vs-``limits:``
swap cannot pass, and the ``.venv`` interpreter is asserted as a **contiguous** command vector so
``uv run`` cannot sneak in.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ARGO = REPO / "cluster" / "argo"
TEMPLATE = ARGO / "workflow-templates" / "force-surrogate-single-config.yaml"
WORKFLOW = ARGO / "workflows" / "force-surrogate-sweep.yaml"
SMOKE = ARGO / "workflows" / "force-surrogate-smoke.yaml"


def _read(path: Path) -> str:
    assert path.exists(), f"missing Argo manifest: {path.relative_to(REPO)}"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Single-config WorkflowTemplate
# ---------------------------------------------------------------------------


def test_single_config_template_scheduling_identity():
    """Scenario: each config runs as root, preemptible, in the lab namespace, as default SA."""
    text = _read(TEMPLATE)
    assert "serviceAccountName: default" in text  # mandatory for workflowtaskresults
    assert "namespace: runai-talmo-lab" in text
    assert 'runai/preemptible: "true"' in text


def test_single_config_template_retry_strategy():
    """Scenario: a dropped/preempted run is retried on a fresh pod."""
    text = _read(TEMPLATE)
    assert "retryStrategy:" in text
    assert re.search(r"retryStrategy:\s*\n(?:\s+\S.*\n)*?\s+limit:\s*5", text), (
        "retryStrategy must set limit: 5"
    )
    assert 'retryPolicy: "OnFailure"' in text or "retryPolicy: OnFailure" in text


def test_single_config_template_runs_venv_python_not_uv_run():
    """Scenario: the pod runs the synced venv interpreter directly (not `uv run`)."""
    text = _read(TEMPLATE)
    # contiguous command vector — a comment mentioning .venv can't satisfy this, and uv run can't sneak in
    assert re.search(
        r'"/opt/cfd/mosquito-cfd/\.venv/bin/python"\s*,\s*"-m"\s*,\s*'
        r'"mosquito_cfd\.force_surrogate\.run_one_config"',
        text,
    ), "command must be the contiguous .venv python -m run_one_config vector"
    assert "uv run" not in text


def test_single_config_template_gpu_is_a_limit():
    """Scenario: each config gets a dedicated full A40 (gpu under limits:, not requests:)."""
    text = _read(TEMPLATE)
    # block-anchored: the gpu line sits in the indented block immediately following `limits:`
    assert re.search(r"limits:\s*\n(?:\s+\S.*\n)*?\s+nvidia\.com/gpu:\s*1", text), (
        "nvidia.com/gpu: 1 must appear under a limits: block"
    )


def test_single_config_template_runs_as_root_not_privileged():
    """Scenario: runs as root for mpirun (runAsUser: 0 under securityContext), NOT privileged."""
    text = _read(TEMPLATE)
    assert re.search(r"securityContext:\s*\n(?:\s+\S.*\n)*?\s+runAsUser:\s*0", text), (
        "runAsUser: 0 must appear under securityContext"
    )
    assert "privileged: true" not in text  # least-privilege (D1)


def test_single_config_template_records_provenance():
    """The template threads orchestrator provenance (workflow uid / pod / node / retry) as CLI args."""
    text = _read(TEMPLATE)
    assert "--workflow-uid" in text and "{{workflow.uid}}" in text
    assert "--pod" in text and "{{pod.name}}" in text
    assert "--retry" in text and "{{retries}}" in text
    # node name is downward-API only → passed via k8s env substitution $(NODE_NAME), declared as env
    assert "--node" in text and "$(NODE_NAME)" in text
    assert (
        "fieldPath: spec.nodeName" in text
    )  # the NODE_NAME env is the node, not the pod


def test_single_config_template_threads_csv_name():
    """The force-CSV name escape hatch is a template parameter passed to the entrypoint."""
    text = _read(TEMPLATE)
    assert "--csv-name" in text and "{{inputs.parameters.csv-name}}" in text


# ---------------------------------------------------------------------------
# Fan-out Workflow
# ---------------------------------------------------------------------------


def test_workflow_has_image_and_parallelism_and_deadline():
    """Scenario: concurrency and total runtime are bounded; image pinned at submit."""
    text = _read(WORKFLOW)
    assert re.search(r"-\s*name:\s*image", text), (
        "an `image` workflow parameter (pinned @sha256 at submit)"
    )
    assert re.search(r"\n\s*parallelism:\s*\d+", text), (
        "a spec-level parallelism cap (bounded concurrency)"
    )
    assert "activeDeadlineSeconds: 86400" in text  # 24h bound


def test_workflow_fans_out_over_manifest_configs():
    """Scenario: per-config tasks are derived from sweep_manifest.json, not a hardcoded list."""
    text = _read(WORKFLOW)
    assert "withParam:" in text  # fan-out, not withSequence/hardcoded
    assert "load_manifest_configs" in text
    assert "sweep_manifest.json" in text
    # no hardcoded s<NN>_f<NNN>_p<NN> config names anywhere
    assert not re.search(r"s\d+_f\d+_p\d+", text), (
        "configs must be derived, not hardcoded"
    )


def test_workflow_validate_and_verify_steps_present():
    """Scenarios: stale image caught before any GPU pod; completion gated by check_completion."""
    text = _read(WORKFLOW)
    assert "validate" in text
    # the validate step imports the module on the pinned image before the fan-out
    assert "import mosquito_cfd.force_surrogate.run_one_config" in text
    # a distinct verify-complete step gates on check_completion over every config
    assert "verify-complete" in text
    assert "check_completion" in text


def test_workflow_validate_hardens_digest_and_preflights_inputs():
    """The validate step fails fast (before any GPU pod) on a mutable/mismatched digest or missing inputs."""
    text = _read(WORKFLOW)
    assert "validate_image_digest" in text  # rejects a mutable docker-digest in seconds
    assert "image == digest" in text  # the pinned image and recorded digest must match
    assert (
        "wing.vertex" in text
    )  # geometry preflight (decks resolve geometry_file relative to run dir)
    # the per-config keys load_manifest_configs does NOT require are checked before fan-out —
    # anchored to the validate-step preflight loop (a bare "input_file"/"max_step" token also appears
    # in the fan-out args, so a loose substring would survive deleting this guard)
    assert re.search(r'for k in \("input_file", "max_step"\)', text)


def test_smoke_workflow_defines_the_nfs_volume():
    """The smoke wrapper defines the nfs-workspace volume the template mounts (the --from bug)."""
    text = _read(SMOKE)
    assert (
        "force-surrogate-single-config" in text
    )  # templateRefs the single-config template
    # block-anchored: a `volumes:` block declaring `- name: nfs-workspace` with a hostPath
    assert re.search(
        r"volumes:\s*\n(?:\s+\S.*\n)*?\s+-\s*name:\s*nfs-workspace", text
    ), "smoke workflow must DEFINE the nfs-workspace volume (not just mount it)"
    assert "hostPath:" in text
    assert "serviceAccountName: default" in text


def test_workflow_threads_csv_name_to_pods_and_verify():
    """The csv-name escape hatch is a workflow parameter threaded to pods and verify-complete."""
    text = _read(WORKFLOW)
    assert re.search(r"-\s*name:\s*csv-name", text)  # declared workflow parameter
    assert "{{workflow.parameters.csv-name}}" in text  # used (pods + verify-complete)
    # verify-complete builds the per-config CSV path from the param variable, not a hardcoded name
    assert "{c['name']}/{csv_name}" in text
    assert "{c['name']}/IB_Particle_1.csv" not in text  # the old hardcoded form is gone


def test_workflow_is_force_only():
    """Scenario: dataset extraction is not in scope of the workflow."""
    text = _read(WORKFLOW) + _read(TEMPLATE)
    for forbidden in ("extract_forces", "dataset.parquet", "plt", "plot_int"):
        assert forbidden not in text, (
            f"force-only: the workflow must not reference {forbidden!r}"
        )


def test_workflow_serviceaccount_and_namespace():
    """The fan-out workflow sets the mandatory serviceAccountName + lab namespace."""
    text = _read(WORKFLOW)
    assert "serviceAccountName: default" in text
    assert "namespace: runai-talmo-lab" in text
