"""Predicted-vs-CFD evidence figure for the force surrogate (Track B PR6, force-only).

Reads the committed PR5 artifacts (``holdout_predictions.parquet`` + ``metrics.json``) and
emits the NVIDIA-grant *Evidence-of-Readiness* figure: predicted-vs-CFD scatter for
``CF_x / CF_z / CF_my`` on the held-out configurations (points colored by config with a shared
legend) and an honest caption + batched-throughput speedup annotation. The translational
Sane-Dickinson quasi-steady model is computed as a **reference number** (RMS ratio), not
drawn on the scatter — the uncalibrated translational model is a poor fit to the CFD lift (it
omits rotational, added-mass, and LEV lift), so an overlay would mostly re-display the model's
analytic loops rather than surrogate skill (CC-4 deviation). No solver, cluster, GPU, or plotfile
(CC-6); the metrics the trainer already computed are *read*, never re-derived.

Design decisions (change ``add-force-surrogate-evidence-figure``): D1 (CF_my headline,
named as a lab-frame component), D2 (translational Sane-Dickinson via the CC-3
``compute_force_reference`` helper; reference-only, not overlaid), D3 (honest caption, split
compact-caption vs README), D4 (batched-throughput >1,000x speedup, disclosed as batch-size
driven; the latency floor is read from ``metrics.json`` each run, never a fixed number — it has
already changed with every corpus regeneration).
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
    R_GYRATION,
    RHO,
    SPAN,
)
from mosquito_cfd.force_surrogate.normalization import (  # noqa: E402
    compute_force_reference,
)
from mosquito_cfd.force_surrogate.sidecar import (  # noqa: E402
    capture_surrogate_run_metadata,
)
from mosquito_cfd.force_surrogate.train import (  # noqa: E402
    TARGET_COLUMNS,
    write_json,
)

# The three figure axes. CF_my is the fixed headline moment (design D1) — labeled an "M_y
# component", not "pitch moment" (moments are lab-frame; the wing-frame conversion is not
# currently tracked). D1 originally picked CF_my because it was the only moment with
# config-resolved signal in the first corpus; which moment carries the most is corpus-dependent
# and has already inverted more than once, so it is NOT re-derived here — the panel set stays
# fixed, and build_caption() discloses the actual off-panel numbers instead of assuming which
# axis (if any) is signal-free.
PANEL_COEFFICIENTS: tuple[str, str, str] = ("CF_x", "CF_z", "CF_my")
MOMENT_PANEL = "CF_my"
LIFT_PANEL = "CF_z"
# All six targets (the trainer's own list): the caption's skill floor and the sidecar cover
# every one (issue #116).
TARGETS: tuple[str, ...] = tuple(TARGET_COLUMNS)
# The one phrase used wherever a sweep has a single seed (never an implied spread).
_SINGLE_SEED = "single seed, no range"

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
    ref = compute_force_reference(f_star, phi_amp_deg, R_GYRATION, SPAN, CHORD, rho=RHO)
    f_trans = ref.q_ref * ref.area * u_ratio**2 * c_l
    return f_trans / ref.f_ref


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    """Return ``mapping[key]`` or raise a clear KeyError naming the missing key + context."""
    if key not in mapping:
        raise KeyError(f"metrics is missing required key {key!r} ({ctx})")
    return mapping[key]


def _per_target(metrics: dict[str, Any], coef: str) -> dict[str, Any]:
    """Read ``per_target.<coef>`` (clear error if any level is missing)."""
    pt = _require(metrics, "per_target", "per-target metrics block")
    return _require(pt, coef, f"per_target entry for {coef}")


def _per_target_rmse(metrics: dict[str, Any], coef: str) -> float:
    """Read ``per_target.<coef>.rmse`` (clear error if any level is missing)."""
    return _require(_per_target(metrics, coef), "rmse", f"per_target.{coef}.rmse")


def _skill_entry(metrics: dict[str, Any], coef: str) -> dict[str, Any]:
    """Read ``phase_baseline_skill.per_target.<coef>`` (skill + the phase-only baseline's R²)."""
    block = _require(metrics, "phase_baseline_skill", "phase-only baseline skill block")
    per_target = _require(block, "per_target", "phase_baseline_skill.per_target")
    return _require(per_target, coef, f"phase_baseline_skill entry for {coef}")


def _pointwise_r2(metrics: dict[str, Any], coef: str) -> float | None:
    """Read ``per_target.<coef>.r2`` (``None`` is the NaN sentinel; a missing key raises)."""
    return _require(_per_target(metrics, coef), "r2", f"per_target.{coef}.r2")


def _phase_baseline_r2(metrics: dict[str, Any], coef: str) -> float | None:
    """Read ``phase_baseline_skill.per_target.<coef>.phase_baseline_r2`` (missing raises)."""
    return _require(
        _skill_entry(metrics, coef),
        "phase_baseline_r2",
        f"phase_baseline_skill.per_target.{coef}.phase_baseline_r2",
    )


def _seed_sweep(metrics: dict[str, Any]) -> dict[str, Any]:
    """Read the ``seed_sweep`` block; a metrics.json without one is rejected (no default seed).

    The plotted seed must be listed first: the provenance records ``seeds[1:]`` as the sweep.
    """
    sweep = _require(metrics, "seed_sweep", "seed-sweep block")
    primary = _require(sweep, "primary_seed", "seed_sweep.primary_seed")
    seeds = _require(sweep, "seeds", "seed_sweep.seeds")
    if not seeds or seeds[0] != primary:
        raise ValueError(
            f"seed_sweep.seeds {seeds} must list the primary seed first ({primary})"
        )
    return sweep


def _skill_range(metrics: dict[str, Any], coef: str) -> dict[str, Any] | None:
    """Read ``seed_sweep.range.<coef>.skill`` (``None`` when null for every seed)."""
    ranges = _require(_seed_sweep(metrics), "range", "seed_sweep.range")
    entry = _require(ranges, coef, f"seed_sweep range for {coef}")
    return _require(entry, "skill", f"seed_sweep.range.{coef}.skill")


def _is_null(value: float | None) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value))


