"""Refuse any plotfile that is not from the committed ns.cfl = 0.6 fine-corpus run."""

from __future__ import annotations

import re
from pathlib import Path

REQUIRED = {"ns.cfl": "0.6", "ns.fixed_dt": "0.0005", "amr.n_cell": "256 128 256"}
IAMR_HASH = "f93dc794"
DT = 5e-4
N_FIELDS_LINE = 1  # Header: version, n_fields, names..., dim, time


class ProvenanceError(RuntimeError):
    pass


def header_time(plt: Path) -> float:
    lines = (plt / "Header").read_text().splitlines()
    n_fields = int(lines[N_FIELDS_LINE])
    return float(lines[N_FIELDS_LINE + n_fields + 2])


def check_plotfile(plt: Path, step: int) -> None:
    """Raise :class:`ProvenanceError` unless ``plt`` matches the committed run's settings and time."""
    plt = Path(plt)
    try:
        info = (plt / "job_info").read_text()
        time = header_time(plt)
    except (OSError, ValueError, IndexError) as exc:
        raise ProvenanceError(f"{plt}: cannot read job_info/Header ({exc})") from exc
    for key, want in REQUIRED.items():
        m = re.search(rf"^{re.escape(key)}\s*=\s*(.+?)\s*$", info, flags=re.M)
        if m is None or m.group(1) != want:
            raise ProvenanceError(f"{plt}: {key} is {m.group(1) if m else 'missing'!r}, expected {want!r}")
    if IAMR_HASH not in info:
        raise ProvenanceError(f"{plt}: IAMR git hash {IAMR_HASH} not found in job_info")
    if abs(time - step * DT) > 1e-9:
        raise ProvenanceError(f"{plt}: header time {time!r} is not step {step} x {DT}")
