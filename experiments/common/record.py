"""Per-run provenance record written beside every experiment's outputs."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from experiments.common.data import REPO


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    except Exception as exc:  # WSL can fail to resolve a Windows worktree (#78); record that, don't crash
        return f"unavailable: {type(exc).__name__}"


def write_run_record(out_dir: Path, *, inputs: list[Path] = (), **fields) -> None:
    """Write ``run_record.json``: commit, dirty flag, input hashes, timestamp and caller fields."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    # From WSL, git cannot resolve this Windows worktree (#78); the launcher passes the commit in.
    commit = os.environ.get("EXP_GIT_COMMIT") or _git("rev-parse", "HEAD")
    status = _git("status", "--porcelain")
    record = {
        "written_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": commit,
        "git_dirty": None if status.startswith("unavailable") else bool(status),
        "inputs": {str(Path(p).relative_to(REPO) if Path(p).is_relative_to(REPO) else p): sha256(Path(p)) for p in inputs},
        **fields,
    }
    (out_dir / "run_record.json").write_text(json.dumps(record, indent=2, default=str))
