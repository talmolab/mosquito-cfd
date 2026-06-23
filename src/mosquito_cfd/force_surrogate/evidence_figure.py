"""Predicted-vs-CFD evidence figure for the force surrogate (Track B PR6, force-only).

Reads the committed PR5 artifacts (``holdout_predictions.parquet`` + ``metrics.json``) and
emits the NVIDIA-grant *Evidence-of-Readiness* figure: predicted-vs-CFD scatter for
``CF_x / CF_z / CF_my`` on the held-out configurations (points colored by config with a shared
legend) and an honest caption + batched-throughput speedup annotation. The translational
Sane-Dickinson quasi-steady model is computed as a **reference number** (overshoot factor), not
drawn on the scatter — at this coarse grid it overshoots the (IB-biased) CFD, so an overlay
would mostly re-display the ~2.4x diffused-IB bias rather than surrogate skill (CC-4 deviation,
design D2). No solver, cluster, GPU, or plotfile (CC-6); the metrics the trainer already
computed are *read*, never re-derived.

Design decisions (change ``add-force-surrogate-evidence-figure``): D1 (CF_my headline,
named as a component — issue #1), D2 (translational Sane-Dickinson via the CC-3
``compute_force_reference`` helper; reference-only, not overlaid), D3 (honest caption, split
compact-caption vs README), D4 (batched-throughput >1,000x speedup, disclosed as batch-size
driven; ~310x latency floor).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # headless: figures are written, never shown (matches examples/*)

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from mosquito_cfd.force_surrogate.constants import (  # noqa: E402
    CHORD,
    R_TIP,
    RHO,
    SPAN,
)
from mosquito_cfd.force_surrogate.normalization import (  # noqa: E402
    compute_force_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (  # noqa: E402
    capture_surrogate_run_metadata,
)
from mosquito_cfd.force_surrogate.train import write_json  # noqa: E402

# The three figure axes. CF_my is the headline moment (design D1): the only moment with
# genuine config-resolved signal; labeled an "M_y component", not "pitch moment" (issue #1).
PANEL_COEFFICIENTS: tuple[str, str, str] = ("CF_x", "CF_z", "CF_my")
MOMENT_PANEL = "CF_my"
LIFT_PANEL = "CF_z"

# Coarse-grid A40 CFD cost (~2.4 min/wingbeat; roadmap Hardware row). Used only for the
# speedup denominator, which the annotation labels "coarse-grid A40 CFD" (design D4).
CFD_SECONDS_PER_WINGBEAT = 144.0

_README_POINTER = "examples/prelim_sweep/README.md"
_CONFIG_RE = re.compile(r"^s(\d+)_f(\d+)_p(\d+)$")
_BATCH_RE = re.compile(r"passes of (\d+) rows")

# Columns the figure requires from the predictions parquet (besides config_name/phase).
_REQUIRED_PRED_COLUMNS: tuple[str, ...] = ("config_name", "phase") + tuple(
    f"{c}_{kind}" for c in PANEL_COEFFICIENTS for kind in ("true", "pred")
)


@dataclass(frozen=True)
class KinematicParams:
    """Kinematic parameters parsed from a sweep ``config_name``.

    Attributes:
        phi_amp_deg: Stroke amplitude [deg].
        f_star: Dimensionless flap frequency.
        pitch_amp_deg: Pitch amplitude [deg].
    """

    phi_amp_deg: float
    f_star: float
    pitch_amp_deg: float


def parse_config_name(name: str) -> KinematicParams:
    """Parse a ``s<phi>_f<fff>_p<pitch>`` config name into kinematic parameters.

    The frequency field is encoded as ``f* * 100`` (``f085`` -> 0.85, ``f100`` -> 1.0,
    ``f115`` -> 1.15); stroke and pitch are integer degrees.

    Args:
        name: Configuration name, e.g. ``"s45_f115_p60"``.

    Returns:
        The parsed :class:`KinematicParams`.

    Raises:
        ValueError: If ``name`` does not match the ``s<int>_f<int>_p<int>`` grammar.
    """
    match = _CONFIG_RE.match(name)
    if match is None:
        raise ValueError(
            f"config_name {name!r} does not match the expected 's<phi>_f<fff>_p<pitch>' "
            "grammar (e.g. 's45_f115_p60')"
        )
    stroke, freq, pitch = match.groups()
    return KinematicParams(
        phi_amp_deg=float(stroke),
        f_star=float(freq) / 100.0,
        pitch_amp_deg=float(pitch),
    )


def lift_coefficient_dickinson(alpha_deg: np.typing.ArrayLike) -> np.ndarray:
    """Dickinson-Lehmann-Sane (1999) Robofly empirical lift-coefficient fit.

    ``C_L(alpha) = 0.225 + 1.58 * sin(2.13*alpha_deg - 7.2deg)``. The argument is evaluated
    in radians; because ``radians()`` is linear, ``radians(2.13*alpha_deg) = 2.13*alpha_rad``
    exactly (the per-degree slope is preserved, not rescaled — design D2).

    Args:
        alpha_deg: Angle(s) of attack [deg]. Scalar or array-like.

    Returns:
        The lift coefficient(s), preserving input shape.
    """
    alpha = np.asarray(alpha_deg, dtype=float)
    return 0.225 + 1.58 * np.sin(np.radians(2.13 * alpha - 7.2))


def _rows_by_config(predictions: pd.DataFrame) -> dict[str, int]:
    """Actual converged-beat row count per config, from the parquet (design D4).

    Design D4 defines ``rows_per_wingbeat(cfg)`` as the **parquet rows for cfg** (the real
    converged-beat count, which can differ by one row from the theoretical ``1/(f*·dt)`` at
    the beat boundary). Using the data — not the analytic value — keeps the committed sidecar
    consistent with the file it describes.

    Args:
        predictions: Holdout predictions frame with a ``config_name`` column.

    Returns:
        Mapping of ``config_name`` to its row count.
    """
    return {
        str(k): int(v) for k, v in predictions.groupby("config_name").size().items()
    }


def sane_dickinson_cf_z(
    phase: np.typing.ArrayLike,
    *,
    f_star: float,
    phi_amp_deg: float,
    pitch_amp_deg: float,
) -> np.ndarray:
    """Translational-only Sane-Dickinson quasi-steady lift coefficient (design D2).

    ``CF_trans(t) = F_trans / F_ref = (U/U_tip)^2 * C_L(alpha_eff)`` with
    ``U/U_tip = cos(2*pi*phase)`` and the symmetric-rotation hovering AoA
    ``alpha_eff = pitch_amp * |cos(2*pi*phase)|``. The reference force ``F_ref`` and tip
    speed come from the single-source :func:`compute_force_reference` (CC-3); the force is
    divided by that ``F_ref`` explicitly (no inline re-derivation), so a different ``f_ref``
    from the helper changes the result.

    Args:
        phase: Cyclic phase in [0, 1). Scalar or array-like.
        f_star: Dimensionless flap frequency.
        phi_amp_deg: Stroke amplitude [deg].
        pitch_amp_deg: Pitch amplitude [deg].

    Returns:
        The dimensionless quasi-steady lift coefficient, preserving input shape.
    """
    ph = np.asarray(phase, dtype=float)
    u_ratio = np.cos(2.0 * np.pi * ph)
    alpha_eff = pitch_amp_deg * np.abs(u_ratio)
    c_l = lift_coefficient_dickinson(alpha_eff)
    ref = compute_force_reference(f_star, phi_amp_deg, R_TIP, SPAN, CHORD, rho=RHO)
    f_trans = ref.q_tip * ref.area * u_ratio**2 * c_l
    return f_trans / ref.f_ref


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    """Return ``mapping[key]`` or raise a clear KeyError naming the missing key + context."""
    if key not in mapping:
        raise KeyError(f"metrics is missing required key {key!r} ({ctx})")
    return mapping[key]


def _config_mean_r2(metrics: dict[str, Any], coef: str) -> float | None:
    """Read ``config_resolved.<coef>.config_mean_r2`` (may be ``None`` NaN-sentinel)."""
    cr = _require(metrics, "config_resolved", "config-resolved skill block")
    entry = _require(cr, coef, f"config_resolved entry for {coef}")
    return entry.get("config_mean_r2")


def _per_target_rmse(metrics: dict[str, Any], coef: str) -> float:
    """Read ``per_target.<coef>.rmse`` (clear error if any level is missing)."""
    pt = _require(metrics, "per_target", "per-target metrics block")
    entry = _require(pt, coef, f"per_target entry for {coef}")
    return _require(entry, "rmse", f"per_target.{coef}.rmse")


def _fmt_r2(value: float | None) -> str:
    """Format a config-resolved R2, rendering the ``None`` NaN-sentinel as 'n/a'."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "n/a"
    return f"{value:.2f}"


