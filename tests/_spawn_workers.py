"""Module-level worker functions for spawn-context tests.

A ``spawn`` child re-imports the function it runs by module name, so it must live in a small,
importable module rather than inside a test file (importing the 1,900-line snapshot test module in
every child would also be slow and import-mode dependent).
"""

from __future__ import annotations

import os

from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

_FULL = {"lo": (-float("inf"),) * 3, "hi": (float("inf"),) * 3}


def read_fixture_snapshot(path: str):
    """Read ``path`` over its full extent in this process.

    Returns:
        ``(pid, snapshot)``: the worker's process id (so the caller can prove the read happened
        in another process) and the :class:`FieldSnapshot`, which the pool pickles back.
    """
    return os.getpid(), read_field_snapshot(path, **_FULL)
