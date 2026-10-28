"""Pure README guard helpers shared by the committed-artifact tests (add-fine-corpus-surrogate).

Each helper takes README text plus the parsed JSON it must agree with and signals every content
failure (missing table, missing row, wrong cell, forbidden wording) with ``AssertionError``, never
``AttributeError``/``KeyError``/``IndexError``. That keeps the fine-corpus tests inside their
``xfail(raises=(FileNotFoundError, AssertionError))`` markers until the artifacts land, while a
genuine coding error still fails (design D6). They are tested on synthetic inputs in
``test_committed_surrogate_provenance.py``, so their logic is verified before any fine artifact
exists.

Tables are located by their exact header line and read row by row until the table ends, so one
table's guard can never read another table's rows.
"""

from __future__ import annotations

import math
import re
from typing import Any

from mosquito_cfd.force_surrogate.evidence_figure import format_metric
from mosquito_cfd.force_surrogate.train import TARGET_COLUMNS

SKILL_HEADER = "| target | skill, seed 1234 | skill, 5 seeds | phase-only baseline R² |"
CYCLE_MEAN_HEADER = "| target | cycle-mean R², 5 seeds |"
COMPARISON_HEADER = (
    "| target | skill, 5 seeds, coarse | skill, 5 seeds, fine | ranges overlap |"
)
COMPARISON_HEADING = "Coarse vs fine"

# Any CF name followed, within one line and before any other CF name, by "≈<num>" or "=<num>".
# Broad on purpose: a stale value in a slightly different form (``CF_z R² ≈0.51``,
# ``CF_my = 0.51``, a Unicode minus) is caught rather than skipped. Percentages are excluded.
R2_NEAR_TARGET = re.compile(
    r"\b(CF_(?:mx|my|mz|x|y|z))\b`?((?:(?!CF_)[^≈=\n|]){0,60})[≈=](-?\d+\.(\d+))(?![\d%])"
)

_TARGET_CELL = re.compile(r"^`(CF_\w+)`$")
_COMPARATIVE = re.compile(r"(?i)\b(higher|lower) on fine\b")
# One target per sentence: `[^.\n]` stops at the sentence end, so two comparative sentences on
# one line are two matches, each naming its own target.
_COMPARATIVE_FORM = re.compile(
    r"`(CF_\w+)`[^.\n`]*\b(?:higher|lower) on fine across 5 seeds"
)
_BANNED = re.compile(r"(?i)\b(improv\w*|better|worse|increas\w*|decreas\w*|drop\w*)\b")
_DENOMINATOR_RATIO = re.compile(
    r"(?i)(\d+(\.\d+)?\s*[×x]\s*(the\s+)?(coarse|slower)|times\s+(the\s+)?coarse)"
)


def parse_table(readme: str, header: str) -> dict[str, list[str]]:
    """Rows of the table under ``header``, keyed by target, as stripped cell strings."""
    lines = [line.strip() for line in readme.splitlines()]
    assert header in lines, f"README has no table with header {header!r}"
    rows: dict[str, list[str]] = {}
    for line in lines[lines.index(header) + 1 :]:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if set(cells[0]) <= {"-", ":", " "}:
            continue  # the |---| separator
        match = _TARGET_CELL.match(cells[0])
        assert match, (
            f"row {line!r} under {header!r} does not start with a `CF_` target"
        )
        assert match.group(1) not in rows, f"duplicate row for {match.group(1)}"
        rows[match.group(1)] = cells[1:]
    assert set(rows) == set(TARGET_COLUMNS), (
        f"table {header!r} rows {sorted(rows)} != targets {sorted(TARGET_COLUMNS)}"
    )
    return rows


def _get(node: Any, *keys: str) -> Any:
    for key in keys:
        assert isinstance(node, dict) and key in node, f"metrics lacks {'.'.join(keys)}"
        node = node[key]
    return node


def _range_cell(rng: dict[str, Any] | None, fmt) -> str:
    if rng is None or rng.get("min") is None or rng.get("max") is None:
        return "n/a"
    return f"{fmt(rng['min'])} to {fmt(rng['max'])}"


def _two_dp(value: float) -> str:
    return f"{value:.2f}".replace("-", "−")


def check_skill_table(readme: str, metrics: dict[str, Any]) -> None:
    """The skill table equals ``metrics.json`` for all six targets, as the figure prints it."""
    rows = parse_table(readme, SKILL_HEADER)
    for c, cells in rows.items():
        skill = _get(metrics, "phase_baseline_skill", "per_target", c)
        rng = _get(metrics, "seed_sweep", "range", c, "skill")
        expected = [
            format_metric(skill["skill"]),
            _range_cell(rng, format_metric),
            format_metric(skill["phase_baseline_r2"]),
        ]
        assert cells == expected, (c, cells, expected)


def check_cycle_mean_table(readme: str, metrics: dict[str, Any]) -> None:
    """The cycle-mean R² table equals the seed-sweep ``config_mean_r2`` ranges (2 dp)."""
    rows = parse_table(readme, CYCLE_MEAN_HEADER)
    for c, cells in rows.items():
        rng = _get(metrics, "seed_sweep", "range", c, "config_mean_r2")
        assert cells == [_range_cell(rng, _two_dp)], (c, cells)


