"""RunAI A40 sweep runner for the Track B force-surrogate program (PR3).

Loops PR2's committed kinematic-sweep corpus (``examples/prelim_sweep/sweep_manifest.json``)
through the pinned ``:fp64`` IAMReX container on one RunAI A40 workspace, writing each run's
IB-particle force CSV to ``<output-root>/<name>/IB_Particle_1.csv`` — exactly PR4's
``scripts/extract_forces.py`` driver contract — plus a per-run ``run_metadata.json``, and
verifying completion.

The cluster launch is an **injected executor** (see :func:`run_sweep`), so every code path in
this module is unit-tested **cluster-free** (CC-2): no RunAI, GPU, or container is touched by the
library. The real WSL/``subprocess`` executor lives only in the thin driver
``scripts/run_sweep.py``; this module never imports ``subprocess``.

Force-only (CC-6): only the IB-particle CSV is produced/consumed — no plotfiles or
velocity/pressure fields (every deck keeps ``amr.plot_int = -1``). Design decisions are in the
OpenSpec change ``add-force-surrogate-sweep-runner`` (``design.md``).
"""

from __future__ import annotations

import json
import logging
import math
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from mosquito_cfd.benchmarks.metadata import hash_file
from mosquito_cfd.force_surrogate.dataset import (
    IB_PARTICLE_COLUMNS,
    load_manifest_configs,
)
from mosquito_cfd.force_surrogate.sidecar import (
    capture_surrogate_run_metadata,
    validate_image_digest,
)

logger = logging.getLogger(__name__)

# Container/runtime defaults. Container paths are portable (every operator's mount maps to
# ``/workspace``); the WSL + KUBECONFIG + absolute-runai wrapping is the driver's concern.
DEFAULT_CONTAINER_WORKSPACE = "/workspace"
DEFAULT_RUNS_SUBDIR = "runs"
DEFAULT_IAMREX_BINARY = "/opt/cfd/IAMReX/Tutorials/FlowPastSphere/amr3d.gnu.MPI.CUDA.ex"
DEFAULT_WING_VERTEX = "/workspace/wing.vertex"
# IAMReX's actual per-run IB-particle CSV name (PR4's extract_forces.py driver contract).
IB_PARTICLE_CSV = "IB_Particle_1.csv"
DEFAULT_COMPLETION_THRESHOLD = 0.99


@dataclass(frozen=True)
class ExecResult:
    """Result of one injected-executor invocation.

    Attributes:
        returncode: Process return code (0 = the container command exited cleanly).
        stdout: Captured standard output (optional).
        stderr: Captured standard error (optional).
    """

    returncode: int
    stdout: str = ""
    stderr: str = ""


# The injected cluster-launch seam: ``executor(command, *, cwd) -> ExecResult``. The real
# implementation (driver) runs the command via WSL/subprocess; tests inject a fake.
Executor = Callable[..., ExecResult]


@dataclass(frozen=True)
class Completion:
    """Outcome of a per-run completion check.

    Attributes:
        complete: True iff the CSV exists, has the 29-column header, and has at least
            ``ceil(max_step * threshold)`` data rows.
        rows: Number of data rows counted (0 if missing/empty).
        reason: One of ``"ok"``, ``"missing"``, ``"empty"``, ``"short"``, ``"bad_header"``.
    """

    complete: bool
    rows: int
    reason: str


@dataclass(frozen=True)
class RunOutcome:
    """Outcome of one configuration in a sweep.

    Attributes:
        name: Configuration name.
        status: One of ``"completed"``, ``"skipped"`` (resume), ``"failed"``.
        csv_path: Host path to the configuration's IB-particle CSV.
        rows: Data-row count of that CSV after the run (0 if missing).
        metadata_path: Path to the written ``run_metadata.json`` (None for a skipped config).
    """

    name: str
    status: str
    csv_path: Path
    rows: int
    metadata_path: Path | None


