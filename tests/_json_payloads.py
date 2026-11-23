"""Byte payloads every JSON loader must reject (OpenSpec change harden-json-loader, #175).

The six unparseable payloads are those of the force-surrogate spec scenario "Unparseable files are
labelled ValueErrors". :data:`FIVE` is the set the caller and drift tests use: deep nesting, the
integer digit limit, bytes that are not UTF-8, and the non-object top levels ``[]`` and ``5``.
"""

from __future__ import annotations

import json
import sys

# The digit-limit payload only fails if Python's int-string limit is on and below 5000 digits.
# Fail loudly here rather than letting the payload parse and a test fail confusingly.
assert 0 < sys.get_int_max_str_digits() < 5000, sys.get_int_max_str_digits()

DEEP_NESTING = b"[" * 100_000 + b"]" * 100_000
INT_DIGIT_LIMIT = b'{"a": ' + b"9" * 5000 + b"}"
NOT_UTF8 = b"\xff\xfe{"
MALFORMED = b"{"
EMPTY = b""
UTF8_BOM = b"\xef\xbb\xbf{}"
TOP_LEVEL_LIST = b"[]"
TOP_LEVEL_INT = b"5"

#: The six unparseable payloads, with the exact ``__cause__`` type and message prefix each must give.
UNPARSEABLE: dict[str, tuple[bytes, type[BaseException], str]] = {
    "deep_nesting": (DEEP_NESTING, RecursionError, "is not valid JSON: "),
    "int_digit_limit": (INT_DIGIT_LIMIT, ValueError, "is not valid JSON: "),
    "non_utf8": (NOT_UTF8, UnicodeDecodeError, "is not valid UTF-8: "),
    "malformed": (MALFORMED, json.JSONDecodeError, "is not valid JSON: "),
    "empty": (EMPTY, json.JSONDecodeError, "is not valid JSON: "),
    "utf8_bom": (UTF8_BOM, json.JSONDecodeError, "is not valid JSON: "),
}

#: The five payloads the caller tests and the drift test send through every loader.
FIVE: dict[str, bytes] = {
    "deep_nesting": DEEP_NESTING,
    "int_digit_limit": INT_DIGIT_LIMIT,
    "non_utf8": NOT_UTF8,
    "list": TOP_LEVEL_LIST,
    "int": TOP_LEVEL_INT,
}

#: The three of :data:`FIVE` that fail to parse (as opposed to parsing to a non-object).
UNPARSEABLE_THREE = ("deep_nesting", "int_digit_limit", "non_utf8")
