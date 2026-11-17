"""Resumable job log: one JSON line per finished fit, keyed by an id."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class JobLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.done = set()
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.done.add(json.loads(line)["job"])

    def has(self, job: str) -> bool:
        return job in self.done

    def add(self, job: str, rows: list[dict]) -> None:
        with open(self.path, "a") as f:
            f.write(json.dumps({"job": job, "rows": rows}) + "\n")
        self.done.add(job)

    def frame(self) -> pd.DataFrame:
        rows = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                rows += [{"job": rec["job"], **r} for r in rec["rows"]]
        return pd.DataFrame(rows)
