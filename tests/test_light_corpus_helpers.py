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
# The AST checks read PKG_DIR: make sure it is this tree, not another editable install.
assert PKG_DIR == (SRC / "mosquito_cfd").resolve(), (PKG_DIR, SRC)

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


def _assert_stdlib_only(path: Path, allowed: tuple[str, ...] = ()) -> None:
    """Every import in ``path`` (nested ones included) names a standard-library module.

    A module named *exactly* in ``allowed`` is also accepted, and is then checked the same way
    with no allow-list (harden-json-loader D2). For ``from X import y`` only ``X`` is checked:
    ``y`` is an attribute, so ``from mosquito_cfd import _json_loader`` is rejected.
    """
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
            if name in allowed:
                _assert_stdlib_only(
                    PKG_DIR / (name.removeprefix("mosquito_cfd.") + ".py")
                )
                continue
            assert name.split(".")[0] in sys.stdlib_module_names, name


_ALLOW_LIST_VERDICTS = {
    "import mosquito_cfd._json_loader": True,
    "from mosquito_cfd._json_loader import load_json_clear_error": True,
    "from mosquito_cfd import force_surrogate": False,
    "from mosquito_cfd import _json_loader": False,
    "import mosquito_cfd": False,
    "import mosquito_cfd.force_surrogate": False,
    "import mosquito_cfd._json_loaderx": False,
    "import mosquito_cfd._json_loader.sub": False,
}


@pytest.mark.parametrize("statement", list(_ALLOW_LIST_VERDICTS))
def test_stdlib_only_allow_list_is_exact(tmp_path, statement):
    # harden-json-loader D2: an allowed name matches exactly, never by prefix either way.
    path = tmp_path / "probe.py"
    path.write_text(f"import json\n{statement}\n", encoding="utf-8")
    if _ALLOW_LIST_VERDICTS[statement]:
        _assert_stdlib_only(path, allowed=("mosquito_cfd._json_loader",))
    else:
        with pytest.raises(AssertionError):
            _assert_stdlib_only(path, allowed=("mosquito_cfd._json_loader",))


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


# --- the shared manifest reader (force-surrogate ADDED requirement, design D4) ---------------

_REQUIRED_KEYS_LITERAL = (
    "['frequency_fstar', 'index', 'name', 'pitch_amp_deg', 'reynolds', 'split', "
    "'stroke_amp_deg']"
)
_MANIFEST_CONFIG = {
    "name": "c0",
    "index": 0,
    "stroke_amp_deg": 35.0,
    "frequency_fstar": 0.85,
    "pitch_amp_deg": 30.0,
    "reynolds": 42.5,
    "split": "train",
}


def _load_manifest_configs():
    from mosquito_cfd._manifest import load_manifest_configs

    return load_manifest_configs


def _manifest_error(path: Path) -> BaseException:
    with pytest.raises(BaseException) as excinfo:
        _load_manifest_configs()(path)
    return excinfo.value


# Pinned from the pre-move reader's output (share-light-corpus-helpers task 2.1): the move must
# not change a single message for an object-top-level manifest.
_PINNED = {
    "no_configs": (
        {"schema_version": 1},
        "manifest {path} has no 'configs' key; not a sweep manifest",
    ),
    "configs_not_a_list": (
        {"configs": {}},
        "manifest 'configs' must be a list, got dict",
    ),
    "config_not_a_mapping": (
        {"configs": [5]},
        "manifest config 0 is not a mapping: 5",
    ),
    "config_missing_a_key": (
        {"configs": [{k: v for k, v in _MANIFEST_CONFIG.items() if k != "reynolds"}]},
        "manifest config 0 is missing required key(s) ['reynolds']; expected at least "
        + _REQUIRED_KEYS_LITERAL,
    ),
    "duplicate_name": (
        {"configs": [_MANIFEST_CONFIG, {**_MANIFEST_CONFIG, "index": 1}]},
        "duplicate config name 'c0' in manifest (config 1); names must be unique so each "
        "maps to one CSV and one split",
    ),
}


@pytest.mark.parametrize("case", sorted(_PINNED))
def test_manifest_reader_messages_are_pinned(tmp_path, case):
    content, template = _PINNED[case]
    path = tmp_path / "sweep_manifest.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    err = _manifest_error(path)
    assert type(err) is ValueError
    assert str(err) == template.format(path=f"{path}")


def test_manifest_reader_invalid_json_message_is_pinned(tmp_path):
    path = tmp_path / "sweep_manifest.json"
    path.write_text("{", encoding="utf-8")
    err = _manifest_error(path)
    assert type(err) is ValueError
    assert str(err) == (
        f"sweep manifest {path} is not valid JSON: Expecting property name enclosed in "
        "double quotes: line 1 column 2 (char 1)"
    )


def test_missing_manifest_is_file_not_found(tmp_path):
    assert type(_manifest_error(tmp_path / "absent.json")) is FileNotFoundError


