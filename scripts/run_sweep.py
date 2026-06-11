r"""Run the force-surrogate kinematic sweep on a RunAI A40 workspace.

Thin driver over :mod:`mosquito_cfd.force_surrogate.runner` (all logic lives in the tested
library). It loops the committed corpus (``examples/prelim_sweep/sweep_manifest.json``) through
the pinned ``:fp64`` container on one long-lived RunAI A40 workspace, writing each run's
IB-particle force CSV to ``<output-root>/<name>/IB_Particle_1.csv`` (PR4's
``scripts/extract_forces.py`` driver contract) plus a per-run ``run_metadata.json``.

This module is the **only** place ``subprocess``/WSL/``KUBECONFIG`` live: the real executor wraps
each logical RunAI command with :func:`build_wsl_command` and runs it via ``subprocess.run``. For
testing, :func:`main` accepts an injected ``executor`` so the smoke test runs cluster-free.

Operator usage (after staging ``wing.vertex`` at the mount root — see the prelim_sweep README)::

    uv run python scripts/run_sweep.py \\
        --manifest examples/prelim_sweep/sweep_manifest.json \\
        --output-root /mnt/hpi_dev/users/eberrigan/mosquito-cfd/examples/prelim_sweep/runs \\
        --workspace force-sweep \\
        --docker-digest ghcr.io/talmolab/mosquito-cfd@sha256:<64hex> \\
        --timestamp 2026-06-30T00:00:00+00:00
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from pathlib import Path

from mosquito_cfd.force_surrogate.runner import (
    DEFAULT_COMPLETION_THRESHOLD,
    DEFAULT_CONTAINER_WORKSPACE,
    DEFAULT_IAMREX_BINARY,
    DEFAULT_RUNS_SUBDIR,
    DEFAULT_WING_VERTEX,
    IB_PARTICLE_CSV,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_SKIPPED,
    ExecResult,
    Executor,
    build_wsl_command,
    run_sweep,
)

# Operator defaults for the Salk RunAI cluster (overridable via CLI). The kubeconfig + runai
# binary paths follow the documented WSL workflow (openspec/runai-dev-workflow.md).
DEFAULT_KUBECONFIG = "~/.kube/kubeconfig-runai-talmo-lab.yaml"
DEFAULT_RUNAI_BINARY = "/home/elizabeth/.runai/bin/runai"


def _make_wsl_executor(kubeconfig: str, runai_binary: str) -> Executor:
    """Build the real WSL executor (the only ``subprocess.run`` shell-out in this program)."""

    def _executor(command: Sequence[str], *, cwd: Path | str) -> ExecResult:
        wsl_command = build_wsl_command(
            command, kubeconfig=kubeconfig, runai_binary=runai_binary
        )
        # Fixed argv, no shell=True; operator-invoked against a trusted cluster.
        proc = subprocess.run(wsl_command, capture_output=True, text=True, cwd=str(cwd))
        return ExecResult(proc.returncode, proc.stdout, proc.stderr)

    return _executor


def main(argv: Sequence[str] | None = None, *, executor: Executor | None = None) -> int:
    """Run the sweep and report per-config outcomes.

    Args:
        argv: Optional argument vector (defaults to ``sys.argv[1:]``).
        executor: Optional injected executor (``executor(command, *, cwd) -> ExecResult``);
            when ``None`` the real WSL/``subprocess`` executor is built. Tests inject a fake so
            the driver runs cluster-free.

    Returns:
        Process exit code: 0 if every configuration completed or was skipped, 1 if any failed.
    """
    parser = argparse.ArgumentParser(
        description="Run the force-surrogate sweep corpus on a RunAI A40 workspace."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Cluster-mount dir holding per-config run output (<root>/<name>/IB_Particle_1.csv).",
    )
    parser.add_argument(
        "--workspace", required=True, help="RunAI workspace name to exec into."
    )
    parser.add_argument(
        "--docker-digest",
        required=True,
        help="Pinned image pin, e.g. ghcr.io/talmolab/mosquito-cfd@sha256:<64hex>.",
    )
    parser.add_argument(
        "--timestamp", required=True, help="Caller-supplied ISO-8601 timestamp."
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-run every config even if its CSV already passes the completion check.",
    )
    parser.add_argument("--threshold", type=float, default=DEFAULT_COMPLETION_THRESHOLD)
    parser.add_argument(
        "--csv-name",
        default=IB_PARTICLE_CSV,
        help=(
            "Per-run IB-particle force CSV filename to verify (default IB_Particle_1.csv; "
            "override if the solver writes a different name, e.g. forces.csv)."
        ),
    )
    parser.add_argument("--container-workspace", default=DEFAULT_CONTAINER_WORKSPACE)
    parser.add_argument("--runs-subdir", default=DEFAULT_RUNS_SUBDIR)
    parser.add_argument("--wing-vertex", default=DEFAULT_WING_VERTEX)
    parser.add_argument("--iamrex-binary", default=DEFAULT_IAMREX_BINARY)
    parser.add_argument("--kubeconfig", default=DEFAULT_KUBECONFIG)
    parser.add_argument("--runai-binary", default=DEFAULT_RUNAI_BINARY)
    args = parser.parse_args(argv)

    run_executor = executor
    if run_executor is None:
        run_executor = _make_wsl_executor(args.kubeconfig, args.runai_binary)

    outcomes = run_sweep(
        args.manifest,
        args.output_root,
        docker_digest=args.docker_digest,
        timestamp=args.timestamp,
        executor=run_executor,
        workspace=args.workspace,
        resume=not args.no_resume,
        threshold=args.threshold,
        csv_name=args.csv_name,
        container_workspace=args.container_workspace,
        runs_subdir=args.runs_subdir,
        wing_vertex=args.wing_vertex,
        iamrex_binary=args.iamrex_binary,
    )

    for outcome in outcomes:
        print(f"{outcome.name}: {outcome.status} ({outcome.rows} rows)")
    failed = [o for o in outcomes if o.status == STATUS_FAILED]
    completed = sum(o.status == STATUS_COMPLETED for o in outcomes)
    skipped = sum(o.status == STATUS_SKIPPED for o in outcomes)
    print(
        f"{len(outcomes)} configs: {completed} completed, {skipped} skipped, "
        f"{len(failed)} failed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
