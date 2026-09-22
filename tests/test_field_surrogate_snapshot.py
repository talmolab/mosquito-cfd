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


# --- tasks 11-13: region semantics, the D1 compatibility surface -----------------------------

_INF = np.inf

#: (id, lo, hi, halo, expected cells per axis). Expected counts are literals derived once from the
#: reference arithmetic, not recomputed with the same formula the reader uses -- that would be
#: tautological. PR B's differential test against the frozen oracle reuses this matrix.
REGION_CASES = [
    ("full", (-_INF, -_INF, -_INF), (_INF, _INF, _INF), 0, (6, 6, 6)),
    ("interior_unaligned", (1.2, 1.2, 1.2), (4.7, 4.7, 4.7), 0, (4, 4, 4)),
    ("cell_aligned", (2.0, 2.0, 2.0), (4.0, 4.0, 4.0), 0, (2, 2, 2)),
    ("halo1", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 1, (4, 4, 4)),
    ("halo2", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 2, (6, 6, 6)),
    # halo=3 on a 2-cell box clips to 6, NOT 8: "halo adds exactly 2h cells" holds only unclipped.
    ("halo3_clipped", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 3, (6, 6, 6)),
    ("mixed_inf", (-_INF, 1.5, -_INF), (_INF, 4.5, _INF), 0, (6, 4, 6)),
    ("zero_width_interior", (2.0, 2.0, 2.0), (2.0, 2.0, 2.0), 0, (1, 1, 1)),
    # At and beyond the upper domain edge the ddims clamp removes the one-cell floor, yielding a
    # zero-cell region. The spec says so explicitly (design.md D1) -- an earlier draft claimed a
    # guaranteed floor, which is false.
    ("upper_edge", (6.0, 6.0, 6.0), (6.0, 6.0, 6.0), 0, (0, 0, 0)),
    ("outside_domain", (7.0, 7.0, 7.0), (9.0, 9.0, 9.0), 0, (0, 0, 0)),
    ("inverted", (4.0, 4.0, 4.0), (2.0, 2.0, 2.0), 0, (1, 1, 1)),
]


@pytest.mark.parametrize(
    ("lo", "hi", "halo", "expected"),
    [c[1:] for c in REGION_CASES],
    ids=[c[0] for c in REGION_CASES],
)
def test_region_clamping_matrix(lo, hi, halo, expected):
    snap = read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo)
    for name, arr in snap.arrays.items():
        assert arr.shape == expected, name
    assert (snap.x.size, snap.y.size, snap.z.size) == expected


def test_nan_corner_is_rejected():
    # np.floor(nan).astype(int64) is INT64_MIN with a RuntimeWarning, which would silently
    # degrade to a full-domain read. Reject instead.
    with pytest.raises(ValueError, match="NaN"):
        read_field_snapshot(FIXTURE, lo=(np.nan, 0.0, 0.0), hi=(_INF,) * 3)


# --- tasks 14-15: point-cloud view -------------------------------------------------------------


def test_point_cloud_is_aligned_and_complete():
    snap = read_field_snapshot(FIXTURE, lo=(1.2,) * 3, hi=(4.7,) * 3)
    pc = snap.to_point_cloud()
    nx, ny, nz = snap.arrays["u"].shape
    n = nx * ny * nz

    assert pc.coords.shape == (n, 3)
    assert pc.values.shape == (n, len(snap.field_names))
    assert pc.field_names == snap.field_names
    np.testing.assert_array_equal(pc.cell_volume, np.full(n, float(np.prod(snap.dx))))

    # C-order alignment: check a specific cell's row index, computed independently.
    i, j, k = 2, 1, 3
    row = (i * ny + j) * nz + k
    np.testing.assert_array_equal(pc.coords[row], [snap.x[i], snap.y[j], snap.z[k]])
    for col, name in enumerate(snap.field_names):
        assert pc.values[row, col] == snap.arrays[name][i, j, k]

    for arr in (pc.coords, pc.values, pc.cell_volume):
        assert arr.flags.writeable is False


@pytest.mark.parametrize(
    ("lo", "hi", "n"),
    [((2.0,) * 3, (2.0,) * 3, 1), ((7.0,) * 3, (9.0,) * 3, 0)],
    ids=["one_cell", "zero_cell"],
)
def test_point_cloud_handles_degenerate_regions(lo, hi, n):
    pc = read_field_snapshot(FIXTURE, lo=lo, hi=hi).to_point_cloud()
    assert pc.coords.shape == (n, 3)
    assert pc.values.shape == (n, 6)


# --- tasks 17-18: AMR refusal ------------------------------------------------------------------


def test_multi_level_plotfile_is_refused(monkeypatch):
    log = _patch_yt(monkeypatch, max_level=2)
    with pytest.raises(ValueError, match="CC-F3") as excinfo:
        read_field_snapshot(FIXTURE, **FULL)
    assert "2" in str(excinfo.value)
    assert log == [], "refusal must precede any field read"


def test_amr_guard_reads_the_attribute_the_proxy_overrides(monkeypatch):
    # The companion assertion that makes the test above honest: with the same proxy left at its
    # real max_level of 0, the read succeeds. Without this, a guard reading the wrong attribute
    # name would still make the refusal test pass while being dead on every real plotfile.
    _patch_yt(monkeypatch, max_level=None)
    snap = read_field_snapshot(FIXTURE, **FULL)
    assert snap.max_level == 0


