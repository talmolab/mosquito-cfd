"""Shared density test helpers for the flapping-wing benchmarks (PR #136 review round 4)."""

from __future__ import annotations

import numbers
from decimal import Decimal

import numpy as np


class PreciseReal:
    """A ``numbers.Real`` whose own arithmetic is more precise than ``float``'s.

    It stands in for an arbitrary-precision real such as ``sympy.Float``: ``float()`` of it is the
    plain value, but multiplying by it directly is not (one ulp away), so a code path that skips
    the conversion to ``float`` gives different coefficients.
    """

    def __init__(self, value: float) -> None:
        """Store the plain ``float`` value ``float(self)`` returns."""
        self.value = value

    def __float__(self) -> float:
        """Return the plain value."""
        return self.value

    def __mul__(self, other):
        """Multiply by a value one ulp above ``float(self)``."""
        return other * np.nextafter(self.value, np.inf)

    __rmul__ = __mul__

    def __repr__(self) -> str:
        """Name the stub and its value."""
        return f"PreciseReal({self.value!r})"


numbers.Real.register(PreciseReal)


# Densities every density-taking function rejects before reading. Decimal and a 0-d array are
# not numbers.Real; 1e-320 and 5e-324 are subnormal floats.
BAD_DENSITIES = {
    "0.0": 0.0,
    "-1.0": -1.0,
    "nan": float("nan"),
    "inf": float("inf"),
    "True": True,
    "None": None,
    "'1.0'": "1.0",
    "10**400": 10**400,
    "Decimal(1)": Decimal("1"),
    "array(1.0)": np.array(1.0),
    "1e-320": 1e-320,
    "5e-324": 5e-324,
}

# Densities that overflow: at 5e305 F_ref is finite but the forces are not; at 1e308 F_ref is not.
OVERFLOW_DENSITIES = [5e305, 1e308]
