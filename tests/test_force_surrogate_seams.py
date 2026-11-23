"""Per-seed seams fit_seed and predict_frame (add-surrogate-comparison-bench, 1c; CPU tier).

Scenarios "The per-seed seams are torch-free up to the model" and "predict_frame builds the fit's
own features (CPU tier)" (force-surrogate spec, requirement "PhysicsNeMo force-coefficient
regressor"). build_model / train_model / predict are replaced by recorders, so the real carve,
feature and standardiser code runs on the CPU-only CI runner.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate import train
from mosquito_cfd.force_surrogate.train import (
    FEATURE_COLUMNS,
    TARGET_COLUMNS,
    SplitAssignment,
    Standardizer,
    filter_converged_beat,
    make_config_splits,
)

REPO = Path(__file__).resolve().parents[1]
FINE_DATASET = REPO / "examples" / "prelim_sweep_fine" / "dataset.parquet"
FIT_KWARGS = {"epochs": 7, "hidden": 64, "num_layers": 3, "lr": 1e-3, "device": "cpu"}
SEEDS = (1234, 1235, 1236, 1237, 1238)


def _array_key(a):
    a = np.asarray(a)
    return ("array", str(a.dtype), a.shape, a.tobytes())


def _freeze(value):
    if isinstance(value, np.ndarray):
        return _array_key(value)
    return value


class _Recorder:
    """Records build_model / train_model / predict calls; returns shape-correct dummies."""

    def __init__(self):
        self.calls = []

    def build_model(self, n_in, n_out, **kwargs):
        self.calls.append(("build_model", (n_in, n_out), _frozen_kwargs(kwargs)))
        return "model"

    def train_model(self, model, x, y, **kwargs):
        self.calls.append(
            (
                "train_model",
                (model, _array_key(x), _array_key(y)),
                _frozen_kwargs(kwargs),
            )
        )
        return []

    def predict(self, model, x, **kwargs):
        self.calls.append(("predict", (model, _array_key(x)), _frozen_kwargs(kwargs)))
        return np.zeros((len(x), len(TARGET_COLUMNS)))


def _frozen_kwargs(kwargs):
    return tuple(sorted((k, _freeze(v)) for k, v in kwargs.items()))


@pytest.fixture
def recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(train, "build_model", rec.build_model)
    monkeypatch.setattr(train, "train_model", rec.train_model)
    monkeypatch.setattr(train, "predict", rec.predict)
    return rec


@pytest.fixture
def split_counter(monkeypatch):
    counter = {"n": 0}
    real = train.make_config_splits

    def counting(*args, **kwargs):
        counter["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(train, "make_config_splits", counting)
    return counter


@pytest.fixture(scope="module")
def fine() -> pd.DataFrame:
    return filter_converged_beat(pd.read_parquet(FINE_DATASET))


def _frozen_expected_calls(df, split, *, seed, harmonics_cols):
    """The calls the pre-change _fit_one_seed made, rebuilt from its frozen construction."""
    cfg = df["config_name"].to_numpy()
    train_mask = np.isin(cfg, split.train_configs)
    val_mask = np.isin(cfg, split.val_configs)
    test_mask = np.isin(cfg, split.test_configs)
    phase = df["phase"].to_numpy(dtype=float)
    columns = [
        df["stroke_amp_deg"].to_numpy(dtype=float),
        df["frequency_fstar"].to_numpy(dtype=float),
        df["pitch_amp_deg"].to_numpy(dtype=float),
        np.sin(2.0 * np.pi * phase),
        np.cos(2.0 * np.pi * phase),
    ]
    for h in range(2, harmonics_cols + 1):
        columns += [np.sin(2.0 * np.pi * h * phase), np.cos(2.0 * np.pi * h * phase)]
    x_all = np.column_stack(columns)
    xz = Standardizer().fit(x_all[train_mask]).transform(x_all)
    y_all = df[TARGET_COLUMNS].to_numpy(dtype=float)
    yz = Standardizer().fit(y_all[train_mask]).transform(y_all)
    return [
        (
            "build_model",
            (x_all.shape[1], len(TARGET_COLUMNS)),
            _frozen_kwargs(
                {
                    "seed": seed,
                    "hidden": FIT_KWARGS["hidden"],
                    "num_layers": FIT_KWARGS["num_layers"],
                }
            ),
        ),
        (
            "train_model",
            ("model", _array_key(xz[train_mask]), _array_key(yz[train_mask])),
            _frozen_kwargs(
                {
                    "epochs": FIT_KWARGS["epochs"],
                    "seed": seed,
                    "lr": FIT_KWARGS["lr"],
                    "device": FIT_KWARGS["device"],
                    "x_val": xz[val_mask],
                    "y_val": yz[val_mask],
                }
            ),
        ),
        (
            "predict",
            ("model", _array_key(xz[test_mask])),
            _frozen_kwargs({"device": "cpu"}),
        ),
        (
            "predict",
            ("model", _array_key(xz[val_mask])),
            _frozen_kwargs({"device": "cpu"}),
        ),
    ]


def test_default_path_carves_once_and_matches_the_frozen_construction(
    fine, recorder, split_counter
):
    seed = 1234
    train._fit_one_seed(fine, seed=seed, n_val_configs=3, **FIT_KWARGS)
    assert split_counter["n"] == 1
    split = make_config_splits(fine, seed=seed, n_val_configs=3)
    assert recorder.calls == _frozen_expected_calls(
        fine, split, seed=seed, harmonics_cols=1
    )
    assert recorder.calls[0][1][0] == 5


@pytest.mark.parametrize("seed", SEEDS)
def test_fit_seed_with_the_shipped_carve_is_the_default_path(fine, monkeypatch, seed):
    default, explicit = _Recorder(), _Recorder()
    for rec, run in (
        (
            default,
            lambda: train._fit_one_seed(fine, seed=seed, n_val_configs=3, **FIT_KWARGS),
        ),
        (
            explicit,
            lambda: train.fit_seed(
                fine,
                make_config_splits(fine, seed=seed, n_val_configs=3),
                seed=seed,
                phase_harmonics=1,
                **FIT_KWARGS,
            ),
        ),
    ):
        monkeypatch.setattr(train, "build_model", rec.build_model)
        monkeypatch.setattr(train, "train_model", rec.train_model)
        monkeypatch.setattr(train, "predict", rec.predict)
        run()
    assert explicit.calls == default.calls


def _face_split(df, setting="stroke_amp_deg", value=55.0):
    """A face split built by hand (surrogate_bench.splits arrives in a later group)."""
    by_config = df.groupby("config_name")[setting].first()
    test = sorted(by_config.index[by_config == value])
    rest = sorted(by_config.index[by_config != value])
    return SplitAssignment(
        train_configs=rest[3:], val_configs=rest[:3], test_configs=test
    )


def test_fit_seed_with_an_explicit_split_uses_it_verbatim(
    fine, recorder, split_counter
):
    split = _face_split(fine)
    fit = train.fit_seed(fine, split, seed=1234, phase_harmonics=3, **FIT_KWARGS)
    assert split_counter["n"] == 0
    assert fit.split == split
    assert recorder.calls == _frozen_expected_calls(
        fine, split, seed=1234, harmonics_cols=3
    )
    assert recorder.calls[0][1][0] == 9
    assert fit.feature_names[-1] == "phase_cos_h3"


_INVALID_SPLITS = {
    "empty train": ([], ["a"], ["b"], "train"),
    "empty validation": (["a"], [], ["b"], "validation"),
    "empty test": (["a"], ["b"], [], "test"),
    "overlap": (["a", "b"], ["c"], ["b"], "overlap"),
    "absent configuration": (["a"], ["b"], ["zzz_missing"], "zzz_missing"),
}


def test_invalid_splits_raise_before_any_model_code_without_torch(tmp_path):
    """Each invalid split raises ValueError; torch imports are blocked in the subprocess.

    If validation came after the model calls, the blocked torch import would surface as
    ImportError instead of the expected ValueError.
    """
    script = textwrap.dedent(
        f"""
        import importlib.abc, sys
        BLOCKED = ("torch", "physicsnemo")
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("blocked import: " + name)
                return None
        sys.meta_path.insert(0, Block())
        import pandas as pd
        from mosquito_cfd.force_surrogate.train import fit_seed, SplitAssignment
        names = ["a", "b", "c", "d"]
        df = pd.DataFrame({{
            "config_name": names, "phase": [0.1, 0.2, 0.3, 0.4], "wingbeat": [1] * 4,
            "split": ["train"] * 4, "stroke_amp_deg": [35.0, 45.0, 55.0, 45.0],
            "frequency_fstar": [1.0] * 4, "pitch_amp_deg": [45.0] * 4,
            **{{c: [0.0] * 4 for c in {list(TARGET_COLUMNS)!r}}},
        }})
        cases = {_INVALID_SPLITS!r}
        for label, (tr, va, te, needle) in cases.items():
            split = SplitAssignment(train_configs=tr, val_configs=va, test_configs=te)
            try:
                fit_seed(df, split, seed=1, phase_harmonics=1, epochs=1)
            except ValueError as exc:
                assert needle in str(exc), (label, str(exc))
                print("OK", label)
            else:
                raise SystemExit("no error for " + label)
        assert not any(m.split(".")[0] in BLOCKED for m in sys.modules), "torch imported"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.count("OK ") == len(_INVALID_SPLITS)