def panel_annotation(metrics: dict[str, Any], coef: str) -> str:
    """Per-panel annotation: config-resolved R2 + RMSE, read from ``metrics`` (not literals).

    Args:
        metrics: The loaded ``metrics.json`` dict.
        coef: Panel coefficient, e.g. ``"CF_z"``.

    Returns:
        A short two-line annotation string.

    Raises:
        KeyError: If a required metrics key for ``coef`` is missing.
    """
    r2 = _fmt_r2(_config_mean_r2(metrics, coef))
    rmse = _per_target_rmse(metrics, coef)
    return f"config-R² = {r2}\nRMSE = {rmse:.3f}"


def compute_speedup(
    inference: dict[str, Any], rows_per_wingbeat: int
) -> dict[str, Any]:
    """Decompose the inference-vs-CFD speedup into throughput (headline) and latency (floor).

    The headline >1,000x is **batched GPU throughput** vs the coarse-grid A40 CFD rate;
    because it equals ``latency_speedup * batch_size`` (the surrogate batches; the CFD is a
    sequential time integration), the batch size and parallelism factor are returned for
    honest disclosure (design D4).

    Args:
        inference: The ``metrics.json`` ``inference`` block (``latency_ms``,
            ``throughput_rows_per_s``, ``basis``).
        rows_per_wingbeat: Converged-beat rows for the representative config.

    Returns:
        A dict with ``throughput_speedup``, ``latency_speedup``, ``batch_size``,
        ``parallelism_factor``, ``cfd_rows_per_s``, ``cfd_seconds_per_wingbeat``,
        ``rows_per_wingbeat``, ``surrogate_throughput_rows_per_s``,
        ``surrogate_latency_ms``, and ``cfd_rate_is_sequential`` (True).

    Raises:
        KeyError: If ``inference`` lacks ``latency_ms`` or ``throughput_rows_per_s``.
    """
    throughput = _require(inference, "throughput_rows_per_s", "inference throughput")
    latency_ms = _require(inference, "latency_ms", "inference latency")
    cfd_rows_per_s = rows_per_wingbeat / CFD_SECONDS_PER_WINGBEAT
    t_cfd_per_row_s = CFD_SECONDS_PER_WINGBEAT / rows_per_wingbeat
    throughput_speedup = throughput / cfd_rows_per_s
    latency_speedup = t_cfd_per_row_s / (latency_ms / 1000.0)
    batch_match = _BATCH_RE.search(inference.get("basis", ""))
    batch_size = int(batch_match.group(1)) if batch_match else None
    return {
        "throughput_speedup": throughput_speedup,
        "latency_speedup": latency_speedup,
        "batch_size": batch_size,
        "parallelism_factor": throughput_speedup / latency_speedup,
        "cfd_rows_per_s": cfd_rows_per_s,
        "cfd_seconds_per_wingbeat": CFD_SECONDS_PER_WINGBEAT,
        "rows_per_wingbeat": rows_per_wingbeat,
        "surrogate_throughput_rows_per_s": throughput,
        "surrogate_latency_ms": latency_ms,
        "cfd_rate_is_sequential": True,
    }


