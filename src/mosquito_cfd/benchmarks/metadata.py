"""Metadata capture for reproducibility."""

import hashlib
import json
import os
import re
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_WINDOWS_GITDIR_RE = re.compile(r"^([A-Za-z]):[\\/](.*)$")

# Mirrors force_surrogate.metadata_capture._FULL_SHA_RE -- kept as a separate constant (not a
# cross-module import) since these two modules have no other shared-regex precedent and
# force_surrogate already depends on benchmarks (not the reverse); duplicating one regex is
# cheaper than introducing a new inter-module coupling for it.
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

_UNKNOWN_COMMIT_SENTINEL = "unknown"  # must match docker/Dockerfile.fp64's ARG default
_SOURCE_DOCKER_BUILD_ARG = "docker-image-build-arg"


def _translate_windows_worktree_gitdir(gitdir_line: str) -> str | None:
    """Translate a Windows-style worktree ``gitdir:`` pointer line to its WSL mount path.

    A Git-for-Windows-created worktree's ``.git`` pointer file names its real gitdir with a
    drive-letter path (e.g. ``gitdir: C:/repos/mosquito-cfd/.git/worktrees/foo``), which a
    Linux ``git`` binary can't resolve as absolute. Returns ``None`` when the content isn't a
    Windows drive-letter path (e.g. it's already POSIX-style, or malformed).
    """
    content = gitdir_line.strip()
    if content.startswith("gitdir:"):
        content = content[len("gitdir:") :].strip()
    match = _WINDOWS_GITDIR_RE.match(content)
    if match is None:
        return None
    drive, rest = match.groups()
    # chr(92) is a backslash; a literal "\\" can't appear inside an f-string
    # expression on this project's target Python (3.11).
    return f"/mnt/{drive.lower()}/{rest.replace(chr(92), '/')}"


def _worktree_retry_env(repo_dir: Path) -> dict[str, str] | None:
    """Build the GIT_DIR/GIT_WORK_TREE override for a Windows-created worktree, if applicable.

    Returns ``None`` when ``repo_dir/.git`` isn't a worktree pointer file at all (missing, or a
    real gitdir directory), or when its content isn't a Windows drive-letter gitdir path.
    """
    git_pointer = repo_dir / ".git"
    try:
        # `Path.is_file()` swallows some OSErrors (ENOENT, ENOTDIR) internally but NOT
        # PermissionError/EACCES, so it must be inside this same try, not called before it.
        if not git_pointer.is_file():
            return None
        # errors="replace": a corrupted/non-UTF-8 pointer file must fail the
        # regex match below (returning None), not raise UnicodeDecodeError.
        content = git_pointer.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    translated = _translate_windows_worktree_gitdir(content)
    if translated is None:
        return None
    return {"GIT_DIR": translated, "GIT_WORK_TREE": str(repo_dir)}


def _collect_git_info(cwd: str, env: dict[str, str] | None) -> dict[str, Any]:
    """Run the git provenance commands once, against the given cwd/env.

    Raises ``subprocess.CalledProcessError`` or an ``OSError`` (e.g. ``FileNotFoundError`` if
    git isn't installed, ``NotADirectoryError`` for a bad ``cwd``) on failure — does not catch
    them, so the caller can decide whether to retry with a different ``env``.
    """
    result: dict[str, Any] = {}
    run_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "cwd": cwd,
    }
    if env is not None:
        run_kwargs["env"] = env

    # Get current commit
    commit = subprocess.run(["git", "rev-parse", "HEAD"], check=True, **run_kwargs)
    result["commit"] = commit.stdout.strip()

    # Get branch name
    branch = subprocess.run(["git", "symbolic-ref", "--short", "HEAD"], **run_kwargs)
    result["branch"] = branch.stdout.strip() if branch.returncode == 0 else "detached"

    # Check if dirty
    diff = subprocess.run(["git", "diff", "HEAD"], check=True, **run_kwargs)
    result["dirty"] = len(diff.stdout) > 0

    # Hash of diff if dirty
    if result["dirty"]:
        result["diff_hash"] = hashlib.sha256(diff.stdout.encode()).hexdigest()[:12]

    # Get remote URL
    remote = subprocess.run(["git", "remote", "get-url", "origin"], **run_kwargs)
    if remote.returncode == 0:
        result["repository"] = remote.stdout.strip()

    return result


def _baked_commit_env() -> str | None:
    """Read the build-time-baked commit SHA from ``MOSQUITO_CFD_COMMIT``, if present and valid.

    The ``:fp64`` image's Dockerfile bakes the mosquito-cfd repo's own commit into this env var
    at build time (``ARG MOSQUITO_CFD_COMMIT``, defaulting to ``"unknown"`` for an
    unparameterized local build) precisely because the image's ``COPY`` list never includes
    ``.git``, so pod-side git queries can never succeed (issue #66). Returns ``None`` for
    ``"unknown"`` (a local dev build with no ``--build-arg`` supplied) so such builds don't
    silently claim a fake commit, and also for any value that isn't a full 40-character lowercase
    hex SHA -- e.g. a misconfigured build-arg (trailing whitespace, a truncated short SHA) --
    matching the same format validation :func:`mosquito_cfd.force_surrogate.metadata_capture.
    resolve_git_info` already applies to a human-supplied ``--git-commit`` override, so this
    fallback can't silently propagate an unverifiable value into a committed provenance file any
    more than that one can.
    """
    commit = os.environ.get("MOSQUITO_CFD_COMMIT")
    if (
        not commit
        or commit == _UNKNOWN_COMMIT_SENTINEL
        or not _FULL_SHA_RE.match(commit)
    ):
        return None
    return commit


