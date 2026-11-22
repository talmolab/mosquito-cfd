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


def _require_predictions_schema(
    predictions: pd.DataFrame, required: tuple[str, ...] = ("config_name",)
) -> None:
    """Raise a clear ``ValueError`` if ``predictions`` is missing any column in ``required``.

    Both builders group by ``config_name``; ``build_config_mean_collapse_diagnostic`` additionally
    needs ``phase`` (its waveform panel sorts by it). Without this check, a predictions frame
    missing either column fails with a bare, context-free ``KeyError`` deep inside a
    ``groupby``/plotting call -- inconsistent with this module's convention of naming exactly
    what's wrong before any computation.
    """
    missing = [c for c in required if c not in predictions.columns]
    if missing:
        raise ValueError(f"predictions parquet is missing required column(s) {missing}")


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
        ValueError: If ``docker_image_digest`` is a mutable tag, either predictions frame is
            missing ``config_name`` or the required ``<coefficient>_{true,pred}`` column, or
            has a non-finite (NaN/inf) value in the latter.
    """
    validate_image_digest(docker_image_digest)  # fail-fast before any I/O

    coarse_df = pd.read_parquet(coarse_predictions_path)
    fine_df = pd.read_parquet(fine_predictions_path)
    _require_predictions_schema(coarse_df)
    _require_predictions_schema(fine_df)
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

    Typed ``float | None`` (not just ``float``): ``train.py``'s ``compute_config_resolved``
    legitimately writes a JSON ``null`` here when between-config variance is (near-)zero, and
    that ``None`` is a meaningful diagnostic result in its own right (near-zero between-config
    signal), not an error to hide -- passed through as-is rather than formatted as ``n/a`` the
    way a figure caption would, since this diagnostic's whole purpose is reporting the exact
    number. (The evidence figure no longer reads config-resolved R²; it reports skill over the
    phase-only baseline.)

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
        ValueError: If ``docker_image_digest`` is a mutable tag, either predictions frame is
            missing ``config_name``/``phase`` or the required ``<coefficient>_{true,pred}``
            column, or has a non-finite (NaN/inf) value in the latter.
        KeyError: If either ``metrics.json`` is missing ``config_resolved``, the
            ``coefficient`` entry within it, or ``config_mean_r2`` -- naming exactly which key
            (see ``_config_resolved_r2``).
    """
    validate_image_digest(docker_image_digest)  # fail-fast before any I/O

    coarse_df = pd.read_parquet(coarse_predictions_path)
    fine_df = pd.read_parquet(fine_predictions_path)
    _require_predictions_schema(coarse_df, required=("config_name", "phase"))
    _require_predictions_schema(fine_df, required=("config_name", "phase"))
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


# =============================================================================================
# Real-data coarse-vs-fine figures (OpenSpec change add-real-comparison-figures).
#
# Three figures, one job each: ``skill_ranges`` (the only cross-grid comparison, under the
# pre-registered overlap rule), ``error_histograms`` (what skill means within each grid) and
# ``cycle_mean_r2_diagnostic`` (why cycle-mean R^2 is ill-conditioned). Every builder reads the
# same eight inputs through one shared loader whose guards run, in a fixed order, before any
# output is written.
# =============================================================================================

import importlib.metadata  # noqa: E402
import io  # noqa: E402
import math  # noqa: E402
import os  # noqa: E402
import platform  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from pathlib import PurePath, PurePosixPath  # noqa: E402

from mosquito_cfd.force_surrogate.train import (  # noqa: E402
    CONVERGED_MIN_WINGBEAT,
    SEED_SWEEP_STATISTICS,
    TARGET_COLUMNS,
    _json_safe,
)

FIGURES: tuple[str, ...] = (
    "skill_ranges",
    "error_histograms",
    "cycle_mean_r2_diagnostic",
)

ROLE_FILES: dict[str, str] = {
    "dataset": "dataset.parquet",
    "predictions": "surrogate/holdout_predictions.parquet",
    "metrics": "surrogate/metrics.json",
    "surrogate_run_metadata": "surrogate/run_metadata.json",
}

_REPO_ROOT = Path(__file__).resolve().parents[3]

