"""Kinematics(+phase) -> force-coefficient surrogate trainer (Track B, PR5).

Trains a small **PhysicsNeMo** regressor mapping a wing-kinematics vector plus the within-beat
phase to the six normalized force/moment coefficients of the committed
``examples/prelim_sweep/dataset.parquet``, evaluates it on **held-out configurations** (CC-4),
and emits ``metrics.json`` + a holdout-predictions table + ``run_metadata.json`` (CC-1). This is
the deliberately small, **force-only** surrogate (roadmap CC-6): no field/plotfile reading, no
DoMINO/latent-dynamics, no RL.

**Two import tiers (design D2).** The pure data/feature/split/standardizer/metrics helpers below
import **no** torch, so this module imports cleanly on the CPU-only CI runner without the optional
``train`` dependency-group; they gate CI. The model + training functions (:func:`build_model`,
:func:`train_model`, :func:`predict`) import ``torch``/``physicsnemo`` **lazily inside themselves**
and are exercised only by the GPU/torch test tier (``@pytest.mark.gpu``) on the local RTX A5000.

**Reproducibility (design D6).** Seeds are explicit; the torch-free CPU helper chain is
bitwise-reproducible (CI-tested). The seeded ``train_model`` step is determinism-tested on the CPU
torch device; the CUDA/GPU run is seeded but not asserted bitwise (cuDNN/TF32). ``metrics.json``
records ``reproducibility.bitwise == "cpu_only"`` to scope the claim honestly.

Decisions D1-D8 are documented in the OpenSpec change ``add-force-surrogate-train`` (``design.md``).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime in CI
    import torch

logger = logging.getLogger(__name__)

# Input features: the three swept kinematic knobs + the cyclic phase encoding (design D3).
# Reynolds is deliberately excluded — under the nu*-fixed policy it is a deterministic function
# of (stroke, frequency) and carries no independent information.
FEATURE_COLUMNS = [
    "stroke_amp_deg",
    "frequency_fstar",
    "pitch_amp_deg",
    "phase_sin",
    "phase_cos",
]

# Targets: all six normalized coefficients (design D4). These are read straight from the
# dataset's already-normalized columns — coefficient math is never re-derived here (CC-3).
TARGET_COLUMNS = ["CF_x", "CF_y", "CF_z", "CF_mx", "CF_my", "CF_mz"]

# Holdout identifier columns carried into the predictions table.
PREDICTION_ID_COLUMNS = ["config_name", "time", "phase", "wingbeat"]

# Dataset columns the trainer requires: the prediction ids, the split label, the three swept
# kinematic knobs (build_features derives phase_sin/phase_cos from `phase`), and the six targets.
REQUIRED_COLUMNS = [
    *PREDICTION_ID_COLUMNS,
    "split",
    "stroke_amp_deg",
    "frequency_fstar",
    "pitch_amp_deg",
    *TARGET_COLUMNS,
]

# Converged-beat threshold: the first whole beat (wingbeat 0) is the startup transient.
CONVERGED_MIN_WINGBEAT = 1

# Absolute floor below which a column's variance / sum-of-squares is treated as zero (a
# constant column). Far below any real coefficient variance (the corpus minimum std is ~0.19)
# yet above pure float rounding of an exactly-constant column — so the zero-variance guards in
# ``Standardizer`` and ``compute_metrics`` fire on genuinely-constant data without letting a
# tiny-but-nonzero variance divide through to a garbage result (design D4).
_VARIANCE_EPS = 1e-12


# --- Feature / target construction -------------------------------------------------------


def build_features(df: pd.DataFrame) -> tuple[NDArray[np.floating], list[str]]:
    """Build the standardizable input feature matrix from a dataset slice.

    Inputs are ``[stroke_amp_deg, frequency_fstar, pitch_amp_deg, sin(2*pi*phase),
    cos(2*pi*phase)]`` (cyclic phase respects the 0/1 wrap; Reynolds is excluded, design D3).

    Args:
        df: A dataset frame carrying at least ``stroke_amp_deg``, ``frequency_fstar``,
            ``pitch_amp_deg``, and ``phase``.

    Returns:
        ``(X, feature_names)`` where ``X`` is a ``(n_rows, 5)`` float array whose columns are
        :data:`FEATURE_COLUMNS`.
    """
    phase = df["phase"].to_numpy(dtype=float)
    x = np.column_stack(
        [
            df["stroke_amp_deg"].to_numpy(dtype=float),
            df["frequency_fstar"].to_numpy(dtype=float),
            df["pitch_amp_deg"].to_numpy(dtype=float),
            np.sin(2.0 * np.pi * phase),
            np.cos(2.0 * np.pi * phase),
        ]
    )
    return x, list(FEATURE_COLUMNS)


def filter_converged_beat(
    df: pd.DataFrame, min_wingbeat: int = CONVERGED_MIN_WINGBEAT
) -> pd.DataFrame:
    """Keep only the converged-beat rows (``wingbeat >= min_wingbeat``).

    The startup transient (``wingbeat == 0``) is dropped here **explicitly** — the dataset
    extractor deliberately carried every beat tagged with ``wingbeat`` so the consumer filters
    visibly, not via a silent mask (PR4 D3).

    Args:
        df: The dataset frame (must carry ``wingbeat``).
        min_wingbeat: Lowest wingbeat index to keep (default the converged beat, 1).

    Returns:
        A copy of ``df`` restricted to ``wingbeat >= min_wingbeat``.
    """
    return df[df["wingbeat"] >= min_wingbeat].copy()


class Standardizer:
    """Per-column mean/std standardizer fit on training rows only (no leakage, design D3/D4).

    A zero-variance column (e.g. ``CF_y`` ~ 0 by symmetry) is floored to scale 1.0 so it
    standardizes to 0 rather than producing NaN.
    """

    def __init__(self) -> None:
        """Initialize an unfitted standardizer (``mean_``/``scale_`` set by :meth:`fit`)."""
        self.mean_: NDArray[np.floating] | None = None
        self.scale_: NDArray[np.floating] | None = None

    def fit(self, x: NDArray[np.floating]) -> Standardizer:
        """Fit mean and (zero-floored) std from ``x``; returns self."""
        x = np.asarray(x, dtype=float)
        self.mean_ = x.mean(axis=0)
        std = x.std(axis=0, ddof=0)
        # Floor a (near-)zero-variance column's scale to 1.0 so it standardizes to 0 rather
        # than NaN/inf; the tolerance catches genuinely-constant columns without amplifying a
        # tiny-but-nonzero std into an astronomically-scaled feature (design D4).
        self.scale_ = np.where(std <= _VARIANCE_EPS, 1.0, std)
        return self

    def transform(self, x: NDArray[np.floating]) -> NDArray[np.floating]:
        """Standardize ``x`` with the fitted mean/scale."""
        if self.mean_ is None or self.scale_ is None:
            raise ValueError("Standardizer must be fit before transform")
        return (np.asarray(x, dtype=float) - self.mean_) / self.scale_

    def inverse_transform(self, z: NDArray[np.floating]) -> NDArray[np.floating]:
        """Invert :meth:`transform`."""
        if self.mean_ is None or self.scale_ is None:
            raise ValueError("Standardizer must be fit before inverse_transform")
        return np.asarray(z, dtype=float) * self.scale_ + self.mean_


# --- Held-out-configuration split (CC-4) -------------------------------------------------


@dataclass(frozen=True)
class SplitAssignment:
    """Config-level train/validation/test assignment (sorted, disjoint name lists).

    Attributes:
        train_configs: Training configuration names.
        val_configs: Validation configuration names (seeded carve from the train pool).
        test_configs: The held-out configuration names (the dataset ``holdout`` label).
    """

    train_configs: list[str]
    val_configs: list[str]
    test_configs: list[str]


def make_config_splits(
    df: pd.DataFrame, *, seed: int, n_val_configs: int = 3
) -> SplitAssignment:
    """Assign whole configurations to train / validation / test (CC-4).

    The configurations labelled ``split == "holdout"`` are the **test** set (taken verbatim
    from the dataset, never re-derived). A seeded selection of ``n_val_configs`` whole
    configurations is carved from the ``split == "train"`` pool for validation; the remaining
    train configurations are the training set. Selection draws from the **sorted** unique
    config-name list so it is reproducible across pandas versions.

    Args:
        df: Dataset frame carrying ``config_name`` and ``split``.
        seed: Seed for the validation carve.
        n_val_configs: Number of whole training configurations to hold for validation.

    Returns:
        A :class:`SplitAssignment` with sorted, mutually disjoint config-name lists.

    Raises:
        ValueError: If ``df`` has no ``split`` column, no ``holdout`` configurations, or
            ``n_val_configs`` would leave an empty validation or training set.
    """
    if "split" not in df.columns:
        raise ValueError(
            "dataset frame has no 'split' column; the held-out-config split (CC-4) is taken "
            "from the manifest-derived 'split' label, never re-derived"
        )
    test_configs = sorted(df.loc[df["split"] == "holdout", "config_name"].unique())
    if not test_configs:
        raise ValueError(
            "no configurations are labelled split == 'holdout'; cannot form the held-out "
            "test set (CC-4)"
        )
    train_pool = sorted(df.loc[df["split"] == "train", "config_name"].unique())
    if not (1 <= n_val_configs < len(train_pool)):
        raise ValueError(
            f"n_val_configs must be a valid carve in 1..{len(train_pool) - 1} (got "
            f"{n_val_configs}); it must leave both a non-empty validation and a non-empty "
            "training set"
        )
    rng = np.random.default_rng(seed)
    val_idx = rng.choice(len(train_pool), size=n_val_configs, replace=False)
    val_configs = sorted(train_pool[i] for i in val_idx)
    train_configs = sorted(set(train_pool) - set(val_configs))
    return SplitAssignment(
        train_configs=train_configs,
        val_configs=val_configs,
        test_configs=test_configs,
    )


# --- Metrics -----------------------------------------------------------------------------


def compute_metrics(
    y_true: NDArray[np.floating],
    y_pred: NDArray[np.floating],
    target_names: list[str],
) -> dict[str, Any]:
    """Per-target RMSE/MAE/R² + a NaN-aware aggregate (pure numpy; no scipy/sklearn).

    R² is ``1 - SS_res/SS_tot``; for a (near-)zero-variance target ``SS_tot == 0`` it is the
    sentinel ``nan`` (serialized as ``null`` downstream) rather than an unhandled ``0/0``. The
    ``aggregate`` R² is the NaN-skipping mean, so a constant target does not poison it.

    Args:
        y_true: ``(n, n_targets)`` true coefficients (physical units, inverse-transformed).
        y_pred: ``(n, n_targets)`` predicted coefficients.
        target_names: The ``n_targets`` column names (e.g. :data:`TARGET_COLUMNS`).

    Returns:
        ``{"per_target": {name: {rmse, mae, r2}}, "aggregate": {rmse, mae, r2}}``.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape:
        raise ValueError(
            f"y_true and y_pred must share shape; got {y_true.shape} vs {y_pred.shape}"
        )
    if y_true.shape[1] != len(target_names):
        raise ValueError(
            f"target_names has {len(target_names)} names but arrays have "
            f"{y_true.shape[1]} columns"
        )
    if y_true.shape[0] == 0:
        raise ValueError("cannot compute metrics on a zero-row array")
    per_target: dict[str, dict[str, float]] = {}
    for i, name in enumerate(target_names):
        t = y_true[:, i]
        p = y_pred[:, i]
        resid = t - p
        rmse = float(np.sqrt(np.mean(resid**2)))
        mae = float(np.mean(np.abs(resid)))
        ss_res = float(np.sum(resid**2))
        ss_tot = float(np.sum((t - t.mean()) ** 2))
        # Sentinel for a (near-)zero-variance target: a tiny-but-nonzero ss_tot would
        # otherwise divide through to an explosive, meaningless R² (design D4). The floor is
        # absolute and far below any real coefficient variance (the corpus minimum is ~0.19).
        r2 = float("nan") if ss_tot <= _VARIANCE_EPS else 1.0 - ss_res / ss_tot
        per_target[name] = {"rmse": rmse, "mae": mae, "r2": r2}
    rmses = np.array([per_target[n]["rmse"] for n in target_names])
    maes = np.array([per_target[n]["mae"] for n in target_names])
    r2s = np.array([per_target[n]["r2"] for n in target_names])
    # All three aggregates are NaN-aware and consistent: a target whose metric is NaN (a
    # constant-target R² sentinel, or a target with a NaN datum) is skipped, not propagated —
    # so a single bad column never silently nulls the headline RMSE/MAE while R² survives.
    aggregate = {
        "rmse": float(np.nanmean(rmses))
        if np.any(np.isfinite(rmses))
        else float("nan"),
        "mae": float(np.nanmean(maes)) if np.any(np.isfinite(maes)) else float("nan"),
        "r2": float(np.nanmean(r2s)) if np.any(np.isfinite(r2s)) else float("nan"),
    }
    return {"per_target": per_target, "aggregate": aggregate}


