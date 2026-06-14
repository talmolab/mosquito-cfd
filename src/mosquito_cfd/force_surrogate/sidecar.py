"""Sidecar conventions for force-surrogate artifacts: units.json + run provenance.

``units.json`` declares the (dimensionless) unit of each dataset column, validated on both
write and read against :data:`UNITS_VOCABULARY` (CC-5). Run provenance reuses
:func:`mosquito_cfd.benchmarks.metadata.capture_run_metadata`, additionally requiring a
Docker image digest and allowing a caller-supplied timestamp so artifacts are reproducible
rather than wall-clock-stamped (CC-1).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mosquito_cfd.benchmarks.metadata import capture_run_metadata

# Allowed dimensionless units (CC-5). The validated pipeline is dimensionless; a physical
# SI mapping, if ever needed, is a downstream concern.
UNITS_VOCABULARY: frozenset[str] = frozenset(
    {
        "dimensionless",
        "deg",
        "dimensionless (f*)",
    }
)

# A content-addressable image digest: `sha256:` + 64 lowercase hex chars, optionally
# prefixed by a registry/repo (e.g. `ghcr.io/org/img@sha256:<64hex>`).
_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _validate_units(units: object) -> None:
    """Validate a units mapping against UNITS_VOCABULARY (shared by write and read)."""
    if not isinstance(units, dict):
        raise ValueError(f"units must be a mapping, got {type(units).__name__}")
    for column, unit in units.items():
        if not isinstance(column, str):
            raise ValueError(
                f"column name must be a string, got {column!r} "
                f"({type(column).__name__}); non-string keys do not round-trip through JSON"
            )
        if not isinstance(unit, str):
            raise ValueError(
                f"unit for column {column!r} must be a string, got "
                f"{unit!r} ({type(unit).__name__})"
            )
        if unit not in UNITS_VOCABULARY:
            raise ValueError(
                f"column {column!r} has unit {unit!r} not in UNITS_VOCABULARY "
                f"{sorted(UNITS_VOCABULARY)}"
            )


def write_units_sidecar(path: Path, units: dict[str, str]) -> None:
    """Write a ``units.json`` sidecar, validating against :data:`UNITS_VOCABULARY`.

    Args:
        path: Output path for the JSON sidecar.
        units: Mapping of column name to unit string.

    Raises:
        ValueError: If any unit is not in :data:`UNITS_VOCABULARY`.
    """
    _validate_units(units)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" disables platform line-ending translation so the sidecar is LF on every
    # OS (Windows included) and therefore byte-reproducible for committed artifacts.
    with open(path, "w", encoding="utf-8", newline="") as f:
        json.dump(units, f, indent=2, ensure_ascii=False)


def read_units_sidecar(path: Path) -> dict[str, str]:
    """Read and validate a ``units.json`` sidecar.

    Args:
        path: Path to the JSON sidecar.

    Returns:
        The column-to-unit mapping.

    Raises:
        ValueError: If the file is not valid JSON, is not a JSON object, or contains a
            unit not in :data:`UNITS_VOCABULARY` (read enforces the same vocabulary as
            write).
    """
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    _validate_units(data)
    return data


def validate_image_digest(docker_image_digest: str) -> str:
    """Validate (no I/O) that a string is a content-addressable image digest, and return it.

    Pure regex guard, separable from :func:`capture_surrogate_run_metadata` so a caller can
    fail-fast on a mutable/missing digest **without** paying the git/hardware probe that the
    full capture performs (CC-1).

    Args:
        docker_image_digest: Candidate image reference; must contain ``sha256:``. Surrounding
            whitespace is stripped.

    Returns:
        The stripped digest.

    Raises:
        ValueError: If the value is empty, blank, or not a content-addressable digest.
    """
    digest = (docker_image_digest or "").strip()
    if not _DIGEST_RE.search(digest):
        raise ValueError(
            "docker_image_digest must be a content-addressable image digest of the form "
            "'sha256:<64 hex chars>' (e.g. 'ghcr.io/talmolab/mosquito-cfd@sha256:...'); a "
            f"mutable tag like ':latest' is not reproducible. Got {docker_image_digest!r}"
        )
    return digest


def capture_surrogate_run_metadata(
    *,
    docker_image_digest: str,
    inputs_file: Path | None = None,
    timestamp: str | None = None,
    timing: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture run provenance for a force-surrogate artifact.

    Wraps :func:`mosquito_cfd.benchmarks.metadata.capture_run_metadata`, additionally
    requiring a Docker image digest (so runs are pinned to a content-addressable image,
    not a mutable tag) and allowing a caller-supplied timestamp for reproducibility
    (CC-1). The base function has no ``timestamp`` parameter and stamps
    ``datetime.now(UTC)``, so the caller value is applied by overriding the returned
    dict's ``timestamp``.

    Args:
        docker_image_digest: Content-addressable pinned image reference; must contain
            ``sha256:`` (e.g. ``ghcr.io/talmolab/mosquito-cfd@sha256:...``). Surrounding
            whitespace is stripped. A mutable tag (``:latest``) is rejected.
        inputs_file: Optional inputs file; its SHA256 is recorded under ``inputs.hash``
            when the file exists.
        timestamp: Optional caller-supplied ISO-8601 timestamp; overrides the wall-clock
            timestamp.
        timing: Optional timing dict.
        extra: Optional extra metadata merged into the result.

    Returns:
        Metadata dict including ``git``, ``hardware``, ``docker_image`` (the digest), and
        (when ``inputs_file`` exists) ``inputs.hash``.

    Raises:
        ValueError: If ``docker_image_digest`` is empty, blank, or not a content-
            addressable digest (does not contain ``sha256:``).
    """
    digest = validate_image_digest(docker_image_digest)
    metadata = capture_run_metadata(
        inputs_file=inputs_file,
        docker_image=digest,
        timing=timing,
        extra=extra,
    )
    if timestamp is not None:
        metadata["timestamp"] = timestamp
    return metadata
