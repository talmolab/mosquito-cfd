"""V1-V5 verification figures: assert each figure displays the unit-tested numbers.

The figures visualize quantities tested elsewhere; here we confirm the generators emit the
same values (so a figure can't silently drift from the math) and write their PNGs. Cluster-
free, committed-data only.
"""

import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe: force Agg before importing pyplot
import matplotlib.pyplot as plt
import numpy as np
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


def test_validation_figures_generate_with_tested_numbers(tmp_path):
    """All five PNGs are written and display the tested van Veen quantities."""
    mod = _load()
    summary = mod.main(out_dir=tmp_path)
    for name in (
        "V1_three_convention_CF.png",
        "V2_second_moment.png",
        "V3_scale_invariance.png",
        "V4_added_mass.png",
        "V5_lab_vs_body.png",
    ):
        assert (tmp_path / name).exists(), f"{name} not written"

    # V1: the three F_ref values
    assert summary["v1"]["f_current"] == pytest.approx(624.79, rel=1e-3)
    assert summary["v1"]["f_mean"] == pytest.approx(253.2, rel=1e-2)
    assert summary["v1"]["f_vanveen"] == pytest.approx(200.27, rel=1e-3)
    # V2: radius of gyration + second moment (matches the normalization traceability test)
    assert summary["v2"]["r_gyr"] == pytest.approx(1.6985, rel=1e-2)
    assert summary["v2"]["s_yy"] == pytest.approx(6.797, rel=1e-2)
    # V3: scale-invariance — Delta R^2 ~ 0 for both panels
    for coef in ("CF_x", "CF_z"):
        assert summary["v3"][coef]["delta"] < 1e-9
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


@pytest.mark.parametrize(
    "script",
    ["make_grid_convergence_3grid_figure.py", "make_grid_convergence_figure.py"],
)
def test_convergence_pdfs_carry_no_creation_date(script, tmp_path):
    """Re-rendering must not change the PDF bytes: no embedded creation date."""
    mod = _load(_FIG_DIR / script, script.removesuffix(".py") + "_pdf")
    out = mod.make_figure(tmp_path / "fig.png")
    assert b"/CreationDate" not in out.with_suffix(".pdf").read_bytes()
