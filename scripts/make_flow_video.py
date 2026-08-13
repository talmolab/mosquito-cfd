r"""Generate a generalized CFD-field video (add-visualization-tooling).

Thin driver over :mod:`mosquito_cfd.visualization.flow_video` (all logic lives in the tested
library). Renders one of 4 field modes -- ``wake-slice``, ``combined-3d``, ``lev-3d``,
``zvelocity-3d`` -- from a directory of plotfiles, using either a named sweep config's own deck
(``--config``/``--corpus-dir``) or explicit center/hinge/kinematics overrides. See OpenSpec change
`add-visualization-tooling` (`design.md` D3) for the two documented hinge-caveat cases (as-run vs.
corrected-for-display).

Run from the repository root, e.g.::

    uv run python scripts/make_flow_video.py \\
        --plotfile-dir Z:/users/eberrigan/mosquito-cfd/examples/flapping_wing/t3c-fine \\
        --field-mode wake-slice \\
        --center 4.0 2.0 4.0 --hinge 4.0 0.5 4.0 \\
        --stroke-amp-deg 70.0 --pitch-amp-deg 45.0 --frequency-fstar 1.0 \\
        --label t3c-fine \\
        --out-dir examples/prelim_sweep_fine/figures \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-08-12T00:00:00+00:00
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.visualization.flow_video import (
    DEFAULT_BOX_MARGIN,
    DEFAULT_FPS,
    DEFAULT_Q_THRESHOLD,
    DEFAULT_VORT_VMAX,
    DEFAULT_VORT_VMIN,
    FIELD_MODES,
    build_flow_video,
)

DEFAULT_VERTEX_PATH = Path("examples/flapping_wing/wing.vertex")


def main(argv: Sequence[str] | None = None) -> int:
    """Render a generalized CFD-field video for one field mode.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Render a generalized CFD-field video "
            "(wake-slice / combined-3d / lev-3d / zvelocity-3d)."
        ),
        epilog=(
            "Center/hinge/kinematics resolve from --config/--corpus-dir's own deck, explicit "
            "--center/--hinge/--stroke-amp-deg/--pitch-amp-deg/--frequency-fstar overrides, or "
            "both (overrides win). See OpenSpec change `add-visualization-tooling` (`design.md` "
            "D3) for the two documented hinge-caveat cases (as-run vs. corrected-for-display)."
        ),
    )
    parser.add_argument(
        "--plotfile-dir",
        type=Path,
        required=True,
        help="Directory containing plt##### plotfile subdirectories.",
    )
    parser.add_argument("--field-mode", required=True, choices=FIELD_MODES)
    parser.add_argument(
        "--vertex-path",
        type=Path,
        default=DEFAULT_VERTEX_PATH,
        help=f"Wing marker file (all modes except wake-slice). Default: {DEFAULT_VERTEX_PATH}.",
    )
    parser.add_argument("--label", required=True, help="Output filename label.")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned sha256: image digest (mutable tags rejected).",
    )
    parser.add_argument(
        "--timestamp",
        required=True,
        help="Caller-supplied ISO-8601 timestamp (reproducible provenance).",
    )

    parser.add_argument(
        "--config", default=None, help="Sweep config name to resolve kinematics from."
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Sweep corpus directory (holds sweep_manifest.json and inputs/); required with "
        "--config.",
    )
    parser.add_argument(
        "--center",
        type=float,
        nargs=3,
        default=None,
        metavar=("X", "Y", "Z"),
        help="Explicit wing-centre override; takes precedence over --config's deck.",
    )
    parser.add_argument(
        "--hinge",
        type=float,
        nargs=3,
        default=None,
        metavar=("X", "Y", "Z"),
        help="Explicit hinge override; takes precedence over --config's deck.",
    )
    parser.add_argument("--stroke-amp-deg", type=float, default=None)
    parser.add_argument("--pitch-amp-deg", type=float, default=None)
    parser.add_argument("--frequency-fstar", type=float, default=None)

    parser.add_argument(
        "--q-threshold",
        type=float,
        default=DEFAULT_Q_THRESHOLD,
        help=f"Q-criterion isosurface level (lev-3d only). Default: {DEFAULT_Q_THRESHOLD}.",
    )
    parser.add_argument("--vort-vmin", type=float, default=DEFAULT_VORT_VMIN)
    parser.add_argument("--vort-vmax", type=float, default=DEFAULT_VORT_VMAX)
    parser.add_argument(
        "--box-margin",
        type=float,
        default=DEFAULT_BOX_MARGIN,
        help="Isotropic half-width of the near-field extraction box around --center "
        "(lev-3d only).",
    )
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)

    args = parser.parse_args(argv)

    build_flow_video(
        plotfile_dir=args.plotfile_dir,
        field_mode=args.field_mode,
        vertex_path=args.vertex_path,
        out_dir=args.out_dir,
        docker_image_digest=args.docker_digest,
        timestamp=args.timestamp,
        label=args.label,
        config_name=args.config,
        corpus_dir=args.corpus_dir,
        center=args.center,
        hinge=args.hinge,
        stroke_amp_deg=args.stroke_amp_deg,
        pitch_amp_deg=args.pitch_amp_deg,
        frequency_fstar=args.frequency_fstar,
        q_threshold=args.q_threshold,
        vort_vmin=args.vort_vmin,
        vort_vmax=args.vort_vmax,
        box_margin=args.box_margin,
        fps=args.fps,
    )
    print(f"Rendered {args.field_mode} video for {args.label!r} -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