# --- PhysicsNeMo model + training (torch tier; lazy import, design D1/D2) ----------------
#
# Everything below imports ``torch``/``physicsnemo`` *inside* the function so this module stays
# importable on the CPU-only CI runner without the optional ``train`` group. Only the
# PhysicsNeMo model ships — there is no PyTorch fallback (design D1). These are exercised by the
# GPU/torch test tier (``@pytest.mark.gpu``) and the operator's A5000 run.

# PhysicsNeMo MLP defaults for this small kinematics->coefficients regression.
DEFAULT_HIDDEN = 64
DEFAULT_NUM_LAYERS = 3


def set_seeds(seed: int) -> None:
    """Seed python/numpy/torch and enable deterministic algorithms (design D6, lazy torch)."""
    import random

    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    # warn_only: some CUDA kernels lack a deterministic impl; we scope the bitwise claim to CPU.
    torch.use_deterministic_algorithms(True, warn_only=True)


def build_model(
    n_in: int,
    n_out: int,
    *,
    seed: int,
    hidden: int = DEFAULT_HIDDEN,
    num_layers: int = DEFAULT_NUM_LAYERS,
) -> torch.nn.Module:
    """Construct the seeded PhysicsNeMo fully-connected regressor (``n_in`` -> ``n_out``).

    PhysicsNeMo-only — no PyTorch fallback model (design D1). The exact PhysicsNeMo MLP class is
    confirmed against the installed API by the de-risk task on the A5000; this uses the
    documented ``physicsnemo.models.mlp.FullyConnected``.

    Args:
        n_in: Number of input features (5: :data:`FEATURE_COLUMNS`).
        n_out: Number of targets (6: :data:`TARGET_COLUMNS`).
        seed: Seed applied before weight initialization.
        hidden: Hidden layer width.
        num_layers: Number of hidden layers.

    Returns:
        A PhysicsNeMo ``torch.nn.Module`` mapping ``(batch, n_in)`` -> ``(batch, n_out)``.
    """
    set_seeds(seed)
    from physicsnemo.models.mlp import FullyConnected

    return FullyConnected(
        in_features=n_in,
        out_features=n_out,
        num_layers=num_layers,
        layer_size=hidden,
    )


