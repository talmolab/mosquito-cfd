"""Tests for mosquito_cfd.field_surrogate.snapshot (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from mosquito_cfd.field_surrogate.snapshot import read_field_snapshot

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


# --- proxies over real yt objects (never MagicMock: an auto-created attribute would let a test
# pass against an implementation that reads the wrong one -- design.md D5) -------------------


class _RecordingGrid:
    def __init__(self, inner, log, fp32_field=None):
        self._inner = inner
        self._log = log
        self._fp32_field = fp32_field

    def __getitem__(self, key):
        self._log.append(key)
        value = self._inner[key]
        if self._fp32_field is not None and key == self._fp32_field:
            return value.astype("float32")
        return value


class _ProxyIndex:
    def __init__(self, inner, max_level):
        self._inner = inner
        self.max_level = inner.max_level if max_level is None else max_level

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _ProxyDataset:
    def __init__(self, inner, log, max_level=None, fp32_field=None):
        self._inner = inner
        self._log = log
        self._max_level = max_level
        self._fp32_field = fp32_field

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def index(self):
        return _ProxyIndex(self._inner.index, self._max_level)

    def covering_grid(self, *args, **kwargs):
        return _RecordingGrid(
            self._inner.covering_grid(*args, **kwargs), self._log, self._fp32_field
        )


def _fixture_generator():
    # Same importlib pattern as test_stress_integral.py's regenerability test; tests/ is not a
    # package, so the generator cannot be imported by module path.
    spec = importlib.util.spec_from_file_location(
        "_make_lev_fixture", FIXTURE.parent / "make_lev_boxlib_fixture.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _patch_yt(monkeypatch, *, max_level=None, fp32_field=None, path=FIXTURE):
    """Return the list that records every ('boxlib', name) tuple actually read."""
    import yt

    log = []
    real_load = yt.load

    def fake_load(_path, *args, **kwargs):
        return _ProxyDataset(real_load(str(path)), log, max_level, fp32_field)

    monkeypatch.setattr(yt, "load", fake_load)
    return log


# --- task 4: the core contract ---------------------------------------------------------------

OMEGA = 1.3
CENTERS = np.arange(6) + 0.5
FULL = {"lo": (-np.inf,) * 3, "hi": (np.inf,) * 3}


def test_reads_fixture_full_extent():
    snap = read_field_snapshot(FIXTURE, **FULL)

    assert snap.max_level == 0
    assert Path(snap.source) == FIXTURE
    assert type(snap.time) is float
    assert snap.time == pytest.approx(0.5)

    assert isinstance(snap.dx, np.ndarray)
    assert snap.dx.dtype == np.float64 and snap.dx.shape == (3,)
    np.testing.assert_array_equal(snap.dx, [1.0, 1.0, 1.0])

    for axis in (snap.x, snap.y, snap.z):
        np.testing.assert_array_equal(axis, CENTERS)

    gx, gy, _ = np.meshgrid(CENTERS, CENTERS, CENTERS, indexing="ij")
    np.testing.assert_allclose(snap.arrays["u"], -OMEGA * gy)
    np.testing.assert_allclose(snap.arrays["v"], OMEGA * gx)
    np.testing.assert_array_equal(snap.arrays["w"], np.zeros((6, 6, 6)))

    for name, arr in snap.arrays.items():
        assert arr.dtype == np.float64, name
        assert arr.shape == (6, 6, 6), name


# --- task 6: immutability and non-aliasing ----------------------------------------------------


def test_snapshot_arrays_are_read_only_and_unshared():
    a = read_field_snapshot(FIXTURE, **FULL)
    b = read_field_snapshot(FIXTURE, **FULL)

    for arr in a.arrays.values():
        assert arr.flags.writeable is False
    with pytest.raises(ValueError):
        a.arrays["u"][0, 0, 0] = 12345.0

    for name in a.arrays:
        assert not np.shares_memory(a.arrays[name], b.arrays[name]), name


# --- tasks 7-9: field selection, validation, fp32 guard ---------------------------------------


def test_selecting_fields_reads_exactly_those(monkeypatch):
    log = _patch_yt(monkeypatch)
    snap = read_field_snapshot(FIXTURE, **FULL, fields=("u", "density", "tracer"))

    assert snap.field_names == ("u", "density", "tracer")
    assert set(snap.arrays) == {"u", "density", "tracer"}
    assert log == [
        ("boxlib", "x_velocity"),
        ("boxlib", "density"),
        ("boxlib", "tracer"),
    ]


def test_default_read_touches_exactly_the_six_required_fields(monkeypatch):
    # A default of all eight would silently add 33% I/O to flow_video's per-frame loop.
    log = _patch_yt(monkeypatch)
    read_field_snapshot(FIXTURE, **FULL)
    assert log == [
        ("boxlib", "x_velocity"),
        ("boxlib", "y_velocity"),
        ("boxlib", "z_velocity"),
        ("boxlib", "gradpx"),
        ("boxlib", "gradpy"),
        ("boxlib", "gradpz"),
    ]


def test_unknown_field_name_rejected_before_any_read(monkeypatch):
    log = _patch_yt(monkeypatch)
    with pytest.raises(ValueError, match="not_a_field"):
        read_field_snapshot(FIXTURE, **FULL, fields=("u", "not_a_field"))
    assert log == []


def test_absent_field_rejected_before_any_read(monkeypatch, tmp_path):
    reduced = _fixture_generator().write_fixture(
        tmp_path / "plt_reduced", fields=("x_velocity", "y_velocity")
    )
    log = _patch_yt(monkeypatch, path=reduced)
    with pytest.raises(ValueError, match="gradpx"):
        read_field_snapshot(reduced, **FULL)
    assert log == []


def test_fp32_field_is_refused_not_upcast(monkeypatch):
    # Uncatchable by any equality test against the FP64 fixture: a cast-then-check ordering would
    # silently upcast instead of raising.
    _patch_yt(monkeypatch, fp32_field=("boxlib", "x_velocity"))
    with pytest.raises(ValueError, match="float32"):
        read_field_snapshot(FIXTURE, **FULL)
