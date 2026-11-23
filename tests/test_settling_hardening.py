"""Regression tests for the PR-review findings on the settling check (add-settled-beat-corpus).

Each test reproduces a defect the review team found at ``3febaf7``: NaN passing a control,
control records miscounted by the precedence check, short runs passing, provenance asserted by
the operator instead of derived from git, records the report never validated, and so on.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from test_settling_report import (  # shared synthetic tree (a git repo)
    COMMIT,
    DT,
    _cf_frame,
    _git,
    _provenance,
    _record,
    _tree,
    _write_csv,
    _write_record,
)

from mosquito_cfd.force_surrogate import settling
from mosquito_cfd.force_surrogate.settling import (
    GATED_FILES,
    RunVerdict,
    build_settling_report,
    check_precedence,
    compare_force_csv,
    decide_beat_count,
    git_provenance,
    print_unit,
    spec_constants,
    validate_run_record,
)

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- NaN in controls


def _ref(n: int) -> pd.DataFrame:
    steps = np.arange(n)
    return pd.DataFrame(
        {"time": steps * DT, **{c: 100.0 + steps for c in settling.FORCE_COLUMNS}}
    )


def _csv(path: Path, n: int, edit=None) -> None:
    cols = ["iStep", "time", *settling.FORCE_COLUMNS]
    rows = [[str(s), f"{s * DT:g}", *[f"{100.0 + s:g}"] * 6] for s in range(n)]
    if edit:
        edit(rows)
    path.write_text("\n".join([",".join(cols), *[",".join(r) for r in rows]]) + "\n")


def _compare(csv: Path, ref: pd.DataFrame):
    return compare_force_csv(
        csv,
        ref,
        config_name="c",
        dt=DT,
        run_stop_time=10.0,
        reference_stop_time=10.0,
        declared_steps=400,
    )


@pytest.mark.parametrize("token", ["nan", "-nan", "inf"])
def test_non_finite_run_value_fails_the_comparison(tmp_path, token):
    csv = tmp_path / "IB_Particle_1.csv"

    def poison(rows):
        rows[100][4] = token  # Fz at step 100

    _csv(csv, 400, poison)
    result = _compare(csv, _ref(400))
    assert not result.passed
    assert "Fz" in result.failures[0]


def test_non_finite_reference_fails_instead_of_crashing(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _csv(csv, 400)
    ref = _ref(400)
    ref.loc[50, "My"] = np.nan
    result = _compare(csv, ref)
    assert not result.passed and "My" in result.failures[0]


def test_missing_force_column_fails_instead_of_crashing(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _csv(csv, 400)
    text = csv.read_text().splitlines()
    csv.write_text(
        "\n".join(",".join(r.split(",")[:-1]) for r in text) + "\n"
    )  # drop Mz
    result = _compare(csv, _ref(400))
    assert not result.passed and "Mz" in result.failures[0]


def test_print_unit_is_vectorised_and_zero_safe():
    values = np.array([7191.76, 0.0, -0.5, 5.39406e-13])
    assert np.allclose(print_unit(values), [0.01, 0.0, 1e-6, 1e-18], rtol=1e-12, atol=0)
    assert print_unit(0.0) == 0.0


# --------------------------------------------------------------------------- precedence counting


def _precedence_tree(tmp_path: Path, names: list[str]) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    sd = root / "examples" / "settling_check"
    sd.mkdir(parents=True)
    for rel in GATED_FILES:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(rel, encoding="utf-8")
    manifest = {
        "runs": [{"name": n} for n in names if "_c1_" not in n],
        "controls": [{"name": n} for n in names if "_c1_" in n],
    }
    (sd / "settling_manifest.json").write_text(json.dumps(manifest))
    (sd / "records").mkdir()
    (sd / "DECISION.md").write_text("x")
    return root, sd


def _precedence_record(root: Path, sd: Path, name: str) -> None:
    hashes = {
        rel: hashlib.sha256((root / rel).read_bytes()).hexdigest()
        for rel in GATED_FILES
    }
    (sd / "records" / f"{name}.json").write_text(
        json.dumps({"run": name, "file_sha256": hashes})
    )


NAMES = ["fine_a", "fine_b", "coarse_a", "fine_c1_a", "coarse_c1_a"]


def test_precedence_counts_control_records_on_the_real_manifest_shape(tmp_path):
    root, sd = _precedence_tree(tmp_path, NAMES)
    for name in NAMES:
        _precedence_record(root, sd, name)
    assert check_precedence(sd, repo_root=root) == []


def test_precedence_names_a_missing_and_a_stray_record(tmp_path):
    root, sd = _precedence_tree(tmp_path, NAMES)
    for name in [*NAMES[:-1], "stray"]:
        _precedence_record(root, sd, name)
    failures = check_precedence(sd, repo_root=root)
    assert any("coarse_c1_a" in f for f in failures)
    assert any("stray" in f for f in failures)


def test_real_committed_manifest_declares_runs_and_controls():
    manifest = json.loads(
        (REPO / "examples/settling_check/settling_manifest.json").read_text()
    )
    names = {e["name"] for e in [*manifest["runs"], *manifest["controls"]]}
    assert len(names) == 8


@pytest.mark.parametrize("payload", ["not json", "[1, 2]", '{"a": 1}'])
def test_malformed_deviations_fail_with_a_named_message(tmp_path, payload):
    root, sd = _precedence_tree(tmp_path, ["fine_a"])
    _precedence_record(root, sd, "fine_a")
    (root / GATED_FILES[0]).write_text("edited", encoding="utf-8")
    (sd / "deviations.json").write_text(payload)
    failures = check_precedence(sd, repo_root=root)
    assert failures
    assert any("deviations.json" in f or GATED_FILES[0] in f for f in failures)


def test_malformed_record_fails_with_its_name(tmp_path):
    root, sd = _precedence_tree(tmp_path, ["fine_a"])
    (sd / "records" / "fine_a.json").write_text("{not json")
    failures = check_precedence(sd, repo_root=root)
    assert failures and any("fine_a.json" in f for f in failures)


# --------------------------------------------------------------------------- short runs


def test_long_run_that_stopped_early_fails_its_record(tmp_path):
    t = _tree(tmp_path)
    _write_csv(t["long"] / "IB_Particle_1.csv", 10000)  # 5 of the declared 8 beats
    record = _record(t, "fine_cfg", t["long"])
    problems = validate_run_record(record, t["manifest"]["runs"][0])
    assert any("steps" in p and "16000" in p for p in problems)


def test_c1_that_ran_the_long_deck_fails(tmp_path):
    t = _tree(tmp_path)
    _write_csv(t["c1"] / "IB_Particle_1.csv", 3478)
    record = _record(t, "fine_c1_cfg", t["c1"])
    problems = validate_run_record(record, t["manifest"]["controls"][0])
    assert any("steps" in p for p in problems)


def test_report_marks_a_short_dataset_run_data_incomplete(tmp_path):
    t = _tree(tmp_path)
    _cf_frame("cfg", 6, 0.2).to_parquet(t["settling_dir"] / "fine" / "dataset.parquet")
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] != "complete"
    assert any("fine_cfg" in m and "8" in m for m in report["data_missing"])


# --------------------------------------------------------------------------- provenance


def test_provenance_is_derived_from_git(tmp_path):
    t = _tree(tmp_path)
    prov = _provenance(t)
    assert prov["start_commit"] == t["commit"] == prov["head_commit"]
    assert prov["ancestor_of_upstream"] is True
    assert prov["dirty_at_launch"] is False and prov["dirty_at_record"] is False
    for rel in (*GATED_FILES, settling.SETTLING_PY):
        expected = hashlib.sha256((t["repo"] / rel).read_bytes()).hexdigest()
        assert prov["file_sha256"][rel] == expected
    assert prov["working_tree_matches_commit"] is True
    assert settling.provenance_problems(prov) == []


def test_records_directory_does_not_make_the_checkout_dirty(tmp_path):
    t = _tree(tmp_path)
    records = t["settling_dir"] / "records"
    records.mkdir()
    (records / "fine_c1_cfg.json").write_text("{}")
    assert _provenance(t)["dirty_at_record"] is False


def test_edited_gated_file_and_dirty_tree_are_detected(tmp_path):
    t = _tree(tmp_path)
    (t["repo"] / GATED_FILES[0]).write_text("edited after the run started\n")
    prov = _provenance(t)
    assert prov["working_tree_matches_commit"] is False
    assert prov["dirty_at_record"] is True


def test_dirty_launch_and_non_ancestor_commit_are_detected(tmp_path):
    t = _tree(tmp_path)
    (t["repo"] / "extra.txt").write_text("x")
    _git(t["repo"], "add", "extra.txt")
    _git(t["repo"], "-c", "commit.gpgsign=false", "commit", "-q", "-m", "local only")
    head = _git(t["repo"], "rev-parse", "HEAD")
    prov = _provenance(t, start_commit=head, launch_status=" M x")
    assert prov["ancestor_of_upstream"] is False and prov["dirty_at_launch"] is True
    problems = settling.provenance_problems(prov)
    assert any("ancestor" in p for p in problems) and any(
        "launch" in p for p in problems
    )


def test_head_moved_since_launch_is_detected(tmp_path):
    t = _tree(tmp_path)
    prov = git_provenance(
        t["repo"],
        launch={"start_commit": "0" * 40, "git_status_porcelain": ""},
    )
    assert prov["head_commit"] == t["commit"] and prov["start_commit"] == "0" * 40
    assert any("HEAD" in p for p in settling.provenance_problems(prov))


def test_validated_record_requires_clean_ancestor_provenance(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_c1_cfg", t["c1"])
    entry = t["manifest"]["controls"][0]
    assert validate_run_record(record, entry) == []
    for key, value in (
        ("ancestor_of_upstream", False),
        ("dirty_at_launch", True),
        ("dirty_at_record", True),
        ("working_tree_matches_commit", False),
    ):
        bad = json.loads(json.dumps(record))
        bad["provenance"][key] = value
        assert any(key in p for p in validate_run_record(bad, entry)), key


# --------------------------------------------------------------------------- deck, image, command


def test_run_deck_must_be_the_committed_deck(tmp_path):
    t = _tree(tmp_path)
    entry = t["manifest"]["controls"][0]
    (t["c1"] / Path(entry["deck"]).name).write_bytes(b"stale deck\n")
    record = _record(t, "fine_c1_cfg", t["c1"])
    assert any("deck" in p for p in validate_run_record(record, entry))


def test_command_must_name_the_pinned_image(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_c1_cfg", t["c1"])
    record["command"] = "docker run ghcr.io/talmolab/mosquito-cfd:fp64 ..."
    problems = validate_run_record(record, t["manifest"]["controls"][0])
    assert any("image" in p for p in problems)


def test_record_without_command_file_raises_naming_it(tmp_path):
    t = _tree(tmp_path)
    (t["c1"] / "command.txt").unlink()
    with pytest.raises(ValueError, match="command.txt"):
        _record(t, "fine_c1_cfg", t["c1"])


def test_several_run_time_lines_raise(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("Run time = 50\nRun time = 7\n")
    with pytest.raises(ValueError, match="run-time"):
        settling._wall_time(log)


# --------------------------------------------------------------------------- report validation


def _extraction_metadata(t: dict, csv_sha: str) -> None:
    (t["settling_dir"] / "fine" / "run_metadata.json").write_text(
        json.dumps({"extraction_inputs": {"csv_sha256": {"cfg": csv_sha}}})
    )


def _complete_tree(tmp_path: Path) -> dict:
    t = _tree(tmp_path)
    t["long_record"] = _record(t, "fine_cfg", t["long"])
    _write_record(t, t["long_record"])
    _write_record(t, _record(t, "fine_c1_cfg", t["c1"]))
    return t


def test_complete_report_validates_records_and_links_the_dataset(tmp_path):
    t = _complete_tree(tmp_path)
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "complete", report
    assert report["runs"]["fine_cfg"]["mean_cf_z_drift"]


def test_string_false_is_not_a_pass(tmp_path):
    t = _complete_tree(tmp_path)
    bad = json.loads(json.dumps(t["long_record"]))
    bad["controls"]["C3"]["passed"] = "false"
    _write_record(t, bad)
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] != "complete"


def test_invalid_record_makes_the_report_incomplete(tmp_path):
    t = _complete_tree(tmp_path)
    bad = dict(t["long_record"], hardware={})
    _write_record(t, bad)
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] != "complete"
    assert any("hardware" in m for m in report["missing"] + report["failed"])


def test_dataset_built_from_another_csv_is_data_incomplete(tmp_path):
    t = _complete_tree(tmp_path)
    _extraction_metadata(t, "0" * 64)
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "data_incomplete"
    assert any("csv" in m.lower() for m in report["data_missing"])


def test_missing_dataset_rows_mark_the_report_data_incomplete(tmp_path):
    t = _complete_tree(tmp_path)
    _cf_frame("other", 8, 0.2).to_parquet(
        t["settling_dir"] / "fine" / "dataset.parquet"
    )
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "data_incomplete"
    assert report["decision"] is None


# --------------------------------------------------------------------------- decision, spec pins


def test_decision_beat_and_target_describe_the_same_beat():
    v = RunVerdict(
        run="r",
        n_star=7,
        contracting=True,
        max_noise=1e-5,
        noise_target="CF_x",
        passes={5: False, 6: False, 7: True, 8: True},
        binding_beat=6,
        binding_target="CF_my",
    )
    d = decide_beat_count([v])
    assert (d.beat, d.target) == (6, "CF_my")


def test_nan_noise_stops():
    v = RunVerdict(
        run="r",
        n_star=6,
        contracting=True,
        max_noise=float("nan"),
        noise_target="CF_x",
        passes={6: True},
        binding_beat=6,
        binding_target="CF_x",
    )
    assert decide_beat_count([v]).action == "stop"


def test_spec_constants_rejects_a_contradicting_duplicate(tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("`SETTLED_TOLERANCE = 0.02` and later `SETTLED_TOLERANCE = 0.01`\n")
    with pytest.raises(ValueError, match="SETTLED_TOLERANCE"):
        spec_constants(spec)


def test_every_decision_number_is_preregistered():
    for name in (
        "COST_APPROVAL_ABOVE",
        "AT_FLOOR_FACTOR",
        "CLAMP_SLACK",
        "COMPARE_RELATIVE_TO_COLUMN",
        "COMPARE_PRINT_UNITS",
        "FIELD_CHANGE_THRESHOLD",
    ):
        assert name in settling.PREREGISTERED_NAMES


def test_settling_py_is_gated():
    assert settling.SETTLING_PY in GATED_FILES


# --------------------------------------------------------------------------- beat labels


def test_incomplete_first_beat_is_named():
    frame = _cf_frame("cfg", 8, 0.2)
    frame = frame[~((frame["wingbeat"] == 0) & (frame.index % 2000 >= 1000))]
    with pytest.raises(ValueError, match="beat 1"):
        settling.settling_metrics(
            frame, config_name="cfg", frequency_fstar=1.0, dt=DT, stop_time=8.0
        )


@pytest.mark.parametrize("bad", [np.nan, 0.5])
def test_non_integer_wingbeat_is_named(bad):
    frame = _cf_frame("cfg", 8, 0.2)
    frame["wingbeat"] = frame["wingbeat"].astype(float)
    frame.loc[10, "wingbeat"] = bad
    with pytest.raises(ValueError, match="cfg.*wingbeat"):
        settling.settling_metrics(
            frame, config_name="cfg", frequency_fstar=1.0, dt=DT, stop_time=8.0
        )


# --------------------------------------------------------------------------- mutation follow-ups


def test_precedence_failure_is_the_report_status(tmp_path):
    """Valid records and complete data, but a gated file edited after the runs."""
    t = _complete_tree(tmp_path)
    (t["repo"] / GATED_FILES[0]).write_bytes(b"# edited after the runs\n")
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "precedence_failed"
    assert any(GATED_FILES[0] in p for p in report["precedence"])


def test_run_with_only_a_partial_first_beat_names_beat_1():
    frame = _cf_frame("cfg", 1, 0.2).iloc[:1200]
    with pytest.raises(ValueError, match="beat 1"):
        settling.settling_metrics(
            frame, config_name="cfg", frequency_fstar=1.0, dt=DT, stop_time=1.0
        )


def test_a_name_in_both_runs_and_controls_is_rejected(tmp_path):
    t = _tree(tmp_path)
    manifest = json.loads((t["settling_dir"] / "settling_manifest.json").read_text())
    manifest["controls"].append(dict(manifest["runs"][0]))
    (t["settling_dir"] / "settling_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="fine_cfg.*2 entries"):
        settling.manifest_entry(t["settling_dir"], "fine_cfg")


# --------------------------------------------------------------------------- re-review round 2


class _T:
    def __init__(self, nu):
        self.noise_floor = nu


def test_a_nan_noise_floor_in_any_target_is_the_noise_target():
    targets = {"CF_x": _T(1e-5), "CF_y": _T(float("nan")), "CF_z": _T(2e-5)}
    assert settling.noisiest_target(targets) == "CF_y"
    assert settling.noisiest_target({"CF_x": _T(1e-5), "CF_y": _T(3e-5)}) == "CF_y"


def test_reason_at_min_beats_does_not_claim_a_blocked_count():
    v = RunVerdict(
        run="r",
        n_star=settling.MIN_BEATS,
        contracting=True,
        max_noise=1e-5,
        noise_target="CF_x",
        passes={5: True},
        binding_beat=5,
        binding_target="CF_z",
    )
    d = decide_beat_count([v])
    assert d.beat == 5 and "blocked" not in d.reason


def test_an_upstream_other_than_origin_main_is_refused(tmp_path):
    t = _tree(tmp_path)
    prov = git_provenance(
        t["repo"],
        launch={"start_commit": t["commit"], "git_status_porcelain": ""},
        upstream_ref="upstream",
    )
    assert any("upstream_ref" in p for p in settling.provenance_problems(prov))


def test_a_missing_origin_main_says_fetch(tmp_path):
    t = _tree(tmp_path)
    _git(t["repo"], "update-ref", "-d", "refs/remotes/origin/main")
    prov = _provenance(t)
    problems = settling.provenance_problems(prov)
    assert any("does not exist" in p and "fetch" in p for p in problems)


@pytest.mark.parametrize(
    "line",
    [
        "R  src/x.py -> examples/settling_check/records/x.py",
        " M examples/settling_check/records/fine_c1_cfg.json",
        " D examples/settling_check/records/fine_c1_cfg.json",
        "?? stray.py",
    ],
)
def test_only_new_untracked_records_are_exempt_from_the_dirty_check(line):
    assert settling._dirty_lines(line) == [line]


def test_a_new_untracked_record_is_not_dirty():
    assert (
        settling._dirty_lines("?? examples/settling_check/records/fine_cfg.json") == []
    )


def test_launch_refuses_a_dirty_checkout(tmp_path):
    from test_settling_report import _launch_script

    t = _tree(tmp_path)
    (t["repo"] / "stray.py").write_text("x = 1\n")
    result = _launch_script(t, t["c1"])
    assert result.returncode == 1 and "dirty" in result.stdout
    assert not (t["c1"] / "launch.json").exists()


def test_launch_refuses_a_commit_not_on_origin_main(tmp_path):
    from test_settling_report import _launch_script

    t = _tree(tmp_path)
    (t["repo"] / "extra.txt").write_text("x")
    _git(t["repo"], "add", "extra.txt")
    _git(t["repo"], "-c", "commit.gpgsign=false", "commit", "-q", "-m", "local")
    result = _launch_script(t, t["c1"])
    assert result.returncode == 1 and "origin/main" in result.stdout
    assert not (t["c1"] / "launch.json").exists()


def test_launch_accepts_new_untracked_records(tmp_path):
    from test_settling_report import _launch_script

    t = _tree(tmp_path)
    (t["settling_dir"] / "records").mkdir()
    (t["settling_dir"] / "records" / "fine_c1_cfg.json").write_text("{}")
    assert _launch_script(t, t["long"]).returncode == 0


def test_short_run_in_the_report_is_data_incomplete_not_a_crash(tmp_path):
    t = _complete_tree(tmp_path)
    _cf_frame("cfg", 3, 0.2).to_parquet(t["settling_dir"] / "fine" / "dataset.parquet")
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] == "data_incomplete"
    assert any("fine_cfg" in m for m in report["data_missing"])


@pytest.mark.parametrize("key", ["force_csv_sha256", "run_log_sha256"])
def test_raw_file_hashes_are_required(tmp_path, key):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    for bad in (None, 5, "abc"):
        broken = dict(record)
        if bad is None:
            broken.pop(key)
        else:
            broken[key] = bad
        assert any(
            key in p for p in validate_run_record(broken, t["manifest"]["runs"][0])
        )


def test_report_with_a_non_string_csv_hash_names_it(tmp_path):
    t = _complete_tree(tmp_path)
    bad = dict(t["long_record"], force_csv_sha256=5)
    _write_record(t, bad)
    report = build_settling_report(
        t["settling_dir"], repo_root=t["repo"], git_commit=COMMIT
    )
    assert report["status"] != "complete"


def test_infinite_reference_value_fails(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _csv(csv, 400)
    ref = _ref(400)
    ref.loc[2, "Fx"] = np.inf
    result = _compare(csv, ref)
    assert not result.passed and "Fx" in result.failures[0]


def test_record_script_without_docker_fails_cleanly(tmp_path, monkeypatch):
    from test_settling_report import _launch_script, _script_module

    t = _tree(tmp_path)
    assert _launch_script(t, t["c1"]).returncode == 0
    module = _script_module()

    def no_docker(*args, **kwargs):
        raise FileNotFoundError("docker")

    monkeypatch.setattr(module.subprocess, "run", no_docker)
    with pytest.raises(SystemExit, match="docker"):
        module._iamrex_label_from_docker("img@sha256:" + "a" * 64)


def test_record_script_without_hardware_json_fails_cleanly(tmp_path):
    from test_settling_report import _launch_script, _run_script

    t = _tree(tmp_path)
    assert _launch_script(t, t["c1"]).returncode == 0
    result = _run_script(
        [
            "record",
            "--name",
            "fine_c1_cfg",
            "--run-dir",
            str(t["c1"]),
            "--settling-dir",
            str(t["settling_dir"]),
            "--repo-root",
            str(t["repo"]),
        ]
    )
    assert result.returncode == 1 and "hardware.json" in result.stdout


def test_record_script_has_no_label_or_upstream_override():
    from test_settling_report import _script_module

    module = _script_module()
    with pytest.raises(SystemExit):
        module.main(["record", "--name", "x", "--run-dir", ".", "--iamrex-commit", "y"])
    with pytest.raises(SystemExit):
        module.main(["record", "--name", "x", "--run-dir", ".", "--upstream-ref", "y"])


def test_field_change_shape_is_validated(tmp_path):
    t = _tree(tmp_path)
    record = _record(t, "fine_cfg", t["long"])
    record["field_change"] = {"beats": "oops"}
    assert any(
        "field_change" in p
        for p in validate_run_record(record, t["manifest"]["runs"][0])
    )


def test_committed_settling_manifests_use_the_project_timestep():
    for grid in ("coarse", "fine"):
        sweep = json.loads(
            (
                REPO / "examples/settling_check" / grid / "sweep_manifest.json"
            ).read_text()
        )
        assert sweep["dt"] == settling.DT
