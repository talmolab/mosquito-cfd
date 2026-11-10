"""Every flapping-wing use site applies the sign through ``force_on_wing``, once (issue #109, design D1).

An identity spy replaces ``force_on_wing`` at each use site (the module attribute the code calls). With
the spy in place:

- series that *are* the IB force equal the pre-change on-fluid series bitwise, so the sign enters only
  through ``force_on_wing``;
- composites equal their formula on the spied output (``cf_hydro``, ``peak_cf_*_6dof``);
- across all calls, the arrays passed are exactly the raw IB-force columns, each once.

The flapping-wing pending phrase's condition is tested the same way: identity at the use site makes the
series on-fluid, the real ``force_on_wing`` makes them on-wing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from test_coordinate_convention_sign import flapping_series_on_wing  # noqa: E402

from mosquito_cfd.benchmarks import flapping_wing  # noqa: E402
from mosquito_cfd.benchmarks.wing_kinematics import (  # noqa: E402
    euler_angles,
    rotation_matrix,
)
from mosquito_cfd.force_surrogate import force_on_wing  # noqa: E402

_ROOT = Path(__file__).resolve().parents[1]
_FW = _ROOT / "examples" / "flapping_wing"
_NEWCONV = _FW / "forces_t2a_newconv.csv"
_OLD = _FW / "forces.csv"
_KIN = {"f_star": 1.0, "phi_amp_deg": 70.0}
_BODY_KIN = {**_KIN, "pitch_amp_deg": 45.0}


class _Spy:
    """Identity stand-in for ``force_on_wing`` that records every component it is given."""

    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, ...]] = []

    def __call__(self, *components):
        arrays = tuple(np.asarray(c) for c in components)
        self.calls.append(tuple(a.copy() for a in arrays))
        return arrays

    def assert_passed_once_each(self, expected: list[np.ndarray]) -> None:
        passed = [a for call in self.calls for a in call]
        assert len(passed) == len(expected), (len(passed), len(expected))
        unmatched = list(expected)
        for array in passed:
            hit = next(
                (i for i, e in enumerate(unmatched) if np.array_equal(array, e)), None
            )
            assert hit is not None, (
                "force_on_wing got an array that is not a raw column"
            )
            unmatched.pop(hit)


def _columns(csv: Path, *names: str) -> list[np.ndarray]:
    df = pd.read_csv(csv)
    return [df[n].to_numpy(float) for n in names]


def _rots(time: np.ndarray) -> np.ndarray:
    """``R(t)`` at the benchmark kinematics, built independently of the module."""
    return np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=1.0,
                    stroke_amp_rad=np.radians(70.0),
                    pitch_amp_rad=np.radians(45.0),
                )
            )
            for t in time
        ]
    )


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"{name}_under_test", _FW / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def spy(monkeypatch):
    s = _Spy()
    monkeypatch.setattr(flapping_wing, "force_on_wing", s)
    return s


def test_reconstruct_wing_forces_signs_only_through_force_on_wing(spy):
    d = flapping_wing.reconstruct_wing_forces(_NEWCONV, rho_f=2.0, **_KIN)
    fx, fz = _columns(_NEWCONV, "Fx", "Fz")
    # ib_force is per unit density, so the IB force on the wing carries rho_f.
    np.testing.assert_array_equal(d.cf_x_ib, 2.0 * fx / d.f_ref)
    np.testing.assert_array_equal(d.cf_z_ib, 2.0 * fz / d.f_ref)
    np.testing.assert_allclose(d.cf_x_hydro, d.cf_x_added + d.cf_x_ib, rtol=1e-12)
    np.testing.assert_allclose(d.cf_z_hydro, d.cf_z_added + d.cf_z_ib, rtol=1e-12)
    spy.assert_passed_once_each([fx, fz])


def test_reconstruct_wing_body_forces_signs_only_through_force_on_wing(spy):
    d = flapping_wing.reconstruct_wing_body_forces(_NEWCONV, **_BODY_KIN)
    fx, fy, fz = _columns(_NEWCONV, "Fx", "Fy", "Fz")
    rots = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=1.0,
                    stroke_amp_rad=np.radians(70.0),
                    pitch_amp_rad=np.radians(45.0),
                )
            )
            for t in d.time
        ]
    )
    on_fluid = flapping_wing.body_frame_coefficients(
        np.column_stack([fx, fy, fz]), rots, d.f_ref
    )
    for key in ("cf_chord", "cf_normal", "cf_span"):
        np.testing.assert_array_equal(getattr(d, key), on_fluid[key])
    spy.assert_passed_once_each([fx, fy, fz])


def test_added_mass_diagnostic_signs_only_through_force_on_wing(spy):
    """With the identity, the 6-DOF peaks are ``rho_f·SumU + rho_f·(spied ib)``, the IB peaks
    ``rho_f·(spied ib)``: both sides of the comparison carry the density (review of #136).
    """
    out = flapping_wing.body_frame_added_mass_subtracted(
        _NEWCONV, rho_f=2.0, **_BODY_KIN
    )
    fx, fy, fz, sx, sy, sz = _columns(
        _NEWCONV, "Fx", "Fy", "Fz", "SumUx", "SumUy", "SumUz"
    )
    spy.assert_passed_once_each([fx, fy, fz])
    time = _columns(_NEWCONV, "time")[0]
    rots = np.stack(
        [
            rotation_matrix(
                *euler_angles(
                    t,
                    frequency=1.0,
                    stroke_amp_rad=np.radians(70.0),
                    pitch_amp_rad=np.radians(45.0),
                )
            )
            for t in time
        ]
    )
    ib = 2.0 * np.column_stack([fx, fy, fz])
    six_dof = 2.0 * np.column_stack([sx, sy, sz]) + ib
    f_ref = flapping_wing.reconstruct_wing_forces(_NEWCONV, **_KIN).f_ref
    m = time >= flapping_wing.STEADY_WINDOW_T0
    for name, force in (("6dof", six_dof), ("ib", ib)):
        cf = flapping_wing.body_frame_coefficients(force, rots, f_ref)
        for comp in ("chord", "normal"):
            assert out[f"peak_cf_{comp}_{name}"] == pytest.approx(
                float(np.abs(cf[f"cf_{comp}"][m]).max()), rel=1e-12
            ), (name, comp)


def test_t4_cfd_series_signs_only_through_force_on_wing(spy):
    """T4's CFD body-frame series carry the sign only through ``force_on_wing`` (review of #136).

    The graded T4 checks use ``|·|``, so without this a re-negated CFD series would pass.
    """
    out = flapping_wing.decompose_wing_force(_NEWCONV, **_BODY_KIN)
    fx, fy, fz = _columns(_NEWCONV, "Fx", "Fy", "Fz")
    spy.assert_passed_once_each([fx, fy, fz])
    time = _columns(_NEWCONV, "time")[0]
    m = time >= flapping_wing.STEADY_WINDOW_T0
    f_ref = flapping_wing.reconstruct_wing_forces(_NEWCONV, **_KIN).f_ref
    on_fluid = flapping_wing.body_frame_coefficients(
        np.column_stack([fx, fy, fz]), _rots(time), f_ref
    )
    series = out["series"]
    np.testing.assert_array_equal(series["time"], time[m])
    for comp in ("chord", "normal"):
        np.testing.assert_array_equal(series[f"cfd_{comp}"], on_fluid[f"cf_{comp}"][m])


_REAL_CLOSE = (
    plt.close
)  # module.plt is pyplot itself, so cleanup must bypass the capture


def _capture_figures(module, monkeypatch) -> list:
    """Keep the figures the module closes, so their plotted data can be read back."""
    figures = []
    monkeypatch.setattr(module.plt, "close", lambda fig=None: figures.append(fig))
    return figures


def test_plot_f1_forces_signs_only_through_force_on_wing(tmp_path, monkeypatch):
    gaf = _load("generate_all_figures")
    s = _Spy()
    monkeypatch.setattr(gaf, "force_on_wing", s)
    figures = _capture_figures(gaf, monkeypatch)
    gaf.plot_f1_forces(tmp_path, _OLD)
    try:
        fx, fy, fz = _columns(_OLD, "Fx", "Fy", "Fz")
        s.assert_passed_once_each([fx, fy, fz])
        t = _columns(_OLD, "time")[0]
        m = t >= 0.05  # F1's own window (generate_all_figures.plot_f1_forces)
        f_ref = gaf.compute_force_reference(
            gaf.F_STAR, gaf.PHI_AMP_DEG, gaf.R_GYRATION, gaf.SPAN, gaf.CHORD, rho=1.0
        ).f_ref
        lines = [ln for ax in figures[0].axes for ln in ax.lines]
        plotted = {ln.get_label(): ln.get_ydata() for ln in lines}
        np.testing.assert_array_equal(
            plotted["CF_x (chord / streamwise)"], fx[m] / f_ref
        )
        np.testing.assert_array_equal(plotted["CF_y (span)"], fy[m] / f_ref)
        np.testing.assert_array_equal(plotted["CF_z (vertical / lift)"], fz[m] / f_ref)
    finally:
        for fig in figures:
            _REAL_CLOSE(fig)


def test_fig_v1_signs_only_through_force_on_wing(tmp_path, monkeypatch):
    gvf = _load("generate_validation_figures")
    s = _Spy()
    monkeypatch.setattr(gvf, "force_on_wing", s)
    figures = _capture_figures(gvf, monkeypatch)
    nums = gvf.fig_v1_three_convention(tmp_path)
    try:
        fx, fz = _columns(_OLD, "Fx", "Fz")
        s.assert_passed_once_each([fx, fz])
        t = _columns(_OLD, "time")[0]
        m = t >= flapping_wing.STEADY_WINDOW_T0
        refs = {
            "current (peak tip)": nums["f_current"],
            "mean tip": nums["f_mean"],
            "van Veen": nums["f_vanveen"],
        }
        axx, axz = figures[0].axes
        for ax, force in ((axx, fx), (axz, fz)):
            curves = [ln for ln in ax.lines if not ln.get_label().startswith("_")]
            assert len(curves) == len(refs)
            for name, f_ref in refs.items():
                (line,) = [ln for ln in curves if ln.get_label().startswith(name)]
                np.testing.assert_array_equal(line.get_ydata(), force[m] / f_ref)
    finally:
        for fig in figures:
            _REAL_CLOSE(fig)


def test_flapping_phrase_condition_follows_force_on_wing_at_the_use_site(monkeypatch):
    """The flapping-wing phrase's condition is tied to the code path, through the use site.

    Identity at the use site leaves the series on-fluid; the real helper makes them on-wing; negating
    only one of the two components is never on-wing. Negating the CSV instead would negate both sides
    of the condition, so the data cannot exercise it. Replaces PR1's injected-reconstruction test.
    """

    def negate_only(index):
        def helper(*components):
            return tuple(
                np.negative(c) if i == index else np.asarray(c)
                for i, c in enumerate(components)
            )

        return helper

    monkeypatch.setattr(
        flapping_wing, "force_on_wing", lambda *c: tuple(np.asarray(x) for x in c)
    )
    assert flapping_series_on_wing() is False
    for index in (0, 1):  # (Fx, Fz) as reconstruct_wing_forces passes them
        monkeypatch.setattr(flapping_wing, "force_on_wing", negate_only(index))
        assert flapping_series_on_wing() is False, index
    monkeypatch.setattr(flapping_wing, "force_on_wing", force_on_wing)
    assert flapping_series_on_wing() is True
