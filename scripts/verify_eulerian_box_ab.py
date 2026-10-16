r"""Bit-exact A/B of ``extract_eulerian_box`` against its frozen pre-refactor copy, on real plotfiles.

The real-plotfile half of ``add-field-surrogate-reader`` design.md D11. CI's only plotfile is a 6³
single-FAB fixture at origin 0 with ``dx = 1``. This is the check that covers multi-FAB covering
grids and non-unit ``dx``. Read-only: it never writes to the plotfile roots.

For every plotfile it runs:

- each ``REGION_CASES`` entry, bit-exact against the frozen copy on key set, values, dtype, shape,
  Python type and writeability, plus the predicted cell counts;
- each ``DIVERGENCE_CASES`` entry, reproducing the recorded legacy and new counts, a contiguous
  sub-block at the edge-facing end, and equal values;
- the production boxes: the sphere control-volume slab and box, and the wing near-field and
  downstream boxes.

The cases are imported from ``tests/test_field_surrogate_snapshot.py``, so they are never
transcribed. Their coordinates are in the 6-cell fixture's cell units. A coordinate ``c >= 6``
maps to ``dre + (c - 6) * dx``, so upper-edge cases stay on the upper edge, and any other
``c`` maps to ``dle + c * dx``. Before anything is compared, every axis must have a dyadic
``dx`` and exact edges: a non-dyadic grid produces false divergences. The run fails unless the
number of comparisons equals the precomputed total, so a run that silently skipped plotfiles
cannot pass.

Run with Z: mounted, using the ``Z:/`` drive form (MSYS rewrites ``/z/...``)::

    uv run python scripts/verify_eulerian_box_ab.py \
        --sphere-root Z:/users/eberrigan/mosquito-cfd-benchmarks \
        --wing-root Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing
"""

from __future__ import annotations

import argparse
import importlib.util
import time
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np

from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

REPO = Path(__file__).resolve().parents[1]
FIX_N = 6  # the committed fixture's cells per axis: the unit the cases are written in
KEYS = sorted(
    ["u", "v", "w", "gradpx", "gradpy", "gradpz", "x", "y", "z", "dx", "current_time"]
)
FIELDS = ("u", "v", "w", "gradpx", "gradpy", "gradpz")
SPHERE_BOXES = [
    # sphere_cv_drag_cd's slab at the analyze_sphere.py planes, and test_stress_integral's box.
    ("sphere_cv_slab", (2.0, -np.inf, -np.inf), (8.0, np.inf, np.inf), 0),
    ("sphere_box_h0", (6.5, 0.0, 0.0), (8.0, 10.0, 10.0), 0),
    ("sphere_box_h2", (6.5, 0.0, 0.0), (8.0, 10.0, 10.0), 2),
]
WING_BOXES = [
    # test_wing_lev.py's pinned near-field and downstream boxes.
    ("wing_nearfield", (2.5, 0.0, 3.0), (5.5, 4.0, 5.0), 0),
    ("wing_downstream", (3.5, 0.0, 3.0), (6.5, 4.0, 5.0), 0),
]
SPHERE_PLOTFILES = (
    "flow_past_sphere_coarse/plt10000",
    "flow_past_sphere_10k/plt10000",
    "flow_past_sphere_10k/plt05000",
)
WING_PLOTFILES = ("t2a-newconv4/plt01000", "t3b-medium/plt01000", "t3c-fine/plt01000")


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _is_dyadic(x: float) -> bool:
    den = float(x).as_integer_ratio()[1]
    return den & (den - 1) == 0


def _map(c: Sequence[float], dle: np.ndarray, dre: np.ndarray, dx: np.ndarray) -> tuple:
    out = []
    for i, v in enumerate(np.broadcast_to(np.asarray(c, float), (3,))):
        if np.isinf(v):
            out.append(float(v))
        elif v >= FIX_N:
            out.append(float(dre[i] + (v - FIX_N) * dx[i]))
        else:
            out.append(float(dle[i] + v * dx[i]))
    return tuple(out)


def _predicted(name: str, counts: tuple, ddims: np.ndarray) -> tuple:
    nx, ny, nz = (int(n) for n in ddims)
    # Lower-anchored cases that are clipped by the fixture's own upper edge, re-derived for a
    # larger grid; every other case keeps the fixture's count under the cell-unit mapping.
    return {
        "full": (nx, ny, nz),
        "mixed_inf": (nx, 4, nz),
        "x_slab_only": (4, ny, nz),
        "halo3_clipped": (7, 7, 7),
    }.get(name, counts)


def _bit_exact(got: dict[str, Any], want: dict[str, Any], tag: str) -> None:
    assert sorted(got) == KEYS == sorted(want), tag
    for k in KEYS:
        if k == "current_time":
            assert type(got[k]) is type(want[k]) is float, (tag, k)
            assert got[k] == want[k], (tag, k)
            continue
        g, w = got[k], want[k]
        assert isinstance(g, np.ndarray), (tag, k)
        assert g.dtype == w.dtype == np.float64, (tag, k)
        assert g.shape == w.shape, (tag, k, g.shape, w.shape)
        assert g.flags.writeable and w.flags.writeable, (tag, k)
        np.testing.assert_array_equal(g, w, err_msg=f"{tag}:{k}")


