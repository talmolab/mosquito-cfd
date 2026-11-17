"""Stale-claim guard for documents that mention the T4 result (design D13).

The corrected van Veen model no longer supports several statements the docs used to make: that T4
resolves the chord PARTIAL (#40), that the CFD chord sits close to or converges to the model, and
a set of superseded model numbers. :func:`stale_claims` finds those statements in a document.

It is a tripwire, not proof. It splits the text into sentences and skips the *claim* patterns in
any sentence that carries a negation, because the docs are required to say "T4 does not resolve
the chord PARTIAL". Known costs: "T4 resolves the chord PARTIAL, not the normal" passes; and the
number patterns reject those digits with any meaning.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize

_NEGATION = re.compile(
    r"\b(not|never|neither|nor|cannot|no)\b|n't|\bun(resolved|explained)"
)

# (name, pattern, companion): rejected in a sentence without a negation. With a companion, both
# must occur in the same sentence.
_CLAIMS: tuple[tuple[str, re.Pattern[str], re.Pattern[str] | None], ...] = (
    # "under-resolves" and "under-resolution" are about the grid, as is "resolution" unless it is
    # "the resolution of" something, so those forms are left alone.
    (
        "T4 resolves the chord PARTIAL",
        re.compile(r"(?<![-\w])resolv\w*|(?<![-\w])resolution\W+of\b"),
        re.compile(r"t4|#40|partial"),
    ),
    (
        "the model explains the chord",
        re.compile(r"explain\w*|accounts?\W+for|settle[sd]?"),
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
        re.compile(r"(pending|awaiting).{0,20}#133|#133.{0,20}(pending|awaiting)"),
    ),
    (
        "#40 closed",
        re.compile(r"#40\W+(is\W+|remains\W+|was\W+)?(closed|resolved|done)"),
    ),
    ("closing #40", re.compile(r"clos\w+\W+#40")),
    # "never" is part of this phrase, so it cannot sit with the negation-skipped claims.
    (
        "should never have been compared",
        re.compile(r"should\W+never\W+have\W+been\W+compared"),
    ),
    ("roughly cancel", re.compile(r"roughly\W+cancel")),
    ("full QS model total", re.compile(r"full qs model total")),
    ("near 0.18", re.compile(r"near 0\.18")),
    ("0.3-0.43 chord range", re.compile(r"0\.3\s*(–|—|-|to)\s*0\.43")),
    ("115 %", re.compile(r"\+?115\s?%")),
    ("4-5 %", re.compile(r"(?<![\d.])4\s?(–|—|-|to)\s?5\s?%")),
    ("2.48", re.compile(r"(?<![\d.])2\.48(?!\d)")),
    ("0.43", re.compile(r"(?<![\d.])0\.43(?!\d)")),
    ("0.42", re.compile(r"(?<![−\-\d.])0\.42(?!\d)")),
    ("0.055 / 0.058", re.compile(r"(?<![\d.])0\.05[58](?!\d)")),
)


def normalize(text: str) -> str:
    """Drop Markdown emphasis and code marks, collapse all whitespace, lower-case."""
    return " ".join(re.sub(r"[*_`]", "", text).split()).lower()


def sentences(text: str) -> list[str]:
    """Sentences of the normalized text: split after ``.``, ``;``, ``!`` or ``?`` plus a space."""
    return [s for s in re.split(r"(?<=[.;!?]) ", normalize(text)) if s]


def stale_claims(text: str) -> list[tuple[str, str]]:
    """``(pattern name, sentence)`` for every stale claim found in ``text``."""
    hits: list[tuple[str, str]] = []
    for sentence in sentences(text):
        for name, pattern in _ALWAYS:
            if pattern.search(sentence):
                hits.append((name, sentence))
        if _NEGATION.search(sentence):
            continue
        for name, pattern, companion in _CLAIMS:
            if pattern.search(sentence) and (
                companion is None or companion.search(sentence)
            ):
                hits.append((name, sentence))
    return hits


def python_prose(source: str) -> str:
    """Comments and docstrings of a Python source file, as one text.

    Consecutive comment lines are joined, so a sentence wrapped over several lines is one
    sentence here too.
    """
    comments = [
        tok.string.lstrip("#").strip()
        for tok in tokenize.generate_tokens(io.StringIO(source).readline)
        if tok.type == tokenize.COMMENT
    ]
    tree = ast.parse(source)
    docstrings = [
        ast.get_docstring(node) or ""
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        )
    ]
    return " ".join(comments) + " . " + " . ".join(docstrings)
