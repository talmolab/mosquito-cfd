"""Tests for scripts/generate_run_metadata.py (TDD, automate-run-metadata-capture).

Loaded via ``importlib.util.spec_from_file_location`` (the `scripts/` bare-script convention,
mirroring ``tests/test_force_surrogate_run_sweep_driver.py``) so no `scripts/__init__.py` is
needed. All logic lives in :mod:`mosquito_cfd.force_surrogate.metadata_capture`; this file only
tests the thin argparse wrapper. Cluster-free: nothing here touches the 3 committed pilot
`run_metadata_*.json` files (design.md D4).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).parent.parent / "scripts" / "generate_run_metadata.py"
_FIXTURES = Path(__file__).parent / "fixtures" / "run_metadata"


def _load_script():
    spec = importlib.util.spec_from_file_location("generate_run_metadata", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _base_args(output_path: Path) -> list[str]:
    return [
        "--pod-metadata",
        str(_FIXTURES / "pod_run_metadata.json"),
        "--csv",
        str(_FIXTURES / "forces_s35_f085_p45.csv"),
        "--run-log",
        str(_FIXTURES / "run.log"),
        "--manifest",
        str(_FIXTURES / "sweep_manifest.json"),
        "--deck",
        str(_FIXTURES / "inputs.3d.s35_f085_p45"),
        "--config-name",
        "s35_f085_p45",
        "--tier",
        "fine-grid-pilot",
        "--wall-time-s",
        "9448.466969",
        "--output",
        str(output_path),
    ]


def test_cli_writes_output_file(tmp_path):
    module = _load_script()
    output = tmp_path / "run_metadata_s35_f085_p45.json"

    rc = module.main(_base_args(output))

    assert rc == 0
    assert output.exists()
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["config"] == "s35_f085_p45"
    assert written["timing"]["final_time"] == 2.3525
    assert written["timing"]["wall_time_s"] == 9448.466969


def test_cli_rejects_missing_required_args(tmp_path):
    module = _load_script()
    output = tmp_path / "run_metadata.json"
    args = _base_args(output)
    # Drop --tier and its value.
    idx = args.index("--tier")
    del args[idx : idx + 2]

    with pytest.raises(SystemExit):
        module.main(args)
    assert not output.exists()


def test_cli_missing_workflow_name_and_wall_time_s_raises_clear_error(tmp_path):
    """`--workflow-name` is optional at the argparse level (the `--wall-time-s` override design
    means it isn't unconditionally required), but omitting BOTH it and `--wall-time-s` must still
    fail with a clear, specific error — not a downstream KeyError."""
    module = _load_script()
    output = tmp_path / "run_metadata.json"
    args = _base_args(output)
    idx = args.index("--wall-time-s")
    del args[
        idx : idx + 2
    ]  # neither --workflow-name (never added) nor --wall-time-s present

    with pytest.raises(ValueError, match="workflow_name"):
        module.main(args)
    assert not output.exists()


def test_cli_git_commit_flag_overrides_pod_value(tmp_path):
    module = _load_script()
    output = tmp_path / "run_metadata.json"

    pod_metadata = json.loads(
        (_FIXTURES / "pod_run_metadata.json").read_text(encoding="utf-8")
    )
    pod_metadata["git"] = {"error": "git not available or not a repository"}
    no_git_pod_metadata = tmp_path / "pod_run_metadata.json"
    with open(no_git_pod_metadata, "w", encoding="utf-8") as handle:
        json.dump(pod_metadata, handle)

    args = _base_args(output)
    idx = args.index("--pod-metadata")
    args[idx + 1] = str(no_git_pod_metadata)
    args += ["--git-commit", "b" * 40]

    rc = module.main(args)

    assert rc == 0
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["git"]["commit"] == "b" * 40
    assert written["git"]["source"] == "cli-override"


def test_cli_git_commit_flag_rejects_malformed_override(tmp_path):
    """Format validation must be enforced end-to-end through the CLI, not just at the
    `resolve_git_info` unit level the wrapper delegates to."""
    module = _load_script()
    output = tmp_path / "run_metadata.json"
    args = _base_args(output) + ["--git-commit", "not-a-real-sha"]

    with pytest.raises(ValueError, match="40-character"):
        module.main(args)

    assert not output.exists()


def test_cli_wall_time_s_flag_skips_argo_query(tmp_path, monkeypatch):
    module = _load_script()
    output = tmp_path / "run_metadata.json"

    def _fail_if_called(workflow_name):
        raise AssertionError("argo query should not run when --wall-time-s is supplied")

    monkeypatch.setattr(
        module.metadata_capture, "query_argo_workflow_status", _fail_if_called
    )

    rc = module.main(_base_args(output))

    assert rc == 0
    assert (
        json.loads(output.read_text(encoding="utf-8"))["timing"]["wall_time_s"]
        == 9448.466969
    )
