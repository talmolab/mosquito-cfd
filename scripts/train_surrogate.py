r"""Thin CLI driver for the force-surrogate trainer (Track B, PR5).

All logic lives in :mod:`mosquito_cfd.force_surrogate.train`; this script only parses arguments
and delegates to :func:`train.run_training`. It trains the PhysicsNeMo kinematics(+phase) ->
force-coefficient regressor on the local RTX A5000 (``--device cuda``) and writes the four
committed artifacts (``metrics.json``, ``holdout_predictions.parquet``, the model checkpoint, and
``run_metadata.json``) into ``--out-dir``.

Run on the A5000 (WSL2) with the optional ``train`` group installed, from the repository root and
from a clean, committed tree (``run_metadata.json`` records the commit and ``dirty``)::

    export UV_PROJECT_ENVIRONMENT="$HOME/.venvs/mosquito-cfd-train"  # ext4, not the Windows .venv
    uv sync --frozen --group train
    uv run --frozen --group train python scripts/train_surrogate.py \\
        --dataset examples/prelim_sweep/dataset.parquet \\
        --out-dir examples/prelim_sweep/surrogate \\
        --docker-digest "$(python -c 'import json;print(json.load(open(\"examples/prelim_sweep/run_metadata.json\"))[\"docker_image\"])')" \\
        --timestamp <iso-8601-utc> \\
        --device cuda --wandb online

Pass ``--group train`` on every ``uv run`` (a bare ``uv run`` can sync torch away), do not export
``GIT_DIR``/``GIT_WORK_TREE`` (the git capture resolves a Windows worktree from WSL itself, #78),
and leave ``CUBLAS_WORKSPACE_CONFIG`` unset, as the committed runs did. See
``examples/prelim_sweep/README.md`` for the full recipe.
"""

from __future__ import annotations

import argparse

# Importing the library does NOT import torch (run_training lazy-imports it); the driver stays
# importable on a CPU-only host so its arg-wiring is unit-testable without the train group.
from mosquito_cfd.force_surrogate import train


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (separated so it is unit-testable without running training)."""
    p = argparse.ArgumentParser(
        description="Train the Track B force-coefficient surrogate."
    )
    p.add_argument("--dataset", required=True, help="Path to dataset.parquet.")
    p.add_argument("--out-dir", required=True, help="Directory for the four artifacts.")
    p.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned sha256: image digest (from the dataset's run_metadata.json).",
    )
    p.add_argument(
        "--timestamp", required=True, help="Caller-supplied ISO-8601 timestamp."
    )
    p.add_argument("--seed", type=int, default=train.DEFAULT_SEED, help="Run seed.")
    p.add_argument("--epochs", type=int, default=2000, help="Training epochs.")
    p.add_argument(
        "--n-val-configs",
        type=int,
        default=3,
        help="Validation configs carved from train.",
    )
    p.add_argument("--device", default="cpu", help="'cpu' or 'cuda' (A5000).")
    p.add_argument(
        "--wandb",
        choices=["disabled", "online"],
        default="disabled",
        help="wandb logging mode (default disabled; online for operator A5000 runs).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the training pipeline; returns a process exit code."""
    args = build_parser().parse_args(argv)
    result = train.run_training(
        args.dataset,
        args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        seed=args.seed,
        epochs=args.epochs,
        n_val_configs=args.n_val_configs,
        device=args.device,
        wandb_mode=args.wandb,
    )
    agg = result["metrics"]["aggregate"]
    print(
        f"Wrote {result['metrics_path']}, {result['predictions_path']}, "
        f"{result['checkpoint_path']}, {result['metadata_path']}\n"
        f"Holdout aggregate: RMSE={agg['rmse']:.4g} MAE={agg['mae']:.4g} R2={agg['r2']:.4g}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
