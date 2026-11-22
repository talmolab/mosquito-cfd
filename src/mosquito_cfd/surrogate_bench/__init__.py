"""Surrogate comparison bench (F3a, OpenSpec change ``add-surrogate-comparison-bench``).

Scores surrogate families on the same named splits of the fine force corpus and records where
each one breaks. Torch-free at import: the MLP entries reach torch only through
:mod:`mosquito_cfd.force_surrogate.train`'s lazy imports.
"""

from __future__ import annotations

# The seeds every learned entry is fitted over: the shipped surrogate's primary and sweep seeds.
BENCH_SEEDS: tuple[int, ...] = (1234, 1235, 1236, 1237, 1238)

# What no bench result may claim beyond (quoted verbatim by the fine README).
BENCH_SCOPE = (
    "Interpolation inside, and extrapolation to a held-out outer layer of, a 3 × 3 × 3 grid of "
    "configurations; second-beat data from 2-beat runs that has not settled; generic "
    "sinusoidal validation kinematics, not van Veen's and not a mosquito's (#142)."
)

__all__ = ["BENCH_SCOPE", "BENCH_SEEDS"]
