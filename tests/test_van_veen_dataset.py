"""The van Veen model against the paper's own published CFD forces.

``tests/fixtures/van_veen_2022/`` holds two files from the paper's supplementary dataset (see the
README beside them). These tests check the moment definitions, the unit of eq 3.12 and the pinned
coefficients against data the authors published, instead of against our reading of the text.

The error bounds are regression bounds set after the results were seen. What these tests cannot
detect: an error of a few per cent in one normal coefficient; tangential behaviour above about
27 degrees (rows at 27 degrees or less carry 80 % of the squared tangential force); and anything
about ``model_inputs``, because every row is a single stroke at a constant angle of attack.
"""

import hashlib
import re
import subprocess
from pathlib import Path

import numpy as np
import pytest
from scipy.io import loadmat

from mosquito_cfd.benchmarks import van_veen_model as vv

_DIR = Path("tests/fixtures/van_veen_2022")
_FILES = ("fruitfly.mat", "wing_geometry_DB.mat")
# The paper's density is not in the text available to this project. With 1 a free fit of the
# normal terms lands inside the printed intervals (test below); a fitted density would absorb an
# error in the 3.13 coefficient.
_RHO = 1.0


def _columns(name: str) -> dict[str, np.ndarray]:
    """Numeric columns of a per-wing file as float64 (the file stores small integer types)."""
    raw = loadmat(str(_DIR / name))
    return {
        k: v.ravel().astype(np.float64)
        for k, v in raw.items()
        if not k.startswith("__")
    }


@pytest.fixture(scope="module")
def geometry() -> dict:
    """``wing_geometry_DB.mat`` with the wing names as a list of str."""
    db = loadmat(str(_DIR / "wing_geometry_DB.mat"))
    db["names"] = [str(w[0][0]) for w in db["wing"]]
    return db


@pytest.fixture(scope="module")
def fruitfly(geometry) -> dict[str, np.ndarray | float]:
    """Fruit-fly rows plus that wing's stored moments."""
    data: dict = _columns("fruitfly.mat")
    i = geometry["names"].index("fruitfly")
    for key in ("Syy", "Scy", "Swe"):
        data[key] = float(geometry[key][i, 0])
    return data


def _rel_error(model: np.ndarray, data: np.ndarray) -> float:
    return float(np.sqrt(np.sum((model - data) ** 2) / np.sum(data**2)))


def _model(ff: dict) -> tuple[np.ndarray, np.ndarray]:
    """Model ``(F_x, F_z)`` at every fruit-fly row, through the public ``total_force``."""
    return vv.total_force(
        np.radians(ff["aoa"]),
        ff["sr"],
        ff["sa"],
        s_yy=ff["Syy"],
        s_cy=ff["Scy"],
        s_we=ff["Swe"],
        rho=_RHO,
    )


def test_fixtures_are_the_published_files():
    """Each fixture's SHA-256 equals the value in the README, and all three files are tracked."""
    readme = (_DIR / "README.md").read_text(encoding="utf-8")
    for name in _FILES:
        digest = hashlib.sha256((_DIR / name).read_bytes()).hexdigest()
        row = re.search(rf"`{re.escape(name)}` \| `([0-9a-f]{{64}})`", readme)
        assert row is not None, name
        assert digest == row.group(1), name
    tracked = subprocess.run(
        ["git", "ls-files", str(_DIR)], capture_output=True, text=True, check=True
    ).stdout.split()
    assert {Path(p).name for p in tracked} >= {*_FILES, "README.md"}


def test_loader_casts_to_float64(fruitfly):
    """The stroke rate is stored as uint16; squaring it uncast would overflow."""
    assert loadmat(str(_DIR / "fruitfly.mat"))["sr"].dtype == np.uint16
    assert fruitfly["sr"].dtype == np.float64
    assert len(fruitfly["aoa"]) == 1089
    assert int(np.sum(fruitfly["sa"] == 0)) == 43