# The renderer whose bytes each committed figure records (``renderer_sources``), keyed by fixed
# names and read from the files' own locations, never from the caller's ``root``.
RENDERER_FILES: dict[str, Path] = {
    "comparison_figure.py": Path(__file__).resolve(),
    "scripts/make_coarse_vs_fine_figures.py": _REPO_ROOT
    / "scripts"
    / "make_coarse_vs_fine_figures.py",
}

_LIBRARIES: tuple[str, ...] = ("numpy", "pandas", "pyarrow", "matplotlib")
_PREDICTION_ID_COLUMNS: tuple[str, ...] = ("config_name", "time", "phase", "wingbeat")
_DATASET_COLUMNS: tuple[str, ...] = (
    "config_name",
    "time",
    "phase",
    "wingbeat",
    "split",
)
_KEY = ["config_name", "time"]


@dataclass(frozen=True)
class Corpus:
    """One corpus's validated inputs (the shared loader's output)."""

    name: str
    paths: dict[str, Path]
    sha: dict[str, str]
    dataset: pd.DataFrame
    predictions: pd.DataFrame
    metrics: dict[str, Any]
    surrogate_run_metadata: dict[str, Any]
    n_beats: int


def _reject_constant(token: str) -> float:
    raise ValueError(f"non-finite JSON literal {token!r}")


