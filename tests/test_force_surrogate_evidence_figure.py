"""CPU-tier, cluster-free tests for force_surrogate.evidence_figure (TDD, PR6).

Cluster-free (roadmap CC-2): every test runs on the CPU-only CI runner with tiny synthetic
predictions + metrics fixtures — no RunAI, no GPU, no plotfiles, no ``train`` group. Figure
structure is asserted via the Matplotlib object model, never pixels.

Each test cites the ``force-surrogate`` spec scenario it verifies (change
``add-force-surrogate-evidence-figure``).
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import mosquito_cfd.force_surrogate as fsurr
from mosquito_cfd.force_surrogate import (
    CFD_SECONDS_PER_WINGBEAT,
    MOMENT_PANEL,
    PANEL_COEFFICIENTS,
    build_caption,
    build_figure,
    compute_speedup,
    format_metric,
    generate_evidence_figure,
    lift_coefficient_dickinson,
    panel_annotation,
    parse_config_name,
    sane_dickinson_cf_z,
)
from mosquito_cfd.force_surrogate.constants import CHORD, R_GYRATION, SPAN

TARGETS = ("CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz")


def _toy_predictions(configs=("s35_f085_p45", "s55_f115_p45"), n=8) -> pd.DataFrame:
    """A tiny synthetic holdout-predictions frame with the committed schema (no `split` col)."""
    frames = []
    for cfg in configs:
        kin = parse_config_name(cfg)
        phase = np.linspace(0.0, 1.0, n, endpoint=False)
        time = 1.0 + phase / kin.f_star
        row = {"config_name": cfg, "time": time, "phase": phase, "wingbeat": 1}
        for t in TARGETS:
            # deterministic, distinct per target/config; pred ~ true + small offset
            base = 0.3 * math.cos(TARGETS.index(t)) + 0.1 * kin.f_star
            true = base + 0.05 * np.sin(2 * np.pi * phase)
            row[f"{t}_true"] = true
            row[f"{t}_pred"] = true + 0.01
        frames.append(pd.DataFrame(row))
    return pd.concat(frames, ignore_index=True)


# Distinct per target so a test can tell which block a printed number came from.
_POINTWISE = {
    "CF_x": (0.9981, 0.041),
    "CF_y": (0.9912, 0.012),
    "CF_z": (0.9993, 0.087),
    "CF_mx": (0.9977, 0.023),
    "CF_my": (0.9985, 0.034),
    "CF_mz": (0.9988, 0.056),
}
# (committed skill, seed-sweep min, seed-sweep max, phase-only baseline pointwise R²)
_SKILL = {
    "CF_x": (0.9876, 0.9876, 0.9921, 0.9546),
    "CF_y": (0.9611, 0.9534, 0.9660, 0.9732),
    "CF_z": (0.9834, 0.9801, 0.9850, 0.8968),
    "CF_mx": (0.9721, 0.9688, 0.9760, 0.9128),
    "CF_my": (0.9773, 0.9702, 0.9795, 0.9441),
    "CF_mz": (0.9852, 0.9811, 0.9877, 0.9614),
}
# Config-resolved R²: collision-proof literals that must never reach the caption.
_CONFIG_R2 = {
    "CF_x": -7.123,
    "CF_y": 0.4567,
    "CF_z": -6.789,
    "CF_mx": 0.3456,
    "CF_my": -5.678,
    "CF_mz": 0.2345,
}
_CONFIG_R2_LITERALS = ("7.123", "0.4567", "0.457", "6.789", "0.3456", "5.678", "0.2345")


def _toy_metrics(*, seeds=(1234, 1235, 1236, 1237, 1238)) -> dict:
    """A tiny metrics dict mirroring the committed metrics.json structure."""
    return {
        "per_target": {
            t: {"rmse": rmse, "mae": 0.03, "r2": r2}
            for t, (r2, rmse) in _POINTWISE.items()
        },
        "aggregate": {"rmse": 0.05, "mae": 0.035, "r2": 0.985},
        "config_resolved": {
            t: {"config_mean_r2": v, "within_config_variance_fraction": 0.99}
            for t, v in _CONFIG_R2.items()
        },
        "phase_baseline_skill": {
            "phase_baseline": {"kind": "phase_only_periodic_interpolation"},
            "per_target": {
                t: {"skill": s, "phase_baseline_rmse": 0.4, "phase_baseline_r2": b}
                for t, (s, _, _, b) in _SKILL.items()
            },
        },
        "seed_sweep": {
            "primary_seed": seeds[0],
            "seeds": list(seeds),
            "runs": [],
            "range": {
                t: {"skill": {"min": lo, "max": hi}}
                for t, (_, lo, hi, _) in _SKILL.items()
            },
        },
        "inference": {
            "latency_ms": 0.232,
            "throughput_rows_per_s": 5.17e7,
            "basis": "mean single-row latency over 200 iters; mean batched throughput "
            "over 20 passes of 12535 rows on cuda; cuda-synchronized",
        },
        "reproducibility": {"seeds": {"global": seeds[0]}},
    }


# --- Fixtures match the committed PR5 inputs (scenario: schema drift guard) ----------------

REPO = Path(__file__).resolve().parents[1]
COMMITTED_PRED = (
    REPO / "examples" / "prelim_sweep" / "surrogate" / "holdout_predictions.parquet"
)
COMMITTED_METRICS = REPO / "examples" / "prelim_sweep" / "surrogate" / "metrics.json"


def test_fixture_matches_committed_pr5_schema():
    """Scenario: fixtures match the committed PR5 inputs (no `split` column)."""
    committed = pd.read_parquet(COMMITTED_PRED)
    toy = _toy_predictions()
    assert set(toy.columns) == set(committed.columns)
    assert "split" not in toy.columns and "split" not in committed.columns


@pytest.mark.xfail(strict=True, reason="#127: regenerated in C6/C7")
def test_fixture_matches_committed_metrics_schema():
    """Scenario: the key paths the figure reads exist in the committed metrics.json and in the
    toy fixture alike (schema drift guard)."""
    committed = json.loads(COMMITTED_METRICS.read_text())
    for metrics in (committed, _toy_metrics()):
        sweep = metrics["seed_sweep"]
        assert {"primary_seed", "seeds", "range"} <= set(sweep)
        for c in TARGETS:
            skill = metrics["phase_baseline_skill"]["per_target"][c]
            assert {"skill", "phase_baseline_r2"} <= set(skill)
            assert {"r2", "rmse"} <= set(metrics["per_target"][c])
            rng = sweep["range"][c]["skill"]
            assert rng is None or {"min", "max"} <= set(rng)
        assert "latency_ms" in metrics["inference"]
        assert "throughput_rows_per_s" in metrics["inference"]


# --- parse_config_name --------------------------------------------------------------------


def test_parse_config_name_known():
    """Scenario: config_name parses to kinematic parameters."""
    kin = parse_config_name("s45_f115_p60")
    assert kin.phi_amp_deg == 45.0
    assert kin.f_star == 1.15
    assert kin.pitch_amp_deg == 60.0
    # decimal convention is load-bearing
    assert parse_config_name("s35_f085_p45").f_star == 0.85


@pytest.mark.parametrize(
    "bad", ["s45_f115", "x45_f115_p60", "sXX_f115_p60", "s45_f115_p60_extra"]
)
def test_parse_config_name_rejects_malformed(bad):
    """Scenario: config_name parses to kinematic parameters (negative cases)."""
    with pytest.raises(ValueError):
        parse_config_name(bad)


# --- Sane-Dickinson baseline --------------------------------------------------------------


def test_lift_coefficient_dickinson_known_answer():
    """Scenario: Baseline coefficient matches the documented formula on known inputs (C_L)."""
    # canonical Dickinson 1999: C_L = 0.225 + 1.58 sin(2.13 alpha_deg - 7.2deg)
    for alpha in (0.0, 45.0, 60.0):
        expected = 0.225 + 1.58 * math.sin(math.radians(2.13 * alpha - 7.2))
        np.testing.assert_allclose(
            lift_coefficient_dickinson(alpha), expected, rtol=1e-9
        )


def test_sane_dickinson_cf_z_known_answer():
    """Scenario: Baseline coefficient matches the documented formula on known inputs."""
    phase = np.array([0.0, 0.1, 0.25, 0.5])
    f_star, phi, pitch = 1.15, 45.0, 60.0
    u_ratio = np.cos(2 * np.pi * phase)
    alpha_eff = pitch * np.abs(np.cos(2 * np.pi * phase))
    expected = u_ratio**2 * lift_coefficient_dickinson(alpha_eff)
    got = sane_dickinson_cf_z(
        phase, f_star=f_star, phi_amp_deg=phi, pitch_amp_deg=pitch
    )
    np.testing.assert_allclose(got, expected, rtol=1e-9)


def test_sane_dickinson_uses_cc3_helper(monkeypatch):
    """Scenario: Baseline normalizes through the CC-3 single-source helper."""
    captured = {"n": 0}
    real = fsurr.compute_force_reference

    def spy(*args, **kwargs):
        captured["n"] += 1
        captured["args"] = (args, kwargs)
        return real(*args, **kwargs)

    import mosquito_cfd.force_surrogate.evidence_figure as ef

    monkeypatch.setattr(ef, "compute_force_reference", spy)
    sane_dickinson_cf_z(
        np.array([0.0, 0.5]), f_star=1.0, phi_amp_deg=45.0, pitch_amp_deg=45.0
    )
    assert captured["n"] >= 1, "baseline did not call compute_force_reference"
    # called with the parsed kinematics + the validated module geometry
    args, kwargs = captured["args"]
    allvals = list(args) + list(kwargs.values())
    assert R_GYRATION in allvals and SPAN in allvals and CHORD in allvals


def test_sane_dickinson_divides_by_helper_f_ref(monkeypatch):
    """Scenario: Baseline normalizes through the CC-3 single-source helper (sentinel f_ref)."""
    import mosquito_cfd.force_surrogate.evidence_figure as ef
    from mosquito_cfd.force_surrogate import ForceReference

    real = fsurr.compute_force_reference

    def sentinel(*args, **kwargs):
        r = real(*args, **kwargs)
        # double f_ref while keeping q_ref*area -> output must halve (proves it divides by f_ref)
        return ForceReference(
            u_ref=r.u_ref, q_ref=r.q_ref, area=r.area, f_ref=2 * r.f_ref
        )

    phase = np.array([0.0, 0.3])
    base = sane_dickinson_cf_z(phase, f_star=1.0, phi_amp_deg=45.0, pitch_amp_deg=45.0)
    monkeypatch.setattr(ef, "compute_force_reference", sentinel)
    halved = sane_dickinson_cf_z(
        phase, f_star=1.0, phi_amp_deg=45.0, pitch_amp_deg=45.0
    )
    np.testing.assert_allclose(halved, base / 2.0, rtol=1e-9)


# --- panel_annotation / value rendering / null + missing key ------------------------------


def test_panel_annotation_reads_metrics():
    """Scenario: Per-panel annotation reports skill, seed range, pointwise R² and RMSE read
    from metrics.json."""
    metrics = _toy_metrics()
    txt = panel_annotation(metrics, "CF_z")
    assert "skill 0.983" in txt  # phase_baseline_skill.per_target.CF_z.skill
    assert "(5 seeds: 0.980 to 0.985)" in txt  # seed_sweep.range.CF_z.skill
    assert "R² 0.999" in txt  # per_target.CF_z.r2 = 0.9993 (rounds to 0.999, not 1.000)
    assert "RMSE 0.087" in txt  # per_target.CF_z.rmse
    for literal in _CONFIG_R2_LITERALS:
        assert literal not in txt


@pytest.mark.parametrize(
    ("path", "value", "expected"),
    [
        (
            ("phase_baseline_skill", "per_target", "CF_z", "skill"),
            0.5123,
            "skill 0.512",
        ),
        (("seed_sweep", "range", "CF_z", "skill", "min"), 0.4321, "0.432 to 0.985"),
        (("seed_sweep", "range", "CF_z", "skill", "max"), 0.9912, "0.980 to 0.991"),
        (("per_target", "CF_z", "r2"), 0.9871, "R² 0.987"),
        (("per_target", "CF_z", "rmse"), 0.1234, "RMSE 0.123"),
    ],
    ids=["skill", "range-min", "range-max", "r2", "rmse"],
)
def test_panel_annotation_mutates_with_each_value(path, value, expected):
    """Changing any one annotated value in metrics.json changes the annotation."""
    metrics = _toy_metrics()
    node = metrics
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    assert expected in panel_annotation(metrics, "CF_z")


def test_panel_annotation_names_the_seed_count():
    """The range names how many seeds it spans; one seed says so instead of a range."""
    three = _toy_metrics(seeds=(7, 8, 9))
    assert "(3 seeds: 0.980 to 0.985)" in panel_annotation(three, "CF_z")
    one = _toy_metrics(seeds=(7,))
    txt = panel_annotation(one, "CF_z")
    assert "(single seed, no range)" in txt
    assert " to " not in txt


def test_panel_annotation_null_renders_na():
    """Scenario: a null skill renders as n/a without raising."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_z"]["skill"] = None
    metrics["seed_sweep"]["range"]["CF_z"]["skill"] = None
    txt = panel_annotation(metrics, "CF_z")
    assert "skill n/a" in txt
    assert "(5 seeds: n/a)" in txt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.9997, ">0.999"),
        (0.99949, "0.999"),
        (0.9876, "0.988"),
        (-0.150, "−0.150"),
        (-0.0004, "−4.0e-04"),
        (0.0004, "4.0e-04"),
        (0.0, "0.000"),
        (-0.0, "0.000"),
        (-7.5, "−7.500"),
        (None, "n/a"),
        (float("nan"), "n/a"),
    ],
)
def test_metric_values_render_honestly(value, expected):
    """Scenario: null, near-perfect, near-zero and negative values render honestly."""
    assert format_metric(value) == expected


