"""Sidecar conventions for force-surrogate artifacts: units.json + run provenance.

``units.json`` declares the (dimensionless) unit of each dataset column, validated on both
write and read against :data:`UNITS_VOCABULARY` (CC-5). Run provenance reuses
:func:`mosquito_cfd.benchmarks.metadata.capture_run_metadata`, additionally requiring a
digest-pinned Docker image reference and allowing a caller-supplied timestamp so artifacts are
reproducible rather than wall-clock-stamped (CC-1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Re-exported (redundant alias marks it explicit): the loader moved to the stdlib-only
# mosquito_cfd._json_loader so mosquito_cfd._manifest can share it (harden-json-loader, #175).
from mosquito_cfd._json_loader import load_json_clear_error as load_json_clear_error
from mosquito_cfd._provenance import is_pinned_image_ref
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
        ValueError: If the file is not valid UTF-8, not valid JSON or not a JSON object
            (exactly ``ValueError``, labelled ``units sidecar <path>`` by
            :func:`mosquito_cfd._json_loader.load_json_clear_error`), or contains a unit not in
            :data:`UNITS_VOCABULARY` (read enforces the same vocabulary as write). Errors
            opening the path are not wrapped.
    """
    data = load_json_clear_error(path, label="units sidecar")
    _validate_units(data)
    return data


def validate_image_digest(docker_image_digest: object) -> str:
    """Validate (no I/O) that a value is a digest-pinned image reference, and return it unchanged.

    Pure guard, separable from :func:`capture_surrogate_run_metadata` so a caller can fail fast on
    a mutable or missing digest **without** paying the git/hardware probe that the full capture
    performs (CC-1). The rule is the shared
    :func:`mosquito_cfd._provenance.is_pinned_image_ref` (share-light-corpus-helpers, #159).

    Args:
        docker_image_digest: Candidate image reference, ``<repo>@sha256:<64 hex>`` (e.g.
            ``ghcr.io/talmolab/mosquito-cfd@sha256:...``; ``<repo>:<tag>@sha256:<64 hex>`` also
            passes). Nothing is stripped or normalized.

    Returns:
        The value, exactly as given.

    Raises:
        ValueError: For any other value, whatever its type: a mutable tag, a bare
            ``sha256:<hex>`` digest, text or whitespace around the reference, a wrong-length or
            uppercase digest, or a non-string. The message ends with the value's ``repr``.
    """
    if not is_pinned_image_ref(docker_image_digest):
        raise ValueError(
            "docker_image_digest must be a content-addressable, digest-pinned image reference "
            "of the form '<repo>@sha256:<64 hex>' (e.g. "
            "'ghcr.io/talmolab/mosquito-cfd@sha256:...'); a mutable tag like ':latest' or a "
            f"bare 'sha256:...' digest is not accepted. Got {docker_image_digest!r}"
        )
    return docker_image_digest


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
    requiring a digest-pinned Docker image reference (so runs are pinned to a
    content-addressable image, not a mutable tag) and allowing a caller-supplied timestamp for
    reproducibility
    (CC-1). The base function has no ``timestamp`` parameter and stamps
    ``datetime.now(UTC)``, so the caller value is applied by overriding the returned
    dict's ``timestamp``.

    Args:
        docker_image_digest: Digest-pinned image reference, ``<repo>@sha256:<64 hex>`` (e.g.
            ``ghcr.io/talmolab/mosquito-cfd@sha256:...``), recorded exactly as given. A mutable
            tag (``:latest``) or a bare ``sha256:`` digest is rejected; see
            :func:`validate_image_digest`.
        inputs_file: Optional inputs file; its SHA256 is recorded under ``inputs.hash``
            when the file exists.
        timestamp: Optional caller-supplied ISO-8601 timestamp; overrides the wall-clock
            timestamp.
        timing: Optional timing dict.
        extra: Optional extra metadata merged into the result.

    Returns:
        Metadata dict including ``git``, ``hardware``, ``docker_image`` (the reference,
        unchanged), and (when ``inputs_file`` exists) ``inputs.hash``.

    Raises:
        ValueError: If ``docker_image_digest`` is not a digest-pinned image reference (see
            :func:`validate_image_digest`).
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
