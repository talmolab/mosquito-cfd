#!/usr/bin/env python3
"""
Capture simulation metadata for reproducibility.

Usage:
    uv run python -m mosquito_cfd.run_metadata --input inputs.3d --output run_metadata.json
"""

import argparse
import hashlib
import json
import os
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path


def get_git_commit() -> str | None:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except FileNotFoundError:
        return None


def get_gpu_info() -> dict | None:
    """Get GPU information from nvidia-smi."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {
                "name": parts[0] if len(parts) > 0 else None,
                "driver_version": parts[1] if len(parts) > 1 else None,
                "memory_mb": int(parts[2]) if len(parts) > 2 else None,
            }
    except FileNotFoundError:
        pass
    return None


def get_cuda_version() -> str | None:
    """Get CUDA version from nvcc."""
    try:
        result = subprocess.run(
            ["nvcc", "--version"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "release" in line.lower():
                    parts = line.split("release")
                    if len(parts) > 1:
                        return parts[1].strip().split(",")[0].strip()
    except FileNotFoundError:
        pass
    return None


def hash_file(filepath: str | Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def create_metadata(
    input_file: str | Path,
    executable: str | Path | None = None,
    wall_time_s: float | None = None,
    timesteps: int | None = None,
) -> dict:
    """Create metadata dictionary."""
    input_path = Path(input_file)

    metadata = {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": get_git_commit(),
        "input_file": str(input_file),
        "input_file_hash": hash_file(input_path) if input_path.exists() else None,
        "build_config": {
            "precision": os.environ.get("PRECISION", "unknown"),
            "cuda_arch": os.environ.get("CUDA_ARCH", "unknown"),
            "use_mpi": os.environ.get("USE_MPI", "unknown"),
        },
        "hardware": {
            "gpu": get_gpu_info(),
            "cuda_version": get_cuda_version(),
            "hostname": os.uname().nodename if hasattr(os, "uname") else None,
        },
    }

    if wall_time_s is not None and timesteps is not None:
        metadata["timing"] = {
            "wall_time_s": wall_time_s,
            "timesteps": timesteps,
            "s_per_step": wall_time_s / timesteps if timesteps > 0 else None,
        }

    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture simulation metadata")
    parser.add_argument("--input", "-i", required=True, help="Input file path")
    parser.add_argument("--output", "-o", default="run_metadata.json", help="Output JSON path")
    parser.add_argument("--executable", "-e", help="Executable path")
    parser.add_argument("--wall-time", type=float, help="Wall time in seconds")
    parser.add_argument("--timesteps", type=int, help="Number of timesteps completed")

    args = parser.parse_args()

    metadata = create_metadata(
        input_file=args.input,
        executable=args.executable,
        wall_time_s=args.wall_time,
        timesteps=args.timesteps,
    )

    with open(args.output, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"Metadata written to {args.output}")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