def test_annotation_renders_near_perfect_negative_and_tiny_values():
    """Panel text: >0.999 for skill and R², a 'lo to hi' range with U+2212, tiny in sci form."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_x"]["skill"] = 0.9997
    metrics["per_target"]["CF_x"]["r2"] = 0.9996
    metrics["seed_sweep"]["range"]["CF_x"]["skill"] = {"min": -0.150, "max": 0.992}
    txt = panel_annotation(metrics, "CF_x")
    assert "skill >0.999" in txt and "R² >0.999" in txt
    assert "1.000" not in txt
    assert "−0.150 to 0.992" in txt
    metrics["phase_baseline_skill"]["per_target"]["CF_x"]["skill"] = -0.0004
    txt = panel_annotation(metrics, "CF_x")
    assert "skill −4.0e-04" in txt and "0.000" not in txt


@pytest.mark.parametrize(
    "path",
    [
        ("phase_baseline_skill",),
        ("phase_baseline_skill", "per_target", "CF_z"),
        ("seed_sweep",),
        ("seed_sweep", "range", "CF_z"),
        ("per_target", "CF_z"),
    ],
    ids=["skill-block", "skill-entry", "sweep-block", "sweep-entry", "per-target"],
)
def test_panel_annotation_missing_key_raises(path):
    """Scenario: A required metrics key or panel coefficient is missing."""
    metrics = _toy_metrics()
    node = metrics
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    with pytest.raises(KeyError, match=path[-1]):
        panel_annotation(metrics, "CF_z")


# --- compute_speedup ----------------------------------------------------------------------


def test_compute_speedup_throughput_headline():
    """Scenario: The >1,000× headline is the batched-throughput speedup, computed not hard-coded."""
    inf = _toy_metrics()["inference"]
    sp = compute_speedup(inf, rows_per_wingbeat=2000)
    expected = 5.17e7 / (2000 / CFD_SECONDS_PER_WINGBEAT)
    np.testing.assert_allclose(sp["throughput_speedup"], expected, rtol=1e-9)
    assert sp["throughput_speedup"] > 1000
    assert sp["batch_size"] == 12535
    # parallelism factor decomposes the headline
    np.testing.assert_allclose(
        sp["parallelism_factor"],
        sp["throughput_speedup"] / sp["latency_speedup"],
        rtol=1e-9,
    )


def test_compute_speedup_latency_floor_not_over_1000():
    """Scenario: The single-row latency speedup is reported honestly and not conflated."""
    inf = _toy_metrics()["inference"]
    sp = compute_speedup(inf, rows_per_wingbeat=2000)
    expected = (CFD_SECONDS_PER_WINGBEAT / 2000) / (0.232 / 1000.0)
    np.testing.assert_allclose(sp["latency_speedup"], expected, rtol=1e-9)
    assert sp["latency_speedup"] < 1000
    assert (
        abs(sp["latency_speedup"] - 310.0) < 5
    )  # toy fixture's 0.232 ms, not a corpus number


def test_rows_per_wingbeat_is_actual_parquet_counts(tmp_path):
    """Scenario: rows_per_wingbeat is the per-config actual parquet count, not a constant."""
    # toy parquet: distinct row counts per config so a constant would be wrong
    a = _toy_predictions(configs=("s35_f085_p45",), n=5)
    b = _toy_predictions(configs=("s55_f115_p45",), n=7)
    pred = tmp_path / "p.parquet"
    pd.concat([a, b], ignore_index=True).to_parquet(pred)
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    out = tmp_path / "figs"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    fig_metrics = json.loads((out / "evidence_figure_metrics.json").read_text())
    assert fig_metrics["rows_per_wingbeat_per_config"] == {
        "s35_f085_p45": 5,
        "s55_f115_p45": 7,
    }


# --- build_caption ------------------------------------------------------------------------


_TOY_BASELINE = {"overshoot_factor": 3.2, "baseline_rmse_cf_z": 0.98}


def _caption(metrics):
    sp = compute_speedup(metrics["inference"], rows_per_wingbeat=2000)
    return build_caption(metrics, sp, _TOY_BASELINE)


def test_build_caption_discloses_everything():
    """Scenario: Caption defines skill and shows why pointwise R² overstates it."""
    cap = _caption(_toy_metrics())
    low = cap.lower()
    assert "seed 1234" in cap and "5 seeds" in cap  # plotted seed + seed count
    assert "1 − mse/mse₀" in low and "phase-only baseline" in low  # skill defined
    # the phase-only baseline's own pointwise R² for the three panel axes
    assert "0.955/0.897/0.944" in cap
    assert "waveform" in low and "amplitude and shape" in low  # skill rewards more
    assert "cycle-mean r²: readme" in low
    assert "skill ≥ 0.953 for all six targets across 5 seeds" in low  # the skill floor
    # off-panel moments excluded, with their skill (plotted seed + range)
    assert "cf_mx 0.972 (5 seeds: 0.969 to 0.976)" in low
    assert "cf_mz 0.985 (5 seeds: 0.981 to 0.988)" in low
    assert "coarse" in low  # coarse-grid pipeline-readiness framing
    assert "2.4" not in cap  # the false ~2.4x diffused-IB claim is retired
    assert "not validated" in low or "validated aerodynamics" in low
    # quasi-steady reference: disclosed as a ratio, NOT presented as a quantitative baseline
    assert (
        "quasi-steady reference" in low and "not used as a quantitative baseline" in low
    )
    assert "3.2x" in low or "3.2" in cap  # the QS-vs-CFD RMS ratio (toy = 3.2)
    assert "uncalibrated" in low  # the quasi-steady reference is unfitted
    assert "readme" in low  # pointer
    assert ">1,000" in cap or ">1000" in cap


def test_build_caption_never_prints_config_resolved_r2():
    """Scenario: no configuration-resolved R² value is present in the caption."""
    cap = _caption(_toy_metrics())
    for literal in _CONFIG_R2_LITERALS:
        assert literal not in cap
    assert "config-resolved" not in cap.lower()


def test_build_caption_headline_does_not_repeat_panel_numbers():
    """The per-axis skill/R²/RMSE live on the panels; the headline carries the definition."""
    headline = _caption(_toy_metrics()).split("\n")[0]
    for value in ("0.988", "0.983", "0.977", "0.041", "0.087", "0.034"):
        assert value not in headline


def test_build_caption_off_panel_claims_are_data_driven_not_hardcoded():
    """Scenario: the off-panel CF_mx/CF_mz disclosure is read from metrics.json at call time,
    so a corpus in which an off-panel moment outscores the headline is visible."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_mx"]["skill"] = 0.9912
    metrics["seed_sweep"]["range"]["CF_mz"]["skill"] = {"min": 0.7123, "max": 0.8456}
    low = _caption(metrics).lower()
    assert "cf_mx 0.991" in low
    assert "cf_mz 0.985 (5 seeds: 0.712 to 0.846)" in low
    assert "no between-config signal" not in low
    assert "waveform fraction" not in low  # no fixed reason asserted for the exclusion


