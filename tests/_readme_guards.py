"""Pure README guard helpers shared by the committed-artifact tests (add-fine-corpus-surrogate).

Each helper takes README text plus the parsed JSON it must agree with and signals every content
failure (missing table, missing row, wrong cell, forbidden wording) with ``AssertionError``, never
``AttributeError``/``KeyError``/``IndexError``, so a content mismatch never reads like a coding
error (design D6). They are tested on synthetic inputs in ``test_committed_surrogate_provenance.py``,
so their logic is verified independently of the committed READMEs.

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
    r"`(CF_\w+)`[^.\n`]*\b(higher|lower) on fine across 5 seeds"
)
_BANNED = re.compile(
    r"(?i)\b(improv\w*|better|worse|increas\w*|decreas\w*|drop\w*|greater|less|"
    r"exceed\w*|outperform\w*|rise[sn]?|rising|fall(?:s|en|ing)?|gain\w*)\b"
)
_SUPERSCRIPT = str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
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
        if cells[0] and set(cells[0]) <= {"-", ":"}:
            continue  # the |---| separator (an empty first cell is a row, and fails below)
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
    assert rng is None or isinstance(rng, dict), f"range is not an object: {rng!r}"
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
            format_metric(_get(skill, "skill")),
            _range_cell(rng, format_metric),
            format_metric(_get(skill, "phase_baseline_r2")),
        ]
        assert cells == expected, (c, cells, expected)


def check_cycle_mean_table(readme: str, metrics: dict[str, Any]) -> None:
    """The cycle-mean R² table equals the seed-sweep ``config_mean_r2`` ranges (2 dp)."""
    rows = parse_table(readme, CYCLE_MEAN_HEADER)
    for c, cells in rows.items():
        rng = _get(metrics, "seed_sweep", "range", c, "config_mean_r2")
        assert cells == [_range_cell(rng, _two_dp)], (c, cells)


def format_power_of_ten(value: float) -> str:
    """Render a large factor as the READMEs write it, e.g. ``≈3.8×10⁶×``.

    The mantissa is rounded to one decimal place first, so 9.96e5 renders ``≈1.0×10⁶×``, not
    ``≈10.0×10⁵×``.
    """
    assert isinstance(value, float) and math.isfinite(value) and value > 0, value
    exponent = math.floor(math.log10(value))
    mantissa = round(value / 10**exponent, 1)
    if mantissa >= 10:
        mantissa, exponent = round(mantissa / 10, 1), exponent + 1
    return f"≈{mantissa:.1f}×10{str(exponent).translate(_SUPERSCRIPT)}×"


def overlap_cell(coarse: dict[str, Any] | None, fine: dict[str, Any] | None) -> str:
    """``yes``/``no`` on the raw values (touching counts as overlapping); ``n/a`` if null."""
    ends = [r.get(k) if r else None for r in (coarse, fine) for k in ("min", "max")]
    if any(e is None for e in ends):
        return "n/a"
    lo_c, hi_c, lo_f, hi_f = ends
    return "yes" if max(lo_c, lo_f) <= min(hi_c, hi_f) else "no"


def _headings(lines: list[str]) -> list[tuple[int, int]]:
    """``(line index, level)`` of each markdown heading, skipping fenced code blocks."""
    out, fenced = [], False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            fenced = not fenced
        elif not fenced and stripped.startswith("#"):
            out.append((i, len(stripped) - len(stripped.lstrip("#"))))
    return out


def _section(readme: str, heading_text: str) -> tuple[str, str]:
    """The section under the first heading containing ``heading_text``, and the rest."""
    lines = readme.splitlines()
    headings = _headings(lines)
    starts = [(i, lvl) for i, lvl in headings if heading_text in lines[i]]
    assert starts, f"README has no heading containing {heading_text!r}"
    start, level = starts[0]
    end = next((i for i, lvl in headings if i > start and lvl <= level), len(lines))
    return "\n".join(lines[start:end]), "\n".join(lines[:start] + lines[end:])


def check_comparison_table(
    readme: str, coarse: dict[str, Any], fine: dict[str, Any]
) -> None:
    """The coarse-vs-fine table and its prose follow the pre-registered overlap rule."""
    rows = parse_table(readme, COMPARISON_HEADER)
    direction: dict[str, str] = {}
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
            direction[c] = "lower" if rf["max"] < rc["min"] else "higher"
    section, rest = _section(readme, COMPARISON_HEADING)
    assert COMPARISON_HEADER in section, "comparison table is outside its section"
    outside = _COMPARATIVE.findall(rest)
    assert not outside, f"higher/lower-on-fine wording outside its section: {outside}"
    comparatives = _COMPARATIVE.findall(section)
    forms = _COMPARATIVE_FORM.findall(section)
    assert len(forms) == len(comparatives), (
        f"{len(comparatives)} higher/lower-on-fine phrases but {len(forms)} in the allowed "
        "form (one `CF_c` target per sentence, '... on fine across 5 seeds')"
    )
    named = dict(forms)
    assert len(named) == len(forms), f"a target is described twice: {forms}"
    assert named == direction, (
        f"prose says {named}; the disjoint ranges say {direction}"
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
    """The fine per-step CFD cost is stated (2 dp, from the sidecar), with no ratio to coarse."""
    per_wingbeat = _get(sidecar, "speedup", "cfd_seconds_per_wingbeat")
    rows = _get(sidecar, "speedup", "rows_per_wingbeat")
    stated_text = f"{per_wingbeat / rows:.2f} s per step"
    stated = re.compile(rf"(?<![\d.]){re.escape(stated_text)}\b")
    assert stated.search(readme), f"README lacks {stated_text!r}"
    ratio = _DENOMINATOR_RATIO.search(readme)
    assert ratio is None, f"README states a denominator ratio: {ratio.group(0)!r}"
