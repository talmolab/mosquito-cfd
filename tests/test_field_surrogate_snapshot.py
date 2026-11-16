"""Tests for mosquito_cfd.field_surrogate.snapshot (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import ast
import functools
import hashlib
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

    # The reader releases yt's per-field cache as it goes (improve-field-reader-perf-memory D4),
    # so the proxy forwards exactly the two members that touches -- explicitly, not through a
    # catch-all __getattr__.
    @property
    def field_data(self):
        return self._inner.field_data

    def clear_data(self):
        self._inner.clear_data()


class _ProxyIndex:
    def __init__(self, inner, max_level):
        self._inner = inner
        self.max_level = inner.max_level if max_level is None else max_level

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _ProxyDataset:
    def __init__(
        self, inner, log, max_level=None, fp32_field=None, grid_log=None, grid_cls=None
    ):
        self._inner = inner
        self._log = log
        self._max_level = max_level
        self._fp32_field = fp32_field
        # Covering-grid construction is recorded in its OWN log, so the field-read logs that
        # existing tests compare with == are unchanged.
        self._grid_log = grid_log
        self._grid_cls = grid_cls or _RecordingGrid

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def index(self):
        return _ProxyIndex(self._inner.index, self._max_level)

    def covering_grid(self, *args, **kwargs):
        if self._grid_log is not None:
            self._grid_log.append(kwargs.get("level", args[0] if args else None))
        return self._grid_cls(
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


def _patch_yt(
    monkeypatch,
    *,
    max_level=None,
    fp32_field=None,
    path=FIXTURE,
    grid_log=None,
    grid_cls=None,
):
    """Return the list that records every ('boxlib', name) tuple actually read.

    ``grid_log``, when given, records each covering-grid construction; ``grid_cls`` replaces
    the recording grid proxy.
    """
    import yt

    log = []
    real_load = yt.load

    def fake_load(_path, *args, **kwargs):
        return _ProxyDataset(
            real_load(str(path)), log, max_level, fp32_field, grid_log, grid_cls
        )

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

#: AGREEMENT cases: requests where read_field_snapshot and the frozen pre-refactor
#: extract_eulerian_box (tests/fixtures/legacy_extract_eulerian_box.py) agree -- the parity region
#: of design.md D1, plus three edge points outside it that agree anyway (lower_edge,
#: lower_edge_halo2, just_below_halo1). (id, lo, hi, halo, expected cells per axis). Expected counts are literals derived once from the
#: reference arithmetic, not recomputed with the same formula the reader uses -- that would be
#: tautological. test_extract_eulerian_box_matches_the_frozen_pre_refactor_oracle and
#: scripts/verify_eulerian_box_ab.py both iterate THIS matrix, so every entry here must be one where
#: the two implementations agree; divergences go in DIVERGENCE_CASES below. Inverted requests
#: (lo > hi) are rejected by the reader (harden-field-corpus-requests D1) and tested separately in
#: INVERTED_REQUESTS and NARROWED_REQUESTS.
REGION_CASES = [
    ("full", (-_INF, -_INF, -_INF), (_INF, _INF, _INF), 0, (6, 6, 6)),
    ("interior_unaligned", (1.2, 1.2, 1.2), (4.7, 4.7, 4.7), 0, (4, 4, 4)),
    ("cell_aligned", (2.0, 2.0, 2.0), (4.0, 4.0, 4.0), 0, (2, 2, 2)),
    ("halo1", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 1, (4, 4, 4)),
    ("halo2", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 2, (6, 6, 6)),
    # halo=3 on a 2-cell box clips to 6, NOT 8: "halo adds exactly 2h cells" holds only unclipped.
    ("halo3_clipped", (2.2, 2.2, 2.2), (3.4, 3.4, 3.4), 3, (6, 6, 6)),
    ("mixed_inf", (-_INF, 1.5, -_INF), (_INF, 4.5, _INF), 0, (6, 4, 6)),
    # x-slab only: what sphere_cv_drag_cd and sphere_cv_steadiness_fraction actually request,
    # and one of the two shapes where a contiguous slice would be returned as a view.
    ("x_slab_only", (1.5, -_INF, -_INF), (4.5, _INF, _INF), 0, (4, 6, 6)),
    ("zero_width_interior", (2.0, 2.0, 2.0), (2.0, 2.0, 2.0), 0, (1, 1, 1)),
    # A point at the upper edge is outside the half-open cell coverage [0, 6): zero cells, and
    # NOT widened to one (design.md D1).
    ("upper_edge", (6.0, 6.0, 6.0), (6.0, 6.0, 6.0), 0, (0, 0, 0)),
    ("outside_domain", (7.0, 7.0, 7.0), (9.0, 9.0, 9.0), 0, (0, 0, 0)),
    ("lower_edge", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 0, (1, 1, 1)),
    # halo at both edges: a point on either edge reaches `halo` cells inward -- symmetric.
    ("lower_edge_halo2", (0.0, 0.0, 0.0), (0.0, 0.0, 0.0), 2, (2, 2, 2)),
    ("upper_edge_halo2", (6.0, 6.0, 6.0), (6.0, 6.0, 6.0), 2, (2, 2, 2)),
    # Less than one cell below the domain, with halo 1: the pad reaches cell 0.
    ("just_below_halo1", (-0.5, -0.5, -0.5), (-0.2, -0.2, -0.2), 1, (1, 1, 1)),
]

#: DIVERGENCE cases: requests lying outside the domain on some axis (hi <= dle or lo > dre), where
#: the legacy adapter clamps the corners onto the domain edge BEFORE padding and so returns edge
#: cells however far away the request is, while read_field_snapshot pads first and keeps only the
#: part of the padded request inside the domain ("halo is reach", design.md D1).
#: (id, lo, hi, halo, legacy cells per axis, read_field_snapshot cells per axis).
DIVERGENCE_CASES = [
    ("below_h0", (-9.0,) * 3, (-7.0,) * 3, 0, (1, 1, 1), (0, 0, 0)),
    ("below_beyond_reach_h2", (-9.0,) * 3, (-7.0,) * 3, 2, (2, 2, 2), (0, 0, 0)),
    ("below_within_reach_h2", (-1.5,) * 3, (-1.2,) * 3, 2, (2, 2, 2), (1, 1, 1)),
    ("above_within_reach_h2", (7.0,) * 3, (9.0,) * 3, 2, (2, 2, 2), (1, 1, 1)),
    ("above_beyond_reach_h2", (100.0,) * 3, (200.0,) * 3, 2, (2, 2, 2), (0, 0, 0)),
    # Within reach but NOT on a cell face: the pad starts from floor(6.5) = 6, so halo 2 reaches
    # cells 4 and 5. above_within_reach_h2 (lo = 7.0) sits on a face, where floor and ceil agree,
    # so it cannot see reach computed from the wrong rounding.
    ("above_within_reach_offface_h2", (6.5,) * 3, (9.0,) * 3, 2, (2, 2, 2), (2, 2, 2)),
    # A range ending exactly on the lower edge covers no cell: upper bounds are exclusive, exactly
    # as in the interior ((1.5, 2.0) yields cell 1 only). A POINT at the lower edge still yields
    # cell 0 (lower_edge, above).
    ("range_ending_at_lower_edge", (-5.0,) * 3, (0.0,) * 3, 0, (1, 1, 1), (0, 0, 0)),
    ("minus_inf_point", (-_INF,) * 3, (-_INF,) * 3, 0, (1, 1, 1), (0, 0, 0)),
    (
        "x_below_yz_inside_h1",
        (-3.0, 1.0, 1.0),
        (-1.0, 5.0, 5.0),
        1,
        (1, 6, 6),
        (0, 6, 6),
    ),
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

    # Shapes alone let a region shifted by one cell pass. Values must also match the fixture's
    # analytic solid-body rotation at the RETURNED coordinates (catches values sliced off the
    # coordinates), and coordinates and values must match the frozen pre-refactor copy (catches a
    # shift of both together). Not the importable extract_eulerian_box: that delegates here, so
    # comparing against it would be a self-comparison.
    shape = snap.arrays["u"].shape
    np.testing.assert_allclose(
        snap.arrays["u"], np.broadcast_to(-OMEGA * snap.y[None, :, None], shape)
    )
    np.testing.assert_allclose(
        snap.arrays["v"], np.broadcast_to(OMEGA * snap.x[:, None, None], shape)
    )
    legacy = _legacy()(str(FIXTURE), lo=lo, hi=hi, halo=halo)
    for axis in ("x", "y", "z"):
        np.testing.assert_array_equal(getattr(snap, axis), legacy[axis], err_msg=axis)
    for name in snap.field_names:
        np.testing.assert_array_equal(snap.arrays[name], legacy[name], err_msg=name)


def test_read_passes_the_requested_halo_to_the_region_helper(monkeypatch):
    # The 6-cell fixture clips any halo above 2 on most boxes, so a halo altered on its way into
    # the helper (e.g. silently capped) is invisible to every shape assertion. Spy on the call.
    import mosquito_cfd.field_surrogate.snapshot as mod

    seen = []
    real = mod._region_bounds

    def spy(lo, hi, halo, **kwargs):
        seen.append(halo)
        return real(lo, hi, halo, **kwargs)

    monkeypatch.setattr(mod, "_region_bounds", spy)
    read_field_snapshot(FIXTURE, lo=(3.0,) * 3, hi=(3.0,) * 3, halo=7)
    assert seen == [7]


@pytest.mark.parametrize(
    ("point", "expected"),
    [
        (2.0, (1, 1, 1)),
        (6.0, (0, 0, 0)),
        (_INF, (0, 0, 0)),
        (-_INF, (0, 0, 0)),
    ],
    ids=["interior", "upper_edge", "plus_inf", "minus_inf"],
)
def test_zero_width_request_is_not_inverted(point, expected):
    # lo == hi is the documented point query, not an inverted request: the inversion check is a
    # strict lo > hi (harden-field-corpus-requests D1), so a `>=` check fails here first. Recorded
    # from the reader before the rejection existed.
    snap = read_field_snapshot(FIXTURE, lo=(point,) * 3, hi=(point,) * 3)
    assert (snap.x.size, snap.y.size, snap.z.size) == expected


#: Inverted requests (lo > hi on some axis). Legacy and the region helper return a small region for
#: each -- one cell, up to 2*halo + 1 cells, or none -- so none of these ever errored before
#: (harden-field-corpus-requests D1). Two have a NON-EMPTY padded range, so a check on the padded
#: indices instead of the raw corners would let them through. (id, lo, hi, halo).
INVERTED_REQUESTS = [
    ("all_axes_h0", (4.0,) * 3, (2.0,) * 3, 0),
    ("all_axes_h1", (4.0,) * 3, (2.0,) * 3, 1),
    ("outside_domain", (9.0,) * 3, (-9.0,) * 3, 0),
    ("within_one_cell", (2.6,) * 3, (2.4,) * 3, 0),
    ("padded_range_nonempty_h2", (4.0,) * 3, (3.0,) * 3, 2),
    ("y_only", (1.0, 4.0, 1.0), (5.0, 2.0, 5.0), 0),
    ("infinite_x", (_INF, 0.0, 0.0), (-_INF, 6.0, 6.0), 0),
]


def _inversion_pattern(lo, hi) -> tuple[list[str], list[str]]:
    """Return (message fragments that must appear, axis labels that must not)."""
    present, absent = [], []
    for i, axis in enumerate(("x", "y", "z")):
        if lo[i] > hi[i]:
            present.append(f"axis {axis}: lo={float(lo[i])} > hi={float(hi[i])}")
        else:
            absent.append(f"axis {axis}:")
    return present, absent


def _assert_inversion_error(excinfo, lo, hi) -> None:
    msg = str(excinfo.value)
    assert msg.startswith("inverted region request (lo > hi): "), msg
    present, absent = _inversion_pattern(lo, hi)
    for fragment in present:
        assert fragment in msg, (fragment, msg)
    for label in absent:
        assert label not in msg, (label, msg)


@pytest.mark.parametrize(
    ("lo", "hi", "halo"),
    [c[1:] for c in INVERTED_REQUESTS],
    ids=[c[0] for c in INVERTED_REQUESTS],
)
def test_inverted_request_is_rejected(lo, hi, halo):
    with pytest.raises(ValueError, match=r"inverted region request") as excinfo:
        read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo)
    _assert_inversion_error(excinfo, lo, hi)


@pytest.mark.parametrize(
    ("lo", "hi", "halo"),
    [c[1:] for c in INVERTED_REQUESTS],
    ids=[c[0] for c in INVERTED_REQUESTS],
)
def test_inverted_request_is_rejected_before_the_plotfile_is_opened(
    tmp_path, lo, hi, halo
):
    # A path that does not exist: if the check ran after yt.load, this would be a load error.
    with pytest.raises(ValueError, match=r"inverted region request") as excinfo:
        read_field_snapshot(tmp_path / "no_such_plotfile", lo=lo, hi=hi, halo=halo)
    _assert_inversion_error(excinfo, lo, hi)


@pytest.mark.parametrize(
    ("lo", "hi", "halo"),
    [c[1:] for c in INVERTED_REQUESTS],
    ids=[c[0] for c in INVERTED_REQUESTS],
)
def test_inverted_request_is_rejected_before_yt_is_imported(monkeypatch, lo, hi, halo):
    # sys.modules[name] = None makes `import yt` raise ImportError, so a check placed between the
    # import and yt.load surfaces as ImportError rather than the inversion error.
    monkeypatch.setitem(sys.modules, "yt", None)
    with pytest.raises(ValueError, match=r"inverted region request") as excinfo:
        read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo)
    _assert_inversion_error(excinfo, lo, hi)


@pytest.mark.parametrize(
    ("lo", "hi", "halo", "legacy_expected", "expected"),
    [c[1:] for c in DIVERGENCE_CASES],
    ids=[c[0] for c in DIVERGENCE_CASES],
)
def test_region_divergence_from_legacy_is_pinned(
    lo, hi, halo, legacy_expected, expected
):
    # Three sides, each against a recorded literal, so the divergence is asserted rather than
    # merely tolerated: the frozen pre-refactor copy, this reader, and the wrapper. The importable
    # extract_eulerian_box delegates here, so it is NOT the legacy side -- comparing against it
    # would be a self-comparison (design.md D1, D10).
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    want = _legacy()(str(FIXTURE), lo=lo, hi=hi, halo=halo)
    assert want["u"].shape == legacy_expected
    snap = read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo)
    assert (snap.x.size, snap.y.size, snap.z.size) == expected
    got = extract_eulerian_box(str(FIXTURE), lo=lo, hi=hi, halo=halo)
    assert got["u"].shape == expected

    # A count-correct but wrong cell must fail: every cell the wrapper returns is a contiguous
    # sub-block of the frozen copy's, with identical coordinates and values, and on an axis where
    # the request lies wholly outside the domain the halo reaches in from THAT edge -- so the
    # block sits at the frozen copy's edge-facing end (above: cell N-1, never N-2).
    dle, dre = CENTERS[0] - 0.5, CENTERS[-1] + 0.5
    block = []
    for i, axis in enumerate(("x", "y", "z")):
        n = got[axis].size
        start = 0
        if n:
            (hits,) = np.nonzero(want[axis] == got[axis][0])
            assert hits.size == 1, axis
            start = int(hits[0])
            if lo[i] > dre:
                assert start + n == want[axis].size, axis
            elif hi[i] <= dle:
                assert start == 0, axis
        np.testing.assert_array_equal(
            got[axis], want[axis][start : start + n], err_msg=axis
        )
        block.append(np.arange(start, start + n))
    for name in ("u", "v", "w", "gradpx", "gradpy", "gradpz"):
        np.testing.assert_array_equal(
            got[name], want[name][np.ix_(*block)], err_msg=name
        )
    for key, value in got.items():
        if isinstance(value, np.ndarray):
            assert value.flags.writeable, key


def _legacy_bounds(lo, hi, halo, dle, dre, n):
    # A literal transcription of the legacy stress_integral arithmetic (clamp the corners onto the
    # domain, THEN pad) -- deliberately a different formula from the one under test.
    dx = (dre - dle) / n
    lo_c = np.clip(lo, dle, dre)
    hi_c = np.clip(hi, dle, dre)
    i_lo = np.maximum(np.floor((lo_c - dle) / dx).astype(np.int64) - halo, 0)
    i_hi = np.minimum(
        np.maximum(np.ceil((hi_c - dle) / dx).astype(np.int64) + halo, i_lo + 1), n
    )
    return i_lo, i_hi


def _grid_values(dle, dre, n):
    # Cell faces (in and beyond the domain) and 1/4 ULPs either side of each, quarter-cell
    # points, both edges +/- 1e-12, far-away values, and +/-inf.
    dx = (dre - dle) / n
    faces = dle + np.arange(-3, n + 4) * dx
    near = [faces]
    for direction in (-np.inf, np.inf):
        v = faces
        for _ in range(4):
            v = np.nextafter(v, direction)
            near.append(v)
    quarters = dle + np.arange(-12, 4 * n + 13) / 4 * dx
    extras = np.array(
        [
            dle - 1e-12,
            dle + 1e-12,
            dre - 1e-12,
            dre + 1e-12,
            dle - 100 * dx,
            dre + 100 * dx,
        ]
    )
    return np.unique(np.concatenate([*near, quarters, extras, [-_INF, _INF]]))


#: (id, domain_left_edge, domain_right_edge, cells, halos). The unit grid is the fixture's; the
#: others exercise halos far larger than 6 cells allow and a non-unit, offset, inexact spacing.
SWEEP_GRIDS = [
    ("unit_6", 0.0, 6.0, 6, range(4)),
    ("unit_24_large_halo", 0.0, 24.0, 24, range(10)),
    ("offset_nonunit_20", -3.7, 2.3, 20, range(5)),
]


def _sweep(dle, dre, n, halos):
    from mosquito_cfd.field_surrogate.snapshot import _region_bounds

    vals = _grid_values(dle, dre, n)
    lo, hi = (a.ravel() for a in np.meshgrid(vals, vals, indexing="ij"))
    for halo in halos:
        new = _region_bounds(
            lo, hi, halo, dle=np.float64(dle), dre=np.float64(dre), ddims=np.int64(n)
        )
        yield lo, hi, halo, new, _legacy_bounds(lo, hi, halo, dle, dre, n)


@pytest.mark.parametrize(
    ("dle", "dre", "n", "halos"),
    [g[1:] for g in SWEEP_GRIDS],
    ids=[g[0] for g in SWEEP_GRIDS],
)
def test_region_arithmetic_matches_legacy_wherever_the_request_meets_the_domain(
    dle, dre, n, halos
):
    # The spec's parity region is lo <= hi, lo <= dre and hi > dle; the public reader rejects
    # lo > hi before reaching this helper. The helper itself is unchanged, so it is held to the
    # SUPERSET lo <= dre and hi > dle here, inverted pairs included. Every pair of the swept
    # values, so a divergence cannot hide between the hand-picked REGION_CASES.
    for lo, hi, halo, (n_lo, n_hi), (o_lo, o_hi) in _sweep(dle, dre, n, halos):
        parity = (lo <= dre) & (hi > dle)
        new_count = np.maximum(n_hi - n_lo, 0)
        old_count = np.maximum(o_hi - o_lo, 0)
        bad = parity & ((new_count != old_count) | ((new_count > 0) & (n_lo != o_lo)))
        assert not bad.any(), (halo, lo[bad][:3], hi[bad][:3])


@pytest.mark.parametrize(
    ("dle", "dre", "n", "halos"),
    [g[1:] for g in SWEEP_GRIDS],
    ids=[g[0] for g in SWEEP_GRIDS],
)
def test_region_arithmetic_never_returns_more_cells_than_legacy(dle, dre, n, halos):
    # Outside the parity region the new rule may return FEWER cells (it drops edge cells the
    # legacy clamp invented for a far-away request), but never more; for a non-inverted request
    # its range lies inside legacy's. The helper's own contract is ordered bounds in [0, n], so
    # `i_hi - i_lo` is always a valid cell count.
    for lo, hi, halo, (n_lo, n_hi), (o_lo, o_hi) in _sweep(dle, dre, n, halos):
        new_count = n_hi - n_lo
        grew = new_count > np.maximum(o_hi - o_lo, 0)
        assert not grew.any(), (halo, lo[grew][:3], hi[grew][:3])
        outside = (lo <= hi) & (new_count > 0) & ((n_lo < o_lo) | (n_hi > o_hi))
        assert not outside.any(), (halo, lo[outside][:3], hi[outside][:3])
        unordered = ~((0 <= n_lo) & (n_lo <= n_hi) & (n_hi <= n))
        assert not unordered.any(), (halo, lo[unordered][:3], hi[unordered][:3])


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


def test_point_cloud_cell_volume_is_the_product_of_all_three_spacings():
    # The fixture is isotropic (dx = 1 on every axis), so dx[0]**3 and prod(dx) agree on it and
    # an axis-dropping bug is invisible. Real decks are not guaranteed isotropic.
    from types import MappingProxyType

    from mosquito_cfd.field_surrogate.snapshot import FieldSnapshot

    snap = FieldSnapshot(
        arrays=MappingProxyType({}),
        x=np.array([0.5, 1.5]),
        y=np.array([1.0]),
        z=np.array([1.5, 4.5, 7.5]),
        dx=np.array([1.0, 2.0, 3.0]),
        time=0.0,
        source="synthetic",
        max_level=0,
        field_names=(),
    )
    np.testing.assert_array_equal(snap.to_point_cloud().cell_volume, np.full(6, 6.0))


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


def test_genuine_fp32_plotfile_is_refused(tmp_path, monkeypatch):
    # Task 46/47. The original guard inspected the RETURNED array's dtype, which can never be
    # float32: yt's AMReX frontend allocates its output buffers float64 unconditionally and
    # widens the on-disk FAB into them. Verified on this very fixture -- ds.index._dtype is
    # float32 while cg[...].to_ndarray().dtype is float64 and the values carry ~1.9e-07 of fp32
    # truncation. A stub returning a float32 array tests the branch, not the property.
    fp32 = _fixture_generator().write_fixture(
        tmp_path / "plt_fp32", real_dtype="float32"
    )
    log = _patch_yt(monkeypatch, path=fp32)
    with pytest.raises(ValueError, match="not 8-byte floats"):
        read_field_snapshot(fp32, **FULL)
    # The refusal must precede any read: a 512-cubed fp32 plotfile would otherwise be read in
    # full -- gigabytes, minutes -- before being rejected. Every neighbouring validation pins
    # this; the precision guard was the only one that did not, and moving it after the read
    # loop left the whole suite green.
    assert log == []


def test_fp64_plotfile_still_accepted(tmp_path):
    # Positive control: an implementation that refused everything would pass the test above.
    # Assert on the VALUES, not on `.dtype == float64` -- the array is built by
    # np.array(..., dtype=np.float64), so a dtype assertion here could never fail.
    fp64 = _fixture_generator().write_fixture(tmp_path / "plt_fp64")
    snap = read_field_snapshot(fp64, **FULL)
    _, gy, _ = np.meshgrid(CENTERS, CENTERS, CENTERS, indexing="ij")
    np.testing.assert_allclose(snap.arrays["u"], -OMEGA * gy)


def test_big_endian_double_plotfile_is_accepted(tmp_path):
    # Regression guard for a false reject introduced by the precision fix itself. yt reports
    # big-endian doubles as `>f8`, and np.dtype(">f8") != np.float64 on a little-endian host --
    # so an equality check rejected a bit-exactly valid FP64 plotfile while blaming an "fp32
    # build" the user does not have. yt's own source documents this descriptor as DOUBLE data.
    be = _fixture_generator().write_fixture(
        tmp_path / "plt_be64", real_dtype="big_endian_float64"
    )
    snap = read_field_snapshot(be, **FULL)
    gx, gy, _ = np.meshgrid(CENTERS, CENTERS, CENTERS, indexing="ij")
    np.testing.assert_array_equal(snap.arrays["u"], -OMEGA * gy)
    np.testing.assert_array_equal(snap.arrays["v"], OMEGA * gx)


def test_empty_field_selection_is_accepted(monkeypatch):
    # Review correction: fields=() was already accepted by _validate_fields (an empty tuple has
    # no unknown/duplicate names) and by to_point_cloud()'s `if self.field_names: ... else:
    # np.empty((n, 0))` branch, but had no test pinning that this is the intended contract rather
    # than an accidental gap. Zero fields still means zero reads.
    log = _patch_yt(monkeypatch)
    snap = read_field_snapshot(FIXTURE, **FULL, fields=())
    assert snap.field_names == ()
    assert dict(snap.arrays) == {}
    assert log == []

    pc = snap.to_point_cloud()
    assert pc.coords.shape == (216, 3)
    assert pc.values.shape == (216, 0)
    assert pc.values.flags.writeable is False


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
    [
        (-1, "non-negative"),
        (-5, "non-negative"),
        (1.9, "integer"),
        (0.5, "integer"),
        # bool is an int subclass, so without the explicit isinstance(halo, bool) clause
        # halo=True would silently mean halo=1. Dropping that clause alone left the whole
        # suite green until these two cases existed.
        (True, "integer"),
        (False, "integer"),
    ],
    ids=["negative", "very_negative", "fractional", "half", "true", "false"],
)
def test_invalid_halo_is_rejected(halo, match):
    # Task 50. A negative halo silently eroded the region (halo=-5 silently returned ZERO cells);
    # a fractional halo truncates per face, so halo=1.9 padded 2 cells low and 1 high -- an
    # asymmetric stencil pad, wrong for anything differentiating across it.
    with pytest.raises(ValueError, match=match):
        read_field_snapshot(FIXTURE, lo=(2.2,) * 3, hi=(3.4,) * 3, halo=halo)


@pytest.mark.parametrize(
    ("halo", "shown"),
    [(np.float64(1.9), "1.9"), (np.bool_(True), "True"), (1.9, "1.9"), ("2", "'2'")],
    ids=["np_float64", "np_bool", "float", "str"],
)
def test_invalid_halo_message_shows_the_plain_value(halo, shown):
    # numpy scalars are shown as their plain Python value, never numpy 2's "np.float64(1.9)" repr,
    # the same as the step and box_margin messages (harden-field-corpus-requests, #140 review).
    with pytest.raises(ValueError, match=r"^halo must be an integer, got ") as excinfo:
        read_field_snapshot(FIXTURE, lo=(2.2,) * 3, hi=(3.4,) * 3, halo=halo)
    assert str(excinfo.value).endswith(f"got {shown}"), str(excinfo.value)


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


# --- PR B, tasks 20-22: the delegation guards ------------------------------------------------


@functools.cache
def _legacy():
    spec = importlib.util.spec_from_file_location(
        "_legacy_extract", FIXTURE.parent / "legacy_extract_eulerian_box.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.legacy_extract_eulerian_box


LEGACY_KEYS = sorted(
    ["u", "v", "w", "gradpx", "gradpy", "gradpz", "x", "y", "z", "dx", "current_time"]
)


@pytest.mark.parametrize(
    ("lo", "hi", "halo", "_expected"),
    [c[1:] for c in REGION_CASES],
    ids=[c[0] for c in REGION_CASES],
)
def test_extract_eulerian_box_matches_the_frozen_pre_refactor_oracle(
    lo, hi, halo, _expected
):
    # Differential, NOT self-referential: the oracle is a byte-for-byte copy of the pre-refactor
    # implementation. Comparing the wrapper to a re-pack of read_field_snapshot would be
    # tautological once the wrapper IS that re-pack (design.md D10).
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    got = extract_eulerian_box(str(FIXTURE), lo=lo, hi=hi, halo=halo)
    want = _legacy()(str(FIXTURE), lo=lo, hi=hi, halo=halo)

    # Exact key set, so no snapshot-only field (time/source/max_level) can leak in.
    assert sorted(got) == LEGACY_KEYS
    assert sorted(got) == sorted(want)

    for key in LEGACY_KEYS:
        if key == "current_time":
            # Type erosion to np.float64 would pass assert_array_equal while changing the
            # published contract.
            assert type(got[key]) is type(want[key]) is float
            assert got[key] == want[key]
        else:
            assert isinstance(got[key], np.ndarray), key
            assert got[key].dtype == want[key].dtype == np.float64, key
            assert got[key].shape == want[key].shape, key
            # Writeability is part of the contract and invisible to value equality; assert it
            # for every region, not just the full-extent one.
            assert got[key].flags.writeable == want[key].flags.writeable is True, key
            np.testing.assert_array_equal(got[key], want[key], err_msg=key)


#: Requests the pre-refactor adapter accepted and the wrapper now refuses (design.md D1; the
#: CHANGELOG states these narrowings). Each names the message of the guard that must fire, so a
#: different guard rejecting it for an unrelated reason does not count.
NARROWED_REQUESTS = [
    ("nan_corner", {"lo": (np.nan, 0.0, 0.0), "hi": (6.0,) * 3}, "NaN"),
    ("nan_in_z", {"lo": (0.0, 0.0, np.nan), "hi": (6.0,) * 3}, "NaN"),
    ("nan_in_hi", {"lo": (0.0,) * 3, "hi": (6.0, np.nan, 6.0)}, "NaN"),
    # The scalar message must name the remedy: legacy broadcast `lo=-np.inf` as "full extent".
    ("scalar_lo", {"lo": 0.0, "hi": (6.0,) * 3}, r"3-vector.*\(-inf,\)\*3"),
    ("scalar_hi", {"lo": (0.0,) * 3, "hi": 6.0}, r"3-vector.*\(inf,\)\*3"),
    # Legacy returned one cell here; the wrapper inherits the reader's rejection
    # (harden-field-corpus-requests D1).
    (
        "inverted",
        {"lo": (4.0,) * 3, "hi": (2.0,) * 3},
        r"inverted region request \(lo > hi\)",
    ),
    ("negative_halo", {**FULL, "halo": -1}, "non-negative"),
    ("fractional_halo", {**FULL, "halo": 1.9}, "integer"),
    ("bool_halo", {**FULL, "halo": True}, "integer"),
    # Integral but not an integer TYPE: the old adapter computed the same cells; refused anyway.
    ("integral_float_halo", {**FULL, "halo": 2.0}, "integer"),
    ("zero_d_array_halo", {**FULL, "halo": np.array(2)}, "integer"),
    ("fp32_plotfile", FULL, "not 8-byte floats"),
]


# The frozen copy floors a NaN corner straight into an int64 cast, so numpy warns there; that is
# the old behaviour being pinned, not something to surface on every run.
@pytest.mark.filterwarnings("ignore:invalid value encountered in cast:RuntimeWarning")
@pytest.mark.parametrize(
    ("case", "kwargs", "match"),
    NARROWED_REQUESTS,
    ids=[c[0] for c in NARROWED_REQUESTS],
)
def test_wrapper_argument_narrowing_is_pinned(case, kwargs, match, tmp_path):
    # Pinned on BOTH sides: the frozen pre-refactor copy accepts each request (the fp32 one
    # silently, as upcast float64), and the wrapper refuses it -- so each is a recorded narrowing,
    # not merely a claim. The reader's own validation tests call read_field_snapshot directly, so
    # they cannot see a wrapper that sanitizes its arguments before delegating.
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    path = FIXTURE
    if case == "fp32_plotfile":
        path = _fixture_generator().write_fixture(
            tmp_path / "plt_fp32", real_dtype="float32"
        )
    legacy = _legacy()(str(path), **kwargs)
    assert sorted(legacy) == LEGACY_KEYS
    with pytest.raises(ValueError, match=match):
        extract_eulerian_box(str(path), **kwargs)


#: The committed fixture is cubic, origin 0, dx 1, with w and every gradp* identically zero, so a
#: wrapper that permuted fields or axes passed every test above (review of #106: S1-S4). This
#: variant is written to tmp_path -- the committed fixture and the hash-pinned oracle are
#: untouched. Dyadic origin and spacing keep every face exact (a non-dyadic origin makes yt itself
#: refuse the full-domain covering grid).
ASYM = {
    "shape": (8, 6, 4),
    "origin": (-2.0, 0.5, 1.25),
    "dx": (0.5, 0.25, 1.0),
    "distinct_fields": True,
}
ASYM_REQUESTS = [
    ("full", (-_INF,) * 3, (_INF,) * 3, 0),
    ("interior", (-1.1, 0.8, 2.0), (1.3, 1.6, 4.5), 0),
    ("x_slab", (-0.6, -_INF, -_INF), (1.2, _INF, _INF), 0),
    ("upper_corner_halo1", (1.6, 1.9, 4.5), (_INF,) * 3, 1),
    ("lower_corner_point_halo2", (-2.0, 0.5, 1.25), (-2.0, 0.5, 1.25), 2),
]


@pytest.fixture(scope="module")
def asym_plotfile(tmp_path_factory):
    root = tmp_path_factory.mktemp("asym") / "plt_asym"
    return _fixture_generator().write_fixture(root, **ASYM)


@pytest.mark.parametrize(
    ("lo", "hi", "halo"),
    [c[1:] for c in ASYM_REQUESTS],
    ids=[c[0] for c in ASYM_REQUESTS],
)
def test_wrapper_maps_every_field_and_axis_on_an_asymmetric_grid(
    asym_plotfile, lo, hi, halo
):
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    got = extract_eulerian_box(str(asym_plotfile), lo=lo, hi=hi, halo=halo)
    want = _legacy()(str(asym_plotfile), lo=lo, hi=hi, halo=halo)
    assert sorted(got) == LEGACY_KEYS
    for key in LEGACY_KEYS:
        np.testing.assert_array_equal(got[key], want[key], err_msg=key)

    # Independently of the oracle: spacing per axis, centres on the per-axis lattice, and every
    # field equal to its own analytic formula (literals here, not the generator's code).
    np.testing.assert_array_equal(got["dx"], ASYM["dx"])
    for i, axis in enumerate(("x", "y", "z")):
        lattice = (
            ASYM["origin"][i] + (np.arange(ASYM["shape"][i]) + 0.5) * ASYM["dx"][i]
        )
        assert got[axis].size > 0, axis
        assert np.isin(got[axis], lattice).all(), axis
        np.testing.assert_allclose(np.diff(got[axis]), ASYM["dx"][i], err_msg=axis)
    x, y, z = np.meshgrid(got["x"], got["y"], got["z"], indexing="ij")
    analytic = {
        "u": -1.3 * y,
        "v": 1.3 * x,
        "w": 0.7 * z,
        "gradpx": 0.11 * x + 1.0,
        "gradpy": -0.23 * y + 2.0,
        "gradpz": 0.37 * z + 3.0,
    }
    for name, expected in analytic.items():
        np.testing.assert_allclose(got[name], expected, rtol=1e-12, err_msg=name)


def test_wrapper_refuses_to_unfreeze_a_view(monkeypatch):
    # The wrapper makes its arrays writable, which is safe only because the reader copies. If the
    # reader ever returned a view, setflags(write=True) would un-freeze shared state; the wrapper
    # must refuse instead.
    import types

    import mosquito_cfd.field_surrogate.snapshot as snapshot_mod
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    real = read_field_snapshot(FIXTURE, **FULL)
    shared = np.zeros((6, 6, 6))
    view = shared[:]
    view.setflags(write=False)
    fake = types.SimpleNamespace(
        arrays={**real.arrays, "u": view},
        x=real.x,
        y=real.y,
        z=real.z,
        dx=real.dx,
        time=real.time,
    )
    monkeypatch.setattr(snapshot_mod, "read_field_snapshot", lambda *a, **k: fake)
    with pytest.raises(RuntimeError, match="view"):
        extract_eulerian_box(str(FIXTURE), **FULL)
    assert not view.flags.writeable


def test_matrix_shaped_corner_now_fails_with_a_clear_error():
    # NOT a narrowing -- the pre-refactor adapter already failed on a (1, 3) corner, just with an
    # opaque TypeError from deep in its slicing. Pinned separately from NARROWED_REQUESTS, whose
    # premise is that the frozen copy accepted the request.
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    kwargs = {"lo": [[0.0, 0.0, 0.0]], "hi": (6.0,) * 3}
    with pytest.raises(TypeError):
        _legacy()(str(FIXTURE), **kwargs)
    with pytest.raises(ValueError, match="3-vector"):
        extract_eulerian_box(str(FIXTURE), **kwargs)


def test_numpy_integer_halo_is_still_accepted():
    # Positive control for the narrowing above: a numpy integer halo is an integer and must keep
    # working exactly as before. Without this, tightening the type check to the builtin int
    # would be an unrecorded new narrowing.
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    kwargs = {"lo": (1.0,) * 3, "hi": (3.0,) * 3, "halo": np.int64(1)}
    got = extract_eulerian_box(str(FIXTURE), **kwargs)
    want = _legacy()(str(FIXTURE), **kwargs)
    assert got["u"].shape == want["u"].shape == (4, 4, 4)
    for key in ("u", "x", "y", "z"):
        np.testing.assert_array_equal(got[key], want[key], err_msg=key)


def test_internal_call_sites_still_resolve_the_module_global(monkeypatch):
    # Tests replace this module global; an internal call site that stopped resolving it would
    # bypass them all, leaving tests green while testing nothing (design.md D3).
    import mosquito_cfd.benchmarks.stress_integral as si

    class _Sentinel(Exception):
        pass

    def _boom(*args, **kwargs):
        raise _Sentinel()

    monkeypatch.setattr(si, "extract_eulerian_box", _boom)

    with pytest.raises(_Sentinel):
        si.sphere_cv_drag_cd(str(FIXTURE), x_inlet=1.0, x_outlet=4.0)
    with pytest.raises(_Sentinel):
        si.check_field_capture_velocity(str(FIXTURE))
    with pytest.raises(_Sentinel):
        si.sphere_cv_steadiness_fraction(
            str(FIXTURE), str(FIXTURE), x_inlet=1.0, x_outlet=4.0, dt=0.1
        )


def test_nan_and_inf_field_values_pass_through_bit_identically(monkeypatch):
    # check_field_capture_velocity's six NaN/Inf tests all monkeypatch the reader away, so none
    # of them exercise the read path. If the reader -- or the wrapper that guard actually calls
    # -- ever normalized values, the guard would stop seeing what it expects.
    import yt

    import mosquito_cfd.benchmarks.stress_integral as si

    real_load = yt.load
    # -0.0 rides along: assert_array_equal cannot tell it from +0.0, the uint64 view can.
    poisoned = np.array([np.nan, np.inf, -np.inf, -0.0, 1.5])

    class _Unyt:
        # Minimal stand-in for yt's unyt_array: the reader unwraps via .d (a view), as
        # unyt does; to_ndarray() is kept for any other caller.
        def __init__(self, array):
            self._array = array

        def to_ndarray(self):
            return self._array.copy()

        @property
        def d(self):
            return self._array

    class _PoisonGrid:
        def __init__(self, inner):
            self._inner = inner

        def __getitem__(self, key):
            value = self._inner[key].to_ndarray().copy()
            value.reshape(-1)[: poisoned.size] = poisoned
            return _Unyt(value)

        # Forwarded for the reader's cache release (improve-field-reader-perf-memory D4).
        @property
        def field_data(self):
            return self._inner.field_data

        def clear_data(self):
            self._inner.clear_data()

    class _PoisonDataset:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def covering_grid(self, *args, **kwargs):
            return _PoisonGrid(self._inner.covering_grid(*args, **kwargs))

    monkeypatch.setattr(
        yt, "load", lambda p, *a, **k: _PoisonDataset(real_load(str(p)))
    )

    snap = read_field_snapshot(FIXTURE, **FULL)
    box = si.extract_eulerian_box(str(FIXTURE), **FULL)
    want = poisoned.view(np.uint64)
    for name in ("u", "v", "w"):
        for source, arrays in (("reader", snap.arrays), ("wrapper", box)):
            got = arrays[name].reshape(-1)[: poisoned.size].view(np.uint64)
            np.testing.assert_array_equal(got, want, err_msg=f"{source}:{name}")

    # End to end: the guard the passthrough exists for still fires through the real read path.
    with pytest.raises(ValueError, match="NaN or Inf"):
        si.check_field_capture_velocity(str(FIXTURE))


def test_legacy_wrapper_returns_writable_arrays_like_the_oracle():
    # Kept as a focused smoke check; writeability is asserted across the WHOLE clamping matrix
    # inside test_extract_eulerian_box_matches_the_frozen_pre_refactor_oracle, because a single
    # region is thin for "the thing array equality cannot see".
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    got = extract_eulerian_box(str(FIXTURE), **FULL)
    got["u"][0, 0, 0] = 1234.5  # must not raise


def test_amr_refusal_propagates_through_the_legacy_wrapper(monkeypatch):
    # The PR B half of the AMR guard: pre-delegation the wrapper raised its own message, so this
    # assertion only becomes meaningful once extract_eulerian_box delegates.
    from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

    log = _patch_yt(monkeypatch, max_level=1)
    with pytest.raises(ValueError, match="CC-F3"):
        extract_eulerian_box(str(FIXTURE), **FULL)
    assert log == []


# --- PR B review corrections -----------------------------------------------------------------

#: SHA-256 of the frozen oracle's RAW BYTES. An earlier version normalized newlines on the
#: premise that `* text=auto` gives this file CRLF in a Windows checkout. That was wrong:
#: `.gitattributes` pins `*.py text eol=lf`, so it is LF in every working tree regardless of
#: `core.autocrlf` (verified with `git check-attr`). Hashing raw bytes is both correct and
#: stricter -- it also catches a CRLF conversion, which would mean the eol=lf rule had been
#: dropped, exactly when you would want to know.
_ORACLE_SHA256 = "3e26a665006a46b0d3e1ca1ea458072d8ec8e1ee69bfbead571cf8c664099c93"


def test_frozen_oracle_is_unmodified():
    # The oracle's entire value is that it is a byte-for-byte copy of the pre-refactor
    # implementation. Nothing else stops `ruff format`, `ruff check --fix`, or a ruff version
    # bump from rewriting it -- and if that happened, the differential above would silently
    # become a comparison against post-hoc-modified code with no test failing. A content hash
    # is squash-merge-safe; a `git show <sha>` check is not (this repo squash-merges).
    path = FIXTURE.parent / "legacy_extract_eulerian_box.py"
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == _ORACLE_SHA256, (
        "the frozen oracle changed. It must NOT be edited, reformatted or linted -- it is a "
        "copy of the pre-refactor implementation taken at 86c729e. If the change was "
        "deliberate, the delegation's equivalence claim no longer means what it says."
    )


# --- improve-field-reader-perf-memory: bit-identity against a full-grid reference --------------


def _ab_script():
    # scripts/ is not a package; _map is the A/B script's cell-unit -> physical mapping, reused so
    # the cases mean the same thing here as in the real-plotfile verification.
    spec = importlib.util.spec_from_file_location(
        "_verify_eulerian_box_ab", REPO_ROOT / "scripts" / "verify_eulerian_box_ab.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=4)
def _full_grid_reference(path: str) -> dict:
    """The full level-0 covering grid of all eight fields, read with yt directly, once per file.

    Built independently of ``read_field_snapshot``'s read loop: no cache release, no teardown.
    Only ``_region_bounds`` is shared, and that arithmetic is pinned against the legacy oracle.
    """
    import yt

    from mosquito_cfd.field_surrogate.snapshot import CANONICAL_FIELDS

    yt.set_log_level("error")
    ds = yt.load(path)
    dle = np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64)
    dre = np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64)
    ddims = np.asarray(ds.domain_dimensions, dtype=np.int64)
    cg = ds.covering_grid(
        level=0, left_edge=ds.domain_left_edge, dims=tuple(int(d) for d in ddims)
    )
    data = {
        name: np.array(cg[field].to_ndarray(), copy=True)
        for name, field in CANONICAL_FIELDS.items()
    }
    return {
        "data": data,
        "dle": dle,
        "dre": dre,
        "ddims": ddims,
        "dx": (dre - dle) / ddims,
        "time": float(ds.current_time),
        "max_level": int(ds.index.max_level),
    }


def _frozen_copy(view: np.ndarray) -> np.ndarray:
    out = np.array(view, dtype=np.float64, order="C", copy=True)
    out.setflags(write=False)
    return out


def _expected_snapshot(path, lo, hi, halo) -> dict:
    from mosquito_cfd.field_surrogate.snapshot import _corner, _region_bounds

    ref = _full_grid_reference(str(path))
    i_lo, i_hi = _region_bounds(
        _corner(lo, "lo"),
        _corner(hi, "hi"),
        halo,
        dle=ref["dle"],
        dre=ref["dre"],
        ddims=ref["ddims"],
    )
    sl = tuple(slice(int(a), int(b)) for a, b in zip(i_lo, i_hi))
    axes = []
    for axis in range(3):
        # The reader's own arithmetic: a linspace reference differs by an ULP on non-dyadic grids.
        centers = (
            ref["dle"][axis] + (np.arange(ref["ddims"][axis]) + 0.5) * ref["dx"][axis]
        )
        axes.append(_frozen_copy(centers[sl[axis]]))
    return {
        "arrays": {name: _frozen_copy(a[sl]) for name, a in ref["data"].items()},
        "x": axes[0],
        "y": axes[1],
        "z": axes[2],
        "dx": ref["dx"],
        "time": ref["time"],
        "max_level": ref["max_level"],
    }


def _assert_same_array(got: np.ndarray, want: np.ndarray, tag: str) -> None:
    # Bitwise, not numeric: assert_array_equal treats -0.0 == 0.0 and ignores NaN payloads.
    assert got.dtype == want.dtype == np.float64, tag
    assert got.shape == want.shape, tag
    assert got.tobytes() == want.tobytes(), tag
    assert got.strides == want.strides, tag
    assert got.flags.c_contiguous == want.flags.c_contiguous, tag
    assert got.flags.f_contiguous == want.flags.f_contiguous, tag
    assert got.flags.writeable is False, tag
    assert got.base is None, tag


def _assert_bit_identical(snap, path, lo, hi, halo) -> None:
    from mosquito_cfd.field_surrogate.snapshot import CANONICAL_FIELDS

    want = _expected_snapshot(path, lo, hi, halo)
    assert snap.field_names == tuple(CANONICAL_FIELDS)
    assert list(snap.arrays) == list(CANONICAL_FIELDS)
    for name in CANONICAL_FIELDS:
        _assert_same_array(snap.arrays[name], want["arrays"][name], name)
    for axis in ("x", "y", "z"):
        _assert_same_array(getattr(snap, axis), want[axis], axis)
    assert snap.dx.tobytes() == want["dx"].tobytes()
    assert snap.dx.dtype == np.float64 and snap.dx.shape == (3,)
    assert snap.dx.flags.writeable is False
    assert type(snap.time) is float and snap.time == want["time"]
    assert snap.source == str(path)
    assert type(snap.max_level) is int and snap.max_level == want["max_level"]


ALL_FIELDS = (
    "u",
    "v",
    "w",
    "gradpx",
    "gradpy",
    "gradpz",
    "density",
    "tracer",
)
_BIT_CASES = [(c[0], c[1], c[2], c[3], c[4]) for c in REGION_CASES] + [
    (c[0], c[1], c[2], c[3], c[5]) for c in DIVERGENCE_CASES
]


@pytest.mark.parametrize(
    ("lo", "hi", "halo", "counts"),
    [c[1:] for c in _BIT_CASES],
    ids=[c[0] for c in _BIT_CASES],
)
def test_read_is_bit_identical_to_a_full_grid_reference(
    asym_plotfile, lo, hi, halo, counts
):
    # Anchor for every speed and memory change in improve-field-reader-perf-memory: the cache
    # release, the teardown and the zero-cell short-circuit must not change one bit of what is
    # returned, on the cubic fixture and on an anisotropic, non-zero-origin grid.
    snap = read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo, fields=ALL_FIELDS)
    assert (
        snap.arrays["u"].shape == counts
    )  # the tables' literal counts, not recomputed
    _assert_bit_identical(snap, FIXTURE, lo, hi, halo)

    ref = _full_grid_reference(str(asym_plotfile))
    mapper = _ab_script()._map
    mlo = mapper(lo, ref["dle"], ref["dre"], ref["dx"])
    mhi = mapper(hi, ref["dle"], ref["dre"], ref["dx"])
    snap = read_field_snapshot(
        asym_plotfile, lo=mlo, hi=mhi, halo=halo, fields=ALL_FIELDS
    )
    _assert_bit_identical(snap, asym_plotfile, mlo, mhi, halo)


_REAL_BIT_CASES = (
    "full",
    "halo2",
    "x_slab_only",
    "outside_domain",
    "above_within_reach_offface_h2",
)


@pytest.mark.requires_plotfile
@pytest.mark.parametrize(
    ("lo", "hi", "halo"),
    [c[1:4] for c in _BIT_CASES if c[0] in _REAL_BIT_CASES],
    ids=[c[0] for c in _BIT_CASES if c[0] in _REAL_BIT_CASES],
)
def test_real_multi_fab_read_is_bit_identical_to_a_full_grid_reference(lo, hi, halo):
    import os

    plotfiles = sorted(
        (Path(os.environ["MOSQUITO_CFD_PLOTFILE_ROOT"]) / "t3c-fine").glob("plt*")
    )
    if not plotfiles:
        pytest.skip("no t3c-fine/plt* under $MOSQUITO_CFD_PLOTFILE_ROOT")
    path = plotfiles[-1]
    ref = _full_grid_reference(str(path))
    mapper = _ab_script()._map
    mlo = mapper(lo, ref["dle"], ref["dre"], ref["dx"])
    mhi = mapper(hi, ref["dle"], ref["dre"], ref["dx"])
    snap = read_field_snapshot(path, lo=mlo, hi=mhi, halo=halo, fields=ALL_FIELDS)
    _assert_bit_identical(snap, path, mlo, mhi, halo)


@pytest.fixture(scope="module", autouse=True)
def _release_full_grid_references():
    # The real t3c-fine reference holds eight full 256x128x256 fields (~1 GB); drop the cache
    # when this module finishes rather than for the rest of the session.
    yield
    _full_grid_reference.cache_clear()


# --- improve-field-reader-perf-memory: guards before the zero-cell short-circuit ---------------

_OUTSIDE = next(c for c in REGION_CASES if c[0] == "outside_domain")
OUTSIDE_DOMAIN = {"lo": _OUTSIDE[1], "hi": _OUTSIDE[2], "halo": _OUTSIDE[3]}


class _IndexWithoutDtype:
    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        if name == "_dtype":
            raise AttributeError(name)
        return getattr(self._inner, name)


class _DatasetWithoutDtype:
    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def index(self):
        return _IndexWithoutDtype(self._inner.index)


@pytest.mark.parametrize(
    "guard", ["multi_level", "no_dtype_attribute", "fp32_on_disk", "missing_field"]
)
def test_guards_fire_before_the_zero_cell_short_circuit(guard, monkeypatch, tmp_path):
    # Anchor (passes before the short-circuit exists): a request with zero cells must still be
    # refused for the same reason as a non-empty one. A short-circuit placed ahead of any guard
    # would return empty arrays from a plotfile the reader refuses to read.
    import yt

    path = FIXTURE
    if guard == "multi_level":
        _patch_yt(monkeypatch, max_level=1)
        match = "CC-F3"
    elif guard == "no_dtype_attribute":
        real_load = yt.load
        monkeypatch.setattr(
            yt, "load", lambda p, *a, **k: _DatasetWithoutDtype(real_load(str(p)))
        )
        match = "cannot determine the plotfile's on-disk precision"
    elif guard == "fp32_on_disk":
        path = _fixture_generator().write_fixture(
            tmp_path / "plt_fp32", real_dtype="float32"
        )
        match = "not 8-byte floats"
    else:
        path = _fixture_generator().write_fixture(
            tmp_path / "plt_reduced", fields=("x_velocity", "y_velocity")
        )
        match = r"missing required fields \[\('boxlib', 'z_velocity'\)"
    with pytest.raises(ValueError, match=match):
        read_field_snapshot(path, **OUTSIDE_DOMAIN)


# --- improve-field-reader-perf-memory: covering-grid release and teardown (#120) ---------------


def test_each_field_leaves_the_covering_grid_cache_once_copied(monkeypatch):
    # #120 / #112 item 3: yt caches every field read through a covering grid in cg.field_data, so
    # a six-field read held all six full-domain buffers at once. Each must be dropped once copied.
    # Checked AT the calls, not after the read: clear_data() empties field_data, so "empty
    # afterwards" holds whether or not the per-field release happened.
    clears: list[int] = []

    class _CacheCheckingGrid(_RecordingGrid):
        def __getitem__(self, key):
            stale = [f for f in self._log if f in self._inner.field_data]
            assert not stale, f"reading {key} with earlier fields still cached: {stale}"
            return super().__getitem__(key)

        def clear_data(self):
            assert not self._inner.field_data, list(self._inner.field_data)
            clears.append(1)
            super().clear_data()

    log = _patch_yt(monkeypatch, grid_cls=_CacheCheckingGrid)
    read_field_snapshot(FIXTURE, **FULL)
    assert len(log) == 6
    assert clears == [1]


class _TrackedField:
    """Stand-in for the yt array a covering grid returns, recording every buffer handed out.

    Offers the two ways the reader may unwrap it: ``to_ndarray()`` (unyt makes a copy) and
    ``.d`` (a view of yt's own buffer). Each handed-out array, and yt's array itself, is
    recorded as ``(weakref, shares_memory_with_yt)``.
    """

    def __init__(self, inner, record):
        import weakref

        self._inner = inner
        self._record = record
        record.append((weakref.ref(inner), True))

    def _hand_out(self, arr):
        import weakref

        self._record.append((weakref.ref(arr), np.shares_memory(arr, self._inner)))
        return arr

    def to_ndarray(self):
        return self._hand_out(self._inner.to_ndarray())

    @property
    def d(self):
        return self._hand_out(self._inner.d)


def _tracking_grid(record):
    class _TrackingGrid(_RecordingGrid):
        def __getitem__(self, key):
            alive = [i for i, (ref, _) in enumerate(record) if ref() is not None]
            assert not alive, f"reading {key} while earlier buffers {alive} are alive"
            return _TrackedField(super().__getitem__(key), record)

    return _TrackingGrid


def test_no_full_domain_buffer_outlives_its_copy(monkeypatch):
    # Refcount-deterministic, unlike the tracemalloc bound: before each field is read, yt's
    # array for every earlier field -- and whatever the reader unwrapped it into -- must already
    # be dead, and none may outlive the call. Kills a reader that keeps `raw` bound until the
    # next iteration, which only adds ~1 S of peak and so passes the 7.5 S bound.
    record: list = []
    _patch_yt(monkeypatch, grid_cls=_tracking_grid(record))
    read_field_snapshot(FIXTURE, **FULL)
    # Positive control: yt's array and one unwrapped array per field were tracked.
    assert len(record) == 12
    assert all(ref() is None for ref, _ in record), "a buffer outlived the call"


def test_fields_are_unwrapped_without_a_full_domain_copy(monkeypatch):
    # unyt's to_ndarray() is np.array(self): a full-domain copy, one more S of peak per field,
    # made only to be sliced and copied again. `.d` is a view of yt's own buffer; the reader's
    # owning slice copy is the only copy it needs.
    record: list = []
    _patch_yt(monkeypatch, grid_cls=_tracking_grid(record))
    read_field_snapshot(FIXTURE, **FULL)
    handed_out = record[1::2]
    assert len(handed_out) == 6
    copies = [i for i, (_, shares) in enumerate(handed_out) if not shares]
    assert not copies, f"fields {copies} were unwrapped into a full-domain copy"


@pytest.fixture(scope="module")
def plotfile_96(tmp_path_factory):
    root = tmp_path_factory.mktemp("p96") / "plt96"
    return _fixture_generator().write_fixture(root, shape=(96, 96, 96))


@pytest.fixture(scope="module")
def plotfile_64(tmp_path_factory):
    root = tmp_path_factory.mktemp("p64") / "plt64"
    return _fixture_generator().write_fixture(root, shape=(64, 64, 64))


def _traced_peak(read) -> int:
    """``tracemalloc`` peak of one call above its starting level, after a warm-up call.

    Automatic GC stays enabled, as in production; a full collection runs before the traced call
    so an earlier read's garbage is not counted. Restores the prior tracing and GC state.
    """
    import gc
    import tracemalloc

    if tracemalloc.is_tracing():
        pytest.skip(
            "tracemalloc is already tracing; a nested trace would be meaningless"
        )
    gc_was_enabled = gc.isenabled()
    try:
        gc.enable()
        read()  # warm-up: yt's lazy imports and per-process caches
        gc.collect()
        tracemalloc.start()
        start = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        result = read()
        peak = tracemalloc.get_traced_memory()[1] - start
        del result
        return peak
    finally:
        tracemalloc.stop()
        if not gc_was_enabled:
            gc.disable()


def test_field_cache_release_bounds_the_peak(plotfile_96):
    # Differential in units of one field's bytes S, never an absolute MB figure: yt's own
    # overhead varies by version and platform, the per-field growth is what this change removes.
    # Measured on 96^3 before the change: 9.7-11.1 S; after: 4.5-5.3 S.
    field_bytes = 8 * 96**3
    one = _traced_peak(lambda: read_field_snapshot(plotfile_96, **FULL, fields=("u",)))
    six = _traced_peak(lambda: read_field_snapshot(plotfile_96, **FULL))
    growth = (six - one) / field_bytes
    assert growth <= 7.5, f"six-field peak exceeds one-field peak by {growth:.2f} S"


def _yt_object_refs(monkeypatch) -> tuple[list, list]:
    """Keep weak references to each REAL yt Dataset and covering grid the reader creates.

    Never to a test proxy around one: a proxy dies on return even while the object it wraps
    lives, which would make the assertion vacuous. The covering grid is tracked separately
    because it holds its dataset only through a ``weakref.proxy``: a reader that dropped the
    dataset but kept the grid would still pass a dataset-only check, while the grid -- in its own
    cycle -- outlived the call.

    Returns:
        ``(datasets, grids)``, lists of weak references in creation order.
    """
    import weakref

    import yt
    from yt.data_objects.construction_data_containers import YTCoveringGrid

    datasets: list = []
    grids: list = []
    real_load = yt.load
    real_init = YTCoveringGrid.__init__

    def load(*args, **kwargs):
        ds = real_load(*args, **kwargs)
        assert type(ds).__module__.startswith("yt."), type(ds)
        datasets.append(weakref.ref(ds))
        return ds

    def init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        grids.append(weakref.ref(self))

    monkeypatch.setattr(yt, "load", load)
    monkeypatch.setattr(YTCoveringGrid, "__init__", init)
    return datasets, grids


def _assert_no_yt_object(snap) -> None:
    values = [getattr(snap, f) for f in snap.__dataclass_fields__]
    values += list(snap.arrays.values())
    for value in values:
        module = type(value).__module__
        assert not module.startswith(("yt", "unyt")), (type(value), value)


def test_dataset_is_dead_when_the_read_returns(plotfile_64, monkeypatch):
    # #120: yt's dataset, index, field-info and covering grid form reference cycles. With
    # automatic GC on they are promoted to the oldest generation during the read, so they -- and
    # every cached field -- outlive the call until Python's next full collection.
    import gc

    datasets, grids = _yt_object_refs(monkeypatch)
    gc_was_enabled = gc.isenabled()
    gc.enable()
    try:
        read_field_snapshot(plotfile_64, **FULL)  # warm-up
        snap = read_field_snapshot(plotfile_64, **FULL)
        assert len(datasets) == 2 and len(grids) == 2
        assert datasets[-1]() is None, "the yt dataset outlived read_field_snapshot"
        assert grids[-1]() is None, "the covering grid outlived read_field_snapshot"
        _assert_no_yt_object(snap)
    finally:
        if not gc_was_enabled:
            gc.disable()


def _mapped_case(name: str, path) -> dict:
    """A REGION_CASES / DIVERGENCE_CASES request, mapped onto ``path``'s domain (cell units)."""
    import yt

    case = next(c for c in REGION_CASES + DIVERGENCE_CASES if c[0] == name)
    yt.set_log_level("error")
    ds = yt.load(str(path))
    dle = np.asarray(ds.domain_left_edge.to_ndarray(), dtype=np.float64)
    dre = np.asarray(ds.domain_right_edge.to_ndarray(), dtype=np.float64)
    dx = (dre - dle) / np.asarray(ds.domain_dimensions, dtype=np.float64)
    mapper = _ab_script()._map
    return {
        "lo": mapper(case[1], dle, dre, dx),
        "hi": mapper(case[2], dle, dre, dx),
        "halo": case[3],
    }


def test_dataset_is_dead_after_a_zero_cell_read(plotfile_64, monkeypatch):
    # Anchor (task 4.3): the zero-cell half of the test above. It passes before the zero-cell
    # short-circuit exists, because that request still takes the full read path; once the
    # short-circuit lands it pins that the early return still tears down.
    import gc

    request = _mapped_case("outside_domain", plotfile_64)
    datasets, _ = _yt_object_refs(monkeypatch)
    gc_was_enabled = gc.isenabled()
    gc.enable()
    try:
        read_field_snapshot(plotfile_64, **request)  # warm-up
        snap = read_field_snapshot(plotfile_64, **request)
        assert snap.arrays["u"].shape == (0, 0, 0)
        assert len(datasets) == 2
        assert datasets[-1]() is None, "the yt dataset outlived a zero-cell read"
        _assert_no_yt_object(snap)
    finally:
        if not gc_was_enabled:
            gc.disable()


_ZERO_CELL_CASES = [
    "upper_edge",
    "outside_domain",
    "above_beyond_reach_h2",
    "x_below_yz_inside_h1",  # empty on x only: kills an any -> all mutant
]


@pytest.mark.parametrize("case", _ZERO_CELL_CASES)
def test_zero_cell_region_reads_nothing(case, monkeypatch):
    # #112 item 5: a region with zero cells on any axis read the full covering grid of every
    # requested field -- 1.28 GB at 256x128x256 -- to return nothing.
    _, lo, hi, halo, *_ = next(
        c for c in REGION_CASES + DIVERGENCE_CASES if c[0] == case
    )
    _full_grid_reference(
        str(FIXTURE)
    )  # build the reference BEFORE the proxy is installed
    grid_log: list = []
    log = _patch_yt(monkeypatch, grid_log=grid_log)
    snap = read_field_snapshot(FIXTURE, lo=lo, hi=hi, halo=halo, fields=ALL_FIELDS)
    assert grid_log == [], "a covering grid was built for a zero-cell region"
    assert log == [], "a field was read for a zero-cell region"
    assert 0 in snap.arrays["u"].shape
    _assert_bit_identical(snap, FIXTURE, lo, hi, halo)


def test_zero_cell_read_costs_no_field_sized_memory(plotfile_96):
    # Differential against fields=() on the same request: what is left after the plotfile guards
    # is yt's own overhead, which is not field-sized. Measured on 96^3 before the change: 13.9 S;
    # after the teardown commit alone: 7.9 S.
    field_bytes = 8 * 96**3
    request = _mapped_case("outside_domain", plotfile_96)
    six = _traced_peak(lambda: read_field_snapshot(plotfile_96, **request))
    none = _traced_peak(lambda: read_field_snapshot(plotfile_96, **request, fields=()))
    gap = (six - none) / field_bytes
    assert gap < 1.0, f"a zero-cell read cost {gap:.2f} S more than a no-field read"


# --- improve-field-reader-perf-memory: point cloud (#112 item 5) -------------------------------


def _in_memory_snapshot(shape, dx, k=6):
    from types import MappingProxyType

    from mosquito_cfd.field_surrogate.snapshot import DEFAULT_FIELDS, FieldSnapshot

    names = DEFAULT_FIELDS[:k]
    rng = np.random.default_rng(0)
    return FieldSnapshot(
        arrays=MappingProxyType({n: rng.standard_normal(shape) for n in names}),
        x=(np.arange(shape[0]) + 0.5) * dx[0],
        y=(np.arange(shape[1]) + 0.5) * dx[1],
        z=(np.arange(shape[2]) + 0.5) * dx[2],
        dx=np.asarray(dx, dtype=np.float64),
        time=0.0,
        source="in-memory",
        max_level=0,
        field_names=names,
    )


def _assert_read_only_broadcast(cell_volume: np.ndarray, n: int, volume: float) -> None:
    assert cell_volume.shape == (n,)
    assert cell_volume.dtype == np.float64
    assert cell_volume.strides == (0,)
    np.testing.assert_array_equal(cell_volume, np.full(n, volume))
    assert cell_volume.flags.writeable is False
    with pytest.raises(ValueError):
        cell_volume.setflags(write=True)
    base = cell_volume.base
    while base is not None:
        assert not getattr(base, "flags", None) or base.flags.writeable is False, base
        base = getattr(base, "base", None)


def test_constant_cell_volume_is_a_read_only_broadcast():
    # #112 item 5: a constant cell volume was an N-element buffer of one repeated value -- 67 MB
    # at 256x128x256. A zero-stride broadcast of a read-only 0-d array costs 8 bytes.
    snap = _in_memory_snapshot((2, 1, 3), (1.0, 2.0, 3.0))
    _assert_read_only_broadcast(snap.to_point_cloud().cell_volume, 6, 6.0)

    zero = read_field_snapshot(FIXTURE, **OUTSIDE_DOMAIN).to_point_cloud()
    _assert_read_only_broadcast(zero.cell_volume, 0, 1.0)


def test_point_cloud_peak_is_its_outputs():
    # coords and values must coexist at the peak; the meshgrid temporaries (3 N-element arrays)
    # and a dense cell_volume must not. Measured at 64^3 before the change: 1.44 x outputs.
    snap = _in_memory_snapshot((64, 64, 64), (1.0, 1.0, 1.0))
    pc = snap.to_point_cloud()
    outputs = pc.coords.nbytes + pc.values.nbytes
    del pc
    peak = _traced_peak(snap.to_point_cloud)
    assert peak <= 1.02 * outputs + 64 * 1024, f"peak {peak / outputs:.3f} x outputs"