def test_build_caption_skill_floor_follows_the_minimum_not_a_named_target():
    """The floor is the minimum over all six targets' seed minima; no target is ranked."""
    metrics = _toy_metrics()
    metrics["seed_sweep"]["range"]["CF_mz"]["skill"] = {"min": 0.9101, "max": 0.99}
    low = _caption(metrics).lower()
    assert "skill ≥ 0.910 for all six targets" in low
    assert "weakest" not in low


def test_build_caption_flags_targets_below_the_phase_only_baseline_subordinate():
    """Scenario: a target below the phase-only baseline is flagged, subordinate, and a
    minimum of exactly 0 is not called below it."""
    metrics = _toy_metrics()
    metrics["seed_sweep"]["range"]["CF_x"]["skill"] = {"min": -0.25, "max": 0.99}
    metrics["seed_sweep"]["range"]["CF_mz"]["skill"] = {"min": -0.0004, "max": 0.99}
    metrics["seed_sweep"]["range"]["CF_y"]["skill"] = {"min": 0.0, "max": 0.99}
    cap = _caption(metrics)
    headline, caveats = cap.split("\n")[:2]
    assert "below the phase-only baseline" in caveats.lower()
    assert "CF_x (min skill −0.250)" in caveats
    assert "CF_mz (min skill −4.0e-04)" in caveats
    assert "CF_y (min" not in caveats  # exactly 0 is not below the phase-only baseline
    assert "below the phase-only baseline" not in headline.lower()
    assert "for all six targets" not in cap


