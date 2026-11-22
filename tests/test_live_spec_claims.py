"""Live-spec claim guard (change ``fix-stale-spec-claims``, issues #115 and #170).

The force-surrogate and flapping-wing-validation specs once froze corpus results into their
requirements, and the numbers went stale as the corpora were rebuilt (#115). This module checks
each spec's *effective* text (the live spec with every active change's delta applied):

- the retired claims stay out (a tripwire, with a stale example and corrective text per pattern);
- every number in the guarded requirements is registered as recomputed, fixture or declared.

The helpers are in ``_spec_claims``; the first part of this module unit-tests them on synthetic
inputs, the second guards the live specs.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from pathlib import Path

import _evidence_fixture
import _spec_claims as sc
import pytest
from _stale_claims import normalize, python_prose

# --------------------------------------------------------------------------------------------
# requirement_blocks
# --------------------------------------------------------------------------------------------

_LIVE = """# cap Specification

## Purpose

Text.

## Requirements

### Requirement: Alpha

Alpha body with 1.5.

#### Scenario: a

- **Given** x

### Requirement: Beta

Beta body.

#### Scenario: b

- **Given** y

### Requirement: Gamma

Gamma body.

#### Scenario: c

- **Given** z
"""


def test_requirement_blocks_splits_on_requirement_headings():
    blocks = sc.requirement_blocks(_LIVE)
    assert list(blocks) == ["Alpha", "Beta", "Gamma"]
    assert blocks["Alpha"].startswith("### Requirement: Alpha")
    assert "Alpha body with 1.5." in blocks["Alpha"]
    assert "Beta" not in blocks["Alpha"]
    assert blocks["Gamma"].rstrip().endswith("- **Given** z")


def test_requirement_blocks_is_crlf_safe():
    blocks = sc.requirement_blocks(_LIVE.replace("\n", "\r\n"))
    assert list(blocks) == ["Alpha", "Beta", "Gamma"]
    assert "\r" not in "".join(blocks)
    assert "\r" not in "".join(blocks.values())


def test_an_unknown_section_ends_a_block_and_is_not_applied():
    delta = (
        "## ADDED Requirements\n\n### Requirement: New\n\nNew body.\n\n#### Scenario: n\n\n"
        "- **Given** q\n\n## Cross-References\n\n- [Other](../other/spec.md)\n"
    )
    sections = sc.delta_sections(delta)
    assert list(sections["ADDED"]) == ["New"]
    assert "Cross-References" not in sections["ADDED"]["New"]
    assert "Other" not in sections["ADDED"]["New"]


# --------------------------------------------------------------------------------------------
# effective_spec / effective_text / effective_block
# --------------------------------------------------------------------------------------------


def _tree(
    tmp_path: Path, changes: dict[str, str], live: str = _LIVE
) -> tuple[Path, Path]:
    specs = tmp_path / "specs"
    (specs / "cap").mkdir(parents=True)
    (specs / "cap" / "spec.md").write_text(live, encoding="utf-8")
    changes_dir = tmp_path / "changes"
    changes_dir.mkdir()
    for change, delta in changes.items():
        d = changes_dir / change / "specs" / "cap"
        d.mkdir(parents=True)
        (d / "spec.md").write_text(delta, encoding="utf-8")
    return specs, changes_dir


def _block(name: str, body: str) -> str:
    return f"### Requirement: {name}\n\n{body}\n\n#### Scenario: s\n\n- **Given** g\n"


def test_delta_replaces_drops_and_appends(tmp_path):
    delta = (
        "## MODIFIED Requirements\n\n" + _block("Alpha", "Alpha NEW body.") + "\n"
        "## REMOVED Requirements\n\n" + _block("Beta", "gone") + "\n"
        "## ADDED Requirements\n\n" + _block("Delta", "Delta body.")
    )
    specs, changes = _tree(tmp_path, {"chg": delta})
    eff = sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)
    assert list(eff) == ["Alpha", "Gamma", "Delta"]
    assert eff["Alpha"] == [("chg", _block("Alpha", "Alpha NEW body.").rstrip("\n"))]
    assert eff["Gamma"][0][0] == "live"
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "Alpha NEW body." in text and "Alpha body with 1.5." not in text
    assert "Beta body." not in text and "Delta body." in text


def test_archive_non_directories_and_other_capabilities_are_ignored(tmp_path):
    specs, changes = _tree(tmp_path, {})
    archived = changes / "archive" / "2026-01-01-old" / "specs" / "cap"
    archived.mkdir(parents=True)
    (archived / "spec.md").write_text(
        "## MODIFIED Requirements\n\n" + _block("Alpha", "ARCHIVED"), encoding="utf-8"
    )
    other = changes / "elsewhere" / "specs" / "other-cap"
    other.mkdir(parents=True)
    (other / "spec.md").write_text(
        "## MODIFIED Requirements\n\n" + _block("Alpha", "OTHER CAP"), encoding="utf-8"
    )
    (changes / "README.md").write_text("not a change", encoding="utf-8")
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "ARCHIVED" not in text and "OTHER CAP" not in text
    assert "Alpha body with 1.5." in text


@pytest.mark.parametrize(
    ("delta", "match"),
    [
        ("## MODIFIED Requirements\n\n" + _block("Nope", "x"), "Nope"),
        ("## REMOVED Requirements\n\n" + _block("Nope", "x"), "Nope"),
        ("## ADDED Requirements\n\n" + _block("Alpha", "x"), "Alpha"),
    ],
)
def test_inconsistent_deltas_raise_naming_change_and_requirement(
    tmp_path, delta, match
):
    specs, changes = _tree(tmp_path, {"bad-change": delta})
    with pytest.raises(ValueError, match=match) as err:
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)
    assert "bad-change" in str(err.value)


@pytest.mark.parametrize(
    "delta",
    [
        # OpenSpec's own parser matches section titles case-insensitively, allows any
        # whitespace in "###  Requirement:" and accepts bullet-form REMOVED entries. A delta it
        # applies must not be silently skipped here (the guard would check stale live text).
        "## Modified Requirements\n\n" + _block("Alpha", "ALPHA NEW"),
        "## MODIFIED Requirements\n\n###  Requirement:  Alpha  \n\nALPHA NEW\n",
        "##   MODIFIED   Requirements\n\n" + _block("Alpha", "ALPHA NEW"),
    ],
)
def test_delta_formatting_openspec_accepts_is_applied(tmp_path, delta):
    specs, changes = _tree(tmp_path, {"chg": delta})
    block = sc.effective_block("cap", "Alpha", specs_dir=specs, changes_dir=changes)
    assert "ALPHA NEW" in block and "Alpha body with 1.5." not in block


def test_bullet_form_removed_is_applied(tmp_path):
    delta = "## REMOVED Requirements\n\n- `### Requirement: Beta`\n- `### Requirement: Gamma`\n"
    specs, changes = _tree(tmp_path, {"chg": delta})
    eff = sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)
    assert list(eff) == ["Alpha"]


def test_an_unclassified_delta_section_raises(tmp_path):
    """A `## ` section that is neither a delta kind nor plainly non-requirement text, holding a
    requirement block, is an error, not a silent skip."""
    delta = "## Changed Requirements\n\n" + _block("Alpha", "ALPHA NEW")
    specs, changes = _tree(tmp_path, {"chg": delta})
    with pytest.raises(ValueError, match="Changed Requirements"):
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)


def test_a_requirement_removed_by_two_changes_names_both(tmp_path):
    removed = "## REMOVED Requirements\n\n" + _block("Beta", "gone")
    specs, changes = _tree(tmp_path, {"one": removed, "two": removed})
    assert "Beta body." not in sc.effective_text(
        "cap", specs_dir=specs, changes_dir=changes
    )
    with pytest.raises(ValueError, match="modified or removed") as err:
        sc.effective_block("cap", "Beta", specs_dir=specs, changes_dir=changes)
    assert "one" in str(err.value) and "two" in str(err.value)


def test_renamed_section_raises(tmp_path):
    delta = "## RENAMED Requirements\n\n- FROM: `### Requirement: Alpha`\n- TO: `### Requirement: A2`\n"
    specs, changes = _tree(tmp_path, {"chg": delta})
    with pytest.raises(NotImplementedError, match="RENAMED"):
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)


def test_two_changes_adding_one_name_raise(tmp_path):
    add = "## ADDED Requirements\n\n" + _block("Delta", "x")
    specs, changes = _tree(tmp_path, {"one": add, "two": add})
    with pytest.raises(ValueError, match="Delta"):
        sc.effective_spec("cap", specs_dir=specs, changes_dir=changes)


def test_two_changes_modifying_one_requirement(tmp_path):
    specs, changes = _tree(
        tmp_path,
        {
            "first-change": "## MODIFIED Requirements\n\n" + _block("Alpha", "FIRST"),
            "second-change": "## MODIFIED Requirements\n\n" + _block("Alpha", "SECOND"),
        },
    )
    text = sc.effective_text("cap", specs_dir=specs, changes_dir=changes)
    assert "FIRST" in text and "SECOND" in text  # a whole-spec scan reads both variants
    with pytest.raises(ValueError) as err:
        sc.effective_block("cap", "Alpha", specs_dir=specs, changes_dir=changes)
    message = str(err.value)
    assert "first-change" in message and "second-change" in message
    assert "second to merge" in message
    # an unshared requirement still builds
    assert "Gamma body." in sc.effective_block(
        "cap", "Gamma", specs_dir=specs, changes_dir=changes
    )


def test_effective_block_of_an_absent_requirement_names_the_registry(tmp_path):
    specs, changes = _tree(tmp_path, {})
    with pytest.raises(KeyError, match="GUARDED"):
        sc.effective_block("cap", "Missing", specs_dir=specs, changes_dir=changes)


def test_default_paths_resolve_from_the_module_at_call_time(tmp_path, monkeypatch):
    specs, changes = _tree(
        tmp_path, {"chg": "## MODIFIED Requirements\n\n" + _block("Alpha", "PATCHED")}
    )
    monkeypatch.setattr(sc, "SPECS_DIR", specs)
    monkeypatch.setattr(sc, "CHANGES_DIR", changes)
    monkeypatch.chdir(tmp_path.parent)
    assert "PATCHED" in sc.effective_text("cap")
    # and the real defaults point at the repository, not the working directory
    monkeypatch.undo()
    repo = Path(__file__).resolve().parents[1]
    assert sc.SPECS_DIR == repo / "openspec" / "specs"
    assert sc.CHANGES_DIR == repo / "openspec" / "changes"


# --------------------------------------------------------------------------------------------
# number_tokens and format_like
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "tokens"),
    [
        ("a 256x128x256 grid", ["256", "128", "256"]),
        ("a 64×32×64 grid", ["64", "32", "64"]),
        ("≈ 3.7×10⁶× faster", ["3.7", "10"]),
        ("within 1e-9", ["1e-9"]),
        ("fell to 3.06e-4", ["3.06e-4"]),
        ("5.17e7 rows", ["5.17e7"]),
        ("cost 2E9 and 2.5E-3", ["2E9", "2.5E-3"]),
        ("N=12,535 rows", ["12,535"]),
        (">1,000× speedup", ["1,000"]),
        ("LF-newline UTF-8 and ISO-8601", ["8", "8601"]),
        ("at t = T/4", ["4"]),
        ("arrays [1, 3] and [5, 7]", ["1", "3", "5", "7"]),
        ("k = −1 case", ["1"]),
        ("k ≈ 3.120.", ["3.120"]),
        ("s45_f115_p60 #115 CC-4 design D6 CC-F1 sha256: R² x ３ y", []),
    ],
)
def test_number_tokens(text, tokens):
    assert sc.number_tokens(text) == tokens


def test_superscript_after_a_digit_is_found():
    found = sc.superscripts_after_digits(
        "3.72×10⁶, ~10³× and 1×10⁻⁹; R² and Σt² are fine"
    )
    assert found == ["0⁶", "0³", "0⁻"]


@pytest.mark.parametrize(
    ("value", "literal", "expected"),
    [
        (3.1197210117, "3.120", "3.120"),
        (3722400.0, "3.72e6", "3.72e6"),
        (5.17e7, "5.17e7", "5.17e7"),
        (3.0607e-4, "3.06e-4", "3.06e-4"),
        (2.0e9, "2E9", "2E9"),
        (12535, "12,535", "12,535"),
        (310.34, "310", "310"),
        (144.0, "144", "144"),
        (2.5, "2", "2"),  # Python rounds half to even
        (3.1187, "3.119", "3.119"),
    ],
)
def test_format_like(value, literal, expected):
    assert sc.format_like(value, literal) == expected


def test_format_like_detects_a_drift_in_the_last_digit_and_in_the_exponent():
    assert sc.format_like(3.1207, "3.120") == "3.121"
    assert sc.format_like(3.72e7, "3.72e6") == "3.72e7"


# ============================================================================================
# The guard on the live specs (design D4, D5, D7)
# ============================================================================================

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "spec_claims"
_REPO = Path(__file__).resolve().parents[1]
FS, FWV = "force-surrogate", "flapping-wing-validation"

# --- Retired claims --------------------------------------------------------------------------
# Patterns are written against ``_stale_claims.normalize`` output: links reduced; ``*``, ``_``
# and backticks dropped; whitespace collapsed; lower case.
RETIRED: dict[str, re.Pattern[str]] = {
    "coarse latency speedup ~310x": re.compile(r"310\s*[×x]\s*on the coarse grid"),
    "parallelism factor 12,009": re.compile(r"12[,\s\u202f]?009"),
    "QS model under-predicts": re.compile(r"fit that under-predicts"),
    "stale numbers tracked in #115": re.compile(
        r"tracked (separately )?in (issue )?#115"
    ),
    "throughput = latency x batch size": re.compile(
        r"equals\s+latencyspeedup\s*[×*]?\s*batchsize"
    ),
    "two orders of magnitude": re.compile(r"two orders of\s+magnitude"),
    "usable tolerance window": re.compile(r"usable tolerance window"),
    "config_mean_r2 physically-central": re.compile(r"physically-central"),
    "QS RMS ratio ~0.7": re.compile(r"[≈~]\s*0\.7\)"),
    "covered only 83%": re.compile(r"covered only 83\s*%"),
    "observed dt 3.06e-4": re.compile(r"3\.06e-4"),
    "alpha=0 called mid-stroke": re.compile(
        r"(α|alpha)\s*=\s*0\s+(at\s+)?mid[-\s\u2011]?stroke"
    ),
    "~0 at mid-stroke": re.compile(r"[≈~]\s*0\s+at\s+mid[-\s\u2011]?stroke"),
    "quarter-period mid-stroke": re.compile(r"quarter-period\s+mid[-\s\u2011]?stroke"),
    # Forward-only: PR #168 already removed these; they guard against a regression.
    "T4 compared with coarse CFD 2.61": re.compile(r"vs\.?\s+cfd\s*[≈~]\s*2\.61"),
    "T4 phase gap ~0.058": re.compile(r"~\s*0\.058"),
}


def _code(source: str) -> tuple[str, str]:
    return ("code", source)


def _spec(sentence: str) -> tuple[str, str]:
    return ("spec", sentence)


# One verbatim stale sentence per site (string literals: CI's shallow checkout cannot git show).
# Spec sites from the live specs at c87e39c (the T4 pair from 5fd6b2c^); code sites as source
# fragments, read through python_prose as the guard reads the code.
RETIRED_EXAMPLES: dict[str, list[tuple[str, str]]] = {
    "coarse latency speedup ~310x": [
        _spec(
            "The conservative per-evaluation **latency**\nspeedup (~310× on the coarse grid, "
            "which is **not** >1,000×; on the fine grid the floor may"
        )
    ],
    "parallelism factor 12,009": [
        _spec(
            "> Note: the result numbers still embedded above and in the scenarios (~310×, "
            "N=12,535, ≈12,009×,"
        ),
        _spec(
            "the batch size, and the implied parallelism factor (≈12,009×, = throughput_speedup "
            "÷ latency_speedup) so the headline is fully decomposable"
        ),
    ],
    "QS model under-predicts": [
        _spec(
            "the quasi-steady reference's RMS ratio is described neutrally (translational-only "
            "model, a poor fit that under-predicts the in-band CFD lift)"
        )
    ],
    "stale numbers tracked in #115": [
        _spec(
            "committed coarse value (≈ 1.3, `examples/prelim_sweep/figures/"
            "evidence_figure_metrics.json`); stale\nnumbers in this spec are tracked in #115."
        ),
        _spec(
            "> 3.7×10⁶×) are stale against the committed artifacts and are tracked separately "
            "in issue #115;"
        ),
    ],
    "throughput = latency x batch size": [
        _spec(
            "which is the >1,000× claim. Because this factor equals\n`latency_speedup × "
            "batch_size` (the surrogate is a pointwise map that batches; the CFD is an"
        ),
        _code(
            'def compute_speedup():\n    """Decompose the speedup.\n\n    The headline >1,000x '
            "is **batched GPU throughput** vs the grid's A40 CFD rate;\n    because it equals "
            "``latency_speedup * batch_size`` (the surrogate batches; the CFD is a\n    "
            'sequential time integration).\n    """\n'
        ),
    ],
    "two orders of magnitude": [
        _spec(
            "whereas the normalized ratio separates healthy from truncated configurations by "
            "roughly\ntwo orders of magnitude."
        )
    ],
    "usable tolerance window": [
        _spec(
            "amplitude and reaches 2.9% of `F_ref` on a healthy corpus, leaving a usable "
            "tolerance window of only\nabout 1.3×,"
        )
    ],
    "config_mean_r2 physically-central": [
        _spec(
            "**cycle-mean** coefficient (the phase-removed config-to-config skill, the "
            "physically-central\ncycle-averaged force)"
        ),
        _code(
            'def compute_config_resolved():\n    """Config-resolved metrics.\n\n    - '
            "``config_mean_r2`` — R² on the per-configuration **cycle-mean** coefficient "
            "(phase removed;\n      the physically-central cycle-averaged force).\n"
            '    """\n'
        ),
    ],
    "QS RMS ratio ~0.7": [
        _spec(
            "as measured, with no bound asserted: the earlier statement that it is < 1 (≈ 0.7) "
            "does not match the"
        )
    ],
    "covered only 83%": [
        _spec(
            "- **Given** a configuration that covered only 83% of its settled wingbeat"
        ),
        _spec(
            "- **Given** a corpus containing a configuration that covered only 83% of its "
            "settled wingbeat"
        ),
    ],
    "observed dt 3.06e-4": [
        _spec(
            "- **Given** a corpus in which one configuration's observed interior timesteps fell "
            "to `3.06e-4`\n  against a declared `ns.fixed_dt` of `5e-4`"
        )
    ],
    "alpha=0 called mid-stroke": [
        _spec(
            "horizontal (in-stroke-plane) excursion SHALL trace a `±φ_amp` arc that is "
            "**non-zero at the α=0\nmidstroke**"
        ),
        _spec(
            "- **When** the span-tip's horizontal excursion is measured at the α=0 midstroke"
        ),
    ],
    "~0 at mid-stroke": [
        _spec(
            "whereas the old composition (stroke `Rz(φ)` about the span) gives a `sin α` "
            "excursion that\nis `≈0` at midstroke."
        )
    ],
    "quarter-period mid-stroke": [
        _code(
            "def test_euler_angles_midstroke_has_zero_pitch():\n"
            '    """At the quarter-period midstroke, φ is at amplitude and α (∝cos) is 0."""\n'
        )
    ],
    "T4 compared with coarse CFD 2.61": [
        _spec(
            "the per-component + total model coefficients, the graded normal peak magnitude "
            "(≈2.48 vs CFD ≈2.61), the"
        )
    ],
    "T4 phase gap ~0.058": [
        _spec(
            "reported normal peak-phase gap (~0.058 cycle) and curve RMSE, and the known-answer "
            "translational-chord peak"
        )
    ],
}

