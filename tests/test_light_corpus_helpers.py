"""Tests for the shared stdlib-only helpers ``mosquito_cfd._provenance`` and ``_manifest``.

OpenSpec change share-light-corpus-helpers (#160, #159).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
from pathlib import Path

from test_field_surrogate_corpus import _CFG, _corpus, _write_run_metadata

_PROVENANCE_PROBE = """
import json, sys
from pathlib import Path
from mosquito_cfd import _provenance
path = Path(sys.argv[1])
meta = _provenance.read_run_metadata(path, config_id=sys.argv[2])
_provenance.run_provenance(meta, config_id=sys.argv[2], path=path)
heavy = [m for m in ("mosquito_cfd.force_surrogate", "pandas", "matplotlib.pyplot")
         if m in sys.modules]
print(json.dumps(heavy))
"""


def test_reading_provenance_loads_no_force_surrogate_stack(tmp_path):
    import subprocess

    root = _corpus(tmp_path)
    path = _write_run_metadata(root / "runs" / _CFG)
    result = subprocess.run(
        [sys.executable, "-c", _PROVENANCE_PROBE, str(path), _CFG],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.strip().splitlines()[-1]) == []


def test_provenance_module_imports_only_the_standard_library():
    import ast

    import mosquito_cfd as pkg

    source = (Path(pkg.__file__).parent / "_provenance.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, (
                f"relative import: from {'.' * node.level}{node.module}"
            )
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            continue
        for name in names:
            assert name.split(".")[0] in sys.stdlib_module_names, name


def test_provenance_lives_at_the_top_level():
    # share-light-corpus-helpers D1: moved, not shimmed -- the old private path is gone.
    assert importlib.import_module("mosquito_cfd._provenance").__name__ == (
        "mosquito_cfd._provenance"
    )
    assert importlib.util.find_spec("mosquito_cfd.field_surrogate._provenance") is None
