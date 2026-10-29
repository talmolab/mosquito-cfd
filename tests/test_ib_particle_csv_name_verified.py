"""The IB-particle CSV name is recorded as verified, not assumed (issue #19).

PR #18 verified ``IB_Particle_1.csv`` against real IAMReX output on the A40 corpus. The live comments
must say so while keeping the ``csv-name`` escape hatch. Whole-file scan for the stale phrasings
only: they sat on lines that do not themselves name the CSV, so a line-scoped check would miss them,
and an unrelated "assume" elsewhere in these files is not stale.

Spec: force-surrogate "Per-configuration output layout matches the dataset driver contract".
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
# File -> the code (not a comment) that keeps the CSV name overridable there.
_FILES = {
    "src/mosquito_cfd/force_surrogate/runner.py": "csv_name: str = IB_PARTICLE_CSV",
    "src/mosquito_cfd/force_surrogate/run_one_config.py": 'parser.add_argument("--csv-name"',
    "cluster/argo/workflow-templates/force-surrogate-single-config.yaml": (
        '- "{{inputs.parameters.csv-name}}"'
    ),
}
_VERIFIED = "verified against the A40 corpus (PR #18)"
# The pre-#19 wording, as it read in each file.
_STALE = re.compile(
    r"(?i)assumed\W+force-csv|\bassumed;|not\s+yet\s+verified|verify\s+on\s+the\s+first|wrong\s+guess"
)


@pytest.mark.parametrize(("rel", "escape_hatch"), _FILES.items())
def test_csv_name_is_stated_as_verified(rel, escape_hatch):
    text = (_ROOT / rel).read_text(encoding="utf-8")
    flat = " ".join(
        re.sub(r"(?m)^\s*#", " ", text).split()
    )  # drop comment leaders only
    assert _VERIFIED in flat, rel
    assert escape_hatch in text, f"{rel}: the escape hatch is gone"
    assert not _STALE.search(flat), rel