# Corrective sentences this change wrote, and true quotes that look like retired claims.
MUST_PASS = (
    "the ratio is stated as measured, with no claim that the model over- or under-predicts "
    "the CFD lift",
    "The parallelism factor is `throughput_speedup ÷ latency_speedup` by definition, and equals "
    "`N · t_single / t_batch` for a batch of `N` rows",
    "pins the known answer ≈310×; a fixture value, not a corpus result",
    "Dividing by the configuration's settled-beat peak reduces that dependence; it does not "
    "remove it.",
    "`config_mean_r2` is a diagnostic, not the surrogate's headline skill.",
    "stroke reversal is `t = T/4` or `3T/4`, where `φ = ±φ_amp`, `φ̇ = 0` and the pitch is zero. "
    "Mid-stroke is `t = 0` or `T/2`, where `φ = 0` and `|α| = α_amp`.",
    "so the old span-tip's distance from its axis is `≈0` and the new span-tip's",
    "- **Then** peak `CF_normal ≈ 2.61` (`cf_normal_match = True`) and peak `CF_chord ≈ 0.92`",
    "the CFD side reproduces the T2a coarse peaks (`CF_chord ≈ 0.92`, `CF_normal ≈ 2.61`)",
    'number (`2.48`, `0.43`, `0.42` not preceded by a minus sign, `0.055`, `0.058`, and "near '
    '0.18")',
    # The corrected docstrings (compute_speedup, compute_config_resolved).
    "It is the latency speedup times the parallelism factor ``throughput_speedup / "
    "latency_speedup`` = N·t_single/t_batch, a measured ratio that can be larger or smaller "
    "than the batch size N and is not N.",
    "A diagnostic, not the headline skill: it divides by the spread of a few held-out cycle "
    "means and is strongly seed-dependent",
    # The renamed kinematics test's docstring.
    "At stroke reversal (t = T/4), φ is at amplitude and α (∝ cos) is 0.",
)