def train_model(
    model: torch.nn.Module,
    x: NDArray[np.floating],
    y: NDArray[np.floating],
    *,
    epochs: int,
    seed: int,
    lr: float = 1e-3,
    device: str = "cpu",
    x_val: NDArray[np.floating] | None = None,
    y_val: NDArray[np.floating] | None = None,
) -> list[float]:
    """Seeded MSE training loop; returns the per-epoch training-loss history.

    If a validation set (``x_val``/``y_val``) is supplied, the per-epoch validation loss is
    tracked and the **best-validation** weights are restored into ``model`` at the end (model
    selection / early-stopping-equivalent, CC-4). Without it, the final-epoch weights are kept.

    Determinism: on ``device="cpu"`` the loss trajectory is reproducible for a fixed seed
    (asserted by the torch tier); the CUDA run is seeded but not asserted bitwise (design D6).

    Args:
        model: A model from :func:`build_model`.
        x: ``(n, n_in)`` standardized training features.
        y: ``(n, n_out)`` standardized training targets.
        epochs: Number of full-batch gradient steps.
        seed: Seed applied before training.
        lr: Adam learning rate.
        device: ``"cpu"`` or ``"cuda"``.
        x_val: Optional ``(m, n_in)`` standardized validation features for model selection.
        y_val: Optional ``(m, n_out)`` standardized validation targets.

    Returns:
        The list of per-epoch **training** losses (length ``epochs``).
    """
    import torch

    set_seeds(seed)
    dev = torch.device(device)
    model = model.to(dev)
    xt = torch.as_tensor(np.asarray(x, dtype=np.float32), device=dev)
    yt = torch.as_tensor(np.asarray(y, dtype=np.float32), device=dev)
    has_val = x_val is not None and y_val is not None
    if has_val:
        xv = torch.as_tensor(np.asarray(x_val, dtype=np.float32), device=dev)
        yv = torch.as_tensor(np.asarray(y_val, dtype=np.float32), device=dev)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = torch.nn.MSELoss()
    history: list[float] = []
    best_val = float("inf")
    best_state: dict | None = None
    model.train()
    for _ in range(epochs):
        opt.zero_grad()
        loss = loss_fn(model(xt), yt)
        loss.backward()
        opt.step()
        history.append(float(loss.detach().cpu()))
        if has_val:
            model.eval()
            with torch.no_grad():
                v = float(loss_fn(model(xv), yv).cpu())
            model.train()
            if v < best_val:
                best_val = v
                best_state = {
                    k: t.detach().cpu().clone() for k, t in model.state_dict().items()
                }
    if has_val and best_state is not None:
        model.load_state_dict(
            best_state
        )  # restore best-validation weights (model selection)
    return history


