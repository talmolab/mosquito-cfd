r"""Render the settling figure (OpenSpec change add-settled-beat-corpus, #192).

Thin driver over :mod:`mosquito_cfd.force_surrogate.settling_figure`. Reads
``settling_report.json`` and writes, in ``--out-dir``:

- ``settling_figure.png``;
- ``settling_figure_metrics.json``: every plotted number (the figure's table view);
- ``settling_figure_run_metadata.json``: the report's SHA-256, the renderer's SHA-256, the git
  commit and timestamp supplied by the caller, and the PNG's SHA-256.

Usage, from the repository root::

    uv run python scripts/make_settling_figure.py \
        --report examples/settling_check/settling_report.json \
        --out-dir examples/settling_check \
        --git-commit "$(git rev-parse HEAD)" --timestamp 2026-12-01T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate import settling_figure

REPO = Path(__file__).resolve().parents[1]
RENDERERS = (
    "scripts/make_settling_figure.py",
    "src/mosquito_cfd/force_surrogate/settling_figure.py",
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    """Render the figure and write its two JSON sidecars."""
    parser = argparse.ArgumentParser(description="Render the settling figure.")
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--git-commit", required=True)
    parser.add_argument(
        "--timestamp", required=True, help="Caller-supplied ISO-8601 time."
    )
    args = parser.parse_args(argv)

    report_bytes = args.report.read_bytes()
    report = json.loads(report_bytes)
    metrics = settling_figure.figure_metrics(report)
    fig = settling_figure.render(report)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    png = args.out_dir / "settling_figure.png"
    fig.savefig(
        png, dpi=150, facecolor=fig.get_facecolor(), metadata={"Software": None}
    )
    (args.out_dir / "settling_figure_metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    meta = {
        "report_sha256": _sha(report_bytes),
        "renderer_sha256": {rel: _sha((REPO / rel).read_bytes()) for rel in RENDERERS},
        "git_commit": args.git_commit,
        "timestamp": args.timestamp,
        "png_sha256": _sha(png.read_bytes()),
    }
    (args.out_dir / "settling_figure_run_metadata.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
