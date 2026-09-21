"""Tests for mosquito_cfd.field_surrogate.snapshot (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = REPO_ROOT / "src" / "mosquito_cfd" / "field_surrogate"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "lev_boxlib_plt"

# Task 1 (design D4): importing the package must not drag in yt (the heavy plotfile reader) or
# pandas (reachable via corpus -> force_surrogate.dataset). Measured at HEAD, importing
# stress_integral is ~0.20s with neither loaded; an eager __init__ re-export of FieldCorpus would
# take it to ~1.2s and propagate to wing_lev, flow_video and the make_flow_video CLI.
_IMPORT_PROBE = """
import sys

import mosquito_cfd.field_surrogate
import mosquito_cfd.field_surrogate.corpus
import mosquito_cfd.field_surrogate.domino_adapter
import mosquito_cfd.field_surrogate.snapshot
import mosquito_cfd.benchmarks.stress_integral

eager = sorted(
    name
    for name in sys.modules
    if name in ("yt", "pandas") or name.startswith(("yt.", "pandas."))
)
if eager:
    sys.stdout.write("EAGER:" + ",".join(eager))
    raise SystemExit(1)
"""


def test_importing_the_package_does_not_import_yt_or_pandas():
    # A subprocess is REQUIRED here, not a convenience. An in-process `"yt" not in sys.modules`
    # check is coupled to pytest's alphabetical file order: test_field_surrogate_corpus.py sorts
    # before this file and reads a real plotfile, so an in-process probe would fail
    # deterministically in a full-suite CI run while passing during solo TDD.
    result = subprocess.run(
        [sys.executable, "-c", _IMPORT_PROBE],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, (
        f"eagerly imported heavy modules: {result.stdout or result.stderr}"
    )


def _yt_import_nodes(tree: ast.Module) -> list[ast.stmt]:
    nodes: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "yt" or a.name.startswith("yt.") for a in node.names):
                nodes.append(node)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "yt" or node.module.startswith("yt.")):
                nodes.append(node)
    return nodes


def _ids_inside_functions(tree: ast.Module) -> set[int]:
    inside: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                inside.add(id(child))
    return inside


def test_package_dir_is_discoverable():
    # Guards the parametrization below: an empty glob makes pytest report a vacuous SKIP, so a
    # renamed or moved package would silently disarm the module-scope-import check.
    assert sorted(PACKAGE_DIR.glob("*.py")), f"no modules found under {PACKAGE_DIR}"


@pytest.mark.parametrize("path", sorted(PACKAGE_DIR.glob("*.py")), ids=lambda p: p.name)
def test_every_yt_import_is_function_scoped(path: Path):
    # Task 2: the static counterpart to the subprocess probe. This one survives someone adding a
    # fourth submodule that the probe's hardcoded import list would miss.
    tree = ast.parse(path.read_text(encoding="utf-8"))
    inside = _ids_inside_functions(tree)
    offenders = [
        f"{path.name}:{node.lineno}"
        for node in _yt_import_nodes(tree)
        if id(node) not in inside
    ]
    assert not offenders, f"module-scope yt import(s): {offenders}"
