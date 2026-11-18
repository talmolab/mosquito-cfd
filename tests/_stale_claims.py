"""Stale-claim guard for documents that mention the T4 result (design D13).

The corrected van Veen model no longer supports several statements the docs used to make: that T4
resolves the chord PARTIAL (#40), that the CFD chord sits close to or converges to the model, and
a set of superseded model numbers. :func:`stale_claims` finds those statements in a document.

It is a tripwire, not proof. It reads a document at two widths:

- **Narrow, for the negation test.** The text is cut into blocks (a heading, a list item, a table
  cell and a paragraph are each their own), and each block into clauses (after ``.``, ``;``,
  ``:``, ``!`` or ``?``). A *claim* pattern is excused only by a negation that comes **before**
  it in the same clause, because the docs are required to say "T4 does not resolve the chord
  PARTIAL". A "not" in a neighbouring cell, bullet or heading excuses nothing, and neither does
  one after the claim ("T4 resolves it, so #40 is no longer blocking").
- **Wide, for what the claim is about.** A claim's companion word (T4, #40, PARTIAL, chord) and
  the always-rejected phrases are looked for over the whole sentence (colons not split) or the
  whole table row. So ``| #40 | resolved |`` and ``#40: closed`` are found. Markdown links are
  reduced to their text first, so ``[#40](url) is closed`` is found too.

Known costs.

- It fails closed on some true sentences: "Whether T4 resolves the chord PARTIAL is not known",
  "T4 fails to resolve it", and any un-negated "resolved" / "explained" / "settled" / "accounts
  for" in a sentence or table row that also names T4, #40, PARTIAL or the chord. Reword with the
  negation first, or split the sentence.
- It does not connect a claim to a heading, label line or parent list item above it: "Resolved."
  under a "### #40" heading is missed. An earlier version tried; it reached only the first block
  after the label, and it rejected true sentences across the join. The misses are pinned in the
  tests.
- It misses a claim excused by an unrelated earlier negation in the same clause ("No doubt T4
  resolves ..."), a claim worded with none of the listed verbs ("agrees", "matches"), a claim
  split over two sentences ("Issue #40. Resolved."), setext headings and tables without a
  leading pipe.
- The number patterns reject those digits with any meaning.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

_NEGATION = re.compile(
    r"\b(not|never|neither|nor|cannot|no)\b|n['’]t\b|\bun(resolved|explained)"
)

# (name, pattern, companion): rejected unless a negation precedes the match in its clause.
# With a companion, the companion must occur in the wide unit around the clause.
_CLAIMS: tuple[tuple[str, re.Pattern[str], re.Pattern[str] | None], ...] = (
    # "under-resolves" and "under-resolution" are about the grid, as is "resolution" unless it is
    # "the resolution of" something, so those forms are left alone. So is "unresolved".
    (
        "T4 resolves the chord PARTIAL",
        re.compile(r"(?<![-\w])resolv\w*|(?<![-\w])resolution\W+of\b"),
        # No leading \b on "partial": normalize() strips underscores, so CF_chord_PARTIAL
        # arrives as "cfchordpartial".
        re.compile(r"\bt4\b|#40(?!\d)|partial\b"),
    ),
    (
        "the model explains the chord",
        re.compile(r"(?<![-\w])explain\w*|\baccounts?\W+for\b|(?<![-\w])settle[sd]?\b"),
        re.compile(r"chord"),
    ),
    (
        "chord sits close to the model",
        re.compile(r"sits\W+(very\W+)?close\W+to\W+the\W+model"),
        None,
    ),
    ("close agreement", re.compile(r"close\W+agreement"), None),
    (
        "converges to the model",
        re.compile(r"converges?\W+to(ward)?\W+the\W+(qs\W+)?model"),
        None,
    ),
    ("apples-to-oranges", re.compile(r"apples-to-oranges"), None),
    ("physical chord target", re.compile(r"physical\W+chord\W+target"), None),
    ("QS-model target", re.compile(r"qs-?model\W+(chord\W+)?target"), None),
)

# Rejected in every sentence, negated or not.
_ALWAYS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "pending #133",
        re.compile(
            r"(pending|awaiting).{0,20}#133(?!\d)|#133(?!\d).{0,20}(pending|awaiting)"
        ),
    ),
    (
        "#40 closed",
        re.compile(r"#40(?!\d)\W+(is\W+|remains\W+|was\W+)?(closed|resolved|done)\b"),
    ),
    ("closing #40", re.compile(r"\bclos\w+\W+#40(?!\d)")),
    # "never" is part of this phrase, so it cannot sit with the negation-skipped claims.
    (
        "should never have been compared",
        re.compile(r"should\W+never\W+have\W+been\W+compared"),
    ),
    ("roughly cancel", re.compile(r"roughly\W+cancel")),
    ("full QS model total", re.compile(r"full qs model total")),
    ("near 0.18", re.compile(r"near 0\.18(?!\d)")),
    ("0.3-0.43 chord range", re.compile(r"0\.3\s*(–|—|-|to)\s*0\.43(?!\d)")),
    ("115 %", re.compile(r"(?<![\d.])115\s?%")),
    ("4-5 %", re.compile(r"(?<![\d.])4\s?(–|—|-|to)\s?5\s?%")),
    ("2.48", re.compile(r"(?<![\d.])2\.48(?!\d)")),
    ("0.43", re.compile(r"(?<![\d.])0\.43(?!\d)")),
    ("0.42", re.compile(r"(?<![−\-\d.])0\.42(?!\d)")),
    ("0.055 / 0.058", re.compile(r"(?<![\d.])0\.05[58](?!\d)")),
)

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s")
_LIST_ITEM = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_TABLE_ROW = re.compile(r"^\s*\|")
# A sentence ends at . ; ! or ?, optionally followed by a closing bracket or quote, then a space.
# A clause also ends at a colon.
_SENTENCE_END = re.compile(r"(?<=[.;!?])[)\]\"'’”]*\s+")
_CLAUSE_END = re.compile(r"(?<=[.;:!?])[)\]\"'’”]*\s+")


_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")


def normalize(text: str) -> str:
    """Reduce links to their text, drop emphasis and code marks, collapse whitespace, lower-case."""
    text = _LINK.sub(r"\1", text)
    return " ".join(re.sub(r"[*_`]", "", text).split()).lower()


def blocks(text: str) -> list[str]:
    """Structural blocks of a Markdown text.

    A heading, a list item, a table row and a paragraph are separate blocks; a wrapped paragraph
    or list item is one block. Blockquote markers are dropped first.
    """
    out: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            out.append(" ".join(current))
            current.clear()

    for raw in text.splitlines():
        line = re.sub(r"^\s*(>\s?)+", "", raw)
        if not line.strip():
            flush()
        elif _HEADING.match(line) or _TABLE_ROW.match(line):
            flush()
            out.append(line)
        elif _LIST_ITEM.match(line):
            flush()
            current.append(line)
        else:
            current.append(line)
    flush()
    return out


def units(text: str) -> list[tuple[str, list[str]]]:
    """``(wide, clauses)`` pairs: the wide unit and the narrow clauses inside it.

    For a table row the wide unit is the row and the clauses come from each cell. For other
    blocks the wide unit is a sentence (split after ``.``, ``;``, ``!`` or ``?``) and the clauses
    are its parts between colons.
    """
    result: list[tuple[str, list[str]]] = []
    for block in blocks(text):
        if _TABLE_ROW.match(block):
            clauses = [
                clause
                for cell in block.split("|")
                for clause in _CLAUSE_END.split(normalize(cell))
                if clause
            ]
            result.append((normalize(block), clauses))
        else:
            for sentence in _SENTENCE_END.split(normalize(block)):
                if sentence:
                    result.append(
                        (sentence, [c for c in _CLAUSE_END.split(sentence) if c])
                    )
    return result


def _negated_before(clause: str, position: int) -> bool:
    return _NEGATION.search(clause[:position]) is not None


def stale_claims(text: str) -> list[tuple[str, str]]:
    """``(pattern name, wide unit)`` for every stale claim found in ``text``."""
    hits: list[tuple[str, str]] = []
    for wide, clauses in units(text):
        for name, pattern in _ALWAYS:
            if pattern.search(wide):
                hits.append((name, wide))
        for name, pattern, companion in _CLAIMS:
            if companion is not None and not companion.search(wide):
                continue
            if any(
                not _negated_before(clause, m.start())
                for clause in clauses
                for m in pattern.finditer(clause)
            ):
                hits.append((name, wide))
    return hits


def python_prose(source: str) -> str:
    """Comments and docstrings of a Python source file, as blank-line-separated blocks.

    Comment lines on consecutive source lines form one block, so a sentence wrapped over several
    comment lines is read whole, while unrelated comments elsewhere in the file stay separate.
    """
    groups: list[list[str]] = []
    last_line = None
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type != tokenize.COMMENT:
            continue
        line = tok.start[0]
        if last_line is None or line != last_line + 1:
            groups.append([])
        groups[-1].append(tok.string.lstrip("#").strip())
        last_line = line
    tree = ast.parse(source)
    docstrings = [
        ast.get_docstring(node) or ""
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
    ]
    return "\n\n".join([" ".join(g) for g in groups] + docstrings)
