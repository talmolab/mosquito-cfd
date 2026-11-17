"""Strict, read-through validation of a corpus run's pod-side ``run_metadata.json``.

Standard library only, by contract: importing ``mosquito_cfd.force_surrogate`` loads pandas and
pyarrow and switches the process's matplotlib backend, which no provenance read should do
(harden-field-reader-pre-f3 D4). The force-surrogate validators are deliberately not reused: they
accept a trailing-newline commit and a tag-plus-digest image (#159).

Every error is a ``ValueError`` of exactly the form
``run_metadata for config <repr(config_id)> (<path>): <field>: <detail>``, where ``<field>`` is
``run_metadata.json`` (the file itself), ``config``, ``git``, ``git.commit`` or ``docker_image``.
Nothing is defaulted, stripped, inferred or fabricated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

#: A full 40-character lowercase commit SHA. Used with ``fullmatch``: ``^...$`` with ``match``
#: would accept a trailing newline.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

#: A digest-pinned image reference. Checks the ``@sha256:<64 hex>`` suffix and a non-empty
#: repository of lowercase reference characters; it does not parse the full OCI grammar.
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}")

_FILE = "run_metadata.json"


def _error(config_id: str, path: Path, field: str, detail: str) -> ValueError:
    return ValueError(
        f"run_metadata for config {config_id!r} ({path}): {field}: {detail}"
    )


def read_run_metadata(path: Path, *, config_id: str) -> dict[str, Any]:
    """Parse a run's ``run_metadata.json`` and return the JSON object unchanged.

    Args:
        path: The ``run_metadata.json`` file.
        config_id: The config the file is expected to describe (used in error messages).

    Returns:
        The parsed top-level JSON object, exactly as written.

    Raises:
        ValueError: If ``path`` is not a regular file, cannot be read or decoded, is not valid
            JSON, or its top level is not a JSON object. The field is ``run_metadata.json``.
    """
    path = Path(path)
    if not path.is_file():
        what = "is not a regular file" if path.exists() else "does not exist"
        raise _error(config_id, path, _FILE, f"{what}; every corpus run writes one")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise _error(config_id, path, _FILE, f"cannot be read: {exc}") from exc
    try:
        meta = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _error(config_id, path, _FILE, f"is not valid JSON: {exc}") from exc
    if not isinstance(meta, dict):
        raise _error(
            config_id,
            path,
            _FILE,
            f"top level is a {type(meta).__name__}, not an object",
        )
    return meta


def run_provenance(
    meta: dict[str, Any], *, config_id: str, path: Path
) -> tuple[str, str]:
    """Validate and return a run's ``(git_commit, docker_image)``, exactly as written.

    Args:
        meta: The parsed ``run_metadata.json`` object.
        config_id: The config the run directory belongs to; must equal ``meta["config"]``.
        path: The file ``meta`` came from (used in error messages).

    Returns:
        ``(git_commit, docker_image)``: the file's own strings, neither stripped nor rewritten.

    Raises:
        ValueError: If ``config`` is absent, not a string, or names another config; if ``git``
            is not an object; if ``git.commit`` is not a 40-character lowercase hex string; or if
            ``docker_image`` is not a ``<repo>@sha256:<64 hex>`` string.
    """
    path = Path(path)
    config = meta.get("config")
    if not isinstance(config, str):
        raise _error(config_id, path, "config", f"must be a string, got {config!r}")
    if config != config_id:
        # A file copied into the wrong run directory must not lend its digest to another run.
        raise _error(config_id, path, "config", f"names {config!r}, not {config_id!r}")

    git = meta.get("git")
    if not isinstance(git, dict):
        raise _error(config_id, path, "git", f"must be an object, got {git!r}")
    commit = git.get("commit")
    if not (isinstance(commit, str) and _COMMIT_RE.fullmatch(commit)):
        raise _error(
            config_id,
            path,
            "git.commit",
            f"must be a full 40-character lowercase hex SHA, got {commit!r}",
        )

    image = meta.get("docker_image")
    if not (isinstance(image, str) and _IMAGE_RE.fullmatch(image)):
        raise _error(
            config_id,
            path,
            "docker_image",
            f"must be a digest-pinned '<repo>@sha256:<64 hex>' reference, got {image!r}",
        )
    return commit, image