def _check_divergence(got, want, mlo, mhi, dle, dre, tag) -> None:
    block = []
    for i, axis in enumerate(("x", "y", "z")):
        n, start = got[axis].size, 0
        if n:
            (hits,) = np.nonzero(want[axis] == got[axis][0])
            assert hits.size == 1, (tag, axis)
            start = int(hits[0])
            if mlo[i] > dre[i]:
                assert start + n == want[axis].size, (tag, axis)
            elif mhi[i] <= dle[i]:
                assert start == 0, (tag, axis)
        np.testing.assert_array_equal(got[axis], want[axis][start : start + n])
        block.append(np.arange(start, start + n))
    for f in FIELDS:
        np.testing.assert_array_equal(got[f], want[f][np.ix_(*block)], err_msg=tag)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the A/B over every listed plotfile and print a per-plotfile table.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code: 0 only if every comparison passed and the comparison count equals the
        precomputed total.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sphere-root", type=Path, required=True)
    parser.add_argument("--wing-root", type=Path, required=True)
    args = parser.parse_args(argv)

    import yt

    yt.set_log_level(50)
    tests = _load("_cases", REPO / "tests" / "test_field_surrogate_snapshot.py")
    oracle = _load(
        "_oracle", REPO / "tests" / "fixtures" / "legacy_extract_eulerian_box.py"
    ).legacy_extract_eulerian_box
    plotfiles = [(args.sphere_root / p, SPHERE_BOXES) for p in SPHERE_PLOTFILES] + [
        (args.wing_root / p, WING_BOXES) for p in WING_PLOTFILES
    ]
    n_cases = len(tests.REGION_CASES) + len(tests.DIVERGENCE_CASES)
    expected_total = sum(n_cases + len(boxes) for _, boxes in plotfiles)
    checked = 0
    rows = []
    t0 = time.time()
    for path, boxes in plotfiles:
        if not path.is_dir():
            print(f"FAIL: missing plotfile {path}")
            return 1
        p = str(path)
        ds = yt.load(p)
        dle = ds.domain_left_edge.to_ndarray().astype(float)
        dre = ds.domain_right_edge.to_ndarray().astype(float)
        ddims = np.asarray(ds.domain_dimensions, dtype=np.int64)
        dx = (dre - dle) / ddims
        for i in range(3):
            assert _is_dyadic(dx[i]), f"{p}: non-dyadic dx {dx[i]!r}"
            assert dle[i] + ddims[i] * dx[i] == dre[i], f"{p}: inexact edge, axis {i}"
        assert ddims.min() >= FIX_N, p
        tag0 = "/".join(path.parts[-2:])
        here = 0
        for name, lo, hi, halo, counts in tests.REGION_CASES:
            mlo, mhi = _map(lo, dle, dre, dx), _map(hi, dle, dre, dx)
            got = extract_eulerian_box(p, lo=mlo, hi=mhi, halo=halo)
            _bit_exact(got, oracle(p, lo=mlo, hi=mhi, halo=halo), f"{tag0}/{name}")
            pred = _predicted(name, counts, ddims)
            assert got["u"].shape == pred, (tag0, name, got["u"].shape, pred)
            here += 1
        for name, lo, hi, halo, legacy_counts, counts in tests.DIVERGENCE_CASES:
            mlo, mhi = _map(lo, dle, dre, dx), _map(hi, dle, dre, dx)
            got = extract_eulerian_box(p, lo=mlo, hi=mhi, halo=halo)
            want = oracle(p, lo=mlo, hi=mhi, halo=halo)
            assert want["u"].shape == legacy_counts, (tag0, name, want["u"].shape)
            assert got["u"].shape == counts, (tag0, name, got["u"].shape)
            _check_divergence(got, want, mlo, mhi, dle, dre, f"{tag0}/{name}")
            here += 1
        for name, lo, hi, halo in boxes:
            got = extract_eulerian_box(p, lo=lo, hi=hi, halo=halo)
            _bit_exact(got, oracle(p, lo=lo, hi=hi, halo=halo), f"{tag0}/{name}")
            assert got["u"].size > 0, (tag0, name)
            here += 1
        checked += here
        rows.append(
            (
                tag0,
                "x".join(str(int(n)) for n in ddims),
                ",".join(f"{v:g}" for v in dx),
                ",".join(f"{v:g}" for v in dle),
                int(ds.index.num_grids),
                here,
            )
        )
        print(f"  {tag0}: {here} comparisons OK ({time.time() - t0:.0f}s)", flush=True)

    print("\n| plotfile | grid | dx | domain_left_edge | FABs | comparisons |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print("| `{}` | {} | {} | {} | {} | {} |".format(*r))
    print(f"\nTOTAL {checked} comparisons, expected {expected_total}")
    if checked == 0 or checked != expected_total:
        print("FAIL: comparison count mismatch")
        return 1
    print("ALL BIT-EXACT / DIVERGENCE AS RECORDED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