# The MUST_PASS sentences quoted from a spec, with the spec they must actually occur in, so a
# corrective rewording cannot leave the "accepts the corrective text" test passing on a sentence
# the spec no longer contains.
MUST_PASS_IN_SPEC = {
    MUST_PASS[0]: FS,
    MUST_PASS[1]: FS,
    MUST_PASS[2]: FS,
    MUST_PASS[3]: FS,
    MUST_PASS[4]: FS,
    MUST_PASS[5]: FWV,
    MUST_PASS[6]: FWV,
    MUST_PASS[7]: FWV,
    MUST_PASS[8]: FWV,
    MUST_PASS[9]: FWV,
}

# Fixed strings in requirements this change does not touch: the scan cannot pass vacuously.
SPEC_ANCHORS = {
    FS: "### Requirement: Moment coefficients are referenced to the wing hinge",
    FWV: "### Requirement: RESULTS.md headline numbers reproducible from committed CSVs",
}


def test_every_retired_pattern_has_examples():
    assert set(RETIRED_EXAMPLES) == set(RETIRED)
    assert all(RETIRED_EXAMPLES.values())


@pytest.mark.parametrize("pname", list(RETIRED))
def test_retired_patterns_match_their_examples(pname):
    """Scenario: A retired claim fails the guard (each pattern matches every stale site)."""
    for kind, example in RETIRED_EXAMPLES[pname]:
        text = python_prose(example) if kind == "code" else example
        assert RETIRED[pname].search(normalize(text)), (pname, example)