def format_metric(value: float | None) -> str:
    """Render a skill or R² value for the figure (design D6).

    Three decimals; a value that would print ``1.000`` prints ``>0.999``; a nonzero value that
    would print ``±0.000`` prints in scientific form (so a below-baseline flag never reads
    ``0.000``); negatives use U+2212; a null (the NaN sentinel) prints ``n/a``.
    """
    if _is_null(value):
        return "n/a"
    if value == 0:  # including -0.0, which is not below anything
        return "0.000"
    text = f"{value:.3f}"
    if text == "1.000":
        return ">0.999"
    if text in ("0.000", "-0.000") and value != 0:
        text = f"{value:.1e}"
    return "−" + text[1:] if text.startswith("-") else text


def _seed_count(metrics: dict[str, Any]) -> int:
    return len(_require(_seed_sweep(metrics), "seeds", "seed_sweep.seeds"))


def _skill_with_range(metrics: dict[str, Any], coef: str) -> str:
    """``"0.988 (5 seeds: 0.988 to 0.992)"``, or ``"... (single seed, no range)"``."""
    skill = format_metric(_require(_skill_entry(metrics, coef), "skill", coef))
    k = _seed_count(metrics)
    rng = _skill_range(metrics, coef)
    if k == 1:
        return f"{skill} ({_SINGLE_SEED})"
    if rng is None:
        return f"{skill} ({k} seeds: n/a)"
    return f"{skill} ({k} seeds: {format_metric(rng['min'])} to {format_metric(rng['max'])})"


def panel_annotation(metrics: dict[str, Any], coef: str) -> str:
    """Per-panel annotation: skill (with seed range), pointwise R² and RMSE from ``metrics``.

    Skill is over the phase-only baseline; every value is read, never a literal.

    Args:
        metrics: The loaded ``metrics.json`` dict.
        coef: Panel coefficient, e.g. ``"CF_z"``.

    Returns:
        A short two-line annotation string.

    Raises:
        KeyError: If a required metrics key for ``coef`` is missing.
    """
    r2 = format_metric(_pointwise_r2(metrics, coef))
    rmse = _per_target_rmse(metrics, coef)
    return f"skill {_skill_with_range(metrics, coef)}\nR² {r2} · RMSE {rmse:.3f}"


