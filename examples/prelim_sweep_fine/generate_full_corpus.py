"""Generate the full 27-config fine-grid corpus under ``examples/prelim_sweep_fine/``.

Thin driver over :func:`mosquito_cfd.force_surrogate.sweep.generate_sweep` (all logic lives in
the tested library) -- mirrors ``examples/prelim_sweep_fine_pilot/generate_pilot.py``, but calls
``generate_sweep()`` with no ``configs=``/``n_holdout=`` override (OpenSpec change
``add-fine-grid-corpus-full``). Run from the repository root::

    uv run python examples/prelim_sweep_fine/generate_full_corpus.py

Unlike the pilot (3 configs, forced ``n_holdout=0``), the full corpus uses ``generate_sweep()``'s
defaults: the full 27-point Aedes grid (``build_kinematic_grid()``) and ``n_holdout=6``
(``N_HOLDOUT``) -- valid here since 27 configs support a non-degenerate 6-config holdout. This
(re)writes ``inputs/inputs.3d.*`` (27 decks), ``sweep_manifest.json``,
``sweep_manifest.units.json``, and ``sweep_provenance.json`` under ``OUTPUT_DIR`` -- never under
the frozen ``examples/prelim_sweep/`` corpus or the already-committed
``examples/prelim_sweep_fine_pilot/`` pilot.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import generate_sweep

# Paths relative to the repository root (run the driver from the repo root). The fine base deck
# is reused unmodified from the pilot -- not copied -- since it's already committed and its
# deck-invariance (vs. the coarse base) is already tested by tests/test_fine_pilot_deck.py.
BASE_INPUTS = Path("examples/prelim_sweep_fine_pilot/base_inputs.3d.fine")
OUTPUT_DIR = Path("examples/prelim_sweep_fine")

# Full-corpus-specific NFS staging path (design.md "Open questions - resolved"). Distinct from
# both the frozen coarse corpus's default (examples/prelim_sweep) and the pilot's
# (examples/prelim_sweep_fine_pilot).
WORKSPACE_HOSTPATH = (
    "/hpi/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep_fine"
)

# The frozen 27-config coarse corpus generate_sweep() must never be pointed at (its
# stale-deck-pruning unlink() would delete real, committed CFD output). Module-level so tests
# can monkeypatch it to a decoy path rather than exercising the guard against the real directory.
_FROZEN_CORPUS_DIR = Path("examples/prelim_sweep")
# The already-committed pilot corpus must likewise never be overwritten.
_PILOT_DIR = Path("examples/prelim_sweep_fine_pilot")


def _validate_output_dir(output: Path) -> None:
    """Reject an ``--output`` directory that resolves to either frozen path.

    Args:
        output: The requested output directory.

    Raises:
        ValueError: If ``output`` resolves to the frozen coarse corpus (``_FROZEN_CORPUS_DIR``)
            or the already-committed pilot directory (``_PILOT_DIR``) -- pointing
            ``generate_sweep()`` at either would prune its real, committed decks and overwrite its
            manifest with this script's 27-config one.
    """
    resolved = output.resolve()
    if resolved == _FROZEN_CORPUS_DIR.resolve():
        raise ValueError(
            f"refusing to generate into {output} -- this is the frozen coarse corpus "
            f"({_FROZEN_CORPUS_DIR}); pointing generate_sweep() at it would prune its real, "
            "committed decks. Use a different --output directory."
        )
    if resolved == _PILOT_DIR.resolve():
        raise ValueError(
            f"refusing to generate into {output} -- this is the already-committed pilot "
            f"directory ({_PILOT_DIR}); pointing generate_sweep() at it would prune its real, "
            "committed pilot decks. Use a different --output directory."
        )


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the full 27-config fine-grid corpus and print a one-line summary.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Generate the full 27-config fine-grid corpus."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="Output directory (default: examples/prelim_sweep_fine).",
    )
    parser.add_argument(
        "--timestamp",
        required=True,
        help=(
            "Caller-supplied ISO-8601 timestamp recorded in sweep_provenance.json. Required: a "
            "real regeneration must supply a fresh value, never silently reuse the stale "
            "2026-08-03 literal from this script's original (buggy-hinge) authoring session "
            "(fix-force-surrogate-sweep-hinge)."
        ),
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
    )
    n_configs = len(manifest["configs"])
    n_holdout = manifest["holdout"]["n_holdout"]
    print(
        f"Generated {n_configs} configs into {args.output.as_posix()}/ "
        f"(reynolds_policy={manifest['reynolds_policy']}, n_holdout={n_holdout})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