@pytest.mark.parametrize("sentence", MUST_PASS)
def test_retired_patterns_accept_the_corrective_text(sentence):
    """Scenario: Retired patterns accept the corrective text."""
    assert sc.retired_hits(sentence, RETIRED, "MUST_PASS") == []


@pytest.mark.parametrize("sentence", list(MUST_PASS_IN_SPEC))
def test_spec_quoted_corrective_text_is_in_the_spec(sentence):
    """The quoted corrective sentence is really in its spec's effective text."""
    capability = MUST_PASS_IN_SPEC[sentence]
    assert normalize(sentence) in normalize(sc.effective_text(capability)), capability


def _scan_spec(capability: str, text: str) -> list[str]:
    """Retired-claim hits in a spec's text, after checking its anchor (no vacuous scan)."""
    if SPEC_ANCHORS[capability] not in text:
        raise AssertionError(f"{capability}: anchor missing; the scan would be vacuous")
    return sc.retired_hits(text, RETIRED, capability)


@pytest.mark.parametrize("capability", [FS, FWV])
def test_no_retired_claim_in_live_specs(capability):
    """Scenario: the effective text of each spec carries no retired claim."""
    hits = _scan_spec(capability, sc.effective_text(capability))
    assert not hits, "\n".join(hits)


@pytest.mark.parametrize("capability", [FS, FWV])
def test_reintroduced_retired_sentence_fails(capability):
    """Every stale spec sentence, inserted into the raw effective text, is reported by name."""
    text = sc.effective_text(capability)
    for pname, examples in RETIRED_EXAMPLES.items():
        for kind, example in examples:
            if kind != "spec":
                continue
            hits = sc.retired_hits(text + "\n\n" + example, RETIRED, capability)
            assert any(f"[{pname}]" in h and h.startswith(capability) for h in hits), (
                pname
            )


@pytest.mark.parametrize("capability", [FS, FWV])
def test_tripwire_anchor_rejects_an_empty_or_unrelated_spec(capability):
    for text in ("", "# Some other spec\n\n### Requirement: Unrelated\n\nBody.\n"):
        with pytest.raises(AssertionError, match="anchor missing"):
            _scan_spec(capability, text)


# --- Code that repeated a retired claim (design D5 "Targets") -------------------------------

# path -> a fixed string in that file, so the scan cannot pass on an empty or wrong file.
CODE_TARGETS = {
    "src/mosquito_cfd/force_surrogate/evidence_figure.py": "def compute_speedup",
    "src/mosquito_cfd/force_surrogate/train.py": "def compute_config_resolved",
    "tests/test_wing_kinematics.py": "def test_rotation_is_orthonormal",
}
# Raw test names (normalize() would strip their underscores) that call t = T/4 mid-stroke.
_RETIRED_TEST_NAMES = re.compile(r"def (test_\w*midstroke_has_zero_pitch\w*)")
_KINEMATICS = _REPO / "tests" / "test_wing_kinematics.py"
_REVERSAL_TEST = "test_euler_angles_at_stroke_reversal_have_zero_pitch"


def _code_prose_hits(path: str, source: str) -> list[str]:
    """Retired-claim hits in a code file's prose, after checking its anchor."""
    if CODE_TARGETS[path] not in source:
        raise AssertionError(f"{path}: anchor missing; the scan would be vacuous")
    return sc.retired_hits(python_prose(source), RETIRED, path)


