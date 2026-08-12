"""Coarse-vs-fine holdout comparison and config-mean-collapse diagnostic figures.

OpenSpec change ``add-visualization-tooling``. Promotes two one-off vault scripts
(``make_coarse_vs_fine_comparison.py``, ``diagnostic_config_mean_collapse.py``) into tested,
run-metadata-traceable library functions, parameterized by predictions/metrics paths rather than
hardcoded to ``examples/prelim_sweep``/``prelim_sweep_fine``.

:func:`build_config_mean_collapse_diagnostic` reads its reported R2 from ``metrics.json``'s
``config_resolved`` block specifically -- never the separate ``per_target`` block (RMSE) --
guarding against the documented gotcha where ``evidence_figure.py``'s own auto-generated panels
read those two blocks side by side and are easy to conflate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are written, never shown (matches examples/*)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from mosquito_cfd.force_surrogate.sidecar import (  # noqa: E402
    capture_surrogate_run_metadata,
    validate_image_digest,
)
from mosquito_cfd.force_surrogate.train import write_json  # noqa: E402

DEFAULT_COEFFICIENT = "CF_x"


def _sha256(path: str | Path) -> str:
    """SHA256 hex digest of a file's bytes (mirrors ``evidence_figure.py``'s own helper)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    """Return ``mapping[key]`` or raise a clear ``KeyError`` naming the missing key + context.

    Mirrors ``evidence_figure.py``'s own ``_require`` helper so a missing/mistyped
    ``metrics.json`` key fails with a message naming what's missing, not a bare
    ``KeyError: 'config_resolved'``.
    """
    if key not in mapping:
        raise KeyError(f"metrics is missing required key {key!r} ({ctx})")
    return mapping[key]


def _validate_predictions_finite(predictions: pd.DataFrame, coefficient: str) -> None:
    """Raise a clear ``ValueError`` if ``<coefficient>_{true,pred}`` contains NaN/inf.

    Mirrors ``evidence_figure.py``'s ``_validate_predictions`` guard: a non-finite value must
    not silently flow into a written comparison figure/metrics sidecar.
    """
    for col in (f"{coefficient}_true", f"{coefficient}_pred"):
        if col not in predictions.columns:
            raise ValueError(
                f"predictions parquet is missing required column {col!r} for "
                f"coefficient {coefficient!r}"
            )
        if not np.isfinite(predictions[col].to_numpy()).all():
            raise ValueError(
                f"predictions parquet has non-finite (NaN/inf) values in column {col!r}; "
                "refusing to emit a silently-wrong comparison figure"
            )


def _config_means(
    predictions: pd.DataFrame, coefficient: str
) -> dict[str, dict[str, float]]:
    """Per-config mean true/predicted values for ``coefficient`` (the plotted diamond positions)."""
    means = predictions.groupby("config_name")[
        [f"{coefficient}_true", f"{coefficient}_pred"]
    ].mean()
    return {
        str(cfg): {
            "true_mean": float(row[f"{coefficient}_true"]),
            "pred_mean": float(row[f"{coefficient}_pred"]),
        }
        for cfg, row in means.iterrows()
    }


def _plot_panel(ax, predictions: pd.DataFrame, coefficient: str, title: str) -> None:
    true_col, pred_col = f"{coefficient}_true", f"{coefficient}_pred"
    ax.scatter(
        predictions[true_col],
        predictions[pred_col],
        s=8,
        color="#2a78d6",
        alpha=0.3,
        zorder=2,
    )
    means = predictions.groupby("config_name")[[true_col, pred_col]].mean()
    ax.scatter(
        means[true_col], means[pred_col], s=100, color="#eb6834", marker="D", zorder=3
    )
    lo = min(predictions[true_col].min(), predictions[pred_col].min())
    hi = max(predictions[true_col].max(), predictions[pred_col].max())
    pad = 0.08 * (hi - lo) if hi > lo else 1.0
    ax.plot(
        [lo - pad, hi + pad],
        [lo - pad, hi + pad],
        color="0.7",
        lw=1.2,
        ls="--",
        zorder=1,
    )
    ax.set_xlim(lo - pad, hi + pad)
    ax.set_ylim(lo - pad, hi + pad)
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=11)
    ax.set_xlabel("actual (simulation)", fontsize=9)
    ax.set_ylabel("predicted (model)", fontsize=9)


