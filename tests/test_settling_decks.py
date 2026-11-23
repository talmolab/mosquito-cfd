"""Stage 1 settling-check decks (add-settled-beat-corpus task 4.1).

Each deck must differ from its committed corpus deck in exactly the declared key set, so the
settling result transfers to the regenerated corpus.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from mosquito_cfd._manifest import load_manifest_configs
from mosquito_cfd.force_surrogate.metadata_capture import parse_deck
from mosquito_cfd.force_surrogate.settling import deck_key_mismatches
from mosquito_cfd.force_surrogate.sweep import derive_run_duration

REPO = Path(__file__).resolve().parents[1]
SETTLING = REPO / "examples" / "settling_check"
DRIVER = SETTLING / "generate_decks.py"
FINE_IMAGE = (
    "ghcr.io/talmolab/mosquito-cfd@sha256:"
    "92817878fead23f9c6b8219706a2ebcec7cccf2158db8016e867e0227ca68a47"
)
COARSE_IMAGE = (
    "ghcr.io/talmolab/mosquito-cfd@sha256:"
    "07625ce41bef8dae5983afddf5a3d09a3fb7706cb29292d19a479600967b24d3"
)
LONG_KEYS = {
    "max_step",
    "stop_time",
    "amrex.the_arena_init_size",
    "amr.plot_int",
    "amr.plot_per",
    "amr.check_int",
    "amr.check_per",
}
C1_KEYS = {"max_step", "amrex.the_arena_init_size"}
EXPECTED_MAX_STEP = {
    "s35_f085_p30": 18824,
    "s45_f100_p30": 16000,
    "s55_f115_p30": 13913,
}


def _driver():
    spec = importlib.util.spec_from_file_location("settling_generate_decks", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _manifest() -> dict:
    return json.loads((SETTLING / "settling_manifest.json").read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_regeneration_is_byte_identical(tmp_path):
    _driver().generate(REPO, tmp_path)
    produced = sorted(
        p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()
    )
    assert produced
    for rel in produced:
        assert (tmp_path / rel).read_bytes() == (SETTLING / rel).read_bytes(), rel


def test_driver_check_mode_passes_on_the_committed_tree():
    proc = subprocess.run(
        [sys.executable, str(DRIVER), "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_orphan_decks_are_found(tmp_path):
    driver = _driver()
    files = driver.generate(REPO, tmp_path)
    assert driver.find_orphans(tmp_path, files) == []
    (tmp_path / "fine" / "inputs" / "inputs.3d.s45_f100_p45").write_text("old deck\n")
    assert driver.find_orphans(tmp_path, files) == [
        "fine/inputs/inputs.3d.s45_f100_p45"
    ]


def test_six_long_runs_and_two_c1_decks_are_declared():
    m = _manifest()
    assert m["n_wingbeats"] == 8
    assert sorted((r["grid"], r["config"]) for r in m["runs"]) == sorted(
        (g, c) for g in ("coarse", "fine") for c in EXPECTED_MAX_STEP
    )
    assert sorted((c["grid"], c["config"], c["kind"]) for c in m["controls"]) == [
        ("coarse", "s55_f115_p30", "C1"),
        ("fine", "s55_f115_p30", "C1"),
    ]
    for run in m["runs"]:
        assert run["controls"] == ["C3", "C4"]
    assert m["images"] == {"coarse": COARSE_IMAGE, "fine": FINE_IMAGE}


@pytest.mark.parametrize("entry_kind", ["runs", "controls"])
def test_every_deck_differs_by_exactly_its_declared_keys(entry_kind):
    for entry in _manifest()[entry_kind]:
        source = REPO / entry["source_deck"]
        deck = SETTLING / entry["deck"]
        assert entry["source_deck_sha256"] == _sha(source)
        assert entry["deck_sha256"] == _sha(deck)
        declared = set(entry["declared_keys"])
        if entry_kind == "controls":
            assert declared == C1_KEYS
        elif entry["grid"] == "fine":
            assert declared == LONG_KEYS
        else:  # the coarse corpus decks already have amr.plot_int = -1
            assert declared == LONG_KEYS - {"amr.plot_int"}
        assert deck_key_mismatches(parse_deck(source), parse_deck(deck), declared) == []


def test_long_run_durations_and_output_cadence():
    for run in _manifest()["runs"]:
        deck = parse_deck(SETTLING / run["deck"])
        source = parse_deck(REPO / run["source_deck"])
        f_star = float(deck["particle_inputs.kinematics_frequency"])
        max_step, stop_time = derive_run_duration(f_star, n_wingbeats=8)
        assert int(deck["max_step"]) == max_step == EXPECTED_MAX_STEP[run["config"]]
        assert float(deck["stop_time"]) == stop_time
        assert float(deck["amr.plot_per"]) == 1.0 / (20 * f_star)
        assert float(deck["amr.check_per"]) == 1.0 / f_star
        assert deck["amr.plot_int"] == "-1" and deck["amr.check_int"] == "-1"
        assert deck["amrex.the_arena_init_size"] == "12884901888"
        for key in ("ns.cfl", "ns.init_iter", "ns.fixed_dt", "amr.n_cell"):
            assert deck[key] == source[key], key


def test_c1_decks_run_400_steps_of_the_unmodified_deck():
    for control in _manifest()["controls"]:
        deck = parse_deck(SETTLING / control["deck"])
        source = parse_deck(REPO / control["source_deck"])
        assert deck["max_step"] == "400"
        assert deck["stop_time"] == source["stop_time"]
        assert control["max_step"] == 400


def test_coarse_keeps_init_iter_zero_and_fine_keeps_two():
    for run in _manifest()["runs"]:
        deck = parse_deck(SETTLING / run["deck"])
        assert deck["ns.init_iter"] == ("2" if run["grid"] == "fine" else "0")


def test_per_grid_sweep_manifests_feed_the_existing_extractor():
    for grid in ("coarse", "fine"):
        path = SETTLING / grid / "sweep_manifest.json"
        configs = load_manifest_configs(path)
        assert sorted(c["name"] for c in configs) == sorted(EXPECTED_MAX_STEP)
        for config in configs:
            assert (path.parent / config["input_file"]).exists()
            assert config["max_step"] == EXPECTED_MAX_STEP[config["name"]]
        top = json.loads(path.read_text(encoding="utf-8"))
        assert top["n_wingbeats"] == 8 and top["dt"] == 0.0005


# --------------------------------------------------------------------------- the key checker


def _kv() -> dict[str, str]:
    return parse_deck(REPO / "examples/prelim_sweep_fine/inputs/inputs.3d.s55_f115_p30")


def test_missing_declared_key_is_named():
    source = _kv()
    generated = dict(source, max_step="13913", stop_time="12.1")
    mismatches = deck_key_mismatches(
        source, generated, {"max_step", "stop_time", "amrex.the_arena_init_size"}
    )
    assert mismatches == [
        "declared key amrex.the_arena_init_size is not changed or added"
    ]


def test_undeclared_change_is_named():
    source = _kv()
    generated = dict(source, max_step="13913", **{"ns.cfl": "0.7"})
    mismatches = deck_key_mismatches(source, generated, {"max_step"})
    assert mismatches == ["undeclared key ns.cfl differs: '0.6' -> '0.7'"]


def test_removed_key_is_named():
    source = _kv()
    generated = {k: v for k, v in source.items() if k != "ns.init_iter"}
    generated["max_step"] = "1"
    assert deck_key_mismatches(source, generated, {"max_step"}) == [
        "undeclared key ns.init_iter is missing from the generated deck"
    ]


# --------------------------------------------------------------------------- ignore rules (4.3)

IGNORED = [
    "examples/settling_check/runs/fine_s35_f085_p30/IB_Particle_1.csv",
    "examples/settling_check/fine/runs/s35_f085_p30/plt00100/Header",
    "examples/settling_check/coarse/runs/s45_f100_p30/run.log",
    # Only the settling rule covers these two (no global *.json or wing.vertex rule):
    "examples/settling_check/fine/runs/s35_f085_p30/run_metadata.json",
    "examples/settling_check/runs/coarse_s55_f115_p30/wing.vertex",
]
TRACKED = [
    "examples/settling_check/fine/dataset.parquet",
    "examples/settling_check/fine/inputs/inputs.3d.s35_f085_p30",
    "examples/settling_check/settling_manifest.json",
    "examples/settling_check/records/fine_s35_f085_p30.json",
    "examples/settling_check/settling_report.json",
    "examples/settling_check/settling_figure.png",
    "examples/settling_check/DECISION.md",
]


def _ignored(path: str) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path], cwd=REPO, capture_output=True
    )
    # 0 = ignored, 1 = not ignored; anything else is a git error, never "not ignored".
    assert proc.returncode in (0, 1), proc.stderr
    return proc.returncode == 0


@pytest.mark.parametrize("path", IGNORED)
def test_raw_run_files_are_ignored(path):
    assert _ignored(path)


@pytest.mark.parametrize("path", TRACKED)
def test_committed_artifacts_are_not_ignored(path):
    assert not _ignored(path)