def _retired_test_names(source: str) -> list[str]:
    return _RETIRED_TEST_NAMES.findall(source)


@pytest.mark.parametrize("path", list(CODE_TARGETS))
def test_no_retired_claim_in_code_prose(path):
    """Scenario: A retired claim fails the guard (in a guarded code docstring)."""
    hits = _code_prose_hits(path, (_REPO / path).read_text(encoding="utf-8"))
    assert not hits, "\n".join(hits)


@pytest.mark.parametrize("path", list(CODE_TARGETS))
def test_code_scan_rejects_a_file_without_its_anchor(path):
    with pytest.raises(AssertionError, match="anchor missing"):
        _code_prose_hits(path, "def unrelated():\n    pass\n")


def test_kinematics_test_names_do_not_call_reversal_midstroke():
    """Scenario: The kinematics tests name the instant they measure (names, read raw)."""
    source = _KINEMATICS.read_text(encoding="utf-8")
    assert "def test_" in source
    assert _retired_test_names(source) == []
    # The check is not vacuous: the pre-change name is caught.
    assert _retired_test_names("def test_euler_angles_midstroke_has_zero_pitch():")


def test_renamed_reversal_test_exists():
    """Scenario: The kinematics tests name the instant they measure (the renamed test exists)."""
    import ast

    tree = ast.parse(_KINEMATICS.read_text(encoding="utf-8"))
    funcs = {
        n.name: ast.get_docstring(n) or ""
        for n in tree.body
        if isinstance(n, ast.FunctionDef)
    }
    assert _REVERSAL_TEST in funcs
    assert "stroke reversal" in funcs[_REVERSAL_TEST]


@pytest.mark.parametrize("path", list(CODE_TARGETS))
def test_reintroduced_code_claim_fails(path):
    """Every stale code example, appended to the real source, is reported by name."""
    source = (_REPO / path).read_text(encoding="utf-8")
    for pname, examples in RETIRED_EXAMPLES.items():
        for kind, example in examples:
            if kind == "code":
                hits = _code_prose_hits(path, source + "\n\n" + example)
                assert any(f"[{pname}]" in h for h in hits), pname


# --- Stale fixtures: the permanent red ------------------------------------------------------


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_every_retired_pattern_hits_a_stale_fixture():
    """Scenario: The pre-change text fails the guard (no pattern is unexercised)."""
    texts = [
        _fixture("stale_force_surrogate.md"),
        _fixture("stale_flapping_wing_validation.md"),
        _fixture("stale_code_prose.txt"),
        _fixture("stale_fwv_pre168.md"),
    ]
    missed = [
        p
        for p, pat in RETIRED.items()
        if not any(pat.search(normalize(t)) for t in texts)
    ]
    assert not missed, missed


_STALE_SITES = {
    "Config-resolved (phase-honest) evaluation metrics": {
        "config_mean_r2 physically-central"
    },
    "Sane–Dickinson quasi-steady reference (computed, not overlaid)": {
        "QS model under-predicts",
        "stale numbers tracked in #115",
        "QS RMS ratio ~0.7",
    },
    "Honest evidence-figure caption and speedup annotation": {
        "coarse latency speedup ~310x",
        "parallelism factor 12,009",
        "stale numbers tracked in #115",
        "throughput = latency x batch size",
    },
    # Its staleness is a number (3.119), caught by the registry, not by a retired phrase.
    "Re-normalization preserves surrogate skill (scale-invariance)": set(),
    "Post-run acceptance gate blocks dataset construction on an unverified corpus": {
        "two orders of magnitude",
        "usable tolerance window",
        "covered only 83%",
        "observed dt 3.06e-4",
    },
    "Committed corpora are guarded by cluster-free reconciliation tests": {
        "covered only 83%"
    },
    "Stroke motion reproduces van Veen's translational sweep": {
        "alpha=0 called mid-stroke",
        "~0 at mid-stroke",
    },
}

# (stale block, number token, minimum count beyond the registry). The check is >=, so adding
# or removing a registry entry with the same literal does not break this permanent red.
_STALE_EXTRA_TOKENS = {
    "Sane–Dickinson quasi-steady reference (computed, not overlaid)": {
        "1": 1,
        "0.7": 1,
        "1.3": 1,
    },
    "Honest evidence-figure caption and speedup annotation": {
        "1,000": 1,
        "12,535": 1,
        "310": 2,
        "12,009": 2,
        "3.7": 2,
        "10": 3,
    },
    "Re-normalization preserves surrogate skill (scale-invariance)": {"3.119": 1},
    "Post-run acceptance gate blocks dataset construction on an unverified corpus": {
        "2.9": 1,
        "1.3": 1,
        "3.06e-4": 1,
        "5e-4": 1,
        "83": 1,
    },
    "Committed corpora are guarded by cluster-free reconciliation tests": {"83": 1},
}


def _stale_blocks() -> dict[str, str]:
    blocks = sc.requirement_blocks(_fixture("stale_force_surrogate.md"))
    blocks.update(sc.requirement_blocks(_fixture("stale_flapping_wing_validation.md")))
    return blocks


def test_stale_fixtures_trip_the_guard():
    """Scenario: The pre-change text fails the guard.

    Superset checks: a later delta to a guarded requirement must not break this permanent red.
    """
    blocks = _stale_blocks()
    assert set(_STALE_SITES) == set(blocks)
    for name, expected in _STALE_SITES.items():
        found = {
            pname
            for pname in RETIRED
            if sc.retired_hits(blocks[name], {pname: RETIRED[pname]}, name)
        }
        assert expected <= found, (name, expected - found)
    for name, extra in _STALE_EXTRA_TOKENS.items():
        failures = sc.check_block(name, blocks[name], REGISTRY[name])
        joined = "\n".join(failures)
        for tok, n in extra.items():
            m = re.search(
                rf"unregistered number {re.escape(repr(tok))} \(x(\d+)\)", joined
            )
            assert m and int(m[1]) >= n, (name, tok, n)
    # Config-resolved's stale claim is a word: the registry passes it, only the tripwire flags it.
    cr = "Config-resolved (phase-honest) evaluation metrics"
    assert not [
        f for f in sc.check_block(cr, blocks[cr], REGISTRY[cr]) if "unregistered" in f
    ]


# --- The registry ---------------------------------------------------------------------------


def _k() -> float:
    from mosquito_cfd.force_surrogate import compute_force_reference
    from mosquito_cfd.force_surrogate import constants as c

    tip = compute_force_reference(1.0, 70.0, c.R_TIP, c.SPAN, c.CHORD, c.RHO).f_ref
    gyr = compute_force_reference(1.0, 70.0, c.R_GYRATION, c.SPAN, c.CHORD, c.RHO).f_ref
    return tip / gyr