def _get(node: Any, label: str, *keys: Any) -> Any:
    """``node[k0][k1]...`` or a ``ValueError`` naming ``label`` and the missing path."""
    for depth, key in enumerate(keys):
        ok = (isinstance(node, dict) and key in node) or (
            isinstance(node, list)
            and isinstance(key, int)
            and -len(node) <= key < len(node)
        )
        if not ok:
            path = ".".join(str(k) for k in keys[: depth + 1])
            raise ValueError(f"{label} lacks {path}")
        node = node[key]
    return node


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _load_corpus(root: str | Path, corpus_dir: str | Path, name: str) -> Corpus:
    """Load and validate one corpus: shared guards 2-10, in order (guard 1 is the digest).

    Raises:
        ValueError: On the first guard that fails, naming the corpus, the role and the defect.
    """
    base = Path(root) / corpus_dir
    paths = {role: base / rel for role, rel in ROLE_FILES.items()}
    # Guard 2: each file exists.
    for role, path in paths.items():
        if not path.is_file():
            raise ValueError(f"{name}_{role} input is missing: {path}")
    raw = {role: path.read_bytes() for role, path in paths.items()}
    sha = {role: hashlib.sha256(data).hexdigest() for role, data in raw.items()}

    # Guard 3: each JSON input is an object without a NaN/Infinity literal.
    def load_json(role: str) -> dict[str, Any]:
        try:
            data = json.loads(
                raw[role].decode("utf-8"), parse_constant=_reject_constant
            )
        except ValueError as exc:
            raise ValueError(f"{name}_{role} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(
                f"{name}_{role} must be a JSON object, got {type(data).__name__}"
            )
        return data

    metrics = load_json("metrics")
    run_metadata = load_json("surrogate_run_metadata")
    dataset = pd.read_parquet(io.BytesIO(raw["dataset"]))
    predictions = pd.read_parquet(io.BytesIO(raw["predictions"]))

    # Guard 4: required columns.
    required = {
        "predictions": [
            *_PREDICTION_ID_COLUMNS,
            *(f"{c}_{kind}" for c in TARGET_COLUMNS for kind in ("true", "pred")),
        ],
        "dataset": [*_DATASET_COLUMNS, *TARGET_COLUMNS],
    }
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        missing = [c for c in required[role] if c not in frame.columns]
        if missing:
            raise ValueError(f"{name}_{role} is missing required column(s) {missing}")

    # Guard 5: the dataset is the surrogate's training data.
    inputs = run_metadata.get("inputs")
    recorded = inputs.get("hash") if isinstance(inputs, dict) else None
    if recorded != sha["dataset"]:
        raise ValueError(
            f"{name}_dataset sha256 {sha['dataset']} differs from the {name} surrogate's "
            f"recorded inputs.hash {recorded}; the surrogate was not trained on this dataset"
        )

    # Guard 6: non-empty, at least two configurations, no repeated (config_name, time) key.
    if len(predictions) == 0:
        raise ValueError(f"{name}_predictions is empty")
    if predictions["config_name"].nunique() < 2:
        raise ValueError(f"{name}_predictions has fewer than two configurations")
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        dup = frame.duplicated(_KEY)
        if dup.any():
            first = frame.loc[dup, _KEY].iloc[0].tolist()
            raise ValueError(
                f"{name}_{role} has duplicate (config_name, time) keys, first {first}"
            )

    # Guard 7: every coefficient is finite.
    finite_cols = {
        "predictions": [c for c in required["predictions"] if c.startswith("CF_")],
        "dataset": list(TARGET_COLUMNS),
    }
    for role, frame in (("predictions", predictions), ("dataset", dataset)):
        for col in finite_cols[role]:
            if not np.isfinite(frame[col].to_numpy(dtype=float)).all():
                raise ValueError(f"{name}_{role} has non-finite values in column {col}")

    # Guard 8: beat structure.
    beats = dataset.groupby("config_name")["wingbeat"].agg(
        lambda s: frozenset(s.tolist())
    )
    n_beats = int(dataset["wingbeat"].max()) + 1
    expected = frozenset(range(n_beats))
    bad = [str(cfg) for cfg, got in beats.items() if got != expected]
    if bad:
        raise ValueError(
            f"{name}_dataset: configuration(s) {bad} do not have wingbeats exactly "
            f"0..{n_beats - 1}; every configuration must have the same contiguous wingbeats"
        )
    recorded_min = _get(
        metrics,
        f"{name}_metrics",
        "phase_baseline_skill",
        "phase_baseline",
        "converged_min_wingbeat",
    )
    if recorded_min != CONVERGED_MIN_WINGBEAT:
        raise ValueError(
            f"{name}_metrics phase_baseline.converged_min_wingbeat {recorded_min} != "
            f"train.CONVERGED_MIN_WINGBEAT {CONVERGED_MIN_WINGBEAT}"
        )
    got = set(predictions["wingbeat"].tolist())
    want = set(range(CONVERGED_MIN_WINGBEAT, n_beats))
    if got != want:
        raise ValueError(
            f"{name}_predictions has wingbeats {sorted(got)}; expected exactly {sorted(want)}"
        )

    # Guard 9: the predictions are the dataset's scored holdout rows.
    holdout = dataset[
        (dataset["split"] == "holdout")
        & (dataset["wingbeat"] >= CONVERGED_MIN_WINGBEAT)
    ]
    merged = predictions[[*_KEY, *(f"{c}_true" for c in TARGET_COLUMNS)]].merge(
        holdout[[*_KEY, *TARGET_COLUMNS]], on=_KEY, how="outer", indicator=True
    )
    if not (merged["_merge"] == "both").all():
        raise ValueError(
            f"{name}_predictions rows are not exactly the {name} dataset's holdout rows "
            f"with wingbeat >= {CONVERGED_MIN_WINGBEAT}"
        )
    for c in TARGET_COLUMNS:
        if not np.array_equal(merged[f"{c}_true"].to_numpy(), merged[c].to_numpy()):
            raise ValueError(
                f"{name}_predictions column {c}_true differs from the {name} dataset's "
                "holdout rows"
            )

    # Guard 10: the seed sweep is self-consistent.
    label = f"{name}_metrics"
    sweep = _get(metrics, label, "seed_sweep")
    runs = _get(sweep, label, "runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError(f"{label} seed_sweep.runs is empty")
    for c in TARGET_COLUMNS:
        for stat in SEED_SWEEP_STATISTICS:
            values = [_get(r, label, "per_target", c, stat) for r in runs]
            finite = [float(v) for v in values if not _is_null(v) and math.isfinite(v)]
            want_range = {"min": min(finite), "max": max(finite)} if finite else None
            have_range = _get(sweep, label, "range", c, stat)
            if have_range != want_range:
                raise ValueError(
                    f"{label} seed_sweep.range.{c}.{stat} {have_range} != the NaN-aware "
                    f"min/max of its runs {want_range}"
                )
    primary = _get(sweep, label, "primary_seed")
    if _get(runs[0], label, "seed") != primary:
        raise ValueError(
            f"{label} seed_sweep.runs[0].seed {runs[0]['seed']} is not primary_seed {primary}"
        )
    for c in TARGET_COLUMNS:
        first = _get(runs[0], label, "per_target", c, "skill")
        block = _get(metrics, label, "phase_baseline_skill", "per_target", c, "skill")
        same = (_is_null(first) and _is_null(block)) or (
            not _is_null(first) and not _is_null(block) and first == block
        )
        if not same:
            raise ValueError(
                f"{label} seed_sweep.runs[0] {c} skill {first} != "
                f"phase_baseline_skill.per_target.{c}.skill {block}"
            )
    for c in TARGET_COLUMNS:
        for stat in ("skill", "config_mean_r2"):
            nulls = [r["seed"] for r in runs if _is_null(r["per_target"][c][stat])]
            if nulls and len(nulls) != len(runs):
                raise ValueError(
                    f"{label} {c} {stat} is null for seed(s) {nulls} but not for the others; "
                    "a null is all-or-none per corpus and target"
                )
        for r in runs:
            value = r["per_target"][c]["config_mean_r2"]
            if not _is_null(value) and value > 1:
                raise ValueError(
                    f"{label} {c} config_mean_r2 {value} at seed {r['seed']} exceeds 1"
                )

    return Corpus(
        name=name,
        paths=paths,
        sha=sha,
        dataset=dataset,
        predictions=predictions,
        metrics=metrics,
        surrogate_run_metadata=run_metadata,
        n_beats=n_beats,
    )


def _check_pair(coarse: Corpus, fine: Corpus) -> int:
    """Guard 11: the two corpora are paired. Returns the shared beat count N."""
    sets = [set(c.predictions["config_name"].unique()) for c in (coarse, fine)]
    if sets[0] != sets[1]:
        raise ValueError(
            "coarse and fine holdout configuration sets differ: "
            f"{sorted(sets[0] ^ sets[1])} are in only one"
        )
    seeds = [
        [r["seed"] for r in c.metrics["seed_sweep"]["runs"]] for c in (coarse, fine)
    ]
    if seeds[0] != seeds[1]:
        raise ValueError(f"coarse and fine seed lists differ: {seeds[0]} vs {seeds[1]}")
    for rc, rf in zip(
        coarse.metrics["seed_sweep"]["runs"],
        fine.metrics["seed_sweep"]["runs"],
        strict=True,
    ):
        if rc.get("val_configs") != rf.get("val_configs"):
            raise ValueError(
                f"coarse and fine val_configs differ at seed {rc['seed']}: "
                f"{rc.get('val_configs')} vs {rf.get('val_configs')}"
            )
    if coarse.n_beats != fine.n_beats:
        raise ValueError(
            f"coarse and fine beat counts differ: {coarse.n_beats} vs {fine.n_beats}"
        )
    return coarse.n_beats


def _portable_path(path: str | PurePath, root: str | PurePath) -> str:
    """``path`` relative to ``root``, with forward slashes; refuses anything outside ``root``.

    A relative ``path`` is taken relative to ``root``. Pure path flavours are preserved, so a
    ``PureWindowsPath`` is handled the same on every OS.
    """
    root_p = root if isinstance(root, PurePath) else Path(root)
    path_p = path if isinstance(path, PurePath) else Path(path)
    if not path_p.is_absolute():
        path_p = root_p / path_p
    if ".." in path_p.parts:
        raise ValueError(f"path {path} is outside the root {root} (it contains '..')")
    try:
        rel = path_p.relative_to(root_p)
    except ValueError as exc:
        raise ValueError(f"path {path} is outside the root {root}") from exc
    return PurePosixPath(*rel.parts).as_posix()


def _renderer_sources(files: dict[str, Path] | None = None) -> dict[str, str | None]:
    """sha256 of each renderer file's LF-normalised bytes (``None`` if the file is absent)."""
    files = RENDERER_FILES if files is None else files
    out: dict[str, str | None] = {}
    for key, path in files.items():
        path = Path(path)
        out[key] = (
            hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
            if path.is_file()
            else None
        )
    return out


def _library_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {"python": platform.python_version()}
    for dist in _LIBRARIES:
        try:
            versions[dist] = importlib.metadata.version(dist)
        except importlib.metadata.PackageNotFoundError:
            versions[dist] = None
    return versions


def _provenance(
    *,
    root: str | Path,
    coarse: Corpus,
    fine: Corpus,
    docker_image_digest: str,
    timestamp: str,
    figure: str,
    renderer_files: dict[str, Path] | None = None,
) -> dict[str, Any]:
    """The figure's ``run_metadata.json`` payload (CC-1 triple plus every input's hash)."""
    input_files = {
        f"{corpus.name}_{role}": {
            "path": _portable_path(corpus.paths[role], root),
            "sha256": corpus.sha[role],
        }
        for corpus in (coarse, fine)
        for role in ROLE_FILES
    }
    images = {}
    for corpus in (coarse, fine):
        image = corpus.surrogate_run_metadata.get("docker_image")
        if not isinstance(image, str):
            raise ValueError(f"{corpus.name}_surrogate_run_metadata lacks docker_image")
        images[corpus.name] = image
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        timestamp=timestamp,
        extra={
            "input_files": input_files,
            "corpus_docker_images": images,
            "library_versions": _library_versions(),
            "renderer_sources": _renderer_sources(renderer_files),
            "figure": figure,
        },
    )
    metadata["inputs"] = {
        "file": input_files["coarse_metrics"]["path"],
        "hash": input_files["coarse_metrics"]["sha256"],
    }
    return metadata


