"""Tests for force_surrogate.metadata_capture (TDD, automate-run-metadata-capture).

Cluster-free: no live cluster, Argo, or RunAI access. Fixtures under
``tests/fixtures/run_metadata/`` are cross-checked against the real, already-committed,
already-corrected pilot config ``s35_f085_p45`` (see the fixtures' own README) as the TDD oracle.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mosquito_cfd.force_surrogate import metadata_capture as mc
from mosquito_cfd.force_surrogate.sidecar import capture_surrogate_run_metadata

_FIXTURES = Path(__file__).parent / "fixtures" / "run_metadata"
_CSV = _FIXTURES / "forces_s35_f085_p45.csv"
_POD_METADATA = _FIXTURES / "pod_run_metadata.json"
_RUN_LOG = _FIXTURES / "run.log"
_MANIFEST = _FIXTURES / "sweep_manifest.json"
_DECK = _FIXTURES / "inputs.3d.s35_f085_p45"
_ARGO_SIMPLE = _FIXTURES / "argo_status_simple.json"
_ARGO_RETRY = _FIXTURES / "argo_status_with_retry.json"
_ARGO_MULTI = _FIXTURES / "argo_status_multi_config.json"

_MULTI_POD_EARLIEST = "force-surrogate-sweep-vb8t5-run-config-1111111111"
_MULTI_POD_MIDDLE = "force-surrogate-sweep-vb8t5-run-config-2222222222"
_MULTI_POD_LATEST = "force-surrogate-sweep-vb8t5-run-config-3333333333"
_MULTI_POD_UNMATCHED = "force-surrogate-sweep-vb8t5-run-config-9999999999"

_REPO_ROOT = Path(__file__).parent.parent
_REAL_COMMITTED_METADATA = (
    _REPO_ROOT
    / "examples"
    / "prelim_sweep_fine_pilot"
    / "run_metadata_s35_f085_p45.json"
)

DIGEST = "sha256:" + "0" * 64


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 0.4 Fixture drift guard
# ---------------------------------------------------------------------------


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_subprocess_run(argv, **kwargs):
    if argv[:2] == ["git", "rev-parse"]:
        return _FakeCompleted(0, "0" * 40 + "\n")
    if argv[:2] == ["git", "symbolic-ref"]:
        return _FakeCompleted(0, "main\n")
    if argv[:2] == ["git", "diff"]:
        return _FakeCompleted(0, "")
    if argv[:2] == ["git", "remote"]:
        return _FakeCompleted(0, "https://github.com/talmolab/mosquito-cfd.git\n")
    if argv[0] == "nvidia-smi":
        return _FakeCompleted(0, "NVIDIA A40, 46068, 550.90.07\n")
    if argv[0] == "nvcc":
        return _FakeCompleted(0, "Cuda compilation tools, release 12.4, V12.4.99\n")
    raise AssertionError(f"unexpected subprocess call in fixture-drift test: {argv}")


def test_pilot_fixture_matches_real_capture_surrogate_run_metadata_shape(monkeypatch):
    """The hand-built fixture's key set matches what the real capture function produces.

    Guards against `benchmarks/metadata.py`/`sidecar.py`'s schema changing later without the
    fixture noticing (a silent-drift failure mode this whole change exists to prevent).
    """
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.subprocess.run", _fake_subprocess_run
    )
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.metadata.socket.gethostname", lambda: "gpu-node14"
    )

    real = capture_surrogate_run_metadata(
        docker_image_digest=DIGEST,
        timestamp="2026-01-01T00:00:00+00:00",
        extra={
            "config": "x",
            "deck": "y",
            "deck_sha256": "z",
            "command": ["mpirun"],
            "ib_particle_csv": "x/IB_Particle_1.csv",
            "log": "x/run.log",
            "rows": 1,
            "max_step": 1,
            "threshold": 0.99,
            "status": "completed",
            "orchestration": {
                "workflow_uid": "u",
                "pod": "p",
                "node": "n",
                "retry": "0",
            },
        },
    )
    fixture = _load_json(_POD_METADATA)
    assert set(real.keys()) == set(fixture.keys())


# ---------------------------------------------------------------------------
# 2. Force-CSV last-row reader
# ---------------------------------------------------------------------------


def test_read_final_time_from_csv_uses_last_row():
    final_time, timesteps = mc.read_final_time_from_csv(_CSV)
    assert final_time == 2.3525
    assert timesteps == 4706
    # Never the deck's stop_time.
    assert final_time != 2.3529411764705883


def test_read_final_time_raises_on_empty_csv(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("iStep,time\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data rows"):
        mc.read_final_time_from_csv(empty)


def test_read_final_time_raises_on_missing_csv_file(tmp_path):
    missing = tmp_path / "does_not_exist.csv"
    with pytest.raises(FileNotFoundError, match="does_not_exist.csv"):
        mc.read_final_time_from_csv(missing)


# ---------------------------------------------------------------------------
# 3. run.log Arena-max parser and stability derivation
# ---------------------------------------------------------------------------


def test_parse_arena_max_mib_from_run_log():
    assert mc.parse_arena_max_mib(_RUN_LOG) == 7998


def test_parse_arena_max_mib_returns_none_when_absent(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("STEP = 1 TIME = 0.0005\nAMReX finalized\n", encoding="utf-8")
    assert mc.parse_arena_max_mib(log) is None


def test_parse_arena_max_mib_raises_on_missing_log_file(tmp_path):
    missing = tmp_path / "run.log"
    with pytest.raises(FileNotFoundError, match="run.log"):
        mc.parse_arena_max_mib(missing)


def test_stability_derived_from_fixed_dt_alone():
    assert mc.derive_stability(5e-4) == "stable_at_5e-4"
    assert mc.derive_stability(2.5e-4) == "stable_at_2.5e-4_fallback"


def test_parse_arena_max_mib_from_real_gpu_run_log_format(tmp_path):
    """The real IAMReX GPU binary pads "[The Arena]" with extra spaces to column-align it with
    the longer Device/Managed/Pinned labels, and reports the figure inside a bracketed
    per-MPI-rank list with no adjacent unit suffix -- distinct from this fixture's older,
    synthetic "... 7998 MiB" phrasing. Caught via the full 27-config fine-grid corpus's real
    run.log files all parsing to arena_max_mib=None despite containing this exact line."""
    log = tmp_path / "run.log"
    log.write_text(
        "[The         Arena] max space (MB) allocated spread across MPI: [34052 ... 34052]\n"
        "[The         Arena] max space (MB) used      spread across MPI: [7998 ... 7998]\n"
        "[The Managed Arena] max space (MB) allocated spread across MPI: [8 ... 8]\n"
        "[The Managed Arena] max space (MB) used      spread across MPI: [0 ... 0]\n"
        "[The  Pinned Arena] max space (MB) allocated spread across MPI: [24 ... 24]\n"
        "[The  Pinned Arena] max space (MB) used      spread across MPI: [17 ... 17]\n",
        encoding="utf-8",
    )
    assert mc.parse_arena_max_mib(log) == 7998


def test_parse_arena_max_mib_reports_max_not_min_across_mpi_ranks(tmp_path):
    """AMReX's CArena::PrintUsage reports "[min ... max]" across MPI ranks. A genuinely
    multi-rank run has min != max; grabbing the first bracketed number (the min) would silently
    under-report the true peak -- invisible in this repo's single-rank runs, where min == max,
    until checked against the actual upstream AMReX source."""
    log = tmp_path / "run.log"
    log.write_text(
        "[The         Arena] max space (MB) used      spread across MPI: [100 ... 7998]\n",
        encoding="utf-8",
    )
    assert mc.parse_arena_max_mib(log) == 7998


def test_parse_arena_max_mib_ignores_other_arena_types(tmp_path):
    """A real GPU-build log also emits Device/Managed/Pinned Arena lines with different (here,
    larger) figures -- only "[The Arena]" itself should be reported, not the max across all."""
    log = tmp_path / "run.log"
    log.write_text(
        "[The Device Arena] Total space used (max across MPI ranks): 40000 MiB\n"
        "[The Arena] Total space used (max across MPI ranks): 7998 MiB\n"
        "[The Pinned Arena] Total space used (max across MPI ranks): 20000 MiB\n",
        encoding="utf-8",
    )
    assert mc.parse_arena_max_mib(log) == 7998


# ---------------------------------------------------------------------------
# 4. Manifest/deck sourcing
# ---------------------------------------------------------------------------


def test_kinematics_grid_fixed_dt_max_step_sourced_from_manifest():
    fields = mc.source_config_fields(
        manifest_path=_MANIFEST, deck_path=_DECK, config_name="s35_f085_p45"
    )
    assert fields["kinematics"] == {
        "stroke_amp_deg": 35.0,
        "frequency_fstar": 0.85,
        "pitch_amp_deg": 45.0,
        "reynolds": 42.5537291206389,
    }
    assert fields["grid"] == "256 128 256"
    assert fields["fixed_dt"] == 0.0005
    assert fields["max_step"] == 4706


def test_parse_deck_skips_lines_with_no_key(tmp_path):
    deck = tmp_path / "inputs.3d.test"
    deck.write_text("= no_key_here\namr.n_cell = 64 32 64\n", encoding="utf-8")
    assert mc.parse_deck(deck) == {"amr.n_cell": "64 32 64"}


def test_source_config_fields_raises_clear_error_on_missing_deck_key(tmp_path):
    deck = tmp_path / "inputs.3d.test"
    deck.write_text("amr.n_cell = 64 32 64\n", encoding="utf-8")  # no ns.fixed_dt
    with pytest.raises(KeyError, match="ns.fixed_dt"):
        mc.source_config_fields(
            manifest_path=_MANIFEST, deck_path=deck, config_name="s35_f085_p45"
        )


def test_source_config_fields_raises_clear_error_on_missing_manifest_field(tmp_path):
    manifest = tmp_path / "sweep_manifest.json"
    manifest.write_text(
        json.dumps({"configs": [{"name": "s35_f085_p45", "max_step": 4706}]}),
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="stroke_amp_deg"):
        mc.source_config_fields(
            manifest_path=manifest, deck_path=_DECK, config_name="s35_f085_p45"
        )


def test_manifest_lookup_raises_on_missing_config():
    with pytest.raises(KeyError, match="not_a_real_config"):
        mc.source_config_fields(
            manifest_path=_MANIFEST, deck_path=_DECK, config_name="not_a_real_config"
        )


def test_manifest_lookup_raises_on_malformed_manifest_json(tmp_path):
    bad = tmp_path / "sweep_manifest.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        mc.source_config_fields(
            manifest_path=bad, deck_path=_DECK, config_name="s35_f085_p45"
        )


# ---------------------------------------------------------------------------
# 5. Docker-digest and git-commit passthrough validation
# ---------------------------------------------------------------------------


def test_docker_digest_field_is_single_named_and_validated():
    pod_metadata = _load_json(_POD_METADATA)
    digest = mc.extract_docker_image(pod_metadata)
    assert digest == pod_metadata["docker_image"]
    assert digest.startswith("sha256:")


def test_malformed_digest_is_rejected():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["docker_image"] = "ghcr.io/talmolab/mosquito-cfd:fp64"
    with pytest.raises(ValueError, match="digest"):
        mc.extract_docker_image(pod_metadata)


def test_git_commit_must_be_full_sha():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"]["commit"] = "634c561"
    with pytest.raises(ValueError, match="40-character"):
        mc.extract_git_info(pod_metadata)


_MISSING_GIT_BLOCK = {"error": "git not available or not a repository"}


def test_extract_git_info_rejects_missing_commit_key():
    """The real #66 failure shape: a pod-side .git-less image's git block has no `commit` key at
    all (not just a truncated one)."""
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"] = dict(_MISSING_GIT_BLOCK)
    with pytest.raises(ValueError, match="40-character"):
        mc.extract_git_info(pod_metadata)


def test_resolve_git_info_falls_through_to_extract_git_info_when_no_override():
    pod_metadata = _load_json(_POD_METADATA)
    assert mc.resolve_git_info(
        pod_metadata, git_commit_override=None
    ) == mc.extract_git_info(pod_metadata)


def test_resolve_git_info_raises_when_no_override_and_pod_commit_missing():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"] = dict(_MISSING_GIT_BLOCK)
    with pytest.raises(ValueError, match="40-character"):
        mc.resolve_git_info(pod_metadata, git_commit_override=None)


def test_resolve_git_info_raises_when_no_override_and_pod_commit_truncated():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"]["commit"] = "634c561"
    with pytest.raises(ValueError, match="40-character"):
        mc.resolve_git_info(pod_metadata, git_commit_override=None)


def test_resolve_git_info_override_bypasses_pod_value():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"] = dict(_MISSING_GIT_BLOCK)
    result = mc.resolve_git_info(pod_metadata, git_commit_override="a" * 40)
    assert result == {"commit": "a" * 40, "source": "cli-override"}


def test_resolve_git_info_override_wins_over_valid_differing_pod_commit():
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"]["commit"] = "b" * 40
    result = mc.resolve_git_info(pod_metadata, git_commit_override="c" * 40)
    assert result == {"commit": "c" * 40, "source": "cli-override"}


def test_resolve_git_info_rejects_malformed_override():
    pod_metadata = _load_json(_POD_METADATA)
    with pytest.raises(ValueError, match="40-character"):
        mc.resolve_git_info(pod_metadata, git_commit_override="634c561")


def test_resolve_git_info_rejects_uppercase_hex_override():
    pod_metadata = _load_json(_POD_METADATA)
    with pytest.raises(ValueError, match="40-character"):
        mc.resolve_git_info(pod_metadata, git_commit_override="A" * 40)


def test_pod_run_metadata_raises_on_missing_file(tmp_path):
    missing = tmp_path / "run_metadata.json"
    with pytest.raises(FileNotFoundError, match="run_metadata.json"):
        mc.load_pod_run_metadata(missing)


def test_pod_run_metadata_raises_on_malformed_json(tmp_path):
    bad = tmp_path / "run_metadata.json"
    bad.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ValueError, match="not valid JSON"):
        mc.load_pod_run_metadata(bad)


# ---------------------------------------------------------------------------
# 6. Argo workflow-status query wrapper
# ---------------------------------------------------------------------------


def test_wall_time_from_argo_status_timestamps():
    status = _load_json(_ARGO_SIMPLE)
    assert mc.compute_wall_time_s(status) == pytest.approx(9448.466969)


def test_wall_time_reflects_only_final_successful_attempt():
    status = _load_json(_ARGO_RETRY)
    # Only the successful retry's span (11:09:12 -> 13:57:28.466969), not the full
    # 09:00:00 -> 13:57:28.466969 window that includes the failed first attempt.
    assert mc.compute_wall_time_s(status) == pytest.approx(10096.466969)


def test_wall_time_selects_matching_pod_node_in_multi_config_status():
    status = _load_json(_ARGO_MULTI)
    middle_node = status["status"]["nodes"][_MULTI_POD_MIDDLE]
    expected_duration_s = (
        mc._parse_argo_timestamp(middle_node["finishedAt"])
        - mc._parse_argo_timestamp(middle_node["startedAt"])
    ).total_seconds()
    # The middle pod's own window is 01:00:00 -> 02:00:00 = 3600s -- neither the
    # shortest (earliest pod, 1800s) nor the longest/latest-finishing (latest pod, 9200s).
    # Under the old unfiltered global-max behavior this would wrongly return 9200s.
    assert expected_duration_s == pytest.approx(3600.0)
    assert mc.compute_wall_time_s(status, pod_name=_MULTI_POD_MIDDLE) == pytest.approx(
        expected_duration_s
    )


def test_wall_time_pod_name_none_preserves_global_max_behavior_on_multi_config_status():
    status = _load_json(_ARGO_MULTI)
    # Latest pod's own window is 03:00:00 -> 05:33:20 = 9200s, which is also the
    # globally-latest-finishing node across the whole multi-config workflow -- the
    # unfiltered fallback (pod_name=None) and an explicit lookup of that same pod agree.
    assert mc.compute_wall_time_s(status, pod_name=None) == pytest.approx(9200.0)
    assert mc.compute_wall_time_s(status) == pytest.approx(9200.0)
    assert mc.compute_wall_time_s(status, pod_name=_MULTI_POD_LATEST) == pytest.approx(
        9200.0
    )


def test_wall_time_raises_on_unmatched_pod_name():
    status = _load_json(_ARGO_MULTI)
    with pytest.raises(ValueError, match=_MULTI_POD_UNMATCHED) as exc_info:
        mc.compute_wall_time_s(status, pod_name=_MULTI_POD_UNMATCHED)
    assert _MULTI_POD_EARLIEST in str(exc_info.value)


def test_wall_time_unmatched_pod_error_excludes_non_candidate_keys():
    status = _load_json(_ARGO_MULTI)
    status["status"]["nodes"]["retry-wrapper"] = {
        "displayName": "run-config",
        "type": "Retry",
        "phase": "Succeeded",
        "startedAt": "2026-08-04T06:00:00Z",
        "finishedAt": "2026-08-04T06:10:00Z",
    }
    status["status"]["nodes"]["failed-pod"] = {
        "displayName": "run-config",
        "type": "Pod",
        "phase": "Failed",
        "startedAt": "2026-08-04T06:20:00Z",
        "finishedAt": "2026-08-04T06:30:00Z",
    }
    with pytest.raises(ValueError, match=_MULTI_POD_UNMATCHED) as exc_info:
        mc.compute_wall_time_s(status, pod_name=_MULTI_POD_UNMATCHED)
    message = str(exc_info.value)
    assert _MULTI_POD_EARLIEST in message
    assert "retry-wrapper" not in message
    assert "failed-pod" not in message


def test_wall_time_empty_string_pod_name_is_treated_as_a_literal_unmatched_name():
    status = _load_json(_ARGO_MULTI)
    with pytest.raises(ValueError, match="''") as exc_info:
        mc.compute_wall_time_s(status, pod_name="")
    assert _MULTI_POD_EARLIEST in str(exc_info.value)


def test_wall_time_raises_clear_error_on_unmatched_pod_name_against_empty_status():
    with pytest.raises(ValueError, match="my-pod"):
        mc.compute_wall_time_s({}, pod_name="my-pod")


def test_wall_time_pod_scoped_lookup_in_multi_config_fan_out_with_retry():
    """The real 27-config resubmission will combine BOTH multi-config fan-out and
    per-config retries (that's the entire reason PR #82/#83 fixed retryStrategy.backoff
    at all). Pins two things against that combined shape: (1) direct pod-name lookup for
    the retried config's own succeeded attempt returns that attempt's own span (900s),
    not the wrapper's inflated 1200s span or any of the other three disjoint configs'
    durations (1800s/3600s/9200s) -- the dict-key convention alone keeps these apart, with
    no filtering logic involved; (2) supplying the Retry wrapper's own key is correctly
    REJECTED (this is the actual exclusion check, exercised via the matched-node validation
    path, not the direct-lookup path above)."""
    status = _load_json(_ARGO_MULTI)
    retried_wrapper_key = "force-surrogate-sweep-vb8t5-run-config-4000000000"
    retried_failed_key = "force-surrogate-sweep-vb8t5-run-config-4111111111"
    retried_succeeded_key = "force-surrogate-sweep-vb8t5-run-config-4222222222"
    status["status"]["nodes"][retried_wrapper_key] = {
        "displayName": "run-config",
        "type": "Retry",
        "phase": "Succeeded",
        "startedAt": "2026-08-04T09:00:00Z",
        "finishedAt": "2026-08-04T09:20:00Z",
    }
    status["status"]["nodes"][retried_failed_key] = {
        "displayName": "run-config(0)",
        "type": "Pod",
        "phase": "Failed",
        "startedAt": "2026-08-04T09:00:00Z",
        "finishedAt": "2026-08-04T09:05:00Z",
    }
    status["status"]["nodes"][retried_succeeded_key] = {
        "displayName": "run-config(1)",
        "type": "Pod",
        "phase": "Succeeded",
        "startedAt": "2026-08-04T09:05:00Z",
        "finishedAt": "2026-08-04T09:20:00Z",
    }
    assert mc.compute_wall_time_s(
        status, pod_name=retried_succeeded_key
    ) == pytest.approx(900.0)
    with pytest.raises(ValueError, match="Retry"):
        mc.compute_wall_time_s(status, pod_name=retried_wrapper_key)


def test_wall_time_raises_when_matched_pod_node_has_wrong_phase():
    status = _load_json(_ARGO_MULTI)
    status["status"]["nodes"]["bad-pod"] = {
        "displayName": "run-config",
        "type": "Pod",
        "phase": "Failed",
        "startedAt": "2026-08-04T06:00:00Z",
        "finishedAt": "2026-08-04T06:10:00Z",
    }
    with pytest.raises(ValueError, match="bad-pod") as exc_info:
        mc.compute_wall_time_s(status, pod_name="bad-pod")
    assert "phase is 'Failed'" in str(exc_info.value)


def test_wall_time_raises_when_matched_pod_node_is_retry_type():
    status = _load_json(_ARGO_MULTI)
    status["status"]["nodes"]["bad-pod"] = {
        "displayName": "run-config",
        "type": "Retry",
        "phase": "Succeeded",
        "startedAt": "2026-08-04T06:00:00Z",
        "finishedAt": "2026-08-04T06:10:00Z",
    }
    with pytest.raises(ValueError, match="bad-pod") as exc_info:
        mc.compute_wall_time_s(status, pod_name="bad-pod")
    assert "'Retry' wrapper" in str(exc_info.value)


def test_wall_time_raises_when_matched_pod_node_missing_timestamps():
    status = _load_json(_ARGO_MULTI)
    status["status"]["nodes"]["bad-pod"] = {
        "displayName": "run-config",
        "type": "Pod",
        "phase": "Succeeded",
        "startedAt": "2026-08-04T06:00:00Z",
    }
    with pytest.raises(ValueError, match="bad-pod") as exc_info:
        mc.compute_wall_time_s(status, pod_name="bad-pod")
    assert "missing startedAt" in str(exc_info.value)


def test_argo_status_missing_timestamps_raises_clear_error():
    status = {
        "status": {
            "nodes": {
                "n1": {"displayName": "run-config", "phase": "Succeeded"},
            }
        }
    }
    with pytest.raises(ValueError, match="Succeeded"):
        mc.compute_wall_time_s(status)


def test_argo_status_query_failure_produces_clear_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("argo")

    monkeypatch.setattr(mc.subprocess, "run", _raise)
    with pytest.raises(RuntimeError, match="argo"):
        mc.query_argo_workflow_status("some-workflow")


def test_argo_status_query_timeout_produces_clear_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise mc.subprocess.TimeoutExpired(
            cmd=["argo"], timeout=mc._ARGO_QUERY_TIMEOUT_S
        )

    monkeypatch.setattr(mc.subprocess, "run", _raise)
    with pytest.raises(RuntimeError, match="did not return within"):
        mc.query_argo_workflow_status("some-workflow")


def test_argo_status_query_nonzero_exit_produces_clear_error(monkeypatch):
    class _FakeCompleted:
        returncode = 1
        stdout = ""
        stderr = 'workflows.argoproj.io "some-workflow" not found'

    monkeypatch.setattr(mc.subprocess, "run", lambda *a, **k: _FakeCompleted())
    with pytest.raises(RuntimeError, match="not found"):
        mc.query_argo_workflow_status("some-workflow")


def test_argo_status_query_invalid_json_produces_clear_error(monkeypatch):
    class _FakeCompleted:
        returncode = 0
        stdout = "not json"
        stderr = ""

    monkeypatch.setattr(mc.subprocess, "run", lambda *a, **k: _FakeCompleted())
    with pytest.raises(RuntimeError, match="valid JSON"):
        mc.query_argo_workflow_status("some-workflow")


def test_resolve_wall_time_s_calls_argo_status_query_when_no_override():
    status = _load_json(_ARGO_SIMPLE)
    calls = []

    def _fake_query(workflow_name):
        calls.append(workflow_name)
        return status

    result = mc.resolve_wall_time_s(
        workflow_name="force-surrogate-smoke-xwm4b",
        wall_time_s_override=None,
        argo_status_query=_fake_query,
    )
    assert result == pytest.approx(9448.466969)
    assert calls == ["force-surrogate-smoke-xwm4b"]


def test_wall_time_s_override_bypasses_argo_query():
    calls = []

    def _spy_query(workflow_name):
        calls.append(workflow_name)
        raise AssertionError("should never be called when an override is supplied")

    result = mc.resolve_wall_time_s(
        workflow_name="some-workflow",
        wall_time_s_override=7032.46,
        argo_status_query=_spy_query,
    )
    assert result == 7032.46
    assert calls == []


def test_resolve_wall_time_s_passes_pod_name_through_to_argo_query_path():
    status = _load_json(_ARGO_MULTI)

    def _fake_query(workflow_name):
        return status

    result = mc.resolve_wall_time_s(
        workflow_name="force-surrogate-sweep-vb8t5",
        wall_time_s_override=None,
        pod_name=_MULTI_POD_MIDDLE,
        argo_status_query=_fake_query,
    )
    assert result == pytest.approx(3600.0)


def test_resolve_wall_time_s_override_ignores_pod_name():
    calls = []

    def _spy_query(workflow_name):
        calls.append(workflow_name)
        raise AssertionError("should never be called when an override is supplied")

    result = mc.resolve_wall_time_s(
        workflow_name="some-workflow",
        wall_time_s_override=7032.46,
        pod_name="anything",
        argo_status_query=_spy_query,
    )
    assert result == 7032.46
    assert calls == []


# ---------------------------------------------------------------------------
# 7. Schema assembler
# ---------------------------------------------------------------------------


def _assemble(**overrides):
    kwargs = dict(
        pod_metadata_path=_POD_METADATA,
        csv_path=_CSV,
        run_log_path=_RUN_LOG,
        manifest_path=_MANIFEST,
        deck_path=_DECK,
        config_name="s35_f085_p45",
        tier="fine-grid-pilot",
        wall_time_s=9448.466969,
    )
    kwargs.update(overrides)
    return mc.assemble_run_metadata(**kwargs)


def test_assemble_metadata_produces_normalized_schema():
    result = _assemble()
    assert result["docker_image"].startswith("sha256:")
    assert "image_digest" not in result
    assert (
        result["deck_sha256"]
        == "92d5ab87b8556b711329f23f197aaefca8954db93df91a409bef396a66a7674d"
    )
    assert result["stability"] == "stable_at_5e-4"
    assert result["arena_max_mib"] == 7998
    assert result["node"] == "gpu-node14"
    assert result["gpu_model"] == "NVIDIA A40"
    assert result["kinematics"]["stroke_amp_deg"] == 35.0
    assert result["grid"] == "256 128 256"
    assert result["fixed_dt"] == 0.0005
    assert result["max_step"] == 4706
    assert result["timing"] == {
        "final_time": 2.3525,
        "timesteps": 4706,
        "wall_time_s": 9448.466969,
    }
    assert (
        result["orchestration"]["workflow_uid"]
        == "4378eb61-6e31-4a5b-8374-f61c89be1a1e"
    )
    assert (
        result["orchestration"]["pod"]
        == "force-surrogate-smoke-xwm4b-run-config-3125566197"
    )
    assert result["orchestration"]["retry"] == "0"
    assert "run_platform" not in result


def test_assemble_run_metadata_accepts_git_commit_override(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"] = dict(_MISSING_GIT_BLOCK)
    no_git = tmp_path / "run_metadata.json"
    no_git.write_text(json.dumps(pod_metadata), encoding="utf-8")

    result = _assemble(pod_metadata_path=no_git, git_commit="b" * 40)
    assert result["git"]["commit"] == "b" * 40
    assert result["git"]["source"] == "cli-override"


def test_assemble_run_metadata_git_commit_override_wins_over_valid_pod_value(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["git"]["commit"] = "b" * 40
    valid_pod_git = tmp_path / "run_metadata.json"
    valid_pod_git.write_text(json.dumps(pod_metadata), encoding="utf-8")

    result = _assemble(pod_metadata_path=valid_pod_git, git_commit="c" * 40)
    assert result["git"]["commit"] == "c" * 40
    assert result["git"]["source"] == "cli-override"


def test_assemble_metadata_includes_workflow_name_in_orchestration_when_supplied():
    result = _assemble(workflow_name="force-surrogate-smoke-xwm4b")
    assert result["orchestration"]["workflow_name"] == "force-surrogate-smoke-xwm4b"


def test_assemble_metadata_wall_time_selects_matching_pod_in_multi_config_workflow(
    tmp_path,
):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["orchestration"]["pod"] = _MULTI_POD_MIDDLE
    pod_metadata_path = tmp_path / "run_metadata.json"
    pod_metadata_path.write_text(json.dumps(pod_metadata), encoding="utf-8")

    multi_status = _load_json(_ARGO_MULTI)

    def _fake_query(workflow_name):
        return multi_status

    result = _assemble(
        pod_metadata_path=pod_metadata_path,
        workflow_name="force-surrogate-sweep-vb8t5",
        wall_time_s=None,
        argo_status_query=_fake_query,
    )
    assert result["timing"]["wall_time_s"] == pytest.approx(3600.0)


def test_assemble_metadata_wall_time_falls_back_when_orchestration_pod_missing(
    tmp_path,
):
    pod_metadata = _load_json(_POD_METADATA)
    del pod_metadata["orchestration"]["pod"]
    pod_metadata_path = tmp_path / "run_metadata.json"
    pod_metadata_path.write_text(json.dumps(pod_metadata), encoding="utf-8")

    simple_status = _load_json(_ARGO_SIMPLE)

    def _fake_query(workflow_name):
        return simple_status

    result = _assemble(
        pod_metadata_path=pod_metadata_path,
        workflow_name="force-surrogate-smoke-xwm4b",
        wall_time_s=None,
        argo_status_query=_fake_query,
    )
    assert result["timing"]["wall_time_s"] == pytest.approx(9448.466969)


def test_assemble_metadata_wall_time_falls_back_when_orchestration_pod_is_explicit_null(
    tmp_path,
):
    # dict.get("pod") returns None whether "pod" is entirely absent (tested above) or present
    # with an explicit JSON null -- confirms assemble_run_metadata treats both identically.
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["orchestration"]["pod"] = None
    pod_metadata_path = tmp_path / "run_metadata.json"
    pod_metadata_path.write_text(json.dumps(pod_metadata), encoding="utf-8")

    simple_status = _load_json(_ARGO_SIMPLE)

    def _fake_query(workflow_name):
        return simple_status

    result = _assemble(
        pod_metadata_path=pod_metadata_path,
        workflow_name="force-surrogate-smoke-xwm4b",
        wall_time_s=None,
        argo_status_query=_fake_query,
    )
    assert result["timing"]["wall_time_s"] == pytest.approx(9448.466969)


def test_assemble_metadata_raises_when_orchestration_pod_unmatched(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["orchestration"]["pod"] = _MULTI_POD_UNMATCHED
    pod_metadata_path = tmp_path / "run_metadata.json"
    pod_metadata_path.write_text(json.dumps(pod_metadata), encoding="utf-8")

    multi_status = _load_json(_ARGO_MULTI)

    def _fake_query(workflow_name):
        return multi_status

    with pytest.raises(ValueError, match=_MULTI_POD_UNMATCHED):
        _assemble(
            pod_metadata_path=pod_metadata_path,
            workflow_name="force-surrogate-sweep-vb8t5",
            wall_time_s=None,
            argo_status_query=_fake_query,
        )


def test_assemble_metadata_notes_field_optional():
    without_notes = _assemble()
    assert "notes" not in without_notes

    with_notes = _assemble(notes="benign truncated final step, see run.log")
    assert with_notes["notes"] == "benign truncated final step, see run.log"


def test_assemble_metadata_raises_on_row_count_mismatch_between_pod_and_csv(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["rows"] = 4700  # CSV actually has 4706 rows
    mismatched = tmp_path / "run_metadata.json"
    mismatched.write_text(json.dumps(pod_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="4700"):
        _assemble(pod_metadata_path=mismatched)


def test_assemble_metadata_raises_on_missing_rows_field(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    del pod_metadata["rows"]
    missing_rows = tmp_path / "run_metadata.json"
    missing_rows.write_text(json.dumps(pod_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="rows"):
        _assemble(pod_metadata_path=missing_rows)


def test_assemble_metadata_raises_on_non_completed_status(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["status"] = "failed"
    failed = tmp_path / "run_metadata.json"
    failed.write_text(json.dumps(pod_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="failed"):
        _assemble(pod_metadata_path=failed)


def test_assemble_metadata_raises_on_deck_hash_mismatch(tmp_path):
    wrong_deck = tmp_path / "inputs.3d.wrong"
    wrong_deck.write_text(
        "amr.n_cell = 1 1 1\nns.fixed_dt = 0.0005\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="deck_sha256"):
        _assemble(deck_path=wrong_deck)


def test_assemble_metadata_raises_on_missing_deck_sha256(tmp_path):
    pod_metadata = _load_json(_POD_METADATA)
    del pod_metadata["deck_sha256"]
    no_hash = tmp_path / "run_metadata.json"
    no_hash.write_text(json.dumps(pod_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="deck_sha256"):
        _assemble(pod_metadata_path=no_hash)


def test_assemble_metadata_raises_on_empty_string_deck_sha256(tmp_path):
    """An empty string is falsy but not None -- must be treated the same as a missing key,
    not fall through to a confusing hash-mismatch message."""
    pod_metadata = _load_json(_POD_METADATA)
    pod_metadata["deck_sha256"] = ""
    empty_hash = tmp_path / "run_metadata.json"
    empty_hash.write_text(json.dumps(pod_metadata), encoding="utf-8")

    with pytest.raises(ValueError, match="has no deck_sha256"):
        _assemble(pod_metadata_path=empty_hash)


@pytest.mark.skipif(
    not _REAL_COMMITTED_METADATA.exists(),
    reason="real committed pilot run_metadata not present",
)
def test_assemble_metadata_matches_known_correct_pilot_config():
    """Fixture-driven end-to-end reproduction (design.md D4): read-only ground truth.

    Does NOT write to or modify the real committed file.
    """
    real = _load_json(_REAL_COMMITTED_METADATA)
    result = _assemble()

    assert result["timing"]["final_time"] == real["timing"]["final_time"]
    assert result["git"]["commit"] == real["git"]["commit"]
    assert result["kinematics"] == real["kinematics"]
