"""Tests for the beat-to-beat settling metric and decision rule (add-settled-beat-corpus).

The synthetic runs here are built on the solver's real sampling grid (``time = step * dt``,
``phase = (time * f*) mod 1``, ``wingbeat = floor(time * f*)``), so off-integer steps per beat
at ``f*`` 0.85 and 1.15 are exercised exactly as the corpus produces them.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import settling
from mosquito_cfd.force_surrogate.settling import (
    COMPLETE_FRACTION,
    FIRST_RATIO_BEAT,
    MAX_NOISE,
    MIN_BEATS,
    NOISE_FACTOR,
    SETTLED_TOLERANCE,
    TARGETS,
    RunVerdict,
    decide_beat_count,
    drop_clamped_rows,
    evaluate_run,
    jitter,
    settling_metrics,
    tail_bound,
)

DT = 5e-4


def _grid(f_star: float, n_beats: int, dt: float = DT) -> tuple[np.ndarray, float]:
    """Return (time, stop_time) for an n-beat run as the sweep would declare it."""
    stop_time = n_beats / f_star
    max_step = round(stop_time / dt)
    time = np.arange(max_step) * dt
    return time, stop_time


def _frame(f_star: float, n_beats: int, signal, *, name: str = "cfg") -> pd.DataFrame:
    """A run frame whose every target is ``signal(beat_index_0based, phase)``.

    ``signal`` may return a scalar array (used for every target) or a dict of arrays per target.
    """
    time, _ = _grid(f_star, n_beats)
    cycles = time * f_star
    phase = np.mod(cycles, 1.0)
    wingbeat = np.floor(cycles).astype(np.int64)
    values = signal(wingbeat, phase)
    data = {
        "config_name": name,
        "time": time,
        "phase": phase,
        "wingbeat": wingbeat,
        "frequency_fstar": f_star,
    }
    for target in TARGETS:
        data[target] = values[target] if isinstance(values, dict) else values
    return pd.DataFrame(data)


def _metrics(frame: pd.DataFrame, f_star: float, n_beats: int):
    _, stop_time = _grid(f_star, n_beats)
    return settling_metrics(
        frame, config_name="cfg", frequency_fstar=f_star, dt=DT, stop_time=stop_time
    )


def _base(phase: np.ndarray) -> np.ndarray:
    return np.sin(2 * np.pi * phase) + 0.3 * np.cos(4 * np.pi * phase)


# --------------------------------------------------------------------------- constants


def test_constants_are_the_preregistered_values():
    assert SETTLED_TOLERANCE == 0.01
    assert COMPLETE_FRACTION == 0.95
    assert MIN_BEATS == 5
    assert FIRST_RATIO_BEAT == 4
    assert NOISE_FACTOR == 3
    assert MAX_NOISE == 0.0006
    assert TARGETS == ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")


# --------------------------------------------------------------------------- tail bound


def test_rising_ratios_widen_the_bound():
    steps = {5: 0.0125, 6: 0.0080, 7: 0.0050, 8: 0.0036}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    r6, r7, r8 = 0.0080 / 0.0125, 0.0050 / 0.0080, 0.0036 / 0.0050
    assert tb.ratios == pytest.approx([r6, r7, r8], rel=1e-12)
    assert tb.rho == pytest.approx(max(r6, r7, r8) + (r8 - r6), rel=1e-12)
    assert tb.rho == pytest.approx(0.80, rel=1e-6)
    assert tb.tail == pytest.approx(0.0036 * 0.80 / 0.20, rel=1e-6)
    assert tb.tail > SETTLED_TOLERANCE
    assert tb.contracting


def test_falling_ratios_add_no_widening():
    steps = {5: 0.02, 6: 0.012, 7: 0.006, 8: 0.0024}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    assert tb.rho == pytest.approx(max(tb.ratios), rel=1e-12)


def test_slow_mode_below_one_percent_is_not_noise():
    steps = {5: 8.1e-4, 6: 7.7e-4, 7: 7.4e-4, 8: 7.0e-4}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    assert tb.skipped == []
    assert tb.tail > SETTLED_TOLERANCE


def test_growth_from_the_noise_floor_is_not_contracting():
    steps = {5: 1e-6, 6: 1e-5, 7: 1e-4, 8: 9e-4}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    assert not tb.contracting
    assert math.isinf(tb.tail)


def test_growth_straight_out_of_the_floor_is_not_contracting():
    steps = {5: 1e-5, 6: 1e-5, 7: 1e-5, 8: 5e-3}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    assert not tb.contracting
    assert math.isinf(tb.tail)


def test_run_at_the_noise_floor_is_bounded_not_stopped():
    steps = {4: 5e-5, 5: 4e-5, 6: 3e-5, 7: 4e-5}
    tb = tail_bound(steps, b_last=7, nu=6e-5)
    assert tb.skipped == [5, 6, 7]
    assert tb.contracting
    assert tb.rho is None
    assert tb.tail == pytest.approx(24 * 4e-5, rel=1e-12)


def test_two_noise_steps_straddling_the_floor_are_not_growth():
    steps = {4: 5e-5, 5: 4e-5, 6: 5e-5, 7: 7e-5}
    tb = tail_bound(steps, b_last=7, nu=6e-5)
    assert tb.contracting
    assert math.isfinite(tb.tail)


def test_ratio_of_exactly_one_is_not_contracting():
    steps = {5: 0.004, 6: 0.004, 7: 0.004, 8: 0.004}
    tb = tail_bound(steps, b_last=8, nu=6e-5)
    assert not tb.contracting
    assert math.isinf(tb.tail)


def test_step_exactly_at_the_floor_counts_as_noise():
    nu = 6e-5
    steps = {5: 0.004, 6: nu, 7: nu, 8: 2 * nu}
    tb = tail_bound(steps, b_last=8, nu=nu)
    # b=6: 0.004 > nu -> a real ratio; b=7 and b=8: previous step at nu and current <= 2 nu.
    assert tb.skipped == [7, 8]
    assert tb.ratios == pytest.approx([nu / 0.004], rel=1e-12)


def test_ratio_window_starts_at_first_ratio_beat():
    steps = {3: 0.5, 4: 0.02, 5: 0.012}
    tb = tail_bound(steps, b_last=5, nu=6e-5)
    # B = 5 uses b = 4 and 5: r_4 = s_4 / s_3 enters, the start-up step s_2 never does.
    assert tb.ratio_beats == [4, 5]
    assert len(tb.ratios) == 2


def test_six_beats_use_three_ratios():
    steps = {3: 0.03, 4: 0.02, 5: 0.012, 6: 0.008}
    tb = tail_bound(steps, b_last=6, nu=6e-5)
    assert tb.ratio_beats == [4, 5, 6]


# --------------------------------------------------------------------------- metric


def _geometric(r: float, a: float):
    def signal(wingbeat, phase):
        g = np.cos(2 * np.pi * phase) + 0.5
        return _base(phase) + a * r ** (wingbeat + 1) * g

    return signal


def test_geometric_approach_reproduces_its_closed_form():
    r, a = 0.6, 1.0
    frame = _frame(1.0, 8, _geometric(r, a))
    result = _metrics(frame, 1.0, 8)
    assert result.b_last == 8
    phase = np.arange(2000) / 2000
    g = np.cos(2 * np.pi * phase) + 0.5
    w_last = _base(phase) + a * r**8 * g
    peak = np.abs(w_last).max()
    rms_g = np.sqrt(np.mean(g**2))
    for target in TARGETS:
        t = result.targets[target]
        for b in range(2, 9):
            expected = a * (r ** (b - 1) - r**b) * rms_g / peak
            assert t.steps[b] == pytest.approx(expected, rel=1e-9)
        assert t.rho == pytest.approx(r, rel=1e-9)
        assert t.tail == pytest.approx(t.steps[8] * r / (1 - r), rel=1e-9)
        for b in range(1, 9):
            true_distance = a * r**b * rms_g / peak
            assert t.estimate[b] >= true_distance * (1 - 1e-9)


def test_too_few_complete_beats_raise():
    frame = _frame(1.0, 4, _geometric(0.6, 1.0))
    with pytest.raises(ValueError, match=r"cfg.*4 complete beat"):
        _metrics(frame, 1.0, 4)


def test_incomplete_final_beat_is_not_the_reference():
    full = _frame(1.0, 8, _geometric(0.6, 1.0))
    keep = (full["wingbeat"] < 7) | (full.index < 7 * 2000 + 1200)  # beat 8 at 60%
    result = _metrics(full[keep].reset_index(drop=True), 1.0, 8)
    assert result.b_last == 7
    assert result.incomplete_beats == [8]


def test_exactly_ninety_five_percent_counts_as_complete():
    full = _frame(1.0, 6, _geometric(0.6, 1.0))
    keep = (full["wingbeat"] < 5) | (full.index < 5 * 2000 + 1900)  # beat 6 at 95%
    result = _metrics(full[keep].reset_index(drop=True), 1.0, 6)
    assert result.b_last == 6


def test_incomplete_beat_before_the_last_complete_one_raises():
    full = _frame(1.0, 6, _geometric(0.6, 1.0))
    gap = (full["wingbeat"] == 2) & (full.index % 2000 >= 1000)
    with pytest.raises(ValueError, match=r"cfg.*beat 3"):
        _metrics(full[~gap].reset_index(drop=True), 1.0, 6)


@pytest.mark.parametrize("f_star", [0.85, 1.15])
def test_row_counts_alternate_and_sum_to_max_step_minus_clamped(f_star):
    time, stop_time = _grid(f_star, 8)
    frame = _frame(f_star, 8, lambda wb, ph: _base(ph))
    counts = frame.groupby("wingbeat").size().to_numpy()
    expected = 1 / (f_star * DT)  # 2352.94 at f085, 1739.13 at f115
    assert set(counts) <= {math.floor(expected), math.ceil(expected)}
    assert counts.sum() == len(time)
    kept = drop_clamped_rows(frame, stop_time=stop_time, dt=DT)
    clamped = 1 if round(stop_time / DT) * DT > stop_time + 1e-9 else 0
    assert len(kept) == len(time) - clamped


def test_clamped_final_step_is_dropped():
    f_star = 0.85
    _, stop_time = _grid(f_star, 8)
    clean = _frame(f_star, 8, _geometric(0.6, 1.0))
    assert (
        round(stop_time / DT) * DT > stop_time
    )  # f085 overshoots, so the last step is clamped
    spiked = clean.copy()
    peak = np.abs(spiked["CF_z"]).max()
    spiked.loc[spiked.index[-1], "CF_z"] += 0.1 * peak
    a = _metrics(spiked, f_star, 8)
    b = _metrics(clean, f_star, 8)
    for target in TARGETS:
        assert a.targets[target].steps == b.targets[target].steps
        assert a.targets[target].tail == b.targets[target].tail


def test_metric_uses_wingbeat_and_phase_as_given():
    frame = _frame(1.0, 6, _geometric(0.6, 1.0))
    moved = frame.copy()
    # Relabel the first 10 rows of beat 3 as beat 2: a consumer that recomputed wingbeat from
    # time would undo this; the metric must not.
    idx = moved.index[(moved["wingbeat"] == 2)][:10]
    moved.loc[idx, "wingbeat"] = 1
    with pytest.raises(ValueError, match="phase"):
        _metrics(moved, 1.0, 6)


def test_duplicate_phase_within_a_beat_raises():
    frame = _frame(1.0, 6, _geometric(0.6, 1.0))
    dup = pd.concat([frame, frame.iloc[[2500]]]).sort_values("time", kind="stable")
    with pytest.raises(ValueError, match=r"cfg.*phase"):
        _metrics(dup.reset_index(drop=True), 1.0, 6)


@pytest.mark.parametrize("column", ["CF_my", "phase", "wingbeat"])
def test_missing_column_raises(column):
    frame = _frame(1.0, 6, _geometric(0.6, 1.0)).drop(columns=[column])
    with pytest.raises(ValueError, match=rf"cfg.*{column}"):
        _metrics(frame, 1.0, 6)


def test_non_finite_value_raises():
    frame = _frame(1.0, 6, _geometric(0.6, 1.0))
    frame.loc[3000, "CF_x"] = np.nan
    with pytest.raises(ValueError, match=r"cfg.*CF_x"):
        _metrics(frame, 1.0, 6)


def test_zero_peak_raises_and_tiny_peak_is_accepted():
    frame = _frame(1.0, 6, _geometric(0.6, 1.0))
    zero = frame.copy()
    zero["CF_y"] = 0.0
    with pytest.raises(ValueError, match=r"cfg.*CF_y.*peak"):
        _metrics(zero, 1.0, 6)
    tiny = frame.copy()
    tiny["CF_y"] = frame["CF_y"] * 1e-6
    assert _metrics(tiny, 1.0, 6).targets["CF_y"].peak > 0


def test_dt_and_stop_time_are_required():
    frame = _frame(1.0, 6, _geometric(0.6, 1.0))
    with pytest.raises(TypeError):
        settling_metrics(frame, config_name="cfg", frequency_fstar=1.0)  # type: ignore[call-arg]


def test_max_abs_difference_is_reported_beside_rms():
    result = _metrics(_frame(1.0, 6, _geometric(0.6, 1.0)), 1.0, 6)
    t = result.targets["CF_x"]
    assert set(t.steps_max_abs) == set(t.steps)
    for b in t.steps:
        assert t.steps_max_abs[b] >= t.steps[b]


def test_mean_cf_z_per_beat_is_reported():
    result = _metrics(_frame(1.0, 6, _geometric(0.6, 1.0)), 1.0, 6)
    assert sorted(result.mean_cf_z) == [1, 2, 3, 4, 5, 6]


def test_jitter_is_the_half_spacing_interpolation_bound():
    v = np.array([0.0, 1.0, 4.0, 9.0, 16.0])  # second difference 2 everywhere
    assert jitter(v, peak=16.0) == pytest.approx(2.0 / (8 * 16.0), rel=1e-12)


@pytest.mark.parametrize("f_star", [0.85, 1.15])
def test_off_integer_steps_add_less_than_the_noise_floor(f_star):
    """An exactly periodic smooth signal on the true step grid gives s_b <= nu."""
    result = _metrics(_frame(f_star, 8, lambda wb, ph: _base(ph)), f_star, 8)
    for target in TARGETS:
        t = result.targets[target]
        for b in range(2, 9):
            assert t.steps[b] <= t.noise_floor
        assert t.noise_floor <= MAX_NOISE


# --------------------------------------------------------------------------- pass(N) and N*


def _two_rate_run(slow_ratio: float, n_beats: int = 8):
    """Beats approach the limit with ratio ``slow_ratio``, from a 5% start."""
    return _frame(1.0, n_beats, _geometric(slow_ratio, 0.05))


def test_fast_settling_run_has_n_star_at_min_beats():
    verdict = evaluate_run(
        "fast", _two_rate_run(0.2), frequency_fstar=1.0, dt=DT, stop_time=8.0
    )
    assert verdict.n_star == MIN_BEATS
    assert verdict.contracting


def test_slow_run_without_settled_beat_has_no_n_star():
    verdict = evaluate_run(
        "slow", _two_rate_run(0.9), frequency_fstar=1.0, dt=DT, stop_time=8.0
    )
    assert verdict.n_star is None
    assert verdict.binding_target in TARGETS


def _two_mode(a1: float, r1: float, a2: float, r2: float):
    def signal(wingbeat, phase):
        g1 = np.cos(2 * np.pi * phase) + 0.5
        g2 = np.sin(4 * np.pi * phase)
        return (
            _base(phase)
            + a1 * r1 ** (wingbeat + 1) * g1
            + a2 * r2 ** (wingbeat + 1) * g2
        )

    return signal


def test_truncated_test_can_fail_when_full_test_passes():
    # A fast mode (ratio 0.1) hands over to a slow one (0.7, from 1%). A single geometric mode
    # cannot do this: its truncated tail bound equals the full run's estimate exactly. Here the
    # run cut at 6 beats sees rising ratios and cannot bound its tail, while the full 8-beat run
    # puts beat 6 well inside the tolerance.
    frame = _frame(1.0, 8, _two_mode(1.0, 0.1, 0.01, 0.7))
    full = settling_metrics(
        frame, config_name="cfg", frequency_fstar=1.0, dt=DT, stop_time=8.0
    )
    trunc = settling_metrics(
        frame[frame["wingbeat"] < 6],
        config_name="cfg",
        frequency_fstar=1.0,
        dt=DT,
        stop_time=6.0,
    )
    assert max(full.targets[t].estimate[6] for t in TARGETS) <= SETTLED_TOLERANCE
    assert max(trunc.targets[t].tail for t in TARGETS) > SETTLED_TOLERANCE
    verdict = evaluate_run("cfg", frame, frequency_fstar=1.0, dt=DT, stop_time=8.0)
    assert verdict.passes[6] is False
    # pass(5) holds here, but N* needs every larger N too, so N* = 7, not 5.
    assert verdict.passes[5] is True
    assert verdict.n_star == 7


def test_n_star_requires_every_later_count_to_pass():
    verdict = RunVerdict(
        run="r",
        n_star=None,
        contracting=True,
        max_noise=1e-5,
        noise_target="CF_x",
        passes={5: True, 6: False, 7: True, 8: True},
        binding_beat=6,
        binding_target="CF_z",
    )
    assert settling.n_star_from_passes(verdict.passes) == 7


# --------------------------------------------------------------------------- decision


def _verdict(run, n_star, *, contracting=True, noise=1e-5, target="CF_z"):
    return RunVerdict(
        run=run,
        n_star=n_star,
        contracting=contracting,
        max_noise=noise,
        noise_target="CF_y",
        passes={},
        binding_beat=(n_star or 8),
        binding_target=target,
    )


def test_slowest_run_sets_the_count():
    d = decide_beat_count(
        [_verdict("a", 5), _verdict("b", 6, target="CF_my"), _verdict("c", 6)]
    )
    assert d.action == "regenerate"
    assert d.n_star == 6
    assert d.run in {"b", "c"} and d.target in TARGETS and d.beat == 6


def test_stop_takes_precedence():
    d = decide_beat_count([_verdict("a", None), _verdict("b", 8)])
    assert d.action == "stop"
    assert d.n_star is None
    assert d.run == "a"


def test_not_contracting_stops():
    d = decide_beat_count([_verdict("a", 6, contracting=False), _verdict("b", 6)])
    assert d.action == "stop" and d.run == "a"


def test_long_count_needs_cost_approval():
    d = decide_beat_count([_verdict("a", 6), _verdict("b", 7), _verdict("c", 7)])
    assert d.action == "regenerate_needs_cost_approval"
    assert d.n_star == 7


def test_too_much_noise_stops():
    d = decide_beat_count([_verdict("a", 6, noise=9e-4), _verdict("b", 6)])
    assert d.action == "stop"
    assert d.run == "a" and d.target == "CF_y"


def test_noise_exactly_at_max_noise_is_accepted():
    d = decide_beat_count([_verdict("a", 6, noise=MAX_NOISE)])
    assert d.action == "regenerate"
