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

from mosquito_cfd.benchmarks.flapping_wing import decompose_wing_force

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
            ln for ln in normal_ax.lines if ln.get_label() == "CFD total (ib_force)"
        )
        np.testing.assert_allclose(
            cfd_total.get_ydata(), result["series"]["cfd_normal"]
        )
    finally:
        plt.close(fig)
    # Cross-check the plotted numbers come from a fresh decomposition (no cluster/plotfile dep).
    fresh = decompose_wing_force(
        REPO / "examples/flapping_wing/forces_t2a_newconv.csv",
        medium_csv=REPO / "examples/flapping_wing/forces_medium.csv",
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
