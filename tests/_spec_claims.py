"""Helpers for guarding OpenSpec specification text (change ``fix-stale-spec-claims``).

A guard on a spec reads its **effective** text: the live ``openspec/specs/<cap>/spec.md`` with
every active (unarchived) change's delta applied. On a proposal branch only the delta carries the
new text; after archiving, the live spec does. Reading the effective text makes one guard hold in
both states (design D3).

Two checks run on that text:

- :func:`retired_hits` is a tripwire for phrases a change retired, applied to
  ``_stale_claims.normalize`` output;
- :func:`check_block` checks that every number in a requirement is registered with the phrase that
  contains it, and is recomputed, fixture or declared (design D4).

Both are pure functions of strings, so their tests can feed them drifted or synthetic text.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from _stale_claims import normalize

_REPO = Path(__file__).resolve().parents[1]
# Read at call time, so a test can monkeypatch them (design D3, D7).
SPECS_DIR = _REPO / "openspec" / "specs"
CHANGES_DIR = _REPO / "openspec" / "changes"

_REQ = re.compile(r"^### Requirement: (.+?)\s*$")
_SECTION = re.compile(r"^## (\S+)")
_DELTA_KINDS = ("ADDED", "MODIFIED", "REMOVED", "RENAMED")


def _lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _split(text: str) -> list[tuple[str | None, str, str]]:
    """``(section, name, block)`` for every requirement block, in order."""
    out: list[tuple[str | None, str, str]] = []
    section: str | None = None
    name: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if name is not None:
            out.append((section, name, "\n".join(buf).rstrip("\n")))

    for line in _lines(text):
        m_req = _REQ.match(line)
        m_sec = None if line.startswith("###") else _SECTION.match(line)
        if m_req:
            flush()
            name, buf = m_req.group(1), [line]
        elif m_sec:
            flush()
            name, buf = None, []
            section = m_sec.group(1)
        elif name is not None:
            buf.append(line)
    flush()
    return out


def requirement_blocks(text: str) -> dict[str, str]:
    """Requirement name → its block (heading to the line before the next heading)."""
    return {name: block for _, name, block in _split(text)}


def delta_sections(text: str) -> dict[str, dict[str, str]]:
    """Delta section (``ADDED`` …) → requirement name → block; other sections are dropped."""
    out: dict[str, dict[str, str]] = {kind: {} for kind in _DELTA_KINDS}
    for section, name, block in _split(text):
        if section in out:
            out[section][name] = block
    if any(_SECTION.match(ln) and ln.split()[1] == "RENAMED" for ln in _lines(text)):
        out["RENAMED"]["<section>"] = ""
    return out


def _active_changes(changes_dir: Path, capability: str) -> list[tuple[str, Path]]:
    found = []
    for change in sorted(changes_dir.iterdir()):
        if not change.is_dir() or change.name == "archive":
            continue
        delta = change / "specs" / capability / "spec.md"
        if delta.is_file():
            found.append((change.name, delta))
    return found


Variants = list[tuple[str, str | None]]  # (source, block); a None block means REMOVED


def effective_spec(
    capability: str, *, specs_dir: Path | None = None, changes_dir: Path | None = None
) -> dict[str, Variants]:
    """Requirement name → its variants after applying every active change's delta.

    ``source`` is ``"live"`` or the change directory's name. A requirement modified or removed by
    two active changes keeps both variants; :func:`effective_block` refuses to pick one.

    Raises:
        ValueError: a MODIFIED/REMOVED name absent from the live spec, or an ADDED name already
            present (live or added by another change). The message names change and requirement.
        NotImplementedError: a delta has a RENAMED section.
    """
    specs_dir = SPECS_DIR if specs_dir is None else specs_dir
    changes_dir = CHANGES_DIR if changes_dir is None else changes_dir
    live = requirement_blocks(
        (specs_dir / capability / "spec.md").read_text(encoding="utf-8")
    )
    touched: dict[str, Variants] = {}
    added: dict[str, Variants] = {}
    for change, path in _active_changes(changes_dir, capability):
        sections = delta_sections(path.read_text(encoding="utf-8"))
        if sections["RENAMED"]:
            raise NotImplementedError(
                f"{change}: RENAMED requirements are not supported by the spec guard"
            )
        for kind, block_of in (("MODIFIED", lambda b: b), ("REMOVED", lambda b: None)):
            for name, block in sections[kind].items():
                if name not in live:
                    raise ValueError(
                        f"{change}: {kind} requirement {name!r} is absent from the live "
                        f"{capability} spec"
                    )
                touched.setdefault(name, []).append((change, block_of(block)))
        for name, block in sections["ADDED"].items():
            if name in live or name in added:
                raise ValueError(
                    f"{change}: ADDED requirement {name!r} is already present in {capability}"
                )
            added[name] = [(change, block)]
    result: dict[str, Variants] = {}
    for name, block in live.items():
        variants = touched.get(name, [("live", block)])
        if all(b is None for _, b in variants) and len(variants) == 1:
            continue  # removed by exactly one change
        result[name] = variants
    result.update(added)
    return result


def effective_text(capability: str, **paths: Path | None) -> str:
    """Every block variant of the effective spec, joined, for a whole-spec scan."""
    eff = effective_spec(capability, **paths)
    return "\n\n".join(b for variants in eff.values() for _, b in variants if b)


def effective_block(capability: str, name: str, **paths: Path | None) -> str:
    """The one effective block of ``name``, for a per-number check.

    Raises:
        KeyError: no such requirement (a stale ``GUARDED`` / ``REGISTRY`` entry).
        ValueError: more than one active change touches it.
    """
    eff = effective_spec(capability, **paths)
    if name not in eff:
        raise KeyError(
            f"{capability}: requirement {name!r} is not in the effective spec; "
            "update GUARDED/REGISTRY in tests/test_live_spec_claims.py"
        )
    variants = eff[name]
    if len(variants) > 1:
        sources = ", ".join(src for src, _ in variants)
        raise ValueError(
            f"{capability}: requirement {name!r} is modified by more than one active change "
            f"({sources}); the second to merge must reconcile it before its numbers can be "
            "checked"
        )
    ((_, block),) = variants
    if block is None:
        raise KeyError(f"{capability}: requirement {name!r} is removed by its change")
    return block


# --------------------------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------------------------

_CC_REF = re.compile(r"\bCC-\d+")
_GRID_JOIN = re.compile(r"(?<=\d)[x×](?=\d)")
_TOKEN = re.compile(r"(?<![A-Za-z_#.\d])\d+(?:[.,]\d+)*(?:e[-+]?\d+)?(?!\d)", re.ASCII)
_SUPERSCRIPT = re.compile(r"\d[⁰¹²³⁴-⁹⁻⁺]")


def number_tokens(text: str) -> list[str]:
    """Every number in ``text``, as written (design D4).

    Identifiers (``s45_f115_p60``, ``sha256``), issue references (``#115``), design references
    (``D6``) and ``CC-<n>`` are skipped; a grid ``256x128x256`` gives each dimension. Digits are
    ASCII only. Tokens are sign-blind.
    """
    text = _GRID_JOIN.sub(" × ", _CC_REF.sub(" ", text))
    return _TOKEN.findall(text)


def superscripts_after_digits(text: str) -> list[str]:
    """Each digit followed by a superscript digit or sign (a ``×10ⁿ`` exponent)."""
    return _SUPERSCRIPT.findall(text)


def format_like(value: float, literal: str) -> str:
    """``value`` rendered in ``literal``'s notation: decimals, comma grouping or e-notation."""
    if "e" in literal:
        mantissa = literal.split("e")[0]
        digits = len(mantissa.split(".")[1]) if "." in mantissa else 0
        m, exp = f"{value:.{digits}e}".split("e")
        return f"{m}e{int(exp)}"
    digits = len(literal.split(".")[1]) if "." in literal else 0
    grouping = "," if "," in literal else ""
    return f"{value:{grouping}.{digits}f}"


@dataclass(frozen=True)
class Entry:
    """One registered number: ``literal`` inside ``phrase``.

    ``kind`` is ``recomputed`` or ``fixture`` (``source`` is a callable returning the value) or
    ``declared`` (``source`` is the reason it is not a measured result).
    """

    phrase: str
    literal: str
    kind: str
    source: Callable[[], float] | str
    count: int = 1


def _collapse(text: str) -> str:
    return " ".join(text.split())


def check_block(
    name: str, text: str, entries: list[Entry] | tuple[Entry, ...]
) -> list[str]:
    """Failure messages for ``text`` against ``entries`` (empty when every number is accounted for)."""
    flat = _collapse(text)
    failures = []
    have = Counter(number_tokens(flat))
    want: Counter[str] = Counter()
    for e in entries:
        want[e.literal] += e.count
    for tok, n in (have - want).items():
        failures.append(f"{name}: unregistered number {tok!r} (x{n}) in the text")
    for tok, n in (want - have).items():
        failures.append(f"{name}: registered number {tok!r} (x{n}) is not in the text")
    for sup in superscripts_after_digits(flat):
        failures.append(
            f"{name}: superscript exponent {sup!r} hides an order of magnitude"
        )
    for e in entries:
        phrase = _collapse(e.phrase)
        if phrase not in flat:
            failures.append(
                f"{name}: phrase {phrase!r} (for {e.literal!r}) is not in the text"
            )
        if e.literal not in number_tokens(phrase):
            failures.append(f"{name}: phrase {phrase!r} does not contain {e.literal!r}")
        if e.kind in ("recomputed", "fixture"):
            assert callable(e.source), e
            value = e.source()
            if value < 0:
                failures.append(
                    f"{name}: {e.kind} source for {e.literal!r} is negative"
                )
            got = format_like(value, e.literal)
            if got != e.literal:
                failures.append(
                    f"{name}: {e.kind} number {e.literal!r} in phrase {phrase!r} now "
                    f"prints as {got!r}"
                )
        elif e.kind == "declared":
            if not (isinstance(e.source, str) and e.source.strip()):
                failures.append(f"{name}: declared {e.literal!r} has no reason")
        else:
            failures.append(f"{name}: unknown kind {e.kind!r} for {e.literal!r}")
    return failures


# --------------------------------------------------------------------------------------------
# Retired claims
# --------------------------------------------------------------------------------------------


def retired_hits(
    text: str, patterns: dict[str, re.Pattern[str]], label: str
) -> list[str]:
    """One message per retired pattern found in ``normalize(text)``, naming pattern and file."""
    flat = normalize(text)
    hits = []
    for pname, pattern in patterns.items():
        m = pattern.search(flat)
        if m:
            start = max(0, m.start() - 60)
            hits.append(
                f"{label}: retired claim [{pname}]: …{flat[start : m.end() + 60]}…"
            )
    return hits
