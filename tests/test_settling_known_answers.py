"""Known answers for the settling metric on real CFD data (add-settled-beat-corpus task 1.2).

Two external references:

- the E0b coarse 6-beat runs (``tests/fixtures/settling/``), whose own per-beat table was computed
  independently on the exploration branch;
- the committed 2-beat corpora, whose final beats set the jitter the noise floor must cover.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.settling import (
    MAX_NOISE,
    TARGETS,
    decide_beat_count,
    drop_clamped_rows,
    evaluate_run,
    jitter,
    resample_beats,
    settling_metrics,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures" / "settling"
DT = 5e-4
FIXTURE_SHA256 = {
    "e0b_s45_f100_p30_6beat.parquet": "63c8f0a100118509fe69d6b19e96f24503b1066f62a2bd932801c63af8677a83",
    "e0b_s45_f100_p30_beat_convergence.csv": "60394460110942045cbe9fd6c22b4ceb4fdf6ea8bda540548128ee9e936ea5d0",
    "e0b_s45_f100_p45_6beat.parquet": "aab87db223c85f088aa1e40d35cf1bd3904de8e1f185a2ec9d80b2df300e6041",
    "e0b_s45_f100_p45_beat_convergence.csv": "d3ece14ee9e1ab9e7adb392847a74cd259e05c29a227be572d1cf32cff78634f",
}


def _e0b(config: str) -> pd.DataFrame:
    return pd.read_parquet(FIXTURES / f"e0b_{config}_6beat.parquet")


def _e0b_metrics(config: str):
    return settling_metrics(
        _e0b(config), config_name=config, frequency_fstar=1.0, dt=DT, stop_time=6.0
    )


@pytest.mark.parametrize("name", sorted(FIXTURE_SHA256))
def test_fixture_bytes_are_the_recorded_ones(name):
    assert (
        hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
        == FIXTURE_SHA256[name]
    )


@pytest.mark.parametrize("config", ["s45_f100_p45", "s45_f100_p30"])
def test_e0b_published_tables_are_reproduced(config):
    """E0b's own method: 256-point grid, phase >= 0.05 mask, beat 6's unmasked grid peak."""
    grids = resample_beats(_e0b(config), n_phase=256)
    table = pd.read_csv(FIXTURES / f"e0b_{config}_beat_convergence.csv")
    keep = np.arange(256) / 256 >= 0.05
    for target in TARGETS:
        last = grids[6][target]
        peak = np.abs(last).max()
        for b in range(2, 7):
            diff = (grids[b][target] - grids[b - 1][target])[keep]
            ours = np.sqrt(np.mean(diff**2)) / peak
            row = table[(table["beat"] == b) & (table["target"] == target)]
            assert ours == pytest.approx(
                float(row["diff_from_previous_over_peak"].iloc[0]), abs=5e-5
            )


def test_s45_f100_p30_known_answer():
    result = _e0b_metrics("s45_f100_p30")
    assert result.b_last == 6
    assert result.targets["CF_my"].tail == pytest.approx(0.01245, abs=1e-4)
    assert result.targets["CF_z"].tail == pytest.approx(0.01168, abs=1e-4)
    assert result.targets["CF_mx"].tail == pytest.approx(0.01048, abs=1e-4)


def test_s45_f100_p45_known_answer():
    result = _e0b_metrics("s45_f100_p45")
    t = result.targets["CF_my"]
    assert t.ratios == pytest.approx([0.476, 0.399, 0.644], abs=1e-3)
    assert t.rho == pytest.approx(0.812, abs=1e-3)
    assert t.tail == pytest.approx(0.01007, abs=1e-4)


def test_e0b_runs_have_no_settled_beat_and_the_decision_is_stop():
    verdicts = [
        evaluate_run(c, _e0b(c), frequency_fstar=1.0, dt=DT, stop_time=6.0)
        for c in ("s45_f100_p45", "s45_f100_p30")
    ]
    p45, p30 = verdicts
    assert p45.passes == {5: False, 6: False}
    assert p30.passes == {5: False, 6: False}
    assert p30.n_star is None and p30.binding_target == "CF_my"
    decision = decide_beat_count(verdicts)
    assert decision.action == "stop"


def _final_beats():
    for corpus in ("prelim_sweep", "prelim_sweep_fine"):
        base = REPO / "examples" / corpus
        manifest = json.loads(
            (base / "sweep_manifest.json").read_text(encoding="utf-8")
        )
        configs = {c["name"]: c for c in manifest["configs"]}
        data = pd.read_parquet(base / "dataset.parquet")
        for name, frame in data.groupby("config_name"):
            kept = drop_clamped_rows(
                frame.sort_values("time"), stop_time=configs[name]["stop_time"], dt=DT
            )
            yield corpus, name, configs[name], kept[kept["wingbeat"] == 1]


def test_jitter_of_every_committed_final_beat_is_below_6p5e_5():
    worst = 0.0
    for _, _, _, beat in _final_beats():
        for target in TARGETS:
            values = beat[target].to_numpy()
            worst = max(worst, jitter(values, peak=float(np.abs(values).max())))
    assert worst < 6.5e-5


def _periodic_run(beat: pd.DataFrame, f_star: float, n_beats: int) -> pd.DataFrame:
    """An exactly periodic run on the true step grid, by linear interpolation of one beat."""
    max_step = round(n_beats / f_star / DT)
    time = np.arange(max_step) * DT
    cycles = time * f_star
    phase = np.mod(cycles, 1.0)
    order = np.argsort(beat["phase"].to_numpy())
    data = {
        "config_name": "periodic",
        "time": time,
        "phase": phase,
        "wingbeat": np.floor(cycles).astype(np.int64),
    }
    for target in TARGETS:
        data[target] = np.interp(
            phase,
            beat["phase"].to_numpy()[order],
            beat[target].to_numpy()[order],
            period=1.0,
        )
    return pd.DataFrame(data)


def test_off_integer_steps_add_less_than_the_noise_floor_on_real_beats():
    checked = 0
    for _, name, config, beat in _final_beats():
        f_star = config["frequency_fstar"]
        if f_star == 1.0:
            continue
        run = _periodic_run(beat, f_star, 8)
        result = settling_metrics(
            run, config_name=name, frequency_fstar=f_star, dt=DT, stop_time=8 / f_star
        )
        for target in TARGETS:
            t = result.targets[target]
            assert t.noise_floor <= MAX_NOISE, (name, target)
            for b in range(2, 9):
                assert t.steps[b] <= t.noise_floor, (name, target, b)
        checked += 1
    assert checked == 36  # 18 off-integer configurations on each of two grids
