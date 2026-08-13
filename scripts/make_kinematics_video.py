r"""Generate a cluster-free wing-kinematics preview video (add-visualization-tooling).

Thin driver over :mod:`mosquito_cfd.visualization.kinematics_video` (all logic lives in the tested
library). Renders the prescribed wing kinematics applied to the ``.vertex`` geometry -- no plotfile,
no CFD run -- using either a named sweep config's own deck (``--config``/``--corpus-dir``) or
explicit center/hinge/kinematics overrides. See OpenSpec change `add-visualization-tooling`
(`design.md` D3) for the two documented hinge-caveat cases (as-run vs. corrected-for-display).

Run from the repository root, e.g.::

    uv run python scripts/make_kinematics_video.py \\
        --config s45_f115_p60 --corpus-dir examples/prelim_sweep_fine \\
        --hinge 4.0 0.5 4.0 \\
        --label s45_f115_p60 \\
        --out-dir examples/prelim_sweep_fine/figures \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-08-12T00:00:00+00:00
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.visualization.kinematics_video import (
    DEFAULT_FPS,
    DEFAULT_N_FRAMES,
    build_kinematics_video,
)

DEFAULT_VERTEX_PATH = Path("examples/flapping_wing/wing.vertex")


def main(argv: Sequence[str] | None = None) -> int:
    """Render a cluster-free wing-kinematics preview video.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Render a cluster-free wing-kinematics preview video.",
        epilog=(
            "Center/hinge/kinematics resolve from --config/--corpus-dir's own deck, explicit "
            "--center/--hinge/--stroke-amp-deg/--pitch-amp-deg/--frequency-fstar overrides, or "
            "both (overrides win). See OpenSpec change `add-visualization-tooling` (`design.md` "
            "D3) for the two documented hinge-caveat cases (as-run vs. corrected-for-display)."
        ),
    )
    parser.add_argument(
        "--vertex-path",
        type=Path,
        default=DEFAULT_VERTEX_PATH,
        help=f"Wing marker file. Default: {DEFAULT_VERTEX_PATH}.",
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
    parser.add_argument("--n-frames", type=int, default=DEFAULT_N_FRAMES)
    parser.add_argument("--fps", type=int, default=DEFAULT_FPS)

    args = parser.parse_args(argv)

    build_kinematics_video(
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
        n_frames=args.n_frames,
        fps=args.fps,
    )
    print(f"Rendered kinematics preview for {args.label!r} -> {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