def skill_floor(metrics: dict[str, Any]) -> dict[str, Any]:
    """The skill floor over all six targets' seed-sweep minima (design D6).

    The floor is reported instead of a "weakest target": overlapping seed ranges do not support
    a ranking. Null minima are skipped; the targets whose minimum is below zero (worse than the
    phase-only baseline) are listed in target order. A minimum of exactly 0 is not below it.

    Returns:
        ``{"value": float | None, "targets_below_phase_baseline": [...], "n_defined": int}``.
    """
    minima = {}
    for c in TARGETS:
        rng = _skill_range(metrics, c)
        minima[c] = None if rng is None or _is_null(rng.get("min")) else rng["min"]
    defined = {c: m for c, m in minima.items() if m is not None}
    return {
        "value": min(defined.values()) if defined else None,
        "targets_below_phase_baseline": [c for c, m in defined.items() if m < 0],
        "n_defined": len(defined),
    }


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


def _floor_sentence(metrics: dict[str, Any], k: int) -> str:
    """The skill-floor caveat: the floor, or the targets below the phase-only baseline."""
    floor = skill_floor(metrics)
    if floor["value"] is None:
        return "Skill is undefined for every target."
    below = floor["targets_below_phase_baseline"]
    if below:
        named = ", ".join(
            f"{c} (min skill {format_metric(_skill_range(metrics, c)['min'])})"
            for c in below
        )
        return f"Below the phase-only baseline: {named}."
    scope = (
        "all six targets"
        if floor["n_defined"] == len(TARGETS)
        else f"the {floor['n_defined']} targets with a defined skill"
    )
    span = f"({_SINGLE_SEED})" if k == 1 else f"across {k} seeds"
    return f"Skill ≥ {format_metric(floor['value'])} for {scope} {span}."


