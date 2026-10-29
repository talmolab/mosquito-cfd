"""The IB-particle CSV name is recorded as verified, not assumed (issue #19).

PR #18 verified ``IB_Particle_1.csv`` against real IAMReX output on the A40 corpus. The live comments
must say so while keeping the ``--csv-name`` escape hatch. Whole-file scan: the stale wording sits on
lines that do not themselves name the CSV, so a line-scoped check would miss it.

Spec: force-surrogate "Per-configuration output layout matches the dataset driver contract".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_FILES = (
    "src/mosquito_cfd/force_surrogate/runner.py",
    "src/mosquito_cfd/force_surrogate/run_one_config.py",
    "cluster/argo/workflow-templates/force-surrogate-single-config.yaml",
)
_VERIFIED = "verified against the A40 corpus (PR #18)"


@pytest.mark.parametrize("rel", _FILES)
def test_csv_name_is_stated_as_verified(rel):
    text = (_ROOT / rel).read_text(encoding="utf-8")
    flat = " ".join(
        re.sub(r"(?m)^\s*#", " ", text).split()
    )  # drop comment leaders only
    assert _VERIFIED in flat, rel
    assert not re.search(r"(?i)assum|not yet verified", text), rel
