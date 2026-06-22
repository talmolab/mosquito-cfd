"""Shared pytest configuration for the test suite.

Defines the ``gpu`` marker auto-skip (force-surrogate PR5, design D2): GPU-tier tests need a
CUDA device and the optional ``train`` dependency-group (PhysicsNeMo/torch), neither of which
exists on the CPU-only CI runner. They are skipped here when unavailable so they are inert in
CI; CI *also* deselects them with ``-m "not gpu"`` (belt-and-suspenders). The import probes are
guarded so a missing ``torch``/``physicsnemo`` yields a skip, never a collection error.
"""

from __future__ import annotations

import importlib.util

import pytest


def _cuda_available() -> bool:
    """True only if torch is importable *and* reports a CUDA device.

    Guarded so a host without the ``train`` group (no ``torch``) returns ``False`` rather
    than raising — the GPU tests then skip instead of erroring at collection.
    """
    if importlib.util.find_spec("torch") is None:
        return False
    try:
        import torch
    except Exception:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _physicsnemo_available() -> bool:
    """True only if ``physicsnemo`` is importable (the optional ``train`` group is present)."""
    return importlib.util.find_spec("physicsnemo") is not None


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip every ``@pytest.mark.gpu`` test when CUDA or PhysicsNeMo is unavailable."""
    if _cuda_available() and _physicsnemo_available():
        return
    skip_gpu = pytest.mark.skip(
        reason="requires a CUDA device and the optional 'train' group (PhysicsNeMo/torch)"
    )
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)