@pytest.mark.parametrize(
    ("text", "type_name"),
    [("5", "int"), ('"configs"', "str"), ("null", "NoneType"), ("[]", "list")],
    ids=["int", "str", "null", "list"],
)
def test_non_object_manifest_top_level_is_a_value_error(tmp_path, text, type_name):
    path = tmp_path / "sweep_manifest.json"
    path.write_text(text, encoding="utf-8")
    err = _manifest_error(path)
    assert type(err) is ValueError, repr(err)
    assert str(err) == (
        f"manifest {path} top level is a {type_name}, not an object; not a sweep manifest"
    )


@pytest.mark.parametrize(
    ("payload", "prefix"),
    [
        (b"[" * 100_000 + b"]" * 100_000, "is not valid JSON: "),
        (b'{"configs": [' + b"9" * 5000 + b"]}", "is not valid JSON: "),
        (b"\xff\xfe{", "is not valid UTF-8: "),
    ],
    ids=["deep_nesting", "int_digit_limit", "non_utf8"],
)
def test_unparseable_manifest_is_a_value_error(tmp_path, payload, prefix):
    path = tmp_path / "sweep_manifest.json"
    path.write_bytes(payload)
    err = _manifest_error(path)
    assert type(err) is ValueError, repr(err)
    assert str(err).startswith(f"sweep manifest {path} {prefix}"), str(err)[:200]


def test_manifest_reexport_is_the_same_object():
    import mosquito_cfd.force_surrogate as fs
    import mosquito_cfd.force_surrogate.dataset as dataset

    manifest = importlib.import_module("mosquito_cfd._manifest")
    assert manifest.load_manifest_configs is dataset.load_manifest_configs
    assert manifest.load_manifest_configs is fs.load_manifest_configs
    assert manifest._REQUIRED_CONFIG_KEYS is dataset._REQUIRED_CONFIG_KEYS
    assert manifest._validate_configs is dataset._validate_configs


def test_manifest_module_imports_only_the_standard_library():
    _assert_stdlib_only(PKG_DIR / "_manifest.py")


_MANIFEST_PROBE = """
from pathlib import Path
from mosquito_cfd import _manifest
configs = _manifest.load_manifest_configs(Path(sys.argv[1]))
assert [c["name"] for c in configs] == ["c0"], configs
"""


def test_manifest_alone_loads_nothing_heavy(tmp_path):
    path = tmp_path / "sweep_manifest.json"
    path.write_text(json.dumps({"configs": [_MANIFEST_CONFIG]}), encoding="utf-8")
    assert _run_child(_MANIFEST_PROBE, _HEAVY, str(path)) == []


@pytest.mark.parametrize(
    "content",
    [5, {"configs": [{k: v for k, v in _MANIFEST_CONFIG.items() if k != "reynolds"}]}],
    ids=["top_level_int", "missing_reynolds"],
)
def test_field_and_force_paths_raise_the_same_manifest_error(tmp_path, content):
    from mosquito_cfd.field_surrogate.corpus import FieldCorpus
    from mosquito_cfd.force_surrogate.dataset import load_manifest_configs

    root = tmp_path / "corpus"
    root.mkdir()
    path = root / "sweep_manifest.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(BaseException) as field:
        FieldCorpus(root).config_ids()
    with pytest.raises(BaseException) as force:
        load_manifest_configs(path)
    assert type(field.value) is ValueError, repr(field.value)
    assert type(force.value) is ValueError, repr(force.value)
    assert str(field.value) == str(force.value)


# --- FieldCorpus reads the manifest without the force-surrogate stack (#160) -----------------

_CORPUS_HEAVY = (
    "mosquito_cfd.force_surrogate",
    "pandas",
    "pyarrow",
    "matplotlib.pyplot",
)

_CORPUS_PROBE = """
from pathlib import Path
from mosquito_cfd.field_surrogate.corpus import FieldCorpus
ids = FieldCorpus(Path(sys.argv[1])).config_ids()
assert ids == ["c0", "c1"], ids
"""


def test_manifest_read_loads_no_force_surrogate_stack(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    configs = [_MANIFEST_CONFIG, {**_MANIFEST_CONFIG, "name": "c1", "index": 1}]
    (root / "sweep_manifest.json").write_text(
        json.dumps({"configs": configs}), encoding="utf-8"
    )
    assert _run_child(_CORPUS_PROBE, _CORPUS_HEAVY, str(root)) == []


def test_corpus_imports_no_force_surrogate_or_benchmarks():
    # Covers code paths the subprocess child does not run: no import anywhere in corpus.py,
    # nested (lazy) imports included, may reach the force-surrogate stack or benchmarks.
    source = (PKG_DIR / "field_surrogate" / "corpus.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            names = [node.module or ""] + [
                f"{node.module}.{a.name}" for a in node.names
            ]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            continue
        for name in names:
            assert not name.startswith(
                ("mosquito_cfd.force_surrogate", "mosquito_cfd.benchmarks")
            ), f"line {node.lineno}: {name}"