def build_caption(
    metrics: dict[str, Any], speedup: dict[str, Any], baseline: dict[str, Any]
) -> str:
    """Build the compact, honest figure caption (design D3; full prose lives in the README).

    A positive headline (per-axis config-resolved R2/RMSE + the batched >1,000x speedup), a
    terse "Caveats:" line, a terse quasi-steady-reference line, and a README pointer.
    CF_x/CF_my read as dominant; the off-panel CF_y negative R2 is a subordinate honesty flag.

    Args:
        metrics: The loaded ``metrics.json`` dict.
        speedup: The :func:`compute_speedup` result.
        baseline: The :func:`_baseline_reference` result (overshoot factor for the caption).

    Returns:
        The multi-line caption string. Every number is read from the artifacts.
    """
    r2 = {c: _fmt_r2(_config_mean_r2(metrics, c)) for c in PANEL_COEFFICIENTS}
    rmse = {c: _per_target_rmse(metrics, c) for c in PANEL_COEFFICIENTS}
    cf_y = _config_mean_r2(metrics, "CF_y")
    agg = _require(metrics, "aggregate", "aggregate metrics")["r2"]
    thr = speedup["throughput_speedup"]
    lat = speedup["latency_speedup"]
    batch = speedup["batch_size"]
    overshoot = baseline["overshoot_factor"]
    headline = (
        f"Predicted-vs-CFD force coefficients on held-out configurations. "
        f"Config-resolved R²: CF_x {r2['CF_x']}, CF_z {r2['CF_z']}, "
        f"CF_m (M_y) {r2['CF_my']}; RMSE {rmse['CF_x']:.3f}/{rmse['CF_z']:.3f}/"
        f"{rmse['CF_my']:.3f}. Surrogate inference >1,000x faster than CFD "
        f"(batched GPU throughput ~{thr:.1e}x, N={batch} parallel evals vs sequential "
        f"coarse-grid A40 CFD; per-evaluation latency floor ~{lat:.0f}x)."
    )
    caveats = (
        f"Caveats: aggregate pointwise R²~{agg:.2f} is waveform-dominated and overstates "
        f"skill (CF_y config-resolved R² = {_fmt_r2(cf_y)} < 0). Coarse 64x32x64 grid, "
        f"~2.4x diffused-IB force underestimate: pipeline readiness, not validated "
        f"aerodynamics. Moment is the M_y component (axis convention, issue #1); "
        f"CF_mx/CF_mz omitted (waveform-only, no between-config signal)."
    )
    reference = (
        f"Quasi-steady reference (not plotted): an uncalibrated translational Sane-Dickinson "
        f"model overshoots the coarse-grid CFD lift ~{overshoot:.1f}x (RMS) — dominated by "
        f"the ~2.4x diffused-IB underestimate plus quasi-steady tip-velocity overprediction — "
        f"so it is not used as a quantitative baseline at this resolution."
    )
    return f"{headline}\n{caveats}\n{reference}\nFull discussion: {_README_POINTER}."


