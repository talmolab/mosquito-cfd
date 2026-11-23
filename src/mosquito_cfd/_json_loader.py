"""The labelled JSON loader shared by the force surrogate and the sweep-manifest reader.

Standard library only, by contract (harden-json-loader, #175): ``mosquito_cfd._manifest`` loads
through it, and that module must stay light enough for every training data-loader worker to
import. Being a leaf module (no ``mosquito_cfd`` imports at all) also lets
``force_surrogate.metadata_capture`` and ``force_surrogate.dataset`` share it without a circular
import -- ``dataset`` is imported by ``runner``, which is imported by ``metadata_capture``.
``mosquito_cfd.force_surrogate.sidecar`` re-exports :func:`load_json_clear_error` as the same
object, so its callers are unchanged.

Every rejection of a file's *contents* (not UTF-8, not JSON, optionally not a JSON object) is
exactly a ``ValueError`` naming the label and path. Errors opening the path are not wrapped: a
missing file stays ``FileNotFoundError``, and any other ``OSError`` (a directory, a permission
error) escapes as raised.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_json_clear_error(
    path: Path | str, *, label: str, require_object: bool = True
) -> Any:
    """Load JSON from ``path``, labelling every content failure with ``label`` and the path.

    Args:
        path: The JSON file.
        label: What the file is, for the message (e.g. ``"sweep manifest"``).
        require_object: If true (the default), reject a top level that is not a JSON object.
            If false, return any JSON value unchecked.

    Returns:
        The parsed JSON value: a ``dict`` when ``require_object`` is true.

    Raises:
        FileNotFoundError: If ``path`` does not exist. (Any other ``OSError`` from opening it is
            raised unwrapped.)
        ValueError: Exactly ``ValueError``, if the file is not valid UTF-8 (raised from the
            ``UnicodeDecodeError``); if ``json.loads`` refuses it with ``ValueError`` or
            ``RecursionError`` -- malformed or empty, a leading byte-order mark, an integer beyond
            Python's digit limit, nesting beyond the recursion limit (raised from that error);
            or, when ``require_object`` is true, if its top level is not a JSON object.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} {path} is not valid UTF-8: {exc}") from exc
    try:
        data = json.loads(text)
    except (ValueError, RecursionError) as exc:
        # JSONDecodeError is a ValueError; so is the int-digit limit, and deep nesting raises
        # RecursionError -- all are "not valid JSON".
        raise ValueError(f"{label} {path} is not valid JSON: {exc}") from exc
    if require_object and not isinstance(data, dict):
        raise ValueError(
            f"{label} {path} top level is a {type(data).__name__}, not an object"
        )
    return data
