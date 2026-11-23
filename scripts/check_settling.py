r"""Build the settling report (OpenSpec change add-settled-beat-corpus, #192).

Thin driver over :func:`mosquito_cfd.force_surrogate.settling.build_settling_report`. It recomputes
every force-derived settling number from the committed Stage 1 datasets, checks that every
declared run record and control result is present, applies the pre-registered decision rule and
writes ``settling_report.json``.

Exit code: 0 when the report's status is ``complete``; 1 otherwise (``controls_incomplete``,
``control_failed`` or ``data_incomplete``). The report is written either way.

Usage, from the repository root::

    uv run python scripts/check_settling.py --git-commit "$(git rev-parse HEAD)"
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.settling import build_settling_report


def main(argv: Sequence[str] | None = None) -> int:
    """Write the settling report and return 0 only when it is complete."""
    parser = argparse.ArgumentParser(description="Build the settling report.")
    parser.add_argument(
        "--settling-dir", type=Path, default=Path("examples/settling_check")
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--git-commit", required=True, help="The commit the report is computed at."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Default: <settling-dir>/settling_report.json",
    )
    args = parser.parse_args(argv)
    report = build_settling_report(
        args.settling_dir, repo_root=args.repo_root, git_commit=args.git_commit
    )
    out = args.out or args.settling_dir / "settling_report.json"
    out.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"settling report: {report['status']} -> {out}")
    for line in report["missing"] + report["failed"] + report["data_missing"]:
        print(f"  {line}")
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
