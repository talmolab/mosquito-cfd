"""V1-V5 verification figures: assert each figure displays the unit-tested numbers.

The figures visualize quantities tested elsewhere; here we confirm the generators emit the
same values (so a figure can't silently drift from the math) and write their PNGs. Cluster-
free, committed-data only.
"""

import importlib.util
import json
import math
import pathlib
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe: force Agg before importing pyplot
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from _stale_claims import stale_claims

from mosquito_cfd.benchmarks.flapping_wing import (
    decompose_wing_force,
    reconstruct_wing_body_forces,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "examples" / "flapping_wing" / "generate_validation_figures.py"
_DECOMP_SCRIPT = (
    REPO / "examples" / "flapping_wing" / "make_force_decomposition_figure.py"
)


def _load(script: Path = SCRIPT, name: str = "gen_validation_figs"):
    spec = importlib.util.spec_from_file_location(name, script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_fig_force_decomposition_regenerates(tmp_path):
    """T4: fig_force_decomposition writes .png+.pdf cluster-free, and its plotted lines equal the
    decompose_wing_force arrays (the figure cannot drift from the graded math)."""
    mod = _load(_DECOMP_SCRIPT, "make_force_decomp_fig")
    out = tmp_path / "fig_force_decomposition.png"
    out_path, fig, result = mod.make_figure(out, return_artifacts=True)
    try:
        assert out_path.exists() and out_path.with_suffix(".pdf").exists()
        # The normal panel's "model total" line ydata equals result["series"]["model_normal"].
        normal_ax = fig.axes[1]
        model_total = next(
            ln for ln in normal_ax.lines if ln.get_label() == "model total"
        )
        np.testing.assert_allclose(
            model_total.get_ydata(), result["series"]["model_normal"]
        )
        cfd_total = next(
            ln for ln in normal_ax.lines if ln.get_label() == "CFD IB force on wing"
        )
        np.testing.assert_allclose(
            cfd_total.get_ydata(), result["series"]["cfd_normal"]
        )
    finally:
        plt.close(fig)
    # Cross-check the plotted numbers come from a fresh decomposition (no cluster/plotfile dep).
    fresh = decompose_wing_force(
        REPO / "examples/flapping_wing/forces_fine.csv",
        f_star=1.0,
        phi_amp_deg=70.0,
        pitch_amp_deg=45.0,
    )
    assert fresh["normal_peak_cfd"] == pytest.approx(result["normal_peak_cfd"])


def test_validation_figures_generate_with_tested_numbers(regenerated):
    """All five PNGs are written and display the tested van Veen quantities."""
    summary = _read_summary(regenerated / "validation_figures_summary.json")
    for name in (
        "V1_three_convention_CF.png",
        "V2_second_moment.png",
        "V3_scale_invariance.png",
        "V4_added_mass.png",
        "V5_lab_vs_body.png",
    ):
        assert (regenerated / name).exists(), f"{name} not written"

    # V1: the three F_ref values
    assert summary["v1"]["f_current"] == pytest.approx(624.79, rel=1e-3)
    assert summary["v1"]["f_mean"] == pytest.approx(253.2, rel=1e-2)
    assert summary["v1"]["f_vanveen"] == pytest.approx(200.27, rel=1e-3)
    # V2: radius of gyration + second moment (matches the normalization traceability test)
    assert summary["v2"]["r_gyr"] == pytest.approx(1.6985, rel=1e-2)
    assert summary["v2"]["s_yy"] == pytest.approx(6.797, rel=1e-2)
    # V3: scale-invariance — Delta R^2 ~ 0 for both panels; scale/sign fields recorded (D6)
    for coef in ("CF_x", "CF_z"):
        assert summary["v3"][coef]["delta"] < 1e-9
        for key in (
            "r2_van_veen",
            "r2_peak_tip",
            "true_mean",
            "true_rms",
            "pred_mean",
            "pred_rms",
        ):
            assert key in summary["v3"][coef], key
    # V4: added-mass RMS fractions are positive, non-trivial, lift > stroke
    assert 0.0 < summary["v4"]["stroke"] < 1.0
    assert 0.0 < summary["v4"]["lift"] < 1.0
    assert summary["v4"]["lift"] > summary["v4"]["stroke"]
    # V5: the frame figure is at the alpha=45 deg midstroke
    assert summary["v5"]["alpha_deg"] == 45.0


def test_t4_figure_plots_the_corrected_model_with_no_pending_note(tmp_path):
    """The T4 figure shows the model fed the angle of attack, and no longer flags a sign issue.

    Scenario: Decomposition figure regenerates cluster-free. The model-total normal line is the
    ``model_normal`` series and is positive through both mid-strokes (it was about -2.2 near phase
    0.5 when the model was fed the signed pitch).
    """
    mod = _load(_DECOMP_SCRIPT, "make_force_decomp_fig_note")
    _, fig, result = mod.make_figure(tmp_path / "decomp.png", return_artifacts=True)
    try:
        texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        texts += [fig._suptitle.get_text()]
        texts += [ax.get_title() for ax in fig.axes]
        texts += [
            t.get_text()
            for ax in fig.axes
            if ax.get_legend() is not None
            for t in ax.get_legend().get_texts()
        ]
        everything = " ".join(texts)
        assert "#133" not in everything and "pending" not in everything.lower()
        assert "inverted" not in everything
        series = result["series"]
        model_total = next(
            ln for ln in fig.axes[1].lines if ln.get_label() == "model total"
        )
        np.testing.assert_array_equal(model_total.get_ydata(), series["model_normal"])
        phase = series["phase"]
        for lo, hi in ((0.4, 0.6), (0.9, 1.0)):
            band = (phase >= lo) & (phase < hi)
            assert band.sum() > 100
            assert (series["model_normal"][band] > 0).all(), (lo, hi)
        # The chord panel's model total follows the CFD's sign on each half-stroke.
        chord_total = next(
            ln for ln in fig.axes[0].lines if ln.get_label() == "model total"
        )
        np.testing.assert_array_equal(chord_total.get_ydata(), series["model_chord"])
        assert series["model_chord"].min() < 0 < series["model_chord"].max()
        # Every labelled curve in both panels is the series decompose_wing_force returned for
        # that component: no curve is swapped between panels, negated or re-derived.
        for ax, idx, comp in ((fig.axes[0], 0, "chord"), (fig.axes[1], 1, "normal")):
            expected = {
                "translational": series["model_transl"][idx],
                "added-mass": series["model_added_mass"][idx],
                "Wagner": series["model_wagner"][idx],
                "model total": series[f"model_{comp}"],
                "CFD IB force on wing": series[f"cfd_{comp}"],
            }
            drawn = {ln.get_label(): ln for ln in ax.lines}
            assert set(expected) <= set(drawn), comp
            for label, want in expected.items():
                np.testing.assert_array_equal(
                    drawn[label].get_xdata(), series["time"], err_msg=f"{comp}/{label}"
                )
                np.testing.assert_array_equal(
                    drawn[label].get_ydata(), want, err_msg=f"{comp}/{label}"
                )
        # The title states the five recomputed numbers, each in its own phrase.
        title = fig._suptitle.get_text()
        for phrase in (
            f"normal peak: model {result['normal_peak_model']:.2f} "
            f"vs CFD {result['normal_peak_cfd']:.2f}",
            f"peaks {result['normal_peak_phase_gap']:.3f} cycle apart",
            f"chord peak: model {result['chord_peak_model']:.3f} "
            f"vs CFD {result['chord_peak_cfd']:.2f}",
            "not explained by the model",
        ):
            assert phrase in title, phrase
        # No text in the figure makes a claim the corrected model does not support.
        assert stale_claims("\n\n".join(texts)) == []
    finally:
        plt.close(fig)


_FIG_DIR = REPO / "examples" / "flapping_wing"
_SENTINEL_MODEL = {"normal_peak_model": 7.77, "chord_peak_model": 5.55}
_SENTINEL_TARGETS = {"cf_normal_peak": 6.66, "cf_chord_peak": 4.44}


def _render_with_sentinels(script: str, tmp_path, monkeypatch):
    """Render a grid figure with the model peaks and T2a targets replaced by sentinels.

    Returns ``(module, figure, real_close)``; the caller closes the figure. A script that types a
    reference value instead of reading it from its source cannot put a line at a sentinel.
    """
    mod = _load(_FIG_DIR / script, script.removesuffix(".py"))
    calls = []

    def fake_decompose(csv_path, **kwargs):
        calls.append(Path(csv_path).name)
        return dict(_SENTINEL_MODEL)

    # raising=False: before this change the scripts did not import either name.
    monkeypatch.setattr(mod, "decompose_wing_force", fake_decompose, raising=False)
    monkeypatch.setattr(
        mod, "VAN_VEEN_CF_TARGETS", dict(_SENTINEL_TARGETS), raising=False
    )
    real_close = plt.close
    figures = []
    monkeypatch.setattr(mod.plt, "close", lambda fig=None: figures.append(fig))
    mod.make_figure(tmp_path / "fig.png")
    assert len(figures) == 1
    return mod, figures[0], real_close, calls


def _hlines(ax) -> dict[float, str]:
    """``{y: label}`` for every horizontal line spanning the axes (``axhline``)."""
    out = {}
    for ln in ax.lines:
        y = np.asarray(ln.get_ydata(), dtype=float)
        if len(y) == 2 and y[0] == y[1] and ln.get_transform() != ax.transData:
            out[round(float(y[0]), 6)] = ln.get_label()
    return out


def _hspans(ax) -> list[tuple[float, float]]:
    """``(ymin, ymax)`` of every ``axhspan`` patch (full-width rectangles, as distinct from bars)."""
    spans = []
    for patch in ax.patches:
        if patch.get_data_transform() == ax.transData:
            continue  # a bar, drawn in data coordinates
        (_, y0), (_, y1) = ax.transData.inverted().transform(
            patch.get_extents().get_points()
        )
        spans.append((round(float(y0), 6), round(float(y1), 6)))
    return spans


def _legend_labels(ax) -> list[str]:
    legend = ax.get_legend()
    return [] if legend is None else [t.get_text() for t in legend.get_texts()]


def test_timeseries_figure_reference_lines_follow_the_model(tmp_path, monkeypatch):
    """fig_force_timeseries_3grid: model-peak lines read from decompose_wing_force, no bands.

    Scenario: Reference lines follow their sources.
    """
    _, fig, real_close, calls = _render_with_sentinels(
        "make_force_timeseries_3grid_figure.py", tmp_path, monkeypatch
    )
    try:
        ax_chord, ax_normal = fig.axes
        assert calls == ["forces_fine.csv"]
        assert _hspans(ax_chord) == [] and _hspans(ax_normal) == []
        chord, normal = _hlines(ax_chord), _hlines(ax_normal)
        # The chord force changes sign each half-stroke: lines at both signs of the model peak.
        assert {5.55, -5.55} <= set(chord)
        assert 7.77 in normal and -7.77 not in normal
        for lines, ax, value in ((chord, ax_chord, 5.55), (normal, ax_normal, 7.77)):
            label = lines[value]
            assert "van Veen" in label and "model" in label and "fine" in label
            assert label in _legend_labels(ax), (
                "the reference line is not in the legend"
            )
        # No typed copy of a superseded reference survives.
        for ax in (ax_chord, ax_normal):
            assert not {0.3, 0.43, 2.16, 2.48, 2.4} & set(_hlines(ax))
        # Each panel plots its own component for each grid (chord in the chord panel).
        fine = reconstruct_wing_body_forces(
            _FIG_DIR / "forces_fine.csv",
            f_star=1.0,
            phi_amp_deg=70.0,
            pitch_amp_deg=45.0,
        )
        window = fine.time >= 0.05
        for ax, want in ((ax_chord, fine.cf_chord), (ax_normal, fine.cf_normal)):
            (line,) = [ln for ln in ax.lines if ln.get_label().startswith("Fine")]
            np.testing.assert_array_equal(line.get_ydata(), want[window])
    finally:
        real_close(fig)


def test_3grid_convergence_figure_reference_lines_follow_their_sources(
    tmp_path, monkeypatch
):
    """fig_grid_convergence_3grid: a model-peak line and a T2a-target line; only the GCI span."""
    _, fig, real_close, calls = _render_with_sentinels(
        "make_grid_convergence_3grid_figure.py", tmp_path, monkeypatch
    )
    try:
        ax_chord, ax_normal = fig.axes
        assert calls == ["forces_fine.csv"]
        for ax, model, target in ((ax_chord, 5.55, 4.44), (ax_normal, 7.77, 6.66)):
            lines = _hlines(ax)
            assert "model" in lines[model] and "van Veen" in lines[model]
            assert "T2a target" in lines[target]
            labels = _legend_labels(ax)
            assert lines[model] in labels and lines[target] in labels
            # Exactly one shaded span: Richardson extrapolant x (1 +/- GCI_fine).
            assert len(_hspans(ax)) == 1
            assert not {0.3, 0.43, 2.4, 2.48} & set(lines)
        from mosquito_cfd.benchmarks.wing_convergence import (
            wing_grid_convergence_from_body_forces,
        )

        conv = wing_grid_convergence_from_body_forces(
            _FIG_DIR / "forces_t2a_newconv.csv",
            _FIG_DIR / "forces_medium.csv",
            _FIG_DIR / "forces_fine.csv",
            f_star=1.0,
            phi_amp_deg=70.0,
            pitch_amp_deg=45.0,
        )
        for ax, comp in ((ax_chord, "cf_chord"), (ax_normal, "cf_normal")):
            # The plotted points are coarse, medium, fine, in that order.
            (points,) = [ln for ln in ax.lines if len(ln.get_xdata()) == 3]
            assert list(points.get_xdata()) == [0, 1, 2]
            np.testing.assert_allclose(
                points.get_ydata(),
                [conv[comp][k] for k in ("cf_coarse", "cf_medium", "cf_fine")],
                rtol=0,
                atol=1e-12,
            )
            target_label = _hlines(ax)[4.44 if comp == "cf_chord" else 6.66]
            assert "not the paper's value" in target_label
            h0, gci = conv[comp]["cf_exact_richardson"], conv[comp]["gci_fine"]
            (lo, hi) = _hspans(ax)[0]
            assert lo == pytest.approx(h0 * (1 - gci), abs=1e-5)
            assert hi == pytest.approx(h0 * (1 + gci), abs=1e-5)
    finally:
        real_close(fig)


def test_2grid_convergence_figure_reference_line_is_the_t2a_target(
    tmp_path, monkeypatch
):
    """fig_grid_convergence: its one reference line is read from VAN_VEEN_CF_TARGETS."""
    _, fig, real_close, calls = _render_with_sentinels(
        "make_grid_convergence_figure.py", tmp_path, monkeypatch
    )
    try:
        assert calls == []  # this figure draws no model line
        for ax, target in zip(fig.axes, (4.44, 6.66), strict=True):
            lines = _hlines(ax)
            assert set(lines) == {target}
            assert (
                "T2a target" in lines[target] and "van Veen 2022 ~" not in lines[target]
            )
            assert lines[target] in _legend_labels(ax)
            assert _hspans(ax) == []
    finally:
        real_close(fig)


# --- V1-V5 summary staleness guard (refresh-v3-validation-figure, #124) -------------------------

_REL_TOL = 1e-12  # relative tolerance for every non-near-zero number (design D2)
_NEAR_ZERO = 1e-12  # committed |value| below this is compared absolutely, within this


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _summary_mismatches(committed, fresh, path: str = "") -> list[str]:
    """Every difference between two summaries, one message per mismatch (design D2).

    Messages start with the dotted key path and say what kind of mismatch it is, so a caller can
    tell a stale value from a missing key: ``"{path}: missing in fresh"``, ``"{path}: missing in
    committed"``, ``"{path}: type {a} != {b}"`` or ``"{path}: committed {c!r} != fresh {f!r}"``.
    Both sides' keys are walked at every level. A number agrees within ``1e-12`` relative to the
    committed value, or within ``1e-12`` absolute when the committed magnitude is below ``1e-12``;
    a non-finite number never agrees.
    """
    if isinstance(committed, dict) and isinstance(fresh, dict):
        out = []
        for key in sorted(committed.keys() | fresh.keys()):
            where = f"{path}.{key}" if path else str(key)
            if key not in fresh:
                out.append(f"{where}: missing in fresh")
            elif key not in committed:
                out.append(f"{where}: missing in committed")
            else:
                out.extend(_summary_mismatches(committed[key], fresh[key], where))
        return out
    if _is_number(committed) and _is_number(fresh):
        c, f = float(committed), float(fresh)
        if not (math.isfinite(c) and math.isfinite(f)):
            agree = False
        elif abs(c) < _NEAR_ZERO:
            agree = abs(f - c) <= _NEAR_ZERO
        else:
            agree = abs(f - c) <= _REL_TOL * abs(c)
        return [] if agree else [f"{path}: committed {committed!r} != fresh {fresh!r}"]
    if type(committed) is not type(fresh):
        return [f"{path}: type {type(committed).__name__} != {type(fresh).__name__}"]
    return (
        []
        if committed == fresh
        else [f"{path}: committed {committed!r} != fresh {fresh!r}"]
    )


def _leaf(value):
    """A summary nested three levels deep, like ``v3.CF_x.r2_van_veen``."""
    return {"a": {"b": {"c": value, "s": "text"}}, "v5": {"alpha_deg": 45.0}}


_DRIFT_CASES = {
    "key missing from fresh": (
        {"a": {"b": {"c": 1.0, "d": 2.0}}},
        {"a": {"b": {"c": 1.0}}},
        ["a.b.d: missing in fresh"],
    ),
    "key present only in fresh": (
        {"a": {"b": {"c": 1.0}}},
        {"a": {"b": {"c": 1.0, "d": 2.0}}},
        ["a.b.d: missing in committed"],
    ),
    "block present only in fresh": (
        {"a": {"b": {"c": 1.0}}},
        {"a": {"b": {"c": 1.0}}, "v5": {"alpha_deg": 45.0}},
        ["v5: missing in committed"],
    ),
    "dict against a number": (
        {"a": {"b": {"c": 1.0}}},
        {"a": {"b": 2.0}},
        ["a.b: type dict != float"],
    ),
    "1e-9 relative": (
        _leaf(0.75),
        _leaf(0.75 * (1 + 1e-9)),
        [f"a.b.c: committed {0.75!r} != fresh {0.75 * (1 + 1e-9)!r}"],
    ),
    "1e-11 against 1.05e-11": (
        _leaf(1e-11),
        _leaf(1.05e-11),
        [f"a.b.c: committed {1e-11!r} != fresh {1.05e-11!r}"],
    ),
    "0.5 against 0.5 + 8e-13": (
        _leaf(0.5),
        _leaf(0.5 + 8e-13),
        [f"a.b.c: committed {0.5!r} != fresh {0.5 + 8e-13!r}"],
    ),
    "committed 0.0 against 2e-12": (
        _leaf(0.0),
        _leaf(2e-12),
        [f"a.b.c: committed {0.0!r} != fresh {2e-12!r}"],
    ),
    "NaN committed": (
        _leaf(float("nan")),
        _leaf(0.5),
        ["a.b.c: committed nan != fresh 0.5"],
    ),
    "NaN fresh": (
        _leaf(0.5),
        _leaf(float("nan")),
        ["a.b.c: committed 0.5 != fresh nan"],
    ),
    "NaN both": (
        _leaf(float("nan")),
        _leaf(float("nan")),
        ["a.b.c: committed nan != fresh nan"],
    ),
    "differing string": (
        {"a": {"b": {"c": 1.0, "s": "one"}}},
        {"a": {"b": {"c": 1.0, "s": "two"}}},
        ["a.b.s: committed 'one' != fresh 'two'"],
    ),
}

_ACCEPT_CASES = {
    "identical": (_leaf(0.75), _leaf(0.75)),
    "1e-13 relative": (_leaf(0.75), _leaf(0.75 * (1 + 1e-13))),
    "committed 0.0 against 5e-13": (_leaf(0.0), _leaf(5e-13)),
}


@pytest.mark.parametrize("case", sorted(_DRIFT_CASES))
def test_summary_comparator_rejects_each_kind_of_drift(case):
    """Each kind of drift yields exactly one message of its kind at its dotted key path (D2)."""
    committed, fresh, expected = _DRIFT_CASES[case]
    assert _summary_mismatches(committed, fresh) == expected


@pytest.mark.parametrize("case", sorted(_ACCEPT_CASES))
def test_summary_comparator_accepts_rounding(case):
    """Identical summaries and sub-tolerance rounding yield no mismatch (D2)."""
    committed, fresh = _ACCEPT_CASES[case]
    assert _summary_mismatches(committed, fresh) == []


_COMMITTED_SUMMARY = (
    REPO / "examples" / "flapping_wing" / "figures" / "validation_figures_summary.json"
)
_PRED = REPO / "examples" / "prelim_sweep" / "surrogate" / "holdout_predictions.parquet"
_METRICS = REPO / "examples" / "prelim_sweep" / "surrogate" / "metrics.json"
_DATASET = REPO / "examples" / "prelim_sweep" / "dataset.parquet"
_V3_COEFS = ("CF_x", "CF_z")

# The summary committed before this change (e600581), with the v3 R^2 keys renamed to the new
# names and the stale values kept: R^2 of the predictions committed in c74d69b (#36).
_STALE_SUMMARY = {
    "v1": {
        "f_current": 624.7901897699495,
        "f_mean": 253.2179262224485,
        "f_vanveen": 200.27117406335543,
    },
    "v2": {"r_gyr": 1.6984914918884995, "s_yy": 6.797322687501861},
    "v3": {
        "CF_x": {
            "r2_van_veen": 0.9931809360713737,
            "r2_peak_tip": 0.9931809360713737,
            "delta": 0.0,
        },
        "CF_z": {
            "r2_van_veen": 0.9854005163288705,
            "r2_peak_tip": 0.9854005163288705,
            "delta": 0.0,
        },
    },
    "v4": {"stroke": 0.1040886353151355, "lift": 0.3976671512205978},
    "v5": {"alpha_deg": 45.0},
}


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory) -> Path:
    """Run ``main()`` once into a module temp dir; return that dir."""
    out = tmp_path_factory.mktemp("validation_figures")
    _load(name="gen_validation_figs_regenerated").main(out_dir=out)
    return out


def _read_summary(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _v3_source_mismatches(summary: dict) -> list[str]:
    """Differences between a summary's ``v3`` block and its committed sources (design D2, D6).

    ``r2_van_veen`` is checked against R^2 recomputed from the committed predictions with the
    trainer's R^2 function and against ``metrics.json``; the mean/RMS fields against numpy
    recomputations of the stored (van Veen) arrays.
    """
    from mosquito_cfd.force_surrogate.train import _r2

    pred = pd.read_parquet(_PRED)
    metrics = _read_summary(_METRICS)
    v3 = summary.get("v3", {})
    out = []
    for coef in _V3_COEFS:
        y = pred[f"{coef}_true"].to_numpy(float)
        yhat = pred[f"{coef}_pred"].to_numpy(float)
        expected = {
            "r2_van_veen": _r2(y, yhat),
            "true_mean": float(np.mean(y)),
            "true_rms": float(np.sqrt(np.mean(y**2))),
            "pred_mean": float(np.mean(yhat)),
            "pred_rms": float(np.sqrt(np.mean(yhat**2))),
        }
        got = v3.get(coef, {})
        for name, want in expected.items():
            where = f"v3.{coef}.{name}"
            if name not in got:
                out.append(f"{where}: missing in committed")
            else:
                out.extend(_summary_mismatches(got[name], want, where))
        if "r2_van_veen" in got:
            out.extend(
                _summary_mismatches(
                    got["r2_van_veen"],
                    metrics["per_target"][coef]["r2"],
                    f"v3.{coef}.r2_van_veen",
                )
            )
    return out


def test_committed_summary_matches_regeneration(regenerated, tmp_path_factory):
    """The committed V1-V5 summary equals a fresh regeneration from committed data, all blocks.

    Scenario: The committed summary equals a fresh regeneration.
    """
    assert _COMMITTED_SUMMARY.is_file()
    # Never a self-comparison: the committed file is the repo's, not a regenerated copy.
    assert not _COMMITTED_SUMMARY.resolve().is_relative_to(
        tmp_path_factory.getbasetemp().resolve()
    )
    mismatches = _summary_mismatches(
        _read_summary(_COMMITTED_SUMMARY),
        _read_summary(regenerated / "validation_figures_summary.json"),
    )
    assert mismatches == [], "\n".join(mismatches)


def test_stale_v3_values_are_rejected(regenerated):
    """Stale R^2 under the correct keys is reported as a value mismatch, not a key mismatch.

    Scenario: Stale values under the correct keys are rejected.
    """
    fresh = _read_summary(regenerated / "validation_figures_summary.json")
    against_fresh = _summary_mismatches(_STALE_SUMMARY, fresh)
    against_sources = _v3_source_mismatches(_STALE_SUMMARY)
    for coef in _V3_COEFS:
        stale = _STALE_SUMMARY["v3"][coef]["r2_van_veen"]
        prefix = f"v3.{coef}.r2_van_veen: committed {stale!r} != fresh "
        assert any(m.startswith(prefix) for m in against_fresh), against_fresh
        assert any(m.startswith(prefix) for m in against_sources), against_sources


def test_committed_v3_matches_parquet_and_metrics():
    """Committed v3 R^2 equals R^2 recomputed from the committed predictions and metrics.json.

    Scenario: The committed V3 R^2 equals R^2 recomputed from the committed predictions.
    """
    mismatches = _v3_source_mismatches(_read_summary(_COMMITTED_SUMMARY))
    assert mismatches == [], "\n".join(mismatches)


def _render_v3(tmp_path, monkeypatch):
    """Render V3 alone with ``plt.close`` collected; return (module, summary, figure, close)."""
    mod = _load(name="gen_validation_figs_v3")
    real_close = plt.close
    figures = []
    monkeypatch.setattr(mod.plt, "close", lambda fig=None: figures.append(fig))
    summary = mod.fig_v3_scale_invariance(tmp_path)
    assert len(figures) == 1
    return mod, summary, figures[0], real_close


def _panel(fig, coef: str, convention: str):
    matches = [
        ax for ax in fig.axes if coef in ax.get_title() and convention in ax.get_title()
    ]
    assert len(matches) == 1, (coef, convention, [ax.get_title() for ax in fig.axes])
    return matches[0]


def _offsets(ax) -> np.ndarray:
    (collection,) = ax.collections
    return np.ma.getdata(collection.get_offsets())


def _k() -> float:
    from mosquito_cfd.force_surrogate import compute_force_reference
    from mosquito_cfd.force_surrogate.constants import (
        CHORD,
        R_GYRATION,
        R_TIP,
        RHO,
        SPAN,
    )

    tip = compute_force_reference(1.0, 70.0, R_TIP, SPAN, CHORD, RHO).f_ref
    gyr = compute_force_reference(1.0, 70.0, R_GYRATION, SPAN, CHORD, RHO).f_ref
    return tip / gyr


def test_v3_panels_plot_both_normalizations(tmp_path, monkeypatch):
    """V3 plots the stored (van Veen) coefficients unscaled and the peak-tip ones as stored / k.

    Scenarios: The van Veen panel plots the stored coefficients unscaled; Titles and axis labels
    describe what is plotted.
    """
    _, summary, fig, real_close = _render_v3(tmp_path, monkeypatch)
    try:
        assert len(fig.axes) == 4
        pred = pd.read_parquet(_PRED)
        k = _k()
        for coef in _V3_COEFS:
            y = pred[f"{coef}_true"].to_numpy(float)
            yhat = pred[f"{coef}_pred"].to_numpy(float)
            # (a) The panel titled van Veen plots the stored arrays, unscaled.
            vv = _panel(fig, coef, "van Veen")
            np.testing.assert_array_equal(_offsets(vv), np.column_stack([y, yhat]))
            # (b) The peak-tip panel plots the same arrays divided by k.
            pt = _panel(fig, coef, "peak-tip")
            np.testing.assert_array_equal(
                _offsets(pt), np.column_stack([y / k, yhat / k])
            )
            # (c) Each title states its own R^2.
            assert f"{summary[coef]['r2_van_veen']:.6f}" in vv.get_title()
            assert f"{summary[coef]['r2_peak_tip']:.6f}" in pt.get_title()
            # (e) Axis labels name the CFD coefficient's frame and sign, and the surrogate.
            for ax in (vv, pt):
                xlabel, ylabel = ax.get_xlabel(), ax.get_ylabel()
                assert coef in xlabel and "lab frame" in xlabel and "on wing" in xlabel
                assert coef in ylabel and "surrogate" in ylabel
        # (d) No before/after wording anywhere.
        titles = [ax.get_title() for ax in fig.axes] + [fig._suptitle.get_text()]
        for text in titles:
            assert "BEFORE" not in text and "AFTER" not in text, text
    finally:
        real_close(fig)


def test_v3_peak_tip_panel_matches_raw_forces_on_tip_reference(tmp_path, monkeypatch):
    """The peak-tip panel equals -F / F_ref(R_TIP) per configuration, from the raw corpus forces.

    Scenario: The peak-tip panel matches raw forces on the tip reference (design D7). A known
    answer independent of the generator: a x k or a dropped sign is off by O(1).
    """
    from mosquito_cfd.force_surrogate import compute_force_reference
    from mosquito_cfd.force_surrogate.constants import (
        CHORD,
        R_GYRATION,
        R_TIP,
        RHO,
        SPAN,
    )

    _, _, fig, real_close = _render_v3(tmp_path, monkeypatch)
    try:
        keys = ["config_name", "time"]
        rows = pd.read_parquet(_PRED, columns=keys)
        raw = pd.read_parquet(
            _DATASET, columns=[*keys, "Fx", "Fz", "frequency_fstar", "stroke_amp_deg"]
        )
        merged = rows.merge(raw, on=keys, how="left", validate="one_to_one")
        assert len(merged) == len(rows) and not merged.isna().any().any()
        f_ref_tip = {
            pair: compute_force_reference(*pair, R_TIP, SPAN, CHORD, RHO).f_ref
            for pair in set(zip(merged.frequency_fstar, merged.stroke_amp_deg))
        }
        tip = np.array(
            [
                f_ref_tip[pair]
                for pair in zip(merged.frequency_fstar, merged.stroke_amp_deg)
            ]
        )
        for coef, force in (("CF_x", "Fx"), ("CF_z", "Fz")):
            pt_x = _offsets(_panel(fig, coef, "peak-tip"))[:, 0]
            # Raw IB force is on the fluid; the coefficient is the force on the wing.
            expected = -merged[force].to_numpy(float) / tip
            assert pt_x == pytest.approx(expected, rel=1e-12, abs=0)
            vv_x = _offsets(_panel(fig, coef, "van Veen"))[:, 0]
            m = pt_x != 0
            assert vv_x[m] / pt_x[m] == pytest.approx(
                np.full(m.sum(), (R_TIP / R_GYRATION) ** 2), rel=1e-15, abs=0
            )
    finally:
        real_close(fig)


def test_summary_is_written_with_lf(tmp_path, monkeypatch):
    """The summary has no CR even where the platform default line ending is CRLF.

    Scenario: The summary has no carriage returns even where the platform default is CRLF.
    """
    original = pathlib.Path.write_text
    written = []

    def crlf_by_default(self, data, *args, **kwargs):
        kwargs.setdefault("newline", "\r\n")
        written.append(self)
        return original(self, data, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", crlf_by_default)
    _load(name="gen_validation_figs_lf").main(out_dir=tmp_path)
    summary = tmp_path / "validation_figures_summary.json"
    assert summary in written, "the summary must be written through Path.write_text"
    assert b"\r" not in summary.read_bytes()


@pytest.mark.parametrize(
    "script",
    ["make_grid_convergence_3grid_figure.py", "make_grid_convergence_figure.py"],
)
def test_convergence_pdfs_carry_no_creation_date(script, tmp_path):
    """Re-rendering must not change the PDF bytes: no embedded creation date."""
    mod = _load(_FIG_DIR / script, script.removesuffix(".py") + "_pdf")
    out = mod.make_figure(tmp_path / "fig.png")
    assert b"/CreationDate" not in out.with_suffix(".pdf").read_bytes()