def predict(
    model: torch.nn.Module,
    x: NDArray[np.floating],
    *,
    device: str = "cpu",
) -> NDArray[np.floating]:
    """Run a forward pass and return predictions as a numpy array.

    Args:
        model: A trained model.
        x: ``(n, n_in)`` standardized features.
        device: ``"cpu"`` or ``"cuda"``.

    Returns:
        ``(n, n_out)`` standardized predictions (inverse-transform before metrics).
    """
    import torch

    dev = torch.device(device)
    model = model.to(dev)
    model.eval()
    with torch.no_grad():
        xt = torch.as_tensor(np.asarray(x, dtype=np.float32), device=dev)
        return model(xt).cpu().numpy()


def _json_safe(obj: Any) -> Any:
    """Recursively replace non-finite floats with ``None`` (NaN R² sentinel -> JSON null)."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


def write_json(path: Path | str, payload: dict[str, Any]) -> None:
    """Write a JSON file with NaN/inf coerced to ``null`` and LF newlines (reproducible)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(_json_safe(payload), f, indent=2, ensure_ascii=False)


# --- Evaluation, artifacts, provenance, wandb (mostly torch-free) -------------------------


def build_predictions_frame(
    holdout_df: pd.DataFrame,
    y_true: NDArray[np.floating],
    y_pred: NDArray[np.floating],
) -> pd.DataFrame:
    """Assemble the versioned holdout-predictions table for the downstream figure (PR6).

    Args:
        holdout_df: The scored holdout rows (converged beat), carrying the
            :data:`PREDICTION_ID_COLUMNS`. Row order must align with ``y_true``/``y_pred``.
        y_true: ``(n, 6)`` true coefficients (physical units).
        y_pred: ``(n, 6)`` predicted coefficients (physical units, inverse-transformed).

    Returns:
        A frame with ``config_name, time, phase, wingbeat`` plus a ``CF_*_true`` and
        ``CF_*_pred`` column per target.
    """
    out = {col: holdout_df[col].to_numpy() for col in PREDICTION_ID_COLUMNS}
    for i, name in enumerate(TARGET_COLUMNS):
        out[f"{name}_true"] = np.asarray(y_true)[:, i]
        out[f"{name}_pred"] = np.asarray(y_pred)[:, i]
    return pd.DataFrame(out)


