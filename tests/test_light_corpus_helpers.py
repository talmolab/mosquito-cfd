"""Tests for the shared stdlib-only helpers ``mosquito_cfd._provenance`` and ``_manifest``.

OpenSpec change share-light-corpus-helpers (#160, #159).
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_field_surrogate_corpus import _CFG, _corpus, _write_run_metadata

import mosquito_cfd
from mosquito_cfd import _provenance

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
PKG_DIR = Path(mosquito_cfd.__file__).resolve().parent

#: Modules no light helper may pull in (design D7, children (b) and (c)).
_HEAVY = (
    "mosquito_cfd.force_surrogate",
    "mosquito_cfd.field_surrogate",
    "mosquito_cfd.benchmarks",
    "pandas",
    "pyarrow",
    "matplotlib.pyplot",
)

# The child reports which package it imported, so a child that silently picked up another tree's
# editable install (e.g. in a mutation worktree) fails the parent instead of passing vacuously.
_CHILD_TAIL = """
import mosquito_cfd
print(json.dumps({"file": mosquito_cfd.__file__,
                  "loaded": sorted(m for m in HEAVY if m in sys.modules)}))
"""


def _run_child(body: str, heavy: tuple[str, ...], *args: str) -> list[str]:
    """Run ``body`` in a fresh interpreter on this tree; return the heavy modules it loaded."""
    code = f"import json, sys\nHEAVY = {heavy!r}\n{body}\n{_CHILD_TAIL}"
    result = subprocess.run(
        [sys.executable, "-c", code, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(SRC),
        },  # inherited: Windows needs SYSTEMROOT
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout.strip().splitlines()[-1])
    assert Path(report["file"]).resolve().parent == PKG_DIR, report["file"]
    return report["loaded"]


def _assert_stdlib_only(path: Path) -> None:
    """Every import in ``path`` (nested ones included) names a standard-library module."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                f"relative import: from {'.' * node.level}{node.module}"
            )
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.Call):
            func = node.func
            called = (
                func.attr
                if isinstance(func, ast.Attribute)
                else getattr(func, "id", None)
            )
            assert called not in ("import_module", "__import__"), (
                f"dynamic import at line {node.lineno}"
            )
            continue
        else:
            continue
        for name in names:
            assert name.split(".")[0] in sys.stdlib_module_names, name


# --- location and isolation ------------------------------------------------------------------

_PROVENANCE_PROBE = """
from pathlib import Path
from mosquito_cfd import _provenance
path = Path(sys.argv[1])
meta = _provenance.read_run_metadata(path, config_id=sys.argv[2])
_provenance.run_provenance(meta, config_id=sys.argv[2], path=path)
"""


def test_reading_provenance_loads_no_force_surrogate_stack(tmp_path):
    root = _corpus(tmp_path)
    path = _write_run_metadata(root / "runs" / _CFG)
    assert _run_child(_PROVENANCE_PROBE, _HEAVY, str(path), _CFG) == []


def test_provenance_module_imports_only_the_standard_library():
    _assert_stdlib_only(PKG_DIR / "_provenance.py")


def test_provenance_lives_at_the_top_level():
    # share-light-corpus-helpers D1: moved, not shimmed -- the old private path is gone.
    assert importlib.import_module("mosquito_cfd._provenance").__name__ == (
        "mosquito_cfd._provenance"
    )
    assert importlib.util.find_spec("mosquito_cfd.field_surrogate._provenance") is None


# --- the shared predicates (design D2) -------------------------------------------------------

_HEX64 = "a" * 64

_COMMIT_CASES = [
    ("a" * 40, True),
    ("a" * 40 + "\n", False),
    ("A" * 40, False),
    ("g" * 40, False),
    ("a" * 39, False),
    ("a" * 41, False),
    (" " + "a" * 40, False),
    (123, False),
    (None, False),
    (b"a" * 40, False),
    (["a" * 40], False),
]


@pytest.mark.parametrize(("value", "expected"), _COMMIT_CASES, ids=repr)
def test_is_full_commit_sha_table(value, expected):
    assert _provenance.is_full_commit_sha(value) is expected


_IMAGE_CASES = [
    ("ghcr.io/x@sha256:" + _HEX64, True),
    ("ghcr.io/talmolab/mosquito-cfd@sha256:" + _HEX64, True),
    ("ghcr.io/x:fp64@sha256:" + _HEX64, True),
    ("sha256:" + _HEX64, False),
    ("@sha256:" + _HEX64, False),
    (":@sha256:" + _HEX64, False),
    ("ghcr.io/X@sha256:" + _HEX64, False),
    ("GHCR.io/x@sha256:" + _HEX64, False),
    ("ghcr.io/x y@sha256:" + _HEX64, False),
    ("ghcr.io/x:latest #sha256:" + _HEX64, False),
    ("ghcr.io/x:latest #@sha256:" + _HEX64, False),
    ("garbage sha256:" + _HEX64 + " junk", False),
    (" ghcr.io/x@sha256:" + _HEX64, False),
    ("ghcr.io/x@sha256:" + _HEX64 + " ", False),
    ("ghcr.io/x@sha256:" + _HEX64 + "\n", False),
    ("ghcr.io/x@sha256:" + "A" * 64, False),
    ("repo@sha256:" + "a" * 65, False),
    ("repo@sha256:" + "a" * 63, False),
    ("ghcr.io/x:latest", False),
    (5, False),
    (None, False),
    (b"ghcr.io/x@sha256:" + b"a" * 64, False),
]


@pytest.mark.parametrize(("value", "expected"), _IMAGE_CASES, ids=repr)
def test_is_pinned_image_ref_table(value, expected):
    assert _provenance.is_pinned_image_ref(value) is expected
