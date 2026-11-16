"""Run mutants from a JSON table; restore each file from saved BYTES (never git checkout).

Usage: python mutate.py <repo> <table.json>
Table: [{"name": ..., "file": "src/...", "old": ..., "new": ..., "tests": ["tests/x.py::t", ...]}]
A mutant is KILLED when pytest exits non-zero. A mutant whose `old` text is not found exactly once
is reported as BAD (the table is wrong), never as survived.
Run with PYTHONDONTWRITEBYTECODE=1 so a restored file is never shadowed by a mutant .pyc.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

assert os.environ.get("PYTHONDONTWRITEBYTECODE") == "1", "set PYTHONDONTWRITEBYTECODE=1"
repo = Path(sys.argv[1])
table = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
env = {**os.environ, "PYTHONPATH": "src"}
env.pop("VIRTUAL_ENV", None)
results = []
for m in table:
    path = repo / m["file"]
    saved = path.read_bytes()
    text = saved.decode("utf-8")
    edits = m.get("edits") or [[m["old"], m["new"]]]
    bad = [e[0][:40] for e in edits if text.count(e[0]) != 1]
    if bad:
        results.append((m["name"], f"BAD (not found exactly once: {bad})"))
        continue
    for old, new in edits:
        text = text.replace(old, new)
    try:
        path.write_bytes(text.encode("utf-8"))
        proc = subprocess.run(
            ["uv", "run", "pytest", *m["tests"], "-p", "no:cacheprovider", "-q", "-x"],
            cwd=repo, env=env, capture_output=True, text=True,
        )
        tail = [ln for ln in proc.stdout.splitlines() if ln.strip()][-1:] or [""]
        verdict = "KILLED" if proc.returncode != 0 else "SURVIVED"
        results.append((m["name"], f"{verdict}  ({tail[0][:110]})"))
    finally:
        path.write_bytes(saved)
    assert path.read_bytes() == saved
for name, verdict in results:
    print(f"{verdict[:8]:8s} | {name} | {verdict[8:].strip()}")