def test_stored_moments_are_the_integrals_the_module_computes(geometry):
    """Stored ``Scy`` and ``Swe`` equal ``profile_moments`` of the stored chord profile."""
    names = geometry["names"]
    assert len(names) == 14
    clipped = 0
    for i, name in enumerate(names):
        c, y = geometry["c"][i, 0].ravel(), geometry["y"][i, 0].ravel()
        clipped += int(np.sum(c**3 * y**3 < 0))
        s_cy, s_we = vv.profile_moments(c, y)
        assert np.isfinite(s_we), name
        assert s_cy == pytest.approx(float(geometry["Scy"][i, 0]), rel=2e-3), name
        assert s_we == pytest.approx(float(geometry["Swe"][i, 0]), rel=2e-3), name
    assert clipped == 3  # the mosquito profile starts a hair inboard of the hinge

    ellipses = [i for i, n in enumerate(names) if n.startswith("ellipse")]
    assert len(ellipses) == 12
    for i in ellipses:
        closed = (
            float(geometry["chord_max"][i, 0]) ** 2
            * float(geometry["span"][i, 0]) ** 2
            / 3.0
        )
        assert float(geometry["Scy"][i, 0]) == pytest.approx(closed, rel=0.01)


def test_nominal_s_cy_over_s_yy_matches_the_papers_ellipse(geometry):
    """Our nominal ``S_cy / S_yy`` is within 1 % of the paper's 3 mm ellipse (same aspect ratio)."""
    i = geometry["names"].index("ellipse_3.00e-03")
    stored = float(geometry["Scy"][i, 0]) / float(geometry["Syy"][i, 0])
    # Nominal ellipse, span 3, chord 1, root at the hinge: integral c*y**2 dy = 5*pi/64*c*R**3.
    s_yy_nominal = 5.0 * np.pi / 64.0 * 1.0 * 3.0**3
    ours = vv.compute_wing_area_moments().s_cy / s_yy_nominal
    assert ours == pytest.approx(stored, rel=0.01)


def test_every_row_is_inside_the_input_domain(fruitfly):
    """No row raises: angle of attack 9-90 degrees, stroke rate positive."""
    assert fruitfly["aoa"].min() == 9 and fruitfly["aoa"].max() == 90
    assert fruitfly["sr"].min() > 0
    fx, fz = _model(fruitfly)
    assert np.isfinite(fx).all() and np.isfinite(fz).all()


def test_model_reproduces_the_published_normal_force(fruitfly):
    """Normal force: relative error below 0.03 over all 1,089 rows (observed 0.016)."""
    _, fz = _model(fruitfly)
    assert _rel_error(fz, fruitfly["Fz"]) < 0.03


def test_model_reproduces_the_published_tangential_force(fruitfly):
    """Tangential force, compared as ``-Fx``: relative error below 0.25 (observed 0.16).

    The dataset's x-axis points against the tangential force the model returns. The bound admits
    both of the paper's printed coefficient sets; it guards the unit of eq 3.12 and the signs of
    the two tangential terms, mainly at 27 degrees and below.
    """
    fx, _ = _model(fruitfly)
    assert _rel_error(fx, -fruitfly["Fx"]) < 0.25


def test_free_fit_of_the_normal_terms_lands_inside_the_pinned_intervals(fruitfly):
    """A least-squares fit of the three normal terms agrees with the pinned 95 % intervals."""
    a, w, wd = np.radians(fruitfly["aoa"]), fruitfly["sr"], fruitfly["sa"]
    basis = np.column_stack(
        [
            0.5 * _RHO * w**2 * fruitfly["Syy"] * np.sin(a),
            _RHO * wd * fruitfly["Scy"] * np.sin(a),
            0.5
            * _RHO
            * w
            * np.sign(wd)
            * np.sqrt(np.abs(wd))
            * fruitfly["Swe"]
            * np.sin(a),
        ]
    )
    fit, *_ = np.linalg.lstsq(basis, fruitfly["Fz"], rcond=None)
    for value, (lo, hi) in zip(
        fit, (vv.C_FZA_TRANSL_CI, vv.C_FZA_AM_CI, vv.C_FZA_WE_CI), strict=True
    ):
        assert lo <= value <= hi, (fit, lo, hi)
