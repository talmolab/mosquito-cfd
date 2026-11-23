"""Settling-check controls: force comparison (C1/C3) and field change (tasks 5.1, 5.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.dataset import IB_PARTICLE_COLUMNS
from mosquito_cfd.force_surrogate.settling import (
    compare_force_csv,
    field_change_stats,
    print_unit,
)

DT = 5e-4
FORCES = ("Fx", "Fy", "Fz", "Mx", "My", "Mz")


def _values(steps: np.ndarray) -> dict[str, np.ndarray]:
    t = steps * DT
    return {
        "Fx": -7191.76 * np.sin(2 * np.pi * t) - 3.0,
        "Fy": 312.0 * np.cos(2 * np.pi * t),
        "Fz": 1234.5 * np.cos(2 * np.pi * t) + 0.25,
        "Mx": 88.0 * np.sin(4 * np.pi * t),
        "My": -0.5 * np.cos(2 * np.pi * t),
        "Mz": 3.0e4 * np.sin(2 * np.pi * t + 0.3),
    }


def _reference(n_steps: int) -> pd.DataFrame:
    """Committed-dataset-shaped reference rows: parsed from 6-significant-figure text."""
    steps = np.arange(n_steps)
    data = {"time": [float(f"{s * DT:g}") for s in steps]}
    for name, values in _values(steps).items():
        data[name] = [float(f"{v:g}") for v in values]
    return pd.DataFrame(data)


def _write_csv(path, n_steps: int, *, init_iter_rows: int = 0, edit=None) -> None:
    """An IAMReX-shaped IB_Particle CSV printed at 6 significant figures (%g)."""
    steps = np.arange(n_steps)
    values = _values(steps)
    rows = []
    for i, step in enumerate(steps):
        row = dict.fromkeys(IB_PARTICLE_COLUMNS, 0.0)
        row["iStep"] = int(step)
        row["time"] = step * DT
        for name in FORCES:
            row[name] = values[name][i]
        rows.append(row)
    extra = [
        dict(rows[0], Fx=0.0) for _ in range(init_iter_rows)
    ]  # placeholder rows first
    rows = extra + rows
    if edit is not None:
        edit(rows)
    lines = [",".join(IB_PARTICLE_COLUMNS)]
    for row in rows:
        cells = [str(int(row["iStep"]))] + [
            f"{row[c]:g}" for c in IB_PARTICLE_COLUMNS[1:]
        ]
        lines.append(",".join(cells))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _compare(path, reference, declared=400, run_stop=1.7391304347826089, ref_stop=None):
    return compare_force_csv(
        path,
        reference,
        config_name="s55_f115_p30",
        dt=DT,
        run_stop_time=run_stop,
        reference_stop_time=ref_stop if ref_stop is not None else run_stop,
        declared_steps=declared,
    )


def test_print_unit_is_one_unit_in_the_sixth_significant_figure():
    assert print_unit(7191.76) == pytest.approx(0.01, rel=1e-12)
    assert print_unit(5.39406e-13) == pytest.approx(1e-18, rel=1e-12)
    assert print_unit(-0.5) == pytest.approx(1e-6, rel=1e-12)
    assert print_unit(0.0) == 0.0


def test_identical_output_passes(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 400)
    result = _compare(csv, _reference(3478))
    assert result.passed, result.failures
    assert result.n_compared == 400


def test_round_off_and_a_last_digit_flip_pass(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    reference = _reference(3478)
    _write_csv(csv, 400)
    text = csv.read_text(encoding="utf-8").splitlines()
    # A flip of the last printed digit of a value near 1 (1.00000 against 0.999999 is the case
    # whose float difference exceeds one unit), and round-off in a physically-zero value of an
    # ordinary column (as E0b saw: 5.39406e-13 against 1.03941e-12).
    # Reference 0.999999 has a unit of 1e-6; the run printed 1.00000. Their parsed difference
    # is 1.0000000000287557e-06, more than one unit, so only the 1.5-unit tolerance passes it.
    reference.loc[10, "My"] = 0.999999
    reference.loc[10, "Fy"] = 5.39406e-13
    cells = text[11].split(",")
    cells[IB_PARTICLE_COLUMNS.index("My")] = "1"
    cells[IB_PARTICLE_COLUMNS.index("Fy")] = "1.03941e-12"
    text[11] = ",".join(cells)
    csv.write_text("\n".join(text) + "\n", encoding="utf-8")
    assert _compare(csv, reference).passed


def test_a_real_difference_near_the_peak_fails_naming_column_and_time(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"

    def bump(rows):
        rows[100]["Fz"] *= 1 + 1e-4

    _write_csv(csv, 400, edit=bump)
    result = _compare(csv, _reference(3478))
    assert not result.passed
    assert "Fz" in result.failures[0] and "0.05" in result.failures[0]


def test_init_iter_duplicates_pass(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 400, init_iter_rows=2)
    assert _compare(csv, _reference(3478)).passed


def test_duplicate_step_elsewhere_fails(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"

    def dup(rows):
        rows.insert(50, dict(rows[50]))

    _write_csv(csv, 400, edit=dup)
    result = _compare(csv, _reference(3478))
    assert not result.passed and "duplicate" in result.failures[0]


def test_truncated_run_fails_naming_the_first_missing_step(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 380)
    result = _compare(csv, _reference(3478))
    assert not result.passed
    assert "380" in result.failures[0]


def test_gap_in_the_run_fails(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"

    def gap(rows):
        del rows[200]

    _write_csv(csv, 400, edit=gap)
    result = _compare(csv, _reference(3478))
    assert not result.passed and "200" in result.failures[0]


def test_duplicate_reference_step_fails(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 400)
    reference = _reference(3478)
    reference = pd.concat([reference, reference.iloc[[123]]]).sort_values(
        "time", kind="stable"
    )
    result = _compare(csv, reference.reset_index(drop=True))
    assert not result.passed and "duplicate" in result.failures[0]


def test_reference_too_short_fails(tmp_path):
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 400)
    assert not _compare(csv, _reference(300)).passed


def test_c3_excludes_the_reference_clamped_final_row(tmp_path):
    """A 2-beat f085 reference ends in a clamped step; the 8-beat run has a full step there."""
    f_star = 0.85
    ref_stop = 2 / f_star
    ref_steps = round(ref_stop / DT)  # 4706; the last one is clamped
    reference = _reference(ref_steps)
    reference.loc[ref_steps - 1, "Fx"] *= 1.5  # the clamped step's force spike
    csv = tmp_path / "IB_Particle_1.csv"
    _write_csv(csv, 5000)  # the long run continues past the reference
    # declared=None: compare every reference step left after its clamped row is dropped.
    result = _compare(
        csv, reference, declared=None, run_stop=8 / f_star, ref_stop=ref_stop
    )
    assert result.passed, result.failures
    assert result.n_compared == ref_steps - 1


# --------------------------------------------------------------------------- field change


def test_identical_fields_give_zero_change():
    a = np.random.default_rng(0).normal(size=(4, 5, 6, 3))
    stats = field_change_stats(a, a.copy(), u_ref=2.0)
    assert stats["median"] == 0.0 and stats["fraction_above"] == 0.0


def test_uniform_offset_is_measured_in_reference_speed():
    a = np.zeros((4, 5, 6, 3))
    b = a.copy()
    b[..., 1] += 0.12 * 2.0
    stats = field_change_stats(b, a, u_ref=2.0)
    assert stats["median"] == pytest.approx(0.12, rel=1e-12)
    assert stats["fraction_above"] == 1.0
    c = a.copy()
    c[..., 0] += 0.08 * 2.0
    assert field_change_stats(c, a, u_ref=2.0)["fraction_above"] == 0.0
    exact = a.copy()
    exact[..., 0] += 0.1  # exactly 0.1 of u_ref = 1: not above
    assert field_change_stats(exact, a, u_ref=1.0)["fraction_above"] == 0.0


def test_vector_difference_norm_not_speed_difference():
    a = np.zeros((2, 2, 2, 3))
    a[..., 0] = 1.0
    b = np.zeros((2, 2, 2, 3))
    b[..., 1] = 1.0  # same speed, different direction
    assert field_change_stats(a, b, u_ref=1.0)["median"] == pytest.approx(np.sqrt(2))


@pytest.mark.parametrize(
    "a, b, u_ref",
    [
        (np.zeros((2, 2, 2, 3)), np.zeros((2, 2, 3, 3)), 1.0),
        (np.full((2, 2, 2, 3), np.nan), np.zeros((2, 2, 2, 3)), 1.0),
        (np.zeros((2, 2, 2, 3)), np.zeros((2, 2, 2, 3)), 0.0),
        (np.zeros((2, 2, 2, 2)), np.zeros((2, 2, 2, 2)), 1.0),
    ],
)
def test_bad_field_input_raises(a, b, u_ref):
    with pytest.raises(ValueError):
        field_change_stats(a, b, u_ref=u_ref)