def _plain(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays to built-ins (NaN/inf become None later)."""
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_plain(v) for v in obj.tolist()]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    return obj


def _dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(_json_safe(_plain(payload)), indent=2, ensure_ascii=False).encode(
        "utf-8"
    )


def _write_outputs(
    out_dir: str | Path,
    figure: str,
    fig: Any,
    metrics: dict[str, Any],
    metadata: dict[str, Any],
) -> None:
    """Write ``<figure>.png``, ``_metrics.json``, ``_run_metadata.json`` (in that order).

    The PNG is rendered into memory and the figure closed before anything touches the disk; each
    file is written to a temporary name and moved into place with ``os.replace``. A failure
    between two moves leaves exactly the files already moved and no temporary file.
    """
    out_dir = Path(out_dir)
    try:
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=200, bbox_inches="tight")
    finally:
        plt.close(fig)
    payloads = [
        (f"{figure}.png", buffer.getvalue()),
        (f"{figure}_metrics.json", _dumps(metrics)),
        (f"{figure}_run_metadata.json", _dumps(metadata)),
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    staged: list[tuple[Path, Path]] = []
    try:
        for name, data in payloads:
            tmp = out_dir / f".{name}.tmp"
            tmp.write_bytes(data)
            staged.append((tmp, out_dir / name))
        for tmp, dst in staged:
            os.replace(tmp, dst)
    finally:
        for tmp, _ in staged:
            if tmp.exists():
                tmp.unlink()


def _prepare(
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    docker_image_digest: str,
) -> tuple[Path, Corpus, Corpus, int]:
    """Guard 1 (the digest, before any file), then the shared loader and the pairing guard."""
    validate_image_digest(docker_image_digest)
    root = Path(root)
    coarse = _load_corpus(root, coarse_dir, "coarse")
    fine = _load_corpus(root, fine_dir, "fine")
    return root, coarse, fine, _check_pair(coarse, fine)


def build_skill_ranges(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Stub until section 4 (validates inputs only)."""
    _prepare(root, coarse_dir, fine_dir, docker_image_digest)
    raise NotImplementedError("skill_ranges")


def build_error_histograms(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Stub until section 5 (validates inputs only)."""
    _prepare(root, coarse_dir, fine_dir, docker_image_digest)
    raise NotImplementedError("error_histograms")


def build_cycle_mean_r2_diagnostic(
    *,
    root: str | Path,
    coarse_dir: str | Path,
    fine_dir: str | Path,
    out_dir: str | Path,
    docker_image_digest: str,
    timestamp: str,
) -> dict[str, Any]:
    """Stub until section 6 (validates inputs only)."""
    _prepare(root, coarse_dir, fine_dir, docker_image_digest)
    raise NotImplementedError("cycle_mean_r2_diagnostic")
