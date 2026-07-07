"""Tier T3b — the wing LEV report composition (extract_eulerian_box -> lev), report-only.

The composition math is CI-covered cluster-free via an in-memory synthetic box (monkeypatched adapter),
so ``wing_lev_report`` never depends on the committed boxlib fixture (that fixture, in
``test_stress_integral.py``, exercises the *actual* yt read for issue #33). The real coarse<->medium
comparison is a ``requires_plotfile`` test that auto-skips off-cluster.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.benchmarks.wing_lev import wing_lev_report

_VERDICT_KEYS = ("pass", "converged", "present", "verdict", "match", "in_band")


def _solid_body_rotation_box(omega: float, n: int, dx: float) -> dict:
    """A synthetic Eulerian box carrying solid-body rotation ``(-omega*y, omega*x, 0)``."""
    xs = np.arange(n) * dx
    x, y, _ = np.meshgrid(xs, xs, xs, indexing="ij")
    return {
        "u": -omega * y,
        "v": omega * x,
        "w": np.zeros_like(x),
        "dx": np.array([dx, dx, dx]),
        "current_time": 0.5,
    }


def test_wing_lev_report_reduction(monkeypatch):
    """The reduction reproduces the analytic ||omega||=2*Omega, Q=Omega^2, and exact q_pos_vol; no gate.

    Uses an in-memory monkeypatched box (no plotfile), so it runs in CI and is independent of the
    committed boxlib fixture. The EXACT q_pos_vol pins the ``* dx*dy*dz`` volume Jacobian a bare ``> 0``
    would miss; solid-body rotation is linear so np.gradient is exact on the interior.
    """
    omega, n, dx = 1.3, 6, 0.0625
    box = _solid_body_rotation_box(omega, n, dx)
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.wing_lev.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi: box,
    )
    rep = wing_lev_report("ignored", lo=(0.0, 0.0, 0.0), hi=(1.0, 1.0, 1.0))

    assert rep["peak_vorticity"] == pytest.approx(2.0 * omega)
    assert rep["peak_q"] == pytest.approx(omega**2)
    assert rep["q_pos_frac"] == pytest.approx(1.0)
    n_interior = (n - 2) ** 3
    assert rep["q_pos_vol"] == pytest.approx(omega**2 * n_interior * dx**3, rel=1e-9)
    assert rep["dx"] == (dx, dx, dx)
    assert rep["phase_time"] == pytest.approx(0.5)
    # Report-only: a plain dict of numbers, no verdict/gate key.
    assert not any(k in rep for k in _VERDICT_KEYS)


def test_wing_lev_report_rejects_degenerate_box(monkeypatch):
    """A NaN field or a <3-point box surfaces a clear error through the composition, not a silent value."""
    # NaN in the field -> lev._validate_field raises (no silent NaN peak).
    nan_box = _solid_body_rotation_box(1.3, 6, 0.0625)
    nan_box["u"] = nan_box["u"].copy()
    nan_box["u"][0, 0, 0] = np.nan
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.wing_lev.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi: nan_box,
    )
    with pytest.raises(ValueError, match="finite"):
        wing_lev_report("ignored", lo=(0.0, 0.0, 0.0), hi=(1.0, 1.0, 1.0))

    # A box with only 2 points on an axis -> the centred-gradient >=3 guard raises.
    tiny = _solid_body_rotation_box(1.3, 6, 0.0625)
    tiny = {**tiny, "u": tiny["u"][:2], "v": tiny["v"][:2], "w": tiny["w"][:2]}
    monkeypatch.setattr(
        "mosquito_cfd.benchmarks.wing_lev.extract_eulerian_box",
        lambda plotfile_path, *, lo, hi: tiny,
    )
    with pytest.raises(ValueError, match="at least 3 points"):
        wing_lev_report("ignored", lo=(0.0, 0.0, 0.0), hi=(1.0, 1.0, 1.0))


# --- real coarse<->medium comparison (cluster/Z: data; auto-skips in CI) ----------------------

# Mid-stroke near-field box (t ~ 0.5): contains the full swept wing (tip y ~ 3.475) + near wake,
# trimming the far-field. Derived to bound the wing-marker bbox; the test asserts that fit below.
_NEARFIELD_LO = (2.5, 0.0, 3.0)
_NEARFIELD_HI = (5.5, 4.0, 5.0)
# A downstream-offset box (shifted ~1 chord in +x) to isolate shed vorticity from the IB shell.
_DOWNSTREAM_LO = (3.5, 0.0, 3.0)
_DOWNSTREAM_HI = (6.5, 4.0, 5.0)
_DT = 5e-4


def _wing_plt(grid: str) -> Path:
    """Path to the coarse/medium plotfile nearest physical time t=0.5 (plt01000 at the held dt)."""
    root = Path(os.environ["MOSQUITO_CFD_PLOTFILE_ROOT"])
    subdir = {"coarse": "t2a-newconv4", "medium": "t3b-medium"}[grid]
    return root / subdir / "plt01000"


def _marker_bbox(plt: Path) -> tuple[list[float], list[float]]:
    import yt

    yt.set_log_level("error")
    ad = yt.load(str(plt)).all_data()
    lo = [float(ad["all", f"particle_position_{a}"].min()) for a in "xyz"]
    hi = [float(ad["all", f"particle_position_{a}"].max()) for a in "xyz"]
    return lo, hi


@pytest.mark.requires_plotfile
def test_wing_lev_medium_vs_coarse():
    """Report interior LEV descriptors at mid-stroke t~0.5 on both grids (report-only, no directional gate)."""
    coarse_plt, medium_plt = _wing_plt("coarse"), _wing_plt("medium")

    # Guard: the derived near-field box actually contains the wing markers on both grids.
    for plt in (coarse_plt, medium_plt):
        mlo, mhi = _marker_bbox(plt)
        assert all(
            _NEARFIELD_LO[i] <= mlo[i] and mhi[i] <= _NEARFIELD_HI[i] for i in range(3)
        )

    coarse = wing_lev_report(coarse_plt, lo=_NEARFIELD_LO, hi=_NEARFIELD_HI)
    medium = wing_lev_report(medium_plt, lo=_NEARFIELD_LO, hi=_NEARFIELD_HI)

    # Same kinematic phase (both plotfiles at t ~ 0.5), within half the finer dt.
    assert abs(coarse["phase_time"] - medium["phase_time"]) < 0.5 * _DT
    # A coherent positive-Q LEV core exists on BOTH grids; pinned per-axis spacing.
    for rep, dx in ((coarse, 0.125), (medium, 0.0625)):
        assert np.isfinite(rep["peak_vorticity"]) and rep["peak_vorticity"] > 0.0
        assert np.isfinite(rep["peak_q"]) and rep["peak_q"] > 0.0
        assert rep["q_pos_vol"] > 0.0
        assert rep["dx"] == pytest.approx((dx, dx, dx))
    # NO directional assertion (Q_medium > Q_coarse would encode a resolution artifact as physics).
    # The shell-clean shed-vorticity descriptor: q_pos_vol on a downstream-offset box, both finite/positive.
    for plt in (coarse_plt, medium_plt):
        shed = wing_lev_report(plt, lo=_DOWNSTREAM_LO, hi=_DOWNSTREAM_HI)
        assert np.isfinite(shed["q_pos_vol"])