def build_run_command(
    config: Mapping[str, object],
    *,
    workspace: str,
    container_workspace: str = DEFAULT_CONTAINER_WORKSPACE,
    runs_subdir: str = DEFAULT_RUNS_SUBDIR,
    wing_vertex: str = DEFAULT_WING_VERTEX,
    iamrex_binary: str = DEFAULT_IAMREX_BINARY,
) -> list[str]:
    """Build the RunAI ``workspace exec`` command for one configuration (pure, no I/O).

    The command runs the validated IAMReX launch with the working directory set to the
    per-configuration run dir ``<container_workspace>/<runs_subdir>/<name>`` so IAMReX writes
    ``IB_Particle_1.csv`` there (which the mount maps to ``<output-root>/<name>/``). ``wing.vertex``
    is staged into the run dir because the deck's ``particle_inputs.geometry_file = wing.vertex``
    is resolved relative to the working directory.

    Args:
        config: A sweep-manifest configuration; must carry ``name`` and ``input_file``.
        workspace: The RunAI workspace name to exec into.
        container_workspace: Container path of the mounted workspace (default ``/workspace``).
        runs_subdir: Per-config output subdir under the workspace (default ``runs``).
        wing_vertex: Container path of the staged ``wing.vertex`` (default ``/workspace/wing.vertex``).
        iamrex_binary: Container path of the IAMReX CUDA executable.

    Returns:
        The command as an argv list:
        ``["runai", "workspace", "exec", <workspace>, "--", "sh", "-c", <inner>]``.

    Raises:
        ValueError: If ``config`` has no ``input_file`` (the published manifest validator does
            not require it, so the runner checks it explicitly rather than emitting a malformed
            command).
    """
    name = str(config["name"])
    if "input_file" not in config:
        raise ValueError(
            f"config {name!r} has no 'input_file'; the sweep-manifest validator does not "
            "require it, so the runner cannot build a launch command without it"
        )
    input_file = str(config["input_file"])
    container_run_dir = f"{container_workspace}/{runs_subdir}/{name}"
    deck = f"{container_workspace}/{input_file}"
    inner = (
        "set -e; "
        f"mkdir -p {shlex.quote(container_run_dir)}; "
        f"cp {shlex.quote(wing_vertex)} {shlex.quote(container_run_dir + '/wing.vertex')}; "
        f"cd {shlex.quote(container_run_dir)}; "
        f"mpirun --allow-run-as-root -np 1 {shlex.quote(iamrex_binary)} {shlex.quote(deck)}"
    )
    return ["runai", "workspace", "exec", workspace, "--", "sh", "-c", inner]


def check_completion(
    csv_path: Path | str,
    max_step: int,
    *,
    threshold: float = DEFAULT_COMPLETION_THRESHOLD,
) -> Completion:
    r"""Verify a configuration's IB-particle CSV is complete.

    A CSV is complete iff it exists, its first line equals the 29-column IB-particle schema
    (:data:`IB_PARTICLE_COLUMNS`), and it has at least ``ceil(max_step * threshold)`` data rows.
    Row counting uses universal-newline handling so ``\r\n`` counts the same as ``\n`` and a
    trailing newline does not add a phantom row (cross-platform).

    Args:
        csv_path: Host path to the IB-particle CSV.
        max_step: The configuration's expected step count.
        threshold: Fraction of ``max_step`` rows required to pass (default 0.99).

    Returns:
        A :class:`Completion` (``complete``, ``rows``, ``reason``). A missing path is incomplete
        (``reason="missing"``) rather than an error — that is the resume signal.
    """
    path = Path(csv_path)
    if not path.exists():
        return Completion(False, 0, "missing")
    # splitlines() collapses \n and \r\n identically and ignores a single trailing newline,
    # so the count is platform-independent (never a raw \n-tally).
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return Completion(False, 0, "empty")
    # Strict, order-sensitive schema gate: the runner is the *producer* and verifies IAMReX
    # wrote the exact 29-column canonical header. (PR4's extractor reads name-based / order-
    # insensitive downstream; the runner deliberately enforces the canonical order here so a
    # solver-side schema change is caught at the source rather than silently consumed.)
    if lines[0].split(",") != IB_PARTICLE_COLUMNS:
        return Completion(False, max(len(lines) - 1, 0), "bad_header")
    rows = len(lines) - 1
    if rows == 0:
        return Completion(False, 0, "empty")
    required = math.ceil(max_step * threshold)
    if rows < required:
        return Completion(False, rows, "short")
    return Completion(True, rows, "ok")