def _cfd_seconds_per_wingbeat() -> float:
    from mosquito_cfd.force_surrogate import evidence_figure

    return evidence_figure.CFD_SECONDS_PER_WINGBEAT


def _toy_speedup() -> dict:
    from mosquito_cfd.force_surrogate import compute_speedup

    return compute_speedup(
        _evidence_fixture._toy_metrics()["inference"],
        rows_per_wingbeat=_evidence_fixture.TOY_ROWS_PER_WINGBEAT,
    )


def _toy_inference(key: str) -> Callable[[], float]:
    return lambda: _evidence_fixture._toy_metrics()["inference"][key]


def _toy_rows() -> float:
    return _evidence_fixture.TOY_ROWS_PER_WINGBEAT


def _speedup(key: str) -> Callable[[], float]:
    return lambda: _toy_speedup()[key]


E = sc.Entry


def P(phrase: str, *items: tuple) -> list[sc.Entry]:
    """Entries sharing one phrase: each item is ``(literal, kind, source[, count])``."""
    return [E(phrase, *item) for item in items]


_KNOWN = "synthetic known-answer input of the scenario"
_KNOWN_OUT = (
    "synthetic known-answer output, pinned by tests/test_force_surrogate_train.py::"
)
_THRESHOLD = "the >1,000× claim's threshold, not a measured value"
_GRID = "grid size by design"
_FORMULA = "constant in a formula"
_SIGN = "the sign case's factor (tokens are sign-blind; #176)"
_RETIRED_QUOTE = (
    "quoted retired claim, asserted absent from the caption and README by "
    "tests/test_force_surrogate_evidence_figure.py::test_build_caption_discloses_everything "
    "and ::test_readme_carries_full_disclosures"
)
_CR_KNOWN = _KNOWN_OUT + "test_config_resolved_known_answer"

REGISTRY: dict[str, list[sc.Entry]] = {
    "Config-resolved (phase-honest) evaluation metrics": [
        *P(
            "`[1, 3]` (mean 2) and `[5, 7]` (mean 6)",
            ("1", "declared", _KNOWN),
            ("3", "declared", _KNOWN),
            ("2", "declared", _KNOWN),
            ("5", "declared", _KNOWN),
            ("7", "declared", _KNOWN),
            ("6", "declared", _KNOWN),
        ),
        *P(
            "cycle-means of `2` and `5`",
            ("2", "declared", _KNOWN),
            ("5", "declared", _KNOWN),
        ),
        *P("`within_config_variance_fraction == 0.2`", ("0.2", "declared", _CR_KNOWN)),
        *P(
            "(within-config SS 4 / total SS 20)",
            ("4", "declared", _CR_KNOWN),
            ("20", "declared", _CR_KNOWN),
        ),
        *P("`config_mean_r2 == 0.875`", ("0.875", "declared", _CR_KNOWN)),
        *P(
            "(`1 - 1/8`)", ("1", "declared", _CR_KNOWN, 2), ("8", "declared", _CR_KNOWN)
        ),
        *P("an unhandled `0/0`", ("0", "declared", _FORMULA, 2)),
        *P(
            "`within_config_variance_fraction == 1.0`",
            ("1.0", "declared", _KNOWN_OUT + "test_config_resolved_single_config"),
        ),
    ],
    "Sane–Dickinson quasi-steady reference (computed, not overlaid)": [
        *P("`U(t)/u_ref = cos(2π·phase)`", ("2", "declared", _FORMULA)),
        *P("Dickinson–Lehmann–Sane (1999)", ("1999", "declared", "citation year")),
        *P("the Dickinson-1999 fit", ("1999", "declared", "citation year")),
        *P(
            "first established on the coarse 64×32×64 grid",
            ("64", "declared", _GRID, 2),
            ("32", "declared", _GRID),
        ),
        *P('"~2.4× diffused-IB underestimate"', ("2.4", "declared", _RETIRED_QUOTE, 2)),
        *P(
            "`(cos(2π·phase))² · C_L(α_amp·|cos(2π·phase)|)`",
            ("2", "declared", _FORMULA, 2),
        ),
        *P("`phi_amp_deg == 45`", ("45", "declared", _KNOWN + " (s45_f115_p60)")),
        *P("`f_star == 1.15`", ("1.15", "declared", _KNOWN + " (s45_f115_p60)")),
        *P("`pitch_amp_deg == 60`", ("60", "declared", _KNOWN + " (s45_f115_p60)")),
    ],
    "Honest evidence-figure caption and speedup annotation": [
        *P("the >1,000× batched speedup", ("1,000", "declared", _THRESHOLD, 2)),
        *P("which is the >1,000× claim", ("1,000", "declared", _THRESHOLD)),
        *P("whether or not it exceeds 1,000×", ("1,000", "declared", _THRESHOLD)),
        *P(
            "The >1,000× headline is the batched-throughput speedup",
            ("1,000", "declared", _THRESHOLD),
        ),
        *P("the realized factor exceeds 1,000×", ("1,000", "declared", _THRESHOLD)),
        *P("asserted to exceed 1,000×", ("1,000", "declared", _THRESHOLD)),
        *P(
            "coarse-grid forces** (64×32×64)",
            ("64", "declared", _GRID, 2),
            ("32", "declared", _GRID),
        ),
        *P(
            "for the fine grid (256×128×256)",
            ("256", "declared", _GRID, 2),
            ("128", "declared", _GRID),
        ),
        *P(
            "144 s on the coarse grid",
            ("144", "recomputed", lambda: _cfd_seconds_per_wingbeat()),
        ),
        *P(
            "The fixture's 2000 rows per wingbeat and 12,535-row",
            ("2000", "fixture", lambda: _toy_rows()),
            ("12,535", "fixture", _speedup("batch_size")),
        ),
        *P("(and another's is exactly 0)", ("0", "declared", _KNOWN)),
        *P(
            "`throughput_rows_per_s = 5.17e7`, 2000 rows per wingbeat, a 12,535-row batch",
            ("5.17e7", "fixture", _toy_inference("throughput_rows_per_s")),
            ("2000", "fixture", lambda: _toy_rows()),
            ("12,535", "fixture", _speedup("batch_size")),
        ),
        *P(
            "5.17e7 ÷ (2000/144) ≈ 3.72e6",
            ("5.17e7", "fixture", _toy_inference("throughput_rows_per_s")),
            ("2000", "fixture", lambda: _toy_rows()),
            ("144", "recomputed", lambda: _cfd_seconds_per_wingbeat()),
            ("3.72e6", "fixture", _speedup("throughput_speedup")),
        ),
        *P("`rows_per_wingbeat = 1/(f*·dt)`", ("1", "declared", _FORMULA)),
        *P(
            "`t_cfd_per_row / (latency_ms/1000)`",
            ("1000", "declared", "ms-to-s conversion"),
        ),
        *P(
            "`latency_ms = 0.232` at 2000 rows per wingbeat pins the known answer ≈310×",
            ("0.232", "fixture", _toy_inference("latency_ms")),
            ("2000", "fixture", lambda: _toy_rows()),
            ("310", "fixture", _speedup("latency_speedup")),
        ),
        *P("with `k == 1` it states", ("1", "declared", _KNOWN)),
        *P(
            'states "Fine 256x128x256 grid',
            ("256", "declared", _GRID, 2),
            ("128", "declared", _GRID),
        ),
        *P(
            'contains no "coarse", "64x32x64"',
            ("64", "declared", _GRID, 2),
            ("32", "declared", _GRID),
        ),
    ],
    "Re-normalization preserves surrogate skill (scale-invariance)": [
        *P("≈ 3.120), so re-expressing it", ("3.120", "recomputed", lambda: _k())),
        *P(
            "`k = f_ref_old / f_ref_new` (≈ 3.120)",
            ("3.120", "recomputed", lambda: _k()),
        ),
        *P("with `k = −1`: the raw columns", ("1", "declared", _SIGN)),
        *P("(`k = −1` is its own inverse", ("1", "declared", _SIGN)),
        *P("the k = −1 scale case", ("1", "declared", _SIGN)),
        *P("(`k = −1`), as verified", ("1", "declared", _SIGN)),
        *P("within `1e-9`, confirming", ("1e-9", "declared", "tolerance")),
        *P("within `1e-9` relative", ("1e-9", "declared", "tolerance")),
        *P("(within `1e-9`)", ("1e-9", "declared", "tolerance")),
        *P("`f_ref_new = 0`", ("0", "declared", _KNOWN)),
    ],
    "Post-run acceptance gate blocks dataset construction on an unverified corpus": [],
    "Committed corpora are guarded by cluster-free reconciliation tests": [],
    "Guards on specification text read the effective specification": [],
    "Data-dependent claims in the live specs are guarded against committed data": [],
    "Stroke motion reproduces van Veen's translational sweep": [
        *P(
            "stroke reversal is `t = T/4` or `3T/4`",
            ("4", "declared", "kinematic instant", 2),
            ("3", "declared", "kinematic instant"),
        ),
        *P("`φ̇ = 0`", ("0", "declared", "kinematic value")),
        *P(
            "Mid-stroke is `t = 0` or `T/2`, where `φ = 0`",
            ("0", "declared", "kinematic value", 2),
            ("2", "declared", "kinematic instant"),
        ),
        *P("`θ ∝ sin 2ωt`", ("2", "declared", _FORMULA)),
        *P("is `≈0`", ("0", "declared", "kinematic value", 2)),
        *P("`(0, r, 0)`", ("0", "declared", "kinematic vector", 6)),
        *P("(`t = T/4`: `φ = φ_amp`", ("4", "declared", "kinematic instant")),
        *P("(`φ = 0`, `α = α_amp`)", ("0", "declared", "kinematic value")),
        *P("`(0, 0, r)`", ("0", "declared", "kinematic vector", 2)),
        *P("`(0, −r·sin α_amp, r·cos α_amp)`", ("0", "declared", "kinematic vector")),
        *P("position at `t = T/4`", ("4", "declared", "kinematic instant")),
    ],
    "Retired kinematics and T4 claims stay out of this specification": [],
}