def build_coarse_vs_fine_comparison(
    *,
    coarse_predictions_path: str | Path,
    fine_predictions_path: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
    coefficient: str = DEFAULT_COEFFICIENT,
) -> dict[str, Any]:
    """Two-panel predicted-vs-actual force scatter (coarse grid | fine grid).

    Args:
        coarse_predictions_path: Coarse-grid ``holdout_predictions.parquet``.
        fine_predictions_path: Fine-grid ``holdout_predictions.parquet``.
        out_dir: Output directory.
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (CC-1).
        coefficient: Force-coefficient column prefix to plot (default ``"CF_x"``).

    Returns:
        Dict with ``"coarse"``/``"fine"`` keys, each mapping config name to
        ``{"true_mean", "pred_mean"}`` -- the exact per-config diamond positions plotted.

    Raises:
        ValueError: If ``docker_image_digest`` is a mutable tag, a required
            ``<coefficient>_{true,pred}`` column is missing, or either predictions frame has a
            non-finite (NaN/inf) value in that column.
    """
    validate_image_digest(docker_image_digest)  # fail-fast before any I/O

    coarse_df = pd.read_parquet(coarse_predictions_path)
    fine_df = pd.read_parquet(fine_predictions_path)
    _validate_predictions_finite(coarse_df, coefficient)
    _validate_predictions_finite(fine_df, coefficient)

    # Compute every fallible value BEFORE creating the matplotlib figure (mirrors
    # evidence_figure.py's "validate + compute everything fallible first" discipline) --
    # a review-round finding was that a later error (e.g. an out_dir that can't be created)
    # left an unclosed Figure with no path back to it. Nothing below this point can raise for
    # reasons unrelated to figure creation/saving itself.
    result: dict[str, Any] = {
        "coefficient": coefficient,
        "coarse": _config_means(coarse_df, coefficient),
        "fine": _config_means(fine_df, coefficient),
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(
            coarse_predictions_path
        ),  # records inputs.file + inputs.hash (coarse)
        timestamp=timestamp,
        extra={
            # The helper hashes only the single inputs_file; record the *second* input's own
            # hash under a distinct key so the built-in inputs.file/hash is not clobbered
            # (mirrors evidence_figure.py's generate_evidence_figure).
            "fine_predictions_path": str(fine_predictions_path),
            "fine_predictions_sha256": _sha256(fine_predictions_path),
        },
    )
    out_dir = Path(out_dir)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5))
    try:
        _plot_panel(axes[0], coarse_df, coefficient, "Coarse grid")
        _plot_panel(axes[1], fine_df, coefficient, "Fine grid")
        handles = [
            Line2D(
                [0],
                [0],
                marker="o",
                color="none",
                markerfacecolor="#2a78d6",
                markersize=8,
                label="one moment in the flapping cycle",
            ),
            Line2D(
                [0],
                [0],
                marker="D",
                color="none",
                markerfacecolor="#eb6834",
                markersize=9,
                label="average for one flight pattern",
            ),
            Line2D([0], [0], color="0.7", lw=1.2, ls="--", label="perfect prediction"),
        ]
        fig.legend(
            handles=handles,
            loc="lower center",
            ncol=3,
            fontsize=9,
            bbox_to_anchor=(0.5, -0.02),
            frameon=False,
        )
        fig.suptitle(f"Predicted vs. actual wing force ({coefficient})", fontsize=13)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            out_dir / "coarse_vs_fine_comparison.png", dpi=200, bbox_inches="tight"
        )
    finally:
        plt.close(fig)

    write_json(out_dir / "coarse_vs_fine_comparison_metrics.json", result)
    write_json(out_dir / "coarse_vs_fine_comparison_run_metadata.json", metadata)
    return result


def _config_resolved_r2(metrics: dict[str, Any], coefficient: str) -> float | None:
    """Read ``config_resolved.<coefficient>.config_mean_r2`` -- never ``per_target``.

    Typed ``float | None`` (not just ``float``), matching ``evidence_figure.py``'s own
    ``_config_mean_r2`` accessor: ``train.py``'s ``compute_config_resolved`` legitimately writes
    a JSON ``null`` here when between-config variance is (near-)zero, and that ``None`` is a
    meaningful diagnostic result in its own right (near-zero between-config signal), not an
    error to hide -- passed through as-is rather than formatted/hidden like
    ``evidence_figure.py``'s caption-only ``_fmt_r2`` does, since this diagnostic's whole purpose
    is reporting the exact number, not a human-readable caption.

    Raises:
        KeyError: If any level of the path is missing, naming exactly which key and why
            (mirrors ``evidence_figure.py``'s own ``_require``-based accessors, rather than a
            bare, context-free ``KeyError`` from unguarded dict indexing).
    """
    cr = _require(metrics, "config_resolved", "config-resolved skill block")
    entry = _require(cr, coefficient, f"config_resolved entry for {coefficient}")
    return _require(
        entry, "config_mean_r2", f"config_resolved.{coefficient}.config_mean_r2"
    )


def _representative_config(predictions: pd.DataFrame) -> str:
    """The first config name, sorted -- used for the diagnostic's raw-waveform bottom row."""
    return sorted(predictions["config_name"].unique())[0]


