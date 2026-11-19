"""Strict provenance rules, and read-through validation of a corpus run's ``run_metadata.json``.

Standard library only, by contract: importing ``mosquito_cfd.force_surrogate`` loads pandas and
pyarrow and switches the process's matplotlib backend, which no provenance read should do
(harden-field-reader-pre-f3 D4). The module lives at the top of ``mosquito_cfd`` so that
``field_surrogate``, ``force_surrogate`` and ``benchmarks`` share one definition of each rule
(share-light-corpus-helpers D2, #159): :func:`is_full_commit_sha` and :func:`is_pinned_image_ref`.
Both full-match (so a trailing newline, surrounding text or whitespace never pass) and are total:
any non-``str`` is simply ``False``. A ``<repo>:<tag>@sha256:<hex>`` reference is accepted, as OCI
resolves it by the digest.

Every error is a ``ValueError`` of exactly the form
``run_metadata for config <repr(config_id)> (<path>): <field>: <detail>``, where ``<field>`` is
``run_metadata.json`` (the file itself), ``config``, ``status``, ``run_id``, ``git``,
``git.commit``, ``git.dirty`` or ``docker_image``. Nothing is defaulted, stripped, inferred or
fabricated.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, TypeGuard

#: A full 40-character lowercase commit SHA. Use only through :func:`is_full_commit_sha`: with
#: ``match``, ``^...$`` would accept a trailing newline.
_COMMIT_RE = re.compile(r"[0-9a-f]{40}")

#: A digest-pinned image reference. Checks the ``@sha256:<64 hex>`` suffix and a non-empty
#: repository of lowercase reference characters; it does not parse the full OCI grammar. Use only
#: through :func:`is_pinned_image_ref`.
_IMAGE_RE = re.compile(r"[a-z0-9][a-z0-9._/:-]*@sha256:[0-9a-f]{64}")

#: The file every corpus pod writes into its run directory.
RUN_METADATA_FILENAME = "run_metadata.json"

#: The field tag for file-level errors (the file itself failed, not one of its keys).
_FILE = RUN_METADATA_FILENAME


def is_full_commit_sha(value: object) -> TypeGuard[str]:
    """Whether ``value`` is a ``str`` that fully matches ``[0-9a-f]{40}``.

    Total: never raises. A trailing newline, surrounding whitespace, uppercase hex, a short SHA,
    and any non-``str`` (``bytes`` included) are all ``False``.
    """
    return isinstance(value, str) and _COMMIT_RE.fullmatch(value) is not None


def is_pinned_image_ref(value: object) -> TypeGuard[str]:
    """Whether ``value`` is a ``str`` that fully matches ``<repo>@sha256:<64 lowercase hex>``.

    The repository is one or more lowercase reference characters (``[a-z0-9][a-z0-9._/:-]*``), so
    ``<repo>:<tag>@sha256:<hex>`` passes. Total: never raises. A bare ``sha256:<hex>``, a tag with
    a digest appended after other text, surrounding whitespace, and any non-``str`` are ``False``.
    """
    return isinstance(value, str) and _IMAGE_RE.fullmatch(value) is not None


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
    except (ValueError, RecursionError) as exc:
        # JSONDecodeError is a ValueError; so is the int-digit limit ("Exceeds the limit (4300
        # digits)"), and deep nesting raises RecursionError -- all are "not valid JSON" (D8.5).
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
) -> tuple[str, str, str]:
    """Validate and return a run's ``(git_commit, docker_image, run_id)``, exactly as written.

    Args:
        meta: The parsed ``run_metadata.json`` object.
        config_id: The config the run directory belongs to; must equal ``meta["config"]``.
        path: The file ``meta`` came from (used in error messages).

    Returns:
        ``(git_commit, docker_image, run_id)``: the file's own strings, neither stripped nor
        rewritten. ``git_commit`` is the mosquito-cfd repository commit the pod recorded, not
        the solver's; the solver build is pinned by the image digest.

    Raises:
        ValueError: If ``config`` is absent, not a string, or names another config; if
            ``status`` is not ``"completed"``; if ``run_id`` is not a non-blank string; if
            ``git`` is not an object; if ``git.commit`` is not a 40-character lowercase hex
            string; if ``git.dirty`` is present and not ``False``; or if ``docker_image`` is
            not a ``<repo>@sha256:<64 hex>`` string.
    """
    path = Path(path)
    config = meta.get("config")
    if not isinstance(config, str):
        raise _error(config_id, path, "config", f"must be a string, got {config!r}")
    if config != config_id:
        # A file copied into the wrong run directory must not lend its digest to another run.
        raise _error(config_id, path, "config", f"names {config!r}, not {config_id!r}")

    status = meta.get("status")
    if status != "completed":
        # A failed or incomplete run's late plotfiles may be unphysical (design D8.2).
        raise _error(config_id, path, "status", f"must be 'completed', got {status!r}")

    run_id = meta.get("run_id")
    if not (isinstance(run_id, str) and run_id.strip()):
        raise _error(
            config_id, path, "run_id", f"must be a non-blank string, got {run_id!r}"
        )

    git = meta.get("git")
    if not isinstance(git, dict):
        raise _error(config_id, path, "git", f"must be an object, got {git!r}")
    commit = git.get("commit")
    if not is_full_commit_sha(commit):
        raise _error(
            config_id,
            path,
            "git.commit",
            f"must be a full 40-character lowercase hex SHA, got {commit!r}",
        )
    if "dirty" in git and git["dirty"] is not False:
        # A dirty tree means the named commit did not produce the code that ran (D8.2).
        raise _error(
            config_id,
            path,
            "git.dirty",
            f"must be false when present, got {git['dirty']!r}",
        )

    image = meta.get("docker_image")
    if not is_pinned_image_ref(image):
        raise _error(
            config_id,
            path,
            "docker_image",
            f"must be a digest-pinned '<repo>@sha256:<64 hex>' reference, got {image!r}",
        )
    return commit, image, run_id
