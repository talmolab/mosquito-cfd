# Validate Development Environment

Check that your development environment is correctly set up and ready for mosquito-cfd development.

## Quick Start

```bash
# Run full environment validation
```

This checks:
1. Python version
2. uv installation
3. Package installation (uv.lock synced)
4. Required dependencies
5. Docker / GPU availability (for simulation work)
6. Import smoke test
7. CLI entry point

## What Gets Checked

### 1. Python Version
- Python version matches `.python-version` (3.11)
- Python version mismatch is flagged

### 2. uv Installation
- uv installed and accessible
- uv version compatible

### 3. Package Installation
- Dependencies synced via `uv.lock`
- All core dependencies present (numpy, matplotlib, pandas, yt)
- Dev dependencies present (pytest, ruff)

### 4. Docker / GPU (simulation prerequisites)
- Docker installed and daemon reachable
- NVIDIA driver present (`nvidia-smi`) for GPU simulation
- NVIDIA Container Toolkit available (`docker run --gpus all ...`)
- `ghcr.io/talmolab/mosquito-cfd:fp64` image pullable (optional)

### 5. Smoke Test
- Package can be imported
- Core modules load without errors

### 6. CLI Entry Point
- `generate-wing-planform` resolves and `--help` works

## Expected Output

### Fully Configured Environment

```
================================
Environment Validation
================================

[1/6] Python Version
OK Python 3.11 (matches .python-version)

[2/6] uv Installation
OK uv installed

[3/6] Package Installation
OK Dependencies synced from uv.lock
   Location: .venv
OK All core dependencies installed:
   numpy, matplotlib, pandas, yt
OK All dev dependencies installed:
   pytest, ruff

[4/6] Docker / GPU
OK Docker daemon reachable
OK nvidia-smi reports 1 GPU (A40)
OK --gpus all works

[5/6] Smoke Test
OK Package imports successfully

[6/6] CLI Entry Point
OK generate-wing-planform --help works

================================
ENVIRONMENT VALID
================================

Your environment is ready for development!

Next steps:
  - Run tests: uv run pytest tests/
  - Check lint/format: uv run ruff check src/ && uv run ruff format --check src/
  - Start developing!
```

### Issues Found

```
================================
Environment Validation
================================

[1/6] Python Version
OK Python 3.11.0

[2/6] uv Installation
FAIL uv not found

FIX: Install uv with:
     curl -LsSf https://astral.sh/uv/install.sh | sh

[3/6] Package Installation
SKIP (uv not available)

[4/6] Docker / GPU
WARN nvidia-smi not found (GPU simulations unavailable on this host)

================================
ENVIRONMENT HAS ISSUES
================================

Found 1 blocking issue. Fix it using the command above.
```

## Detailed Checks

### Python Version Check
```bash
uv run python --version
# Should match the version in .python-version (3.11)
```

The Python version is automatically managed by uv based on the `.python-version` file.

### Dependency Sync Check
```bash
uv sync --frozen
uv tree
# Should show all dependencies installed from uv.lock
```

### Docker / GPU Check
```bash
# Docker daemon reachable
docker info

# NVIDIA driver + GPU visible
nvidia-smi

# Container Toolkit / GPU passthrough works
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# Optional: pull the primary simulation image
docker pull ghcr.io/talmolab/mosquito-cfd:fp64
```

### Smoke Test
```python
import mosquito_cfd
print("Basic import works")
```

### CLI Entry Point
```bash
uv run generate-wing-planform --help
```

## Common Issues & Fixes

### Issue: "uv not found"

**Fix:**
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Issue: "Dependencies not synced"

**Fix:**
```bash
uv sync --frozen
```

### Issue: "nvidia-smi not found" / "could not select device driver"

**Cause:** Missing NVIDIA driver or NVIDIA Container Toolkit.

**Fix:**
```bash
# Install NVIDIA Container Toolkit (Ubuntu)
# https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

GPU is only required for running simulations/benchmarks — Python utilities and tests
run CPU-only.

### Issue: "Import errors during smoke test"

**Fix:**
```bash
# Recreate virtual environment
rm -rf .venv
uv sync --frozen
```

## When to Run This

### Initial Setup
Run after cloning the repository for the first time.

### After Environment Changes
- After updating `pyproject.toml` dependencies
- After `uv lock`
- After installing new dependencies

### Troubleshooting
- When tests fail unexpectedly
- When imports don't work
- When GPU simulations won't launch
- After switching machines

## Platform-Specific Notes

### Linux (primary — GPU host)
- Install uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- NVIDIA driver 550.54.14+ for CUDA 12.4
- NVIDIA Container Toolkit for `--gpus all`

### macOS / Windows (CPU-only)
- Python utilities and tests run fine
- GPU simulations require a Linux host with an NVIDIA GPU (local A40 / cluster / A100)

## Integration with Other Commands

```bash
# 1. First time setup
git clone https://github.com/talmolab/mosquito-cfd.git
cd mosquito-cfd

# 2. Install dependencies
uv sync --frozen

# 3. Validate environment
/validate-env
# Fix any issues it identifies

# 4. Run tests to verify
uv run pytest tests/

# 5. Start development!
```

## Related Commands

- `/run-ci-locally` - Run all CI checks (requires valid environment)
- `/lint` - Check lint and formatting
- `/coverage` - Run tests with coverage
