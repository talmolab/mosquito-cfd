"""Formatting shared by the input validators' error messages."""

from __future__ import annotations

from typing import Any

import numpy as np


def plain_repr(value: Any) -> str:
    """Return ``repr(value)``, showing a numpy scalar as its plain Python value.

    numpy 2 reprs scalars as ``np.int64(-1)`` or ``np.True_``; a validator's message should show
    the value the caller meant (``-1``, ``True``). ``repr`` is kept for everything else, so the
    string ``'100'`` can still be told apart from the number ``100``.

    Args:
        value: The rejected argument.

    Returns:
        The repr to put in the error message.
    """
    return repr(value.item() if isinstance(value, np.generic) else value)
