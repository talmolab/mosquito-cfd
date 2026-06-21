"""GPU/torch-tier tests for force_surrogate.train (PR5).

Every test is ``@pytest.mark.gpu``: it needs a CUDA device and the optional ``train`` group
(PhysicsNeMo/torch). The ``conftest.py`` autoskip makes them inert when unavailable, and CI also
deselects them with ``-m "not gpu"`` — so these run on the local RTX A5000 (``uv run pytest -m
gpu``), never in CI.

**No top-level ``import torch``** — torch is imported *inside* each test (after the skip guard has
fired), so collection on a CPU-only host without the ``train`` group never errors.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mosquito_cfd.force_surrogate.train import (
    TARGET_COLUMNS,
    build_model,
    build_training_metadata,
    predict,
    run_training,
    train_model,
)

pytestmark = pytest.mark.gpu

N_IN = 5
N_OUT = 6
DIGEST = "ghcr.io/talmolab/mosquito-cfd@sha256:" + "b" * 64
HOLDOUT = ["s35_f085_p45", "s45_f085_p60"]


def _toy_parquet(path):
    """Write a tiny dataset.parquet (train + holdout configs, 2 wingbeats) for a round-trip."""
    rng = np.random.default_rng(0)
    frames = []
    names = [f"train_{i:02d}" for i in range(8)] + HOLDOUT
    for idx, name in enumerate(names):
        split = "holdout" if name in HOLDOUT else "train"
        stroke, fstar, pitch = (
            float(rng.choice([35.0, 45.0, 55.0])),
            float(rng.choice([0.85, 1.0, 1.15])),
            float(rng.choice([30.0, 45.0, 60.0])),
        )
        for beat in (0, 1):
            phase = np.linspace(0.0, 1.0, 6, endpoint=False)
            cf_x = 0.1 * stroke / 45.0 + 0.05 * np.sin(2 * np.pi * phase)
            cf_z = 0.2 * fstar + 0.03 * np.cos(2 * np.pi * phase)
            frames.append(
                pd.DataFrame(
                    {
                        "config_name": name,
                        "index": idx,
                        "time": (beat + phase) / fstar,
                        "phase": phase,
                        "wingbeat": beat,
                        "stroke_amp_deg": stroke,
                        "frequency_fstar": fstar,
                        "pitch_amp_deg": pitch,
                        "reynolds": 50.0,
                        "split": split,
                        "Fx": cf_x,
                        "Fy": 0.0,
                        "Fz": cf_z,
                        "Mx": 0.0,
                        "My": 0.0,
                        "Mz": 0.0,
                        "CF_x": cf_x,
                        "CF_y": 0.0,
                        "CF_z": cf_z,
                        "CF_mx": 0.0,
                        "CF_my": 0.0,
                        "CF_mz": cf_x * 0.1,
                    }
                )
            )
    pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
    return path


def _toy_xy(n: int = 64, seed: int = 0):
    """A tiny standardized (features, targets) pair a small MLP can fit."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal((n, N_IN)).astype(np.float32)
    w = rng.standard_normal((N_IN, N_OUT)).astype(np.float32)
    y = (x @ w + 0.01 * rng.standard_normal((n, N_OUT))).astype(np.float32)
    return x, y


def test_build_model_constructs_and_forward_shape():
    """Scenario: Model constructs with the right shape (GPU tier)."""
    import torch

    model = build_model(N_IN, N_OUT, seed=0)
    x = torch.zeros((8, N_IN))
    out = model(x)
    assert tuple(out.shape) == (8, N_OUT)


def test_seeded_training_reduces_loss():
    """Scenario: Seeded training reduces loss (GPU/torch tier)."""
    x, y = _toy_xy()
    model = build_model(N_IN, N_OUT, seed=1)
    history = train_model(model, x, y, epochs=200, seed=1, device="cuda")
    assert history[-1] < history[0]


def test_seeded_training_deterministic_on_cpu_device():
    """Scenario: Seeded training step is deterministic on the CPU torch device (torch tier)."""
    x, y = _toy_xy()
    h1 = train_model(
        build_model(N_IN, N_OUT, seed=2), x, y, epochs=20, seed=2, device="cpu"
    )
    h2 = train_model(
        build_model(N_IN, N_OUT, seed=2), x, y, epochs=20, seed=2, device="cpu"
    )
    assert h1 == h2  # identical loss trajectory on CPU device for a fixed seed


def test_predict_shape_and_finite():
    """A forward pass yields finite predictions of the right shape."""
    x, y = _toy_xy()
    model = build_model(N_IN, N_OUT, seed=3)
    train_model(model, x, y, epochs=10, seed=3, device="cuda")
    out = predict(model, x, device="cuda")
    assert out.shape == (x.shape[0], N_OUT)
    assert np.isfinite(out).all()


def test_full_round_trip_writes_four_artifacts(tmp_path):
    """Scenario: All four artifacts are written (real train->predict->metrics round-trip)."""
    dataset = _toy_parquet(tmp_path / "dataset.parquet")
    out = tmp_path / "out"
    result = run_training(
        dataset,
        out,
        docker_image_digest=DIGEST,
        timestamp="2026-06-18T00:00:00Z",
        seed=1,
        epochs=50,
        n_val_configs=2,
        device="cuda",
        wandb_mode="disabled",
    )
    for key in ("metrics_path", "predictions_path", "checkpoint_path", "metadata_path"):
        assert Path(result[key]).exists()
    preds = pd.read_parquet(result["predictions_path"])
    assert set(preds["config_name"]) <= set(HOLDOUT)
    for c in TARGET_COLUMNS:
        assert f"{c}_true" in preds.columns and f"{c}_pred" in preds.columns


def test_provenance_records_library_versions():
    """Scenario: Resolved library versions recorded on the training host (torch tier)."""
    meta = build_training_metadata(
        docker_image_digest=DIGEST,
        timestamp="2026-06-18T00:00:00Z",
        seeds={"global": 1},
        feature_names=["a"],
    )
    assert meta["library_versions"]["torch"] is not None
    assert meta["library_versions"]["physicsnemo"] is not None