def build_wsl_command(
    command: Sequence[str],
    *,
    kubeconfig: str,
    runai_binary: str,
) -> list[str]:
    """Wrap a logical ``runai`` command for execution via WSL (pure, no subprocess).

    Produces ``["wsl", "-e", "bash", "-c", <payload>]`` where ``<payload>`` exports
    ``KUBECONFIG`` and invokes the operator's **absolute** ``runai`` binary (replacing the
    logical ``"runai"`` argv[0]). Each argument is shell-quoted via :func:`shlex.join` so an
    inner ``sh -c "<script>"`` argument keeps its grouping. This is the only genuinely
    cluster-bound string construction; isolating it here keeps it unit-tested, leaving only the
    driver's single ``subprocess.run`` call outside CI coverage.

    Args:
        command: The logical command from :func:`build_run_command` (argv[0] == ``"runai"``).
        kubeconfig: Path to the RunAI kubeconfig (exported as ``KUBECONFIG``).
        runai_binary: Absolute path to the ``runai`` binary inside WSL.

    Returns:
        The WSL argv list to hand to ``subprocess.run``.
    """
    argv = list(command)
    if argv and argv[0] == "runai":
        argv = [runai_binary, *argv[1:]]
    payload = f"export KUBECONFIG={shlex.quote(kubeconfig)}; {shlex.join(argv)}"
    return ["wsl", "-e", "bash", "-c", payload]


def _write_run_metadata(
    *,
    run_dir: Path,
    config: Mapping[str, object],
    manifest_dir: Path,
    docker_digest: str,
    timestamp: str,
    command: list[str],
    rows: int,
    status: str,
    threshold: float,
) -> Path:
    """Write a per-run ``run_metadata.json`` with portable provenance (CC-1).

    Records the pinned digest, caller timestamp, config name, the deck's manifest-relative path
    and SHA256, the exact logical command (portable container paths), and the ``rows``/``max_step``/
    ``threshold`` that decided the completion verdict (so a ``completed``/``failed`` ``status`` is
    self-describing). It deliberately does NOT pass ``inputs_file=``/``output_dir=`` to the base
    capture (which would record absolute host paths); the portable fields go through ``extra=``.
    """
    name = str(config["name"])
    input_file = str(config["input_file"])
    deck_host = manifest_dir / input_file
    extra = {
        "config": name,
        "deck": input_file,
        "deck_sha256": hash_file(deck_host) if deck_host.exists() else None,
        "command": command,
        "ib_particle_csv": f"{name}/{IB_PARTICLE_CSV}",
        "rows": rows,
        "max_step": int(config["max_step"]),  # type: ignore[arg-type]
        "threshold": threshold,
        "status": status,
    }
    metadata = capture_surrogate_run_metadata(
        docker_image_digest=docker_digest,
        timestamp=timestamp,
        extra=extra,
    )
    path = run_dir / "run_metadata.json"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return path