# --- review corrections (tasks 46-51) ---------------------------------------------------------


def test_genuine_fp32_plotfile_is_refused(tmp_path):
    # Task 46/47. The original guard inspected the RETURNED array's dtype, which can never be
    # float32: yt's AMReX frontend allocates its output buffers float64 unconditionally and
    # widens the on-disk FAB into them. Verified on this very fixture -- ds.index._dtype is
    # float32 while cg[...].to_ndarray().dtype is float64 and the values carry ~1.9e-07 of fp32
    # truncation. A stub returning a float32 array tests the branch, not the property.
    fp32 = _fixture_generator().write_fixture(
        tmp_path / "plt_fp32", real_dtype="float32"
    )
    with pytest.raises(ValueError, match="float32"):
        read_field_snapshot(fp32, **FULL)


def test_fp64_plotfile_still_accepted(tmp_path):
    # Positive control: an implementation that refused everything would pass the test above.
    fp64 = _fixture_generator().write_fixture(tmp_path / "plt_fp64")
    assert read_field_snapshot(fp64, **FULL).arrays["u"].dtype == np.float64


def test_duplicate_field_names_are_rejected(monkeypatch):
    # Task 48. Previously fields=("u","v","u") gave arrays with 2 entries but field_names with 3,
    # a point cloud with a duplicated column, and one yt read per repetition.
    log = _patch_yt(monkeypatch)
    with pytest.raises(ValueError, match="duplicate"):
        read_field_snapshot(FIXTURE, **FULL, fields=("u", "v", "u"))
    assert log == []


@pytest.mark.parametrize(
    ("lo", "hi"),
    [
        ((-np.inf,) * 3, (np.inf,) * 3),
        ((1.2,) * 3, (4.7,) * 3),
        ((1.2, -np.inf, -np.inf), (4.7, np.inf, np.inf)),
    ],
    ids=["full_extent", "sub_box", "x_slab"],
)
def test_snapshot_arrays_own_their_data(lo, hi):
    # Task 49. np.ascontiguousarray does NOT copy a slice that is already C-contiguous -- the
    # full-extent and single-axis-slab cases -- so setflags(write=False) there left a reachable,
    # WRITABLE base and the immutability guarantee was a facade. Owning the data is what makes it
    # real, and it also stops a small region pinning the whole covering grid alive.
    snap = read_field_snapshot(FIXTURE, lo=lo, hi=hi)
    for name, arr in snap.arrays.items():
        assert arr.base is None, f"{name} is a view onto the covering grid"
        assert arr.flags.writeable is False, name
    for axis_name, axis in (("x", snap.x), ("y", snap.y), ("z", snap.z)):
        assert axis.base is None, axis_name


@pytest.mark.parametrize(
    ("halo", "match"),
    [(-1, "non-negative"), (-5, "non-negative"), (1.9, "integer"), (0.5, "integer")],
    ids=["negative", "very_negative", "fractional", "half"],
)
def test_invalid_halo_is_rejected(halo, match):
    # Task 50. A negative halo silently eroded the region (halo=-5 silently returned ZERO cells);
    # a fractional halo truncates per face, so halo=1.9 padded 2 cells low and 1 high -- an
    # asymmetric stencil pad, wrong for anything differentiating across it.
    with pytest.raises(ValueError, match=match):
        read_field_snapshot(FIXTURE, lo=(2.2,) * 3, hi=(3.4,) * 3, halo=halo)


_PACKAGE_ONLY_PROBE = """
import sys

import mosquito_cfd.field_surrogate

leaked = sorted(n for n in sys.modules if n.startswith("mosquito_cfd.field_surrogate."))
sys.stdout.write("LEAKED:" + ",".join(leaked) if leaked else "OK")
"""


def test_package_init_imports_no_submodule():
    # Task 51. design.md D4: an eager re-export both ~6x's stress_integral's import cost (corpus
    # reaches force_surrogate.dataset -> pandas) and arms a
    # benchmarks -> field_surrogate -> force_surrogate -> benchmarks cycle. The yt/pandas probe
    # CANNOT see this -- it imports the submodules itself -- and an eager-__init__ mutant left
    # the whole suite green.
    result = subprocess.run(
        [sys.executable, "-c", _PACKAGE_ONLY_PROBE],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "OK", result.stdout


def test_missing_private_dtype_attribute_is_a_hard_failure(monkeypatch):
    # ds.index._dtype is private yt API. An earlier version of this guard used
    # getattr(..., np.float64), which would silently pass EVERY plotfile if yt renamed it --
    # re-creating the vacuous check this guard exists to replace, with nothing failing.
    import yt

    real_load = yt.load

    class _NoDtypeIndex:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            if name == "_dtype":
                raise AttributeError(name)
            return getattr(self._inner, name)

    class _NoDtypeDataset:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        @property
        def index(self):
            return _NoDtypeIndex(self._inner.index)

    monkeypatch.setattr(
        yt, "load", lambda p, *a, **k: _NoDtypeDataset(real_load(str(p)))
    )
    with pytest.raises(ValueError, match="on-disk precision"):
        read_field_snapshot(FIXTURE, **FULL)