def build_config_mean_collapse_diagnostic(
    *,
    coarse_predictions_path: str | Path,
    fine_predictions_path: str | Path,
    coarse_metrics_path: str | Path,
    fine_metrics_path: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
    coefficient: str = DEFAULT_COEFFICIENT,
) -> dict[str, Any]:
    """2x2 diagnostic: per-config mean collapse (top) + one config's raw waveform (bottom).

    Internal diagnostic, not a slide asset -- confirms whether the *true* per-config average
    force has collapsed toward a single point on the fine grid even though the model's
    moment-by-moment waveform fit stays visually accurate (the accuracy-metric-crater finding
    this tooling replaces documented by hand).

    Args:
        coarse_predictions_path: Coarse-grid ``holdout_predictions.parquet``.
        fine_predictions_path: Fine-grid ``holdout_predictions.parquet``.
        coarse_metrics_path: Coarse-grid ``metrics.json``.
        fine_metrics_path: Fine-grid ``metrics.json``.
        out_dir: Output directory.
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (CC-1).
        coefficient: Force-coefficient column prefix (default ``"CF_x"``).

    Returns:
        Dict with ``"coarse"``/``"fine"`` keys, each ``{"config_mean_r2": float | None}`` read
        verbatim (``None`` if the source metrics.json legitimately has a JSON ``null`` there)
        from that grid's ``metrics.json`` ``config_resolved`` block.

    Raises:
        ValueError: If ``docker_image_digest`` is a mutable tag, a required
            ``<coefficient>_{true,pred}`` column is missing, or either predictions frame has a
            non-finite (NaN/inf) value in that column.
        KeyError: If either ``metrics.json`` is missing ``config_resolved``, the
            ``coefficient`` entry within it, or ``config_mean_r2`` -- naming exactly which key
            (see ``_config_resolved_r2``).
    """
    validate_image_digest(docker_image_digest)  # fail-fast before any I/O

    coarse_df = pd.read_parquet(coarse_predictions_path)
    fine_df = pd.read_parquet(fine_predictions_path)
    _validate_predictions_finite(coarse_df, coefficient)
    _validate_predictions_finite(fine_df, coefficient)
    coarse_metrics = json.loads(Path(coarse_metrics_path).read_text(encoding="utf-8"))
    fine_metrics = json.loads(Path(fine_metrics_path).read_text(encoding="utf-8"))

    # Compute every fallible value BEFORE creating the matplotlib figure (mirrors
    # evidence_figure.py's "validate + compute everything fallible first" discipline, and fixes
    # a review-round finding: a malformed metrics.json used to raise KeyError from
    # _config_resolved_r2 *after* plt.subplots() had already created a Figure, leaking it since
    # neither fig.savefig nor plt.close was ever reached).
    result: dict[str, Any] = {
        "coefficient": coefficient,
        "coarse": {"config_mean_r2": _config_resolved_r2(coarse_metrics, coefficient)},
        "fine": {"config_mean_r2": _config_resolved_r2(fine_metrics, coefficient)},
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(
            coarse_metrics_path
        ),  # records inputs.file + inputs.hash (coarse metrics)
        timestamp=timestamp,
        extra={
            # The helper hashes only the single inputs_file; this diagnostic reads three more
            # inputs (fine metrics + both predictions parquets) that must each be independently
            # traceable too -- an untracked path string alone can't prove which bytes were
            # actually read (mirrors evidence_figure.py's second-input-hash pattern, extended to
            # all three remaining inputs here).
            "fine_metrics_path": str(fine_metrics_path),
            "fine_metrics_sha256": _sha256(fine_metrics_path),
            "coarse_predictions_path": str(coarse_predictions_path),
            "coarse_predictions_sha256": _sha256(coarse_predictions_path),
            "fine_predictions_path": str(fine_predictions_path),
            "fine_predictions_sha256": _sha256(fine_predictions_path),
        },
    )
    out_dir = Path(out_dir)

    true_col, pred_col = f"{coefficient}_true", f"{coefficient}_pred"
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    try:
        for col, (df, label) in enumerate(
            [(coarse_df, "Coarse grid"), (fine_df, "Fine grid")]
        ):
            means = df.groupby("config_name")[[true_col, pred_col]].mean()
            top = axes[0, col]
            top.scatter(
                means[true_col], means[pred_col], s=80, color="#eb6834", marker="D"
            )
            top.set_title(f"{label}: per-config mean", fontsize=10)
            top.set_xlabel("true mean", fontsize=8)
            top.set_ylabel("pred mean", fontsize=8)

            rep_config = _representative_config(df)
            rep = df[df["config_name"] == rep_config].sort_values("phase")
            bottom = axes[1, col]
            bottom.plot(rep["phase"], rep[true_col], label="true", color="0.2")
            bottom.plot(
                rep["phase"], rep[pred_col], label="pred", color="#2a78d6", ls="--"
            )
            bottom.set_title(f"{label}: {rep_config} waveform", fontsize=10)
            bottom.set_xlabel("phase", fontsize=8)
            bottom.legend(fontsize=7)
        fig.tight_layout()
        out_dir.mkdir(parents=True, exist_ok=True)
        fig.savefig(
            out_dir / "diagnostic_config_mean_collapse.png",
            dpi=150,
            bbox_inches="tight",
        )
    finally:
        plt.close(fig)

    write_json(out_dir / "diagnostic_config_mean_collapse_metrics.json", result)
    write_json(out_dir / "diagnostic_config_mean_collapse_run_metadata.json", metadata)
    return result
