"""Formatting shared by the input validators' error messages."""

from __future__ import annotations

from typing import Any

import numpy as np


def plain_repr(value: Any) -> str:
    """Return ``repr(value)``, showing a numpy number or bool scalar as its plain Python value.

    numpy 2 reprs scalars as ``np.int64(-1)`` or ``np.True_``; a validator's message should show
    the value the caller meant (``-1``, ``True``). ``repr`` is kept for everything else, so the
    string ``'100'`` can still be told apart from the number ``100``. Datetime and timedelta
    scalars keep numpy's repr: ``.item()`` would show ``np.timedelta64(5, 'ns')`` as ``5`` and
    ``NaT`` as ``None``, hiding why the value was rejected.

    Args:
        value: The rejected argument.

    Returns:
        The repr to put in the error message.
    """
    # np.timedelta64 subclasses np.signedinteger, so it must be excluded by name.
    plain = isinstance(value, (np.number, np.bool_)) and not isinstance(
        value, np.timedelta64
    )
    return repr(value.item() if plain else value)
