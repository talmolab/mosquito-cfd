"""Tests for the shared stdlib-only JSON loader ``mosquito_cfd._json_loader``.

OpenSpec change harden-json-loader (#175): every way a file's contents can fail to load is exactly
a ``ValueError`` naming the label and path; errors opening the path are not wrapped.
"""

from __future__ import annotations

import importlib
import json

import pytest
from _json_payloads import UNPARSEABLE
from test_light_corpus_helpers import (
    _HEAVY,
    PKG_DIR,
    _assert_stdlib_only,
    _run_child,
)

_MODULES = ("mosquito_cfd._json_loader", "mosquito_cfd.force_surrogate.sidecar")


def _loader(module: str):
    return importlib.import_module(module).load_json_clear_error


def _write(tmp_path, data: bytes):
    path = tmp_path / "probe.json"
    path.write_bytes(data)
    return path


# --- location and isolation ------------------------------------------------------------------


def test_json_module_imports_only_the_standard_library():
    _assert_stdlib_only(PKG_DIR / "_json_loader.py")


_JSON_PROBE = """
from pathlib import Path
from mosquito_cfd import _json_loader
assert _json_loader.load_json_clear_error(Path(sys.argv[1]), label="probe") == {"a": 1}
"""


def test_json_alone_loads_nothing_heavy(tmp_path):
    path = _write(tmp_path, b'{"a": 1}')
    assert _run_child(_JSON_PROBE, _HEAVY, str(path)) == []


def test_sidecar_name_is_the_shared_loader():
    import mosquito_cfd.force_surrogate.sidecar as sidecar

    shared = importlib.import_module("mosquito_cfd._json_loader")
    assert sidecar.load_json_clear_error is shared.load_json_clear_error


# --- content failures ------------------------------------------------------------------------


@pytest.mark.parametrize("module", _MODULES)
@pytest.mark.parametrize("case", list(UNPARSEABLE))
def test_unparseable_file_is_a_labelled_value_error(tmp_path, module, case):
    data, cause_type, prefix = UNPARSEABLE[case]
    path = _write(tmp_path, data)
    with pytest.raises(BaseException) as excinfo:
        _loader(module)(path, label="probe")
    err = excinfo.value
    assert type(err) is ValueError, repr(err)[:200]
    assert str(err).startswith(f"probe {path} {prefix}"), str(err)[:200]
    assert type(err.__cause__) is cause_type, repr(err.__cause__)[:200]


def test_json_decode_error_message_is_unchanged(tmp_path):
    # The malformed-JSON message is the one the old sidecar loader produced.
    try:
        json.loads("{")
    except json.JSONDecodeError as exc:
        expected_tail = str(exc)
    path = _write(tmp_path, b"{")
    with pytest.raises(ValueError) as excinfo:
        _loader("mosquito_cfd._json_loader")(path, label="probe")
    assert type(excinfo.value) is ValueError
    assert str(excinfo.value) == f"probe {path} is not valid JSON: {expected_tail}"


_NON_OBJECTS = [
    (b"[]", [], "list"),
    (b"5", 5, "int"),
    (b'"x"', "x", "str"),
    (b"null", None, "NoneType"),
]


@pytest.mark.parametrize("module", _MODULES)
@pytest.mark.parametrize(
    ("data", "value", "type_name"), _NON_OBJECTS, ids=[t for *_, t in _NON_OBJECTS]
)
def test_non_object_top_level_is_a_labelled_value_error(
    tmp_path, module, data, value, type_name
):
    path = _write(tmp_path, data)
    load = _loader(module)
    with pytest.raises(BaseException) as excinfo:
        load(path, label="probe")
    err = excinfo.value
    assert type(err) is ValueError, repr(err)
    assert str(err) == f"probe {path} top level is a {type_name}, not an object"
    assert load(path, label="probe", require_object=False) == value


@pytest.mark.parametrize("module", _MODULES)
@pytest.mark.parametrize("as_type", [str, lambda p: p], ids=["str", "Path"])
def test_valid_object_is_returned_unchanged(tmp_path, module, as_type):
    path = _write(tmp_path, b'{"a": [1, 2.5, "x", null]}')
    assert _loader(module)(as_type(path), label="probe") == {"a": [1, 2.5, "x", None]}


# --- opening errors are not wrapped (design D3) ----------------------------------------------


def test_missing_file_is_file_not_found(tmp_path):
    with pytest.raises(BaseException) as excinfo:
        _loader("mosquito_cfd._json_loader")(tmp_path / "absent.json", label="probe")
    assert type(excinfo.value) is FileNotFoundError


def test_directory_is_an_os_error_not_a_value_error(tmp_path):
    # PermissionError on Windows, IsADirectoryError on Linux: both OSError, neither ValueError.
    with pytest.raises(BaseException) as excinfo:
        _loader("mosquito_cfd._json_loader")(tmp_path, label="probe")
    assert isinstance(excinfo.value, OSError), repr(excinfo.value)
    assert not isinstance(excinfo.value, ValueError), repr(excinfo.value)