def build_metrics(
    y_true: NDArray[np.floating],
    y_pred: NDArray[np.floating],
    holdout_df: pd.DataFrame,
    *,
    target_names: list[str] | None = None,
    inference: dict[str, Any],
    reproducibility: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the ``metrics.json`` payload (per-target / aggregate / per-config / + blocks).

    Args:
        y_true: ``(n, n_targets)`` true coefficients (physical units), aligned with ``holdout_df``.
        y_pred: ``(n, n_targets)`` predictions (physical units).
        holdout_df: The scored holdout rows (carries ``config_name`` for the per-config split).
        target_names: Target column names (defaults to :data:`TARGET_COLUMNS`).
        inference: The inference-timing block (``latency_ms``/``throughput_rows_per_s``/basis).
        reproducibility: The reproducibility block (seeds, features, ``bitwise`` scope).

    Returns:
        ``{"per_target", "aggregate", "per_config", "inference", "reproducibility"}``.
    """
    names = list(target_names) if target_names is not None else list(TARGET_COLUMNS)
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    overall = compute_metrics(y_true, y_pred, names)
    config_names = holdout_df["config_name"].to_numpy()
    per_config: dict[str, Any] = {}
    for cfg in sorted(pd.unique(config_names)):
        mask = config_names == cfg
        per_config[str(cfg)] = compute_metrics(y_true[mask], y_pred[mask], names)
    return {
        "per_target": overall["per_target"],
        "aggregate": overall["aggregate"],
        "per_config": per_config,
        "inference": dict(inference),
        "reproducibility": dict(reproducibility),
    }


def _library_version(distribution: str) -> str | None:
    """Resolved version of an installed distribution, or ``None`` (no import, no GPU needed)."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(distribution)
    except PackageNotFoundError:
        return None


def build_training_metadata(
    *,
    docker_image_digest: str,
    timestamp: str,
    seeds: dict[str, int],
    feature_names: list[str],
) -> dict[str, Any]:
    """Capture training-run provenance (CC-1): pinned digest, timestamp, seeds, lib versions.

    Wraps :func:`capture_surrogate_run_metadata` (which requires a pinned ``sha256:`` digest and
    accepts a caller-supplied timestamp). The seeds, feature list, and resolved
    ``torch``/``physicsnemo`` versions are added via ``extra`` (top-level). Versions are read
    from installed-package metadata (no import), so they are ``None`` on the CI tier where the
    ``train`` group is absent and populated on the A5000 training host.

    Args:
        docker_image_digest: Pinned ``sha256:`` image reference (a mutable tag is rejected).
        timestamp: Caller-supplied ISO-8601 timestamp.
        seeds: The run seeds.
        feature_names: The input feature list.

    Returns:
        The provenance dict with ``seeds``, ``features``, and ``library_versions`` at top level.
    """
    from mosquito_cfd.force_surrogate.sidecar import capture_surrogate_run_metadata

    library_versions = {
        "torch": _library_version("torch"),
        "physicsnemo": _library_version("nvidia-physicsnemo"),
    }
    return capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        extra={
            "seeds": dict(seeds),
            "features": list(feature_names),
            "library_versions": library_versions,
        },
    )


