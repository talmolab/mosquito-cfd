"""The evidence-figure tests' synthetic metrics fixture, shared so there is one module object.

``test_force_surrogate_evidence_figure.py`` builds its captions and speedups from it, and
``test_live_spec_claims.py`` recomputes the spec's fixture known answers from it (change
``fix-stale-spec-claims``, design D6). Values are synthetic, not corpus results.
"""

from __future__ import annotations

# The rows per wingbeat the speedup tests pass to ``compute_speedup`` with ``_toy_metrics()``.
TOY_ROWS_PER_WINGBEAT = 2000

# Distinct per target so a test can tell which block a printed number came from.
_POINTWISE = {
    "CF_x": (0.9981, 0.041),
    "CF_y": (0.9912, 0.012),
    "CF_z": (0.9993, 0.087),
    "CF_mx": (0.9977, 0.023),
    "CF_my": (0.9985, 0.034),
    "CF_mz": (0.9988, 0.056),
}
# (committed skill, seed-sweep min, seed-sweep max, phase-only baseline pointwise R²)
_SKILL = {
    "CF_x": (0.9876, 0.9876, 0.9921, 0.9546),
    "CF_y": (0.9611, 0.9534, 0.9660, 0.9732),
    "CF_z": (0.9834, 0.9801, 0.9850, 0.8968),
    "CF_mx": (0.9721, 0.9688, 0.9760, 0.9128),
    "CF_my": (0.9773, 0.9702, 0.9795, 0.9441),
    "CF_mz": (0.9852, 0.9811, 0.9877, 0.9614),
}
# Config-resolved R²: collision-proof literals that must never reach the caption.
_CONFIG_R2 = {
    "CF_x": -7.123,
    "CF_y": 0.4567,
    "CF_z": -6.789,
    "CF_mx": 0.3456,
    "CF_my": -5.678,
    "CF_mz": 0.2345,
}
_CONFIG_R2_LITERALS = ("7.123", "0.4567", "0.457", "6.789", "0.3456", "5.678", "0.2345")


def _toy_metrics(*, seeds=(1234, 1235, 1236, 1237, 1238)) -> dict:
    """A tiny metrics dict mirroring the committed metrics.json structure."""
    return {
        "per_target": {
            t: {"rmse": rmse, "mae": 0.03, "r2": r2}
            for t, (r2, rmse) in _POINTWISE.items()
        },
        "aggregate": {"rmse": 0.05, "mae": 0.035, "r2": 0.985},
        "config_resolved": {
            t: {"config_mean_r2": v, "within_config_variance_fraction": 0.99}
            for t, v in _CONFIG_R2.items()
        },
        "phase_baseline_skill": {
            "phase_baseline": {"kind": "phase_only_periodic_interpolation"},
            "per_target": {
                t: {"skill": s, "phase_baseline_rmse": 0.4, "phase_baseline_r2": b}
                for t, (s, _, _, b) in _SKILL.items()
            },
        },
        "seed_sweep": {
            "primary_seed": seeds[0],
            "seeds": list(seeds),
            "runs": [],
            "range": {
                t: {"skill": {"min": lo, "max": hi}}
                for t, (_, lo, hi, _) in _SKILL.items()
            },
        },
        "inference": {
            "latency_ms": 0.232,
            "throughput_rows_per_s": 5.17e7,
            "basis": "mean single-row latency over 200 iters; mean batched throughput "
            "over 20 passes of 12535 rows on cuda; cuda-synchronized",
        },
        "reproducibility": {"seeds": {"global": seeds[0]}},
    }
