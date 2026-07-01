"""Guard the IAMReX commit pin against drift between build-args.env and Dockerfile.fp64 (T2a).

The ``:fp64`` image clones IAMReX at ``IAMREX_COMMIT``, pinned in BOTH ``docker/build-args.env`` and
``docker/Dockerfile.fp64`` (the ARG default). They MUST match — a documented footgun (MEMORY.md). This
cheap cluster-free test catches a mismatch before an image build silently uses the wrong commit.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_PIN_RE = re.compile(
    r"^\s*(?:ARG\s+)?IAMREX_COMMIT\s*=\s*([0-9a-f]{40})\b", re.MULTILINE
)
_BUILD_ARGS = Path("docker/build-args.env")
_DOCKERFILE = Path("docker/Dockerfile.fp64")


def _pin(path: Path) -> str:
    text = path.read_text()
    m = _PIN_RE.search(text)
    assert m is not None, (
        f"{path} has no IAMREX_COMMIT pinned to a full 40-hex SHA "
        f"(a truncated/abbreviated SHA would not be reproducible)"
    )
    return m.group(1)


@pytest.mark.skipif(
    not (_BUILD_ARGS.exists() and _DOCKERFILE.exists()),
    reason="docker pin files not present",
)
def test_iamrex_pin_consistent():
    """IAMREX_COMMIT in build-args.env equals the Dockerfile.fp64 ARG default (both full 40-hex)."""
    build_pin = _pin(_BUILD_ARGS)
    docker_pin = _pin(_DOCKERFILE)
    assert build_pin == docker_pin, (
        f"IAMREX_COMMIT mismatch: build-args.env={build_pin} vs "
        f"Dockerfile.fp64={docker_pin} — bump BOTH (they must match)"
    )
