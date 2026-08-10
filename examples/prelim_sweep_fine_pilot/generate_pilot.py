"""Generate the 3-config fine-grid pilot corpus under ``examples/prelim_sweep_fine_pilot/``.

Thin driver over :func:`mosquito_cfd.force_surrogate.sweep.generate_sweep` (all logic lives in
the tested library) -- mirrors ``examples/prelim_sweep/generate_sweep.py``, but pinned to the
fine 256x128x256 base deck and the 3 pilot configs only (OpenSpec change
``add-fine-grid-training-pilot``). Run from the repository root::

    uv run python examples/prelim_sweep_fine_pilot/generate_pilot.py

``n_holdout=0`` is required here: the default ``N_HOLDOUT=6`` exceeds the number of non-corner
eligible configs when only 1 of these 3 pilot configs is a non-corner point of this 3-config set
(``select_holdout`` would raise ``ValueError``). This (re)writes ``inputs/inputs.3d.*`` (3 decks),
``sweep_manifest.json``, ``sweep_manifest.units.json``, and ``sweep_provenance.json`` under
``OUTPUT_DIR`` -- never under the frozen ``examples/prelim_sweep/`` corpus.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import generate_sweep

# Paths relative to the repository root (run the driver from the repo root).
BASE_INPUTS = Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")
OUTPUT_DIR = Path("examples/prelim_sweep_fine_pilot")
# Fixed caller-supplied timestamp so the committed provenance is reproducible (never wall-clock).
# NOTE (fix-force-surrogate-sweep-hinge): the sibling scripts generate_sweep.py and
# generate_full_corpus.py had this identical default removed (it let a real regeneration silently
# reuse a stale timestamp) and now require --timestamp explicitly. This script keeps the default
# deliberately -- the pilot isn't re-run by that change -- but the same latent footgun exists here
# if this script is ever used for a real regeneration; make --timestamp required then too.
DEFAULT_TIMESTAMP = "2026-07-29T00:00:00+00:00"

# The 3 pilot configs (highest-Reynolds-first per design.md D4). Pitch held at 45 deg across
# all three to isolate the stroke x frequency (CFL-driving) axis.
PILOT_CONFIGS = [
    {"stroke_amp_deg": 55.0, "frequency_fstar": 1.15, "pitch_amp_deg": 45.0},
    {"stroke_amp_deg": 45.0, "frequency_fstar": 1.00, "pitch_amp_deg": 45.0},
    {"stroke_amp_deg": 35.0, "frequency_fstar": 0.85, "pitch_amp_deg": 45.0},
]

# Pilot-specific NFS staging path (design.md "Open questions - resolved"). Distinct from the
# frozen coarse corpus's default (examples/prelim_sweep) used by cluster/argo/scripts/submit_workflow.sh.
WORKSPACE_HOSTPATH = (
    "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine_pilot"
)

# The frozen 27-config coarse corpus generate_sweep() must never be pointed at (its
# stale-deck-pruning unlink() would delete real, committed CFD output). Module-level so tests
# can monkeypatch it to a decoy path rather than exercising the guard against the real directory.
_FROZEN_CORPUS_DIR = Path("examples/prelim_sweep")


def _validate_output_dir(output: Path) -> None:
    """Reject an ``--output`` directory that resolves to the frozen coarse corpus.

    Args:
        output: The requested output directory.

    Raises:
        ValueError: If ``output`` resolves to the same directory as the frozen coarse corpus
            (``_FROZEN_CORPUS_DIR``) -- pointing ``generate_sweep()`` at it would prune its real,
            committed decks and overwrite its manifest with this script's 3-config one.
    """
    if output.resolve() == _FROZEN_CORPUS_DIR.resolve():
        raise ValueError(
            f"refusing to generate into {output} -- this is the frozen coarse corpus "
            f"({_FROZEN_CORPUS_DIR}); pointing generate_sweep() at it would prune its real, "
            "committed decks. Use a different --output directory."
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the fine-grid pilot corpus and print a one-line summary.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Generate the fine-grid training-data pilot corpus (3 configs)."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory (default: examples/prelim_sweep_fine_pilot).",
    )
    parser.add_argument(
        "--timestamp",
        default=DEFAULT_TIMESTAMP,
        help="Caller-supplied ISO-8601 timestamp recorded in sweep_provenance.json.",
    )
    args = parser.parse_args(argv)

    # BASE_INPUTS is repo-root-relative (kept relative so the committed provenance path is
    # portable); fail with guidance rather than a bare FileNotFoundError if run elsewhere.
    if not BASE_INPUTS.exists():
        parser.error(
            f"base inputs {BASE_INPUTS} not found relative to cwd {Path.cwd()}; "
            "run this driver from the repository root"
        )

    try:
        _validate_output_dir(args.output)
    except ValueError as exc:
        parser.error(str(exc))

    manifest = generate_sweep(
        BASE_INPUTS,
        args.output,
        timestamp=args.timestamp,
        configs=PILOT_CONFIGS,
        n_holdout=0,
    )
    n_configs = len(manifest["configs"])
    names = [c["name"] for c in manifest["configs"]]
    print(
        f"Generated {n_configs} pilot configs into {args.output.as_posix()}/ "
        f"(reynolds_policy={manifest['reynolds_policy']}, configs={names})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
