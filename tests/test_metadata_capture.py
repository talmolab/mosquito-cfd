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

_REAL_COMMITTED_METADATA = Path(
    "examples/prelim_sweep_fine_pilot/run_metadata_s35_f085_p45.json"
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


def test_assemble_metadata_includes_workflow_name_in_orchestration_when_supplied():
    result = _assemble(workflow_name="force-surrogate-smoke-xwm4b")
    assert result["orchestration"]["workflow_name"] == "force-surrogate-smoke-xwm4b"


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
