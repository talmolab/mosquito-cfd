"""Shared pytest configuration for the test suite.

Defines the ``gpu`` marker auto-skip (force-surrogate PR5, design D2): GPU-tier tests need a
CUDA device and the optional ``train`` dependency-group (PhysicsNeMo/torch), neither of which
exists on the CPU-only CI runner. They are skipped here when unavailable so they are inert in
CI; CI *also* deselects them with ``-m "not gpu"`` (belt-and-suspenders). The import probes are
guarded so a missing ``torch``/``physicsnemo`` yields a skip, never a collection error.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

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


def _plotfile_root_available() -> bool:
    """True only if ``MOSQUITO_CFD_PLOTFILE_ROOT`` is set and the directory exists.

    The benchmark plotfiles live on the cluster-mounted Z: drive (Windows) and are absent on
    the CI runner, so ``requires_plotfile`` tests skip unless the env var points at a real dir.
    No Windows path is ever hard-coded into collection.
    """
    root = os.environ.get("MOSQUITO_CFD_PLOTFILE_ROOT")
    return root is not None and Path(root).is_dir()


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Auto-skip ``gpu`` (no CUDA/PhysicsNeMo) and ``requires_plotfile`` (no plotfile root)."""
    skip_gpu = (
        None
        if _cuda_available() and _physicsnemo_available()
        else pytest.mark.skip(
            reason="requires a CUDA device and the optional 'train' group (PhysicsNeMo/torch)"
        )
    )
    skip_plotfile = (
        None
        if _plotfile_root_available()
        else pytest.mark.skip(
            reason="requires a plotfile under $MOSQUITO_CFD_PLOTFILE_ROOT (cluster/Z: data)"
        )
    )
    for item in items:
        if skip_gpu is not None and "gpu" in item.keywords:
            item.add_marker(skip_gpu)
        if skip_plotfile is not None and "requires_plotfile" in item.keywords:
            item.add_marker(skip_plotfile)
