"""Physics guard for the wing force/moment sign convention (issue #109).

IAMReX's ``ib_force``/``ib_moment`` (the IB-particle CSV's ``Fx..Mz``) are what the wing exerts on the
**fluid**. The evidence is the second law: for a rigid wing rotating about a fixed hinge,
``M_hinge · Ω`` is the power the IB forcing delivers to the fluid. Starting from rest, the cumulative
work ``W(t) = ∫ M_hinge · Ω dt`` should never go negative. This is an empirical check with measured
margins, not a theorem, because the domain has open outflow boundaries
(``docs/coordinate-convention.md#force-and-moment-sign``).

These tests recompute that inequality from committed data, so the convention is pinned by physics
rather than by re-running the extractor's algebra:

- the raw columns satisfy the on-fluid inequality;
- raw force and moment share one convention;
- the coefficients satisfy the on-wing mirror inequality.

The coefficient guard fails with :class:`CoefficientsOnFluid` while the committed corpus still carries
the solver's on-fluid sign. Design: ``openspec/changes/fix-wing-force-sign-convention/design.md`` D3.
"""

from __future__ import annotations

import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.benchmarks.flapping_wing import STEADY_WINDOW_T0
from mosquito_cfd.benchmarks.wing_kinematics import angular_velocity
from mosquito_cfd.force_surrogate import shift_moment_reference
from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value

_ROOT = Path(__file__).resolve().parents[1]
_CORPORA = ("prelim_sweep", "prelim_sweep_fine")
_FLAPPING = _ROOT / "examples" / "flapping_wing"
# Validation CSV -> (deck, run metadata whose inputs.hash pins that deck's sha256). All five
# flapping-wing decks share particle_inputs (4, 2, 4), so X,Y,Z alone cannot identify the deck.
_VALIDATION_RUNS = {
    "forces_t2a_newconv.csv": ("inputs.3d.validation", "run_metadata_t2a.json"),
    "forces_medium.csv": ("inputs.3d.convergence_medium", "run_metadata_t3b.json"),
    "forces_fine.csv": ("inputs.3d.convergence_fine", "run_metadata_t3c.json"),
}
_HINGE = np.array([4.0, 0.5, 4.0])
_N_CORPUS_CONFIGS = 54
_N_RUNS = _N_CORPUS_CONFIGS + len(_VALIDATION_RUNS)


class CoefficientsOnFluid(AssertionError):
    """The coefficient sign predicates fail: the coefficients carry the solver's on-fluid sign."""


@dataclass(frozen=True)
class _Run:
    name: str
    time: np.ndarray
    omega: np.ndarray  # (n, 3) lab-frame angular velocity
    force: np.ndarray  # (n, 3) raw solver Fx..Fz
    moment_origin: np.ndarray  # (n, 3) raw solver Mx..Mz, about the particle origin
    moment_hinge: np.ndarray  # (n, 3) raw moments shifted to the hinge
    cf: np.ndarray | None  # (n, 3) committed CF_x..CF_z (corpus runs only)
    cf_m: np.ndarray | None  # (n, 3) committed CF_mx..CF_mz (corpus runs only)


def _deck_values(text: str, keys: tuple[str, ...]) -> np.ndarray:
    return np.array([read_deck_value(text, f"particle_inputs.{k}") for k in keys])


def _omega(time: np.ndarray, deck_text: str) -> np.ndarray:
    freq, stroke, pitch, deviation = _deck_values(
        deck_text,
        (
            "kinematics_frequency",
            "kinematics_stroke_amp",
            "kinematics_pitch_amp",
            "kinematics_deviation_amp",
        ),
    )
    return angular_velocity(
        time,
        frequency=freq,
        stroke_amp_rad=np.radians(stroke),
        pitch_amp_rad=np.radians(pitch),
        deviation_amp_rad=np.radians(deviation),
    )


def _shift(moment: np.ndarray, force: np.ndarray, offset: np.ndarray) -> np.ndarray:
    return np.column_stack(shift_moment_reference(*moment.T, *force.T, offset=offset))