def overlap_cell(coarse: dict[str, Any] | None, fine: dict[str, Any] | None) -> str:
    """``yes``/``no`` on the raw values (touching counts as overlapping); ``n/a`` if null."""
    ends = [r.get(k) if r else None for r in (coarse, fine) for k in ("min", "max")]
    if any(e is None for e in ends):
        return "n/a"
    lo_c, hi_c, lo_f, hi_f = ends
    return "yes" if max(lo_c, lo_f) <= min(hi_c, hi_f) else "no"


def _section(readme: str, heading_text: str) -> str:
    lines = readme.splitlines()
    starts = [
        i
        for i, line in enumerate(lines)
        if line.lstrip().startswith("#") and heading_text in line
    ]
    assert starts, f"README has no heading containing {heading_text!r}"
    start = starts[0]
    level = len(lines[start].lstrip()) - len(lines[start].lstrip().lstrip("#"))
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].lstrip()
        if stripped.startswith("#"):
            if len(stripped) - len(stripped.lstrip("#")) <= level:
                end = i
                break
    return "\n".join(lines[start:end])


def check_comparison_table(
    readme: str, coarse: dict[str, Any], fine: dict[str, Any]
) -> None:
    """The coarse-vs-fine table and its prose follow the pre-registered overlap rule."""
    rows = parse_table(readme, COMPARISON_HEADER)
    disjoint = set()
    for c, cells in rows.items():
        rc = _get(coarse, "seed_sweep", "range", c, "skill")
        rf = _get(fine, "seed_sweep", "range", c, "skill")
        expected = [
            _range_cell(rc, format_metric),
            _range_cell(rf, format_metric),
            overlap_cell(rc, rf),
        ]
        assert cells == expected, (c, cells, expected)
        if expected[2] == "no":
            disjoint.add(c)
    section = _section(readme, COMPARISON_HEADING)
    assert COMPARISON_HEADER in section, "comparison table is outside its section"
    comparatives = _COMPARATIVE.findall(section)
    forms = _COMPARATIVE_FORM.findall(section)
    assert len(forms) == len(comparatives), (
        f"{len(comparatives)} higher/lower-on-fine phrases but {len(forms)} in the allowed "
        "form (one `CF_c` target per sentence, '... on fine across 5 seeds')"
    )
    named = set(forms)
    assert named == disjoint, (
        f"prose calls {sorted(named)} higher/lower on fine; disjoint: {sorted(disjoint)}"
    )
    banned = _BANNED.findall(section)
    assert not banned, f"comparative wording outside the rule: {banned}"
    low = section.lower()
    assert low.count("shift") == low.count("no shift detected"), (
        "'shift' used other than as 'no shift detected'"
    )


FINE_REQUIRED = (
    "not with experiment",
    "outside this sweep",
    "3.7 %",
    "27.6 %",
    "examples/flapping_wing/RESULTS.md",
    "docs/force_surrogate/fine-grid-pilot-report.md",
    "plotfile",
    "median",
    "phase-only baseline",
    "skill = 1 − mse/mse₀",
    "lab-frame",
    "about the hinge",
    "not currently tracked",
)
FINE_FORBIDDEN = (
    "2.4×",
    "2.4x",
    "diffused-ib underestimate",
    "pitch moment",
    "roll moment",
)


def check_fine_disclosures(readme: str) -> None:
    """The fine README's required disclosures are present and retired claims absent."""
    low = readme.lower()
    missing = [s for s in FINE_REQUIRED if s.lower() not in low]
    assert not missing, f"fine README lacks {missing}"
    present = [s for s in FINE_FORBIDDEN if s in low]
    assert not present, f"fine README contains {present}"


def check_quoted_in_source(readme: str, source: str, quotes: tuple[str, ...]) -> None:
    """Each fixed number quoted in the README appears verbatim in its cited source."""
    for q in quotes:
        assert q in readme, f"README does not quote {q!r}"
        assert q in source, f"{q!r} is not in the cited source"


QS_REQUIRED = (
    "uncalibrated",
    "translational-only",
    "symmetric-rotation",
    "stroke-plane-normal",
    "lab-z",
    "not overlaid",
)


def check_fine_qs_disclosure(readme: str, sidecar: dict[str, Any]) -> None:
    """The quasi-steady paragraph gives the sidecar's ratio and the model's nature."""
    ratio = _get(sidecar, "quasi_steady_reference", "overshoot_factor")
    assert isinstance(ratio, float) and math.isfinite(ratio), ratio
    assert f"~{ratio:.1f}×" in readme, f"README lacks the QS ratio ~{ratio:.1f}×"
    low = readme.lower()
    missing = [s for s in QS_REQUIRED if s not in low]
    assert not missing, f"fine README QS paragraph lacks {missing}"


def check_fine_denominator(readme: str, sidecar: dict[str, Any]) -> None:
    """The fine CFD cost is stated as the sidecar value, and no coarse/fine ratio is stated."""
    seconds = _get(sidecar, "speedup", "cfd_seconds_per_wingbeat")
    assert f"{round(seconds):,} s" in readme, f"README lacks '{round(seconds):,} s'"
    ratio = _DENOMINATOR_RATIO.search(readme)
    assert ratio is None, f"README states a denominator ratio: {ratio.group(0)!r}"
