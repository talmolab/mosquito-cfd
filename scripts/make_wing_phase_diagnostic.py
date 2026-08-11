r"""Generate the cluster-free wing-phase geometric diagnostic (fix-force-surrogate-sweep-hinge).

Thin driver over :mod:`mosquito_cfd.force_surrogate.wing_phase_diagnostic` (all logic lives in
the tested library). Renders marker positions at 4 phases of one wingbeat, purely from a config's
kinematics + hinge + ``wing.vertex`` -- no CFD run, plotfile, or force CSV required. Intended as a
sanity check before/after regenerating a sweep corpus: a proper root-hinged wingbeat sweeps the
span-tip through a visible arc; a midspan-pivot bug (the defect this change fixes) does not.

Default sample (documented here, not silently chosen): "validated" (the calibration baseline,
`examples/flapping_wing/inputs.3d.validation`'s own kinematics -- known correct) plus the two grid
corners "s35_f085_p30" and "s55_f115_p60" (the sweep's stroke/frequency/pitch extremes). The
kinematics amplitude/frequency don't affect hinge correctness, so this sample is representative of
the whole 27-config grid without rendering all of it. Pass --config all to render every config in
the manifest under --corpus-dir instead.

Run from the repository root, e.g.::

    uv run python scripts/make_wing_phase_diagnostic.py \\
        --out-dir examples/prelim_sweep/figures \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-06-23T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from mosquito_cfd.force_surrogate.evidence_figure import parse_config_name
from mosquito_cfd.force_surrogate.geometry_guard import read_deck_value
from mosquito_cfd.force_surrogate.wing_phase_diagnostic import build_wing_phase_figure

DEFAULT_VERTEX_PATH = Path("examples/flapping_wing/wing.vertex")
DEFAULT_CORPUS_DIR = Path("examples/prelim_sweep")
_VALIDATED_DECK = Path("examples/flapping_wing/inputs.3d.validation")

# The default sample: named, literal, documented (no silent caps -- CC-4 convention). See the
# module docstring for why these three.
DEFAULT_SAMPLE = ("validated", "s35_f085_p30", "s55_f115_p60")


def _validated_kwargs() -> dict[str, Any]:
    deck_text = _VALIDATED_DECK.read_text(encoding="utf-8")
    center = tuple(read_deck_value(deck_text, f"particle_inputs.{a}") for a in "xyz")
    hinge = tuple(
        read_deck_value(deck_text, f"particle_inputs.hinge_{a}") for a in "xyz"
    )
    return {
        "center": center,
        "hinge": hinge,
        "stroke_amp_deg": 70.0,
        "pitch_amp_deg": 45.0,
        "frequency_fstar": 1.0,
    }


def _sweep_config_kwargs(name: str, corpus_dir: Path) -> dict[str, Any]:
    # Read hinge/centre from the config's OWN generated deck, not a "base deck" file -- corpora
    # don't share a common base-deck filename/location (e.g. the fine corpus's base deck lives
    # under examples/prelim_sweep_fine_pilot/, not under its own directory), but render_inputs()
    # always copies hinge/centre through unchanged, so any generated deck carries the real values.
    deck_path = corpus_dir / "inputs" / f"inputs.3d.{name}"
    deck_text = deck_path.read_text(encoding="utf-8")
    center = tuple(read_deck_value(deck_text, f"particle_inputs.{a}") for a in "xyz")
    hinge = tuple(
        read_deck_value(deck_text, f"particle_inputs.hinge_{a}") for a in "xyz"
    )
    params = parse_config_name(name)
    return {
        "center": center,
        "hinge": hinge,
        "stroke_amp_deg": params.phi_amp_deg,
        "pitch_amp_deg": params.pitch_amp_deg,
        "frequency_fstar": params.f_star,
    }


def _config_kwargs(name: str, corpus_dir: Path) -> dict[str, Any]:
    if name == "validated":
        return _validated_kwargs()
    return _sweep_config_kwargs(name, corpus_dir)


def _all_config_names(corpus_dir: Path) -> list[str]:
    manifest = json.loads(
        (corpus_dir / "sweep_manifest.json").read_text(encoding="utf-8")
    )
    return [c["name"] for c in manifest["configs"]]


def main(argv: Sequence[str] | None = None) -> int:
    """Render the wing-phase diagnostic for the default sample or a specific config/``all``.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Render the cluster-free wing-phase geometric diagnostic.",
        epilog=(
            "Default sample (no CFD output needed, hinge-independent of kinematics): "
            f"{', '.join(DEFAULT_SAMPLE)} -- 'validated' is the known-correct calibration "
            "baseline; 's35_f085_p30'/'s55_f115_p60' are the sweep grid's stroke/frequency/"
            "pitch extremes. Pass --config all to render every config in --corpus-dir's manifest "
            "instead, or --config <name> for a single one."
        ),
    )
    parser.add_argument(
        "--config",
        default=None,
        help="A specific config name, 'all' (every config in --corpus-dir's manifest), or "
        "omit for the default sample.",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help="Sweep corpus directory (holds sweep_manifest.json and inputs/). "
        f"Default: {DEFAULT_CORPUS_DIR}.",
    )
    parser.add_argument(
        "--vertex-path",
        type=Path,
        default=DEFAULT_VERTEX_PATH,
        help=f"Wing marker file. Default: {DEFAULT_VERTEX_PATH}.",
    )
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
    args = parser.parse_args(argv)

    if args.config is None:
        names = list(DEFAULT_SAMPLE)
    elif args.config == "all":
        names = _all_config_names(args.corpus_dir)
    elif args.config == "validated":
        if args.corpus_dir != DEFAULT_CORPUS_DIR:
            parser.error(
                "--config validated always reads examples/flapping_wing/inputs.3d.validation "
                "directly -- it is corpus-independent and ignores --corpus-dir. Pass "
                "--corpus-dir only with 'all' or a specific manifest config name."
            )
        names = [args.config]
    else:
        manifest_names = _all_config_names(args.corpus_dir)
        if args.config not in manifest_names:
            parser.error(
                f"--config {args.config!r} is not a config in "
                f"{args.corpus_dir}/sweep_manifest.json -- pass 'all', 'validated', or an exact "
                "name from that manifest"
            )
        names = [args.config]

    for name in names:
        kwargs = _config_kwargs(name, args.corpus_dir)
        build_wing_phase_figure(
            vertex_path=args.vertex_path,
            config_name=name,
            docker_image_digest=args.docker_digest,
            timestamp=args.timestamp,
            out_dir=args.out_dir,
            **kwargs,
        )
    print(f"Rendered wing-phase diagnostic for {len(names)} config(s): {names}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