def log_to_wandb(
    mode: str,
    *,
    project: str,
    run_config: dict[str, Any],
    metrics: dict[str, Any],
) -> None:
    """Log a run to Weights & Biases, gated so it never blocks the committed ``metrics.json``.

    ``mode == "disabled"`` (the CI/rerun default) is a no-op that does **not** import ``wandb``.
    ``mode == "online"`` wraps **both** ``import wandb`` and the init/log call in one
    ``try/except`` so a missing or unreachable wandb (e.g. no login on a CI runner) is logged and
    swallowed — the committed ``metrics.json`` is written from local state regardless (design D7).

    Args:
        mode: ``"disabled"`` or ``"online"``.
        project: wandb project name.
        run_config: Run configuration to attach.
        metrics: Metrics to log.
    """
    if mode == "disabled":
        return
    try:
        import wandb

        wandb.init(project=project, config=run_config, mode="online")
        wandb.log(_json_safe(metrics))
        wandb.finish()
    except Exception as exc:  # noqa: BLE001 - any wandb/import/network failure must not block
        logger.warning(
            "wandb '%s' logging failed (%s); metrics.json is unaffected", mode, exc
        )


def _measure_inference(
    model: torch.nn.Module,
    x: NDArray[np.floating],
    *,
    device: str,
    n_latency: int = 200,
) -> dict[str, Any]:
    """Measure single-row latency (ms) and batched throughput (rows/s) for the speedup figure.

    On CUDA, kernel launches are asynchronous, so the timed regions are bracketed with
    ``torch.cuda.synchronize()`` (otherwise ``perf_counter`` captures only launch overhead).
    Latency is the **mean** over ``n_latency`` single-row passes (one un-timed warm-up batch
    first); throughput is one synchronized full-batch pass. Tensors are placed on-device once so
    host->device transfer and ``model.to`` are not counted in the inference time.
    """
    import time

    import torch

    dev = torch.device(device)
    model = model.to(dev).eval()
    xt = torch.as_tensor(np.asarray(x, dtype=np.float32), device=dev)
    one = xt[:1]
    n = xt.shape[0]

    def _sync() -> None:
        if dev.type == "cuda":
            torch.cuda.synchronize()

    with torch.no_grad():
        for _ in range(10):  # warm up
            model(one)
        _sync()
        t0 = time.perf_counter()
        for _ in range(n_latency):
            model(one)
        _sync()
        latency_ms = (time.perf_counter() - t0) / n_latency * 1.0e3
        _sync()
        t0 = time.perf_counter()
        model(xt)
        _sync()
        batch_s = time.perf_counter() - t0
    throughput = n / batch_s if batch_s > 0 else float("inf")
    return {
        "latency_ms": float(latency_ms),
        "throughput_rows_per_s": float(throughput),
        "basis": (
            f"mean single-row latency over {n_latency} iters; batched throughput over {n} "
            f"rows on {device}; cuda-synchronized"
        ),
    }


