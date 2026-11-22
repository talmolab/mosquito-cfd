"""Optional phase harmonics in the force-surrogate inputs (add-surrogate-comparison-bench, 1a).

Scenarios: "Default harmonics are bitwise identical to the pre-option features", "Extra harmonics
are appended in a fixed order and recoverable from names", "Invalid harmonic counts and malformed
names are rejected" (force-surrogate spec, requirement "Surrogate input and target construction").
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import (
    FEATURE_COLUMNS,
    build_features,
    filter_converged_beat,
    phase_harmonics_from_features,
)

FINE_DATASET = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "prelim_sweep_fine"
    / "dataset.parquet"
)
_KINEMATICS = ["stroke_amp_deg", "frequency_fstar", "pitch_amp_deg"]


def _frozen_pre_change_features(df: pd.DataFrame) -> np.ndarray:
    """The five-column construction exactly as it stood before this change (frozen copy)."""
    phase = df["phase"].to_numpy(dtype=float)
    return np.column_stack(
        [
            df["stroke_amp_deg"].to_numpy(dtype=float),
            df["frequency_fstar"].to_numpy(dtype=float),
            df["pitch_amp_deg"].to_numpy(dtype=float),
            np.sin(2.0 * np.pi * phase),
            np.cos(2.0 * np.pi * phase),
        ]
    )


def _toy_frame() -> pd.DataFrame:
    phase = np.array([0.0, 0.1, 0.25, 0.4, 0.5, 0.77, 0.999])
    return pd.DataFrame(
        {
            "stroke_amp_deg": np.full(phase.size, 45.0),
            "frequency_fstar": np.full(phase.size, 1.0),
            "pitch_amp_deg": np.full(phase.size, 30.0),
            "phase": phase,
        }
    )


@pytest.fixture(scope="module")
def fine_converged() -> pd.DataFrame:
    df = pd.read_parquet(FINE_DATASET, columns=[*_KINEMATICS, "phase", "wingbeat"])
    return filter_converged_beat(df)


def test_default_and_h1_are_bitwise_the_pre_change_features(fine_converged):
    expected = _frozen_pre_change_features(fine_converged)
    for x, names in (
        build_features(fine_converged),
        build_features(fine_converged, phase_harmonics=1),
    ):
        assert x.dtype == expected.dtype and x.shape == expected.shape
        assert x.tobytes() == expected.tobytes()
        assert names == FEATURE_COLUMNS


def test_three_harmonics_append_in_a_fixed_order():
    df = _toy_frame()
    x1, _ = build_features(df)
    x3, names = build_features(df, phase_harmonics=3)
    assert names == [
        *FEATURE_COLUMNS,
        "phase_sin_h2",
        "phase_cos_h2",
        "phase_sin_h3",
        "phase_cos_h3",
    ]
    assert x3.shape == (len(df), 9)
    assert x3[:, :5].tobytes() == x1.tobytes()
    phase = df["phase"].to_numpy()
    for col, h in ((5, 2), (7, 3)):
        np.testing.assert_allclose(
            x3[:, col], np.sin(2 * np.pi * h * phase), atol=1e-15
        )
        np.testing.assert_allclose(
            x3[:, col + 1], np.cos(2 * np.pi * h * phase), atol=1e-15
        )


@pytest.mark.parametrize("h", [1, 2, 3, 4, 5])
def test_harmonic_count_round_trips_through_the_names(h):
    _, names = build_features(_toy_frame(), phase_harmonics=h)
    assert len(names) == 3 + 2 * h
    assert phase_harmonics_from_features(names) == h


def test_numpy_integer_harmonic_count_is_accepted():
    _, names = build_features(_toy_frame(), phase_harmonics=np.int64(3))
    assert phase_harmonics_from_features(names) == 3


@pytest.mark.parametrize("bad", [0, -1, np.int64(0)])
def test_non_positive_harmonic_count_raises_value_error(bad):
    with pytest.raises(ValueError, match="phase_harmonics"):
        build_features(_toy_frame(), phase_harmonics=bad)


@pytest.mark.parametrize("bad", [2.5, True, False, "3", None, np.timedelta64(3, "s")])
def test_non_integer_harmonic_count_raises_type_error(bad):
    with pytest.raises(TypeError, match="phase_harmonics"):
        build_features(_toy_frame(), phase_harmonics=bad)


@pytest.mark.parametrize(
    ("names", "match"),
    [
        (
            [*FEATURE_COLUMNS, "phase_sin_h3", "phase_cos_h3"],
            "phase_sin_h3",
        ),  # gap: no h2
        (
            [
                *FEATURE_COLUMNS,
                "phase_sin_h2",
                "phase_cos_h2",
                "phase_sin_h2",
                "phase_cos_h2",
            ],
            "phase_sin_h2",
        ),  # duplicate
        ([*FEATURE_COLUMNS, "phase_tan_h2", "phase_cos_h2"], "phase_tan_h2"),  # unknown
        (
            [*FEATURE_COLUMNS, "phase_cos_h2", "phase_sin_h2"],
            "phase_cos_h2",
        ),  # wrong order
        ([*FEATURE_COLUMNS, "phase_sin_h2"], "phase_sin_h2"),  # unpaired
        (FEATURE_COLUMNS[:4], "phase_cos"),  # missing a base column
        (["reynolds", *FEATURE_COLUMNS[1:]], "reynolds"),  # unknown base column
    ],
)
def test_malformed_feature_names_raise_value_error(names, match):
    with pytest.raises(ValueError, match=match):
        phase_harmonics_from_features(names)