def _baseline_for_config(df_cfg: pd.DataFrame) -> np.ndarray:
    """Sane-Dickinson CF_z prediction for one config's rows."""
    kin = parse_config_name(str(df_cfg["config_name"].iloc[0]))
    return sane_dickinson_cf_z(
        df_cfg["phase"].to_numpy(),
        f_star=kin.f_star,
        phi_amp_deg=kin.phi_amp_deg,
        pitch_amp_deg=kin.pitch_amp_deg,
    )


def _rmse(true: np.ndarray, pred: np.ndarray) -> float:
    """Root-mean-square error."""
    return float(np.sqrt(np.mean((np.asarray(true) - np.asarray(pred)) ** 2)))


def _baseline_reference(predictions: pd.DataFrame) -> dict[str, Any]:
    """Translational Sane-Dickinson CF_z reference (computed, NOT overlaid on the figure).

    The uncalibrated quasi-steady model overshoots the coarse-grid CFD lift, dominated by the
    ~2.4x diffused-IB underestimate (the CFD is biased low) plus the model's tip-velocity
    overprediction — so the gap mostly re-displays the IB bias rather than surrogate skill.
    It is therefore reported as a reference number (RMSE + overshoot factor), not drawn as a
    misleading scatter overlay (design D2; CC-4 deviation recorded in the proposal).

    Args:
        predictions: Holdout predictions frame.

    Returns:
        ``{baseline_rmse_cf_z, overshoot_factor, note}`` — ``overshoot_factor`` is
        ``rms(baseline) / rms(cfd_true)`` over CF_z.
    """
    true, pred = [], []
    for cfg in sorted(predictions["config_name"].unique()):
        d = predictions[predictions["config_name"] == cfg]
        true.append(d[f"{LIFT_PANEL}_true"].to_numpy())
        pred.append(_baseline_for_config(d))
    t, p = np.concatenate(true), np.concatenate(pred)
    rms_true = float(np.sqrt(np.mean(t**2)))
    rms_pred = float(np.sqrt(np.mean(p**2)))
    return {
        "baseline_rmse_cf_z": _rmse(t, p),
        "overshoot_factor": rms_pred / rms_true if rms_true > 0 else float("nan"),
        "note": (
            "uncalibrated translational Sane-Dickinson quasi-steady CF_z; NOT overlaid on the "
            "figure — overshoots coarse-grid CFD (dominated by the ~2.4x diffused-IB "
            "underestimate + tip-velocity overprediction), so not a quantitative baseline here"
        ),
    }


