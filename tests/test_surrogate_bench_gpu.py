"""GPU end-to-end run of the bench driver (add-surrogate-comparison-bench, 7d and 8b; GPU tier).

``@pytest.mark.gpu``: needs CUDA and the ``train`` group, so it runs under WSL2 on the A5000 and
never in CI. torch is imported inside the test, after the autoskip guard.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest
from test_surrogate_bench_runner import DIGEST, synthetic_corpus

from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS, build_model
from mosquito_cfd.surrogate_bench import BENCH_SEEDS
from mosquito_cfd.surrogate_bench.runner import MLP_ENTRIES

pytestmark = pytest.mark.gpu

DRIVER = Path(__file__).resolve().parents[1] / "scripts" / "run_surrogate_bench.py"
N_SETTINGS = 3
# Known answers (spec "The parameter counts are the architectures'"): a fully connected net
# with inputs 3 + 2·harmonics, `num_layers` hidden layers of width `hidden`, and 6 outputs.
N_PARAMS = {
    "mlp_h1": 9094,  # (5·64+64) + 2·(64·64+64) + (64·6+6)
    "mlp_h3": 9350,  # (9·64+64) + 2·(64·64+64) + (64·6+6)
    "mlp_w256d5": 266246,  # (5·256+256) + 4·(256·256+256) + (256·6+6)
    "mlp_w256d5_h3": 267270,  # (9·256+256) + 4·(256·256+256) + (256·6+6)
}


def _load():
    spec = importlib.util.spec_from_file_location("run_surrogate_bench", DRIVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _interpolation_peaks(mlp, entry):
    rows = mlp[(mlp["entry"] == entry) & (mlp["split"] == "interpolation")]
    return rows.groupby("seed")["peak_gpu_mem"].first().astype("int64")


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

    assert list(MLP_ENTRIES) == list(N_PARAMS)
    results = pd.read_parquet(out / "results.parquet")
    mlp = results[results["entry"].isin(list(N_PARAMS))]
    assert set(mlp["entry"]) == set(N_PARAMS)
    seeds = mlp.groupby(["entry", "split"])["seed"].apply(lambda s: sorted(set(s)))
    assert len(seeds) == 4 * 14
    assert all(list(v) == list(BENCH_SEEDS) for v in seeds)
    assert (mlp["peak_gpu_mem"].astype("int64") > 0).all()
    # The warm-up keeps cuBLAS's one-time workspace out of the first fit's peak: the very first
    # fit (mlp_h1 / interpolation / seed 1234) is no larger than the other interpolation fits.
    # The same holds for the first fit at the larger layer shapes. The workspace belongs to the
    # cuBLAS handle, not the shape, so this is a sanity check, not a test of a second warm-up.
    for entry in ("mlp_h1", "mlp_w256d5"):
        peaks = _interpolation_peaks(mlp, entry)
        print(f"interpolation {entry} peak_gpu_mem by seed:", dict(peaks))
        assert peaks.iloc[0] <= peaks.iloc[1:].max(), entry
    # The probe sees the larger model.
    assert (
        _interpolation_peaks(mlp, "mlp_w256d5").median()
        > _interpolation_peaks(mlp, "mlp_h1").median()
    )
    print(
        "fit_seconds median by entry:",
        dict(mlp.groupby("entry")["fit_seconds"].median()),
    )

    for entry, row in MLP_ENTRIES.items():
        model = build_model(
            N_SETTINGS + 2 * row["phase_harmonics"],
            len(TARGET_COLUMNS),
            seed=0,
            hidden=row["hidden"],
            num_layers=row["num_layers"],
        )
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        assert trainable == N_PARAMS[entry], entry
        assert set(results.loc[results["entry"] == entry, "n_params"]) == {trainable}

    meta = json.loads((out / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["mlp_hyperparameters"] == MLP_ENTRIES
