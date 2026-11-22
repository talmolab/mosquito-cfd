"""The bench package imports no heavy dependency, and its scope names three limits (3b.1).

Scenarios "Importing the bench pulls in no heavy dependency" and "The scope names all three
limits" (surrogate-comparison-bench spec).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BLOCKED = ("torch", "physicsnemo", "scipy", "sklearn")


def test_importing_the_bench_imports_no_heavy_dependency():
    """A meta-path hook raises on any blocked import, so the check holds with or without them."""
    script = textwrap.dedent(
        f"""
        import importlib.abc, sys
        BLOCKED = {BLOCKED!r}
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in BLOCKED:
                    raise ImportError("blocked import: " + name)
                return None
        sys.meta_path.insert(0, Block())
        import mosquito_cfd.surrogate_bench
        import mosquito_cfd.surrogate_bench.splits
        print("imported")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, cwd=REPO
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "imported" in result.stdout


def test_the_scope_names_all_three_limits():
    from mosquito_cfd.surrogate_bench import BENCH_SCOPE

    for phrase in (
        "3 × 3 × 3",
        "held-out outer layer",
        "2-beat",
        "has not settled",
        "#142",
    ):
        assert phrase in BENCH_SCOPE, phrase


def test_the_bench_seeds_are_the_shipped_seeds():
    from mosquito_cfd.surrogate_bench import BENCH_SEEDS

    assert BENCH_SEEDS == (1234, 1235, 1236, 1237, 1238)