@functools.cache
def _corpus_runs() -> tuple[_Run, ...]:
    runs = []
    for corpus in _CORPORA:
        base = _ROOT / "examples" / corpus
        manifest = json.loads((base / "sweep_manifest.json").read_text("utf-8"))
        df = pd.read_parquet(base / "dataset.parquet")
        for config in manifest["configs"]:
            deck = (base / config["input_file"]).read_text(encoding="utf-8")
            origin = _deck_values(deck, ("x", "y", "z"))
            hinge = _deck_values(deck, ("hinge_x", "hinge_y", "hinge_z"))
            sub = df[df["config_name"] == config["name"]].sort_values("time")
            t = sub["time"].to_numpy(float)
            force = sub[["Fx", "Fy", "Fz"]].to_numpy(float)
            moment = sub[["Mx", "My", "Mz"]].to_numpy(float)
            runs.append(
                _Run(
                    name=f"{corpus}/{config['name']}",
                    time=t,
                    omega=_omega(t, deck),
                    force=force,
                    moment_origin=moment,
                    moment_hinge=_shift(moment, force, origin - hinge),
                    cf=sub[["CF_x", "CF_y", "CF_z"]].to_numpy(float),
                    cf_m=sub[["CF_mx", "CF_my", "CF_mz"]].to_numpy(float),
                )
            )
    return tuple(runs)


@functools.cache
def _validation_runs() -> tuple[_Run, ...]:
    runs = []
    for csv_name, (deck_name, metadata_name) in _VALIDATION_RUNS.items():
        deck_bytes = (_FLAPPING / deck_name).read_bytes()
        recorded = json.loads((_FLAPPING / metadata_name).read_text("utf-8"))
        assert hashlib.sha256(deck_bytes).hexdigest() == recorded["inputs"]["hash"], (
            f"{deck_name} is not the deck {metadata_name} records for {csv_name}"
        )
        deck = deck_bytes.decode("utf-8")
        hinge = _deck_values(deck, ("hinge_x", "hinge_y", "hinge_z"))
        np.testing.assert_array_equal(hinge, _HINGE)
        raw = pd.read_csv(_FLAPPING / csv_name)
        raw = raw.drop_duplicates(subset="iStep", keep="last")  # ns.init_iter rows
        t = raw["time"].to_numpy(float)
        assert np.all(np.diff(t) > 0), f"{csv_name}: time not strictly increasing"
        origin = raw[["X", "Y", "Z"]].to_numpy(float)
        # Sanity only: every flapping-wing deck shares this particle origin.
        np.testing.assert_array_equal(
            np.unique(origin, axis=0), [_deck_values(deck, ("x", "y", "z"))]
        )
        force = raw[["Fx", "Fy", "Fz"]].to_numpy(float)
        moment = raw[["Mx", "My", "Mz"]].to_numpy(float)
        runs.append(
            _Run(
                name=f"flapping_wing/{csv_name}",
                time=t,
                omega=_omega(t, deck),
                force=force,
                moment_origin=moment,
                moment_hinge=_shift(moment, force, origin[0] - hinge),
                cf=None,
                cf_m=None,
            )
        )
    return tuple(runs)


def _work(time: np.ndarray, moment: np.ndarray, omega: np.ndarray) -> np.ndarray:
    """Cumulative trapezoidal work ``∫ moment · Ω dt`` from the first row (``W[0] = 0``)."""
    power = np.einsum("ij,ij->i", moment, omega)
    return np.concatenate(
        [[0.0], np.cumsum(0.5 * (power[1:] + power[:-1]) * np.diff(time))]
    )


def _late(time: np.ndarray) -> np.ndarray:
    return time >= STEADY_WINDOW_T0


def _assert_runs_are_usable(runs: tuple[_Run, ...], expected: int) -> None:
    """Non-vacuity: the guard covers every run, each with a usable late window and finite data."""
    assert len(runs) == expected, f"expected {expected} runs, got {len(runs)}"
    for run in runs:
        assert _late(run.time).sum() >= 2, f"{run.name}: fewer than 2 late rows"
        assert np.isfinite(run.force).all() and np.isfinite(run.moment_hinge).all(), (
            f"{run.name}: non-finite force or moment"
        )


