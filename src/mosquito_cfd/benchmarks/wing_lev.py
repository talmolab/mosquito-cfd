"""Wing LEV report — compose the yt Eulerian-box adapter with the LEV pure functions (Tier T3b).

Reuses :func:`mosquito_cfd.benchmarks.stress_integral.extract_eulerian_box` (the only cluster-touching
read) + the :mod:`mosquito_cfd.benchmarks.lev` pure functions to report the leading-edge-vortex (LEV)
diagnostic over a **wing near-field box** at a single kinematic phase. Report-only: returns a plain dict
of numbers, never a pass/fail verdict.

The PRIMARY descriptor is the **resolution-fair** integrated positive Q over the box interior
(``q_pos_vol = sum(max(Q, 0)) * dx*dy*dz``) plus the positive-Q volume fraction ``q_pos_frac``. The peak
``||omega||`` / peak ``Q`` are reported **secondarily** and are resolution-biased: peak ``Q ~ (U/dx)^2``
grows under refinement for the *same* physical vortex, so a larger medium peak Q is partly a resolution
artifact, not proof a coarse LEV is absent. Even ``q_pos_vol`` is not resolution-invariant (a
marginally-resolved coarse core under-estimates it), so a coarse->medium increase is a **lower bound on
LEV growth, not a present/absent gate** — the present/absent reading lives in RESULTS prose.

The near-field box (``lo``/``hi``) is **required** — a domain-wide reduction is dominated by far-field
noise and the grid-tied IB marker shell (which the box cannot fully exclude, so the peak metrics stay
shell-contaminated; a downstream-offset box is reported separately to isolate shed vorticity). The box is
derived by the caller from the plotfile's wing-marker (``particle_position_*``) bounding box + a margin;
this function just reduces over whatever box it is given. Interior ``[1:-1]`` because ``np.gradient`` uses
one-sided lower-order stencils on the box edges.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mosquito_cfd.benchmarks.lev import q_criterion, vorticity_magnitude
from mosquito_cfd.benchmarks.stress_integral import extract_eulerian_box

_INTERIOR = (slice(1, -1), slice(1, -1), slice(1, -1))


def wing_lev_report(
    plotfile_path: str | Path,
    *,
    lo: tuple[float, float, float],
    hi: tuple[float, float, float],
) -> dict[str, Any]:
    """Report LEV vorticity/Q descriptors over a wing near-field box of one plotfile (report-only).

    Args:
        plotfile_path: AMReX plotfile directory (the caller selects it by physical time).
        lo: Physical lower corner ``(x, y, z)`` of the wing near-field box (required, no default).
        hi: Physical upper corner ``(x, y, z)`` of the wing near-field box (required, no default).

    Returns:
        A report-only dict with **no** verdict key:
          - ``peak_vorticity`` / ``peak_q``: interior max ``||omega||`` / ``Q`` (secondary, resolution-biased),
          - ``q_pos_vol``: resolution-fair ``sum(max(Q, 0)) * dx*dy*dz`` over the interior (primary descriptor),
          - ``q_pos_frac``: fraction of interior cells with ``Q > 0``,
          - ``dx``: per-axis grid spacing ``(dx, dy, dz)``,
          - ``phase_time``: plotfile ``current_time`` (for the coarse<->medium same-phase guard).
    """
    box = extract_eulerian_box(plotfile_path, lo=lo, hi=hi)
    u, v, w = box["u"], box["v"], box["w"]
    dx = np.asarray(box["dx"], dtype=float)
    omega_int = vorticity_magnitude(u, v, w, dx)[_INTERIOR]
    q_int = q_criterion(u, v, w, dx)[_INTERIOR]
    cell_vol = float(dx[0] * dx[1] * dx[2])
    return {
        "peak_vorticity": float(omega_int.max()),
        "peak_q": float(q_int.max()),
        "q_pos_vol": float(np.maximum(q_int, 0.0).sum() * cell_vol),
        "q_pos_frac": float((q_int > 0.0).mean()),
        "dx": tuple(float(d) for d in dx),
        "phase_time": float(box["current_time"]),
    }
