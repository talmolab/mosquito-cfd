"""Metadata capture for reproducibility."""

import hashlib
import json
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def get_git_info(repo_path: Path | None = None) -> dict[str, Any]:
    """Get git repository information for provenance tracking.

    Args:
        repo_path: Path to git repository. If None, uses current directory.

    Returns:
        Dictionary with git commit, branch, dirty status, and diff hash.
    """
    cwd = str(repo_path) if repo_path else None
    result = {}

    try:
        # Get current commit
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=True,
        )
        result["commit"] = commit.stdout.strip()

        # Get branch name
        branch = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        result["branch"] = branch.stdout.strip() if branch.returncode == 0 else "detached"

        # Check if dirty
        diff = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=True,
        )
        result["dirty"] = len(diff.stdout) > 0

        # Hash of diff if dirty
        if result["dirty"]:
            result["diff_hash"] = hashlib.sha256(diff.stdout.encode()).hexdigest()[:12]

        # Get remote URL
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if remote.returncode == 0:
            result["repository"] = remote.stdout.strip()

    except (subprocess.CalledProcessError, FileNotFoundError):
        result["error"] = "git not available or not a repository"

    return result


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
            check=True,
        )
        lines = nvidia_smi.stdout.strip().split("\n")
        gpus = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                gpus.append({
                    "model": parts[0],
                    "memory_mb": int(parts[1]),
                    "driver_version": parts[2],
                })
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