def test_build_caption_null_values_render_without_crashing():
    """Scenario: null skills in the caption render as n/a; the floor skips nulls."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_mz"]["skill"] = None
    metrics["phase_baseline_skill"]["per_target"]["CF_z"]["phase_baseline_r2"] = None
    metrics["seed_sweep"]["range"]["CF_y"]["skill"] = None
    cap = _caption(metrics)
    low = cap.lower()
    assert "cf_mz n/a" in low
    assert "0.955/n/a/0.944" in cap
    # CF_y's 0.953 minimum is null now; the floor is the next-lowest minimum (CF_mx 0.969)
    assert "skill ≥ 0.969 for the 5 targets with a defined skill across 5 seeds" in low


def test_build_caption_all_null_skill_is_undefined_not_an_error():
    """Every seed-sweep minimum null -> the caption says skill is undefined."""
    metrics = _toy_metrics()
    for entry in metrics["seed_sweep"]["range"].values():
        entry["skill"] = None
    assert "skill is undefined for every target" in _caption(metrics).lower()


def test_build_caption_renders_near_perfect_phase_baseline_r2_as_above_0_999():
    """A value that would print 1.000 prints >0.999 (the caption's phase-only baseline R²)."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_x"]["phase_baseline_r2"] = 0.99989
    cap = _caption(metrics)
    assert ">0.999/0.897/0.944" in cap
    assert "1.000" not in cap


def test_build_caption_mutates_with_metrics():
    """Scenario: Caption numbers are read from metrics, never hard-coded."""
    metrics = _toy_metrics()
    metrics["phase_baseline_skill"]["per_target"]["CF_my"]["phase_baseline_r2"] = 0.4242
    assert "0.955/0.897/0.424" in _caption(metrics)


# --- build_figure (Matplotlib object model, no pixels) ------------------------------------


def _scatter_axes(fig):
    return [ax for ax in fig.axes if ax.collections or ax.lines]


def test_build_figure_three_panels():
    """Scenario: Figure has three predicted-vs-CFD panels for CF_x, CF_z, CF_my."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    axes = _scatter_axes(fig)
    assert len(axes) == 3
    titles = " ".join(ax.get_title() for ax in axes).lower()
    assert "cf_x" in titles and "cf_z" in titles
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_build_figure_moment_panel_is_my_not_pitch():
    """Scenario: Moment panel is CF_my labeled as a component, not "pitch moment"."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    labels = " ".join(ax.get_title() for ax in fig.axes)
    assert MOMENT_PANEL == "CF_my"
    assert "M_y" in labels and "moment" in labels.lower()
    assert "pitch moment" not in labels.lower()
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_build_figure_off_axis_moments_excluded():
    """Scenario: The off-axis (waveform-dominated) moments are not the headline."""
    assert PANEL_COEFFICIENTS == ("CF_x", "CF_z", "CF_my")
    fig = build_figure(_toy_predictions(), _toy_metrics())
    titles = " ".join(ax.get_title() for ax in fig.axes).lower()
    assert "cf_mx" not in titles and "cf_mz" not in titles
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_baseline_not_plotted_anywhere():
    """Scenario: the Sane-Dickinson baseline is a computed reference, not drawn on any panel."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    # no axis carries a 'Sane-Dickinson'/'baseline' series (poor fit; reference-only)
    for ax in fig.axes:
        labels = [t.lower() for t in ax.get_legend_handles_labels()[1]]
        assert not any("dickinson" in lbl or "baseline" in lbl for lbl in labels)
    # ...and nothing beyond the per-config points and the 1:1 line: no curve of any kind
    n_configs = _toy_predictions()["config_name"].nunique()
    for ax in _scatter_axes(fig):
        assert len(ax.lines) == 1  # the 1:1 reference only
        assert len(ax.collections) == n_configs  # one scatter series per config
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_config_color_legend_present():
    """The figure has a shared legend mapping each held-out config to its color."""
    configs = sorted(_toy_predictions()["config_name"].unique())
    fig = build_figure(_toy_predictions(), _toy_metrics())
    legend_labels = [t.get_text() for lg in fig.legends for t in lg.get_texts()]
    for cfg in configs:
        assert cfg in legend_labels
    import matplotlib.pyplot as plt

    plt.close(fig)


def _caption_text(metrics: dict) -> str:
    import matplotlib.pyplot as plt

    fig = build_figure(_toy_predictions(), metrics)
    text = " ".join(t.get_text() for t in fig.texts)
    plt.close(fig)
    return text


def test_build_figure_caption_names_its_seed_and_seed_count():
    """Scenario: the caption names the plotted seed and the seed count."""
    text = _caption_text(_toy_metrics(seeds=(4321, 1, 2)))
    assert "seed 4321" in text and "3 seeds" in text


def test_build_figure_caption_says_single_seed_no_range():
    """With one seed the caption states "single seed, no range", never an implied spread."""
    text = _caption_text(_toy_metrics(seeds=(4321,)))
    assert "seed 4321" in text
    assert "single seed, no range" in text
    assert "seeds:" not in text and "across 1 seeds" not in text


def test_build_figure_rejects_metrics_without_a_seed_sweep():
    """A metrics.json with no seed_sweep block raises rather than captioning a default seed."""
    metrics = _toy_metrics()
    del metrics["seed_sweep"]
    with pytest.raises(KeyError, match="seed_sweep"):
        _caption_text(metrics)


def test_build_figure_caption_states_the_lab_frame_moment_caveat():
    """Scenario: Moment panel ... the caption states the moment is a lab-frame component and
    that the wing-frame conversion is not currently tracked (issue #1 is closed)."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    alltext = " ".join(t.get_text() for t in fig.texts).lower()
    assert "lab-frame m_y component" in alltext
    assert "not currently tracked" in alltext
    import matplotlib.pyplot as plt

    plt.close(fig)


# --- generate_evidence_figure: artifacts + provenance -------------------------------------


def _write_inputs(tmp_path):
    pred = tmp_path / "holdout_predictions.parquet"
    _toy_predictions().to_parquet(pred)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    return pred, metrics


DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "a" * 64
TS = "2026-06-23T00:00:00+00:00"


def test_generate_writes_three_artifacts(tmp_path):
    """Scenario: All three artifacts write and re-load with the documented content."""
    pred, metrics = _write_inputs(tmp_path)
    out = tmp_path / "figures"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    assert (out / "evidence_figure.png").exists()
    fig_metrics = json.loads((out / "evidence_figure_metrics.json").read_text())
    for c in PANEL_COEFFICIENTS:
        assert c in fig_metrics["surrogate_rmse"]
    qs = fig_metrics["quasi_steady_reference"]
    assert "baseline_rmse_cf_z" in qs and qs["overshoot_factor"] > 1
    assert (
        "speedup" in fig_metrics and fig_metrics["speedup"]["throughput_speedup"] > 1000
    )
    assert fig_metrics["speedup"]["batch_size"] == 12535
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["timestamp"] == TS
    assert "sha256:" in meta["docker_image"]


def test_sidecar_records_skill_for_all_six_targets_and_no_config_r2(tmp_path):
    """Scenario: the sidecar carries primary_seed, n_seeds, six-target skill / pointwise R² /
    phase-only baseline R², the skill floor -- equal to metrics.json -- and no config_mean_r2."""
    pred, metrics_path = _write_inputs(tmp_path)
    out = tmp_path / "figures"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics_path,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    raw = (out / "evidence_figure_metrics.json").read_text(encoding="utf-8")
    fig_metrics = json.loads(raw)
    metrics = _toy_metrics()
    assert fig_metrics["primary_seed"] == 1234
    assert fig_metrics["n_seeds"] == 5
    for c in TARGETS:
        skill = metrics["phase_baseline_skill"]["per_target"][c]
        rng = metrics["seed_sweep"]["range"][c]["skill"]
        assert fig_metrics["skill"][c] == {
            "committed": skill["skill"],
            "min": rng["min"],
            "max": rng["max"],
        }
        assert fig_metrics["pointwise_r2"][c] == metrics["per_target"][c]["r2"]
        assert (
            fig_metrics["phase_baseline_pointwise_r2"][c] == skill["phase_baseline_r2"]
        )
    assert fig_metrics["skill_floor"] == {
        "value": 0.9534,
        "targets_below_phase_baseline": [],
    }
    assert "config_mean_r2" not in raw
    for literal in _CONFIG_R2_LITERALS:
        assert literal not in raw


def test_sidecar_skill_floor_lists_targets_below_the_phase_only_baseline(tmp_path):
    """The sidecar's skill_floor names the targets whose seed minimum is below zero."""
    m = _toy_metrics()
    # CF_mz is the lower minimum: the list is in target order, not ranked by value
    m["seed_sweep"]["range"]["CF_mz"]["skill"] = {"min": -0.5, "max": 0.99}
    m["seed_sweep"]["range"]["CF_x"]["skill"] = {"min": -0.25, "max": 0.99}
    m["seed_sweep"]["range"]["CF_y"]["skill"] = {"min": 0.0, "max": 0.99}
    pred = tmp_path / "p.parquet"
    _toy_predictions().to_parquet(pred)
    metrics_path = tmp_path / "m.json"
    metrics_path.write_text(json.dumps(m))
    out = tmp_path / "figures"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics_path,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    fig_metrics = json.loads((out / "evidence_figure_metrics.json").read_text())
    assert fig_metrics["skill_floor"] == {
        "value": -0.5,
        "targets_below_phase_baseline": ["CF_x", "CF_mz"],
    }


def test_every_number_in_the_caption_is_in_the_sidecar(tmp_path):
    """Scenario: Every number in the caption is in the sidecar (issue #116)."""
    pred, metrics_path = _write_inputs(tmp_path)
    out = tmp_path / "figures"
    fig_metrics = generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics_path,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    cap = _caption(_toy_metrics())
    assert f"seed {fig_metrics['primary_seed']}" in cap
    assert f"{fig_metrics['n_seeds']} seeds" in cap
    b = fig_metrics["phase_baseline_pointwise_r2"]
    assert f"{b['CF_x']:.3f}/{b['CF_z']:.3f}/{b['CF_my']:.3f}" in cap
    assert f"skill ≥ {fig_metrics['skill_floor']['value']:.3f}" in cap.lower()
    for c in ("CF_mx", "CF_mz"):
        s = fig_metrics["skill"][c]
        assert (
            f"{c} {s['committed']:.3f} (5 seeds: {s['min']:.3f} to {s['max']:.3f})"
            in cap
        )


def test_figure_run_metadata_seeds_come_from_metrics_json(tmp_path):
    """Scenario: provenance records seeds equal to the metrics.json seed_sweep."""
    pred = tmp_path / "p.parquet"
    _toy_predictions().to_parquet(pred)
    metrics_path = tmp_path / "m.json"
    metrics_path.write_text(json.dumps(_toy_metrics(seeds=(9, 3, 5))))
    out = tmp_path / "figures"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics_path,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["seeds"] == {"global": 9, "sweep": [3, 5]}


def test_generate_takes_no_seed_argument():
    """The figure's seeds are read from metrics.json, never passed in (D7)."""
    import inspect

    assert "seeds" not in inspect.signature(generate_evidence_figure).parameters


def test_generate_rejects_mutable_tag(tmp_path):
    """Scenario: Mutable image tag is rejected."""
    pred, metrics = _write_inputs(tmp_path)
    out = tmp_path / "figures"
    with pytest.raises(ValueError):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest="ghcr.io/talmolab/mosquito-cfd:latest",
            timestamp=TS,
        )
    assert not (out / "evidence_figure.png").exists()


def test_generate_dpi_at_least_200(tmp_path, monkeypatch):
    """Scenario: ≥200 dpi (asserted via the savefig dpi kwarg, not a PNG re-read)."""
    import matplotlib.figure

    captured = {}
    real = matplotlib.figure.Figure.savefig

    def spy(self, *a, **k):
        captured["dpi"] = k.get("dpi")
        return real(self, *a, **k)

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", spy)
    pred, metrics = _write_inputs(tmp_path)
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics,
        out_dir=tmp_path / "figures",
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    assert captured["dpi"] is not None and captured["dpi"] >= 200


def test_generate_json_sidecars_are_lf(tmp_path):
    """Scenario: JSON sidecars are written LF-newline UTF-8."""
    pred, metrics = _write_inputs(tmp_path)
    out = tmp_path / "figures"
    generate_evidence_figure(
        predictions_path=pred,
        metrics_path=metrics,
        out_dir=out,
        docker_image_digest=DIGEST,
        timestamp=TS,
    )
    for name in ("evidence_figure_metrics.json", "run_metadata.json"):
        assert b"\r\n" not in (out / name).read_bytes(), name


def test_generate_rejects_degenerate_inputs(tmp_path):
    """Scenario: Degenerate prediction sets are rejected, not silently mis-plotted."""
    out = tmp_path / "figures"
    # single config
    single = tmp_path / "single.parquet"
    _toy_predictions(configs=("s35_f085_p45",)).to_parquet(single)
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    with pytest.raises(ValueError):
        generate_evidence_figure(
            predictions_path=single,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    # empty
    empty = tmp_path / "empty.parquet"
    _toy_predictions().iloc[:0].to_parquet(empty)
    with pytest.raises(ValueError):
        generate_evidence_figure(
            predictions_path=empty,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )


def test_generate_requires_only_committed_artifacts():
    """Scenario: Generator requires only the committed surrogate artifacts (force-only CC-6)."""
    import inspect

    sig = inspect.signature(generate_evidence_figure)
    params = set(sig.parameters)
    assert "predictions_path" in params and "metrics_path" in params
    # no plotfile/field path accepted
    assert not any("plot" in p or "field" in p or "plt" in p for p in params)


def test_only_holdout_config_points_plotted():
    """Scenario: Only held-out configurations are plotted (point count == row count)."""
    pred = _toy_predictions()
    fig = build_figure(pred, _toy_metrics())
    axes = _scatter_axes(fig)
    for ax in axes:
        # every panel plots exactly the surrogate points (one scatter series per config)
        n_points = sum(c.get_offsets().shape[0] for c in ax.collections)
        assert n_points == len(pred)
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_missing_prediction_column_raises_no_partial_artifact(tmp_path):
    """Scenario: A required panel CF_* column is missing -> clear error, no artifact written."""
    bad = _toy_predictions().drop(columns=["CF_z_pred"])
    pred = tmp_path / "bad.parquet"
    bad.to_parquet(pred)
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    out = tmp_path / "figs"
    with pytest.raises(ValueError, match="CF_z_pred"):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    # no partial artifact set of any kind
    assert not (out / "evidence_figure.png").exists()
    assert not (out / "evidence_figure_metrics.json").exists()
    assert not (out / "run_metadata.json").exists()


def test_nonfinite_coefficient_rejected_no_artifact(tmp_path):
    """Non-finite CF_* values are rejected before any write (no silently-wrong figure)."""
    bad = _toy_predictions()
    bad.loc[0, "CF_z_true"] = np.nan
    pred = tmp_path / "nan.parquet"
    bad.to_parquet(pred)
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    out = tmp_path / "figs"
    with pytest.raises(ValueError, match="non-finite"):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (out / "evidence_figure.png").exists()


def test_non_object_metrics_rejected(tmp_path):
    """A metrics.json that is not a JSON object raises a clear ValueError (not TypeError)."""
    pred, _ = _write_inputs(tmp_path)
    metrics = tmp_path / "scalar.json"
    metrics.write_text("42")
    out = tmp_path / "figs"
    with pytest.raises(ValueError, match="must be a JSON object"):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not (out / "evidence_figure.png").exists()


@pytest.mark.parametrize(
    "key", ["inference", "phase_baseline_skill", "seed_sweep", "per_target"]
)
def test_missing_metrics_key_leaves_no_partial_artifact(tmp_path, key):
    """A metrics.json missing a required key raises and writes NO partial artifact set."""
    pred, _ = _write_inputs(tmp_path)
    metrics = tmp_path / "bad_metrics.json"
    m = _toy_metrics()
    del m[key]
    metrics.write_text(json.dumps(m))
    out = tmp_path / "figs"
    with pytest.raises((KeyError, ValueError)):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    # no orphan PNG / sidecar left behind
    assert not (out / "evidence_figure.png").exists()
    assert not (out / "evidence_figure_metrics.json").exists()
    assert not (out / "run_metadata.json").exists()


def test_generate_degenerate_leaves_no_artifact(tmp_path):
    """Degenerate inputs are rejected before any artifact is written."""
    single = tmp_path / "single.parquet"
    _toy_predictions(configs=("s35_f085_p45",)).to_parquet(single)
    metrics = tmp_path / "m.json"
    metrics.write_text(json.dumps(_toy_metrics()))
    out = tmp_path / "figs"
    with pytest.raises(ValueError):
        generate_evidence_figure(
            predictions_path=single,
            metrics_path=metrics,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not out.exists() or not (out / "evidence_figure.png").exists()


# --- CLI driver ---------------------------------------------------------------------------


def _load_cli():
    import importlib.util

    path = REPO / "scripts" / "make_evidence_figure.py"
    spec = importlib.util.spec_from_file_location(
        "make_evidence_figure_under_test", path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_delegates_to_library(monkeypatch):
    """The thin CLI delegates parsed args to the tested library entrypoint."""
    cli = _load_cli()
    captured = {}

    def fake_generate(**kwargs):
        captured.update(kwargs)
        return {}

    monkeypatch.setattr(cli, "generate_evidence_figure", fake_generate)
    rc = cli.main(
        [
            "--predictions",
            "p.parquet",
            "--metrics",
            "m.json",
            "--out-dir",
            "figs",
            "--docker-digest",
            DIGEST,
            "--timestamp",
            TS,
        ]
    )
    assert rc == 0
    assert Path(captured["predictions_path"]).name == "p.parquet"
    assert Path(captured["metrics_path"]).name == "m.json"
    assert captured["docker_image_digest"] == DIGEST
    assert captured["timestamp"] == TS
    assert "seeds" not in captured  # read from metrics.json, never a CLI flag
    with pytest.raises(SystemExit):
        cli.main(
            [
                "--predictions",
                "p.parquet",
                "--metrics",
                "m.json",
                "--out-dir",
                "figs",
                "--docker-digest",
                DIGEST,
                "--timestamp",
                TS,
                "--seed",
                "1234",
            ]
        )


# --- README full-disclosure home (honesty test-enforced off the PNG) ----------------------


def test_readme_carries_full_disclosures():
    """Scenario: On-figure caption is compact; full disclosures live in the README."""
    readme = (REPO / "examples" / "prelim_sweep" / "README.md").read_text(
        encoding="utf-8"
    )
    low = readme.lower()
    # the full disclosure set the compact caption only points to
    assert "**lab-frame** components about the hinge" in low  # the axis caveat
    assert (
        "not currently tracked" in low
    )  # ...and that the wing-frame conversion is deferred
    assert "cf_mx" in low and "cf_mz" in low  # off-axis exclusion
    assert "symmetric-rotation" in low
    assert "stroke-plane-normal" in low and "lab-z" in low  # projection caveat
    assert "zero-parameter" in low  # fitted-vs-unfitted
    assert "not validated aerodynamics" in low or "not a validated" in low
    assert "2.4" not in readme  # the false ~2.4x diffused-IB claim is retired
    assert "batch size" in low or "batch_size" in low  # speedup decomposition
    assert "sequential" in low  # CFD rate is sequential
    # the latency floor, read from the committed sidecar so the prose moves with the artifact
    figures = REPO / "examples" / "prelim_sweep" / "figures"
    sidecar = json.loads((figures / "evidence_figure_metrics.json").read_text())
    latency = round(sidecar["speedup"]["latency_speedup"])
    assert f"~{latency}×" in readme, (
        f"README must state the latency floor as ~{latency}×"
    )


def _normalized_readme() -> str:
    text = (REPO / "examples" / "prelim_sweep" / "README.md").read_text(
        encoding="utf-8"
    )
    text = text.replace("−", "-")  # README house style writes negatives with U+2212
    return re.sub(r"([≈=])\s+", r"\1", text)


# Any CF name followed, within one line and before any other CF name, by "≈<num>" or "=<num>".
# Broad on purpose: a stale value in a slightly different form (``CF_z R² ≈0.51``,
# ``CF_my = 0.51``, a Unicode minus) is caught rather than skipped. Percentages are excluded.
_R2_NEAR_TARGET = re.compile(
    r"\b(CF_(?:mx|my|mz|x|y|z))\b`?((?:(?!CF_)[^≈=\n|]){0,60})[≈=](-?\d+\.(\d+))(?![\d%])"
)
# Historical values the README quotes on purpose (an earlier corpus), not current results.
_HISTORICAL_R2 = {("CF_x", "0.94")}
# The figure's three panels plus the two off-panel moments must each be quoted.
_QUOTED_TARGETS = ("CF_x", "CF_z", "CF_my", "CF_mx", "CF_mz")


def test_readme_config_resolved_r2_matches_committed_metrics():
    """Every config-resolved R² the README quotes equals metrics.json at its stated precision,
    and the panel and off-panel moment targets are each quoted in the canonical ``CF_c ≈v`` form
    (scenario: the CF_mx/CF_mz exclusion is stated **with** their config-resolved R²) -- so a
    retrain cannot leave an old number or an old ranking in the prose."""
    readme = _normalized_readme()
    resolved = json.loads(COMMITTED_METRICS.read_text())["config_resolved"]
    for m in _R2_NEAR_TARGET.finditer(readme):
        c, _, value, decimals = m.groups()
        if (c, value) in _HISTORICAL_R2:
            continue
        actual = resolved[c]["config_mean_r2"]
        assert abs(actual - float(value)) <= 0.5 * 10 ** -len(decimals) + 1e-12, (
            f"README quotes {m.group(0)!r}; metrics.json {c} config_mean_r2 is {actual:.4f}"
        )
    for c in _QUOTED_TARGETS:
        canonical = f"{c} ≈{resolved[c]['config_mean_r2']:.2f}"
        assert canonical in readme.replace("`", ""), f"README must quote {canonical!r}"


def test_readme_throughput_figures_match_the_committed_sidecar():
    """The README's batched-throughput and parallelism figures are the sidecar's, like the
    latency floor -- each is a single wall-clock timing sample that moves on every retrain."""
    readme = (REPO / "examples" / "prelim_sweep" / "README.md").read_text(
        encoding="utf-8"
    )
    sidecar = json.loads(
        (
            REPO
            / "examples"
            / "prelim_sweep"
            / "figures"
            / "evidence_figure_metrics.json"
        ).read_text()
    )["speedup"]
    throughput = sidecar["throughput_speedup"]
    assert 1e6 <= throughput < 1e7, (
        "update the README's ×10⁶ wording for this magnitude"
    )
    assert f"≈{throughput / 1e6:.1f}×10⁶×" in readme
    assert f"~{round(sidecar['parallelism_factor'], -1):,.0f}×" in readme


# --- Committed-figure contract (guards the committed sidecar against drift) ----------------


@pytest.mark.xfail(strict=True, reason="#127: regenerated in C6/C7")
def test_committed_figure_metrics_matches_committed_inputs():
    """The committed evidence_figure_metrics.json numbers match the committed metrics.json."""
    fig_dir = REPO / "examples" / "prelim_sweep" / "figures"
    raw = (fig_dir / "evidence_figure_metrics.json").read_text(encoding="utf-8")
    fig_metrics = json.loads(raw)
    metrics = json.loads(COMMITTED_METRICS.read_text())
    for c in PANEL_COEFFICIENTS:
        assert fig_metrics["surrogate_rmse"][c] == metrics["per_target"][c]["rmse"]
    sweep = metrics["seed_sweep"]
    assert fig_metrics["primary_seed"] == sweep["primary_seed"]
    assert fig_metrics["n_seeds"] == len(sweep["seeds"])
    for c in TARGETS:
        skill = metrics["phase_baseline_skill"]["per_target"][c]
        rng = sweep["range"][c]["skill"] or {"min": None, "max": None}
        assert fig_metrics["skill"][c] == {
            "committed": skill["skill"],
            "min": rng["min"],
            "max": rng["max"],
        }
        assert fig_metrics["pointwise_r2"][c] == metrics["per_target"][c]["r2"]
        assert (
            fig_metrics["phase_baseline_pointwise_r2"][c] == skill["phase_baseline_r2"]
        )
    minima = [
        sweep["range"][c]["skill"]["min"]
        for c in TARGETS
        if sweep["range"][c]["skill"] is not None
    ]
    assert fig_metrics["skill_floor"]["value"] == min(minima)
    assert "config_mean_r2" not in raw
    sp = fig_metrics["speedup"]
    assert sp["throughput_speedup"] > 1000
    assert sp["latency_speedup"] < 1000
    assert sp["batch_size"] == 12535
    # the uncalibrated translational QS reference is a poor fit to the coarse CFD (reference-only,
    # CC-4). Under the van Veen convention the RMS ratio is < 1 (the model under-predicts the
    # now-in-band CFD lift); the surrogate beats it by RMSE regardless.
    qs = fig_metrics["quasi_steady_reference"]
    assert qs["overshoot_factor"] > 0  # positive finite RMS ratio (van Veen: < 1)
    assert qs["baseline_rmse_cf_z"] > fig_metrics["surrogate_rmse"]["CF_z"]


def test_seed_sweep_must_list_the_primary_seed_first(tmp_path):
    """The provenance sweep is seeds[1:], so a metrics.json not listing the primary first is
    rejected rather than recorded with a wrong sweep."""
    metrics = _toy_metrics(seeds=(1235, 1234, 1236))
    metrics["seed_sweep"]["primary_seed"] = 1234
    with pytest.raises(ValueError, match="primary seed first"):
        _caption(metrics)


@pytest.mark.parametrize(
    "path",
    [
        ("phase_baseline_skill", "per_target", "CF_mx", "phase_baseline_r2"),
        ("per_target", "CF_mz", "r2"),
    ],
    ids=["phase-baseline-r2", "pointwise-r2"],
)
def test_missing_r2_key_raises_before_any_artifact(tmp_path, path):
    """A missing R² key raises a KeyError naming it, never a silent n/a or null."""
    m = _toy_metrics()
    node = m
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    pred = tmp_path / "p.parquet"
    _toy_predictions().to_parquet(pred)
    metrics_path = tmp_path / "m.json"
    metrics_path.write_text(json.dumps(m))
    out = tmp_path / "figs"
    with pytest.raises(KeyError, match=path[-1]):
        generate_evidence_figure(
            predictions_path=pred,
            metrics_path=metrics_path,
            out_dir=out,
            docker_image_digest=DIGEST,
            timestamp=TS,
        )
    assert not out.exists()