def test_new_names_are_exported():
    from mosquito_cfd import force_surrogate

    for name in ("fit_seed", "predict_frame", "phase_harmonics_from_features"):
        assert name in force_surrogate.__all__
        assert getattr(force_surrogate, name) is getattr(train, name)


# --- Scenario: predict_frame builds the fit's own features (CPU tier) ---------------------


def _toy_rows(n=6):
    rng = np.random.default_rng(0)
    return pd.DataFrame(
        {
            "stroke_amp_deg": rng.choice([35.0, 45.0, 55.0], n),
            "frequency_fstar": rng.choice([0.85, 1.0, 1.15], n),
            "pitch_amp_deg": rng.choice([30.0, 45.0, 60.0], n),
            "phase": rng.uniform(0, 1, n),
        }
    )


def _h3_fit():
    rng = np.random.default_rng(1)
    names = [
        *FEATURE_COLUMNS,
        "phase_sin_h2",
        "phase_cos_h2",
        "phase_sin_h3",
        "phase_cos_h3",
    ]
    feature_std = Standardizer().fit(rng.normal(3.0, 2.0, (40, len(names))))
    target_std = Standardizer().fit(rng.normal(-1.0, 0.5, (40, len(TARGET_COLUMNS))))
    return train.SeedFit(
        split=SplitAssignment([], [], []),
        model="model",
        feature_std=feature_std,
        target_std=target_std,
        feature_names=names,
        history=[],
        x_test=np.zeros((0, len(names))),
        y_pred=np.zeros((0, len(TARGET_COLUMNS))),
        val_aggregate={},
    )


def test_predict_frame_builds_the_fits_own_standardised_features(monkeypatch):
    fit, frame = _h3_fit(), _toy_rows()
    seen = {}
    raw = np.arange(len(frame) * len(TARGET_COLUMNS), dtype=float).reshape(
        len(frame), -1
    )

    def fake_predict(model, x, *, device="cpu"):
        seen["model"], seen["x"], seen["device"] = model, np.asarray(x), device
        return raw

    monkeypatch.setattr(train, "predict", fake_predict)
    out = train.predict_frame(fit, frame, device="cpu")
    x, _ = train.build_features(frame, phase_harmonics=3)
    assert seen["model"] == "model" and seen["x"].shape == (len(frame), 9)
    assert seen["x"].tobytes() == fit.feature_std.transform(x).tobytes()
    assert out.tobytes() == fit.target_std.inverse_transform(raw).tobytes()


def test_predict_frame_rejects_a_frame_missing_a_kinematics_column(monkeypatch):
    monkeypatch.setattr(train, "predict", lambda *a, **k: pytest.fail("predicted"))
    with pytest.raises(ValueError, match="pitch_amp_deg"):
        train.predict_frame(
            _h3_fit(), _toy_rows().drop(columns="pitch_amp_deg"), device="cpu"
        )
