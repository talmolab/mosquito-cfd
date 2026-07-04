"""Guard benchmarks/METHODS.md provenance against drift from the built image (T2b).

METHODS.md documents the ``:fp64`` image; its IAMReX commit MUST agree with the pin actually
built into that image (``docker/build-args.env``). The repo refers to the pin by its conventional
abbreviation (``f93dc794``), so this asserts the METHODS commit is a **prefix** of the full 40-hex
build-args pin (equality modulo abbreviation) — not full-40-hex equality, which would force an
unreadable SHA into prose and could not even match an abbreviation on the current stale doc.

Complements ``test_iamrex_pin_consistent`` (build-args.env <-> Dockerfile.fp64); this pair is
METHODS.md <-> build-args.env.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_METHODS = Path("benchmarks/METHODS.md")
_BUILD_ARGS = Path("docker/build-args.env")

# The IAMReX software-stack row: "| IAMReX | commit <7-40 hex> | <url> |". A 7-to-40-hex extractor
# (independent of test_iamrex_pin_consistent's 40-hex regex) so the current abbreviated pin matches.
_METHODS_PIN_RE = re.compile(r"\|\s*IAMReX\s*\|\s*commit\s+([0-9a-f]{7,40})\b")
_BUILD_PIN_RE = re.compile(r"^\s*IAMREX_COMMIT\s*=\s*([0-9a-f]{40})\b", re.MULTILINE)

# The sphere analysis-scripts EXAMPLE call (distinct from the Known-Limitation prose, which already
# names method="cv"). The corrected example passes method="cv"; the stale one uses the bare default.
_EXAMPLE_CV = "extract_sphere_cd('path/to/plt10000', method=\"cv\")"
_EXAMPLE_BARE = "extract_sphere_cd('path/to/plt10000')"


def _methods_pin(text: str) -> str:
    m = _METHODS_PIN_RE.search(text)
    assert m is not None, (
        f"{_METHODS} has no IAMReX software-stack row of the form "
        f"'| IAMReX | commit <7-40 hex> | <url> |'"
    )
    return m.group(1)


def _build_pin(text: str) -> str:
    m = _BUILD_PIN_RE.search(text)
    assert m is not None, f"{_BUILD_ARGS} has no 'IAMREX_COMMIT=<40 hex>'"
    return m.group(1)


@pytest.mark.skipif(
    not (_METHODS.exists() and _BUILD_ARGS.exists()),
    reason="METHODS.md or build-args.env not present",
)
def test_methods_iamrex_pin_matches_build_args():
    """The METHODS.md IAMReX commit is a >=7-hex prefix of the full build-args.env pin."""
    methods_pin = _methods_pin(_METHODS.read_text(encoding="utf-8"))
    build_pin = _build_pin(_BUILD_ARGS.read_text(encoding="utf-8"))
    assert len(methods_pin) >= 7, (
        f"METHODS.md pin '{methods_pin}' is too short to be safe"
    )
    assert build_pin.startswith(methods_pin), (
        f"IAMReX pin skew: METHODS.md pins '{methods_pin}' but docker/build-args.env pins "
        f"'{build_pin}' — the METHODS commit must be a prefix of the built pin (bump METHODS.md)"
    )


@pytest.mark.skipif(not _METHODS.exists(), reason="METHODS.md not present")
def test_methods_has_no_stale_provenance():
    """METHODS.md names the fork + real Dockerfile + the CV example, and drops stale refs.

    The `method="cv"` guard is POSITIVE and scoped to the analysis EXAMPLE call: a "marker absent"
    negative would be vacuous (no literal `method="marker"` exists in the doc), and a bare
    `method="cv" in text` would also be vacuous (Known-Limitation #1 already names it). The upstream
    FP32 issue link (ruohai0925/IAMReX#59) is legitimate and is NOT asserted absent.
    """
    text = _METHODS.read_text(encoding="utf-8")
    # Positive: fork repo, real Dockerfile, and the corrected sphere EXAMPLE call.
    assert "talmolab/IAMReX" in text, "METHODS.md must name the talmolab/IAMReX fork"
    assert "docker/Dockerfile.fp64" in text, (
        "METHODS.md must reference the real Dockerfile.fp64"
    )
    assert _EXAMPLE_CV in text, (
        'the sphere analysis example must call extract_sphere_cd(..., method="cv") — '
        "the T1b-corrected path, not the known-wrong marker default"
    )
    # Negative: the superseded pin, the non-existent Dockerfile, and the bare-default example are gone.
    assert "c5f8e2a" not in text, "stale IAMReX commit c5f8e2a must be removed"
    assert "Dockerfile.iamrex" not in text, (
        "non-existent Dockerfile.iamrex reference must be removed"
    )
    assert _EXAMPLE_BARE not in text, (
        'the bare-default sphere example (marker path) must be replaced with the method="cv" call'
    )