def build_caption(
    metrics: dict[str, Any], speedup: dict[str, Any], baseline: dict[str, Any]
) -> str:
    """Build the compact, honest figure caption (design D6; full prose lives in the README).

    A positive headline (the plotted seed, the definition of skill over the phase-only
    baseline and the seed count, + the batched >1,000x speedup; the per-axis numbers live on
    the panels), a terse "Caveats:" line, a terse quasi-steady-reference line, and a README
    pointer. Configuration-resolved R² is not printed: it divides by the near-zero spread of
    six cycle means for some targets and swings with the seed (it stays in ``metrics.json``
    and the README).

    The caveats state the **skill floor** over all six targets -- not a "weakest" target,
    because overlapping seed ranges do not support a ranking -- or, when that floor is
    negative, each target below the phase-only baseline, as a subordinate flag. The off-panel
    CF_mx/CF_mz skill is read at call time, so a corpus in which an off-panel moment outscores
    the headline stays visible.

    Args:
        metrics: The loaded ``metrics.json`` dict.
        speedup: The :func:`compute_speedup` result.
        baseline: The :func:`_baseline_reference` result (overshoot factor for the caption).

    Returns:
        The multi-line caption string. Every number is read from the artifacts.

    Raises:
        KeyError: If ``seed_sweep``, ``phase_baseline_skill`` or a target's entry is missing.
    """
    sweep = _seed_sweep(metrics)
    seed = _require(sweep, "primary_seed", "seed_sweep.primary_seed")
    k = _seed_count(metrics)
    seeds_note = _SINGLE_SEED if k == 1 else f"ranges over {k} seeds"
    phase_r2 = "/".join(
        format_metric(_phase_baseline_r2(metrics, c)) for c in PANEL_COEFFICIENTS
    )
    off_panel = "; ".join(
        f"{c} {_skill_with_range(metrics, c)}" for c in ("CF_mx", "CF_mz")
    )
    thr = speedup["throughput_speedup"]
    lat = speedup["latency_speedup"]
    batch = speedup["batch_size"]
    overshoot = baseline["overshoot_factor"]
    headline = (
        f"Predicted vs CFD on held-out configurations, seed {seed}. Skill = 1 − MSE/MSE₀, "
        f"where MSE₀ is the error of a phase-only baseline (the mean training waveform; "
        f"ignores stroke, frequency and pitch); {seeds_note}. Surrogate inference >1,000x "
        f"faster than CFD (batched GPU throughput ~{thr:.1e}x, N={batch} parallel evals vs "
        f"sequential coarse-grid A40 CFD; per-evaluation latency floor ~{lat:.0f}x)."
    )
    caveats = (
        f"Caveats: pointwise R² mostly reflects the shared waveform (the phase-only "
        f"baseline alone scores R² {phase_r2} for CF_x/CF_z/CF_my); skill also rewards "
        f"predicting how waveform amplitude and shape change with the kinematics, not only "
        f"the cycle-mean force (cycle-mean R²: README). {_floor_sentence(metrics, k)} "
        f"CF_mx/CF_mz omitted from panels (skill {off_panel}). Coarse 64x32x64 grid: "
        f"pipeline readiness, not validated aerodynamics. Moment is the lab-frame M_y "
        f"component (wing-frame conversion not currently tracked)."
    )
    reference = (
        f"Quasi-steady reference (not plotted): an uncalibrated translational Sane-Dickinson "
        f"model is ~{overshoot:.1f}x the coarse-grid CFD lift (RMS) — translational-only, it "
        f"omits rotational/added-mass/LEV lift — "
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

    The uncalibrated translational quasi-steady model is a poor fit to the coarse-grid CFD lift
    (RMS ratio < 1 under the van Veen convention; it omits rotational, added-mass, and LEV lift,
    so it under-predicts the now-in-band CFD) — so the gap mostly re-displays the model's analytic
    loops rather than surrogate skill.
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
            "figure — translational-only (omits rotational/added-mass/LEV lift), a poor fit to "
            "the coarse-grid CFD lift, so not a quantitative baseline here"
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


def _skill_record(metrics: dict[str, Any], coef: str) -> dict[str, Any]:
    """The sidecar's ``skill.<coef>``: the plotted seed's value and the seed-sweep range."""
    rng = _skill_range(metrics, coef) or {}
    return {
        "committed": _require(_skill_entry(metrics, coef), "skill", coef),
        "min": rng.get("min"),
        "max": rng.get("max"),
    }


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
        dpi: Raster resolution (>=200).

    Returns:
        The ``evidence_figure_metrics.json`` payload: per-axis surrogate RMSE, the plotted seed
        and seed count, six-target skill (plotted seed + seed range), pointwise R² and
        phase-only baseline R², the skill floor, the quasi-steady reference and the speedup
        decomposition -- every number the caption prints. The provenance seeds are read from
        ``metrics.json`` ``seed_sweep``, so they cannot disagree with the caption.

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

    sweep = _seed_sweep(metrics)
    seeds = list(_require(sweep, "seeds", "seed_sweep.seeds"))
    floor = skill_floor(metrics)
    fig_metrics: dict[str, Any] = {
        "surrogate_rmse": {c: _per_target_rmse(metrics, c) for c in PANEL_COEFFICIENTS},
        "primary_seed": _require(sweep, "primary_seed", "seed_sweep.primary_seed"),
        "n_seeds": len(seeds),
        "skill": {c: _skill_record(metrics, c) for c in TARGETS},
        "pointwise_r2": {c: _pointwise_r2(metrics, c) for c in TARGETS},
        "phase_baseline_pointwise_r2": {
            c: _phase_baseline_r2(metrics, c) for c in TARGETS
        },
        "skill_floor": {
            "value": floor["value"],
            "targets_below_phase_baseline": floor["targets_below_phase_baseline"],
        },
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
            "seeds": {"global": fig_metrics["primary_seed"], "sweep": seeds[1:]},
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
