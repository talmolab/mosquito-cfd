"""README guards added by add-real-comparison-figures.

``check_coarse_qs_ratios`` is tested on synthetic bullets for each defect in the force-surrogate
spec scenario, then applied to the committed coarse README against both committed evidence-figure
sidecars. The link checks tie both READMEs to the committed comparison figures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from _readme_guards import check_coarse_qs_ratios

REPO = Path(__file__).resolve().parents[1]
COARSE_SIDECAR = {"quasi_steady_reference": {"overshoot_factor": 1.3435407346470738}}
FINE_SIDECAR = {"quasi_steady_reference": {"overshoot_factor": 1.4074274138248275}}

GOOD = """\
- **Something before.** Text.
- **The Sane–Dickinson quasi-steady model is a reference, not a plotted baseline.** At this
  coarse grid it overshoots the CFD lift ~1.3× in RMS, and on the 256×128×256 grid ~1.4×. The
  ratio stays above 1 on the fine grid. A fair comparison needs a calibrated model.
- **The >1,000× speedup is batched GPU throughput.** The headline (≈2.8×10⁶×) and ~372×.
"""


def test_a_well_formed_bullet_passes():
    check_coarse_qs_ratios(GOOD, COARSE_SIDECAR, FINE_SIDECAR)


def test_the_phrase_may_wrap_across_lines():
    wrapped = GOOD.replace("The\n  ratio stays above 1", "The ratio stays\n  above 1")
    check_coarse_qs_ratios(wrapped, COARSE_SIDECAR, FINE_SIDECAR)


@pytest.mark.parametrize(
    "defect,old,new,needle",
    [
        ("digit changed", "~1.4×", "~1.5×", "exactly"),
        (
            "ratios swapped",
            "~1.3× in RMS, and on the 256×128×256 grid ~1.4×",
            "~1.4× in RMS, and on the 256×128×256 grid ~1.3×",
            "exactly",
        ),
        (
            "third token",
            "A fair comparison",
            "It was ~2.3× before. A fair comparison",
            "exactly",
        ),
        ("markup", "~1.3×", "~**1.3×**", "markup"),
        (
            "phrase removed",
            "The\n  ratio stays above 1 on the fine grid.",
            "",
            "stays above 1",
        ),
        (
            "IB-bias-free added",
            "A fair comparison",
            "An IB-bias-free grid would help. A fair comparison",
            "IB-bias-free",
        ),
        (
            "start removed",
            "The Sane–Dickinson",
            "The quasi-steady",
            "expected exactly 1",
        ),
    ],
)
def test_each_defect_fails_with_a_named_assertion(defect, old, new, needle):
    assert old in GOOD, defect
    with pytest.raises(AssertionError, match=re.escape(needle)):
        check_coarse_qs_ratios(GOOD.replace(old, new), COARSE_SIDECAR, FINE_SIDECAR)


def _sidecar(corpus):
    path = REPO / "examples" / corpus / "figures" / "evidence_figure_metrics.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_committed_coarse_readme_states_both_ratios():
    readme = (REPO / "examples" / "prelim_sweep" / "README.md").read_text(
        encoding="utf-8"
    )
    check_coarse_qs_ratios(
        readme, _sidecar("prelim_sweep"), _sidecar("prelim_sweep_fine")
    )