GUARDED: dict[str, list[str]] = {
    FS: [
        "Config-resolved (phase-honest) evaluation metrics",
        "Sane–Dickinson quasi-steady reference (computed, not overlaid)",
        "Honest evidence-figure caption and speedup annotation",
        "Re-normalization preserves surrogate skill (scale-invariance)",
        "Post-run acceptance gate blocks dataset construction on an unverified corpus",
        "Committed corpora are guarded by cluster-free reconciliation tests",
        "Guards on specification text read the effective specification",
        "Data-dependent claims in the live specs are guarded against committed data",
    ],
    FWV: [
        "Stroke motion reproduces van Veen's translational sweep",
        "Retired kinematics and T4 claims stay out of this specification",
    ],
}


_HOW_TO_FIX = (
    "To fix: edit REGISTRY in tests/test_live_spec_claims.py. Register each number with the "
    "phrase that contains it as 'recomputed' (from a committed artifact or code constant), "
    "'fixture' (from tests/_evidence_fixture.py) or 'declared' (not a measured result, with the "
    "reason); or delete a corpus result whose value is not the point (#115)."
)


def test_registry_covers_exactly_the_guarded_requirements():
    assert set(REGISTRY) == {n for names in GUARDED.values() for n in names}


@pytest.mark.parametrize(
    ("capability", "name"), [(c, n) for c, names in GUARDED.items() for n in names]
)
def test_guarded_requirement_numbers_are_registered(capability, name):
    """Scenario: An unregistered, missing or stale number fails the guard (here: none does)."""
    failures = sc.check_block(
        name, sc.effective_block(capability, name), REGISTRY[name]
    )
    assert not failures, "\n".join([*failures, _HOW_TO_FIX])


# --- Synthetic must-fail tests (each also kills a mutant of the checker) --------------------

_SYN_TEXT = (
    "### Requirement: Syn\n\nThe factor is ≈ 3.120 and the batch has\n12,535 rows."
)
_SYN = [
    E("factor is ≈ 3.120", "3.120", "recomputed", lambda: 3.1197),
    E("the batch has 12,535 rows", "12,535", "declared", "synthetic"),
]


def test_synthetic_registry_passes_including_a_wrapped_phrase():
    assert sc.check_block("Syn", _SYN_TEXT, _SYN) == []