def get_git_info(repo_path: Path | None = None) -> dict[str, Any]:
    """Get git repository information for provenance tracking.

    Args:
        repo_path: Path to git repository. If None, uses current directory.

    Returns:
        Dictionary with git commit, branch, dirty status, and diff hash -- or, when git itself is
        completely unavailable and a build-time-baked commit was supplied (see below), the
        reduced ``{"commit": ..., "source": "docker-image-build-arg"}`` shape with no
        branch/dirty/diff_hash/repository keys, since none of those are knowable without an
        actual ``.git`` to inspect.

    A Windows-created git worktree's ``.git`` pointer file names its real gitdir with a
    drive-letter path that a Linux ``git`` binary (e.g. invoked from WSL) can't resolve, causing
    every command to fail as if the repo didn't exist at all. If the first attempt fails, this
    retries once with GIT_DIR/GIT_WORK_TREE translated to their WSL ``/mnt/<drive>`` mount
    equivalents (only that convention is supported; other cross-platform mount schemes are not).

    If both the direct query and that retry fail, this checks for a ``MOSQUITO_CFD_COMMIT``
    environment variable (baked into the ``:fp64`` image at build time, see
    :func:`_baked_commit_env`) before finally falling back to the existing honest error -- this is
    how a pod-side container with no ``.git`` directory at all (issue #66) still yields git
    provenance. Never raises: any OS-level failure (a missing/unreadable repo directory, a deleted
    cwd, permissions) is reported the same way as "not a repository", not propagated to the
    caller.
    """
    try:
        repo_dir = repo_path if repo_path is not None else Path.cwd()
    except OSError:
        return {"error": "git not available or not a repository"}
    cwd = str(repo_dir)

    try:
        return _collect_git_info(cwd, env=None)
    except (subprocess.CalledProcessError, OSError):
        pass

    override = _worktree_retry_env(repo_dir)
    if override is not None:
        try:
            return _collect_git_info(cwd, env={**os.environ, **override})
        except (subprocess.CalledProcessError, OSError):
            pass

    baked_commit = _baked_commit_env()
    if baked_commit is not None:
        return {"commit": baked_commit, "source": _SOURCE_DOCKER_BUILD_ARG}

    return {"error": "git not available or not a repository"}


def get_hardware_info() -> dict[str, Any]:
    """Get hardware fingerprint for reproducibility.

    Returns:
        Dictionary with hostname, GPU model, CUDA version, etc.
    """
    result = {
        "hostname": socket.gethostname(),
    }

    # Try to get NVIDIA GPU info
    try:
        nvidia_smi = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        lines = nvidia_smi.stdout.strip().split("\n")
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append(
                    {
                        "model": parts[0],
                        "memory_mb": int(parts[1]),
                        "driver_version": parts[2],
                    }
                )
        result["gpus"] = gpus
        result["gpu_count"] = len(gpus)
    except (subprocess.CalledProcessError, FileNotFoundError):
        result["gpus"] = []
        result["gpu_count"] = 0

    # Try to get CUDA version
    try:
        nvcc = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        for line in nvcc.stdout.split("\n"):
            if "release" in line.lower():
                result["cuda_version"] = line.strip()
                break
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return result


def hash_file(path: Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        path: Path to file.

    Returns:
        SHA256 hash as hex string.
    """
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def capture_run_metadata(
    inputs_file: Path | None = None,
    output_dir: Path | None = None,
    docker_image: str | None = None,
    timing: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Capture complete run metadata for reproducibility.

    Args:
        inputs_file: Path to input file (will compute hash).
        output_dir: Directory containing output files.
        docker_image: Docker image name with tag/digest.
        timing: Timing information dict (wall_time_s, timesteps, etc.).
        extra: Additional metadata to include.

    Returns:
        Complete metadata dictionary ready for JSON serialization.
    """
    metadata = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "git": get_git_info(),
        "hardware": get_hardware_info(),
    }

    if docker_image:
        metadata["docker_image"] = docker_image

    if inputs_file and inputs_file.exists():
        metadata["inputs"] = {
            "file": str(inputs_file),
            "hash": hash_file(inputs_file),
        }

    if timing:
        metadata["timing"] = timing

    if output_dir and output_dir.exists():
        # List output files
        plot_files = sorted([f.name for f in output_dir.glob("plt*") if f.is_dir()])
        chk_files = sorted([f.name for f in output_dir.glob("chk*") if f.is_dir()])
        metadata["outputs"] = {
            "directory": str(output_dir),
            "plot_files": plot_files,
            "checkpoint_files": chk_files,
        }

    # `extra` is applied LAST so callers can deliberately override built-in top-level keys — e.g.
    # the force-surrogate runner overrides `hardware` with the compute node's GPU instead of this
    # local (driver-host) probe. Do NOT reorder this before the built-ins are set, or switch to
    # `{**extra, **metadata}`: that would silently let the local hardware win and reintroduce the
    # provenance bug fixed in `fix-force-surrogate-compute-hardware`.
    if extra:
        metadata.update(extra)

    return metadata


def save_metadata(metadata: dict[str, Any], output_path: Path) -> None:
    """Save metadata to JSON file.

    Args:
        metadata: Metadata dictionary.
        output_path: Path for JSON output file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2, default=str)


def load_metadata(input_path: Path) -> dict[str, Any]:
    """Load metadata from JSON file.

    Args:
        input_path: Path to JSON metadata file.

    Returns:
        Metadata dictionary.
    """
    with open(input_path) as f:
        return json.load(f)