# Default training seed for the surrogate run (recorded in run_metadata; design D6).
DEFAULT_SEED = 1234


def run_training(
    dataset_path: Path | str,
    out_dir: Path | str,
    *,
    docker_image_digest: str,
    timestamp: str,
    seed: int = DEFAULT_SEED,
    epochs: int = 2000,
    n_val_configs: int = 3,
    hidden: int = DEFAULT_HIDDEN,
    num_layers: int = DEFAULT_NUM_LAYERS,
    lr: float = 1e-3,
    device: str = "cpu",
    wandb_mode: str = "disabled",
    wandb_project: str = "force-surrogate",
    checkpoint_name: str = "surrogate.pt",
) -> dict[str, Any]:
    """Train the PhysicsNeMo surrogate end-to-end and emit the four committed artifacts.

    Consumes **only** the tidy ``dataset.parquet`` (kinematics + phase + coefficients) — no
    plotfiles, fields, DoMINO, or RL (CC-6). Filters to the converged beat, splits at the
    configuration level (CC-4), standardizes on train rows only, trains the PhysicsNeMo
    regressor, evaluates on the holdout configs, and writes ``metrics.json``, the
    holdout-predictions parquet, the model checkpoint, and ``run_metadata.json`` into ``out_dir``.

    Torch tier: this drives ``build_model``/``train_model``/``predict`` and ``torch.save`` (lazy
    imports), so it runs on the A5000, not CI.

    Args:
        dataset_path: Path to ``examples/prelim_sweep/dataset.parquet``.
        out_dir: Directory to write the four artifacts into.
        docker_image_digest: Pinned ``sha256:`` digest (sourced from the dataset's
            ``run_metadata.json``).
        timestamp: Caller-supplied ISO-8601 timestamp.
        seed: Run seed.
        epochs: Training epochs (full-batch).
        n_val_configs: Validation configurations carved from the train pool.
        hidden: MLP hidden width.
        num_layers: MLP hidden layers.
        lr: Adam learning rate.
        device: ``"cpu"`` or ``"cuda"``.
        wandb_mode: ``"disabled"`` (default) or ``"online"``.
        wandb_project: wandb project name.
        checkpoint_name: Filename for the saved checkpoint under ``out_dir``.

    Returns:
        A dict of the written artifact paths plus the in-memory ``metrics`` and ``split``.
    """
    import torch

    from mosquito_cfd.force_surrogate.sidecar import validate_image_digest

    dataset_path = Path(dataset_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # Fail fast on a missing/mutable digest *before* paying for the full A5000 training run
    # (a pure regex guard; the same digest is re-validated by build_training_metadata, CC-1).
    validate_image_digest(docker_image_digest)

    df = pd.read_parquet(dataset_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"dataset is missing required column(s) {missing}")
    holdout_before = set(df.loc[df["split"] == "holdout", "config_name"].unique())
    df = filter_converged_beat(df)
    holdout_after = set(df.loc[df["split"] == "holdout", "config_name"].unique())
    dropped = sorted(holdout_before - holdout_after)
    if dropped:
        # A holdout config with no converged-beat rows would silently vanish from the eval.
        logger.warning(
            "holdout config(s) %s have no converged-beat (wingbeat>=%d) rows and are absent "
            "from the evaluation; metrics.json covers %d of %d holdout configs",
            dropped,
            CONVERGED_MIN_WINGBEAT,
            len(holdout_after),
            len(holdout_before),
        )
    split = make_config_splits(df, seed=seed, n_val_configs=n_val_configs)

    cfg = df["config_name"].to_numpy()
    train_mask = np.isin(cfg, split.train_configs)
    val_mask = np.isin(cfg, split.val_configs)
    test_mask = np.isin(cfg, split.test_configs)

    x_all, feature_names = build_features(df)
    feature_std = Standardizer().fit(x_all[train_mask])
    xz = feature_std.transform(x_all)
    y_all = df[TARGET_COLUMNS].to_numpy(dtype=float)
    target_std = Standardizer().fit(y_all[train_mask])
    yz = target_std.transform(y_all)

    model = build_model(
        len(feature_names),
        len(TARGET_COLUMNS),
        seed=seed,
        hidden=hidden,
        num_layers=num_layers,
    )
    # Train with the val set driving best-checkpoint selection (CC-4: val is config-level).
    history = train_model(
        model,
        xz[train_mask],
        yz[train_mask],
        epochs=epochs,
        seed=seed,
        lr=lr,
        device=device,
        x_val=xz[val_mask],
        y_val=yz[val_mask],
    )

    holdout_df = df[test_mask].reset_index(drop=True)
    yz_pred = predict(model, xz[test_mask], device=device)
    y_pred = target_std.inverse_transform(yz_pred)
    y_true = y_all[test_mask]

    # Validation generalization of the selected model (the val set is held out of the fit and
    # of the holdout metrics; reported so the carved configs are used, not silently discarded).
    y_val_pred = target_std.inverse_transform(
        predict(model, xz[val_mask], device=device)
    )
    val_aggregate = compute_metrics(y_all[val_mask], y_val_pred, list(TARGET_COLUMNS))[
        "aggregate"
    ]

    inference = _measure_inference(model, xz[test_mask], device=device)
    reproducibility = {
        "seeds": {"global": seed},
        "features": list(feature_names),
        "bitwise": "cpu_only",
        "deterministic_algorithms": True,
        "device": device,
        "epochs": epochs,
        "final_train_loss": history[-1] if history else None,
        "model_selection": "best_validation_checkpoint",
        "val_configs": list(split.val_configs),
        "val_aggregate": val_aggregate,
    }
    metrics = build_metrics(
        y_true, y_pred, holdout_df, inference=inference, reproducibility=reproducibility
    )
    predictions = build_predictions_frame(holdout_df, y_true, y_pred)
    metadata = build_training_metadata(
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        seeds={"global": seed},
        feature_names=list(feature_names),
    )

    metrics_path = out_dir / "metrics.json"
    predictions_path = out_dir / "holdout_predictions.parquet"
    checkpoint_path = out_dir / checkpoint_name
    metadata_path = out_dir / "run_metadata.json"
    write_json(metrics_path, metrics)
    predictions.to_parquet(predictions_path, index=False)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "feature_mean": feature_std.mean_,
            "feature_scale": feature_std.scale_,
            "target_mean": target_std.mean_,
            "target_scale": target_std.scale_,
            "feature_names": list(feature_names),
            "target_names": list(TARGET_COLUMNS),
            "seed": seed,
        },
        checkpoint_path,
    )
    write_json(metadata_path, metadata)

    log_to_wandb(
        wandb_mode,
        project=wandb_project,
        run_config={"seed": seed, "epochs": epochs, "lr": lr, "device": device},
        metrics=metrics,
    )

    return {
        "metrics_path": str(metrics_path),
        "predictions_path": str(predictions_path),
        "checkpoint_path": str(checkpoint_path),
        "metadata_path": str(metadata_path),
        "metrics": metrics,
        "split": split,
    }