def run_sweep(
    manifest_path: Path | str,
    output_root: Path | str,
    *,
    docker_digest: str,
    timestamp: str,
    executor: Executor,
    workspace: str,
    resume: bool = True,
    threshold: float = DEFAULT_COMPLETION_THRESHOLD,
    container_workspace: str = DEFAULT_CONTAINER_WORKSPACE,
    runs_subdir: str = DEFAULT_RUNS_SUBDIR,
    wing_vertex: str = DEFAULT_WING_VERTEX,
    iamrex_binary: str = DEFAULT_IAMREX_BINARY,
) -> list[RunOutcome]:
    """Run the sweep corpus through the container, one configuration at a time (CC-1/CC-2).

    Fail-fast up front (before any run): validates the pinned digest (via
    :func:`capture_surrogate_run_metadata`), duplicate config names (via
    :func:`load_manifest_configs`), and each config's ``input_file``/``max_step`` presence (the
    published manifest validator does not require these — a bare ``KeyError`` deep in the loop
    would otherwise waste A40 time). Then per configuration: skip it if already complete (resume),
    else invoke ``executor`` with ``cwd`` set to the host per-config dir, re-verify completion
    (authoritative over the return code), and write a ``run_metadata.json``.

    Args:
        manifest_path: Path to ``sweep_manifest.json``.
        output_root: Host directory (cluster mount) holding the per-config run dirs.
        docker_digest: Pinned ``sha256:`` container reference (a mutable tag is rejected).
        timestamp: Caller-supplied ISO-8601 timestamp recorded in every ``run_metadata.json``.
        executor: The injected cluster-launch seam ``executor(command, *, cwd) -> ExecResult``.
        workspace: RunAI workspace name to exec into.
        resume: If True (default), skip configs whose CSV already passes the completion check.
        threshold: Completion row-count fraction (default 0.99).
        container_workspace: Container path of the mounted workspace.
        runs_subdir: Per-config output subdir name under the workspace.
        wing_vertex: Container path of the staged ``wing.vertex``.
        iamrex_binary: Container path of the IAMReX CUDA executable.

    Returns:
        One :class:`RunOutcome` per configuration, in manifest order.

    Raises:
        ValueError: On a missing/mutable digest, duplicate config names, or a config missing
            ``input_file``/``max_step`` — all before any executor call.
    """
    output_root = Path(output_root)
    manifest_path = Path(manifest_path)

    # 1. Digest fail-fast: a pure regex guard (no git/hardware probe) before any run.
    validate_image_digest(docker_digest)
    # 2. Manifest fail-fast: duplicate names + base keys (load_manifest_configs); then the
    #    runner-required keys the published validator does not check.
    configs = load_manifest_configs(manifest_path)
    for config in configs:
        name = str(config["name"])
        for key in ("input_file", "max_step"):
            if key not in config:
                raise ValueError(
                    f"config {name!r} is missing required key {key!r}; the sweep-manifest "
                    "validator does not require it, but the runner needs it to launch/verify "
                    "the run"
                )
        if int(config["max_step"]) <= 0:
            raise ValueError(
                f"config {name!r} has max_step={config['max_step']!r}; must be a positive "
                "integer (a non-positive max_step can never satisfy the completion check)"
            )

    manifest_dir = manifest_path.parent
    outcomes: list[RunOutcome] = []
    for config in configs:
        name = str(config["name"])
        max_step = int(config["max_step"])
        run_dir = output_root / name
        csv_path = run_dir / IB_PARTICLE_CSV

        if resume:
            pre = check_completion(csv_path, max_step, threshold=threshold)
            if pre.complete:
                logger.info(
                    "config %r already complete (%d rows); skipping (resume)",
                    name,
                    pre.rows,
                )
                outcomes.append(RunOutcome(name, "skipped", csv_path, pre.rows, None))
                continue

        run_dir.mkdir(parents=True, exist_ok=True)
        command = build_run_command(
            config,
            workspace=workspace,
            container_workspace=container_workspace,
            runs_subdir=runs_subdir,
            wing_vertex=wing_vertex,
            iamrex_binary=iamrex_binary,
        )
        # Resilience: an executor that *raises* (e.g. the real WSL/subprocess executor hitting a
        # transient cluster error, or `wsl` not found) must not abort the unattended corpus — it
        # is recorded as a failed run (returncode 1) and the loop continues, exactly like a
        # nonzero return. Exception (not BaseException) so KeyboardInterrupt still propagates.
        try:
            result = executor(command, cwd=run_dir)
        except Exception as exc:
            logger.warning(
                "config %r executor raised %r; recording failed and continuing",
                name,
                exc,
            )
            result = ExecResult(returncode=1, stderr=repr(exc))
        post = check_completion(csv_path, max_step, threshold=threshold)
        if result.returncode != 0 or not post.complete:
            status = "failed"
            logger.warning(
                "config %r FAILED (returncode=%s, completion=%s rows=%d/%d); continuing to "
                "the next config",
                name,
                result.returncode,
                post.reason,
                post.rows,
                max_step,
            )
        else:
            status = "completed"

        metadata_path = _write_run_metadata(
            run_dir=run_dir,
            config=config,
            manifest_dir=manifest_dir,
            docker_digest=docker_digest,
            timestamp=timestamp,
            command=command,
            rows=post.rows,
            status=status,
            threshold=threshold,
        )
        outcomes.append(RunOutcome(name, status, csv_path, post.rows, metadata_path))

    return outcomes