@pytest.mark.parametrize(
    ("text", "entries", "needle"),
    [
        (_SYN_TEXT + " Also 17.5 widgets.", _SYN, "unregistered number '17.5'"),
        (_SYN_TEXT + " Again ≈ 3.120.", _SYN, "unregistered number '3.120' (x1)"),
        (
            _SYN_TEXT,
            [*_SYN, E("factor is ≈ 3.120", "9", "declared", "x")],
            "'9' (x1) is not in",
        ),
        (
            _SYN_TEXT.replace("the batch has", "the set has"),
            _SYN,
            "phrase 'the batch has 12,535 rows'",
        ),
        (_SYN_TEXT.replace("3.120", "3.121"), _SYN, "unregistered number '3.121'"),
        (
            _SYN_TEXT,
            [E("factor is ≈ 3.120", "3.120", "recomputed", lambda: 3.1217), _SYN[1]],
            "now prints as '3.122'",
        ),
        (
            _SYN_TEXT + " It is 3.72×10⁶, ~10³× and 1×10⁻⁹.",
            [
                *_SYN,
                E("It is 3.72×10⁶", "3.72", "declared", "x"),
                E("It is 3.72×10⁶, ~10³× and 1×10⁻⁹", "10", "declared", "x", count=3),
                E("and 1×10⁻⁹", "1", "declared", "x"),
            ],
            "superscript exponent",
        ),
        (
            _SYN_TEXT,
            [_SYN[0], E("the batch has 12,535 rows", "12,535", "declared", "")],
            "no reason",
        ),
        (  # each literal bound to the other's phrase: the multiset balances, the binding fails
            _SYN_TEXT,
            [
                E("the batch has 12,535 rows", "3.120", "recomputed", lambda: 3.1197),
                E("factor is ≈ 3.120", "12,535", "declared", "x"),
            ],
            "does not contain '3.120'",
        ),
        (
            _SYN_TEXT,
            [E("factor is ≈ 3.120", "3.120", "measured", lambda: 3.1197), _SYN[1]],
            "unknown kind 'measured'",
        ),
        (
            _SYN_TEXT,
            [E("factor is ≈ 3.120", "3.120", "recomputed", lambda: -3.1197), _SYN[1]],
            "is negative",
        ),
        (  # a count larger than the phrase's own occurrences cannot bind the extra copies
            _SYN_TEXT + " Also 12,535 more.",
            [
                _SYN[0],
                E("the batch has 12,535 rows", "12,535", "declared", "x", count=2),
            ],
            "occurs 1 time(s) in the phrase's sites",
        ),
    ],
)
def test_check_block_reports(text, entries, needle):
    failures = sc.check_block("Syn", text, entries)
    assert any(needle in f for f in failures), failures
    assert all(f.startswith("Syn: ") for f in failures)


# --- Drift tests: each source of a registered number is load-bearing ------------------------

_RENORM = "Re-normalization preserves surrogate skill (scale-invariance)"
_CAPTION = "Honest evidence-figure caption and speedup annotation"


def test_drifted_spec_number_fails():
    block = sc.effective_block(FS, _RENORM)
    assert sc.check_block(_RENORM, block, REGISTRY[_RENORM]) == []
    drifted = block.replace("≈ 3.120", "≈ 3.121", 1)
    assert drifted != block
    failures = sc.check_block(_RENORM, drifted, REGISTRY[_RENORM])
    assert any("'3.121'" in f for f in failures), failures


def test_drifted_exponent_fails():
    block = sc.effective_block(FS, _CAPTION)
    drifted = block.replace("≈ 3.72e6", "≈ 3.72e7", 1)
    assert drifted != block
    failures = sc.check_block(_CAPTION, drifted, REGISTRY[_CAPTION])
    assert any("'3.72e7'" in f for f in failures), failures


def test_drifted_recomputed_source_fails(monkeypatch):
    from mosquito_cfd.force_surrogate import constants

    # Move k's third decimal (3.120 -> 3.121) without moving its second.
    drifted_gyr = constants.R_TIP / math.sqrt(3.1212)
    monkeypatch.setattr(constants, "R_GYRATION", drifted_gyr)
    assert f"{_k():.3f}" == "3.121"
    failures = sc.check_block(
        _RENORM, sc.effective_block(FS, _RENORM), REGISTRY[_RENORM]
    )
    assert any("now prints as '3.121'" in f for f in failures), failures


def _patch_toy(monkeypatch, **inference):
    real = _evidence_fixture._toy_metrics

    def drifted(**kw):
        m = real(**kw)
        m["inference"].update(inference)
        return m

    monkeypatch.setattr(_evidence_fixture, "_toy_metrics", drifted)


def _patch_cfd_seconds(monkeypatch):
    from mosquito_cfd.force_surrogate import evidence_figure

    monkeypatch.setattr(evidence_figure, "CFD_SECONDS_PER_WINGBEAT", 145.0)


def _patch_rows(monkeypatch):
    monkeypatch.setattr(_evidence_fixture, "TOY_ROWS_PER_WINGBEAT", 2001)


def _patch_latency(monkeypatch):
    _patch_toy(monkeypatch, latency_ms=0.240)


def _patch_batch(monkeypatch):
    basis = _evidence_fixture._toy_metrics()["inference"]["basis"]
    assert basis.count("12535 rows") == 1
    _patch_toy(monkeypatch, basis=basis.replace("12535 rows", "12536 rows"))


def _patch_throughput(monkeypatch):
    _patch_toy(monkeypatch, throughput_rows_per_s=5.18e7)


def _patch_gyration(monkeypatch):
    from mosquito_cfd.force_surrogate import constants

    monkeypatch.setattr(constants, "R_GYRATION", constants.R_TIP / math.sqrt(3.1212))


# (patch, requirement, the literals it must make drift)
_SOURCE_DRIFTS = {
    "CFD_SECONDS_PER_WINGBEAT": (_patch_cfd_seconds, _CAPTION, {"144"}),
    "TOY_ROWS_PER_WINGBEAT": (_patch_rows, _CAPTION, {"2000"}),
    "toy latency": (_patch_latency, _CAPTION, {"0.232", "310"}),
    "toy batch in basis": (_patch_batch, _CAPTION, {"12,535"}),
    "toy throughput": (_patch_throughput, _CAPTION, {"5.17e7", "3.72e6"}),
    "R_GYRATION": (_patch_gyration, _RENORM, {"3.120"}),
}


def test_every_non_declared_literal_has_a_source_drift_test():
    non_declared = {
        e.literal
        for entries in REGISTRY.values()
        for e in entries
        if e.kind != "declared"
    }
    covered = set().union(*(lits for _, _, lits in _SOURCE_DRIFTS.values()))
    assert non_declared == covered


@pytest.mark.parametrize("source", list(_SOURCE_DRIFTS))
def test_every_non_declared_source_is_load_bearing(source, monkeypatch):
    """Scenario: Each source of a recomputed number is load-bearing (one drift per source)."""
    patch, name, literals = _SOURCE_DRIFTS[source]
    block = sc.effective_block(FS, name)
    assert sc.check_block(name, block, REGISTRY[name]) == []
    patch(monkeypatch)
    failures = "\n".join(sc.check_block(name, block, REGISTRY[name]))
    for lit in literals:
        assert f"number {lit!r}" in failures and "now prints as" in failures, (
            lit,
            failures,
        )


def test_drifted_fixture_source_fails(monkeypatch):
    real = _evidence_fixture._toy_metrics

    def drifted(**kw):
        m = real(**kw)
        m["inference"]["throughput_rows_per_s"] = 5.18e7
        return m

    monkeypatch.setattr(_evidence_fixture, "_toy_metrics", drifted)
    failures = sc.check_block(
        _CAPTION, sc.effective_block(FS, _CAPTION), REGISTRY[_CAPTION]
    )
    assert any("now prints as '5.18e7'" in f for f in failures), failures
