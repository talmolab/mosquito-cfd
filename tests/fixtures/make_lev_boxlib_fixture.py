"""Generate the tiny synthetic single-level AMReX/boxlib plotfile fixture for the LEV yt-read test.

Hand-authors a minimal boxlib plotfile (``Header`` + ``Level_0/{Cell_H, Cell_D_00000}``) that ``yt.load``
opens with ``max_level == 0`` and the eight ``('boxlib', ...)`` fields the real wing plotfiles write, of
which ``extract_eulerian_box`` reads the six it requires. The velocity field is analytic **solid-body
rotation** ``(-Omega*y, Omega*x, 0)`` so ``extract_eulerian_box -> lev`` yields the known ``||omega|| =
2*Omega``, ``Q = Omega^2`` on the interior.

The FAB is written **big-endian** (``>f8``) with a descriptor matching the real plotfiles'
``(8, (8 7 6 5 4 3 2 1))`` byte order, so the fixture exercises the exact same yt read path. yt cannot
*write* boxlib, so this is hand-authored; committing the generator (not just the bytes) keeps the fixture
auditable and regenerable. Run: ``uv run python tests/fixtures/make_lev_boxlib_fixture.py``.

This closes the #33 CI-coverage gap for the yt Eulerian-box adapter.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

FIELDS = (
    "x_velocity",
    "y_velocity",
    "z_velocity",
    "density",
    "tracer",
    "gradpx",
    "gradpy",
    "gradpz",
)
OMEGA = 1.3
N = 6  # cells per axis (>= 5 so the [1:-1] interior has >= 3 points per axis for lev's stencil)
DX = 1.0
TIME = 0.5
FIXTURE_DIR = Path(__file__).parent / "lev_boxlib_plt"
# Descriptor copied verbatim from a real wing plotfile FAB header (IEEE double, big-endian order).
_REAL_DESCRIPTOR = "(8, (64 11 52 0 1 12 0 1023)),(8, (8 7 6 5 4 3 2 1))"


def _fields() -> list[np.ndarray]:
    xs = (np.arange(N) + 0.5) * DX
    x, y, _ = np.meshgrid(xs, xs, xs, indexing="ij")
    zero = np.zeros_like(x)
    return [
        -OMEGA * y,  # x_velocity
        OMEGA * x,  # y_velocity
        zero,  # z_velocity
        np.ones_like(x),  # density
        zero,  # tracer
        zero,  # gradpx
        zero,  # gradpy
        zero,  # gradpz
    ]


def write_fixture(root: Path = FIXTURE_DIR) -> Path:
    """Write the fixture plotfile under ``root`` and return the path."""
    lev = root / "Level_0"
    lev.mkdir(parents=True, exist_ok=True)
    fields = _fields()
    box = f"((0,0,0) ({N - 1},{N - 1},{N - 1}) (0,0,0))"

    # Cell_D: ASCII FAB header, then little-endian float64, component-major, x-fastest (Fortran order).
    # AMReX writes native little-endian doubles (verified by decoding a real plotfile FAB), even though
    # its RealDescriptor labels the byte order (8 7 6 5 4 3 2 1); the descriptor is copied verbatim so yt
    # reads this fixture on the exact same path as a real plotfile.
    fab_hdr = f"FAB ({_REAL_DESCRIPTOR}){box} {len(FIELDS)}\n".encode()
    body = b"".join(f.flatten(order="F").astype("<f8").tobytes() for f in fields)
    (lev / "Cell_D_00000").write_bytes(fab_hdr + body)

    # Cell_H: version/how/ncomp/nghost, one box, one FabOnDisk, then per-fab min/max blocks.
    def _row(vals: list[float]) -> str:
        return ",".join(f"{v:.17e}" for v in vals) + ","

    mins = [float(f.min()) for f in fields]
    maxs = [float(f.max()) for f in fields]
    cell_h = "\n".join(
        [
            "1",
            "1",
            str(len(FIELDS)),
            "0",
            "(1 0",
            box,
            ")",
            "1",
            "FabOnDisk: Cell_D_00000 0",
            "",
            f"1,{len(FIELDS)}",
            _row(mins),
            "",
            f"1,{len(FIELDS)}",
            _row(maxs),
            "",
        ]
    )
    (lev / "Cell_H").write_text(cell_h)

    hi = N * DX
    header = "\n".join(
        [
            "NavierStokes-V1.1",
            str(len(FIELDS)),
            *FIELDS,
            "3",  # spacedim
            f"{TIME}",  # time
            "0",  # finest_level
            "0 0 0 ",  # prob_lo
            f"{hi} {hi} {hi} ",  # prob_hi
            "",  # ref_factors (empty for max_level=0 -> yt defaults)
            f"{box} ",  # level-0 domain (index space)
            "0 ",  # level steps (one per level)
            f"{DX} {DX} {DX} ",  # cell size
            "0",  # coord sys (cartesian)
            "0",  # boundary width
            f"0 1 {TIME}",  # level 0: lev ngrids time
            "0",  # level step
            f"0 {hi}",  # grid 0 RealBox: x lo/hi
            f"0 {hi}",  # y lo/hi
            f"0 {hi}",  # z lo/hi
            "Level_0/Cell",
            "",
        ]
    )
    (root / "Header").write_text(header)
    return root


if __name__ == "__main__":
    print("wrote", write_fixture())
