"""CPU-tier smoke tests for the scripts/train_surrogate.py driver (PR5, torch-free).

Loads the driver via ``importlib.util.spec_from_file_location`` (mirrors the PR3/PR4 driver
tests). The driver delegates to ``train.run_training`` — we monkeypatch that symbol so ``main()``
is exercised **without** triggering the lazy torch/PhysicsNeMo import, keeping the CPU tier
provably torch-free (design D2). Verifies the *Force-only training scope guard* via the parser.
"""

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / "scripts" / "train_surrogate.py"


def _load_driver():
    spec = importlib.util.spec_from_file_location("train_surrogate_driver", DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    return driver


def test_parser_wires_all_flags():
    """build_parser() exposes every documented flag with the right types/defaults."""
    driver = _load_driver()
    args = driver.build_parser().parse_args(
        [
            "--dataset",
            "d.parquet",
            "--out-dir",
            "out",
            "--docker-digest",
            "ghcr.io/x@sha256:" + "a" * 64,
            "--timestamp",
            "2026-06-18T00:00:00Z",
            "--seed",
            "7",
            "--epochs",
            "5",
            "--n-val-configs",
            "2",
            "--device",
            "cuda",
            "--wandb",
            "online",
        ]
    )
    assert args.dataset == "d.parquet"
    assert args.out_dir == "out"
    assert args.seed == 7 and args.epochs == 5 and args.n_val_configs == 2
    assert args.device == "cuda" and args.wandb == "online"
    # default wandb is the safe disabled mode
    defaults = driver.build_parser().parse_args(
        ["--dataset", "d", "--out-dir", "o", "--docker-digest", "x", "--timestamp", "t"]
    )
    assert defaults.wandb == "disabled"


def test_main_delegates_without_importing_torch(monkeypatch):
    """main() calls train.run_training with the parsed args and never imports torch."""
    driver = _load_driver()
    captured = {}

    def fake_run_training(dataset, out_dir, **kwargs):
        captured["dataset"] = dataset
        captured["out_dir"] = out_dir
        captured.update(kwargs)
        return {
            "metrics_path": "m.json",
            "predictions_path": "p.parquet",
            "checkpoint_path": "c.pt",
            "metadata_path": "r.json",
            "metrics": {"aggregate": {"rmse": 0.1, "mae": 0.05, "r2": 0.9}},
        }

    monkeypatch.setattr(driver.train, "run_training", fake_run_training)
    monkeypatch.delitem(sys.modules, "torch", raising=False)
    rc = driver.main(
        [
            "--dataset",
            "d.parquet",
            "--out-dir",
            "out",
            "--docker-digest",
            "ghcr.io/x@sha256:" + "a" * 64,
            "--timestamp",
            "2026-06-18T00:00:00Z",
            "--wandb",
            "disabled",
        ]
    )
    assert rc == 0
    assert captured["dataset"] == "d.parquet"
    assert captured["docker_image_digest"].endswith("a" * 64)
    assert captured["wandb_mode"] == "disabled"
    assert "torch" not in sys.modules  # the driver never triggered the lazy import
