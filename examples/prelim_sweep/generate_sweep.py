"""Generate the committed force-surrogate sweep corpus under ``examples/prelim_sweep/``.

Thin driver over :func:`mosquito_cfd.force_surrogate.sweep.generate_sweep` (all logic lives in
the tested library). Run from the repository root::

    uv run python examples/prelim_sweep/generate_sweep.py --timestamp 2026-06-09T00:00:00+00:00

``--timestamp`` is required (a real regeneration must supply a fresh, caller-chosen value --
fix-force-surrogate-sweep-hinge).

This (re)writes ``inputs/inputs.3d.*`` (27 decks), ``sweep_manifest.json``,
``sweep_manifest.units.json``, and ``sweep_provenance.json``. The corpus is committed and a test
(``test_committed_sweep_matches_regeneration``) asserts it is byte-identical to a fresh run.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import generate_sweep, iso8601_timestamp

# Paths relative to the repository root (run the driver from the repo root).
BASE_INPUTS = Path("examples/flapping_wing/inputs.3d.validation")
DEFAULT_OUTPUT = Path("examples/prelim_sweep")


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the sweep corpus and print a one-line summary.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        description="Generate the force-surrogate sweep corpus."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output directory (default: examples/prelim_sweep).",
    )
    parser.add_argument(
        "--timestamp",
        type=iso8601_timestamp,
        required=True,
        help=(
            "Caller-supplied ISO-8601 timestamp recorded in sweep_provenance.json. Required: a "
            "real regeneration must supply a fresh value, never silently reuse a stale one "
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

    manifest = generate_sweep(BASE_INPUTS, args.output, timestamp=args.timestamp)
    n_configs = len(manifest["configs"])
    holdout = [c["name"] for c in manifest["configs"] if c["split"] == "holdout"]
    print(
        f"Generated {n_configs} configs into {args.output.as_posix()}/ "
        f"(reynolds_policy={manifest['reynolds_policy']}, holdout={sorted(holdout)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
