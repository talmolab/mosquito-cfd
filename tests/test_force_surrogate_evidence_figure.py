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
    generate_evidence_figure,
    lift_coefficient_dickinson,
    panel_annotation,
    parse_config_name,
    sane_dickinson_cf_z,
)
from mosquito_cfd.force_surrogate.constants import CHORD, R_TIP, SPAN

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


def _toy_metrics(*, cf_y_r2=-3.61, cf_z_r2=0.83, null_target="CF_mz") -> dict:
    """A tiny metrics dict mirroring the committed metrics.json structure.

    ``null_target`` gets a JSON-``null`` (NaN-sentinel) config_mean_r2 to exercise rendering.
    """
    per_target = {t: {"rmse": 0.05, "mae": 0.03, "r2": 0.98} for t in TARGETS}
    config_resolved = {
        "CF_x": {"config_mean_r2": 0.94, "within_config_variance_fraction": 0.978},
        "CF_y": {"config_mean_r2": cf_y_r2, "within_config_variance_fraction": 0.999},
        "CF_z": {"config_mean_r2": cf_z_r2, "within_config_variance_fraction": 0.999},
        "CF_mx": {"config_mean_r2": 0.94, "within_config_variance_fraction": 0.999},
        "CF_my": {"config_mean_r2": 0.99, "within_config_variance_fraction": 0.442},
        "CF_mz": {"config_mean_r2": None, "within_config_variance_fraction": 0.999},
    }
    if null_target is not None:
        config_resolved[null_target]["config_mean_r2"] = None
    return {
        "per_target": per_target,
        "aggregate": {"rmse": 0.05, "mae": 0.035, "r2": 0.985},
        "config_resolved": config_resolved,
        "inference": {
            "latency_ms": 0.232,
            "throughput_rows_per_s": 5.17e7,
            "basis": "mean single-row latency over 200 iters; mean batched throughput "
            "over 20 passes of 12535 rows on cuda; cuda-synchronized",
        },
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
    metrics = json.loads(COMMITTED_METRICS.read_text())
    # the nested key paths the figure reads must exist in the committed artifact
    for c in PANEL_COEFFICIENTS:
        assert "config_mean_r2" in metrics["config_resolved"][c]
        assert "rmse" in metrics["per_target"][c]
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
    assert R_TIP in allvals and SPAN in allvals and CHORD in allvals


def test_sane_dickinson_divides_by_helper_f_ref(monkeypatch):
    """Scenario: Baseline normalizes through the CC-3 single-source helper (sentinel f_ref)."""
    import mosquito_cfd.force_surrogate.evidence_figure as ef
    from mosquito_cfd.force_surrogate import ForceReference

    real = fsurr.compute_force_reference

    def sentinel(*args, **kwargs):
        r = real(*args, **kwargs)
        # double f_ref while keeping q_tip*area -> output must halve (proves it divides by f_ref)
        return ForceReference(
            u_tip_max=r.u_tip_max, q_tip=r.q_tip, area=r.area, f_ref=2 * r.f_ref
        )

    phase = np.array([0.0, 0.3])
    base = sane_dickinson_cf_z(phase, f_star=1.0, phi_amp_deg=45.0, pitch_amp_deg=45.0)
    monkeypatch.setattr(ef, "compute_force_reference", sentinel)
    halved = sane_dickinson_cf_z(
        phase, f_star=1.0, phi_amp_deg=45.0, pitch_amp_deg=45.0
    )
    np.testing.assert_allclose(halved, base / 2.0, rtol=1e-9)


# --- panel_annotation / null + missing key ------------------------------------------------


def test_panel_annotation_reads_metrics():
    """Scenario: Per-panel annotation reports config-resolved R² and RMSE read from metrics.json."""
    metrics = _toy_metrics(null_target=None)
    txt = panel_annotation(metrics, "CF_z")
    assert "0.83" in txt  # config_resolved.CF_z.config_mean_r2
    assert "0.05" in txt  # per_target.CF_z.rmse
    # mutate -> output changes (not hard-coded)
    metrics["config_resolved"]["CF_z"]["config_mean_r2"] = 0.50
    assert "0.50" in panel_annotation(metrics, "CF_z")


def test_panel_annotation_null_renders_na():
    """Scenario: A NaN-sentinel (null) config-resolved R² renders without crashing."""
    metrics = _toy_metrics(null_target="CF_z")
    txt = panel_annotation(metrics, "CF_z")
    assert "n/a" in txt.lower()


def test_panel_annotation_missing_key_raises():
    """Scenario: A required metrics key or panel coefficient is missing."""
    metrics = _toy_metrics(null_target=None)
    del metrics["config_resolved"]["CF_z"]
    with pytest.raises((KeyError, ValueError)):
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
    assert abs(sp["latency_speedup"] - 310.0) < 5  # ~310x


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


def test_build_caption_discloses_everything():
    """Scenario: Caption reports config-resolved skill, flags aggregate, discloses exclusions."""
    metrics = _toy_metrics(null_target=None)
    sp = compute_speedup(metrics["inference"], rows_per_wingbeat=2000)
    cap = build_caption(metrics, sp)
    low = cap.lower()
    assert (
        "0.94" in cap and "0.83" in cap and "0.99" in cap
    )  # per-axis config-resolved R²
    assert "-3.61" in cap or "−3.61" in cap  # CF_y negative tell
    assert "waveform" in low and "overstates" in low  # aggregate inflated
    assert "cf_mx" in low and "cf_mz" in low  # off-axis exclusion
    assert "coarse" in low and "2.4" in cap  # coarse grid + IB underestimate
    assert "not validated" in low or "validated aerodynamics" in low
    assert "zero-parameter" in low or "zero parameter" in low  # fitted-vs-unfitted
    assert "readme" in low  # pointer
    assert ">1,000" in cap or ">1000" in cap


def test_build_caption_mutates_with_metrics():
    """Scenario: Caption numbers are read from metrics, never hard-coded."""
    metrics = _toy_metrics(null_target=None)
    sp = compute_speedup(metrics["inference"], rows_per_wingbeat=2000)
    metrics["config_resolved"]["CF_x"]["config_mean_r2"] = 0.42
    assert "0.42" in build_caption(metrics, sp)


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


def test_build_figure_baseline_only_on_cf_z():
    """Scenario: Baseline is overlaid only on the lift panel with both RMSEs annotated."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    # the baseline series label appears on exactly one axis, and that axis is CF_z
    baseline_axes = []
    for ax in fig.axes:
        labels = [t.lower() for t in ax.get_legend_handles_labels()[1]]
        if any("dickinson" in lbl or "baseline" in lbl for lbl in labels):
            baseline_axes.append(ax)
    assert len(baseline_axes) == 1
    assert "cf_z" in baseline_axes[0].get_title().lower()
    # CF_z carries two labeled series
    assert len(baseline_axes[0].get_legend_handles_labels()[1]) == 2
    import matplotlib.pyplot as plt

    plt.close(fig)


def test_build_figure_caption_references_issue_1():
    """Scenario: Moment panel ... figure caption references the issue-#1 axis-convention caveat."""
    fig = build_figure(_toy_predictions(), _toy_metrics())
    alltext = " ".join(t.get_text() for t in fig.texts).lower()
    assert "issue #1" in alltext or "#1" in alltext
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
    assert "baseline_rmse_cf_z" in fig_metrics
    assert (
        "speedup" in fig_metrics and fig_metrics["speedup"]["throughput_speedup"] > 1000
    )
    assert fig_metrics["speedup"]["batch_size"] == 12535
    meta = json.loads((out / "run_metadata.json").read_text())
    assert meta["timestamp"] == TS
    assert "sha256:" in meta["docker_image"]


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
    raw = (out / "evidence_figure_metrics.json").read_bytes()
    assert b"\r\n" not in raw


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
    for ax, coef in zip(axes, PANEL_COEFFICIENTS):
        # surrogate offsets across all config scatters on this axis (exclude the baseline 'x'
        # series on CF_z): total surrogate points == parquet row count
        n_surrogate = sum(
            c.get_offsets().shape[0]
            for c in ax.collections
            if c.get_paths()  # scatter PathCollections
        )
        # CF_z has an extra baseline series of equal length; others have just the surrogate
        expected = len(pred) * (2 if coef == "CF_z" else 1)
        assert n_surrogate == expected
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


def test_missing_metrics_key_leaves_no_partial_artifact(tmp_path):
    """A metrics.json missing a required key raises and writes NO partial artifact set."""
    pred, _ = _write_inputs(tmp_path)
    metrics = tmp_path / "bad_metrics.json"
    m = _toy_metrics()
    del m["inference"]
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


# --- README full-disclosure home (honesty test-enforced off the PNG) ----------------------


def test_readme_carries_full_disclosures():
    """Scenario: On-figure caption is compact; full disclosures live in the README."""
    readme = (REPO / "examples" / "prelim_sweep" / "README.md").read_text(
        encoding="utf-8"
    )
    low = readme.lower()
    # the full disclosure set the compact caption only points to
    assert "issue #1" in low
    assert "cf_mx" in low and "cf_mz" in low  # off-axis exclusion
    assert "symmetric-rotation" in low
    assert "stroke-plane-normal" in low and "lab-z" in low  # projection caveat
    assert "zero-parameter" in low  # fitted-vs-unfitted
    assert "not validated aerodynamics" in low or "not a validated" in low
    assert "2.4" in readme  # diffused-IB underestimate
    assert "batch size" in low or "batch_size" in low  # speedup decomposition
    assert "sequential" in low  # CFD rate is sequential
    assert "~310" in readme or "310×" in readme or "310x" in low  # latency floor


# --- Committed-figure contract (guards the committed sidecar against drift) ----------------


def test_committed_figure_metrics_matches_committed_inputs():
    """The committed evidence_figure_metrics.json numbers match the committed metrics.json."""
    fig_dir = REPO / "examples" / "prelim_sweep" / "figures"
    fig_metrics = json.loads((fig_dir / "evidence_figure_metrics.json").read_text())
    metrics = json.loads(COMMITTED_METRICS.read_text())
    for c in PANEL_COEFFICIENTS:
        assert fig_metrics["surrogate_rmse"][c] == metrics["per_target"][c]["rmse"]
        assert (
            fig_metrics["config_mean_r2"][c]
            == metrics["config_resolved"][c]["config_mean_r2"]
        )
    sp = fig_metrics["speedup"]
    assert sp["throughput_speedup"] > 1000
    assert sp["latency_speedup"] < 1000
    assert sp["batch_size"] == 12535
    # baseline is much worse than the surrogate on CF_z (surrogate >= analytic model, CC-4)
    assert fig_metrics["baseline_rmse_cf_z"] > fig_metrics["surrogate_rmse"]["CF_z"]
