"""Shared pytest configuration for the test suite.

Defines two marker auto-skips so the suite is inert on a CPU-only, cluster-free runner:

- ``gpu``: needs a CUDA device + the optional ``train`` group (PhysicsNeMo/torch). Auto-skipped
  here when unavailable; CI *also* deselects it with ``-m "not gpu"`` (belt-and-suspenders).
- ``requires_plotfile``: needs an AMReX plotfile under ``$MOSQUITO_CFD_PLOTFILE_ROOT``
  (cluster/Z: data). Auto-skipped here when that path is absent — CI lacks it, so CI skips these
  *without* needing an ``-m`` filter (it currently runs only ``-m "not gpu"``).

The import/path probes are guarded so a missing dependency or path yields a skip, never a
collection error.
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