def _work_violations(name: str, time, moment, omega, *, sign: int) -> list[str]:
    """Rows where ``sign·W`` or its late increment goes negative, or ``W`` is non-finite."""
    work = sign * _work(time, moment, omega)
    if not np.isfinite(work).all():
        return [f"{name}: non-finite work"]
    late = _late(time)
    increment = work[late] - work[np.argmax(late)]
    problems = []
    if (work < 0).any():
        problems.append(f"{name}: min {sign:+d}·W = {work.min():.4g}")
    if (increment < 0).any():
        problems.append(f"{name}: min late {sign:+d}·ΔW = {increment.min():.4g}")
    return problems


def test_raw_ib_force_does_net_positive_work_on_the_fluid():
    """Raw ``ib_force``/``ib_moment`` are on the fluid: ``W ≥ 0`` at every row, with no tolerance.

    The late increment ``W(t) − W₀`` (``W₀`` at the first row with ``t ≥ STEADY_WINDOW_T0``) is also
    ``≥ 0``, so the verdict does not rest on the impulsive start. Measured at a2e8f64: the minimum is
    exactly 0 (at ``t = 0``) in all 57 runs.
    """
    runs = _corpus_runs() + _validation_runs()
    _assert_runs_are_usable(runs, _N_RUNS)
    violations = [
        v
        for run in runs
        for v in _work_violations(
            run.name, run.time, run.moment_hinge, run.omega, sign=+1
        )
    ]
    assert not violations, (
        "raw ib_force no longer does net positive work:\n" + "\n".join(violations)
    )


def test_raw_force_and_moment_share_one_convention():
    """On the solver's UNSHIFTED columns, ``corr(Mz, −Fx) > 0`` and ``corr(Mx, Fz) > 0`` per run.

    A force at a ``+y`` span arm gives ``Mz ≈ −r·Fx`` and ``Mx ≈ r·Fz``. The unshifted moments are used
    because the hinge shift itself adds ``−1.5·Fx`` to ``Mz``, which would make a hinge-referenced
    check correlate ``Fx`` with itself. Measured minima at a2e8f64: +0.870 and +0.740.
    """
    runs = _corpus_runs() + _validation_runs()
    _assert_runs_are_usable(runs, _N_RUNS)
    bad = []
    for run in runs:
        mx, _, mz = run.moment_origin.T
        fx, _, fz = run.force.T
        c_z, c_x = np.corrcoef(mz, -fx)[0, 1], np.corrcoef(mx, fz)[0, 1]
        if not (c_z > 0 and c_x > 0):
            bad.append(f"{run.name}: corr(Mz,-Fx)={c_z:.3f} corr(Mx,Fz)={c_x:.3f}")
    assert not bad, "raw force and moment disagree in sign:\n" + "\n".join(bad)


@pytest.mark.xfail(
    strict=True,
    raises=CoefficientsOnFluid,
    reason="#109: the committed corpus coefficients carry the solver's on-fluid sign "
    "until re-extraction",
)
def test_coefficients_are_the_ib_force_on_the_wing():
    """Coefficients are on the wing: ``W_wing = ∫ CF_m · Ω dt ≤ 0`` and ``corr(CF_mz, −CF_x) > 0``.

    The correlation check catches a half-flip inside extraction (only the force or only the moment
    coefficients negated). Only the sign predicates raise :class:`CoefficientsOnFluid`; the
    non-vacuity checks are plain assertions, so a broken run set fails even under the xfail.
    """
    runs = _corpus_runs()
    _assert_runs_are_usable(runs, _N_CORPUS_CONFIGS)
    problems = []
    for run in runs:
        problems += _work_violations(run.name, run.time, run.cf_m, run.omega, sign=-1)
        c = np.corrcoef(run.cf_m[:, 2], -run.cf[:, 0])[0, 1]
        if not c > 0:
            problems.append(f"{run.name}: corr(CF_mz, -CF_x) = {c:.3f}")
    if problems:
        raise CoefficientsOnFluid(
            f"{len(problems)} coefficient sign violation(s):\n"
            + "\n".join(problems[:10])
        )
