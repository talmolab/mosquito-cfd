"""Tests for mosquito_cfd.field_surrogate.snapshot (F2, add-field-surrogate-reader)."""

from __future__ import annotations

import ast
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

#: AGREEMENT cases: requests where read_field_snapshot and the frozen pre-refactor
#: extract_eulerian_box (tests/fixtures/legacy_extract_eulerian_box.py) agree -- the parity region
#: of design.md D1, plus three edge points outside it that agree anyway (lower_edge,
#: lower_edge_halo2, just_below_halo1). (id, lo, hi, halo, expected cells per axis). Expected counts are literals derived once from the
#: reference arithmetic, not recomputed with the same formula the reader uses -- that would be
#: tautological. PR B's differential test against the frozen oracle iterates THIS matrix, so every
#: entry here must be one where the two implementations agree; divergences go in
#: DIVERGENCE_CASES below.
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
    ("inverted", (4.0, 4.0, 4.0), (2.0, 2.0, 2.0), 0, (1, 1, 1)),
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
        np.testing.assert_array_equal(got[axis], want[axis][start : start + n], err_msg=axis)
        block.append(np.arange(start, start + n))
    for name in ("u", "v", "w", "gradpx", "gradpy", "gradpz"):
        np.testing.assert_array_equal(got[name], want[name][np.ix_(*block)], err_msg=name)
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
    # The parity region stated in the spec: identical to legacy whenever lo <= dre and hi > dle.
    # Every pair of the swept values, so a divergence cannot hide between the hand-picked
    # REGION_CASES.
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
    ("scalar_lo", {"lo": 0.0, "hi": (6.0,) * 3}, "3-vector"),
    ("scalar_hi", {"lo": (0.0,) * 3, "hi": 6.0}, "3-vector"),
    ("negative_halo", {**FULL, "halo": -1}, "non-negative"),
    ("fractional_halo", {**FULL, "halo": 1.9}, "integer"),
    ("bool_halo", {**FULL, "halo": True}, "integer"),
    ("fp32_plotfile", FULL, "not 8-byte floats"),
]


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


def test_internal_call_sites_still_resolve_the_module_global(monkeypatch):
    # 21 tests replace this module global; an internal call site that stopped resolving it would
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
    # of them exercise the read path. If the reader ever normalized values, its downstream guard
    # would stop seeing what it expects.
    import yt

    real_load = yt.load
    poisoned = np.array([np.nan, np.inf, -np.inf, 1.5])

    class _Unyt:
        # Minimal stand-in for yt's unyt_array: the reader unwraps via .to_ndarray().
        def __init__(self, array):
            self._array = array

        def to_ndarray(self):
            return self._array

    class _PoisonGrid:
        def __init__(self, inner):
            self._inner = inner

        def __getitem__(self, key):
            value = self._inner[key].to_ndarray().copy()
            value.reshape(-1)[: poisoned.size] = poisoned
            return _Unyt(value)

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
    np.testing.assert_array_equal(
        snap.arrays["u"].reshape(-1)[: poisoned.size], poisoned
    )


def test_legacy_wrapper_returns_writable_arrays_like_the_oracle():
    # Kept as a focused smoke check; writeability is asserted across the WHOLE clamping matrix
    # inside test_extract_eulerian_box_matches_the_frozen_pre_refactor_oracle, because covering
    # one region of eleven is thin for "the thing array equality cannot see".
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
