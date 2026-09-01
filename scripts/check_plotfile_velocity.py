r"""Assert a field-capture plotfile's velocity field is not silently zero (CC-F1).

Thin driver over :func:`mosquito_cfd.benchmarks.stress_integral.check_field_capture_velocity`
(all logic lives in the tested library). Guards against a known, previously-hit defect: with
``ns.init_iter = 0``, IAMReX never persists the induced velocity field to the plotfile -- every
``x_velocity`` value reads as exactly zero, with no other symptom (see
``examples/flapping_wing/RESULTS.md``, "Note on the velocity field").

Run against a real smoke-run plotfile during ``/submit-cluster-sweep``'s Step 2, before trusting
any field-capture output as training data::

    uv run python scripts/check_plotfile_velocity.py --plotfile <workspace>/runs/<config>/plt00100
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.benchmarks.stress_integral import check_field_capture_velocity


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CC-F1 check against a plotfile and print the result.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).

    Returns:
        Process exit code (0 if the velocity field is genuinely non-zero).
    """
    parser = argparse.ArgumentParser(
        description="Assert a field-capture plotfile's x_velocity field is not silently zero."
    )
    parser.add_argument(
        "--plotfile",
        type=Path,
        required=True,
        help="Path to the plotfile directory (e.g. .../plt00100).",
    )
    args = parser.parse_args(argv)

    result = check_field_capture_velocity(str(args.plotfile))
    print(
        f"OK: x_velocity in [{result['x_velocity_min']:.6g}, {result['x_velocity_max']:.6g}] "
        f"(abs max {result['x_velocity_abs_max']:.6g}) -- field-capture is genuinely non-zero."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