def _panel_title(coef: str) -> str:
    """Axis title for a panel coefficient (CF_my labeled an M_y component, not 'pitch')."""
    if coef == MOMENT_PANEL:
        return "CF_m  (aerodynamic moment, M_y component)"
    label = "lift / span-normal" if coef == LIFT_PANEL else "stroke-axis"
    return f"{coef}  ({label} force)"


def build_figure(predictions: pd.DataFrame, metrics: dict[str, Any]) -> plt.Figure:
    """Assemble the three-panel predicted-vs-CFD evidence figure (object model, no I/O).

    Args:
        predictions: Holdout predictions frame (``config_name, phase, CF_*_{true,pred}``).
        metrics: The loaded ``metrics.json`` dict.

    Returns:
        A :class:`matplotlib.figure.Figure` with three predicted-vs-CFD scatter panels
        (CF_x, CF_z, CF_my), points colored by held-out configuration with a shared legend.
    """
    _validate_predictions(predictions)
    configs = sorted(predictions["config_name"].unique())
    cmap = plt.get_cmap("tab10")
    color = {cfg: cmap(i % 10) for i, cfg in enumerate(configs)}

    speedup = compute_speedup(
        _require(metrics, "inference", "inference block"),
        _representative_rows(predictions),
    )
    baseline = _baseline_reference(predictions)

    fig, axes = plt.subplots(1, 3, figsize=(13.5, 5.2))
    for ax, coef in zip(axes, PANEL_COEFFICIENTS, strict=True):
        true_col, pred_col = f"{coef}_true", f"{coef}_pred"
        lo = min(predictions[true_col].min(), predictions[pred_col].min())
        hi = max(predictions[true_col].max(), predictions[pred_col].max())
        ax.plot(
            [lo, hi],
            [lo, hi],
            color="0.5",
            lw=0.8,
            ls="--",
            zorder=0,
            label="1:1 (perfect)",
        )
        for cfg in configs:
            d = predictions[predictions["config_name"] == cfg]
            ax.scatter(d[true_col], d[pred_col], s=8, color=color[cfg], alpha=0.7)
        ax.text(
            0.97,
            0.03,
            panel_annotation(metrics, coef),
            transform=ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=8,
        )
        ax.set_title(_panel_title(coef), fontsize=9)
        ax.set_xlabel("CFD (true)", fontsize=8)
        ax.set_ylabel("surrogate (predicted)", fontsize=8)

    # Shared config->color legend (so the colors are readable) + the 1:1 line, at the top.
    config_handles = [
        Line2D([], [], marker="o", ls="", color=color[cfg], label=cfg, markersize=5)
        for cfg in configs
    ]
    one_to_one = Line2D([], [], color="0.5", lw=0.8, ls="--", label="1:1 (perfect)")
    fig.legend(
        handles=[*config_handles, one_to_one],
        loc="upper center",
        ncol=len(configs) + 1,
        fontsize=7,
        title="held-out configurations (one color each)",
        title_fontsize=7,
        bbox_to_anchor=(0.5, 1.02),
    )

    fig.text(
        0.5,
        -0.04,
        build_caption(metrics, speedup, baseline),
        ha="center",
        va="top",
        fontsize=6.5,
        wrap=True,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return fig


def _representative_rows(predictions: pd.DataFrame) -> int:
    """Actual converged-beat rows of the config closest to f*=1.0 (speedup headline).

    The representative is the config nearest f*=1.0 (for the validated holdout that is the
    f*=1.0 config, 2000 rows); its **actual** parquet row count is used so the headline
    speedup matches the committed data (design D4).
    """
    rows = _rows_by_config(predictions)
    rep = min(rows, key=lambda c: abs(parse_config_name(c).f_star - 1.0))
    return rows[rep]


def _validate_predictions(predictions: pd.DataFrame) -> None:
    """Validate the predictions frame: required columns present and CF_* values finite.

    Raises a clear ``ValueError`` if a required column is missing or if any coefficient
    column contains NaN/inf — a non-finite coefficient would otherwise produce a silently
    wrong (``nan``) evidence artifact (the figure's whole purpose is an *honest* number).
    """
    missing = [c for c in _REQUIRED_PRED_COLUMNS if c not in predictions.columns]
    if missing:
        raise ValueError(
            f"predictions parquet is missing required column(s) {missing}; the figure needs "
            f"{list(_REQUIRED_PRED_COLUMNS)}"
        )
    coef_cols = [c for c in _REQUIRED_PRED_COLUMNS if c.startswith("CF_")]
    nonfinite = [
        c for c in coef_cols if not np.isfinite(predictions[c].to_numpy()).all()
    ]
    if nonfinite:
        raise ValueError(
            f"predictions parquet has non-finite (NaN/inf) values in coefficient column(s) "
            f"{nonfinite}; refusing to emit a silently-wrong evidence figure"
        )


def _sha256(path: Path) -> str:
    """SHA256 hex digest of a file's bytes."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate_evidence_figure(
    *,
    predictions_path: Path,
    metrics_path: Path,
    out_dir: Path,
    docker_image_digest: str,
    timestamp: str,
    seeds: dict[str, int] | None = None,
    dpi: int = 200,
) -> dict[str, Any]:
    """Generate + write the evidence figure, its metrics sidecar, and run provenance.

    Force-only (CC-6): the only inputs are the committed predictions parquet and metrics.json.

    Args:
        predictions_path: Committed ``holdout_predictions.parquet``.
        metrics_path: Committed ``metrics.json``.
        out_dir: Output directory (``examples/prelim_sweep/figures/``).
        docker_image_digest: Pinned ``sha256:`` image digest (mutable tags rejected, CC-1).
        timestamp: Caller-supplied ISO-8601 timestamp (no wall-clock baked in, CC-1).
        seeds: Optional seed dict recorded in provenance.
        dpi: Raster resolution (>=200).

    Returns:
        The ``evidence_figure_metrics.json`` payload (per-axis surrogate RMSE, CF_z baseline
        RMSE, the annotated config-resolved R2, and the speedup decomposition).

    Raises:
        ValueError: If the digest is a mutable tag, or the predictions have <2 configs / 0 rows.
    """
    # --- Validate + compute EVERYTHING fallible first; only then touch the filesystem, so a
    #     late failure can never leave a partial artifact set (no orphan PNG).
    from mosquito_cfd.force_surrogate.sidecar import validate_image_digest

    validate_image_digest(docker_image_digest)  # fail-fast on a mutable tag

    predictions = pd.read_parquet(predictions_path)
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))
    if not isinstance(metrics, dict):
        raise ValueError(
            f"metrics.json must be a JSON object, got {type(metrics).__name__}"
        )
    _validate_predictions(predictions)
    configs = sorted(predictions["config_name"].unique())
    if len(predictions) == 0 or len(configs) < 2:
        raise ValueError(
            "evidence figure requires >=2 holdout configurations and a non-empty "
            f"predictions frame (got {len(configs)} configs, {len(predictions)} rows); the "
            "config-resolved scatter is undefined otherwise"
        )

    fig = build_figure(predictions, metrics)
    speedup = compute_speedup(
        _require(metrics, "inference", "inference block"),
        _representative_rows(predictions),
    )
    baseline = _baseline_reference(predictions)

    fig_metrics: dict[str, Any] = {
        "surrogate_rmse": {c: _per_target_rmse(metrics, c) for c in PANEL_COEFFICIENTS},
        "config_mean_r2": {c: _config_mean_r2(metrics, c) for c in PANEL_COEFFICIENTS},
        "quasi_steady_reference": baseline,
        "speedup": speedup,
        "rows_per_wingbeat_per_config": _rows_by_config(predictions),
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_image_digest,
        inputs_file=Path(
            predictions_path
        ),  # records inputs.file + inputs.hash (predictions)
        timestamp=timestamp,
        extra={
            # The helper hashes only the single inputs_file; record the *second* input's hash
            # under a distinct key so the built-in inputs.file/hash is not clobbered.
            "metrics_json_sha256": _sha256(metrics_path),
            "seeds": seeds or {},
        },
    )

    # --- All computation succeeded: write the three artifacts together.
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "evidence_figure.png", dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    write_json(out_dir / "evidence_figure_metrics.json", fig_metrics)
    write_json(out_dir / "run_metadata.json", metadata)
    return fig_metrics
