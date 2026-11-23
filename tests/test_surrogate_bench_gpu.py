"""GPU end-to-end run of the bench driver (add-surrogate-comparison-bench, 7d; GPU tier).

``@pytest.mark.gpu``: needs CUDA and the ``train`` group, so it runs under WSL2 on the A5000 and
never in CI. torch is imported inside the test, after the autoskip guard.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest
from test_surrogate_bench_runner import DIGEST, synthetic_corpus

from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS, build_model
from mosquito_cfd.surrogate_bench import BENCH_SEEDS
from mosquito_cfd.surrogate_bench.runner import MLP_HARMONICS, MLP_HYPERPARAMETERS

pytestmark = pytest.mark.gpu

DRIVER = Path(__file__).resolve().parents[1] / "scripts" / "run_surrogate_bench.py"
N_SETTINGS = 3


def _load():
    spec = importlib.util.spec_from_file_location("run_surrogate_bench", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_driver_runs_every_entry_end_to_end_on_cuda(tmp_path):
    fine, coarse = tmp_path / "fine.parquet", tmp_path / "coarse.parquet"
    synthetic_corpus().to_parquet(fine, index=False)
    synthetic_corpus(scale=1.1).to_parquet(coarse, index=False)
    out = tmp_path / "bench"
    argv = [
        "--dataset",
        str(fine),
        "--coarse-dataset",
        str(coarse),
        "--out-dir",
        str(out),
        "--docker-digest",
        DIGEST,
        "--timestamp",
        "2026-11-22T12:00:00Z",
        "--epochs",
        "5",
        "--device",
        "cuda",
        "--allow-dirty",
    ]
    assert _load().main(argv) == 0

    results = pd.read_parquet(out / "results.parquet")
    mlp = results[results["entry"].isin(list(MLP_HARMONICS))]
    assert set(mlp["entry"]) == set(MLP_HARMONICS)
    seeds = mlp.groupby(["entry", "split"])["seed"].apply(lambda s: sorted(set(s)))
    assert len(seeds) == len(MLP_HARMONICS) * 14
    assert all(list(v) == list(BENCH_SEEDS) for v in seeds)
    assert (mlp["peak_gpu_mem"].astype("int64") > 0).all()
    # The warm-up keeps cuBLAS's one-time workspace out of the first fit's peak: the very first
    # fit (mlp_h1 / interpolation / seed 1234) is no larger than the other interpolation fits.
    first = mlp[(mlp["entry"] == "mlp_h1") & (mlp["split"] == "interpolation")]
    peaks = first.groupby("seed")["peak_gpu_mem"].first().astype("int64")
    print("interpolation mlp_h1 peak_gpu_mem by seed:", dict(peaks))
    assert peaks.iloc[0] <= peaks.iloc[1:].max()

    for entry, harmonics in MLP_HARMONICS.items():
        model = build_model(
            N_SETTINGS + 2 * harmonics,
            len(TARGET_COLUMNS),
            seed=0,
            hidden=MLP_HYPERPARAMETERS["hidden"],
            num_layers=MLP_HYPERPARAMETERS["num_layers"],
        )
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        assert set(results.loc[results["entry"] == entry, "n_params"]) == {trainable}
