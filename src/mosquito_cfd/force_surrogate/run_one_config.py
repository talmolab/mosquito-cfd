"""Per-configuration pod entrypoint for the Track B force-surrogate Argo sweep.

The Argo workflow runs **each** sweep configuration as its own pod whose main process *is*
``mpirun`` (Kubernetes-managed, so there is no remote ``runai exec`` stream to drop and no
orphaned ``amr3d`` holding the GPU — the failure mode that lost 26/27 configs of the first
laptop-driven run). This module is that pod's entrypoint: it stages ``wing.vertex`` into the run
directory, invokes ``mpirun`` through an **injected runner seam** (so every code path is
unit-tested cluster-free, CC-2 — the real ``subprocess`` runner is exercised only on the cluster),
verifies completion via PR3's published :func:`check_completion`, writes the run's captured output
to ``run.log``, and writes a per-run ``run_metadata.json`` via PR3's
:func:`capture_surrogate_run_metadata`. The entrypoint exits **0 iff the run completed, else 1**,
so Argo retries an incomplete pod on a fresh GPU.

Reuse, not reinvention: the transport-agnostic PR3 runner library (``check_completion``,
``capture_surrogate_run_metadata``, ``_format_run_log``, the ``IB_PARTICLE_CSV``/``RUN_LOG``
constants, ``RunOutcome``/``ExecResult``, ``STATUS_*``) is reused unchanged. Unlike the laptop
driver (PR3 #13), this pod runs **on** the A40, so the base local ``nvidia-smi`` probe captures the
compute GPU **natively** — no in-container exec probe, hence this module deliberately does **not**
import ``capture_compute_hardware``/``build_probe_command`` and writes no ``hardware`` override.

Design decisions are in the OpenSpec change ``add-force-surrogate-argo-sweep`` (``design.md``).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate.runner import (
    DEFAULT_COMPLETION_THRESHOLD,
    DEFAULT_CONTAINER_WORKSPACE,
    DEFAULT_IAMREX_BINARY,
    DEFAULT_WING_VERTEX,
    IB_PARTICLE_CSV,
    RUN_LOG,
    STATUS_COMPLETED,
    STATUS_FAILED,
    ExecResult,
    RunOutcome,
    _format_run_log,
    check_completion,
)
from mosquito_cfd.force_surrogate.sidecar import (
    capture_surrogate_run_metadata,
    validate_image_digest,
)

logger = logging.getLogger(__name__)

# The injected runner seam: mpi_runner(argv, *, cwd) -> ExecResult. The real implementation runs
# mpirun via subprocess; tests inject a fake. Mirrors PR3's runner.Executor alias.
MpiRunner = Callable[..., ExecResult]


def _subprocess_mpi_runner(argv: list[str], *, cwd: Path) -> ExecResult:
    """The real per-pod runner: run ``argv`` to completion, capturing stdout/stderr.

    This is the only genuinely cluster-bound code path (the pod runs ``mpirun`` directly); tests
    inject a fake with the same ``(argv, *, cwd) -> ExecResult`` shape, so the module's logic is
    covered cluster-free (CC-2).

    Args:
        argv: The ``mpirun`` argv to execute.
        cwd: Working directory for the run (the per-config run dir).

    Returns:
        An :class:`ExecResult` with the process return code and captured output.
    """
    completed = subprocess.run(  # noqa: S603 - argv is constructed, not shell-interpolated
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return ExecResult(completed.returncode, completed.stdout, completed.stderr)


def _write_run_metadata(
    *,
    run_dir: Path,
    name: str,
    input_file: str,
    deck_path: Path,
    docker_digest: str,
    timestamp: str,
    command: list[str],
    rows: int,
    max_step: int,
    status: str,
    threshold: float,
    csv_name: str,
    extra_provenance: dict[str, Any] | None,
) -> Path:
    """Write a per-run ``run_metadata.json`` with portable, native-hardware provenance (CC-1).

    Records the pinned digest, caller timestamp, config name, the deck's manifest-relative path
    and SHA256, the exact ``mpirun`` command (portable ``/workspace`` paths), the
    ``rows``/``max_step``/``threshold`` that decided the verdict, and (when supplied) the Argo
    orchestrator provenance under ``orchestration``. It deliberately writes **no** ``hardware``
    override — the pod runs on the A40, so the base capture's local ``nvidia-smi`` probe is the
    correct, native compute GPU.
    """
    extra: dict[str, Any] = {
        "config": name,
        "deck": input_file,
        "deck_sha256": hash_file(deck_path) if deck_path.exists() else None,
        "command": command,
        "ib_particle_csv": f"{name}/{csv_name}",
        "log": f"{name}/{RUN_LOG}",
        "rows": rows,
        "max_step": max_step,
        "threshold": threshold,
        "status": status,
    }
    if extra_provenance:
        # Nested under a single key so orchestrator fields never collide with the provenance keys
        # above, and a reader can tell run-provenance from orchestration-provenance at a glance.
        extra["orchestration"] = dict(extra_provenance)
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_digest,
        timestamp=timestamp,
        extra=extra,
    )
    path = run_dir / "run_metadata.json"
    # newline="" → LF on every OS, so the sidecar is byte-reproducible (matches PR3).
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def run_config(
    *,
    name: str,
    input_file: str,
    max_step: int,
    output_root: Path | str,
    docker_digest: str,
    timestamp: str,
    mpi_runner: MpiRunner,
    container_workspace: str = DEFAULT_CONTAINER_WORKSPACE,
    wing_vertex: Path | str = DEFAULT_WING_VERTEX,
    deck_path: Path | str | None = None,
    iamrex_binary: str = DEFAULT_IAMREX_BINARY,
    csv_name: str = IB_PARTICLE_CSV,
    threshold: float = DEFAULT_COMPLETION_THRESHOLD,
    extra_provenance: dict[str, Any] | None = None,
) -> RunOutcome:
    """Run one sweep configuration to completion in this pod (CC-2 via the injected runner).

    Fail-fast validates the config (a non-positive ``max_step`` or an empty ``name``/``input_file``
    raises a clear ``ValueError`` naming the config — the published ``load_manifest_configs``
    validator does **not** require ``input_file``/``max_step``, so a hopeless config is rejected
    once rather than retried five times on the A40) and the pinned digest (a mutable tag is
    rejected). Then it stages ``wing.vertex`` into the run dir, invokes the injected ``mpi_runner``
    (guarding a raise as a clean failure), writes ``run.log``, re-verifies completion via
    :func:`check_completion`, and writes ``run_metadata.json`` for **both** completed and failed
    attempts.

    Args:
        name: Configuration name → run dir ``<output_root>/<name>/``.
        input_file: Deck path relative to ``container_workspace`` (recorded portably in the
            command and as the ``deck`` provenance field).
        max_step: Expected step count (drives the completion check).
        output_root: Host/in-pod directory holding the per-config run dirs (e.g. ``/workspace/runs``).
        docker_digest: Pinned ``sha256:`` container reference (a mutable tag is rejected).
        timestamp: Caller-supplied ISO-8601 timestamp recorded in ``run_metadata.json``.
        mpi_runner: Injected runner seam ``mpi_runner(argv, *, cwd) -> ExecResult``. The real
            implementation runs ``subprocess.run(mpirun ...)``; tests inject a fake.
        container_workspace: In-container mount path used to build the **portable** recorded
            ``mpirun`` deck path (default ``/workspace``).
        wing_vertex: Source path of ``wing.vertex`` staged into the run dir (the deck's
            ``geometry_file = wing.vertex`` resolves relative to the run dir).
        deck_path: Real filesystem path to the deck, used **only** to compute ``deck_sha256``.
            Defaults to ``container_workspace/input_file`` (the deck's real location in the pod);
            tests pass an explicit fixture path so the recorded command can stay portable.
        iamrex_binary: Container path of the IAMReX CUDA executable.
        csv_name: Per-run IB-particle CSV filename to verify/record (default :data:`IB_PARTICLE_CSV`).
        threshold: Completion row-count fraction (default 0.99).
        extra_provenance: Optional Argo provenance (``workflow_uid``/``pod``/``node``/``retry``),
            recorded under ``orchestration``.

    Returns:
        A :class:`RunOutcome` (``status`` is ``"completed"`` iff the runner returned 0 *and* the
        CSV passes :func:`check_completion`, else ``"failed"``); ``run_metadata.json`` is written
        either way.

    Raises:
        ValueError: On an empty ``name``/``input_file``, a non-positive/non-integer ``max_step``,
            or a missing/mutable ``docker_digest`` — all before any runner invocation.
    """
    if not str(name).strip():
        raise ValueError("config name is empty; a configuration must be named")
    if not str(input_file).strip():
        raise ValueError(
            f"config {name!r} has an empty input_file; cannot locate the deck"
        )
    try:
        max_step = int(max_step)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"config {name!r} has non-integer max_step={max_step!r}"
        ) from exc
    if max_step <= 0:
        raise ValueError(
            f"config {name!r} has max_step={max_step!r}; must be a positive integer "
            "(a non-positive max_step can never satisfy the completion check)"
        )
    # Digest fail-fast: reject a mutable tag before staging or running anything.
    validate_image_digest(docker_digest)

    output_root = Path(output_root)
    run_dir = output_root / name
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / csv_name
    if deck_path is None:
        deck_path = Path(container_workspace) / input_file
    deck_path = Path(deck_path)

    deck_container = f"{container_workspace}/{input_file}"
    argv = [
        "mpirun",
        "--allow-run-as-root",
        "-np",
        "1",
        iamrex_binary,
        deck_container,
    ]

    # Staging the geometry and the run are guarded together: a missing `wing.vertex` source (a
    # partial-mount / setup error) or an injected runner that *raises* (the real subprocess hitting a
    # missing binary or a transient OSError) both become a clean failed run with the exception in
    # run.log — not an uncaught traceback with no audit artifact. Argo retries on a fresh pod, and
    # `verify-complete` still gates the corpus. Exception (not BaseException) so KeyboardInterrupt
    # propagates. (The Argo `validate` step preflights `wing.vertex` once before the fan-out, so a
    # globally-missing geometry fails the workflow in seconds rather than 27 × retries here.)
    try:
        # Stage wing.vertex into the run dir (the deck resolves geometry_file relative to cwd).
        shutil.copyfile(wing_vertex, run_dir / "wing.vertex")
        result = mpi_runner(argv, cwd=run_dir)
    except Exception as exc:
        logger.warning(
            "config %r staging/runner failed %r; recording failed", name, exc
        )
        result = ExecResult(returncode=1, stderr=repr(exc))

    # newline="" → LF on every OS. Overwrites in place on an Argo retry (last write wins).
    (run_dir / RUN_LOG).write_text(
        _format_run_log(result), encoding="utf-8", newline=""
    )

    post = check_completion(csv_path, max_step, threshold=threshold)
    if result.returncode != 0 or not post.complete:
        status = STATUS_FAILED
        logger.warning(
            "config %r FAILED (returncode=%s, completion=%s rows=%d/%d)",
            name,
            result.returncode,
            post.reason,
            post.rows,
            max_step,
        )
    else:
        status = STATUS_COMPLETED

    metadata_path = _write_run_metadata(
        run_dir=run_dir,
        name=name,
        input_file=str(input_file),
        deck_path=deck_path,
        docker_digest=docker_digest,
        timestamp=timestamp,
        command=argv,
        rows=post.rows,
        max_step=max_step,
        status=status,
        threshold=threshold,
        csv_name=csv_name,
        extra_provenance=extra_provenance,
    )
    return RunOutcome(name, status, csv_path, post.rows, metadata_path)


def main(argv: list[str] | None = None, *, mpi_runner: MpiRunner | None = None) -> int:
    """CLI entrypoint: run one configuration; exit 0 iff completed, else 1 (the Argo retry signal).

    When ``mpi_runner`` is ``None`` the real :func:`_subprocess_mpi_runner` is used (so the pod runs
    ``mpirun`` directly); tests inject a fake, so ``main`` is unit-testable cluster-free.

    Args:
        argv: Argument vector (defaults to ``sys.argv[1:]``).
        mpi_runner: Optional injected runner seam (tests pass a fake).

    Returns:
        ``0`` if the configuration completed, else ``1``.
    """
    parser = argparse.ArgumentParser(
        description="Run one force-surrogate sweep configuration in this pod."
    )
    parser.add_argument("--config-name", required=True)
    parser.add_argument("--input-file", required=True)
    parser.add_argument("--max-step", required=True, type=int)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--docker-digest", required=True)
    parser.add_argument("--timestamp", required=True)
    parser.add_argument("--container-workspace", default=DEFAULT_CONTAINER_WORKSPACE)
    parser.add_argument("--wing-vertex", default=DEFAULT_WING_VERTEX)
    parser.add_argument("--deck-path", default=None)
    parser.add_argument("--iamrex-binary", default=DEFAULT_IAMREX_BINARY)
    # Escape hatch (mirrors PR3's run_sweep --csv-name): IB_Particle_1.csv is the assumed force-CSV
    # name and is not yet verified against a real IAMReX run; a wrong guess costs a flag, not a corpus.
    parser.add_argument("--csv-name", default=IB_PARTICLE_CSV)
    parser.add_argument("--threshold", type=float, default=DEFAULT_COMPLETION_THRESHOLD)
    # Argo orchestrator provenance (optional; recorded under run_metadata "orchestration").
    parser.add_argument("--workflow-uid", default=None)
    parser.add_argument("--pod", default=None)
    parser.add_argument("--node", default=None)
    parser.add_argument("--retry", default=None)
    args = parser.parse_args(argv)

    if mpi_runner is None:
        mpi_runner = _subprocess_mpi_runner

    extra_provenance = {
        key: value
        for key, value in (
            ("workflow_uid", args.workflow_uid),
            ("pod", args.pod),
            ("node", args.node),
            ("retry", args.retry),
        )
        if value is not None
    }

    outcome = run_config(
        name=args.config_name,
        input_file=args.input_file,
        max_step=args.max_step,
        output_root=args.output_root,
        docker_digest=args.docker_digest,
        timestamp=args.timestamp,
        mpi_runner=mpi_runner,
        container_workspace=args.container_workspace,
        wing_vertex=args.wing_vertex,
        deck_path=args.deck_path,
        iamrex_binary=args.iamrex_binary,
        csv_name=args.csv_name,
        threshold=args.threshold,
        extra_provenance=extra_provenance or None,
    )
    return 0 if outcome.status == STATUS_COMPLETED else 1


if __name__ == "__main__":  # pragma: no cover - thin CLI shim
    raise SystemExit(main())
